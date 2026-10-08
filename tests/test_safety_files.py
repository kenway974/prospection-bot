"""
tests/test_safety_files.py — Un fichier abîmé ne doit jamais faire recontacter tout le monde.

Fichiers protégés : output/contacted_place_ids.json (qui a déjà été contacté) et
output/history.json (statistiques des campagnes).

Règles :
  1. écriture sûre : une coupure pendant l'écriture laisse l'ancien fichier intact ;
  2. copie de secours : la version précédente lisible est gardée avant chaque écriture ;
  3. restauration automatique : fichier illisible + copie lisible → la copie est remise
     en place, le fichier abîmé est gardé en .corrupt, un avertissement est affiché ;
  4. rien de fiable (fichier ET copie illisibles) → arrêt avant tout appel Google,
     aucun fichier modifié, message qui dit où sont les fichiers et quoi faire.
"""

import glob
import json
import os

import pytest

import history_manager
import main
from tests.fakes import BAD_SITE
from tests.test_app_pipeline import run as run_ui

CONTACTS = history_manager.CONTACTED_FILE
CONTACTS_BAK = history_manager.CONTACTED_BACKUP_FILE
HISTORY = history_manager.HISTORY_FILE


def corrupt(path, content="{pas du json"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def output_files():
    return {name: read(os.path.join("output", name)) for name in sorted(os.listdir("output"))}


def scenario(web):
    web.add_place("boulangerie", "p_nosite", "Chez Zoé", website=None)
    web.add_place("boulangerie", "p_bad", "Vieux Garage",
                  website="http://vieux-garage.fr", html=BAD_SITE)


def produced_names():
    files = sorted(glob.glob("output/prospects_*.json"))
    return [p["name"] for p in json.load(open(files[-1], encoding="utf-8"))] if files else []


class FakeProspect:
    def __init__(self, place_id, name="X", email=""):
        self.place_id, self.name, self.email = place_id, name, email


def crash_mid_dump(mp):
    """Simule une coupure en plein json.dump : une partie du JSON est écrite, puis plantage."""
    def boom(obj, fp, *args, **kwargs):
        fp.write('{"coupure')
        raise OSError("coupure de courant simulée")
    mp.setattr(json, "dump", boom)


class RecordingLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, msg, *args):
        self.warnings.append(msg % args if args else msg)

    def __getattr__(self, _name):
        return lambda *a, **k: None


DEJA_CONTACTE = {"p_nosite": {"name": "Chez Zoé", "email": "", "first_contact_date": "2026-09-01",
                              "last_contact_date": "2026-09-01", "responded": False,
                              "followup_sent": False, "followup_step": 0}}


# ---------------------------------------------------------------------------
# Fichier des contacts — rien de fiable : on s'arrête
# ---------------------------------------------------------------------------

class TestContactsIllisibles:
    def test_un_fichier_illisible_sans_copie_leve_une_erreur_claire(self):
        corrupt(CONTACTS)
        with pytest.raises(history_manager.HistoryFileError):
            history_manager.load_contacted_ids()

    def test_le_fichier_illisible_n_est_pas_ecrase(self):
        corrupt(CONTACTS)
        with pytest.raises(history_manager.HistoryFileError):
            history_manager.mark_as_contacted([FakeProspect("x")])
        assert read(CONTACTS) == "{pas du json"

    def test_un_fichier_absent_n_est_pas_une_erreur(self):
        assert history_manager.load_contacted_ids() == set()

    def test_main_s_arrete_avant_tout_appel_google(self, web):
        scenario(web)
        corrupt(CONTACTS)

        with pytest.raises(SystemExit) as exc:
            main.run()

        assert exc.value.code == 1
        assert web.calls == []                      # aucun crédit Google dépensé
        assert produced_names() == []

    def test_l_interface_s_arrete_aussi_et_le_dit(self, web, smtp, ui_pipeline):
        scenario(web)
        corrupt(CONTACTS)

        result, logs = run_ui(ui_pipeline, send_emails=True,
                              gmail_address="moi@gmail.com", gmail_password="pwd")

        assert result == []
        assert web.calls == []
        assert smtp.sent == []
        assert any("illisible" in line for line in logs)

    def test_fichier_et_copie_illisibles_arret_sans_rien_toucher(self):
        corrupt(CONTACTS)
        corrupt(CONTACTS_BAK)
        before = output_files()

        with pytest.raises(history_manager.HistoryFileError) as exc:
            history_manager.load_contacted_ids()

        assert output_files() == before              # aucun fichier modifié, aucun .corrupt
        msg = str(exc.value)
        assert CONTACTS in msg and CONTACTS_BAK in msg   # dit où sont les fichiers
        assert "aucune copie de secours lisible" in msg
        assert "MANUEL.md" in msg                         # renvoie vers la marche à suivre

    def test_main_s_arrete_avant_google_si_rien_de_fiable(self, web):
        scenario(web)
        corrupt(CONTACTS)
        corrupt(CONTACTS_BAK)
        before = output_files()

        with pytest.raises(SystemExit) as exc:
            main.run()

        assert exc.value.code == 1
        assert web.calls == []
        assert output_files() == before


# ---------------------------------------------------------------------------
# Fichier des contacts — écriture sûre et copie de secours
# ---------------------------------------------------------------------------

class TestContactsEcritureSure:
    def test_une_coupure_pendant_l_ecriture_laisse_le_fichier_intact(self, monkeypatch):
        history_manager.mark_as_contacted([FakeProspect("p_avant", "Avant")])
        before = read(CONTACTS)

        with monkeypatch.context() as mp:
            crash_mid_dump(mp)
            with pytest.raises(OSError):
                history_manager.mark_as_contacted([FakeProspect("p_nouveau", "Nouveau")])

        assert read(CONTACTS) == before
        assert history_manager.load_contacted_ids() == {"p_avant"}
        assert not [f for f in os.listdir("output") if f.endswith(".tmp")]   # pas de fichier temporaire oublié

    def test_apres_deux_ecritures_la_copie_contient_la_version_precedente(self):
        history_manager.mark_as_contacted([FakeProspect("p1")])
        version_1 = read(CONTACTS)

        history_manager.mark_as_contacted([FakeProspect("p2")])

        assert read(CONTACTS_BAK) == version_1
        assert history_manager.load_contacted_ids() == {"p1", "p2"}

    def test_une_bonne_copie_n_est_jamais_ecrasee_par_un_fichier_abime(self):
        write_json(CONTACTS_BAK, DEJA_CONTACTE)
        bonne_copie = read(CONTACTS_BAK)
        corrupt(CONTACTS)

        history_manager.mark_as_contacted([FakeProspect("p_nouveau")])   # restaure puis écrit

        assert json.loads(read(CONTACTS_BAK)) == json.loads(bonne_copie)
        assert history_manager.load_contacted_ids() == {"p_nosite", "p_nouveau"}


# ---------------------------------------------------------------------------
# Fichier des contacts — restauration automatique
# ---------------------------------------------------------------------------

class TestContactsRestauration:
    def test_la_copie_est_restauree_et_le_fichier_abime_mis_de_cote(self, monkeypatch):
        import config as cfg
        log = RecordingLogger()
        monkeypatch.setattr(cfg, "logger", log)
        write_json(CONTACTS_BAK, DEJA_CONTACTE)
        corrupt(CONTACTS)

        assert history_manager.load_contacted_ids() == {"p_nosite"}

        assert read(CONTACTS + ".corrupt") == "{pas du json"     # jamais supprimé
        assert read(CONTACTS) == read(CONTACTS_BAK)
        assert any("restaur" in w and CONTACTS_BAK in w for w in log.warnings), log.warnings

    def test_main_continue_sans_recontacter_les_contacts_de_la_copie(self, web):
        scenario(web)
        write_json(CONTACTS_BAK, DEJA_CONTACTE)
        corrupt(CONTACTS)

        main.run()                                   # ne s'arrête pas

        assert web.calls                             # la prospection a bien eu lieu
        assert "Chez Zoé" not in produced_names()    # présent dans la copie → pas recontacté
        assert "Vieux Garage" in produced_names()

    def test_l_interface_previent_et_continue(self, web, ui_pipeline):
        scenario(web)
        write_json(CONTACTS_BAK, DEJA_CONTACTE)
        corrupt(CONTACTS)

        result, logs = run_ui(ui_pipeline)

        assert [p.name for p in result] == ["Vieux Garage"]
        assert any("restaur" in line for line in logs), logs


# ---------------------------------------------------------------------------
# Historique des campagnes (history.json)
# ---------------------------------------------------------------------------

def run_stats(n):
    history_manager.save_run(f"profil {n}", "Lyon", ["k"], n, 0, 0, 0, f"f{n}.json")


class TestHistoriqueDesRuns:
    def test_un_historique_illisible_est_mis_de_cote_pas_perdu(self):
        corrupt(HISTORY)

        run_stats(1)

        assert read(HISTORY + ".corrupt") == "{pas du json"
        assert len(history_manager.load_history()) == 1

    def test_une_coupure_pendant_l_ecriture_laisse_l_historique_intact(self, monkeypatch):
        run_stats(1)
        before = read(HISTORY)

        with monkeypatch.context() as mp:
            crash_mid_dump(mp)
            with pytest.raises(OSError):
                run_stats(2)

        assert read(HISTORY) == before
        assert [r["profile"] for r in history_manager.load_history()] == ["profil 1"]

    def test_apres_deux_runs_la_copie_contient_la_version_precedente(self):
        run_stats(1)
        version_1 = read(HISTORY)

        run_stats(2)

        assert read(HISTORY + ".bak") == version_1

    def test_un_historique_illisible_est_restaure_depuis_la_copie(self):
        run_stats(1)
        run_stats(2)                                   # copie = [profil 1]
        corrupt(HISTORY)

        assert [r["profile"] for r in history_manager.load_history()] == ["profil 1"]
        assert read(HISTORY + ".corrupt") == "{pas du json"

    def test_un_ancien_corrupt_n_est_jamais_ecrase(self):
        corrupt(HISTORY)
        run_stats(1)                                   # 1re mise de côté → .corrupt
        assert not os.path.exists(HISTORY + ".bak")    # pas de copie fiable
        corrupt(HISTORY, "{deuxieme panne")

        run_stats(2)                                   # 2e mise de côté : ne doit pas écraser la 1re

        assert read(HISTORY + ".corrupt") == "{pas du json"
        assert read(HISTORY + ".corrupt.1") == "{deuxieme panne"
