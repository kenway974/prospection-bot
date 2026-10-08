"""
safe_files.py — Écriture sûre des fichiers JSON importants (contacts, historique, refus).

Une coupure (courant, plantage, disque plein) pendant l'écriture ne doit jamais
laisser un fichier à moitié écrit : on écrit dans un fichier temporaire du MÊME
dossier, puis on le substitue d'un coup à l'original avec os.replace (atomique).

Copie de secours : juste avant de remplacer le fichier, sa version précédente
(si elle est lisible) est copiée en <fichier>.bak. Un fichier abîmé n'écrase
jamais une bonne copie de secours.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

BACKUP_SUFFIX = ".bak"


def backup_path(path: str) -> str:
    return path + BACKUP_SUFFIX


def is_readable_json(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as f:
            json.load(f)
        return True
    except (OSError, ValueError):
        return False


def _copy_atomic(src: str, dst: str) -> None:
    """Copie src vers dst sans jamais laisser dst à moitié copié."""
    folder = os.path.dirname(dst) or "."
    fd, tmp_path = tempfile.mkstemp(dir=folder, prefix=os.path.basename(dst) + ".", suffix=".tmp")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp_path)
        os.replace(tmp_path, dst)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def write_json_atomic(path: str, data) -> None:
    """
    Écrit `data` dans `path` sans jamais laisser `path` à moitié écrit.
    La version précédente lisible est conservée dans `path`.bak.
    """
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=folder, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if is_readable_json(path):
            _copy_atomic(path, backup_path(path))
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
