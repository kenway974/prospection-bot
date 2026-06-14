"""
Génère un brouillon de cold email ultra-personnalisé.

Logique de construction :
  - Cas 1 : Pas de site web → offre de création
  - Cas 2 : Site inaccessible → urgence disponibilité
  - Cas 3 : 1 seul problème → mail focus sur ce point précis
  - Cas 4 : 2-3 problèmes → mail avec liste courte
  - Cas 5 : 4+ problèmes → mail audit complet
  - Profil custom → accroche définie par l'utilisateur en priorité
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from config import config, logger
from services.google_maps import Prospect


# ---------------------------------------------------------------------------
# Style configurable des emails dynamiques
# ---------------------------------------------------------------------------

@dataclass
class EmailStyle:
    intonation: str = "professional"  # "formal" | "professional" | "direct" | "casual"
    length: str = "medium"            # "short" | "medium" | "long"
    salutation: str = "neutral"       # "formal" | "neutral" | "first_name"
    cta: str = "audit"               # "audit" | "call" | "meeting" | "reply"


EMAIL_STYLE_LABELS = {
    "intonation": {
        "formal":       "Formel",
        "professional": "Professionnel",
        "direct":       "Direct",
        "casual":       "Décontracté",
    },
    "length": {
        "short":  "Court (3-4 lignes)",
        "medium": "Moyen (2 paragraphes)",
        "long":   "Long (3 paragraphes)",
    },
    "salutation": {
        "formal":     "Madame, Monsieur,",
        "neutral":    "Bonjour,",
        "first_name": "Bonjour [Prénom],",
    },
    "cta": {
        "audit":   "Je vous propose un audit gratuit — sans engagement.",
        "call":    "Seriez-vous disponible pour un appel de 15 min cette semaine ?",
        "meeting": "Je serais ravi(e) d'en discuter lors d'un rapide échange.",
        "reply":   "N'hésitez pas à me répondre pour en savoir plus.",
    },
}

# Structure : issue_key → {intonation: sentence}
# {name} sera remplacé par le nom du prospect, {cms} par le CMS détecté
ISSUE_COPY = {
    "no_website": {
        "formal":       "Il m'est apparu que {name} ne dispose pas encore de site internet. Dans votre secteur d'activité, cette absence constitue un frein significatif à l'acquisition de nouveaux clients.",
        "professional": "En cherchant {name} en ligne, j'ai constaté l'absence de site web. Dans votre secteur, une présence web est devenue incontournable pour capter de nouveaux clients.",
        "direct":       "{name} n'a pas de site web — vos concurrents captent chaque jour les clients qui vous cherchent sur Google.",
        "casual":       "J'ai voulu consulter votre site web... et je n'en ai pas trouvé ! Dans votre domaine, c'est une vraie opportunité à saisir avant vos concurrents.",
    },
    "site_down": {
        "formal":       "Votre site internet semble actuellement inaccessible, ce qui prive vos clients potentiels de tout accès à votre activité en ligne.",
        "professional": "Votre site est actuellement inaccessible — vos visiteurs tombent sur une erreur et repartent chez la concurrence.",
        "direct":       "Votre site est down. Vos clients ne peuvent pas vous trouver en ligne.",
        "casual":       "Mauvaise nouvelle : votre site est actuellement inaccessible ! Vos clients arrivent sur une page d'erreur...",
    },
    "https": {
        "formal":       "Votre site fonctionne en HTTP non sécurisé, ce qui entraîne l'affichage d'un avertissement de sécurité dans les navigateurs et pénalise votre référencement.",
        "professional": "Votre site n'est pas sécurisé (HTTP) : Google affiche un avertissement à vos visiteurs et pénalise les sites sans HTTPS dans ses résultats.",
        "direct":       "Votre site est en HTTP — pas en HTTPS. Google le déclasse et vos visiteurs voient un avertissement de sécurité.",
        "casual":       "Votre site n'a pas le cadenas HTTPS — les navigateurs affichent un message d'alerte à vos visiteurs, ce qui fait fuir beaucoup de monde.",
    },
    "viewport": {
        "formal":       "Votre site n'est pas optimisé pour les appareils mobiles, alors que plus de 60 % des recherches locales sont effectuées depuis un smartphone.",
        "professional": "Votre site n'est pas adapté aux mobiles — or plus de 60% de vos clients potentiels vous cherchent depuis leur téléphone.",
        "direct":       "Votre site n'est pas responsive. Sur mobile, il est illisible — 60% de vos visiteurs potentiels partent immédiatement.",
        "casual":       "Sur téléphone, votre site est vraiment difficile à lire... Et c'est sur mobile que la plupart des gens vous cherchent !",
    },
    "tracking": {
        "formal":       "Aucun outil de mesure d'audience n'est installé sur votre site, ce qui vous prive de toute donnée sur le comportement de vos visiteurs.",
        "professional": "Votre site ne dispose d'aucun analytics — vous ne savez pas combien de personnes vous visitent, ni comment elles vous ont trouvé.",
        "direct":       "Pas d'analytics sur votre site. Vous pilotez à l'aveugle : impossible de savoir ce qui marche ou non.",
        "casual":       "Votre site n'a pas de stats ! Vous ne pouvez pas savoir combien de personnes le visitent ni ce qu'elles font dessus.",
    },
    "lead_form": {
        "formal":       "Votre site ne propose pas de formulaire de contact, ce qui complique considérablement la prise de contact pour vos visiteurs.",
        "professional": "Votre site n'a pas de formulaire de contact visible — vos visiteurs intéressés n'ont aucun moyen simple de vous joindre.",
        "direct":       "Pas de formulaire sur votre site. Vos visiteurs n'ont aucun moyen facile de vous contacter — vous perdez des leads.",
        "casual":       "Il n'y a pas de formulaire de contact sur votre site — un visiteur intéressé ne sait pas comment vous écrire facilement !",
    },
    "free_builder": {
        "formal":       "Votre site est actuellement construit avec {cms}, un outil grand public qui présente des limitations importantes en matière de référencement et de personnalisation.",
        "professional": "Votre site est sur {cms} — ces plateformes limitent vos options SEO, votre vitesse de chargement et la personnalisation de votre image.",
        "direct":       "Votre site tourne sur {cms}. Ces outils freinent votre référencement Google et donnent une image peu professionnelle.",
        "casual":       "Votre site est sur {cms} — c'est bien pour démarrer, mais ça bloque votre référencement et ça se voit visuellement.",
    },
    "response_time": {
        "formal":       "Votre site présente des temps de chargement élevés, ce qui nuit à l'expérience utilisateur et pénalise votre positionnement dans les résultats Google.",
        "professional": "Votre site est lent à charger sur mobile — Google pénalise les sites qui mettent plus de 3 secondes, et vos visiteurs abandonnent avant même de voir votre contenu.",
        "direct":       "Votre site est lent. Google déclasse les sites lents, et vos visiteurs partent avant que la page charge.",
        "casual":       "Votre site met beaucoup de temps à charger... 3 secondes, c'est le maximum avant que les gens partent sans même voir votre contenu.",
    },
    "title": {
        "formal":       "La balise titre de votre site n'est pas optimisée, ce qui limite significativement votre visibilité dans les résultats de recherche Google.",
        "professional": "La balise titre de votre site (ce qui apparaît dans Google) est absente ou mal renseignée — vous n'apparaissez pas sur vos mots-clés cibles.",
        "direct":       "Votre balise titre est mal configurée — vous n'apparaissez pas sur Google pour les recherches de vos clients.",
        "casual":       "Sur Google, le titre de votre site n'est pas optimisé — du coup vous n'apparaissez pas quand vos clients vous cherchent.",
    },
    "meta_description": {
        "formal":       "La méta-description de votre site est absente ou générique, réduisant votre taux de clics depuis les résultats Google.",
        "professional": "Votre méta-description (le texte affiché sous votre lien dans Google) est absente — c'est une occasion manquée de convaincre les visiteurs de cliquer.",
        "direct":       "Votre description dans Google est vide ou générique. Personne ne clique sur un lien sans description.",
        "casual":       "Dans Google, sous le lien de votre site, il n'y a pas de description... ça donne peu envie de cliquer !",
    },
    "social_links": {
        "formal":       "Votre site ne référence aucun réseau social, privant vos visiteurs d'un moyen de vous suivre et de maintenir le contact avec votre marque.",
        "professional": "Votre site n'affiche aucun lien vers vos réseaux sociaux — une opportunité manquée de fidéliser vos visiteurs.",
        "direct":       "Pas de liens réseaux sociaux sur votre site. Vous perdez des followers potentiels à chaque visite.",
        "casual":       "Vos réseaux sociaux ne sont pas liés depuis votre site — dommage, vous ratez des abonnés !",
    },
    "outdated": {
        "formal":       "Le design de votre site semble dater de plusieurs années, ce qui peut nuire à la perception de professionnalisme et de modernité de votre activité.",
        "professional": "Visuellement, votre site date — un design moderne renforce immédiatement la confiance de vos visiteurs et reflète mieux la qualité de vos services.",
        "direct":       "Votre site est visuellement daté. En 2024, un site vieillissant fait fuir les clients avant même qu'ils lisent votre offre.",
        "casual":       "Honnêtement, votre site a un peu vieilli visuellement — ça peut donner l'impression que votre activité n'est plus très active.",
    },
}

INTRO_TEMPLATES = {
    "formal": (
        "Je me permets de vous contacter suite à l'analyse de la présence en ligne de {name}. "
        "Voici les principaux points que j'ai identifiés :"
    ),
    "professional": (
        "En analysant la présence en ligne de {name}, j'ai identifié plusieurs points "
        "qui méritent votre attention :"
    ),
    "direct": "En deux mots, voilà ce que j'ai trouvé sur {name} :",
    "casual": "J'ai jeté un œil à votre présence en ligne, et voilà ce que j'ai vu :",
}

SIGN_OFF = {
    "formal":       "Dans l'attente de votre retour, je reste à votre disposition.\n\nCordialement,",
    "professional": "Je reste disponible pour toute question.\n\nBien cordialement,",
    "direct":       "Au plaisir d'échanger,",
    "casual":       "À bientôt j'espère !",
}


# ---------------------------------------------------------------------------
# Génération dynamique selon audit + style
# ---------------------------------------------------------------------------

def build_dynamic_email(
    prospect: Prospect,
    style: EmailStyle,
    your_name: str,
    your_title: str,
    your_offer: str,
) -> str:
    """
    Génère un email personnalisé selon les résultats de l'audit ET le style choisi.
    """
    intonation = style.intonation
    length = style.length

    # --- Salutation ---
    salutation_map = {
        "formal":     "Madame, Monsieur,",
        "neutral":    "Bonjour,",
        "first_name": "Bonjour,",  # prénom non disponible en général
    }
    salutation = salutation_map.get(style.salutation, "Bonjour,")

    # --- Problèmes à mentionner ---
    keys = list(prospect.issue_keys) if prospect.issue_keys else []

    # Nombre de problèmes selon la longueur
    n_issues = {"short": 1, "medium": 2, "long": 3}.get(length, 2)
    keys_to_use = keys[:n_issues]

    # --- Corps des problèmes ---
    issue_paragraphs = []
    cms = prospect.cms or "cet outil"
    for key in keys_to_use:
        if key in ISSUE_COPY:
            sentence = ISSUE_COPY[key].get(intonation, ISSUE_COPY[key]["professional"])
            sentence = sentence.format(name=prospect.name, cms=cms)
            issue_paragraphs.append(sentence)

    # Si aucun problème détecté → message générique
    if not issue_paragraphs:
        issue_paragraphs = [
            f"En analysant la présence en ligne de {prospect.name}, j'ai identifié "
            "des opportunités d'amélioration qui pourraient booster votre visibilité."
        ]

    # --- Intro ---
    if length == "short":
        intro = ""
    else:
        intro_template = INTRO_TEMPLATES.get(intonation, INTRO_TEMPLATES["professional"])
        intro = intro_template.format(name=prospect.name)

    # --- Proposition de valeur ---
    if length != "short" and your_offer:
        value_prop = f"{your_offer}."
    else:
        value_prop = ""

    # --- CTA ---
    cta = EMAIL_STYLE_LABELS["cta"].get(style.cta, EMAIL_STYLE_LABELS["cta"]["audit"])

    # --- Signature ---
    sign_off = SIGN_OFF.get(intonation, SIGN_OFF["professional"])
    signature = f"{sign_off}\n{your_name}"
    if your_title:
        signature += f"\n{your_title}"

    # --- Assemblage ---
    parts = [salutation, ""]
    if intro:
        parts.append(intro)
        parts.append("")
    parts.extend(issue_paragraphs)
    parts.append("")
    if value_prop:
        parts.append(value_prop)
        parts.append("")
    parts.append(cta)
    parts.append("")
    parts.append(signature)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# A/B test helpers
# ---------------------------------------------------------------------------

def get_template_variant(place_id: str) -> str:
    """Assigne le variant A ou B de façon déterministe via le hash du place_id (50/50)."""
    return "A" if int(hashlib.md5(place_id.encode()).hexdigest(), 16) % 2 == 0 else "B"


# ---------------------------------------------------------------------------
# Helpers grammaticaux
# ---------------------------------------------------------------------------

def _pluriel(n: int, mot: str, mot_pluriel: str = "") -> str:
    if n <= 1:
        return mot
    return mot_pluriel if mot_pluriel else mot + "s"


# ---------------------------------------------------------------------------
# Sujets dynamiques
# ---------------------------------------------------------------------------

def _build_subject(prospect: Prospect, n_issues: int) -> str:
    name = prospect.name

    if not prospect.has_website():
        return f"{name} — votre présence en ligne peut tout changer"

    if n_issues == 0:
        return f"{name} — une idée pour aller encore plus loin"

    if n_issues == 1:
        issue_short = prospect.issues[0].split("→")[0].strip().lower()
        return f"{name} — un point à corriger sur votre site"

    if n_issues <= 3:
        return f"{name} — {n_issues} {_pluriel(n_issues, 'point')} d'amélioration identifiés sur votre site"

    return f"{name} — audit rapide de votre présence en ligne"


# ---------------------------------------------------------------------------
# Accroche (1er paragraphe)
# ---------------------------------------------------------------------------

def _build_hook(prospect: Prospect) -> str:
    custom_hook = os.getenv("EMAIL_HOOK", "").strip()
    if custom_hook:
        return custom_hook.format(name=prospect.name)

    if not prospect.has_website():
        return (
            f"En cherchant {prospect.name} sur Google, je n'ai pas trouvé de site web associé à votre établissement. "
            f"C'est souvent la première chose que vos clients potentiels vérifient avant de vous contacter — "
            f"et sans site, vous laissez cette opportunité à vos concurrents."
        )

    if any("inaccessible" in i for i in prospect.issues):
        return (
            f"En visitant le site de {prospect.name} aujourd'hui, j'ai constaté qu'il était inaccessible. "
            f"Chaque heure d'indisponibilité, c'est un client potentiel qui repart chez un concurrent."
        )

    if any("HTTPS" in i for i in prospect.issues):
        return (
            f"En consultant le site de {prospect.name}, j'ai remarqué qu'il fonctionne encore en HTTP "
            f"(connexion non sécurisée). Google pénalise activement ces sites dans ses résultats de recherche, "
            f"et les navigateurs affichent une alerte à vos visiteurs."
        )

    if any("viewport" in i.lower() or "mobile" in i.lower() or "responsive" in i.lower() for i in prospect.issues):
        return (
            f"En visitant le site de {prospect.name} depuis un smartphone, j'ai constaté qu'il n'est pas adapté "
            f"à la navigation mobile. Or, plus de 60 % de vos visiteurs naviguent sur téléphone — "
            f"c'est autant de clients potentiels qui repartent."
        )

    if any("formulaire" in i.lower() for i in prospect.issues):
        return (
            f"En parcourant le site de {prospect.name}, j'ai remarqué l'absence de formulaire de contact visible. "
            f"Des visiteurs intéressés ne savent pas comment vous joindre facilement — "
            f"et une partie repart sans laisser ses coordonnées."
        )

    cms = getattr(prospect, "cms", None)
    free_builders = {"Wix", "Jimdo", "Weebly", "Webnode"}
    if cms and cms in free_builders and any("gratuit" in i.lower() or "outil" in i.lower() or "builder" in i.lower() for i in prospect.issues):
        return (
            f"En visitant le site de {prospect.name}, j'ai constaté qu'il est construit avec {cms}. "
            f"Ces outils sont pratiques au départ, mais ils limitent sérieusement votre référencement naturel "
            f"et votre image professionnelle — et Google le sait."
        )

    if cms in {"WordPress", "Joomla", "Drupal", "PrestaShop"} and prospect.issues:
        return (
            f"En analysant le site de {prospect.name} (construit sous {cms}), "
            f"j'ai identifié {len(prospect.issues)} point(s) qui pénalisent votre visibilité "
            f"et votre taux de conversion."
        )

    if any("tracking" in i.lower() or "analytics" in i.lower() for i in prospect.issues):
        return (
            f"En analysant le site de {prospect.name}, j'ai constaté l'absence d'outils de mesure "
            f"(Google Analytics, etc.). Sans données, impossible de savoir d'où viennent vos visiteurs "
            f"ni quelles actions ils réalisent — tout investissement marketing devient aveugle."
        )

    # Accroche générique si aucun cas précis
    n = len(prospect.issues)
    return (
        f"En analysant la présence en ligne de {prospect.name}, "
        f"j'ai identifié {n} {_pluriel(n, 'point')} qui {_pluriel(n, 'freine', 'freinent')} "
        f"votre visibilité et vos conversions."
    )


# ---------------------------------------------------------------------------
# Corps du mail — bloc problèmes
# ---------------------------------------------------------------------------

def _build_issues_block(prospect: Prospect) -> str:
    issues = prospect.issues
    n = len(issues)

    if n == 0:
        return ""

    if n == 1:
        short = issues[0].split("→")[0].strip()
        detail = issues[0].split("→")[1].strip() if "→" in issues[0] else ""
        block = f"Le point que j'ai noté :\n  • {short}"
        if detail:
            block += f" — {detail}"
        return block

    top = issues[:3]
    label = f"Les {_pluriel(n, 'point principal', 'points principaux')} que j'ai notés :"
    lines = [label]
    for issue in top:
        short = issue.split("→")[0].strip()
        lines.append(f"  • {short}")
    if n > 3:
        lines.append(f"  • … et {n - 3} autre{_pluriel(n - 3, '')} point{_pluriel(n - 3, '')} détecté{_pluriel(n - 3, '')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CTA (appel à l'action)
# ---------------------------------------------------------------------------

def _build_cta(prospect: Prospect) -> str:
    offer = os.getenv("YOUR_OFFER", "").strip()
    n = len(prospect.issues)

    if not prospect.has_website():
        base = (
            "Je serais ravi de vous montrer en 15 minutes ce qu'un site simple, rapide et bien référencé "
            "peut apporter concrètement à votre activité — sans engagement."
        )
    elif n >= 4:
        base = (
            "Je vous propose un audit complet de votre site, gratuit et sans engagement. "
            "Vous repartez avec une feuille de route claire des actions prioritaires à mettre en place."
        )
    elif n >= 2:
        base = (
            "Je serais heureux de vous partager un retour détaillé (gratuit, sans engagement) "
            "avec les corrections à apporter en priorité."
        )
    else:
        base = (
            "Je peux vous proposer une correction rapide de ce point "
            "— sans engagement, avec un résultat visible en quelques jours."
        )

    if offer:
        return f"{base}\n\n({offer})"
    return base


# ---------------------------------------------------------------------------
# Template B — ton court et direct, accroche chiffrée
# ---------------------------------------------------------------------------

def _draft_email_b(prospect: Prospect) -> str:
    """Variante B : email plus court, ton direct, chiffres mis en avant."""
    n = len(prospect.issues)
    cms = getattr(prospect, "cms", None)

    if not prospect.has_website():
        subject = f"Site web pour {prospect.name} ?"
        body_lines = [
            "Bonjour,",
            "",
            f"Votre établissement n'apparaît pas avec de site web sur Google.",
            "En moyenne, les commerces avec un site reçoivent 70 % de contacts supplémentaires.",
            "",
            "Je crée des sites efficaces en moins de 2 semaines. Ça vous intéresse ?",
        ]
    elif any("inaccessible" in i for i in prospect.issues):
        subject = f"Votre site est down — {prospect.name}"
        body_lines = [
            "Bonjour,",
            "",
            f"Votre site est actuellement inaccessible.",
            "Chaque heure perdue, c'est un client qui va chez un concurrent.",
            "",
            "15 minutes suffisent pour faire le point. Disponible cette semaine ?",
        ]
    else:
        cms_mention = f" (construit sous {cms})" if cms else ""
        top = prospect.issues[0].split("→")[0].strip().lower() if prospect.issues else "votre présence en ligne"
        subject = f"Question rapide — {prospect.name}"
        body_lines = [
            "Bonjour,",
            "",
            f"J'ai analysé votre site{cms_mention} et relevé {n} point(s) qui vous coûtent des clients :",
            f"→ {top}",
        ]
        if n > 1:
            second = prospect.issues[1].split("→")[0].strip().lower()
            body_lines.append(f"→ {second}")
        body_lines += [
            "",
            "Je peux vous montrer en 15 min comment corriger ça, sans engagement.",
            "Disponible cette semaine ?",
        ]

    signature_parts = [config.your_name, config.your_title]
    if config.your_email:
        signature_parts.append(config.your_email)
    signature = "\n".join(filter(None, signature_parts))

    body = "\n".join(body_lines)
    return f"OBJET : {subject}\n\n{body}\n\n{signature}".strip()


# ---------------------------------------------------------------------------
# Construction finale — dispatche vers A ou B
# ---------------------------------------------------------------------------

def _draft_email_a(prospect: Prospect) -> str:
    """Template A (original) — accroche narrative, argumentée."""
    n_issues = len(prospect.issues)
    subject = _build_subject(prospect, n_issues)
    hook = _build_hook(prospect)
    issues_block = _build_issues_block(prospect)
    cta = _build_cta(prospect)

    signature_parts = [config.your_name, config.your_title]
    if config.your_website:
        signature_parts.append(config.your_website)
    if config.your_email:
        signature_parts.append(config.your_email)
    signature = "\n".join(filter(None, signature_parts))

    parts = [f"OBJET : {subject}", "", "Bonjour,", "", hook]
    if issues_block:
        parts += ["", issues_block]
    parts += ["", cta, ""]
    parts += [
        "Un simple échange de 15 minutes suffit — et si je ne peux pas vous aider, je vous le dirai franchement.",
        "",
        "Seriez-vous disponible cette semaine ou la semaine prochaine ?",
        "",
        "Bonne journée,",
        "",
        signature,
    ]
    return "\n".join(parts).strip()


def draft_email(prospect: Prospect, style: "EmailStyle | None" = None) -> str:
    """Dispatche vers le template A ou B selon le hash du place_id (test A/B 50/50).
    Si `style` est fourni, utilise build_dynamic_email à la place des templates A/B."""
    if style is not None:
        return build_dynamic_email(
            prospect,
            style,
            your_name=config.your_name,
            your_title=config.your_title,
            your_offer=os.getenv("YOUR_OFFER", "").strip(),
        )
    variant = get_template_variant(prospect.place_id)
    return _draft_email_b(prospect) if variant == "B" else _draft_email_a(prospect)


def enrich_with_email(prospect: Prospect) -> Prospect:
    prospect.email_draft = draft_email(prospect)
    variant = get_template_variant(prospect.place_id)
    logger.debug("  ✉️  Brouillon [template %s] généré pour %s.", variant, prospect.name)
    return prospect


# ---------------------------------------------------------------------------
# Email de relance
# ---------------------------------------------------------------------------

def draft_followup_email(prospect: Prospect) -> str:
    """
    Email de relance court envoyé ~5 jours après le premier contact sans réponse.
    Ton plus direct, recentré sur le problème principal.
    """
    name = prospect.name

    if not prospect.has_website():
        issue_context = "l'absence de site web pour votre établissement"
    elif prospect.issues:
        issue_context = prospect.issues[0].split("→")[0].strip().lower()
    else:
        issue_context = "votre présence en ligne"

    subject = f"{name} — suite à mon message"

    signature_parts = [config.your_name, config.your_title]
    if config.your_email:
        signature_parts.append(config.your_email)
    signature = "\n".join(filter(None, signature_parts))

    parts = [
        f"OBJET : {subject}",
        "",
        "Bonjour,",
        "",
        f"Je me permets de revenir vers vous suite à mon message de la semaine dernière "
        f"concernant {issue_context}.",
        "",
        "Je sais que votre agenda est chargé — si vous n'êtes pas intéressé(e), "
        "un simple retour suffit et je n'insisterai pas.",
        "",
        "Sinon, 15 minutes suffisent pour faire le point ensemble, sans engagement.",
        "",
        "Bonne journée,",
        "",
        signature,
    ]
    return "\n".join(parts).strip()


def enrich_with_followup(prospect: Prospect) -> Prospect:
    """Remplace le brouillon existant par un email de relance."""
    prospect.email_draft = draft_followup_email(prospect)
    logger.debug("  🔄 Email de relance généré pour %s.", prospect.name)
    return prospect
