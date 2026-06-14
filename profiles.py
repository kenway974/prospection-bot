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
    category: str = "autre"     # groupement UI
    target_size: str = "all"    # "tpe", "pme", "all"



PROFILES: List[Profile] = [

    Profile(
        id="web_tpe",
        emoji="💻",
        name="Refonte Web → TPE / Artisans",
        category="web_digital",
        target_size="tpe",
        description="Cible les commerces et TPE avec un site absent, vieillissant ou non optimisé.",
        keywords=["restaurant", "boulangerie", "coiffeur", "garage automobile", "cabinet dentaire"],
        location="Lyon, France",
        your_title="Développeur Web",
        your_offer="Création et refonte de sites web professionnels pour TPE et artisans",
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
        id="web_pme",
        emoji="🏢",
        name="Refonte Web → PME / Entreprises",
        category="web_digital",
        target_size="pme",
        description="Cible les PME, cabinets et hôtels avec un site lent, non mobile ou qui ne convertit pas.",
        keywords=["cabinet médical", "agence immobilière", "cabinet d'avocats", "clinique", "hôtel", "restaurant gastronomique", "cabinet comptable"],
        location="Paris, France",
        your_title="Développeur Web",
        your_offer="Refonte web orientée conversion et performance pour les structures de 10 à 250 salariés",
        email_hook=(
            "En analysant le site de {name}, j'ai identifié plusieurs points critiques "
            "qui freinent vos conversions et votre crédibilité en ligne : "
            "temps de chargement élevé, manque de formulaires de contact efficaces, "
            "et un design qui ne reflète plus votre niveau d'expertise. "
            "Un site bien conçu peut augmenter vos demandes entrantes de 30 à 60 %."
        ),
        sms_hook="Votre site freine vos conversions. J'ai identifié les points à corriger. Échange 15 min ?",
        qualification_criteria=[
            "Site lent ou non responsive",
            "Aucun formulaire de lead visible",
            "Absence de tracking / analytics",
            "Design daté pour une structure de cette taille",
        ],
        check_weight_overrides={
            "response_time": 20,
            "viewport": 20,
            "lead_form": 20,
            "tracking": 15,
            "https": 10,
            "title": 5,
            "meta_description": 5,
            "free_builder": 5,
            "social_links": 0,
            "outdated": 0,
        },
        score_threshold_default=55,
    ),

    Profile(
        id="seo_local",
        emoji="📈",
        name="SEO Local → Commerces & Artisans",
        category="web_digital",
        target_size="tpe",
        description="Cible les TPE et commerces mal positionnés sur Google — balises absentes, contenu pauvre, site non indexé.",
        keywords=["restaurant", "boulangerie", "pharmacie", "cabinet dentaire", "agence immobilière", "hôtel", "artisan"],
        location="Lyon, France",
        your_title="Consultant SEO",
        your_offer="Audit SEO gratuit + plan d'action priorisé pour remonter dans Google",
        email_hook=(
            "En cherchant {name} sur Google, j'ai constaté que votre site n'apparaît pas "
            "dans les premières positions sur vos mots-clés locaux. "
            "Un audit rapide m'a permis d'identifier plusieurs points bloquants pour votre référencement."
        ),
        sms_hook="Votre site n'apparaît pas dans le top Google local. Audit SEO offert — 15 min suffisent.",
        qualification_criteria=[
            "Balise title absente ou mal renseignée",
            "Meta description manquante",
            "Site non sécurisé (HTTP)",
            "Aucun outil de mesure d'audience",
        ],
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

    Profile(
        id="redacteur_web",
        emoji="✍️",
        name="Rédacteur Web / Copywriter",
        category="web_digital",
        target_size="all",
        description="Cible les agences, startups et e-commerces avec un contenu pauvre, des pages vides ou un blog inexistant.",
        keywords=["agence web", "startup", "e-commerce", "cabinet conseil", "coach", "consultant"],
        location="Paris, France",
        your_title="Rédacteur Web & Copywriter",
        your_offer="Rédaction de pages web, articles SEO et emails de vente qui convertissent",
        email_hook=(
            "En parcourant le site de {name}, j'ai remarqué que le contenu de certaines pages "
            "pourrait être renforcé pour mieux convaincre vos visiteurs et améliorer votre référencement. "
            "Un bon texte peut doubler le taux de conversion d'une page."
        ),
        sms_hook="Vos pages web pourraient convertir bien mieux avec des textes optimisés. On en parle ?",
        qualification_criteria=[
            "Balise title et meta description absentes ou génériques",
            "Pages avec peu de contenu texte",
            "Pas de blog ou section actualités",
            "CTA peu convaincants ou absents",
        ],
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

    Profile(
        id="ads_btoc",
        emoji="📣",
        name="Google/Meta Ads → B2C",
        category="web_digital",
        target_size="all",
        description="Cible les commerces et professions libérales qui n'utilisent aucun pixel de tracking — zéro pub en place.",
        keywords=["restaurant", "clinique esthétique", "cabinet dentaire", "agence immobilière", "salle de sport", "boutique"],
        location="Paris, France",
        your_title="Expert Google Ads & Meta Ads",
        your_offer="Campagnes publicitaires rentables avec ROI mesurable dès le 1er mois",
        email_hook=(
            "En analysant le site de {name}, j'ai constaté qu'aucun pixel de tracking n'est installé. "
            "Cela signifie que vous ne pouvez pas diffuser de publicité ciblée ni mesurer vos conversions. "
            "Vos concurrents vous prennent des clients chaque jour grâce à Google Ads et Meta Ads."
        ),
        sms_hook="Pas de tracking sur votre site = vous perdez des clients face à vos concurrents sur Google. On corrige ça ?",
        qualification_criteria=[
            "Aucun pixel de tracking (Google, Facebook)",
            "Pas de formulaire de lead visible",
            "Secteur avec forte concurrence locale",
        ],
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

    Profile(
        id="ecommerce",
        emoji="🛒",
        name="E-commerce → Artisans & Commerces",
        category="web_digital",
        target_size="tpe",
        description="Cible les artisans et commerces physiques qui vendent uniquement en boutique, sans solution de vente en ligne.",
        keywords=["artisan", "fromagerie", "confiserie", "bijouterie", "librairie", "producteur local", "cave à vins", "épicerie fine"],
        location="Lyon, France",
        your_title="Développeur E-commerce",
        your_offer="Boutique en ligne clé en main pour vendre 24h/24 sans effort supplémentaire",
        email_hook=(
            "En visitant le site de {name}, j'ai constaté que vous n'avez pas encore de boutique en ligne. "
            "Avec une solution e-commerce bien pensée, vous pourriez vendre vos produits à des clients "
            "qui ne peuvent pas se déplacer — et augmenter votre chiffre d'affaires sans coût fixe supplémentaire."
        ),
        sms_hook="Vendre vos produits en ligne peut doubler votre CA. Je crée des boutiques clé en main. Dispo cette semaine ?",
        qualification_criteria=[
            "Site vitrine sans fonctionnalité e-commerce",
            "Artisan ou commerce de proximité",
            "Produits à fort potentiel de vente en ligne",
        ],
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

    Profile(
        id="social_media",
        emoji="📱",
        name="Social Media Manager",
        category="web_digital",
        target_size="tpe",
        description="Cible les TPE et commerces avec une faible présence sur les réseaux sociaux.",
        keywords=["restaurant", "boutique", "salon de coiffure", "agence", "cabinet"],
        location="Paris, France",
        your_title="Social Media Manager",
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
        id="automatisation",
        emoji="⚡",
        name="Automatisation & Outils → Agences",
        category="web_digital",
        target_size="pme",
        description="Cible les agences, coachs et consultants pour digitaliser et automatiser leurs processus internes.",
        keywords=["agence web", "cabinet conseil", "coach", "consultant", "agence communication", "startup", "freelance"],
        location="Paris, France",
        your_title="Intégrateur Notion & Automatisation (Make, Zapier)",
        your_offer="Automatisation de vos processus métier pour gagner 5h par semaine",
        email_hook=(
            "En consultant le site de {name}, j'ai pensé que votre activité pourrait bénéficier "
            "d'une meilleure organisation digitale. "
            "Beaucoup d'agences et de consultants perdent des heures chaque semaine sur des tâches "
            "répétitives que l'on peut automatiser facilement avec Notion, Make ou Zapier."
        ),
        sms_hook="Vous perdez du temps sur des tâches répétitives ? Je les automatise en 1 semaine. On en parle ?",
        qualification_criteria=[
            "Agence ou consultant avec processus manuels",
            "Pas d'outil de gestion interne visible",
            "Site sans espace client ou portail",
        ],
    ),

    # -----------------------------------------------------------------------
    # Profils Créatif & Visuel
    # -----------------------------------------------------------------------

    Profile(
        id="graphiste",
        emoji="🎨",
        name="Graphiste / Designer",
        category="creatif",
        target_size="tpe",
        description="Cible les commerces et TPE avec une identité visuelle faible, un logo daté ou un site construit avec un outil gratuit.",
        keywords=["restaurant", "boutique", "coiffeur", "salon de beauté", "artisan", "boulangerie", "commerce"],
        location="Lyon, France",
        your_title="Graphiste & Designer",
        your_offer="Identité visuelle professionnelle : logo, charte graphique, supports print et web",
        email_hook=(
            "En visitant le site de {name}, j'ai remarqué que votre identité visuelle actuelle "
            "ne reflète pas forcément la qualité de ce que vous proposez. "
            "Un logo professionnel et une charte graphique cohérente augmentent la confiance de vos clients "
            "avant même qu'ils franchissent votre porte."
        ),
        sms_hook="Votre identité visuelle mérite d'être à la hauteur de votre activité. Je crée des logos pro. Intéressé(e) ?",
        qualification_criteria=[
            "Site construit avec un outil gratuit (Wix, Jimdo…)",
            "Site visuellement daté",
            "Absence de charte graphique cohérente",
        ],
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

    Profile(
        id="photographe",
        emoji="📸",
        name="Photographe",
        category="creatif",
        target_size="all",
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
        id="videaste",
        emoji="🎬",
        name="Vidéaste / Motion Designer",
        category="creatif",
        target_size="all",
        description="Cible les restaurants, hôtels et agences immo pour des vidéos de présentation qui convertissent.",
        keywords=["restaurant gastronomique", "hôtel", "agence immobilière", "salle de mariage", "startup", "spa", "cabinet médical"],
        location="Paris, France",
        your_title="Vidéaste & Motion Designer",
        your_offer="Vidéos de présentation et spots publicitaires qui valorisent votre établissement",
        email_hook=(
            "En visitant le site de {name}, j'ai constaté l'absence de vidéo de présentation. "
            "Les pages avec une vidéo convertissent en moyenne 80 % mieux que les pages sans. "
            "Un court film de 60 secondes suffit pour faire la différence face à vos concurrents."
        ),
        sms_hook="Une vidéo de 60 sec sur votre site peut doubler vos demandes. Je filme ce mois-ci dans votre secteur.",
        qualification_criteria=[
            "Aucune vidéo de présentation sur le site",
            "Secteur où le visuel fait vendre (resto, hôtel, immo)",
            "Photos de qualité moyenne ou absentes",
        ],
        check_weight_overrides={
            "outdated": 15,
            "social_links": 10,
            "free_builder": 10,
            "tracking": 5,
            "title": 0,
            "meta_description": 0,
        },
        score_threshold_default=75,
    ),

    Profile(
        id="podcaster",
        emoji="🎙️",
        name="Podcaster / Production Audio",
        category="creatif",
        target_size="all",
        description="Cible les coachs, consultants et thérapeutes pour lancer un podcast comme outil d'autorité et de prospection.",
        keywords=["coach", "consultant", "thérapeute", "formateur", "cabinet conseil", "psychologue", "nutritionniste"],
        location="Paris, France",
        your_title="Producteur de Podcast",
        your_offer="Lancement et production de votre podcast clé en main — de l'idée au premier épisode",
        email_hook=(
            "En regardant la stratégie de contenu de {name}, j'ai pensé qu'un podcast pourrait "
            "considérablement renforcer votre autorité dans votre domaine. "
            "Les professionnels qui publient du contenu audio régulier convertissent 3× plus de prospects "
            "en clients que ceux qui n'en publient pas."
        ),
        sms_hook="Un podcast vous poserait en expert et vous amènerait des clients. Je lance ça pour vous en 2 semaines.",
        qualification_criteria=[
            "Professionnel expert dans son domaine",
            "Pas de contenu audio ou podcast",
            "Présence digitale à renforcer",
        ],
    ),

    Profile(
        id="illustrateur",
        emoji="🖼️",
        name="Illustrateur / BD",
        category="creatif",
        target_size="pme",
        description="Cible les maisons d'édition, agences de communication et studios de jeux pour des illustrations originales.",
        keywords=["maison d'édition", "agence communication", "studio jeux vidéo", "agence web", "agence marketing"],
        location="Paris, France",
        your_title="Illustrateur & Artiste BD",
        your_offer="Illustrations originales sur mesure pour vos projets éditoriaux, web et marketing",
        email_hook=(
            "En visitant le site de {name}, j'ai remarqué que vos visuels actuels reposent principalement "
            "sur des photos ou des illustrations stock. "
            "Des illustrations originales apportent une identité unique qui vous distingue immédiatement "
            "de vos concurrents et renforce la mémorisation de votre marque."
        ),
        sms_hook="Des illustrations originales pour démarquer votre marque. Dispo pour un brief cette semaine ?",
        qualification_criteria=[
            "Utilisation de visuels génériques ou stock",
            "Secteur créatif ou éditorial",
            "Pas d'identité illustrée distinctive",
        ],
    ),

    # -----------------------------------------------------------------------
    # Profils Conseil & Formation
    # -----------------------------------------------------------------------

    Profile(
        id="consultant_marketing",
        emoji="🎯",
        name="Consultant Marketing",
        category="conseil",
        target_size="pme",
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
        id="consultant_rh",
        emoji="👥",
        name="Consultant RH",
        category="conseil",
        target_size="pme",
        description="Cible les PME et startups en croissance avec des besoins de recrutement ou d'organisation RH.",
        keywords=["startup", "PME", "agence", "cabinet conseil", "industrie", "ESN", "scale-up"],
        location="Paris, France",
        your_title="Consultant RH",
        your_offer="Recrutement, onboarding et structuration RH pour les entreprises en croissance",
        email_hook=(
            "J'ai regardé l'activité de {name} et j'ai noté que votre croissance "
            "génère probablement des besoins RH importants. "
            "Recrutement, intégration, organisation des équipes — je structure tout ça "
            "pour que vous puissiez vous concentrer sur votre cœur de métier."
        ),
        sms_hook="Recrutement ou structuration RH pour votre équipe en croissance. Échange 20 min cette semaine ?",
        qualification_criteria=[
            "Entreprise en croissance visible",
            "Offres d'emploi publiées ou mentionnées",
            "Pas de DRH ou service RH dédié affiché",
        ],
    ),

    Profile(
        id="comptable",
        emoji="💰",
        name="Comptabilité → TPE & Indépendants",
        category="conseil",
        target_size="tpe",
        description="Cible les auto-entrepreneurs, artisans et petits commerces sans cabinet comptable apparent.",
        keywords=["auto-entrepreneur", "artisan", "coiffeur indépendant", "restaurateur", "commerce indépendant", "micro-entreprise"],
        location="Lyon, France",
        your_title="Expert-comptable & Conseiller Fiscal",
        your_offer="Comptabilité, déclarations fiscales et conseil pour indépendants et TPE",
        email_hook=(
            "En tant qu'indépendant ou gérant de {name}, la gestion comptable et fiscale "
            "prend souvent du temps que vous n'avez pas. "
            "Je m'occupe de tout — déclarations, bilans, optimisation fiscale — "
            "pour que vous puissiez vous concentrer sur votre activité."
        ),
        sms_hook="Comptabilité et déclarations gérées pour vous. Tarif adapté aux indépendants. On en parle ?",
        qualification_criteria=[
            "Indépendant ou TPE",
            "Pas de cabinet comptable mentionné",
            "Site simple sans back-office apparent",
        ],
    ),

    Profile(
        id="juriste",
        emoji="⚖️",
        name="Juridique & RGPD → Startups & E-commerce",
        category="conseil",
        target_size="pme",
        description="Cible les startups et e-commerces sans mentions légales, CGV ou politique de confidentialité.",
        keywords=["startup", "e-commerce", "agence", "SaaS", "boutique en ligne", "marketplace", "coach en ligne"],
        location="Paris, France",
        your_title="Juriste — Droit des affaires & RGPD",
        your_offer="Contrats, CGV, mentions légales et conformité RGPD pour entreprises digitales",
        email_hook=(
            "En consultant le site de {name}, j'ai constaté que certaines mentions légales "
            "obligatoires semblent incomplètes ou absentes. "
            "En cas de litige ou de contrôle CNIL, cela expose votre entreprise à des amendes "
            "pouvant aller jusqu'à 20 000 €. Je peux régulariser tout ça rapidement."
        ),
        sms_hook="Votre site est-il conforme RGPD et CGV ? Je vérifie gratuitement en 10 min.",
        qualification_criteria=[
            "Site sans mentions légales visibles",
            "Absence de politique de confidentialité",
            "E-commerce ou collecte de données",
        ],
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

    Profile(
        id="consultant_rse",
        emoji="🌱",
        name="Consultant RSE",
        category="conseil",
        target_size="pme",
        description="Cible les PME et industries qui n'ont aucune démarche RSE visible — obligation légale pour les +500 salariés.",
        keywords=["PME", "industrie", "logistique", "grande surface", "promoteur immobilier", "cabinet conseil", "collectivité"],
        location="Lyon, France",
        your_title="Consultant RSE & Développement Durable",
        your_offer="Diagnostic RSE, bilan carbone et plan d'action développement durable pour PME",
        email_hook=(
            "En analysant la présence en ligne de {name}, je n'ai pas trouvé de page dédiée "
            "à votre démarche RSE ou développement durable. "
            "Au-delà de l'obligation légale pour certaines structures, une stratégie RSE visible "
            "améliore votre image auprès de vos clients et facilite vos appels d'offres publics."
        ),
        sms_hook="Bilan RSE et plan développement durable pour votre entreprise. Diagnostic gratuit. Intéressé(e) ?",
        qualification_criteria=[
            "PME ou industrie sans page RSE",
            "Secteur à fort impact environnemental",
            "Pas de certification environnementale mentionnée",
        ],
    ),

    Profile(
        id="formateur",
        emoji="📚",
        name="Formateur / E-learning",
        category="conseil",
        target_size="all",
        description="Cible les entreprises et associations pour des formations en présentiel ou distanciel.",
        keywords=["entreprise", "PME", "association", "cabinet médical", "industrie", "coworking", "agence"],
        location="Lyon, France",
        your_title="Formateur & Concepteur E-learning",
        your_offer="Formations sur mesure en présentiel ou en ligne pour monter en compétences vos équipes",
        email_hook=(
            "Je propose aux équipes de {name} des formations courtes et opérationnelles "
            "adaptées à vos enjeux métier. "
            "Une journée de formation bien ciblée peut générer un retour sur investissement "
            "immédiat sur la productivité et la qualité de travail de vos collaborateurs."
        ),
        sms_hook="Formations courtes et opérationnelles pour vos équipes. Devis gratuit en 24h. Dispo ?",
        qualification_criteria=[
            "Entreprise avec salariés à former",
            "Pas de section formation ou développement des compétences",
            "Secteur en évolution rapide",
        ],
    ),

    Profile(
        id="assistant_virtuel",
        emoji="📋",
        name="Assistant(e) Virtuel(le)",
        category="conseil",
        target_size="tpe",
        description="Cible les professionnels libéraux solo surchargés — médecins, avocats, coachs — pour déléguer les tâches administratives.",
        keywords=["médecin", "avocat", "notaire", "consultant", "thérapeute", "coach", "expert-comptable"],
        location="Lyon, France",
        your_title="Assistante Virtuelle",
        your_offer="Gestion administrative, agenda et email pour libérer votre temps sur votre cœur de métier",
        email_hook=(
            "En tant que professionnel indépendant, {name} gère probablement seul(e) "
            "une part importante de ses tâches administratives. "
            "Gestion d'agenda, réponse aux emails, relances clients, saisie de documents — "
            "je prends en charge tout ça à distance pour que vous puissiez vous concentrer sur l'essentiel."
        ),
        sms_hook="Déléguez vos tâches admin à distance. Gestion d'agenda, emails, relances. Dispo pour en parler ?",
        qualification_criteria=[
            "Professionnel libéral ou consultant solo",
            "Pas d'assistante ou de secrétariat visible",
            "Activité à forte charge administrative",
        ],
    ),

    Profile(
        id="traducteur",
        emoji="🌍",
        name="Traducteur",
        category="conseil",
        target_size="all",
        description="Cible les cabinets juridiques, hôtels et exportateurs avec une clientèle internationale et un site français uniquement.",
        keywords=["cabinet d'avocats", "hôtel", "restaurant gastronomique", "exportateur", "agence internationale", "cabinet d'affaires"],
        location="Paris, France",
        your_title="Traducteur Assermenté — FR/EN/ES",
        your_offer="Traduction professionnelle de documents juridiques, marketing et sites web",
        email_hook=(
            "En consultant le site de {name}, j'ai remarqué qu'il est uniquement disponible en français. "
            "Si une partie de votre clientèle est internationale, "
            "l'absence de version traduite vous fait manquer des opportunités concrètes. "
            "Je traduis sites web, contrats et documents officiels avec précision et rapidité."
        ),
        sms_hook="Votre site en anglais ou espagnol peut ouvrir de nouveaux marchés. Devis sous 24h.",
        qualification_criteria=[
            "Secteur avec clientèle internationale probable",
            "Site en français uniquement",
            "Documents juridiques ou contractuels",
        ],
    ),

    # -----------------------------------------------------------------------
    # Profils Santé & Bien-être
    # -----------------------------------------------------------------------

    Profile(
        id="coach_sportif",
        emoji="🏋️",
        name="Coach Sportif",
        category="sante",
        target_size="pme",
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
        id="nutritionniste",
        emoji="🥗",
        name="Nutritionniste / Diététicien",
        category="sante",
        target_size="all",
        description="Cible les salles de sport, clubs fitness et entreprises sans partenaire nutrition.",
        keywords=["salle de sport", "club de fitness", "CrossFit", "studio de yoga", "cabinet médical", "centre bien-être"],
        location="Lyon, France",
        your_title="Nutritionniste & Diététicien",
        your_offer="Suivi nutritionnel personnalisé pour vos adhérents et collaborateurs",
        email_hook=(
            "En consultant le site de {name}, je n'ai pas trouvé de service de suivi nutritionnel "
            "pour vos adhérents ou collaborateurs. "
            "La nutrition est le complément indispensable à l'activité physique — "
            "une collaboration nous permettrait d'offrir un accompagnement vraiment complet à vos clients."
        ),
        sms_hook="Partenariat nutrition pour vos adhérents ? Je propose des consultations sur place. On en parle ?",
        qualification_criteria=[
            "Salle de sport ou structure bien-être",
            "Pas de nutritionniste partenaire mentionné",
            "Clientèle axée performance ou santé",
        ],
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
    ),

    Profile(
        id="kine_osteo",
        emoji="💆",
        name="Ostéopathe / Kiné",
        category="sante",
        target_size="all",
        description="Cible les clubs sportifs, studios de danse et entreprises sédentaires sans praticien référencé.",
        keywords=["club de sport", "studio de danse", "salle de fitness", "école de sport", "cabinet médical sportif"],
        location="Paris, France",
        your_title="Ostéopathe / Kinésithérapeute",
        your_offer="Suivi ostéopathique et kinésithérapeutique pour vos sportifs et équipes",
        email_hook=(
            "Je travaille avec des structures sportives comme {name} pour proposer "
            "un suivi ostéopathique à leurs adhérents et sportifs. "
            "La prévention des blessures et la récupération font partie intégrante de la performance — "
            "une collaboration pourrait apporter une vraie valeur ajoutée à votre offre."
        ),
        sms_hook="Suivi ostéopathique pour vos sportifs. Séances sur place possibles. Partenariat ?",
        qualification_criteria=[
            "Club ou structure sportive",
            "Pas de praticien spécialisé mentionné",
            "Risque de blessures ou sollicitation physique forte",
        ],
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
    ),

    Profile(
        id="psy_therapeute",
        emoji="🧠",
        name="Psychologue / Thérapeute",
        category="sante",
        target_size="pme",
        description="Cible les entreprises et cabinets RH pour des programmes de soutien psychologique et QVT.",
        keywords=["entreprise", "PME", "startup", "cabinet RH", "SSII", "cabinet médical", "association"],
        location="Paris, France",
        your_title="Psychologue du Travail",
        your_offer="Accompagnement psychologique en entreprise — prévention burnout et amélioration QVT",
        email_hook=(
            "Le bien-être mental au travail est aujourd'hui un enjeu majeur de performance pour {name}. "
            "Absentéisme, turnover, burnout — ces signaux coûtent en moyenne 14 000 € par salarié perdu. "
            "Je propose des interventions discrètes et efficaces pour prévenir ces situations et "
            "renforcer la cohésion de vos équipes."
        ),
        sms_hook="Programme bien-être mental pour vos équipes. Prévention burnout et QVT. Échange rapide ?",
        qualification_criteria=[
            "Entreprise avec équipes en pression",
            "Pas de programme QVT ou soutien psy mentionné",
            "Secteur à forte intensité émotionnelle",
        ],
    ),

    # -----------------------------------------------------------------------
    # Profils Services Physiques
    # -----------------------------------------------------------------------

    Profile(
        id="nettoyage",
        emoji="🧹",
        name="Service de Nettoyage",
        category="services_physiques",
        target_size="all",
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
        id="securite",
        emoji="🛡️",
        name="Agent de sécurité / Gardiennage",
        category="services_physiques",
        target_size="all",
        description="Cible les bijouteries, pharmacies, galeries d'art et cliniques pour des contrats de gardiennage.",
        keywords=["bijouterie", "pharmacie", "galerie d'art", "clinique privée", "boutique luxe", "joaillier", "horloger"],
        location="Paris, France",
        your_title="Responsable sécurité — Gardiennage & Surveillance",
        your_offer="Gardiennage professionnel et surveillance de vos locaux et marchandises de valeur",
        email_hook=(
            "Je propose aux établissements comme {name} des solutions de gardiennage "
            "adaptées aux commerces de valeur. "
            "Présence discrète mais visible, intervention rapide, agents certifiés — "
            "pour que vous et vos clients vous sentiez en sécurité."
        ),
        sms_hook="Gardiennage pour votre établissement. Agents certifiés, tarifs compétitifs. Devis gratuit ?",
        qualification_criteria=[
            "Commerce à forte valeur marchande",
            "Bijouterie, pharmacie ou galerie",
            "Pas de prestataire sécurité mentionné",
        ],
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
    ),

    Profile(
        id="traiteur",
        emoji="🍽️",
        name="Traiteur / Chef à domicile",
        category="services_physiques",
        target_size="pme",
        description="Cible les espaces de coworking, hôtels d'affaires et entreprises sans prestataire repas.",
        keywords=["espace coworking", "hôtel d'affaires", "salle de réunion", "centre de conférences", "entreprise", "PME"],
        location="Paris, France",
        your_title="Traiteur & Chef à domicile",
        your_offer="Plateaux repas et buffets pour vos réunions, séminaires et événements d'entreprise",
        email_hook=(
            "Je propose aux équipes de {name} des solutions de restauration sur mesure "
            "pour vos réunions et événements professionnels. "
            "Plateaux repas, buffets déjeuner ou cocktails dînatoires — "
            "je m'occupe de tout pour que votre événement soit mémorable."
        ),
        sms_hook="Plateaux repas et buffets pour vos réunions d'entreprise. Devis sous 2h. Disponible ?",
        qualification_criteria=[
            "Espace avec salles de réunion",
            "Pas de prestataire restauration mentionné",
            "Entreprise avec équipes régulières",
        ],
    ),

    Profile(
        id="artisan_batiment",
        emoji="🔧",
        name="Plombier / Électricien",
        category="services_physiques",
        target_size="all",
        description="Cible les agences immobilières, syndics et hôtels pour des contrats de maintenance récurrente.",
        keywords=["agence immobilière", "syndic de copropriété", "hôtel", "résidence services", "gestionnaire de biens"],
        location="Lyon, France",
        your_title="Artisan — Plomberie & Électricité",
        your_offer="Maintenance et interventions d'urgence pour gestionnaires de biens immobiliers",
        email_hook=(
            "Je me spécialise dans les contrats de maintenance pour les gestionnaires de patrimoine "
            "comme {name}. Interventions rapides, devis transparents, disponibilité 7j/7 — "
            "le tout sans les contraintes d'un prestataire unique sous-dimensionné."
        ),
        sms_hook="Contrat maintenance plomberie/électricité pour vos biens. Intervention sous 4h. Devis gratuit.",
        qualification_criteria=[
            "Gestionnaire de biens immobiliers",
            "Plusieurs logements ou locaux à gérer",
            "Pas de prestataire technique mentionné",
        ],
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
    ),

    Profile(
        id="paysagiste",
        emoji="🌿",
        name="Paysagiste",
        category="services_physiques",
        target_size="all",
        description="Cible les hôtels, restaurants avec terrasse et entreprises avec espaces verts à entretenir.",
        keywords=["hôtel", "restaurant avec terrasse", "château", "résidence", "entreprise", "golf", "camping"],
        location="Lyon, France",
        your_title="Paysagiste & Jardinier Paysagiste",
        your_offer="Création et entretien d'espaces verts pour établissements professionnels",
        email_hook=(
            "Les espaces verts de {name} sont souvent la première impression que donnent "
            "vos locaux à vos clients et visiteurs. "
            "Un jardin bien entretenu ou une terrasse fleurie valorise votre image "
            "et incite les clients à s'y attarder — je peux vous proposer un devis adapté à votre budget."
        ),
        sms_hook="Entretien de vos espaces verts professionnel et régulier. Devis gratuit sous 48h.",
        qualification_criteria=[
            "Établissement avec espaces extérieurs",
            "Hôtel, restaurant ou entreprise avec parc",
            "Pas de prestataire paysagiste mentionné",
        ],
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
    ),

    Profile(
        id="imprimeur",
        emoji="🖨️",
        name="Imprimeur / Signalétique",
        category="services_physiques",
        target_size="tpe",
        description="Cible les commerces et agences pour des supports print, enseignes et signalétique professionnelle.",
        keywords=["commerce", "restaurant", "agence", "startup", "boutique", "salon", "pharmacie"],
        location="Lyon, France",
        your_title="Imprimeur & Signalétique Professionnelle",
        your_offer="Flyers, kakémonos, enseignes et signalétique pour professionnels — délai 48h",
        email_hook=(
            "En regardant la présence de {name}, j'ai pensé que vos supports print "
            "pourraient être optimisés pour mieux attirer et informer vos clients. "
            "Flyers, menus, PLV, enseigne — je réalise tous vos supports en délai express "
            "avec un résultat professionnel garanti."
        ),
        sms_hook="Flyers, enseignes, PLV en 48h. Qualité pro, prix compétitifs. Devis gratuit ?",
        qualification_criteria=[
            "Commerce ou agence avec besoins de communication print",
            "Site avec identité visuelle peu développée",
            "Secteur grand public ou événementiel",
        ],
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

    Profile(
        id="archi_interieur",
        emoji="🏠",
        name="Architecte d'intérieur",
        category="services_physiques",
        target_size="all",
        description="Cible les hôtels, restaurants et boutiques avec une décoration datée ou en cours de travaux.",
        keywords=["hôtel", "restaurant", "boutique", "spa", "café", "bureau coworking", "cabinet médical"],
        location="Paris, France",
        your_title="Architecte d'intérieur",
        your_offer="Conception et rénovation d'espaces commerciaux pour maximiser l'expérience client",
        email_hook=(
            "En visitant le site de {name}, j'ai remarqué que l'espace mérite peut-être "
            "une mise à jour pour mieux refléter vos valeurs et attirer davantage de clients. "
            "Un espace bien conçu augmente le panier moyen et la durée de visite — "
            "je serais ravi de vous présenter quelques idées sans engagement."
        ),
        sms_hook="Un réaménagement de votre espace peut booster vos ventes. Visite conseil offerte cette semaine.",
        qualification_criteria=[
            "Commerce ou hôtel avec espace physique",
            "Site avec photos d'intérieur datées",
            "Pas de mention de rénovation récente",
        ],
        check_weight_overrides={
            "outdated": 20,
            "social_links": 10,
            "free_builder": 15,
            "tracking": 0,
            "title": 0,
            "meta_description": 0,
        },
        score_threshold_default=70,
    ),

    # -----------------------------------------------------------------------
    # Profils Spéciaux
    # -----------------------------------------------------------------------

    Profile(
        id="fleuriste",
        emoji="💐",
        name="Fleuriste",
        category="special",
        target_size="all",
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
        id="coursier",
        emoji="🚚",
        name="Coursier High Ticket",
        category="special",
        target_size="all",
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
        id="chercheur_emploi",
        emoji="🔍",
        name="Chercheur d'emploi",
        category="special",
        target_size="pme",
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
        id="prof_particulier",
        emoji="📖",
        name="Professeur particulier",
        category="special",
        target_size="all",
        description="Cible les établissements scolaires et centres de soutien pour des partenariats de cours particuliers.",
        keywords=["collège", "lycée", "école primaire", "centre de soutien scolaire", "prépa", "établissement scolaire"],
        location="Paris, France",
        your_title="Professeur particulier — Maths, Français, Anglais",
        your_offer="Cours particuliers à domicile ou en ligne, résultats garantis en 3 mois",
        email_hook=(
            "Je propose aux familles liées à {name} des cours particuliers personnalisés "
            "pour les élèves en difficulté ou souhaitant progresser rapidement. "
            "Mes élèves progressent en moyenne d'une demi-lettre de note par mois — "
            "une collaboration avec votre établissement bénéficierait directement à vos élèves."
        ),
        sms_hook="Cours particuliers pour élèves en difficulté. Partenariat établissement possible. On en discute ?",
        qualification_criteria=[
            "Établissement scolaire ou centre de formation",
            "Pas de service de soutien scolaire intégré",
            "Présence d'élèves nécessitant un accompagnement",
        ],
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
    ),

    Profile(
        id="animateur_enfants",
        emoji="🎪",
        name="Animateur / Événements enfants",
        category="special",
        target_size="all",
        description="Cible les restaurants familiaux, hôtels et centres commerciaux pour des animations enfants.",
        keywords=["restaurant familial", "centre commercial", "hôtel familial", "salle de fête", "camping", "parc de loisirs"],
        location="Lyon, France",
        your_title="Animateur & Organisateur d'événements enfants",
        your_offer="Animations et ateliers enfants pour vos événements — magie, jeux, activités créatives",
        email_hook=(
            "Je propose aux établissements comme {name} des animations enfants "
            "sur mesure pour vos événements familiaux. "
            "Un espace animation bien conçu augmente le panier moyen des familles de 40 % "
            "et les fidélise sur le long terme."
        ),
        sms_hook="Animations enfants pour votre établissement. Magie, ateliers, jeux. Devis gratuit sous 24h.",
        qualification_criteria=[
            "Établissement accueillant des familles",
            "Pas d'animation enfants mentionnée",
            "Restaurant, hôtel ou centre de loisirs",
        ],
        check_weight_overrides={
            "https": 0, "tracking": 0, "viewport": 0, "title": 0,
            "meta_description": 0, "lead_form": 0, "free_builder": 0,
            "social_links": 0, "outdated": 0, "response_time": 0,
        },
    ),

    # -----------------------------------------------------------------------
    # Profil Custom
    # -----------------------------------------------------------------------

    Profile(
        id="custom",
        emoji="⚙️",
        name="Profil Custom",
        category="autre",
        target_size="all",
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
