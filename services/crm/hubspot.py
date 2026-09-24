"""Exporteur CRM → HubSpot."""

from __future__ import annotations

from typing import List

# 📘 requests : bibliothèque (à installer, cf. requirements.txt) pour faire des appels HTTP
# 📘 vers des API web : requests.get(...), requests.post(...), etc.
import requests

from config import config, logger
from services.google_maps import Prospect
from services.crm.base import CRMExporter

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : envoie les prospects vers HubSpot sous forme de "contacts" (API REST v3), en
# 📘   évitant les doublons par email. Une des "stratégies" du pattern Strategy de services/crm.
# 📘 Appelé par : services/crm/__init__.py (get_exporter("hubspot", clé)), donc par pipeline.py.
# 📘 Appelle : l'API HubSpot (api.hubapi.com) via requests ; config (timeout), logger.
# 📘 Concepts Python à retenir ici : héritage d'une classe abstraite, méthodes "privées" (_x),
# 📘   @property, appels HTTP avec requests (headers, json, timeout, raise_for_status).
HUBSPOT_BASE_URL = "https://api.hubapi.com"


# 📘 `class HubSpotExporter(CRMExporter)` : HÉRITE de CRMExporter. Elle doit donc définir
# 📘 crm_name et export() (le contrat), et peut ajouter ses propres méthodes internes (_...).
class HubSpotExporter(CRMExporter):

    def __init__(self, api_key: str):
        # 📘 self._api_key : attribut "privé" par convention (préfixe _), propre à CET objet.
        self._api_key = api_key

    @property
    def crm_name(self) -> str:
        return "HubSpot"

    # 📘 En-têtes HTTP : "Bearer <clé>" = façon standard de s'authentifier auprès d'une API.
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _prospect_to_properties(self, p: Prospect) -> dict:
        # 📘 split(" ", 1) coupe au 1er espace seulement. Attention : c'est le NOM DE L'ENTREPRISE
        # 📘 qui est découpé en prénom/nom ("Boulangerie Martin" → firstname "Boulangerie", lastname
        # 📘 "Martin").
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
            # 📘 Recherche d'un contact existant par email (POST .../contacts/search avec un filtre
            # 📘 EQ). raise_for_status() lève une exception si HubSpot répond une erreur (4xx/5xx).
            # 📘 En cas d'erreur réseau on renvoie False ("pas trouvé") : le contact sera donc tenté
            # 📘 quand même.
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
            # 📘 409 = code HTTP "Conflict" : HubSpot signale que le contact existe déjà.
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
        # 📘 sum(1 for p in prospects if ...) : compte les prospects créés avec un "générateur" (une
        # 📘 boucle compacte entre parenthèses). Un appel HTTP (voire deux) par prospect, en série.
        # 💡 pipeline.py ne remplace pas le logger ni le config de CE module (seulement ceux de
        # 💡   services/crm/notion) : les logs HubSpot partent dans la console, pas dans l'UI. Passer
        # 💡   logger/config au constructeur (injection de dépendances) réglerait ça. L'API "batch"
        # 💡   de HubSpot (jusqu'à 100 contacts par appel) réduirait aussi le nombre d'appels.
        created = sum(1 for p in prospects if self._push_one(p))
        logger.info("   → %d contact(s) créé(s) dans HubSpot.", created)
        return created
