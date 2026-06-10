"""
Profils de prospection prédéfinis.
Chaque profil définit :
  - L'identité du prospecteur
  - Les mots-clés de recherche
  - Les critères de qualification
  - Le template d'accroche email/SMS
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class Profile:
    id: str
    emoji: str
    name: str
    description: str
    keywords: List[str]
    location: str
    your_title: str
    your_offer: str                # Ce que tu proposes en 1 phrase
    email_hook: str                # Accroche personnalisée pour le mail
    sms_hook: str                  # Accroche courte pour le SMS (max 100 chars)
    qualification_criteria: List[str]   # Ce qu'on cherche chez le prospect
    check_weight_overrides: dict = field(default_factory=dict)  # Poids spécifiques à ce profil
    radius: int = 10000
    max_results: int = 5
    # "asc" = score bas = bon prospect (défaut, web dev)
    # "desc" = score haut = bon prospect (ex: coursier — score 100 = pas de livraison = opportunité)
    score_direction: str = "asc"
    score_threshold_default: int = 100


PROFILES: List[Profile] = [

    Profile(
        id="dev_web",
        emoji="💻",
        name="Dev Web / Freelance",
        description="Cible les commerces et PME avec un site absent, vieillissant ou non optimisé.",
        keywords=["restaurant", "boulangerie", "coiffeur", "garage automobile", "cabinet dentaire"],
        location="Lyon, France",
        your_title="Développeur Web Freelance",
        your_offer="Création et refonte de sites web professionnels",
        email_hook=(
            "En cherchant {name} sur Google, j'ai analysé votre présence en ligne "
            "et identifié plusieurs points qui freinent votre visibilité et vos conversions."
        ),
        sms_hook="J'ai analysé votre site et trouvé des axes d'amélioration. Dispo pour un retour gratuit ?",
        qualification_criteria=[
            "Site web absent",
            "Site non sécurisé (HTTP)",
            "Site non responsive",
            "Absence de formulaire de contact",
            "Absence de tracking",
            "Mauvais référencement SEO",
        ],
    ),

    Profile(
        id="coursier",
        emoji="🚚",
        name="Coursier High Ticket",
        description="Cible les professionnels et commerces haut de gamme sans solution de course dédiée.",
        keywords=["notaire", "avocat", "bijouterie", "galerie d'art", "boutique mode", "mobilier design", "architecte", "expert-comptable"],
        location="Paris, France",
        your_title="Service de course express haut de gamme",
        your_offer="Livraison sécurisée et discrète de vos documents et colis sensibles en moins de 2h",
        email_hook=(
            "Je gère un service de course express spécialisé dans les envois sensibles et haut de gamme. "
            "Pour des professionnels comme {name}, la rapidité et la discrétion ne sont pas négociables — "
            "c'est exactement ce que nous proposons, sans les contraintes d'un prestataire généraliste."
        ),
        sms_hook="Course express discrète pour docs et colis sensibles. Intervention en 2h. Dispo pour en parler ?",
        qualification_criteria=[
            "Professionnel ou commerce haut de gamme",
            "Pas de service de course dédié en place",
            "Besoins en envois de documents ou colis de valeur",
        ],
        score_direction="desc",
        score_threshold_default=70,
        check_weight_overrides={
            # Désactiver tous les checks web dev
            "https": 0, "response_time": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "tracking": 0, "lead_form": 0,
            "free_builder": 0, "social_links": 0, "outdated": 0,
            # Livraison déjà couverte = moins d'opportunité
            "delivery_covered": 15,
            # low_volume désactivé : un petit cabinet d'avocats a peu d'avis mais reste bon client
            "low_volume": 0,
        },
    ),

    Profile(
        id="fleuriste",
        emoji="💐",
        name="Fleuriste",
        description="Cible les salles de mariage, hôtels et entreprises pour des collaborations événementielles.",
        keywords=["salle de mariage", "hôtel", "wedding planner", "organisateur événement", "entreprise"],
        location="Lyon, France",
        your_title="Fleuriste événementiel",
        your_offer="Décoration florale sur mesure pour vos événements et cérémonies",
        email_hook=(
            "Je suis fleuriste spécialisé dans la décoration événementielle. "
            "En consultant le site de {name}, j'ai pensé qu'une collaboration "
            "pourrait sublimer vos événements et apporter une vraie valeur ajoutée à vos clients."
        ),
        sms_hook="Fleuriste événementiel disponible pour vos mariages et événements. Collaboration possible ?",
        qualification_criteria=[
            "Établissement organisant des événements",
            "Hôtel ou salle de réception",
            "Absence de prestataire floral mentionné",
        ],
    ),

    Profile(
        id="photographe",
        emoji="📸",
        name="Photographe",
        description="Cible les restaurants, hôtels et agences immobilières pour des shootings professionnels.",
        keywords=["restaurant gastronomique", "hôtel", "agence immobilière", "boutique mode", "spa"],
        location="Paris, France",
        your_title="Photographe professionnel",
        your_offer="Shootings photo professionnels pour valoriser votre établissement",
        email_hook=(
            "En visitant le site de {name}, j'ai remarqué que vos visuels actuels "
            "ne reflètent peut-être pas encore la qualité de ce que vous proposez. "
            "Des photos professionnelles peuvent augmenter vos réservations de 30% en moyenne."
        ),
        sms_hook="Photographe pro disponible pour shooter votre établissement. Tarif découverte ce mois-ci.",
        qualification_criteria=[
            "Visuels de faible qualité sur le site",
            "Absence de galerie photo",
            "Secteur visuel (resto, hôtel, immo)",
        ],
    ),

    Profile(
        id="coach_sportif",
        emoji="🏋️",
        name="Coach Sportif",
        description="Cible les entreprises et RH pour proposer des sessions bien-être au travail.",
        keywords=["entreprise", "cabinet RH", "coworking", "startup", "PME", "cabinet médical"],
        location="Lyon, France",
        your_title="Coach Sportif & Bien-être en entreprise",
        your_offer="Sessions sport et bien-être en entreprise pour booster la productivité de vos équipes",
        email_hook=(
            "Le bien-être au travail est devenu un levier majeur de performance et de rétention des talents. "
            "Je propose à {name} des sessions de sport et de relaxation adaptées à vos équipes, "
            "directement sur votre lieu de travail."
        ),
        sms_hook="Coach sportif pro. Sessions bien-être en entreprise. Vos équipes méritent ça. On en parle ?",
        qualification_criteria=[
            "Entreprise avec salariés",
            "Pas de programme bien-être mentionné",
            "Secteur tertiaire ou bureau",
        ],
    ),

    Profile(
        id="social_media",
        emoji="📱",
        name="Social Media Manager",
        description="Cible les PME et commerces avec une faible présence sur les réseaux sociaux.",
        keywords=["restaurant", "boutique", "salon de coiffure", "agence", "cabinet"],
        location="Paris, France",
        your_title="Social Media Manager Freelance",
        your_offer="Gestion de vos réseaux sociaux pour attirer plus de clients en ligne",
        email_hook=(
            "J'ai regardé la présence de {name} sur les réseaux sociaux "
            "et j'ai constaté qu'il y a une vraie opportunité à saisir. "
            "Vos concurrents locaux gagnent des clients chaque jour grâce à Instagram et Facebook — "
            "je peux vous aider à faire pareil."
        ),
        sms_hook="Votre présence sur les réseaux peut être boostée facilement. Je m'en occupe pour vous ?",
        qualification_criteria=[
            "Absence de liens réseaux sociaux",
            "Compte inactif ou inexistant",
            "Secteur grand public (B2C)",
        ],
        check_weight_overrides={"social_links": 15},  # critère principal pour ce profil
    ),

    Profile(
        id="nettoyage",
        emoji="🧹",
        name="Service de Nettoyage",
        description="Cible les bureaux, restaurants et hôtels pour des contrats de nettoyage régulier.",
        keywords=["bureau", "restaurant", "hôtel", "clinique", "cabinet médical", "coworking"],
        location="Lyon, France",
        your_title="Service de nettoyage professionnel",
        your_offer="Nettoyage professionnel de vos locaux, disponible 7j/7",
        email_hook=(
            "Je propose aux établissements comme {name} un service de nettoyage professionnel "
            "fiable et flexible. Intervention en dehors de vos heures d'ouverture, "
            "produits certifiés, tarifs compétitifs."
        ),
        sms_hook="Service nettoyage pro pour vos locaux. Disponible 7j/7. Devis gratuit en 24h.",
        qualification_criteria=[
            "Local commercial ou professionnel",
            "Restaurant ou hôtel",
            "Bureau ou cabinet",
        ],
    ),

    Profile(
        id="consultant_marketing",
        emoji="🎯",
        name="Consultant Marketing",
        description="Cible les PME et commerces pour un audit et une stratégie marketing.",
        keywords=["PME", "agence", "commerce", "artisan", "cabinet conseil"],
        location="Paris, France",
        your_title="Consultant Marketing Digital",
        your_offer="Audit et stratégie marketing pour accélérer votre croissance",
        email_hook=(
            "En analysant la stratégie digitale de {name}, j'ai identifié plusieurs leviers "
            "inexploités qui pourraient significativement augmenter votre chiffre d'affaires. "
            "Un audit rapide suffit pour savoir où concentrer vos efforts."
        ),
        sms_hook="Audit marketing offert pour votre entreprise. Je vous dis exactement quoi améliorer en 30 min.",
        qualification_criteria=[
            "Absence de stratégie digitale visible",
            "Pas de blog ou contenu",
            "Faible présence publicitaire",
        ],
    ),

    Profile(
        id="chercheur_emploi",
        emoji="🔍",
        name="Chercheur d'emploi",
        description="Cible les entreprises susceptibles de recruter pour une candidature spontanée percutante.",
        keywords=["agence web", "startup", "cabinet conseil", "agence communication", "ESN"],
        location="Paris, France",
        your_title="Candidat motivé",
        your_offer="Candidature spontanée — profil junior polyvalent et motivé",
        email_hook=(
            "Je me permets de vous contacter car le projet de {name} m'a particulièrement intéressé. "
            "Convaincu que je pourrais apporter une vraie valeur à votre équipe, "
            "je vous adresse ma candidature spontanée."
        ),
        sms_hook="Candidature spontanée pour rejoindre votre équipe. Mon profil pourrait vous intéresser ?",
        qualification_criteria=[
            "Entreprise en croissance",
            "Secteur en lien avec mon profil",
            "Offres d'emploi publiées récemment",
        ],
    ),

    Profile(
        id="custom",
        emoji="⚙️",
        name="Profil Custom",
        description="Configurez entièrement votre propre profil de prospection.",
        keywords=[""],
        location="",
        your_title="",
        your_offer="",
        email_hook="En analysant {name}, j'ai pensé que ma proposition pourrait vous intéresser.",
        sms_hook="Bonjour, j'ai une proposition qui pourrait vous intéresser. On en parle ?",
        qualification_criteria=[],
    ),
]


def get_profile(profile_id: str) -> Profile | None:
    return next((p for p in PROFILES if p.id == profile_id), None)


def list_profiles() -> List[Profile]:
    return PROFILES
