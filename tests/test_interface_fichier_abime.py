"""
Fichier des contacts abîmé : l'interface affiche un message clair au lieu de planter.
"""

import os
import re

import pytest

import history_manager

PAGES = {
    "page_relances": "relances",
    "page_statistiques": "statistiques",
    "page_reglages": "reglages",
}


def _open_page(page_func: str):
    from streamlit.testing.v1 import AppTest
    root = os.path.join(os.path.dirname(__file__), "..")
    src = open(os.path.join(root, "app.py"), encoding="utf-8").read()
    src = src.replace('url_path="ma-journee", default=True)', 'url_path="ma-journee")')
    src, n = re.subn(rf"(st\.Page\({page_func},[^)]*?)\)", r"\1, default=True)", src, count=1)
    assert n == 1, f"{page_func} introuvable dans la navigation"
    path = os.path.join(root, f"_apptest_abime_{page_func}.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        return AppTest.from_file(path, default_timeout=60).run()
    finally:
        os.remove(path)


@pytest.mark.parametrize("page_func", list(PAGES))
def test_contacts_abimes_message_clair_sans_plantage(page_func):
    os.makedirs("output", exist_ok=True)
    with open(history_manager.CONTACTED_FILE, "w", encoding="utf-8") as f:
        f.write('{"p_1": {"name": ')          # JSON tronqué, aucune copie de secours

    at = _open_page(page_func)

    assert not at.exception
    assert any("MANUEL.md" in e.value for e in at.error)
