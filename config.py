"""
config.py — Configuration centralisée du projet.

Charge les variables d'environnement depuis .env (via python-dotenv).
Expose un objet `config` utilisé par tous les autres modules.
Expose aussi le logger global `logger`.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Logger global — coloré si colorlog est installé, sinon standard
# ---------------------------------------------------------------------------

def setup_logger(name: str = "prospection") -> logging.Logger:
    try:
        import colorlog
        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)s]%(reset)s %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        ))
    except ImportError:
        # Fallback sans couleurs si colorlog n'est pas installé
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
        ))

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        logger.addHandler(handler)
    return logger


logger = setup_logger()


# ---------------------------------------------------------------------------
# Objet de configuration principal
# Toutes les valeurs sont lues depuis les variables d'environnement.
# Les valeurs par défaut s'appliquent si la variable est absente du .env.
# ---------------------------------------------------------------------------

@dataclass
class Config:

    # --- Clés API ---
    google_api_key: str = field(
        default_factory=lambda: os.getenv("GOOGLE_PLACES_API_KEY", "")
    )
    notion_api_key: str = field(
        default_factory=lambda: os.getenv("NOTION_API_KEY", "")
    )
    brevo_api_key: str = field(
        default_factory=lambda: os.getenv("BREVO_API_KEY", "")
    )

    # --- Critères de recherche (modifiables aussi depuis l'UI) ---
    search_keywords: List[str] = field(default_factory=lambda: [
        k.strip()
        for k in os.getenv("SEARCH_KEYWORDS", "restaurant,boulangerie").split(",")
        if k.strip()
    ])
    search_location: str = field(
        default_factory=lambda: os.getenv("SEARCH_LOCATION", "Lyon, France")
    )
    search_radius: int = field(
        default_factory=lambda: int(os.getenv("SEARCH_RADIUS", "10000"))
    )
    max_results_per_keyword: int = field(
        default_factory=lambda: int(os.getenv("MAX_RESULTS_PER_KEYWORD", "5"))
    )

    # --- Identité du prospecteur (utilisée dans la signature des mails/SMS) ---
    your_name: str = field(default_factory=lambda: os.getenv("YOUR_NAME", ""))
    your_title: str = field(default_factory=lambda: os.getenv("YOUR_TITLE", ""))
    your_email: str = field(default_factory=lambda: os.getenv("YOUR_EMAIL", ""))
    your_website: str = field(default_factory=lambda: os.getenv("YOUR_WEBSITE", ""))

    # --- Paramètres techniques ---
    request_timeout: int = 10   # timeout HTTP en secondes pour toutes les requêtes
    output_dir: str = "output"  # dossier où sont sauvegardés les résultats

    def validate(self) -> None:
        """Vérifie que la config minimale est présente. Lève ValueError sinon."""
        if not self.google_api_key:
            raise ValueError(
                "GOOGLE_PLACES_API_KEY manquante. "
                "Copiez .env.example en .env et renseignez votre clé API Google."
            )
        os.makedirs(self.output_dir, exist_ok=True)
        logger.debug("Configuration validée.")


# Instance globale importée par tous les autres modules
config = Config()
