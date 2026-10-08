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


class TestCopieDeSecours:
    def test_apres_deux_ecritures_le_bak_contient_la_version_precedente(self):
        history_manager.mark_as_contacted([FakeProspect("p1")])
        version_1 = read(history_manager.CONTACTED_FILE)

        history_manager.mark_as_contacted([FakeProspect("p2")])

        bak = history_manager.CONTACTED_FILE + ".bak"
        assert read(bak) == version_1
        assert history_manager.load_contacted_ids() == {"p1", "p2"}


class RecordingLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, msg, *args):
        self.warnings.append(msg % args if args else msg)

    def __getattr__(self, _name):           # info, debug, error… : ignorés
        return lambda *a, **k: None


def write_backup(path, data):
    import json
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".bak", "w", encoding="utf-8") as f:
        json.dump(data, f)


DEJA_CONTACTE = {"p_nosite": {"name": "Chez Zoé", "email": "", "first_contact_date": "2026-09-01",
                              "responded": False, "followup_sent": False}}


class TestRestaurationAutomatique:
    def test_le_bak_est_restaure_et_le_fichier_abime_mis_de_cote(self, monkeypatch):
        import config as cfg
        log = RecordingLogger()
        monkeypatch.setattr(cfg, "logger", log)
        write_backup(history_manager.CONTACTED_FILE, DEJA_CONTACTE)
        corrupt(history_manager.CONTACTED_FILE)

        assert history_manager.load_contacted_ids() == {"p_nosite"}

        assert read(history_manager.CONTACTED_FILE + ".corrupt") == "{pas du json"   # jamais supprimé
        assert read(history_manager.CONTACTED_FILE) == read(history_manager.CONTACTED_FILE + ".bak")
        assert any("restaur" in w and ".bak" in w for w in log.warnings), log.warnings

    def test_main_continue_sans_recontacter_les_contacts_du_bak(self, web):
        scenario(web)
        write_backup(history_manager.CONTACTED_FILE, DEJA_CONTACTE)
        corrupt(history_manager.CONTACTED_FILE)

        main.run()                                   # ne s'arrête pas

        assert web.calls                             # la prospection a bien eu lieu
        produced = sorted(glob.glob("output/prospects_*.json"))
        names = [p["name"] for p in __import__("json").load(open(produced[-1], encoding="utf-8"))]
        assert "Chez Zoé" not in names               # présent dans le .bak → pas recontacté
        assert "Vieux Garage" in names

    def test_l_interface_previent_et_continue(self, web, app_module):
        scenario(web)
        write_backup(history_manager.CONTACTED_FILE, DEJA_CONTACTE)
        corrupt(history_manager.CONTACTED_FILE)

        result, logs = run_app(app_module)

        assert [p.name for p in result] == ["Vieux Garage"]
        assert any("restaur" in line for line in logs), logs


class TestRienDeFiable:
    def _files(self):
        return {name: read(os.path.join("output", name)) for name in sorted(os.listdir("output"))}

    def test_principal_et_bak_illisibles_arret_sans_rien_toucher(self):
        corrupt(history_manager.CONTACTED_FILE)
        corrupt(history_manager.CONTACTED_FILE + ".bak")
        before = self._files()

        with pytest.raises(history_manager.HistoryFileError) as exc:
            history_manager.load_contacted_ids()

        assert self._files() == before                       # aucun fichier modifié, aucun .corrupt
        msg = str(exc.value)
        assert history_manager.CONTACTED_FILE in msg
        assert history_manager.CONTACTED_FILE + ".bak" in msg   # dit où est la copie de secours
        assert "aucune copie de secours lisible" in msg

    def test_sans_bak_le_message_le_dit_et_explique_quoi_faire(self):
        corrupt(history_manager.CONTACTED_FILE)

        with pytest.raises(history_manager.HistoryFileError) as exc:
            history_manager.load_contacted_ids()

        msg = str(exc.value)
        assert "aucune copie de secours lisible" in msg
        assert "MANUEL.md" in msg                             # renvoie vers la marche à suivre

    def test_main_s_arrete_avant_google_si_rien_de_fiable(self, web):
        scenario(web)
        corrupt(history_manager.CONTACTED_FILE)
        corrupt(history_manager.CONTACTED_FILE + ".bak")
        before = self._files()

        with pytest.raises(SystemExit) as exc:
            main.run()

        assert exc.value.code == 1
        assert web.calls == []
        assert self._files() == before
