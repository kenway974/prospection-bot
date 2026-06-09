"""
Synchronise les prospects qualifiés vers la base Notion "Prospection (CRM)".

Champs mappés :
  Entreprise   ← prospect.name
  Tel standard ← prospect.phone
  Récap propal ← résumé des problèmes détectés + score
  Status       ← "à contacter"
  mail1        ← brouillon cold email complet
"""

from __future__ import annotations

import requests

from config import config, logger
from services.google_maps import Prospect


# ---------------------------------------------------------------------------
# Config Notion
# ---------------------------------------------------------------------------

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"
DATABASE_ID = "c2507703-1756-4717-aaf2-132a76c00e06"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.notion_api_key}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Helpers de construction de propriétés Notion
# ---------------------------------------------------------------------------

def _title(value: str) -> dict:
    return {"title": [{"text": {"content": value[:2000]}}]}


def _rich_text(value: str) -> dict:
    # Notion limite un bloc rich_text à 2000 caractères
    return {"rich_text": [{"text": {"content": value[:2000]}}]}


def _phone(value: str | None) -> dict:
    return {"phone_number": value or ""}


def _email_prop(value: str | None) -> dict:
    return {"email": value} if value else {"email": None}


def _url_prop(value: str | None) -> dict:
    return {"url": value} if value else {"url": None}


# ---------------------------------------------------------------------------
# Vérification de doublon
# ---------------------------------------------------------------------------

def _already_exists(name: str, phone: str | None = None) -> bool:
    """
    Retourne True si une entrée existe déjà (par nom ET/OU téléphone).
    Double vérification pour éviter les doublons même si le nom diffère légèrement.
    """
    url = f"{NOTION_BASE_URL}/databases/{DATABASE_ID}/query"

    # Vérif par nom
    try:
        payload = {
            "filter": {"property": "Entreprise", "title": {"equals": name}},
            "page_size": 1,
        }
        resp = requests.post(url, headers=_headers(), json=payload,
                             timeout=config.request_timeout)
        resp.raise_for_status()
        if len(resp.json().get("results", [])) > 0:
            return True
    except requests.RequestException as exc:
        logger.warning("    ⚠️  Vérification doublon Notion (nom) échouée : %s", exc)

    # Vérif par téléphone si disponible
    if phone:
        try:
            payload = {
                "filter": {"property": "Tel standard", "phone_number": {"equals": phone}},
                "page_size": 1,
            }
            resp = requests.post(url, headers=_headers(), json=payload,
                                 timeout=config.request_timeout)
            resp.raise_for_status()
            if len(resp.json().get("results", [])) > 0:
                return True
        except requests.RequestException:
            pass

    return False


# ---------------------------------------------------------------------------
# Création d'une page prospect
# ---------------------------------------------------------------------------

def _build_recap(prospect: Prospect) -> str:
    lines = [
        f"Score : {prospect.score}/100",
        f"Mot-clé : {prospect.keyword}",
        f"Adresse : {prospect.address}",
        f"Site web : {prospect.website or 'Aucun'}",
        "",
        "Problèmes détectés :",
    ]
    for i, issue in enumerate(prospect.issues, 1):
        lines.append(f"  {i}. {issue}")
    return "\n".join(lines)


def push_prospect(prospect: Prospect) -> bool:
    """
    Crée une entrée dans la BDD Notion pour ce prospect.
    Retourne True si créé, False si doublon ou erreur.
    """
    if _already_exists(prospect.name, prospect.phone):
        logger.debug("    ↩️  Doublon ignoré : %s", prospect.name)
        return False

    recap = _build_recap(prospect)

    properties: dict = {
        "Entreprise": _title(prospect.name),
        "Tel standard": _phone(prospect.phone),
        "Récap propal": _rich_text(recap),
        "Status": _rich_text("à contacter"),
        "mail1": _rich_text(prospect.email_draft),
    }

    if prospect.email:
        properties["Email"] = _email_prop(prospect.email)

    # Site web → champ LinkedIn si pas d'autre champ URL disponible
    if prospect.website:
        properties["LinkedIn"] = _url_prop(prospect.website)

    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": properties,
    }

    try:
        resp = requests.post(
            f"{NOTION_BASE_URL}/pages",
            headers=_headers(),
            json=payload,
            timeout=config.request_timeout,
        )
        resp.raise_for_status()
        logger.info("    ✅ Notion ← %s", prospect.name)
        return True
    except requests.RequestException as exc:
        logger.error("    ❌ Erreur Notion pour %s : %s", prospect.name, exc)
        if hasattr(exc, "response") and exc.response is not None:
            logger.debug("       Détail : %s", exc.response.text[:300])
        return False


# ---------------------------------------------------------------------------
# Sync batch
# ---------------------------------------------------------------------------

def sync_all(prospects: list[Prospect]) -> None:
    if not config.notion_api_key:
        logger.warning("NOTION_API_KEY manquante → sync Notion ignorée.")
        return

    logger.info("")
    logger.info("🔄 Synchronisation Notion (%d prospects)…", len(prospects))
    created = 0
    for p in prospects:
        if push_prospect(p):
            created += 1

    logger.info("   → %d fiche(s) créée(s) dans Notion.", created)
