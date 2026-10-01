"""
tests/test_filters.py — Critères de sélection des prospects et nouveaux segments cibles.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from filters import (
    FilterCriteria, PHONE_MOBILE, PHONE_REQUIRED, WEBSITE_WITH, WEBSITE_WITHOUT,
    count_reason, format_exclusions, is_mobile, parse_locations,
    post_analysis_reason, prospect_exclusion_reason, raw_exclusion_reason,
)
from services.google_maps import Prospect
from target_segments import TARGET_SEGMENTS, get_target, merge_keywords


def _p(name="Test", website="https://ex.fr", phone="04 78 00 00 00", email=None) -> Prospect:
    p = Prospect(name, name, "", phone, website, 4.0, 20, "kw")
    p.email = email
    return p


def _raw(rating=4.0, reviews=20, status="OPERATIONAL") -> dict:
    return {"place_id": "x", "name": "X", "rating": rating, "user_ratings_total": reviews, "business_status": status}


class TestFilterCriteria(unittest.TestCase):

    def test_valeurs_invalides_refusees(self):
        invalid = [
            {"website": "sans"},
            {"phone": "fixe"},
            {"min_rating": 4.5, "max_rating": 3.0},
            {"max_rating": 6.0},
            {"min_reviews": -1},
            {"min_reviews": 50, "max_reviews": 10},
        ]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                FilterCriteria(**kwargs)

    def test_aller_retour_dict(self):
        c = FilterCriteria(min_rating=4.0, max_reviews=150, website=WEBSITE_WITHOUT, require_email=True)
        self.assertEqual(FilterCriteria.from_dict(c.to_dict()), c)

    def test_from_dict_tolerant(self):
        self.assertEqual(FilterCriteria.from_dict(None), FilterCriteria())
        self.assertEqual(FilterCriteria.from_dict({"cle_obsolete": 1, "min_reviews": 3}).min_reviews, 3)

    def test_summary_ne_montre_que_les_criteres_actifs(self):
        self.assertEqual(FilterCriteria(exclude_closed=False).summary(), "note 3–5")
        s = FilterCriteria(min_reviews=5, website=WEBSITE_WITHOUT, require_email=True).summary()
        self.assertIn("avis 5–∞", s)
        self.assertIn("sans site", s)
        self.assertIn("email obligatoire", s)


class TestRawExclusion(unittest.TestCase):
    """Critères appliqués au résultat brut Google Maps, avant Place Details."""

    def test_par_defaut_un_resultat_normal_passe(self):
        self.assertIsNone(raw_exclusion_reason(_raw(), FilterCriteria()))

    def test_note(self):
        c = FilterCriteria(min_rating=3.5, max_rating=4.5)
        self.assertEqual(raw_exclusion_reason(_raw(rating=3.0), c), "note < 3.5")
        self.assertEqual(raw_exclusion_reason(_raw(rating=4.9), c), "note > 4.5")
        self.assertIsNone(raw_exclusion_reason(_raw(rating=None), c))  # fiche sans note : gardée

    def test_nombre_avis(self):
        c = FilterCriteria(min_reviews=5, max_reviews=100)
        self.assertEqual(raw_exclusion_reason(_raw(reviews=2), c), "moins de 5 avis")
        self.assertEqual(raw_exclusion_reason(_raw(reviews=500), c), "plus de 100 avis")
        self.assertIsNone(raw_exclusion_reason(_raw(reviews=50), c))
        self.assertEqual(raw_exclusion_reason({"rating": 4.0}, c), "moins de 5 avis")  # champ absent = 0

    def test_etablissement_ferme(self):
        closed = _raw(status="CLOSED_PERMANENTLY")
        self.assertEqual(raw_exclusion_reason(closed, FilterCriteria()), "établissement fermé")
        self.assertIsNone(raw_exclusion_reason(closed, FilterCriteria(exclude_closed=False)))
        self.assertIsNone(raw_exclusion_reason(_raw(status=None), FilterCriteria()))  # statut inconnu : gardé


class TestProspectExclusion(unittest.TestCase):

    def test_site_web(self):
        with_site, no_site = _p("a"), _p("b", website=None)
        self.assertEqual(prospect_exclusion_reason(with_site, FilterCriteria(website=WEBSITE_WITHOUT)), "a déjà un site")
        self.assertIsNone(prospect_exclusion_reason(no_site, FilterCriteria(website=WEBSITE_WITHOUT)))
        self.assertEqual(prospect_exclusion_reason(no_site, FilterCriteria(website=WEBSITE_WITH)), "pas de site")

    def test_telephone(self):
        fixe, mobile, aucun = _p(), _p(phone="06 00 00 00 00"), _p(phone=None)
        self.assertIsNone(prospect_exclusion_reason(fixe, FilterCriteria(phone=PHONE_REQUIRED)))
        self.assertEqual(prospect_exclusion_reason(aucun, FilterCriteria(phone=PHONE_REQUIRED)), "pas de téléphone")
        self.assertEqual(prospect_exclusion_reason(fixe, FilterCriteria(phone=PHONE_MOBILE)), "pas de mobile")
        self.assertIsNone(prospect_exclusion_reason(mobile, FilterCriteria(phone=PHONE_MOBILE)))

    def test_email_obligatoire_apres_analyse(self):
        c = FilterCriteria(require_email=True)
        self.assertEqual(post_analysis_reason(_p(), c), "pas d'email trouvé")
        self.assertIsNone(post_analysis_reason(_p(email="a@b.fr"), c))
        self.assertIsNone(post_analysis_reason(_p(), FilterCriteria()))


class TestHelpers(unittest.TestCase):

    def test_is_mobile(self):
        self.assertTrue(is_mobile("06 12 34 56 78"))
        self.assertTrue(is_mobile("+33 7 12 34 56 78"))
        self.assertFalse(is_mobile("04 78 00 00 00"))
        self.assertFalse(is_mobile(None))

    def test_parse_locations(self):
        self.assertEqual(
            parse_locations("Lyon, France\n\n Bron ; Lyon, France\nVilleurbanne"),
            ["Lyon, France", "Bron", "Villeurbanne"],
        )

    def test_count_et_format(self):
        counter: dict = {}
        self.assertFalse(count_reason(counter, None))
        self.assertTrue(count_reason(counter, "pas de site"))
        self.assertTrue(count_reason(counter, "pas de site"))
        self.assertEqual(format_exclusions(counter), "2 pas de site")

    def test_merge_keywords(self):
        self.assertEqual(
            merge_keywords(["Cuisiniste", " ", "plombier"], ["cuisiniste", "Pisciniste"]),
            ["Cuisiniste", "plombier", "Pisciniste"],
        )


class TestNouveauxSegments(unittest.TestCase):

    def test_cuisinistes_et_piscinistes(self):
        self.assertIn("cuisiniste", get_target("cuisinistes").keywords)
        self.assertIn("pisciniste", get_target("piscinistes").keywords)
        self.assertEqual(get_target("cuisinistes").sector, "habitat")

    def test_pas_de_mot_cle_en_double_dans_un_segment(self):
        for t in TARGET_SEGMENTS:
            kws = [k.lower() for k in t.keywords]
            self.assertEqual(len(kws), len(set(kws)), f"Doublon dans {t.id}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
