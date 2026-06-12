"""
services/sources/linkedin_csv.py — Import de contacts depuis un export CSV LinkedIn.

Supporte les formats :
  - LinkedIn Sales Navigator (Company, First Name, Last Name, Title, Email, Website…)
  - LinkedIn Mes connexions (First Name, Last Name, Email Address, Company, Position)
  - Tout CSV avec des colonnes reconnues (détection automatique, insensible à la casse)

Usage : l'utilisateur exporte ses contacts depuis LinkedIn et uploade le fichier
dans l'UI Streamlit. Aucune API, aucune clé — 100% légal (données propres).
"""

from __future__ import annotations

import csv
import hashlib
import io
from typing import List, Optional

from config import logger
from services.google_maps import Prospect

# Synonymes de colonnes reconnus (en minuscules)
_COL_COMPANY  = ["company", "entreprise", "société", "organization", "nom entreprise", "company name"]
_COL_FIRST    = ["first name", "prénom", "firstname", "first"]
_COL_LAST     = ["last name", "nom", "lastname", "last", "surname"]
_COL_TITLE    = ["title", "poste", "fonction", "position", "job title"]
_COL_EMAIL    = ["email", "email address", "courriel", "mail", "e-mail"]
_COL_WEBSITE  = ["website", "site web", "url", "company website", "site", "company url"]
_COL_PHONE    = ["phone", "téléphone", "mobile", "telephone", "phone number"]
_COL_LOCATION = ["location", "localisation", "ville", "city", "country", "pays", "geography"]


def _find_col(headers: list, candidates: list) -> Optional[int]:
    """Retourne l'index de la première colonne dont le nom figure dans `candidates`."""
    lower = [h.lower().strip() for h in headers]
    for c in candidates:
        if c in lower:
            return lower.index(c)
    return None


def _clean_website(raw: str) -> Optional[str]:
    raw = raw.strip()
    if not raw:
        return None
    if not raw.startswith("http"):
        raw = "https://" + raw
    return raw


def parse_linkedin_csv(content: str, keyword: str = "LinkedIn") -> List[Prospect]:
    """
    Parse un CSV LinkedIn (contenu texte) et retourne une liste de Prospects.

    Priorités pour le nom : colonne Company > "Prénom Nom — Titre".
    Si email déjà présent dans le CSV il est directement affecté à `prospect.email`
    (pas besoin de scraper le site).
    """
    prospects: List[Prospect] = []

    # Détecter le délimiteur (virgule ou point-virgule)
    sample = content[:2048]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","

    try:
        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        rows = list(reader)
    except Exception as exc:
        logger.error("LinkedIn CSV : erreur de parsing — %s", exc)
        return []

    if len(rows) < 2:
        logger.warning("LinkedIn CSV : fichier vide ou sans données")
        return []

    headers = rows[0]

    i_company  = _find_col(headers, _COL_COMPANY)
    i_first    = _find_col(headers, _COL_FIRST)
    i_last     = _find_col(headers, _COL_LAST)
    i_title    = _find_col(headers, _COL_TITLE)
    i_email    = _find_col(headers, _COL_EMAIL)
    i_website  = _find_col(headers, _COL_WEBSITE)
    i_phone    = _find_col(headers, _COL_PHONE)
    i_location = _find_col(headers, _COL_LOCATION)

    def _get(row: list, idx: Optional[int]) -> str:
        if idx is None or idx >= len(row):
            return ""
        return row[idx].strip()

    skipped = 0
    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue

        company  = _get(row, i_company)
        first    = _get(row, i_first)
        last     = _get(row, i_last)
        title    = _get(row, i_title)
        email    = _get(row, i_email)
        website  = _get(row, i_website)
        phone    = _get(row, i_phone)
        location = _get(row, i_location)

        # Nom : préfère l'entreprise
        if company:
            name = company
        elif first or last:
            person = f"{first} {last}".strip()
            name = f"{person} — {title}" if title else person
        else:
            skipped += 1
            continue

        pid = "li_" + hashlib.md5(f"{name}{email}{website}".encode()).hexdigest()[:16]

        p = Prospect(
            place_id=pid,
            name=name,
            address=location or "",
            phone=phone or None,
            website=_clean_website(website),
            rating=None,
            user_ratings_total=0,
            keyword=keyword,
            maps_url="",
        )
        if email:
            p.email = email

        prospects.append(p)

    if skipped:
        logger.debug("LinkedIn CSV : %d ligne(s) ignorée(s) (sans nom ni entreprise)", skipped)

    logger.info("  → %d contact(s) importés depuis le CSV LinkedIn", len(prospects))
    return prospects
