"""
run_tests.py — Lance tous les tests du projet et affiche un rapport.

Usage :
  python run_tests.py           → tests unitaires uniquement (rapides, sans API)
  python run_tests.py --all     → unitaires + campagnes multi-villes (avec API)
  python run_tests.py --unit    → unitaires seulement
  python run_tests.py --campaign → campagnes seulement
  python run_tests.py --campaign --max 2 → campagnes avec 2 prospects max/kw
"""

import sys
import os
import unittest
import argparse
import time

sys.path.insert(0, os.path.dirname(__file__))


def run_unit_tests() -> bool:
    """Lance les tests unitaires (analyzer, mailer, profiles). Retourne True si tout passe."""
    print("\n" + "=" * 60)
    print("🧪 TESTS UNITAIRES")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Charge les modules de tests unitaires
    for module in ["tests.test_analyzer", "tests.test_mailer", "tests.test_profiles", "tests.test_service_profiles"]:
        try:
            suite.addTests(loader.loadTestsFromName(module))
        except Exception as e:
            print(f"❌ Impossible de charger {module} : {e}")
            return False

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)

    print(f"\n{'✅ TOUS LES TESTS PASSENT' if result.wasSuccessful() else '❌ DES TESTS ÉCHOUENT'}")
    print(f"   Tests : {result.testsRun} | Échecs : {len(result.failures)} | Erreurs : {len(result.errors)}")

    return result.wasSuccessful()


def run_campaign_tests(max_results: int = 3, campagne_filter: str = None) -> None:
    """Lance les tests d'intégration multi-villes avec rapport de métriques."""
    print("\n" + "=" * 60)
    print("🌍 TESTS D'INTÉGRATION — CAMPAGNES MULTI-VILLES")
    print("=" * 60)

    # Import ici pour ne pas charger les modules API si on ne fait que les tests unitaires
    from tests.test_campaign import CAMPAGNES, run_campagne, print_rapport
    import json
    from datetime import datetime

    campagnes = CAMPAGNES
    if campagne_filter:
        campagnes = [c for c in CAMPAGNES if campagne_filter.lower() in c["nom"].lower()]

    resultats = []
    for campagne in campagnes:
        try:
            metriques = run_campagne(campagne, max_results=max_results)
            resultats.append(metriques)
            time.sleep(1)
        except Exception as e:
            print(f"  ❌ '{campagne['nom']}' échouée : {e}")
            resultats.append({"nom": campagne["nom"], "total_prospects": 0, "erreur": str(e)})

    print_rapport(resultats)

    # Sauvegarde
    os.makedirs("output", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join("output", f"rapport_test_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)
    print(f"💾 Rapport JSON : {path}")


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lance les tests du projet Prospection B2B")
    parser.add_argument("--all",      action="store_true", help="Unitaires + campagnes")
    parser.add_argument("--unit",     action="store_true", help="Tests unitaires uniquement")
    parser.add_argument("--campaign", action="store_true", help="Tests de campagnes uniquement")
    parser.add_argument("--max",      type=int, default=3,  help="Max prospects/kw (campagnes)")
    parser.add_argument("--filtre",   type=str, default=None, help="Filtrer une campagne (ex: 'Lyon')")
    args = parser.parse_args()

    # Par défaut : unitaires seulement
    if not any([args.all, args.unit, args.campaign]):
        args.unit = True

    ok = True

    if args.unit or args.all:
        ok = run_unit_tests()

    if args.campaign or args.all:
        api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
        if not api_key:
            print("\n❌ GOOGLE_PLACES_API_KEY manquante — impossible de lancer les campagnes.")
            print("   Ajoutez la clé dans votre .env et relancez avec --campaign")
            sys.exit(1)
        run_campaign_tests(max_results=args.max, campagne_filter=args.filtre)

    sys.exit(0 if ok else 1)
