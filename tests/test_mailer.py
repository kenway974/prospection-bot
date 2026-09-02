"""
tests/test_mailer.py — Tests unitaires du module mailer.

Vérifie que les emails générés sont cohérents avec le diagnostic du prospect.
Aucune requête HTTP — tout est simulé.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from services.mailer import draft_email, _build_subject, _build_hook, _build_issues_block
from services.google_maps import Prospect


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_prospect(name="Boulangerie Test", website="https://example.com",
                  issues=None, score=70) -> Prospect:
    p = Prospect(
        place_id="test_id",
        name=name,
        address="1 rue Test, 69001 Lyon",
        phone="04 78 12 34 56",
        website=website,
        rating=4.2,
        user_ratings_total=80,
        keyword="boulangerie",
    )
    p.issues = issues or []
    p.score = score
    return p


# ---------------------------------------------------------------------------
# Tests du sujet
# ---------------------------------------------------------------------------

class TestBuildSubject(unittest.TestCase):

    def test_sujet_sans_site(self):
        p = make_prospect(website=None, issues=["Pas de site web référencé"], score=0)
        subject = _build_subject(p, 1)
        self.assertIn(p.name, subject)
        # Doit parler de présence en ligne, pas de "points d'amélioration"
        self.assertNotIn("points d'amélioration", subject)

    def test_sujet_1_probleme_singulier(self):
        p = make_prospect(issues=["Site sans HTTPS"], score=90)
        subject = _build_subject(p, 1)
        # Pas de "1 points" — doit être singulier
        self.assertNotIn("1 points", subject)
        self.assertIn(p.name, subject)

    def test_sujet_plusieurs_problemes(self):
        p = make_prospect(issues=["HTTPS", "viewport", "favicon"], score=70)
        subject = _build_subject(p, 3)
        self.assertIn("3", subject)
        self.assertIn(p.name, subject)

    def test_sujet_0_probleme(self):
        p = make_prospect(issues=[], score=100)
        subject = _build_subject(p, 0)
        self.assertIn(p.name, subject)
        self.assertNotIn("0", subject)


# ---------------------------------------------------------------------------
# Tests de l'accroche
# ---------------------------------------------------------------------------

class TestBuildHook(unittest.TestCase):

    def test_hook_sans_site(self):
        p = make_prospect(website=None, issues=["Pas de site web référencé"], score=0)
        hook = _build_hook(p)
        self.assertIn(p.name, hook)
        self.assertIn("site", hook.lower())

    def test_hook_https(self):
        p = make_prospect(issues=["Site sans HTTPS (connexion non sécurisée)"])
        hook = _build_hook(p)
        self.assertIn("HTTP", hook)

    def test_hook_mobile(self):
        p = make_prospect(issues=["Absence de meta viewport → site probablement non responsive (mobile)"])
        hook = _build_hook(p)
        self.assertIn("mobile", hook.lower())

    def test_hook_formulaire(self):
        p = make_prospect(issues=["Aucun formulaire de contact / capture de lead visible"])
        hook = _build_hook(p)
        self.assertIn("formulaire", hook.lower())

    def test_hook_tracking(self):
        p = make_prospect(issues=["Aucun pixel de tracking détecté"])
        hook = _build_hook(p)
        self.assertIn("mesure", hook.lower())

    def test_hook_custom_via_env(self):
        """Si EMAIL_HOOK est défini dans l'env, il doit être utilisé en priorité."""
        os.environ["EMAIL_HOOK"] = "Bonjour, j'ai une offre pour {name}."
        p = make_prospect(issues=["Site sans HTTPS"])
        hook = _build_hook(p)
        self.assertIn(p.name, hook)
        self.assertIn("Bonjour", hook)
        del os.environ["EMAIL_HOOK"]


# ---------------------------------------------------------------------------
# Tests du bloc problèmes
# ---------------------------------------------------------------------------

class TestBuildIssuesBlock(unittest.TestCase):

    def test_0_probleme(self):
        p = make_prospect(issues=[])
        block = _build_issues_block(p)
        self.assertEqual(block, "")

    def test_1_probleme_singulier(self):
        p = make_prospect(issues=["Site sans HTTPS → pénalité SEO"])
        block = _build_issues_block(p)
        self.assertIn("point", block.lower())
        # Pas de pluriel sur "1 point"
        self.assertNotIn("points", block.lower())

    def test_2_problemes(self):
        p = make_prospect(issues=["HTTPS", "viewport"])
        block = _build_issues_block(p)
        self.assertIn("•", block)

    def test_4_problemes_affiche_3_max(self):
        p = make_prospect(issues=["A", "B", "C", "D"])
        block = _build_issues_block(p)
        # Doit mentionner qu'il y en a d'autres
        self.assertIn("autre", block)


# ---------------------------------------------------------------------------
# Tests du mail complet
# ---------------------------------------------------------------------------

class TestDraftEmail(unittest.TestCase):

    def test_mail_contient_objet(self):
        p = make_prospect(issues=["Site sans HTTPS"])
        p.score = 90
        mail = draft_email(p)
        self.assertIn("OBJET", mail)

    def test_mail_contient_bonjour(self):
        p = make_prospect(issues=["Site sans HTTPS"])
        mail = draft_email(p)
        self.assertIn("Bonjour", mail)

    def test_mail_contient_nom_prospect(self):
        p = make_prospect(name="Garage Dupont", issues=["Site sans HTTPS"])
        mail = draft_email(p)
        self.assertIn("Garage Dupont", mail)

    def test_mail_sans_site_pas_de_liste_vide(self):
        """Quand il n'y a pas de site, le mail ne doit pas afficher 'Voici les 3 points'."""
        p = make_prospect(website=None, issues=["Pas de site web référencé"], score=0)
        mail = draft_email(p)
        self.assertNotIn("les 3 points", mail)

    def test_mail_1_probleme_coherent(self):
        """Avec 1 problème, le mail ne doit pas parler de '3 points'."""
        p = make_prospect(issues=["Site sans HTTPS → pénalité SEO"])
        p.score = 90
        mail = draft_email(p)
        self.assertNotIn("les 3 points", mail)
        self.assertNotIn("1 points", mail)

    def test_mail_different_selon_diagnostic(self):
        """Deux diagnostics différents doivent produire deux mails différents."""
        p1 = make_prospect(issues=["Site sans HTTPS"])
        p2 = make_prospect(issues=["Aucun formulaire de contact"])
        mail1 = draft_email(p1)
        mail2 = draft_email(p2)
        # Les accroches doivent être différentes
        self.assertNotEqual(mail1, mail2)

    def test_mail_score_eleve_cta_correction(self):
        """Score élevé (1 problème) → CTA 'correction rapide', pas 'audit complet'."""
        p = make_prospect(issues=["Absence de favicon"], score=90)
        mail = draft_email(p)
        self.assertNotIn("audit complet", mail.lower())

    def test_mail_score_bas_cta_audit(self):
        """Score bas (4+ problèmes) → CTA 'audit complet'."""
        p = make_prospect(
            issues=["HTTPS", "viewport", "favicon", "tracking", "formulaire"],
            score=50
        )
        mail = draft_email(p)
        self.assertIn("audit", mail.lower())


class TestFollowupSequence(unittest.TestCase):
    """Séquence de 4 relances à angles distincts + logique donner-d'abord."""

    def test_quatre_etapes_distinctes(self):
        from services.mailer import draft_followup_email, MAX_FOLLOWUPS
        self.assertEqual(MAX_FOLLOWUPS, 4)
        p = make_prospect()
        mails = [draft_followup_email(p, step=s) for s in range(1, 5)]
        # Les 4 relances ont des objets/contenus différents
        self.assertEqual(len(set(mails)), 4)
        # La dernière est une rupture
        self.assertIn("dernier message", mails[3].lower())

    def test_step_borne(self):
        from services.mailer import draft_followup_email
        p = make_prospect()
        # step hors bornes → ramené dans [1, 4]
        self.assertEqual(draft_followup_email(p, step=9), draft_followup_email(p, step=4))
        self.assertEqual(draft_followup_email(p, step=0), draft_followup_email(p, step=1))

    def test_donner_avant_recevoir(self):
        from services.mailer import draft_followup_email
        p = make_prospect()
        # Les relances proposent d'ENVOYER de la valeur, pas de caler un créneau
        for s in (1, 2, 3):
            mail = draft_followup_email(p, step=s).lower()
            self.assertIn("envoie", mail)


class TestReassurance(unittest.TestCase):
    def test_ligne_reassurance_presente(self):
        from services.mailer import build_dynamic_email, EmailStyle, REASSURANCE
        p = make_prospect()
        mail = build_dynamic_email(
            p, EmailStyle(intonation="professional", length="medium"),
            your_name="Moi", your_title="Dev", your_offer="",
            service_category="web_digital",
        )
        self.assertIn(REASSURANCE["professional"], mail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
