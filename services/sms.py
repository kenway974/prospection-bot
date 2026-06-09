"""
Envoi de SMS via l'API Brevo (ex-Sendinblue).
100 SMS/jour offerts sur le plan gratuit.

Doc : https://developers.brevo.com/reference/sendtransacsms
"""

from __future__ import annotations

import time
import requests

from config import config, logger
from services.google_maps import Prospect


BREVO_SMS_URL = "https://api.brevo.com/v3/transactionalSMS/sms"
DELAY_BETWEEN_SMS = 2   # secondes entre chaque envoi


def _format_phone(phone: str) -> str | None:
    """
    Convertit un numéro français en format international E.164.
    Ex: 06 12 34 56 78 → +33612345678
    """
    cleaned = phone.replace(" ", "").replace(".", "").replace("-", "")
    if cleaned.startswith("0"):
        cleaned = "+33" + cleaned[1:]
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    # Garde uniquement les mobiles (06, 07)
    local = cleaned.replace("+33", "0")
    if not (local.startswith("06") or local.startswith("07")):
        return None
    return cleaned


def _build_sms(prospect: Prospect) -> str:
    """Génère un SMS court et percutant (max 160 caractères)."""
    import os
    custom_hook = os.getenv("SMS_HOOK", "").strip()
    if custom_hook:
        msg = custom_hook.format(name=prospect.name)
    else:
        name = config.your_name
        issue = prospect.issues[0].split("→")[0].strip() if prospect.issues else "votre présence en ligne"
        msg = (
            f"Bonjour, je suis {name}. "
            f"J'ai analysé {prospect.name} : {issue}. "
            f"Dispo pour un retour gratuit ? {config.your_email}"
        )
    # Tronque à 160 caractères si nécessaire
    return msg[:160]


def send_sms(prospect: Prospect) -> bool:
    """
    Envoie un SMS au prospect via Brevo.
    Retourne True si succès.
    """
    if not config.brevo_api_key:
        logger.warning("BREVO_API_KEY manquante → SMS ignoré.")
        return False

    if not prospect.phone:
        logger.debug("    ⏭️  %s : pas de téléphone.", prospect.name)
        return False

    phone = _format_phone(prospect.phone)
    if not phone:
        logger.debug(
            "    ⏭️  %s : numéro fixe ou invalide (%s) → ignoré.",
            prospect.name, prospect.phone,
        )
        return False

    message = _build_sms(prospect)

    payload = {
        "sender": (config.your_name[:11] if config.your_name else "ProspectBot"),
        "recipient": phone,
        "content": message,
        "type": "transactional",
    }
    headers = {
        "api-key": config.brevo_api_key,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(BREVO_SMS_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code in (200, 201):
            logger.info("    📱 SMS envoyé → %s (%s)", prospect.name, phone)
            return True
        else:
            logger.error(
                "    ❌ Brevo erreur %d pour %s : %s",
                resp.status_code, prospect.name, resp.text[:200],
            )
            return False
    except requests.RequestException as exc:
        logger.error("    ❌ Erreur réseau SMS (%s) : %s", prospect.name, exc)
        return False


def send_all_sms(prospects: list[Prospect]) -> dict:
    """Envoie un SMS à tous les prospects avec un numéro mobile."""
    stats = {"sent": 0, "skipped": 0, "failed": 0}

    if not config.brevo_api_key:
        logger.warning("BREVO_API_KEY manquante → envoi SMS ignoré.")
        stats["skipped"] = len(prospects)
        return stats

    logger.info("")
    logger.info("📱 Envoi des SMS via Brevo (%d prospects)…", len(prospects))

    for p in prospects:
        result = send_sms(p)
        if result is True:
            stats["sent"] += 1
            time.sleep(DELAY_BETWEEN_SMS)
        elif result is False and p.phone:
            stats["failed"] += 1
        else:
            stats["skipped"] += 1

    logger.info(
        "   → %d envoyé(s) | %d ignoré(s) | %d échec(s)",
        stats["sent"], stats["skipped"], stats["failed"],
    )
    return stats
