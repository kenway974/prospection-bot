"""
tests/test_no_undefined_names.py — Garde-fou anti-régression.

Deux bugs critiques (NameError sur `_crm_type` puis `_with_email`) ont fait
planter TOUTE prospection sans qu'aucun test ne le détecte, car aucun test
n'exécute run_prospection() de bout en bout. Ce test statique (pyflakes)
attrape ce genre de nom non défini AVANT le déploiement, sans avoir besoin
d'exécuter le code.
"""

import os
import subprocess
import sys
import unittest

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : ANALYSE STATIQUE de tout le projet avec pyflakes : échoue si un fichier .py
# 📘   utilise une variable/fonction jamais définie (faute de frappe, variable renommée...).
# 📘   Ça attrape des NameError AVANT que le code ne tourne en production.
# 📘 Appelé par : pytest / `python -m unittest` (pas inclus dans run_tests.py).
# 📘 Appelle : pyflakes (lancé comme programme séparé via subprocess), os.walk.
# 📘 Concepts Python à retenir ici : analyse statique, skipTest, os.walk, subprocess.run,
# 📘   sys.executable, affectation par tranche `liste[:] = ...`.
# 📘 PYFLAKES : outil qui LIT le code sans l'exécuter et signale les erreurs évidentes
# 📘   (nom non défini, import inutilisé...). Ici on ne garde que les « undefined name ».
# 💡 Un linter plus complet comme ruff (très rapide) lancé en CI couvrirait pyflakes et
# 💡   bien plus (imports inutilisés, style), y compris sur le dossier tests/ exclu ici.

ROOT = os.path.join(os.path.dirname(__file__), "..")


class TestNoUndefinedNames(unittest.TestCase):

    def test_pyflakes_pas_de_nom_non_defini(self):
        """Aucun fichier .py du projet ne doit référencer un nom non défini (F821)."""
        try:
            import pyflakes  # noqa: F401
        # 📘 skipTest marque le test « ignoré » (ni réussi ni échoué) si l'outil manque.
        except ImportError:
            self.skipTest("pyflakes non installé (voir requirements-dev.txt) — test ignoré.")

        py_files = []
        # 📘 os.walk parcourt récursivement les dossiers : pour chacun il donne son chemin,
        # 📘   ses sous-dossiers et ses fichiers.
        for dirpath, dirnames, filenames in os.walk(ROOT):
            # 📘 `dirnames[:] = ...` modifie la liste SUR PLACE : os.walk n'entrera donc pas
            # 📘   dans les dossiers retirés (.git, tests, venv...). `dirnames = ...` ne
            # 📘   marcherait pas (ça créerait juste une nouvelle variable locale).
            dirnames[:] = [d for d in dirnames if d not in (".git", "tests", "__pycache__", ".venv", "venv")]
            for f in filenames:
                if f.endswith(".py"):
                    py_files.append(os.path.join(dirpath, f))

        self.assertTrue(py_files, "Aucun fichier .py trouvé — le scan a un problème.")

        # 📘 subprocess.run lance une commande externe : `<python actuel> -m pyflakes f1 f2...`.
        # 📘   capture_output + text=True récupèrent sa sortie sous forme de texte (.stdout).
        result = subprocess.run(
            [sys.executable, "-m", "pyflakes"] + py_files,
            capture_output=True, text=True,
        )
        undefined = [
            line for line in result.stdout.splitlines()
            if "undefined name" in line
        ]
        self.assertEqual(
            undefined, [],
            "Nom(s) non défini(s) détecté(s) — corrige avant de merger :\n" + "\n".join(undefined),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
