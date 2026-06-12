"""
services/sources/google_search.py — Recherche de prospects via Google Custom Search JSON API.

Endpoint : https://www.googleapis.com/customsearch/v1?key={key}&cx={cx}&q={query}&num=10&start={start}&gl=fr&hl=fr
"""

from __future__ import annotations

import hashlib
import time
from typing import List, Optional

import requests

from config import config, logger
from services.google_maps import Prospect


SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
MAX_START = 91  # Google CSE max start index


def _fetch_batch(
    query: str, start: int, cx: str
) -> Optional[List[dict]]:
    """
    Récupère un batch de 10 résultats depuis l'API Google Custom Search.
    Retry 3x avec backoff (2s, 4s) et gestion du 429.
    """
    params = {
        "key": config.google_api_key,
        "cx": cx,
        "q": query,
        "num": 10,
        "start": start,
        "gl": "fr",
        "hl": "fr",
    }

    for attempt in range(3):
        try:
            resp = requests.get(SEARCH_URL, params=params, timeout=config.request_timeout)
            if resp.status_code == 429:
                delay = 2 ** (attempt + 1)
                logger.debug(
                    "    ↩️  Google Search 429 (rate limit), attente %ds…", delay
                )
                time.sleep(delay)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", [])
        except requests.RequestException as exc:
            if attempt < 2:
                delay = 2 ** (attempt + 1)
                logger.debug(
                    "    ↩️  Google Search retry %d/3 dans %ds…", attempt + 1, delay
                )
                time.sleep(delay)
            else:
                logger.error("Erreur Google Custom Search (start=%d) : %s", start, exc)
    return None


def search_google_custom(
    keyword: str,
    location: str,
    max_results: int = 10,
    cx: str = "",
) -> List[Prospect]:
    """
    Recherche des prospects via Google Custom Search JSON API.

    Args:
        keyword:     Mot-clé métier (ex: "boulangerie").
        location:    Ville (ex: "Lyon").
        max_results: Nombre maximum de prospects à retourner.
        cx:          Identifiant du moteur de recherche personnalisé Google (CX).

    Returns:
        Liste d'objets Prospect.
    """
    logger.info("🔎 Google Search : '%s %s'", keyword, location)

    if not config.google_api_key or not cx:
        logger.warning(
            "Google Search : google_api_key ou cx manquant — source ignorée."
        )
        return []

    query = f"{keyword} {location}"
    prospects: List[Prospect] = []

    start = 1
    while len(prospects) < max_results and start <= MAX_START:
        items = _fetch_batch(query, start, cx)

        if items is None:
            break

        for item in items:
            if len(prospects) >= max_results:
                break

            url = item.get("link", "")
            if not url:
                continue

            title = item.get("title", "")
            # Extrait le nom depuis le titre (avant " - " ou " | ")
            name = title.split(" - ")[0].split(" | ")[0].strip() or url

            place_id = "gs_" + hashlib.md5(url.encode()).hexdigest()[:16]

            prospect = Prospect(
                place_id=place_id,
                name=name,
                address=location,
                phone=None,
                website=url,
                rating=None,
                user_ratings_total=0,
                keyword=keyword,
                maps_url="",
            )
            prospects.append(prospect)

        start += 10
        # Rate limiting entre les batches
        if start <= MAX_START and len(prospects) < max_results:
            time.sleep(0.3)

    logger.info("  → %d résultat(s) Google Search", len(prospects))
    return prospects
