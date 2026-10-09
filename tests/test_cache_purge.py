"""
Cache d'analyse : les entrées périmées sont supprimées, le fichier ne grossit pas sans fin.
"""

import time

from services import cache


def test_une_entree_perimee_est_supprimee_a_l_ecriture(monkeypatch):
    cache.set_ttl(30)
    vieux = time.time() - 31 * 86_400
    with monkeypatch.context() as m:
        m.setattr(cache.time, "time", lambda: vieux)
        cache.set_cached("https://ancien.fr", [], 50, None)

    cache.set_cached("https://recent.fr", [], 80, None)

    assert cache.count() == 1
    assert cache.get_cached("https://recent.fr")["score"] == 80


def test_une_entree_encore_valide_est_gardee():
    cache.set_ttl(30)
    cache.set_cached("https://a.fr", [], 50, None)
    cache.set_cached("https://b.fr", [], 60, None)

    assert cache.count() == 2
