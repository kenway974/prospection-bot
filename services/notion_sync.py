"""Shim de compatibilité — délègue à services/crm/notion.py."""

from __future__ import annotations
from typing import List

from config import config, logger
from services.google_maps import Prospect

DATABASE_ID = "c2507703-1756-4717-aaf2-132a76c00e06"


def sync_all(prospects: List[Prospect]) -> None:
    if not config.notion_api_key:
        logger.warning("NOTION_API_KEY manquante → sync Notion ignorée.")
        return
    from services.crm.notion import NotionExporter
    NotionExporter(config.notion_api_key, DATABASE_ID).export(prospects)
