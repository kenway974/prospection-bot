"""
tests/test_offers.py — Tests du moteur d'offres (offers.py).

Vérifie que le bot sélectionne UNE offre cohérente selon l'état web du prospect,
adapte le bénéfice au secteur, et n'affiche le prix que sur les offres d'appel.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from offers import select_offer, WIDGET_PRICE, SECTOR_BENEFITS
from services.google_maps import Prospect


def make_prospect(website="https://example.com", issues=None, issue_keys=None,
                  cms=None, score=70) -> Prospect:
    p = Prospect(
        place_id="test_id",
        name="Agence Test",
        address="1 rue Test, 97400 Saint-Denis",
        phone="06 92 12 34 56",
        website=website,
        rating=4.2,
        user_ratings_total=80,
        keyword="agence immobilière",
    )
    p.issues = issues or []
    p.issue_keys = issue_keys or []
    p.cms = cms
    p.score = score
    return p


class TestOfferSelection(unittest.TestCase):

    def test_pas_de_site_creation(self):
        p = make_prospect(website=None)
        offer = select_offer(p, sector="immo")
        self.assertEqual(offer.offer_type, "creation")
        # Pas de prix sur le cœur de marge
        self.assertNotIn("€", offer.cta)
        self.assertIn("maquette", offer.cta.lower())

    def test_wix_migration(self):
        p = make_prospect(cms="Wix")
        offer = select_offer(p, sector="immo")
        self.assertEqual(offer.offer_type, "migration")
        self.assertIn("Wix", offer.pitch)
        self.assertNotIn("€", offer.cta)

    def test_free_builder_key_migration(self):
        p = make_prospect(issue_keys=["free_builder"])
        offer = select_offer(p, sector="food")
        self.assertEqual(offer.offer_type, "migration")

    def test_site_vieux_refonte(self):
        p = make_prospect(issue_keys=["outdated"])
        offer = select_offer(p, sector="immo")
        self.assertEqual(offer.offer_type, "refonte")
        self.assertNotIn("€", offer.cta)

    def test_beaucoup_de_problemes_refonte(self):
        p = make_prospect(issues=["a", "b", "c", "d"], issue_keys=["title", "meta_description"])
        offer = select_offer(p, sector="immo")
        self.assertEqual(offer.offer_type, "refonte")

    def test_site_ok_sans_capture_widget(self):
        p = make_prospect(issue_keys=["lead_form"])
        offer = select_offer(p, sector="immo")
        self.assertEqual(offer.offer_type, "widget")
        # Le widget AFFICHE le prix (offre d'appel récurrente)
        self.assertIn("€", offer.cta)
        self.assertIn(WIDGET_PRICE, offer.cta)

    def test_site_correct_audit(self):
        p = make_prospect(issue_keys=[], issues=[])
        offer = select_offer(p, sector="immo")
        self.assertEqual(offer.offer_type, "audit")
        self.assertIn("gratuit", offer.cta.lower())

    def test_benefice_adapte_au_secteur(self):
        p = make_prospect(website=None)
        offer_immo = select_offer(p, sector="immo")
        offer_food = select_offer(p, sector="food")
        self.assertIn("estimation", offer_immo.pitch)
        self.assertIn("réservations", offer_food.pitch)
        self.assertNotEqual(offer_immo.pitch, offer_food.pitch)

    def test_secteur_inconnu_benefice_generique(self):
        p = make_prospect(website=None)
        offer = select_offer(p, sector="secteur_bidon")
        self.assertTrue(offer.pitch)  # ne crash pas, bénéfice générique

    def test_tous_les_secteurs_ont_un_benefice(self):
        # Garde-fou : chaque secteur de target_segments doit avoir un bénéfice
        from target_segments import TARGET_SECTOR_LABELS
        for sector in TARGET_SECTOR_LABELS:
            self.assertIn(sector, SECTOR_BENEFITS, f"Bénéfice manquant pour {sector}")


class TestOfferInEmail(unittest.TestCase):

    def test_offre_integree_email_web(self):
        from services.mailer import build_dynamic_email, EmailStyle
        p = make_prospect(cms="Wix", issue_keys=["free_builder"])
        email = build_dynamic_email(
            p, EmailStyle(), your_name="Moi", your_title="Dev Web",
            your_offer="generic", service_id="web_refonte",
            service_category="web_digital", target_sector="immo",
        )
        self.assertIn("estimation", email)  # bénéfice immo présent
        self.assertNotIn("generic", email)  # value_prop générique remplacée par l'offre


if __name__ == "__main__":
    unittest.main()
