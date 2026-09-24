"""
tests/test_email_check.py — Vérification des emails avant envoi.

Deux erreurs à éviter, aussi graves l'une que l'autre :
  - laisser partir une adresse morte (rebond → délivrabilité abîmée) ;
  - bloquer une adresse valide (prospect perdu).
Le DNS est simulé : les tests ne dépendent pas du réseau.
"""

import os
import sys
import unittest
from unittest.mock import patch

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : protège la vérification des emails avant envoi (services/email_check.py) :
# 📘   syntaxe, noreply, adresses factices/jetables, fautes de frappe (gmial → gmail),
# 📘   contrôle DNS du serveur mail (MX) simulé, cache par domaine, règles d'envoi.
# 📘 Appelé par : pytest / `python -m unittest` (pas inclus dans run_tests.py).
# 📘 Appelle : services/email_check.py, services/google_maps.py (Prospect), dnspython.
# 📘 Concepts Python à retenir ici : boucle de cas dans un test, side_effect=Exception
# 📘   (simuler une erreur), mock.call_count, assertFalse/assertTrue.
# 📘 DNS / MX : l'annuaire d'Internet ; l'enregistrement MX dit quel serveur reçoit les
# 📘   mails d'un domaine. Pas de MX = l'email risque de rebondir.

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import email_check as ec
from services.google_maps import Prospect

# 📘 Réponse DNS « tout va bien » réutilisée par plusieurs tests (tuple statut, raison).
MX_OK = (ec.STATUS_VALIDE, "serveur mail déclaré")


class TestSansReseau(unittest.TestCase):
    """Contrôles qui ne nécessitent aucun appel DNS."""

    def test_syntaxe(self):
        # 📘 Un test, plusieurs cas : repr(bad) en message permet de voir quelle adresse a
        # 📘   fait échouer (ex. '' vs '   '). use_dns=False → aucun appel réseau.
        # 💡 `with self.subTest(addr=bad):` dans la boucle ferait continuer le test après un
        # 💡   échec et listerait TOUS les cas cassés d'un coup (cf. test_pages_run.py).
        for bad in ["", "   ", "pasunemail", "a@", "@x.fr", "a@@x.fr", "a b@x.fr", "a@x", "a@x.f"]:
            self.assertEqual(ec.check_email(bad, use_dns=False).status, ec.STATUS_INVALIDE, repr(bad))

    def test_noreply(self):
        for addr in ["noreply@esn.fr", "no-reply@esn.fr", "ne-pas-repondre@esn.fr", "NoReply@ESN.fr"]:
            r = ec.check_email(addr, use_dns=False)
            self.assertEqual(r.status, ec.STATUS_INVALIDE, addr)

    def test_factices(self):
        for addr in ["contact@example.com", "test@esn.fr", "jean@domain.com", "x@sentry.io"]:
            self.assertEqual(ec.check_email(addr, use_dns=False).status, ec.STATUS_INVALIDE, addr)

    def test_faute_de_frappe_avec_suggestion(self):
        r = ec.check_email("jean.dupont@gmial.com", use_dns=False)
        self.assertEqual(r.status, ec.STATUS_INVALIDE)
        self.assertIn("gmail.com", r.reason)

    def test_jetable(self):
        self.assertEqual(ec.check_email("x@yopmail.com", use_dns=False).status, ec.STATUS_INVALIDE)

    def test_adresses_normales_acceptees(self):
        for addr in ["jean.dupont@esn-alpha.re", "contact@garage-payet.fr",
                     "Jean.Dupont+prospect@gmail.com", "k@orange.fr"]:
            r = ec.check_email(addr, use_dns=False)
            self.assertEqual(r.status, ec.STATUS_VALIDE, addr)

    def test_adresse_generique_signalee_mais_valide(self):
        r = ec.check_email("contact@esn.fr", use_dns=False)
        self.assertEqual(r.status, ec.STATUS_VALIDE)
        self.assertTrue(r.generic)
        self.assertFalse(ec.check_email("jean@esn.fr", use_dns=False).generic)


class TestDNS(unittest.TestCase):

    def setUp(self):
        ec._dns_cache.clear()

    def test_mx_present(self):
        with patch.object(ec, "_dns_lookup", return_value=MX_OK):
            self.assertEqual(ec.check_email("jean@esn.fr").status, ec.STATUS_VALIDE)

    def test_domaine_inexistant(self):
        with patch.object(ec, "_dns_lookup", return_value=(ec.STATUS_INVALIDE, "domaine inexistant")):
            r = ec.check_email("jean@esn-qui-nexiste-pas.fr")
        self.assertEqual(r.status, ec.STATUS_INVALIDE)
        self.assertFalse(r.sendable)

    def test_sans_mx_risque(self):
        with patch.object(ec, "_dns_lookup", return_value=(ec.STATUS_RISQUE, "pas de serveur mail")):
            self.assertEqual(ec.check_email("jean@esn.fr").status, ec.STATUS_RISQUE)

    def test_panne_reseau_ne_condamne_pas(self):
        """Un aléa réseau ne doit jamais faire classer une adresse « invalide »."""
        import dns.exception
        ec._dns_cache.clear()
        # 📘 side_effect=une exception : quand le faux est appelé, il LÈVE cette erreur.
        # 📘   Idéal pour simuler une panne (ici un timeout DNS) sans couper le réseau.
        with patch("dns.resolver.resolve", side_effect=dns.exception.Timeout()):
            r = ec.check_email("jean@esn-tout-a-fait-valide.fr")
        self.assertEqual(r.status, ec.STATUS_RISQUE)
        self.assertTrue(r.sendable)

    def test_nxdomain_reel(self):
        import dns.resolver
        ec._dns_cache.clear()
        with patch("dns.resolver.resolve", side_effect=dns.resolver.NXDOMAIN()):
            self.assertEqual(ec.check_email("a@zzz-inexistant.fr").status, ec.STATUS_INVALIDE)

    def test_noanswer_reel(self):
        import dns.resolver
        ec._dns_cache.clear()
        with patch("dns.resolver.resolve", side_effect=dns.resolver.NoAnswer()):
            self.assertEqual(ec.check_email("a@sans-mx.fr").status, ec.STATUS_RISQUE)

    def test_cache_par_domaine(self):
        import dns.resolver
        ec._dns_cache.clear()
        with patch("dns.resolver.resolve") as m:
            ec.check_email("a@meme-domaine.fr")
            ec.check_email("b@meme-domaine.fr")
        # 📘 call_count = nombre de fois où le faux a été appelé : 1 seul appel DNS pour
        # 📘   2 adresses du même domaine → le cache fonctionne.
        self.assertEqual(m.call_count, 1)

    def test_pas_de_dns_si_deja_invalide(self):
        with patch.object(ec, "_dns_lookup") as m:
            ec.check_email("noreply@esn.fr")
        m.assert_not_called()


class TestEnvoi(unittest.TestCase):

    def _p(self, email, status=""):
        p = Prospect("id_" + (email or "x"), "X", "", None, None, None, 0, "kw")
        p.email, p.email_status = email, status
        return p

    def test_regles_denvoi(self):
        self.assertTrue(ec.is_sendable(self._p("a@x.fr", ec.STATUS_VALIDE)))
        self.assertFalse(ec.is_sendable(self._p("a@x.fr", ec.STATUS_INVALIDE)))
        self.assertFalse(ec.is_sendable(self._p("a@x.fr", ec.STATUS_RISQUE)))
        self.assertTrue(ec.is_sendable(self._p("a@x.fr", ec.STATUS_RISQUE), allow_risky=True))
        self.assertFalse(ec.is_sendable(self._p(None)))

    def test_invalide_jamais_envoye_meme_avec_option(self):
        self.assertFalse(ec.is_sendable(self._p("a@x.fr", ec.STATUS_INVALIDE), allow_risky=True))

    def test_prospect_non_verifie_verifie_a_la_volee(self):
        self.assertFalse(ec.is_sendable(self._p("noreply@x.fr")))

    def test_check_prospects_compte_et_renseigne(self):
        ps = [self._p("jean@esn.fr"), self._p("noreply@esn.fr"), self._p(None)]
        logs = []
        with patch.object(ec, "_dns_lookup", return_value=MX_OK):
            counts = ec.check_prospects(ps, log=logs.append)
        self.assertEqual(counts, {"valide": 1, "risque": 0, "invalide": 1})
        self.assertEqual(ps[0].email_status, ec.STATUS_VALIDE)
        self.assertEqual(ps[1].email_status, ec.STATUS_INVALIDE)
        self.assertEqual(len(logs), 1)   # on ne logue que ce qui pose problème


if __name__ == "__main__":
    unittest.main(verbosity=2)
