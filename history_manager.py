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

import json
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, List

from safe_files import read_json_with_recovery, write_json_atomic

if TYPE_CHECKING:
    from services.google_maps import Prospect

HISTORY_FILE   = os.path.join("output", "history.json")
CONTACTED_FILE = os.path.join("output", "contacted_place_ids.json")


class HistoryFileError(RuntimeError):
    """Le fichier des contacts existe mais est illisible : on s'arrête plutôt que de tout recontacter."""


def _ensure_output() -> None:
    os.makedirs("output", exist_ok=True)


# ---------------------------------------------------------------------------
# Fonctions internes — gestion du fichier contacted_place_ids.json
# ---------------------------------------------------------------------------

def _load_contacted_data() -> dict:
    """
    Charge le dict complet des prospects contactés.
    Gère la migration depuis l'ancien format (liste de place_id).
    """
    _ensure_output()
    if not os.path.exists(CONTACTED_FILE):
        return {}
    try:
        data = read_json_with_recovery(CONTACTED_FILE, "Fichier des contacts")
        # Migration depuis l'ancien format (liste de strings)
        if isinstance(data, list):
            return {
                pid: {
                    "name": "",
                    "email": "",
                    "first_contact_date": "",
                    "responded": False,
                    "followup_sent": False,
                }
                for pid in data
            }
        return data
    except (OSError, ValueError) as exc:
        raise HistoryFileError(
            f"Fichier des contacts illisible ({CONTACTED_FILE}) : {exc}. "
            "Le fichier n'a pas été modifié. Réparez-le (ou restaurez une copie) puis relancez : "
            "sinon tous les prospects déjà contactés seraient recontactés."
        ) from exc


def _save_contacted_data(data: dict) -> None:
    _ensure_output()
    write_json_atomic(CONTACTED_FILE, data)


# ---------------------------------------------------------------------------
# API publique — contacts
# ---------------------------------------------------------------------------

def load_contacted_ids() -> set:
    """Retourne le set des place_id déjà traités."""
    return set(_load_contacted_data().keys())


def mark_as_contacted(prospects: List[Prospect]) -> None:
    """
    Enregistre les prospects contactés avec leur date de premier contact.
    Les prospects déjà présents ne sont pas écrasés (on garde la date initiale).
    """
    data = _load_contacted_data()
    today = datetime.now().strftime("%Y-%m-%d")
    for p in prospects:
        if p.place_id not in data:
            data[p.place_id] = {
                "name": p.name,
                "email": p.email or "",
                "first_contact_date": today,
                "responded": False,
                "followup_sent": False,
            }
    _save_contacted_data(data)


def get_due_followups(delay_days: int = 5) -> List[dict]:
    """
    Retourne les contacts à relancer :
    - contactés il y a au moins delay_days jours
    - n'ont pas répondu
    - relance pas encore envoyée

    - n'ont pas demandé à ne plus être contactés (STOP, voir optout_manager)

    Chaque entrée retournée contient le place_id + toutes les infos.
    """
    from optout_manager import filter_opted_out  # import local : évite une dépendance au chargement

    data = _load_contacted_data()
    cutoff = datetime.now() - timedelta(days=delay_days)
    due = []
    for place_id, info in data.items():
        if info.get("responded", False):
            continue
        if info.get("followup_sent", False):
            continue
        date_str = info.get("first_contact_date", "")
        if not date_str:
            continue
        try:
            contact_date = datetime.strptime(date_str, "%Y-%m-%d")
            if contact_date <= cutoff:
                due.append({"place_id": place_id, **info})
        except ValueError:
            continue

    # Les refus (par email ou par fiche Google) ne sont jamais relancés
    contacts = [SimpleNamespace(place_id=d["place_id"], email=d.get("email")) for d in due]
    kept_ids = {c.place_id for c in filter_opted_out(contacts)[0]}
    return [d for d in due if d["place_id"] in kept_ids]


def mark_as_responded(place_id: str) -> None:
    """Marque un prospect comme ayant répondu — il ne sera plus relancé."""
    data = _load_contacted_data()
    if place_id in data:
        data[place_id]["responded"] = True
        _save_contacted_data(data)


def mark_followup_sent(place_id: str) -> None:
    """Marque qu'une relance a été envoyée pour ce prospect."""
    data = _load_contacted_data()
    if place_id in data:
        data[place_id]["followup_sent"] = True
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
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
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
) -> None:
    """Enregistre les statistiques d'un run terminé (max 50 entrées conservées)."""
    _ensure_output()
    history = load_history()
    if not history and os.path.exists(HISTORY_FILE) and os.path.getsize(HISTORY_FILE) > 0:
        # Fichier présent mais illisible : on le met de côté au lieu de l'écraser
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                json.load(f)
        except (OSError, ValueError):
            os.replace(HISTORY_FILE, HISTORY_FILE + ".corrupt")
    history.insert(0, {
        "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "profile": profile_name,
        "location": location,
        "keywords": keywords,
        "total_prospects": total,
        "sans_site": no_site,
        "emails_trouvés": emails_found,
        "mobiles_trouvés": mobiles_found,
        "fichier": output_file,
    })
    history = history[:50]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
