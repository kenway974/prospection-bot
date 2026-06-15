"""
tests/test_service_profiles.py — Tests unitaires des ServiceProfiles et TargetSegments.

Vérifie que tous les profils de service et segments de cible sont valides.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from service_profiles import SERVICE_PROFILES, ServiceProfile, get_service, list_services, SERVICE_CATEGORY_LABELS
from target_segments import TARGET_SEGMENTS, TargetSegment, get_target, list_targets, TARGET_SECTOR_LABELS, SIZE_LABELS


# ---------------------------------------------------------------------------
# Tests des ServiceProfiles
# ---------------------------------------------------------------------------

class TestServiceProfiles(unittest.TestCase):

    def test_tous_ont_id(self):
        for s in SERVICE_PROFILES:
            self.assertTrue(s.id, f"ServiceProfile sans id : {s.name}")

    def test_tous_ont_nom(self):
        for s in SERVICE_PROFILES:
            self.assertTrue(s.name, f"ServiceProfile sans nom : {s.id}")

    def test_tous_ont_description(self):
        for s in SERVICE_PROFILES:
            self.assertTrue(s.description, f"ServiceProfile sans description : {s.id}")

    def test_tous_ont_your_title(self):
        for s in SERVICE_PROFILES:
            self.assertTrue(s.your_title, f"ServiceProfile sans your_title : {s.id}")

    def test_tous_ont_your_offer(self):
        for s in SERVICE_PROFILES:
            self.assertTrue(s.your_offer, f"ServiceProfile sans your_offer : {s.id}")

    def test_email_hook_contient_name(self):
        """Le hook email doit contenir {name} pour la personnalisation."""
        for s in SERVICE_PROFILES:
            self.assertIn(
                "{name}", s.email_hook,
                f"email_hook sans {{name}} pour {s.name}"
            )

    def test_sms_max_160(self):
        """Le SMS ne doit pas dépasser 160 caractères."""
        for s in SERVICE_PROFILES:
            self.assertLessEqual(
                len(s.sms_hook), 160,
                f"SMS trop long pour {s.name} : {len(s.sms_hook)} chars"
            )

    def test_ids_uniques(self):
        ids = [s.id for s in SERVICE_PROFILES]
        self.assertEqual(len(ids), len(set(ids)), "Des ServiceProfiles ont des ids en doublon")

    def test_categories_valides(self):
        """Chaque service doit appartenir à une catégorie connue."""
        for s in SERVICE_PROFILES:
            self.assertIn(
                s.category, SERVICE_CATEGORY_LABELS,
                f"Catégorie inconnue '{s.category}' pour {s.name}"
            )

    def test_score_direction_valide(self):
        for s in SERVICE_PROFILES:
            self.assertIn(
                s.score_direction, ("asc", "desc"),
                f"score_direction invalide pour {s.name} : {s.score_direction}"
            )

    def test_score_threshold_positif(self):
        for s in SERVICE_PROFILES:
            self.assertGreaterEqual(
                s.score_threshold_default, 0,
                f"score_threshold_default négatif pour {s.name}"
            )

    def test_get_service_existant(self):
        s = get_service("web_refonte")
        self.assertIsNotNone(s)
        self.assertEqual(s.id, "web_refonte")

    def test_get_service_inexistant(self):
        s = get_service("service_qui_nexiste_pas")
        self.assertIsNone(s)

    def test_list_services_retourne_tous(self):
        services = list_services()
        self.assertEqual(len(services), len(SERVICE_PROFILES))

    def test_minimum_services(self):
        self.assertGreaterEqual(len(SERVICE_PROFILES), 20, "Il devrait y avoir au moins 20 services")

    def test_toutes_categories_representees(self):
        """Chaque catégorie doit avoir au moins un service."""
        cats_presentes = {s.category for s in SERVICE_PROFILES}
        for cat in SERVICE_CATEGORY_LABELS:
            self.assertIn(cat, cats_presentes, f"Catégorie '{cat}' sans aucun service")

    def test_coursier_score_direction_desc(self):
        """Le coursier doit avoir score_direction='desc' (logique inversée)."""
        coursier = get_service("coursier")
        self.assertIsNotNone(coursier)
        self.assertEqual(coursier.score_direction, "desc")

    def test_sms_non_vide(self):
        for s in SERVICE_PROFILES:
            self.assertTrue(s.sms_hook.strip(), f"SMS vide pour {s.name}")

    def test_email_hook_non_vide(self):
        for s in SERVICE_PROFILES:
            self.assertTrue(s.email_hook.strip(), f"email_hook vide pour {s.name}")


# ---------------------------------------------------------------------------
# Tests des TargetSegments
# ---------------------------------------------------------------------------

class TestTargetSegments(unittest.TestCase):

    def test_tous_ont_id(self):
        for t in TARGET_SEGMENTS:
            self.assertTrue(t.id, f"TargetSegment sans id : {t.name}")

    def test_tous_ont_nom(self):
        for t in TARGET_SEGMENTS:
            self.assertTrue(t.name, f"TargetSegment sans nom : {t.id}")

    def test_tous_ont_keywords(self):
        for t in TARGET_SEGMENTS:
            self.assertTrue(
                any(k.strip() for k in t.keywords),
                f"TargetSegment sans mots-clés : {t.name}"
            )

    def test_tous_ont_description(self):
        for t in TARGET_SEGMENTS:
            self.assertTrue(t.description, f"TargetSegment sans description : {t.id}")

    def test_target_size_valide(self):
        valid_sizes = {"tpe", "pme", "all"}
        for t in TARGET_SEGMENTS:
            self.assertIn(
                t.target_size, valid_sizes,
                f"target_size invalide pour {t.name} : {t.target_size}"
            )

    def test_secteurs_valides(self):
        """Chaque segment doit appartenir à un secteur connu."""
        for t in TARGET_SEGMENTS:
            self.assertIn(
                t.sector, TARGET_SECTOR_LABELS,
                f"Secteur inconnu '{t.sector}' pour {t.name}"
            )

    def test_ids_uniques(self):
        ids = [t.id for t in TARGET_SEGMENTS]
        self.assertEqual(len(ids), len(set(ids)), "Des TargetSegments ont des ids en doublon")

    def test_get_target_existant(self):
        t = get_target("restaurants")
        self.assertIsNotNone(t)
        self.assertEqual(t.id, "restaurants")

    def test_get_target_inexistant(self):
        t = get_target("cible_qui_nexiste_pas")
        self.assertIsNone(t)

    def test_list_targets_retourne_tous(self):
        targets = list_targets()
        self.assertEqual(len(targets), len(TARGET_SEGMENTS))

    def test_minimum_segments(self):
        self.assertGreaterEqual(len(TARGET_SEGMENTS), 20, "Il devrait y avoir au moins 20 segments cibles")

    def test_tous_secteurs_representes(self):
        """Chaque secteur doit avoir au moins un segment."""
        secteurs_presents = {t.sector for t in TARGET_SEGMENTS}
        for sector in TARGET_SECTOR_LABELS:
            self.assertIn(sector, secteurs_presents, f"Secteur '{sector}' sans aucun segment")

    def test_radius_positif(self):
        for t in TARGET_SEGMENTS:
            self.assertGreater(t.radius, 0, f"radius invalide pour {t.name}")

    def test_max_results_positif(self):
        for t in TARGET_SEGMENTS:
            self.assertGreater(t.max_results, 0, f"max_results invalide pour {t.name}")

    def test_size_labels_complet(self):
        """SIZE_LABELS doit couvrir toutes les valeurs de target_size utilisées."""
        for t in TARGET_SEGMENTS:
            self.assertIn(
                t.target_size, SIZE_LABELS,
                f"SIZE_LABELS manquant pour target_size='{t.target_size}' ({t.name})"
            )

    def test_restaurants_secteur_food(self):
        t = get_target("restaurants")
        self.assertIsNotNone(t)
        self.assertEqual(t.sector, "food")

    def test_keywords_sont_des_strings(self):
        for t in TARGET_SEGMENTS:
            for kw in t.keywords:
                self.assertIsInstance(kw, str, f"Keyword non-string dans {t.name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
