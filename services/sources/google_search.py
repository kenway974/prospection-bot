"""
services/sources/google_search.py — Recherche de prospects via Google Custom Search JSON API.

Endpoint : https://www.googleapis.com/customsearch/v1?key={key}&cx={cx}&q={query}&num=10&start={start}&gl=fr&hl=fr
"""

from __future__ import annotations

import hashlib
import time
from typing import List, Optional

import requests

# 📘 ⚠️ BUG CONFIRMÉ (config périmée) : `config` est l'objet Config créé au 1er import de ce
# 📘   module, c.-à-d. au démarrage de l'appli (app.py importe services.sources tout en haut).
# 📘   pipeline.py recrée un Config avec la clé Google saisie dans l'UI mais ne le réinjecte PAS
# 📘   ici (seulement dans google_maps, analyzer, notion_sync). Donc config.google_api_key (lignes
# 📘   `"key": ...` et `if not config.google_api_key`) = la clé présente dans l'environnement au
# 📘   démarrage : si elle n'y était pas (clé saisie seulement dans l'UI / settings.json), la
# 📘   source est toujours "ignorée" ; si tu changes de clé dans l'UI, l'ancienne reste utilisée.
# 📘   Et comme `logger` n'est pas remplacé non plus, l'avertissement ne s'affiche que dans la
# 📘   console, pas dans le journal de l'UI.
# 💡 Correctif simple : passer la clé en argument, comme cx (search_google_custom(...,
# 💡   api_key=params["google_key"])) ; pipeline.py la connaît déjà.
from config import config, logger
from services.google_maps import Prospect


# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : trouver des sites d'entreprises via l'API Google Custom Search (moteur de recherche
# 📘   Google programmable) pour "mot-clé ville", et en faire des Prospect (site = lien trouvé).
# 📘 Appelé par : pipeline.py (search_google_custom, source "google_search"), via __init__.py.
# 📘 Appelle : www.googleapis.com/customsearch/v1 (HTTP GET, clé API + identifiant cx).
# 📘 Concepts Python à retenir ici : pagination par index (start), gestion du code HTTP 429,
# 📘   `continue`, split en chaîne, hashlib.md5, boucle while à double condition.
# 📘 "cx" = identifiant de TON moteur Custom Search (créé sur programmablesearchengine.google.com).
SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
# 📘 L'API ne sert que les 100 premiers résultats : start va de 1 à 91 par pas de 10.
MAX_START = 91  # Google CSE max start index


def _fetch_batch(
    query: str, start: int, cx: str
) -> Optional[List[dict]]:
    """
    Récupère un batch de 10 résultats depuis l'API Google Custom Search.
    Retry 3x avec backoff (2s, 4s) et gestion du 429.
    """
    # 📘 num=10 résultats par appel (le maximum) ; gl=fr/hl=fr : résultats et langue orientés France.
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
            # 📘 HTTP 429 "Too Many Requests" : quota/débit dépassé. On attend, puis `continue` passe
            # 📘 directement au tour de boucle suivant (nouvel essai), sans lever d'erreur.
            # 📘 Si les 3 essais tombent sur 429, on sort de la boucle et la fonction renvoie None.
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
    # 📘 On s'arrête quand on a assez de prospects OU qu'on a atteint la limite des 100 résultats.
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
            # 📘 On garde ce qui précède " - " puis " | " : "Boulangerie Dupont - Lyon" → "Boulangerie
            # 📘 Dupont" ; "Chez Paul | Accueil" → "Chez Paul". `or url` : repli si le titre est vide.
            name = title.split(" - ")[0].split(" | ")[0].strip() or url

            # 📘 Identifiant stable dérivé de l'URL : la même page trouvée deux fois donnera le même id.
            place_id = "gs_" + hashlib.md5(url.encode()).hexdigest()[:16]

            prospect = Prospect(
                place_id=place_id,
                name=name,
                # 📘 Pas d'adresse dans les résultats de recherche : on met la ville recherchée.
                # 📘 Les résultats peuvent être des annuaires ou des articles, pas que des sites de boîtes.
                # 💡 Filtrer les domaines d'annuaires (pagesjaunes.fr, tripadvisor, facebook…) éviterait
                # 💡   d'analyser et de prospecter un annuaire comme s'il s'agissait d'une entreprise.
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
