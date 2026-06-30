"""Exporteur CRM → Notion."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import requests

from config import config, logger
from services.google_maps import Prospect
from services.crm.base import CRMExporter

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL    = "https://api.notion.com/v1"


def clean_database_id(raw: str) -> str:
    """
    Extrait un Database ID Notion propre, même si l'utilisateur colle l'URL
    complète ou le lien « Copier le lien » (qui ajoute ?v=...&source=copy_link).

    Exemples acceptés :
      - c250770317564717aaf2132a76c00e06
      - c250770317564717aaf2132a76c00e06?v=ca57...&source=copy_link
      - https://notion.so/MonEspace/c2507703...?v=...
      - c2507703-1756-4717-aaf2-132a76c00e06
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    # Retire la query string puis garde le dernier segment de chemin
    raw = raw.split("?")[0].rstrip("/").split("/")[-1]
    raw = raw.replace("-", "")
    match = re.search(r"[0-9a-fA-F]{32}", raw)
    return match.group(0) if match else raw


class NotionExporter(CRMExporter):

    def __init__(self, api_key: str, database_id: str):
        self._api_key     = api_key.strip()
        self._database_id = clean_database_id(database_id)

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
    # Vérification d'accès — appelée avant l'export pour un diagnostic clair
    # ------------------------------------------------------------------

    def verify_access(self) -> Tuple[bool, str]:
        """
        Vérifie que la clé API peut lire la base.
        Retourne (ok, message) avec un message d'erreur explicite et actionnable.
        """
        if not self._api_key:
            return False, "Clé API Notion manquante."
        if not self._database_id:
            return False, "Database ID Notion manquant ou invalide."
        try:
            resp = requests.get(
                f"{NOTION_BASE_URL}/databases/{self._database_id}",
                headers=self._headers(),
                timeout=config.request_timeout,
            )
        except requests.RequestException as exc:
            return False, f"Connexion à Notion impossible : {exc}"

        if resp.status_code == 200:
            return True, "Accès à la base OK."
        if resp.status_code == 401:
            return False, (
                "Clé API refusée (401). Vérifie le token d'intégration "
                "(notion.so/my-integrations)."
            )
        if resp.status_code == 404:
            return False, (
                "Base introuvable (404). Deux causes possibles : "
                "(1) l'intégration n'est pas connectée à la base — ouvre la base → "
                "⋯ (en haut à droite) → Connexions → ajoute ton intégration ; "
                "(2) le Database ID est incorrect (ne colle que les 32 caractères, "
                "sans le « ?v=… » du lien)."
            )
        return False, f"Notion a répondu {resp.status_code} : {resp.text[:200]}"

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
            if resp.status_code != 200:
                # Surface le message d'erreur réel de Notion (propriété manquante, etc.)
                logger.error("    ❌ Notion %s pour %s : %s", resp.status_code, p.name, resp.text[:300])
                return None
            logger.info("    ✅ Notion ← %s", p.name)
            return resp.json().get("id")
        except requests.RequestException as exc:
            logger.error("    ❌ Erreur réseau Notion pour %s : %s", p.name, exc)
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
