"""
tests/conftest.py — Isolation commune à tous les tests (pytest).

- chaque test pytest tourne dans un dossier temporaire → output/, profiles_custom.json…
  ne polluent jamais le vrai projet (les classes unittest gèrent leur propre dossier)
- time.sleep est neutralisé (les délais anti-spam et les retries ne ralentissent pas)
- la config globale est remise à zéro pour que .env ne fuite pas dans les tests
"""

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from config import config, logger as _ORIGINAL_LOGGER  # noqa: E402
from tests.fakes import FakeSMTP, FakeWeb  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_workdir(request, tmp_path, monkeypatch):
    # Les classes unittest existantes gèrent elles-mêmes leur dossier (setUpClass) :
    # on ne change de dossier que pour les tests pytest.
    import unittest
    if not isinstance(request.instance, unittest.TestCase):
        monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
    for var in ("EMAIL_HOOK", "SMS_HOOK", "YOUR_OFFER"):
        monkeypatch.delenv(var, raising=False)
    yield


# Modules dont run_prospection() (pipeline.py) remplace config/logger sans les remettre.
_MODULES_WITH_CONFIG = (
    "config", "services.google_maps", "services.analyzer", "services.mailer",
    "services.notion_sync", "services.sms", "services.gmail",
)


@pytest.fixture(autouse=True)
def reset_module_configs(monkeypatch):
    """Chaque test repart de la config et du logger d'origine, même si un test précédent
    a lancé run_prospection() (qui les remplace dans plusieurs modules)."""
    import importlib
    import config as cfg
    for name in _MODULES_WITH_CONFIG:
        mod = importlib.import_module(name)
        if hasattr(mod, "config"):
            monkeypatch.setattr(mod, "config", config)
        if hasattr(mod, "logger"):
            monkeypatch.setattr(mod, "logger", _ORIGINAL_LOGGER)
    monkeypatch.setattr(cfg, "config", config)


@pytest.fixture(autouse=True)
def clean_config(monkeypatch, reset_module_configs):
    """Valeurs de config déterministes, indépendantes du .env de la machine."""
    values = dict(
        google_api_key="test-google-key",
        notion_api_key="",
        brevo_api_key="",
        search_keywords=["boulangerie"],
        search_locations=["Lyon, France"],
        search_radius=10000,
        max_results_per_keyword=5,
        your_name="Kenny",
        your_title="Développeur Web Freelance",
        your_email="kenny@example.com",
        your_website="https://kennydev.fr",
        min_rating=3.0,
        max_rating=5.0,
        min_reviews=0,
        max_reviews=None,
        website_filter="any",
        phone_filter="any",
        exclude_closed=True,
        require_email=False,
        contact_score_threshold=70,
        analysis_workers=1,
        followup_delay_days=5,
        output_dir="output",
    )
    for key, value in values.items():
        monkeypatch.setattr(config, key, value)
    return config


@pytest.fixture
def web(monkeypatch):
    """Faux Google Places + faux sites + faux Notion + faux Brevo."""
    return FakeWeb().install(monkeypatch)


@pytest.fixture
def smtp(monkeypatch):
    """Faux serveur SMTP Gmail. Les mails envoyés sont dans smtp.sent."""
    FakeSMTP.reset()
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    yield FakeSMTP
    FakeSMTP.reset()


@pytest.fixture
def ui_pipeline(monkeypatch):
    """
    Module pipeline (parcours de l'interface). run_prospection() remplace la config et le
    logger de plusieurs modules : on les restaure tous à la fin du test.
    """
    import config as cfg
    import pipeline
    import services.analyzer as an
    import services.crm.notion as crm_notion
    import services.google_maps as gm
    import services.mailer as ma
    import services.notion_sync as no

    for mod in (cfg, gm, an, ma, no):
        monkeypatch.setattr(mod, "config", getattr(mod, "config"))
        monkeypatch.setattr(mod, "logger", getattr(mod, "logger"))
    monkeypatch.setattr(crm_notion, "logger", crm_notion.logger)
    for var in ("GOOGLE_PLACES_API_KEY", "NOTION_API_KEY", "BREVO_API_KEY", "SEARCH_LOCATION",
                "SEARCH_KEYWORDS", "SEARCH_RADIUS", "MAX_RESULTS_PER_KEYWORD", "YOUR_NAME",
                "YOUR_TITLE", "YOUR_EMAIL", "YOUR_WEBSITE", "YOUR_OFFER", "EMAIL_HOOK", "SMS_HOOK"):
        monkeypatch.setenv(var, "")
    return pipeline
