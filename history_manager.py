"""
history_manager.py — Historique des campagnes de prospection.

Chaque lancement réussi est enregistré dans output/history.json.
L'historique est affiché dans l'interface Streamlit (section tout en bas).
Maximum 50 entrées conservées (les plus anciennes sont supprimées).

Fonctions exposées :
  - save_run()      → enregistre les stats d'un run
  - load_history()  → retourne la liste des runs (du plus récent au plus ancien)
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import List

HISTORY_FILE = os.path.join("output", "history.json")


def _ensure_output() -> None:
    """Crée le dossier output/ s'il n'existe pas."""
    os.makedirs("output", exist_ok=True)


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
    except Exception:
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
    """
    Enregistre les statistiques d'un run terminé.

    Paramètres :
      profile_name  → nom du profil utilisé (ex: "💻 Dev Web")
      location      → zone de recherche (ex: "Lyon, France")
      keywords      → liste des mots-clés utilisés
      total         → nombre total de prospects collectés
      no_site       → prospects sans site web
      emails_found  → prospects avec un email scrapé
      mobiles_found → prospects avec un numéro mobile (06/07)
      output_file   → chemin vers le fichier JSON de résultats
    """
    _ensure_output()
    history = load_history()
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
    # On garde les 50 derniers runs pour ne pas surcharger le fichier
    history = history[:50]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
