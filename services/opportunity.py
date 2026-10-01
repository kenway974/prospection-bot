"""
services/opportunity.py — Score d'opportunité explicable (0-100, PLUS HAUT = MEILLEUR).

Remplace la lecture « 100 − défauts du site » qui donnait 0 (= meilleure
opportunité) à toute fiche sans site, même hors cible ou déjà très équipée.
Chaque composante est une ligne [libellé, points] visible dans l'interface.

Le score « qualité du site » (p.score, calculé par analyzer.py) reste inchangé
et sert toujours au seuil « Score max à contacter ».
"""

from __future__ import annotations

from typing import List, Tuple

NO_SITE_POINTS = 55            # aucun site, ni sur la fiche ni retrouvé
WEAK_SITE_FACTOR = 0.5         # site faible : (100 − qualité) × 0,5 → jusqu'à 50 pts
NO_FORM_POINTS = 15            # site sans formulaire de contact / devis
MISSING_ON_MAPS_POINTS = 5     # site existant mais absent de la fiche Google
FEW_REVIEWS = ((10, 20, "très peu d'avis Google"), (30, 10, "peu d'avis Google"))
MANY_REVIEWS = (100, -10, "beaucoup d'avis Google")
SOLID_PRESENCE_POINTS = -40    # bon site + beaucoup d'avis bien notés + réseaux sociaux
SOLID_MIN_REVIEWS, SOLID_MIN_RATING = 50, 4.5

# Drapeaux « à vérifier » qui rendent l'opportunité douteuse (début du libellé → points)
FLAG_PENALTIES = (
    ("site sur un domaine étranger", -30),
    ("chiffre d'affaires déclaré 0", -20),
    ("établissements ouverts (chaîne", -20),
    ("code NAF", -10),
    ("métier « ", -5),
)


def _has_solid_presence(p, keys: set) -> bool:
    return (
        p.has_website()
        and not keys & {"https", "viewport", "social_links", "site_down"}
        and (p.user_ratings_total or 0) >= SOLID_MIN_REVIEWS
        and (p.rating or 0) >= SOLID_MIN_RATING
    )


def compute(p) -> Tuple[int, List[list]]:
    """(score d'opportunité 0-100, détail [[libellé, points], …]) pour un prospect analysé."""
    keys = set(p.issue_keys or [])
    details: List[list] = []

    if not p.has_website():
        details.append(["aucun site (ni sur la fiche Google, ni retrouvé)", NO_SITE_POINTS])
    else:
        weakness = round((100 - max(0, min(100, p.score))) * WEAK_SITE_FACTOR)
        if weakness:
            details.append([f"site à améliorer (qualité {p.score}/100)", weakness])
        if "lead_form" in keys:
            details.append(["pas de formulaire de contact / devis", NO_FORM_POINTS])
        if getattr(p, "website_source", "") == "deviné":
            details.append(["site absent de la fiche Google", MISSING_ON_MAPS_POINTS])

    reviews = p.user_ratings_total or 0
    for limit, points, label in FEW_REVIEWS:
        if reviews < limit:
            details.append([f"{label} ({reviews})", points])
            break
    else:
        if reviews >= MANY_REVIEWS[0]:
            details.append([f"{MANY_REVIEWS[2]} ({reviews})", MANY_REVIEWS[1]])

    if _has_solid_presence(p, keys):
        details.append(["présence déjà solide (bon site, avis, réseaux sociaux)", SOLID_PRESENCE_POINTS])

    for flag in getattr(p, "flags", []) or []:
        for prefix, points in FLAG_PENALTIES:
            if prefix in flag:
                details.append([f"à vérifier : {flag}", points])
                break

    total = max(0, min(100, sum(points for _, points in details)))
    return total, details


def apply(p) -> None:
    p.opportunity, p.score_details = compute(p)
