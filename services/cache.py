"""Cache JSON pour les analyses de prospects (TTL 30 jours).

Clé = URL du site. Valeur = issues, score, email + timestamp Unix.
Évite de refaire fetch + 11 checks pour un prospect déjà analysé récemment.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

_CACHE_FILE = os.path.join("output", "analysis_cache.json")
_TTL_SECONDS = 30 * 86_400  # 30 jours


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
    """Retourne l'entrée en cache si elle existe et n'est pas expirée (30 jours)."""
    entry = _load().get(url)
    if entry and time.time() - entry.get("ts", 0) < _TTL_SECONDS:
        return entry
    return None


def set_cached(url: str, issues: List[str], score: int, email: Optional[str]) -> None:
    """Sauvegarde le résultat d'analyse pour une URL."""
    cache = _load()
    cache[url] = {"issues": issues, "score": score, "email": email, "ts": time.time()}
    _save(cache)
