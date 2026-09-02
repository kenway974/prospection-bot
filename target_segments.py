"""
Segments de cibles — qui vous prospectez.
Séparé des services (service_profiles.py) pour permettre 2 sélecteurs indépendants dans l'UI.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class TargetSegment:
    id: str
    emoji: str
    name: str
    sector: str
    keywords: List[str]
    target_size: str          # "tpe", "pme", "all"
    description: str
    radius: int = 10000
    max_results: int = 5
    score_threshold_override: Optional[int] = None
    location_default: str = ""


TARGET_SECTOR_LABELS: Dict[str, str] = {
    "food":           "🍽️ Restauration & Food",
    "commerce":       "🛍️ Commerce & Retail",
    "sante_beaute":   "🏥 Santé & Beauté",
    "artisans_btp":   "🔨 Artisans & BTP",
    "immo":           "🏠 Immobilier & Hôtellerie",
    "tourisme":       "🌴 Tourisme & Loisirs",
    "entreprises":    "💼 Entreprises & B2B",
    "education":      "📚 Éducation & Formation",
    "liberales":      "⚖️ Professions libérales",
}

SIZE_LABELS: Dict[str, str] = {
    "tpe": "TPE / Artisans",
    "pme": "PME / Entreprises",
    "all": "Tous secteurs",
}


TARGET_SEGMENTS: List[TargetSegment] = [

    # -----------------------------------------------------------------------
    # Restauration & Food
    # -----------------------------------------------------------------------

    TargetSegment(
        id="restaurants",
        emoji="🍽️",
        name="Restaurants & Brasseries",
        sector="food",
        keywords=[
            "restaurant", "brasserie", "bistrot", "auberge",
            "restaurant gastronomique", "restaurant traditionnel",
            "restaurant italien", "restaurant de spécialités", "table d'hôtes",
        ],
        target_size="tpe",
        description="Restaurants, brasseries et bistrots locaux — forte densité, besoins web récurrents.",
    ),

    TargetSegment(
        id="boulangeries",
        emoji="🥐",
        name="Boulangeries & Pâtisseries",
        sector="food",
        keywords=[
            "boulangerie", "pâtisserie", "viennoiserie",
            "boulangerie artisanale", "boulangerie pâtisserie",
            "chocolatier", "pâtisserie fine",
        ],
        target_size="tpe",
        description="Boulangeries et pâtisseries artisanales — présence web souvent minimale.",
    ),

    TargetSegment(
        id="cafes_bars",
        emoji="☕",
        name="Cafés & Bars",
        sector="food",
        keywords=[
            "café", "bar", "pub", "bar à vins", "salon de thé",
            "bar à cocktails", "café restaurant", "bar à bières",
        ],
        target_size="tpe",
        description="Cafés et bars de proximité — clientèle locale, fort potentiel réseaux sociaux.",
    ),

    TargetSegment(
        id="restauration_rapide",
        emoji="🍕",
        name="Restauration rapide",
        sector="food",
        keywords=[
            "pizzeria", "kebab", "fast food", "sushi", "snack",
            "burger", "food truck", "tacos", "poke bowl", "traiteur asiatique",
        ],
        target_size="tpe",
        description="Fast food, pizzerias et snacks — besoin de visibilité locale et commande en ligne.",
    ),

    # -----------------------------------------------------------------------
    # Commerce & Retail
    # -----------------------------------------------------------------------

    TargetSegment(
        id="boutiques_mode",
        emoji="👗",
        name="Boutiques mode & accessoires",
        sector="commerce",
        keywords=[
            "boutique mode", "prêt-à-porter", "vêtements",
            "boutique vêtements femme", "boutique vêtements homme",
            "friperie", "boutique chaussures", "concept store", "maroquinerie",
        ],
        target_size="tpe",
        description="Boutiques de mode indépendantes — fort besoin de présence visuelle et réseaux sociaux.",
    ),

    TargetSegment(
        id="commerces_luxe",
        emoji="💎",
        name="Commerces de luxe & cadeaux",
        sector="commerce",
        keywords=[
            "bijouterie", "horloger", "galerie art", "luxe", "joaillerie",
            "antiquaire", "boutique cadeaux", "parfumerie", "art de la table",
        ],
        target_size="tpe",
        description="Bijouteries, galeries d'art et commerces de luxe — image de marque premium.",
    ),

    TargetSegment(
        id="pharmacies",
        emoji="💊",
        name="Pharmacies & Parapharmacies",
        sector="commerce",
        keywords=[
            "pharmacie", "parapharmacie", "herboristerie", "pharmacie de garde",
            "orthopédie", "matériel médical",
        ],
        target_size="tpe",
        description="Pharmacies et parapharmacies — concurrence accrue, besoin de fidélisation digitale.",
    ),

    TargetSegment(
        id="epiceries_cavistes",
        emoji="🍷",
        name="Épiceries fines & Cavistes",
        sector="commerce",
        keywords=[
            "épicerie fine", "cave à vins", "fromagerie", "confiserie",
            "caviste", "épicerie bio", "torréfacteur", "primeur", "chocolaterie",
        ],
        target_size="tpe",
        description="Épiceries fines, cavistes et fromagers — produits à fort potentiel e-commerce.",
    ),

    # -----------------------------------------------------------------------
    # Santé & Beauté
    # -----------------------------------------------------------------------

    TargetSegment(
        id="cabinets_medicaux",
        emoji="🩺",
        name="Cabinets médicaux & Dentistes",
        sector="sante_beaute",
        keywords=[
            "cabinet médical", "dentiste", "ophtalmologue", "dermatologue",
            "médecin généraliste", "cabinet dentaire", "orthodontiste",
            "kinésithérapeute", "ostéopathe", "cabinet infirmier",
        ],
        target_size="tpe",
        description="Cabinets médicaux libéraux — prise de RDV en ligne souvent absente ou mal configurée.",
    ),

    TargetSegment(
        id="salles_sport",
        emoji="💪",
        name="Salles de sport & Fitness",
        sector="sante_beaute",
        keywords=[
            "salle de sport", "fitness", "CrossFit", "studio yoga",
            "salle de musculation", "club de sport", "studio pilates",
            "coach sportif", "box crossfit",
        ],
        target_size="tpe",
        description="Salles de sport et studios fitness — abonnements en ligne, suivi client, réseaux sociaux.",
    ),

    TargetSegment(
        id="spas_instituts",
        emoji="🌸",
        name="Spas & Instituts de beauté",
        sector="sante_beaute",
        keywords=[
            "spa", "institut de beauté", "salon esthétique", "onglerie",
            "centre de bien-être", "salon de massage", "centre d'épilation",
            "centre d'amincissement",
        ],
        target_size="tpe",
        description="Spas et instituts de beauté — réservation en ligne, photos professionnelles.",
    ),

    TargetSegment(
        id="coiffeurs",
        emoji="✂️",
        name="Coiffeurs & Barbiers",
        sector="sante_beaute",
        keywords=[
            "coiffeur", "barbier", "salon de coiffure", "coiffeur visagiste",
            "salon de coiffure homme", "coiffure à domicile", "salon de coiffure mixte",
        ],
        target_size="tpe",
        description="Salons de coiffure et barbiers — prise de RDV, présence Instagram, fidélisation.",
    ),

    # -----------------------------------------------------------------------
    # Artisans & BTP
    # -----------------------------------------------------------------------

    TargetSegment(
        id="artisans_batiment",
        emoji="🏗️",
        name="Artisans du bâtiment (tous corps)",
        sector="artisans_btp",
        keywords=[
            "artisan", "maçon", "carreleur", "peintre en bâtiment", "plâtrier",
            "menuisier", "couvreur", "charpentier", "façadier", "plaquiste",
        ],
        target_size="tpe",
        description="Artisans du bâtiment — souvent sans site ou avec un site très basique.",
    ),

    TargetSegment(
        id="plombiers_electriciens",
        emoji="🔌",
        name="Plombiers & Électriciens",
        sector="artisans_btp",
        keywords=[
            "plombier", "électricien", "dépannage", "plomberie chauffage",
            "électricité générale", "serrurier", "dépannage plomberie",
        ],
        target_size="tpe",
        description="Plombiers et électriciens — besoin de visibilité locale pour les urgences.",
    ),

    TargetSegment(
        id="entreprises_cvc",
        emoji="🌡️",
        name="Entreprises CVC (Chauffage, Ventil, Clim)",
        sector="artisans_btp",
        keywords=[
            "chauffagiste", "climatisation", "pompe à chaleur", "CVC",
            "installateur climatisation", "entreprise de chauffage", "frigoriste",
        ],
        target_size="tpe",
        description="Entreprises CVC — saisonnalité forte, besoin de générer des leads en continu.",
    ),

    TargetSegment(
        id="garages_auto",
        emoji="🚗",
        name="Garages & Carrosseries",
        sector="artisans_btp",
        keywords=[
            "garage automobile", "carrosserie", "mécanique auto", "centre auto",
            "réparation automobile", "contrôle technique", "pneumaticien",
        ],
        target_size="tpe",
        description="Garages et carrosseries — avis Google cruciaux, présence locale à renforcer.",
    ),

    # -----------------------------------------------------------------------
    # Immobilier & Hôtellerie
    # -----------------------------------------------------------------------

    TargetSegment(
        id="agences_immo",
        emoji="🏘️",
        name="Agences immobilières & Syndics",
        sector="immo",
        keywords=[
            "agence immobilière", "syndic de copropriété", "promoteur immobilier",
            "gestion locative", "administrateur de biens", "agence de location",
            "mandataire immobilier", "chasseur immobilier", "immobilier neuf",
            "transaction immobilière", "agence immobilière commerciale",
        ],
        target_size="pme",
        description="Agences immobilières et syndics — lead generation, CRM, outils digitaux.",
    ),

    TargetSegment(
        id="hotels",
        emoji="🏨",
        name="Hôtels & Résidences",
        sector="immo",
        keywords=[
            "hôtel", "résidence services", "appart hôtel", "hôtel restaurant",
            "hôtel spa", "hôtel de charme", "boutique hôtel",
        ],
        target_size="all",
        description="Hôtels et résidences — booking direct, référencement, photos et vidéos.",
    ),

    TargetSegment(
        id="locations_saisonnieres",
        emoji="🏡",
        name="Locations saisonnières & Gîtes",
        sector="immo",
        keywords=[
            "gîte", "location saisonnière", "chambre d'hôtes", "maison d'hôtes",
            "gîte rural", "location vacances", "meublé de tourisme", "hébergement insolite",
        ],
        target_size="tpe",
        description="Gîtes et chambres d'hôtes — présence en dehors des plateformes, booking direct.",
    ),

    # -----------------------------------------------------------------------
    # Tourisme & Loisirs
    # -----------------------------------------------------------------------

    TargetSegment(
        id="activites_touristiques",
        emoji="🎡",
        name="Activités touristiques & Loisirs",
        sector="tourisme",
        keywords=[
            "activité touristique", "escape game", "accrobranche", "parc loisirs",
            "laser game", "bowling", "karting", "mini-golf", "parc d'attractions",
        ],
        target_size="tpe",
        description="Activités touristiques et de loisirs — réservation en ligne, avis Google, SEO local.",
    ),

    TargetSegment(
        id="salles_evenements",
        emoji="🎉",
        name="Salles de mariage & Réceptions",
        sector="tourisme",
        keywords=[
            "salle de mariage", "salle de réception", "château", "domaine",
            "salle des fêtes", "lieu de réception", "domaine viticole", "salle de séminaire",
        ],
        target_size="all",
        description="Salles de mariage et domaines — photos et vidéos cruciales, forte valeur par contrat.",
    ),

    TargetSegment(
        id="camping_villages",
        emoji="⛺",
        name="Campings & Villages vacances",
        sector="tourisme",
        keywords=[
            "camping", "village vacances", "glamping", "camping caravaning",
            "camping 4 étoiles", "parc résidentiel de loisirs",
        ],
        target_size="all",
        description="Campings et villages vacances — site web, réservation en ligne, avis clients.",
    ),

    # -----------------------------------------------------------------------
    # Entreprises & B2B
    # -----------------------------------------------------------------------

    TargetSegment(
        id="startups_tech",
        emoji="🚀",
        name="Startups & Entreprises tech",
        sector="entreprises",
        keywords=[
            "startup", "SaaS", "fintech", "scale-up", "éditeur de logiciel",
            "entreprise tech", "jeune entreprise innovante",
        ],
        target_size="pme",
        description="Startups et scale-ups en croissance — outils, automatisation, recrutement.",
    ),

    TargetSegment(
        id="agences_comm",
        emoji="📢",
        name="Agences web & Communication",
        sector="entreprises",
        keywords=[
            "agence web", "agence communication", "agence marketing",
            "agence digitale", "agence de publicité", "studio graphique",
            "agence événementielle", "agence de relations presse",
        ],
        target_size="pme",
        description="Agences web et communication — sous-traitance, partenariats, white label.",
    ),

    TargetSegment(
        id="cabinets_conseil",
        emoji="🏢",
        name="Cabinets de conseil & ESN",
        sector="entreprises",
        keywords=[
            "cabinet conseil", "ESN", "SSII", "consulting", "cabinet d'audit",
            "société de conseil", "cabinet de recrutement", "bureau d'études",
        ],
        target_size="pme",
        description="Cabinets de conseil et ESN — profils RH, formation, automatisation.",
    ),

    TargetSegment(
        id="cabinets_juridiques",
        emoji="⚖️",
        name="Cabinets d'avocats & Notaires",
        sector="entreprises",
        keywords=[
            "cabinet d'avocats", "notaire", "cabinet juridique", "avocat d'affaires",
            "étude notariale", "huissier de justice", "expert-comptable",
        ],
        target_size="pme",
        description="Cabinets juridiques — discrétion, traduction, coursier, conformité RGPD.",
    ),

    TargetSegment(
        id="pme_industrie",
        emoji="🏭",
        name="PME & Industries",
        sector="entreprises",
        keywords=[
            "PME", "industrie", "logistique", "entrepôt", "société de transport",
            "entreprise industrielle", "fabricant", "grossiste",
        ],
        target_size="pme",
        description="PME industrielles et logistiques — RSE, formation, optimisation des processus.",
    ),

    TargetSegment(
        id="coworking",
        emoji="🖥️",
        name="Espaces de coworking",
        sector="entreprises",
        keywords=[
            "coworking", "espace de travail partagé", "pépinière d'entreprises",
            "bureau partagé", "centre d'affaires", "espace de coworking",
        ],
        target_size="pme",
        description="Espaces de coworking et pépinières — traiteur, animation, services aux membres.",
    ),

    # -----------------------------------------------------------------------
    # Éducation & Formation
    # -----------------------------------------------------------------------

    TargetSegment(
        id="ecoles_lycees",
        emoji="🏫",
        name="Écoles & Lycées",
        sector="education",
        keywords=[
            "école", "lycée", "collège", "établissement scolaire", "école privée",
            "groupe scolaire", "école primaire", "institut privé",
        ],
        target_size="all",
        description="Établissements scolaires — cours particuliers, animation, formation des équipes.",
    ),

    TargetSegment(
        id="centres_formation",
        emoji="🎓",
        name="Centres de formation",
        sector="education",
        keywords=[
            "centre de formation", "auto-école", "organisme de formation",
            "formation professionnelle", "centre de formation continue",
            "école de langues", "école supérieure privée",
        ],
        target_size="tpe",
        description="Centres de formation et auto-écoles — présence digitale, recrutement d'apprenants.",
    ),

    # -----------------------------------------------------------------------
    # Professions libérales
    # -----------------------------------------------------------------------

    TargetSegment(
        id="professions_liberales",
        emoji="👔",
        name="Médecins, Avocats, Coachs solos",
        sector="liberales",
        keywords=[
            "médecin libéral", "avocat", "notaire solo", "coach", "thérapeute",
            "psychologue", "naturopathe", "consultant indépendant", "sophrologue",
            "diététicien",
        ],
        target_size="tpe",
        description="Professions libérales solo — assistance virtuelle, outils de gestion, site web.",
    ),

]


def get_target(target_id: str) -> Optional[TargetSegment]:
    return next((t for t in TARGET_SEGMENTS if t.id == target_id), None)


def list_targets() -> List[TargetSegment]:
    return TARGET_SEGMENTS
