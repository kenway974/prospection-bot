"""
tests/reims_fixture.py — Données simulées du cas réel « cuisinistes Reims ».

Construites d'après les fiches constatées (types Google plausibles : HYPOTHÈSE,
l'API ne renvoie que des catégories grossières). Google renvoie les fiches
« bruit » sur la 1re requête ; les vrais cuisinistes n'apparaissent qu'avec les
synonymes (« magasin de cuisines équipées », « cuisine sur mesure »).
"""

ADDR = "51100 Reims, France"


def raw(pid, name, types, rating=4.5, reviews=20, phone="03 26 00 00 00", website=None):
    return {
        "place_id": pid, "name": name, "types": types + ["point_of_interest", "establishment"],
        "rating": rating, "user_ratings_total": reviews, "business_status": "OPERATIONAL",
        "formatted_address": f"1 rue X, {ADDR}", "_phone": phone, "_website": website,
    }


NOISE = [
    raw("az", "AZ Energy", ["electrician"], rating=5.0, reviews=3),
    raw("piano", "Au Piano des Chefs", ["school"]),
    raw("cedeo1", "CEDEO Reims", ["home_goods_store"]),
    raw("cedeo2", "CEDEO Tinqueux", ["hardware_store"]),
    raw("cedeo3", "Cedeo Salle de Bains", ["home_goods_store"]),
    raw("design", "Cuisine Design", ["home_goods_store"], reviews=0, phone=None),
    raw("angel", "Angel Carrelages & Bains", ["home_goods_store", "general_contractor"],
        rating=4.8, reviews=100, website="https://angel-carrelages.fr"),
    raw("cuisinella", "Cuisinella Reims", ["furniture_store"]),
    raw("lapeyre", "Lapeyre", ["home_goods_store"]),
    raw("darty", "Darty Cuisine Reims", ["home_goods_store"]),
    raw("lm", "Leroy Merlin Reims", ["hardware_store"]),
]

REAL_CUISINISTES = [
    raw("etoile", "Etoile Cuisines", ["home_goods_store"], reviews=12),
    raw("bressan", "Bressan Création", ["furniture_store"], reviews=8),
    raw("dineries", "Dineries Cuisines et Bain", ["home_goods_store"], reviews=25),
    raw("bodezign", "BO DeZign", ["home_goods_store"], reviews=5),
    raw("bruschi", "Bruschi Créations", ["general_contractor"], reviews=15),
    raw("interieur", "Intérieur Actuel", ["furniture_store"], reviews=40),
    raw("cuisinium", "Cuisinium", ["home_goods_store"], reviews=30),
]
REAL_IDS = {r["place_id"] for r in REAL_CUISINISTES}

# Résultats par requête : la 1re ne contient que du bruit (+ 1 vrai cuisiniste)
BY_QUERY = {
    "cuisinistes": NOISE + REAL_CUISINISTES[:1],
    "magasin de cuisines équipées": REAL_CUISINISTES[:5] + NOISE[2:4],
    "cuisine sur mesure": REAL_CUISINISTES[3:] + NOISE[:1],
}

# Sirène simulée (nom → fiche) ; absent = introuvable
SIRENE = {
    "Etoile Cuisines": {"naf": "47.59A", "etab": 1},
    "Bressan Création": {"naf": "31.02Z", "etab": 1},
    "Dineries Cuisines et Bain": {"naf": "47.59A", "etab": 1},
    "BO DeZign": {"naf": "43.32A", "etab": 1},
    "Bruschi Créations": {"naf": "43.32A", "etab": 1},
    "Intérieur Actuel": {"naf": "47.59A", "etab": 2},
    "Cuisinium": {"naf": "47.59A", "etab": 1},
    "Angel Carrelages & Bains": {"naf": "43.33Z", "etab": 1},
    "AZ Energy": {"naf": "43.21A", "etab": 1, "ca": 0},
}


def sirene_entry(name):
    data = SIRENE.get(name)
    if data is None:
        return None
    return {
        "siren": "123456789", "nom_complet": name.upper(), "nom_raison_sociale": name.upper(),
        "etat_administratif": "A", "activite_principale": data["naf"], "date_creation": "2015-01-01",
        "nombre_etablissements_ouverts": data["etab"],
        "finances": {"2025": {"ca": data["ca"]}} if "ca" in data else {},
        "dirigeants": [],
    }


# Pages web simulées (site finder) : AZ Energy n'a un site qu'au Luxembourg
PAGES = {"azenergy.lu": "<h1>AZ Energy</h1><p>Installation photovoltaïque — Luxembourg</p>"}
