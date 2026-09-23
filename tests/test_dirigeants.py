"""
tests/test_dirigeants.py — Dirigeants via Sirène.

Le risque principal : attribuer le MAUVAIS dirigeant (« Bonjour Jean » au
mauvais Jean). Les tests de correspondance incertaine sont donc centraux.
Réponses API simulées selon le format documenté :
https://recherche-entreprises.api.gouv.fr/docs/
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import dirigeants as d
from services.google_maps import Prospect


def entry(name, dirigeants, siren="123456789"):
    return {"siren": siren, "nom_raison_sociale": name, "nom_complet": name, "dirigeants": dirigeants}


def pp(nom, prenoms, qualite):
    return {"nom": nom, "prenoms": prenoms, "qualite": qualite, "type_dirigeant": "personne physique"}


def pm(denomination, qualite="Président"):
    return {"denomination": denomination, "siren": "999", "qualite": qualite, "type_dirigeant": "personne morale"}


class TestExtraction(unittest.TestCase):

    def test_president_prioritaire(self):
        e = entry("ESN X", [pp("MARTIN", "Sophie", "Directeur général"),
                            pp("DUPONT", "Jean Marc", "Président de SAS")])
        self.assertEqual(d.extract_dirigeant(e), ("Jean Dupont", "Président"))

    def test_gerant(self):
        e = entry("Garage", [pp("PAYET", "Louis", "Gérant")])
        self.assertEqual(d.extract_dirigeant(e), ("Louis Payet", "Gérant"))

    def test_holding_ignoree(self):
        """Une holding présidente n'est pas une personne à qui écrire."""
        e = entry("ESN X", [pm("HOLDING DUPONT"), pp("DUPONT", "Jean", "Directeur général")])
        self.assertEqual(d.extract_dirigeant(e)[0], "Jean Dupont")

    def test_uniquement_holding(self):
        self.assertEqual(d.extract_dirigeant(entry("X", [pm("HOLDING")])), ("", ""))

    def test_aucun_dirigeant(self):
        self.assertEqual(d.extract_dirigeant(entry("X", [])), ("", ""))
        self.assertEqual(d.extract_dirigeant({"siren": "1"}), ("", ""))

    def test_formatage_noms_composes(self):
        self.assertEqual(d._format_person("Jean-Pierre Marc", "LE GOFF"), "Jean-Pierre Le Goff")
        self.assertEqual(d._format_person("Anne", "D'ARTAGNAN"), "Anne D'Artagnan")
        self.assertEqual(d._format_person("Marie", "GRONDIN-HOARAU"), "Marie Grondin-Hoarau")


class TestSimilarite(unittest.TestCase):

    def test_forme_juridique_ignoree(self):
        self.assertGreaterEqual(d.name_similarity("Garage Payet", "GARAGE PAYET SARL"), d.MATCH_THRESHOLD)

    def test_accents_et_casse(self):
        self.assertGreaterEqual(d.name_similarity("Boulangerie Hoarau", "BOULANGERIE HOARAU"), d.MATCH_THRESHOLD)

    def test_ordre_des_mots(self):
        self.assertGreaterEqual(d.name_similarity("Digital ESN Réunion", "ESN REUNION DIGITAL"), d.MATCH_THRESHOLD)

    def test_nom_generique_refuse(self):
        """« Garage » seul ne doit pas s'attribuer le dirigeant de « Garage Dupont »."""
        for court, long_ in [("Garage", "GARAGE DUPONT"), ("Boulangerie", "BOULANGERIE HOARAU"),
                             ("Payet", "PAYET TRANSPORTS"),
                             ("Studio Web", "STUDIO WEB REUNION CONSEIL")]:
            self.assertLess(d.name_similarity(court, long_), d.MATCH_THRESHOLD, f"{court} ≈ {long_}")

    def test_variante_proche_acceptee(self):
        self.assertGreaterEqual(d.name_similarity("Garage Payet", "GARAGE PAYET ET FILS"), d.MATCH_THRESHOLD)

    def test_entreprises_differentes_rejetees(self):
        self.assertLess(d.name_similarity("Garage Payet", "Boulangerie Grondin"), d.MATCH_THRESHOLD)
        self.assertLess(d.name_similarity("Studio Web Péi", "Pharmacie du Centre"), d.MATCH_THRESHOLD)

    def test_code_postal(self):
        self.assertEqual(d.extract_postal_code("12 rue de Paris, 97400 Saint-Denis, La Réunion"), "97400")
        self.assertEqual(d.extract_postal_code("5 avenue X, 75011 Paris"), "75011")
        self.assertEqual(d.extract_postal_code("Adresse sans code"), "")


class TestRecherche(unittest.TestCase):

    def setUp(self):
        d._MIN_INTERVAL_S = 0  # pas d'attente en test

    def test_correspondance_sure_acceptee(self):
        api = [entry("GARAGE PAYET SARL", [pp("PAYET", "Louis", "Gérant")], siren="111")]
        with patch.object(d, "_search", return_value=api) as m:
            info = d.find_dirigeant("Garage Payet", "3 rue X, 97410 Saint-Pierre")
        m.assert_called_once_with("Garage Payet", "97410")
        self.assertEqual(info["dirigeant"], "Louis Payet")
        self.assertEqual(info["siren"], "111")

    def test_correspondance_incertaine_refusee(self):
        """Sirène renvoie une autre entreprise → on n'invente PAS de dirigeant."""
        api = [entry("BOULANGERIE GRONDIN", [pp("GRONDIN", "Paul", "Gérant")])]
        with patch.object(d, "_search", return_value=api):
            self.assertIsNone(d.find_dirigeant("Garage Payet", "97410 Saint-Pierre"))

    def test_meilleure_correspondance_choisie(self):
        api = [entry("PAYET TRANSPORTS", [pp("PAYET", "Marc", "Gérant")], siren="222"),
               entry("GARAGE PAYET", [pp("PAYET", "Louis", "Gérant")], siren="111")]
        with patch.object(d, "_search", return_value=api):
            self.assertEqual(d.find_dirigeant("Garage Payet")["dirigeant"], "Louis Payet")

    def test_api_indisponible(self):
        with patch.object(d, "_search", return_value=[]):
            self.assertIsNone(d.find_dirigeant("Garage Payet"))

    def test_nom_vide(self):
        self.assertIsNone(d.find_dirigeant(""))


class TestEnrichissement(unittest.TestCase):

    def setUp(self):
        d._MIN_INTERVAL_S = 0

    def _p(self, name, **kw):
        p = Prospect("id_" + name, name, "1 rue X, 97400 Saint-Denis", None, None, None, 0, "kw")
        for k, v in kw.items():
            setattr(p, k, v)
        return p

    def test_enrichit_et_compte(self):
        api = {"Garage Payet": {"siren": "1", "dirigeant": "Louis Payet", "qualite": "Gérant", "score": 1}}
        prospects = [self._p("Garage Payet"), self._p("Inconnu SARL")]
        with patch.object(d, "find_dirigeant", side_effect=lambda n, a="": api.get(n)):
            n = d.enrich_prospects(prospects)
        self.assertEqual(n, 1)
        self.assertEqual(prospects[0].dirigeant, "Louis Payet")
        self.assertEqual(prospects[0].siren, "1")
        self.assertEqual(prospects[1].dirigeant, "")

    def test_ne_reecrit_pas_un_dirigeant_connu(self):
        """Un prospect Sirène a déjà son dirigeant : pas d'appel inutile."""
        p = self._p("ESN X", dirigeant="Jean Dupont", dirigeant_qualite="Président")
        with patch.object(d, "find_dirigeant") as m:
            d.enrich_prospects([p])
        m.assert_not_called()
        self.assertEqual(p.dirigeant, "Jean Dupont")

    def test_serialisation(self):
        p = self._p("X", dirigeant="Jean Dupont", dirigeant_qualite="Président", siren="123")
        p2 = Prospect.from_dict(p.to_dict())
        self.assertEqual((p2.dirigeant, p2.dirigeant_qualite, p2.siren), ("Jean Dupont", "Président", "123"))



class TestIntegration(unittest.TestCase):
    """Garanties bout en bout : base CRM et salutation des emails."""

    def test_rescan_nefface_pas_le_dirigeant(self):
        import tempfile, crm_store as cs
        tmp = tempfile.TemporaryDirectory(); orig = cs.DB_FILE
        cs.DB_FILE = os.path.join(tmp.name, "crm.db")
        try:
            cs.init_db()
            p = Prospect("x", "Garage Payet", "97410", None, None, None, 0, "kw")
            p.dirigeant, p.dirigeant_qualite, p.siren = "Louis Payet", "Gérant", "111"
            cs.upsert_prospects([p])
            # Nouveau run où Sirène n'a rien trouvé cette fois
            p2 = Prospect("x", "Garage Payet", "97410", None, None, None, 0, "kw")
            cs.upsert_prospects([p2])
            row = cs.get_prospect("x")
            self.assertEqual((row["dirigeant"], row["dirigeant_qualite"], row["siren"]),
                             ("Louis Payet", "Gérant", "111"))
        finally:
            cs.DB_FILE = orig; tmp.cleanup()

    def _email(self, dirigeant, salutation):
        from services.mailer import build_dynamic_email, EmailStyle
        p = Prospect("x", "Garage Payet", "97410", None, "https://x.fr", None, 0, "kw")
        p.dirigeant = dirigeant
        return build_dynamic_email(p, EmailStyle(salutation=salutation), your_name="Kenny",
                                   your_title="Dev", your_offer="", service_category="web_digital")

    def test_salutation_avec_prenom(self):
        self.assertTrue(self._email("Louis Payet", "first_name").startswith("Bonjour Louis,"))

    def test_salutation_sans_dirigeant_ninvente_rien(self):
        self.assertTrue(self._email("", "first_name").startswith("Bonjour,"))

    def test_salutation_neutre_respectee(self):
        """Si l'utilisateur a choisi « Bonjour, », on n'impose pas le prénom."""
        self.assertTrue(self._email("Louis Payet", "neutral").startswith("Bonjour,"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
