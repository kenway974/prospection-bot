"""
tests/test_analyzer.py — Tests unitaires du module analyzer.

Teste chaque check individuellement sans faire de vraies requêtes HTTP.
Les réponses HTTP sont simulées avec unittest.mock.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from services.analyzer import (
    _check_https,
    _check_viewport,
    _check_title,
    _check_meta_description,
    _check_tracking,
    _check_lead_form,
    _check_free_builder,
    _check_social_links,
    _check_response_time,
    _scrape_email,
    analyze_prospect,
    SLOW_RESPONSE_THRESHOLD_S,
    CRITICAL_WEIGHT,
    MAJOR_WEIGHT,
    MINOR_WEIGHT,
)
from services.google_maps import Prospect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_prospect(website="https://example.com", name="Test SARL") -> Prospect:
    return Prospect(
        place_id="test_id",
        name=name,
        address="1 rue Test, 75001 Paris",
        phone="01 23 45 67 89",
        website=website,
        rating=4.0,
        user_ratings_total=50,
        keyword="test",
    )


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# ---------------------------------------------------------------------------
# Tests des checks individuels
# ---------------------------------------------------------------------------

class TestCheckHttps(unittest.TestCase):

    def test_http_detecte(self):
        issues = []
        _check_https("http://example.com", issues)
        self.assertEqual(len(issues), 1)
        self.assertIn("HTTPS", issues[0][0])
        self.assertEqual(issues[0][1], CRITICAL_WEIGHT)

    def test_https_ok(self):
        issues = []
        _check_https("https://example.com", issues)
        self.assertEqual(len(issues), 0)


class TestCheckResponseTime(unittest.TestCase):

    def test_lent_detecte(self):
        issues = []
        _check_response_time(SLOW_RESPONSE_THRESHOLD_S + 1, issues)
        self.assertEqual(len(issues), 1)
        self.assertIn("chargement", issues[0][0])
        self.assertEqual(issues[0][1], MAJOR_WEIGHT)

    def test_rapide_ok(self):
        issues = []
        _check_response_time(1.0, issues)
        self.assertEqual(len(issues), 0)


class TestCheckViewport(unittest.TestCase):

    def test_viewport_absent(self):
        soup = make_soup("<html><head></head><body></body></html>")
        issues = []
        _check_viewport(soup, issues)
        self.assertEqual(len(issues), 1)
        self.assertIn("viewport", issues[0][0])
        self.assertEqual(issues[0][1], CRITICAL_WEIGHT)

    def test_viewport_present(self):
        soup = make_soup('<html><head><meta name="viewport" content="width=device-width"/></head></html>')
        issues = []
        _check_viewport(soup, issues)
        self.assertEqual(len(issues), 0)


class TestCheckTitle(unittest.TestCase):

    def test_title_absent(self):
        soup = make_soup("<html><head></head></html>")
        issues = []
        _check_title(soup, issues)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0][1], MAJOR_WEIGHT)

    def test_title_vide(self):
        soup = make_soup("<html><head><title>   </title></head></html>")
        issues = []
        _check_title(soup, issues)
        self.assertEqual(len(issues), 1)

    def test_title_present(self):
        soup = make_soup("<html><head><title>Mon super site</title></head></html>")
        issues = []
        _check_title(soup, issues)
        self.assertEqual(len(issues), 0)


class TestCheckMetaDescription(unittest.TestCase):

    def test_meta_desc_absente(self):
        soup = make_soup("<html><head></head></html>")
        issues = []
        _check_meta_description(soup, issues)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0][1], MINOR_WEIGHT)

    def test_meta_desc_presente(self):
        soup = make_soup('<html><head><meta name="description" content="Super description"/></head></html>')
        issues = []
        _check_meta_description(soup, issues)
        self.assertEqual(len(issues), 0)


class TestCheckTracking(unittest.TestCase):

    def test_tracking_absent(self):
        issues = []
        _check_tracking("<html><body>Bonjour</body></html>", issues)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0][1], CRITICAL_WEIGHT)

    def test_gtag_detecte(self):
        issues = []
        _check_tracking("gtag('config', 'UA-XXXXX')", issues)
        self.assertEqual(len(issues), 0)

    def test_fbq_detecte(self):
        issues = []
        _check_tracking("fbq('init', '123456')", issues)
        self.assertEqual(len(issues), 0)

    def test_gtm_detecte(self):
        issues = []
        _check_tracking("GTM-ABCDE", issues)
        self.assertEqual(len(issues), 0)


class TestCheckLeadForm(unittest.TestCase):

    def test_pas_de_formulaire(self):
        soup = make_soup("<html><body><p>Bonjour</p></body></html>")
        issues = []
        _check_lead_form(soup, issues)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0][1], CRITICAL_WEIGHT)

    def test_formulaire_present(self):
        soup = make_soup('<html><body><form><input type="text"/></form></body></html>')
        issues = []
        _check_lead_form(soup, issues)
        self.assertEqual(len(issues), 0)

    def test_input_email_suffit(self):
        soup = make_soup('<html><body><input type="email" placeholder="votre email"/></body></html>')
        issues = []
        _check_lead_form(soup, issues)
        self.assertEqual(len(issues), 0)


class TestCheckFreeBuilder(unittest.TestCase):

    def test_wix_detecte(self):
        issues = []
        _check_free_builder("https://monsite.wix.com", "", issues)
        self.assertEqual(len(issues), 1)
        self.assertIn("wix.com", issues[0][0])
        self.assertEqual(issues[0][1], MAJOR_WEIGHT)

    def test_wix_dans_html(self):
        issues = []
        _check_free_builder("https://example.com", "powered by wix.com", issues)
        self.assertEqual(len(issues), 1)

    def test_site_normal(self):
        issues = []
        _check_free_builder("https://example.com", "<html>normal site</html>", issues)
        self.assertEqual(len(issues), 0)


class TestCheckSocialLinks(unittest.TestCase):

    def test_pas_de_social(self):
        soup = make_soup("<html><body><a href='/contact'>Contact</a></body></html>")
        issues = []
        _check_social_links(soup, issues)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0][1], MINOR_WEIGHT)

    def test_facebook_detecte(self):
        soup = make_soup('<html><body><a href="https://facebook.com/mapage">FB</a></body></html>')
        issues = []
        _check_social_links(soup, issues)
        self.assertEqual(len(issues), 0)

    def test_instagram_detecte(self):
        soup = make_soup('<html><body><a href="https://instagram.com/moncompte">IG</a></body></html>')
        issues = []
        _check_social_links(soup, issues)
        self.assertEqual(len(issues), 0)


# ---------------------------------------------------------------------------
# Tests du scraping email
# ---------------------------------------------------------------------------

class TestScrapeEmail(unittest.TestCase):

    def test_mailto_detecte(self):
        soup = make_soup('<html><body><a href="mailto:contact@example.fr">Email</a></body></html>')
        email = _scrape_email("https://example.fr", soup)
        self.assertEqual(email, "contact@example.fr")

    def test_email_dans_texte(self):
        soup = make_soup("<html><body>Contactez-nous : info@maboite.fr</body></html>")
        email = _scrape_email("https://maboite.fr", soup)
        self.assertEqual(email, "info@maboite.fr")

    def test_email_blackliste_ignore(self):
        soup = make_soup('<html><body><a href="mailto:noreply@example.com">test</a></body></html>')
        email = _scrape_email("https://test.fr", soup)
        self.assertIsNone(email)

    def test_pas_email(self):
        soup = make_soup("<html><body>Aucune info de contact.</body></html>")
        email = _scrape_email("https://test.fr", soup)
        self.assertIsNone(email)


# ---------------------------------------------------------------------------
# Tests du workflow analyze_prospect
# ---------------------------------------------------------------------------

class TestAnalyzeProspect(unittest.TestCase):

    def test_prospect_sans_site(self):
        p = make_prospect(website=None)
        result = analyze_prospect(p)
        self.assertEqual(result.score, 0)
        self.assertEqual(len(result.issues), 1)
        self.assertIn("Pas de site web", result.issues[0])

    def test_prospect_site_inaccessible(self):
        p = make_prospect(website="https://site-down-xyz-123.fr")
        with patch("services.analyzer._fetch", return_value=(None, 0.0)):
            result = analyze_prospect(p)
        self.assertEqual(result.score, 5)
        self.assertIn("inaccessible", result.issues[0])

    def test_score_calcule_correctement(self):
        """Un site parfait (0 problème) doit avoir un score de 100."""
        html = """
        <html>
        <head>
            <title>Mon site parfait</title>
            <meta name="description" content="Super description"/>
            <meta name="viewport" content="width=device-width"/>
        </head>
        <body>
            <form><input type="email"/></form>
            <script>gtag('config', 'UA-XXXXX')</script>
            <a href="https://facebook.com/page">FB</a>
        </body>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.ok = True

        p = make_prospect(website="https://mon-site-parfait.fr")
        with patch("services.analyzer._fetch", return_value=(mock_resp, 0.5)):
            result = analyze_prospect(p)

        self.assertEqual(result.score, 100)
        self.assertEqual(len(result.issues), 0)

    def test_score_diminue_avec_problemes(self):
        """Les problèmes détectés réduisent le score selon leur poids (critique/important/mineur)."""
        html = "<html><head></head><body></body></html>"  # Plein de problèmes
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.ok = True

        p = make_prospect(website="https://mauvais-site.fr")
        with patch("services.analyzer._fetch", return_value=(mock_resp, 0.5)):
            result = analyze_prospect(p)

        self.assertLess(result.score, 100)
        self.assertGreater(len(result.issues), 0)

    def test_score_ponderation_critique_plus_fort(self):
        """Un site avec des problèmes critiques doit avoir un score plus bas qu'un site avec des problèmes mineurs."""
        # Site avec seulement des problèmes mineurs (meta desc + social)
        html_mineur = """
        <html>
        <head>
            <title>Mon site</title>
            <meta name="viewport" content="width=device-width"/>
        </head>
        <body>
            <form><input type="email"/></form>
            <script>gtag('config', 'UA-XXXXX')</script>
        </body>
        </html>
        """
        # Site avec seulement un problème critique (pas de tracking)
        html_critique = """
        <html>
        <head>
            <title>Mon site</title>
            <meta name="description" content="Description"/>
            <meta name="viewport" content="width=device-width"/>
        </head>
        <body>
            <form><input type="email"/></form>
            <a href="https://facebook.com/page">FB</a>
        </body>
        </html>
        """
        mock_mineur = MagicMock()
        mock_mineur.text = html_mineur
        mock_critique = MagicMock()
        mock_critique.text = html_critique

        p1 = make_prospect(website="https://site-mineur.fr")
        p2 = make_prospect(website="https://site-critique.fr")

        with patch("services.analyzer._fetch", return_value=(mock_mineur, 0.5)):
            result_mineur = analyze_prospect(p1)
        with patch("services.analyzer._fetch", return_value=(mock_critique, 0.5)):
            result_critique = analyze_prospect(p2)

        self.assertLess(result_critique.score, result_mineur.score)


if __name__ == "__main__":
    unittest.main(verbosity=2)
