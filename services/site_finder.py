"""
services/site_finder.py — Retrouver le site d'une entreprise absent de sa fiche Google.

Le champ « site web » de Google Maps est souvent vide alors que l'entreprise a un
site. On devine quelques domaines à partir du nom (« AZ Energy » → azenergy.fr,
az-energy.com, azenergy.lu…), on les charge, et on ne retient un domaine que si
la page CONFIRME l'entreprise (nom complet ou numéro de téléphone présent).

Pas de scraping de Google (interdit par ses CGU) : uniquement des requêtes
directes vers les domaines devinés, peu nombreuses, avec délai court.

HYPOTHÈSE : beaucoup de petits sites ont un domaine dérivé du nom ; ceux qui
ont un nom de domaine sans rapport ne seront pas retrouvés (faux « sans site »).
"""

from __future__ import annotations

import ipaddress
import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import requests

from trades import normalize

FRENCH_TLDS = ("fr", "com")
FOREIGN_TLDS = ("lu", "be", "ch")       # proches de la France : activité frontalière fréquente
TIMEOUT_S = 5
MAX_BYTES = 300_000                      # on ne lit jamais plus de 300 Ko par page
_USER_AGENT = "Mozilla/5.0 (compatible; ProspectBot/1.0)"

_LEGAL_WORDS = {"sarl", "sas", "sasu", "eurl", "sa", "sci", "ets", "etablissements", "entreprise", "ste", "societe"}
_STOP_WORDS = {"le", "la", "les", "l", "de", "des", "du", "d", "et", "a", "au", "aux", "en"}


def _name_tokens(name: str) -> List[str]:
    return [t for t in normalize(name).split() if t not in _LEGAL_WORDS | _STOP_WORDS]


def candidate_domains(name: str) -> List[str]:
    """Domaines plausibles, du plus probable au moins probable (8 au maximum)."""
    tokens = _name_tokens(name)
    if not tokens:
        return []
    joined, dashed = "".join(tokens), "-".join(tokens)
    if len(joined) < 3 or len(joined) > 40:
        return []
    slugs = [joined] + ([dashed] if dashed != joined else [])
    out = [f"{slug}.{tld}" for tld in FRENCH_TLDS for slug in slugs]
    out += [f"{joined}.{tld}" for tld in FOREIGN_TLDS]
    return out[:8]


def tld_of(url: str) -> str:
    host = (urlparse(url if "//" in url else f"//{url}").hostname or "").lower()
    return host.rsplit(".", 1)[-1] if "." in host else ""


def is_foreign(url: str) -> bool:
    return tld_of(url) in FOREIGN_TLDS


def _safe_host(url: str) -> bool:
    """Refuse localhost et les adresses IP (une redirection ne doit pas viser le réseau local)."""
    host = (urlparse(url).hostname or "").lower()
    if not host or host == "localhost" or host.endswith(".local"):
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        return True


def _fetch_text(domain: str) -> Tuple[Optional[str], str]:
    """(texte de la page ou None, URL finale). Lecture plafonnée, jamais d'exception."""
    url = f"https://{domain}"
    try:
        with requests.get(url, timeout=TIMEOUT_S, stream=True, allow_redirects=True,
                          headers={"User-Agent": _USER_AGENT}) as resp:
            if resp.status_code >= 400 or not _safe_host(resp.url):
                return None, url
            if "html" not in resp.headers.get("Content-Type", "html"):
                return None, url
            body = b""
            for chunk in resp.iter_content(16_384):
                body += chunk
                if len(body) >= MAX_BYTES:
                    break
            return body.decode(resp.encoding or "utf-8", errors="ignore"), resp.url
    except requests.RequestException:
        return None, url


def _locality(address: str) -> List[str]:
    """Code postal et ville tirés de l'adresse Google (« 12 rue X, 51100 Reims, France »)."""
    m = re.search(r"\b(\d{5})\s+([^,]+)", address or "")
    return [m.group(1), normalize(m.group(2))] if m else []


def page_confirms(text: str, name: str, phone: Optional[str], address: str = "") -> Optional[str]:
    """
    La page parle-t-elle bien de cette entreprise ?
      « fort »   : même téléphone, ou nom complet + code postal / ville
      « faible » : nom complet seulement (homonyme possible)
      None       : rien ne correspond
    """
    digits = re.sub(r"\D", "", phone or "")[-9:]
    if len(digits) == 9 and digits in re.sub(r"\D", "", text):
        return "fort"
    page = normalize(re.sub(r"<[^>]+>", " ", text))
    tokens = _name_tokens(name)
    if not tokens or f" {' '.join(tokens)} " not in f" {page} ":
        return None
    padded = f" {page} "
    if any(loc and f" {loc} " in padded for loc in _locality(address)):
        return "fort"
    return "faible"


def find_site(name: str, phone: Optional[str] = None, address: str = "") -> Tuple[Optional[str], Optional[str]]:
    """
    (URL du site retrouvé, niveau de confirmation « fort » / « faible »), ou (None, None).
    Domaines testés en parallèle ; une confirmation forte l'emporte, puis le plus probable.
    """
    domains = candidate_domains(name)
    if not domains:
        return None, None
    with ThreadPoolExecutor(max_workers=len(domains)) as ex:
        pages = list(ex.map(_fetch_text, domains))
    weak: Optional[str] = None
    for text, final_url in pages:
        level = page_confirms(text, name, phone, address) if text else None
        if level == "fort":
            return final_url, "fort"
        if level == "faible" and weak is None:
            weak = final_url
    return (weak, "faible") if weak else (None, None)


def complete_website(p) -> None:
    """
    Complète un prospect : site retrouvé si la fiche Google n'en a pas, et drapeau
    si le site est sur un domaine étranger (activité probablement hors France).
    """
    if not p.has_website():
        url, level = find_site(p.name, p.phone, p.address)
        if url:
            p.website = url
            p.website_source = "deviné"
            if level == "fort":
                p.flags.append(f"site absent de la fiche Google, retrouvé : {url}")
            else:
                p.flags.append(f"site probable (même nom, homonyme possible) — à confirmer : {url}")
    if p.has_website() and is_foreign(p.website):
        p.flags.append(f"site sur un domaine étranger (.{tld_of(p.website)}) — activité hors France ?")
