# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : __init__.py fait du dossier services/sources un "package" Python. Il ré-exporte les
# 📘   fonctions de recherche de chaque source et définit leurs libellés affichés dans l'UI.
# 📘 Appelé par : app.py (SOURCE_LABELS, importé DÈS le démarrage de l'appli) et pipeline.py
# 📘   (les fonctions search_* + SOURCE_LABELS).
# 📘 Appelle : les 5 modules du dossier (sirene, pages_jaunes, france_travail, google_search,
# 📘   linkedin_csv).
# 📘 Concepts Python à retenir ici : package et __init__.py, ré-export d'imports, dict constant.
# 📘 Grâce à ces imports, on peut écrire `from services.sources import search_sirene` au lieu de
# 📘 `from services.sources.sirene import search_sirene`.
# 📘 ⚠️ Importer ce package importe aussi les 5 modules, qui font `from config import config,
# 📘   logger` : comme app.py l'importe au démarrage, ils figent la config ET le logger de ce
# 📘   moment-là (pipeline.py ne les remplace pas ensuite). Détail dans chaque fichier.
from services.sources.sirene import search_sirene
from services.sources.pages_jaunes import search_pages_jaunes
from services.sources.france_travail import search_france_travail
from services.sources.google_search import search_google_custom
from services.sources.linkedin_csv import parse_linkedin_csv

# 📘 Dictionnaire "identifiant technique → libellé affiché". Les clés sont les valeurs stockées
# 📘 dans les réglages (source_types) ; "google_maps" est géré par services/google_maps.py.
# 💡 Pattern "registre" : un dict {"sirene": search_sirene, ...} ici éviterait la chaîne if/elif
# 💡   de pipeline.py, à condition d'uniformiser les signatures (cx, client_id… via un objet
# 💡   de config passé en argument).
SOURCE_LABELS = {
    "google_maps":    "🗺️ Google Maps",
    "sirene":         "🏛️ Sirene INSEE",
    "pages_jaunes":   "📖 Pages Jaunes",
    "france_travail": "💼 France Travail",
    "google_search":  "🔎 Google Search",
    "linkedin_csv":   "💼 LinkedIn CSV",
}
