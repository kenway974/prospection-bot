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

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : lire / écrire les profils personnalisés dans un fichier JSON sur le disque,
# 📘   et les fusionner avec les profils prédéfinis de profiles.py.
# 📘 Appelé par : app.py (uniquement save_custom_profile, bouton « 💾 Sauvegarder ce
# 📘   profil » de la page Prospection), tests/test_profiles.py (toutes les fonctions).
# 📘 Appelle : profiles.py (classe Profile, liste PROFILES), modules standard json / os.
# 📘 Concepts Python à retenir ici : lecture/écriture de fichier avec `with open(...)`,
# 📘   json.load / json.dump, try/except, list comprehension, set comprehension,
# 📘   `**dict` (dépaquetage), dataclasses.asdict.
# 💡 Personne ne RELIT ces profils : get_all_profiles() n'est appelée que par les tests, alors
# 💡   que l'UI annonce « Il apparaîtra dans la liste au prochain lancement ». Soit brancher
# 💡   un sélecteur « Mes profils » qui recharge ville/mots-clés/pitch, soit retirer le bouton.

# 📘 Chemin RELATIF : le fichier est créé dans le dossier depuis lequel tu lances l'app
# 📘   (le « répertoire courant »), pas forcément à côté de ce .py. Il est dans .gitignore.
# 💡 Construire un chemin absolu (ex. à partir de Path(__file__).parent ou d'un dossier data/
# 💡   configurable) éviterait de « perdre » ses profils en lançant l'app d'ailleurs, et
# 💡   faciliterait un volume persistant en déploiement (Docker, etc.).
CUSTOM_PROFILES_FILE = "profiles_custom.json"


def load_custom_profiles() -> List[Profile]:
    """Charge les profils sauvegardés depuis profiles_custom.json."""
    # 📘 Pas de fichier = aucun profil custom encore : on renvoie une liste vide [].
    if not os.path.exists(CUSTOM_PROFILES_FILE):
        return []
    # 📘 try/except : si une erreur survient dans le bloc `try`, Python saute dans `except`
    # 📘   au lieu de planter. Ici : fichier JSON corrompu → on fait comme s'il était vide.
    try:
        # 📘 `with open(...) as f` ouvre le fichier et le REFERME automatiquement à la fin
        # 📘   du bloc, même en cas d'erreur. "r" = lecture ; encoding utf-8 pour les accents.
        with open(CUSTOM_PROFILES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)  # 📘 texte JSON → objets Python (ici une liste de dicts)
        # 📘 LIST COMPREHENSION : [expression for p in data] fabrique une nouvelle liste.
        # 📘 `Profile(**p)` : `**` « déplie » le dict p en arguments nommés, donc
        # 📘   {"id": "x", "name": "y"} devient Profile(id="x", name="y").
        return [Profile(**p) for p in data]
    # 📘 `except Exception` attrape toutes les erreurs « normales ». Pratique mais silencieux :
    # 📘   un champ en trop dans le JSON ferait disparaître TOUS les profils sans message.
    except Exception:
        return []


def save_custom_profile(profile: Profile) -> None:
    """
    Sauvegarde un profil custom.
    Si un profil avec le même id existe déjà, il est remplacé (mise à jour).
    """
    # 📘 Stratégie simple « tout relire, modifier en mémoire, tout réécrire ».
    profiles = load_custom_profiles()
    existing_ids = [p.id for p in profiles]
    # 📘 `x in liste` teste la présence d'un élément.
    if profile.id in existing_ids:
        # 📘 Comprehension avec condition ternaire `A if cond else B` : on remplace
        # 📘   l'ancien profil de même id par le nouveau, on garde les autres tels quels.
        profiles = [profile if p.id == profile.id else p for p in profiles]
    else:
        profiles.append(profile)  # 📘 .append() ajoute un élément à la fin de la liste

    # 📘 "w" = écriture : le fichier est ÉCRASÉ entièrement. asdict() convertit chaque objet
    # 📘   dataclass en dict (sérialisable en JSON). ensure_ascii=False garde les accents
    # 📘   lisibles, indent=2 rend le fichier joliment indenté.
    # 📘 Si le programme plante pendant l'écriture, le fichier peut rester à moitié écrit.
    with open(CUSTOM_PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in profiles], f, ensure_ascii=False, indent=2)


def delete_custom_profile(profile_id: str) -> None:
    """Supprime un profil custom par son id. Sans effet si l'id n'existe pas."""
    # 📘 On « supprime » en reconstruisant la liste sans l'élément visé (filtre `if`).
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
    # 📘 Accolades + for = SET comprehension : un `set` est un ensemble sans doublons, dont
    # 📘   le test `in` est très rapide (contrairement à une liste qu'il faut parcourir).
    custom_ids = {p.id for p in custom}
    base = [p for p in PROFILES if p.id not in custom_ids]
    # 📘 `liste1 + liste2` crée une nouvelle liste qui met bout à bout les deux.
    return base + custom
