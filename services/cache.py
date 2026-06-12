"""Cache JSON pour les analyses de prospects.

Clé = URL du site. Valeur = issues, score, email + timestamp Unix.
Évite de refaire fetch + checks pour un prospect déjà analysé récemment.
Thread-safe via threading.Lock (utilisé avec ThreadPoolExecutor dans app.py).
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

_CACHE_FILE = os.path.join("output", "analysis_cache.json")
_ttl_days: int = 30
_lock = threading.Lock()


def set_ttl(days: int) -> None:
    """Modifie la durée de validité du cache (en jours)."""
    global _ttl_days
    _ttl_days = max(1, days)


def _load() -> Dict[str, Any]:
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
    with open(_CACHE_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def get_cached(url: str) -> Optional[Dict[str, Any]]:
    """Retourne l'entrée en cache si elle n'est pas expirée, None sinon."""
    with _lock:
        entry = _load().get(url)
    if entry and time.time() - entry.get("ts", 0) < _ttl_days * 86_400:
        return entry
    return None


def set_cached(url: str, issues: List[str], score: int, email: Optional[str], cms: Optional[str] = None) -> None:
    """Sauvegarde le résultat d'analyse pour une URL (thread-safe)."""
    with _lock:
        cache = _load()
        cache[url] = {"issues": issues, "score": score, "email": email, "cms": cms, "ts": time.time()}
        _save(cache)


def count() -> int:
    """Retourne le nombre d'entrées actuellement en cache."""
    with _lock:
        return len(_load())


def clear_all() -> int:
    """Vide complètement le cache. Retourne le nombre d'entrées supprimées."""
    with _lock:
        n = len(_load())
        _save({})
        return n
