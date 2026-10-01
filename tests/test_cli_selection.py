"""
tests/test_cli_selection.py — Critères de sélection dans la ligne de commande (main.py).

Google Maps, l'analyse et les envois sont simulés ; le test tourne dans un
dossier temporaire pour isoler output/.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main
from config import Config
from services import google_maps
from services.google_maps import Prospect


def _raw(pid, website=None):
    return {"place_id": pid, "name": pid, "rating": 4.5, "user_ratings_total": 10,
            "business_status": "OPERATIONAL", "_website": website}


# Lyon et Bron partagent « commun » ; à Lyon, les 2 premiers ont déjà un site
RAW = {
    "Lyon": [_raw("site_1", "https://a.fr"), _raw("site_2", "https://b.fr"), _raw("commun"), _raw("lyon_2")],
    "Bron": [_raw("commun"), _raw("bron_1")],
}


class _Silent:
    def __getattr__(self, _):
        return lambda *a, **k: None


class TestCliSelection(unittest.TestCase):

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)
        self.details_calls = []

    def tearDown(self):
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _build(self, raw, keyword, location=""):
        self.details_calls.append(raw["place_id"])
        return Prospect(raw["place_id"], raw["name"], "", "04 00 00 00 00", raw["_website"],
                        raw["rating"], raw["user_ratings_total"], keyword, location=location)

    def _run(self, env):
        base = {"GOOGLE_PLACES_API_KEY": "x", "SEARCH_LOCATION": "Lyon;Bron",
                "SEARCH_KEYWORDS": "cuisiniste", "MAX_RESULTS_PER_KEYWORD": "2"}
        with patch.dict(os.environ, {**base, **env}):
            cfg = Config()
        saved = {}

        def analyze(p):
            p.score = 0
            return p

        with patch.object(main, "config", cfg), patch.object(google_maps, "config", cfg), \
             patch.object(main, "logger", _Silent()), patch.object(google_maps, "logger", _Silent()), \
             patch.object(google_maps, "fetch_raw_candidates", lambda kw, max_raw=60, location=None: [dict(r) for r in RAW[location]]), \
             patch.object(google_maps, "build_prospect", self._build), \
             patch.object(main, "analyze_prospect", analyze), \
             patch.object(main, "sync_all", lambda p: None), \
             patch.object(main, "mark_as_contacted", lambda p: saved.setdefault("final", list(p))), \
             patch.object(main, "load_contacted_ids", lambda: set()):
            main.run()
        return [p.place_id for p in saved.get("final", [])]

    def test_prospects_exclus_remplaces_et_doublons_sans_appel_payant(self):
        final = self._run({"WEBSITE_FILTER": "without"})
        # Les 2 sites écartés ne comptent pas dans l'objectif (2/mot-clé) : on obtient
        # quand même 2 prospects à Lyon, plus 1 à Bron.
        self.assertEqual(sorted(final), ["bron_1", "commun", "lyon_2"])
        # « commun » n'est construit (Place Details payant) qu'une seule fois
        self.assertEqual(self.details_calls.count("commun"), 1)

    def test_valeur_invalide_arrete_le_script(self):
        with self.assertRaises(SystemExit) as ctx:
            self._run({"PHONE_FILTER": "portable"})
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(self.details_calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
