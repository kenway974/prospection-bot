"""
services/analyzer.py — Analyse du site web d'un prospect.

Pour chaque prospect avec un site web, ce module :
  1. Charge la page principale (GET HTTP)
  2. Passe BeautifulSoup dessus pour inspecter le HTML
  3. Lance 10 checks (HTTPS, mobile, SEO, tracking, formulaire…)
  4. Scrape l'email de contact (mailto + page /contact)
  5. Calcule un score sur 100 (100 = parfait, 0 = aucun site)

Score = 100 - (nb_problèmes × 10)
Plus le score est bas, plus il y a d'opportunités commerciales.
"""

from __future__ import annotations

import re
import time
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import config, logger
from services.google_maps import Prospect


# ---------------------------------------------------------------------------
# Seuils et constantes
# ---------------------------------------------------------------------------

SLOW_RESPONSE_THRESHOLD_S = 3.0  # Au-delà de 3s → signalé comme lent
MAX_SCORE = 100
POINTS_PER_ISSUE = 10            # Chaque problème détecté retire 10 points

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
    Charge une URL et retourne (response, temps_en_secondes).
    Retourne (None, 0.0) si la requête échoue — le prospect est marqué inaccessible.
    """
    if not url.startswith("http"):
        url = "https://" + url
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
        logger.warning("    ⚠️  Impossible de charger %s : %s", url, exc)
        return None, 0.0


# ---------------------------------------------------------------------------
# Checks individuels — chacun ajoute un message dans la liste `issues`
# ---------------------------------------------------------------------------

def _check_https(url: str, issues: List[str]) -> None:
    """Le site doit être en HTTPS. HTTP = pénalité SEO + alerte navigateur."""
    if not url.startswith("https://"):
        issues.append("Site sans HTTPS (connexion non sécurisée, pénalité SEO Google)")


def _check_response_time(elapsed: float, issues: List[str]) -> None:
    """Temps de réponse > 3s = mauvaise expérience utilisateur + pénalité SEO."""
    if elapsed > SLOW_RESPONSE_THRESHOLD_S:
        issues.append(
            f"Temps de chargement élevé ({elapsed:.1f}s > {SLOW_RESPONSE_THRESHOLD_S}s) "
            "→ impact SEO et expérience utilisateur"
        )


def _check_viewport(soup: BeautifulSoup, issues: List[str]) -> None:
    """Meta viewport absente = site non responsive = mauvaise expérience mobile."""
    if not soup.find("meta", attrs={"name": "viewport"}):
        issues.append("Absence de meta viewport → site probablement non responsive (mobile)")


def _check_title(soup: BeautifulSoup, issues: List[str]) -> None:
    """Balise <title> obligatoire pour le SEO on-page."""
    title = soup.find("title")
    if not title or not title.get_text(strip=True):
        issues.append("Absence de balise <title> → SEO on-page défaillant")


def _check_meta_description(soup: BeautifulSoup, issues: List[str]) -> None:
    """Meta description = snippet affiché dans Google. Son absence réduit le CTR."""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if not meta_desc or not meta_desc.get("content", "").strip():
        issues.append("Absence de meta description → snippet Google non optimisé")


def _check_favicon(soup: BeautifulSoup, issues: List[str]) -> None:
    """Favicon absente = manque de soin dans les détails, image moins pro."""
    # lxml peut retourner rel comme liste ['icon'] ou chaîne 'icon' selon le tag
    def _has_icon(rel):
        if not rel:
            return False
        rel_str = " ".join(rel).lower() if isinstance(rel, list) else str(rel).lower()
        return "icon" in rel_str

    favicon = soup.find("link", rel=_has_icon)
    if not favicon:
        issues.append("Absence de favicon → manque de professionnalisme perçu")


def _check_tracking(html: str, issues: List[str]) -> None:
    """Sans tracking (GA, GTM, Pixel…), impossible de mesurer les performances."""
    if not any(sig in html for sig in _TRACKING_SIGNATURES):
        issues.append(
            "Aucun pixel de tracking détecté (Google Analytics, GTM, Facebook Pixel) "
            "→ impossible de mesurer les conversions"
        )


def _check_lead_form(soup: BeautifulSoup, issues: List[str]) -> None:
    """Formulaire de contact absent = les visiteurs n'ont pas de moyen facile de convertir."""
    forms = soup.find_all("form")
    inputs_email = soup.find_all("input", {"type": "email"})
    if not forms and not inputs_email:
        issues.append(
            "Aucun formulaire de contact / capture de lead visible "
            "→ les visiteurs n'ont pas de moyen simple de se convertir"
        )


def _check_free_builder(url: str, html: str, issues: List[str]) -> None:
    """Sites construits sur Wix, Jimdo… = limitations SEO + image non professionnelle."""
    combined = url.lower() + html.lower()
    for builder in _FREE_BUILDERS:
        if builder in combined:
            issues.append(
                f"Site construit avec un outil gratuit ({builder}) "
                "→ limitations techniques, SEO restreint, image non professionnelle"
            )
            return


def _check_social_links(soup: BeautifulSoup, issues: List[str]) -> None:
    """Absence de liens réseaux sociaux = présence digitale limitée."""
    links = soup.find_all("a", href=True)
    has_social = any(
        domain in (a["href"] or "").lower()
        for a in links
        for domain in _SOCIAL_DOMAINS
    )
    if not has_social:
        issues.append(
            "Aucun lien vers des réseaux sociaux détecté "
            "→ présence digitale limitée, opportunité de stratégie social media"
        )


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

def analyze_prospect(prospect: Prospect) -> Prospect:
    """
    Analyse complète du prospect.

    Cas particuliers gérés :
    - Pas de site → score 0, problème unique "pas de site web"
    - Site inaccessible → score 5, problème unique "site down"
    - Site normal → 10 checks + scraping email + calcul du score

    Retourne le prospect enrichi (issues, score, email).
    """
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
    issues: List[str] = []

    # Cas 3 : site accessible → lancement des 10 checks
    _check_https(url, issues)
    _check_response_time(elapsed, issues)
    _check_viewport(soup, issues)
    _check_title(soup, issues)
    _check_meta_description(soup, issues)
    _check_favicon(soup, issues)
    _check_tracking(html, issues)
    _check_lead_form(soup, issues)
    _check_free_builder(url, html, issues)
    _check_social_links(soup, issues)

    # Scraping de l'email de contact
    email = _scrape_email(url, soup)
    if email:
        prospect.email = email
        logger.debug("  📧 Email trouvé : %s", email)
    else:
        logger.debug("  📭 Aucun email trouvé pour %s", prospect.name)

    # Score final
    prospect.issues = issues
    prospect.score = max(0, MAX_SCORE - len(issues) * POINTS_PER_ISSUE)

    level = "🟢" if prospect.score >= 70 else ("🟡" if prospect.score >= 40 else "🔴")
    logger.info(
        "  %s %s → score %d/100 | %d problème(s)",
        level, prospect.name, prospect.score, len(issues),
    )
    for i, issue in enumerate(issues, 1):
        logger.debug("      %d. %s", i, issue)

    return prospect
