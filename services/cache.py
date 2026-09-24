"""Cache JSON pour les analyses de prospects.

Clé = URL du site. Valeur = issues, score, email + timestamp Unix.
Évite de refaire fetch + checks pour un prospect déjà analysé récemment.
Thread-safe via threading.Lock (utilisé avec ThreadPoolExecutor dans app.py).
"""

# 📘 `from __future__ import annotations` : les type hints (ex: `-> Dict[str, Any]`) ne sont plus
# 📘 évalués à l'exécution, juste stockés en texte. Ça évite des erreurs et accélère l'import.
from __future__ import annotations

# 📘 `import X` charge un module (une boîte à outils). Ici que des modules de la librairie standard :
# 📘 json (lire/écrire du JSON), os (fichiers/dossiers), threading (exécution parallèle),
# 📘 time (heure actuelle), typing (annotations de types, purement informatives).
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : mémoriser sur disque (output/analysis_cache.json) le résultat de l'analyse d'un site
# 📘   (problèmes détectés, score, email, CMS) pour ne pas re-télécharger/re-analyser un site
# 📘   déjà vu il y a moins de N jours (30 par défaut).
# 📘 Appelé par : services/analyzer.py (get_cached / set_cached), pipeline.py (set_ttl),
# 📘   app.py (count / clear_all dans l'onglet réglages), tests/test_analyzer.py.
# 📘 Appelle : rien d'externe, juste le système de fichiers.
# 📘 Concepts Python à retenir ici : variables "privées" préfixées par `_`, `global`,
# 📘   `with` (context manager), try/except, threading.Lock, Optional / type hints.

# 📘 Constantes de module. Le `_` au début = convention "usage interne, ne pas importer".
# 📘 os.path.join construit un chemin compatible Windows/Linux ("output/analysis_cache.json").
# 📘 ⚠️ Chemin RELATIF : il dépend du dossier depuis lequel tu lances l'app.
_CACHE_FILE = os.path.join("output", "analysis_cache.json")
# 📘 `_ttl_days: int = 30` : variable annotée (type hint `int`). TTL = "Time To Live", durée de vie.
_ttl_days: int = 30
# 📘 Un Lock (verrou) : un seul thread à la fois peut exécuter le code protégé par `with _lock:`.
# 📘 Indispensable car analyzer tourne en parallèle (ThreadPoolExecutor) : sans verrou, deux threads
# 📘 pourraient lire/écrire le fichier en même temps et le corrompre ou perdre des entrées.
_lock = threading.Lock()


# 📘 `def nom(param: type) -> type_retour:` définit une fonction. `-> None` = ne renvoie rien.
def set_ttl(days: int) -> None:
    """Modifie la durée de validité du cache (en jours)."""
    # 📘 `global` : on veut modifier la variable du MODULE, pas créer une variable locale homonyme.
    global _ttl_days
    # 📘 max(1, days) garantit au moins 1 jour (protège contre 0 ou une valeur négative).
    _ttl_days = max(1, days)


# 📘 Lit tout le fichier JSON et le renvoie sous forme de dict (dictionnaire clé -> valeur).
def _load() -> Dict[str, Any]:
    # 📘 try/except : on "essaie" un bloc ; si une erreur listée survient, on exécute le except
    # 📘 au lieu de planter. Ici : fichier absent ou JSON corrompu -> on repart d'un cache vide.
    try:
        # 📘 `with open(...) as fh:` ouvre le fichier et le ferme AUTOMATIQUEMENT à la fin du bloc,
        # 📘 même en cas d'erreur (c'est un "context manager"). "r" = lecture.
        with open(_CACHE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# 📘 Réécrit TOUT le fichier avec le dict donné.
def _save(data: Dict[str, Any]) -> None:
    # 📘 Crée le dossier "output" s'il n'existe pas (exist_ok=True : pas d'erreur s'il existe déjà).
    os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
    # 📘 "w" = écriture (écrase le contenu). ensure_ascii=False garde les accents lisibles,
    # 📘 indent=2 rend le fichier joli (mais plus gros).
    # 💡 Écriture non atomique : si l'app crashe pendant l'écriture, le JSON est tronqué et
    # 💡   _load() renverra {} (tout le cache perdu). Écris dans un fichier .tmp puis
    # 💡   os.replace(tmp, _CACHE_FILE) : le remplacement est atomique.
    with open(_CACHE_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


# 📘 Optional[X] = "X ou None". La fonction renvoie un dict ou None si pas de cache valide.
def get_cached(url: str) -> Optional[Dict[str, Any]]:
    """Retourne l'entrée en cache si elle n'est pas expirée, None sinon."""
    # 📘 On ne garde le verrou que le temps de la lecture ; la comparaison se fait en dehors.
    # 📘 dict.get(url) renvoie None si la clé n'existe pas (au lieu d'une erreur KeyError).
    with _lock:
        entry = _load().get(url)
    # 📘 time.time() = secondes depuis 1970. 86_400 = secondes dans une journée (le `_` sert
    # 📘 juste à rendre le nombre lisible). Entrée valide si elle a moins de _ttl_days jours.
    if entry and time.time() - entry.get("ts", 0) < _ttl_days * 86_400:
        return entry
    return None


# 📘 `cms: Optional[str] = None` : paramètre avec valeur par défaut, donc facultatif à l'appel.
# 💡 Chaque set_cached relit + réécrit tout le fichier : O(taille du cache) par site analysé.
# 💡   Avec des milliers d'entrées, SQLite (module sqlite3 intégré à Python) serait bien plus
# 💡   efficace et gère lui-même la concurrence et l'expiration (DELETE WHERE ts < ...).
def set_cached(url: str, issues: List[str], score: int, email: Optional[str], cms: Optional[str] = None) -> None:
    """Sauvegarde le résultat d'analyse pour une URL (thread-safe)."""
    # 📘 Lecture + modification + écriture DANS le même verrou : sinon deux threads pourraient
    # 📘 lire la même version, et le second écraserait l'ajout du premier ("lost update").
    with _lock:
        cache = _load()
        cache[url] = {"issues": issues, "score": score, "email": email, "cms": cms, "ts": time.time()}
        _save(cache)
    # 💡 Les entrées expirées ne sont jamais supprimées : le fichier grossit indéfiniment.
    # 💡   Tu pourrais purger ici les entrées où time.time() - ts > TTL avant _save().


def count() -> int:
    """Retourne le nombre d'entrées actuellement en cache."""
    # 📘 len() donne la taille d'un conteneur (ici le nombre de clés du dict).
    with _lock:
        return len(_load())


def clear_all() -> int:
    """Vide complètement le cache. Retourne le nombre d'entrées supprimées."""
    with _lock:
        n = len(_load())
        _save({})
        return n
