"""
safe_files.py — Écriture sûre des fichiers JSON importants (contacts, historique, refus).

Une coupure (courant, plantage, disque plein) pendant l'écriture ne doit jamais
laisser un fichier à moitié écrit : on écrit dans un fichier temporaire du MÊME
dossier, puis on le substitue d'un coup à l'original avec os.replace (atomique).
"""

from __future__ import annotations

import json
import os
import tempfile


def write_json_atomic(path: str, data) -> None:
    """Écrit `data` dans `path` sans jamais laisser `path` à moitié écrit."""
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=folder, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
