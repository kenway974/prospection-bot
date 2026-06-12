"""
services/sources/sirene.py — Recherche de prospects via l'API Recherche Entreprises data.gouv.fr.

API gratuite, sans authentification :
  https://recherche-entreprises.api.gouv.fr/search?q={keyword}&departement={dept}&page=1&per_page=25
"""

from __future__ import annotations

import time
from typing import List, Optional

import requests

from config import config, logger
from services.google_maps import Prospect


# ---------------------------------------------------------------------------
# Mapping ville → code département (30 plus grandes villes françaises)
# ---------------------------------------------------------------------------

CITY_TO_DEPT: dict = {
    "paris": "75",
    "lyon": "69",
    "marseille": "13",
    "toulouse": "31",
    "bordeaux": "33",
    "nantes": "44",
    "lille": "59",
    "strasbourg": "67",
    "montpellier": "34",
    "nice": "06",
    "rennes": "35",
    "grenoble": "38",
    "dijon": "21",
    "reims": "51",
    "saint-etienne": "42",
    "toulon": "83",
    "angers": "49",
    "brest": "29",
    "le mans": "72",
    "amiens": "80",
    "aix-en-provence": "13",
    "clermont-ferrand": "63",
    "nîmes": "30",
    "nimes": "30",
    "metz": "57",
    "caen": "14",
    "nancy": "54",
    "orleans": "45",
    "orléans": "45",
    "mulhouse": "68",
    "rouen": "76",
    "besancon": "25",
    "besançon": "25",
}

BASE_URL = "https://recherche-entreprises.api.gouv.fr/search"


def _get_dept(location: str) -> Optional[str]:
    """Retourne le code département pour une ville, ou None si inconnu."""
    normalized = location.lower().strip()
    # Essai exact
    if normalized in CITY_TO_DEPT:
        return CITY_TO_DEPT[normalized]
    # Essai sur le premier mot (ex: "Lyon, France" → "lyon")
    first_word = normalized.split(",")[0].strip()
    if first_word in CITY_TO_DEPT:
        return CITY_TO_DEPT[first_word]
    # Essai partiel
    for city, dept in CITY_TO_DEPT.items():
        if city in normalized:
            return dept
    return None


def _build_address(siege: dict) -> str:
    """Construit l'adresse complète depuis le siège social."""
    parts = [
        siege.get("numero_voie", ""),
        siege.get("type_voie", ""),
        siege.get("libelle_voie", ""),
        siege.get("code_postal", ""),
        siege.get("libelle_commune", ""),
    ]
    return " ".join(p for p in parts if p).strip()


def _fetch_page(params: dict, attempt_max: int = 3) -> Optional[dict]:
    """Effectue une requête avec retry exponentiel (2s, 4s)."""
    for attempt in range(attempt_max):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=config.request_timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            if attempt < attempt_max - 1:
                delay = 2 ** (attempt + 1)
                logger.debug(
                    "    ↩️  Sirene retry %d/%d dans %ds…", attempt + 1, attempt_max, delay
                )
                time.sleep(delay)
            else:
                logger.error("Erreur Sirene API : %s", exc)
    return None


def search_sirene(keyword: str, location: str, max_results: int = 20) -> List[Prospect]:
    """
    Recherche des entreprises via l'API Recherche Entreprises (data.gouv.fr).

    Args:
        keyword:     Mot-clé métier (ex: "boulangerie").
        location:    Ville ou région (ex: "Lyon").
        max_results: Nombre maximum de prospects à retourner.

    Returns:
        Liste d'objets Prospect.
    """
    logger.info("🏛️  Sirene : '%s' à %s", keyword, location)

    dept = _get_dept(location)
    per_page = 25

    if dept:
        base_params: dict = {
            "q": keyword,
            "departement": dept,
            "per_page": per_page,
        }
    else:
        base_params = {
            "q": f"{keyword} {location}",
            "per_page": per_page,
        }

    prospects: List[Prospect] = []
    page = 1

    while len(prospects) < max_results:
        params = {**base_params, "page": page}
        data = _fetch_page(params)

        if data is None:
            break

        results = data.get("results", [])
        total_pages = data.get("total_pages", 1)

        for entry in results:
            if len(prospects) >= max_results:
                break

            siren = entry.get("siren", "")
            name = entry.get("nom_raison_sociale") or entry.get("nom_complet") or "Inconnu"
            siege = entry.get("siege") or {}
            address = _build_address(siege)

            prospect = Prospect(
                place_id=f"sirene_{siren}",
                name=name,
                address=address,
                phone=None,
                website=None,
                rating=None,
                user_ratings_total=0,
                keyword=keyword,
                maps_url=f"https://annuaire-entreprises.data.gouv.fr/entreprise/{siren}",
            )
            prospects.append(prospect)

        if page >= total_pages:
            break

        page += 1
        time.sleep(0.5)  # Rate limiting entre les pages

    logger.info("  → %d entreprise(s) Sirene", len(prospects))
    return prospects
