"""
config.py — Configuration centralisée du projet.

Charge les variables d'environnement depuis .env (via python-dotenv).
Expose un objet `config` utilisé par tous les autres modules.
Expose aussi le logger global `logger`.
"""

# 📘 `import os` : module standard pour parler au système (variables d'environnement, dossiers).
# 📘 `logging` : module standard pour écrire des messages de log (DEBUG < INFO < WARNING < ERROR).
# 📘 `from X import a, b` : on importe seulement certains noms du module X.
# 📘 `dotenv` (paquet python-dotenv) : lit le fichier .env et copie ses lignes CLE=valeur dans
# 📘   os.environ (les variables d'environnement du processus).
import os
import logging
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : lire les réglages (clés API, zone, mots-clés, seuils…) depuis .env / l'environnement
# 📘   et les exposer dans UN objet `config`, plus un `logger` commun à tout le projet.
# 📘 Appelé par : quasiment tout le projet via `from config import config, logger` : main.py,
# 📘   pipeline.py, services/google_maps, analyzer, mailer, gmail, sms, notion_sync, dirigeants,
# 📘   services/crm/*, services/sources/*, tests/test_campaign.py.
# 📘 Appelle : python-dotenv (fichier .env), colorlog (optionnel, logs en couleur).
# 📘 Concepts Python à retenir ici : os.getenv, dotenv, logging, try/except ImportError,
# 📘   @dataclass + field(default_factory=lambda: ...), list comprehension, instance globale.
# 📘 load_dotenv() est exécuté UNE fois, au premier `import config` du processus. Il ne remplace
# 📘 pas une variable déjà définie dans l'environnement (ex. celles saisies sur Railway).
load_dotenv()


# ---------------------------------------------------------------------------
# Logger global — coloré si colorlog est installé, sinon standard
# ---------------------------------------------------------------------------

# 📘 `def nom(param: str = "prospection") -> logging.Logger:` : fonction avec un paramètre
# 📘 typé (type hint `: str`), une valeur par défaut, et un type de retour annoncé (`->`).
# 📘 Les type hints sont informatifs : Python ne les vérifie pas à l'exécution.
def setup_logger(name: str = "prospection") -> logging.Logger:
    # 📘 try/except ImportError : on TENTE d'importer colorlog ; s'il n'est pas installé, Python lève
    # 📘 une erreur ImportError qu'on "attrape" pour basculer sur le logger standard sans planter.
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

    # 📘 getLogger(name) renvoie TOUJOURS le même objet pour un même nom (c'est un registre global).
    # 📘 D'où le `if not logger.handlers` : sans lui, chaque appel ajouterait un handler de plus et
    # 📘 chaque message s'afficherait en double, triple…
    # 💡 Le niveau est figé à DEBUG. Le lire depuis une variable (ex. LOG_LEVEL=INFO) permettrait
    # 💡   d'avoir des logs moins bavards en production (Railway) sans toucher au code.
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        logger.addHandler(handler)
    return logger


# 📘 Variable créée au moment de l'import : tous les modules qui font `from config import logger`
# 📘 récupèrent CET objet (sauf si quelqu'un le remplace ensuite, comme pipeline.py).
logger = setup_logger()


# ---------------------------------------------------------------------------
# Objet de configuration principal
# Toutes les valeurs sont lues depuis les variables d'environnement.
# Les valeurs par défaut s'appliquent si la variable est absente du .env.
# ---------------------------------------------------------------------------

# 📘 @dataclass : décorateur (le `@` devant) qui "emballe" la classe et lui génère automatiquement
# 📘 un constructeur __init__ à partir des attributs annotés ci-dessous. Config() crée une instance.
@dataclass
class Config:

    # --- Clés API ---
    # 📘 field(default_factory=lambda: ...) : la valeur par défaut est CALCULÉE à chaque création
    # 📘 d'un Config(), pas une seule fois au chargement du fichier. `lambda: ...` = mini-fonction
    # 📘 anonyme sans nom. C'est ce qui permet à pipeline.py de refaire Config() après avoir modifié
    # 📘 os.environ et d'obtenir les nouvelles valeurs.
    # 📘 os.getenv("NOM", "") : lit une variable d'environnement, renvoie "" si elle n'existe pas.
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
    # 📘 List comprehension : `[expr for x in liste if condition]` construit une liste en une ligne.
    # 📘 Ici : "restaurant, boulangerie" → split(",") → strip() retire les espaces → on ignore les vides.
    search_keywords: List[str] = field(default_factory=lambda: [
        k.strip()
        for k in os.getenv("SEARCH_KEYWORDS", "restaurant,boulangerie").split(",")
        if k.strip()
    ])
    search_location: str = field(
        default_factory=lambda: os.getenv("SEARCH_LOCATION", "Lyon, France")
    )
    # 📘 int(...) convertit le texte lu dans l'environnement en nombre entier.
    # 💡 Si la variable contient une valeur non numérique (ex. SEARCH_RADIUS=10km), int() lève
    # 💡   ValueError et TOUT le projet plante à l'import. Une petite fonction _env_int(nom, défaut)
    # 💡   avec try/except + message clair serait plus robuste (ou pydantic-settings).
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

    # --- Paramètres techniques ---
    # 📘 Attributs sans field(...) : valeur fixe, identique pour toutes les instances. request_timeout
    # 📘 (10 s) n'est donc PAS réglable par variable d'environnement.
    request_timeout: int = 10
    output_dir: str = "output"
    analysis_workers: int = field(
        default_factory=lambda: int(os.getenv("ANALYSIS_WORKERS", "5"))
    )
    followup_delay_days: int = field(
        default_factory=lambda: int(os.getenv("FOLLOWUP_DELAY_DAYS", "5"))
    )

    # 📘 Méthode : fonction définie DANS la classe. `self` = l'instance sur laquelle on l'appelle
    # 📘 (config.validate() → self vaut config). `-> None` : elle ne renvoie rien.
    # 📘 Seul main.py l'appelle ; l'appli Streamlit (pipeline.py) ne passe pas par validate().
    def validate(self) -> None:
        """Vérifie que la config minimale est présente. Lève ValueError sinon."""
        if not self.google_api_key:
            # 📘 raise : déclenche volontairement une erreur ; l'appelant peut l'attraper (try/except).
            raise ValueError(
                "GOOGLE_PLACES_API_KEY manquante. "
                "Copiez .env.example en .env et renseignez votre clé API Google."
            )
        # 📘 exist_ok=True : ne plante pas si le dossier existe déjà.
        os.makedirs(self.output_dir, exist_ok=True)
        logger.debug("Configuration validée.")


# 📘 Instance créée UNE fois, au premier import du module. Tous les `from config import config`
# 📘 reçoivent une RÉFÉRENCE vers cet objet précis, recopiée dans leur propre module.
# 📘 ⚠️ Piège confirmé : pipeline.py fait `cfg_module.config = Config()` puis ne réinjecte la
# 📘   nouvelle config que dans google_maps, analyzer et notion_sync. Les autres modules
# 📘   (mailer, sms, gmail, services/sources/*…) gardent l'ANCIEN objet, lu au démarrage de
# 📘   l'appli. Ex. concret : services/sources/google_search.py lit config.google_api_key → c'est
# 📘   la clé de l'environnement au démarrage, pas celle saisie dans l'UI pour la campagne.
# 💡 Remède durable : ne plus lire de global. Construire Config à partir des paramètres de la
# 💡   campagne et le PASSER en argument (search_google_custom(..., cfg=cfg)) : plus de config
# 💡   périmée, et deux campagnes simultanées ne se marchent plus dessus via os.environ.
# Instance globale importée par tous les autres modules
config = Config()
