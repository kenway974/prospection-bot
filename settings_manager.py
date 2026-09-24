"""
Persistance locale des paramètres de la sidebar.

Sauvegarde dans output/settings.json à chaque lancement.
Chargés comme valeurs par défaut au prochain démarrage — les env vars
Railway restent supportées mais ne sont plus obligatoires.

Note : le mot de passe Gmail n'est jamais sauvegardé (entré chaque session
ou configuré via la variable d'env GMAIL_APP_PASSWORD sur Railway).
"""

# 📘 `from __future__ import annotations` : les annotations de type ne sont pas évaluées au
# 📘 chargement (permet d'écrire des types modernes même sur un Python un peu ancien).
from __future__ import annotations

# 📘 json : module standard pour convertir texte JSON <-> dict/list Python.
# 📘 Dict[str, Any] : "dictionnaire dont les clés sont du texte et les valeurs n'importe quoi".
import json
import os
from typing import Any, Dict

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : mémoriser les réglages de la barre latérale Streamlit dans output/settings.json,
# 📘   pour les retrouver pré-remplis au prochain lancement.
# 📘 Appelé par : app.py uniquement (load_settings au chargement ; save_settings via
# 📘   _persist_cfg à chaque modification d'un champ, et au lancement d'une campagne).
# 📘 ⚠️ Seul gmail_password est exclu (_SECRET_KEYS d'app.py). Les clés API (Google, Notion,
# 📘   HubSpot, Brevo, France Travail) sont bien écrites EN CLAIR dans settings.json.
# 💡 output/ est bien dans .gitignore (bon point), mais toute personne ayant accès au disque ou
# 💡   à une sauvegarde lit les clés. Mieux : secrets en variables d'environnement Railway seules.
# 📘 Appelle : rien d'autre que le disque (modules standard json et os).
# 📘 Concepts Python à retenir ici : with open(...), json.load / json.dump, try/except multiple,
# 📘   dict.update, dict comprehension.
# 📘 Chemin RELATIF : "output/settings.json" est résolu depuis le dossier où l'on lance
# 📘 l'appli (le "répertoire courant"), pas depuis l'emplacement de ce fichier.
# 💡 Sur Railway le disque du conteneur est éphémère : ce fichier disparaît à chaque redéploiement
# 💡   (sauf volume monté sur output/). Pour des réglages durables : volume Railway, ou table
# 💡   SQLite/Postgres (crm_store.py utilise déjà SQLite).
_SETTINGS_FILE = os.path.join("output", "settings.json")


def load_settings() -> Dict[str, Any]:
    """Charge les paramètres sauvegardés. Retourne un dict vide si absent."""
    # 📘 `with open(...) as f:` : ouvre le fichier et GARANTIT sa fermeture à la fin du bloc, même en
    # 📘 cas d'erreur. encoding="utf-8" : indispensable pour les accents.
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # 📘 except (A, B) : attrape plusieurs types d'erreurs d'un coup. Fichier absent ou JSON corrompu
    # 📘 → on repart d'un dict vide au lieu de planter l'interface.
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(settings: Dict[str, Any]) -> None:
    """Sauvegarde les paramètres (merge avec l'existant)."""
    os.makedirs("output", exist_ok=True)
    # 📘 "Merge" : on relit l'existant, puis update() écrase seulement les clés reçues.
    # 📘 Dict comprehension `{k: v for k, v in ... if v is not None}` : on ignore les valeurs None.
    current = load_settings()
    current.update({k: v for k, v in settings.items() if v is not None})
    # 📘 Mode "w" : le fichier est vidé puis réécrit. ensure_ascii=False garde les accents lisibles,
    # 📘 indent=2 rend le JSON indenté (lisible par un humain).
    # 💡 Écriture non atomique : si l'appli s'arrête pendant l'écriture, settings.json peut rester
    # 💡   à moitié écrit (alors ignoré au prochain chargement → réglages perdus). Écrire dans un
    # 💡   fichier temporaire puis os.replace(tmp, _SETTINGS_FILE) rend l'opération tout-ou-rien.
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
