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

import os
from typing import Iterable, List, Optional, Tuple

from safe_files import read_json_with_recovery, write_json_atomic

OPTOUT_FILE = os.path.join("output", "optout.json")


class OptOutFileError(RuntimeError):
    """Le fichier de refus existe mais n'est pas lisible : on ne prospecte pas dans le doute."""


def _normalize_email(email: Optional[str]) -> str:
    return (email or "").strip().lower()


def _load() -> dict:
    try:
        # Illisible ou absent + .bak lisible → restauré automatiquement (voir safe_files)
        data = read_json_with_recovery(
            OPTOUT_FILE, "Fichier de refus (STOP)", default={"emails": [], "place_ids": []},
        )
        return {
            "emails": [_normalize_email(e) for e in data.get("emails", [])],
            "place_ids": list(data.get("place_ids", [])),
        }
    except OSError as exc:
        raise OptOutFileError(
            f"Impossible de lire le fichier de refus ({OPTOUT_FILE}) : {exc}. Il est peut-être "
            "verrouillé (antivirus, synchronisation) ou protégé. Aucun fichier n'a été modifié "
            "et aucun envoi n'a été fait : réessayez dans un instant."
        ) from exc
    except (ValueError, AttributeError, TypeError) as exc:
        raise OptOutFileError(
            f"Fichier de refus illisible ({OPTOUT_FILE}) : {exc}. "
            f"Et aucune copie de secours lisible ({OPTOUT_FILE}.bak absent ou abîmé). "
            "Aucun envoi n'a été fait. Réparez le JSON sans le supprimer (le supprimer "
            "ferait recontacter des personnes qui ont dit STOP), puis relancez. "
            "Marche à suivre : MANUEL.md, section « Fichier abîmé »."
        ) from exc


def _save(data: dict) -> None:
    # Écriture atomique + copie de secours .bak : un refus n'est jamais perdu
    write_json_atomic(OPTOUT_FILE, data)


def add_optout(email: Optional[str] = None, place_id: Optional[str] = None) -> None:
    """
    Enregistre un refus par adresse email et/ou par fiche Google (place_id).
    Le prospect correspondant est aussi sorti du CRM (statut blacklist, plus aucune
    action prévue dans « Ma journée »).
    """
    email = _normalize_email(email)
    if not email and not place_id:
        raise ValueError("Il faut une adresse email ou un place_id.")
    data = _load()
    if email and email not in data["emails"]:
        data["emails"].append(email)
    if place_id and place_id not in data["place_ids"]:
        data["place_ids"].append(place_id)
    _save(data)
    _blacklist_in_crm(email, place_id)


def _blacklist_in_crm(email: str, place_id: Optional[str]) -> None:
    """
    Passe en blacklist, dans le CRM local, les fiches qui correspondent au refus.
    Au mieux : le refus est déjà enregistré dans optout.json (qui fait foi partout) ;
    un CRM indisponible ne doit pas faire croire qu'il ne l'a pas été.
    """
    try:
        import crm_store
        for pid in crm_store.place_ids_matching(email=email, place_id=place_id):
            crm_store.set_status(pid, crm_store.STATUS_BLACKLIST, note="A demandé à ne plus être contacté (STOP)")
            crm_store.clear_next_action(pid)
    except Exception as exc:  # noqa: BLE001 — base SQLite verrouillée, schéma ancien…
        import config
        config.logger.warning(
            "⚠️  Refus bien enregistré, mais le CRM n'a pas pu être mis à jour (%s). "
            "Passe la fiche en « blacklist » à la main dans la page Pipeline.", exc,
        )


class OptOutList:
    """
    Instantané de la liste des refus, lu UNE fois puis interrogé en mémoire.
    À charger au début d'une opération (recherche, envoi…) : la même liste sert du début
    à la fin, et une panne du fichier en cours de route ne peut pas couper l'opération.
    """

    def __init__(self, data: dict):
        self.emails = set(data["emails"])
        self.place_ids = set(data["place_ids"])

    def contains(self, prospect) -> bool:
        email = _normalize_email(getattr(prospect, "email", None))
        return bool(email and email in self.emails) or getattr(prospect, "place_id", "") in self.place_ids

    def filter(self, prospects: Iterable) -> Tuple[List, int]:
        prospects = list(prospects)
        kept = [p for p in prospects if not self.contains(p)]
        return kept, len(prospects) - len(kept)


def load_optouts() -> OptOutList:
    """Lit la liste des refus une fois. Lève OptOutFileError si elle est illisible sans copie fiable."""
    return OptOutList(_load())


def opted_out_place_ids() -> set:
    """place_id des fiches Google qui ont refusé (pour écarter un résultat brut avant tout appel)."""
    return load_optouts().place_ids


def is_opted_out(prospect) -> bool:
    """True si l'email OU la fiche Google du prospect figure dans la liste de refus (lit le fichier)."""
    return load_optouts().contains(prospect)


def filter_opted_out(prospects: Iterable) -> Tuple[List, int]:
    """Retire les prospects qui ont refusé. Retourne (liste filtrée, nombre exclus)."""
    return load_optouts().filter(prospects)
