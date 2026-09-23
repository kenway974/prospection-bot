"""
services/linkedin.py — Prospection LinkedIn ASSISTÉE (jamais automatisée).

L'app ne se connecte pas à LinkedIn et n'envoie rien : automatiser LinkedIn
viole ses conditions d'utilisation et fait restreindre les comptes. Ici on
prépare tout pour que l'envoi prenne ~30 s à la main :
  1. un lien de recherche qui ouvre directement le bon profil ;
  2. un message personnalisé prêt à copier ;
  3. un suivi dans le CRM une fois envoyé.

Contraintes LinkedIn (2026) :
  - note de connexion : 300 caractères max ;
  - comptes gratuits : ~5 notes personnalisées / mois ;
  - les notes de 120 à 180 caractères sont les mieux acceptées.
→ Stratégie par défaut : note courte (ou invitation sans note), et le vrai
  message une fois la connexion acceptée.
"""

from __future__ import annotations

import re
from typing import Dict, Optional
from urllib.parse import quote_plus

NOTE_MAX_CHARS = 300          # limite dure LinkedIn
NOTE_IDEAL_MIN = 120          # zone la mieux acceptée
NOTE_IDEAL_MAX = 180
MESSAGE_MAX_CHARS = 8000      # limite d'un message LinkedIn classique

# Types de modèles
TPL_NOTE_FREELANCE = "note_freelance"
TPL_MSG_FREELANCE  = "msg_freelance"
TPL_NOTE_SERVICE   = "note_service"
TPL_MSG_SERVICE    = "msg_service"

TEMPLATE_LABELS: Dict[str, str] = {
    TPL_NOTE_FREELANCE: "Note de connexion — candidature freelance (ESN, agences, startups)",
    TPL_MSG_FREELANCE:  "1er message après acceptation — candidature freelance",
    TPL_NOTE_SERVICE:   "Note de connexion — proposition de service (site, appli…)",
    TPL_MSG_SERVICE:    "1er message après acceptation — proposition de service",
}

# Modèles par défaut : courts, directs, une seule demande. Variables :
# {prenom} {entreprise} {mon_prenom} {mon_titre} {mon_site}
DEFAULT_TEMPLATES: Dict[str, str] = {
    TPL_NOTE_FREELANCE: (
        "Bonjour {prenom}, dev fullstack freelance, je renforce les équipes tech "
        "sur des missions ponctuelles. Ravi d'échanger si {entreprise} a besoin de bras !"
    ),
    TPL_MSG_FREELANCE: (
        "Merci pour la connexion {prenom} !\n\n"
        "Je suis {mon_prenom}, développeur fullstack freelance. J'interviens en renfort "
        "quand les équipes débordent : une feature à livrer, un projet client en plus, "
        "une dette technique à résorber.\n\n"
        "Si {entreprise} a ce genre de besoin en ce moment ou dans les prochains mois, "
        "je peux vous envoyer mon profil et 2-3 réalisations.\n\n"
        "{mon_site}"
    ),
    TPL_NOTE_SERVICE: (
        "Bonjour {prenom}, j'ai regardé la présence en ligne de {entreprise} et j'ai "
        "une idée concrète pour vous amener plus de clients. Au plaisir d'échanger !"
    ),
    TPL_MSG_SERVICE: (
        "Merci pour la connexion {prenom} !\n\n"
        "Je suis {mon_prenom}, développeur web. En regardant {entreprise}, j'ai repéré "
        "2-3 points simples qui vous font perdre des demandes de clients.\n\n"
        "Je peux vous les envoyer en quelques lignes, sans engagement. Ça vous intéresse ?\n\n"
        "{mon_site}"
    ),
}


def _first_name(full: str) -> str:
    return (full or "").strip().split(" ")[0] if full else ""


def render(template: str, *, dirigeant: str = "", entreprise: str = "",
           mon_nom: str = "", mon_titre: str = "", mon_site: str = "") -> str:
    """
    Remplit un modèle. Sans prénom connu, « Bonjour {prenom}, » devient
    « Bonjour, » plutôt que « Bonjour , » : jamais de trou visible.
    """
    prenom = _first_name(dirigeant)
    values = {
        "prenom": prenom,
        "entreprise": entreprise or "votre entreprise",
        "mon_prenom": _first_name(mon_nom) or mon_nom,
        "mon_titre": mon_titre,
        "mon_site": mon_site,
    }
    text = template
    for key, val in values.items():
        text = text.replace("{" + key + "}", val)
    # Nettoyage si le prénom est inconnu, en respectant la typographie française :
    #   « Bonjour , » → « Bonjour, »   et   « connexion  ! » → « connexion ! »
    text = re.sub(r"(Bonjour|Merci pour la connexion)\s+,", r"\1,", text)
    text = re.sub(r"(Bonjour|Merci pour la connexion)\s+!", r"\1 !", text)
    # Lignes vides en fin (ex. {mon_site} vide)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def note_verdict(text: str) -> tuple:
    """(niveau, message) pour guider la longueur d'une note de connexion."""
    n = len(text)
    if n > NOTE_MAX_CHARS:
        return "error", f"{n}/{NOTE_MAX_CHARS} — trop long, LinkedIn la refusera"
    if NOTE_IDEAL_MIN <= n <= NOTE_IDEAL_MAX:
        return "ok", f"{n}/{NOTE_MAX_CHARS} — longueur idéale ({NOTE_IDEAL_MIN}-{NOTE_IDEAL_MAX})"
    if n < NOTE_IDEAL_MIN:
        return "warn", f"{n}/{NOTE_MAX_CHARS} — un peu court, vise {NOTE_IDEAL_MIN}-{NOTE_IDEAL_MAX}"
    return "warn", f"{n}/{NOTE_MAX_CHARS} — OK, mais {NOTE_IDEAL_MIN}-{NOTE_IDEAL_MAX} est mieux accepté"


def people_search_url(entreprise: str, dirigeant: str = "", role: str = "") -> str:
    """
    Lien de recherche LinkedIn :
      - dirigeant connu → « Jean Dupont ESN Alpha » (tombe en général pile dessus)
      - sinon rôle → « CTO ESN Alpha »
    """
    who = dirigeant.strip() if dirigeant else (role or "").strip()
    query = f"{who} {entreprise}".strip()
    return f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(query)}"


def company_search_url(entreprise: str) -> str:
    return f"https://www.linkedin.com/search/results/companies/?keywords={quote_plus(entreprise.strip())}"


def default_templates_for(candidacy: bool) -> tuple:
    """(clé note, clé message) selon le mode (candidature freelance ou service)."""
    if candidacy:
        return TPL_NOTE_FREELANCE, TPL_MSG_FREELANCE
    return TPL_NOTE_SERVICE, TPL_MSG_SERVICE


# Rôles à chercher quand le dirigeant ne suffit pas (Sirène ne les connaît pas)
TECH_ROLES = ["CTO", "Directeur technique", "Head of Engineering", "Product Owner", "Lead developer"]


def get_template(key: str, overrides: Optional[Dict[str, str]] = None) -> str:
    """Modèle personnalisé s'il existe, sinon celui par défaut."""
    if overrides and overrides.get(key, "").strip():
        return overrides[key]
    return DEFAULT_TEMPLATES[key]
