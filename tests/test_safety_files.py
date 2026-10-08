"""
tests/test_safety_files.py — Un fichier d'historique abîmé ne doit jamais faire recontacter tout le monde.

Avant : si output/contacted_place_ids.json était corrompu, le bot repartait d'une liste
vide sans rien dire et re-démarchait tous les prospects déjà contactés.
Maintenant : il s'arrête, explique, et laisse le fichier intact pour qu'on puisse le réparer.
"""

import glob
import os

import pytest

import history_manager
import main
from tests.fakes import BAD_SITE
from tests.test_app_pipeline import run as run_app


def corrupt(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{pas du json")


def scenario(web):
    web.add_place("boulangerie", "p_nosite", "Chez Zoé", website=None)
    web.add_place("boulangerie", "p_bad", "Vieux Garage",
                  website="http://vieux-garage.fr", html=BAD_SITE)


class TestContactedFile:
    def test_un_fichier_illisible_leve_une_erreur_claire(self):
        corrupt(history_manager.CONTACTED_FILE)
        with pytest.raises(history_manager.HistoryFileError):
            history_manager.load_contacted_ids()

    def test_le_fichier_illisible_n_est_pas_ecrase(self):
        corrupt(history_manager.CONTACTED_FILE)
        with pytest.raises(history_manager.HistoryFileError):
            history_manager.mark_as_responded("x")
        assert open(history_manager.CONTACTED_FILE, encoding="utf-8").read() == "{pas du json"

    def test_un_fichier_absent_n_est_pas_une_erreur(self):
        assert history_manager.load_contacted_ids() == set()

    def test_main_s_arrete_avant_tout_appel_google(self, web):
        scenario(web)
        corrupt(history_manager.CONTACTED_FILE)

        with pytest.raises(SystemExit) as exc:
            main.run()

        assert exc.value.code == 1
        assert web.calls == []                      # aucun crédit Google dépensé
        assert glob.glob("output/prospects_*.json") == []

    def test_l_interface_s_arrete_aussi_et_le_dit(self, web, smtp, app_module):
        scenario(web)
        corrupt(history_manager.CONTACTED_FILE)

        result, logs = run_app(app_module, send_emails=True,
                               gmail_address="moi@gmail.com", gmail_password="pwd")

        assert result == []
        assert web.calls == []
        assert smtp.sent == []
        assert any("illisible" in line for line in logs)


class TestRunHistoryFile:
    def test_un_historique_illisible_est_mis_de_cote_pas_perdu(self):
        corrupt(history_manager.HISTORY_FILE)

        history_manager.save_run("p", "Lyon", ["k"], 1, 0, 0, 0, "f.json")

        assert open(history_manager.HISTORY_FILE + ".corrupt", encoding="utf-8").read() == "{pas du json"
        assert len(history_manager.load_history()) == 1


# ---------------------------------------------------------------------------
# Le bot se rattrape tout seul quand c'est possible
# ---------------------------------------------------------------------------

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class FakeProspect:
    def __init__(self, place_id, name="X", email=""):
        self.place_id, self.name, self.email = place_id, name, email


def crash_mid_dump(mp):
    """Simule une coupure en plein json.dump : une partie du JSON est écrite, puis plantage."""
    import json

    def boom(obj, fp, *args, **kwargs):
        fp.write('{"coupure')
        raise OSError("coupure de courant simulée")

    mp.setattr(json, "dump", boom)


class TestEcritureSure:
    def test_une_coupure_pendant_l_ecriture_laisse_le_fichier_intact(self, monkeypatch):
        history_manager.mark_as_contacted([FakeProspect("p_avant", "Avant")])
        before = read(history_manager.CONTACTED_FILE)

        with monkeypatch.context() as mp:
            crash_mid_dump(mp)
            with pytest.raises(OSError):
                history_manager.mark_as_contacted([FakeProspect("p_nouveau", "Nouveau")])

        assert read(history_manager.CONTACTED_FILE) == before
        assert history_manager.load_contacted_ids() == {"p_avant"}
        # Aucun fichier temporaire oublié dans output/
        assert sorted(os.listdir("output")) == ["contacted_place_ids.json"]
