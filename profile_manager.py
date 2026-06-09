"""
profile_manager.py — Sauvegarde et chargement des profils personnalisés.

Les profils prédéfinis sont dans profiles.py (non modifiables).
Les profils custom créés depuis l'UI sont stockés dans profiles_custom.json
et rechargés automatiquement au prochain lancement.

Fonctions exposées :
  - get_all_profiles()      → tous les profils (prédéfinis + custom)
  - save_custom_profile()   → crée ou met à jour un profil custom
  - delete_custom_profile() → supprime un profil custom
  - load_custom_profiles()  → charge uniquement les profils custom
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import List

from profiles import Profile, PROFILES

CUSTOM_PROFILES_FILE = "profiles_custom.json"


def load_custom_profiles() -> List[Profile]:
    """Charge les profils sauvegardés depuis profiles_custom.json."""
    if not os.path.exists(CUSTOM_PROFILES_FILE):
        return []
    try:
        with open(CUSTOM_PROFILES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [Profile(**p) for p in data]
    except Exception:
        return []


def save_custom_profile(profile: Profile) -> None:
    """
    Sauvegarde un profil custom.
    Si un profil avec le même id existe déjà, il est remplacé (mise à jour).
    """
    profiles = load_custom_profiles()
    existing_ids = [p.id for p in profiles]
    if profile.id in existing_ids:
        profiles = [profile if p.id == profile.id else p for p in profiles]
    else:
        profiles.append(profile)

    with open(CUSTOM_PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in profiles], f, ensure_ascii=False, indent=2)


def delete_custom_profile(profile_id: str) -> None:
    """Supprime un profil custom par son id. Sans effet si l'id n'existe pas."""
    profiles = [p for p in load_custom_profiles() if p.id != profile_id]
    with open(CUSTOM_PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in profiles], f, ensure_ascii=False, indent=2)


def get_all_profiles() -> List[Profile]:
    """
    Retourne la liste complète des profils disponibles.
    Les profils custom écrasent les prédéfinis si même id.
    Ordre : prédéfinis non écrasés → custom.
    """
    custom = load_custom_profiles()
    custom_ids = {p.id for p in custom}
    base = [p for p in PROFILES if p.id not in custom_ids]
    return base + custom
