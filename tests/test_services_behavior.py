"""
tests/test_services_behavior.py — Comportement de chaque service externe.

Google Places, Gmail (SMTP), Notion, Brevo et le scraping d'emails,
avec de faux serveurs. Vérifie ce qui sort, pas comment c'est codé.
"""

import pytest
import requests

import history_manager
from services import gmail, google_maps, notion_sync, sms
from services.analyzer import analyze_prospect
from services.google_maps import Prospect
from services.mailer import enrich_with_email
from tests.fakes import make_response


def prospect(**kw) -> Prospect:
    base = dict(place_id="p1", name="Chez Test", address="1 rue Test", phone="06 12 34 56 78",
                website=None, rating=4.5, user_ratings_total=10, keyword="boulangerie")
    base.update(kw)
    return Prospect(**base)


# ----------------------------------------------------------------- Google Places

class TestGooglePlaces:
    def test_retourne_un_prospect_par_lieu_avec_ses_details(self, web):
        web.add_place("boulangerie", "p1", "Chez Zoé", website="https://zoe.fr", html="<html></html>")
        result = google_maps.search_prospects("boulangerie")
        assert [p.name for p in result] == ["Chez Zoé"]
        assert result[0].website == "https://zoe.fr"
        assert result[0].keyword == "boulangerie"

    def test_respecte_le_maximum_par_mot_cle(self, web, clean_config):
        clean_config.max_results_per_keyword = 2
        for i in range(5):
            web.add_place("boulangerie", f"p{i}", f"Lieu {i}")
        assert len(google_maps.search_prospects("boulangerie")) == 2

    def test_aucun_resultat_donne_une_liste_vide(self, web):
        assert google_maps.search_prospects("licorne") == []

    def test_une_erreur_reseau_ne_plante_pas(self, monkeypatch):
        def boom(*a, **k):
            raise requests.ConnectionError("down")
        monkeypatch.setattr(requests, "get", boom)
        assert google_maps.search_prospects("boulangerie") == []

    def test_un_statut_d_erreur_google_est_ignore(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **k: make_response(
            200, {"status": "REQUEST_DENIED", "results": []}))
        assert google_maps.search_prospects("boulangerie") == []

    def test_un_lieu_dont_les_details_echouent_est_saute(self, web):
        web.add_place("boulangerie", "p1", "OK")
        web.places["boulangerie"].append({"place_id": "p_bad", "name": "KO"})  # pas de détails
        result = google_maps.search_prospects("boulangerie")
        assert [p.name for p in result] == ["OK"]

    def test_suit_la_pagination_de_google(self, monkeypatch, clean_config):
        clean_config.max_results_per_keyword = 3
        pages = [
            {"status": "OK", "results": [{"place_id": "a"}, {"place_id": "b"}], "next_page_token": "T"},
            {"status": "OK", "results": [{"place_id": "c"}, {"place_id": "d"}]},
        ]
        calls = []

        def fake_get(url, params=None, **k):
            calls.append(params)
            if "details" in url:
                return make_response(200, {"result": {"name": params["place_id"]}})
            return make_response(200, pages.pop(0))
        monkeypatch.setattr(requests, "get", fake_get)

        result = google_maps.search_prospects("x")

        assert [p.place_id for p in result] == ["a", "b", "c"]
        assert any(c and c.get("pagetoken") == "T" for c in calls)


# ----------------------------------------------------------------------- Gmail

class TestGmail:
    def test_extrait_sujet_et_corps_du_brouillon(self):
        subject, body = gmail._parse_subject("OBJET : Bonjour\n\nLigne 1\nLigne 2")
        assert subject == "Bonjour"
        assert body == "Ligne 1\nLigne 2"

    def test_envoie_le_mail_avec_le_bon_sujet_et_destinataire(self, smtp):
        ok = gmail.send_email("a@b.fr", "OBJET : Sujet\n\nCorps", "moi@gmail.com", "pwd", "Chez Test")
        assert ok is True
        assert smtp.sent[0]["to"] == "a@b.fr"
        assert smtp.sent[0]["from"] == "moi@gmail.com"
        assert smtp.sent[0]["subject"] == "Sujet"
        assert "Corps" in smtp.sent[0]["body"]

    def test_mauvais_mot_de_passe_renvoie_false_sans_planter(self, smtp):
        smtp.fail_auth = True
        assert gmail.send_email("a@b.fr", "OBJET : S\n\nC", "moi@gmail.com", "bad") is False

    def test_envoi_en_serie_compte_envoyes_ignores_et_echecs(self, smtp):
        ok = prospect(place_id="1", email="ok@x.fr")
        ok.email_draft = "OBJET : S\n\nC"
        sans_mail = prospect(place_id="2", email=None)
        sans_mail.email_draft = "OBJET : S\n\nC"
        sans_brouillon = prospect(place_id="3", email="z@x.fr")
        en_panne = prospect(place_id="4", email="panne@x.fr")
        en_panne.email_draft = "OBJET : S\n\nC"
        smtp.fail_send_to = {"panne@x.fr"}

        stats = gmail.send_all([ok, sans_mail, sans_brouillon, en_panne], "moi@gmail.com", "pwd")

        assert stats == {"sent": 1, "skipped": 2, "failed": 1}
        assert [m["to"] for m in smtp.sent] == ["ok@x.fr"]

    def test_sans_identifiants_rien_n_est_envoye(self, smtp):
        p = prospect(email="a@b.fr")
        p.email_draft = "OBJET : S\n\nC"
        assert gmail.send_all([p], "", "")["skipped"] == 1
        assert smtp.sent == []


# ---------------------------------------------------------------------- Notion

class TestNotion:
    def test_la_fiche_contient_les_champs_du_crm(self, web, clean_config):
        clean_config.notion_api_key = "secret"
        p = prospect(email="a@b.fr", website="https://x.fr", issues=["Problème 1"], score=40)
        p.email_draft = "OBJET : S\n\nCorps"

        assert notion_sync.push_prospect(p) is True

        props = web.notion_created[0]["properties"]
        assert props["Entreprise"]["title"][0]["text"]["content"] == "Chez Test"
        assert props["Status"]["rich_text"][0]["text"]["content"] == "à contacter"
        assert props["Email"] == {"email": "a@b.fr"}
        assert "Score : 40/100" in props["Récap propal"]["rich_text"][0]["text"]["content"]
        assert "Corps" in props["mail1"]["rich_text"][0]["text"]["content"]

    def test_un_doublon_n_est_pas_recree(self, web, clean_config):
        clean_config.notion_api_key = "secret"
        web.notion_existing_names = {"Chez Test"}
        assert notion_sync.push_prospect(prospect()) is False
        assert web.notion_created == []

    def test_une_erreur_notion_renvoie_false(self, web, clean_config):
        clean_config.notion_api_key = "secret"
        web.notion_fail_create = True
        assert notion_sync.push_prospect(prospect()) is False

    def test_les_textes_trop_longs_sont_tronques_pour_notion(self, web, clean_config):
        clean_config.notion_api_key = "secret"
        p = prospect()
        p.email_draft = "x" * 5000
        notion_sync.push_prospect(p)
        text = web.notion_created[0]["properties"]["mail1"]["rich_text"][0]["text"]["content"]
        assert len(text) == 2000


# ------------------------------------------------------------------------- SMS

class TestSms:
    @pytest.mark.parametrize("raw,expected", [
        ("06 12 34 56 78", "+33612345678"),
        ("07.12.34.56.78", "+33712345678"),
        ("04 78 12 34 56", None),     # fixe → pas de SMS
        ("+33 6 12 34 56 78", "+33612345678"),
    ])
    def test_formatage_des_numeros(self, raw, expected):
        assert sms._format_phone(raw) == expected

    def test_le_sms_ne_depasse_jamais_160_caracteres(self):
        p = prospect(name="N" * 300, issues=["x" * 300])
        assert len(sms._build_sms(p)) <= 160

    def test_envoi_unique_aux_mobiles(self, web, clean_config):
        clean_config.brevo_api_key = "k"
        mobile = prospect(place_id="1", phone="06 12 34 56 78")
        fixe = prospect(place_id="2", phone="04 78 12 34 56")
        stats = sms.send_all_sms([mobile, fixe])
        assert stats["sent"] == 1
        assert len(web.sms_sent) == 1

    def test_erreur_brevo_compte_comme_echec(self, web, clean_config):
        clean_config.brevo_api_key = "k"
        web.brevo_status = 500
        stats = sms.send_all_sms([prospect(phone="06 12 34 56 78")])
        assert stats["failed"] == 1 and stats["sent"] == 0

    def test_sans_cle_brevo_rien_n_est_envoye(self, web):
        stats = sms.send_all_sms([prospect(phone="06 12 34 56 78")])
        assert stats["skipped"] == 1
        assert web.sms_sent == []


# ----------------------------------------------------------- Scraping d'emails

class TestEmailScraping:
    def test_prefere_le_lien_mailto(self, web):
        html = '<html><body>info@a.fr <a href="mailto:direction@a.fr">x</a></body></html>'
        web.sites["https://a.fr"] = html
        p = analyze_prospect(prospect(website="https://a.fr"))
        assert p.email == "direction@a.fr"

    def test_ignore_les_faux_emails_techniques(self, web):
        web.sites["https://a.fr"] = "<html><body>bug@sentry.io logo@wix.com image@x.png</body></html>"
        p = analyze_prospect(prospect(website="https://a.fr"))
        assert p.email is None

    def test_cherche_aussi_sur_la_page_contact(self, web):
        web.sites["https://a.fr"] = "<html><body>rien</body></html>"
        web.sites["https://a.fr/contact"] = "<html><body>contact@a.fr</body></html>"
        p = analyze_prospect(prospect(website="https://a.fr"))
        assert p.email == "contact@a.fr"


# -------------------------------------------------------------------- Historique

class TestHistory:
    def test_marquer_deux_fois_garde_la_premiere_date(self):
        p = prospect(place_id="x")
        history_manager.mark_as_contacted([p])
        data = history_manager._load_contacted_data()
        data["x"]["first_contact_date"] = "2020-01-01"
        history_manager._save_contacted_data(data)
        history_manager.mark_as_contacted([p])
        assert history_manager._load_contacted_data()["x"]["first_contact_date"] == "2020-01-01"

    def test_relance_due_apres_le_delai_seulement(self):
        history_manager.mark_as_contacted([prospect(place_id="recent")])
        history_manager.mark_as_contacted([prospect(place_id="vieux")])
        data = history_manager._load_contacted_data()
        data["vieux"]["first_contact_date"] = "2020-01-01"
        history_manager._save_contacted_data(data)
        assert [d["place_id"] for d in history_manager.get_due_followups(5)] == ["vieux"]

    def test_un_contact_qui_a_repondu_n_est_plus_relance(self):
        history_manager.mark_as_contacted([prospect(place_id="vieux")])
        data = history_manager._load_contacted_data()
        data["vieux"]["first_contact_date"] = "2020-01-01"
        history_manager._save_contacted_data(data)
        history_manager.mark_as_responded("vieux")
        assert history_manager.get_due_followups(5) == []

    def test_une_relance_deja_envoyee_n_est_pas_redue(self):
        history_manager.mark_as_contacted([prospect(place_id="vieux")])
        data = history_manager._load_contacted_data()
        data["vieux"]["first_contact_date"] = "2020-01-01"
        history_manager._save_contacted_data(data)
        history_manager.mark_followup_sent("vieux")
        assert history_manager.get_due_followups(5) == []

    def test_migration_de_l_ancien_format_liste(self):
        import json, os
        os.makedirs("output", exist_ok=True)
        with open(history_manager.CONTACTED_FILE, "w", encoding="utf-8") as f:
            json.dump(["a", "b"], f)
        assert history_manager.load_contacted_ids() == {"a", "b"}

    def test_l_historique_garde_les_50_derniers_runs(self):
        for i in range(55):
            history_manager.save_run("p", "Lyon", ["k"], i, 0, 0, 0, "f.json")
        history = history_manager.load_history()
        assert len(history) == 50
        assert history[0]["total_prospects"] == 54  # le plus récent en premier


# ------------------------------------------------------------ Mails de bout en bout

class TestMailContent:
    def test_le_mail_contient_la_signature_configuree(self):
        p = prospect(website=None)
        enrich_with_email(p)
        assert "Kenny" in p.email_draft
        assert "kenny@example.com" in p.email_draft
        assert "https://kennydev.fr" in p.email_draft

    def test_l_accroche_personnalisee_du_profil_remplace_l_accroche_par_defaut(self, monkeypatch):
        monkeypatch.setenv("EMAIL_HOOK", "Salut {name}, test de profil.")
        p = prospect(website=None)
        enrich_with_email(p)
        assert "Salut Chez Test, test de profil." in p.email_draft
        assert "pas trouvé de site web" not in p.email_draft
