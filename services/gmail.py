"""
Envoi de cold emails via SMTP Gmail.

Prérequis :
  - Activer la validation en 2 étapes sur le compte Google
  - Générer un "Mot de passe d'application" (myaccount.google.com/apppasswords)
  - Renseigner GMAIL_ADDRESS et GMAIL_APP_PASSWORD dans .env / l'interface
"""

from __future__ import annotations

import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from config import config, logger
from services.google_maps import Prospect


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
DELAY_BETWEEN_MAILS = 3   # secondes entre chaque envoi (anti-spam)


def _parse_subject(draft: str) -> tuple[str, str]:
    """Extrait le sujet et le corps du brouillon généré par mailer.py."""
    lines = draft.strip().splitlines()
    subject = ""
    body_lines = []
    in_body = False

    for line in lines:
        if line.startswith("OBJET :") and not in_body:
            subject = line.replace("OBJET :", "").strip()
        elif line.strip() == "" and not in_body and subject:
            in_body = True
        elif in_body:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    return subject, body


def send_email(
    to_address: str,
    draft: str,
    gmail_address: str,
    gmail_app_password: str,
    prospect_name: str = "",
) -> bool:
    """
    Envoie un email via SMTP Gmail.
    Retourne True si succès, False sinon.
    """
    subject, body = _parse_subject(draft)
    if not subject:
        subject = f"Votre présence en ligne — {prospect_name}"
    if not body:
        body = draft

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = to_address
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(gmail_address, gmail_app_password)
            server.sendmail(gmail_address, to_address, msg.as_string())
        logger.info("    📤 Mail envoyé → %s (%s)", prospect_name, to_address)
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("    ❌ Authentification Gmail échouée. Vérifiez le mot de passe d'application.")
        return False
    except Exception as exc:
        logger.error("    ❌ Erreur envoi mail (%s) : %s", prospect_name, exc)
        return False


def send_all(
    prospects: list[Prospect],
    gmail_address: str,
    gmail_app_password: str,
) -> dict[str, int]:
    """
    Envoie les cold emails à tous les prospects qui ont un email renseigné.
    Retourne un dict {sent, skipped, failed}.
    """
    stats = {"sent": 0, "skipped": 0, "failed": 0}

    if not gmail_address or not gmail_app_password:
        logger.warning("Identifiants Gmail manquants → envoi ignoré.")
        stats["skipped"] = len(prospects)
        return stats

    logger.info("")
    logger.info("📤 Envoi des cold emails…")

    for p in prospects:
        if not p.email_draft:
            stats["skipped"] += 1
            continue

        # On utilise l'email stocké dans le prospect (renseigné manuellement ou via enrichissement futur)
        to_address = getattr(p, "email", None)
        if not to_address:
            logger.debug("    ⏭️  %s : pas d'email → ignoré", p.name)
            stats["skipped"] += 1
            continue

        success = send_email(
            to_address=to_address,
            draft=p.email_draft,
            gmail_address=gmail_address,
            gmail_app_password=gmail_app_password,
            prospect_name=p.name,
        )
        if success:
            stats["sent"] += 1
            time.sleep(DELAY_BETWEEN_MAILS)
        else:
            stats["failed"] += 1

    logger.info(
        "   → %d envoyé(s) | %d ignoré(s) | %d échec(s)",
        stats["sent"], stats["skipped"], stats["failed"],
    )
    return stats
