"""
tests/test_qualification_reims.py — Régression « cuisinistes Reims » + tests unitaires
de la qualification (métier, Sirène, site retrouvé, score d'opportunité, appelable).

Aucun appel réseau : Google Maps, Sirène, sites web et analyse sont simulés.
"""

import os
import queue
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.google_maps import Prospect
from tests import reims_fixture as F


def _build(raw, keyword, location=""):
    return Prospect(
        raw["place_id"], raw["name"], raw["formatted_address"], raw["_phone"], raw["_website"],
        raw["rating"], raw["user_ratings_total"], keyword, location=location,
        types=list(raw["types"]), website_source="maps" if raw["_website"] else "",
    )


def _analyze(p, **kwargs):
    if p.has_website():
        p.score, p.issues, p.issue_keys = 85, [], []        # site correct (HTTPS, mobile, réseaux)
    else:
        p.score, p.issues, p.issue_keys = 0, ["Pas de site web"], ["no_website"]
    return p


def run_reims(by_query=None, extra_params=None):
    """Lance run_prospection sur « cuisinistes Reims » simulé → (prospects, exclus, logs)."""
    by_query = by_query or F.BY_QUERY
    params = {
        "google_key": "x", "notion_key": "", "brevo_key": "",
        "location": "Reims", "keywords": ["cuisinistes"], "radius": 10000, "max_results": 10,
        "your_name": "Kenny", "your_title": "Dev", "your_email": "", "your_website": "",
        "contact_score_threshold": 85, "send_emails": False, "gmail_address": "",
        "gmail_password": "", "send_sms": False, "find_dirigeants": False,
        "exclude_franchises": True, "user_franchises": [], "source_types": ["google_maps"],
        "analysis_workers": 2, **(extra_params or {}),
    }
    log_q, results, excluded = queue.Queue(), [], []
    from pipeline import run_prospection
    with patch("services.google_maps.fetch_raw_candidates",
               lambda kw, max_raw=60, location=None: [dict(r) for r in by_query.get(kw, [])]), \
         patch("services.google_maps.build_prospect", _build), \
         patch("services.analyzer.analyze_prospect", _analyze), \
         patch("services.dirigeants._search",
               lambda name, postal, raise_errors=False: [e for e in [F.sirene_entry(name)] if e]), \
         patch("services.site_finder._fetch_text",
               lambda domain: (F.PAGES.get(domain), f"https://{domain}/")), \
         patch("services.email_check.check_prospects", lambda prospects, log=None: {"valide": 0, "risque": 0, "invalide": 0}):
        run_prospection(params, log_q, results, excluded)
    logs = []
    while not log_q.empty():
        logs.append(log_q.get_nowait())
    return results, excluded, logs


class _TmpCwd(unittest.TestCase):
    def setUp(self):
        self._cwd, self._tmp = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestRegressionCuisinistesReims(_TmpCwd):

    @classmethod
    def setUpClass(cls):
        cwd, tmp = os.getcwd(), tempfile.mkdtemp()
        os.chdir(tmp)
        try:
            cls.results, cls.excluded, cls.logs = run_reims()
        finally:
            os.chdir(cwd)
            shutil.rmtree(tmp, ignore_errors=True)
        cls.by_id = {p.place_id: p for p in cls.results}
        cls.excl = {e["place_id"]: e for e in cls.excluded}

    def test_pas_d_erreur(self):
        self.assertEqual(self.logs[-1], "__DONE__")
        self.assertFalse([l for l in self.logs if "Erreur critique" in l])

    def test_hors_cible_exclus_avec_raison(self):
        self.assertIn("electrician", self.excl["az"]["reason"])           # AZ Energy
        self.assertEqual(self.excl["az"]["stage"], "catégorie")
        self.assertEqual(self.excl["piano"]["stage"], "catégorie")        # Au Piano des Chefs (nom + école)

    def test_chaines_et_distributeurs_exclus(self):
        for pid in ("cedeo1", "cedeo2", "cedeo3", "cuisinella", "lapeyre", "darty", "lm"):
            with self.subTest(pid=pid):
                self.assertEqual(self.excl[pid]["stage"], "liste noire")
                self.assertNotIn(pid, self.by_id)

    def test_chaque_exclusion_a_une_raison_et_une_seule_ligne(self):
        ids = [e["place_id"] for e in self.excluded]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(e["reason"] for e in self.excluded))

    def test_vrais_cuisiniers_retrouves(self):
        self.assertTrue(F.REAL_IDS <= set(self.by_id), F.REAL_IDS - set(self.by_id))

    def test_cuisine_design_a_completer(self):
        p = self.by_id["design"]
        self.assertLess(p.opportunity, min(self.by_id[i].opportunity for i in F.REAL_IDS))
        self.assertFalse(p.is_callable())
        self.assertEqual(p.contact_status, "à compléter")
        self.assertTrue(any("introuvable dans Sirène" in f for f in p.flags))

    def test_angel_tres_equipe_en_bas_de_liste(self):
        angel = self.by_id["angel"]
        self.assertLess(angel.opportunity, 20)
        self.assertTrue(any("présence déjà solide" in label for label, _ in angel.score_details))
        self.assertEqual(self.results[-1].place_id, "angel")

    def test_vrais_cuisinistes_devant(self):
        self.assertIn(self.results[0].place_id, F.REAL_IDS)
        for pid in F.REAL_IDS:
            self.assertGreater(self.by_id[pid].opportunity, self.by_id["angel"].opportunity)


class TestAzEnergyMalCategorise(_TmpCwd):
    """Si Google range AZ Energy en « entrepreneur général », Sirène + site le démasquent."""

    def test_signale_et_penalise(self):
        az = dict(F.NOISE[0], types=["general_contractor", "point_of_interest"])
        results, _, _ = run_reims(by_query={"cuisinistes": [az]})
        p = results[0]
        flags = " | ".join(p.flags)
        self.assertIn("domaine étranger (.lu)", flags)
        self.assertIn("chiffre d'affaires déclaré 0", flags)
        self.assertIn("NAF 43.21A", flags)
        self.assertLess(p.opportunity, 20)


# ---------------------------------------------------------------------------
# Tests unitaires des briques
# ---------------------------------------------------------------------------

class TestTrades(unittest.TestCase):

    def test_find_trade_pluriel_accents(self):
        from trades import find_trade
        self.assertEqual(find_trade("Cuisinistes").id, "cuisiniste")
        self.assertEqual(find_trade("électricien").id, "electricien")
        self.assertEqual(find_trade("Piscines").id, "pisciniste")
        self.assertIsNone(find_trade("restaurant"))

    def test_category_verdict(self):
        from trades import category_verdict, find_trade
        t = find_trade("cuisiniste")
        self.assertEqual(category_verdict("Etoile Cuisines", [], t)[0], "ok")            # le nom confirme
        self.assertEqual(category_verdict("BO DeZign", ["home_goods_store"], t)[0], "ok")  # la catégorie confirme
        self.assertEqual(category_verdict("AZ Energy", ["electrician"], t)[0], "exclure")
        self.assertEqual(category_verdict("Atelier X", ["restaurant"], t)[0], "exclure")
        self.assertEqual(category_verdict("Au Piano des Chefs", [], t)[0], "exclure")    # nom hors métier
        self.assertEqual(category_verdict("Société Martin", ["point_of_interest"], t)[0], "verifier")
        self.assertEqual(category_verdict("Société Martin", ["electronics_store"], t)[0], "verifier")  # inconnue ≠ exclue
        self.assertEqual(category_verdict("Boissons du Nord", [], find_trade("menuisier"))[0], "verifier")  # « bois » ≠ « Boissons »
        self.assertEqual(category_verdict("Piscines & Spa", ["spa"], find_trade("pisciniste"))[0], "ok")

    def test_queries_sans_doublon_et_plafonnees(self):
        from trades import MAX_QUERIES_PER_KEYWORD, queries_for
        q = queries_for("cuisinistes")
        self.assertEqual(q[0], "cuisinistes")
        self.assertNotIn("cuisiniste", q)            # même requête au singulier : pas relancée
        self.assertLessEqual(len(q), MAX_QUERIES_PER_KEYWORD)
        self.assertEqual(queries_for("restaurant"), ["restaurant"])


class TestCompanyCheck(unittest.TestCase):

    def test_evaluate(self):
        from services.company_check import evaluate
        from trades import find_trade
        t = find_trade("cuisiniste")
        self.assertEqual(evaluate({"etat_administratif": "C"}, t)[0], "entreprise fermée (Sirène)")
        reason, flags = evaluate({"etat_administratif": "A", "activite_principale": "47.59A",
                                  "nombre_etablissements_ouverts": 1}, t)
        self.assertIsNone(reason)
        self.assertEqual(flags, [])
        _, flags = evaluate({"etat_administratif": "A", "activite_principale": "43.21A",
                             "nombre_etablissements_ouverts": 12, "finances": {"2025": {"ca": 0}}}, t)
        self.assertEqual(len(flags), 3)               # NAF + chaîne + CA nul
        self.assertTrue(evaluate(None, t)[1][0].startswith("introuvable"))

    def test_panne_reseau_ne_fait_pas_exclure(self):
        from services import company_check
        p = Prospect("x", "Etoile Cuisines", F.ADDR, "03", None, 4.0, 3, "kw")

        def boom(*a, **k):
            raise company_check.dirigeants.requests.ConnectionError("down")
        with patch("services.dirigeants._search", boom):
            self.assertIsNone(company_check.check_prospect(p, None))
        self.assertIn("Sirène indisponible", p.flags[0])


class TestSiteFinder(unittest.TestCase):

    def test_domaines_candidats(self):
        from services.site_finder import candidate_domains
        d = candidate_domains("SARL AZ Energy")
        self.assertEqual(d[0], "azenergy.fr")
        self.assertIn("azenergy.lu", d)
        self.assertLessEqual(len(d), 8)
        self.assertEqual(candidate_domains("&"), [])

    def test_confirmation(self):
        from services.site_finder import page_confirms
        self.assertEqual(page_confirms("Tél. 03 26 11 22 33", "X", "03 26 11 22 33"), "fort")
        self.assertEqual(page_confirms("Etoile Cuisines - 51100 Reims", "Etoile Cuisines", None, F.ADDR), "fort")
        self.assertEqual(page_confirms("Etoile Cuisines à Lyon", "Etoile Cuisines", None, F.ADDR), "faible")
        self.assertIsNone(page_confirms("Autre entreprise", "Etoile Cuisines", None, F.ADDR))

    def test_securite_hote(self):
        from services import site_finder
        public = [(2, 1, 6, "", ("93.184.216.34", 0))]
        private = [(2, 1, 6, "", ("10.0.0.5", 0))]
        metadata = [(2, 1, 6, "", ("169.254.169.254", 0))]
        with patch.object(site_finder.socket, "getaddrinfo", lambda h, p: public):
            self.assertTrue(site_finder._safe_host("https://etoile-cuisines.fr"))
            self.assertFalse(site_finder._safe_host("https://etoile-cuisines.fr:8080"))   # port non standard
            self.assertFalse(site_finder._safe_host("ftp://etoile-cuisines.fr"))          # schéma
            self.assertFalse(site_finder._safe_host("http://127.0.0.1/admin"))            # IP littérale
            self.assertFalse(site_finder._safe_host("http://localhost:8501"))
        with patch.object(site_finder.socket, "getaddrinfo", lambda h, p: private):
            self.assertFalse(site_finder._safe_host("https://piege.fr"))                  # DNS → réseau privé
        with patch.object(site_finder.socket, "getaddrinfo", lambda h, p: metadata):
            self.assertFalse(site_finder._safe_host("https://piege.fr"))                  # métadonnées cloud

    def test_redirection_vers_reseau_interne_bloquee(self):
        from services import site_finder

        class Resp:
            is_redirect, status_code, headers = True, 302, {"Location": "http://192.168.1.1/admin"}
            def __enter__(self): return self
            def __exit__(self, *a): return False

        calls = []
        with patch.object(site_finder.socket, "getaddrinfo", lambda h, p: [(2, 1, 6, "", ("93.184.216.34", 0))]), \
             patch.object(site_finder.requests, "get", lambda url, **k: calls.append(url) or Resp()):
            text, _ = site_finder._fetch_text("piege.fr")
        self.assertIsNone(text)
        self.assertEqual(calls, ["https://piege.fr"])     # la 2e requête (interne) n'est jamais partie

    def test_homonyme_non_adopte(self):
        from services import site_finder
        p = Prospect("x", "Cuisine Design", f"1 rue X, {F.ADDR}", None, None, 4.0, 0, "kw")
        pages = {"cuisinedesign.fr": "<h1>Cuisine Design</h1> Bordeaux"}
        with patch.object(site_finder, "_fetch_text", lambda d: (pages.get(d), f"https://{d}/")):
            site_finder.complete_website(p)
        self.assertIsNone(p.website)                      # pas d'audit ni d'email d'un homonyme
        self.assertIn("à confirmer", p.flags[0])

    def test_site_trouve_complete_le_prospect(self):
        from services import site_finder
        p = Prospect("x", "Etoile Cuisines", f"1 rue X, {F.ADDR}", "03 26 11 22 33", None, 4.0, 3, "kw")
        pages = {"etoilecuisines.fr": "<p>Appelez le 03 26 11 22 33</p>"}
        with patch.object(site_finder, "_fetch_text", lambda d: (pages.get(d), f"https://{d}/")):
            site_finder.complete_website(p)
        self.assertEqual(p.website, "https://etoilecuisines.fr/")
        self.assertEqual(p.website_source, "deviné")


class TestOpportunite(unittest.TestCase):

    def _p(self, website=None, score=0, keys=(), reviews=5, rating=4.0, flags=()):
        p = Prospect("x", "X", "", "03", website, rating, reviews, "kw")
        p.score, p.issue_keys, p.flags = score, list(keys), list(flags)
        return p

    def test_sans_site_peu_d_avis_en_tete(self):
        from services.opportunity import compute
        total, details = compute(self._p())
        self.assertEqual(total, 75)                    # 55 sans site + 20 très peu d'avis
        self.assertEqual(len(details), 2)

    def test_presence_solide_penalisee(self):
        from services.opportunity import compute
        total, details = compute(self._p("https://a.fr", score=85, reviews=120, rating=4.8))
        self.assertEqual(total, 0)
        self.assertTrue(any(pts == -40 for _, pts in details))

    def test_drapeaux_penalisent(self):
        from services.opportunity import compute
        sans, _ = compute(self._p())
        avec, _ = compute(self._p(flags=["site sur un domaine étranger (.lu) — activité hors France ?"]))
        self.assertEqual(sans - avec, 30)

    def test_detail_somme_coherente(self):
        from services.opportunity import compute
        total, details = compute(self._p("https://a.fr", score=40, keys=["lead_form"], reviews=20))
        self.assertEqual(total, sum(pts for _, pts in details))


class TestAppelable(unittest.TestCase):

    def test_statut(self):
        self.assertTrue(Prospect("x", "X", "", "03 26 00 00 00", None, None, 0, "kw").is_callable())
        self.assertFalse(Prospect("x", "X", "", None, None, None, 0, "kw").is_callable())
        self.assertFalse(Prospect("x", "X", "", "  ", None, None, 0, "kw").is_callable())
        self.assertEqual(Prospect("x", "X", "", None, None, None, 0, "kw").to_dict()["contact_status"], "à compléter")


if __name__ == "__main__":
    unittest.main(verbosity=2)
