"""Factory CRM — retourne l'exporteur correspondant au type choisi."""

from __future__ import annotations
from typing import Optional

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : fichier __init__.py = il fait du dossier services/crm un "package" importable, et
# 📘   expose la FACTORY get_exporter (une fonction qui fabrique le bon objet selon un paramètre).
# 📘 Appelé par : pipeline.py (ÉTAPE 13, export CRM) via `from services.crm import get_exporter`.
# 📘 Appelle : services/crm/notion.py (NotionExporter), services/crm/hubspot.py (HubSpotExporter).
# 📘 Concepts Python à retenir ici : package et __init__.py, pattern Factory, import à la demande,
# 📘   **kwargs, Optional (renvoie un objet OU None).
from services.crm.base import CRMExporter


# 📘 Pattern Factory : l'appelant dit juste "notion" ou "hubspot" et reçoit un objet prêt à
# 📘 l'emploi, sans connaître les classes ni leurs paramètres de construction. Tous les objets
# 📘 renvoyés respectent la même interface CRMExporter (voir base.py) : c'est ce qui permet au
# 📘 pipeline d'appeler .export() sans se soucier du CRM choisi.
# 📘 `**kwargs` récupère les arguments nommés en plus dans un dict (ici database_id pour Notion).
def get_exporter(crm_type: str, api_key: str, **kwargs) -> Optional[CRMExporter]:
    """
    crm_type : "notion" | "hubspot"
    kwargs   : paramètres spécifiques (ex: database_id pour Notion)
    Retourne None si crm_type inconnu ou api_key vide.
    """
    if not api_key:
        # 📘 Garde-fou : sans clé API, pas d'exporteur (None). L'appelant doit donc tester le
        # 📘 résultat.
        return None

    if crm_type == "notion":
        # 📘 Import À LA DEMANDE (dans le if) : on ne charge le code Notion que si on en a besoin.
        from services.crm.notion import NotionExporter
        database_id = kwargs.get("database_id", "")
        if not database_id:
            return None
        return NotionExporter(api_key, database_id)

    if crm_type == "hubspot":
        from services.crm.hubspot import HubSpotExporter
        return HubSpotExporter(api_key)

    # 💡 La chaîne de `if` grandit à chaque nouveau CRM. Un registre (dict {"notion": ..., "hubspot":
    # 💡   ...}) ou un décorateur @register("pipedrive") permettrait d'ajouter un CRM sans toucher
    # 💡   ici.
    return None
