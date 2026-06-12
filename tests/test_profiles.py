"""
tests/test_profiles.py — Tests unitaires des profils et du profile_manager.

Vérifie que tous les profils prédéfinis sont valides
et que la sauvegarde/chargement des profils custom fonctionne.
"""

import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import patch
from profiles import PROFILES, Profile, get_profile, list_profiles
from profile_manager import save_custom_profile, load_custom_profiles, delete_custom_profile, get_all_profiles


# ---------------------------------------------------------------------------
# Tests des profils prédéfinis
# ---------------------------------------------------------------------------

class TestProfilesPredefinis(unittest.TestCase):

    def test_tous_les_profils_ont_un_id(self):
        for p in PROFILES:
            self.assertTrue(p.id, f"Profil sans id : {p.name}")

    def test_tous_les_profils_ont_un_nom(self):
        for p in PROFILES:
            self.assertTrue(p.name, f"Profil sans nom : {p.id}")

    def test_tous_les_profils_ont_des_keywords(self):
        for p in PROFILES:
            if p.id != "custom":
                self.assertTrue(
                    any(k.strip() for k in p.keywords),
                    f"Profil sans mots-clés : {p.name}"
                )

    def test_tous_les_profils_ont_une_accroche_email(self):
        for p in PROFILES:
            self.assertTrue(p.email_hook, f"Profil sans email_hook : {p.name}")

    def test_tous_les_profils_ont_une_accroche_sms(self):
        for p in PROFILES:
            self.assertTrue(p.sms_hook, f"Profil sans sms_hook : {p.name}")

    def test_sms_hook_max_160_chars(self):
        """Le SMS ne doit pas dépasser 160 caractères."""
        for p in PROFILES:
            self.assertLessEqual(
                len(p.sms_hook), 160,
                f"SMS trop long pour {p.name} : {len(p.sms_hook)} chars"
            )

    def test_email_hook_contient_placeholder_name(self):
        """Le hook email doit contenir {name} pour la personnalisation."""
        for p in PROFILES:
            if p.id != "custom":
                self.assertIn(
                    "{name}", p.email_hook,
                    f"email_hook sans {{name}} pour {p.name}"
                )

    def test_ids_uniques(self):
        ids = [p.id for p in PROFILES]
        self.assertEqual(len(ids), len(set(ids)), "Des profils ont des ids en doublon")

    def test_get_profile_existant(self):
        p = get_profile("web_tpe")
        self.assertIsNotNone(p)
        self.assertEqual(p.id, "web_tpe")

    def test_get_profile_inexistant(self):
        p = get_profile("profil_qui_nexiste_pas")
        self.assertIsNone(p)

    def test_list_profiles_retourne_tous(self):
        profiles = list_profiles()
        self.assertEqual(len(profiles), len(PROFILES))

    def test_profil_custom_existe(self):
        p = get_profile("custom")
        self.assertIsNotNone(p)

    def test_10_profils_minimum(self):
        self.assertGreaterEqual(len(PROFILES), 10, "Il devrait y avoir au moins 10 profils")

    def test_tous_les_profils_ont_une_category(self):
        for p in PROFILES:
            self.assertTrue(p.category, f"Profil sans category : {p.name}")

    def test_tous_les_profils_ont_un_target_size(self):
        valid_sizes = {"tpe", "pme", "all"}
        for p in PROFILES:
            self.assertIn(p.target_size, valid_sizes, f"target_size invalide pour {p.name}")


# ---------------------------------------------------------------------------
# Tests du profile_manager (sauvegarde/chargement)
# ---------------------------------------------------------------------------

class TestProfileManager(unittest.TestCase):

    def _make_test_profile(self, id="test_profil") -> Profile:
        return Profile(
            id=id,
            emoji="🧪",
            name="Profil Test",
            description="Profil créé pour les tests unitaires",
            keywords=["test", "unittest"],
            location="Paris, France",
            your_title="Testeur",
            your_offer="Tests automatisés",
            email_hook="Bonjour {name}, j'ai une offre de test.",
            sms_hook="Test SMS pour {name}.",
            qualification_criteria=["critère 1"],
        )

    def test_sauvegarde_et_chargement(self):
        """Un profil sauvegardé doit être rechargeable identiquement."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp_path = f.name

        with patch("profile_manager.CUSTOM_PROFILES_FILE", tmp_path):
            profile = self._make_test_profile()
            save_custom_profile(profile)
            loaded = load_custom_profiles()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, profile.id)
        self.assertEqual(loaded[0].name, profile.name)
        os.unlink(tmp_path)

    def test_mise_a_jour_profil_existant(self):
        """Sauvegarder un profil avec le même id doit le mettre à jour, pas le dupliquer."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp_path = f.name

        with patch("profile_manager.CUSTOM_PROFILES_FILE", tmp_path):
            p1 = self._make_test_profile()
            save_custom_profile(p1)

            p2 = self._make_test_profile()
            p2.name = "Profil Test Modifié"
            save_custom_profile(p2)

            loaded = load_custom_profiles()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].name, "Profil Test Modifié")
        os.unlink(tmp_path)

    def test_suppression_profil(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp_path = f.name

        with patch("profile_manager.CUSTOM_PROFILES_FILE", tmp_path):
            p = self._make_test_profile()
            save_custom_profile(p)
            delete_custom_profile(p.id)
            loaded = load_custom_profiles()

        self.assertEqual(len(loaded), 0)
        os.unlink(tmp_path)

    def test_fichier_inexistant_retourne_liste_vide(self):
        with patch("profile_manager.CUSTOM_PROFILES_FILE", "/tmp/fichier_inexistant_xyz.json"):
            loaded = load_custom_profiles()
        self.assertEqual(loaded, [])

    def test_get_all_profiles_inclut_predefinis(self):
        with patch("profile_manager.CUSTOM_PROFILES_FILE", "/tmp/fichier_inexistant_xyz.json"):
            all_profiles = get_all_profiles()
        self.assertEqual(len(all_profiles), len(PROFILES))

    def test_custom_ecrase_predefini_meme_id(self):
        """Un profil custom avec le même id qu'un prédéfini doit le remplacer."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp_path = f.name

        with patch("profile_manager.CUSTOM_PROFILES_FILE", tmp_path):
            p = self._make_test_profile(id="web_tpe")  # même id qu'un profil prédéfini
            p.name = "Mon Dev Web Custom"
            save_custom_profile(p)
            all_profiles = get_all_profiles()

        web_tpe_profiles = [x for x in all_profiles if x.id == "web_tpe"]
        self.assertEqual(len(web_tpe_profiles), 1)
        self.assertEqual(web_tpe_profiles[0].name, "Mon Dev Web Custom")
        os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
