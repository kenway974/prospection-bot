"""
services/scheduler.py — Envoi différé d'emails.

Les emails programmés sont stockés dans output/pending_emails.json.
Un thread de fond vérifie toutes les 60 secondes et envoie les emails dus.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

_QUEUE_FILE = os.path.join("output", "pending_emails.json")
_lock = threading.Lock()
_thread: Optional[threading.Thread] = None


def _load() -> List[Dict[str, Any]]:
    try:
        with open(_QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(data: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(_QUEUE_FILE), exist_ok=True)
    with open(_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_pending(
    place_id: str,
    name: str,
    email: str,
    draft: str,
    gmail_address: str,
    gmail_password: str,
    send_at: float,
    notion_page_id: str = "",
    notion_api_key: str = "",
) -> None:
    """Ajoute un email dans la file d'envoi différé."""
    with _lock:
        queue = _load()
        queue.append({
            "id": f"{place_id}_{int(send_at)}",
            "place_id": place_id,
            "name": name,
            "email": email,
            "draft": draft,
            "gmail_address": gmail_address,
            "gmail_password": gmail_password,
            "send_at": send_at,
            "sent": False,
            "notion_page_id": notion_page_id,
            "notion_api_key": notion_api_key,
        })
        _save(queue)


def get_stats() -> Dict[str, int]:
    """Retourne {pending, sent, total} pour affichage dans l'UI."""
    queue = _load()
    sent = sum(1 for e in queue if e.get("sent"))
    return {"pending": len(queue) - sent, "sent": sent, "total": len(queue)}


def _run_loop() -> None:
    from services.gmail import send_email
    while True:
        time.sleep(60)
        try:
            with _lock:
                queue = _load()
            now = time.time()
            changed = False
            for entry in queue:
                if entry.get("sent") or entry["send_at"] > now:
                    continue
                ok = send_email(
                    to_address=entry["email"],
                    draft=entry["draft"],
                    gmail_address=entry["gmail_address"],
                    gmail_app_password=entry["gmail_password"],
                    prospect_name=entry["name"],
                )
                if ok:
                    entry["sent"] = True
                    entry["sent_at"] = datetime.now().isoformat()
                    if entry.get("notion_page_id") and entry.get("notion_api_key"):
                        try:
                            from services.crm.notion import NotionExporter
                            NotionExporter(entry["notion_api_key"], "").update_status(
                                entry["notion_page_id"], "contacté"
                            )
                        except Exception:
                            pass
                    changed = True
            if changed:
                with _lock:
                    _save(queue)
        except Exception:
            pass


def ensure_running() -> None:
    """Démarre le thread d'envoi différé si pas déjà actif (idempotent)."""
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_run_loop, daemon=True)
        _thread.start()
