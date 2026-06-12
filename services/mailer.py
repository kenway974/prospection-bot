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

import os
from config import config, logger
from services.google_maps import Prospect


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
# Construction finale
# ---------------------------------------------------------------------------

def draft_email(prospect: Prospect) -> str:
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

    # Corps du mail
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


def enrich_with_email(prospect: Prospect) -> Prospect:
    prospect.email_draft = draft_email(prospect)
    logger.debug("  ✉️  Brouillon généré pour %s.", prospect.name)
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
