"""
services/reply_tracker.py — Suivi automatique des réponses par email (IMAP Gmail).

Poll Gmail IMAP toutes les 5 minutes pour détecter les réponses des prospects.
Quand un prospect répond, il est automatiquement marqué "répondu" dans
contacted_place_ids.json — plus de relance inutile.

Nécessite gmail_address + gmail_app_password (IMAP doit être activé sur le compte).
Thread daemon — démarré une seule fois par process (ensure_running est idempotent).
"""

from __future__ import annotations

# 📘 Modules de la bibliothèque standard :
# 📘 - email (renommé _email_lib avec `as`) : lit/décode un email brut reçu ;
# 📘 - imaplib : protocole IMAP, pour LIRE une boîte mail (SMTP, lui, sert à envoyer) ;
# 📘 - re : expressions régulières ; threading : exécuter du code "en parallèle" ;
# 📘 - time : pauses (sleep).
import email as _email_lib
import imaplib
import re
import threading
import time
from typing import Optional

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : surveiller la boîte Gmail en tâche de fond (toutes les 5 min) et marquer
# 📘         "répondu" les prospects qui ont écrit, pour ne plus leur envoyer de relance.
# 📘 Appelé par : app.py (ensure_running au démarrage si identifiants, is_running /
# 📘              ensure_running dans l'interface de suivi).
# 📘 Appelle : le serveur imap.gmail.com (IMAP chiffré SSL) et history_manager.py
# 📘           (_load_contacted_data, mark_as_responded → output/contacted_place_ids.json).
# 📘 Concepts Python à retenir ici : threading.Thread daemon, variable globale `global`,
# 📘   boucle infinie + time.sleep, imaplib, regex, dict en compréhension, try/except.
#
# 📘 Variables "de module" : elles vivent tant que le process Python tourne. _thread garde
# 📘 une référence au thread de fond (None = pas encore démarré).
_thread: Optional[threading.Thread] = None
_POLL_INTERVAL = 300  # 5 minutes entre chaque vérification


# 📘 L'en-tête From ressemble à : `Jean Dupont <jean@exemple.fr>` ou juste `jean@exemple.fr`.
def _extract_sender(msg) -> Optional[str]:
    """Extrait l'adresse email de l'expéditeur depuis un header email."""
    from_header = msg.get("From", "")
    # 📘 re.search cherche le motif n'importe où dans le texte. <([^>]+@[^>]+)> = "ce qui est
    # 📘 entre < et > et contient un @". match.group(1) = le contenu de la 1re parenthèse.
    match = re.search(r"<([^>]+@[^>]+)>", from_header)
    if match:
        return match.group(1).lower().strip()
    # 📘 2e essai : une adresse email "nue" (sans chevrons). .lower() : comparaison sans casse.
    match = re.search(r"[\w.+\-]+@[\w.\-]+\.\w+", from_header)
    if match:
        return match.group(0).lower().strip()
    return None


def poll_once(gmail_address: str, gmail_password: str) -> int:
    """
    Poll IMAP une fois. Retourne le nombre de nouvelles réponses détectées.
    Consulte uniquement les emails non lus pour éviter les faux positifs.
    """
    # 📘 Import local (dans la fonction) : évite une importation circulaire et ne charge
    # 📘 history_manager que quand on en a besoin.
    from history_manager import _load_contacted_data, mark_as_responded

    contacted = _load_contacted_data()
    # 📘 Dictionnaire "en compréhension" : on construit {email: place_id} en une expression,
    # 📘 en ne gardant que les prospects qui ont un email ET n'ont pas encore répondu.
    # 📘 Ça permet ensuite de retrouver le prospect à partir de l'expéditeur, instantanément.
    email_to_place_id = {
        info.get("email", "").lower(): pid
        for pid, info in contacted.items()
        if info.get("email") and not info.get("responded")
    }
    if not email_to_place_id:
        return 0

    found = 0
    try:
        # 📘 IMAP4_SSL : connexion chiffrée dès le départ (port 993). `with` ferme la session
        # 📘 proprement à la fin. readonly=True : on ne modifie RIEN dans la boîte (les mails
        # 📘 restent "non lus" pour toi).
        with imaplib.IMAP4_SSL("imap.gmail.com", timeout=20) as imap:
            imap.login(gmail_address, gmail_password)
            imap.select("INBOX", readonly=True)
            # 📘 imap.search(None, "UNSEEN") renvoie les numéros des mails non lus, sous forme
            # 📘 d'octets séparés par des espaces (d'où le .split()).
            # 📘 Limite : un prospect dont tu as déjà LU la réponse avant le passage du thread
            # 📘 ne sera pas détecté.
            _, msgnums = imap.search(None, "UNSEEN")
            for num in msgnums[0].split():
                try:
                    # 📘 RFC822.HEADER : on ne télécharge que les en-têtes (pas le corps) : plus léger.
                    # 📘 data[0][1] = les octets bruts ; message_from_bytes en fait un objet email.
                    _, data = imap.fetch(num, "(RFC822.HEADER)")
                    msg = _email_lib.message_from_bytes(data[0][1])
                    sender = _extract_sender(msg)
                    if sender and sender in email_to_place_id:
                        mark_as_responded(email_to_place_id[sender])
                        found += 1
                # 📘 `except Exception: continue` : un mail illisible est ignoré sans casser la boucle.
                except Exception:
                    continue
    # 📘 Toutes les erreurs (mauvais mot de passe, réseau…) sont avalées en silence (`pass`).
    # 💡 Au minimum, logger l'erreur (logger.warning) : aujourd'hui, si le mot de passe
    # 💡 d'application est révoqué, le suivi s'arrête sans que personne ne le sache.
    except imaplib.IMAP4.error:
        pass
    except Exception:
        pass
    return found


# 📘 Boucle infinie `while True` : on attend d'abord 5 min (time.sleep), puis on vérifie.
# 📘 Elle tourne dans un thread séparé, donc elle ne bloque pas l'interface Streamlit.
def _run_loop(gmail_address: str, gmail_password: str) -> None:
    while True:
        time.sleep(_POLL_INTERVAL)
        try:
            poll_once(gmail_address, gmail_password)
        except Exception:
            pass


# 📘 "Idempotent" : l'appeler 1 ou 10 fois donne le même résultat (un seul thread).
# 📘 Utile car Streamlit ré-exécute tout le script à chaque clic de l'utilisateur.
def ensure_running(gmail_address: str, gmail_password: str) -> None:
    """Démarre le thread de suivi de réponses (idempotent). No-op si credentials manquants."""
    # 📘 `global _thread` : sans ce mot-clé, l'affectation créerait une variable LOCALE
    # 📘 à la fonction au lieu de modifier la variable du module.
    global _thread
    if not gmail_address or not gmail_password:
        return
    if _thread is None or not _thread.is_alive():
        # 📘 threading.Thread(target=fonction, args=(...)) prépare un thread qui exécutera
        # 📘 _run_loop(gmail_address, gmail_password). daemon=True : le thread s'arrête tout seul
        # 📘 quand le programme principal se termine (il ne l'empêche pas de quitter).
        # 📘 .start() le lance réellement.
        # 📘 Attention : si les identifiants changent, le thread existant garde les anciens.
        # 💡 Infra : ce thread vit DANS le process Streamlit (perdu au redémarrage, dupliqué si
        # 💡 plusieurs process). Un worker séparé planifié (cron, APScheduler, ou un service type
        # 💡 Railway/systemd) serait plus fiable ; un webhook Gmail (API + Pub/Sub) éviterait le polling.
        _thread = threading.Thread(
            target=_run_loop,
            args=(gmail_address, gmail_password),
            daemon=True,
        )
        _thread.start()


# 📘 .is_alive() : True tant que le thread tourne. Sert à afficher l'état dans l'UI.
def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
