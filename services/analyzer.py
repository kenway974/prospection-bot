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
from services import cache as _cache


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
# Checks métier — coursier/livreur
CHECK_DELIVERY_COVERED = "delivery_covered"  # livraison déjà gérée → opportunité réduite
CHECK_LOW_VOLUME       = "low_volume"         # peu d'avis → activité faible
# Check performance mobile via Lighthouse
CHECK_PAGESPEED        = "pagespeed"

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
    # Checks métier inactifs par défaut (activés via check_weight_overrides dans les profils)
    CHECK_DELIVERY_COVERED: 0,
    CHECK_LOW_VOLUME:       0,
    # PageSpeed actif par défaut (nécessite GOOGLE_PLACES_API_KEY, skip si absente)
    CHECK_PAGESPEED: MAJOR_WEIGHT,
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

# Mots-clés et plateformes indiquant que la livraison est déjà couverte
_DELIVERY_KEYWORDS = (
    "livraison", "livrer", "nous livrons", "click and collect",
    "commander en ligne", "commandez en ligne", "order online",
    "à domicile", "livré chez vous", "livraison gratuite",
)
_DELIVERY_PLATFORMS = (
    "ubereats", "uber eats", "deliveroo", "just-eat", "justeat",
    "just eat", "glovo", "stuart", "lyveat", "takeaway",
)

# CMS / builders détectables par signature dans l'URL ou le HTML
_CMS_SIGNATURES: dict = {
    "WordPress":   ["wp-content/", "wp-includes/", "wordpress"],
    "Wix":         ["wix.com", "wixstatic.com"],
    "Squarespace": ["squarespace.com", "squarespace-cdn.com", "static1.squarespace"],
    "Shopify":     ["myshopify.com", "cdn.shopify.com"],
    "PrestaShop":  ["prestashop", "/modules/blockwishlist", "prestashop-"],
    "Joomla":      ["/components/com_", "joomla"],
    "Drupal":      ["sites/default/files", "/drupal"],
    "Webflow":     ["webflow.io", "webflow.com/css"],
    "Jimdo":       ["jimdo.com", "jimdofree.com", "jimdosite.com"],
    "Weebly":      ["weebly.com", "editmysite.com"],
    "Webnode":     ["webnode.fr", "webnode.com"],
}

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


def _check_pagespeed(url: str, issues: _IssueList, weight: int = MAJOR_WEIGHT) -> None:
    """Score Lighthouse mobile via l'API Google PageSpeed Insights.
    Skip silencieusement si la clé API est absente ou si l'API répond mal.
    Retry exponentiel (2s, 4s) sur les erreurs réseau et rate-limit (429)."""
    if weight == 0 or not config.google_api_key:
        return
    for attempt in range(3):
        try:
            resp = requests.get(
                "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                params={"url": url, "strategy": "mobile", "key": config.google_api_key},
                timeout=30,
            )
            if resp.status_code == 429 and attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            if not resp.ok:
                logger.debug("    ⚠️  PageSpeed API HTTP %d pour %s", resp.status_code, url)
                return
            score = int(resp.json()["lighthouseResult"]["categories"]["performance"]["score"] * 100)
            if score < 50:
                issues.append((
                    f"Performance mobile mauvaise (PageSpeed : {score}/100) "
                    "→ site très lent sur smartphone, pénalité SEO Core Web Vitals",
                    weight,
                ))
            elif score < 70:
                issues.append((
                    f"Performance mobile moyenne (PageSpeed : {score}/100) "
                    "→ optimisations nécessaires (images, JS, CSS)",
                    MINOR_WEIGHT,
                ))
            else:
                logger.debug("    ✅ PageSpeed mobile OK : %d/100 pour %s", score, url)
            return
        except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
            else:
                logger.debug("    ⚠️  PageSpeed API indisponible pour %s : %s", url, exc)


def _check_delivery_covered(
    soup: BeautifulSoup, html: str, issues: _IssueList, weight: int = CRITICAL_WEIGHT,
) -> None:
    """Détecte si l'établissement propose déjà de la livraison (propre ou via plateforme)."""
    if weight == 0:
        return
    text = soup.get_text().lower()
    hrefs = " ".join(a.get("href", "").lower() for a in soup.find_all("a", href=True))
    combined = text + " " + hrefs + " " + html.lower()
    if any(kw in combined for kw in _DELIVERY_KEYWORDS) or \
       any(p in combined for p in _DELIVERY_PLATFORMS):
        issues.append((
            "Livraison déjà gérée (service propre ou plateforme tierce) "
            "→ opportunité réduite pour un coursier externe",
            weight,
        ))


def _detect_cms(url: str, html: str) -> Optional[str]:
    """Identifie le CMS ou builder utilisé par le site via signatures URL/HTML."""
    combined = url.lower() + html.lower()
    for cms, signatures in _CMS_SIGNATURES.items():
        if any(sig.lower() in combined for sig in signatures):
            return cms
    return None


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
# Vérification MX d'email
# ---------------------------------------------------------------------------

def _verify_email_mx(email: str) -> bool:
    """Retourne True si le domaine email a au moins un enregistrement MX valide."""
    try:
        import dns.resolver
        domain = email.split("@", 1)[1]
        dns.resolver.resolve(domain, "MX")
        return True
    except Exception:
        return False


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
    if email and _verify_email_mx(email):
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
                if email and _verify_email_mx(email):
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

    # Cache hit — évite de refaire fetch + checks pour un site déjà analysé (<30 j)
    cached = _cache.get_cached(url)
    if cached:
        prospect.issues = cached["issues"]
        prospect.score  = cached["score"]
        prospect.email  = cached.get("email")
        prospect.cms    = cached.get("cms")
        logger.info("  ⚡ %s — résultat en cache (score %d/100)", prospect.name, prospect.score)
        return prospect

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
    _check_https(url, weighted_issues,              weights[CHECK_HTTPS])
    _check_response_time(elapsed, weighted_issues,  weights[CHECK_RESPONSE_TIME])
    _check_viewport(soup, weighted_issues,          weights[CHECK_VIEWPORT])
    _check_title(soup, weighted_issues,             weights[CHECK_TITLE])
    _check_meta_description(soup, weighted_issues,  weights[CHECK_META_DESC])
    _check_tracking(html, weighted_issues,          weights[CHECK_TRACKING])
    _check_lead_form(soup, weighted_issues,         weights[CHECK_LEAD_FORM])
    _check_free_builder(url, html, weighted_issues, weights[CHECK_FREE_BUILDER])
    _check_social_links(soup, weighted_issues,      weights[CHECK_SOCIAL_LINKS])
    _check_outdated_site(html, weighted_issues,     weights[CHECK_OUTDATED])
    _check_delivery_covered(soup, html, weighted_issues, weights[CHECK_DELIVERY_COVERED])
    _check_pagespeed(url, weighted_issues,          weights[CHECK_PAGESPEED])

    # Détection du CMS (pas un check, pas de pénalité — utilisé pour personnaliser l'email)
    prospect.cms = _detect_cms(url, html)
    if prospect.cms:
        logger.debug("  🧩 CMS détecté : %s pour %s", prospect.cms, prospect.name)

    # Check volume d'activité (données Google, pas HTML)
    low_vol_weight = weights.get(CHECK_LOW_VOLUME, 0)
    if low_vol_weight > 0 and prospect.user_ratings_total < 30:
        weighted_issues.append((
            f"Peu d'avis Google ({prospect.user_ratings_total}) "
            "→ activité faible, retour sur investissement incertain",
            low_vol_weight,
        ))

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

    # Mise en cache du résultat (évite de refaire l'analyse dans les 30 prochains jours)
    _cache.set_cached(url, prospect.issues, prospect.score, prospect.email, prospect.cms)

    return prospect
