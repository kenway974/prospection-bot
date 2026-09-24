"""
tests/test_linkedin.py — Prospection LinkedIn assistée.

Rien n'est envoyé automatiquement : on vérifie que les messages sont propres
(jamais de trou « Bonjour , »), que les longueurs respectent les limites
LinkedIn, que les modèles perso persistent, et que le suivi CRM s'enchaîne.
"""

import os
import sys
import tempfile
import unittest
from urllib.parse import unquote_plus

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : protège la prospection LinkedIn ASSISTÉE (services/linkedin.py + suivi dans
# 📘   crm_store.py) : rendu des modèles de message sans « trous », longueurs max LinkedIn,
# 📘   liens de recherche correctement encodés, modèles perso sauvegardés/réinitialisés,
# 📘   et prochaine action programmée après une invitation ou un message.
# 📘 Appelé par : pytest / `python -m unittest` (pas inclus dans run_tests.py).
# 📘 Appelle : services/linkedin.py, crm_store.py, services/google_maps.py, urllib.parse.
# 📘 Concepts Python à retenir ici : assertNotIn, assertLessEqual, `"x" * 301` (répétition
# 📘   de chaîne pour fabriquer un texte d'une longueur donnée), unquote_plus (décodage d'URL).

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import linkedin as L
import crm_store as cs
from services.google_maps import Prospect


class TestRendu(unittest.TestCase):

    def test_prenom_et_entreprise(self):
        t = L.render("Bonjour {prenom}, et {entreprise} ?", dirigeant="Jean Dupont", entreprise="ESN X")
        self.assertEqual(t, "Bonjour Jean, et ESN X ?")

    def test_sans_prenom_pas_de_trou(self):
        """« Bonjour , » serait immédiatement repéré comme un message automatique."""
        t = L.render(L.DEFAULT_TEMPLATES[L.TPL_NOTE_FREELANCE], entreprise="ESN X")
        self.assertTrue(t.startswith("Bonjour,"), t)
        self.assertNotIn("Bonjour ,", t)
        t2 = L.render(L.DEFAULT_TEMPLATES[L.TPL_MSG_FREELANCE], entreprise="ESN X", mon_nom="Kenny")
        self.assertTrue(t2.startswith("Merci pour la connexion !"), t2)  # typo française
        self.assertNotIn("connexion  !", t2)
        self.assertNotIn("connexion!", t2)

    def test_aucune_variable_non_remplie(self):
        for key, tpl in L.DEFAULT_TEMPLATES.items():
            t = L.render(tpl, dirigeant="Jean Dupont", entreprise="ESN X",
                         mon_nom="Kenny Pignolet", mon_titre="Dev", mon_site="https://k.dev")
            self.assertNotIn("{", t, key)

    def test_site_vide_sans_lignes_vides_en_trop(self):
        t = L.render(L.DEFAULT_TEMPLATES[L.TPL_MSG_SERVICE], entreprise="X", mon_nom="Kenny")
        self.assertNotIn("\n\n\n", t)
        self.assertFalse(t.endswith("\n"))


class TestLongueurs(unittest.TestCase):

    def test_notes_par_defaut_dans_la_zone_ideale(self):
        for key in (L.TPL_NOTE_FREELANCE, L.TPL_NOTE_SERVICE):
            t = L.render(L.DEFAULT_TEMPLATES[key], dirigeant="Jean Dupont", entreprise="ESN Alpha Réunion")
            self.assertLessEqual(len(t), L.NOTE_MAX_CHARS, key)
            self.assertEqual(L.note_verdict(t)[0], "ok", f"{key} : {len(t)} car.")

    def test_verdicts(self):
        self.assertEqual(L.note_verdict("x" * 301)[0], "error")
        self.assertEqual(L.note_verdict("x" * 150)[0], "ok")
        self.assertEqual(L.note_verdict("x" * 50)[0], "warn")
        self.assertEqual(L.note_verdict("x" * 250)[0], "warn")


class TestLiens(unittest.TestCase):

    def test_recherche_dirigeant(self):
        url = L.people_search_url("ESN Alpha", dirigeant="Jean Dupont")
        # 📘 Dans une URL, espaces et caractères spéciaux sont encodés (" " → "+", "&" → "%26").
        # 📘   unquote_plus fait l'inverse, pour comparer avec du texte lisible.
        self.assertTrue(url.startswith("https://www.linkedin.com/search/results/people/"))
        self.assertIn("Jean Dupont ESN Alpha", unquote_plus(url))

    def test_recherche_par_role(self):
        self.assertIn("CTO ESN Alpha", unquote_plus(L.people_search_url("ESN Alpha", role="CTO")))

    def test_caracteres_speciaux_encodes(self):
        url = L.people_search_url("Café & Co", dirigeant="Zoé")
        self.assertNotIn(" ", url)
        self.assertNotIn("&C", url)  # le & doit être encodé

    def test_templates_selon_mode(self):
        self.assertEqual(L.default_templates_for(True), (L.TPL_NOTE_FREELANCE, L.TPL_MSG_FREELANCE))
        self.assertEqual(L.default_templates_for(False), (L.TPL_NOTE_SERVICE, L.TPL_MSG_SERVICE))


class TestPersistanceEtSuivi(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = cs.DB_FILE
        cs.DB_FILE = os.path.join(self._tmp.name, "crm.db")
        cs.init_db()
        p = Prospect("p1", "ESN Alpha", "97400", None, None, None, 0, "ESN")
        cs.upsert_prospects([p])

    def tearDown(self):
        cs.DB_FILE = self._orig
        self._tmp.cleanup()

    def test_modele_perso_puis_reset(self):
        key = L.TPL_NOTE_FREELANCE
        self.assertEqual(L.get_template(key, cs.get_linkedin_templates()), L.DEFAULT_TEMPLATES[key])
        cs.set_linkedin_template(key, "Salut {prenom} !")
        self.assertEqual(L.get_template(key, cs.get_linkedin_templates()), "Salut {prenom} !")
        cs.reset_linkedin_template(key)
        self.assertEqual(L.get_template(key, cs.get_linkedin_templates()), L.DEFAULT_TEMPLATES[key])

    def test_modele_vide_ignore(self):
        cs.set_linkedin_template(L.TPL_MSG_SERVICE, "   ")
        self.assertEqual(L.get_template(L.TPL_MSG_SERVICE, cs.get_linkedin_templates()),
                         L.DEFAULT_TEMPLATES[L.TPL_MSG_SERVICE])

    def test_invitation_programme_la_verification(self):
        due = cs.mark_linkedin_sent("p1", "invitation")
        p = cs.get_prospect("p1")
        self.assertEqual(p["next_action"], cs.ACTION_LINKEDIN)
        self.assertEqual(due, cs.add_business_days(None, cs.LINKEDIN_ACCEPT_CHECK_DAYS))
        self.assertEqual(p["status"], cs.STATUS_CONTACTE)
        self.assertIn("linkedin", [e["kind"] for e in cs.get_events("p1")])

    def test_message_programme_une_relance(self):
        cs.mark_linkedin_sent("p1", "message")
        self.assertEqual(cs.get_prospect("p1")["next_action"], cs.ACTION_RELANCER)

    def test_type_inconnu(self):
        with self.assertRaises(ValueError):
            cs.mark_linkedin_sent("p1", "pigeon_voyageur")


if __name__ == "__main__":
    unittest.main(verbosity=2)
