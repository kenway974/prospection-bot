"""Exporteur CRM → Notion."""

from __future__ import annotations

# 📘 re = expressions régulières (motifs de recherche dans du texte), utilisées plus bas pour
# 📘 extraire un identifiant de 32 caractères hexadécimaux.
import re
from typing import Dict, List, Optional, Tuple

import requests

from config import config, logger
from services.google_maps import Prospect
from services.crm.base import CRMExporter

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : crée une fiche (page) Notion par prospect dans une base Notion, sans doublon, et
# 📘   sait mettre à jour son statut. Une des "stratégies" du pattern Strategy de services/crm.
# 📘 Appelé par : services/crm/__init__.py (get_exporter), pipeline.py (verify_access, export,
# 📘   update_status après envoi), app.py (relances), services/scheduler.py, services/notion_sync.py.
# 📘 Appelle : l'API Notion (api.notion.com/v1) via requests ; config (timeout), logger.
# 📘 Concepts Python à retenir ici : regex (re.search), héritage, @staticmethod, tuple de retour
# 📘   (ok, message), déballage de liste avec `*`, codes HTTP (200/401/404), try/except.
# 📘 Constantes de module : version de l'API Notion demandée et adresse de base des appels.
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
    # 📘 `(raw or "")` : si raw est None, on utilise "" pour que .strip() ne plante pas.
    raw = (raw or "").strip()
    if not raw:
        return ""
    # Retire la query string puis garde le dernier segment de chemin
    raw = raw.split("?")[0].rstrip("/").split("/")[-1]
    raw = raw.replace("-", "")
    # 📘 r"[0-9a-fA-F]{32}" : motif = exactement 32 caractères hexadécimaux à la suite (le `r`
    # 📘 devant la chaîne = "raw string", les \ n'y sont pas interprétés). match.group(0) = le texte
    # 📘 trouvé. Si rien ne correspond, on renvoie raw tel quel.
    match = re.search(r"[0-9a-fA-F]{32}", raw)
    return match.group(0) if match else raw


# 📘 Hérite de CRMExporter (contrat : crm_name + export). Ajoute verify_access et update_status,
# 📘 propres à Notion (hors contrat, d'où les hasattr côté pipeline.py).
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

    # 📘 Renvoie un TUPLE (ok, message) : l'appelant fait `_ok, _msg = exporter.verify_access()`
    # 📘 ("déballage" : chaque valeur va dans sa variable). 200 = OK, 401 = clé refusée,
    # 📘 404 = base introuvable ou non partagée avec l'intégration.
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

    # 📘 @staticmethod : méthode qui n'utilise pas `self` (pas besoin de l'objet), juste rangée dans
    # 📘 la classe. Chacune fabrique le petit dict JSON qu'attend Notion pour un type de propriété.
    # 📘 v[:2000] : Notion limite un bloc de texte à 2000 caractères.
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
        # 📘 Anti-doublon : on cherche une fiche avec le même nom (propriété "Entreprise"), puis avec
        # 📘 le même téléphone si on en a un. `*( [...] if phone else [] )` insère 0 ou 1 filtre dans
        # 📘 la liste (l'étoile "déballe" la liste). Une erreur réseau compte comme "pas trouvé".
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
        # 📘 enumerate(liste, 1) donne (numéro, élément) en commençant à 1 : "1. ...", "2. ...".
        for i, issue in enumerate(p.issues, 1):
            lines.append(f"  {i}. {issue}")
        return "\n".join(lines)

    def _push_one(self, p: Prospect) -> Optional[str]:
        # 📘 Renvoie l'id de la page Notion créée (str), ou None si doublon/erreur (Optional[str]).
        if self._already_exists(p.name, p.phone):
            logger.debug("    ↩️  Notion — doublon ignoré : %s", p.name)
            return None

        # 📘 Les clés ("Entreprise", "Tel standard", "Status"…) doivent correspondre EXACTEMENT aux
        # 📘 noms des colonnes de ta base Notion, sinon Notion répond 400.
        # 💡 Le site web est rangé dans la propriété nommée "LinkedIn" : à vérifier (erreur ou astuce
        # 💡   liée à ta base ?). Rendre ces noms de propriétés configurables (un dict de mapping
        # 💡   dans les réglages) éviterait de modifier le code quand la base Notion change.
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
        # 📘 L'attribut _last_exported_ids n'est créé QUE lorsqu'export() est appelé ; pipeline.py le
        # 📘 lit ensuite ({place_id: id de page Notion}) pour pouvoir mettre la fiche à "contacté"
        # 📘 plus tard.
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
        # 📘 PATCH = méthode HTTP pour modifier partiellement une ressource existante (ici une page).
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
