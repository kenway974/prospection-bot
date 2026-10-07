"""
optout_manager.py — Liste des personnes qui ne veulent plus être contactées.

Quand quelqu'un répond « STOP » (ou refuse par téléphone), on l'enregistre ici :
    python main.py --optout adresse@exemple.fr

Fichier : output/optout.json
    {"emails": ["refus@exemple.fr"], "place_ids": ["ChIJ..."]}

Règle de sécurité : si le fichier existe mais est illisible, on LÈVE une erreur au lieu
de repartir d'une liste vide. Mieux vaut ne rien envoyer que recontacter quelqu'un
qui a refusé.

Fonctions exposées :
  - add_optout(email=None, place_id=None) → enregistre un refus
  - is_opted_out(prospect)                → True si le prospect a refusé
  - filter_opted_out(prospects)           → (gardés, nombre_exclus)
"""

from __future__ import annotations

import json
import os
from typing import Iterable, List, Optional, Tuple

OPTOUT_FILE = os.path.join("output", "optout.json")


class OptOutFileError(RuntimeError):
    """Le fichier de refus existe mais n'est pas lisible : on ne prospecte pas dans le doute."""


def _normalize_email(email: Optional[str]) -> str:
    return (email or "").strip().lower()


def _load() -> dict:
    if not os.path.exists(OPTOUT_FILE):
        return {"emails": [], "place_ids": []}
    try:
        with open(OPTOUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "emails": [_normalize_email(e) for e in data.get("emails", [])],
            "place_ids": list(data.get("place_ids", [])),
        }
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        raise OptOutFileError(
            f"Fichier de refus illisible ({OPTOUT_FILE}) : {exc}. "
            "Réparez ou supprimez ce fichier (vérifiez d'abord son contenu), "
            "puis relancez : aucun envoi n'a été fait."
        ) from exc


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(OPTOUT_FILE), exist_ok=True)
    with open(OPTOUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_optout(email: Optional[str] = None, place_id: Optional[str] = None) -> None:
    """Enregistre un refus par adresse email et/ou par fiche Google (place_id)."""
    email = _normalize_email(email)
    if not email and not place_id:
        raise ValueError("Il faut une adresse email ou un place_id.")
    data = _load()
    if email and email not in data["emails"]:
        data["emails"].append(email)
    if place_id and place_id not in data["place_ids"]:
        data["place_ids"].append(place_id)
    _save(data)


def is_opted_out(prospect) -> bool:
    """True si l'email OU la fiche Google du prospect figure dans la liste de refus."""
    data = _load()
    email = _normalize_email(getattr(prospect, "email", None))
    if email and email in data["emails"]:
        return True
    return getattr(prospect, "place_id", "") in data["place_ids"]


def filter_opted_out(prospects: Iterable) -> Tuple[List, int]:
    """Retire les prospects qui ont refusé. Retourne (liste filtrée, nombre exclus)."""
    prospects = list(prospects)
    data = _load()
    kept = []
    for p in prospects:
        email = _normalize_email(getattr(p, "email", None))
        if (email and email in data["emails"]) or getattr(p, "place_id", "") in data["place_ids"]:
            continue
        kept.append(p)
    return kept, len(prospects) - len(kept)
