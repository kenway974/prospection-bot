"""Interface commune pour tous les exporteurs CRM."""

# 📘 abc = "Abstract Base Classes" (module standard) : outils pour définir une INTERFACE,
# 📘 c'est-à-dire un contrat que toutes les classes filles doivent respecter.
from abc import ABC, abstractmethod
from typing import List

from services.google_maps import Prospect


# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : définit le contrat commun CRMExporter que tout exporteur CRM doit remplir
# 📘   (un nom crm_name + une méthode export). C'est l'interface du pattern Strategy.
# 📘 Appelé par : services/crm/notion.py et hubspot.py (qui en héritent), services/crm/__init__.py
# 📘   (annotation de type de get_exporter).
# 📘 Appelle : rien (importe seulement Prospect pour les annotations de type).
# 📘 Concepts Python à retenir ici : classe abstraite (ABC), @abstractmethod, @property, héritage.
# 📘
# 📘 Pattern Strategy : plusieurs classes interchangeables (NotionExporter, HubSpotExporter) qui
# 📘 exposent les MÊMES méthodes. Le code appelant (pipeline.py) choisit une "stratégie" et
# 📘 l'utilise sans savoir laquelle c'est. Ajouter un CRM = écrire une nouvelle classe fille.
# 📘 `class CRMExporter(ABC)` : hérite de ABC. On ne peut PAS créer directement un CRMExporter()
# 📘 tant qu'une méthode marquée @abstractmethod n'a pas été écrite par une classe fille
# 📘 (Python lève TypeError). Ça force chaque CRM à implémenter tout le contrat.
class CRMExporter(ABC):

    # 📘 @property : se lit comme un attribut (exporter.crm_name, sans parenthèses) mais est calculé
    # 📘 par une méthode. Combiné à @abstractmethod : chaque classe fille DOIT le définir.
    @property
    @abstractmethod
    def crm_name(self) -> str:
        """Nom du CRM affiché dans les logs."""
        # 📘 `...` (Ellipsis) : corps vide, "rien ici, c'est aux classes filles de le faire".
        ...

    # 💡 pipeline.py utilise aussi verify_access(), update_status() et _last_exported_ids, qui ne
    # 💡   sont PAS dans ce contrat (d'où ses hasattr). Les ajouter ici (avec une version par défaut)
    # 💡   et faire renvoyer à export() un petit objet résultat (créés + ids) rendrait l'API propre.
    @abstractmethod
    def export(self, prospects: List[Prospect]) -> int:
        """
        Exporte les prospects vers le CRM.
        Retourne le nombre de fiches créées.
        """
        ...
