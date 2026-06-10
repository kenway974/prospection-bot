"""
main.py — Point d'entrée en ligne de commande.

Alternative à l'interface Streamlit (app.py).
Utile pour automatiser la prospection via un planificateur de tâches (cron, Task Scheduler).

Workflow complet :
  1. Collecte      → Google Places → liste de prospects uniques
  1b. Filtres      → note Google minimum + déduplication inter-sessions
  2. Analyse       → inspection du site web (parallèle, 5 workers par défaut)
  2b. Seuil        → on exclut les sites trop bons (score > CONTACT_SCORE_THRESHOLD)
  3. Email         → génération du brouillon cold email personnalisé
  4. Tri           → classement par score croissant (meilleures opportunités en premier)
  5. Sauvegarde    → JSON + CSV + fichiers .txt par prospect dans output/
  6. Notion        → sync vers la base CRM Notion (si clé configurée)
  7. SMS           → envoi via Brevo (si clé configurée)
  8. Marquage      → enregistre les place_id dans contacted_place_ids.json

Mode relance :
  python main.py --followup   → génère les emails de relance pour les contacts sans réponse

Variables d'environnement clés (dans .env) :
  MIN_RATING               → note Google minimum (défaut : 3.0)
  CONTACT_SCORE_THRESHOLD  → score max pour contacter (défaut : 70)
  ANALYSIS_WORKERS         → parallélisation (défaut : 5)
  FOLLOWUP_DELAY_DAYS      → délai avant relance en jours (défaut : 5)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List

from config import config, logger
from services.google_maps import Prospect, search_prospects
from services.analyzer import analyze_prospect
from services.mailer import enrich_with_email, enrich_with_followup
from services.notion_sync import sync_all
from services.sms import send_all_sms
from history_manager import (
    load_contacted_ids,
    mark_as_contacted,
    get_due_followups,
    mark_followup_sent,
)


# ---------------------------------------------------------------------------
# Fonctions de sauvegarde locale
# ---------------------------------------------------------------------------

def _output_path(ext: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(config.output_dir, f"prospects_{timestamp}.{ext}")


def save_json(prospects: List[Prospect], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in prospects], f, ensure_ascii=False, indent=2)
    logger.info("💾 JSON sauvegardé : %s", path)


def save_csv(prospects: List[Prospect], path: str) -> None:
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
    drafts_dir = base_path.replace(".json", "_emails")
    os.makedirs(drafts_dir, exist_ok=True)
    for p in prospects:
        if not p.email_draft:
            continue
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in p.name)
        filepath = os.path.join(drafts_dir, f"{safe_name}.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(p.email_draft)
    logger.info("✉️  Brouillons emails sauvegardés dans : %s/", drafts_dir)


# ---------------------------------------------------------------------------
# Mode relance
# ---------------------------------------------------------------------------

def run_followup() -> None:
    """Génère et sauvegarde les emails de relance pour les contacts sans réponse."""
    logger.info("=" * 60)
    logger.info("🔄 MODE RELANCE — génération des emails de suivi")
    logger.info("   Délai   : %d jours sans réponse", config.followup_delay_days)
    logger.info("=" * 60)

    due = get_due_followups(config.followup_delay_days)
    if not due:
        logger.info("✅ Aucun contact à relancer pour l'instant.")
        return

    logger.info("📋 %d contact(s) à relancer.", len(due))
    os.makedirs(config.output_dir, exist_ok=True)
    followup_dir = os.path.join(config.output_dir, f"relances_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(followup_dir, exist_ok=True)

    for contact in due:
        # Reconstruit un Prospect minimal pour générer l'email
        p = Prospect(
            place_id=contact["place_id"],
            name=contact["name"],
            address="",
            phone=None,
            website=None,
            rating=None,
            user_ratings_total=0,
            keyword="",
            email=contact.get("email") or None,
        )
        p = enrich_with_followup(p)

        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in p.name)
        filepath = os.path.join(followup_dir, f"{safe_name}.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(p.email_draft)

        mark_followup_sent(p.place_id)
        logger.info("  🔄 Relance générée : %s", p.name)

    logger.info("")
    logger.info("✅ %d email(s) de relance sauvegardés dans : %s/", len(due), followup_dir)


# ---------------------------------------------------------------------------
# Workflow principal
# ---------------------------------------------------------------------------

def run() -> None:
    logger.info("=" * 60)
    logger.info("🚀 DÉMARRAGE — Prospection B2B automatisée")
    logger.info("   Zone        : %s", config.search_location)
    logger.info("   Mots-clés   : %s", ", ".join(config.search_keywords))
    logger.info("   Max/kw      : %d résultats", config.max_results_per_keyword)
    logger.info("   Note min    : %.1f/5", config.min_rating)
    logger.info("   Seuil score : ≤ %d/100", config.contact_score_threshold)
    logger.info("   Workers     : %d", config.analysis_workers)
    logger.info("=" * 60)

    try:
        config.validate()
    except ValueError as exc:
        logger.critical("❌ %s", exc)
        sys.exit(1)

    all_prospects: List[Prospect] = []
    seen_place_ids: set[str] = set()

    # 1. COLLECTE — Google Places pour chaque mot-clé
    for keyword in config.search_keywords:
        for p in search_prospects(keyword):
            if p.place_id not in seen_place_ids:
                seen_place_ids.add(p.place_id)
                all_prospects.append(p)

    logger.info("")
    logger.info("📋 %d prospect(s) uniques collectés.", len(all_prospects))

    if not all_prospects:
        logger.warning("Aucun prospect trouvé. Vérifiez vos critères de recherche.")
        sys.exit(0)

    # 1b. FILTRE NOTE GOOGLE
    before = len(all_prospects)
    all_prospects = [
        p for p in all_prospects
        if p.rating is None or p.rating >= config.min_rating
    ]
    excluded = before - len(all_prospects)
    if excluded:
        logger.info("⭐ %d prospect(s) exclus (note < %.1f/5).", excluded, config.min_rating)

    # 1c. DÉDUPLICATION inter-sessions
    already_contacted = load_contacted_ids()
    before_dedup = len(all_prospects)
    all_prospects = [p for p in all_prospects if p.place_id not in already_contacted]
    skipped = before_dedup - len(all_prospects)
    if skipped:
        logger.info("⏭️  %d prospect(s) déjà contacté(s) ignoré(s).", skipped)

    if not all_prospects:
        logger.warning("Aucun nouveau prospect à traiter. Élargissez votre recherche.")
        sys.exit(0)

    # 2. ANALYSE — parallèle via ThreadPoolExecutor
    logger.info("")
    logger.info("🔬 Analyse des sites web… (%d workers)", config.analysis_workers)
    analyzed: List[Prospect] = []
    with ThreadPoolExecutor(max_workers=config.analysis_workers) as executor:
        futures = {executor.submit(analyze_prospect, p): p for p in all_prospects}
        for future in as_completed(futures):
            try:
                analyzed.append(future.result())
            except Exception as exc:
                p = futures[future]
                logger.error("  ❌ Erreur analyse %s : %s", p.name, exc)
    all_prospects = analyzed

    # 2b. FILTRAGE PAR SEUIL DE SCORE
    threshold = config.contact_score_threshold
    contactable = [p for p in all_prospects if p.score <= threshold]
    filtered_out = len(all_prospects) - len(contactable)
    if filtered_out:
        logger.info(
            "🚫 %d prospect(s) ignoré(s) (score > %d/100 — site trop bon).",
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

    # 4. TRI — meilleures opportunités (score bas) en premier
    all_prospects.sort(key=lambda p: p.score)

    # 5. SAUVEGARDE LOCALE
    json_path = _output_path("json")
    csv_path  = _output_path("csv")
    save_json(all_prospects, json_path)
    save_csv(all_prospects, csv_path)
    save_email_drafts(all_prospects, json_path)

    # 6. SYNC NOTION
    sync_all(all_prospects)

    # 7. SMS BREVO
    if config.brevo_api_key:
        send_all_sms(all_prospects)

    # 8. MARQUAGE — enregistre pour éviter les doublons aux prochains runs
    mark_as_contacted(all_prospects)

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
    parser = argparse.ArgumentParser(description="Prospection B2B automatisée")
    parser.add_argument(
        "--followup",
        action="store_true",
        help="Mode relance : génère les emails pour les contacts sans réponse",
    )
    args = parser.parse_args()

    if args.followup:
        run_followup()
    else:
        run()
