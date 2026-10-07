"""
tests/fakes.py — Faux services externes pour les tests de comportement.

Tout le réseau est simulé : Google Places, les sites des prospects, Notion,
Brevo et le SMTP de Gmail. Aucun test ne touche Internet ni ne consomme de crédits.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests


def make_response(status: int = 200, body="", url: str = "https://example.test") -> requests.Response:
    """Fabrique un vrai objet requests.Response (json, text, raise_for_status, ok…)."""
    resp = requests.Response()
    resp.status_code = status
    resp.url = url
    resp.encoding = "utf-8"
    if isinstance(body, (dict, list)):
        resp._content = json.dumps(body).encode("utf-8")
    else:
        resp._content = str(body).encode("utf-8")
    return resp


class FakeWeb:
    """
    Remplace requests.get / requests.post.

    - places      : liste de dicts {place_id, name, address} renvoyés par la Text Search
    - details     : {place_id: dict de détails} renvoyés par Place Details
    - sites       : {url: html} ; une URL absente = site injoignable (ConnectionError)
    - slow_sites  : {url: secondes} → pas utilisé (le temps est mesuré, pas simulé)
    - notion_existing_names : noms déjà présents dans le CRM Notion
    """

    def __init__(self):
        self.places: Dict[str, List[dict]] = {}      # keyword → résultats Text Search
        self.details: Dict[str, dict] = {}
        self.sites: Dict[str, str] = {}
        self.notion_existing_names: set = set()
        self.notion_fail_create: bool = False
        self.brevo_status: int = 201
        self.calls: List[tuple] = []                 # (méthode, url)
        self.notion_created: List[dict] = []
        self.sms_sent: List[dict] = []

    # --- API de configuration des scénarios -------------------------------

    def add_place(self, keyword: str, place_id: str, name: str, *,
                  website: Optional[str] = None, phone: Optional[str] = "04 78 12 34 56",
                  rating: Optional[float] = 4.5, html: Optional[str] = None,
                  address: str = "1 rue Test, 69001 Lyon") -> None:
        self.places.setdefault(keyword, []).append(
            {"place_id": place_id, "name": name, "formatted_address": address}
        )
        det = {
            "name": name,
            "formatted_address": address,
            "formatted_phone_number": phone,
            "rating": rating,
            "user_ratings_total": 42,
            "url": f"https://maps.example/{place_id}",
        }
        if website:
            det["website"] = website
        self.details[place_id] = det
        if website and html is not None:
            self.sites[website] = html

    # --- Remplaçants de requests ------------------------------------------

    def get(self, url, params=None, **kwargs):
        self.calls.append(("GET", url))
        if "maps.googleapis.com/maps/api/place/textsearch" in url:
            query = (params or {}).get("query", "")
            for keyword, results in self.places.items():
                if query.startswith(keyword):
                    return make_response(200, {"status": "OK", "results": results})
            return make_response(200, {"status": "ZERO_RESULTS", "results": []})
        if "maps.googleapis.com/maps/api/place/details" in url:
            pid = (params or {}).get("place_id")
            return make_response(200, {"status": "OK", "result": self.details.get(pid, {})})
        # Site de prospect
        if url in self.sites:
            return make_response(200, self.sites[url], url=url)
        # Pages /contact inexistantes → 404 (ne lève pas)
        host = urlparse(url)
        base = f"{host.scheme}://{host.netloc}"
        if any(s.startswith(base) for s in self.sites):
            return make_response(404, "", url=url)
        raise requests.ConnectionError(f"site injoignable : {url}")

    def post(self, url, headers=None, json=None, **kwargs):  # noqa: A002 (nom imposé par requests)
        self.calls.append(("POST", url))
        if "api.notion.com" in url and url.endswith("/query"):
            name = (json or {}).get("filter", {}).get("title", {}).get("equals")
            results = [{"id": "x"}] if name in self.notion_existing_names else []
            return make_response(200, {"results": results})
        if "api.notion.com" in url and url.endswith("/pages"):
            if self.notion_fail_create:
                return make_response(400, {"message": "boom"})
            self.notion_created.append(json)
            return make_response(200, {"id": "page"})
        if "api.brevo.com" in url:
            self.sms_sent.append(json)
            return make_response(self.brevo_status, {"messageId": 1})
        raise AssertionError(f"POST inattendu : {url}")

    def install(self, monkeypatch) -> "FakeWeb":
        monkeypatch.setattr(requests, "get", self.get)
        monkeypatch.setattr(requests, "post", self.post)
        return self


class FakeSMTP:
    """Remplace smtplib.SMTP ; enregistre les messages envoyés dans FakeSMTP.sent."""

    sent: List[dict] = []
    fail_auth: bool = False
    fail_send_to: set = set()

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, user, password):
        import smtplib
        if FakeSMTP.fail_auth:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    def sendmail(self, from_addr, to_addr, raw):
        if to_addr in FakeSMTP.fail_send_to:
            raise OSError("SMTP down")
        import email
        msg = email.message_from_string(raw)
        payload = msg.get_payload(0).get_payload(decode=True).decode("utf-8")
        FakeSMTP.sent.append({
            "from": from_addr, "to": to_addr,
            "subject": msg["Subject"], "headers": dict(msg.items()), "body": payload,
        })

    @classmethod
    def reset(cls):
        cls.sent = []
        cls.fail_auth = False
        cls.fail_send_to = set()


# HTML de sites de test --------------------------------------------------------

GOOD_SITE = """<!doctype html><html><head><title>Boulangerie Dupont</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="La meilleure boulangerie">
<script>gtag('config','G-XXXX')</script></head><body>
<form><input type="email" name="mail"></form>
<a href="https://facebook.com/dupont">fb</a>
<footer>© 2026 Boulangerie Dupont</footer></body></html>"""

BAD_SITE = """<html><head></head><body><p>Bienvenue</p>
<a href="mailto:contact@vieux-garage.fr">Nous écrire</a>
<footer>© 2015 Vieux Garage</footer></body></html>"""

MID_SITE = """<!doctype html><html><head><title>Cabinet Martin</title>
<meta name="viewport" content="width=device-width"></head><body>
<form><input type="email"></form>
<footer>© 2026</footer></body></html>"""
