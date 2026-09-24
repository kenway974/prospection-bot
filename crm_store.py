"""
crm_store.py — Base de données unique du CRM (SQLite).

Remplace les fichiers JSON éparpillés (contacted_place_ids.json, history.json,
prospects_*.json) qui ne communiquaient pas entre eux : impossible de filtrer,
trier ou suivre un prospect dans le temps.

Un seul fichier : output/crm.db — zéro serveur, parfait sur un volume Railway.

Trois tables :
  - prospects : une ligne par entreprise (clé = place_id), avec son statut CRM
  - campaigns : une ligne par run de prospection
  - events    : la timeline de chaque prospect (contacté, relancé, note, réponse…)

La migration depuis les anciens fichiers JSON est automatique et idempotente.
"""

from __future__ import annotations

# 📘 sqlite3 : base de données SQL rangée dans UN simple fichier (output/crm.db), incluse dans
# 📘 Python : pas de serveur à installer. threading.Lock : un "verrou" pour qu'un seul thread
# 📘 écrive à la fois. contextmanager : outil pour fabriquer ses propres blocs `with`.
# 📘 typing (Dict, List, Optional…) : annotations de type, purement indicatives pour le lecteur
# 📘 et l'éditeur (Optional[int] = "un int OU None").
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : toute la persistance du CRM (prospects, campagnes, timeline, réglages) dans SQLite.
# 📘   C'est un "Repository" (dépôt) : le SEUL endroit qui écrit du SQL. Le reste de l'app
# 📘   appelle des fonctions métier (set_status, mark_contacted…) sans jamais voir de SQL.
# 📘 Appelé par : app.py (écrans CRM, « Ma journée », Réglages ; ensure_ready au démarrage),
# 📘   pipeline.py (exclusions, add_campaign, upsert_prospects, mark_contacted, relances),
# 📘   tests/ (test_crm_store, test_crm_actions, test_linkedin, test_pages_run…).
# 📘 Appelle : sqlite3 (bibliothèque standard) ; services.google_maps.Prospect (migration).
# 📘 Concepts Python à retenir ici : connexion/curseur SQLite, requêtes paramétrées (?, :nom),
# 📘   transactions (commit), context manager (with + @contextmanager), verrou (Lock),
# 📘   migrations de schéma, constantes de module, dict.get, jours ouvrés avec datetime.
# 📘
# 📘 Cycle de vie d'un prospect (colonne `status`) :
# 📘   nouveau → contacte → relance → interesse → rdv → client
# 📘   (+ 2 sorties : pas_interesse, blacklist). Les changements automatiques :
# 📘   upsert_prospects crée en "nouveau" ; mark_contacted passe nouveau→contacte ;
# 📘   mark_responded passe à "interesse" (sauf si déjà rdv/client). Le reste (relance, rdv,
# 📘   client, pas_interesse, blacklist…) est choisi à la main dans l'UI via set_status.
# 📘 En parallèle, `next_action` + `due_date` = la prochaine tâche à faire (écran « Ma journée »).
DB_FILE = os.path.join("output", "crm.db")

# 📘 Verrou GLOBAL au module : chaque fonction qui ÉCRIT fait `with _lock` pour que deux threads
# 📘 (UI + pipeline) n'écrivent pas en même temps dans le fichier SQLite. Les lectures ne le
# 📘 prennent pas. Attention : un Lock ne protège qu'à l'intérieur d'UN processus Python.
_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Statuts du pipeline
# ---------------------------------------------------------------------------

# 📘 Constantes : des noms en MAJUSCULES (convention Python, rien ne les empêche de changer).
# 📘 On écrit STATUS_CLIENT partout plutôt que "client" : une faute de frappe devient une
# 📘 erreur visible (NameError) au lieu d'un bug silencieux.
STATUS_NOUVEAU       = "nouveau"
STATUS_CONTACTE      = "contacte"
STATUS_RELANCE       = "relance"
STATUS_INTERESSE     = "interesse"
STATUS_RDV           = "rdv"
STATUS_CLIENT        = "client"
STATUS_PAS_INTERESSE = "pas_interesse"
STATUS_BLACKLIST     = "blacklist"

# Ordre = progression dans le pipeline (les 3 derniers sont des sorties)
STATUS_ORDER: List[str] = [
    STATUS_NOUVEAU, STATUS_CONTACTE, STATUS_RELANCE,
    STATUS_INTERESSE, STATUS_RDV, STATUS_CLIENT,
    STATUS_PAS_INTERESSE, STATUS_BLACKLIST,
]

# 📘 Dict[str, str] : dictionnaire clé → valeur (ici code interne → libellé affiché dans l'UI).
STATUS_LABELS: Dict[str, str] = {
    STATUS_NOUVEAU:       "🆕 Nouveau",
    STATUS_CONTACTE:      "📤 Contacté",
    STATUS_RELANCE:       "🔄 Relancé",
    STATUS_INTERESSE:     "👀 Intéressé",
    STATUS_RDV:           "📅 RDV",
    STATUS_CLIENT:        "🏆 Client",
    STATUS_PAS_INTERESSE: "🚫 Pas intéressé",
    STATUS_BLACKLIST:     "⛔ Blacklist",
}

# Statuts qui sortent le prospect du flux de prospection/relance
# 📘 `{a, b, c}` sans ":" = un set (ensemble), pas un dict.
CLOSED_STATUSES = {STATUS_CLIENT, STATUS_PAS_INTERESSE, STATUS_BLACKLIST}

# ---------------------------------------------------------------------------
# Prochaines actions — la colonne vertébrale de l'écran « Ma journée »
# ---------------------------------------------------------------------------

ACTION_RELANCER = "relancer"
ACTION_MAQUETTE = "envoyer_maquette"
ACTION_RAPPELER = "rappeler"
ACTION_PROPALE  = "envoyer_propale"
ACTION_LINKEDIN = "message_linkedin"
ACTION_AUTRE    = "autre"

ACTION_LABELS: Dict[str, str] = {
    ACTION_RELANCER: "🔄 Relancer",
    ACTION_MAQUETTE: "🎨 Envoyer la maquette",
    ACTION_RAPPELER: "📞 Rappeler",
    ACTION_PROPALE:  "📄 Envoyer la propale",
    ACTION_LINKEDIN: "💬 Message LinkedIn",
    ACTION_AUTRE:    "📌 À faire",
}

# Délais par défaut, en JOURS OUVRÉS. Modifiables dans Réglages (table meta).
DEFAULT_DELAYS: Dict[str, int] = {
    ACTION_RELANCER: 4,   # relance si pas de réponse
    ACTION_MAQUETTE: 1,   # dès le lendemain : on voit tout de suite qu'il faut l'envoyer
    ACTION_RAPPELER: 1,   # « il devait me rappeler » → on rappelle le lendemain
    ACTION_PROPALE:  1,
    ACTION_LINKEDIN: 1,
    ACTION_AUTRE:    1,
}


# 📘 isoformat → texte triable "2026-09-24T10:15:00" : c'est ainsi que les dates sont stockées
# 📘 (colonnes TEXT). Comparer deux textes ISO revient à comparer les dates.
def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# 📘 Jours ouvrés : on avance jour par jour et on ne compte que lundi→vendredi
# 📘 (date.weekday() : 0 = lundi … 6 = dimanche). Les jours fériés ne sont PAS exclus.
# 📘 `start or date.today()` : si start est None (ou vide), on prend aujourd'hui.
def add_business_days(start: Optional[date], n: int) -> str:
    """
    Ajoute n jours OUVRÉS (week-ends exclus) et retourne 'YYYY-MM-DD'.
    n=1 un vendredi → le lundi suivant.
    """
    d = start or date.today()
    if isinstance(d, datetime):
        d = d.date()
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:      # 0-4 = lundi-vendredi
            added += 1
    return d.isoformat()


# ---------------------------------------------------------------------------
# Connexion & schéma
# ---------------------------------------------------------------------------

# 📘 _connect() est un context manager maison, grâce au décorateur @contextmanager :
# 📘   `with _connect() as conn:` exécute le code AVANT le `yield` (ouvrir la connexion), donne
# 📘   `conn` au bloc, puis exécute la suite APRÈS le bloc.
# 📘 Connexion = le lien ouvert vers le fichier .db ; conn.execute(...) crée un curseur (objet
# 📘   qui exécute une requête et parcourt ses résultats : .fetchone(), .fetchall()).
# 📘 Transaction : les modifications restent "en brouillon" jusqu'à conn.commit(). Si le bloc
# 📘   lève une erreur, commit() n'est pas atteint : tout le bloc est annulé (tout ou rien).
# 📘   `finally` garantit que la connexion est fermée dans tous les cas.
# 📘 row_factory = sqlite3.Row : chaque ligne se lit comme un dict (row["name"]).
# 📘 timeout=15 : si la base est occupée par une autre écriture, on attend jusqu'à 15 s.
@contextmanager
def _connect():
    os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# 📘 Schéma = la structure des tables, en SQL. `IF NOT EXISTS` rend la création rejouable sans
# 📘 erreur. Tables : prospects (clé primaire place_id = identifiant unique), campaigns (une ligne
# 📘 par run, id auto-incrémenté), events (timeline d'un prospect) et meta (réglages clé/valeur).
# 📘 SQLite n'a pas de type liste : issues, keywords… sont stockés en texte JSON ('[]').
# 💡 events.place_id n'a pas de FOREIGN KEY vers prospects(place_id) : rien n'empêche des
# 💡   événements orphelins. Une contrainte (avec ON DELETE CASCADE) garantirait la cohérence.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS prospects (
    place_id            TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    address             TEXT DEFAULT '',
    phone               TEXT,
    website             TEXT,
    email               TEXT,
    rating              REAL,
    user_ratings_total  INTEGER DEFAULT 0,
    keyword             TEXT DEFAULT '',
    maps_url            TEXT DEFAULT '',
    cms                 TEXT,
    score               INTEGER DEFAULT 0,
    issues              TEXT DEFAULT '[]',
    issue_keys          TEXT DEFAULT '[]',
    email_draft         TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'nouveau',
    notes               TEXT DEFAULT '',
    target_sector       TEXT DEFAULT '',
    service_id          TEXT DEFAULT '',
    campaign_id         INTEGER,
    first_seen_at       TEXT,
    updated_at          TEXT,
    first_contact_date  TEXT,
    last_contact_date   TEXT,
    followup_step       INTEGER DEFAULT 0,
    responded           INTEGER DEFAULT 0,
    notion_page_id      TEXT DEFAULT '',
    email_template      TEXT DEFAULT '',
    next_action         TEXT DEFAULT '',
    due_date            TEXT DEFAULT '',
    action_note         TEXT DEFAULT '',
    siren               TEXT DEFAULT '',
    dirigeant           TEXT DEFAULT '',
    dirigeant_qualite   TEXT DEFAULT '',
    email_status        TEXT DEFAULT '',
    email_status_reason TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS campaigns (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT,
    profile           TEXT DEFAULT '',
    location          TEXT DEFAULT '',
    keywords          TEXT DEFAULT '[]',
    sources           TEXT DEFAULT '[]',
    target_sector     TEXT DEFAULT '',
    total_prospects   INTEGER DEFAULT 0,
    sans_site         INTEGER DEFAULT 0,
    emails_trouves    INTEGER DEFAULT 0,
    mobiles_trouves   INTEGER DEFAULT 0,
    emails_envoyes    INTEGER DEFAULT 0,
    sms_envoyes       INTEGER DEFAULT 0,
    crm_synchronises  INTEGER DEFAULT 0,
    offer_types       TEXT DEFAULT '{}',
    fichier           TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id  TEXT NOT NULL,
    at        TEXT NOT NULL,
    kind      TEXT NOT NULL,
    detail    TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT
);
"""


# 📘 Migration "maison" : quand on ajoute une colonne au code, les bases déjà existantes ne l'ont
# 📘 pas. init_db compare avec les colonnes réelles et fait un ALTER TABLE pour les manquantes.
# Colonnes ajoutées après coup : migrées sur les bases déjà créées.
_ADDED_COLUMNS = {
    "next_action": "TEXT DEFAULT ''",
    "due_date":    "TEXT DEFAULT ''",
    "action_note": "TEXT DEFAULT ''",
    "siren":             "TEXT DEFAULT ''",
    "dirigeant":         "TEXT DEFAULT ''",
    "dirigeant_qualite": "TEXT DEFAULT ''",
    "email_status":        "TEXT DEFAULT ''",
    "email_status_reason": "TEXT DEFAULT ''",
}


# Index créés APRÈS la migration des colonnes : sur une base ancienne, indexer
# une colonne pas encore ajoutée ferait échouer tout le schéma.
_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects(status);
CREATE INDEX IF NOT EXISTS idx_prospects_campaign ON prospects(campaign_id);
CREATE INDEX IF NOT EXISTS idx_prospects_due ON prospects(due_date);
CREATE INDEX IF NOT EXISTS idx_events_place ON events(place_id);
"""


# 📘 `with _lock, _connect() as conn:` = deux context managers imbriqués sur une ligne :
# 📘 on prend le verrou PUIS on ouvre la connexion ; on les libère dans l'ordre inverse.
# 📘 PRAGMA table_info(prospects) : commande SQLite qui liste les colonnes d'une table.
# 📘 {r["name"] for r in ...} = "set comprehension" : construit un ensemble en une ligne.
# 📘 Le f-string dans ALTER TABLE est sûr ici car col/ddl viennent de notre constante, jamais
# 📘 de l'utilisateur.
def init_db() -> None:
    """Crée le schéma si besoin, ajoute les colonnes manquantes, puis les index."""
    with _lock, _connect() as conn:
        conn.executescript(_SCHEMA)
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(prospects)")}
        for col, ddl in _ADDED_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE prospects ADD COLUMN {col} {ddl}")
        try:
            conn.executescript(_INDEXES)
        except sqlite3.OperationalError:
            pass  # base héritée sans certaines colonnes indexables : non bloquant


# ---------------------------------------------------------------------------
# Réglages persistants (délais configurables)
# ---------------------------------------------------------------------------

# 📘 Requête paramétrée : le `?` est remplacé par la valeur du tuple, de façon SÛRE (la base
# 📘 échappe elle-même la valeur). Ne JAMAIS coller une valeur utilisateur dans le texte SQL
# 📘 (f"... '{x}'") : c'est la porte ouverte à l'injection SQL.
# 📘 `(f"delay_{action}",)` : la virgule finale fait un tuple à 1 élément (sinon juste des ()).
# 📘 Table meta = petit stockage clé/valeur pour les réglages (délais, modèles, franchises…).
def get_delay(action: str) -> int:
    """Délai en jours ouvrés pour une action (réglage utilisateur ou défaut)."""
    with _connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (f"delay_{action}",)).fetchone()
    if row:
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            pass
    return DEFAULT_DELAYS.get(action, 1)


# 📘 "INSERT OR REPLACE" (spécifique SQLite) : insère, ou remplace la ligne si la clé existe.
def set_delay(action: str, days: int) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (f"delay_{action}", str(max(0, int(days)))),
        )


def get_linkedin_templates() -> Dict[str, str]:
    """Modèles LinkedIn personnalisés par l'utilisateur ({clé: texte})."""
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM meta WHERE key LIKE 'li_tpl_%'").fetchall()
    # 📘 Dict comprehension + slicing : r["key"][len("li_tpl_"):] retire le préfixe "li_tpl_".
    return {r["key"][len("li_tpl_"):]: r["value"] for r in rows if (r["value"] or "").strip()}


def set_linkedin_template(key: str, text: str) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"li_tpl_{key}", text)
        )


def reset_linkedin_template(key: str) -> None:
    """Revient au modèle par défaut."""
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM meta WHERE key = ?", (f"li_tpl_{key}",))


# Délai avant de vérifier qu'une invitation a été acceptée (jours ouvrés)
LINKEDIN_ACCEPT_CHECK_DAYS = 3


# 📘 Fonction "métier" qui en combine d'autres : événement dans la timeline + contact + action.
# 📘 `raise ValueError(...)` : on refuse une valeur invalide en levant une exception.
def mark_linkedin_sent(place_id: str, kind: str, detail: str = "") -> str:
    """
    Trace un envoi LinkedIn fait À LA MAIN et programme la suite :
      - « invitation » → vérifier l'acceptation et envoyer le 1er message ;
      - « message »    → relancer si pas de réponse.
    Retourne la date d'échéance de la suite.
    """
    if kind not in ("invitation", "message"):
        raise ValueError(f"Type d'envoi LinkedIn inconnu : {kind}")
    label = "Invitation LinkedIn envoyée" if kind == "invitation" else "Message LinkedIn envoyé"
    add_event(place_id, "linkedin", label + (f" · {detail}" if detail else ""))
    mark_contacted([place_id], channel="linkedin")
    if kind == "invitation":
        return set_next_action(
            place_id, ACTION_LINKEDIN, delay_days=LINKEDIN_ACCEPT_CHECK_DAYS,
            note="Invitation envoyée : si acceptée, envoyer le 1er message",
        )
    return set_next_action(
        place_id, ACTION_RELANCER, note="Message LinkedIn envoyé : relancer si pas de réponse",
    )


def get_user_franchises() -> List[str]:
    """Enseignes ajoutées par l'utilisateur, en plus de la liste intégrée."""
    with _connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = 'user_franchises'").fetchone()
    if not row:
        return []
    try:
        # 📘 json.loads : texte JSON → objet Python (ici une liste). json.dumps fait l'inverse.
        return [s for s in json.loads(row["value"]) if s.strip()]
    except (json.JSONDecodeError, TypeError):
        return []


def set_user_franchises(names: Iterable[str]) -> None:
    # 📘 sorted(..., key=str.lower) : trie sans tenir compte des majuscules.
    clean = sorted({n.strip() for n in names if n and n.strip()}, key=str.lower)
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('user_franchises', ?)",
            (json.dumps(clean, ensure_ascii=False),),
        )


# ---------------------------------------------------------------------------
# Prospects
# ---------------------------------------------------------------------------

# 📘 Conversion objet Prospect → dict de colonnes. getattr(p, "siren", "") lit l'attribut s'il
# 📘 existe, sinon renvoie "" (protège contre d'anciens objets qui n'ont pas ce champ).
# 📘 `x or ""` : si x est None ou vide, on met "" à la place.
def _prospect_to_row(p, campaign_id: Optional[int], sector: str, service_id: str) -> dict:
    return {
        "place_id": p.place_id,
        "name": p.name,
        "address": p.address or "",
        "phone": p.phone,
        "website": p.website,
        "email": p.email,
        "rating": p.rating,
        "user_ratings_total": p.user_ratings_total or 0,
        "keyword": p.keyword or "",
        "maps_url": getattr(p, "maps_url", "") or "",
        "cms": p.cms,
        "score": p.score or 0,
        "issues": json.dumps(p.issues or [], ensure_ascii=False),
        "issue_keys": json.dumps(p.issue_keys or [], ensure_ascii=False),
        "email_draft": p.email_draft or "",
        "target_sector": sector or "",
        "service_id": service_id or "",
        "campaign_id": campaign_id,
        "siren": getattr(p, "siren", "") or "",
        "dirigeant": getattr(p, "dirigeant", "") or "",
        "dirigeant_qualite": getattr(p, "dirigeant_qualite", "") or "",
        "email_status": getattr(p, "email_status", "") or "",
        "email_status_reason": getattr(p, "email_status_reason", "") or "",
    }


# 📘 "Upsert" = UPDATE si le prospect existe déjà, INSERT sinon.
# 💡 Une requête SELECT puis une autre par prospect (2 allers-retours) : SQLite ≥ 3.24 et
# 💡   Postgres savent faire `INSERT ... ON CONFLICT(place_id) DO UPDATE SET ...` en une fois.
def upsert_prospects(prospects: Iterable, campaign_id: Optional[int] = None,
                     sector: str = "", service_id: str = "") -> int:
    """
    Insère/actualise des prospects. Ne réinitialise JAMAIS le statut, les notes
    ni l'historique de contact d'un prospect déjà connu : on ne fait que
    rafraîchir les données d'audit (score, issues, email…).
    Retourne le nombre de NOUVEAUX prospects créés.
    """
    now = _now()
    created = 0
    with _lock, _connect() as conn:
        for p in prospects:
            row = _prospect_to_row(p, campaign_id, sector, service_id)
            # 📘 Tout le lot est traité dans UNE seule transaction (un seul commit à la fin du with).
            existing = conn.execute(
                "SELECT place_id FROM prospects WHERE place_id = ?", (row["place_id"],)
            ).fetchone()
            if existing:
                # 📘 Paramètres NOMMÉS (:name, :email…) remplis depuis un dict : plus lisible que des
                # 📘 `?`. COALESCE(a, b) = a s'il n'est pas NULL, sinon b. NULLIF(x, '') = NULL si x
                # 📘 est vide. Donc COALESCE(NULLIF(:siren, ''), siren) = "garde l'ancien siren si le
                # 📘 nouveau est vide". Le statut, les notes et les dates de contact ne sont PAS dans
                # 📘 ce UPDATE : on ne les écrase jamais (c'est la mémoire du travail commercial).
                conn.execute(
                    """UPDATE prospects SET
                         name=:name, address=:address, phone=:phone, website=:website,
                         email=COALESCE(:email, email), rating=:rating,
                         user_ratings_total=:user_ratings_total, keyword=:keyword,
                         maps_url=:maps_url, cms=:cms, score=:score, issues=:issues,
                         issue_keys=:issue_keys, email_draft=:email_draft,
                         target_sector=:target_sector, service_id=:service_id,
                         campaign_id=COALESCE(:campaign_id, campaign_id),
                         siren=COALESCE(NULLIF(:siren, ''), siren),
                         dirigeant=COALESCE(NULLIF(:dirigeant, ''), dirigeant),
                         dirigeant_qualite=COALESCE(NULLIF(:dirigeant_qualite, ''), dirigeant_qualite),
                         email_status=COALESCE(NULLIF(:email_status, ''), email_status),
                         email_status_reason=COALESCE(NULLIF(:email_status_reason, ''), email_status_reason),
                         updated_at=:updated_at
                       WHERE place_id=:place_id""",
                    # 📘 {**row, "updated_at": now} : copie du dict row avec une clé en
                    # 📘 plus (déballage `**`).
                    {**row, "updated_at": now},
                )
            else:
                conn.execute(
                    """INSERT INTO prospects
                       (place_id, name, address, phone, website, email, rating,
                        user_ratings_total, keyword, maps_url, cms, score, issues,
                        issue_keys, email_draft, target_sector, service_id, campaign_id,
                        siren, dirigeant, dirigeant_qualite, email_status, email_status_reason,
                        status, first_seen_at, updated_at)
                       VALUES
                       (:place_id, :name, :address, :phone, :website, :email, :rating,
                        :user_ratings_total, :keyword, :maps_url, :cms, :score, :issues,
                        :issue_keys, :email_draft, :target_sector, :service_id, :campaign_id,
                        :siren, :dirigeant, :dirigeant_qualite, :email_status, :email_status_reason,
                        'nouveau', :first_seen_at, :updated_at)""",
                    {**row, "first_seen_at": now, "updated_at": now},
                )
                created += 1
    return created


def get_prospect(place_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM prospects WHERE place_id = ?", (place_id,)).fetchone()
    return dict(row) if row else None


# 📘 Construction dynamique du WHERE : on empile des morceaux SQL fixes dans `clauses` et les
# 📘 valeurs dans `params`, puis on les relie par AND. Les valeurs restent des `?` → sûr.
# 📘 LIKE '%texte%' = "contient texte". (*params, limit) : tuple avec les params puis limit.
def list_prospects(status: Optional[str] = None, sector: Optional[str] = None,
                   has_email: Optional[bool] = None, search: str = "",
                   limit: int = 500) -> List[dict]:
    """Liste filtrée des prospects, les plus récemment mis à jour d'abord."""
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if sector:
        clauses.append("target_sector = ?")
        params.append(sector)
    if has_email is True:
        clauses.append("email IS NOT NULL AND email != ''")
    elif has_email is False:
        clauses.append("(email IS NULL OR email = '')")
    if search:
        clauses.append("(name LIKE ? OR email LIKE ? OR website LIKE ?)")
        params += [f"%{search}%"] * 3
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM prospects {where} ORDER BY COALESCE(updated_at, first_seen_at) DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# 📘 Chaque changement métier écrit AUSSI une ligne dans `events` : c'est la timeline du prospect.
def set_status(place_id: str, status: str, note: str = "") -> None:
    """Change le statut d'un prospect et trace l'événement."""
    if status not in STATUS_LABELS:
        raise ValueError(f"Statut inconnu : {status}")
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE prospects SET status = ?, updated_at = ? WHERE place_id = ?",
            (status, _now(), place_id),
        )
        conn.execute(
            "INSERT INTO events (place_id, at, kind, detail) VALUES (?, ?, 'statut', ?)",
            (place_id, _now(), note or STATUS_LABELS[status]),
        )


def set_notes(place_id: str, notes: str) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE prospects SET notes = ?, updated_at = ? WHERE place_id = ?",
            (notes, _now(), place_id),
        )


def add_event(place_id: str, kind: str, detail: str = "") -> None:
    """Ajoute une entrée à la timeline d'un prospect."""
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO events (place_id, at, kind, detail) VALUES (?, ?, ?, ?)",
            (place_id, _now(), kind, detail),
        )


def get_events(place_id: str, limit: int = 50) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE place_id = ? ORDER BY at DESC LIMIT ?",
            (place_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# 📘 CASE WHEN ... THEN ... ELSE ... END = un "if" en SQL : seul un prospect "nouveau" passe à
# 📘 "contacte" ; un statut plus avancé est conservé. La 1re date de contact n'est posée qu'une fois.
def mark_contacted(place_ids: Iterable[str], channel: str = "email") -> None:
    """Marque des prospects comme contactés (statut + dates + événement)."""
    now = _now()
    today = datetime.now().strftime("%Y-%m-%d")
    with _lock, _connect() as conn:
        for pid in place_ids:
            conn.execute(
                """UPDATE prospects
                   SET status = CASE WHEN status = 'nouveau' THEN 'contacte' ELSE status END,
                       first_contact_date = COALESCE(NULLIF(first_contact_date, ''), ?),
                       last_contact_date = ?, updated_at = ?
                   WHERE place_id = ?""",
                (today, today, now, pid),
            )
            conn.execute(
                "INSERT INTO events (place_id, at, kind, detail) VALUES (?, ?, 'contact', ?)",
                (pid, now, channel),
            )


# 📘 Priorité de l'échéance : date saisie > delay_days fourni > délai réglé pour cette action.
# 📘 Si le délai vaut 0, l'échéance est aujourd'hui.
def set_next_action(place_id: str, action: str, delay_days: Optional[int] = None,
                    due_date: Optional[str] = None, note: str = "") -> str:
    """
    Programme la prochaine action sur un prospect.

    - `due_date` (YYYY-MM-DD) prioritaire si fourni (saisie manuelle) ;
    - sinon `delay_days` en jours ouvrés ;
    - sinon le délai configuré pour cette action.
    Retourne la date d'échéance retenue.
    """
    if action not in ACTION_LABELS:
        raise ValueError(f"Action inconnue : {action}")
    if not due_date:
        days = get_delay(action) if delay_days is None else int(delay_days)
        due_date = add_business_days(None, days) if days > 0 else datetime.now().strftime("%Y-%m-%d")
    with _lock, _connect() as conn:
        conn.execute(
            """UPDATE prospects SET next_action = ?, due_date = ?, action_note = ?, updated_at = ?
               WHERE place_id = ?""",
            (action, due_date, note, _now(), place_id),
        )
        conn.execute(
            "INSERT INTO events (place_id, at, kind, detail) VALUES (?, ?, 'action', ?)",
            (place_id, _now(), f"{ACTION_LABELS[action]} → {due_date}" + (f" · {note}" if note else "")),
        )
    return due_date


def clear_next_action(place_id: str, done_note: str = "") -> None:
    """Marque l'action comme faite : on la retire de « Ma journée »."""
    with _lock, _connect() as conn:
        conn.execute(
            """UPDATE prospects SET next_action = '', due_date = '', action_note = '', updated_at = ?
               WHERE place_id = ?""",
            (_now(), place_id),
        )
        if done_note:
            conn.execute(
                "INSERT INTO events (place_id, at, kind, detail) VALUES (?, ?, 'fait', ?)",
                (place_id, _now(), done_note),
            )


# 📘 Données de l'écran « Ma journée ». Les dates ISO "AAAA-MM-JJ" se comparent comme du texte.
# 💡 Les statuts "clos" sont réécrits en dur dans le SQL ici et plus bas, alors que
# 💡   CLOSED_STATUSES existe : générer la liste depuis la constante (ou un Enum) évite qu'un
# 💡   futur statut soit oublié à un endroit.
def due_actions(on_date: Optional[str] = None, include_future: bool = False) -> List[dict]:
    """
    Les actions à faire : échéance passée ou aujourd'hui, prospect non clos.
    Triées par échéance (les plus en retard d'abord).
    """
    day = on_date or datetime.now().strftime("%Y-%m-%d")
    cmp_op = "<= ?" if not include_future else "!= ''"
    params: list = [] if include_future else [day]
    with _connect() as conn:
        rows = conn.execute(
            f"""SELECT * FROM prospects
                WHERE next_action != '' AND due_date != '' AND due_date {cmp_op}
                  AND status NOT IN ('client', 'pas_interesse', 'blacklist')
                ORDER BY due_date ASC""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


# 📘 Réponse du prospect : relance automatique annulée (next_action/due_date vidés), statut
# 📘 "interesse", puis éventuellement une nouvelle action. set_next_action est appelé APRÈS le
# 📘 bloc `with _lock` : _lock n'est pas ré-entrant, le reprendre dedans bloquerait le thread.
def mark_responded(place_id: str, how: str = "email", note: str = "",
                   next_action: Optional[str] = None,
                   delay_days: Optional[int] = None,
                   due_date: Optional[str] = None) -> None:
    """
    Le prospect a répondu (mail détecté OU retour téléphonique saisi à la main).

    → statut « intéressé » (s'il n'est pas déjà plus avancé), relance ANNULÉE,
      et éventuellement une nouvelle action programmée (envoyer maquette, rappeler…).
    """
    with _lock, _connect() as conn:
        row = conn.execute("SELECT status, next_action FROM prospects WHERE place_id = ?",
                           (place_id,)).fetchone()
        current = row["status"] if row else STATUS_NOUVEAU
        # On ne dégrade jamais un statut déjà plus avancé (RDV, client…)
        new_status = current if current in (STATUS_RDV, STATUS_CLIENT) else STATUS_INTERESSE
        conn.execute(
            """UPDATE prospects
               SET responded = 1, status = ?, next_action = '', due_date = '', updated_at = ?
               WHERE place_id = ?""",
            (new_status, _now(), place_id),
        )
        conn.execute(
            "INSERT INTO events (place_id, at, kind, detail) VALUES (?, ?, 'reponse', ?)",
            (place_id, _now(), f"Réponse ({how})" + (f" · {note}" if note else "")),
        )
    if next_action:
        set_next_action(place_id, next_action, delay_days=delay_days, due_date=due_date, note=note)


# 📘 Le calcul se fait en Python (sum sur les lignes) plutôt qu'en SQL : simple car peu de lignes.
def actions_summary() -> Dict[str, int]:
    """{en_retard, aujourdhui, a_venir} pour le badge de « Ma journée »."""
    today = datetime.now().strftime("%Y-%m-%d")
    with _connect() as conn:
        rows = conn.execute(
            """SELECT due_date FROM prospects
               WHERE next_action != '' AND due_date != ''
                 AND status NOT IN ('client', 'pas_interesse', 'blacklist')"""
        ).fetchall()
    late = sum(1 for r in rows if r["due_date"] < today)
    now_ = sum(1 for r in rows if r["due_date"] == today)
    return {"en_retard": late, "aujourdhui": now_, "a_venir": len(rows) - late - now_}


# 📘 Utilisé par pipeline.py (ÉTAPE 2) pour ne pas re-prospecter ces entreprises.
def contacted_place_ids() -> set:
    """place_id déjà contactés OU sortis du flux (client, pas intéressé, blacklist)."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT place_id FROM prospects
               WHERE (first_contact_date IS NOT NULL AND first_contact_date != '')
                  OR status IN ('client', 'pas_interesse', 'blacklist')"""
        ).fetchall()
    return {r["place_id"] for r in rows}


# 📘 GROUP BY status + COUNT(*) : SQL compte les prospects par statut en une requête.
def status_counts() -> Dict[str, int]:
    """{statut: nombre} pour le tableau de bord du pipeline."""
    with _connect() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM prospects GROUP BY status").fetchall()
    counts = {s: 0 for s in STATUS_ORDER}
    for r in rows:
        counts[r["status"]] = r["n"]
    return counts


# ---------------------------------------------------------------------------
# Campagnes
# ---------------------------------------------------------------------------

# 📘 `**kw` récupère tous les arguments nommés dans un dict ; kw.get("x", défaut) lit sans planter.
# 📘 cur.lastrowid = l'id auto-incrémenté que SQLite vient d'attribuer à la nouvelle campagne.
def add_campaign(**kw) -> int:
    """Enregistre une campagne et retourne son id."""
    data = {
        "date": kw.get("date") or datetime.now().strftime("%d/%m/%Y %H:%M"),
        "profile": kw.get("profile", ""),
        "location": kw.get("location", ""),
        "keywords": json.dumps(kw.get("keywords", []), ensure_ascii=False),
        "sources": json.dumps(kw.get("sources", []), ensure_ascii=False),
        "target_sector": kw.get("target_sector", ""),
        "total_prospects": kw.get("total_prospects", 0),
        "sans_site": kw.get("sans_site", 0),
        "emails_trouves": kw.get("emails_trouves", 0),
        "mobiles_trouves": kw.get("mobiles_trouves", 0),
        "emails_envoyes": kw.get("emails_envoyes", 0),
        "sms_envoyes": kw.get("sms_envoyes", 0),
        "crm_synchronises": kw.get("crm_synchronises", 0),
        "offer_types": json.dumps(kw.get("offer_types", {}), ensure_ascii=False),
        "fichier": kw.get("fichier", ""),
    }
    with _lock, _connect() as conn:
        cur = conn.execute(
            """INSERT INTO campaigns
               (date, profile, location, keywords, sources, target_sector, total_prospects,
                sans_site, emails_trouves, mobiles_trouves, emails_envoyes, sms_envoyes,
                crm_synchronises, offer_types, fichier)
               VALUES
               (:date, :profile, :location, :keywords, :sources, :target_sector, :total_prospects,
                :sans_site, :emails_trouves, :mobiles_trouves, :emails_envoyes, :sms_envoyes,
                :crm_synchronises, :offer_types, :fichier)""",
            data,
        )
        return int(cur.lastrowid)


def list_campaigns(limit: int = 50) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM campaigns ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["keywords"] = json.loads(d.get("keywords") or "[]")
        d["sources"] = json.loads(d.get("sources") or "[]")
        d["offer_types"] = json.loads(d.get("offer_types") or "{}")
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Migration depuis les anciens fichiers JSON (idempotente)
# ---------------------------------------------------------------------------

# 📘 Migration de DONNÉES (et plus seulement de schéma) : reprise des anciens fichiers JSON.
# 📘 "Idempotente" = on peut la relancer sans risque : le drapeau json_migrated dans meta fait
# 📘 qu'elle ne s'exécute réellement qu'une fois.
def _meta_get(conn, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def migrate_from_json(output_dir: str = "output") -> Dict[str, int]:
    """
    Importe les anciennes données JSON dans la base. Ne s'exécute qu'une fois
    (drapeau en table meta). Retourne {campaigns, prospects, contacts}.
    """
    init_db()
    result = {"campaigns": 0, "prospects": 0, "contacts": 0}

    with _connect() as conn:
        if _meta_get(conn, "json_migrated"):
            return result

    # 1) Campagnes (history.json) — et les prospects de chaque fichier associé
    hist_path = os.path.join(output_dir, "history.json")
    if os.path.exists(hist_path):
        try:
            with open(hist_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
        # 📘 reversed(history) : history.json est du plus récent au plus ancien ; on insère à
        # 📘 l'endroit.
        for run in reversed(history):  # du plus ancien au plus récent
            cid = add_campaign(
                date=run.get("date"),
                profile=run.get("profile", ""),
                location=run.get("location", ""),
                keywords=run.get("keywords", []),
                sources=run.get("sources", []),
                target_sector=run.get("target_sector", ""),
                total_prospects=run.get("total_prospects", 0),
                sans_site=run.get("sans_site", 0),
                emails_trouves=run.get("emails_trouvés", 0),
                mobiles_trouves=run.get("mobiles_trouvés", 0),
                emails_envoyes=run.get("emails_envoyés", 0),
                sms_envoyes=run.get("sms_envoyés", 0),
                crm_synchronises=run.get("crm_synchronisés", 0),
                offer_types=run.get("offer_types", {}),
                fichier=run.get("fichier", ""),
            )
            result["campaigns"] += 1
            fichier = run.get("fichier", "")
            if fichier and os.path.exists(fichier):
                try:
                    from services.google_maps import Prospect
                    with open(fichier, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    objs = [Prospect.from_dict(d) for d in data]
                    result["prospects"] += upsert_prospects(
                        objs, campaign_id=cid, sector=run.get("target_sector", "")
                    )
                except Exception:
                    pass

    # 2) Contacts déjà démarchés (contacted_place_ids.json)
    contacted_path = os.path.join(output_dir, "contacted_place_ids.json")
    if os.path.exists(contacted_path):
        try:
            with open(contacted_path, "r", encoding="utf-8") as f:
                contacted = json.load(f)
        except Exception:
            contacted = {}
        if isinstance(contacted, list):  # très ancien format
            contacted = {pid: {} for pid in contacted}
        now = _now()
        with _lock, _connect() as conn:
            for pid, info in contacted.items():
                # 📘 On déduit le statut CRM des anciens champs : a répondu → interesse ; au moins
                # 📘 une relance → relance ; sinon → contacte.
                step = info.get("followup_step")
                if step is None:
                    step = 1 if info.get("followup_sent") else 0
                responded = 1 if info.get("responded") else 0
                status = STATUS_INTERESSE if responded else (
                    STATUS_RELANCE if step else STATUS_CONTACTE
                )
                exists = conn.execute(
                    "SELECT place_id FROM prospects WHERE place_id = ?", (pid,)
                ).fetchone()
                if exists:
                    conn.execute(
                        """UPDATE prospects SET
                             status = ?, first_contact_date = ?, last_contact_date = ?,
                             followup_step = ?, responded = ?,
                             notion_page_id = ?, email_template = ?, updated_at = ?
                           WHERE place_id = ?""",
                        (status, info.get("first_contact_date", ""),
                         info.get("last_contact_date") or info.get("first_contact_date", ""),
                         int(step), responded, info.get("notion_page_id", ""),
                         info.get("email_template", ""), now, pid),
                    )
                else:
                    conn.execute(
                        """INSERT INTO prospects
                           (place_id, name, email, status, first_contact_date, last_contact_date,
                            followup_step, responded, notion_page_id, email_template,
                            first_seen_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (pid, info.get("name", "") or "(inconnu)", info.get("email", ""),
                         status, info.get("first_contact_date", ""),
                         info.get("last_contact_date") or info.get("first_contact_date", ""),
                         int(step), responded, info.get("notion_page_id", ""),
                         info.get("email_template", ""), now, now),
                    )
                result["contacts"] += 1

    with _lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('json_migrated', ?)", (_now(),)
        )
    return result


# 📘 Point d'entrée appelé par app.py au démarrage : schéma + migrations.
# 💡 Pour FastAPI/multi-utilisateur : passer à Postgres via SQLAlchemy (ou SQLModel) et gérer le
# 💡   schéma avec Alembic (migrations versionnées, au lieu de _ADDED_COLUMNS). Ajouter une
# 💡   colonne user_id à chaque table (clé prospects = (user_id, place_id)) et filtrer TOUTES les
# 💡   requêtes dessus. Le _lock deviendrait inutile : Postgres gère la concurrence entre
# 💡   plusieurs processus/serveurs, ce que ce verrou en mémoire ne sait pas faire.
def ensure_ready() -> Dict[str, int]:
    """À appeler au démarrage de l'app : crée le schéma puis migre si nécessaire."""
    init_db()
    return migrate_from_json()
