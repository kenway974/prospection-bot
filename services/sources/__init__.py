from services.sources.sirene import search_sirene
from services.sources.pages_jaunes import search_pages_jaunes
from services.sources.france_travail import search_france_travail
from services.sources.google_search import search_google_custom
from services.sources.linkedin_csv import parse_linkedin_csv

SOURCE_LABELS = {
    "google_maps":    "🗺️ Google Maps",
    "sirene":         "🏛️ Sirene INSEE",
    "pages_jaunes":   "📖 Pages Jaunes",
    "france_travail": "💼 France Travail",
    "google_search":  "🔎 Google Search",
    "linkedin_csv":   "💼 LinkedIn CSV",
}
