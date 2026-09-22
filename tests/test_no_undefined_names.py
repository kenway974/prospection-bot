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

ROOT = os.path.join(os.path.dirname(__file__), "..")


class TestNoUndefinedNames(unittest.TestCase):

    def test_pyflakes_pas_de_nom_non_defini(self):
        """Aucun fichier .py du projet ne doit référencer un nom non défini (F821)."""
        try:
            import pyflakes  # noqa: F401
        except ImportError:
            self.skipTest("pyflakes non installé (voir requirements-dev.txt) — test ignoré.")

        py_files = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in (".git", "tests", "__pycache__", ".venv", "venv")]
            for f in filenames:
                if f.endswith(".py"):
                    py_files.append(os.path.join(dirpath, f))

        self.assertTrue(py_files, "Aucun fichier .py trouvé — le scan a un problème.")

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
