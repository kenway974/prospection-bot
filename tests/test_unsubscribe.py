"""
tests/test_unsubscribe.py — Désinscription : une personne qui dit STOP n'est plus jamais contactée.

Comportement attendu :
  1. chaque mail (premier contact et relance) explique comment refuser et d'où vient l'adresse
  2. chaque mail envoyé porte l'en-tête List-Unsubscribe (bouton « se désabonner » de Gmail)
  3. python main.py --optout adresse@exemple.fr enregistre le refus
  4. une personne qui a refusé (par email OU par fiche Google) est exclue partout :
     parcours main, parcours interface, envoi Gmail, relances, SMS
  5. un fichier de refus illisible arrête l'envoi au lieu de l'ignorer en silence
"""

import glob
import json
import os

import pytest

import history_manager
import main
import optout_manager
from services import gmail, sms
from services.google_maps import Prospect
from services.mailer import draft_email, draft_followup_email
from tests.fakes import BAD_SITE
from tests.test_app_pipeline import run as run_app


def prospect(**kw) -> Prospect:
    base = dict(place_id="p1", name="Chez Test", address="1 rue Test", phone="06 12 34 56 78",
                website=None, rating=4.5, user_ratings_total=10, keyword="boulangerie")
    base.update(kw)
    return Prospect(**base)


def scenario(web):
    web.add_place("boulangerie", "p_nosite", "Chez Zoé", website=None, phone="06 11 22 33 44")
    web.add_place("boulangerie", "p_bad", "Vieux Garage",
                  website="http://vieux-garage.fr", html=BAD_SITE)


def names_in_output():
    files = sorted(glob.glob("output/prospects_*.json"))
    if not files:
        return []
    return [p["name"] for p in json.load(open(files[-1], encoding="utf-8"))]


# ------------------------------------------------------------------ 1. contenu des mails

class TestMailFooter:
    def test_le_premier_mail_explique_comment_refuser(self):
        mail = draft_email(prospect())
        assert "STOP" in mail
        assert "ne vous contacterai plus" in mail

    def test_le_premier_mail_dit_d_ou_vient_l_adresse(self):
        mail = draft_email(prospect())
        assert "publiquement" in mail

    def test_la_relance_contient_aussi_la_desinscription(self):
        mail = draft_followup_email(prospect())
        assert "STOP" in mail

    def test_la_mention_est_apres_la_signature(self):
        mail = draft_email(prospect())
        assert mail.index("kenny@example.com") < mail.index("STOP")

    def test_le_texte_de_desinscription_est_personnalisable(self, monkeypatch):
        monkeypatch.setenv("UNSUBSCRIBE_TEXT", "Pour ne plus me lire : répondez NON MERCI.")
        mail = draft_email(prospect())
        assert "répondez NON MERCI" in mail
        assert "STOP" not in mail


# ------------------------------------------------------------------ 2. en-tête technique

class TestListUnsubscribeHeader:
    def test_le_mail_envoye_a_l_entete_list_unsubscribe(self, smtp):
        gmail.send_email("a@b.fr", "OBJET : S\n\nCorps", "moi@gmail.com", "pwd", "Chez Test")

        header = smtp.sent[0]["headers"]["List-Unsubscribe"]
        assert header.startswith("<mailto:moi@gmail.com")
        assert "subject=STOP" in header


# ------------------------------------------------------------------ 3. enregistrement du refus

class TestOptOutStorage:
    def test_un_refus_est_conserve_entre_deux_lancements(self):
        optout_manager.add_optout(email="Refus@Exemple.FR")
        assert optout_manager.is_opted_out(prospect(email="refus@exemple.fr"))

    def test_la_casse_et_les_espaces_sont_ignores(self):
        optout_manager.add_optout(email="  Refus@Exemple.FR ")
        assert optout_manager.is_opted_out(prospect(email="REFUS@exemple.fr"))

    def test_un_refus_par_fiche_google_marche_sans_email(self):
        optout_manager.add_optout(place_id="p_abc")
        assert optout_manager.is_opted_out(prospect(place_id="p_abc", email=None))

    def test_une_personne_non_inscrite_n_est_pas_bloquee(self):
        optout_manager.add_optout(email="autre@exemple.fr")
        assert not optout_manager.is_opted_out(prospect(email="moi@exemple.fr"))

    def test_ajouter_deux_fois_ne_cree_pas_de_doublon(self):
        optout_manager.add_optout(email="a@b.fr")
        optout_manager.add_optout(email="a@b.fr")
        data = json.load(open(optout_manager.OPTOUT_FILE, encoding="utf-8"))
        assert data["emails"] == ["a@b.fr"]

    def test_un_fichier_illisible_leve_une_erreur_claire_et_n_est_pas_ecrase(self):
        os.makedirs("output", exist_ok=True)
        with open(optout_manager.OPTOUT_FILE, "w", encoding="utf-8") as f:
            f.write("{pas du json")
        with pytest.raises(optout_manager.OptOutFileError):
            optout_manager.is_opted_out(prospect())
        assert open(optout_manager.OPTOUT_FILE, encoding="utf-8").read() == "{pas du json"

    def test_une_adresse_vide_est_refusee(self):
        with pytest.raises(ValueError):
            optout_manager.add_optout()


class TestOptOutCommandLine:
    def test_main_optout_enregistre_l_adresse(self):
        main.main(["--optout", "refus@exemple.fr"])
        assert optout_manager.is_opted_out(prospect(email="refus@exemple.fr"))

    def test_main_optout_ne_lance_pas_de_prospection(self, web):
        scenario(web)
        main.main(["--optout", "refus@exemple.fr"])
        assert web.calls == []


# ------------------------------------------------------------------ 4. exclusion partout

class TestOptOutIsRespected:
    def test_le_parcours_main_exclut_un_refus_par_email_trouve_sur_le_site(self, web):
        scenario(web)
        optout_manager.add_optout(email="contact@vieux-garage.fr")

        main.run()

        assert names_in_output() == ["Chez Zoé"]

    def test_le_parcours_main_exclut_un_refus_par_fiche_google_avant_toute_analyse(self, web):
        scenario(web)
        optout_manager.add_optout(place_id="p_bad")

        main.run()

        assert names_in_output() == ["Chez Zoé"]
        assert ("GET", "http://vieux-garage.fr") not in web.calls   # son site n'est même pas visité

    def test_un_refus_n_est_pas_enregistre_comme_contact(self, web):
        scenario(web)
        optout_manager.add_optout(email="contact@vieux-garage.fr")

        main.run()

        assert "p_bad" not in history_manager.load_contacted_ids()

    def test_le_parcours_interface_exclut_aussi_les_refus(self, web, app_module):
        scenario(web)
        optout_manager.add_optout(email="contact@vieux-garage.fr")

        result, _ = run_app(app_module)

        assert [p.name for p in result] == ["Chez Zoé"]

    def test_l_envoi_gmail_ignore_un_refus_meme_si_le_prospect_est_dans_la_liste(self, smtp):
        refus = prospect(place_id="1", email="refus@x.fr")
        refus.email_draft = "OBJET : S\n\nC"
        ok = prospect(place_id="2", email="ok@x.fr")
        ok.email_draft = "OBJET : S\n\nC"
        optout_manager.add_optout(email="refus@x.fr")

        stats = gmail.send_all([refus, ok], "moi@gmail.com", "pwd")

        assert [m["to"] for m in smtp.sent] == ["ok@x.fr"]
        assert stats == {"sent": 1, "skipped": 1, "failed": 0}

    def test_la_relance_n_est_pas_generee_pour_un_refus(self, web):
        scenario(web)
        main.run()
        data = history_manager._load_contacted_data()
        for info in data.values():
            info["first_contact_date"] = "2000-01-01"
        history_manager._save_contacted_data(data)
        optout_manager.add_optout(email="contact@vieux-garage.fr")
        optout_manager.add_optout(place_id="p_nosite")

        main.run_followup()

        assert glob.glob("output/relances_*/*.txt") == []

    def test_le_sms_n_est_pas_envoye_a_un_refus(self, web, clean_config):
        clean_config.brevo_api_key = "k"
        optout_manager.add_optout(place_id="p1")

        stats = sms.send_all_sms([prospect(place_id="p1", phone="06 12 34 56 78")])

        assert web.sms_sent == []
        assert stats["skipped"] == 1


# ------------------------------------------------------------------ 5. on s'arrête si doute

def test_un_fichier_de_refus_illisible_arrete_la_prospection(web):
    scenario(web)
    os.makedirs("output", exist_ok=True)
    with open(optout_manager.OPTOUT_FILE, "w", encoding="utf-8") as f:
        f.write("{pas du json")

    with pytest.raises(SystemExit) as exc:
        main.run()

    assert exc.value.code == 1
    assert names_in_output() == []


# ------------------------------------------------------------------ interface : onglet Relances

def _due_contact(place_id="p_due", email="due@exemple.fr"):
    history_manager._save_contacted_data({
        place_id: {"name": "Chez Due", "email": email, "first_contact_date": "2000-01-01",
                   "responded": False, "followup_sent": False}
    })


class TestFollowupsExcludeOptOut:
    def test_la_liste_des_relances_exclut_un_refus_par_email(self):
        _due_contact()
        optout_manager.add_optout(email="DUE@exemple.fr")
        assert history_manager.get_due_followups(5) == []

    def test_la_liste_des_relances_exclut_un_refus_par_fiche_google(self):
        _due_contact()
        optout_manager.add_optout(place_id="p_due")
        assert history_manager.get_due_followups(5) == []

    def test_sans_refus_la_relance_est_proposee(self):
        _due_contact()
        assert [d["place_id"] for d in history_manager.get_due_followups(5)] == ["p_due"]

    def test_l_interface_ne_propose_pas_de_relancer_un_refus(self):
        from streamlit.testing.v1 import AppTest
        _due_contact()
        optout_manager.add_optout(email="due@exemple.fr")

        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", "app.py"),
                               default_timeout=30).run()

        assert not at.exception
        assert any("Aucun contact à relancer" in s.value for s in at.success)
