"""
tests/test_crm_actions.py — Prochaines actions & écran « Ma journée ».

Verrouille les deux scénarios réels décrits par l'utilisateur :
  1. « Envoyez-moi une maquette » au téléphone → réapparaît DÈS LE LENDEMAIN.
  2. « Mon associé vous rappelle cet après-midi » → il ne rappelle pas,
     le prospect ressort le lendemain en « Rappeler ».
Plus la règle d'or : une réponse annule toujours la relance.
"""

import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crm_store as cs
from services.google_maps import Prospect


def mk(pid="p1", name="ESN Alpha"):
    p = Prospect(pid, name, "1 rue X", "0612345678", "https://x.fr", 4.5, 40, "ESN")
    p.email, p.score, p.issues, p.issue_keys = "c@x.fr", 80, [], []
    return p


class _DbTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = cs.DB_FILE
        cs.DB_FILE = os.path.join(self._tmp.name, "crm.db")
        cs.init_db()
        cs.upsert_prospects([mk()])

    def tearDown(self):
        cs.DB_FILE = self._orig
        self._tmp.cleanup()


class TestJoursOuvres(unittest.TestCase):

    def test_saute_le_weekend(self):
        vendredi = date(2026, 9, 25)          # un vendredi
        self.assertEqual(cs.add_business_days(vendredi, 1), "2026-09-28")  # lundi
        self.assertEqual(cs.add_business_days(vendredi, 2), "2026-09-29")  # mardi

    def test_quatre_jours_ouvres_depuis_mercredi(self):
        mercredi = date(2026, 9, 23)
        # jeu, ven, lun, mar → mardi suivant
        self.assertEqual(cs.add_business_days(mercredi, 4), "2026-09-29")

    def test_samedi_tombe_sur_lundi(self):
        samedi = date(2026, 9, 26)
        self.assertEqual(cs.add_business_days(samedi, 1), "2026-09-28")


class TestActions(_DbTestCase):

    def test_action_utilise_le_delai_par_defaut(self):
        due = cs.set_next_action("p1", cs.ACTION_RELANCER)
        self.assertEqual(due, cs.add_business_days(None, cs.DEFAULT_DELAYS[cs.ACTION_RELANCER]))
        p = cs.get_prospect("p1")
        self.assertEqual(p["next_action"], cs.ACTION_RELANCER)

    def test_maquette_des_le_lendemain(self):
        """Le besoin exprimé : voir tout de suite qu'il faut envoyer la maquette."""
        due = cs.set_next_action("p1", cs.ACTION_MAQUETTE)
        self.assertEqual(due, cs.add_business_days(None, 1))

    def test_delai_manuel_prioritaire(self):
        due = cs.set_next_action("p1", cs.ACTION_RAPPELER, delay_days=10)
        self.assertEqual(due, cs.add_business_days(None, 10))

    def test_date_manuelle_prioritaire_sur_tout(self):
        due = cs.set_next_action("p1", cs.ACTION_AUTRE, delay_days=5, due_date="2026-12-24")
        self.assertEqual(due, "2026-12-24")

    def test_delai_configurable(self):
        cs.set_delay(cs.ACTION_RELANCER, 3)
        self.assertEqual(cs.get_delay(cs.ACTION_RELANCER), 3)
        due = cs.set_next_action("p1", cs.ACTION_RELANCER)
        self.assertEqual(due, cs.add_business_days(None, 3))

    def test_action_inconnue_rejetee(self):
        with self.assertRaises(ValueError):
            cs.set_next_action("p1", "faire_un_cafe")

    def test_action_faite_disparait(self):
        cs.set_next_action("p1", cs.ACTION_RELANCER, due_date="2020-01-01")
        self.assertEqual(len(cs.due_actions()), 1)
        cs.clear_next_action("p1", done_note="Relance envoyée")
        self.assertEqual(len(cs.due_actions()), 0)


class TestMaJournee(_DbTestCase):

    def test_seules_les_echeances_passees_remontent(self):
        cs.upsert_prospects([mk("p2", "Studio Beta")])
        cs.set_next_action("p1", cs.ACTION_RELANCER, due_date="2020-01-01")   # en retard
        futur = (date.today() + timedelta(days=30)).isoformat()
        cs.set_next_action("p2", cs.ACTION_RAPPELER, due_date=futur)          # plus tard

        due = cs.due_actions()
        self.assertEqual([d["place_id"] for d in due], ["p1"])
        self.assertEqual(len(cs.due_actions(include_future=True)), 2)

    def test_prospect_clos_sort_de_ma_journee(self):
        cs.set_next_action("p1", cs.ACTION_RELANCER, due_date="2020-01-01")
        cs.set_status("p1", cs.STATUS_PAS_INTERESSE)
        self.assertEqual(cs.due_actions(), [])

    def test_tri_les_plus_en_retard_dabord(self):
        cs.upsert_prospects([mk("p2", "B"), mk("p3", "C")])
        cs.set_next_action("p1", cs.ACTION_RELANCER, due_date="2020-06-01")
        cs.set_next_action("p2", cs.ACTION_RELANCER, due_date="2020-01-01")
        cs.set_next_action("p3", cs.ACTION_RELANCER, due_date="2020-03-01")
        self.assertEqual([d["place_id"] for d in cs.due_actions()], ["p2", "p3", "p1"])

    def test_compteurs(self):
        cs.upsert_prospects([mk("p2", "B")])
        cs.set_next_action("p1", cs.ACTION_RELANCER, due_date="2020-01-01")
        cs.set_next_action("p2", cs.ACTION_RELANCER, due_date=date.today().isoformat())
        s = cs.actions_summary()
        self.assertEqual(s["en_retard"], 1)
        self.assertEqual(s["aujourdhui"], 1)


class TestReponses(_DbTestCase):

    def test_reponse_annule_la_relance(self):
        """Règle d'or : on ne relance jamais quelqu'un qui a répondu."""
        cs.set_next_action("p1", cs.ACTION_RELANCER, due_date="2020-01-01")
        cs.mark_responded("p1", how="email")
        p = cs.get_prospect("p1")
        self.assertEqual(p["responded"], 1)
        self.assertEqual(p["next_action"], "")
        self.assertEqual(p["status"], cs.STATUS_INTERESSE)
        self.assertEqual(cs.due_actions(), [])

    def test_scenario_envoyez_moi_une_maquette(self):
        """Appel : « envoyez-moi une maquette » → à faire dès demain."""
        cs.mark_responded("p1", how="téléphone", note="Veut une maquette",
                          next_action=cs.ACTION_MAQUETTE)
        p = cs.get_prospect("p1")
        self.assertEqual(p["next_action"], cs.ACTION_MAQUETTE)
        self.assertEqual(p["due_date"], cs.add_business_days(None, 1))
        self.assertEqual(p["status"], cs.STATUS_INTERESSE)

    def test_scenario_associe_devait_rappeler(self):
        """« Mon associé vous rappelle » → il ne l'a pas fait → rappeler demain."""
        cs.set_next_action("p1", cs.ACTION_RAPPELER, delay_days=1,
                           note="L'associé devait rappeler, sans nouvelles")
        p = cs.get_prospect("p1")
        self.assertEqual(p["next_action"], cs.ACTION_RAPPELER)
        self.assertEqual(p["due_date"], cs.add_business_days(None, 1))
        self.assertIn("associé", p["action_note"])

    def test_reponse_ne_degrade_pas_un_rdv(self):
        cs.set_status("p1", cs.STATUS_RDV)
        cs.mark_responded("p1", how="email")
        self.assertEqual(cs.get_prospect("p1")["status"], cs.STATUS_RDV)

    def test_timeline_trace_tout(self):
        cs.set_next_action("p1", cs.ACTION_RELANCER)
        cs.mark_responded("p1", how="téléphone", next_action=cs.ACTION_MAQUETTE)
        kinds = [e["kind"] for e in cs.get_events("p1")]
        self.assertIn("action", kinds)
        self.assertIn("reponse", kinds)


class TestMigrationColonnes(unittest.TestCase):

    def test_ajout_colonnes_sur_base_existante(self):
        """Une base créée avant l'ajout des actions doit être migrée sans perte."""
        tmp = tempfile.TemporaryDirectory()
        orig = cs.DB_FILE
        cs.DB_FILE = os.path.join(tmp.name, "crm.db")
        try:
            import sqlite3
            os.makedirs(os.path.dirname(cs.DB_FILE), exist_ok=True)
            conn = sqlite3.connect(cs.DB_FILE)
            conn.executescript("""
                CREATE TABLE prospects (place_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    status TEXT DEFAULT 'nouveau', updated_at TEXT);
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
                INSERT INTO prospects (place_id, name) VALUES ('old', 'Ancien Prospect');
            """)
            conn.commit(); conn.close()

            cs.init_db()   # doit ajouter les colonnes manquantes

            cs.set_next_action("old", cs.ACTION_RELANCER, due_date="2020-01-01")
            self.assertEqual(cs.get_prospect("old")["name"], "Ancien Prospect")
            self.assertEqual(len(cs.due_actions()), 1)
        finally:
            cs.DB_FILE = orig
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
