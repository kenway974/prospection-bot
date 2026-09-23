"""
services/email_check.py — Vérification des adresses avant envoi.

Pourquoi : au-delà d'environ 2 % de rebonds (emails non distribuables),
Gmail et les autres fournisseurs commencent à classer TES envois en spam. Une
adresse morte ne coûte pas qu'un mail perdu : elle abîme ta délivrabilité
pour tous les suivants.

Contrôles, du moins coûteux au plus coûteux :
  1. syntaxe ;
  2. adresses factices / « noreply » (inutile d'y écrire) ;
  3. fautes de frappe sur les grands fournisseurs (gmial.com…) ;
  4. domaines jetables (yopmail, mailinator…) ;
  5. DNS : le domaine existe-t-il et déclare-t-il un serveur mail (MX) ?

Volontairement NON fait : la sonde SMTP (« RCPT TO »). Elle est bloquée par
la plupart des hébergeurs (port 25 fermé sur Railway), peu fiable (serveurs
« catch-all ») et peut faire mettre ton IP sur liste noire.

Statuts :
  - valide      : syntaxe OK + serveur mail déclaré
  - risque      : domaine existant mais sans MX, ou DNS injoignable
  - invalide    : envoi voué à l'échec ou inutile → bloqué
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional

STATUS_VALIDE = "valide"
STATUS_RISQUE = "risque"
STATUS_INVALIDE = "invalide"

STATUS_BADGES: Dict[str, str] = {
    STATUS_VALIDE: "✅",
    STATUS_RISQUE: "⚠️",
    STATUS_INVALIDE: "❌",
}

_EMAIL_RE = re.compile(
    r"^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)

# Parties locales à qui écrire ne sert à rien (personne ne lit)
_NOREPLY_LOCAL = {
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply", "nepasrepondre",
    "ne-pas-repondre", "mailer-daemon", "postmaster", "bounce", "bounces",
}
_PLACEHOLDER_LOCAL = {"test", "exemple", "example", "email", "votre-email", "votremail", "xxx", "nom"}
_PLACEHOLDER_DOMAINS = {
    "example.com", "example.org", "example.net", "exemple.com", "exemple.fr",
    "domain.com", "domaine.com", "email.com", "test.com", "votresite.com",
    "yourdomain.com", "sentry.io", "wixpress.com",
}

# Adresses génériques : valides, mais ce n'est pas un décideur (info utile)
_GENERIC_LOCAL = {
    "contact", "info", "infos", "hello", "bonjour", "accueil", "admin", "office",
    "commercial", "direction", "secretariat", "service", "support", "sales", "team",
}

# Fautes de frappe fréquentes sur les grands fournisseurs → correction suggérée
_TYPOS: Dict[str, str] = {
    "gmial.com": "gmail.com", "gmal.com": "gmail.com", "gmaill.com": "gmail.com",
    "gamil.com": "gmail.com", "gmail.co": "gmail.com", "gmail.fr": "gmail.com",
    "gnail.com": "gmail.com", "gmail.cm": "gmail.com",
    "hotmial.com": "hotmail.com", "hotmal.com": "hotmail.com", "hotmail.fe": "hotmail.fr",
    "hotmai.fr": "hotmail.fr", "yahooo.fr": "yahoo.fr", "yaho.fr": "yahoo.fr",
    "yahoo.fe": "yahoo.fr", "orange.fe": "orange.fr", "oranje.fr": "orange.fr",
    "wanadoo.fe": "wanadoo.fr", "outlok.com": "outlook.com", "outlook.fe": "outlook.fr",
    "icloud.fr": "icloud.com", "live.fe": "live.fr", "laposte.fe": "laposte.net",
    "sfr.fe": "sfr.fr", "free.fe": "free.fr",
}

# Domaines d'adresses jetables
_DISPOSABLE = {
    "yopmail.com", "yopmail.fr", "yopmail.net", "mailinator.com", "10minutemail.com",
    "guerrillamail.com", "guerrillamail.net", "tempmail.com", "temp-mail.org",
    "trashmail.com", "trashmail.fr", "jetable.org", "getnada.com", "maildrop.cc",
    "throwawaymail.com", "dispostable.com", "sharklasers.com", "fakeinbox.com",
    "mailnesia.com", "tempr.email", "emailondeck.com", "mohmal.com", "burnermail.io",
}


@dataclass
class EmailCheck:
    email: str
    status: str
    reason: str
    generic: bool = False

    @property
    def sendable(self) -> bool:
        return self.status != STATUS_INVALIDE


# Cache DNS par domaine, pour ne pas interroger 20 fois le même
_dns_cache: Dict[str, tuple] = {}


def _dns_lookup(domain: str) -> tuple:
    """
    (statut, raison) selon le DNS du domaine. Isolé pour être simulé en test.
    """
    if domain in _dns_cache:
        return _dns_cache[domain]
    try:
        import dns.resolver
        import dns.exception
    except ImportError:
        return STATUS_RISQUE, "vérification DNS indisponible"

    try:
        dns.resolver.resolve(domain, "MX", lifetime=5)
        result = (STATUS_VALIDE, "serveur mail déclaré")
    except dns.resolver.NXDOMAIN:
        result = (STATUS_INVALIDE, "domaine inexistant")
    except dns.resolver.NoAnswer:
        result = (STATUS_RISQUE, "le domaine n'a pas de serveur mail déclaré")
    except dns.resolver.NoNameservers:
        result = (STATUS_INVALIDE, "domaine sans serveur DNS")
    except (dns.exception.Timeout, Exception):
        # Réseau indisponible : on ne condamne pas une adresse sur un aléa réseau
        result = (STATUS_RISQUE, "DNS injoignable, non vérifié")
    _dns_cache[domain] = result
    return result


def check_email(email: Optional[str], use_dns: bool = True) -> EmailCheck:
    raw = (email or "").strip()
    addr = raw.lower()
    if not addr:
        return EmailCheck(raw, STATUS_INVALIDE, "adresse vide")

    if not _EMAIL_RE.match(addr):
        return EmailCheck(raw, STATUS_INVALIDE, "syntaxe incorrecte")

    local, domain = addr.rsplit("@", 1)
    local_base = local.split("+", 1)[0]

    if local_base in _NOREPLY_LOCAL:
        return EmailCheck(raw, STATUS_INVALIDE, "adresse « ne pas répondre »")
    if domain in _PLACEHOLDER_DOMAINS or local_base in _PLACEHOLDER_LOCAL:
        return EmailCheck(raw, STATUS_INVALIDE, "adresse factice")
    if domain in _TYPOS:
        return EmailCheck(raw, STATUS_INVALIDE, f"faute de frappe probable (@{_TYPOS[domain]} ?)")
    if domain in _DISPOSABLE:
        return EmailCheck(raw, STATUS_INVALIDE, "adresse jetable")

    generic = local_base in _GENERIC_LOCAL
    if not use_dns:
        return EmailCheck(raw, STATUS_VALIDE, "syntaxe OK (DNS non vérifié)", generic)

    status, reason = _dns_lookup(domain)
    if generic and status == STATUS_VALIDE:
        reason = "valide — adresse générique (pas forcément le décideur)"
    return EmailCheck(raw, status, reason, generic)


def check_prospects(prospects, log=None) -> Dict[str, int]:
    """Renseigne p.email_status / p.email_status_reason. Retourne un décompte."""
    counts = {STATUS_VALIDE: 0, STATUS_RISQUE: 0, STATUS_INVALIDE: 0}
    for p in prospects:
        if not getattr(p, "email", None):
            continue
        res = check_email(p.email)
        p.email_status, p.email_status_reason = res.status, res.reason
        counts[res.status] += 1
        if log and res.status != STATUS_VALIDE:
            log(f"[--] {STATUS_BADGES[res.status]} {p.name} — {p.email} : {res.reason}")
    return counts


def is_sendable(prospect, allow_risky: bool = False) -> bool:
    """Un email doit-il partir ? Jamais vers « invalide », « risqué » sur option."""
    if not getattr(prospect, "email", None):
        return False
    status = getattr(prospect, "email_status", "") or ""
    if not status:   # pas encore vérifié (ancien prospect) : on vérifie à la volée
        status = check_email(prospect.email).status
    if status == STATUS_INVALIDE:
        return False
    if status == STATUS_RISQUE:
        return allow_risky
    return True
