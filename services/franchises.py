"""
services/franchises.py — Exclusion des franchises et grandes enseignes.

Une agence Laforêt ou un Fitness Park ne décide rien en local : leur site est
géré par le siège, et le gérant n'a ni le budget ni la main sur le digital.
Les prospecter, c'est du temps perdu.

Deux niveaux de détection :
  1. liste d'enseignes connues (par mot entier, insensible casse/accents) ;
  2. enseignes « ambiguës » (Paul, Ange, Quick…) qui ne matchent que si le nom
     COMMENCE par le mot — pour ne pas exclure « Paul Durand Immobilier ».

L'utilisateur peut ajouter ses propres enseignes (stockées en base).
"""

# 📘 `from __future__ import annotations` : les type hints ne sont pas évalués à l'exécution.
# 📘 ⚠️ La docstring dit que les ambiguës matchent si le nom "COMMENCE par" le mot ; le code
# 📘 plus bas fait en réalité une égalité EXACTE (voir le bloc de commentaires ligne AMBIGUOUS).
from __future__ import annotations

# 📘 re = regex ; unicodedata = enlever les accents ; typing = types (Set, Tuple, Iterable...).
import re
import unicodedata
from typing import Iterable, List, Optional, Set, Tuple

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : reconnaître les franchises / grandes enseignes (McDonald's, Orpi, Basic-Fit...) dans
# 📘   le nom d'un prospect pour les exclure : leur site est géré par le siège, pas en local.
# 📘 Appelé par : pipeline.py (is_franchise, sur les prospects Maps et les autres sources),
# 📘   app.py (affiche la liste FRANCHISES intégrée), tests/test_franchises.py.
# 📘   filter_franchises n'est utilisée que par les tests actuellement.
# 📘 Appelle : rien d'externe (pur calcul sur du texte).
# 📘 Concepts Python à retenir ici : set, normalisation Unicode, regex avec lookaround et
# 📘   re.escape, retour de tuple, lambda comme paramètre par défaut, `x or ()`.
# ---------------------------------------------------------------------------
# Enseignes nationales — match par mot entier, n'importe où dans le nom
# ---------------------------------------------------------------------------

# 📘 Set[str] = ensemble de chaînes. Les noms sont écrits "à la main" (accents, apostrophes) :
# 📘 ils sont normalisés au moment de la comparaison par _normalize().
# 📘 ⚠️ "but " et "ecf " ont une espace finale, mais _normalize() la retire : "but" matchera donc
# 📘 comme mot entier n'importe où (ex: "Le But du jeu" est exclu).
FRANCHISES: Set[str] = {
    # Immobilier
    "century 21", "century21", "laforet", "orpi", "guy hoquet", "stephane plaza",
    "era immobilier", "nestenn", "foncia", "citya", "square habitat", "iad france",
    "l'adresse", "human immobilier", "arthurimmo", "optimhome", "capifrance",
    "safti", "sergic", "immo de france", "nexity", "sogeprom", "bouygues immobilier",
    # Fitness
    "basic fit", "basic-fit", "fitness park", "keep cool", "keepcool",
    "l'orange bleue", "orange bleue", "vita liberte", "neoness", "on air fitness",
    "curves", "magic form", "cmg sports", "club med gym", "interval",
    # Restauration rapide & chaînes
    "mcdonald", "burger king", "kfc", "subway", "domino's", "dominos pizza",
    "pizza hut", "buffalo grill", "hippopotamus", "courtepaille", "flunch",
    "del arte", "la boucherie", "leon de bruxelles", "au bureau", "3 brasseurs",
    "les 3 brasseurs", "big fernand", "o'tacos", "otacos", "sushi shop",
    "planet sushi", "starbucks", "columbus cafe", "brioche doree", "la mie caline",
    "class'croute", "pomme de pain", "mcdo", "five guys", "steak'n shake",
    "pitaya", "waffle factory", "la croissanterie", "cojean", "exki",
    # Boulangerie / pâtisserie
    "marie blachere", "sophie lebreuilly", "banette", "feuillette", "louise",
    # Coiffure & beauté
    "franck provost", "jean louis david", "jean-louis david", "dessange",
    "camille albane", "tchip", "saint algue", "coiff&co", "jean claude aubry",
    "fabio salsa", "intermede", "body minute", "bodyminute", "yves rocher",
    "nocibe", "sephora", "marionnaud", "beauty success", "guinot", "depil tech",
    # Optique & audition
    "krys", "optic 2000", "afflelou", "grand optical", "generale d'optique",
    "les opticiens mutualistes", "ecouter voir", "lissac", "amplifon", "audika",
    # Grande distribution
    "carrefour", "leclerc", "e.leclerc", "intermarche", "super u", "hyper u",
    "casino supermarche", "lidl", "aldi", "monoprix", "franprix", "auchan",
    "cora", "netto", "colruyt", "grand frais", "picard", "biocoop", "naturalia",
    "action", "gifi", "noz", "stokomani", "la foir'fouille", "centrakor",
    # Bricolage & jardin
    "leroy merlin", "castorama", "bricomarche", "mr bricolage", "weldom",
    "gamm vert", "jardiland", "truffaut", "botanic", "point p", "brico depot",
    "bricorama", "tridome",
    # Auto
    "norauto", "feu vert", "midas", "speedy", "euromaster", "roady", "vulco",
    "ad auto", "carglass", "point s", "first stop", "dekra", "securitest",
    "autovision", "norisko", "ucar", "rent a car", "ada location",
    # Banque & assurance
    "credit agricole", "bnp paribas", "societe generale", "caisse d'epargne",
    "banque populaire", "credit mutuel", "banque postale", "axa", "allianz",
    "maaf", "maif", "groupama", "generali", "swiss life", "matmut", "macif",
    "gan assurances", "april", "abeille assurances",
    # Télécom
    "orange boutique", "sfr", "bouygues telecom", "free mobile",
    # Hôtellerie
    "ibis", "novotel", "mercure", "campanile", "premiere classe", "b&b hotel",
    "kyriad", "best western", "formule 1", "hotelf1", "accor", "ibis budget",
    "mercure hotel", "logis hotel", "appart'city", "aparthotel adagio",
    # Sport & mode
    "decathlon", "intersport", "go sport", "sport 2000", "courir", "foot locker",
    "zara", "h&m", "kiabi", "gemo", "jules", "celio", "armand thiery",
    "cache cache", "bonobo", "pimkie", "jennyfer", "promod", "etam", "undiz",
    "chaussea", "besson chaussures", "la halle", "grain de malice",
    # Équipement maison / électro
    "darty", "fnac", "boulanger", "conforama", "ikea", "maisons du monde",
    "alinea", "but ", "centrakor", "delamaison",
    # Animalerie & divers
    "maxi zoo", "animalis", "mondial relay", "chronopost", "la poste",
    "pole emploi", "france travail", "pharmabest", "pharmacie lafayette",
    "wellpharma", "giphar",
    # Auto-écoles & formation
    "ecf ", "cer permis", "en voiture simone", "ornikar", "auto ecole du centre",
    # Services aux entreprises
    "manpower", "adecco", "randstad", "synergie interim", "proman", "start people",
    "temporis", "crit interim", "actual interim", "adia",
}

# ---------------------------------------------------------------------------
# Enseignes ambiguës — le nom doit être EXACTEMENT celui-ci.
#
# Compromis assumé : exclure par erreur un vrai prospect coûte un client,
# rater une franchise ne coûte qu'un peu de temps. On est donc très strict :
#   « Paul »                  → exclu (boulangerie Paul)
#   « Paul Durand Immobilier » → gardé (indépendant) ✅
#   « Paul Saint-Denis »       → gardé (faux négatif accepté)
# L'utilisateur peut ajouter les cas précis à sa liste perso.
# ---------------------------------------------------------------------------

# 📘 ⚠️ Plusieurs mots d'ici ("louise", "action", "but", "courir") sont AUSSI dans FRANCHISES,
# 📘 qui est testé en premier par mot entier : la protection "exact seulement" ne s'applique
# 📘 donc pas à eux ("Louise Coiffure" ou "Action Plomberie" sont exclus).
# 💡 Retire ces doublons de FRANCHISES (et ajoute un test "Louise Coiffure -> gardé") pour que
# 💡   la règle stricte des enseignes ambiguës fonctionne vraiment. Même réflexion pour des mots
# 💡   courants comme "interval", "april", "adia" ou "cora".
AMBIGUOUS: Set[str] = {
    "paul", "ange", "atol", "vog", "quick", "casino", "orange", "free",
    "louise", "action", "but", "courir", "leader price", "carrefour city",
}


def _normalize(text: str) -> str:
    """Minuscules, sans accents, ponctuation réduite à des espaces."""
    # 📘 Early return : texte vide ou None -> chaîne vide.
    if not text:
        return ""
    # 📘 NFKD sépare lettre et accent (é -> e + ´) ; on enlève ensuite les accents ("combining").
    text = unicodedata.normalize("NFKD", text)
    # 📘 "".join(générateur) recolle les caractères gardés en une seule chaîne.
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    # 📘 Regex : [^...] = tout caractère SAUF lettres, chiffres, & et ' ; + = un ou plusieurs.
    # 📘 On les remplace par une espace, puis on compresse les espaces multiples (\s+).
    text = re.sub(r"[^a-z0-9&']+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _matches(needle: str, haystack: str) -> bool:
    """Match par mot entier (évite « ange » dans « angelo »)."""
    # 📘 re.escape() neutralise les caractères spéciaux regex du nom (ex: le "." de "e.leclerc").
    # 📘 (?<![a-z0-9]) = "lookbehind négatif" : pas de lettre/chiffre juste AVANT ;
    # 📘 (?![a-z0-9]) = "lookahead négatif" : pas de lettre/chiffre juste APRÈS. = mot entier.
    pattern = r"(?<![a-z0-9])" + re.escape(needle.strip()) + r"(?![a-z0-9])"
    # 📘 re.search renvoie un objet Match ou None ; `is not None` le convertit en True/False.
    return re.search(pattern, haystack) is not None


# 📘 Optional[Iterable[str]] = une liste (ou tout itérable) de textes, ou None.
# 📘 Tuple[bool, str] : on renvoie 2 infos (est-ce une franchise ?, laquelle ?).
def is_franchise(name: str, extra: Optional[Iterable[str]] = None) -> Tuple[bool, str]:
    """
    Retourne (True, "enseigne détectée") si le nom correspond à une franchise.

    `extra` : enseignes ajoutées par l'utilisateur (traitées comme les connues).
    """
    norm = _normalize(name)
    if not norm:
        return False, ""

    # 📘 Parcours d'un set : l'ordre n'est pas garanti. Si 2 enseignes matchent, celle renvoyée
    # 📘 peut varier d'un lancement à l'autre (sans impact sur le True/False).
    # 💡 Chaque appel re-normalise ~350 enseignes et construit ~350 regex : pré-calcule une fois
    # 💡   au chargement du module un seul re.compile(r"(?<![a-z0-9])(nom1|nom2|...)(?![a-z0-9])")
    # 💡   pour tester toutes les enseignes en un seul passage.
    for brand in FRANCHISES:
        if _matches(_normalize(brand), norm):
            return True, brand

    # 📘 `extra or ()` : si extra vaut None, on boucle sur un tuple vide (aucun tour de boucle).
    for brand in (extra or ()):
        nb = _normalize(brand)
        # 📘 `nb and ...` : ignore les entrées vides saisies par l'utilisateur.
        if nb and _matches(nb, norm):
            return True, brand

    # Ambiguës : correspondance exacte uniquement (cf. commentaire plus haut)
    for brand in AMBIGUOUS:
        if norm == _normalize(brand):
            return True, brand

    return False, ""


# 📘 name_getter : fonction qui sait extraire le nom d'un élément. Par défaut, une lambda qui lit
# 📘 l'attribut .name (objet Prospect). On pourrait passer lambda d: d["name"] pour des dicts.
# 📘 Une lambda comme valeur par défaut ne pose pas de souci (elle n'est pas modifiable).
def filter_franchises(
    items: Iterable, name_getter=lambda x: getattr(x, "name", ""),
    extra: Optional[Iterable[str]] = None,
) -> Tuple[List, List[Tuple[str, str]]]:
    """
    Sépare une liste en (gardés, exclus).
    `exclus` est une liste de (nom du prospect, enseigne détectée) pour le log.
    """
    # 📘 Deux listes vides créées en une ligne (affectation multiple).
    kept, removed = [], []
    # 📘 list(...) : on "matérialise" extra une seule fois, car un générateur ne se parcourt qu'une
    # 📘 fois alors qu'is_franchise va le reparcourir pour chaque élément.
    extra = list(extra or ())
    for item in items:
        name = name_getter(item) or ""
        # 📘 Déballage du tuple renvoyé par is_franchise.
        hit, brand = is_franchise(name, extra)
        if hit:
            removed.append((name, brand))
        else:
            kept.append(item)
    return kept, removed
