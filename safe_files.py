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

import contextlib
import json
import os
import shutil
import tempfile
import threading
import time

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


_MISSING = object()


def _warn(message: str, *args) -> None:
    import config  # import tardif : l'interface remplace config.logger pendant un run
    config.logger.warning(message, *args)


def read_json_with_recovery(path: str, label: str, backup: str | None = None, default=_MISSING):
    """
    Lit le JSON de `path`, avec la copie de secours (`backup`, par défaut `path`.bak) :

    - JSON illisible + copie lisible → le fichier abîmé est mis de côté (.corrupt, jamais
      supprimé), la copie est restaurée à sa place, un avertissement est loggé ;
    - fichier absent + copie lisible → la copie est restaurée (fichier supprimé par erreur) ;
    - fichier absent sans copie → `default` (ou FileNotFoundError si aucun défaut) ;
    - fichier présent mais impossible à LIRE (verrou, droits…) → l'erreur remonte telle
      quelle : ce n'est pas une corruption, on ne remplace pas un bon fichier par une copie
      plus ancienne ;
    - aucune copie fiable → l'erreur d'origine remonte SANS qu'aucun fichier n'ait été
      touché : c'est à l'appelant de s'arrêter.
    """
    bak = backup or backup_path(path)
    if not os.path.exists(path):
        if is_readable_json(bak):
            with open(bak, "r", encoding="utf-8") as f:
                data = json.load(f)
            _copy_atomic(bak, path)
            _warn("⚠️  %s absent : copie de secours restaurée automatiquement (%s → %s).",
                  label, bak, path)
            return data
        if default is not _MISSING:
            return default
        raise FileNotFoundError(path)

    with open(path, "r", encoding="utf-8") as f:     # OSError (verrou, droits) : remonte
        text = f.read()
    try:
        return json.loads(text)
    except ValueError:
        if not is_readable_json(bak):
            raise
        with open(bak, "r", encoding="utf-8") as f:
            data = json.load(f)
        set_aside_to = set_aside(path)
        _copy_atomic(bak, path)
        _warn(
            "⚠️  %s illisible : copie de secours restaurée automatiquement (%s → %s). "
            "Le fichier abîmé est conservé dans %s. Les données écrites depuis la dernière "
            "sauvegarde peuvent manquer : vérifiez-les si besoin.",
            label, bak, path, set_aside_to,
        )
        return data


# ---------------------------------------------------------------------------
# Verrou : une seule modification à la fois (lecture → modification → écriture)
# ---------------------------------------------------------------------------

LOCK_TIMEOUT_S = 15        # au-delà, on abandonne (TimeoutError) plutôt que d'écrire en double
LOCK_STALE_S = 60          # un verrou plus vieux vient d'un programme planté : on le retire


@contextlib.contextmanager
def file_lock(path: str):
    """
    Verrou inter-processus (interface + ligne de commande) et inter-threads, sans
    dépendance : création exclusive de <fichier>.lock. Sans lui, deux modifications
    simultanées lisent la même version et la dernière écriture efface l'autre.
    """
    lock = path + ".lock"
    os.makedirs(os.path.dirname(lock) or ".", exist_ok=True)
    deadline = time.monotonic() + LOCK_TIMEOUT_S
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > LOCK_STALE_S:
                    os.remove(lock)
                    continue
            except OSError:
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"{path} est en cours de modification par un autre programme")
            _wait_for_lock()
    try:
        yield
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def _wait_for_lock() -> None:
    # threading.Event().wait plutôt que time.sleep : reste une vraie attente même quand
    # les tests neutralisent time.sleep.
    threading.Event().wait(0.02)
