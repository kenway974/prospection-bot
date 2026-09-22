"""
tests/test_scheduler_security.py — Aucun secret ne doit atterrir sur disque.

Les emails programmés stockaient le mot de passe d'application Gmail et la clé
Notion en clair dans output/pending_emails.json. Ces tests verrouillent le
correctif : secrets gardés en RAM uniquement, et purge des fichiers hérités.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import scheduler


class TestSchedulerSecurity(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_queue = scheduler._QUEUE_FILE
        scheduler._QUEUE_FILE = os.path.join(self._tmp.name, "pending_emails.json")
        scheduler._runtime_creds.clear()

    def tearDown(self):
        scheduler._QUEUE_FILE = self._orig_queue
        scheduler._runtime_creds.clear()
        self._tmp.cleanup()

    def _disk(self) -> str:
        with open(scheduler._QUEUE_FILE, "r", encoding="utf-8") as f:
            return f.read()

    def test_aucun_secret_ecrit_sur_disque(self):
        scheduler.add_pending(
            place_id="p1", name="Agence X", email="a@x.fr", draft="OBJET : test",
            gmail_address="moi@gmail.com", gmail_password="MDP-SECRET",
            send_at=9e9, notion_page_id="pg1", notion_api_key="CLE-NOTION",
        )
        disk = self._disk()
        self.assertNotIn("MDP-SECRET", disk)
        self.assertNotIn("CLE-NOTION", disk)
        # Les données non sensibles restent bien présentes
        self.assertIn("a@x.fr", disk)
        self.assertIn("moi@gmail.com", disk)

    def test_identifiants_disponibles_en_memoire(self):
        scheduler.add_pending(
            place_id="p1", name="X", email="a@x.fr", draft="d",
            gmail_address="moi@gmail.com", gmail_password="MDP-SECRET", send_at=9e9,
        )
        self.assertEqual(scheduler._gmail_password_for("moi@gmail.com"), "MDP-SECRET")
        self.assertTrue(scheduler.credentials_available())

    def test_purge_des_secrets_hérités(self):
        """Un fichier écrit par une ancienne version doit être nettoyé."""
        legacy = [{
            "id": "old", "place_id": "p", "name": "X", "email": "a@x.fr",
            "draft": "d", "gmail_address": "moi@gmail.com",
            "gmail_password": "ANCIEN-MDP", "notion_api_key": "ANCIENNE-CLE",
            "send_at": 9e9, "sent": False,
        }]
        os.makedirs(os.path.dirname(scheduler._QUEUE_FILE), exist_ok=True)
        with open(scheduler._QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(legacy, f)

        purged = scheduler._purge_secrets_on_disk()

        self.assertEqual(purged, 2)
        disk = self._disk()
        self.assertNotIn("ANCIEN-MDP", disk)
        self.assertNotIn("ANCIENNE-CLE", disk)
        # L'email reste en file, il n'est pas perdu
        self.assertIn("a@x.fr", disk)

    def test_email_en_retard_compte_comme_overdue(self):
        scheduler.add_pending(
            place_id="p1", name="X", email="a@x.fr", draft="d",
            gmail_address="moi@gmail.com", gmail_password="mdp", send_at=1.0,  # passé
        )
        self.assertEqual(scheduler.get_stats()["overdue"], 1)

    def test_sans_identifiant_email_non_perdu(self):
        """Sans mot de passe, l'email reste en file (pas de perte silencieuse)."""
        scheduler.add_pending(
            place_id="p1", name="X", email="a@x.fr", draft="d",
            gmail_address="moi@gmail.com", gmail_password="mdp", send_at=1.0,
        )
        scheduler._runtime_creds.clear()  # simule un redémarrage
        os.environ.pop("GMAIL_APP_PASSWORD", None)

        stats = scheduler.process_due()

        self.assertEqual(stats["skipped_no_credentials"], 1)
        self.assertEqual(stats["sent"], 0)
        self.assertEqual(scheduler.get_stats()["pending"], 1)  # toujours là


if __name__ == "__main__":
    unittest.main(verbosity=2)
