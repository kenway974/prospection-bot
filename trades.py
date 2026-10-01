"""
trades.py — Métiers du bâtiment / aménagement : de quoi reconnaître une vraie cible.

Pour chaque métier :
  - aliases      : mots-clés saisis qui désignent ce métier (« cuisinistes », « cuisine équipée »…)
  - queries      : requêtes Google Maps à lancer (synonymes) pour ne pas rater les indépendants
  - name_words   : mots qui, dans le NOM de l'établissement, confirment le métier
  - maps_types   : catégories Google Maps compatibles (liste blanche)
  - naf_prefixes : codes NAF (Sirène) cohérents avec le métier

HYPOTHÈSE : les catégories Google (`types` de l'API Places) sont grossières
(ex. « home_goods_store », « general_contractor ») et les listes NAF sont
volontairement larges. Une catégorie inconnue ne fait donc pas exclure : elle
fait seulement « marquer à vérifier ». Seule une catégorie clairement hors
métier (électricien pour un cuisiniste, restaurant, école…) exclut.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

# Catégories Google trop génériques pour conclure quoi que ce soit
GENERIC_TYPES = {"point_of_interest", "establishment", "store", "premise", "local_government_office"}

# Catégories Google jamais compatibles avec un métier du bâtiment
NEVER_BUILDING_TYPES = {
    "restaurant", "food", "cafe", "bar", "meal_takeaway", "meal_delivery", "bakery",
    "school", "primary_school", "secondary_school", "university", "lodging",
    "night_club", "gym", "beauty_salon", "hair_care", "spa", "doctor", "dentist",
    "hospital", "pharmacy", "bank", "insurance_agency", "real_estate_agency",
    "car_dealer", "car_repair", "supermarket", "grocery_or_supermarket",
}

# Mots du nom qui signalent une autre activité (cours de cuisine, restauration…)
OFF_TARGET_NAME_WORDS = (
    "cours de cuisine", "atelier culinaire", "ecole de cuisine", "chef", "chefs",
    "restaurant", "traiteur", "brasserie", "pizzeria", "boulangerie",
)

# Coût Google : chaque requête = jusqu'à 3 pages Text Search (~0,032 $ / page).
MAX_QUERIES_PER_KEYWORD = 3

_BUILDING_TYPES = {"general_contractor", "home_goods_store", "furniture_store", "hardware_store"}


@dataclass(frozen=True)
class Trade:
    id: str
    label: str
    aliases: Tuple[str, ...]
    queries: Tuple[str, ...]
    name_words: Tuple[str, ...]
    maps_types: frozenset = field(default_factory=frozenset)
    naf_prefixes: Tuple[str, ...] = ()


TRADES: Tuple[Trade, ...] = (
    Trade(
        "cuisiniste", "Cuisiniste",
        aliases=("cuisiniste", "magasin de cuisine", "cuisine equipee", "cuisine sur mesure", "cuisines"),
        queries=("cuisiniste", "magasin de cuisines équipées", "cuisine sur mesure"),
        name_words=("cuisine", "cuisines", "cuisiniste", "kitchen", "agencement"),
        maps_types=frozenset(_BUILDING_TYPES),
        naf_prefixes=("47.59", "43.32", "31.02", "31.09", "46.47", "43.39", "43.22"),
    ),
    Trade(
        "salle_de_bain", "Salle de bain",
        aliases=("salle de bain", "salles de bain", "amenagement salle de bain"),
        queries=("salle de bain", "aménagement salle de bain", "rénovation salle de bain"),
        name_words=("bain", "bains", "sanitaire", "douche"),
        maps_types=frozenset(_BUILDING_TYPES | {"plumber"}),
        naf_prefixes=("43.22", "43.33", "43.39", "47.59", "47.52", "43.32"),
    ),
    Trade(
        "carreleur", "Carreleur",
        aliases=("carreleur", "carrelage", "carrelages"),
        queries=("carreleur", "carrelage pose"),
        name_words=("carrel", "carrelage", "carrelages", "carreleur", "faience"),
        maps_types=frozenset(_BUILDING_TYPES),
        naf_prefixes=("43.33", "43.39", "47.52", "46.73"),
    ),
    Trade(
        "chauffagiste", "Chauffagiste",
        aliases=("chauffagiste", "chauffage", "pompe a chaleur", "climatisation"),
        queries=("chauffagiste", "installateur pompe à chaleur", "entreprise de chauffage"),
        name_words=("chauffage", "chauffagiste", "thermique", "clim", "climatisation", "energie", "pac"),
        maps_types=frozenset(_BUILDING_TYPES | {"plumber", "electrician"}),
        naf_prefixes=("43.22", "33.12", "43.21", "71.12"),
    ),
    Trade(
        "electricien", "Électricien",
        aliases=("electricien", "electricite", "electricite generale"),
        queries=("électricien", "entreprise d'électricité"),
        name_words=("elec", "electric", "electricite", "electricien"),
        maps_types=frozenset(_BUILDING_TYPES | {"electrician"}),
        naf_prefixes=("43.21",),
    ),
    Trade(
        "plombier", "Plombier",
        aliases=("plombier", "plomberie"),
        queries=("plombier", "entreprise de plomberie"),
        name_words=("plomb", "plomberie", "plombier", "sanitaire"),
        maps_types=frozenset(_BUILDING_TYPES | {"plumber"}),
        naf_prefixes=("43.22",),
    ),
    Trade(
        "pisciniste", "Pisciniste",
        aliases=("pisciniste", "piscine", "piscines", "construction piscine"),
        queries=("pisciniste", "construction piscine", "entretien piscine"),
        name_words=("piscine", "piscines", "pool", "spa", "aqua"),
        maps_types=frozenset(_BUILDING_TYPES),
        naf_prefixes=("43.99", "42.99", "43.22", "47.64", "81.30", "41.20", "43.29", "33.19"),
    ),
    Trade(
        "menuisier", "Menuisier",
        aliases=("menuisier", "menuiserie", "fenetres", "poseur de fenetres"),
        queries=("menuisier", "menuiserie", "pose de fenêtres"),
        name_words=("menuis", "bois", "fenetre", "fenetres", "ebeniste"),
        maps_types=frozenset(_BUILDING_TYPES),
        naf_prefixes=("43.32", "16.23", "31.09", "43.39"),
    ),
)


def normalize(text: str) -> str:
    """Minuscules, sans accents ni ponctuation : « Électricité-Générale » → « electricite generale »."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _singular(text: str) -> str:
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in text.split())


def find_trade(keyword: str) -> Optional[Trade]:
    """Métier correspondant à un mot-clé saisi (pluriel et accents tolérés), ou None."""
    kw = _singular(normalize(keyword))
    if not kw:
        return None
    for trade in TRADES:
        if any(kw == _singular(normalize(a)) for a in trade.aliases):
            return trade
    return None


def _has_word(name_norm: str, words: Iterable[str]) -> bool:
    padded = f" {name_norm} "
    return any(f" {normalize(w)}" in padded for w in words)


def category_verdict(name: str, types: Iterable[str], trade: Trade) -> Tuple[str, str]:
    """
    Verdict de catégorie pour un établissement Google Maps :
      ("ok", "")                 → cible cohérente
      ("verifier", raison)       → rien ne confirme le métier, gardé mais marqué
      ("exclure", raison)        → hors cible
    """
    name_norm = normalize(name)
    specific = {t for t in (types or []) if t not in GENERIC_TYPES}

    if _has_word(name_norm, OFF_TARGET_NAME_WORDS):
        return "exclure", "nom hors métier (cours de cuisine, restauration…)"
    if specific & NEVER_BUILDING_TYPES:
        return "exclure", f"catégorie Google hors bâtiment : {', '.join(sorted(specific & NEVER_BUILDING_TYPES))}"
    if _has_word(name_norm, trade.name_words):
        return "ok", ""
    if specific & trade.maps_types:
        return "ok", ""
    if specific:
        return "exclure", f"catégorie Google hors métier « {trade.label} » : {', '.join(sorted(specific))}"
    return "verifier", f"métier « {trade.label} » non confirmé (ni le nom ni la catégorie Google)"


def naf_matches(naf: str, trade: Trade) -> bool:
    """Le code NAF Sirène (ex. « 47.59A ») est-il cohérent avec le métier ?"""
    return bool(naf) and any(naf.startswith(prefix) for prefix in trade.naf_prefixes)


def queries_for(keyword: str) -> List[str]:
    """Requêtes à lancer : le mot-clé saisi d'abord, puis les synonymes du métier (sans doublon)."""
    trade = find_trade(keyword)
    out: List[str] = [keyword]
    for q in (trade.queries if trade else ()):
        if _singular(normalize(q)) not in {_singular(normalize(x)) for x in out}:
            out.append(q)
    return out[:MAX_QUERIES_PER_KEYWORD]
