"""
services/sources/france_travail.py — Recherche de prospects via l'API France Travail (ex Pôle Emploi).

Authentification OAuth2 client_credentials.
Endpoint : https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import requests

from config import config, logger
from services.google_maps import Prospect


# ---------------------------------------------------------------------------
# Cache du token OAuth2 (dict module-level)
# ---------------------------------------------------------------------------

_token_cache: Dict[str, object] = {
    "access_token": None,
    "expires_at": 0.0,
}

TOKEN_URL = (
    "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
    "?realm=%2Fpartenaire"
)
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"


def _get_token(client_id: str, client_secret: str) -> Optional[str]:
    """
    Récupère un token OAuth2, en utilisant le cache si encore valide.
    Retry 3x avec backoff exponentiel.
    """
    now = time.time()
    if _token_cache["access_token"] and now < float(_token_cache["expires_at"]):  # type: ignore[arg-type]
        return str(_token_cache["access_token"])

    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "api_offresdemploiv2 o2dsoffre",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    for attempt in range(3):
        try:
            resp = requests.post(TOKEN_URL, data=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token")
            expires_in = int(data.get("expires_in", 3600))
            _token_cache["access_token"] = token
            _token_cache["expires_at"] = now + expires_in - 30  # marge de 30s
            return token
        except requests.RequestException as exc:
            if attempt < 2:
                delay = 2 ** (attempt + 1)
                logger.debug(
                    "    ↩️  France Travail token retry %d/3 dans %ds…", attempt + 1, delay
                )
                time.sleep(delay)
            else:
                logger.error("Impossible d'obtenir le token France Travail : %s", exc)
    return None


def _search_offers(
    token: str, keyword: str, max_results: int
) -> Optional[List[dict]]:
    """
    Recherche des offres d'emploi via l'API France Travail.
    Retry 3x avec backoff exponentiel.
    """
    range_end = min(max_results * 2 - 1, 149)
    params = {
        "motsCles": keyword,
        "range": f"0-{range_end}",
        "distance": 30,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    for attempt in range(3):
        try:
            resp = requests.get(
                SEARCH_URL, params=params, headers=headers, timeout=config.request_timeout
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("resultats", [])
        except requests.RequestException as exc:
            if attempt < 2:
                delay = 2 ** (attempt + 1)
                logger.debug(
                    "    ↩️  France Travail search retry %d/3 dans %ds…",
                    attempt + 1,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error("Erreur recherche France Travail : %s", exc)
    return None


def search_france_travail(
    keyword: str,
    location: str,
    max_results: int = 20,
    client_id: str = "",
    client_secret: str = "",
) -> List[Prospect]:
    """
    Recherche des entreprises qui recrutent via l'API France Travail.
    Déduplique par nom d'entreprise.

    Args:
        keyword:       Mots-clés métier.
        location:      Ville (non utilisée dans la requête API, conservation pour cohérence).
        max_results:   Nombre maximum de prospects uniques à retourner.
        client_id:     Identifiant client OAuth2 France Travail.
        client_secret: Secret client OAuth2 France Travail.

    Returns:
        Liste d'objets Prospect (une entrée par entreprise unique).
    """
    logger.info("💼 France Travail : '%s' à %s", keyword, location)

    if not client_id or not client_secret:
        logger.warning(
            "France Travail : client_id ou client_secret manquant — source ignorée."
        )
        return []

    token = _get_token(client_id, client_secret)
    if not token:
        return []

    offers = _search_offers(token, keyword, max_results)
    if offers is None:
        return []

    prospects: List[Prospect] = []
    seen_companies: Dict[str, bool] = {}

    for offer in offers:
        if len(prospects) >= max_results:
            break

        entreprise = offer.get("entreprise") or {}
        company_name = entreprise.get("nom", "").strip()
        if not company_name:
            continue

        # Déduplication par nom d'entreprise (insensible à la casse)
        company_key = company_name.lower()
        if company_key in seen_companies:
            continue
        seen_companies[company_key] = True

        offer_id = offer.get("id", "")
        lieu_travail = offer.get("lieuTravail") or {}
        contact = offer.get("contact") or {}

        address = lieu_travail.get("libelle", "")
        website = entreprise.get("url") or None
        phone = contact.get("telephone") or None
        email_val = contact.get("courriel") or None

        prospect = Prospect(
            place_id=f"ft_{offer_id}",
            name=company_name,
            address=address,
            phone=phone,
            website=website,
            rating=None,
            user_ratings_total=0,
            keyword=keyword,
            maps_url=f"https://candidat.francetravail.fr/offres/recherche/detail/{offer_id}",
        )
        if email_val:
            prospect.email = email_val

        prospects.append(prospect)

    logger.info("  → %d entreprise(s) France Travail", len(prospects))
    return prospects
