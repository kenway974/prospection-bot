"""
safe_files.py — Écriture sûre des fichiers JSON importants (contacts, historique, refus).

Une coupure (courant, plantage, disque plein) pendant l'écriture ne doit jamais
laisser un fichier à moitié écrit : on écrit dans un fichier temporaire du MÊME
dossier, puis on le substitue d'un coup à l'original avec os.replace (atomique).

Copie de secours : juste avant de remplacer le fichier, sa version précédente
(si elle est lisible) est copiée en <fichier>.bak — ou sous le nom passé en
paramètre `backup`. Un fichier abîmé n'écrase jamais une bonne copie de secours.
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


def write_json_atomic(path: str, data, backup: str | None = None) -> None:
    """
    Écrit `data` dans `path` sans jamais laisser `path` à moitié écrit.
    La version précédente lisible est conservée dans `backup` (par défaut `path`.bak).
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
            _copy_atomic(path, backup or backup_path(path))
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


CORRUPT_SUFFIX = ".corrupt"


def set_aside(path: str) -> str:
    """Renomme le fichier abîmé en <fichier>.corrupt (ou .corrupt.1, .2… : on n'écrase jamais)."""
    target = path + CORRUPT_SUFFIX
    n = 1
    while os.path.exists(target):
        target = f"{path}{CORRUPT_SUFFIX}.{n}"
        n += 1
    os.replace(path, target)
    return target


def read_json_with_recovery(path: str, label: str, backup: str | None = None):
    """
    Lit le JSON de `path`. S'il est illisible et que la copie de secours (`backup`,
    par défaut `path`.bak) est lisible : le fichier abîmé est mis de côté (.corrupt, jamais supprimé), le .bak est
    restauré à sa place, un avertissement est loggé, et le contenu du .bak est renvoyé.

    S'il n'y a aucune copie fiable, l'erreur de lecture d'origine est relevée SANS
    qu'aucun fichier n'ait été touché : c'est à l'appelant de s'arrêter.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        bak = backup or backup_path(path)
        if not is_readable_json(bak):
            raise
        with open(bak, "r", encoding="utf-8") as f:
            data = json.load(f)
        set_aside_to = set_aside(path)
        _copy_atomic(bak, path)

        import config  # import tardif : l'interface remplace config.logger pendant un run
        config.logger.warning(
            "⚠️  %s illisible : copie de secours restaurée automatiquement (%s → %s). "
            "Le fichier abîmé est conservé dans %s. Les données écrites depuis la dernière "
            "sauvegarde peuvent manquer : vérifiez-les si besoin.",
            label, bak, path, set_aside_to,
        )
        return data
