"""
services/dirigeants.py — Trouver le dirigeant d'une entreprise via Sirène.

Source : API Recherche d'entreprises (data.gouv.fr) — données publiques et
gratuites du registre national, sans authentification.
  https://recherche-entreprises.api.gouv.fr/docs/

Sirène ne contient que les REPRÉSENTANTS LÉGAUX (président, gérant, DG…).
Un CTO ou un Product Owner n'y figure jamais : pour eux, c'est LinkedIn.

Règle d'or : on n'attribue un dirigeant QUE si la correspondance est sûre.
Écrire « Bonjour Jean » au mauvais Jean est pire que « Bonjour ».
"""

from __future__ import annotations

import re
import time
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Tuple

import requests

from config import config, logger

BASE_URL = "https://recherche-entreprises.api.gouv.fr/search"

# Rate limit documenté de l'API : ~7 requêtes/s. On reste largement en dessous.
_MIN_INTERVAL_S = 0.2
_last_call = 0.0

# Seuil de similarité des noms pour accepter une correspondance
MATCH_THRESHOLD = 0.82

# Priorité des fonctions : le plus décisionnaire d'abord.
_ROLE_PRIORITY: List[Tuple[str, int]] = [
    ("president", 0),
    ("directeur general", 1),
    ("gerant", 2),
    ("co-gerant", 2),
    ("cogerant", 2),
    ("directeur general delegue", 3),
    ("administrateur", 5),
]

# Mots qui n'aident pas à identifier une entreprise (formes juridiques, etc.)
_STOPWORDS = {
    "sas", "sasu", "sarl", "eurl", "sa", "sci", "snc", "scop", "selarl", "ei",
    "eirl", "micro", "entreprise", "societe", "ste", "et", "de", "du", "des",
    "la", "le", "les", "l", "d", "en", "a",
}


# ---------------------------------------------------------------------------
# Normalisation & comparaison de noms
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _tokens(text: str) -> List[str]:
    return [t for t in _norm(text).split() if t not in _STOPWORDS]


def name_similarity(a: str, b: str) -> float:
    """
    Similarité 0..1 entre deux raisons sociales, robuste aux formes juridiques
    (« Garage Payet SARL » ≈ « GARAGE PAYET ») et à l'ordre des mots.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    sa, sb = " ".join(sorted(ta)), " ".join(sorted(tb))
    ratio = SequenceMatcher(None, sa, sb).ratio()
    # Tous les mots significatifs de l'un sont dans l'autre → bon signe, MAIS
    # seulement si le nom court est assez spécifique : sinon « Garage » matcherait
    # « Garage Dupont » et on écrirait au mauvais dirigeant.
    set_a, set_b = set(ta), set(tb)
    if set_a <= set_b or set_b <= set_a:
        small, large = sorted((len(set_a), len(set_b)))
        overlap = small / large
        if small >= 2 and overlap >= 2 / 3:
            ratio = max(ratio, 0.85 + 0.15 * overlap)
    return ratio


def extract_postal_code(address: str) -> str:
    """Code postal français depuis une adresse Google Maps (« … 97400 Saint-Denis »)."""
    m = re.search(r"\b(97[1-6]\d{2}|\d{5})\b", address or "")
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Extraction du dirigeant depuis une entrée de l'API
# ---------------------------------------------------------------------------

def _format_person(prenoms: str, nom: str) -> str:
    """« Jean Marc Pierre » + « LE GOFF » → « Jean Le Goff »."""
    first = (prenoms or "").strip().split(" ")[0] if prenoms else ""
    first = "-".join(p.capitalize() for p in first.split("-"))

    def _cap(word: str) -> str:
        if "'" in word:  # D'ARTAGNAN → D'Artagnan
            return "'".join(p.capitalize() for p in word.split("'"))
        return "-".join(p.capitalize() for p in word.split("-"))

    last = " ".join(_cap(w) for w in (nom or "").strip().lower().split())
    return f"{first} {last}".strip()


def _role_rank(qualite: str) -> int:
    q = _norm(qualite)
    for key, rank in _ROLE_PRIORITY:
        if key in q:
            return rank
    return 9


def _clean_role(qualite: str) -> str:
    """« Président de SAS » → « Président » ; garde le libellé lisible."""
    q = (qualite or "").strip()
    q = re.sub(r"\s+de\s+(sas|sasu|sarl|eurl|sa|snc|sci).*$", "", q, flags=re.I)
    return q[:1].upper() + q[1:] if q else ""


def extract_dirigeant(entry: dict) -> Tuple[str, str]:
    """
    Retourne (« Prénom Nom », « Fonction ») du dirigeant le plus décisionnaire.
    Ignore les personnes morales (holdings). ("", "") si aucun.
    """
    people = [
        d for d in (entry.get("dirigeants") or [])
        if (d.get("type_dirigeant") or "").lower() == "personne physique"
        and (d.get("nom") or "").strip()
    ]
    if not people:
        return "", ""
    best = min(people, key=lambda d: _role_rank(d.get("qualite", "")))
    return _format_person(best.get("prenoms", ""), best.get("nom", "")), _clean_role(best.get("qualite", ""))


# ---------------------------------------------------------------------------
# Recherche d'une entreprise précise
# ---------------------------------------------------------------------------

def _throttle() -> None:
    global _last_call
    wait = _MIN_INTERVAL_S - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _search(name: str, postal_code: str) -> List[dict]:
    params = {"q": name, "per_page": 5, "page": 1}
    if postal_code:
        params["code_postal"] = postal_code
    _throttle()
    try:
        resp = requests.get(BASE_URL, params=params, timeout=config.request_timeout)
        if resp.status_code == 429:           # trop de requêtes : on patiente une fois
            time.sleep(2)
            resp = requests.get(BASE_URL, params=params, timeout=config.request_timeout)
        resp.raise_for_status()
        return resp.json().get("results", []) or []
    except (requests.RequestException, ValueError) as exc:
        logger.debug("  Sirène dirigeant indisponible pour %s : %s", name, exc)
        return []


def find_dirigeant(name: str, address: str = "") -> Optional[dict]:
    """
    Cherche l'entreprise dans Sirène et retourne
      {"siren", "dirigeant", "qualite", "score"} si la correspondance est SÛRE,
    None sinon.
    """
    if not name or not name.strip():
        return None
    postal = extract_postal_code(address)
    results = _search(name, postal)

    best, best_score = None, 0.0
    for entry in results:
        for candidate in (entry.get("nom_raison_sociale"), entry.get("nom_complet")):
            if not candidate:
                continue
            score = name_similarity(name, candidate)
            if score > best_score:
                best, best_score = entry, score

    if best is None or best_score < MATCH_THRESHOLD:
        return None

    dirigeant, qualite = extract_dirigeant(best)
    if not dirigeant:
        return None
    return {
        "siren": best.get("siren", ""),
        "dirigeant": dirigeant,
        "qualite": qualite,
        "score": round(best_score, 2),
    }


def enrich_prospects(prospects: Iterable, log=None) -> int:
    """
    Complète p.dirigeant / p.dirigeant_qualite / p.siren sur chaque prospect.
    Ne touche pas un prospect déjà renseigné. Retourne le nombre enrichi.
    """
    found = 0
    for p in prospects:
        if getattr(p, "dirigeant", ""):
            continue
        info = find_dirigeant(p.name, p.address or "")
        if info:
            p.dirigeant = info["dirigeant"]
            p.dirigeant_qualite = info["qualite"]
            p.siren = p.siren or info["siren"]
            found += 1
            if log:
                log(f"[--] 👤 {p.name} → {p.dirigeant} ({p.dirigeant_qualite})")
    return found
