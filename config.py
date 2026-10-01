"""
config.py — Configuration centralisée du projet.

Charge les variables d'environnement depuis .env (via python-dotenv).
Expose un objet `config` utilisé par tous les autres modules.
Expose aussi le logger global `logger`.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import List, Optional
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

# ---------------------------------------------------------------------------
# Lecture des variables d'environnement
# ---------------------------------------------------------------------------

_TRUE_VALUES = ("1", "true", "yes", "oui")


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    return raw in _TRUE_VALUES if raw else default


def env_list(name: str, default: str = "", sep: str = ",") -> List[str]:
    return [item.strip() for item in os.getenv(name, default).split(sep) if item.strip()]


def env_optional_int(name: str) -> Optional[int]:
    """Entier, ou None si la variable est absente ou vide."""
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else None


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
    # Plusieurs villes séparées par des « ; » — la 1re sert de zone par défaut
    search_locations: List[str] = field(
        default_factory=lambda: env_list("SEARCH_LOCATION", "Lyon, France", sep=";")
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

    # --- Paramètres de filtrage ---
    min_rating: float = field(
        default_factory=lambda: float(os.getenv("MIN_RATING", "3.0"))
    )
    contact_score_threshold: int = field(
        default_factory=lambda: int(os.getenv("CONTACT_SCORE_THRESHOLD", "70"))
    )
    # Critères de sélection (voir filters.py)
    max_rating: float = field(default_factory=lambda: float(os.getenv("MAX_RATING", "5.0")))
    min_reviews: int = field(default_factory=lambda: int(os.getenv("MIN_REVIEWS", "0")))
    max_reviews: Optional[int] = field(default_factory=lambda: env_optional_int("MAX_REVIEWS"))  # vide = sans limite
    website_filter: str = field(default_factory=lambda: os.getenv("WEBSITE_FILTER", "any"))  # any / without / with
    phone_filter: str = field(default_factory=lambda: os.getenv("PHONE_FILTER", "any"))      # any / required / mobile
    exclude_closed: bool = field(default_factory=lambda: env_bool("EXCLUDE_CLOSED", True))
    require_email: bool = field(default_factory=lambda: env_bool("REQUIRE_EMAIL", False))

    # --- Paramètres techniques ---
    request_timeout: int = 10
    output_dir: str = "output"
    analysis_workers: int = field(
        default_factory=lambda: int(os.getenv("ANALYSIS_WORKERS", "5"))
    )
    followup_delay_days: int = field(
        default_factory=lambda: int(os.getenv("FOLLOWUP_DELAY_DAYS", "5"))
    )

    def __post_init__(self) -> None:
        if self.search_locations:
            self.search_location = self.search_locations[0]

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
