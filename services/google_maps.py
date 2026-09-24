"""
services/google_maps.py — Recherche de prospects via l'API Google Places.

Flux :
  1. Text Search  → liste brute de lieux (jusqu'à 60 résultats, 3 pages Google)
  2. Place Details → détails complets de chaque lieu (tel, site, note…)
  3. Retourne une liste d'objets Prospect typés

Doc API : https://developers.google.com/maps/documentation/places/web-service
"""

from __future__ import annotations

# 📘 time : module standard (ici time.sleep(n) = attendre n secondes).
# 📘 Optional[str] = "du texte OU None" ; List[dict] = "liste de dictionnaires".
import time
from dataclasses import dataclass, field
from typing import List, Optional

# 📘 requests : LA librairie pour faire des appels HTTP (comme un navigateur, mais en code).
# 📘 requests.get(url, params=..., timeout=...) envoie une requête GET et renvoie une réponse.
import requests

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : (1) définir la classe Prospect, la "fiche entreprise" utilisée PARTOUT dans le projet ;
# 📘   (2) chercher des entreprises sur Google Maps via l'API Google Places.
# 📘 Appelé par : pipeline.py (fetch_raw_candidates, build_prospect), main.py (search_prospects),
# 📘   et presque tous les modules pour la classe Prospect (analyzer, mailer, gmail, sms,
# 📘   notion_sync, crm/*, sources/*, offers.py, crm_store.py, history_manager.py…).
# 📘 Appelle : API Google Places (Text Search puis Place Details), phonenumbers (optionnel), config.
# 📘 Concepts Python à retenir ici : @dataclass, Optional, @classmethod, méthode et self,
# 📘   requests + raise_for_status, pagination par jeton, retry avec backoff exponentiel, f-string.
# 📘 pipeline.py remplace `config` et `logger` de CE module avant chaque campagne (gm_mod.config
# 📘 = ...) : ici la config est donc bien à jour, contrairement aux modules services/sources/*.
from config import config, logger


# ---------------------------------------------------------------------------
# Modèle Prospect — partagé par tous les modules
# ---------------------------------------------------------------------------

# 📘 @dataclass : génère le constructeur. Prospect(place_id=..., name=..., ...) crée une fiche.
# 📘 Les attributs SANS valeur par défaut (place_id → keyword) sont obligatoires ; ceux avec
# 📘 `= ...` sont facultatifs. Python impose : obligatoires d'abord, facultatifs ensuite.
# 📘 C'est le "modèle de données" commun : chaque source (Maps, Sirene, Pages Jaunes…) fabrique
# 📘 des Prospect, puis chaque étape (analyse, email, CRM) les complète.
# 💡 Ce modèle partagé vit dans le fichier d'UNE source (Google Maps). Le déplacer dans un
# 💡   models.py neutre clarifierait les dépendances (les sources n'importeraient plus google_maps).
@dataclass
class Prospect:
    place_id: str               # Identifiant unique Google Places (sert à dédupliquer)
    name: str                   # Nom de l'établissement
    address: str                # Adresse complète
    phone: Optional[str]        # Numéro de téléphone (format local, ex: 04 78 xx xx xx)
    website: Optional[str]      # URL du site web (None si pas de site)
    rating: Optional[float]     # Note Google (0-5)
    user_ratings_total: int     # Nombre d'avis Google
    keyword: str                # Mot-clé ayant permis de trouver ce prospect
    maps_url: str = ""          # Lien Google Maps vers la fiche
    # Remplis par analyzer.py
    # 📘 field(default_factory=list) : chaque Prospect reçoit SA propre liste vide. Écrire `= []`
    # 📘 directement est interdit par dataclass : la même liste serait partagée par toutes les fiches.
    issues: List[str] = field(default_factory=list)  # Problèmes détectés sur le site
    issue_keys: List[str] = field(default_factory=list)  # Clés normalisées des problèmes (pour personnalisation email)
    score: int = 0              # Score de 0 à 100 (plus bas = plus d'opportunités)
    email: Optional[str] = None # Email scrapé sur le site du prospect
    cms: Optional[str] = None   # CMS/builder détecté (ex: "WordPress", "Wix")
    # Rempli par mailer.py
    email_draft: str = ""       # Brouillon de cold email prêt à envoyer
    # Rempli par services/dirigeants.py (registre Sirène, données publiques)
    siren: str = ""             # Numéro SIREN de l'entreprise
    dirigeant: str = ""         # « Jean Dupont » — représentant légal
    dirigeant_qualite: str = "" # « Président », « Gérant », « Directeur général »…
    # Rempli par services/email_check.py
    email_status: str = ""        # « valide » | « risque » | « invalide »
    email_status_reason: str = "" # explication lisible

    # 📘 Méthode : `self` = la fiche sur laquelle on appelle p.has_website(). bool(...) → True/False.
    def has_website(self) -> bool:
        """Retourne True si le prospect a un site web valide."""
        return bool(self.website and self.website.startswith("http"))

    # 📘 @classmethod : méthode appelée sur la CLASSE (Prospect.from_dict(d)), qui reçoit la classe
    # 📘 dans `cls` au lieu d'une instance. Pratique pour des "constructeurs alternatifs".
    # 📘 `cls(**dict)` : ** "déballe" le dict en arguments nommés (clé=valeur). On ne garde que les
    # 📘 clés qui sont de vrais champs, pour tolérer d'anciens JSON avec des clés en trop.
    @classmethod
    def from_dict(cls, d: dict) -> "Prospect":
        """Reconstruit un Prospect depuis un dict (inverse de to_dict)."""
        import dataclasses
        fields = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in fields})

    # 💡 to_dict recopie chaque champ à la main : un champ ajouté à la classe et oublié ici ne serait
    # 💡   jamais sauvegardé. dataclasses.asdict(self) fait la même chose automatiquement.
    def to_dict(self) -> dict:
        """Sérialise le prospect en dict pour export JSON/CSV."""
        return {
            "place_id": self.place_id,
            "name": self.name,
            "address": self.address,
            "phone": self.phone,
            "website": self.website,
            "rating": self.rating,
            "user_ratings_total": self.user_ratings_total,
            "keyword": self.keyword,
            "maps_url": self.maps_url,
            "issues": self.issues,
            "issue_keys": self.issue_keys,
            "score": self.score,
            "email": self.email,
            "cms": self.cms,
            "email_draft": self.email_draft,
            "siren": self.siren,
            "dirigeant": self.dirigeant,
            "dirigeant_qualite": self.dirigeant_qualite,
            "email_status": self.email_status,
            "email_status_reason": self.email_status_reason,
        }


# ---------------------------------------------------------------------------
# Appels API Google Places
# ---------------------------------------------------------------------------

# 📘 Constante de module (MAJUSCULES par convention) : l'URL de base de l'API Google.
BASE_URL = "https://maps.googleapis.com/maps/api"


# 📘 Fonction "privée" : le `_` initial signale "usage interne à ce fichier" (simple convention).
def _normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Normalise un numéro au format national français (0X XX XX XX XX).
    Fallback silencieux sur la valeur brute si phonenumbers est indisponible ou invalide."""
    if not raw:
        return None
    # 📘 Import DANS la fonction + `except Exception: pass` : si phonenumbers manque ou si le numéro
    # 📘 est bizarre, on ignore l'erreur et on renvoie le numéro brut (dernière ligne).
    try:
        import phonenumbers
        parsed = phonenumbers.parse(raw, "FR")
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)
    except Exception:
        pass
    return raw
# Google Places Text Search renvoie max 3 pages × 20 = 60 résultats par requête
GOOGLE_MAX_RESULTS = 60


# 📘 Étape 1 de la recherche Maps : liste BRUTE des lieux (nom, place_id…), sans téléphone ni site.
def fetch_raw_candidates(keyword: str, max_raw: int = GOOGLE_MAX_RESULTS) -> List[dict]:
    """
    Récupère jusqu'à `max_raw` résultats bruts via Google Places Text Search.
    Gère la pagination automatiquement (next_page_token).
    Retry exponentiel (2s, 4s, 8s) sur la première page uniquement.
    """
    # 📘 f-string : f"{BASE_URL}/place/..." insère la valeur des variables entre { } dans le texte.
    # 📘 `params` = paramètres ajoutés à l'URL (?query=...&key=...) ; requests les encode pour toi.
    # 📘 Selon la doc Google, `radius` ne sert qu'avec un paramètre `location` (lat,lng), absent ici :
    # 📘   la zone vient en pratique du texte "mot-clé + ville" de la requête.
    url = f"{BASE_URL}/place/textsearch/json"
    params = {
        "query": f"{keyword} {config.search_location}",
        "radius": config.search_radius,
        "key": config.google_api_key,
        "language": "fr",
    }
    results: List[dict] = []
    is_first_page = True
    token_retries = 0   # le next_page_token met 2-5s à devenir valide côté Google

    # 📘 Pagination : Google renvoie 20 résultats par page + un `next_page_token`. On boucle
    # 📘 (`while True` … `break`) en redemandant avec ce jeton, jusqu'à max_raw ou plus de jeton.
    while True:
        max_attempts = 3 if is_first_page else 1
        data = None
        # 📘 Retry avec backoff exponentiel : en cas d'erreur réseau, on réessaie après 2 s puis 4 s
        # 📘 (2 ** (attempt + 1)). `for ... break` : on sort de la boucle dès que ça marche.
        for attempt in range(max_attempts):
            try:
                resp = requests.get(url, params=params, timeout=config.request_timeout)
                # 📘 raise_for_status() lève une exception si le code HTTP est une erreur (4xx/5xx).
                # 📘 resp.json() transforme le texte JSON de la réponse en dict Python.
                resp.raise_for_status()
                data = resp.json()
                break
            # 📘 requests.RequestException : famille de toutes les erreurs requests (timeout, DNS, HTTP…).
            # 💡 Sécurité : le message d'une erreur HTTP de requests contient l'URL complète, donc `key=`
            # 💡   (ta clé API Google) finit en clair dans les logs. Masquer la clé avant de logger exc.
            except requests.RequestException as exc:
                if attempt < max_attempts - 1:
                    delay = 2 ** (attempt + 1)
                    logger.debug("    ↩️  Text Search retry %d/%d dans %ds… ('%s')", attempt + 1, max_attempts, delay, keyword)
                    time.sleep(delay)
                else:
                    logger.error("Erreur Text Search pour '%s' : %s", keyword, exc)
        if data is None:
            break
        is_first_page = False

        # 📘 Google répond HTTP 200 même en cas de souci : le vrai verdict est le champ "status" du JSON
        # 📘 (OK, ZERO_RESULTS, INVALID_REQUEST, OVER_QUERY_LIMIT, REQUEST_DENIED…).
        status = data.get("status")

        # Le next_page_token Google n'est pas valide immédiatement (2-5s de propagation).
        # Sur INVALID_REQUEST avec un token en cours, on patiente et on rejoue le MÊME
        # token (jusqu'à 3 fois) SANS spammer les logs — c'est un comportement normal.
        if status == "INVALID_REQUEST" and "pagetoken" in params and token_retries < 3:
            token_retries += 1
            time.sleep(2)
            continue

        if status not in ("OK", "ZERO_RESULTS"):
            if results:
                # Cas normal : Google ne sert que 20 résultats/page pour ce mot-clé.
                logger.debug(
                    "    ℹ️  Google limite à %d résultat(s) pour '%s' (page suivante indisponible) — c'est normal.",
                    len(results), keyword,
                )
            else:
                logger.warning("Statut API inattendu (%s) pour '%s'", status, keyword)
            break

        token_retries = 0
        results.extend(data.get("results", []))

        next_token = data.get("next_page_token")
        if not next_token or len(results) >= max_raw:
            break

        # Google impose un délai avant d'utiliser le next_page_token (2s minimum, 3s plus fiable)
        time.sleep(3)
        params = {"pagetoken": next_token, "key": config.google_api_key}

    # 📘 Slicing : results[:max_raw] = les max_raw premiers éléments de la liste.
    return results[:max_raw]


# 📘 Étape 2 : 1 appel Place Details PAR lieu pour obtenir téléphone, site, note, lien Maps.
# 📘 `fields=` limite les champs demandés : Google facture Place Details selon les champs demandés.
def build_prospect(raw: dict, keyword: str) -> Optional[Prospect]:
    """
    Appelle Place Details pour un résultat brut Text Search et construit un Prospect.
    Retourne None si l'appel échoue.
    """
    place_id = raw.get("place_id", "")
    if not place_id:
        return None

    url = f"{BASE_URL}/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,website,rating,user_ratings_total,url",
        "key": config.google_api_key,
        "language": "fr",
    }
    details: dict = {}
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=config.request_timeout)
            resp.raise_for_status()
            details = resp.json().get("result", {})
            break
        except requests.RequestException as exc:
            if attempt < 2:
                delay = 2 ** (attempt + 1)
                logger.debug("    ↩️  Place Details retry %d/3 dans %ds… (%s)", attempt + 1, delay, place_id)
                time.sleep(delay)
            else:
                logger.error("Erreur Place Details (%s) : %s", place_id, exc)
                return None

    if not details:
        return None

    # 📘 details.get("name", raw.get("name", "Inconnu")) : valeur de Details, sinon celle de Text
    # 📘 Search, sinon "Inconnu". .get(clé, défaut) ne plante jamais si la clé manque.
    return Prospect(
        place_id=place_id,
        name=details.get("name", raw.get("name", "Inconnu")),
        address=details.get("formatted_address", raw.get("formatted_address", "")),
        phone=_normalize_phone(details.get("formatted_phone_number")),
        website=details.get("website"),
        rating=details.get("rating"),
        user_ratings_total=details.get("user_ratings_total", 0),
        keyword=keyword,
        maps_url=details.get("url", ""),
    )


# 📘 Utilisée seulement par main.py (CLI). pipeline.py appelle directement fetch_raw_candidates
# 📘 et build_prospect pour gérer lui-même filtres, dédoublonnage et parallélisme.
def search_prospects(keyword: str) -> List[Prospect]:
    """
    Compatibilité main.py — recherche N prospects confirmés pour un mot-clé.
    Utilise fetch_raw_candidates + build_prospect en interne.
    """
    target = config.max_results_per_keyword
    logger.info("🔍 Recherche : '%s' autour de %s", keyword, config.search_location)

    raw_results = fetch_raw_candidates(keyword, max_raw=GOOGLE_MAX_RESULTS)
    if not raw_results:
        logger.warning("Aucun résultat pour '%s'.", keyword)
        return []

    prospects: List[Prospect] = []
    # 📘 Boucle séquentielle : un appel Place Details à la fois, jusqu'à `target` fiches valides.
    # 💡 Pour tester sans payer d'appels Google, on pourrait injecter une "session" requests en
    # 💡   paramètre (ou utiliser la librairie `responses`) et simuler les réponses de l'API.
    for raw in raw_results:
        if len(prospects) >= target:
            break
        prospect = build_prospect(raw, keyword)
        if not prospect:
            continue
        prospects.append(prospect)
        logger.debug("  ✅ %s | site=%s | tél=%s",
                     prospect.name, prospect.website or "AUCUN", prospect.phone or "AUCUN")

    logger.info("  → %d/%d prospect(s) confirmé(s) pour '%s'.", len(prospects), target, keyword)
    return prospects
