"""
Moteur d'offres pour le dev web.

Principe (cf. Notion « 9. Offres commerciales ») : l'hameçon → le repas.
On mène TOUJOURS avec UNE offre d'appel à faible engagement (audit / maquette /
widget), avec un bénéfice CONCRET adapté au secteur du prospect. La montée en
gamme (refonte / création à forte marge) se fait après, une fois la confiance
établie — donc on n'affiche jamais le prix du cœur de marge dans un cold email.

Le bot choisit UNE seule offre par prospect, selon l'état de présence web
détecté par l'audit (analyzer.py) :

    pas de site            → création   (entrée : maquette gratuite)
    site Wix/Weebly/…      → migration  (entrée : audit gratuit)
    site vieux/lent/4+ pbs → refonte    (entrée : audit gratuit)
    site OK mais 0 capture → widget      (entrée : démo, ~39€/mois)
    site correct           → audit       (entrée : audit gratuit)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from services.google_maps import Prospect


# ---------------------------------------------------------------------------
# Prix affichés — UNIQUEMENT pour les offres d'appel à faible engagement.
# Modifie ici si tes tarifs changent. Le cœur de marge (création/refonte/
# migration) n'affiche jamais de prix : il se chiffre en propale.
# ---------------------------------------------------------------------------

WIDGET_PRICE = "à partir de 39€/mois (1er mois offert, sans engagement)"

# Outils no-code / propriétaires qui justifient une migration
_FREE_BUILDERS = {"Wix", "Jimdo", "Weebly", "Webnode", "Site123", "GoDaddy"}


# ---------------------------------------------------------------------------
# Bénéfice business concret par secteur cible (target_segments.sector)
# C'est le RÉSULTAT que le prospect comprend immédiatement, pas la technique.
# ---------------------------------------------------------------------------

SECTOR_BENEFITS: Dict[str, str] = {
    "food":         "transformer les visiteurs de votre site en réservations directes, sans commission de plateforme",
    "commerce":     "mettre vos produits en valeur et capter les clients qui vous cherchent déjà en ligne",
    "sante_beaute": "permettre à vos clients de prendre rendez-vous en ligne 24h/24, sans appel à gérer",
    "artisans_btp": "recevoir des demandes de devis qualifiées directement dans votre boîte mail",
    "immo":         "transformer vos visiteurs vendeurs en demandes d'estimation directement dans votre boîte mail",
    "tourisme":     "générer des réservations en direct et réduire votre dépendance aux plateformes",
    "entreprises":  "générer des prises de contact B2B qualifiées et crédibiliser votre expertise",
    "education":    "générer des demandes d'inscription et d'information en ligne",
    "liberales":    "permettre la prise de rendez-vous en ligne et réduire les appels à gérer",
}

_GENERIC_BENEFIT = "transformer votre site en véritable outil d'acquisition de clients"


# ---------------------------------------------------------------------------
# Pitch (proposition de valeur) par type d'offre. {benefit} et {cms} remplis.
# ---------------------------------------------------------------------------

_PITCH: Dict[str, str] = {
    "creation":  "Je conçois pour vous un site moderne, rapide et bien référencé, pensé pour {benefit}.",
    "migration": "Je migre votre site {cms} vers une technologie moderne — plus rapide, mieux référencée et sans dépendance à la plateforme — pensée pour {benefit}.",
    "refonte":   "Je modernise votre site pour qu'il devienne un vrai levier pour votre activité : {benefit}.",
    "widget":    "J'installe sur votre site un outil de capture de leads qui travaille pour vous en continu : {benefit}.",
    "audit":     "Je peux vous montrer concrètement comment votre site pourrait {benefit}.",
}

# ---------------------------------------------------------------------------
# Entrée / CTA par type d'offre. Le prix n'apparaît QUE sur widget et audit.
# ---------------------------------------------------------------------------

_ENTRY: Dict[str, str] = {
    "creation":  "Pour démarrer sans engagement, je vous prépare une maquette gratuite de votre future page d'accueil — vous voyez le résultat avant toute décision.",
    "migration": "Pour commencer, je vous propose un audit gratuit de votre site actuel avec les gains concrets attendus (vitesse, référencement) — sans engagement.",
    "refonte":   "Je vous propose un audit gratuit de votre site avec 3 à 4 améliorations prioritaires — sans engagement.",
    "widget":    f"Je peux l'installer en marque blanche {WIDGET_PRICE} — je vous montre une démo en 15 minutes.",
    "audit":     "Je vous propose un audit gratuit (quelques captures, points concrets et priorisés) — sans engagement.",
}

_LABELS: Dict[str, str] = {
    "creation":  "Création de site",
    "migration": "Migration vers stack moderne",
    "refonte":   "Refonte de site",
    "widget":    "Widget de capture de leads",
    "audit":     "Audit gratuit",
}


@dataclass
class Offer:
    offer_type: str   # creation | migration | refonte | widget | audit
    label: str        # nom lisible (pour debug / export)
    pitch: str        # proposition de valeur, déjà formatée
    cta: str          # offre d'appel + prix éventuel, déjà formatée


def _presence_state(prospect: Prospect) -> str:
    """Déduit le type d'offre à mener depuis l'audit du prospect."""
    if not prospect.has_website():
        return "creation"

    keys = set(prospect.issue_keys or [])
    cms = prospect.cms or ""

    # Site no-code / propriétaire → migration vers un stack maîtrisé
    if cms in _FREE_BUILDERS or "free_builder" in keys:
        return "migration"

    # Site lourdement pénalisé → refonte
    severe = {"outdated", "response_time", "viewport", "site_down"}
    if keys & severe or len(prospect.issues) >= 4:
        return "refonte"

    # Site correct mais aucune capture de leads → widget (offre d'appel récurrente)
    if "lead_form" in keys or "tracking" in keys:
        return "widget"

    # Site correct → audit gratuit comme point d'entrée
    return "audit"


def select_offer(prospect: Prospect, sector: str = "") -> Offer:
    """Sélectionne UNE offre adaptée à l'état web du prospect et à son secteur."""
    offer_type = _presence_state(prospect)
    benefit = SECTOR_BENEFITS.get(sector, _GENERIC_BENEFIT)
    cms = prospect.cms or "actuel"

    pitch = _PITCH[offer_type].format(benefit=benefit, cms=cms)
    cta = _ENTRY[offer_type]
    return Offer(offer_type=offer_type, label=_LABELS[offer_type], pitch=pitch, cta=cta)
