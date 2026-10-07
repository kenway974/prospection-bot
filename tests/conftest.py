"""
tests/conftest.py — Isolation commune à tous les tests (pytest).

- chaque test tourne dans un dossier temporaire → output/, profiles_custom.json…
  ne polluent jamais le vrai projet
- time.sleep est neutralisé (les délais anti-spam et les retries ne ralentissent pas)
- la config globale est remise à zéro pour que .env ne fuite pas dans les tests
"""

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from config import config  # noqa: E402
from tests.fakes import FakeSMTP, FakeWeb  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
    for var in ("EMAIL_HOOK", "SMS_HOOK", "YOUR_OFFER"):
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    """Valeurs de config déterministes, indépendantes du .env de la machine."""
    values = dict(
        google_api_key="test-google-key",
        notion_api_key="",
        brevo_api_key="",
        search_keywords=["boulangerie"],
        search_location="Lyon, France",
        search_radius=10000,
        max_results_per_keyword=5,
        your_name="Kenny",
        your_title="Développeur Web Freelance",
        your_email="kenny@example.com",
        your_website="https://kennydev.fr",
        min_rating=3.0,
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
def app_module(monkeypatch):
    """Importe app.py et restaure tout l'état global que run_prospection modifie."""
    import config as cfg
    import app
    import services.google_maps as gm
    import services.analyzer as an
    import services.mailer as ma
    import services.notion_sync as no
    import services.sms as sm
    import services.gmail as gm_mail

    for mod, names in [
        (cfg, ["config", "logger"]),
        (gm, ["config", "logger"]),
        (an, ["config", "logger"]),
        (ma, ["config", "logger"]),
        (no, ["config", "logger"]),
        (sm, ["config", "logger"]),
        (gm_mail, ["config", "logger"]),
    ]:
        for n in names:
            monkeypatch.setattr(mod, n, getattr(mod, n))
    for var in ("GOOGLE_PLACES_API_KEY", "NOTION_API_KEY", "BREVO_API_KEY", "SEARCH_LOCATION",
                "SEARCH_KEYWORDS", "SEARCH_RADIUS", "MAX_RESULTS_PER_KEYWORD", "YOUR_NAME",
                "YOUR_TITLE", "YOUR_EMAIL", "YOUR_WEBSITE", "YOUR_OFFER", "EMAIL_HOOK", "SMS_HOOK"):
        monkeypatch.setenv(var, "")
    return app
