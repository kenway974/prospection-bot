"""
services/sources/pages_jaunes.py — Scraper Pages Jaunes public.

URL: https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui={keyword}&ou={location}&page={page}
"""

from __future__ import annotations

import hashlib
import time
from typing import List, Optional

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore

from config import config, logger
from services.google_maps import Prospect


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

BASE_URL = "https://www.pagesjaunes.fr/annuaire/chercherlespros"
MAX_PAGES = 5


def _fetch_page_html(keyword: str, location: str, page: int) -> Optional[str]:
    """Récupère le HTML d'une page de résultats avec retry (2s, 4s, 8s)."""
    params = {
        "quoiqui": keyword,
        "ou": location,
        "page": page,
    }
    for attempt in range(3):
        try:
            resp = requests.get(
                BASE_URL,
                params=params,
                headers=HEADERS,
                timeout=config.request_timeout,
            )
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            if attempt < 2:
                delay = 2 ** (attempt + 1)
                logger.debug(
                    "    ↩️  Pages Jaunes retry %d/3 dans %ds…", attempt + 1, delay
                )
                time.sleep(delay)
            else:
                logger.error("Erreur Pages Jaunes page %d : %s", page, exc)
    return None


def _extract_text(tag) -> str:
    """Extrait le texte d'un tag BeautifulSoup, retourne '' si None."""
    if tag is None:
        return ""
    return tag.get_text(strip=True)


def _parse_articles(soup) -> list:
    """Tente plusieurs sélecteurs pour trouver les articles de résultats."""
    # Sélecteur 1 : articles avec classe contenant "bi-"
    articles = soup.find_all(
        "article",
        class_=lambda c: c and "bi-" in " ".join(c if isinstance(c, list) else [c]),
    )
    if articles:
        return articles

    # Sélecteur 2 : li avec classe contenant "bi-"
    articles = soup.find_all(
        "li",
        class_=lambda c: c and "bi-" in str(c),
    )
    if articles:
        return articles

    # Sélecteur 3 : éléments avec classe contenant "bi-generic"
    articles = soup.select("[class*='bi-generic']")
    return articles


def _parse_prospect(article, keyword: str) -> Optional[Prospect]:
    """Extrait les informations d'un article et retourne un Prospect."""
    # Nom
    name_tag = (
        article.find("a", class_=lambda c: c and "denomination" in str(c))
        or article.find("span", class_=lambda c: c and "denomination" in str(c))
        or article.find("h2")
        or article.find("h3")
    )
    name = _extract_text(name_tag)
    if not name:
        return None

    # Adresse
    address_tag = (
        article.find(class_=lambda c: c and "address" in str(c))
        or article.find("address")
    )
    address = _extract_text(address_tag)

    # Téléphone (depuis href tel:)
    phone = None
    phone_tag = article.find("a", href=lambda h: h and h.startswith("tel:"))
    if phone_tag:
        phone = phone_tag["href"].replace("tel:", "").strip()

    # Site web (premier lien externe non pagesjaunes)
    website = None
    for link in article.find_all("a", href=True):
        href = link["href"]
        if href.startswith("http") and "pagesjaunes" not in href:
            website = href
            break

    place_id = "pj_" + hashlib.md5(f"{name}{address}".encode()).hexdigest()[:16]

    return Prospect(
        place_id=place_id,
        name=name,
        address=address,
        phone=phone,
        website=website,
        rating=None,
        user_ratings_total=0,
        keyword=keyword,
        maps_url="",
    )


def search_pages_jaunes(
    keyword: str, location: str, max_results: int = 20
) -> List[Prospect]:
    """
    Scrape les résultats Pages Jaunes pour un mot-clé et une ville.

    Args:
        keyword:     Mot-clé métier (ex: "boulangerie").
        location:    Ville (ex: "Lyon").
        max_results: Nombre maximum de prospects à retourner.

    Returns:
        Liste d'objets Prospect.
    """
    if BeautifulSoup is None:
        logger.error("beautifulsoup4 n'est pas installé. Impossible de scraper Pages Jaunes.")
        return []

    logger.info("📖 Pages Jaunes : '%s' à %s", keyword, location)

    prospects: List[Prospect] = []

    for page in range(1, MAX_PAGES + 1):
        if len(prospects) >= max_results:
            break

        html = _fetch_page_html(keyword, location, page)
        if html is None:
            break

        soup = BeautifulSoup(html, "lxml")
        articles = _parse_articles(soup)

        if not articles:
            logger.warning(
                "Pages Jaunes : pas de résultats (rendu JS probable)"
            )
            break

        for article in articles:
            if len(prospects) >= max_results:
                break
            prospect = _parse_prospect(article, keyword)
            if prospect:
                prospects.append(prospect)

        # Rate limiting entre les pages
        if page < MAX_PAGES:
            time.sleep(2)

    logger.info("  → %d résultat(s) Pages Jaunes", len(prospects))
    return prospects
