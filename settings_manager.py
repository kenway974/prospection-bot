"""
Persistance locale des paramètres de la sidebar.

Sauvegarde dans output/settings.json à chaque lancement.
Chargés comme valeurs par défaut au prochain démarrage — les env vars
Railway restent supportées mais ne sont plus obligatoires.

Note : le mot de passe Gmail n'est jamais sauvegardé (entré chaque session
ou configuré via la variable d'env GMAIL_APP_PASSWORD sur Railway).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

_SETTINGS_FILE = os.path.join("output", "settings.json")


def load_settings() -> Dict[str, Any]:
    """Charge les paramètres sauvegardés. Retourne un dict vide si absent."""
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(settings: Dict[str, Any]) -> None:
    """Sauvegarde les paramètres (merge avec l'existant)."""
    os.makedirs("output", exist_ok=True)
    current = load_settings()
    current.update({k: v for k, v in settings.items() if v is not None})
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
