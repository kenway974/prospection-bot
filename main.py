"""
main.py — Point d'entrée en ligne de commande.

Alternative à l'interface Streamlit (app.py).
Utile pour automatiser la prospection via un planificateur de tâches (cron, Task Scheduler).

Workflow complet :
  1. Collecte      → Google Places → liste de prospects uniques
  2. Analyse       → inspection du site web de chaque prospect
  3. Email         → génération du brouillon cold email personnalisé
  4. Tri           → classement par score croissant (meilleures opportunités en premier)
  5. Sauvegarde    → JSON + CSV + fichiers .txt par prospect dans output/
  6. Notion        → sync vers la base CRM Notion (si clé configurée)
  7. SMS           → envoi via Brevo (si clé configurée)

Usage :
  python main.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime
from typing import List

from config import config, logger
from services.google_maps import Prospect, search_prospects
from services.analyzer import analyze_prospect
from services.mailer import enrich_with_email
from services.notion_sync import sync_all
from services.sms import send_all_sms
from history_manager import load_contacted_ids, mark_as_contacted


# ---------------------------------------------------------------------------
# Fonctions de sauvegarde locale
# ---------------------------------------------------------------------------

def _output_path(ext: str) -> str:
    """Génère un chemin de fichier horodaté dans le dossier output/."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(config.output_dir, f"prospects_{timestamp}.{ext}")


def save_json(prospects: List[Prospect], path: str) -> None:
    """Sauvegarde tous les prospects avec leurs données complètes en JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in prospects], f, ensure_ascii=False, indent=2)
    logger.info("💾 JSON sauvegardé : %s", path)


def save_csv(prospects: List[Prospect], path: str) -> None:
    """Sauvegarde un CSV lisible dans Excel (encodage UTF-8 avec BOM)."""
    if not prospects:
        return
    fieldnames = [
        "name", "keyword", "address", "phone", "email", "website",
        "rating", "user_ratings_total", "score",
        "issues_count", "issues_summary", "maps_url",
    ]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in prospects:
            writer.writerow({
                "name": p.name,
                "keyword": p.keyword,
                "address": p.address,
                "phone": p.phone or "",
                "email": p.email or "",
                "website": p.website or "",
                "rating": p.rating or "",
                "user_ratings_total": p.user_ratings_total,
                "score": p.score,
                "issues_count": len(p.issues),
                "issues_summary": " | ".join(p.issues[:3]),
                "maps_url": p.maps_url,
            })
    logger.info("📊 CSV sauvegardé  : %s", path)


def save_email_drafts(prospects: List[Prospect], base_path: str) -> None:
    """Sauvegarde un fichier .txt par prospect dans un sous-dossier _emails/."""
    drafts_dir = base_path.replace(".json", "_emails")
    os.makedirs(drafts_dir, exist_ok=True)
    for p in prospects:
        if not p.email_draft:
            continue
        # Nom de fichier sécurisé (pas de caractères spéciaux)
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in p.name)
        filepath = os.path.join(drafts_dir, f"{safe_name}.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(p.email_draft)
    logger.info("✉️  Brouillons emails sauvegardés dans : %s/", drafts_dir)


# ---------------------------------------------------------------------------
# Workflow principal
# ---------------------------------------------------------------------------

def run() -> None:
    logger.info("=" * 60)
    logger.info("🚀 DÉMARRAGE — Prospection B2B automatisée")
    logger.info("   Zone     : %s", config.search_location)
    logger.info("   Mots-clés: %s", ", ".join(config.search_keywords))
    logger.info("   Max/kw   : %d résultats", config.max_results_per_keyword)
    logger.info("=" * 60)

    # Vérifie que la clé Google est bien configurée avant de démarrer
    try:
        config.validate()
    except ValueError as exc:
        logger.critical("❌ %s", exc)
        sys.exit(1)

    all_prospects: List[Prospect] = []
    seen_place_ids: set[str] = set()

    # 1. COLLECTE — Google Places pour chaque mot-clé
    for keyword in config.search_keywords:
        prospects = search_prospects(keyword)
        for p in prospects:
            # Déduplication par place_id pour éviter les doublons entre mots-clés
            if p.place_id not in seen_place_ids:
                seen_place_ids.add(p.place_id)
                all_prospects.append(p)

    logger.info("")
    logger.info("📋 %d prospect(s) uniques collectés.", len(all_prospects))

    if not all_prospects:
        logger.warning("Aucun prospect trouvé. Vérifiez vos critères de recherche.")
        sys.exit(0)

    # 1b. DÉDUPLICATION — exclure les prospects déjà contactés lors de sessions précédentes
    already_contacted = load_contacted_ids()
    before_dedup = len(all_prospects)
    all_prospects = [p for p in all_prospects if p.place_id not in already_contacted]
    skipped = before_dedup - len(all_prospects)
    if skipped:
        logger.info("⏭️  %d prospect(s) déjà contacté(s) ignoré(s).", skipped)

    if not all_prospects:
        logger.warning("Tous les prospects ont déjà été contactés. Élargissez votre recherche.")
        sys.exit(0)

    # 2. ANALYSE — inspection du site web + scraping email
    logger.info("")
    logger.info("🔬 Analyse des sites web…")
    all_prospects = [analyze_prospect(p) for p in all_prospects]

    # 2b. FILTRAGE PAR SEUIL — on ne contacte que les prospects avec assez d'opportunités
    threshold = config.contact_score_threshold
    contactable = [p for p in all_prospects if p.score <= threshold]
    filtered_out = len(all_prospects) - len(contactable)
    if filtered_out:
        logger.info(
            "🚫 %d prospect(s) ignoré(s) (score > %d/100 — site trop bon pour notre offre).",
            filtered_out, threshold,
        )
    all_prospects = contactable

    if not all_prospects:
        logger.warning(
            "Aucun prospect sous le seuil de %d/100. "
            "Réduisez CONTACT_SCORE_THRESHOLD ou changez de zone/mots-clés.", threshold,
        )
        sys.exit(0)

    # 3. EMAILS — génération des brouillons personnalisés
    logger.info("")
    logger.info("✉️  Génération des brouillons d'emails…")
    all_prospects = [enrich_with_email(p) for p in all_prospects]

    # 4. TRI — les prospects avec le plus d'opportunités (score bas) en premier
    all_prospects.sort(key=lambda p: p.score)

    # 5. SAUVEGARDE LOCALE
    json_path = _output_path("json")
    csv_path  = _output_path("csv")
    save_json(all_prospects, json_path)
    save_csv(all_prospects, csv_path)
    save_email_drafts(all_prospects, json_path)

    # 6. SYNC NOTION — crée une fiche par prospect (ignoré si clé absente)
    sync_all(all_prospects)

    # 7. SMS BREVO — envoie un SMS aux numéros mobiles (ignoré si clé absente)
    if config.brevo_api_key:
        send_all_sms(all_prospects)

    # 8. MARQUAGE — enregistre les place_id pour éviter les doublons aux prochains runs
    mark_as_contacted([p.place_id for p in all_prospects])

    # Résumé final
    no_site  = sum(1 for p in all_prospects if not p.has_website())
    critical = sum(1 for p in all_prospects if p.score < 40)
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ TERMINÉ")
    logger.info("   Total prospects   : %d", len(all_prospects))
    logger.info("   Sans site web     : %d  (opportunité création)", no_site)
    logger.info("   Score < 40/100    : %d  (priorité haute)", critical)
    logger.info("   Résultats dans    : %s/", config.output_dir)
    logger.info("=" * 60)

    # Top 3 des meilleures opportunités à contacter en priorité
    logger.info("")
    logger.info("🏆 TOP OPPORTUNITÉS :")
    for i, p in enumerate(all_prospects[:3], 1):
        logger.info(
            "  %d. %s — score %d/100 — %d problème(s)",
            i, p.name, p.score, len(p.issues),
        )
        if p.issues:
            logger.info("     ↳ %s", p.issues[0].split("→")[0].strip())


if __name__ == "__main__":
    run()
