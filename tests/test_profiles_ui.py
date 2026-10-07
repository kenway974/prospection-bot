"""
tests/test_profiles_ui.py — Les profils sauvegardés depuis l'interface doivent réapparaître.

Avant : « Sauvegarder le profil » écrivait profiles_custom.json, mais la liste déroulante
ne lisait que les profils prédéfinis : un profil sauvegardé n'était jamais retrouvé.
"""

import os

from streamlit.testing.v1 import AppTest

from profile_manager import save_custom_profile
from profiles import PROFILES, Profile

APP = os.path.join(os.path.dirname(__file__), "..", "app.py")


def custom(profile_id="mon_secteur", name="Mon Secteur Test"):
    return Profile(id=profile_id, emoji="🧪", name=name, description="d", keywords=["a", "b"],
                   location="Nantes, France", your_title="t", your_offer="o",
                   email_hook="Bonjour {name}", sms_hook="s", qualification_criteria=[])


def options():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    return list(at.selectbox[0].options)


def test_sans_profil_sauvegarde_on_a_les_profils_predefinis():
    assert len(options()) == len(PROFILES)


def test_un_profil_sauvegarde_apparait_dans_la_liste():
    save_custom_profile(custom())
    assert any("Mon Secteur Test" in o for o in options())


def test_un_profil_sauvegarde_peut_etre_selectionne_et_pre_remplit_la_zone():
    save_custom_profile(custom())
    at = AppTest.from_file(APP, default_timeout=30).run()
    label = next(o for o in at.selectbox[0].options if "Mon Secteur Test" in o)

    at.selectbox[0].select(label).run()

    assert not at.exception
    assert any("Nantes, France" in str(w.value) for w in at.text_input)


def test_un_profil_sauvegarde_avec_le_meme_id_qu_un_predefini_le_remplace():
    save_custom_profile(custom(profile_id="dev_web", name="Dev Web Version Perso"))
    opts = options()
    assert any("Dev Web Version Perso" in o for o in opts)
    assert not any(o.endswith("Dev Web / Freelance") for o in opts)
