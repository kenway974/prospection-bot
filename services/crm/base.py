"""Interface commune pour tous les exporteurs CRM."""

from abc import ABC, abstractmethod
from typing import List

from services.google_maps import Prospect


class CRMExporter(ABC):

    @property
    @abstractmethod
    def crm_name(self) -> str:
        """Nom du CRM affiché dans les logs."""
        ...

    @abstractmethod
    def export(self, prospects: List[Prospect]) -> int:
        """
        Exporte les prospects vers le CRM.
        Retourne le nombre de fiches créées.
        """
        ...
