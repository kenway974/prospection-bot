"""
tests/test_pipeline_main.py — Comportement du parcours complet (python main.py).

On ne teste pas des fonctions isolées : on lance run() de bout en bout avec de faux
Google / sites / Notion / Brevo, et on vérifie ce que l'utilisateur voit au final
(fichiers produits, fiches Notion, SMS, historique).
"""

import csv
import glob
import json
import os

import pytest

import history_manager
import main
from tests.fakes import BAD_SITE, GOOD_SITE, MID_SITE


def read_json_outputs():
    files = sorted(glob.glob("output/prospects_*.json"))
    assert files, "aucun fichier JSON produit"
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def scenario(web):
    """Trois prospects : sans site, site mauvais, site parfait."""
    web.add_place("boulangerie", "p_nosite", "Chez Zoé", website=None, phone="06 11 22 33 44")
    web.add_place("boulangerie", "p_bad", "Vieux Garage",
                  website="http://vieux-garage.fr", html=BAD_SITE)
    web.add_place("boulangerie", "p_good", "Boulangerie Dupont",
                  website="https://dupont.fr", html=GOOD_SITE)


def test_le_parcours_complet_produit_json_csv_et_brouillons(web):
    scenario(web)

    main.run()

    prospects = read_json_outputs()
    names = [p["name"] for p in prospects]
    # Le site parfait (score 100 > seuil 70) est écarté : inutile de le démarcher
    assert "Boulangerie Dupont" not in names
    assert set(names) == {"Chez Zoé", "Vieux Garage"}
    assert glob.glob("output/prospects_*.csv")
    drafts = glob.glob("output/prospects_*_emails/*.txt")
    assert len(drafts) == 2


def test_les_meilleures_opportunites_sont_en_premier(web):
    scenario(web)

    main.run()

    scores = [p["score"] for p in read_json_outputs()]
    assert scores == sorted(scores)
    assert read_json_outputs()[0]["name"] == "Chez Zoé"  # sans site = score 0


def test_un_prospect_sans_site_recoit_une_offre_de_creation(web):
    scenario(web)

    main.run()

    zoe = next(p for p in read_json_outputs() if p["name"] == "Chez Zoé")
    assert zoe["score"] == 0
    assert "pas trouvé de site web" in zoe["email_draft"]


def test_l_email_est_scrape_sur_le_site_du_prospect(web):
    scenario(web)

    main.run()

    garage = next(p for p in read_json_outputs() if p["name"] == "Vieux Garage")
    assert garage["email"] == "contact@vieux-garage.fr"


def test_les_mauvaises_notes_google_sont_exclues(web, clean_config):
    web.add_place("boulangerie", "p_low", "Mal Noté", website=None, rating=2.1)
    web.add_place("boulangerie", "p_ok", "Bien Noté", website=None, rating=4.4)

    main.run()

    assert [p["name"] for p in read_json_outputs()] == ["Bien Noté"]


def test_un_prospect_sans_note_n_est_pas_exclu(web):
    web.add_place("boulangerie", "p_none", "Sans Note", website=None, rating=None)

    main.run()

    assert [p["name"] for p in read_json_outputs()] == ["Sans Note"]


def test_un_doublon_entre_deux_mots_cles_n_est_traite_qu_une_fois(web, clean_config):
    clean_config.search_keywords = ["boulangerie", "pâtisserie"]
    web.add_place("boulangerie", "p_same", "Maison Blanc", website=None)
    web.add_place("pâtisserie", "p_same", "Maison Blanc", website=None)

    main.run()

    assert [p["name"] for p in read_json_outputs()] == ["Maison Blanc"]


def test_un_prospect_deja_contacte_n_est_pas_recontacte(web):
    scenario(web)
    main.run()
    first = len(read_json_outputs())
    assert first == 2

    # Deuxième lancement : tous les prospects ont déjà été vus → plus rien à traiter
    with pytest.raises(SystemExit) as exc:
        main.run()
    assert exc.value.code == 0
    assert len(read_json_outputs()) == first  # pas de nouveau fichier


def test_les_prospects_traites_sont_marques_pour_les_relances(web):
    scenario(web)

    main.run()

    contacted = history_manager.load_contacted_ids()
    assert contacted == {"p_nosite", "p_bad"}


def test_sans_cle_google_le_programme_s_arrete_proprement(web, clean_config):
    clean_config.google_api_key = ""

    with pytest.raises(SystemExit) as exc:
        main.run()

    assert exc.value.code == 1
    assert not glob.glob("output/prospects_*.json")


def test_aucun_resultat_google_ne_plante_pas(web):
    with pytest.raises(SystemExit) as exc:
        main.run()
    assert exc.value.code == 0


def test_un_site_inaccessible_donne_un_prospect_a_fort_potentiel(web):
    # Place avec un site déclaré mais jamais servi par le faux web → ConnectionError
    web.add_place("boulangerie", "p_down", "Site Mort", website="https://mort.fr")

    main.run()

    mort = read_json_outputs()[0]
    assert mort["score"] == 5
    assert "inaccessible" in mort["issues"][0]
    assert "inaccessible" in mort["email_draft"]


def test_le_seuil_de_score_est_reglable(web, clean_config):
    web.add_place("boulangerie", "p_mid", "Cabinet Martin",
                  website="https://martin.fr", html=MID_SITE)
    clean_config.contact_score_threshold = 100

    main.run()

    assert [p["name"] for p in read_json_outputs()] == ["Cabinet Martin"]


def test_sync_notion_cree_une_fiche_par_prospect_si_la_cle_est_presente(web, clean_config):
    scenario(web)
    clean_config.notion_api_key = "secret_x"

    main.run()

    created = [c["properties"]["Entreprise"]["title"][0]["text"]["content"]
               for c in web.notion_created]
    assert sorted(created) == ["Chez Zoé", "Vieux Garage"]


def test_pas_de_cle_notion_pas_d_appel_notion(web):
    scenario(web)

    main.run()

    assert web.notion_created == []
    assert not any("notion" in url for _, url in web.calls)


def test_notion_ne_recree_pas_une_fiche_deja_existante(web, clean_config):
    scenario(web)
    clean_config.notion_api_key = "secret_x"
    web.notion_existing_names = {"Vieux Garage"}

    main.run()

    created = [c["properties"]["Entreprise"]["title"][0]["text"]["content"]
               for c in web.notion_created]
    assert created == ["Chez Zoé"]


def test_sms_uniquement_aux_mobiles_et_si_la_cle_brevo_est_presente(web, clean_config):
    scenario(web)  # Chez Zoé: mobile 06 ; Vieux Garage: fixe 04
    clean_config.brevo_api_key = "brevo-key"

    main.run()

    assert len(web.sms_sent) == 1
    assert web.sms_sent[0]["recipient"] == "+33611223344"


def test_pas_de_cle_brevo_pas_de_sms(web):
    scenario(web)

    main.run()

    assert web.sms_sent == []


def test_le_csv_est_lisible_par_excel_et_complet(web):
    scenario(web)

    main.run()

    path = glob.glob("output/prospects_*.csv")[0]
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert {r["name"] for r in rows} == {"Chez Zoé", "Vieux Garage"}
    assert all(r["score"] != "" for r in rows)


def test_le_mode_relance_ne_genere_que_pour_les_contacts_dus(web, clean_config):
    scenario(web)
    main.run()
    # On vieillit artificiellement le premier contact de Vieux Garage
    data = history_manager._load_contacted_data()
    data["p_bad"]["first_contact_date"] = "2000-01-01"
    history_manager._save_contacted_data(data)

    main.run_followup()

    relances = glob.glob("output/relances_*/*.txt")
    assert [os.path.basename(r) for r in relances] == ["Vieux Garage.txt"]
    # et la relance n'est générée qu'une seule fois
    main.run_followup()
    assert len(glob.glob("output/relances_*/*.txt")) == 1
