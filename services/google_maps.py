"""
services/google_maps.py — Recherche de prospects via l'API Google Places.

Flux :
  1. Text Search  → liste brute de lieux correspondant au mot-clé + ville
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
    score: int = 0              # Score de 0 à 100 (plus bas = plus d'opportunités)
    email: Optional[str] = None # Email scrapé sur le site du prospect
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
            "email_draft": self.email_draft,
        }


# ---------------------------------------------------------------------------
# Appels API Google Places
# ---------------------------------------------------------------------------

BASE_URL = "https://maps.googleapis.com/maps/api"


def _text_search(keyword: str, location: str, radius: int, limit: int) -> List[dict]:
    """
    Lance une Text Search Google Places.
    Gère la pagination automatiquement (next_page_token).
    Retourne jusqu'à `limit` résultats bruts.
    """
    url = f"{BASE_URL}/place/textsearch/json"
    params = {
        "query": f"{keyword} {location}",
        "radius": radius,
        "key": config.google_api_key,
        "language": "fr",
    }
    results: List[dict] = []

    while True:
        try:
            resp = requests.get(url, params=params, timeout=config.request_timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.error("Erreur Text Search pour '%s' : %s", keyword, exc)
            break

        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            logger.warning("Statut API inattendu (%s) pour '%s'", status, keyword)
            break

        results.extend(data.get("results", []))

        next_token = data.get("next_page_token")
        if not next_token or len(results) >= limit:
            break

        # Google impose un délai de ~2s avant d'utiliser le next_page_token
        time.sleep(2)
        params = {"pagetoken": next_token, "key": config.google_api_key}

    return results[:limit]


def _get_place_details(place_id: str) -> dict:
    """
    Récupère les détails complets d'un lieu via son place_id.
    Retourne un dict vide en cas d'erreur (le prospect sera ignoré).
    """
    url = f"{BASE_URL}/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,website,rating,user_ratings_total,url",
        "key": config.google_api_key,
        "language": "fr",
    }
    try:
        resp = requests.get(url, params=params, timeout=config.request_timeout)
        resp.raise_for_status()
        return resp.json().get("result", {})
    except requests.RequestException as exc:
        logger.error("Erreur Place Details (%s) : %s", place_id, exc)
        return {}


# ---------------------------------------------------------------------------
# Fonction principale exportée
# ---------------------------------------------------------------------------

def search_prospects(keyword: str) -> List[Prospect]:
    """
    Recherche des prospects locaux pour un mot-clé donné.
    Garantit jusqu'à max_results_per_keyword prospects CONFIRMÉS en fetchant
    un buffer 5× pour absorber les échecs Place Details silencieux.
    """
    target = config.max_results_per_keyword
    # Buffer 5× pour compenser les appels Place Details qui échouent
    raw_limit = target * 5

    logger.info("🔍 Recherche : '%s' autour de %s", keyword, config.search_location)
    raw_results = _text_search(keyword, config.search_location, config.search_radius, limit=raw_limit)

    if not raw_results:
        logger.warning("Aucun résultat pour '%s'.", keyword)
        return []

    prospects: List[Prospect] = []
    for raw in raw_results:
        if len(prospects) >= target:
            break

        place_id = raw.get("place_id", "")
        if not place_id:
            continue

        details = _get_place_details(place_id)
        if not details:
            continue

        prospect = Prospect(
            place_id=place_id,
            name=details.get("name", raw.get("name", "Inconnu")),
            address=details.get("formatted_address", raw.get("formatted_address", "")),
            phone=details.get("formatted_phone_number"),
            website=details.get("website"),
            rating=details.get("rating"),
            user_ratings_total=details.get("user_ratings_total", 0),
            keyword=keyword,
            maps_url=details.get("url", ""),
        )
        prospects.append(prospect)
        logger.debug(
            "  ✅ %s | site=%s | tél=%s",
            prospect.name,
            prospect.website or "AUCUN",
            prospect.phone or "AUCUN",
        )

    logger.info("  → %d/%d prospect(s) confirmé(s) pour '%s'.", len(prospects), target, keyword)
    return prospects
