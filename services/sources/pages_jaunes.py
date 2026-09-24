"""
services/sources/pages_jaunes.py — Scraper Pages Jaunes public.

URL: https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui={keyword}&ou={location}&page={page}
"""

from __future__ import annotations

# 📘 hashlib : fonctions de hachage (md5…) ; sert ici à fabriquer un identifiant stable.
import hashlib
import time
from typing import List, Optional

import requests

# 📘 Import optionnel : si beautifulsoup4 n'est pas installé, on met BeautifulSoup à None au lieu
# 📘 de planter ; search_pages_jaunes le vérifie et renvoie une liste vide.
# 📘 BeautifulSoup : librairie qui transforme du HTML en arbre qu'on peut fouiller (find, select).
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore

# 📘 ⚠️ `config` est figé à l'import (au démarrage de l'appli) : pipeline.py ne le remplace pas ici.
# 📘   Sans conséquence : seul config.request_timeout (fixe, 10 s) est lu. `logger` non plus n'est
# 📘   pas remplacé : ces logs vont dans la console, pas dans le journal de l'UI.
from config import config, logger
from services.google_maps import Prospect


# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : "scraper" (lire automatiquement) les pages de résultats pagesjaunes.fr et en extraire
# 📘   nom, adresse, téléphone et site pour fabriquer des Prospect. Pas d'API : du HTML brut.
# 📘 Appelé par : pipeline.py (search_pages_jaunes, source "pages_jaunes"), via __init__.py.
# 📘 Appelle : www.pagesjaunes.fr (HTTP GET avec en-têtes de navigateur), BeautifulSoup + lxml.
# 📘 Concepts Python à retenir ici : import optionnel, en-têtes HTTP, BeautifulSoup (find,
# 📘   find_all, select), lambda comme filtre, `a or b or c`, hashlib.md5, pagination.
# 📘 HEADERS : on se fait passer pour Chrome (User-Agent), sinon le site bloque souvent les robots.
# 💡 Fragile par nature : si Pages Jaunes change son HTML (ou le génère en JavaScript), le parseur
# 💡   ne trouve plus rien. Vérifier aussi les CGU du site, qui encadrent l'extraction automatisée
# 💡   de données (risque juridique et de blocage d'IP).
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
# 📘 On lit au maximum 5 pages de résultats par mot-clé.
MAX_PAGES = 5


def _fetch_page_html(keyword: str, location: str, page: int) -> Optional[str]:
    """Récupère le HTML d'une page de résultats avec retry (2s, 4s, 8s)."""
    params = {
        "quoiqui": keyword,
        "ou": location,
        "page": page,
    }
    # 📘 3 essais, avec pause de 2 s puis 4 s entre eux ; None si les 3 échouent.
    for attempt in range(3):
        try:
            resp = requests.get(
                BASE_URL,
                params=params,
                headers=HEADERS,
                timeout=config.request_timeout,
            )
            resp.raise_for_status()
            # 📘 resp.text : le contenu de la réponse sous forme de texte (ici du HTML).
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


# 📘 get_text(strip=True) : tout le texte visible d'une balise, espaces du bord retirés.
def _extract_text(tag) -> str:
    """Extrait le texte d'un tag BeautifulSoup, retourne '' si None."""
    if tag is None:
        return ""
    return tag.get_text(strip=True)


def _parse_articles(soup) -> list:
    # 📘 Plusieurs "sélecteurs" tentés l'un après l'autre : si le 1er ne trouve rien, on essaie le
    # 📘 suivant. Le `class_=lambda c: ...` passe une mini-fonction qui dit si la classe CSS convient.
    # 📘 ("class" est un mot réservé de Python, d'où le `class_` avec un tiret bas.)
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
    # 📘 soup.select("[class*='bi-generic']") : sélecteur CSS, "classe CONTENANT bi-generic".
    articles = soup.select("[class*='bi-generic']")
    return articles


def _parse_prospect(article, keyword: str) -> Optional[Prospect]:
    """Extrait les informations d'un article et retourne un Prospect."""
    # Nom
    # 📘 `a or b or c or d` : la 1re balise trouvée (find renvoie None si rien → on essaie la suivante).
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
    # 📘 href=lambda h: ... : on cherche un lien <a> dont l'adresse commence par "tel:".
    # 📘 tag["href"] lit l'attribut href de la balise, comme dans un dict.
    phone_tag = article.find("a", href=lambda h: h and h.startswith("tel:"))
    if phone_tag:
        phone = phone_tag["href"].replace("tel:", "").strip()

    # Site web (premier lien externe non pagesjaunes)
    website = None
    # 📘 Heuristique : le premier lien http qui ne pointe pas vers pagesjaunes est supposé être le
    # 📘 site de l'entreprise (peut parfois être un lien de réseau social ou de partenaire).
    for link in article.find_all("a", href=True):
        href = link["href"]
        if href.startswith("http") and "pagesjaunes" not in href:
            website = href
            break

    # 📘 Pas d'identifiant fourni : on en fabrique un stable en hachant nom + adresse (md5 → texte
    # 📘 hexadécimal, on garde 16 caractères). Même entreprise = même id à chaque recherche.
    # 📘 .encode() : md5 travaille sur des octets (bytes), pas sur du texte (str).
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
    # 📘 `is None` : la bonne façon de tester None en Python (plutôt que `== None`).
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

        # 📘 "lxml" = moteur de lecture HTML rapide (paquet lxml, présent dans requirements.txt). S'il
        # 📘 manquait, BeautifulSoup lèverait une erreur non attrapée ici.
        soup = BeautifulSoup(html, "lxml")
        articles = _parse_articles(soup)

        # 📘 Aucun article trouvé → on arrête : soit plus de résultats, soit le site a servi une page
        # 📘 vide (contenu chargé en JavaScript, ou page anti-robot) → message "rendu JS probable".
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

        # 📘 Pause de 2 s entre deux pages pour ne pas surcharger le site (et moins risquer un blocage).
        # 💡 Un requests.Session() réutilisé entre les pages garderait cookies et connexion ouverte :
        # 💡   plus rapide et plus proche d'un vrai navigateur.
        # Rate limiting entre les pages
        if page < MAX_PAGES:
            time.sleep(2)

    logger.info("  → %d résultat(s) Pages Jaunes", len(prospects))
    return prospects
