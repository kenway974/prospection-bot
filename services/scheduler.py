"""
services/scheduler.py — Envoi différé d'emails.

Les emails programmés sont stockés dans output/pending_emails.json.
Un thread de fond vérifie toutes les 60 secondes et envoie les emails dus.
"""

from __future__ import annotations

# 📘 json : lire/écrire des fichiers JSON (format texte de données, proche des dict Python).
# 📘 os : chemins de fichiers, dossiers, variables d'environnement.
# 📘 threading : thread de fond + Lock (verrou) ; datetime : dates/heures lisibles.
# 📘 typing.Any/Dict/List/Optional : annotations de type (aide à la lecture, pas exécutées).
import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : "programmer" des emails pour plus tard : on les range dans une file (un fichier
# 📘         JSON) et un thread de fond envoie ceux dont l'heure est arrivée.
# 📘 Appelé par : app.py (ensure_running au démarrage, stats + bouton d'envoi dans l'UI),
# 📘              pipeline.py (add_pending en mode "⏰ Programmé"), tests/test_scheduler_security.py.
# 📘 Appelle : services/gmail.py (send_email), services/crm/notion.py (update_status),
# 📘           le fichier output/pending_emails.json.
# 📘 Concepts Python à retenir ici : threading.Thread daemon, threading.Lock + `with`,
# 📘   JSON (json.load/json.dump), `global`, os.getenv, timestamps (time.time) et datetime,
# 📘   dict.pop, sum() sur un générateur, try/except.
#
# 📘 os.path.join construit un chemin compatible Windows/Mac/Linux ("output/pending_emails.json").
_QUEUE_FILE = os.path.join("output", "pending_emails.json")
# 📘 Lock = verrou : un seul thread à la fois peut exécuter un bloc `with _lock:`.
# 📘 POURQUOI : le thread de fond et l'interface peuvent lire/écrire le même fichier JSON
# 📘 en même temps ; sans verrou, l'un pourrait écraser les modifications de l'autre.
_lock = threading.Lock()
_thread: Optional[threading.Thread] = None

# 📘 Sécurité : un mot de passe écrit dans un fichier en clair peut fuiter (sauvegarde,
# 📘 partage, commit Git par erreur). Ce module fait donc le choix de ne jamais les écrire.
# Champs secrets qui ne doivent JAMAIS être écrits sur disque.
_SECRET_FIELDS = ("gmail_password", "notion_api_key")

# Identifiants gardés en mémoire uniquement (jamais persistés) : permettent
# l'envoi différé tant que le process vit, sans laisser de secret dans un fichier.
# 📘 Ce dict est une variable de module : il vit en RAM et disparaît au redémarrage.
_runtime_creds: Dict[str, str] = {}


# 📘 Clé = adresse Gmail, valeur = mot de passe d'application. La clé Notion est rangée
# 📘 sous la clé spéciale "_notion".
def remember_credentials(gmail_address: str, gmail_password: str, notion_api_key: str = "") -> None:
    """Mémorise les identifiants en RAM (jamais sur disque) pour l'envoi différé."""
    if gmail_address and gmail_password:
        _runtime_creds[gmail_address] = gmail_password
    if notion_api_key:
        _runtime_creds["_notion"] = notion_api_key


def _gmail_password_for(gmail_address: str) -> str:
    """Récupère le mot de passe : mémoire d'abord, puis variable d'environnement."""
    # 📘 `a or b` : le mot de passe en RAM s'il existe, sinon celui de la variable d'environnement.
    return _runtime_creds.get(gmail_address) or os.getenv("GMAIL_APP_PASSWORD", "")


def _notion_key() -> str:
    return _runtime_creds.get("_notion") or os.getenv("NOTION_API_KEY", "")


# 📘 Lit la file depuis le disque. `with open(...) as f` ferme le fichier automatiquement.
# 📘 json.load transforme le texte JSON en objets Python (ici une liste de dicts).
def _load() -> List[Dict[str, Any]]:
    try:
        with open(_QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # 📘 On attrape 2 erreurs précises : fichier absent (1er lancement) ou JSON corrompu.
    # 📘 Dans les deux cas on repart d'une file vide.
    # 💡 Un JSON corrompu = file vidée SANS alerte : les emails programmés seraient perdus
    # 💡 au prochain _save. Logger l'erreur et garder une copie du fichier abîmé serait plus sûr.
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _purge_secrets_on_disk() -> int:
    """
    Migration : supprime les secrets déjà écrits sur disque par les anciennes
    versions (mot de passe Gmail / clé Notion en clair). Retourne le nb purgé.
    """
    # 📘 `with _lock:` prend le verrou, et le relâche automatiquement en sortie de bloc.
    with _lock:
        queue = _load()
        purged = 0
        for entry in queue:
            for field in _SECRET_FIELDS:
                # 📘 dict.pop(clé, None) supprime la clé si elle existe et renvoie sa valeur (None sinon).
                if entry.pop(field, None):
                    purged += 1
        if purged:
            _save(queue)
    return purged


# 📘 Écrit toute la file sur disque. exist_ok=True : pas d'erreur si le dossier existe déjà.
# 📘 ensure_ascii=False garde les accents lisibles ; indent=2 rend le fichier lisible.
# 💡 Écriture "atomique" recommandée : écrire dans un fichier temporaire puis os.replace(),
# 💡 pour qu'un crash en pleine écriture ne laisse jamais un JSON à moitié écrit.
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
    # 📘 send_at est un "timestamp" : un nombre de secondes depuis le 01/01/1970 (float).
    remember_credentials(gmail_address, gmail_password, notion_api_key)
    with _lock:
        # 📘 Schéma classique "lire → modifier → réécrire", protégé par le verrou pour que
        # 📘 personne d'autre ne modifie le fichier entre la lecture et l'écriture.
        queue = _load()
        queue.append({
            # 📘 id unique = place_id + heure d'envoi. Remarque : "gmail_address" est bien stocké,
            # 📘 mais PAS le mot de passe (voir remember_credentials plus haut).
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


# 📘 Lecture sans verrou ici : c'est seulement pour l'affichage, un léger décalage est acceptable.
def get_stats() -> Dict[str, int]:
    """Retourne {pending, sent, total, overdue} pour affichage dans l'UI."""
    queue = _load()
    # 📘 time.time() = maintenant, en timestamp. sum(1 for e in queue if ...) compte les
    # 📘 éléments qui respectent la condition (expression "générateur").
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
        # 📘 any(...) renvoie True si au moins un élément est vrai : ici, au moins une adresse
        # 📘 Gmail mémorisée en RAM (en excluant la clé spéciale "_notion").
        or any(k != "_notion" for k in _runtime_creds)
    )


def process_due(force: bool = False) -> Dict[str, int]:
    """
    Envoie tous les emails dus (y compris ceux en retard après un redémarrage).
    Retourne {sent, failed, skipped_no_credentials}.
    `force=True` envoie aussi ceux programmés plus tard (bouton « envoyer maintenant »).
    """
    # 📘 Import local : charge services.gmail seulement au moment d'envoyer.
    from services.gmail import send_email
    stats = {"sent": 0, "failed": 0, "skipped_no_credentials": 0}
    # 📘 Le verrou n'est tenu que pendant la LECTURE : on ne le garde pas pendant les envois
    # 📘 SMTP (lents), pour ne pas bloquer l'interface.
    with _lock:
        queue = _load()
    now = time.time()
    changed = False
    for entry in queue:
        if entry.get("sent"):
            continue
        # 📘 `force` : le bouton « envoyer maintenant » ignore l'heure prévue.
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
        # 📘 On modifie directement le dict `entry` : comme il fait partie de la liste `queue`,
        # 📘 la liste est à jour (les objets Python sont manipulés par référence).
        if ok:
            entry["sent"] = True
            # 📘 datetime.now().isoformat() → texte du type "2026-09-24T09:00:00.123456" (lisible).
            entry["sent_at"] = datetime.now().isoformat()
            stats["sent"] += 1
            changed = True
            # 📘 Mise à jour du statut Notion "contacté" ; toute erreur Notion est ignorée pour ne
            # 📘 pas bloquer l'envoi des autres emails.
            _nkey = _notion_key()
            if entry.get("notion_page_id") and _nkey:
                try:
                    from services.crm.notion import NotionExporter
                    NotionExporter(_nkey, "").update_status(entry["notion_page_id"], "contacté")
                except Exception:
                    pass
        else:
            stats["failed"] += 1
    # 📘 On réécrit la liste lue AU DÉBUT, en fin de traitement.
    # 💡 Bug potentiel : un email ajouté via add_pending PENDANT la boucle d'envoi est écrasé
    # 💡 (perdu) par ce _save, et si l'UI et le thread lancent process_due en même temps, un mail
    # 💡 peut partir 2 fois. Relire la file sous verrou et ne mettre à jour que les entrées
    # 💡 envoyées (par "id") — ou passer à SQLite, déjà utilisé par le CRM — corrigerait ça.
    if changed:
        with _lock:
            _save(queue)
    return stats


# 📘 Boucle du thread de fond : un passage immédiat, puis un toutes les 60 secondes.
# 📘 Chaque passage est entouré d'un try/except : une erreur ne tue pas le thread.
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


# 📘 Idempotent : appelé à chaque ré-exécution du script Streamlit, mais ne crée
# 📘 qu'un seul thread par process (grâce au test is_alive()).
def ensure_running() -> None:
    """Démarre le thread d'envoi différé si pas déjà actif (idempotent)."""
    # 📘 `global _thread` : pour modifier la variable du module, pas en créer une locale.
    global _thread
    if _thread is None or not _thread.is_alive():
        # Purge les secrets laissés sur disque par les anciennes versions.
        try:
            _purge_secrets_on_disk()
        except Exception:
            pass
        # 📘 daemon=True : le thread s'arrête avec le programme principal, sans le retenir.
        # 💡 Infra : ce "planificateur" ne tourne que si l'app Streamlit est ouverte/active.
        # 💡 Un worker séparé (process dédié, cron, ou file de tâches type RQ/Celery + Redis avec
        # 💡 tâches planifiées) enverrait les mails même app fermée, avec retries et logs.
        _thread = threading.Thread(target=_run_loop, daemon=True)
        _thread.start()
