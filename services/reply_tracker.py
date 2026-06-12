"""
services/reply_tracker.py — Suivi automatique des réponses par email (IMAP Gmail).

Poll Gmail IMAP toutes les 5 minutes pour détecter les réponses des prospects.
Quand un prospect répond, il est automatiquement marqué "répondu" dans
contacted_place_ids.json — plus de relance inutile.

Nécessite gmail_address + gmail_app_password (IMAP doit être activé sur le compte).
Thread daemon — démarré une seule fois par process (ensure_running est idempotent).
"""

from __future__ import annotations

import email as _email_lib
import imaplib
import re
import threading
import time
from typing import Optional

_thread: Optional[threading.Thread] = None
_POLL_INTERVAL = 300  # 5 minutes entre chaque vérification


def _extract_sender(msg) -> Optional[str]:
    """Extrait l'adresse email de l'expéditeur depuis un header email."""
    from_header = msg.get("From", "")
    match = re.search(r"<([^>]+@[^>]+)>", from_header)
    if match:
        return match.group(1).lower().strip()
    match = re.search(r"[\w.+\-]+@[\w.\-]+\.\w+", from_header)
    if match:
        return match.group(0).lower().strip()
    return None


def poll_once(gmail_address: str, gmail_password: str) -> int:
    """
    Poll IMAP une fois. Retourne le nombre de nouvelles réponses détectées.
    Consulte uniquement les emails non lus pour éviter les faux positifs.
    """
    from history_manager import _load_contacted_data, mark_as_responded

    contacted = _load_contacted_data()
    email_to_place_id = {
        info.get("email", "").lower(): pid
        for pid, info in contacted.items()
        if info.get("email") and not info.get("responded")
    }
    if not email_to_place_id:
        return 0

    found = 0
    try:
        with imaplib.IMAP4_SSL("imap.gmail.com", timeout=20) as imap:
            imap.login(gmail_address, gmail_password)
            imap.select("INBOX", readonly=True)
            _, msgnums = imap.search(None, "UNSEEN")
            for num in msgnums[0].split():
                try:
                    _, data = imap.fetch(num, "(RFC822.HEADER)")
                    msg = _email_lib.message_from_bytes(data[0][1])
                    sender = _extract_sender(msg)
                    if sender and sender in email_to_place_id:
                        mark_as_responded(email_to_place_id[sender])
                        found += 1
                except Exception:
                    continue
    except imaplib.IMAP4.error:
        pass
    except Exception:
        pass
    return found


def _run_loop(gmail_address: str, gmail_password: str) -> None:
    while True:
        time.sleep(_POLL_INTERVAL)
        try:
            poll_once(gmail_address, gmail_password)
        except Exception:
            pass


def ensure_running(gmail_address: str, gmail_password: str) -> None:
    """Démarre le thread de suivi de réponses (idempotent). No-op si credentials manquants."""
    global _thread
    if not gmail_address or not gmail_password:
        return
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(
            target=_run_loop,
            args=(gmail_address, gmail_password),
            daemon=True,
        )
        _thread.start()


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
