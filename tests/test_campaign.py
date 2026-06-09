"""
tests/test_campaign.py — Tests d'intégration multi-villes avec rapport de métriques.

Ce script lance de vraies requêtes API sur plusieurs combinaisons
ville × mots-clés × profil et génère un rapport JSON + affichage console.

NÉCESSITE une clé Google Places valide dans .env ou la variable d'env.

Usage :
  python tests/test_campaign.py
  python tests/test_campaign.py --villes "Paris,Lyon,Bordeaux" --max 3
"""

import sys
import os
import json
import time
import argparse
from datetime import datetime
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from config import Config
from services.google_maps import search_prospects, Prospect
from services.analyzer import analyze_prospect
from services.mailer import enrich_with_email


# ---------------------------------------------------------------------------
# Campagnes de test — combinaisons à tester
# ---------------------------------------------------------------------------

CAMPAGNES = [
    {
        "nom": "Dev Web — Lyon",
        "ville": "Lyon, France",
        "keywords": ["restaurant", "boulangerie", "coiffeur"],
        "profil": "dev_web",
    },
    {
        "nom": "Dev Web — Paris 13",
        "ville": "Paris 13, France",
        "keywords": ["restaurant", "cabinet dentaire"],
        "profil": "dev_web",
    },
    {
        "nom": "Dev Web — Bordeaux",
        "ville": "Bordeaux, France",
        "keywords": ["garage automobile", "agence immobilière"],
        "profil": "dev_web",
    },
    {
        "nom": "Photographe — Paris",
        "ville": "Paris, France",
        "keywords": ["restaurant gastronomique", "hôtel"],
        "profil": "photographe",
    },
    {
        "nom": "SMM — Marseille",
        "ville": "Marseille, France",
        "keywords": ["boutique", "salon de coiffure"],
        "profil": "social_media",
    },
]


# ---------------------------------------------------------------------------
# Runner de campagne
# ---------------------------------------------------------------------------

def run_campagne(campagne: dict, max_results: int = 3) -> dict:
    """
    Lance une campagne de test et retourne les métriques.

    Retourne un dict avec :
      - nom, ville, profil
      - total_prospects, avec_site, sans_site
      - emails_trouvés, mobiles_trouvés
      - score_moyen, score_min, score_max
      - issues_les_plus_frequentes
      - duree_secondes
      - erreurs
    """
    start = time.perf_counter()
    erreurs = []
    all_prospects: List[Prospect] = []
    seen = set()

    # Config temporaire pour cette campagne
    cfg = Config()
    cfg.search_location = campagne["ville"]
    cfg.max_results_per_keyword = max_results

    import services.google_maps as gm
    import services.analyzer as an
    gm.config = cfg
    an.config = cfg

    print(f"\n  🔍 {campagne['nom']} — {campagne['ville']}")

    # Collecte
    for kw in campagne["keywords"]:
        try:
            prospects = search_prospects(kw)
            for p in prospects:
                if p.place_id not in seen:
                    seen.add(p.place_id)
                    all_prospects.append(p)
            print(f"     '{kw}' → {len(prospects)} prospect(s)")
        except Exception as e:
            erreurs.append(f"Collecte '{kw}' : {str(e)}")
            print(f"     ❌ '{kw}' : {e}")

    if not all_prospects:
        return {
            "nom": campagne["nom"],
            "ville": campagne["ville"],
            "profil": campagne["profil"],
            "total_prospects": 0,
            "erreurs": erreurs,
            "duree_secondes": round(time.perf_counter() - start, 1),
        }

    # Analyse
    print(f"  🔬 Analyse de {len(all_prospects)} prospect(s)…")
    for p in all_prospects:
        try:
            analyze_prospect(p)
            enrich_with_email(p)
        except Exception as e:
            erreurs.append(f"Analyse {p.name} : {str(e)}")

    # Calcul des métriques
    avec_site    = [p for p in all_prospects if p.has_website()]
    sans_site    = [p for p in all_prospects if not p.has_website()]
    emails_ok    = [p for p in all_prospects if p.email]
    mobiles_ok   = [p for p in all_prospects if p.phone and (
        p.phone.replace(" ", "").startswith("06") or
        p.phone.replace(" ", "").startswith("07")
    )]

    scores = [p.score for p in all_prospects]
    score_moyen = round(sum(scores) / len(scores), 1) if scores else 0

    # Issues les plus fréquentes
    all_issues = []
    for p in all_prospects:
        for issue in p.issues:
            all_issues.append(issue.split("→")[0].strip())
    from collections import Counter
    top_issues = [
        {"issue": issue, "count": count}
        for issue, count in Counter(all_issues).most_common(5)
    ]

    duree = round(time.perf_counter() - start, 1)

    metriques = {
        "nom": campagne["nom"],
        "ville": campagne["ville"],
        "profil": campagne["profil"],
        "keywords": campagne["keywords"],
        "total_prospects": len(all_prospects),
        "avec_site": len(avec_site),
        "sans_site": len(sans_site),
        "taux_sans_site_pct": round(len(sans_site) / len(all_prospects) * 100, 1),
        "emails_trouvés": len(emails_ok),
        "taux_email_pct": round(len(emails_ok) / len(all_prospects) * 100, 1),
        "mobiles_trouvés": len(mobiles_ok),
        "taux_mobile_pct": round(len(mobiles_ok) / len(all_prospects) * 100, 1),
        "score_moyen": score_moyen,
        "score_min": min(scores) if scores else 0,
        "score_max": max(scores) if scores else 0,
        "prospects_score_critique": len([p for p in all_prospects if p.score < 40]),
        "top_issues": top_issues,
        "duree_secondes": duree,
        "erreurs": erreurs,
        "top_opportunites": [
            {
                "name": p.name,
                "score": p.score,
                "phone": p.phone,
                "email": p.email,
                "issues_count": len(p.issues),
            }
            for p in sorted(all_prospects, key=lambda x: x.score)[:3]
        ],
    }

    # Affichage console
    print(f"  ✅ {len(all_prospects)} prospects | "
          f"📧 {len(emails_ok)} emails ({metriques['taux_email_pct']}%) | "
          f"📱 {len(mobiles_ok)} mobiles | "
          f"Score moy. {score_moyen}/100 | "
          f"⏱ {duree}s")

    return metriques


# ---------------------------------------------------------------------------
# Rapport final
# ---------------------------------------------------------------------------

def print_rapport(resultats: List[dict]) -> None:
    """Affiche un tableau récapitulatif dans la console."""
    print("\n")
    print("=" * 80)
    print("📊  RAPPORT DE CAMPAGNE — RÉSUMÉ")
    print("=" * 80)

    total_prospects = sum(r.get("total_prospects", 0) for r in resultats)
    total_emails    = sum(r.get("emails_trouvés", 0) for r in resultats)
    total_mobiles   = sum(r.get("mobiles_trouvés", 0) for r in resultats)
    total_sans_site = sum(r.get("sans_site", 0) for r in resultats)
    total_duree     = sum(r.get("duree_secondes", 0) for r in resultats)

    print(f"\n  Total prospects analysés : {total_prospects}")
    print(f"  Sans site web            : {total_sans_site} ({round(total_sans_site/max(total_prospects,1)*100,1)}%)")
    print(f"  Emails trouvés           : {total_emails} ({round(total_emails/max(total_prospects,1)*100,1)}%)")
    print(f"  Mobiles trouvés          : {total_mobiles} ({round(total_mobiles/max(total_prospects,1)*100,1)}%)")
    print(f"  Durée totale             : {round(total_duree, 1)}s")

    print("\n  Par campagne :")
    print(f"  {'Campagne':<30} {'Total':>6} {'Sans site':>10} {'Emails':>8} {'Mobiles':>8} {'Score moy':>10}")
    print("  " + "-" * 74)
    for r in resultats:
        print(
            f"  {r['nom']:<30} "
            f"{r.get('total_prospects',0):>6} "
            f"{r.get('sans_site',0):>8} ({r.get('taux_sans_site_pct',0)}%) "
            f"{r.get('emails_trouvés',0):>5} ({r.get('taux_email_pct',0)}%) "
            f"{r.get('score_moyen',0):>8}/100"
        )

    print("\n  🏆 TOP ISSUES détectées toutes campagnes confondues :")
    all_issues = {}
    for r in resultats:
        for item in r.get("top_issues", []):
            key = item["issue"]
            all_issues[key] = all_issues.get(key, 0) + item["count"]
    for issue, count in sorted(all_issues.items(), key=lambda x: -x[1])[:7]:
        bar = "█" * min(count, 20)
        print(f"    {count:>3}x  {bar}  {issue[:60]}")

    print("\n  🔴 TOP 5 OPPORTUNITÉS (score le plus bas) :")
    top_opps = []
    for r in resultats:
        for opp in r.get("top_opportunites", []):
            opp["campagne"] = r["nom"]
            top_opps.append(opp)
    top_opps.sort(key=lambda x: x["score"])
    for i, opp in enumerate(top_opps[:5], 1):
        email_str = f"📧 {opp['email']}" if opp.get("email") else "📧 -"
        phone_str = f"📞 {opp['phone']}" if opp.get("phone") else "📞 -"
        print(f"    {i}. {opp['name']} [{opp['campagne']}] — score {opp['score']}/100 | {email_str} | {phone_str}")

    print("\n" + "=" * 80)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tests d'intégration multi-campagnes")
    parser.add_argument(
        "--max", type=int, default=3,
        help="Nombre max de prospects par mot-clé (défaut: 3)"
    )
    parser.add_argument(
        "--campagne", type=str, default=None,
        help="Nom partiel d'une campagne spécifique à tester (ex: 'Lyon')"
    )
    args = parser.parse_args()

    # Vérifie la clé API
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        print("❌ GOOGLE_PLACES_API_KEY manquante dans .env")
        sys.exit(1)

    # Filtre les campagnes si demandé
    campagnes = CAMPAGNES
    if args.campagne:
        campagnes = [c for c in CAMPAGNES if args.campagne.lower() in c["nom"].lower()]
        if not campagnes:
            print(f"❌ Aucune campagne trouvée pour '{args.campagne}'")
            sys.exit(1)

    print(f"\n🚀 Lancement de {len(campagnes)} campagne(s) — max {args.max} prospects/kw")
    print(f"   Clé API : {api_key[:10]}...")

    resultats = []
    for campagne in campagnes:
        try:
            metriques = run_campagne(campagne, max_results=args.max)
            resultats.append(metriques)
            time.sleep(1)  # Petite pause entre les campagnes
        except Exception as e:
            print(f"  ❌ Campagne '{campagne['nom']}' échouée : {e}")
            resultats.append({
                "nom": campagne["nom"],
                "erreur_critique": str(e),
                "total_prospects": 0,
            })

    # Rapport console
    print_rapport(resultats)

    # Sauvegarde du rapport JSON
    os.makedirs("output", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rapport_path = os.path.join("output", f"rapport_test_{ts}.json")
    with open(rapport_path, "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Rapport complet sauvegardé : {rapport_path}\n")
