"""
tests/test_crm_store.py — Base CRM SQLite.

Points critiques verrouillés ici :
  - un re-scan ne doit JAMAIS écraser le statut, les notes ou l'historique
    de contact d'un prospect déjà suivi ;
  - la migration depuis les anciens JSON est fidèle et ne s'exécute qu'une fois ;
  - les prospects sortis du flux (client/pas intéressé/blacklist) ne sont plus
    reprospectés.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crm_store
from services.google_maps import Prospect


def make_prospect(place_id="p1", name="Agence X", email=None, score=80, website="https://x.fr"):
    p = Prospect(
        place_id=place_id, name=name, address="1 rue X", phone="0612345678",
        website=website, rating=4.5, user_ratings_total=40, keyword="agence web",
    )
    p.email = email
    p.score = score
    p.issues = ["Pas de HTTPS"]
    p.issue_keys = ["https"]
    return p


class _DbTestCase(unittest.TestCase):
    """Isole chaque test dans sa propre base temporaire."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_db = crm_store.DB_FILE
        crm_store.DB_FILE = os.path.join(self._tmp.name, "crm.db")
        crm_store.init_db()

    def tearDown(self):
        crm_store.DB_FILE = self._orig_db
        self._tmp.cleanup()


class TestProspects(_DbTestCase):

    def test_insertion_et_lecture(self):
        created = crm_store.upsert_prospects([make_prospect()], sector="entreprises")
        self.assertEqual(created, 1)
        p = crm_store.get_prospect("p1")
        self.assertEqual(p["name"], "Agence X")
        self.assertEqual(p["status"], crm_store.STATUS_NOUVEAU)
        self.assertEqual(json.loads(p["issue_keys"]), ["https"])
        self.assertEqual(p["target_sector"], "entreprises")

    def test_rescan_nécrase_pas_statut_ni_notes(self):
        """Le cœur du CRM : re-trouver un prospect ne doit rien perdre."""
        crm_store.upsert_prospects([make_prospect()])
        crm_store.set_status("p1", crm_store.STATUS_INTERESSE)
        crm_store.set_notes("p1", "Rappeler en janvier")

        # Nouveau run : le même prospect ressort avec un score différent
        crm_store.upsert_prospects([make_prospect(score=42, email="c@x.fr")])

        p = crm_store.get_prospect("p1")
        self.assertEqual(p["status"], crm_store.STATUS_INTERESSE)   # préservé
        self.assertEqual(p["notes"], "Rappeler en janvier")          # préservé
        self.assertEqual(p["score"], 42)                             # rafraîchi
        self.assertEqual(p["email"], "c@x.fr")                       # enrichi

    def test_email_existant_non_ecrase_par_none(self):
        crm_store.upsert_prospects([make_prospect(email="garde@moi.fr")])
        crm_store.upsert_prospects([make_prospect(email=None)])
        self.assertEqual(crm_store.get_prospect("p1")["email"], "garde@moi.fr")

    def test_marquage_contacte(self):
        crm_store.upsert_prospects([make_prospect()])
        crm_store.mark_contacted(["p1"], channel="email")
        p = crm_store.get_prospect("p1")
        self.assertEqual(p["status"], crm_store.STATUS_CONTACTE)
        self.assertTrue(p["first_contact_date"])
        self.assertIn("p1", crm_store.contacted_place_ids())

    def test_marquage_ne_degrade_pas_un_statut_avance(self):
        crm_store.upsert_prospects([make_prospect()])
        crm_store.set_status("p1", crm_store.STATUS_RDV)
        crm_store.mark_contacted(["p1"])
        self.assertEqual(crm_store.get_prospect("p1")["status"], crm_store.STATUS_RDV)

    def test_blacklist_exclu_de_la_prospection(self):
        crm_store.upsert_prospects([make_prospect()])
        crm_store.set_status("p1", crm_store.STATUS_BLACKLIST)
        self.assertIn("p1", crm_store.contacted_place_ids())

    def test_filtres(self):
        crm_store.upsert_prospects([
            make_prospect("p1", "Avec Email", email="a@x.fr"),
            make_prospect("p2", "Sans Email", email=None),
        ])
        crm_store.set_status("p2", crm_store.STATUS_CLIENT)

        self.assertEqual(len(crm_store.list_prospects(has_email=True)), 1)
        self.assertEqual(len(crm_store.list_prospects(has_email=False)), 1)
        self.assertEqual(len(crm_store.list_prospects(status=crm_store.STATUS_CLIENT)), 1)
        self.assertEqual(len(crm_store.list_prospects(search="Avec")), 1)

    def test_statut_invalide_rejete(self):
        crm_store.upsert_prospects([make_prospect()])
        with self.assertRaises(ValueError):
            crm_store.set_status("p1", "n_importe_quoi")

    def test_timeline_evenements(self):
        crm_store.upsert_prospects([make_prospect()])
        crm_store.set_status("p1", crm_store.STATUS_INTERESSE)
        crm_store.add_event("p1", "linkedin", "Demande de connexion envoyée")
        kinds = [e["kind"] for e in crm_store.get_events("p1")]
        self.assertIn("statut", kinds)
        self.assertIn("linkedin", kinds)

    def test_compteurs_par_statut(self):
        crm_store.upsert_prospects([make_prospect("p1"), make_prospect("p2")])
        crm_store.set_status("p2", crm_store.STATUS_CLIENT)
        counts = crm_store.status_counts()
        self.assertEqual(counts[crm_store.STATUS_NOUVEAU], 1)
        self.assertEqual(counts[crm_store.STATUS_CLIENT], 1)


class TestCampaigns(_DbTestCase):

    def test_campagne_et_rattachement(self):
        cid = crm_store.add_campaign(
            profile="Freelance", location="Paris", keywords=["ESN"],
            sources=["Google Maps"], total_prospects=2,
        )
        crm_store.upsert_prospects([make_prospect()], campaign_id=cid)
        camps = crm_store.list_campaigns()
        self.assertEqual(len(camps), 1)
        self.assertEqual(camps[0]["keywords"], ["ESN"])
        self.assertEqual(crm_store.get_prospect("p1")["campaign_id"], cid)


class TestMigration(_DbTestCase):

    def _write_legacy(self, out: str):
        os.makedirs(out, exist_ok=True)
        prospects_file = os.path.join(out, "prospects_20260101_000000.json")
        with open(prospects_file, "w", encoding="utf-8") as f:
            json.dump([make_prospect("pA", "Ancienne Agence").to_dict()], f)
        with open(os.path.join(out, "history.json"), "w", encoding="utf-8") as f:
            json.dump([{
                "date": "01/01/2026 10:00", "profile": "Dev Web", "location": "Paris",
                "keywords": ["agence web"], "sources": ["Google Maps"],
                "total_prospects": 1, "emails_trouvés": 1, "fichier": prospects_file,
            }], f)
        with open(os.path.join(out, "contacted_place_ids.json"), "w", encoding="utf-8") as f:
            json.dump({
                "pA": {"name": "Ancienne Agence", "email": "a@x.fr",
                       "first_contact_date": "2026-01-02", "responded": False,
                       "followup_step": 2},
                "pB": {"name": "Jamais Scannée", "first_contact_date": "2026-01-03",
                       "responded": True},
            }, f)

    def test_migration_complete_et_idempotente(self):
        out = os.path.join(self._tmp.name, "output")
        self._write_legacy(out)

        res = crm_store.migrate_from_json(out)
        self.assertEqual(res["campaigns"], 1)
        self.assertEqual(res["contacts"], 2)

        # Campagne importée
        self.assertEqual(len(crm_store.list_campaigns()), 1)

        # Prospect scanné + son historique de contact fusionnés
        pa = crm_store.get_prospect("pA")
        self.assertEqual(pa["name"], "Ancienne Agence")
        self.assertEqual(pa["followup_step"], 2)
        self.assertEqual(pa["status"], crm_store.STATUS_RELANCE)

        # Contact connu mais jamais scanné : créé quand même, marqué intéressé
        pb = crm_store.get_prospect("pB")
        self.assertIsNotNone(pb)
        self.assertEqual(pb["status"], crm_store.STATUS_INTERESSE)

        # Idempotence : une 2e migration ne duplique rien
        res2 = crm_store.migrate_from_json(out)
        self.assertEqual(res2["campaigns"], 0)
        self.assertEqual(len(crm_store.list_campaigns()), 1)

    def test_ancien_format_liste(self):
        """contacted_place_ids.json au tout premier format (simple liste)."""
        out = os.path.join(self._tmp.name, "output")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "contacted_place_ids.json"), "w", encoding="utf-8") as f:
            json.dump(["pX", "pY"], f)
        res = crm_store.migrate_from_json(out)
        self.assertEqual(res["contacts"], 2)
        self.assertEqual(crm_store.get_prospect("pX")["status"], crm_store.STATUS_CONTACTE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
