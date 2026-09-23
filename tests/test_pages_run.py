"""
tests/test_pages_run.py — Exécute RÉELLEMENT chaque page de l'app.

Les autres tests vérifient la logique métier ; celui-ci vérifie que l'interface
s'affiche sans planter, page par page, avec une base CRM remplie (prospects,
actions dues, dirigeant, email vérifié) pour exercer les vrais chemins de rendu
(panneau LinkedIn, badges, Ma journée…).

Utilise l'outil officiel Streamlit AppTest.
"""

import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

PAGES = [
    "page_ma_journee", "page_pipeline", "page_relances",
    "page_prospection", "page_statistiques", "page_reglages",
]

try:
    from streamlit.testing.v1 import AppTest
    HAS_ST = True
except ImportError:
    HAS_ST = False


def _seed_db(db_path: str) -> None:
    import crm_store as cs
    from services.google_maps import Prospect
    orig = cs.DB_FILE
    cs.DB_FILE = db_path
    try:
        cs.init_db()
        a = Prospect("p_a", "ESN Alpha", "1 rue X, 97400 Saint-Denis", "0692000000",
                     "https://esn-alpha.re", 4.6, 40, "ESN")
        a.email, a.email_status, a.email_status_reason = "jean@esn-alpha.re", "valide", "serveur mail déclaré"
        a.dirigeant, a.dirigeant_qualite = "Jean Dupont", "Président"
        b = Prospect("p_b", "Studio Beta", "2 rue Y, 97410 Saint-Pierre", None, None, None, 0, "agence web")
        b.email, b.email_status, b.email_status_reason = "contact@beta.re", "risque", "sans MX"
        cs.upsert_prospects([a, b], sector="entreprises", service_id="web_freelance")
        cs.set_next_action("p_a", cs.ACTION_LINKEDIN, due_date="2020-01-01", note="Invitation envoyée")
        cs.set_next_action("p_b", cs.ACTION_RELANCER, due_date="2020-01-01")
        cs.set_status("p_b", cs.STATUS_INTERESSE)
    finally:
        cs.DB_FILE = orig


@unittest.skipUnless(HAS_ST, "streamlit non installé")
class TestChaquePageSExecute(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
        cls.workdir = tempfile.mkdtemp()
        cls.old_cwd = os.getcwd()
        os.chdir(cls.workdir)                      # output/ isolé dans un dossier temporaire
        os.makedirs("output", exist_ok=True)
        _seed_db(os.path.join(cls.workdir, "output", "crm.db"))

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.old_cwd)
        shutil.rmtree(cls.workdir, ignore_errors=True)

    def _run_page(self, page_fn: str):
        # Rend la page ciblée « par défaut » pour l'ouvrir directement
        s = self.src.replace('url_path="ma-journee", default=True)', 'url_path="ma-journee")')
        s, n = re.subn(r"(st\.Page\(" + page_fn + r",[^)]*?)\)", r"\1, default=True)", s, count=1)
        self.assertEqual(n, 1, f"page {page_fn} introuvable dans la navigation")
        tmp = os.path.join(ROOT, f"_apptest_{page_fn}.py")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(s)
        try:
            at = AppTest.from_file(tmp, default_timeout=120)
            at.run()
            return at
        finally:
            os.remove(tmp)

    def test_toutes_les_pages(self):
        for page in PAGES:
            with self.subTest(page=page):
                at = self._run_page(page)
                errors = [str(e.value)[:500] for e in at.exception]
                self.assertEqual(errors, [], f"{page} plante : {errors}")

    def test_ma_journee_affiche_les_actions_dues(self):
        at = self._run_page("page_ma_journee")
        text = " ".join(m.value for m in at.markdown)
        self.assertIn("ESN Alpha", text)
        self.assertIn("Jean Dupont", text)     # dirigeant visible


if __name__ == "__main__":
    unittest.main(verbosity=2)
