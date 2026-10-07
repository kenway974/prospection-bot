"""
tests/test_app_config.py — Les valeurs saisies dans l'interface doivent être celles utilisées.

Dans app.py, la config est rechargée à chaque lancement. Ces tests vérifient que tous les
modules (mailer, SMS…) lisent bien les valeurs du formulaire, pas celles du .env de départ.
"""

from tests.test_app_pipeline import run


def test_la_signature_du_mail_utilise_les_champs_de_l_interface(web, app_module):
    web.add_place("boulangerie", "p_nosite", "Chez Zoé", website=None)

    result, _ = run(app_module, your_name="Nom Saisi Dans L UI", your_email="ui@example.com")

    assert "Nom Saisi Dans L UI" in result[0].email_draft
    assert "ui@example.com" in result[0].email_draft
    assert "Kenny" not in result[0].email_draft   # valeur de départ du .env / des tests


def test_la_cle_brevo_saisie_dans_l_interface_est_utilisee_pour_les_sms(web, app_module):
    web.add_place("boulangerie", "p_nosite", "Chez Zoé", website=None, phone="06 11 22 33 44")

    run(app_module, brevo_key="cle-brevo-ui", send_sms=True)

    assert len(web.sms_sent) == 1
