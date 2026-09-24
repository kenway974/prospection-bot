"""
Envoi de SMS via l'API Brevo (ex-Sendinblue).
100 SMS/jour offerts sur le plan gratuit.

Doc : https://developers.brevo.com/reference/sendtransacsms
"""

from __future__ import annotations

import time
# 📘 `requests` n'est PAS dans la bibliothèque standard : c'est un paquet externe (installé
# 📘 via requirements.txt) qui sert à faire des appels HTTP vers des API web.
import requests

from config import config, logger
from services.google_maps import Prospect


# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : envoyer un SMS de prospection court (≤ 160 caractères) aux prospects qui ont
# 📘         un numéro de MOBILE, via l'API HTTP de Brevo.
# 📘 Appelé par : main.py et pipeline.py (send_all_sms).
# 📘 Appelle : l'API REST Brevo (requests.post), config (clé API, ton nom), Prospect.
# 📘 Concepts Python à retenir ici : requests (HTTP POST + JSON), str.replace/startswith,
# 📘   listes de templates + str.format, hash (hashlib.md5) pour un choix déterministe,
# 📘   import local dans une fonction, os.getenv, slicing [:160], try/except.
#
# 📘 URL de l'API : l'adresse web à laquelle on envoie la demande d'envoi de SMS.
BREVO_SMS_URL = "https://api.brevo.com/v3/transactionalSMS/sms"
DELAY_BETWEEN_SMS = 2   # secondes entre chaque envoi


# 📘 `str | None` : la fonction renvoie soit un texte, soit None ("rien") si le numéro
# 📘 n'est pas utilisable. E.164 = format international standard (+33…) exigé par l'API.
def _format_phone(phone: str) -> str | None:
    """
    Convertit un numéro français en format international E.164.
    Ex: 06 12 34 56 78 → +33612345678
    """
    # 📘 Les .replace() s'enchaînent : chacun renvoie un NOUVEAU texte (un str ne se modifie
    # 📘 jamais "sur place" en Python, on dit qu'il est immuable).
    cleaned = phone.replace(" ", "").replace(".", "").replace("-", "")
    if cleaned.startswith("0"):
        # 📘 cleaned[1:] = "slicing" : le texte à partir du 2e caractère (on retire le 0 initial).
        cleaned = "+33" + cleaned[1:]
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    # 📘 POURQUOI : un SMS vers un fixe ne sert à rien (et coûte des crédits), on ne garde
    # 📘 que les 06/07. Limite : seuls les numéros français sont bien gérés ici.
    # Garde uniquement les mobiles (06, 07)
    local = cleaned.replace("+33", "0")
    if not (local.startswith("06") or local.startswith("07")):
        return None
    return cleaned


# 📘 Listes de templates : {business} et {sender} sont des "trous" remplis plus tard par
# 📘 .format(business=..., sender=...). Plusieurs variantes = messages moins répétitifs.
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


# 📘 hashlib.md5(...) calcule une "empreinte" du place_id ; % n (modulo) la ramène entre
# 📘 0 et n-1. Même prospect ⇒ toujours le même template (déterministe), mais les
# 📘 prospects sont répartis entre les variantes.
def _sms_variant(place_id: str, n: int) -> int:
    """Choisit un template de façon déterministe via le hash du place_id."""
    # 📘 Import "local" (dans la fonction) : fonctionne, mais par convention on met plutôt
    # 📘 les imports en haut du fichier.
    import hashlib
    return int(hashlib.md5(place_id.encode()).hexdigest(), 16) % n


def _build_sms(prospect: Prospect) -> str:
    """Génère un SMS naturel et percutant (max 160 caractères)."""
    # 📘 os.getenv("SMS_HOOK", "") lit une variable d'environnement (réglage externe au code),
    # 📘 avec "" comme valeur par défaut si elle n'existe pas.
    import os
    custom_hook = os.getenv("SMS_HOOK", "").strip()
    if custom_hook:
        # 📘 [:160] tronque à 160 caractères : la taille d'un SMS "simple". Au-delà, le SMS est
        # 📘 découpé en plusieurs (et facturé plusieurs fois).
        return custom_hook.format(name=prospect.name)[:160]

    # 📘 `a or b` : prend a si a est "vrai" (non vide), sinon b. Pratique pour une valeur de repli.
    sender = config.your_name or "un développeur web"
    business = prospect.name

    if not prospect.has_website():
        tpl = _SMS_NO_SITE[_sms_variant(prospect.place_id, len(_SMS_NO_SITE))]
        msg = tpl.format(business=business, sender=sender)
    else:
        # 📘 Expression conditionnelle sur une ligne : `valeur_si_vrai if condition else valeur_si_faux`.
        # 📘 On garde le 1er problème détecté par l'audit, avant la flèche "→".
        issue = prospect.issues[0].split("→")[0].strip() if prospect.issues else None
        if issue:
            tpl = _SMS_WITH_ISSUE[_sms_variant(prospect.place_id, len(_SMS_WITH_ISSUE))]
            msg = tpl.format(business=business, issue=issue.lower(), sender=sender)
        else:
            msg = (
                f"Bonjour ! J'ai quelques idées pour améliorer la visibilité de {business} en ligne. "
                f"Dispo pour un échange rapide ? — {sender}"
            )

    # 💡 Tronquer brutalement à 160 peut couper la signature ou un mot en plein milieu.
    # 💡 Et le tiret long « — » ou des lettres comme ê/ç ne sont pas dans l'alphabet SMS "GSM" :
    # 💡 le SMS passe alors en Unicode, limité à 70 caractères par segment → un texte de 160
    # 💡 caractères = 3 SMS facturés. Remplacer « — » par « - » et viser ≤ 70 ou ≤ 160 GSM.
    return msg[:160]


def send_sms(prospect: Prospect) -> bool:
    """
    Envoie un SMS au prospect via Brevo.
    Retourne True si succès.
    """
    # 📘 Série de "gardes" : on sort tôt (return False) dès qu'une condition manque. Ça évite
    # 📘 d'imbriquer des if les uns dans les autres.
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

    # 📘 payload = le contenu JSON envoyé à l'API. "sender" limité à 11 caractères : c'est la
    # 📘 limite des noms d'expéditeur alphanumériques pour les SMS.
    payload = {
        "sender": (config.your_name[:11] if config.your_name else "ProspectBot"),
        "recipient": phone,
        "content": message,
        "type": "transactional",
    }
    # 📘 La clé API passe dans un en-tête HTTP : c'est un SECRET (ne jamais la mettre dans le
    # 📘 code ni sur GitHub, elle vient de config / du fichier .env).
    headers = {
        "api-key": config.brevo_api_key,
        "Content-Type": "application/json",
    }

    try:
        # 📘 requests.post(..., json=payload) convertit le dict en JSON et l'envoie. timeout=10 :
        # 📘 on n'attend pas plus de 10 s. Codes HTTP 200/201 = succès ; sinon on log l'erreur.
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
    # 📘 requests.RequestException = toutes les erreurs réseau de requests (timeout, DNS…).
    except requests.RequestException as exc:
        logger.error("    ❌ Erreur réseau SMS (%s) : %s", prospect.name, exc)
        return False


# 💡 Le SMS de prospection vers des particuliers/entreprises est encadré (opt-out "STOP"
# 💡 obligatoire en France, horaires autorisés) : ajouter une mention STOP et un filtre
# 💡 horaire limiterait les risques légaux et les signalements.
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
        # 📘 `is True` / `is False` compare à la valeur exacte. Ici send_sms renvoie toujours un
        # 📘 booléen : un échec est compté "failed" si le prospect a un téléphone (même un fixe
        # 📘 ignoré), "skipped" s'il n'en a pas du tout.
        if result is True:
            stats["sent"] += 1
            # 💡 Comme pour les emails, une file de tâches avec retries et un compteur du quota
            # 💡 quotidien Brevo éviteraient de bloquer l'app et de dépasser le quota gratuit.
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
