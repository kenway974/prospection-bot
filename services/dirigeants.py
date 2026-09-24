"""
services/dirigeants.py — Trouver le dirigeant d'une entreprise via Sirène.

Source : API Recherche d'entreprises (data.gouv.fr) — données publiques et
gratuites du registre national, sans authentification.
  https://recherche-entreprises.api.gouv.fr/docs/

Sirène ne contient que les REPRÉSENTANTS LÉGAUX (président, gérant, DG…).
Un CTO ou un Product Owner n'y figure jamais : pour eux, c'est LinkedIn.

Règle d'or : on n'attribue un dirigeant QUE si la correspondance est sûre.
Écrire « Bonjour Jean » au mauvais Jean est pire que « Bonjour ».
"""

# 📘 Voir la docstring ci-dessus : la "règle d'or" (ne rien attribuer si doute) explique tous les
# 📘 seuils stricts de ce fichier. `from __future__ import annotations` : type hints non évalués.
from __future__ import annotations

# 📘 Modules standard : re (regex), time (pauses), unicodedata (enlever les accents),
# 📘 difflib.SequenceMatcher (mesurer la ressemblance entre deux textes), typing (types).
import re
import time
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Tuple

# 📘 requests : librairie externe pour appeler des API HTTP.
import requests

from config import config, logger

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : retrouver le nom et la fonction du dirigeant légal d'une entreprise (président,
# 📘   gérant...) dans le registre public Sirène, pour personnaliser l'email ("Bonjour Jean").
# 📘 Appelé par : pipeline.py (enrich_prospects, après la sélection des prospects),
# 📘   services/sources/sirene.py (extract_dirigeant), tests/test_dirigeants.py.
# 📘 Appelle : l'API publique recherche-entreprises.api.gouv.fr (gratuite, sans clé), config.py.
# 📘 Concepts Python à retenir ici : normalisation Unicode, regex, set (ensembles) et <=,
# 📘   sorted / min avec key=lambda, comprehension avec filtre, `global`, getattr, Iterable.
BASE_URL = "https://recherche-entreprises.api.gouv.fr/search"

# Rate limit documenté de l'API : ~7 requêtes/s. On reste largement en dessous.
# 📘 Throttling (limitation de débit) : on impose au moins 0,2 s entre deux appels (=5 req/s max)
# 📘 pour ne pas se faire bloquer par l'API. _last_call mémorise l'heure du dernier appel.
_MIN_INTERVAL_S = 0.2
_last_call = 0.0

# Seuil de similarité des noms pour accepter une correspondance
# 📘 Similarité minimale (0 = rien à voir, 1 = identique) pour accepter qu'un résultat Sirène
# 📘 soit bien NOTRE entreprise. Élevé exprès : mieux vaut pas de nom qu'un mauvais nom.
MATCH_THRESHOLD = 0.82

# Priorité des fonctions : le plus décisionnaire d'abord.
# 📘 Liste de tuples (mot-clé, rang) : plus le rang est petit, plus la personne décide.
# 📘 ⚠️ _role_rank prend la PREMIÈRE clé contenue dans la fonction : "directeur general delegue"
# 📘 contient "directeur general" (testé avant) => il reçoit le rang 1 et jamais le rang 3.
# 📘 De même "co-gerant" devient "co gerant" après _norm, c'est "gerant" qui matche (même rang 2).
# 💡 Tester les clés les plus longues d'abord (trier par len décroissante) ou comparer par égalité
# 💡   corrigerait ce classement ; un test unitaire "DG délégué < DG" le verrouillerait.
_ROLE_PRIORITY: List[Tuple[str, int]] = [
    ("president", 0),
    ("directeur general", 1),
    ("gerant", 2),
    ("co-gerant", 2),
    ("cogerant", 2),
    ("directeur general delegue", 3),
    ("administrateur", 5),
]

# Mots qui n'aident pas à identifier une entreprise (formes juridiques, etc.)
# 📘 { ... } avec des valeurs seules (sans ":") = un SET (ensemble) : pas de doublons, et le test
# 📘 `x in set` est quasi instantané, même avec beaucoup d'éléments (plus rapide qu'une liste).
_STOPWORDS = {
    "sas", "sasu", "sarl", "eurl", "sa", "sci", "snc", "scop", "selarl", "ei",
    "eirl", "micro", "entreprise", "societe", "ste", "et", "de", "du", "des",
    "la", "le", "les", "l", "d", "en", "a",
}


# ---------------------------------------------------------------------------
# Normalisation & comparaison de noms
# ---------------------------------------------------------------------------

# 📘 Normalise un texte pour comparer "Société Générale" et "SOCIETE  GENERALE" :
# 📘 1) NFKD sépare les lettres de leurs accents (é -> e + ´), 2) on jette les accents
# 📘 (combining), 3) minuscules, 4) regex : tout ce qui n'est pas a-z/0-9 devient un espace.
# 📘 `text or ""` : si text vaut None, on utilise "" (évite un plantage).
def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


# 📘 Découpe en mots normalisés en retirant les mots vides (_STOPWORDS : SARL, de, la...).
def _tokens(text: str) -> List[str]:
    return [t for t in _norm(text).split() if t not in _STOPWORDS]


def name_similarity(a: str, b: str) -> float:
    """
    Similarité 0..1 entre deux raisons sociales, robuste aux formes juridiques
    (« Garage Payet SARL » ≈ « GARAGE PAYET ») et à l'ordre des mots.
    """
    # 📘 Affectation multiple : ta, tb = x, y assigne les deux d'un coup.
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    # 📘 On trie les mots pour que l'ordre n'influe pas ("Payet Garage" == "Garage Payet").
    # 📘 SequenceMatcher(...).ratio() renvoie un score de ressemblance entre 0 et 1.
    sa, sb = " ".join(sorted(ta)), " ".join(sorted(tb))
    ratio = SequenceMatcher(None, sa, sb).ratio()
    # Tous les mots significatifs de l'un sont dans l'autre → bon signe, MAIS
    # seulement si le nom court est assez spécifique : sinon « Garage » matcherait
    # « Garage Dupont » et on écrirait au mauvais dirigeant.
    set_a, set_b = set(ta), set(tb)
    # 📘 Avec des sets, `a <= b` veut dire "a est inclus dans b" (sous-ensemble).
    if set_a <= set_b or set_b <= set_a:
        # 📘 sorted((x, y)) trie les deux tailles : small = la plus petite, large = la plus grande.
        small, large = sorted((len(set_a), len(set_b)))
        overlap = small / large
        if small >= 2 and overlap >= 2 / 3:
            ratio = max(ratio, 0.85 + 0.15 * overlap)
    return ratio


def extract_postal_code(address: str) -> str:
    """Code postal français depuis une adresse Google Maps (« … 97400 Saint-Denis »)."""
    # 📘 re.search cherche le motif n'importe où. \b = frontière de mot, \d{5} = 5 chiffres.
    # 📘 La branche 97[1-6]\d{2} (DOM-TOM) est déjà couverte par \d{5} : elle est redondante.
    m = re.search(r"\b(97[1-6]\d{2}|\d{5})\b", address or "")
    # 📘 m.group(1) = le texte capturé par les parenthèses. `A if cond else B` = if en une ligne.
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Extraction du dirigeant depuis une entrée de l'API
# ---------------------------------------------------------------------------

def _format_person(prenoms: str, nom: str) -> str:
    """« Jean Marc Pierre » + « LE GOFF » → « Jean Le Goff »."""
    # 📘 On ne garde que le 1er prénom ("Jean Marc Pierre" -> "Jean"), en gérant les prénoms
    # 📘 composés à tiret ("jean-marc" -> "Jean-Marc"). .capitalize() = 1re lettre en majuscule.
    first = (prenoms or "").strip().split(" ")[0] if prenoms else ""
    first = "-".join(p.capitalize() for p in first.split("-"))

    # 📘 Petite fonction imbriquée, utile seulement ici, pour mettre en forme chaque mot du nom.
    def _cap(word: str) -> str:
        if "'" in word:  # D'ARTAGNAN → D'Artagnan
            return "'".join(p.capitalize() for p in word.split("'"))
        return "-".join(p.capitalize() for p in word.split("-"))

    last = " ".join(_cap(w) for w in (nom or "").strip().lower().split())
    return f"{first} {last}".strip()


# 📘 Donne le rang d'une fonction (0 = président...). 9 = fonction inconnue (priorité la plus basse).
def _role_rank(qualite: str) -> int:
    q = _norm(qualite)
    for key, rank in _ROLE_PRIORITY:
        if key in q:
            return rank
    return 9


def _clean_role(qualite: str) -> str:
    """« Président de SAS » → « Président » ; garde le libellé lisible."""
    q = (qualite or "").strip()
    # 📘 re.sub(motif, remplacement, texte) : supprime " de SAS..." jusqu'à la fin ($). flags=re.I
    # 📘 = insensible à la casse. \s+ = un ou plusieurs espaces.
    q = re.sub(r"\s+de\s+(sas|sasu|sarl|eurl|sa|snc|sci).*$", "", q, flags=re.I)
    # 📘 q[:1] = 1er caractère, q[1:] = le reste (slicing). On met juste la 1re lettre en majuscule.
    return q[:1].upper() + q[1:] if q else ""


def extract_dirigeant(entry: dict) -> Tuple[str, str]:
    """
    Retourne (« Prénom Nom », « Fonction ») du dirigeant le plus décisionnaire.
    Ignore les personnes morales (holdings). ("", "") si aucun.
    """
    # 📘 Comprehension avec filtre sur plusieurs lignes : on garde les dirigeants "personne physique"
    # 📘 (pas les sociétés/holdings) qui ont un nom. `or []` protège si la clé vaut None.
    people = [
        d for d in (entry.get("dirigeants") or [])
        if (d.get("type_dirigeant") or "").lower() == "personne physique"
        and (d.get("nom") or "").strip()
    ]
    if not people:
        return "", ""
    # 📘 min(liste, key=fonction) renvoie l'élément dont la "clé" est la plus petite : ici le
    # 📘 dirigeant au rang le plus décisionnaire. `lambda d: ...` = mini-fonction anonyme.
    best = min(people, key=lambda d: _role_rank(d.get("qualite", "")))
    # 📘 On renvoie un tuple de 2 valeurs, que l'appelant "déballe" : nom, fonction = extract_...(e)
    return _format_person(best.get("prenoms", ""), best.get("nom", "")), _clean_role(best.get("qualite", ""))


# ---------------------------------------------------------------------------
# Recherche d'une entreprise précise
# ---------------------------------------------------------------------------

# 📘 `global _last_call` : on modifie la variable du module (partagée entre tous les appels).
# 📘 Pas de verrou ici : OK car enrich_prospects est appelé en séquence (pas en threads).
def _throttle() -> None:
    global _last_call
    wait = _MIN_INTERVAL_S - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _search(name: str, postal_code: str) -> List[dict]:
    # 📘 params= est transformé par requests en "?q=...&per_page=5&page=1" dans l'URL.
    params = {"q": name, "per_page": 5, "page": 1}
    if postal_code:
        params["code_postal"] = postal_code
    _throttle()
    try:
        resp = requests.get(BASE_URL, params=params, timeout=config.request_timeout)
        # 📘 status_code = code HTTP de la réponse (200 = OK, 404 = introuvable, 429 = trop de requêtes).
        if resp.status_code == 429:           # trop de requêtes : on patiente une fois
            time.sleep(2)
            resp = requests.get(BASE_URL, params=params, timeout=config.request_timeout)
        # 📘 raise_for_status() lève une exception si le code HTTP est une erreur (4xx/5xx).
        resp.raise_for_status()
        # 📘 .get("results", []) or [] : liste vide si la clé manque OU vaut None.
        return resp.json().get("results", []) or []
    # 📘 ValueError couvre le cas où la réponse n'est pas du JSON valide. En cas d'échec on renvoie
    # 📘 une liste vide : "pas trouvé" plutôt que planter toute la campagne.
    except (requests.RequestException, ValueError) as exc:
        logger.debug("  Sirène dirigeant indisponible pour %s : %s", name, exc)
        return []


# 📘 Optional[dict] : renvoie un dict si trouvé avec certitude, sinon None.
def find_dirigeant(name: str, address: str = "") -> Optional[dict]:
    """
    Cherche l'entreprise dans Sirène et retourne
      {"siren", "dirigeant", "qualite", "score"} si la correspondance est SÛRE,
    None sinon.
    """
    if not name or not name.strip():
        return None
    # 📘 Le code postal (extrait de l'adresse Google Maps) filtre fortement les homonymes.
    postal = extract_postal_code(address)
    results = _search(name, postal)

    # 📘 On cherche, parmi les 5 résultats et leurs 2 variantes de nom, celui qui ressemble le plus.
    best, best_score = None, 0.0
    for entry in results:
        # 📘 Boucle sur un tuple de 2 noms possibles ; `continue` saute les valeurs vides.
        for candidate in (entry.get("nom_raison_sociale"), entry.get("nom_complet")):
            if not candidate:
                continue
            score = name_similarity(name, candidate)
            if score > best_score:
                best, best_score = entry, score

    # 📘 Règle d'or appliquée : sous le seuil de similarité, on préfère ne rien renvoyer.
    if best is None or best_score < MATCH_THRESHOLD:
        return None

    dirigeant, qualite = extract_dirigeant(best)
    if not dirigeant:
        return None
    return {
        "siren": best.get("siren", ""),
        "dirigeant": dirigeant,
        "qualite": qualite,
        # 📘 round(x, 2) arrondit à 2 décimales.
        "score": round(best_score, 2),
    }


# 📘 Iterable = "n'importe quoi qu'on peut parcourir avec for" (liste, tuple, générateur...).
# 📘 `log=None` : fonction de log optionnelle (pipeline passe log_q.put pour afficher dans l'UI).
# 💡 Traitement séquentiel : ~0,2 s de throttle + temps de réponse par prospect. Pour 200
# 💡   prospects ça fait plus d'une minute ; un petit cache disque par (nom, code postal), comme
# 💡   services/cache.py, éviterait de réinterroger Sirène à chaque campagne.
def enrich_prospects(prospects: Iterable, log=None) -> int:
    """
    Complète p.dirigeant / p.dirigeant_qualite / p.siren sur chaque prospect.
    Ne touche pas un prospect déjà renseigné. Retourne le nombre enrichi.
    """
    found = 0
    for p in prospects:
        # 📘 getattr(objet, "attr", défaut) lit un attribut sans planter s'il n'existe pas.
        # 📘 On ne réécrase pas un dirigeant déjà connu (ex: fourni par la source Sirène).
        if getattr(p, "dirigeant", ""):
            continue
        info = find_dirigeant(p.name, p.address or "")
        if info:
            p.dirigeant = info["dirigeant"]
            p.dirigeant_qualite = info["qualite"]
            # 📘 `p.siren or info["siren"]` : garde le SIREN existant, sinon prend celui trouvé.
            p.siren = p.siren or info["siren"]
            found += 1
            if log:
                log(f"[--] 👤 {p.name} → {p.dirigeant} ({p.dirigeant_qualite})")
    return found
