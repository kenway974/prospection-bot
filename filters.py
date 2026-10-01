"""
filters.py — Critères de sélection des prospects.

Trois moments de filtrage, du moins cher au plus cher :
  1. raw_exclusion_reason()       → résultat brut Google Maps (Text Search), AVANT
                                    l'appel payant Place Details : fermé, note, nb d'avis
  2. prospect_exclusion_reason()  → prospect construit (toutes sources) : site web, téléphone
  3. post_analysis_reason()       → après l'analyse du site : email trouvé

Les sources hors Google Maps (Sirène, Pages Jaunes…) n'ont ni note ni avis :
les critères 1 ne s'appliquent qu'à Google Maps.

Les franchises sont gérées à part (services/franchises.py) et le seuil de score
par le pipeline, car son sens dépend du service (score_direction).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, List, Optional

WEBSITE_ANY = "any"
WEBSITE_WITHOUT = "without"
WEBSITE_WITH = "with"

PHONE_ANY = "any"
PHONE_REQUIRED = "required"
PHONE_MOBILE = "mobile"

WEBSITE_CHOICES = (WEBSITE_ANY, WEBSITE_WITHOUT, WEBSITE_WITH)
PHONE_CHOICES = (PHONE_ANY, PHONE_REQUIRED, PHONE_MOBILE)

# Libellés de l'interface
WEBSITE_LABELS: Dict[str, str] = {
    WEBSITE_ANY: "Peu importe",
    WEBSITE_WITHOUT: "Sans site uniquement",
    WEBSITE_WITH: "Avec site uniquement",
}
PHONE_LABELS: Dict[str, str] = {
    PHONE_ANY: "Peu importe",
    PHONE_REQUIRED: "Téléphone obligatoire",
    PHONE_MOBILE: "Mobile (06/07) uniquement",
}

GOOGLE_OPERATIONAL = "OPERATIONAL"


@dataclass
class FilterCriteria:
    min_rating: float = 3.0
    max_rating: float = 5.0
    min_reviews: int = 0
    max_reviews: Optional[int] = None   # None = pas de limite (beaucoup d'avis = souvent une grosse enseigne)
    website: str = WEBSITE_ANY
    phone: str = PHONE_ANY
    exclude_closed: bool = True         # Fermé temporairement ou définitivement (Google Maps)
    require_email: bool = False

    def __post_init__(self) -> None:
        """Refuse les valeurs incohérentes plutôt que de désactiver un filtre sans prévenir."""
        if self.website not in WEBSITE_CHOICES:
            raise ValueError(f"Filtre site web invalide : {self.website!r} (attendu : {', '.join(WEBSITE_CHOICES)})")
        if self.phone not in PHONE_CHOICES:
            raise ValueError(f"Filtre téléphone invalide : {self.phone!r} (attendu : {', '.join(PHONE_CHOICES)})")
        if not 0 <= self.min_rating <= self.max_rating <= 5:
            raise ValueError(f"Fourchette de note invalide : {self.min_rating} → {self.max_rating} (entre 0 et 5)")
        if self.min_reviews < 0:
            raise ValueError(f"Nombre d'avis minimum invalide : {self.min_reviews}")
        if self.max_reviews is not None and self.max_reviews < self.min_reviews:
            raise ValueError(f"Fourchette d'avis invalide : {self.min_reviews} → {self.max_reviews}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "FilterCriteria":
        """Recrée des critères depuis un dict sauvegardé (clés inconnues ignorées, manquantes = défaut)."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})

    def summary(self) -> str:
        """Résumé lisible pour les logs, limité aux critères actifs."""
        parts = [f"note {self.min_rating:g}–{self.max_rating:g}"]
        if self.min_reviews or self.max_reviews is not None:
            high = "∞" if self.max_reviews is None else str(self.max_reviews)
            parts.append(f"avis {self.min_reviews}–{high}")
        if self.website != WEBSITE_ANY:
            parts.append(WEBSITE_LABELS[self.website].lower())
        if self.phone != PHONE_ANY:
            parts.append(PHONE_LABELS[self.phone].lower())
        if self.exclude_closed:
            parts.append("ouverts uniquement")
        if self.require_email:
            parts.append("email obligatoire")
        return " · ".join(parts)


def is_mobile(phone: Optional[str]) -> bool:
    if not phone:
        return False
    num = phone.replace(" ", "").replace(".", "").replace("-", "")
    if num.startswith("+33"):
        num = "0" + num[3:]
    return num.startswith("06") or num.startswith("07")


def raw_exclusion_reason(raw: Dict[str, Any], c: FilterCriteria) -> Optional[str]:
    """Résultat brut Google Maps Text Search → raison d'exclusion, ou None s'il est gardé."""
    status = raw.get("business_status")
    if c.exclude_closed and status and status != GOOGLE_OPERATIONAL:
        return "établissement fermé"
    rating = raw.get("rating")
    if rating is not None and rating < c.min_rating:
        return f"note < {c.min_rating:g}"
    if rating is not None and rating > c.max_rating:
        return f"note > {c.max_rating:g}"
    reviews = raw.get("user_ratings_total") or 0
    if reviews < c.min_reviews:
        return f"moins de {c.min_reviews} avis"
    if c.max_reviews is not None and reviews > c.max_reviews:
        return f"plus de {c.max_reviews} avis"
    return None


def prospect_exclusion_reason(p, c: FilterCriteria) -> Optional[str]:
    """Prospect construit (toutes sources) → raison d'exclusion, ou None s'il est gardé."""
    if c.website == WEBSITE_WITHOUT and p.has_website():
        return "a déjà un site"
    if c.website == WEBSITE_WITH and not p.has_website():
        return "pas de site"
    if c.phone == PHONE_REQUIRED and not p.phone:
        return "pas de téléphone"
    if c.phone == PHONE_MOBILE and not is_mobile(p.phone):
        return "pas de mobile"
    return None


def post_analysis_reason(p, c: FilterCriteria) -> Optional[str]:
    """Prospect analysé → raison d'exclusion, ou None s'il est gardé."""
    if c.require_email and not p.email:
        return "pas d'email trouvé"
    return None


def count_reason(counter: Dict[str, int], reason: Optional[str]) -> bool:
    """Incrémente le compteur de la raison. Retourne True si le prospect est exclu."""
    if reason is None:
        return False
    counter[reason] = counter.get(reason, 0) + 1
    return True


def format_exclusions(counter: Dict[str, int]) -> str:
    """{'note < 3': 2, 'pas de site': 1} → '2 note < 3 · 1 pas de site'."""
    return " · ".join(f"{n} {reason}" for reason, n in counter.items())


def parse_locations(raw: str) -> List[str]:
    """Une ville par ligne (ou séparées par « ; »), sans doublon ni ligne vide."""
    out: List[str] = []
    for part in raw.replace(";", "\n").splitlines():
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out
