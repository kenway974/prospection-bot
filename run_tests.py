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

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : SCRIPT en ligne de commande qui lance une sélection de tests unitaires et/ou
# 📘   des « campagnes » réelles (appels à l'API Google) avec un rapport de métriques.
# 📘 Appelé par : toi, dans un terminal (`python run_tests.py ...`, cf. README.md).
# 📘 Appelle : unittest (bibliothèque standard de tests), tests/test_analyzer.py,
# 📘   tests/test_mailer.py, tests/test_profiles.py, tests/test_service_profiles.py,
# 📘   tests/test_campaign.py (CAMPAGNES, run_campagne, print_rapport).
# 📘 Concepts Python à retenir ici : sys.path, argparse (options de ligne de commande),
# 📘   unittest.TestLoader/TestSuite/TextTestRunner, import local dans une fonction,
# 📘   `if __name__ == "__main__":`, sys.exit (code de retour 0 = succès).
# 📘 Autre façon de lancer TOUS les tests : `python -m pytest` (pytest est dans
# 📘   requirements-dev.txt) ou `python -m unittest discover tests`.

# 📘 sys.path = la liste des dossiers où Python cherche les modules à importer. On y ajoute
# 📘   en 1re position le dossier de ce script, pour que `import tests.xxx`, `import offers`...
# 📘   fonctionnent même si tu lances le script depuis un autre dossier.
sys.path.insert(0, os.path.dirname(__file__))


def run_unit_tests() -> bool:
    """Lance les tests unitaires (analyzer, mailer, profiles). Retourne True si tout passe."""
    print("\n" + "=" * 60)  # 📘 "=" * 60 répète le caractère 60 fois (ligne de séparation)
    print("🧪 TESTS UNITAIRES")
    print("=" * 60)

    # 📘 unittest en 3 pièces : le LOADER trouve les tests dans un module, la SUITE les
    # 📘   regroupe, le RUNNER les exécute et affiche le résultat (verbosity=2 = détaillé).
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Charge les modules de tests unitaires
    # 📘 Seuls 4 fichiers de tests sur 14 sont lancés ici (pas test_offers, test_crm_store,
    # 📘   test_pages_run, test_no_undefined_names...).
    # 💡 Remplacer cette liste en dur par loader.discover("tests", pattern="test_*.py") (en
    # 💡   excluant test_campaign) : un nouveau fichier de test serait pris en compte tout seul.
    # 💡   Idéalement, lancer `pytest` automatiquement à chaque push (GitHub Actions) avant
    # 💡   le déploiement Railway.
    for module in ["tests.test_analyzer", "tests.test_mailer", "tests.test_profiles", "tests.test_service_profiles"]:
        try:
            suite.addTests(loader.loadTestsFromName(module))
        # 📘 `except Exception as e` : on récupère l'erreur dans la variable e pour l'afficher.
        except Exception as e:
            print(f"❌ Impossible de charger {module} : {e}")
            return False

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)  # 📘 result contient le bilan : testsRun, failures, errors...

    print(f"\n{'✅ TOUS LES TESTS PASSENT' if result.wasSuccessful() else '❌ DES TESTS ÉCHOUENT'}")
    print(f"   Tests : {result.testsRun} | Échecs : {len(result.failures)} | Erreurs : {len(result.errors)}")

    return result.wasSuccessful()


def run_campaign_tests(max_results: int = 3, campagne_filter: str = None) -> None:
    """Lance les tests d'intégration multi-villes avec rapport de métriques."""
    # 📘 `campagne_filter: str = None` : paramètre facultatif (valeur par défaut None).
    # 📘   L'annotation exacte serait Optional[str], puisque None n'est pas un str.
    # 📘 Tests « d'INTÉGRATION » : contrairement aux tests unitaires, ils appellent de
    # 📘   vraies API (réseau, clé, quotas) → plus lents, et peuvent coûter / varier.
    print("\n" + "=" * 60)
    print("🌍 TESTS D'INTÉGRATION — CAMPAGNES MULTI-VILLES")
    print("=" * 60)

    # Import ici pour ne pas charger les modules API si on ne fait que les tests unitaires
    from tests.test_campaign import CAMPAGNES, run_campagne, print_rapport
    import json
    from datetime import datetime

    campagnes = CAMPAGNES
    if campagne_filter:
        # 📘 Filtre insensible à la casse : .lower() met tout en minuscules des deux côtés.
        campagnes = [c for c in CAMPAGNES if campagne_filter.lower() in c["nom"].lower()]

    resultats = []
    for campagne in campagnes:
        try:
            metriques = run_campagne(campagne, max_results=max_results)
            resultats.append(metriques)
            time.sleep(1)  # 📘 pause d'1 s entre campagnes pour ménager l'API
        # 📘 Une campagne qui plante ne stoppe pas les autres : on note l'erreur et on continue.
        except Exception as e:
            print(f"  ❌ '{campagne['nom']}' échouée : {e}")
            resultats.append({"nom": campagne["nom"], "total_prospects": 0, "erreur": str(e)})

    print_rapport(resultats)

    # Sauvegarde
    # 📘 exist_ok=True : pas d'erreur si le dossier existe déjà.
    os.makedirs("output", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join("output", f"rapport_test_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)
    print(f"💾 Rapport JSON : {path}")


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

# 📘 `__name__` vaut "__main__" seulement quand on exécute CE fichier directement
# 📘   (python run_tests.py). S'il est importé par un autre fichier, ce bloc ne s'exécute pas.
if __name__ == "__main__":
    # 📘 argparse lit les options tapées après le nom du script (--all, --max 2...).
    # 📘   action="store_true" : l'option vaut True si elle est présente, False sinon.
    parser = argparse.ArgumentParser(description="Lance les tests du projet Prospection B2B")
    parser.add_argument("--all",      action="store_true", help="Unitaires + campagnes")
    parser.add_argument("--unit",     action="store_true", help="Tests unitaires uniquement")
    parser.add_argument("--campaign", action="store_true", help="Tests de campagnes uniquement")
    parser.add_argument("--max",      type=int, default=3,  help="Max prospects/kw (campagnes)")
    parser.add_argument("--filtre",   type=str, default=None, help="Filtrer une campagne (ex: 'Lyon')")
    args = parser.parse_args()

    # Par défaut : unitaires seulement
    # 📘 any([...]) renvoie True si au moins un élément de la liste est vrai.
    if not any([args.all, args.unit, args.campaign]):
        args.unit = True

    ok = True

    if args.unit or args.all:
        ok = run_unit_tests()

    if args.campaign or args.all:
        # 📘 os.getenv lit une VARIABLE D'ENVIRONNEMENT (valeur par défaut "" si absente).
        # 📘 Attention : ce script ne charge pas le fichier .env lui-même (c'est
        # 📘   tests/test_campaign.py qui appelle load_dotenv, mais il est importé APRÈS ce
        # 📘   contrôle). La clé doit donc être exportée dans ton terminal.
        # 💡 Appeler load_dotenv() en haut de ce script rendrait le message « Ajoutez la clé
        # 💡   dans votre .env » cohérent avec le comportement réel.
        api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
        if not api_key:
            print("\n❌ GOOGLE_PLACES_API_KEY manquante — impossible de lancer les campagnes.")
            print("   Ajoutez la clé dans votre .env et relancez avec --campaign")
            sys.exit(1)
        run_campaign_tests(max_results=args.max, campagne_filter=args.filtre)

    # 📘 Code de sortie : 0 = succès, autre = échec. Les outils d'intégration continue (CI)
    # 📘   s'en servent pour savoir si l'étape « tests » est passée.
    sys.exit(0 if ok else 1)
