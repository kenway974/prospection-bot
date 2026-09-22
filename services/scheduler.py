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

# Champs secrets qui ne doivent JAMAIS être écrits sur disque.
_SECRET_FIELDS = ("gmail_password", "notion_api_key")

# Identifiants gardés en mémoire uniquement (jamais persistés) : permettent
# l'envoi différé tant que le process vit, sans laisser de secret dans un fichier.
_runtime_creds: Dict[str, str] = {}


def remember_credentials(gmail_address: str, gmail_password: str, notion_api_key: str = "") -> None:
    """Mémorise les identifiants en RAM (jamais sur disque) pour l'envoi différé."""
    if gmail_address and gmail_password:
        _runtime_creds[gmail_address] = gmail_password
    if notion_api_key:
        _runtime_creds["_notion"] = notion_api_key


def _gmail_password_for(gmail_address: str) -> str:
    """Récupère le mot de passe : mémoire d'abord, puis variable d'environnement."""
    return _runtime_creds.get(gmail_address) or os.getenv("GMAIL_APP_PASSWORD", "")


def _notion_key() -> str:
    return _runtime_creds.get("_notion") or os.getenv("NOTION_API_KEY", "")


def _load() -> List[Dict[str, Any]]:
    try:
        with open(_QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _purge_secrets_on_disk() -> int:
    """
    Migration : supprime les secrets déjà écrits sur disque par les anciennes
    versions (mot de passe Gmail / clé Notion en clair). Retourne le nb purgé.
    """
    with _lock:
        queue = _load()
        purged = 0
        for entry in queue:
            for field in _SECRET_FIELDS:
                if entry.pop(field, None):
                    purged += 1
        if purged:
            _save(queue)
    return purged


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
    """
    Ajoute un email dans la file d'envoi différé.

    Sécurité : le mot de passe Gmail et la clé Notion ne sont JAMAIS écrits sur
    disque — ils sont gardés en mémoire (remember_credentials) et relus depuis
    les variables d'environnement après un redémarrage.
    """
    remember_credentials(gmail_address, gmail_password, notion_api_key)
    with _lock:
        queue = _load()
        queue.append({
            "id": f"{place_id}_{int(send_at)}",
            "place_id": place_id,
            "name": name,
            "email": email,
            "draft": draft,
            "gmail_address": gmail_address,
            "send_at": send_at,
            "sent": False,
            "notion_page_id": notion_page_id,
        })
        _save(queue)


def get_stats() -> Dict[str, int]:
    """Retourne {pending, sent, total, overdue} pour affichage dans l'UI."""
    queue = _load()
    now = time.time()
    sent = sum(1 for e in queue if e.get("sent"))
    overdue = sum(1 for e in queue if not e.get("sent") and e.get("send_at", 0) <= now)
    return {
        "pending": len(queue) - sent,
        "sent": sent,
        "total": len(queue),
        "overdue": overdue,
    }


def credentials_available() -> bool:
    """True si un envoi différé est possible (identifiants en RAM ou en env)."""
    return bool(
        os.getenv("GMAIL_APP_PASSWORD")
        or any(k != "_notion" for k in _runtime_creds)
    )


def process_due(force: bool = False) -> Dict[str, int]:
    """
    Envoie tous les emails dus (y compris ceux en retard après un redémarrage).
    Retourne {sent, failed, skipped_no_credentials}.
    `force=True` envoie aussi ceux programmés plus tard (bouton « envoyer maintenant »).
    """
    from services.gmail import send_email
    stats = {"sent": 0, "failed": 0, "skipped_no_credentials": 0}
    with _lock:
        queue = _load()
    now = time.time()
    changed = False
    for entry in queue:
        if entry.get("sent"):
            continue
        if not force and entry["send_at"] > now:
            continue
        password = _gmail_password_for(entry.get("gmail_address", ""))
        if not password:
            # Après un redémarrage sans GMAIL_APP_PASSWORD en variable d'env,
            # on ne peut plus envoyer : on laisse l'email en file, sans le perdre.
            stats["skipped_no_credentials"] += 1
            continue
        ok = send_email(
            to_address=entry["email"],
            draft=entry["draft"],
            gmail_address=entry["gmail_address"],
            gmail_app_password=password,
            prospect_name=entry["name"],
        )
        if ok:
            entry["sent"] = True
            entry["sent_at"] = datetime.now().isoformat()
            stats["sent"] += 1
            changed = True
            _nkey = _notion_key()
            if entry.get("notion_page_id") and _nkey:
                try:
                    from services.crm.notion import NotionExporter
                    NotionExporter(_nkey, "").update_status(entry["notion_page_id"], "contacté")
                except Exception:
                    pass
        else:
            stats["failed"] += 1
    if changed:
        with _lock:
            _save(queue)
    return stats


def _run_loop() -> None:
    # Rattrapage immédiat au démarrage : les emails dont l'heure est passée
    # pendant que l'app était éteinte partent tout de suite, sans attendre 60 s.
    try:
        process_due()
    except Exception:
        pass
    while True:
        time.sleep(60)
        try:
            process_due()
        except Exception:
            pass


def ensure_running() -> None:
    """Démarre le thread d'envoi différé si pas déjà actif (idempotent)."""
    global _thread
    if _thread is None or not _thread.is_alive():
        # Purge les secrets laissés sur disque par les anciennes versions.
        try:
            _purge_secrets_on_disk()
        except Exception:
            pass
        _thread = threading.Thread(target=_run_loop, daemon=True)
        _thread.start()
