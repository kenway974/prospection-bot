"""
tests/test_unsubscribe.py — Désinscription : une personne qui dit STOP n'est plus jamais contactée.

Comportement attendu :
  1. chaque mail (premier contact, relances, mails de l'interface) explique comment refuser
     et d'où vient l'adresse ;
  2. chaque mail envoyé porte l'en-tête List-Unsubscribe (bouton « se désabonner » de Gmail) ;
  3. python main.py --optout adresse@exemple.fr enregistre le refus ;
  4. une personne qui a refusé (par email OU par fiche Google) est exclue partout :
     parcours main, parcours interface, envoi Gmail immédiat ET programmé, relances, SMS,
     et « Ma journée » (CRM) ;
  5. le fichier de refus est protégé comme celui des contacts : un refus n'est jamais perdu,
     et un fichier illisible sans copie fiable arrête l'envoi au lieu de l'ignorer.
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
from services.mailer import EmailStyle, draft_email, draft_followup_email
from tests.fakes import BAD_SITE
from tests.test_app_pipeline import run as run_ui


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


def corrupt(path, content="{pas du json"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------ 1. contenu des mails

class TestMailFooter:
    def test_le_premier_mail_explique_comment_refuser(self):
        mail = draft_email(prospect())
        assert "STOP" in mail
        assert "ne vous contacterai plus" in mail

    def test_le_premier_mail_dit_d_ou_vient_l_adresse(self):
        assert "publiquement" in draft_email(prospect())

    def test_le_mail_de_l_interface_contient_aussi_la_desinscription(self):
        mail = draft_email(prospect(), style=EmailStyle())
        assert "STOP" in mail and "publiquement" in mail

    @pytest.mark.parametrize("step", [1, 2, 3, 4])
    def test_chaque_relance_contient_la_desinscription(self, step):
        assert "STOP" in draft_followup_email(prospect(), step=step)

    def test_le_mail_de_candidature_freelance_contient_aussi_la_desinscription(self):
        mail = draft_email(prospect(), style=EmailStyle(), service_category="freelance")
        assert "STOP" in mail

    def test_la_mention_est_apres_la_signature(self):
        mail = draft_email(prospect())
        assert mail.index("Kenny") < mail.index("STOP")

    def test_la_mention_n_apparait_qu_une_fois(self):
        assert draft_email(prospect(), style=EmailStyle()).count("STOP") == 1

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

    def test_le_parcours_interface_exclut_les_refus_et_le_dit(self, web, ui_pipeline):
        scenario(web)
        optout_manager.add_optout(email="contact@vieux-garage.fr")
        excluded = []

        import queue
        q, result = queue.Queue(), []
        from tests.test_app_pipeline import base_params
        ui_pipeline.run_prospection(base_params(), q, result, excluded)

        assert [p.name for p in result] == ["Chez Zoé"]
        assert any(e["name"] == "Vieux Garage" and "STOP" in e["reason"] for e in excluded)

    def test_le_parcours_interface_ne_visite_pas_le_site_d_un_refus_par_fiche(self, web, ui_pipeline):
        scenario(web)
        optout_manager.add_optout(place_id="p_bad")

        result, _ = run_ui(ui_pipeline)

        assert [p.name for p in result] == ["Chez Zoé"]
        assert ("GET", "http://vieux-garage.fr") not in web.calls

    def test_l_envoi_gmail_ignore_un_refus_meme_si_le_prospect_est_dans_la_liste(self, smtp):
        refus = prospect(place_id="1", email="refus@x.fr")
        refus.email_draft = "OBJET : S\n\nC"
        ok = prospect(place_id="2", email="ok@x.fr")
        ok.email_draft = "OBJET : S\n\nC"
        optout_manager.add_optout(email="refus@x.fr")

        stats = gmail.send_all([refus, ok], "moi@gmail.com", "pwd")

        assert [m["to"] for m in smtp.sent] == ["ok@x.fr"]
        assert stats["sent"] == 1 and stats["skipped"] == 1

    def test_un_envoi_programme_n_est_pas_envoye_si_la_personne_a_refuse_entre_temps(self, smtp):
        from services import scheduler
        scheduler.remember_credentials("moi@gmail.com", "pwd")
        scheduler.add_pending(place_id="p1", name="Chez Test", email="refus@x.fr",
                              draft="OBJET : S\n\nC", gmail_address="moi@gmail.com",
                              gmail_password="pwd", send_at=0)
        optout_manager.add_optout(email="refus@x.fr")

        stats = scheduler.process_due()

        assert smtp.sent == []
        assert stats["skipped_optout"] == 1
        assert scheduler.get_stats()["pending"] == 0      # annulé, plus « en attente »
        scheduler.process_due()                           # et jamais retenté
        assert smtp.sent == []

    def test_la_relance_n_est_pas_generee_pour_un_refus(self, web):
        scenario(web)
        main.run()
        data = history_manager._load_contacted_data()
        for info in data.values():
            info["first_contact_date"] = info["last_contact_date"] = "2000-01-01"
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

    def test_un_refus_sort_le_prospect_du_crm_et_de_ma_journee(self):
        import crm_store
        crm_store.init_db()
        crm_store.upsert_prospects([prospect(place_id="p1", email="refus@x.fr")])
        crm_store.set_next_action("p1", crm_store.ACTION_RELANCER, due_date="2000-01-01")

        optout_manager.add_optout(email="REFUS@x.fr")

        assert crm_store.get_prospect("p1")["status"] == crm_store.STATUS_BLACKLIST
        assert all(a["place_id"] != "p1" for a in crm_store.due_actions())


# ------------------------------------------------------------------ 5. fichier de refus protégé

class TestFichierDeRefus:
    def test_une_coupure_pendant_l_ecriture_garde_les_refus_existants(self, monkeypatch):
        optout_manager.add_optout(email="refus@exemple.fr")

        with monkeypatch.context() as mp:
            def boom(obj, fp, *args, **kwargs):
                fp.write('{"coupure')
                raise OSError("coupure de courant simulée")
            mp.setattr(json, "dump", boom)
            with pytest.raises(OSError):
                optout_manager.add_optout(email="autre@exemple.fr")

        assert optout_manager.is_opted_out(prospect(email="refus@exemple.fr"))

    def test_apres_deux_refus_la_copie_contient_la_version_precedente(self):
        optout_manager.add_optout(email="a@exemple.fr")
        version_1 = read(optout_manager.OPTOUT_FILE)

        optout_manager.add_optout(email="b@exemple.fr")

        assert read(optout_manager.OPTOUT_FILE + ".bak") == version_1

    def test_un_fichier_de_refus_illisible_est_restaure_depuis_la_copie(self, web):
        optout_manager.add_optout(place_id="p_nosite")
        optout_manager.add_optout(email="b@exemple.fr")      # copie = refus de p_nosite
        corrupt(optout_manager.OPTOUT_FILE)
        scenario(web)

        main.run()                                            # ne s'arrête pas

        assert "Chez Zoé" not in names_in_output()            # le refus de la copie est respecté
        assert read(optout_manager.OPTOUT_FILE + ".corrupt") == "{pas du json"

    def test_un_fichier_illisible_sans_copie_leve_une_erreur_et_n_est_pas_ecrase(self):
        corrupt(optout_manager.OPTOUT_FILE)
        with pytest.raises(optout_manager.OptOutFileError):
            optout_manager.is_opted_out(prospect())
        assert read(optout_manager.OPTOUT_FILE) == "{pas du json"
        assert not os.path.exists(optout_manager.OPTOUT_FILE + ".corrupt")

    def test_le_message_ne_conseille_jamais_de_supprimer_le_fichier(self):
        corrupt(optout_manager.OPTOUT_FILE)
        with pytest.raises(optout_manager.OptOutFileError) as exc:
            optout_manager.is_opted_out(prospect())
        assert "sans le supprimer" in str(exc.value)

    def test_un_fichier_de_refus_illisible_arrete_main_avant_google(self, web):
        scenario(web)
        corrupt(optout_manager.OPTOUT_FILE)

        with pytest.raises(SystemExit) as exc:
            main.run()

        assert exc.value.code == 1
        assert web.calls == []
        assert names_in_output() == []

    def test_un_fichier_de_refus_illisible_arrete_l_interface(self, web, smtp, ui_pipeline):
        scenario(web)
        corrupt(optout_manager.OPTOUT_FILE)

        result, logs = run_ui(ui_pipeline, send_emails=True,
                              gmail_address="moi@gmail.com", gmail_password="pwd")

        assert result == [] and web.calls == [] and smtp.sent == []
        assert any("refus" in line.lower() and "illisible" in line for line in logs)


# ------------------------------------------------------------------ relances (liste de l'interface)

def _due_contact(place_id="p_due", email="due@exemple.fr"):
    history_manager._save_contacted_data({
        place_id: {"name": "Chez Due", "email": email, "first_contact_date": "2000-01-01",
                   "last_contact_date": "2000-01-01", "responded": False,
                   "followup_sent": False, "followup_step": 0}
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


class TestPageRelances:
    """La page « Relances » de l'interface ne propose jamais de relancer un refus."""

    def _open_page(self):
        import re
        from streamlit.testing.v1 import AppTest
        root = os.path.join(os.path.dirname(__file__), "..")
        src = open(os.path.join(root, "app.py"), encoding="utf-8").read()
        src = src.replace('url_path="ma-journee", default=True)', 'url_path="ma-journee")')
        src, n = re.subn(r"(st\.Page\(page_relances,[^)]*?)\)", r"\1, default=True)", src, count=1)
        assert n == 1, "page Relances introuvable dans la navigation"
        path = os.path.join(root, "_apptest_relances_optout.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        try:
            return AppTest.from_file(path, default_timeout=60).run()
        finally:
            os.remove(path)

    def test_un_refus_n_apparait_pas_dans_les_relances(self):
        _due_contact()
        optout_manager.add_optout(email="due@exemple.fr")

        at = self._open_page()

        assert not at.exception
        assert any("Aucun contact à relancer" in s.value for s in at.success)

    def test_sans_refus_le_contact_est_propose(self):
        _due_contact()

        at = self._open_page()

        assert not at.exception
        assert not any("Aucun contact à relancer" in s.value for s in at.success)


# ------------------------------------------------------------------ revue de code

class TestUneSeuleLectureDesRefus:
    """La liste des refus est lue UNE fois par opération : cohérente du début à la fin,
    et une panne du fichier en cours de route ne peut pas laisser un envoi à moitié fait."""

    def _count_loads(self, monkeypatch):
        calls = []
        real = optout_manager._load
        monkeypatch.setattr(optout_manager, "_load", lambda: calls.append(1) or real())
        return calls

    def test_l_envoi_gmail_lit_les_refus_une_seule_fois(self, smtp, monkeypatch):
        prospects = []
        for i in range(3):
            p = prospect(place_id=str(i), email=f"p{i}@x.fr")
            p.email_draft = "OBJET : S\n\nC"
            prospects.append(p)
        calls = self._count_loads(monkeypatch)

        gmail.send_all(prospects, "moi@gmail.com", "pwd")

        assert len(calls) == 1

    def test_l_envoi_sms_lit_les_refus_une_seule_fois(self, web, clean_config, monkeypatch):
        clean_config.brevo_api_key = "k"
        calls = self._count_loads(monkeypatch)

        sms.send_all_sms([prospect(place_id=str(i)) for i in range(3)])

        assert len(calls) == 1

    def test_le_parcours_interface_lit_les_refus_une_seule_fois(self, web, ui_pipeline, monkeypatch):
        scenario(web)
        calls = self._count_loads(monkeypatch)

        run_ui(ui_pipeline)

        assert len(calls) == 1

    def test_un_fichier_de_refus_abime_en_cours_d_envoi_programme_ne_fait_rien_renvoyer(self, smtp, monkeypatch):
        from services import scheduler
        scheduler.remember_credentials("moi@gmail.com", "pwd")
        for i in (1, 2):
            scheduler.add_pending(place_id=f"p{i}", name=f"P{i}", email=f"p{i}@x.fr",
                                  draft="OBJET : S\n\nC", gmail_address="moi@gmail.com",
                                  gmail_password="pwd", send_at=0)
        real_send = gmail.send_email

        def send_then_break_optout(*a, **k):
            ok = real_send(*a, **k)
            corrupt(optout_manager.OPTOUT_FILE)      # le fichier de refus s'abîme pendant l'envoi
            return ok
        monkeypatch.setattr(gmail, "send_email", send_then_break_optout)

        try:
            scheduler.process_due()
        except optout_manager.OptOutFileError:
            pass
        sent_first = [m["to"] for m in smtp.sent]
        scheduler.process_due()                       # tour suivant de la boucle d'envoi

        assert [m["to"] for m in smtp.sent] == sent_first          # rien n'est renvoyé
        assert sorted(sent_first) == ["p1@x.fr", "p2@x.fr"]      # l'envoi en cours est allé au bout


class TestOptOutCrmIndisponible:
    def test_un_crm_indisponible_n_empeche_pas_d_enregistrer_le_refus(self, monkeypatch):
        import sqlite3
        import crm_store

        def boom(*a, **k):
            raise sqlite3.OperationalError("database is locked")
        monkeypatch.setattr(crm_store, "place_ids_matching", boom)

        main.main(["--optout", "refus@exemple.fr"])          # pas de plantage

        assert optout_manager.is_opted_out(prospect(email="refus@exemple.fr"))


class TestRefusSimultanes:
    def test_deux_refus_enregistres_en_meme_temps_sont_tous_les_deux_gardes(self, monkeypatch):
        """Ex. : un STOP saisi dans l'interface pendant qu'un « --optout » tourne."""
        import threading
        barrier = threading.Barrier(2, timeout=0.5)
        real_load = optout_manager._load

        def load_then_wait():
            data = real_load()
            try:
                barrier.wait()          # sans protection : les deux lisent AVANT que l'un n'écrive
            except threading.BrokenBarrierError:
                pass
            return data
        monkeypatch.setattr(optout_manager, "_load", load_then_wait)

        threads = [threading.Thread(target=optout_manager.add_optout, kwargs={"email": e})
                   for e in ("a@exemple.fr", "b@exemple.fr")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        monkeypatch.setattr(optout_manager, "_load", real_load)
        assert optout_manager.is_opted_out(prospect(email="a@exemple.fr"))
        assert optout_manager.is_opted_out(prospect(email="b@exemple.fr"))
