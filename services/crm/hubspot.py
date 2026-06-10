"""Exporteur CRM → HubSpot."""

from __future__ import annotations

from typing import List

import requests

from config import config, logger
from services.google_maps import Prospect
from services.crm.base import CRMExporter

HUBSPOT_BASE_URL = "https://api.hubapi.com"


class HubSpotExporter(CRMExporter):

    def __init__(self, api_key: str):
        self._api_key = api_key

    @property
    def crm_name(self) -> str:
        return "HubSpot"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _prospect_to_properties(self, p: Prospect) -> dict:
        parts = p.name.strip().split(" ", 1)
        firstname = parts[0]
        lastname  = parts[1] if len(parts) > 1 else ""

        recap = f"Score : {p.score}/100\n"
        if p.issues:
            recap += "Problèmes : " + " | ".join(p.issues[:5])

        return {
            "firstname":      firstname,
            "lastname":       lastname,
            "company":        p.name,
            "phone":          p.phone or "",
            "email":          p.email or "",
            "website":        p.website or "",
            "address":        p.address or "",
            "hs_lead_status": "NEW",
            "description":    recap[:500],
        }

    def _find_by_email(self, email: str) -> bool:
        """Retourne True si un contact avec cet email existe déjà."""
        if not email:
            return False
        try:
            resp = requests.post(
                f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts/search",
                headers=self._headers(),
                json={
                    "filterGroups": [{
                        "filters": [{"propertyName": "email", "operator": "EQ", "value": email}]
                    }],
                    "limit": 1,
                },
                timeout=config.request_timeout,
            )
            resp.raise_for_status()
            return resp.json().get("total", 0) > 0
        except requests.RequestException:
            return False

    def _push_one(self, p: Prospect) -> bool:
        if p.email and self._find_by_email(p.email):
            logger.debug("    ↩️  HubSpot — doublon ignoré : %s (%s)", p.name, p.email)
            return False

        try:
            resp = requests.post(
                f"{HUBSPOT_BASE_URL}/crm/v3/objects/contacts",
                headers=self._headers(),
                json={"properties": self._prospect_to_properties(p)},
                timeout=config.request_timeout,
            )
            if resp.status_code == 409:
                logger.debug("    ↩️  HubSpot — doublon (409) : %s", p.name)
                return False
            resp.raise_for_status()
            logger.info("    ✅ HubSpot ← %s", p.name)
            return True
        except requests.RequestException as exc:
            logger.error("    ❌ Erreur HubSpot pour %s : %s", p.name, exc)
            return False

    # ------------------------------------------------------------------
    # Interface CRMExporter
    # ------------------------------------------------------------------

    def export(self, prospects: List[Prospect]) -> int:
        logger.info("")
        logger.info("🔄 Synchronisation HubSpot (%d prospects)…", len(prospects))
        created = sum(1 for p in prospects if self._push_one(p))
        logger.info("   → %d contact(s) créé(s) dans HubSpot.", created)
        return created
