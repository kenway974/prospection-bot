"""
tests/test_pipeline_selection.py — run_prospection() de bout en bout, sans réseau.

Google Maps, l'analyse des sites et la vérification des emails sont simulés.
Le test tourne dans un dossier temporaire : historique, CRM et cache
(tous dans ./output) restent isolés du vrai projet.
"""

import os
import queue
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from filters import FilterCriteria, WEBSITE_WITHOUT
from services.google_maps import Prospect

# Résultats Text Search simulés, par ville
RAW = {
    "Lyon": [
        {"place_id": "ok_lyon", "name": "Cuisines Dupont", "rating": 4.5, "user_ratings_total": 30, "business_status": "OPERATIONAL"},
        {"place_id": "mal_note", "name": "Cuisines Bof", "rating": 2.0, "user_ratings_total": 30, "business_status": "OPERATIONAL"},
        {"place_id": "ferme", "name": "Cuisines Fermées", "rating": 4.5, "user_ratings_total": 30, "business_status": "CLOSED_PERMANENTLY"},
        {"place_id": "avec_site", "name": "Cuisines Web", "rating": 4.5, "user_ratings_total": 30, "business_status": "OPERATIONAL"},
        {"place_id": "franchise", "name": "Mobalpa Lyon", "rating": 4.5, "user_ratings_total": 30, "business_status": "OPERATIONAL"},
    ],
    "Bron": [
        {"place_id": "ok_bron", "name": "Piscines Martin", "rating": 4.8, "user_ratings_total": 12, "business_status": "OPERATIONAL"},
        {"place_id": "ok_lyon", "name": "Cuisines Dupont", "rating": 4.5, "user_ratings_total": 30, "business_status": "OPERATIONAL"},
    ],
}


class TestRunProspectionSelection(unittest.TestCase):

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)
        self.text_search_calls = []
        self.details_calls = []

    def tearDown(self):
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _fake_fetch(self, keyword, max_raw=60, location=None):
        self.text_search_calls.append((keyword, location))
        return [dict(r) for r in RAW.get(location, [])]

    def _fake_build(self, raw, keyword, location=""):
        self.details_calls.append(raw["place_id"])
        website = "https://site.fr" if raw["place_id"] == "avec_site" else None
        return Prospect(
            raw["place_id"], raw["name"], "", "06 11 22 33 44", website,
            raw.get("rating"), raw.get("user_ratings_total", 0), keyword,
            location=location, business_status=raw.get("business_status", ""),
        )

    @staticmethod
    def _fake_analyze(p, **kwargs):
        p.score = 0
        p.issues = ["Pas de site web"]
        return p

    def _run(self, criteria, sources=("google_maps",)):
        params = {
            "google_key": "x", "notion_key": "", "brevo_key": "",
            "location": "Lyon", "locations": ["Lyon", "Bron"],
            "keywords": ["cuisiniste"], "radius": 10000, "max_results": 5,
            "your_name": "Kenny", "your_title": "Dev", "your_email": "", "your_website": "",
            "filters": criteria, "contact_score_threshold": 85,
            "send_emails": False, "gmail_address": "", "gmail_password": "", "send_sms": False,
            "find_dirigeants": False, "exclude_franchises": True, "user_franchises": [],
            "source_types": list(sources), "analysis_workers": 2,
        }
        log_q, results = queue.Queue(), []
        from pipeline import run_prospection
        with patch("services.google_maps.fetch_raw_candidates", self._fake_fetch), \
             patch("services.google_maps.build_prospect", self._fake_build), \
             patch("services.analyzer.analyze_prospect", self._fake_analyze), \
             patch("services.email_check.check_prospects", lambda prospects, log=None: {"valide": 0, "risque": 0, "invalide": 0}):
            run_prospection(params, log_q, results)
        logs = []
        while not log_q.empty():
            logs.append(log_q.get_nowait())
        return results, logs

    def test_multi_villes_et_criteres(self):
        results, logs = self._run(FilterCriteria(website=WEBSITE_WITHOUT))
        self.assertEqual(logs[-1], "__DONE__")
        self.assertFalse([l for l in logs if "Erreur critique" in l], logs)

        # Chaque ville interrogée
        self.assertEqual(self.text_search_calls, [("cuisiniste", "Lyon"), ("cuisiniste", "Bron")])
        # Note trop basse, fermé et franchise écartés AVANT Place Details (pas d'appel payant)
        self.assertNotIn("mal_note", self.details_calls)
        self.assertNotIn("ferme", self.details_calls)
        self.assertNotIn("franchise", self.details_calls)
        # Le doublon Lyon/Bron n'est construit qu'une fois
        self.assertEqual(self.details_calls.count("ok_lyon"), 1)

        by_id = {p.place_id: p for p in results}
        self.assertEqual(set(by_id), {"ok_lyon", "ok_bron"})  # « avec_site » exclu : a déjà un site
        self.assertEqual(by_id["ok_bron"].location, "Bron")
        self.assertTrue(any("exclus par les critères" in l and "a déjà un site" in l for l in logs))

    def test_email_obligatoire(self):
        results, logs = self._run(FilterCriteria(require_email=True))
        self.assertEqual(results, [])
        self.assertTrue(any("pas d'email trouvé" in l for l in logs))

    def test_ancien_parametre_min_rating_toujours_compris(self):
        """Sans « filters », le pipeline retombe sur min_rating (compatibilité)."""
        results, _ = self._run(None)  # min_rating 3.0 par défaut
        self.assertNotIn("mal_note", self.details_calls)
        self.assertIn("avec_site", {p.place_id for p in results})  # pas de filtre site web

    def test_tout_exclu_par_les_criteres_est_explique(self):
        """Si les critères écartent tout, le log le dit (et pas « tous déjà contactés »)."""
        results, logs = self._run(FilterCriteria(min_rating=4.9))
        self.assertEqual(results, [])
        self.assertEqual(self.details_calls, [])  # aucun appel payant
        self.assertTrue(any("exclus par les critères" in l and "note < 4.9" in l for l in logs), logs)
        self.assertFalse(any("tous déjà contactés" in l for l in logs))

    def test_criteres_maps_non_appliques_aux_autres_sources(self):
        """Sirène n'a ni site ni téléphone : le filtre téléphone ne doit pas tout exclure."""
        from filters import PHONE_REQUIRED
        sirene = [Prospect("siren_1", "Menuiserie Durand", "", None, None, None, 0, "menuisier")]
        params_sources = ["sirene"]
        with patch("services.sources.search_sirene", lambda kw, loc, n: [Prospect(**vars(x)) for x in sirene]):
            results, logs = self._run(FilterCriteria(phone=PHONE_REQUIRED), sources=params_sources)
        self.assertEqual([p.place_id for p in results], ["siren_1"])
        self.assertEqual(results[0].location, "Lyon")
        self.assertTrue(any("Google Maps uniquement" in l for l in logs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
