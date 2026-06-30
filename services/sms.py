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


_SMS_NO_SITE = [
    "Bonjour ! {business} n'a pas de site web — vous perdez des clients chaque jour. Je peux en créer un. Dispo ? — {sender}",
    "Bonjour ! J'ai cherché {business} sur Google… pas de site. Ça vous coûte des clients. On en parle ? — {sender}",
    "Bonjour ! Je n'ai pas trouvé de site pour {business}. En 2 semaines, je peux en créer un efficace. Dispo ? — {sender}",
]

_SMS_WITH_ISSUE = [
    "Bonjour ! J'ai regardé le site de {business} : {issue}. Je peux corriger ça. Un appel de 15 min ? — {sender}",
    "Bonjour ! Le site de {business} a un point qui coince : {issue}. Je m'en occupe. On en parle ? — {sender}",
    "Bonjour ! Petit point sur {business} : {issue}. Je peux régler ça rapidement. Dispo cette semaine ? — {sender}",
]


def _sms_variant(place_id: str, n: int) -> int:
    """Choisit un template de façon déterministe via le hash du place_id."""
    import hashlib
    return int(hashlib.md5(place_id.encode()).hexdigest(), 16) % n


def _build_sms(prospect: Prospect) -> str:
    """Génère un SMS naturel et percutant (max 160 caractères)."""
    import os
    custom_hook = os.getenv("SMS_HOOK", "").strip()
    if custom_hook:
        return custom_hook.format(name=prospect.name)[:160]

    sender = config.your_name or "un développeur web"
    business = prospect.name

    if not prospect.has_website():
        tpl = _SMS_NO_SITE[_sms_variant(prospect.place_id, len(_SMS_NO_SITE))]
        msg = tpl.format(business=business, sender=sender)
    else:
        issue = prospect.issues[0].split("→")[0].strip() if prospect.issues else None
        if issue:
            tpl = _SMS_WITH_ISSUE[_sms_variant(prospect.place_id, len(_SMS_WITH_ISSUE))]
            msg = tpl.format(business=business, issue=issue.lower(), sender=sender)
        else:
            msg = (
                f"Bonjour ! J'ai quelques idées pour améliorer la visibilité de {business} en ligne. "
                f"Dispo pour un échange rapide ? — {sender}"
            )

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
