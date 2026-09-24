"""
services/sources/sirene.py — Recherche de prospects via l'API Recherche Entreprises data.gouv.fr.

API gratuite, sans authentification :
  https://recherche-entreprises.api.gouv.fr/search?q={keyword}&departement={dept}&page=1&per_page=25
"""

from __future__ import annotations

import time
from typing import List, Optional

import requests

# 📘 ⚠️ Import de `config` au chargement : l'objet est figé au démarrage de l'appli (pipeline.py ne
# 📘   le remplace pas ici). Sans conséquence dans ce fichier : seul config.request_timeout est lu,
# 📘   et c'est une valeur fixe (10 s) qui ne dépend pas de la campagne. En revanche `logger`
# 📘   n'est pas le QueueLogger de pipeline : les logs Sirene vont dans la console, pas dans l'UI.
from config import config, logger
from services.google_maps import Prospect


# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : trouver des entreprises dans le registre officiel (API Recherche Entreprises,
# 📘   data.gouv.fr, gratuite et sans clé) et les convertir en Prospect, avec SIREN et dirigeant.
# 📘 Appelé par : pipeline.py (search_sirene, quand la source "sirene" est cochée), via
# 📘   services/sources/__init__.py.
# 📘 Appelle : recherche-entreprises.api.gouv.fr (HTTP GET), services/dirigeants.extract_dirigeant.
# 📘 Concepts Python à retenir ici : dict de correspondance, str.lower/strip/split, pagination
# 📘   par numéro de page, retry, `{**dict, "clé": v}`, import local dans une boucle.
# 📘 Pas de téléphone ni de site web dans ce registre : ces prospects ont website=None.
# ---------------------------------------------------------------------------
# Mapping ville → code département (30 plus grandes villes françaises)
# ---------------------------------------------------------------------------

# 📘 `CITY_TO_DEPT: dict = {...}` : variable annotée (type hint) ; dict ville → n° de département.
# 📘 Sert à filtrer l'API par département ("departement": "69") plutôt qu'en texte libre.
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
    # DOM-TOM
    "la réunion": "974",
    "la reunion": "974",
    "réunion": "974",
    "reunion": "974",
    # 📘 ⚠️ "saint-denis" est mappé sur 974 (La Réunion), mais Saint-Denis (93) existe aussi ; pareil
    # 📘   pour "saint-paul"/"saint-pierre" (plusieurs communes en métropole). Idem via l'essai partiel
    # 📘   plus bas : "Saint-Paul-lès-Dax" contient "saint-paul" → 974.
    "saint-denis": "974",   # saint-denis de la réunion (le plus commun)
    "saint-paul": "974",
    "saint-pierre": "974",
    "le tampon": "974",
    "saint-andré": "974",
    "saint-andre": "974",
    "guadeloupe": "971",
    "martinique": "972",
    "guyane": "973",
    "mayotte": "976",
}

BASE_URL = "https://recherche-entreprises.api.gouv.fr/search"


# 📘 Trois essais du plus strict au plus souple : clé exacte, puis partie avant la virgule
# 📘 ("Lyon, France" → "lyon"), puis "la ville connue est-elle contenue dans le texte ?".
# 💡 Liste limitée à ~30 villes. L'API Géo officielle (geo.api.gouv.fr/communes?nom=...) donne
# 💡   le département de n'importe quelle commune ; ou utiliser le code postal si l'UI le fournit.
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
    # 📘 On assemble les morceaux d'adresse en ignorant les vides : `" ".join(p for p in parts if p)`
    # 📘 (générateur : comme une list comprehension, mais sans crochets ni liste intermédiaire).
    parts = [
        siege.get("numero_voie", ""),
        siege.get("type_voie", ""),
        siege.get("libelle_voie", ""),
        siege.get("code_postal", ""),
        siege.get("libelle_commune", ""),
    ]
    return " ".join(p for p in parts if p).strip()


# 📘 Retry avec backoff exponentiel (attendre 2 s puis 4 s) ; renvoie None si tout a échoué.
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


# 📘 Signature sur plusieurs lignes : paramètres avec types et valeurs par défaut. naf_code est
# 📘 prévu mais pipeline.py ne le passe pas (il vaut donc toujours "").
def search_sirene(
    keyword: str,
    location: str,
    max_results: int = 20,
    naf_code: str = "",
) -> List[Prospect]:
    """
    Recherche des entreprises via l'API Recherche Entreprises (data.gouv.fr).

    Args:
        keyword:     Mot-clé métier (ex: "boulangerie").
        location:    Ville ou région (ex: "Lyon").
        max_results: Nombre maximum de prospects à retourner.
        naf_code:    Code APE/NAF pour filtrer par activité (ex: "47.11Z"). Optionnel.

    Returns:
        Liste d'objets Prospect.
    """
    # 📘 `f" [NAF {naf_code}]" if naf_code else ""` : expression conditionnelle (ternaire) :
    # 📘 valeur_si_vrai if condition else valeur_si_faux.
    logger.info("🏛️  Sirene : '%s' à %s%s", keyword, location, f" [NAF {naf_code}]" if naf_code else "")

    dept = _get_dept(location)
    per_page = 25

    # 📘 Département connu → filtre précis ; sinon on colle la ville au mot-clé dans la recherche.
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

    if naf_code:
        base_params["activite_principale"] = naf_code

    prospects: List[Prospect] = []
    page = 1

    # 📘 Pagination par numéro de page : on demande page 1, 2, 3… jusqu'à avoir max_results fiches
    # 📘 ou atteindre total_pages (renvoyé par l'API).
    while len(prospects) < max_results:
        # 📘 {**base_params, "page": page} : copie du dict + la clé "page" (l'original reste intact).
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
            # 📘 `a or b or "Inconnu"` : prend la première valeur "vraie" (non vide, non None).
            name = entry.get("nom_raison_sociale") or entry.get("nom_complet") or "Inconnu"
            siege = entry.get("siege") or {}
            address = _build_address(siege)

            prospect = Prospect(
                # 📘 place_id préfixé "sirene_" : identifiant unique inventé pour cette source, pour que
                # 📘 le dédoublonnage et l'historique fonctionnent comme avec les place_id Google.
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
            # Le dirigeant est déjà dans la réponse : aucun appel supplémentaire
            # 📘 Import dans la boucle : Python ne charge le module qu'une fois (cache sys.modules), les
            # 📘 passages suivants sont quasi gratuits (import "paresseux", fait seulement si besoin).
            # 📘 extract_dirigeant renvoie un tuple (nom, qualité) ; `a, b = tuple` déballe les 2 valeurs.
            from services.dirigeants import extract_dirigeant
            prospect.siren = siren
            prospect.dirigeant, prospect.dirigeant_qualite = extract_dirigeant(entry)
            prospects.append(prospect)

        if page >= total_pages:
            break

        page += 1
        # 💡 Le sleep(0.5) protège l'API (limite de débit publique). Pour les tests, rendre ce délai
        # 💡   paramétrable ou simuler requests.get (librairie `responses`) évite d'attendre et d'appeler
        # 💡   le vrai service.
        time.sleep(0.5)  # Rate limiting entre les pages

    logger.info("  → %d entreprise(s) Sirene", len(prospects))
    return prospects
