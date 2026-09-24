"""
tests/test_franchises.py — Exclusion des franchises.

Le risque n'est pas de rater une franchise : c'est d'exclure par erreur un
VRAI prospect indépendant. Les tests de faux positifs sont donc les plus
importants ici.
"""

import os
import sys
import unittest

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : protège la détection/exclusion des franchises et grandes enseignes
# 📘   (services/franchises.py) : vrais positifs, insensibilité casse/accents/tirets, et
# 📘   SURTOUT l'absence de faux positifs (ne jamais exclure un indépendant), la liste perso
# 📘   de l'utilisateur, le filtrage d'une liste et la normalisation des noms.
# 📘 Appelé par : pytest / `python -m unittest` (pas inclus dans run_tests.py).
# 📘 Appelle : services/franchises.py uniquement (tests 100 % hors réseau, sans mock).
# 📘 Concepts Python à retenir ici : dépaquetage de tuple `hit, brand = ...`, indexation
# 📘   [0] d'un tuple, classe minimale définie DANS un test (objet factice).

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.franchises import is_franchise, filter_franchises, _normalize


class TestDetection(unittest.TestCase):

    def test_franchises_evidentes(self):
        # 📘 is_franchise renvoie un TUPLE (trouvé?, marque) ; `hit, brand = ...` le « déballe »
        # 📘   dans deux variables. Plus bas, `is_franchise(...)[0]` prend seulement le 1er.
        for nom in [
            "Fitness Park Saint-Denis",
            "LAFORET IMMOBILIER",
            "Century 21 Agence du Port",
            "Agence Laforêt Sainte-Marie",
            "Basic-Fit Le Port",
            "McDonald's Saint-Pierre",
            "Orpi Immobilier Réunion",
            "Franck Provost Coiffure",
            "Optic 2000 Saint-Gilles",
            "Crédit Agricole agence de Saint-Leu",
            "Leroy Merlin Sainte-Clotilde",
        ]:
            hit, brand = is_franchise(nom)
            self.assertTrue(hit, f"non détecté : {nom}")

    def test_insensible_casse_et_accents(self):
        for variante in ["LAFORÊT", "laforet", "Laforêt", "LaForet"]:
            self.assertTrue(is_franchise(f"{variante} Immobilier")[0], variante)

    def test_ponctuation_et_tirets(self):
        self.assertTrue(is_franchise("Basic Fit")[0])
        self.assertTrue(is_franchise("Basic-Fit")[0])
        self.assertTrue(is_franchise("Jean-Louis David")[0])
        self.assertTrue(is_franchise("Jean Louis David")[0])


class TestFauxPositifs(unittest.TestCase):
    """Le plus important : ne JAMAIS exclure un indépendant."""

    def test_independants_conserves(self):
        for nom in [
            "Agence Immobilière du Lagon",
            "Boulangerie Chez Marcel",
            "Studio Créatif Péi",
            "Salon de coiffure Élégance",
            "Garage Payet et Fils",
            "Restaurant Le Vieux Port",
            "ESN Réunion Digital",
            "Cabinet Dupont Architecture",
            "Optique du Centre",
            "Pharmacie de la Plage",
        ]:
            hit, brand = is_franchise(nom)
            self.assertFalse(hit, f"faux positif : {nom} → détecté comme « {brand} »")

    def test_mots_ambigus_exacts_uniquement(self):
        """
        Compromis assumé : un faux positif coûte un client, un oubli coûte
        quelques secondes. Les noms ambigus ne matchent donc QU'à l'identique.
        """
        self.assertTrue(is_franchise("Paul")[0])              # la boulangerie Paul
        self.assertFalse(is_franchise("Paul Durand Immobilier")[0])  # indépendant ✅
        self.assertFalse(is_franchise("Cabinet Paul Martin")[0])
        self.assertFalse(is_franchise("Paul Saint-Denis")[0])  # faux négatif accepté

    def test_pas_de_match_sur_sous_chaine(self):
        """« ange » ne doit pas matcher dans « Angelo » ou « boulangerie »."""
        self.assertFalse(is_franchise("Angelo Pizzeria")[0])
        self.assertFalse(is_franchise("Boulangerie Angelique")[0])
        self.assertFalse(is_franchise("Orangerie du Sud")[0])

    def test_casino_le_vrai(self):
        self.assertFalse(is_franchise("Le Casino du Port")[0])
        self.assertTrue(is_franchise("Casino Supermarché")[0])


class TestListeUtilisateur(unittest.TestCase):

    def test_enseigne_ajoutee_par_lutilisateur(self):
        self.assertFalse(is_franchise("Ti Resto Péi")[0])
        hit, brand = is_franchise("Ti Resto Péi", extra=["Ti Resto"])
        self.assertTrue(hit)
        self.assertEqual(brand, "Ti Resto")

    def test_liste_utilisateur_insensible_accents(self):
        self.assertTrue(is_franchise("MAISON PEI Saint-Denis", extra=["maison péi"])[0])


class TestFiltrage(unittest.TestCase):

    def test_separe_gardes_et_exclus(self):
        # 📘 Faux prospect minimal : filter_franchises n'a besoin que d'un attribut .name,
        # 📘   inutile de construire un vrai Prospect complet (« duck typing »).
        class P:
            def __init__(self, name): self.name = name
        items = [P("Fitness Park"), P("Salle Muscu Péi"), P("Century 21 Nord"), P("Agence du Lagon")]
        kept, removed = filter_franchises(items)
        self.assertEqual([p.name for p in kept], ["Salle Muscu Péi", "Agence du Lagon"])
        self.assertEqual(len(removed), 2)
        self.assertEqual(removed[0][0], "Fitness Park")

    def test_liste_vide(self):
        kept, removed = filter_franchises([])
        self.assertEqual((kept, removed), ([], []))

    def test_nom_vide_conserve(self):
        class P:
            def __init__(self, name): self.name = name
        kept, removed = filter_franchises([P(""), P(None)])
        self.assertEqual(len(kept), 2)


class TestNormalisation(unittest.TestCase):

    def test_normalize(self):
        self.assertEqual(_normalize("Laforêt  IMMOBILIER !"), "laforet immobilier")
        self.assertEqual(_normalize("Coiff&Co"), "coiff&co")
        self.assertEqual(_normalize(""), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
