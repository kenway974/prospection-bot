"""
services/analyzer.py — Analyse du site web d'un prospect.

Pour chaque prospect avec un site web, ce module :
  1. Charge la page principale (GET HTTP)
  2. Passe BeautifulSoup dessus pour inspecter le HTML
  3. Lance des checks pondérés (HTTPS, mobile, SEO, tracking, obsolescence, visibilité…)
  4. Scrape l'email de contact (mailto + page /contact)
  5. Calcule un score pondéré sur 100 (100 = parfait, 0 = aucun site)

Score = 100 − Σ(poids de chaque problème détecté)
  Critique (−15 pts) : HTTPS manquant, site non mobile, tracking absent, formulaire absent
  Important (−10 pts) : chargement lent, builder gratuit, titre absent, site obsolète
  Mineur   (−5 pts)  : meta description absente, réseaux sociaux absents

Les poids peuvent être surchargés par profil via weight_overrides dans analyze_prospect().
"""

# 📘 Le texte entre triple guillemets tout en haut est la "docstring" du module : sa doc officielle
# 📘 (affichée par help()). Lis-la, elle résume très bien la logique du scoring.
# 📘 `from __future__ import annotations` : les type hints ne sont pas évalués à l'exécution. C'est
# 📘 ce qui permet d'écrire `requests.Response | None` plus bas même sur un Python un peu ancien.
from __future__ import annotations

# 📘 Imports de la librairie standard : re (expressions régulières = motifs de recherche dans du
# 📘 texte), time (chronos / pauses), datetime (dates), typing (types), urllib.parse (découper URL).
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

# 📘 Librairies externes (installées via pip, listées dans requirements.txt) :
# 📘 - requests : faire des requêtes HTTP (télécharger une page web) très simplement.
# 📘 - BeautifulSoup (bs4) : transforme le HTML brut en arbre navigable, pour chercher des balises
# 📘   (ex: soup.find("title")) au lieu de bricoler avec du texte.
import requests
from bs4 import BeautifulSoup

# 📘 Imports internes au projet. `config` = réglages (clés API, timeouts), `logger` = journal.
# 📘 ⚠️ pipeline.py REMPLACE ensuite `analyzer.config` et `analyzer.logger` (monkeypatch) pour
# 📘 rediriger les logs vers l'interface Streamlit : ça marche car on les utilise via ces noms
# 📘 globaux du module. `import cache as _cache` = alias local (on écrira _cache.get_cached()).
from config import config, logger
from services.google_maps import Prospect
from services import cache as _cache


# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : "auditer" le site web d'un prospect (HTTPS, mobile, SEO, tracking, formulaire...),
# 📘   calculer un score /100 (bas = beaucoup de défauts = bonne opportunité commerciale pour toi)
# 📘   et récupérer un email de contact. Point d'entrée unique : analyze_prospect().
# 📘 Appelé par : pipeline.py (appli Streamlit, en parallèle via ThreadPoolExecutor), main.py (CLI),
# 📘   tests/test_analyzer.py, tests/test_campaign.py.
# 📘 Appelle : le site du prospect (HTTP via requests), l'API Google PageSpeed Insights,
# 📘   le DNS (dnspython, enregistrements MX), services/cache.py, config.py, google_maps.Prospect.
# 📘 Concepts Python à retenir ici : constantes en MAJUSCULES, dict / tuple / list, type alias,
# 📘   f-strings, try/except + retry, générateurs dans any(), list comprehension, regex (re),
# 📘   BeautifulSoup (find / find_all), fonctions imbriquées, paramètres par défaut, unpacking.
# ---------------------------------------------------------------------------
# Mapping clés de problème → patterns textuels (pour personnalisation email)
# ---------------------------------------------------------------------------

# 📘 Un dict (dictionnaire) associe des clés à des valeurs : {"clé": valeur}. Ici chaque clé
# 📘 technique ("https", "viewport"...) est associée à une liste de mots qu'on cherche dans les
# 📘 messages d'erreur. But : retrouver les clés à partir des messages (ex: depuis le cache, qui
# 📘 ne stocke que les messages), pour personnaliser l'email (voir mailer).
_KEY_PATTERNS = {
    "no_website":    ["pas de site web", "aucun site"],
    "site_down":     ["inaccessible", "down", "ne répond pas"],
    "https":         ["http", "sécurisé", "ssl"],
    "viewport":      ["mobile", "responsive", "viewport"],
    "title":         ["balise title", "titre", "<title>"],
    "meta_description": ["meta description", "description", "snippet"],
    "tracking":      ["tracking", "analytics", "pixel", "mesure", "gtm", "hotjar"],
    "lead_form":     ["formulaire", "contact form", "lead"],
    "free_builder":  ["wix", "jimdo", "squarespace", "shopify", "builder", "weebly", "webnode", "gratuit"],
    "social_links":  ["réseaux sociaux", "social"],
    "response_time": ["lent", "chargement", "performance", "pagespeed", "temps de"],
    "outdated":      ["daté", "obsolète", "ancien", "non mis à jour"],
    "seo_visibility": ["noindex", "trafic organique", "à indexer", "titre h1", "structure seo", "contenu très léger"],
    # Enrichissement sémantique (weight=0 — n'affectent pas le score)
    "no_video":      ["aucune vidéo", "valorisation par la vidéo"],
    "no_gallery":    ["aucune galerie", "valorisation visuelle"],
    "no_blog":       ["aucun blog", "stratégie de contenu"],
    "french_only":   ["uniquement en français", "version traduite"],
    # no_service_mention : ajouté directement dans issue_keys (check dynamique)
}


# 📘 `List[str]` = "liste de chaînes de caractères" (type hint, purement indicatif).
def _extract_issue_keys(issues: List[str]) -> List[str]:
    """Extrait les clés normalisées à partir des messages d'issues."""
    keys: List[str] = []
    for issue_text in issues:
        # 📘 `.items()` parcourt les paires (clé, valeur) du dict ; on les "déballe" dans key, patterns.
        # 📘 `any(p in lower for p in patterns)` : any() renvoie True dès qu'UN élément est vrai.
        # 📘 Le `p in lower for p in patterns` est une "expression génératrice" (une boucle compacte).
        # 📘 Recherche par sous-chaîne => approximatif : "Aucun titre H1" contient "titre" et déclenche
        # 📘 donc aussi la clé "title" en plus de "seo_visibility".
        lower = issue_text.lower()
        for key, patterns in _KEY_PATTERNS.items():
            if any(p in lower for p in patterns) and key not in keys:
                keys.append(key)
    return keys


# ---------------------------------------------------------------------------
# Seuils et constantes
# ---------------------------------------------------------------------------

# 📘 Constantes : en Python rien n'est vraiment constant, c'est la convention MAJUSCULES qui dit
# 📘 "ne modifie pas". Les centraliser en haut évite les "nombres magiques" perdus dans le code.
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
# Check visibilité SEO — proxy gratuit du "trafic organique" (noindex, contenu, structure)
CHECK_SEO_VISIBILITY   = "seo_visibility"

# 📘 Poids par défaut de chaque check = nb de points retirés au score si le problème est détecté.
# 📘 Un poids 0 = check désactivé (ou purement informatif). Les profils métier peuvent surcharger.
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
    # Visibilité SEO — proxy gratuit du trafic organique (aucune API, 0 €)
    CHECK_SEO_VISIBILITY: MAJOR_WEIGHT,
}

# 📘 Type alias : on donne un nom à un type complexe. Tuple[str, int] = paire fixe (message, poids).
# Type interne : liste de (message, poids)
_IssueList = List[Tuple[str, int]]

# Constructeurs de sites gratuits — leur présence = opportunité de refonte pro
# 📘 Un tuple ( , , ) est une liste NON modifiable : parfait pour des listes de référence fixes.
_FREE_BUILDERS = (
    "wix.com", "jimdo.com", "webnode.fr", "webself.net",
    "site123.com", "weebly.com", "yola.com",
)

# Signatures de scripts de tracking dans le HTML
# 📘 Détection naïve par sous-chaîne dans le HTML. "ga(" peut matcher d'autres mots (ex: "mega(")
# 📘 => faux positifs possibles, le site paraîtra "équipé" alors qu'il ne l'est pas.
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

# 📘 Tuple[requests.Response | None, float] : la fonction renvoie 2 valeurs (réponse ou None, durée).
# 📘 `X | None` = "X ou None" (même sens qu'Optional[X]).
def _fetch(url: str) -> Tuple[requests.Response | None, float]:
    """
    Charge une URL avec retry exponentiel (2 tentatives supplémentaires : 2s, 4s).
    Retourne (None, 0.0) si toutes les tentatives échouent.
    """
    # 📘 Si l'URL n'a pas de schéma (ex: "monsite.fr"), on préfixe https:// pour que requests l'accepte.
    if not url.startswith("http"):
        url = "https://" + url
    last_exc: Exception | None = None
    # 📘 Boucle de "retry" : range(3) donne 0, 1, 2 -> 1 essai + 2 nouvelles tentatives.
    for attempt in range(_FETCH_MAX_RETRIES + 1):
        try:
            # 📘 perf_counter() = chronomètre précis, pour mesurer le temps de réponse du site.
            start = time.perf_counter()
            # 📘 requests.get télécharge la page. timeout = abandon si trop long (sinon on peut attendre à
            # 📘 l'infini). User-Agent = "carte d'identité" du client HTTP ; certains sites bloquent les robots.
            # 📘 allow_redirects=True : suit les redirections (http -> https, domaine -> www...).
            resp = requests.get(
                url,
                timeout=config.request_timeout,
                headers={"User-Agent": "Mozilla/5.0 (compatible; ProspectBot/1.0)"},
                allow_redirects=True,
            )
            elapsed = time.perf_counter() - start
            return resp, elapsed
        # 📘 RequestException = classe mère de toutes les erreurs réseau de requests (timeout, DNS...).
        # 📘 `as exc` récupère l'objet erreur pour pouvoir l'afficher plus tard.
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < _FETCH_MAX_RETRIES:
                # 📘 "Backoff exponentiel" : on attend de plus en plus longtemps (2s puis 4s) entre les essais,
                # 📘 pour laisser au serveur le temps de se remettre. `**` = puissance.
                delay = 2 ** (attempt + 1)  # 2s, puis 4s
                # 📘 logger.debug("... %s ...", valeur) : le %s est remplacé par la valeur seulement si le message
                # 📘 est réellement affiché (plus efficace qu'une f-string dans les logs).
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

# 📘 Tous les checks suivent le même "contrat" : ils reçoivent la liste `issues` et y AJOUTENT
# 📘 (append) un tuple (message, poids) si le problème est trouvé. Ils ne renvoient rien (-> None) :
# 📘 ils modifient la liste passée en paramètre (une liste est "mutable", passée par référence).
# 📘 `weight: int = CRITICAL_WEIGHT` = paramètre optionnel avec valeur par défaut.
def _check_https(url: str, issues: _IssueList, weight: int = CRITICAL_WEIGHT) -> None:
    """HTTPS absent = pénalité SEO + alerte navigateur + signal de méfiance."""
    # 📘 ⚠️ On teste l'URL fournie par Google Maps, pas l'URL finale après redirection :
    # 📘 un site "http://..." qui redirige vers https sera quand même pénalisé.
    # 💡 Utiliser resp.url (URL finale après redirections, renvoyée par _fetch) éviterait ce faux
    # 💡   positif ; même chose pour une URL stockée sans schéma ("monsite.fr").
    if not url.startswith("https://"):
        issues.append((
            "Site sans HTTPS (connexion non sécurisée, pénalité SEO Google)",
            weight,
        ))


def _check_response_time(elapsed: float, issues: _IssueList, weight: int = MAJOR_WEIGHT) -> None:
    """Temps de réponse > 3s = mauvaise expérience utilisateur + pénalité SEO."""
    # 📘 f-string : f"...{variable}..." insère la valeur dans le texte. `{elapsed:.1f}` = 1 décimale.
    # 📘 Deux chaînes côte à côte entre parenthèses sont automatiquement collées (concaténation).
    if elapsed > SLOW_RESPONSE_THRESHOLD_S:
        issues.append((
            f"Temps de chargement élevé ({elapsed:.1f}s > {SLOW_RESPONSE_THRESHOLD_S}s) "
            "→ impact SEO et expérience utilisateur",
            weight,
        ))


def _check_viewport(soup: BeautifulSoup, issues: _IssueList, weight: int = CRITICAL_WEIGHT) -> None:
    """Meta viewport absente = site non responsive = perte de ~60 % du trafic mobile."""
    # 📘 soup.find(balise, attrs={...}) renvoie la PREMIÈRE balise correspondante, ou None.
    # 📘 Ici on cherche <meta name="viewport">, indispensable pour un affichage correct sur mobile.
    if not soup.find("meta", attrs={"name": "viewport"}):
        issues.append((
            "Absence de meta viewport → site probablement non responsive (mobile)",
            weight,
        ))


def _check_title(soup: BeautifulSoup, issues: _IssueList, weight: int = MAJOR_WEIGHT) -> None:
    """Balise <title> obligatoire pour le SEO on-page."""
    title = soup.find("title")
    # 📘 get_text(strip=True) = texte de la balise sans espaces autour. `not title` gère le cas None.
    if not title or not title.get_text(strip=True):
        issues.append((
            "Absence de balise <title> → SEO on-page défaillant",
            weight,
        ))


def _check_meta_description(soup: BeautifulSoup, issues: _IssueList, weight: int = MINOR_WEIGHT) -> None:
    """Meta description = snippet affiché dans Google. Son absence réduit le CTR."""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    # 📘 .get("content", "") lit un attribut HTML avec valeur par défaut "" s'il est absent.
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
    # 📘 find_all renvoie une LISTE de toutes les balises trouvées (vide si aucune -> "falsy").
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
    # 📘 On concatène URL + HTML en minuscules pour ne faire qu'une recherche. `return` sort de la
    # 📘 fonction dès le premier builder trouvé (pour ne pas pénaliser deux fois).
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
    # 📘 Générateur à DOUBLE boucle : pour chaque lien <a>, pour chaque domaine social... any() s'arrête
    # 📘 au premier True trouvé. `(a["href"] or "")` évite une erreur si href est vide/None.
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
    # 📘 Sortie anticipée ("early return") : si le check est désactivé ou sans clé API, on ne fait rien.
    if weight == 0 or not config.google_api_key:
        return
    for attempt in range(3):
        try:
            # 📘 Appel à l'API Google PageSpeed (Lighthouse) : elle charge le site sur un mobile simulé et
            # 📘 renvoie un score de performance entre 0 et 1. params= construit l'URL ?url=...&strategy=...
            # 📘 Timeout de 30 s : cette API est lente (elle charge vraiment le site).
            resp = requests.get(
                "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                params={"url": url, "strategy": "mobile", "key": config.google_api_key},
                timeout=30,
            )
            # 📘 HTTP 429 = "Too Many Requests" (quota/rythme dépassé) -> on attend et `continue` = on passe
            # 📘 directement au tour de boucle suivant.
            if resp.status_code == 429 and attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            if not resp.ok:
                logger.debug("    ⚠️  PageSpeed API HTTP %d pour %s", resp.status_code, url)
                return
            # 📘 resp.json() convertit la réponse JSON en dict Python ; on descend dans les clés imbriquées.
            # 📘 Si une clé manque -> KeyError, rattrapée par le except plus bas.
            score = int(resp.json()["lighthouseResult"]["categories"]["performance"]["score"] * 100)
            if score < 50:
                issues.append((
                    f"Performance mobile mauvaise (PageSpeed : {score}/100) "
                    "→ site très lent sur smartphone, pénalité SEO Core Web Vitals",
                    weight,
                ))
            elif score < 70:
                # 📘 Remarque : pour un score moyen on applique MINOR_WEIGHT fixe, pas le poids du profil.
                issues.append((
                    f"Performance mobile moyenne (PageSpeed : {score}/100) "
                    "→ optimisations nécessaires (images, JS, CSS)",
                    MINOR_WEIGHT,
                ))
            else:
                logger.debug("    ✅ PageSpeed mobile OK : %d/100 pour %s", score, url)
            return
        # 📘 On peut rattraper plusieurs types d'erreurs d'un coup avec un tuple d'exceptions.
        # 💡 En cas de KeyError/ValueError (réponse mal formée) on retente quand même 2 fois avec pause :
        # 💡   inutile, seules les erreurs réseau méritent un retry. Et chaque appel prend souvent 10-30 s :
        # 💡   c'est de loin le check le plus lent, un cache dédié ou une option pour le couper aiderait.
        except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
            else:
                logger.debug("    ⚠️  PageSpeed API indisponible pour %s : %s", url, exc)


def _check_seo_visibility(soup: BeautifulSoup, issues: _IssueList, weight: int = MAJOR_WEIGHT) -> None:
    """
    Proxy GRATUIT du trafic organique (« passages sur le site ») — aucune API.

    On ne peut pas mesurer les visites réelles sans outil payant (SEMrush…),
    mais on détecte les bloqueurs concrets qui privent un site de trafic Google :
      1. noindex   → le site est explicitement exclu de Google = 0 trafic organique
      2. contenu très léger → quasi rien à indexer → faible visibilité
      3. pas de H1 → structure SEO faible, Google comprend mal la page
    """
    if weight == 0:
        return

    # 1. noindex — bloqueur le plus grave (site volontairement invisible)
    # 📘 re.compile(r"^(robots|googlebot)$", re.I) = regex : ^ début, $ fin, | = "ou", re.I = ignore
    # 📘 majuscules. Le préfixe r"..." (raw string) évite d'avoir à doubler les antislashs.
    # 📘 BeautifulSoup accepte une regex comme valeur d'attribut à matcher.
    robots = soup.find("meta", attrs={"name": re.compile(r"^(robots|googlebot)$", re.I)})
    if robots and "noindex" in (robots.get("content", "") or "").lower():
        issues.append((
            "Site en noindex → explicitement exclu de Google, il ne reçoit "
            "aucun trafic organique (visibilité quasi nulle dans les recherches)",
            CRITICAL_WEIGHT,
        ))
        return  # inutile d'évaluer le reste : la page n'est de toute façon pas indexée

    # 2. Contenu très léger → peu de matière à référencer
    # 📘 get_text(separator=" ") = tout le texte visible (+ scripts inline) ; .split() découpe en mots.
    word_count = len(soup.get_text(separator=" ", strip=True).split())
    if word_count < 200:
        issues.append((
            f"Contenu très léger en page d'accueil (~{word_count} mots) → peu de "
            "contenu à indexer, donc faible visibilité et trafic organique sur Google",
            weight,
        ))

    # 3. Absence de titre H1 → structure SEO faible
    if not soup.find("h1"):
        issues.append((
            "Aucun titre H1 détecté → structure SEO faible, Google identifie mal "
            "le sujet de la page (pénalise le référencement et le trafic)",
            MINOR_WEIGHT,
        ))


def _check_delivery_covered(
    soup: BeautifulSoup, html: str, issues: _IssueList, weight: int = CRITICAL_WEIGHT,
) -> None:
    """Détecte si l'établissement propose déjà de la livraison (propre ou via plateforme)."""
    if weight == 0:
        return
    # 📘 Mode "coursier/livreur" : ici DÉTECTER de la livraison est un point NÉGATIF pour le prospect
    # 📘 (le commerce n'a pas besoin de toi). Check désactivé par défaut (poids 0).
    text = soup.get_text().lower()
    # 📘 " ".join(liste) colle les éléments d'une liste avec un espace entre chacun.
    hrefs = " ".join(a.get("href", "").lower() for a in soup.find_all("a", href=True))
    combined = text + " " + hrefs + " " + html.lower()
    if any(kw in combined for kw in _DELIVERY_KEYWORDS) or \
       any(p in combined for p in _DELIVERY_PLATFORMS):
        issues.append((
            "Livraison déjà gérée (service propre ou plateforme tierce) "
            "→ opportunité réduite pour un coursier externe",
            weight,
        ))


# 📘 Optional[str] = renvoie le nom du CMS (ex: "WordPress") ou None si inconnu.
# 📘 CMS = logiciel qui génère le site (WordPress, Wix...). L'ordre du dict compte : premier trouvé.
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
    # 📘 Regex : (?:...) = groupe NON capturant (sert juste au "ou"), \s* = espaces éventuels,
    # 📘 (\d{4}) = 4 chiffres capturés. findall renvoie la liste des années capturées.
    matches = re.findall(r'(?:©|&copy;|copyright)\s*(\d{4})', html, re.IGNORECASE)
    if matches:
        # 📘 List comprehension : [expression for x in liste if condition] construit une nouvelle liste
        # 📘 en une ligne. Ici : années plausibles converties en entiers (int).
        years = [int(y) for y in matches if 2000 <= int(y) <= current_year]
        # 📘 Copyright le plus récent vieux de 3 ans ou plus => site probablement plus entretenu.
        if years and current_year - max(years) >= 3:
            issues.append((
                f"Site non mis à jour depuis {max(years)} "
                "→ risque d'obsolescence technique et de contenu",
                weight,
            ))


# ---------------------------------------------------------------------------
# Checks d'enrichissement sémantique (weight=0 — n'affectent pas le score)
# ---------------------------------------------------------------------------

# 📘 Les 4 checks ci-dessous ont un poids 0 : ils n'enlèvent aucun point, mais leurs messages
# 📘 alimentent issue_keys pour proposer d'autres services (vidéo, photo, blog, traduction).
_GALLERY_SIGNALS = [
    "gallery", "galerie", "carousel", "slider", "lightbox",
    "swiper", "splide", "isotope", "masonry", "portfolio", "photos",
]

def _check_no_video(html: str, soup: BeautifulSoup, issues: _IssueList, weight: int = 0) -> None:
    """Absence de vidéo = opportunité pour un vidéaste / motion designer."""
    video_signals = ["<video", "youtube.com/embed", "player.vimeo.com", "youtu.be", "dailymotion.com"]
    if any(s in html.lower() for s in video_signals):
        return
    iframes = soup.find_all("iframe", src=True)
    # 📘 any() imbriqué : pour chaque iframe, est-ce que son src contient youtube/vimeo ?
    if any(any(v in (f.get("src") or "").lower() for v in ["youtube", "vimeo", "youtu.be"]) for f in iframes):
        return
    issues.append((
        "Aucune vidéo de présentation détectée → opportunité de valorisation par la vidéo",
        weight,
    ))


def _check_no_gallery(soup: BeautifulSoup, issues: _IssueList, weight: int = 0) -> None:
    """Absence de galerie photo = opportunité pour un photographe / graphiste."""
    # 📘 str(soup) reconvertit l'arbre BeautifulSoup en texte HTML complet.
    html_lower = str(soup).lower()
    if any(s in html_lower for s in _GALLERY_SIGNALS):
        return
    # Beaucoup d'images = galerie implicite
    imgs = soup.find_all("img", src=True)
    # 📘 Comprehension avec filtre : on garde les images dont le src ne ressemble pas à une icône/logo.
    non_icon_imgs = [
        img for img in imgs
        if not any(s in (img.get("src") or "").lower() for s in ["icon", "logo", "favicon", "sprite"])
    ]
    if len(non_icon_imgs) >= 6:
        return
    issues.append((
        "Aucune galerie photo ou portfolio détecté → opportunité de valorisation visuelle",
        weight,
    ))


def _check_no_blog(soup: BeautifulSoup, html: str, issues: _IssueList, weight: int = 0) -> None:
    """Absence de blog ou contenus éditoriaux."""
    blog_signals = ["blog", "actualités", "actualites", "nos articles", "nos conseils", "publications"]
    if any(s in html.lower() for s in blog_signals):
        return
    if soup.find("article"):
        return
    # 📘 `lambda h: ...` = petite fonction anonyme d'une ligne. BeautifulSoup l'appelle pour chaque
    # 📘 valeur de href ; `h and ...` évite l'erreur quand h vaut None.
    if soup.find_all("a", href=lambda h: h and "blog" in h.lower()):
        return
    issues.append((
        "Aucun blog ou section actualités détecté → opportunité de stratégie de contenu",
        weight,
    ))


def _check_french_only(html: str, issues: _IssueList, weight: int = 0) -> None:
    """Site uniquement en français — opportunité pour un traducteur."""
    intl_signals = [
        "english", "español", "deutsch", "italiano", "português",
        "/en/", "/es/", 'lang="en"', "lang='en'",
        "in english", "en anglais", "translate",
    ]
    if not any(s in html.lower() for s in intl_signals):
        issues.append((
            "Site uniquement en français — pas de version traduite détectée → opportunité de traduction",
            weight,
        ))


# ---------------------------------------------------------------------------
# Vérification MX d'email
# ---------------------------------------------------------------------------

# 📘 DNS = "annuaire" d'Internet. Un enregistrement MX indique quel serveur reçoit les emails
# 📘 d'un domaine. Pas de MX (domaine inexistant) => l'email ne peut pas exister.
def _verify_email_mx(email: str) -> bool:
    """Retourne True si le domaine email a au moins un enregistrement MX valide.
    Retourne True aussi si le DNS est injoignable (timeout / réseau) pour ne pas
    rejeter d'emails valides à cause d'une indisponibilité réseau passagère.
    Retourne False uniquement si le domaine est confirmé inexistant (NXDOMAIN)."""
    try:
        # 📘 Import "paresseux" DANS la fonction : dnspython n'est chargé que si on en a besoin (et si le
        # 📘 paquet manque, l'ImportError est attrapée par le except => on renvoie True).
        import dns.resolver
        # 📘 split("@", 1) coupe en 2 morceaux max ; [1] = la partie après le @ (le domaine).
        domain = email.split("@", 1)[1]
        dns.resolver.resolve(domain, "MX")
        return True
    # 📘 `except Exception` attrape (presque) TOUT. type(exc).__name__ = nom de la classe d'erreur,
    # 📘 utilisé ici pour distinguer "domaine inexistant" des soucis réseau.
    # 💡 Tester le nom de classe en texte est fragile : mieux vaut
    # 💡   `except (dns.resolver.NXDOMAIN, dns.resolver.NoNameservers): return False` explicitement.
    # 💡   services/email_check.py fait déjà une vérif MX plus complète : réutilise-la.
    except Exception as exc:
        exc_name = type(exc).__name__
        # Domaine inexistant → rejet certain
        if "NXDOMAIN" in exc_name or "NoNameservers" in exc_name:
            return False
        # Tout le reste (timeout, NoAnswer, réseau indispo, tests) → on laisse passer
        return True


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
    # 📘 Regex d'un email : [caractères autorisés]+ @ domaine . extension de 2 lettres ou plus.
    # 📘 re.compile "pré-compile" la regex pour la réutiliser plus vite.
    _EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

    # 📘 Fonction imbriquée (définie DANS une autre) : visible seulement ici, et elle peut lire les
    # 📘 variables de la fonction englobante (_EMAIL_RE). Pratique pour une aide locale.
    def _extract(html: str) -> Optional[str]:
        # Priorité aux liens mailto: (email explicitement mis en lien)
        # 📘 finditer parcourt toutes les correspondances ; match.group(1) = ce qui est capturé par la
        # 📘 1re paire de parenthèses (l'email sans le "mailto:").
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
    # 📘 urlparse découpe une URL : scheme ("https") + netloc ("www.site.fr"). On reconstruit la racine
    # 📘 du site pour tester les pages de contact classiques.
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    # 📘 On essaie jusqu'à 4 URLs à la suite : dans le pire cas, 4 x timeout par prospect.
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
        # 📘 `continue` : en cas d'erreur réseau sur une page, on passe simplement à la suivante.
        except requests.RequestException:
            continue

    return None


# ---------------------------------------------------------------------------
# Fonction principale exportée
# ---------------------------------------------------------------------------

# 📘 Fonction principale, la seule "publique" (sans _ devant) : c'est elle que pipeline/main
# 📘 appellent. `Dict[str, int] | None = None` : paramètre optionnel. On ne met JAMAIS un dict {}
# 📘 comme valeur par défaut (il serait partagé entre tous les appels) : None puis test, c'est
# 📘 le bon réflexe Python.
def analyze_prospect(
    prospect: Prospect,
    weight_overrides: Dict[str, int] | None = None,
    detection_keywords: Optional[List[str]] = None,
    candidacy: bool = False,
) -> Prospect:
    """
    Analyse complète du prospect.

    Cas particuliers gérés :
    - Pas de site → score 0, problème unique "pas de site web"
    - Site inaccessible → score 5, problème unique "site down"
    - Site normal → checks pondérés + enrichissement sémantique + scraping email

    weight_overrides : dict optionnel pour surcharger les poids par défaut.
    detection_keywords : mots-clés métier du profil ; leur absence → no_service_mention.
    candidacy : mode candidature freelance — on N'AUDITE PAS le site, on récupère
      juste le contact et on retient toutes les cibles (score neutre).

    Retourne le prospect enrichi (issues, score, email, issue_keys).
    """
    # --- Mode candidature freelance : aucun audit, on veut juste le contact ---
    # 📘 Mode candidature : on n'évalue pas le site, on cherche juste l'email et le CMS.
    if candidacy:
        prospect.issues = []
        prospect.issue_keys = []
        prospect.score = 100  # neutre → ne filtre personne
        if prospect.has_website():
            try:
                # 📘 `resp, _ = ...` : déballage d'un tuple ; `_` = "variable dont je me fiche" (ici la durée).
                resp, _ = _fetch(prospect.website)
                if resp is not None:
                    # 📘 "lxml" = moteur d'analyse HTML rapide utilisé par BeautifulSoup (paquet lxml requis).
                    soup = BeautifulSoup(resp.text, "lxml")
                    prospect.cms = _detect_cms(prospect.website, resp.text)
                    email = _scrape_email(prospect.website, soup)
                    if email:
                        prospect.email = email
            # 📘 `except Exception: pass` avale toute erreur en silence : pratique pour ne jamais bloquer la
            # 📘 campagne, mais tu ne sauras jamais pourquoi un email n'a pas été trouvé.
            except Exception:
                pass
        logger.info("  ✅ %s — cible retenue (candidature)", prospect.name)
        return prospect

    # Construction du dict de poids (défauts + surcharges du profil)
    # 📘 dict(_DEFAULT_WEIGHTS) fait une COPIE : on peut la modifier sans toucher aux défauts globaux.
    # 📘 .update() écrase les clés existantes avec celles du profil.
    weights = dict(_DEFAULT_WEIGHTS)
    if weight_overrides:
        weights.update(weight_overrides)

    # Cas 1 : pas de site web du tout → opportunité maximale
    if not prospect.has_website():
        prospect.issues = [
            "Pas de site web référencé → opportunité directe de création de site"
        ]
        prospect.issue_keys = ["no_website"]
        prospect.score = 0
        logger.info("  📵 %s : pas de site web → opportunité maximale.", prospect.name)
        return prospect

    url = prospect.website

    # Cache hit — évite de refaire fetch + checks pour un site déjà analysé (<30 j)
    # 📘 Consultation du cache disque (services/cache.py) avant de refaire tout le travail réseau.
    # 💡 Le cache est indexé par URL seule, alors que le score dépend des poids du profil
    # 💡   (weight_overrides) : un site analysé avec le profil A ressort avec le score de A sous le
    # 💡   profil B. Stocker la liste (message, poids) brute et recalculer le score, ou inclure le
    # 💡   profil dans la clé, corrigerait ça.
    cached = _cache.get_cached(url)
    if cached:
        prospect.issues = cached["issues"]
        prospect.score  = cached["score"]
        # 📘 cached["x"] plante si la clé manque ; cached.get("x") renvoie None : plus tolérant.
        prospect.email  = cached.get("email")
        prospect.cms    = cached.get("cms")
        prospect.issue_keys = _extract_issue_keys(prospect.issues)
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
        prospect.issue_keys = ["site_down"]
        prospect.score = 5
        return prospect

    html = resp.text
    # 📘 On parse le HTML une seule fois et on partage `soup` avec tous les checks (économie de CPU).
    soup = BeautifulSoup(html, "lxml")
    weighted_issues: _IssueList = []

    # Cas 3 : site accessible → lancement des checks pondérés
    # 📘 Chaque check reçoit son poids depuis le dict `weights` (défaut ou surcharge du profil).
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
    _check_seo_visibility(soup, weighted_issues,    weights[CHECK_SEO_VISIBILITY])

    # Enrichissement sémantique (weight=0 — stocké en cache, enrichit les emails)
    # 📘 Pas de poids passé : ils prennent leur valeur par défaut `weight=0`.
    _check_no_video(html, soup, weighted_issues)
    _check_no_gallery(soup, weighted_issues)
    _check_no_blog(soup, html, weighted_issues)
    _check_french_only(html, weighted_issues)

    # Détection du CMS (pas un check, pas de pénalité — utilisé pour personnaliser l'email)
    prospect.cms = _detect_cms(url, html)
    if prospect.cms:
        logger.debug("  🧩 CMS détecté : %s pour %s", prospect.cms, prospect.name)

    # Check volume d'activité (données Google, pas HTML)
    low_vol_weight = weights.get(CHECK_LOW_VOLUME, 0)
    # 📘 user_ratings_total vient de Google Maps (nombre d'avis), pas du site. Check désactivé par
    # 📘 défaut (poids 0), activable par les profils.
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

    # Score final pondéré (les enrichissements à weight=0 n'impactent pas le score)
    # 📘 Deux comprehensions avec déballage : `for msg, _ in weighted_issues` parcourt les tuples.
    # 📘 Score = 100 - somme des poids, borné à 0 minimum avec max(0, ...).
    prospect.issues = [msg for msg, _ in weighted_issues]
    prospect.score = max(0, MAX_SCORE - sum(w for _, w in weighted_issues))
    prospect.issue_keys = _extract_issue_keys(prospect.issues)

    # no_service_mention : check dynamique non mis en cache (dépend du profil courant)
    # 📘 Si le profil fournit des mots-clés métier et qu'AUCUN n'apparaît sur le site, on marque que
    # 📘 le prospect ne parle pas de ce service (argument commercial pour l'email).
    if detection_keywords and not any(kw.lower() in html.lower() for kw in detection_keywords):
        prospect.issue_keys.append("no_service_mention")

    # 📘 Expression conditionnelle (ternaire) : A if condition else B, ici imbriquée pour 3 niveaux.
    level = "🟢" if prospect.score >= 70 else ("🟡" if prospect.score >= 40 else "🔴")
    logger.info(
        "  %s %s → score %d/100 | %d problème(s)",
        level, prospect.name, prospect.score, len(weighted_issues),
    )
    # 📘 enumerate(liste, 1) donne (numéro, élément) en commençant à 1 ; on déballe le tuple interne.
    for i, (msg, weight) in enumerate(weighted_issues, 1):
        logger.debug("      %d. [-%d pts] %s", i, weight, msg)

    # Mise en cache du résultat (évite de refaire l'analyse dans les 30 prochains jours)
    _cache.set_cached(url, prospect.issues, prospect.score, prospect.email, prospect.cms)

    return prospect
