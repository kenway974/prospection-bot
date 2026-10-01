"""
services/company_check.py — Vérification de l'entreprise dans le registre Sirène.

API publique et gratuite recherche-entreprises.api.gouv.fr (pas de clé ;
limite ~7 requêtes/s : le throttle de services/dirigeants.py nous garde sous 5/s).
On réutilise la recherche et la correspondance de noms de dirigeants.py :
un seul appel par prospect donne à la fois les contrôles ET le dirigeant.

Verdicts :
  - « exclure »  : entreprise fermée (état administratif C)
  - drapeaux « à vérifier » : introuvable, NAF incohérent avec le métier,
    plusieurs établissements ouverts (chaîne ?), chiffre d'affaires déclaré nul

HYPOTHÈSE : noms de champs selon la doc de l'API (etat_administratif,
activite_principale, nombre_etablissements_ouverts, finances…). Un champ absent
ne déclenche jamais d'exclusion, seulement l'absence du contrôle.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from services import dirigeants
from trades import Trade, naf_matches

CHAIN_MIN_ESTABLISHMENTS = 3   # À partir de 3 établissements ouverts : chaîne probable


def _best_match(name: str, results: List[dict]) -> Optional[dict]:
    best, best_score = None, 0.0
    for entry in results:
        for candidate in (entry.get("nom_raison_sociale"), entry.get("nom_complet")):
            if candidate:
                score = dirigeants.name_similarity(name, candidate)
                if score > best_score:
                    best, best_score = entry, score
    return best if best_score >= dirigeants.MATCH_THRESHOLD else None


def _latest_revenue(entry: dict) -> Tuple[Optional[str], Optional[float]]:
    finances = entry.get("finances") or {}
    if not isinstance(finances, dict) or not finances:
        return None, None
    year = max(finances)
    return year, (finances.get(year) or {}).get("ca")


def summarize(entry: dict) -> dict:
    """Données utiles d'une fiche Sirène, au format stocké dans Prospect.company."""
    year, ca = _latest_revenue(entry)
    return {
        "siren": entry.get("siren", ""),
        "nom": entry.get("nom_complet", ""),
        "etat": entry.get("etat_administratif", ""),
        "naf": entry.get("activite_principale", ""),
        "date_creation": entry.get("date_creation", ""),
        "effectif": entry.get("tranche_effectif_salarie", ""),
        "etablissements_ouverts": entry.get("nombre_etablissements_ouverts"),
        "ca": ca,
        "annee_ca": year,
    }


def evaluate(entry: Optional[dict], trade: Optional[Trade]) -> Tuple[Optional[str], List[str]]:
    """(raison d'exclusion ou None, drapeaux « à vérifier ») pour une fiche Sirène (ou None)."""
    if entry is None:
        return None, ["introuvable dans Sirène (nom différent, auto-entrepreneur ou hors France ?)"]
    info = summarize(entry)
    if info["etat"] == "C":
        return "entreprise fermée (Sirène)", []
    flags: List[str] = []
    if trade is not None and info["naf"] and not naf_matches(info["naf"], trade):
        flags.append(f"code NAF {info['naf']} incohérent avec « {trade.label} »")
    n = info["etablissements_ouverts"]
    if isinstance(n, int) and n >= CHAIN_MIN_ESTABLISHMENTS:
        flags.append(f"{n} établissements ouverts (chaîne ?)")
    if info["ca"] == 0:
        flags.append(f"chiffre d'affaires déclaré 0 € ({info['annee_ca']})")
    return None, flags


def check_prospect(p, trade: Optional[Trade]) -> Optional[str]:
    """
    Vérifie un prospect dans Sirène et le complète (company, siren, dirigeant, flags).
    Retourne une raison d'exclusion, ou None s'il est gardé.
    Une erreur réseau ne fait jamais exclure : le prospect est marqué « à vérifier ».
    """
    try:
        results = dirigeants._search(
            p.name, dirigeants.extract_postal_code(p.address or ""), raise_errors=True,
        )
    except Exception:
        p.flags.append("Sirène indisponible — entreprise non vérifiée")
        return None
    entry = _best_match(p.name, results)
    reason, flags = evaluate(entry, trade)
    p.flags.extend(flags)
    if entry is not None:
        p.company = summarize(entry)
        p.siren = p.siren or p.company["siren"]
        if not getattr(p, "dirigeant", ""):
            p.dirigeant, p.dirigeant_qualite = dirigeants.extract_dirigeant(entry)
    return reason
