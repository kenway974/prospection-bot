"""
tests/test_mail_contract.py — Contrat entre l'analyse du site et la phrase d'accroche du mail.

mailer.py choisit son accroche en cherchant des mots (« HTTPS », « viewport »…) dans les
messages de problème écrits par analyzer.py. Si quelqu'un reformule un message dans
analyzer.py, le mail changerait sans aucune erreur. Ces tests lancent le vrai analyseur
sur un vrai HTML et vérifient que l'accroche parle bien du bon sujet.
"""

import pytest

from services.analyzer import analyze_prospect
from services.google_maps import Prospect
from services.mailer import enrich_with_email

PERFECT = """<!doctype html><html><head><title>T</title>
<meta name="viewport" content="width=device-width"><meta name="description" content="d">
<script>gtag('config','G-1')</script></head><body><form><input type="email"></form>
<a href="https://facebook.com/x">fb</a><footer>© 2026</footer></body></html>"""


def site(**removed):
    """Un site parfait auquel on retire une seule chose."""
    html = PERFECT
    for needle in removed.values():
        html = html.replace(needle, "")
    return html


CASES = [
    # (description, url, html, mot attendu dans l'accroche)
    ("HTTPS manquant", "http://x.fr", PERFECT, "HTTP"),
    ("viewport manquant", "https://x.fr",
     PERFECT.replace('<meta name="viewport" content="width=device-width">', ""), "smartphone"),
    ("formulaire manquant", "https://x.fr",
     PERFECT.replace('<form><input type="email"></form>', ""), "formulaire"),
    ("tracking manquant", "https://x.fr",
     PERFECT.replace("<script>gtag('config','G-1')</script>", ""), "mesure"),
]


@pytest.mark.parametrize("label,url,html,expected", CASES, ids=[c[0] for c in CASES])
def test_l_accroche_parle_du_probleme_detecte(web, label, url, html, expected):
    web.sites[url] = html
    p = Prospect(place_id="p", name="Chez Test", address="a", phone=None, website=url,
                 rating=4.0, user_ratings_total=1, keyword="k")

    analyze_prospect(p)
    enrich_with_email(p)

    assert len(p.issues) == 1, f"{label} : un seul problème attendu, trouvé {p.issues}"
    assert expected in p.email_draft


def test_un_site_parfait_n_a_aucun_probleme(web):
    web.sites["https://x.fr"] = PERFECT
    p = Prospect(place_id="p", name="Chez Test", address="a", phone=None, website="https://x.fr",
                 rating=4.0, user_ratings_total=1, keyword="k")
    analyze_prospect(p)
    assert p.issues == [] and p.score == 100
