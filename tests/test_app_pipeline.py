"""
tests/test_app_pipeline.py — Comportement du parcours lancé depuis l'interface Streamlit.

Sur main, ce parcours est dans pipeline.py (run_prospection). On le teste avec les mêmes
faux services que main.py, sans ouvrir de navigateur.
"""

import glob
import json
import queue

import history_manager
from tests.fakes import BAD_SITE, GOOD_SITE, MID_SITE


def base_params(**over):
    params = dict(
        google_key="k", notion_key="", brevo_key="", location="Lyon, France",
        keywords=["boulangerie"], radius=10000, max_results=5,
        your_name="Autre Nom", your_title="Autre Titre", your_email="autre@example.com",
        your_website="https://autre.fr", your_offer="", email_hook="", sms_hook="",
        min_rating=3.0, contact_score_threshold=70, analysis_workers=1,
        weight_overrides={}, send_emails=False, gmail_address="", gmail_password="",
        send_sms=False, profile_name="Test", source_types=["google_maps"],
        find_dirigeants=False, crm_type="aucun",
    )
    params.update(over)
    return params


def run(ui_pipeline, **over):
    """Lance le parcours de l'interface → (prospects retenus, lignes de log)."""
    q, result = queue.Queue(), []
    ui_pipeline.run_prospection(base_params(**over), q, result)
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


def test_le_parcours_ui_filtre_trie_et_sauvegarde(web, ui_pipeline):
    scenario(web)

    result, logs = run(ui_pipeline)

    # Site parfait écarté (score > seuil) ; meilleure opportunité d'abord
    assert {p.name for p in result} == {"Chez Zoé", "Vieux Garage"}
    assert [p.opportunity for p in result] == sorted((p.opportunity for p in result), reverse=True)
    saved = json.load(open(sorted(glob.glob("output/prospects_*.json"))[-1], encoding="utf-8"))
    assert [p["name"] for p in saved] == [p.name for p in result]
    assert logs[-1] == "__DONE__"


def test_le_parcours_ui_enregistre_l_historique(web, ui_pipeline):
    scenario(web)

    run(ui_pipeline, profile_name="Mon profil")

    assert history_manager.load_history()[0]["profile"] == "Mon profil"


def test_un_run_sans_envoi_ne_marque_personne_comme_contacte(web, ui_pipeline):
    """Run d'exploration : les prospects restent disponibles au prochain lancement."""
    scenario(web)

    run(ui_pipeline)

    assert history_manager.load_contacted_ids() == set()


def test_le_parcours_ui_n_envoie_pas_de_mail_sans_la_case_cochee(web, smtp, ui_pipeline):
    scenario(web)

    run(ui_pipeline, send_emails=False, gmail_address="moi@gmail.com", gmail_password="pwd")

    assert smtp.sent == []


def test_le_parcours_ui_envoie_les_mails_et_marque_les_contacts(web, smtp, ui_pipeline):
    scenario(web)

    run(ui_pipeline, send_emails=True, gmail_address="moi@gmail.com", gmail_password="pwd")

    # Seul Vieux Garage a un email trouvé ; Chez Zoé n'a pas de site donc pas d'adresse
    assert [m["to"] for m in smtp.sent] == ["contact@vieux-garage.fr"]
    assert history_manager.load_contacted_ids() == {"p_nosite", "p_bad"}
def test_les_poids_du_profil_changent_le_score(web, ui_pipeline):
    web.add_place("boulangerie", "p_mid", "Cabinet Martin",
                  website="https://martin.fr", html=MID_SITE)

    default, _ = run(ui_pipeline, contact_score_threshold=100)
    boosted, _ = run(ui_pipeline, contact_score_threshold=100,
                     weight_overrides={"social_links": 30})

    assert boosted[0].score == default[0].score - 25  # 30 points au lieu de 5
