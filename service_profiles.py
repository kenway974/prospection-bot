"""
Profils de service — ce que VOUS proposez (le prestataire).
Séparé des cibles (target_segments.py) pour permettre 2 sélecteurs indépendants dans l'UI.
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


SERVICE_CATEGORY_LABELS: Dict[str, str] = {
    "web_digital":    "🌐 Web & Digital",
    "creatif":        "🎨 Créatif & Visuel",
    "conseil_b2b":    "💼 Conseil & B2B",
    "sante":          "🏥 Santé & Bien-être",
    "terrain":        "🔧 Services Terrain",
    "special":        "⭐ Spéciaux",
}


SERVICE_PROFILES: List[ServiceProfile] = [

    # -----------------------------------------------------------------------
    # Web & Digital
    # -----------------------------------------------------------------------

    ServiceProfile(
        id="web_refonte",
        emoji="💻",
        name="Refonte / Création web",
        category="web_digital",
        description="Création et refonte de sites web professionnels pour TPE, artisans et PME.",
        your_title="Développeur Web",
        your_offer="Création et refonte de sites web professionnels pour TPE et artisans",
        email_hook=(
            "En cherchant {name} sur Google, j'ai analysé votre présence en ligne "
            "et identifié plusieurs points qui freinent votre visibilité et vos conversions."
        ),
        sms_hook="J'ai analysé votre site et trouvé des axes d'amélioration. Dispo pour un retour gratuit ?",
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="seo",
        emoji="📈",
        name="Référencement SEO",
        category="web_digital",
        description="Audit SEO et plan d'action pour remonter dans Google — balises, contenu, indexation.",
        your_title="Consultant SEO",
        your_offer="Audit SEO gratuit + plan d'action priorisé pour remonter dans Google",
        email_hook=(
            "En cherchant {name} sur Google, j'ai constaté que votre site n'apparaît pas "
            "dans les premières positions sur vos mots-clés locaux. "
            "Un audit rapide m'a permis d'identifier plusieurs points bloquants pour votre référencement."
        ),
        sms_hook="Votre site n'apparaît pas dans le top Google local. Audit SEO offert — 15 min suffisent.",
        check_weight_overrides={
            "title": 15,
            "meta_description": 15,
            "https": 15,
            "tracking": 15,
            "response_time": 5,
            "lead_form": 5,
            "social_links": 0,
        },
        score_threshold_default=70,
    ),

    ServiceProfile(
        id="ads",
        emoji="📣",
        name="Google / Meta Ads",
        category="web_digital",
        description="Campagnes publicitaires rentables pour commerces sans pixel de tracking en place.",
        your_title="Expert Google Ads & Meta Ads",
        your_offer="Campagnes publicitaires rentables avec ROI mesurable dès le 1er mois",
        email_hook=(
            "En analysant le site de {name}, j'ai constaté qu'aucun pixel de tracking n'est installé. "
            "Cela signifie que vous ne pouvez pas diffuser de publicité ciblée ni mesurer vos conversions. "
            "Vos concurrents vous prennent des clients chaque jour grâce à Google Ads et Meta Ads."
        ),
        sms_hook="Pas de tracking sur votre site = vous perdez des clients face à vos concurrents. On corrige ça ?",
        check_weight_overrides={
            "tracking": 30,
            "lead_form": 20,
            "https": 5,
            "viewport": 5,
            "title": 0,
            "meta_description": 0,
            "free_builder": 0,
            "social_links": 0,
            "outdated": 0,
            "response_time": 0,
        },
        score_threshold_default=60,
    ),

    ServiceProfile(
        id="ecommerce",
        emoji="🛒",
        name="E-commerce",
        category="web_digital",
        description="Boutique en ligne clé en main pour artisans et commerces physiques sans vente en ligne.",
        your_title="Développeur E-commerce",
        your_offer="Boutique en ligne clé en main pour vendre 24h/24 sans effort supplémentaire",
        email_hook=(
            "En visitant le site de {name}, j'ai constaté que vous n'avez pas encore de boutique en ligne. "
            "Avec une solution e-commerce bien pensée, vous pourriez vendre vos produits à des clients "
            "qui ne peuvent pas se déplacer — et augmenter votre chiffre d'affaires sans coût fixe supplémentaire."
        ),
        sms_hook="Vendre vos produits en ligne peut doubler votre CA. Je crée des boutiques clé en main. Dispo ?",
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
        score_threshold_default=70,
    ),

    ServiceProfile(
        id="social_media",
        emoji="📱",
        name="Social Media Management",
        category="web_digital",
        description="Gestion des réseaux sociaux pour TPE et commerces avec faible présence en ligne.",
        your_title="Social Media Manager",
        your_offer="Gestion de vos réseaux sociaux pour attirer plus de clients en ligne",
        email_hook=(
            "J'ai regardé la présence de {name} sur les réseaux sociaux "
            "et j'ai constaté qu'il y a une vraie opportunité à saisir. "
            "Vos concurrents locaux gagnent des clients chaque jour grâce à Instagram et Facebook — "
            "je peux vous aider à faire pareil."
        ),
        sms_hook="Votre présence sur les réseaux peut être boostée facilement. Je m'en occupe pour vous ?",
        check_weight_overrides={"social_links": 15},
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="copywriting",
        emoji="✍️",
        name="Rédaction / Copywriting",
        category="web_digital",
        description="Rédaction de pages web, articles SEO et emails de vente qui convertissent.",
        your_title="Rédacteur Web & Copywriter",
        your_offer="Rédaction de pages web, articles SEO et emails de vente qui convertissent",
        email_hook=(
            "En parcourant le site de {name}, j'ai remarqué que le contenu de certaines pages "
            "pourrait être renforcé pour mieux convaincre vos visiteurs et améliorer votre référencement. "
            "Un bon texte peut doubler le taux de conversion d'une page."
        ),
        sms_hook="Vos pages web pourraient convertir bien mieux avec des textes optimisés. On en parle ?",
        check_weight_overrides={
            "title": 15,
            "meta_description": 15,
            "tracking": 5,
            "lead_form": 10,
            "social_links": 5,
            "free_builder": 5,
        },
        score_threshold_default=65,
    ),

    ServiceProfile(
        id="automatisation",
        emoji="⚡",
        name="Automatisation & Outils",
        category="web_digital",
        description="Automatisation des processus métier pour agences, coachs et consultants.",
        your_title="Intégrateur Notion & Automatisation (Make, Zapier)",
        your_offer="Automatisation de vos processus métier pour gagner 5h par semaine",
        email_hook=(
            "En consultant le site de {name}, j'ai pensé que votre activité pourrait bénéficier "
            "d'une meilleure organisation digitale. "
            "Beaucoup d'agences et de consultants perdent des heures chaque semaine sur des tâches "
            "répétitives que l'on peut automatiser facilement avec Notion, Make ou Zapier."
        ),
        sms_hook="Vous perdez du temps sur des tâches répétitives ? Je les automatise en 1 semaine. On en parle ?",
        score_threshold_default=100,
    ),

    # -----------------------------------------------------------------------
    # Créatif & Visuel
    # -----------------------------------------------------------------------

    ServiceProfile(
        id="graphisme",
        emoji="🎨",
        name="Graphisme & Identité visuelle",
        category="creatif",
        description="Identité visuelle professionnelle : logo, charte graphique, supports print et web.",
        your_title="Graphiste & Designer",
        your_offer="Identité visuelle professionnelle : logo, charte graphique, supports print et web",
        email_hook=(
            "En visitant le site de {name}, j'ai remarqué que votre identité visuelle actuelle "
            "ne reflète pas forcément la qualité de ce que vous proposez. "
            "Un logo professionnel et une charte graphique cohérente augmentent la confiance de vos clients "
            "avant même qu'ils franchissent votre porte."
        ),
        sms_hook="Votre identité visuelle mérite d'être à la hauteur de votre activité. Logo pro — intéressé(e) ?",
        check_weight_overrides={
            "free_builder": 25,
            "outdated": 20,
            "viewport": 5,
            "tracking": 0,
            "lead_form": 5,
            "social_links": 5,
        },
        score_threshold_default=65,
    ),

    ServiceProfile(
        id="photo",
        emoji="📸",
        name="Photographie professionnelle",
        category="creatif",
        description="Shootings photo professionnels pour valoriser restaurants, hôtels et agences immobilières.",
        your_title="Photographe professionnel",
        your_offer="Shootings photo professionnels pour valoriser votre établissement",
        email_hook=(
            "En visitant le site de {name}, j'ai remarqué que vos visuels actuels "
            "ne reflètent peut-être pas encore la qualité de ce que vous proposez. "
            "Des photos professionnelles peuvent augmenter vos réservations de 30% en moyenne."
        ),
        sms_hook="Photographe pro disponible pour shooter votre établissement. Tarif découverte ce mois-ci.",
        check_weight_overrides={
            "outdated": 15,
            "social_links": 10,
        },
        score_threshold_default=75,
    ),

    ServiceProfile(
        id="video",
        emoji="🎬",
        name="Vidéo & Motion Design",
        category="creatif",
        description="Vidéos de présentation et spots publicitaires qui valorisent votre établissement.",
        your_title="Vidéaste & Motion Designer",
        your_offer="Vidéos de présentation et spots publicitaires qui valorisent votre établissement",
        email_hook=(
            "En visitant le site de {name}, j'ai constaté l'absence de vidéo de présentation. "
            "Les pages avec une vidéo convertissent en moyenne 80 % mieux que les pages sans. "
            "Un court film de 60 secondes suffit pour faire la différence face à vos concurrents."
        ),
        sms_hook="Une vidéo de 60 sec sur votre site peut doubler vos demandes. Je filme ce mois-ci dans votre secteur.",
        check_weight_overrides={
            "outdated": 15,
            "social_links": 10,
        },
        score_threshold_default=75,
    ),

    ServiceProfile(
        id="podcasting",
        emoji="🎙️",
        name="Podcast & Production audio",
        category="creatif",
        description="Lancement et production de podcast clé en main pour coachs, consultants et thérapeutes.",
        your_title="Producteur de Podcast",
        your_offer="Lancement et production de votre podcast clé en main — de l'idée au premier épisode",
        email_hook=(
            "En regardant la stratégie de contenu de {name}, j'ai pensé qu'un podcast pourrait "
            "considérablement renforcer votre autorité dans votre domaine. "
            "Les professionnels qui publient du contenu audio régulier convertissent 3× plus de prospects "
            "en clients que ceux qui n'en publient pas."
        ),
        sms_hook="Un podcast vous poserait en expert et vous amènerait des clients. Je lance ça pour vous en 2 semaines.",
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="illustration",
        emoji="🖼️",
        name="Illustration",
        category="creatif",
        description="Illustrations originales sur mesure pour projets éditoriaux, web et marketing.",
        your_title="Illustrateur & Artiste BD",
        your_offer="Illustrations originales sur mesure pour vos projets éditoriaux, web et marketing",
        email_hook=(
            "En visitant le site de {name}, j'ai remarqué que vos visuels actuels reposent principalement "
            "sur des photos ou des illustrations stock. "
            "Des illustrations originales apportent une identité unique qui vous distingue immédiatement "
            "de vos concurrents et renforce la mémorisation de votre marque."
        ),
        sms_hook="Des illustrations originales pour démarquer votre marque. Dispo pour un brief cette semaine ?",
        score_threshold_default=100,
    ),

    # -----------------------------------------------------------------------
    # Conseil & B2B
    # -----------------------------------------------------------------------

    ServiceProfile(
        id="conseil_marketing",
        emoji="🎯",
        name="Conseil Marketing",
        category="conseil_b2b",
        description="Audit et stratégie marketing pour accélérer la croissance des PME et commerces.",
        your_title="Consultant Marketing Digital",
        your_offer="Audit et stratégie marketing pour accélérer votre croissance",
        email_hook=(
            "En analysant la stratégie digitale de {name}, j'ai identifié plusieurs leviers "
            "inexploités qui pourraient significativement augmenter votre chiffre d'affaires. "
            "Un audit rapide suffit pour savoir où concentrer vos efforts."
        ),
        sms_hook="Audit marketing offert pour votre entreprise. Je vous dis exactement quoi améliorer en 30 min.",
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="conseil_rh",
        emoji="👥",
        name="Conseil RH",
        category="conseil_b2b",
        description="Recrutement, onboarding et structuration RH pour les entreprises en croissance.",
        your_title="Consultant RH",
        your_offer="Recrutement, onboarding et structuration RH pour les entreprises en croissance",
        email_hook=(
            "J'ai regardé l'activité de {name} et j'ai noté que votre croissance "
            "génère probablement des besoins RH importants. "
            "Recrutement, intégration, organisation des équipes — je structure tout ça "
            "pour que vous puissiez vous concentrer sur votre cœur de métier."
        ),
        sms_hook="Recrutement ou structuration RH pour votre équipe en croissance. Échange 20 min cette semaine ?",
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="formation",
        emoji="📚",
        name="Formation professionnelle",
        category="conseil_b2b",
        description="Formations sur mesure en présentiel ou en ligne pour monter en compétences vos équipes.",
        your_title="Formateur & Concepteur E-learning",
        your_offer="Formations sur mesure en présentiel ou en ligne pour monter en compétences vos équipes",
        email_hook=(
            "Je propose aux équipes de {name} des formations courtes et opérationnelles "
            "adaptées à vos enjeux métier. "
            "Une journée de formation bien ciblée peut générer un retour sur investissement "
            "immédiat sur la productivité et la qualité de travail de vos collaborateurs."
        ),
        sms_hook="Formations courtes et opérationnelles pour vos équipes. Devis gratuit en 24h. Dispo ?",
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="juridique",
        emoji="⚖️",
        name="Juridique & RGPD",
        category="conseil_b2b",
        description="Contrats, CGV, mentions légales et conformité RGPD pour entreprises digitales.",
        your_title="Juriste — Droit des affaires & RGPD",
        your_offer="Contrats, CGV, mentions légales et conformité RGPD pour entreprises digitales",
        email_hook=(
            "En consultant le site de {name}, j'ai constaté que certaines mentions légales "
            "obligatoires semblent incomplètes ou absentes. "
            "En cas de litige ou de contrôle CNIL, cela expose votre entreprise à des amendes "
            "pouvant aller jusqu'à 20 000 €. Je peux régulariser tout ça rapidement."
        ),
        sms_hook="Votre site est-il conforme RGPD et CGV ? Je vérifie gratuitement en 10 min.",
        check_weight_overrides={
            "lead_form": 20,
            "tracking": 15,
            "https": 15,
            "title": 0,
            "meta_description": 0,
            "social_links": 0,
            "free_builder": 5,
            "outdated": 5,
        },
        score_threshold_default=70,
    ),

    ServiceProfile(
        id="comptabilite",
        emoji="💰",
        name="Comptabilité & Fiscalité",
        category="conseil_b2b",
        description="Comptabilité, déclarations fiscales et conseil pour indépendants et TPE.",
        your_title="Expert-comptable & Conseiller Fiscal",
        your_offer="Comptabilité, déclarations fiscales et conseil pour indépendants et TPE",
        email_hook=(
            "En tant qu'indépendant ou gérant de {name}, la gestion comptable et fiscale "
            "prend souvent du temps que vous n'avez pas. "
            "Je m'occupe de tout — déclarations, bilans, optimisation fiscale — "
            "pour que vous puissiez vous concentrer sur votre activité."
        ),
        sms_hook="Comptabilité et déclarations gérées pour vous. Tarif adapté aux indépendants. On en parle ?",
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="assistance_virtuelle",
        emoji="📋",
        name="Assistance virtuelle",
        category="conseil_b2b",
        description="Gestion administrative, agenda et email pour libérer le temps des professionnels indépendants.",
        your_title="Assistante Virtuelle",
        your_offer="Gestion administrative, agenda et email pour libérer votre temps sur votre cœur de métier",
        email_hook=(
            "En tant que professionnel indépendant, {name} gère probablement seul(e) "
            "une part importante de ses tâches administratives. "
            "Gestion d'agenda, réponse aux emails, relances clients, saisie de documents — "
            "je prends en charge tout ça à distance pour que vous puissiez vous concentrer sur l'essentiel."
        ),
        sms_hook="Déléguez vos tâches admin à distance. Gestion d'agenda, emails, relances. Dispo pour en parler ?",
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="traduction",
        emoji="🌍",
        name="Traduction",
        category="conseil_b2b",
        description="Traduction professionnelle de documents juridiques, marketing et sites web.",
        your_title="Traducteur Assermenté — FR/EN/ES",
        your_offer="Traduction professionnelle de documents juridiques, marketing et sites web",
        email_hook=(
            "En consultant le site de {name}, j'ai remarqué qu'il est uniquement disponible en français. "
            "Si une partie de votre clientèle est internationale, "
            "l'absence de version traduite vous fait manquer des opportunités concrètes. "
            "Je traduis sites web, contrats et documents officiels avec précision et rapidité."
        ),
        sms_hook="Votre site en anglais ou espagnol peut ouvrir de nouveaux marchés. Devis sous 24h.",
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="consultant_rse",
        emoji="🌱",
        name="RSE & Développement durable",
        category="conseil_b2b",
        description="Diagnostic RSE, bilan carbone et plan d'action développement durable pour PME.",
        your_title="Consultant RSE & Développement Durable",
        your_offer="Diagnostic RSE, bilan carbone et plan d'action développement durable pour PME",
        email_hook=(
            "En analysant la présence en ligne de {name}, je n'ai pas trouvé de page dédiée "
            "à votre démarche RSE ou développement durable. "
            "Au-delà de l'obligation légale pour certaines structures, une stratégie RSE visible "
            "améliore votre image auprès de vos clients et facilite vos appels d'offres publics."
        ),
        sms_hook="Bilan RSE et plan développement durable pour votre entreprise. Diagnostic gratuit. Intéressé(e) ?",
        score_threshold_default=100,
    ),

    # -----------------------------------------------------------------------
    # Santé & Bien-être
    # -----------------------------------------------------------------------

    ServiceProfile(
        id="coaching_sportif",
        emoji="🏋️",
        name="Coaching sportif & bien-être",
        category="sante",
        description="Sessions sport et bien-être en entreprise pour booster la productivité des équipes.",
        your_title="Coach Sportif & Bien-être en entreprise",
        your_offer="Sessions sport et bien-être en entreprise pour booster la productivité de vos équipes",
        email_hook=(
            "Le bien-être au travail est devenu un levier majeur de performance et de rétention des talents. "
            "Je propose à {name} des sessions de sport et de relaxation adaptées à vos équipes, "
            "directement sur votre lieu de travail."
        ),
        sms_hook="Coach sportif pro. Sessions bien-être en entreprise. Vos équipes méritent ça. On en parle ?",
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="nutrition",
        emoji="🥗",
        name="Nutrition & Diététique",
        category="sante",
        description="Suivi nutritionnel personnalisé pour adhérents de salles de sport et collaborateurs d'entreprise.",
        your_title="Nutritionniste & Diététicien",
        your_offer="Suivi nutritionnel personnalisé pour vos adhérents et collaborateurs",
        email_hook=(
            "En consultant le site de {name}, je n'ai pas trouvé de service de suivi nutritionnel "
            "pour vos adhérents ou collaborateurs. "
            "La nutrition est le complément indispensable à l'activité physique — "
            "une collaboration nous permettrait d'offrir un accompagnement vraiment complet à vos clients."
        ),
        sms_hook="Partenariat nutrition pour vos adhérents ? Je propose des consultations sur place. On en parle ?",
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="osteopathie",
        emoji="💆",
        name="Ostéopathie / Kinésithérapie",
        category="sante",
        description="Suivi ostéopathique et kinésithérapeutique pour sportifs et équipes sédentaires.",
        your_title="Ostéopathe / Kinésithérapeute",
        your_offer="Suivi ostéopathique et kinésithérapeutique pour vos sportifs et équipes",
        email_hook=(
            "Je travaille avec des structures sportives comme {name} pour proposer "
            "un suivi ostéopathique à leurs adhérents et sportifs. "
            "La prévention des blessures et la récupération font partie intégrante de la performance — "
            "une collaboration pourrait apporter une vraie valeur ajoutée à votre offre."
        ),
        sms_hook="Suivi ostéopathique pour vos sportifs. Séances sur place possibles. Partenariat ?",
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="psychologie_travail",
        emoji="🧠",
        name="Psychologie du travail",
        category="sante",
        description="Accompagnement psychologique en entreprise — prévention burnout et amélioration QVT.",
        your_title="Psychologue du Travail",
        your_offer="Accompagnement psychologique en entreprise — prévention burnout et amélioration QVT",
        email_hook=(
            "Le bien-être mental au travail est aujourd'hui un enjeu majeur de performance pour {name}. "
            "Absentéisme, turnover, burnout — ces signaux coûtent en moyenne 14 000 € par salarié perdu. "
            "Je propose des interventions discrètes et efficaces pour prévenir ces situations et "
            "renforcer la cohésion de vos équipes."
        ),
        sms_hook="Programme bien-être mental pour vos équipes. Prévention burnout et QVT. Échange rapide ?",
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
        score_threshold_default=100,
    ),

    # -----------------------------------------------------------------------
    # Services Terrain
    # -----------------------------------------------------------------------

    ServiceProfile(
        id="nettoyage",
        emoji="🧹",
        name="Nettoyage professionnel",
        category="terrain",
        description="Nettoyage professionnel de locaux pour bureaux, restaurants et hôtels, 7j/7.",
        your_title="Service de nettoyage professionnel",
        your_offer="Nettoyage professionnel de vos locaux, disponible 7j/7",
        email_hook=(
            "Je propose aux établissements comme {name} un service de nettoyage professionnel "
            "fiable et flexible. Intervention en dehors de vos heures d'ouverture, "
            "produits certifiés, tarifs compétitifs."
        ),
        sms_hook="Service nettoyage pro pour vos locaux. Disponible 7j/7. Devis gratuit en 24h.",
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="securite_gardiennage",
        emoji="🛡️",
        name="Gardiennage & Sécurité",
        category="terrain",
        description="Gardiennage professionnel et surveillance de locaux et marchandises de valeur.",
        your_title="Responsable sécurité — Gardiennage & Surveillance",
        your_offer="Gardiennage professionnel et surveillance de vos locaux et marchandises de valeur",
        email_hook=(
            "Je propose aux établissements comme {name} des solutions de gardiennage "
            "adaptées aux commerces de valeur. "
            "Présence discrète mais visible, intervention rapide, agents certifiés — "
            "pour que vous et vos clients vous sentiez en sécurité."
        ),
        sms_hook="Gardiennage pour votre établissement. Agents certifiés, tarifs compétitifs. Devis gratuit ?",
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="traiteur",
        emoji="🍽️",
        name="Traiteur & Événementiel",
        category="terrain",
        description="Plateaux repas et buffets pour réunions, séminaires et événements d'entreprise.",
        your_title="Traiteur & Chef à domicile",
        your_offer="Plateaux repas et buffets pour vos réunions, séminaires et événements d'entreprise",
        email_hook=(
            "Je propose aux équipes de {name} des solutions de restauration sur mesure "
            "pour vos réunions et événements professionnels. "
            "Plateaux repas, buffets déjeuner ou cocktails dînatoires — "
            "je m'occupe de tout pour que votre événement soit mémorable."
        ),
        sms_hook="Plateaux repas et buffets pour vos réunions d'entreprise. Devis sous 2h. Disponible ?",
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="paysagisme",
        emoji="🌿",
        name="Paysagisme",
        category="terrain",
        description="Création et entretien d'espaces verts pour hôtels, restaurants et entreprises.",
        your_title="Paysagiste & Jardinier Paysagiste",
        your_offer="Création et entretien d'espaces verts pour établissements professionnels",
        email_hook=(
            "Les espaces verts de {name} sont souvent la première impression que donnent "
            "vos locaux à vos clients et visiteurs. "
            "Un jardin bien entretenu ou une terrasse fleurie valorise votre image "
            "et incite les clients à s'y attarder — je peux vous proposer un devis adapté à votre budget."
        ),
        sms_hook="Entretien de vos espaces verts professionnel et régulier. Devis gratuit sous 48h.",
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="architecture_interieure",
        emoji="🏠",
        name="Architecture d'intérieur",
        category="terrain",
        description="Conception et rénovation d'espaces commerciaux pour maximiser l'expérience client.",
        your_title="Architecte d'intérieur",
        your_offer="Conception et rénovation d'espaces commerciaux pour maximiser l'expérience client",
        email_hook=(
            "En visitant le site de {name}, j'ai remarqué que l'espace mérite peut-être "
            "une mise à jour pour mieux refléter vos valeurs et attirer davantage de clients. "
            "Un espace bien conçu augmente le panier moyen et la durée de visite — "
            "je serais ravi de vous présenter quelques idées sans engagement."
        ),
        sms_hook="Un réaménagement de votre espace peut booster vos ventes. Visite conseil offerte cette semaine.",
        check_weight_overrides={
            "outdated": 20,
            "free_builder": 15,
            "social_links": 10,
            "tracking": 0,
            "title": 0,
            "meta_description": 0,
        },
        score_threshold_default=70,
    ),

    ServiceProfile(
        id="impression_signaletique",
        emoji="🖨️",
        name="Impression & Signalétique",
        category="terrain",
        description="Flyers, kakémonos, enseignes et signalétique pour professionnels — délai 48h.",
        your_title="Imprimeur & Signalétique Professionnelle",
        your_offer="Flyers, kakémonos, enseignes et signalétique pour professionnels — délai 48h",
        email_hook=(
            "En regardant la présence de {name}, j'ai pensé que vos supports print "
            "pourraient être optimisés pour mieux attirer et informer vos clients. "
            "Flyers, menus, PLV, enseigne — je réalise tous vos supports en délai express "
            "avec un résultat professionnel garanti."
        ),
        sms_hook="Flyers, enseignes, PLV en 48h. Qualité pro, prix compétitifs. Devis gratuit ?",
        check_weight_overrides={
            "free_builder": 15,
            "outdated": 15,
            "social_links": 5,
            "tracking": 0,
            "title": 0,
            "meta_description": 0,
        },
        score_threshold_default=70,
    ),

    ServiceProfile(
        id="fleuriste",
        emoji="💐",
        name="Fleuriste événementiel",
        category="terrain",
        description="Décoration florale sur mesure pour événements et cérémonies.",
        your_title="Fleuriste événementiel",
        your_offer="Décoration florale sur mesure pour vos événements et cérémonies",
        email_hook=(
            "Je suis fleuriste spécialisé dans la décoration événementielle. "
            "En consultant le site de {name}, j'ai pensé qu'une collaboration "
            "pourrait sublimer vos événements et apporter une vraie valeur ajoutée à vos clients."
        ),
        sms_hook="Fleuriste événementiel disponible pour vos mariages et événements. Collaboration possible ?",
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="animation_enfants",
        emoji="🎪",
        name="Animation enfants",
        category="terrain",
        description="Animations et ateliers enfants pour établissements familiaux — magie, jeux, activités créatives.",
        your_title="Animateur & Organisateur d'événements enfants",
        your_offer="Animations et ateliers enfants pour vos événements — magie, jeux, activités créatives",
        email_hook=(
            "Je propose aux établissements comme {name} des animations enfants "
            "sur mesure pour vos événements familiaux. "
            "Un espace animation bien conçu augmente le panier moyen des familles de 40 % "
            "et les fidélise sur le long terme."
        ),
        sms_hook="Animations enfants pour votre établissement. Magie, ateliers, jeux. Devis gratuit sous 24h.",
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
        score_threshold_default=100,
    ),

    # -----------------------------------------------------------------------
    # Spéciaux
    # -----------------------------------------------------------------------

    ServiceProfile(
        id="coursier",
        emoji="🚚",
        name="Coursier express",
        category="special",
        description="Livraison sécurisée et discrète de documents et colis sensibles en moins de 2h.",
        your_title="Service de course express haut de gamme",
        your_offer="Livraison sécurisée et discrète de vos documents et colis sensibles en moins de 2h",
        email_hook=(
            "Je gère un service de course express spécialisé dans les envois sensibles et haut de gamme. "
            "Pour des professionnels comme {name}, la rapidité et la discrétion ne sont pas négociables — "
            "c'est exactement ce que nous proposons, sans les contraintes d'un prestataire généraliste."
        ),
        sms_hook="Course express discrète pour docs et colis sensibles. Intervention en 2h. Dispo pour en parler ?",
        check_weight_overrides={
            "https": 0, "response_time": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "tracking": 0, "lead_form": 0,
            "free_builder": 0, "social_links": 0, "outdated": 0,
            "delivery_covered": 15,
            "low_volume": 0,
        },
        score_direction="desc",
        score_threshold_default=70,
    ),

    ServiceProfile(
        id="cours_particuliers",
        emoji="📖",
        name="Cours particuliers",
        category="special",
        description="Cours particuliers à domicile ou en ligne pour élèves en difficulté ou souhaitant progresser.",
        your_title="Professeur particulier — Maths, Français, Anglais",
        your_offer="Cours particuliers à domicile ou en ligne, résultats garantis en 3 mois",
        email_hook=(
            "Je propose aux familles liées à {name} des cours particuliers personnalisés "
            "pour les élèves en difficulté ou souhaitant progresser rapidement. "
            "Mes élèves progressent en moyenne d'une demi-lettre de note par mois — "
            "une collaboration avec votre établissement bénéficierait directement à vos élèves."
        ),
        sms_hook="Cours particuliers pour élèves en difficulté. Partenariat établissement possible. On en discute ?",
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
        score_threshold_default=100,
    ),

    ServiceProfile(
        id="candidature_spontanee",
        emoji="🔍",
        name="Candidature spontanée",
        category="special",
        description="Candidature spontanée percutante pour entreprises susceptibles de recruter.",
        your_title="Candidat motivé",
        your_offer="Candidature spontanée — profil junior polyvalent et motivé",
        email_hook=(
            "Je me permets de vous contacter car le projet de {name} m'a particulièrement intéressé. "
            "Convaincu que je pourrais apporter une vraie valeur à votre équipe, "
            "je vous adresse ma candidature spontanée."
        ),
        sms_hook="Candidature spontanée pour rejoindre votre équipe. Mon profil pourrait vous intéresser ?",
        score_threshold_default=100,
    ),

]


def get_service(service_id: str) -> Optional[ServiceProfile]:
    return next((s for s in SERVICE_PROFILES if s.id == service_id), None)


def list_services() -> List[ServiceProfile]:
    return SERVICE_PROFILES
