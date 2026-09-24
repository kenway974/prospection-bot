"""
Profils de service — ce que VOUS proposez (le prestataire).
Séparé des cibles (target_segments.py) pour permettre 2 sélecteurs indépendants dans l'UI.

Catalogue recentré sur le métier de développeur web fullstack : uniquement des
prestations de BUILD (ce qu'on code et livre), pas de marketing pur ni de créatif.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : catalogue des SERVICES que TU vends (site vitrine, appli web, e-commerce...).
# 📘   Chaque service fournit ton titre, ton pitch, les accroches email/SMS et les réglages
# 📘   de scoring utilisés pour juger si un prospect est intéressant.
# 📘 Appelé par : app.py (sélecteurs « Votre activité » de la page Prospection, puis
# 📘   construction du dict `params` envoyé à pipeline.py), tests/test_service_profiles.py.
# 📘 Appelle : rien du projet (uniquement la bibliothèque standard : dataclasses, typing).
# 📘 Concepts Python à retenir ici : import, @dataclass, type hints (str, int, List, Dict,
# 📘   Optional), field(default_factory=...), liste d'objets, dict, next() + générateur.
#
# 📘 `from __future__ import annotations` : les annotations de type (": str", "-> List")
# 📘   sont gardées comme du texte et pas évaluées tout de suite (plus souple, plus rapide).
# 📘 `from X import Y` : on importe seulement Y depuis le module X (module = fichier .py).
# 📘 `typing` fournit des types pour les annotations : List[str] = « liste de textes »,
# 📘   Dict[str, str] = « dictionnaire clé texte → valeur texte », Optional[X] = « X ou None ».


# 📘 `@dataclass` est un DÉCORATEUR : il transforme la classe en « fiche de données ».
# 📘   Python génère tout seul le constructeur __init__ à partir des champs déclarés,
# 📘   donc on peut écrire ServiceProfile(id="...", emoji="...", ...) sans code en plus.
# 📘 Une CLASSE = un modèle d'objet ; chaque ServiceProfile(...) créé plus bas est une
# 📘   INSTANCE (un objet concret) de ce modèle.
# 📘 Chaque ligne `nom: type` déclare un ATTRIBUT (un champ). Les champs sans valeur par
# 📘   défaut sont obligatoires ; ceux avec `= ...` sont facultatifs.
@dataclass
class ServiceProfile:
    id: str                                # 📘 identifiant technique unique (ex. "web_app")
    emoji: str
    name: str
    category: str                          # pour grouper dans l'UI
    description: str
    your_title: str                        # 📘 ta signature si le titre des Réglages est vide
    your_offer: str                        # 📘 pitch en 1 phrase, pré-rempli dans l'UI (modifiable)
    email_hook: str                        # doit contenir {name}
    # 📘 {name} est un « placeholder » : il sera remplacé par le nom de l'entreprise
    # 📘   prospectée (via str.format / f-string ailleurs dans le code).
    sms_hook: str                          # max 160 chars
    # 📘 Poids des vérifications du site (clés = noms de checks de services/analyzer.py).
    # 📘   Vide = poids par défaut de l'analyzer. Passé tel quel dans params["weight_overrides"].
    # 📘 `field(default_factory=dict)` : crée un NOUVEAU dict vide pour chaque objet.
    # 📘   Piège classique : écrire `= {}` partagerait LE MÊME dict entre tous les objets
    # 📘   (dataclass l'interdit d'ailleurs et lève une erreur).
    check_weight_overrides: dict = field(default_factory=dict)
    score_direction: str = "asc"           # "asc" = site mauvais = bon prospect
    # 📘 Seuil de score proposé par défaut dans le slider de l'UI (une cible peut le
    # 📘   remplacer via son propre score_threshold_override, cf. target_segments.py).
    score_threshold_default: int = 100
    # Mots-clés : si ABSENTS du site prospect → opportunité (no_service_mention)
    detection_keywords: List[str] = field(default_factory=list)


# 📘 Un DICTIONNAIRE (dict) associe des clés à des valeurs : {"clé": "valeur", ...}.
# 📘   Ici : code de catégorie → libellé affiché. app.py s'en sert pour le bouton radio
# 📘   « Catégorie » ; l'ordre des clés = l'ordre d'affichage (les dict gardent l'ordre).
# 💡 Chaque ServiceProfile.category devrait exister dans ce dict : c'est vérifié par un test,
# 💡   mais on pourrait l'imposer dans le code avec un Enum (from enum import Enum) pour
# 💡   qu'une faute de frappe soit détectée par l'éditeur et pas seulement par les tests.
SERVICE_CATEGORY_LABELS: Dict[str, str] = {
    "web_digital": "🌐 Développement Web",
    "freelance":   "🧑‍💻 Mission freelance",
}


# 📘 Une LISTE (list) est une suite ordonnée d'éléments entre crochets [a, b, c].
# 📘   Ici chaque élément est un objet ServiceProfile. On utilise des ARGUMENTS NOMMÉS
# 📘   (id=..., name=...) : plus lisible et l'ordre n'a pas d'importance.
# 📘 Convention : un nom EN_MAJUSCULES = une « constante » (on ne la modifie pas en cours de
# 📘   route). Python ne l'interdit pas, c'est juste une convention entre développeurs.
# 📘 Consommation : app.py filtre cette liste par `category` pour remplir le menu « Service »,
# 📘   puis recopie les champs du service choisi dans `params` (your_offer, email_hook,
# 📘   sms_hook, detection_keywords, check_weight_overrides → weight_overrides, score_direction).
# 💡 Ce catalogue est du CONTENU (textes commerciaux) mélangé au code : le déplacer dans un
# 💡   fichier YAML/JSON (ou une table en base) permettrait de modifier un pitch sans toucher
# 💡   au Python ni redéployer ; on garderait la dataclass pour valider le chargement.
SERVICE_PROFILES: List[ServiceProfile] = [

    # -----------------------------------------------------------------------
    # Développement Web — prestations de build d'un dev fullstack
    # -----------------------------------------------------------------------

    # 📘 Création d'un objet : on « appelle » la classe comme une fonction. Les parenthèses
    # 📘   autour du texte d'email_hook permettent d'écrire une longue chaîne sur plusieurs
    # 📘   lignes : Python colle automatiquement les morceaux "..." "..." bout à bout.
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
        # 📘 Seul service qui surcharge les poids : on insiste sur l'absence de formulaire
        # 📘   et de tracking (signes qu'on ne vend pas en ligne). Les checks non listés
        # 📘   gardent leur poids par défaut (analyzer fait weights.update(overrides)).
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

    # -----------------------------------------------------------------------
    # Mission freelance / Renfort — on ne vend pas un site, on propose SES bras
    # (agences web, startups, SaaS, studios de dev, éditeurs). Pitch = candidature,
    # pas audit du site. Score neutre (seuil 100) : on veut les boîtes ACTIVES,
    # peu importe l'état de leur site.
    # -----------------------------------------------------------------------

    ServiceProfile(
        id="web_freelance",
        emoji="🧑‍💻",
        name="Mission freelance / Renfort dev",
        category="freelance",
        description="Candidature freelance : renfort dev fullstack pour agences, startups, SaaS et studios.",
        your_title="Développeur Web Fullstack — Freelance",
        your_offer="Renfort dev fullstack en freelance : missions ponctuelles, débordement ou régie",
        email_hook=(
            "Je me permets de vous contacter en tant que développeur web fullstack freelance. "
            "En découvrant {name}, je me suis dit que je pourrais vous être utile en renfort — "
            "sur du débordement, une mission ponctuelle ou un projet précis."
        ),
        sms_hook="Dev web fullstack freelance, dispo pour du renfort / des missions. Je peux vous envoyer mon profil ?",
        score_threshold_default=100,
        detection_keywords=[],
    ),

]


# 📘 `def` définit une FONCTION. `service_id: str` = paramètre annoté « texte attendu » ;
# 📘   `-> Optional[ServiceProfile]` = elle renvoie un ServiceProfile OU None (rien trouvé).
# 📘 `(s for s in LISTE if condition)` est une EXPRESSION GÉNÉRATRICE : elle parcourt la liste
# 📘   et ne produit que les éléments qui respectent la condition, un par un, à la demande.
# 📘 `next(generateur, None)` prend le PREMIER élément produit, ou None si aucun ne correspond.
# 📘 Note : app.py importe cette fonction mais ne l'appelle pas (il se construit son propre
# 📘   dict {id: service}) ; elle est utilisée par les tests.
def get_service(service_id: str) -> Optional[ServiceProfile]:
    return next((s for s in SERVICE_PROFILES if s.id == service_id), None)


# 📘 Renvoie la liste elle-même (pas une copie) : si l'appelant la modifie, il modifie
# 📘   le catalogue global. Sans conséquence aujourd'hui, mais bon à savoir.
# 💡 Renvoyer `list(SERVICE_PROFILES)` (une copie) protégerait le catalogue d'une modif
# 💡   accidentelle par un appelant.
def list_services() -> List[ServiceProfile]:
    return SERVICE_PROFILES
