"""
services/google_maps.py — Recherche de prospects via l'API Google Places.

Flux :
  1. Text Search  → liste brute de lieux (jusqu'à 60 résultats, 3 pages Google)
  2. Place Details → détails complets de chaque lieu (tel, site, note…)
  3. Retourne une liste d'objets Prospect typés

Doc API : https://developers.google.com/maps/documentation/places/web-service
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

import requests

from config import config, logger


# ---------------------------------------------------------------------------
# Modèle Prospect — partagé par tous les modules
# ---------------------------------------------------------------------------

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
    issues: List[str] = field(default_factory=list)  # Problèmes détectés sur le site
    issue_keys: List[str] = field(default_factory=list)  # Clés normalisées des problèmes (pour personnalisation email)
    score: int = 0              # Score de 0 à 100 (plus bas = plus d'opportunités)
    email: Optional[str] = None # Email scrapé sur le site du prospect
    cms: Optional[str] = None   # CMS/builder détecté (ex: "WordPress", "Wix")
    # Rempli par mailer.py
    email_draft: str = ""       # Brouillon de cold email prêt à envoyer

    def has_website(self) -> bool:
        """Retourne True si le prospect a un site web valide."""
        return bool(self.website and self.website.startswith("http"))

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
            "score": self.score,
            "email": self.email,
            "cms": self.cms,
            "email_draft": self.email_draft,
        }


# ---------------------------------------------------------------------------
# Appels API Google Places
# ---------------------------------------------------------------------------

BASE_URL = "https://maps.googleapis.com/maps/api"


def _normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Normalise un numéro au format national français (0X XX XX XX XX).
    Fallback silencieux sur la valeur brute si phonenumbers est indisponible ou invalide."""
    if not raw:
        return None
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


def fetch_raw_candidates(keyword: str, max_raw: int = GOOGLE_MAX_RESULTS) -> List[dict]:
    """
    Récupère jusqu'à `max_raw` résultats bruts via Google Places Text Search.
    Gère la pagination automatiquement (next_page_token).
    Retry exponentiel (2s, 4s, 8s) sur la première page uniquement.
    """
    url = f"{BASE_URL}/place/textsearch/json"
    params = {
        "query": f"{keyword} {config.search_location}",
        "radius": config.search_radius,
        "key": config.google_api_key,
        "language": "fr",
    }
    results: List[dict] = []
    is_first_page = True

    while True:
        max_attempts = 3 if is_first_page else 1
        data = None
        for attempt in range(max_attempts):
            try:
                resp = requests.get(url, params=params, timeout=config.request_timeout)
                resp.raise_for_status()
                data = resp.json()
                break
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

        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            # INVALID_REQUEST sur next_page_token = token expiré, non critique si on a déjà des résultats
            if results:
                logger.debug("Pagination interrompue (%s) pour '%s' — %d résultats conservés.", status, keyword, len(results))
            else:
                logger.warning("Statut API inattendu (%s) pour '%s'", status, keyword)
            break

        results.extend(data.get("results", []))

        next_token = data.get("next_page_token")
        if not next_token or len(results) >= max_raw:
            break

        # Google impose un délai avant d'utiliser le next_page_token (2s minimum, 3s plus fiable)
        time.sleep(3)
        params = {"pagetoken": next_token, "key": config.google_api_key}

    return results[:max_raw]


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
