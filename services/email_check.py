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

# 📘 La docstring ci-dessus est excellente : elle explique le POURQUOI (délivrabilité) et
# 📘 pourquoi on ne fait PAS de sonde SMTP. `from __future__ import annotations` : hints non évalués.
from __future__ import annotations

# 📘 dataclass : décorateur qui génère automatiquement le constructeur (__init__) d'une classe
# 📘 à partir de ses attributs annotés. Idéal pour de simples "fiches" de données.
import re
from dataclasses import dataclass
from typing import Dict, Optional

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : juger si une adresse email mérite qu'on y envoie un mail (valide / risque / invalide),
# 📘   sans rien envoyer : syntaxe, adresses bidon, fautes de frappe, jetables, puis DNS (MX).
# 📘 Appelé par : pipeline.py (check_prospects avant les emails, is_sendable avant l'envoi),
# 📘   app.py (STATUS_BADGES pour afficher ✅ ⚠️ ❌), tests/test_email_check.py.
# 📘 Appelle : le DNS via la librairie dnspython (import optionnel). Aucun autre module du projet.
# 📘 Concepts Python à retenir ici : @dataclass, @property, set et `in`, regex ancrée (^...$),
# 📘   cache dict en mémoire, try/except multiples, import optionnel, rsplit, getattr.
# 📘 Constantes de statut : on écrit STATUS_VALIDE partout au lieu de "valide" pour éviter les
# 📘 fautes de frappe (une faute dans un nom de variable plante tout de suite, pas dans un texte).
STATUS_VALIDE = "valide"
STATUS_RISQUE = "risque"
STATUS_INVALIDE = "invalide"

# 📘 Dict[str, str] : dictionnaire texte -> texte. Statut -> emoji affiché dans l'interface.
STATUS_BADGES: Dict[str, str] = {
    STATUS_VALIDE: "✅",
    STATUS_RISQUE: "⚠️",
    STATUS_INVALIDE: "❌",
}

# 📘 Regex d'email assez stricte : ^ et $ obligent à matcher TOUTE la chaîne (pas juste un bout).
# 📘 Partie locale (avant @) : caractères autorisés par la norme, points non consécutifs.
# 📘 Domaine : étiquettes de 1 à 63 caractères séparées par des points, extension de 2 à 63
# 📘 lettres. Deux chaînes r"..." côte à côte sont collées en une seule. Pas de A-Z : on passe
# 📘 l'adresse en minuscules avant de tester.
_EMAIL_RE = re.compile(
    r"^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)

# Parties locales à qui écrire ne sert à rien (personne ne lit)
# 📘 Des SETS { } : recherche `x in set` instantanée et pas de doublons. Parfait pour des listes
# 📘 noires (noreply, factices, jetables...).
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
# 📘 Dictionnaire "faute -> correction". On ne corrige pas automatiquement : on bloque et on
# 📘 affiche la correction probable dans la raison.
# 💡 La liste en dur ne couvre que les fautes prévues ; difflib.get_close_matches(domain,
# 💡   ["gmail.com", "hotmail.fr", ...]) détecterait aussi les fautes non listées.
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


# 📘 @dataclass génère __init__(self, email, status, reason, generic=False) : tu peux écrire
# 📘 EmailCheck("a@b.fr", "valide", "ok") sans coder le constructeur. `generic: bool = False`
# 📘 = champ facultatif (valeur par défaut). Les champs sans défaut doivent venir avant.
@dataclass
class EmailCheck:
    email: str
    status: str
    reason: str
    generic: bool = False

    # 📘 @property transforme une méthode en "attribut calculé" : on écrit res.sendable (sans
    # 📘 parenthèses) et la valeur est recalculée à chaque lecture.
    @property
    def sendable(self) -> bool:
        return self.status != STATUS_INVALIDE


# 📘 Dict global en mémoire : il vit tant que le processus Python tourne (tout le temps d'une
# 📘 session Streamlit) et n'est jamais vidé.
# 💡 Pas d'expiration ni de limite de taille : un domaine vu "injoignable" une fois reste "risque"
# 💡   jusqu'au redémarrage. Ne mets pas en cache les résultats de timeout, ou ajoute un horodatage.
# Cache DNS par domaine, pour ne pas interroger 20 fois le même
_dns_cache: Dict[str, tuple] = {}


# 📘 `-> tuple` : renvoie un tuple (statut, raison). Isolé dans sa propre fonction pour que les
# 📘 tests puissent la remplacer (monkeypatch) et ne pas dépendre d'Internet.
def _dns_lookup(domain: str) -> tuple:
    """
    (statut, raison) selon le DNS du domaine. Isolé pour être simulé en test.
    """
    if domain in _dns_cache:
        return _dns_cache[domain]
    # 📘 Import optionnel : si le paquet dnspython n'est pas installé, ImportError est levée et on
    # 📘 renvoie "risque" au lieu de planter. L'app reste utilisable sans cette dépendance.
    try:
        import dns.resolver
        import dns.exception
    except ImportError:
        return STATUS_RISQUE, "vérification DNS indisponible"

    try:
        # 📘 Question DNS : "quels serveurs reçoivent les mails de ce domaine ?" (enregistrement MX).
        # 📘 lifetime=5 : on abandonne après 5 s. On ne se sert pas de la réponse, seulement du fait
        # 📘 qu'elle existe (sinon une exception est levée).
        dns.resolver.resolve(domain, "MX", lifetime=5)
        result = (STATUS_VALIDE, "serveur mail déclaré")
    # 📘 Plusieurs `except` à la suite : Python prend le PREMIER qui correspond au type d'erreur.
    # 📘 NXDOMAIN = le domaine n'existe pas ; NoAnswer = il existe mais n'a pas de MX.
    except dns.resolver.NXDOMAIN:
        result = (STATUS_INVALIDE, "domaine inexistant")
    except dns.resolver.NoAnswer:
        result = (STATUS_RISQUE, "le domaine n'a pas de serveur mail déclaré")
    except dns.resolver.NoNameservers:
        result = (STATUS_INVALIDE, "domaine sans serveur DNS")
    # 📘 Exception attrape tout le reste ; dns.exception.Timeout dans le tuple est donc redondant
    # 📘 (mais ça documente l'intention).
    except (dns.exception.Timeout, Exception):
        # Réseau indisponible : on ne condamne pas une adresse sur un aléa réseau
        result = (STATUS_RISQUE, "DNS injoignable, non vérifié")
    _dns_cache[domain] = result
    return result


# 📘 Fonction centrale : les contrôles vont du moins cher (texte) au plus cher (réseau DNS),
# 📘 et on s'arrête (`return`) au premier problème trouvé.
# 📘 `use_dns=False` permet de tester sans réseau.
def check_email(email: Optional[str], use_dns: bool = True) -> EmailCheck:
    # 📘 On garde `raw` (tel que saisi) pour l'affichage, et `addr` (minuscules) pour les tests.
    raw = (email or "").strip()
    addr = raw.lower()
    if not addr:
        return EmailCheck(raw, STATUS_INVALIDE, "adresse vide")

    if not _EMAIL_RE.match(addr):
        return EmailCheck(raw, STATUS_INVALIDE, "syntaxe incorrecte")

    # 📘 rsplit("@", 1) coupe au DERNIER @ en 2 morceaux ; on "déballe" en local et domain.
    local, domain = addr.rsplit("@", 1)
    # 📘 "jean+promo@x.fr" -> "jean" : le +suffixe est un alias, on compare la base.
    local_base = local.split("+", 1)[0]

    if local_base in _NOREPLY_LOCAL:
        return EmailCheck(raw, STATUS_INVALIDE, "adresse « ne pas répondre »")
    if domain in _PLACEHOLDER_DOMAINS or local_base in _PLACEHOLDER_LOCAL:
        return EmailCheck(raw, STATUS_INVALIDE, "adresse factice")
    if domain in _TYPOS:
        # 📘 f-string : {_TYPOS[domain]} insère la correction suggérée dans le message.
        return EmailCheck(raw, STATUS_INVALIDE, f"faute de frappe probable (@{_TYPOS[domain]} ?)")
    if domain in _DISPOSABLE:
        return EmailCheck(raw, STATUS_INVALIDE, "adresse jetable")

    # 📘 Une adresse générique (contact@, info@) reste valide, on note juste que ce n'est
    # 📘 probablement pas le décideur.
    generic = local_base in _GENERIC_LOCAL
    if not use_dns:
        return EmailCheck(raw, STATUS_VALIDE, "syntaxe OK (DNS non vérifié)", generic)

    status, reason = _dns_lookup(domain)
    if generic and status == STATUS_VALIDE:
        reason = "valide — adresse générique (pas forcément le décideur)"
    return EmailCheck(raw, status, reason, generic)


# 📘 Pas de type hints ici : `prospects` est une liste de Prospect, `log` une fonction optionnelle.
def check_prospects(prospects, log=None) -> Dict[str, int]:
    """Renseigne p.email_status / p.email_status_reason. Retourne un décompte."""
    # 📘 Compteur par statut, initialisé à 0 ; `counts[res.status] += 1` incrémente.
    counts = {STATUS_VALIDE: 0, STATUS_RISQUE: 0, STATUS_INVALIDE: 0}
    for p in prospects:
        # 📘 getattr(p, "email", None) : lit l'attribut sans planter s'il n'existe pas.
        if not getattr(p, "email", None):
            continue
        # 💡 Vérifications faites une par une ; chaque domaine inconnu peut coûter jusqu'à 5 s de DNS.
        # 💡   Un ThreadPoolExecutor sur les domaines uniques accélérerait les grosses campagnes
        # 💡   (attention alors au dict _dns_cache partagé entre threads).
        res = check_email(p.email)
        # 📘 Affectation multiple : on écrit les deux attributs du prospect en une ligne.
        p.email_status, p.email_status_reason = res.status, res.reason
        counts[res.status] += 1
        if log and res.status != STATUS_VALIDE:
            log(f"[--] {STATUS_BADGES[res.status]} {p.name} — {p.email} : {res.reason}")
    return counts


# 📘 Dernière barrière avant l'envoi réel (utilisée par pipeline.py juste avant les brouillons).
def is_sendable(prospect, allow_risky: bool = False) -> bool:
    """Un email doit-il partir ? Jamais vers « invalide », « risqué » sur option."""
    if not getattr(prospect, "email", None):
        return False
    status = getattr(prospect, "email_status", "") or ""
    # 📘 Rattrapage : un prospect jamais vérifié (ex: chargé depuis un ancien fichier) est vérifié
    # 📘 ici à la volée.
    if not status:   # pas encore vérifié (ancien prospect) : on vérifie à la volée
        status = check_email(prospect.email).status
    if status == STATUS_INVALIDE:
        return False
    # 📘 "risque" n'est envoyé que si l'utilisateur l'a explicitement autorisé (allow_risky).
    if status == STATUS_RISQUE:
        return allow_risky
    return True
