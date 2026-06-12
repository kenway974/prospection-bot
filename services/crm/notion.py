"""Exporteur CRM → Notion."""

from __future__ import annotations

from typing import Dict, List, Optional

import requests

from config import config, logger
from services.google_maps import Prospect
from services.crm.base import CRMExporter

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL    = "https://api.notion.com/v1"


class NotionExporter(CRMExporter):

    def __init__(self, api_key: str, database_id: str):
        self._api_key     = api_key
        self._database_id = database_id

    @property
    def crm_name(self) -> str:
        return "Notion"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Helpers propriétés Notion
    # ------------------------------------------------------------------

    @staticmethod
    def _title(v: str)              -> dict: return {"title": [{"text": {"content": v[:2000]}}]}
    @staticmethod
    def _rich_text(v: str)          -> dict: return {"rich_text": [{"text": {"content": v[:2000]}}]}
    @staticmethod
    def _phone(v: str | None)       -> dict: return {"phone_number": v or ""}
    @staticmethod
    def _email_prop(v: str | None)  -> dict: return {"email": v} if v else {"email": None}
    @staticmethod
    def _url_prop(v: str | None)    -> dict: return {"url": v} if v else {"url": None}

    def _already_exists(self, name: str, phone: str | None) -> bool:
        url = f"{NOTION_BASE_URL}/databases/{self._database_id}/query"
        for filter_payload in [
            {"property": "Entreprise", "title": {"equals": name}},
            *(
                [{"property": "Tel standard", "phone_number": {"equals": phone}}]
                if phone else []
            ),
        ]:
            try:
                resp = requests.post(
                    url, headers=self._headers(),
                    json={"filter": filter_payload, "page_size": 1},
                    timeout=config.request_timeout,
                )
                resp.raise_for_status()
                if resp.json().get("results"):
                    return True
            except requests.RequestException:
                pass
        return False

    def _build_recap(self, p: Prospect) -> str:
        lines = [
            f"Score : {p.score}/100",
            f"Mot-clé : {p.keyword}",
            f"Adresse : {p.address}",
            f"Site web : {p.website or 'Aucun'}",
            "",
            "Problèmes détectés :",
        ]
        for i, issue in enumerate(p.issues, 1):
            lines.append(f"  {i}. {issue}")
        return "\n".join(lines)

    def _push_one(self, p: Prospect) -> Optional[str]:
        if self._already_exists(p.name, p.phone):
            logger.debug("    ↩️  Notion — doublon ignoré : %s", p.name)
            return None

        properties: dict = {
            "Entreprise":   self._title(p.name),
            "Tel standard": self._phone(p.phone),
            "Récap propal": self._rich_text(self._build_recap(p)),
            "Status":       self._rich_text("à contacter"),
            "mail1":        self._rich_text(p.email_draft),
        }
        if p.email:
            properties["Email"] = self._email_prop(p.email)
        if p.website:
            properties["LinkedIn"] = self._url_prop(p.website)

        try:
            resp = requests.post(
                f"{NOTION_BASE_URL}/pages",
                headers=self._headers(),
                json={"parent": {"database_id": self._database_id}, "properties": properties},
                timeout=config.request_timeout,
            )
            resp.raise_for_status()
            logger.info("    ✅ Notion ← %s", p.name)
            return resp.json().get("id")
        except requests.RequestException as exc:
            logger.error("    ❌ Erreur Notion pour %s : %s", p.name, exc)
            return None

    # ------------------------------------------------------------------
    # Interface CRMExporter
    # ------------------------------------------------------------------

    def export(self, prospects: List[Prospect]) -> int:
        logger.info("")
        logger.info("🔄 Synchronisation Notion (%d prospects)…", len(prospects))
        self._last_exported_ids: Dict[str, str] = {}
        for p in prospects:
            page_id = self._push_one(p)
            if page_id:
                self._last_exported_ids[p.place_id] = page_id
        created = len(self._last_exported_ids)
        logger.info("   → %d fiche(s) créée(s) dans Notion.", created)
        return created

    def update_status(self, page_id: str, status: str) -> bool:
        """Met à jour le statut d'une fiche Notion (PATCH /pages/{id})."""
        try:
            resp = requests.patch(
                f"{NOTION_BASE_URL}/pages/{page_id}",
                headers=self._headers(),
                json={"properties": {"Status": self._rich_text(status)}},
                timeout=config.request_timeout,
            )
            resp.raise_for_status()
            logger.debug("    🔄 Notion statut → '%s' (%s…)", status, page_id[:8])
            return True
        except requests.RequestException as exc:
            logger.error("    ❌ Notion update_status : %s", exc)
            return False
