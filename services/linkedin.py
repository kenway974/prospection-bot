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

# 📘 re = expressions régulières (motifs de recherche/remplacement dans du texte).
# 📘 typing.Dict / Optional : annotations de type ("dict de str vers str", "peut valoir None").
# 📘 quote_plus : encode un texte pour qu'il soit valide dans une URL (espace → "+", é → %C3%A9).
import re
from typing import Dict, Optional
from urllib.parse import quote_plus

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : préparer la prospection LinkedIn MANUELLE : liens de recherche vers le bon
# 📘         profil, notes/messages pré-remplis, contrôle de longueur. Rien n'est envoyé ici.
# 📘 Appelé par : app.py (onglet LinkedIn + réglages des modèles) et tests/test_linkedin.py.
# 📘 Appelle : aucun service externe — uniquement de la manipulation de texte et d'URL.
# 📘 Concepts Python à retenir ici : constantes, dict de templates, concaténation de
# 📘   chaînes entre parenthèses, arguments "keyword-only" (`*`), re.sub, f-string,
# 📘   tuple en retour, quote_plus.
#
# 📘 POURQUOI "assisté" et pas automatisé : un robot qui se connecte à LinkedIn enfreint
# 📘 leurs CGU et fait bannir le compte. Choix de conception volontaire et sain.
NOTE_MAX_CHARS = 300          # limite dure LinkedIn
NOTE_IDEAL_MIN = 120          # zone la mieux acceptée
NOTE_IDEAL_MAX = 180
MESSAGE_MAX_CHARS = 8000      # limite d'un message LinkedIn classique

# Types de modèles
# 📘 Des constantes texte servent de "clés" : on écrit TPL_NOTE_FREELANCE partout au lieu
# 📘 de "note_freelance", ainsi une faute de frappe devient une erreur visible.
TPL_NOTE_FREELANCE = "note_freelance"
TPL_MSG_FREELANCE  = "msg_freelance"
TPL_NOTE_SERVICE   = "note_service"
TPL_MSG_SERVICE    = "msg_service"

# 📘 `Dict[str, str]` : annotation qui dit "dictionnaire dont clés et valeurs sont des str".
# 📘 Ces libellés sont affichés dans l'interface Streamlit.
TEMPLATE_LABELS: Dict[str, str] = {
    TPL_NOTE_FREELANCE: "Note de connexion — candidature freelance (ESN, agences, startups)",
    TPL_MSG_FREELANCE:  "1er message après acceptation — candidature freelance",
    TPL_NOTE_SERVICE:   "Note de connexion — proposition de service (site, appli…)",
    TPL_MSG_SERVICE:    "1er message après acceptation — proposition de service",
}

# Modèles par défaut : courts, directs, une seule demande. Variables :
# {prenom} {entreprise} {mon_prenom} {mon_titre} {mon_site}
DEFAULT_TEMPLATES: Dict[str, str] = {
    # 📘 Des chaînes écrites côte à côte entre parenthèses sont COLLÉES automatiquement par
    # 📘 Python : c'est une façon lisible d'écrire un long texte sur plusieurs lignes.
    # 📘 "\n\n" = deux retours à la ligne (un paragraphe vide).
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


# 📘 Récupère le prénom : "Jean Dupont" → "Jean". `(full or "")` protège contre None.
def _first_name(full: str) -> str:
    return (full or "").strip().split(" ")[0] if full else ""


# 📘 Le `*` dans la signature force les arguments suivants à être passés PAR NOM :
# 📘 render(tpl, dirigeant="Jean Dupont") marche, render(tpl, "Jean Dupont") échoue.
# 📘 Ça évite de mélanger l'ordre de 5 paramètres texte.
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
    # 📘 On remplace chaque {cle} à la main (str.replace) plutôt qu'avec .format() :
    # 📘 un modèle personnalisé contenant une accolade inconnue ne fera donc pas planter.
    text = template
    for key, val in values.items():
        text = text.replace("{" + key + "}", val)
    # Nettoyage si le prénom est inconnu, en respectant la typographie française :
    #   « Bonjour , » → « Bonjour, »   et   « connexion  ! » → « connexion ! »
    # 📘 re.sub(motif, remplacement, texte) : \s+ = un ou plusieurs espaces ; (…) capture un
    # 📘 groupe que \1 réinjecte dans le remplacement.
    text = re.sub(r"(Bonjour|Merci pour la connexion)\s+,", r"\1,", text)
    text = re.sub(r"(Bonjour|Merci pour la connexion)\s+!", r"\1 !", text)
    # Lignes vides en fin (ex. {mon_site} vide)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# 📘 Renvoie un tuple (niveau, message) ; l'UI s'en sert pour afficher une alerte colorée
# 📘 (erreur / ok / avertissement) sous la zone de texte.
def note_verdict(text: str) -> tuple:
    """(niveau, message) pour guider la longueur d'une note de connexion."""
    n = len(text)
    # 📘 `A <= n <= B` : comparaison chaînée, Python la lit comme "A <= n et n <= B".
    if n > NOTE_MAX_CHARS:
        return "error", f"{n}/{NOTE_MAX_CHARS} — trop long, LinkedIn la refusera"
    if NOTE_IDEAL_MIN <= n <= NOTE_IDEAL_MAX:
        return "ok", f"{n}/{NOTE_MAX_CHARS} — longueur idéale ({NOTE_IDEAL_MIN}-{NOTE_IDEAL_MAX})"
    if n < NOTE_IDEAL_MIN:
        return "warn", f"{n}/{NOTE_MAX_CHARS} — un peu court, vise {NOTE_IDEAL_MIN}-{NOTE_IDEAL_MAX}"
    return "warn", f"{n}/{NOTE_MAX_CHARS} — OK, mais {NOTE_IDEAL_MIN}-{NOTE_IDEAL_MAX} est mieux accepté"


# 📘 Construit un lien de recherche de personnes sur LinkedIn : l'utilisateur clique,
# 📘 LinkedIn s'ouvre sur les résultats, il choisit le bon profil lui-même.
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


# 📘 Liste de rôles techniques proposés comme liens de recherche quand on veut viser
# 📘 le bon interlocuteur (Sirène = registre des entreprises, il ne liste que les dirigeants).
# Rôles à chercher quand le dirigeant ne suffit pas (Sirène ne les connaît pas)
TECH_ROLES = ["CTO", "Directeur technique", "Head of Engineering", "Product Owner", "Lead developer"]


# 📘 overrides = modèles personnalisés par l'utilisateur (sauvés dans le CRM local).
# 📘 `.get(key, "")` lit la clé sans erreur si elle est absente.
def get_template(key: str, overrides: Optional[Dict[str, str]] = None) -> str:
    """Modèle personnalisé s'il existe, sinon celui par défaut."""
    if overrides and overrides.get(key, "").strip():
        return overrides[key]
    # 💡 Enregistrer la date d'envoi de la note puis de l'acceptation (dans le CRM) permettrait
    # 💡 de rappeler automatiquement d'envoyer le "1er message" X jours après la connexion.
    # 💡 Autre piste qualité : utiliser string.Template ou un moteur comme Jinja2 si les
    # 💡 modèles se complexifient (conditions, boucles), avec validation des variables inconnues.
    return DEFAULT_TEMPLATES[key]
