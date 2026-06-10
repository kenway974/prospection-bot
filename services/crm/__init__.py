"""Factory CRM — retourne l'exporteur correspondant au type choisi."""

from __future__ import annotations
from typing import Optional

from services.crm.base import CRMExporter


def get_exporter(crm_type: str, api_key: str, **kwargs) -> Optional[CRMExporter]:
    """
    crm_type : "notion" | "hubspot"
    kwargs   : paramètres spécifiques (ex: database_id pour Notion)
    Retourne None si crm_type inconnu ou api_key vide.
    """
    if not api_key:
        return None

    if crm_type == "notion":
        from services.crm.notion import NotionExporter
        database_id = kwargs.get("database_id", "")
        if not database_id:
            return None
        return NotionExporter(api_key, database_id)

    if crm_type == "hubspot":
        from services.crm.hubspot import HubSpotExporter
        return HubSpotExporter(api_key)

    return None
