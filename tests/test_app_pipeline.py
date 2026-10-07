"""
tests/test_app_pipeline.py — Comportement du parcours lancé depuis l'interface Streamlit.

app.py contient sa propre version du parcours (run_prospection). On la teste avec les
mêmes faux services que main.py, sans ouvrir de navigateur.
"""

import glob
import json
import queue

import pytest

import history_manager
from tests.fakes import BAD_SITE, GOOD_SITE, MID_SITE


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

    for mod, names in [
        (cfg, ["config", "logger"]),
        (gm, ["config", "logger"]),
        (an, ["config", "logger"]),
        (ma, ["config", "logger"]),
        (no, ["config", "logger"]),
        (sm, ["config", "logger"]),
    ]:
        for n in names:
            monkeypatch.setattr(mod, n, getattr(mod, n))
    for var in ("GOOGLE_PLACES_API_KEY", "NOTION_API_KEY", "BREVO_API_KEY", "SEARCH_LOCATION",
                "SEARCH_KEYWORDS", "SEARCH_RADIUS", "MAX_RESULTS_PER_KEYWORD", "YOUR_NAME",
                "YOUR_TITLE", "YOUR_EMAIL", "YOUR_WEBSITE", "YOUR_OFFER", "EMAIL_HOOK", "SMS_HOOK"):
        monkeypatch.setenv(var, "")
    return app


def base_params(**over):
    params = dict(
        google_key="k", notion_key="", brevo_key="", location="Lyon, France",
        keywords=["boulangerie"], radius=10000, max_results=5,
        your_name="Autre Nom", your_title="Autre Titre", your_email="autre@example.com",
        your_website="https://autre.fr", your_offer="", email_hook="", sms_hook="",
        min_rating=3.0, contact_score_threshold=70, analysis_workers=1,
        weight_overrides={}, send_emails=False, gmail_address="", gmail_password="",
        send_sms=False, profile_name="Test",
    )
    params.update(over)
    return params


def run(app_module, **over):
    q, result = queue.Queue(), []
    app_module.run_prospection(base_params(**over), q, result)
    logs = []
    while not q.empty():
        logs.append(q.get())
    return result, logs


def scenario(web):
    web.add_place("boulangerie", "p_nosite", "Chez Zoé", website=None, phone="06 11 22 33 44")
    web.add_place("boulangerie", "p_bad", "Vieux Garage",
                  website="http://vieux-garage.fr", html=BAD_SITE)
    web.add_place("boulangerie", "p_good", "Boulangerie Dupont",
                  website="https://dupont.fr", html=GOOD_SITE)


def test_le_parcours_ui_filtre_trie_et_sauvegarde(web, app_module):
    scenario(web)

    result, logs = run(app_module)

    assert [p.name for p in result] == ["Chez Zoé", "Vieux Garage"]  # site parfait écarté, tri par score
    saved = json.load(open(sorted(glob.glob("output/prospects_*.json"))[-1], encoding="utf-8"))
    assert [p["name"] for p in saved] == ["Chez Zoé", "Vieux Garage"]
    assert logs[-1] == "__DONE__"


def test_le_parcours_ui_enregistre_l_historique_et_les_contacts(web, app_module):
    scenario(web)

    run(app_module, profile_name="Mon profil")

    assert history_manager.load_contacted_ids() == {"p_nosite", "p_bad"}
    assert history_manager.load_history()[0]["profile"] == "Mon profil"


def test_le_parcours_ui_n_envoie_pas_de_mail_sans_la_case_cochee(web, smtp, app_module):
    scenario(web)

    run(app_module, send_emails=False, gmail_address="moi@gmail.com", gmail_password="pwd")

    assert smtp.sent == []


def test_le_parcours_ui_envoie_les_mails_aux_adresses_trouvees(web, smtp, app_module):
    scenario(web)

    run(app_module, send_emails=True, gmail_address="moi@gmail.com", gmail_password="pwd")

    # Seul Vieux Garage a un email scrapé ; Chez Zoé n'a pas de site donc pas d'adresse
    assert [m["to"] for m in smtp.sent] == ["contact@vieux-garage.fr"]


def test_les_poids_du_profil_changent_le_score(web, app_module):
    web.add_place("boulangerie", "p_mid", "Cabinet Martin",
                  website="https://martin.fr", html=MID_SITE)

    default, _ = run(app_module, contact_score_threshold=100)
    history_manager._save_contacted_data({})  # on relance le même prospect
    boosted, _ = run(app_module, contact_score_threshold=100,
                     weight_overrides={"social_links": 30})

    assert boosted[0].score == default[0].score - 25  # 30 points au lieu de 5
