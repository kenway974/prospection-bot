"""
history_manager.py — Historique des campagnes + suivi des relances.

Deux fichiers persistés dans output/ :
  - history.json              → statistiques de chaque run (max 50)
  - contacted_place_ids.json  → prospects déjà traités avec infos de relance

Format de contacted_place_ids.json :
  {
    "place_id": {
      "name": "Boulangerie Martin",
      "email": "contact@boulangerie.fr",
      "first_contact_date": "2026-06-09",
      "responded": false,
      "followup_sent": false
    }
  }

Fonctions exposées :
  - save_run()           → enregistre les stats d'un run
  - load_history()       → retourne la liste des runs (du plus récent au plus ancien)
  - load_contacted_ids() → retourne le set des place_id déjà traités
  - mark_as_contacted()  → enregistre les prospects contactés avec date + infos
  - get_due_followups()  → retourne les contacts à relancer (N jours sans réponse)
  - mark_as_responded()  → marque un contact comme ayant répondu
  - mark_followup_sent() → marque qu'une relance a été envoyée
"""

from __future__ import annotations

import functools
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Dict, List, Optional

from safe_files import file_lock, is_readable_json, read_json_with_recovery, set_aside, write_json_atomic

if TYPE_CHECKING:
    from services.google_maps import Prospect

HISTORY_FILE          = os.path.join("output", "history.json")
CONTACTED_FILE        = os.path.join("output", "contacted_place_ids.json")
CONTACTED_BACKUP_FILE = os.path.join("output", "contacted_place_ids.bak.json")


class HistoryFileError(RuntimeError):
    """Le fichier des contacts ET sa copie sont illisibles : on s'arrête plutôt que de tout recontacter."""


def _ensure_output() -> None:
    os.makedirs("output", exist_ok=True)


# ---------------------------------------------------------------------------
# Fonctions internes — gestion du fichier contacted_place_ids.json
# ---------------------------------------------------------------------------

# Nombre maximal de relances de la séquence (après le 1er contact).
MAX_FOLLOWUPS = 4


def _migrate(data) -> dict:
    """Migre depuis l'ancien format (liste de place_id strings)."""
    if isinstance(data, list):
        return {
            pid: {
                "name": "",
                "email": "",
                "first_contact_date": "",
                "responded": False,
                "followup_sent": False,
                "followup_step": 0,
                "last_contact_date": "",
            }
            for pid in data
        }
    return data


def _followup_step(info: dict) -> int:
    """Étape de relance courante, avec compat de l'ancien champ booléen."""
    if "followup_step" in info:
        try:
            return int(info["followup_step"])
        except (TypeError, ValueError):
            return 0
    # Ancien format : followup_sent booléen → 1 relance envoyée si True
    return 1 if info.get("followup_sent") else 0


def _load_contacted_data() -> dict:
    """
    Charge le dict complet des prospects contactés.

    - fichier absent → copie restaurée si elle existe, sinon personne n'a encore été contacté ({}) ;
    - fichier illisible mais copie de secours lisible → la copie est restaurée
      automatiquement (le fichier abîmé est gardé en .corrupt, un avertissement s'affiche) ;
    - fichier ET copie illisibles → HistoryFileError : on s'arrête plutôt que de tout
      recontacter, sans modifier aucun fichier.
    """
    _ensure_output()
    try:
        data = read_json_with_recovery(
            CONTACTED_FILE, "Fichier des contacts", backup=CONTACTED_BACKUP_FILE, default={},
        )
        return _migrate(data)
    except OSError as exc:
        raise HistoryFileError(
            f"Impossible de lire le fichier des contacts ({CONTACTED_FILE}) : {exc}. Il est "
            "peut-être verrouillé (antivirus, synchronisation) ou protégé. Aucun fichier n'a été "
            "modifié : réessayez dans un instant."
        ) from exc
    except ValueError as exc:
        raise HistoryFileError(
            f"Fichier des contacts illisible ({CONTACTED_FILE}) : {exc}. "
            f"Et aucune copie de secours lisible ({CONTACTED_BACKUP_FILE} absent ou abîmé). "
            "Le bot s'arrête pour ne recontacter personne, et aucun fichier n'a été modifié. "
            "Que faire : ouvrez ces fichiers, réparez le JSON (ou remplacez le fichier par une "
            "sauvegarde à vous), puis relancez. Marche à suivre détaillée : MANUEL.md, "
            "section « Fichier abîmé »."
        ) from exc


def _save_contacted_data(data: dict) -> None:
    """Écriture atomique ; la version précédente lisible est gardée dans CONTACTED_BACKUP_FILE."""
    _ensure_output()
    write_json_atomic(CONTACTED_FILE, data, backup=CONTACTED_BACKUP_FILE)


# ---------------------------------------------------------------------------
# API publique — contacts
# ---------------------------------------------------------------------------

def load_contacted_ids() -> set:
    """Retourne le set des place_id déjà traités."""
    return set(_load_contacted_data().keys())


def get_ab_stats() -> Dict[str, Dict[str, int]]:
    """Retourne les stats A/B : {variant: {total, responded}} pour chaque template."""
    data = _load_contacted_data()
    stats: Dict[str, Dict[str, int]] = {"A": {"total": 0, "responded": 0}, "B": {"total": 0, "responded": 0}}
    for info in data.values():
        variant = info.get("email_template", "A")
        if variant not in stats:
            stats[variant] = {"total": 0, "responded": 0}
        stats[variant]["total"] += 1
        if info.get("responded"):
            stats[variant]["responded"] += 1
    return stats


def _locked_contacts(func):
    """Une seule modification du fichier des contacts à la fois (interface, CLI, envois programmés)."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with file_lock(CONTACTED_FILE):
            return func(*args, **kwargs)
    return wrapper


@_locked_contacts
def mark_as_contacted(prospects: List[Prospect], notion_page_ids: Dict[str, str] | None = None) -> None:
    """
    Enregistre les prospects contactés avec leur date de premier contact.
    Les prospects déjà présents ne sont pas écrasés (on garde la date initiale).
    """
    from services.mailer import get_template_variant
    data = _load_contacted_data()
    today = datetime.now().strftime("%Y-%m-%d")
    for p in prospects:
        if p.place_id not in data:
            entry = {
                "name": p.name,
                "email": p.email or "",
                "first_contact_date": today,
                "last_contact_date": today,
                "responded": False,
                "followup_sent": False,
                "followup_step": 0,
                "email_template": get_template_variant(p.place_id),
            }
            if notion_page_ids and p.place_id in notion_page_ids:
                entry["notion_page_id"] = notion_page_ids[p.place_id]
            data[p.place_id] = entry
    _save_contacted_data(data)


def get_notion_page_id(place_id: str) -> Optional[str]:
    """Retourne le page_id Notion stocké pour un prospect, ou None."""
    return _load_contacted_data().get(place_id, {}).get("notion_page_id")


def get_due_followups(delay_days: int = 5) -> List[dict]:
    """
    Retourne les contacts dont la PROCHAINE relance de la séquence est due :
    - n'ont pas répondu
    - n'ont pas déjà reçu les 4 relances
    - dernier message envoyé il y a au moins delay_days jours

    Chaque entrée contient le place_id, toutes les infos, et `followup_step`
    (nombre de relances déjà envoyées) pour savoir quelle relance générer ensuite.

    Les personnes qui ont dit STOP (par email ou par fiche Google, voir optout_manager)
    ne sont jamais relancées.
    """
    from optout_manager import filter_opted_out  # import local : évite une dépendance au chargement

    data = _load_contacted_data()
    cutoff = datetime.now() - timedelta(days=delay_days)
    due = []
    for place_id, info in data.items():
        if info.get("responded", False):
            continue
        step = _followup_step(info)
        if step >= MAX_FOLLOWUPS:
            continue
        # On se base sur la date du dernier message (relance ou 1er contact)
        date_str = info.get("last_contact_date") or info.get("first_contact_date", "")
        if not date_str:
            continue
        try:
            last_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if last_date <= cutoff:
            entry = {"place_id": place_id, **info}
            entry["followup_step"] = step  # normalise (compat ancien format)
            due.append(entry)

    contacts = [SimpleNamespace(place_id=d["place_id"], email=d.get("email")) for d in due]
    kept_ids = {c.place_id for c in filter_opted_out(contacts)[0]}
    return [d for d in due if d["place_id"] in kept_ids]


@_locked_contacts
def mark_as_responded(place_id: str) -> None:
    """Marque un prospect comme ayant répondu — il ne sera plus relancé."""
    data = _load_contacted_data()
    if place_id in data:
        data[place_id]["responded"] = True
        _save_contacted_data(data)


@_locked_contacts
def mark_followup_sent(place_id: str) -> None:
    """Incrémente l'étape de relance et enregistre la date du dernier message."""
    data = _load_contacted_data()
    if place_id in data:
        info = data[place_id]
        info["followup_step"] = min(_followup_step(info) + 1, MAX_FOLLOWUPS)
        info["followup_sent"] = True  # conservé pour compat
        info["last_contact_date"] = datetime.now().strftime("%Y-%m-%d")
        _save_contacted_data(data)


# ---------------------------------------------------------------------------
# API publique — historique des runs
# ---------------------------------------------------------------------------

def load_history() -> List[dict]:
    """
    Charge l'historique depuis output/history.json.
    Retourne une liste vide si le fichier n'existe pas encore.
    """
    _ensure_output()
    try:
        # Illisible ou absent + copie lisible → restauré automatiquement (voir safe_files)
        return read_json_with_recovery(HISTORY_FILE, "Historique des campagnes", default=[])
    except (OSError, ValueError):
        return []


def save_run(
    profile_name: str,
    location: str,
    keywords: List[str],
    total: int,
    no_site: int,
    emails_found: int,
    mobiles_found: int,
    output_file: str,
    emails_sent: int = 0,
    sms_sent: int = 0,
    crm_synced: int = 0,
    offer_types: Optional[Dict[str, int]] = None,
    sources: Optional[List[str]] = None,
    target_sector: str = "",
) -> None:
    """Enregistre les statistiques d'un run terminé (max 50 entrées conservées)."""
    _ensure_output()
    history = load_history()
    if not history and os.path.exists(HISTORY_FILE) and os.path.getsize(HISTORY_FILE) > 0:
        # Fichier présent, illisible et sans copie de secours : on le met de côté
        # (.corrupt, .corrupt.1…) au lieu de l'écraser
        if not is_readable_json(HISTORY_FILE):
            set_aside(HISTORY_FILE)
    history.insert(0, {
        "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "profile": profile_name,
        "location": location,
        "keywords": keywords,
        "total_prospects": total,
        "sans_site": no_site,
        "emails_trouvés": emails_found,
        "mobiles_trouvés": mobiles_found,
        "emails_envoyés": emails_sent,
        "sms_envoyés": sms_sent,
        "crm_synchronisés": crm_synced,
        "offer_types": offer_types or {},
        "sources": sources or [],
        "target_sector": target_sector,
        "fichier": output_file,
    })
    history = history[:50]
    write_json_atomic(HISTORY_FILE, history)
