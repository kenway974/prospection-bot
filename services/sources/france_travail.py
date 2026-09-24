"""
services/sources/france_travail.py — Recherche de prospects via l'API France Travail (ex Pôle Emploi).

Authentification OAuth2 client_credentials.
Endpoint : https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search
"""

from __future__ import annotations

# 📘 Tuple, Dict… : types du module typing, pour annoter (type hints). Tuple n'est pas utilisé ici.
import time
from typing import Dict, List, Optional, Tuple

import requests

# 📘 ⚠️ `config` est figé à l'import (démarrage de l'appli) : pipeline.py ne le remplace pas ici.
# 📘   Sans conséquence pour la config : seul config.request_timeout (fixe, 10 s) est lu, et les
# 📘   identifiants arrivent en ARGUMENTS (client_id/client_secret passés par pipeline.py : bonne
# 📘   pratique). `logger` non remplacé → ces logs vont dans la console, pas dans l'UI.
from config import config, logger
from services.google_maps import Prospect


# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : trouver des entreprises QUI RECRUTENT via l'API officielle des offres d'emploi France
# 📘   Travail ; une entreprise qui embauche a souvent un budget → bon signal commercial.
# 📘 Appelé par : pipeline.py (search_france_travail, source "france_travail"), via __init__.py.
# 📘 Appelle : entreprise.francetravail.fr (jeton OAuth2) puis api.francetravail.io (recherche).
# 📘 Concepts Python à retenir ici : OAuth2 "client_credentials", cache global dans un dict,
# 📘   requests.post(data=...), en-tête Authorization Bearer, dédoublonnage avec un dict.
# 📘 OAuth2 client_credentials : on échange (client_id, client_secret) contre un "jeton d'accès"
# 📘 temporaire, qu'on joint ensuite à chaque requête. Le secret, lui, ne voyage qu'une fois.
# ---------------------------------------------------------------------------
# Cache du token OAuth2 (dict module-level)
# ---------------------------------------------------------------------------

# 📘 Cache au niveau du MODULE : ce dict vit tant que le processus tourne, donc le jeton est
# 📘 réutilisé d'une recherche (et d'une campagne) à l'autre jusqu'à son expiration.
# 📘 ⚠️ La clé du cache ne contient pas le client_id : si tu changes d'identifiants dans l'UI, le
# 📘   jeton des ANCIENS identifiants reste utilisé jusqu'à expiration (≈ 1 h en pratique).
# 💡 Indexer le cache par client_id (dict {client_id: (jeton, expiration)}) règle ce problème.
_token_cache: Dict[str, object] = {
    "access_token": None,
    "expires_at": 0.0,
}

# 📘 Deux chaînes côte à côte entre parenthèses sont collées en une seule par Python.
# 📘 "%2F" = "/" encodé pour une URL : realm=/partenaire.
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
    # 📘 time.time() = nombre de secondes depuis 1970 ("timestamp"), pratique pour comparer des dates.
    now = time.time()
    if _token_cache["access_token"] and now < float(_token_cache["expires_at"]):  # type: ignore[arg-type]
        return str(_token_cache["access_token"])

    # 📘 requests.post(..., data=payload) envoie le dict comme un formulaire HTML (clé=valeur&...),
    # 📘 ce que demande le serveur OAuth2 (Content-Type x-www-form-urlencoded).
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
            # 📘 On retire 30 s de marge pour ne jamais envoyer un jeton qui expire pendant la requête.
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
    # 📘 "range": "0-39" : pagination façon France Travail, on demande les offres n°0 à 39 d'un coup
    # 📘 (2× max_results car plusieurs offres viennent souvent de la même entreprise), 149 max ici.
    range_end = min(max_results * 2 - 1, 149)
    params = {
        "motsCles": keyword,
        "range": f"0-{range_end}",
        # 📘 ⚠️ "distance": 30 est envoyé sans commune de référence et `location` n'est jamais transmis :
        # 📘   la recherche porte sur TOUTE la France, pas sur ta ville (la docstring le reconnaît).
        # 💡 L'API offres v2 accepte des filtres géographiques (departement, ou commune + distance) :
        # 💡   réutiliser _get_dept de sirene.py pour en déduire le département de `location`.
        "distance": 30,
    }
    # 📘 En-tête "Authorization: Bearer <jeton>" : c'est ainsi qu'on présente le jeton OAuth2.
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
            # 📘 data.get("resultats", []) : la liste d'offres, ou liste vide si la clé est absente.
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

    # 📘 Sortie anticipée ("early return") : on vérifie les prérequis en haut et on quitte tout de
    # 📘 suite, ce qui évite d'imbriquer tout le reste dans des if.
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
    # 📘 Dict utilisé comme "déjà vu ?" ; un set() (seen = set(); seen.add(k)) ferait pareil, plus
    # 📘 simplement. Dédoublonnage par nom en minuscules : 1 prospect par entreprise.
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

        # 📘 Le contact d'une offre (tél., courriel) est souvent celui du recruteur, pas du dirigeant.
        address = lieu_travail.get("libelle", "")
        website = entreprise.get("url") or None
        phone = contact.get("telephone") or None
        email_val = contact.get("courriel") or None

        prospect = Prospect(
            # 📘 place_id = "ft_" + id de l'OFFRE : si la même entreprise revient avec une autre offre
            # 📘 plus tard, elle aura un autre place_id → _dedup de pipeline.py (qui compare les place_id)
            # 📘 ne la reconnaîtra pas comme déjà contactée.
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
