"""
Profils de service — ce que VOUS proposez (le prestataire).
Séparé des cibles (target_segments.py) pour permettre 2 sélecteurs indépendants dans l'UI.

Catalogue recentré sur le métier de développeur web fullstack : uniquement des
prestations de BUILD (ce qu'on code et livre), pas de marketing pur ni de créatif.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class ServiceProfile:
    id: str
    emoji: str
    name: str
    category: str                          # pour grouper dans l'UI
    description: str
    your_title: str
    your_offer: str
    email_hook: str                        # doit contenir {name}
    sms_hook: str                          # max 160 chars
    check_weight_overrides: dict = field(default_factory=dict)
    score_direction: str = "asc"           # "asc" = site mauvais = bon prospect
    score_threshold_default: int = 100
    # Mots-clés : si ABSENTS du site prospect → opportunité (no_service_mention)
    detection_keywords: List[str] = field(default_factory=list)


SERVICE_CATEGORY_LABELS: Dict[str, str] = {
    "web_digital": "🌐 Développement Web",
}


SERVICE_PROFILES: List[ServiceProfile] = [

    # -----------------------------------------------------------------------
    # Développement Web — prestations de build d'un dev fullstack
    # -----------------------------------------------------------------------

    ServiceProfile(
        id="web_refonte",
        emoji="💻",
        name="Site vitrine (création / refonte)",
        category="web_digital",
        description="Création ou refonte de sites vitrines rapides, modernes et bien référencés.",
        your_title="Développeur Web Fullstack",
        your_offer="Création et refonte de sites web modernes, rapides et bien référencés",
        email_hook=(
            "En cherchant {name} sur Google, j'ai constaté que votre présence en ligne "
            "pourrait être largement améliorée — que ce soit pour créer votre premier site "
            "ou moderniser celui que vous avez déjà."
        ),
        sms_hook="Votre présence en ligne peut être boostée. Site à créer ou refaire ? Je m'en occupe.",
        score_threshold_default=85,
        detection_keywords=[],
    ),

    ServiceProfile(
        id="web_app",
        emoji="🧩",
        name="Application web sur mesure",
        category="web_digital",
        description="Espace client, tableau de bord, outil métier ou SaaS développé sur mesure.",
        your_title="Développeur Fullstack (applications web)",
        your_offer="Application web sur mesure : espace client, dashboard ou outil métier",
        email_hook=(
            "En regardant l'activité de {name}, je me suis dit qu'une application web sur mesure "
            "(espace client, tableau de bord, outil interne) pourrait vous faire gagner un temps "
            "précieux et fluidifier l'expérience de vos clients — au-delà d'un simple site vitrine."
        ),
        sms_hook="Espace client, dashboard, outil métier sur mesure ? Je développe l'appli qu'il vous faut. On en parle ?",
        score_threshold_default=90,
        detection_keywords=[],
    ),

    ServiceProfile(
        id="ecommerce",
        emoji="🛒",
        name="E-commerce / Boutique en ligne",
        category="web_digital",
        description="Boutique en ligne clé en main pour vendre 24h/24, avec paiement et gestion des commandes.",
        your_title="Développeur E-commerce",
        your_offer="Boutique en ligne clé en main pour vendre 24h/24 sans effort supplémentaire",
        email_hook=(
            "En visitant le site de {name}, j'ai constaté que vous n'avez pas encore de boutique en ligne. "
            "Avec une solution e-commerce bien pensée, vous pourriez vendre vos produits à des clients "
            "qui ne peuvent pas se déplacer — et augmenter votre chiffre d'affaires sans coût fixe supplémentaire."
        ),
        sms_hook="Vendre vos produits en ligne peut doubler votre CA. Je crée des boutiques clé en main. Dispo ?",
        detection_keywords=[],
        check_weight_overrides={
            "lead_form": 15,
            "tracking": 15,
            "https": 10,
            "viewport": 10,
            "title": 5,
            "meta_description": 5,
            "social_links": 5,
            "free_builder": 10,
            "outdated": 5,
        },
        score_threshold_default=85,
    ),

    ServiceProfile(
        id="api_integration",
        emoji="🔗",
        name="API & Intégrations",
        category="web_digital",
        description="Connexion de vos outils (CRM, paiement, résa, compta) via API et intégrations sur mesure.",
        your_title="Développeur Backend & Intégrations",
        your_offer="Connexion de vos outils métier via API : CRM, paiement, réservation, comptabilité",
        email_hook=(
            "En consultant {name}, j'ai pensé que vos différents outils (site, CRM, paiement, "
            "réservation, comptabilité) gagneraient à communiquer entre eux automatiquement. "
            "Une intégration bien faite supprime les doubles saisies et les erreurs — et vous fait "
            "gagner des heures chaque semaine."
        ),
        sms_hook="Vos outils ne communiquent pas entre eux ? Je les connecte via API. Fini les doubles saisies. On en parle ?",
        score_threshold_default=100,
        detection_keywords=[],
    ),

    ServiceProfile(
        id="automatisation",
        emoji="⚡",
        name="Automatisation & Outils internes",
        category="web_digital",
        description="Automatisation des tâches répétitives et outils internes (scripts, Make, Zapier, n8n).",
        your_title="Développeur & Intégrateur d'automatisations",
        your_offer="Automatisation de vos processus métier pour gagner plusieurs heures par semaine",
        email_hook=(
            "En consultant le site de {name}, j'ai pensé que votre activité pourrait bénéficier "
            "d'une meilleure organisation digitale. "
            "Beaucoup d'entreprises perdent des heures chaque semaine sur des tâches répétitives "
            "que l'on peut automatiser (scripts sur mesure, Make, Zapier, n8n)."
        ),
        sms_hook="Vous perdez du temps sur des tâches répétitives ? Je les automatise. On en parle ?",
        detection_keywords=[],
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="maintenance",
        emoji="🛠️",
        name="Maintenance & TMA",
        category="web_digital",
        description="Maintenance, mises à jour, sécurité et évolutions de sites et applications existants.",
        your_title="Développeur Web (maintenance & évolutions)",
        your_offer="Maintenance, sécurité et évolutions continues de votre site ou application",
        email_hook=(
            "En analysant le site de {name}, j'ai repéré quelques points techniques "
            "(sécurité, mises à jour, performance) qui mériteraient un suivi régulier. "
            "Un contrat de maintenance évite les mauvaises surprises et garde votre site rapide, "
            "sécurisé et à jour, sans que vous ayez à vous en occuper."
        ),
        sms_hook="Votre site mérite un suivi (sécurité, mises à jour, perf). Je m'en occupe en continu. Dispo pour en parler ?",
        score_threshold_default=85,
        detection_keywords=[],
    ),

]


def get_service(service_id: str) -> Optional[ServiceProfile]:
    return next((s for s in SERVICE_PROFILES if s.id == service_id), None)


def list_services() -> List[ServiceProfile]:
    return SERVICE_PROFILES
