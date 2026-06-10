"""
services/analyzer.py — Analyse du site web d'un prospect.

Pour chaque prospect avec un site web, ce module :
  1. Charge la page principale (GET HTTP)
  2. Passe BeautifulSoup dessus pour inspecter le HTML
  3. Lance 10 checks pondérés (HTTPS, mobile, SEO, tracking, obsolescence…)
  4. Scrape l'email de contact (mailto + page /contact)
  5. Calcule un score pondéré sur 100 (100 = parfait, 0 = aucun site)

Score = 100 − Σ(poids de chaque problème détecté)
  Critique (−15 pts) : HTTPS manquant, site non mobile, tracking absent, formulaire absent
  Important (−10 pts) : chargement lent, builder gratuit, titre absent, site obsolète
  Mineur   (−5 pts)  : meta description absente, réseaux sociaux absents

Les poids peuvent être surchargés par profil via weight_overrides dans analyze_prospect().
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from config import config, logger
from services.google_maps import Prospect


# ---------------------------------------------------------------------------
# Seuils et constantes
# ---------------------------------------------------------------------------

SLOW_RESPONSE_THRESHOLD_S = 3.0  # Au-delà de 3s → signalé comme lent
MAX_SCORE = 100
_FETCH_MAX_RETRIES = 2           # Nombre de tentatives supplémentaires si timeout/erreur réseau

CRITICAL_WEIGHT = 15   # Problèmes bloquants pour l'activité commerciale
MAJOR_WEIGHT    = 10   # Problèmes importants mais non bloquants
MINOR_WEIGHT    = 5    # Défauts mineurs, à améliorer si possible

# Noms de checks — utilisés comme clés dans check_weight_overrides des profils
CHECK_HTTPS          = "https"
CHECK_RESPONSE_TIME  = "response_time"
CHECK_VIEWPORT       = "viewport"
CHECK_TITLE          = "title"
CHECK_META_DESC      = "meta_description"
CHECK_TRACKING       = "tracking"
CHECK_LEAD_FORM      = "lead_form"
CHECK_FREE_BUILDER   = "free_builder"
CHECK_SOCIAL_LINKS   = "social_links"
CHECK_OUTDATED       = "outdated"

_DEFAULT_WEIGHTS: Dict[str, int] = {
    CHECK_HTTPS:         CRITICAL_WEIGHT,
    CHECK_RESPONSE_TIME: MAJOR_WEIGHT,
    CHECK_VIEWPORT:      CRITICAL_WEIGHT,
    CHECK_TITLE:         MAJOR_WEIGHT,
    CHECK_META_DESC:     MINOR_WEIGHT,
    CHECK_TRACKING:      CRITICAL_WEIGHT,
    CHECK_LEAD_FORM:     CRITICAL_WEIGHT,
    CHECK_FREE_BUILDER:  MAJOR_WEIGHT,
    CHECK_SOCIAL_LINKS:  MINOR_WEIGHT,
    CHECK_OUTDATED:      MAJOR_WEIGHT,
}

# Type interne : liste de (message, poids)
_IssueList = List[Tuple[str, int]]

# Constructeurs de sites gratuits — leur présence = opportunité de refonte pro
_FREE_BUILDERS = (
    "wix.com", "jimdo.com", "webnode.fr", "webself.net",
    "site123.com", "weebly.com", "yola.com",
)

# Signatures de scripts de tracking dans le HTML
_TRACKING_SIGNATURES = (
    "gtag(", "ga(", "fbq(", "google-analytics",
    "googletagmanager", "GTM-", "hotjar", "clarity.ms",
)

# Domaines des réseaux sociaux principaux
_SOCIAL_DOMAINS = (
    "facebook.com", "instagram.com", "linkedin.com",
    "twitter.com", "x.com", "tiktok.com", "youtube.com",
)

# Emails à ignorer lors du scraping (faux positifs courants)
_EMAIL_BLACKLIST = (
    "example.com", "sentry.io", "wix.com", "googleapis",
    "schema.org", ".png", ".jpg", ".gif", ".svg",
)


# ---------------------------------------------------------------------------
# Chargement de la page
# ---------------------------------------------------------------------------

def _fetch(url: str) -> Tuple[requests.Response | None, float]:
    """
    Charge une URL avec retry exponentiel (2 tentatives supplémentaires : 2s, 4s).
    Retourne (None, 0.0) si toutes les tentatives échouent.
    """
    if not url.startswith("http"):
        url = "https://" + url
    last_exc: Exception | None = None
    for attempt in range(_FETCH_MAX_RETRIES + 1):
        try:
            start = time.perf_counter()
            resp = requests.get(
                url,
                timeout=config.request_timeout,
                headers={"User-Agent": "Mozilla/5.0 (compatible; ProspectBot/1.0)"},
                allow_redirects=True,
            )
            elapsed = time.perf_counter() - start
            return resp, elapsed
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < _FETCH_MAX_RETRIES:
                delay = 2 ** (attempt + 1)  # 2s, puis 4s
                logger.debug(
                    "    ↩️  %s — tentative %d/%d dans %ds…",
                    url, attempt + 1, _FETCH_MAX_RETRIES, delay,
                )
                time.sleep(delay)
    logger.warning(
        "    ⚠️  Impossible de charger %s après %d tentatives : %s",
        url, _FETCH_MAX_RETRIES + 1, last_exc,
    )
    return None, 0.0


# ---------------------------------------------------------------------------
# Checks individuels — chacun ajoute un tuple (message, poids) dans `issues`
# ---------------------------------------------------------------------------

def _check_https(url: str, issues: _IssueList, weight: int = CRITICAL_WEIGHT) -> None:
    """HTTPS absent = pénalité SEO + alerte navigateur + signal de méfiance."""
    if not url.startswith("https://"):
        issues.append((
            "Site sans HTTPS (connexion non sécurisée, pénalité SEO Google)",
            weight,
        ))


def _check_response_time(elapsed: float, issues: _IssueList, weight: int = MAJOR_WEIGHT) -> None:
    """Temps de réponse > 3s = mauvaise expérience utilisateur + pénalité SEO."""
    if elapsed > SLOW_RESPONSE_THRESHOLD_S:
        issues.append((
            f"Temps de chargement élevé ({elapsed:.1f}s > {SLOW_RESPONSE_THRESHOLD_S}s) "
            "→ impact SEO et expérience utilisateur",
            weight,
        ))


def _check_viewport(soup: BeautifulSoup, issues: _IssueList, weight: int = CRITICAL_WEIGHT) -> None:
    """Meta viewport absente = site non responsive = perte de ~60 % du trafic mobile."""
    if not soup.find("meta", attrs={"name": "viewport"}):
        issues.append((
            "Absence de meta viewport → site probablement non responsive (mobile)",
            weight,
        ))


def _check_title(soup: BeautifulSoup, issues: _IssueList, weight: int = MAJOR_WEIGHT) -> None:
    """Balise <title> obligatoire pour le SEO on-page."""
    title = soup.find("title")
    if not title or not title.get_text(strip=True):
        issues.append((
            "Absence de balise <title> → SEO on-page défaillant",
            weight,
        ))


def _check_meta_description(soup: BeautifulSoup, issues: _IssueList, weight: int = MINOR_WEIGHT) -> None:
    """Meta description = snippet affiché dans Google. Son absence réduit le CTR."""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if not meta_desc or not meta_desc.get("content", "").strip():
        issues.append((
            "Absence de meta description → snippet Google non optimisé",
            weight,
        ))


def _check_tracking(html: str, issues: _IssueList, weight: int = CRITICAL_WEIGHT) -> None:
    """Sans tracking (GA, GTM, Pixel…), impossible de mesurer les performances."""
    if not any(sig in html for sig in _TRACKING_SIGNATURES):
        issues.append((
            "Aucun pixel de tracking détecté (Google Analytics, GTM, Facebook Pixel) "
            "→ impossible de mesurer les conversions",
            weight,
        ))


def _check_lead_form(soup: BeautifulSoup, issues: _IssueList, weight: int = CRITICAL_WEIGHT) -> None:
    """Formulaire de contact absent = les visiteurs n'ont pas de moyen facile de convertir."""
    forms = soup.find_all("form")
    inputs_email = soup.find_all("input", {"type": "email"})
    if not forms and not inputs_email:
        issues.append((
            "Aucun formulaire de contact / capture de lead visible "
            "→ les visiteurs n'ont pas de moyen simple de se convertir",
            weight,
        ))


def _check_free_builder(url: str, html: str, issues: _IssueList, weight: int = MAJOR_WEIGHT) -> None:
    """Sites construits sur Wix, Jimdo… = limitations SEO + image non professionnelle."""
    combined = url.lower() + html.lower()
    for builder in _FREE_BUILDERS:
        if builder in combined:
            issues.append((
                f"Site construit avec un outil gratuit ({builder}) "
                "→ limitations techniques, SEO restreint, image non professionnelle",
                weight,
            ))
            return


def _check_social_links(soup: BeautifulSoup, issues: _IssueList, weight: int = MINOR_WEIGHT) -> None:
    """Absence de liens réseaux sociaux = présence digitale limitée."""
    links = soup.find_all("a", href=True)
    has_social = any(
        domain in (a["href"] or "").lower()
        for a in links
        for domain in _SOCIAL_DOMAINS
    )
    if not has_social:
        issues.append((
            "Aucun lien vers des réseaux sociaux détecté "
            "→ présence digitale limitée, opportunité de stratégie social media",
            weight,
        ))


def _check_outdated_site(html: str, issues: _IssueList, weight: int = MAJOR_WEIGHT) -> None:
    """Copyright trop ancien = site non maintenu → opportunité de refonte."""
    current_year = datetime.now().year
    matches = re.findall(r'(?:©|&copy;|copyright)\s*(\d{4})', html, re.IGNORECASE)
    if matches:
        years = [int(y) for y in matches if 2000 <= int(y) <= current_year]
        if years and current_year - max(years) >= 3:
            issues.append((
                f"Site non mis à jour depuis {max(years)} "
                "→ risque d'obsolescence technique et de contenu",
                weight,
            ))


# ---------------------------------------------------------------------------
# Scraping d'email
# ---------------------------------------------------------------------------

def _scrape_email(url: str, soup: BeautifulSoup) -> Optional[str]:
    """
    Cherche un email de contact sur le site du prospect.

    Stratégie :
      1. Liens mailto: sur la page principale
      2. Texte brut de la page principale (regex email)
      3. Même chose sur les pages /contact, /nous-contacter, etc.

    Les emails blacklistés (sentry, wix, example.com…) sont ignorés.
    """
    _EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

    def _extract(html: str) -> Optional[str]:
        # Priorité aux liens mailto: (email explicitement mis en lien)
        for match in re.finditer(r"mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", html):
            email = match.group(1)
            if not any(b in email for b in _EMAIL_BLACKLIST):
                return email
        # Fallback : scan du texte brut
        for match in _EMAIL_RE.finditer(html):
            email = match.group(0)
            if not any(b in email for b in _EMAIL_BLACKLIST):
                return email
        return None

    # Tentative 1 : page principale
    email = _extract(str(soup))
    if email:
        return email

    # Tentative 2 : pages de contact courantes
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    for path in ["/contact", "/contact-us", "/nous-contacter", "/contactez-nous"]:
        try:
            resp = requests.get(
                base + path,
                timeout=config.request_timeout,
                headers={"User-Agent": "Mozilla/5.0"},
                allow_redirects=True,
            )
            if resp.ok:
                email = _extract(resp.text)
                if email:
                    return email
        except requests.RequestException:
            continue

    return None


# ---------------------------------------------------------------------------
# Fonction principale exportée
# ---------------------------------------------------------------------------

def analyze_prospect(
    prospect: Prospect,
    weight_overrides: Dict[str, int] | None = None,
) -> Prospect:
    """
    Analyse complète du prospect.

    Cas particuliers gérés :
    - Pas de site → score 0, problème unique "pas de site web"
    - Site inaccessible → score 5, problème unique "site down"
    - Site normal → 10 checks pondérés + scraping email + calcul du score

    weight_overrides : dict optionnel pour surcharger les poids par défaut.
    Exemple : {"social_links": 15} pour rendre ce check critique.

    Retourne le prospect enrichi (issues, score, email).
    """
    # Construction du dict de poids (défauts + surcharges du profil)
    weights = dict(_DEFAULT_WEIGHTS)
    if weight_overrides:
        weights.update(weight_overrides)

    # Cas 1 : pas de site web du tout → opportunité maximale
    if not prospect.has_website():
        prospect.issues = [
            "Pas de site web référencé → opportunité directe de création de site"
        ]
        prospect.score = 0
        logger.info("  📵 %s : pas de site web → opportunité maximale.", prospect.name)
        return prospect

    url = prospect.website
    logger.info("  🔬 Analyse de %s (%s)…", prospect.name, url)

    resp, elapsed = _fetch(url)

    # Cas 2 : site inaccessible (down, timeout, erreur serveur)
    if resp is None:
        prospect.issues = [
            "Site web inaccessible (erreur réseau ou serveur down) "
            "→ perte de crédibilité et de clients potentiels"
        ]
        prospect.score = 5
        return prospect

    html = resp.text
    soup = BeautifulSoup(html, "lxml")
    weighted_issues: _IssueList = []

    # Cas 3 : site accessible → lancement des 10 checks pondérés
    _check_https(url, weighted_issues,           weights[CHECK_HTTPS])
    _check_response_time(elapsed, weighted_issues, weights[CHECK_RESPONSE_TIME])
    _check_viewport(soup, weighted_issues,        weights[CHECK_VIEWPORT])
    _check_title(soup, weighted_issues,           weights[CHECK_TITLE])
    _check_meta_description(soup, weighted_issues, weights[CHECK_META_DESC])
    _check_tracking(html, weighted_issues,        weights[CHECK_TRACKING])
    _check_lead_form(soup, weighted_issues,       weights[CHECK_LEAD_FORM])
    _check_free_builder(url, html, weighted_issues, weights[CHECK_FREE_BUILDER])
    _check_social_links(soup, weighted_issues,    weights[CHECK_SOCIAL_LINKS])
    _check_outdated_site(html, weighted_issues,   weights[CHECK_OUTDATED])

    # Scraping de l'email de contact
    email = _scrape_email(url, soup)
    if email:
        prospect.email = email
        logger.debug("  📧 Email trouvé : %s", email)
    else:
        logger.debug("  📭 Aucun email trouvé pour %s", prospect.name)

    # Score final pondéré : critique = −15, important = −10, mineur = −5
    prospect.issues = [msg for msg, _ in weighted_issues]
    prospect.score = max(0, MAX_SCORE - sum(w for _, w in weighted_issues))

    level = "🟢" if prospect.score >= 70 else ("🟡" if prospect.score >= 40 else "🔴")
    logger.info(
        "  %s %s → score %d/100 | %d problème(s)",
        level, prospect.name, prospect.score, len(weighted_issues),
    )
    for i, (msg, weight) in enumerate(weighted_issues, 1):
        logger.debug("      %d. [-%d pts] %s", i, weight, msg)

    return prospect
