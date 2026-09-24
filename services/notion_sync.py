"""Shim de compatibilité — délègue à services/crm/notion.py."""

# 📘 `from __future__ import annotations` : annotations de type évaluées "plus tard",
# 📘 ce qui autorise une syntaxe moderne sur d'anciennes versions de Python.
# 📘 typing.List[Prospect] = "liste d'objets Prospect" (ancienne écriture de list[Prospect]).
from __future__ import annotations
from typing import List

from config import config, logger
from services.google_maps import Prospect

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : "shim" (cale de compatibilité) : garde l'ancien point d'entrée sync_all() mais
# 📘         délègue tout le travail au nouveau module services/crm/notion.py.
# 📘 Appelé par : main.py (sync_all) ; pipeline.py l'importe aussi pour remplacer ses
# 📘              variables `logger` et `config` (logs affichés dans l'interface).
# 📘 Appelle : services/crm/notion.py (NotionExporter), qui lui parle à l'API Notion.
# 📘 Concepts Python à retenir ici : shim/rétrocompatibilité, garde + return anticipé,
# 📘   import local (différé), instanciation d'une classe puis appel de méthode.
#
# 📘 L'identifiant de la base Notion cible est écrit "en dur" dans le code.
# 💡 Le mettre dans la config (.env, ex. NOTION_DATABASE_ID) permettrait de changer de base
# 💡 (test / prod, autre client) sans modifier le code.
DATABASE_ID = "c2507703-1756-4717-aaf2-132a76c00e06"


def sync_all(prospects: List[Prospect]) -> None:
    # 📘 Garde : sans clé API Notion, on prévient dans les logs et on sort (return) sans rien faire.
    if not config.notion_api_key:
        logger.warning("NOTION_API_KEY manquante → sync Notion ignorée.")
        return
    # 📘 Import local : services.crm.notion n'est chargé que si on en a vraiment besoin.
    # 📘 NotionExporter(...) crée un objet (une "instance" de la classe) avec la clé et la base,
    # 📘 puis .export(prospects) envoie chaque prospect vers Notion.
    # 💡 À terme, appeler directement services.crm (get_exporter) partout et supprimer ce shim
    # 💡 réduirait le nombre de chemins de code à maintenir.
    from services.crm.notion import NotionExporter
    NotionExporter(config.notion_api_key, DATABASE_ID).export(prospects)
