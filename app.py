"""
Interface Streamlit — Prospection B2B automatisée.
Lance avec : streamlit run app.py
"""

# 📘 ═══ SECTION : IMPORTS ═══
# 📘 `import x` charge un module (un fichier .py ou une librairie) ; `from x import y` ne prend
# 📘 qu'un nom précis dedans ; `as z` le renomme. Python ne charge un module qu'UNE fois par
# 📘 process : aux reruns suivants (voir plus bas), les imports réutilisent la version en mémoire.
import json
import os
# 📘 queue + threading : outils pour faire tourner la campagne EN PARALLÈLE de l'interface
# 📘 (voir « Démarrage du thread » dans la page Nouvelle campagne).
import queue
import threading
import time
# 💡 Imports inutilisés (signalés par pyflakes) : ThreadPoolExecutor, partial, Optional ici,
# 💡 PROFILES / get_profile / get_service / list_services / get_target / list_targets plus bas,
# 💡 et uuid dans la sauvegarde de profil. Supprime-les : moins de bruit à la lecture.
# 💡 Outil : `pip install pyflakes` puis `pyflakes app.py` (ou `ruff check app.py`).
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from typing import Optional

# 📘 `st` = raccourci conventionnel pour Streamlit : toute l'interface passe par st.quelquechose().
import streamlit as st

# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : c'est TOUTE l'interface web de l'outil (écrans, formulaires, boutons), écrite avec
# 📘   Streamlit, une librairie qui transforme un script Python en site web, sans HTML/JS.
# 📘 Appelé par : la commande `streamlit run app.py` (en local ou sur Railway). Aucun autre
# 📘   fichier n'importe app.py : c'est le point d'entrée.
# 📘 Appelle : pipeline.run_prospection (le moteur d'une campagne), crm_store (base SQLite des
# 📘   prospects), settings_manager (output/settings.json), history_manager (historique JSON),
# 📘   services/* (scheduler, reply_tracker, linkedin, mailer, cache, franchises…), et les
# 📘   catalogues service_profiles / target_segments / profiles / profile_manager.
# 📘
# 📘 LE concept à comprendre : le « rerun » de Streamlit.
# 📘   À CHAQUE interaction (clic, saisie validée, changement de page), Streamlit ré-exécute CE
# 📘   FICHIER ENTIER, de la 1re à la dernière ligne. Les variables Python ordinaires repartent
# 📘   donc de zéro à chaque fois. Ce qui doit survivre d'un rerun au suivant est rangé dans
# 📘   st.session_state (un dictionnaire propre à chaque onglet de navigateur).
# 📘   Un widget (st.button, st.text_input…) fait 2 choses : il s'AFFICHE et il RENVOIE sa
# 📘   valeur actuelle. st.button renvoie True uniquement pendant le rerun déclenché par le clic.
# 📘   st.rerun() force un rerun immédiat (pour réafficher après une écriture en base).
# 📘
# 📘 Concepts Python à retenir ici : import, fonctions (def), dictionnaires {clé: valeur},
# 📘   listes en compréhension [x for x in ...], f-strings f"...{var}...", lambda,
# 📘   try/except, `with` (blocs de mise en page), threads + queue (travail en parallèle).
# 📘 Concepts Streamlit : rerun, st.session_state, widgets avec key= / on_change= (callbacks),
# 📘   st.rerun(), st.navigation + st.Page. NB : st.cache_data / st.cache_resource (garder un
# 📘   résultat calculé entre reruns) ne sont PAS utilisés dans ce fichier (voir 💡 Export).
# 📘
# 📘 Plan du fichier (cherche « SECTION : » dans ton éditeur pour sauter de l'une à l'autre) :
# 📘    1. Imports
# 📘    2. Config de la page + CSS
# 📘    3. Mémoire de session (st.session_state) + rechargement des derniers résultats
# 📘    4. Démarrage des services de fond (scheduler, base CRM, settings.json)
# 📘    5. Configuration : _cfg / _persist_cfg (clés API, signature, secrets)
# 📘    6. Barre latérale (état des connexions)
# 📘    7. Catalogues (services, cibles) + panneau LinkedIn partagé
# 📘    8. Pont vers le moteur (pipeline.run_prospection)
# 📘    9. PAGE « Ma journée »
# 📘   10. PAGE « Nouvelle campagne » (formulaire → lancement → logs live → résultats → export)
# 📘   11. PAGE « Pipeline »
# 📘   12. PAGE « Relances »
# 📘   13. PAGE « Statistiques »
# 📘   14. PAGE « Réglages »
# 📘   15. Navigation (st.navigation) : choisit LA page à exécuter
# 📘
# 📘 Ordre d'exécution à chaque rerun : tout le code « au niveau 0 » (non indenté) tourne de
# 📘   haut en bas (config, état, services, réglages, sidebar) ; les `def page_...` ne font que
# 📘   DÉFINIR des fonctions ; puis tout en bas, _nav.run() appelle UNE seule de ces pages.

# 📘 ═══ SECTION : CONFIG DE LA PAGE + CSS ═══
# ---------------------------------------------------------------------------
# Config page (doit être le 1er appel Streamlit)
# ---------------------------------------------------------------------------
# 📘 set_page_config règle le titre de l'onglet, l'icône, la largeur. Streamlit exige que ce
# 📘 soit le tout premier appel st.* du script.
st.set_page_config(
    page_title="Prospection B2B",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS custom
# ---------------------------------------------------------------------------
# 📘 st.markdown affiche du texte Markdown. Avec unsafe_allow_html=True on peut y glisser du
# 📘 HTML brut : ici une balise <style> qui injecte du CSS pour relooker boutons, cartes, logs.
# 📘 Les classes (.metric-card, .log-box, .issue-chip…) sont réutilisées plus bas dans du HTML.
st.markdown("""
<style>
    .main { background-color: #0f1117; }

    /* Bouton */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white; border: none; border-radius: 8px;
        padding: 0.6rem 2rem; font-size: 1rem; font-weight: 600;
        width: 100%; transition: opacity 0.2s;
    }
    .stButton > button:hover { opacity: 0.85; }

    /* Metric cards */
    .metric-card {
        background: #1e2130; border-radius: 10px;
        padding: 1rem; text-align: center; border: 1px solid #2d3250;
        margin-bottom: 8px;
    }
    .metric-value { font-size: 1.6rem; font-weight: 700; color: #667eea; }
    .metric-label { font-size: 0.75rem; color: #888; margin-top: 4px; }

    /* Log box */
    .log-box {
        background: #0d1117; border: 1px solid #2d3250;
        border-radius: 8px; padding: 1rem;
        font-family: monospace; font-size: 0.75rem;
        height: 250px; overflow-y: auto; color: #cdd6f4;
    }

    /* Issue chips */
    .issue-chip {
        display: inline-block; background: #2d1b1b;
        color: #f38ba8; border-radius: 4px;
        padding: 2px 8px; font-size: 0.75rem; margin: 2px;
    }

    /* Score colors */
    .score-high { color: #a6e3a1; font-weight: 700; }
    .score-mid  { color: #f9e2af; font-weight: 700; }
    .score-low  { color: #f38ba8; font-weight: 700; }

    /* Mobile : sidebar masquée par défaut, tout en colonne */
    @media (max-width: 768px) {
        .metric-value { font-size: 1.2rem; }
        .metric-label { font-size: 0.7rem; }
        .metric-card  { padding: 0.6rem; }
        .log-box      { height: 180px; font-size: 0.7rem; }
        .issue-chip   { font-size: 0.7rem; }

        /* Colonnes Streamlit en pleine largeur sur mobile */
        [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }

        /* Padding réduit */
        .block-container {
            padding: 1rem 0.5rem !important;
        }

        /* Texte plus lisible */
        p, li, label { font-size: 0.9rem !important; }

        /* Bouton plus grand sur mobile */
        .stButton > button {
            padding: 0.8rem 1rem;
            font-size: 1.1rem;
        }
    }
</style>
""", unsafe_allow_html=True)


# 📘 ═══ SECTION : MÉMOIRE DE SESSION (st.session_state) ═══
# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
# 📘 st.session_state = dictionnaire qui SURVIT aux reruns (un par onglet / visiteur).
# 📘 _init_state pose des valeurs par défaut sans écraser celles déjà là (`if k not in ...`) :
# 📘 comme ce code tourne à chaque rerun, sans ce test on remettrait tout à zéro à chaque clic.
# 📘   running   : une campagne tourne-t-elle ?    logs      : lignes de log déjà reçues
# 📘   prospects : résultats à afficher            log_queue : boîte aux lettres thread → UI
# 📘   run_done  : la dernière campagne est terminée
# 📘 Le préfixe « _ » (_init_state) est une convention : « usage interne à ce fichier ».
def _init_state():
    defaults = {
        "running": False,
        "logs": [],
        "prospects": [],
        "log_queue": queue.Queue(),
        "run_done": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# 📘 Au 1er chargement d'une session, on relit le fichier output/prospects_*.json le plus
# 📘 récent (écrit par pipeline.py à chaque campagne) pour réafficher les derniers résultats.
# 📘 Le drapeau "_restored" en session garantit qu'on ne le fait qu'une fois.
def _restore_last_results():
    """
    Recharge les résultats du dernier run depuis le disque au chargement de la page.
    → les résultats survivent à un rechargement / une déconnexion (mobile, réseau).
    Ne s'exécute qu'une fois par session, et jamais pendant un run en cours.
    """
    if (st.session_state.get("running")
            or st.session_state.get("run_done")
            or st.session_state.get("prospects")
            or st.session_state.get("_restored")):
        return
    st.session_state["_restored"] = True
    # 📘 try/except : si une instruction du bloc try échoue, Python saute dans except.
    # 📘 `except Exception: pass` = on ignore l'erreur en silence (rien à recharger, tant pis).
    try:
        import glob
        # 📘 glob liste les fichiers qui correspondent au motif. Le nom contient la date
        # 📘 (AAAAMMJJ_HHMMSS) : trier par ordre alphabétique = trier par date ; [-1] = le plus récent.
        files = sorted(glob.glob(os.path.join("output", "prospects_*.json")))
        if not files:
            return
        latest = files[-1]
        with open(latest, "r", encoding="utf-8") as f:
            data = json.load(f)
        from services.google_maps import Prospect as _P
        # 📘 Liste en compréhension : [f(d) for d in data] = « applique f à chaque élément ».
        # 📘 Prospect.from_dict reconstruit un objet Prospect à partir du dict lu dans le JSON.
        st.session_state.prospects = [_P.from_dict(d) for d in data]
        st.session_state["_restored_from"] = os.path.basename(latest)
    except Exception:
        pass

_restore_last_results()

# 📘 ═══ SECTION : DÉMARRAGE DES SERVICES DE FOND (scheduler, CRM, settings) ═══
# 📘 Ce code est au niveau 0 → il tourne à CHAQUE rerun. Les fonctions appelées sont donc
# 📘 « idempotentes » : les rappeler ne refait rien si c'est déjà fait (un seul thread d'envoi
# 📘 différé par process, schéma SQLite créé / anciens JSON migrés une seule fois).
# Démarrage du thread d'envoi différé (idempotent — ne démarre qu'une fois par process)
from services import scheduler as _scheduler
_scheduler.ensure_running()

# Base CRM (SQLite) : création du schéma + migration des anciens JSON (idempotent)
# 📘 crm_store = la base SQLite des prospects (statuts, prochaines actions, événements…).
# 📘 C'est elle que lisent/écrivent Ma journée, Pipeline et une partie de Réglages.
import crm_store
try:
    _crm_migration = crm_store.ensure_ready()
except Exception as _crm_init_exc:  # la base ne doit jamais empêcher l'app de démarrer
    _crm_migration = {}
    print(f"[CRM] init impossible : {_crm_init_exc}")

# Démarrage du suivi de réponses IMAP (démarré plus tard après lecture des credentials)

# Chargement des paramètres sauvegardés (fallback sur env vars, puis "")
# 📘 settings_manager lit/écrit output/settings.json. _saved est relu à chaque rerun :
# 📘 c'est un dict du genre {"google_api_key": "...", "your_name": "...", ...}.
from settings_manager import load_settings as _load_settings, save_settings as _save_settings
_saved = _load_settings()

# 📘 `key: str` et `-> str` sont des annotations de type : de la doc pour humains et outils,
# 📘 Python ne les vérifie pas. `a or b or c` renvoie la 1re valeur « vraie » (non vide).
def _get(key: str, env_var: str = "", default: str = "") -> str:
    """Priorité : settings.json > variable d'env > valeur par défaut."""
    return _saved.get(key) or os.getenv(env_var, "") or default


# 📘 ═══ SECTION : CONFIGURATION (_cfg, _persist_cfg, secrets) ═══
# ---------------------------------------------------------------------------
# Sidebar — Configuration
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Réglages de connexion — source de vérité UNIQUE, lue par toutes les pages.
# Priorité : saisie de la session > output/settings.json > variable d'env.
# Les champs de saisie sont dans la page ⚙️ Réglages ; la barre latérale ne
# sert plus qu'à naviguer. Chaque champ est enregistré dès qu'il change.
# ---------------------------------------------------------------------------
# 📘 Un set {…} = collection sans doublon, idéale pour tester « est-ce dedans ? ».
# 📘 Seul gmail_password est protégé ainsi. ⚠️ Les AUTRES clés (Google, Notion, HubSpot,
# 📘 Brevo, France Travail) sont, elles, écrites en clair dans output/settings.json.
_SECRET_KEYS = {"gmail_password"}   # jamais écrit sur disque


# 📘 _cfg(key) = LA fonction pour lire un réglage. Ordre de priorité :
# 📘   1. st.session_state["cfg_<key>"] (ce que tu as saisi dans Réglages pendant la session)
# 📘   2. pour un secret : la variable d'environnement uniquement (jamais le disque)
# 📘   3. sinon _get : settings.json > variable d'environnement > default
def _cfg(key: str, env_var: str = "", default=""):
    val = st.session_state.get(f"cfg_{key}")
    if val is not None:
        return val
    if key in _SECRET_KEYS:
        return os.getenv(env_var, "") or default
    return _get(key, env_var, default)


# 📘 _persist_cfg est un « callback » : une fonction que Streamlit appelle TOUT SEUL quand un
# 📘 widget change (on_change=_persist_cfg, args=(key,) dans page_reglages / page_prospection).
# 📘 Le callback s'exécute AVANT le rerun : quand le script repasse, la valeur est à jour.
# 📘 Convention de clés : "w_<key>" = valeur du widget ; "cfg_<key>" = copie gardée en
# 📘 session (lue par _cfg) ; et sur disque sauf pour les secrets.
def _persist_cfg(key: str) -> None:
    """Callback des champs de réglage : garde la valeur en session + sur disque."""
    val = st.session_state.get(f"w_{key}")
    st.session_state[f"cfg_{key}"] = val
    if key not in _SECRET_KEYS:
        # 📘 Une liste (ex. les sources cochées) est stockée sous forme de texte "a,b,c".
        _save_settings({key: ",".join(val) if isinstance(val, list) else val})


# 📘 Les réglages sont lus ici dans des variables « globales » du module : toutes les pages
# 📘 (définies plus bas) s'en servent directement. Elles sont recalculées à chaque rerun.
from services.sources import SOURCE_LABELS as _SRC_LABELS
_src_raw = _cfg("source_types") or "google_maps"
# 📘 On accepte une liste OU un texte "a,b" ; on ne garde que les sources connues ;
# 📘 `[...] or ["google_maps"]` = si la liste est vide, valeur de repli.
source_types = [
    s for s in (_src_raw if isinstance(_src_raw, list) else str(_src_raw).split(","))
    if s in _SRC_LABELS
] or ["google_maps"]
google_key_required = "google_maps" in source_types or "google_search" in source_types

google_key       = _cfg("google_api_key", "GOOGLE_PLACES_API_KEY")
google_cx        = _cfg("google_cx", "GOOGLE_CX")
ft_client_id     = _cfg("ft_client_id", "FT_CLIENT_ID")
ft_client_secret = _cfg("ft_client_secret", "FT_CLIENT_SECRET")

crm_type = (_cfg("crm_type") or "aucun").lower()
if crm_type == "notion":
    crm_key = _cfg("notion_api_key", "NOTION_API_KEY")
    crm_extra = {"database_id": _cfg("notion_database_id", "NOTION_DATABASE_ID")}
elif crm_type == "hubspot":
    crm_key = _cfg("hubspot_api_key", "HUBSPOT_API_KEY")
    crm_extra = {}
else:
    crm_key, crm_extra = "", {}
notion_key = crm_key if crm_type == "notion" else ""   # compat historique/relances

brevo_key      = _cfg("brevo_api_key", "BREVO_API_KEY")
gmail_address  = _cfg("gmail_address", "GMAIL_ADDRESS")
gmail_password = _cfg("gmail_password", "GMAIL_APP_PASSWORD")

your_name    = _cfg("your_name", "YOUR_NAME")
your_title   = _cfg("your_title", "YOUR_TITLE")
your_email   = _cfg("your_email", "YOUR_EMAIL")
your_website = _cfg("your_website", "YOUR_WEBSITE")

# 📘 Le suivi des réponses (lecture IMAP de ta boîte Gmail) tourne dans un thread de fond,
# 📘 démarré une seule fois (ensure_running est idempotent) dès que les identifiants existent.
# Démarrage auto du suivi des réponses Gmail si les identifiants sont connus
if gmail_address and gmail_password:
    from services import reply_tracker as _rt
    _rt.ensure_running(gmail_address, gmail_password)

# 📘 ═══ SECTION : BARRE LATÉRALE ═══
# 📘 `with st.sidebar:` = tout ce qui est appelé dans ce bloc indenté s'affiche dans la barre
# 📘 latérale. `with` ouvre un « contexte » qui se referme à la fin de l'indentation.
# Barre latérale : le menu (ajouté par st.navigation) + l'état des connexions
with st.sidebar:
    _conn = [
        ("Google", bool(google_key)),
        ("Gmail", bool(gmail_address and gmail_password)),
        ("CRM", crm_type != "aucun" and bool(crm_key)),
        ("SMS", bool(brevo_key)),
    ]
    # 📘 Expression ternaire : A if condition else B → 🟢 si connecté, ⚪ sinon.
    st.caption("**Connexions** · " + " · ".join(f"{'🟢' if ok else '⚪'} {n}" for n, ok in _conn))
    if not google_key:
        st.caption("👉 Configure tes clés dans **⚙️ Réglages**.")


# 📘 ═══ SECTION : CATALOGUES (services, cibles) + PANNEAU LINKEDIN PARTAGÉ ═══
# 📘 SERVICE_PROFILES / TARGET_SEGMENTS = listes écrites en dur dans le code : les services
# 📘 que tu vends et les cibles possibles. Le formulaire « Nouvelle campagne » les croise.
# ---------------------------------------------------------------------------
# Titre principal
# ---------------------------------------------------------------------------
from profiles import PROFILES, get_profile
from service_profiles import (
    SERVICE_PROFILES, SERVICE_CATEGORY_LABELS,
    get_service, list_services,
)
from target_segments import (
    TARGET_SEGMENTS, TARGET_SECTOR_LABELS, SIZE_LABELS,
    get_target, list_targets,
)


# 📘 Fonction réutilisée par 2 pages (Ma journée et Pipeline) : c'est un « composant ».
# 📘 key_prefix sert à donner des key= UNIQUES aux widgets : Streamlit plante si deux widgets
# 📘 ont la même key. Ce panneau étant affiché une fois par prospect, on préfixe avec la page
# 📘 + place_id (l'identifiant unique du prospect). `-> None` : ne renvoie rien, affiche.
def _linkedin_panel(row: dict, key_prefix: str) -> None:
    """
    Panneau LinkedIn ASSISTÉ pour un prospect : lien vers le bon profil,
    message prêt à copier, et bouton « envoyé » qui met à jour le suivi.
    Rien n'est jamais envoyé automatiquement.
    """
    from services import linkedin as _li
    pid = row["place_id"]
    company = row.get("name", "")
    dirigeant = row.get("dirigeant") or ""
    is_freelance = (row.get("service_id") or "") == "web_freelance"

    # 1) Trouver la bonne personne
    st.markdown("**1. Trouver la personne**")
    _links = []
    if dirigeant:
        _links.append(f"[👤 {dirigeant}]({_li.people_search_url(company, dirigeant=dirigeant)})")
    for _role in ("CTO", "Product Owner"):
        _links.append(f"[{_role}]({_li.people_search_url(company, role=_role)})")
    _links.append(f"[🏢 Page entreprise]({_li.company_search_url(company)})")
    st.markdown(" · ".join(_links))
    st.caption("Chaque lien ouvre une recherche LinkedIn déjà remplie.")

    # 2) Le message
    st.markdown("**2. Copier le message**")
    # 📘 format_func=lambda k: ... : une lambda est une mini-fonction anonyme d'une ligne.
    # 📘 Le widget renvoie la valeur brute ("invitation") mais affiche le texte de la lambda.
    _kind = st.radio(
        "Type", ["invitation", "message"], horizontal=True, key=f"{key_prefix}_likind",
        format_func=lambda k: "Note d'invitation" if k == "invitation" else "1er message (après acceptation)",
        label_visibility="collapsed",
    )
    _angle = st.radio(
        "Angle", ["freelance", "service"], index=0 if is_freelance else 1, horizontal=True,
        key=f"{key_prefix}_liangle", label_visibility="collapsed",
        format_func=lambda a: "🧑‍💻 Candidature freelance" if a == "freelance" else "🌐 Proposition de service",
    )
    _note_key, _msg_key = _li.default_templates_for(_angle == "freelance")
    # 📘 Lecture crm_store : les modèles LinkedIn personnalisés (page Réglages), sinon les défauts.
    _tpl = _li.get_template(_note_key if _kind == "invitation" else _msg_key, crm_store.get_linkedin_templates())
    _text = _li.render(
        _tpl, dirigeant=dirigeant, entreprise=company,
        mon_nom=your_name, mon_titre=your_title, mon_site=your_website,
    )
    # 📘 La key contient _kind et _angle : changer de type/angle crée un NOUVEAU widget, donc
    # 📘 le texte est régénéré au lieu de garder l'ancienne saisie.
    _edited = st.text_area(
        "Message", value=_text, height=110 if _kind == "invitation" else 200,
        key=f"{key_prefix}_litext_{_kind}_{_angle}", label_visibility="collapsed",
    )
    if _kind == "invitation":
        _lvl, _msg = _li.note_verdict(_edited)
        # 📘 Astuce : on choisit la fonction d'affichage (success/warning/error) dans un dict,
        # 📘 puis on l'appelle directement avec (_msg).
        {"ok": st.success, "warn": st.warning, "error": st.error}[_lvl](_msg)
        st.caption("Compte gratuit : ~5 notes personnalisées par mois. Garde-les pour tes meilleurs prospects.")
    st.code(_edited, language=None)   # icône « copier » en haut à droite du bloc
    st.caption("⬆️ Clique sur l'icône en haut à droite du bloc pour copier.")

    # 3) Marquer comme envoyé
    st.markdown("**3. Une fois envoyé sur LinkedIn**")
    _label = "✅ Invitation envoyée" if _kind == "invitation" else "✅ Message envoyé"
    # 📘 Écriture crm_store : mark_linkedin_sent ajoute un événement, marque le prospect
    # 📘 « contacté » et programme la suite (vérifier l'acceptation / relancer). st.rerun()
    # 📘 relance le script aussitôt pour que l'écran reflète la base à jour.
    if st.button(_label, key=f"{key_prefix}_lisent_{_kind}", type="primary"):
        _due = crm_store.mark_linkedin_sent(pid, _kind)
        st.toast(f"Suivi programmé pour le {_due} ✅")
        st.rerun()





# 📘 ═══ SECTION : PONT VERS LE MOTEUR (pipeline.run_prospection) ═══
# 📘 Toute la logique d'une campagne (recherche, analyse, emails, CRM, envois) vit dans
# 📘 pipeline.py, qui n'importe PAS Streamlit. app.py lui passe un dict `params`, une queue
# 📘 de logs et une liste vide à remplir (voir « Démarrage du thread » plus bas).
# 📘 `# noqa: E402` demande au linter d'ignorer « import qui n'est pas en haut du fichier ».
# ---------------------------------------------------------------------------
# Orchestration de campagne → pipeline.py (aucune dépendance à Streamlit)
# ---------------------------------------------------------------------------
from pipeline import run_prospection  # noqa: E402







    # ---------------------------------------------------------------------------
    # Relances



# 📘 (Les lignes vides et le commentaire « Relances » isolé juste au-dessus sont des restes
# 📘 d'un ancien découpage : aucun effet.)
# 📘 Chaque page = une simple fonction Python (def page_xxx():). Elle n'est PAS exécutée ici :
# 📘 `def` ne fait que la définir. C'est st.navigation (tout en bas) qui appellera la bonne.
# ===========================================================================
# PAGES — navigation officielle Streamlit (st.Page + st.navigation)
# https://docs.streamlit.io/develop/concepts/multipage-apps/page-and-navigation
# ===========================================================================

# 📘 ═══ SECTION : PAGE « MA JOURNÉE » ═══
# 📘 Lit dans crm_store : actions_summary (compteurs), due_actions (actions dues aujourd'hui
# 📘   ou en retard), ACTION_LABELS, get_delay (+ get_linkedin_templates via le panneau).
# 📘 Écrit dans crm_store : clear_next_action, mark_responded, set_next_action, set_status
# 📘   (+ mark_linkedin_sent via le panneau LinkedIn).
def page_ma_journee():
    st.title("☀️ Ma journée")
    st.caption("Tes actions du jour : relances, rappels, maquettes à envoyer, messages LinkedIn.")

    _sum = crm_store.actions_summary()
    # 📘 st.columns(3) renvoie 3 colonnes côte à côte, « déballées » dans _m1, _m2, _m3.
    _m1, _m2, _m3 = st.columns(3)
    _m1.metric("🔴 En retard", _sum["en_retard"])
    _m2.metric("🟠 Aujourd'hui", _sum["aujourdhui"])
    _m3.metric("🗓️ À venir", _sum["a_venir"])

    _due = crm_store.due_actions()
    _today_str = datetime.now().strftime("%Y-%m-%d")

    if not _due:
        st.success(
            "✅ Rien à faire aujourd'hui. "
            "Les actions programmées (relances, maquettes, rappels) apparaîtront ici à leur échéance."
        )
    else:
        st.caption(f"{len(_due)} action(s) à traiter — les plus en retard d'abord.")

    for _d in _due:
        _pid = _d["place_id"]
        # 📘 Les dates sont stockées en texte "AAAA-MM-JJ" : dans ce format, comparer les textes
        # 📘 avec < revient à comparer les dates.
        _late = _d["due_date"] < _today_str
        # 📘 st.container(border=True) = une « carte » encadrée qui regroupe les widgets du prospect.
        with st.container(border=True):
            _h1, _h2 = st.columns([3, 1])
            with _h1:
                st.markdown(
                    f"{crm_store.ACTION_LABELS.get(_d['next_action'], _d['next_action'])} "
                    f"— **{_d['name']}**"
                )
                _info = []
                if _d.get("dirigeant"):
                    _qual = f", {_d['dirigeant_qualite']}" if _d.get("dirigeant_qualite") else ""
                    _info.append(f"👤 **{_d['dirigeant']}**{_qual}")
                if _d.get("email"):
                    _info.append(f"📧 {_d['email']}")
                if _d.get("phone"):
                    _info.append(f"📞 {_d['phone']}")
                if _d.get("website"):
                    _info.append(f"[🌐 site]({_d['website']})")
                if _info:
                    st.caption(" · ".join(_info))
                if _d.get("action_note"):
                    st.info(_d["action_note"])
            with _h2:
                if _late:
                    st.markdown(f"🔴 **en retard**  \n_{_d['due_date']}_")
                else:
                    st.markdown("🟠 **aujourd'hui**")

            # Actions rapides : un clic après un appel ou une réponse
            # 📘 Motif Streamlit classique : `if st.button(...):` → le bloc ne s'exécute QUE pendant le
            # 📘 rerun qui suit le clic. On écrit en base puis st.rerun() pour réafficher la liste à jour
            # 📘 (le prospect traité disparaît). Les key= contiennent _pid pour être uniques.
            _b1, _b2, _b3, _b4 = st.columns(4)
            if _b1.button("✅ Fait", key=f"done_{_pid}", use_container_width=True):
                crm_store.clear_next_action(_pid, done_note=crm_store.ACTION_LABELS.get(_d["next_action"], ""))
                st.rerun()
            if _b2.button("💬 A répondu", key=f"rep_{_pid}", use_container_width=True):
                crm_store.mark_responded(_pid, how="saisie manuelle")
                st.rerun()
            if _b3.button("📅 Demain", key=f"tom_{_pid}", use_container_width=True):
                crm_store.set_next_action(_pid, _d["next_action"] or crm_store.ACTION_RAPPELER,
                                          delay_days=1, note=_d.get("action_note", ""))
                st.rerun()
            if _b4.button("🚫 Pas intéressé", key=f"no_{_pid}", use_container_width=True):
                crm_store.set_status(_pid, crm_store.STATUS_PAS_INTERESSE)
                crm_store.clear_next_action(_pid)
                st.rerun()

            # Programmer une suite précise (issue d'appel)
            # 📘 st.expander = bloc repliable. Les widgets dedans gardent leur valeur entre reruns grâce
            # 📘 à leur key= ; seul le clic sur « Programmer » écrit en base.
            with st.expander("➡️ Programmer la suite", expanded=False):
                _c1, _c2, _c3 = st.columns([2, 1, 1])
                _next = _c1.selectbox(
                    "Action", options=list(crm_store.ACTION_LABELS.keys()),
                    format_func=lambda a: crm_store.ACTION_LABELS[a],
                    key=f"na_{_pid}",
                )
                _delay = _c2.number_input("Dans (j. ouvrés)", min_value=0, max_value=60,
                                          value=crm_store.get_delay(_next), key=f"nd_{_pid}")
                _note = st.text_input("Note", placeholder="ex : l'associé devait rappeler",
                                      key=f"nn_{_pid}")
                if _c3.button("Programmer", key=f"nb_{_pid}", use_container_width=True):
                    _dd = crm_store.set_next_action(_pid, _next, delay_days=int(_delay), note=_note)
                    st.toast(f"Programmé pour le {_dd} ✅")
                    st.rerun()

            with st.expander("💬 LinkedIn", expanded=_d["next_action"] == crm_store.ACTION_LINKEDIN):
                _linkedin_panel(_d, key_prefix=f"mj_{_pid}")

# 📘 ═══ SECTION : PAGE « NOUVELLE CAMPAGNE » ═══
# 📘 La plus grosse page (~800 lignes). Déroulé : formulaire (sources, service, cible,
# 📘 critères) → bouton Lancer → thread qui exécute pipeline.run_prospection → logs en direct
# 📘 (un rerun par seconde) → résultats + export → sauvegarde de profil.
# 📘 Lit : settings.json (_get, _cfg), catalogues, crm_store.get_user_franchises.
# 📘 Écrit : settings.json (au lancement, et les sources via callback), st.session_state,
# 📘   un profil perso (profile_manager). Indirectement, via pipeline.py dans le thread :
# 📘   crm_store.add_campaign / upsert_prospects / mark_contacted, output/prospects_*.json,
# 📘   l'historique JSON (history_manager.save_run).
def page_prospection():
    st.title("🔍 Nouvelle campagne")

    st.markdown("### 📡 Sources")
    # 📘 Widget avec key= + on_change= : sa valeur vit dans st.session_state["w_source_types"], et
    # 📘 à chaque modification Streamlit appelle _persist_cfg("source_types"). args=(...,) est un
    # 📘 tuple d'arguments (la virgule est obligatoire pour un tuple d'un seul élément).
    # 📘 source_types, utilisé juste en dessous, a été calculé en haut du fichier dans CE rerun ;
    # 📘 comme le callback passe avant le rerun, il est déjà à jour.
    st.multiselect(
        "Sources", options=list(_SRC_LABELS.keys()), default=source_types,
        format_func=lambda x: _SRC_LABELS[x], key="w_source_types",
        on_change=_persist_cfg, args=("source_types",), label_visibility="collapsed",
    )
    _missing = []
    if google_key_required and not google_key:
        _missing.append("la clé Google")
    if "google_search" in source_types and not google_cx:
        _missing.append("le Custom Search Engine ID")
    if "france_travail" in source_types and not (ft_client_id and ft_client_secret):
        _missing.append("les identifiants France Travail")
    if _missing:
        st.warning(f"⚙️ Il manque {', '.join(_missing)} — à renseigner dans **Réglages**.")
    # 📘 Compréhension sur des paires (id, nom) « déballées » : on garde le nom si la source est
    # 📘 cochée.
    _free = [n for s_, n in (("sirene", "Sirène"), ("pages_jaunes", "Pages Jaunes")) if s_ in source_types]
    if _free:
        st.caption(f"✅ {' et '.join(_free)} : gratuit, aucune clé requise.")
    st.markdown("---")
    # ---------------------------------------------------------------------------
    # Sélection service × cible
    # ---------------------------------------------------------------------------
    st.markdown("### 🧩 Votre activité")

    # Sélecteur catégorie de service (radio horizontal)
    _svc_cats = list(SERVICE_CATEGORY_LABELS.keys())
    # 📘 Valeur présélectionnée = dernier choix enregistré dans settings.json (sauvé au lancement).
    # 📘 liste.index(x) donne la position de x ; on retombe sur 0 si x est inconnu.
    _saved_svc_cat = _get("service_category", _svc_cats[0])
    _svc_cat_idx = _svc_cats.index(_saved_svc_cat) if _saved_svc_cat in _svc_cats else 0
    selected_svc_cat = st.radio(
        "Catégorie",
        options=_svc_cats,
        format_func=lambda c: SERVICE_CATEGORY_LABELS[c],
        index=_svc_cat_idx,
        horizontal=True,
        label_visibility="collapsed",
        key="svc_cat_radio",
    )

    # Sélecteur service (filtré par catégorie)
    _svcs_in_cat = [s for s in SERVICE_PROFILES if s.category == selected_svc_cat]
    _svc_ids = [s.id for s in _svcs_in_cat]
    # 📘 Dict en compréhension {id: objet} : accès direct à un service par son id.
    _svc_by_id = {s.id: s for s in SERVICE_PROFILES}
    _saved_svc = _get("service_id", _svc_ids[0] if _svc_ids else "web_refonte")
    _svc_idx = _svc_ids.index(_saved_svc) if _saved_svc in _svc_ids else 0
    selected_service_id = st.selectbox(
        "Service",
        options=_svc_ids,
        format_func=lambda sid: f"{_svc_by_id[sid].emoji} {_svc_by_id[sid].name}",
        index=_svc_idx,
        label_visibility="collapsed",
        key="service_selectbox",
    )
    selected_service = _svc_by_id[selected_service_id]
    st.caption(f"*{selected_service.description}*")

    st.markdown("---")
    st.markdown("### 🎯 Votre cible")

    # Sélecteur secteur cible (radio horizontal)
    _tgt_sectors = list(TARGET_SECTOR_LABELS.keys())
    _saved_tgt_sector = _get("target_sector", _tgt_sectors[0])
    _tgt_sector_idx = _tgt_sectors.index(_saved_tgt_sector) if _saved_tgt_sector in _tgt_sectors else 0
    selected_tgt_sector = st.radio(
        "Secteur",
        options=_tgt_sectors,
        format_func=lambda s: TARGET_SECTOR_LABELS[s],
        index=_tgt_sector_idx,
        horizontal=True,
        label_visibility="collapsed",
        key="tgt_sector_radio",
    )

    # Sélecteur cible (filtré par secteur)
    _tgts_in_sector = [t for t in TARGET_SEGMENTS if t.sector == selected_tgt_sector]
    _tgt_ids = [t.id for t in _tgts_in_sector]
    _tgt_by_id = {t.id: t for t in TARGET_SEGMENTS}
    _saved_tgt = _get("target_id", _tgt_ids[0] if _tgt_ids else "restaurants")
    _tgt_idx = _tgt_ids.index(_saved_tgt) if _saved_tgt in _tgt_ids else 0
    selected_target_id = st.selectbox(
        "Cible",
        options=_tgt_ids,
        format_func=lambda tid: f"{_tgt_by_id[tid].emoji} {_tgt_by_id[tid].name}  ·  {SIZE_LABELS[_tgt_by_id[tid].target_size]}",
        index=_tgt_idx,
        label_visibility="collapsed",
        key="target_selectbox",
    )
    selected_target = _tgt_by_id[selected_target_id]
    st.caption(f"*{selected_target.description}*")

    st.markdown("---")

    # ---------------------------------------------------------------------------
    # Critères de recherche — pré-remplis depuis le profil
    # ---------------------------------------------------------------------------
    st.markdown("### 📍 Configurez votre campagne")

    col1, col2 = st.columns([2, 1])

    with col1:
        location = st.text_input(
            "📌 Ville / Zone géographique",
            value=selected_target.location_default or os.getenv("SEARCH_LOCATION", "Lyon, France"),
            placeholder="Paris, France",
        )
        keywords_raw = st.text_area(
            "🔑 Mots-clés cibles (un par ligne)",
            value="\n".join(selected_target.keywords),
            height=150,
            placeholder="restaurant\nboulangerie\ncoiffeur",
        )
        # 📘 splitlines() coupe par ligne, strip() enlève les espaces ; on ignore les lignes vides.
        keywords = [k.strip() for k in keywords_raw.splitlines() if k.strip()]

        # 📘 Import local (dans la fonction) : fait seulement quand cette page s'affiche.
        from services.mailer import EmailStyle, EMAIL_STYLE_LABELS, build_dynamic_email
        from services.google_maps import Prospect as _PreviewProspect

        with st.expander("✉️ Style des emails", expanded=False):
            _email_intonation = st.radio(
                "Intonation",
                options=list(EMAIL_STYLE_LABELS["intonation"].keys()),
                format_func=lambda k: EMAIL_STYLE_LABELS["intonation"][k],
                index=list(EMAIL_STYLE_LABELS["intonation"].keys()).index(
                    _get("email_intonation") if _get("email_intonation") in EMAIL_STYLE_LABELS["intonation"] else "professional"
                ),
                horizontal=True,
                key="email_intonation",
            )
            _email_length = st.radio(
                "Longueur",
                options=list(EMAIL_STYLE_LABELS["length"].keys()),
                format_func=lambda k: EMAIL_STYLE_LABELS["length"][k],
                index=list(EMAIL_STYLE_LABELS["length"].keys()).index(
                    _get("email_length") if _get("email_length") in EMAIL_STYLE_LABELS["length"] else "medium"
                ),
                horizontal=True,
                key="email_length",
            )
            _email_salutation = st.selectbox(
                "Formule d'ouverture",
                options=list(EMAIL_STYLE_LABELS["salutation"].keys()),
                format_func=lambda k: EMAIL_STYLE_LABELS["salutation"][k],
                index=list(EMAIL_STYLE_LABELS["salutation"].keys()).index(
                    _get("email_salutation") if _get("email_salutation") in EMAIL_STYLE_LABELS["salutation"] else "neutral"
                ),
                key="email_salutation",
            )
            _email_cta = st.selectbox(
                "Appel à l'action",
                options=list(EMAIL_STYLE_LABELS["cta"].keys()),
                format_func=lambda k: EMAIL_STYLE_LABELS["cta"][k],
                index=list(EMAIL_STYLE_LABELS["cta"].keys()).index(
                    _get("email_cta") if _get("email_cta") in EMAIL_STYLE_LABELS["cta"] else "audit"
                ),
                key="email_cta",
            )

            # Prévisualisation avec un faux prospect
            # 📘 Aperçu en direct : à chaque changement de style, le rerun régénère l'email d'exemple
            # 📘 avec un faux prospect (build_dynamic_email vient de services/mailer.py).
            _preview_style = EmailStyle(
                intonation=_email_intonation,
                length=_email_length,
                salutation=_email_salutation,
                cta=_email_cta,
            )
            _preview_issue_map = {
                "web_digital":  (["https", "lead_form"],       "site sans HTTPS + pas de formulaire"),
                "freelance":    ([],                            "candidature freelance (renfort dev)"),
                "creatif":      (["no_gallery", "no_video"],   "pas de galerie + pas de vidéo"),
                "conseil_b2b":  (["tracking", "no_blog"],      "pas de tracking + pas de blog"),
                "sante":        (["no_service_mention"],        "service non mentionné sur le site"),
                "terrain":      (["no_service_mention"],        "service non mentionné sur le site"),
                "special":      (["no_service_mention"],        "service non mentionné sur le site"),
            }
            _pkeys, _plabel = _preview_issue_map.get(selected_svc_cat, (["https", "lead_form"], "site sans HTTPS"))
            st.markdown(f"**Aperçu ({_plabel}) :**")
            _preview_prospect = _PreviewProspect(
                place_id="preview",
                name="Votre Prospect",
                address="",
                phone=None,
                website="http://exemple.com",
                rating=None,
                user_ratings_total=0,
                keyword="",
                maps_url="",
            )
            _preview_prospect.issue_keys = _pkeys
            _preview_prospect.score = 40
            _preview_text = build_dynamic_email(
                _preview_prospect,
                _preview_style,
                your_name=_get("your_name", "YOUR_NAME") or "Votre Nom",
                your_title=_get("your_title", "YOUR_TITLE") or "",
                your_offer=selected_service.your_offer or "vous aider à améliorer votre présence en ligne",
                service_id=selected_service_id,
                service_category=selected_svc_cat,
            )
            st.code(_preview_text, language=None)

        st.markdown("**📱 Accroche SMS** *(max 160 caractères)*")
        sms_hook = st.text_input(
            "Accroche SMS",
            value=selected_service.sms_hook,
            label_visibility="collapsed",
        )
        if len(sms_hook) > 160:
            st.warning(f"⚠️ SMS trop long : {len(sms_hook)}/160 caractères")

        # Variables de compatibilité (toujours référencées ailleurs dans app.py)
        email_hook = selected_service.email_hook

    with col2:
        st.markdown("**⚙️ Paramètres**")
        your_offer = st.text_area(
            "🎁 Mon offre",
            value=selected_service.your_offer,
            height=80,
            help="Décrivez votre offre en 1-2 phrases",
        )
        max_results = st.slider("Prospects par mot-clé", 1, 20, 5)
        min_rating = st.slider(
            "Note Google minimum ⭐",
            min_value=1.0, max_value=5.0, value=3.0, step=0.5,
            help="Les établissements en dessous de cette note sont ignorés (probablement en difficulté)",
        )
        # 📘 Le sens du score dépend du service : "desc" = score élevé = bonne opportunité ;
        # 📘 sinon, score bas = site plein de défauts = bon prospect pour toi.
        _score_dir = selected_service.score_direction
        _score_default = (selected_target.score_threshold_override or selected_service.score_threshold_default)
        if selected_svc_cat == "freelance":
            # Mode candidature : on n'audite pas les sites, toutes les cibles sont retenues.
            st.info(
                "🧑‍💻 **Mode candidature freelance** — on n'audite **pas** le site des cibles. "
                "Toutes les entreprises trouvées sont retenues, et le bot génère un email de "
                "candidature (renfort dev). Le filtre de score ne s'applique pas ici."
            )
            score_threshold = 100
        elif _score_dir == "desc":
            score_threshold = st.slider(
                "Score min requis",
                min_value=0, max_value=100, value=_score_default,
                help="Score élevé = bonne opportunité selon ce service.",
            )
        else:
            score_threshold = st.slider(
                "Score max à contacter",
                min_value=0, max_value=100, value=_score_default,
                help=(
                    "Le score = qualité du site (100 = parfait, 0 = pas de site). "
                    "Plus le score est BAS, plus le site a de défauts à corriger = meilleur prospect pour toi. "
                    "On ne contacte que les sites au score ≤ cette valeur. "
                    "85 = large (au moins un défaut réel) ; 60 = strict (sites vraiment mauvais)."
                ),
            )
        radius = st.select_slider(
            "Rayon de recherche",
            options=[1000, 2000, 5000, 10000, 20000, 50000],
            value=10000,
            format_func=lambda x: f"{x//1000} km",
        )
        # 📘 Les widgets sans key= (toggle, slider…) gardent leur valeur entre reruns tant que tu
        # 📘 restes sur la page (Streamlit les reconnaît à leur libellé/paramètres), mais ne sont
        # 📘 sauvegardés nulle part : ils reviennent à leur défaut au prochain chargement.
        send_emails = st.toggle("📧 Envoyer les emails auto", value=False)
        send_risky_emails = False
        if send_emails:
            st.info(
                "🛡️ Chaque adresse est vérifiée avant envoi. Les adresses **invalides** "
                "(domaine inexistant, jetable, faute de frappe, « noreply ») ne reçoivent jamais "
                "de mail : un taux de rebond > 2 % envoie tous tes mails suivants en spam."
            )
            send_risky_emails = st.checkbox(
                "Envoyer aussi aux adresses « risquées » (domaine sans serveur mail déclaré)",
                value=False,
            )
            _email_mode = st.radio(
                "Mode d'envoi", ["📤 Immédiat", "⏰ Programmé"],
                horizontal=True, label_visibility="collapsed",
            )
            if _email_mode == "⏰ Programmé":
                # 📘 Import avec alias : date/timedelta/time renommés pour ne pas écraser
                # 📘 le module `time`
                # 📘 importé en haut du fichier (utilisé par time.sleep plus bas).
                from datetime import date as _dt_date, timedelta as _dt_td, time as _dt_time
                _sched_date = st.date_input("Date d'envoi", value=_dt_date.today() + _dt_td(days=1), min_value=_dt_date.today())
                _sched_time = st.time_input("Heure d'envoi", value=_dt_time(9, 0))
            else:
                _sched_date = None
                _sched_time = None
        else:
            _email_mode = "📤 Immédiat"
            _sched_date = None
            _sched_time = None
        send_sms_toggle = st.toggle("📱 Envoyer les SMS auto", value=False)
        if send_sms_toggle:
            st.warning("⚠️ Seuls les numéros mobiles (06/07) recevront un SMS.")
        exclude_franchises = st.toggle(
            "🏢 Exclure les franchises", value=True,
            help="Fitness Park, Laforêt, Century 21, McDonald's… Le siège décide, "
                 "pas l'agence locale : aucun budget ni décision sur le digital. "
                 "Liste complétable dans Réglages.",
        )
        find_dirigeants = st.toggle(
            "👤 Trouver le dirigeant (Sirène)", value=True,
            help="Nom et fonction du représentant légal (Président, Gérant, DG) via le "
                 "registre public Sirène, gratuit. Seules les correspondances sûres sont "
                 "retenues. Les CTO/PO n'y figurent pas : pour eux, c'est LinkedIn.",
        )
        cache_ttl_days = st.slider(
            "⚡ Cache analyses (jours)", 1, 90, 30,
            help="Durée de validité : un site analysé il y a moins de X jours ne sera pas réanalysé.",
        )

    # LinkedIn CSV uploader (visible seulement si source linkedin_csv sélectionnée)
    linkedin_content = ""
    if "linkedin_csv" in source_types:
        st.markdown("---")
        st.markdown("### 📎 Import CSV LinkedIn")
        st.caption(
            "Exporte tes contacts depuis **LinkedIn Sales Navigator** (Accounts/Leads → Export) "
            "ou **Mes connexions** (Paramètres → Confidentialité → Obtenir une copie de tes données)."
        )
        # 📘 st.file_uploader renvoie un objet fichier (ou None). .read() donne des octets (bytes),
        # 📘 .decode("utf-8-sig") les convertit en texte (-sig retire le BOM ajouté par Excel).
        _uploaded_csv = st.file_uploader(
            "Déposer le fichier CSV LinkedIn",
            type=["csv"],
            help="Format auto-détecté : Sales Navigator, Connexions, ou tout CSV avec colonnes Company/Email/Website.",
        )
        if _uploaded_csv:
            try:
                linkedin_content = _uploaded_csv.read().decode("utf-8-sig")
                _n_rows = max(0, len(linkedin_content.splitlines()) - 1)
                st.success(f"✅ {_n_rows} ligne(s) importée(s) — prêt à analyser.")
            except Exception as _e:
                st.error(f"❌ Erreur de lecture : {_e}")

    st.markdown("---")

    # ---------------------------------------------------------------------------
    # Bouton de lancement
    # ---------------------------------------------------------------------------
    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
    with col_btn2:
        # 📘 Le bouton est grisé (disabled) si une campagne tourne déjà ou s'il manque une clé.
        # 📘 Mêmes contrôles qu'en haut de page (« Il manque… ») et que juste en dessous.
        _launch_disabled = st.session_state.running
        if not source_types:
            _launch_disabled = True
        if ("google_maps" in source_types or "google_search" in source_types) and not google_key:
            _launch_disabled = True
        if "google_search" in source_types and not google_cx:
            _launch_disabled = True
        if "france_travail" in source_types and (not ft_client_id or not ft_client_secret):
            _launch_disabled = True
        if "linkedin_csv" in source_types and not linkedin_content:
            _launch_disabled = True
        # 📘 Mots-clés obligatoires sauf si la seule source est le CSV LinkedIn. Lecture exacte : si
        # 📘 la liste est vide, `not keywords` suffit déjà à griser ; la ville (location) n'est donc
        # 📘 en pratique jamais contrôlée.
        if not keywords and not ("linkedin_csv" in source_types and len(source_types) == 1):
            _launch_disabled = _launch_disabled or not keywords or not location

        # 📘 `launch` vaut True uniquement pendant le rerun déclenché par le clic.
        launch = st.button("🚀 Lancer la prospection", disabled=_launch_disabled)

    if ("google_maps" in source_types or "google_search" in source_types) and not google_key:
        st.info("⚙️ Renseigne ta clé Google Places dans ⚙️ Réglages pour commencer.")
    if "google_search" in source_types and not google_cx:
        st.info("⚙️ Renseigne ton Custom Search Engine ID (cx) dans ⚙️ Réglages.")
    if "france_travail" in source_types and (not ft_client_id or not ft_client_secret):
        st.info("⚙️ Renseigne tes identifiants France Travail dans ⚙️ Réglages.")
    if "linkedin_csv" in source_types and not linkedin_content:
        st.info("👆 Importe un fichier CSV LinkedIn ci-dessus pour commencer.")

    # ---------------------------------------------------------------------------
    # Démarrage du thread
    # ---------------------------------------------------------------------------
    # 📘 ─── Le clic sur « Lancer » (rerun n°1) ───
    # 📘 1. On remet l'état de session à zéro et on crée une NOUVELLE queue.Queue : une file
    # 📘    « thread-safe » (plusieurs threads peuvent y déposer/retirer sans se marcher dessus).
    # 📘 2. On sauvegarde les choix dans settings.json (défauts du prochain lancement).
    # 📘 3. On construit `params` (un gros dict) et une liste vide `result_container`.
    # 📘 4. On démarre un thread qui exécute run_prospection(params, queue, result_container).
    # 📘 5. Le script continue SANS attendre : la section « logs » juste après prend le relais.
    if launch and not st.session_state.running:
        st.session_state.running = True
        st.session_state.run_done = False
        st.session_state.logs = []
        st.session_state.prospects = []
        st.session_state.log_queue = queue.Queue()
        st.session_state.pop("_restored_from", None)  # nouveau run → on n'affiche plus le bandeau « rechargés »

        # Persistance des paramètres (rechargés comme defaults au prochain démarrage)
        # 📘 ⚠️ Écrit aussi les clés API (Google, Notion, HubSpot, Brevo, France Travail) en clair ;
        # 📘 save_settings ignore seulement les valeurs None. gmail_password n'y figure pas.
        _save_settings({
            "google_api_key":    google_key,
            "source_types":      ",".join(source_types),
            "source_type":       source_types[0] if source_types else "google_maps",
            "ft_client_id":      ft_client_id or None,
            "ft_client_secret":  ft_client_secret or None,
            "google_cx":         google_cx or None,
            "crm_type":          crm_type,
            "notion_api_key":    crm_key if crm_type == "notion" else None,
            "notion_database_id": crm_extra.get("database_id") if crm_type == "notion" else None,
            "hubspot_api_key":   crm_key if crm_type == "hubspot" else None,
            "brevo_api_key":     brevo_key,
            "gmail_address":     gmail_address,
            "your_name":         your_name,
            "your_title":        your_title,
            "your_email":        your_email,
            "your_website":      your_website,
            "service_id":        selected_service_id,
            "service_category":  selected_svc_cat,
            "target_id":         selected_target_id,
            "target_sector":     selected_tgt_sector,
            "email_intonation":  _email_intonation,
            "email_length":      _email_length,
            "email_salutation":  _email_salutation,
            "email_cta":         _email_cta,
        })

        # 📘 Liste vide passée au thread : pipeline.py la remplit (.extend) avec les Prospect retenus.
        # 📘 Une liste est « mutable » : le thread et l'interface manipulent le MÊME objet en mémoire.
        result_container = []

        params = {
            "google_key": google_key,
            "notion_key": notion_key,
            "crm_type":   crm_type,
            "crm_key":    crm_key,
            "crm_extra":  crm_extra,
            "brevo_key": brevo_key,
            "location": location,
            "keywords": keywords,
            "radius": radius,
            "max_results": max_results,
            "your_name": your_name,
            "your_title": your_title or selected_service.your_title,
            "your_email": your_email,
            "your_website": your_website,
            "your_offer": your_offer,
            "email_hook": email_hook,
            "sms_hook": sms_hook,
            "email_style": {
                "intonation": _email_intonation,
                "length":     _email_length,
                "salutation": _email_salutation,
                "cta":        _email_cta,
            },
            "profile_id": f"{selected_service_id}_x_{selected_target_id}",
            "profile_name": f"{selected_service.emoji} {selected_service.name}  →  {selected_target.emoji} {selected_target.name}",
            "service_id": selected_service_id,
            "service_category": selected_svc_cat,
            "target_sector": selected_tgt_sector,
            "detection_keywords": selected_service.detection_keywords,
            "weight_overrides": selected_service.check_weight_overrides,
            "score_direction": selected_service.score_direction,
            "min_rating": min_rating,
            "contact_score_threshold": score_threshold,
            # 📘 Nombre d'analyses de sites en parallèle (variable d'env ANALYSIS_WORKERS, 5 par défaut).
            "analysis_workers": int(os.getenv("ANALYSIS_WORKERS", "5")),
            "send_emails": send_emails,
            "send_risky_emails": send_risky_emails,
            "gmail_address": gmail_address,
            "gmail_password": gmail_password,
            "send_sms": send_sms_toggle,
            "cache_ttl_days": cache_ttl_days,
            "exclude_franchises": exclude_franchises,
            "find_dirigeants": find_dirigeants,
            "user_franchises": crm_store.get_user_franchises(),
            "email_send_mode": _email_mode,
            # 📘 .isoformat() → "2026-09-25" ; strftime("%H:%M") → "09:00" : du texte simple.
            "sched_date": _sched_date.isoformat() if _sched_date else None,
            "sched_time": _sched_time.strftime("%H:%M") if _sched_time else None,
            "source_types":      source_types,
            "source_type":       source_types[0] if source_types else "google_maps",
            "ft_client_id":      ft_client_id,
            "ft_client_secret":  ft_client_secret,
            "google_cx":         google_cx,
            "linkedin_content":  linkedin_content,
        }

        # 📘 threading.Thread : fait tourner une fonction EN PARALLÈLE du script Streamlit ; sans lui,
        # 📘 l'interface resterait figée pendant toute la campagne (plusieurs minutes).
        # 📘   target = la fonction à lancer ; args = ses arguments (un tuple) ;
        # 📘   daemon=True = le thread ne retient pas l'arrêt du programme (il meurt avec lui).
        thread = threading.Thread(
            target=run_prospection,
            args=(params, st.session_state.log_queue, result_container),
            daemon=True,
        )
        thread.start()
        # 📘 On range le thread et la liste résultat en session pour les retrouver aux reruns
        # 📘 suivants (les variables locales `thread` et `result_container`, elles, disparaissent).
        st.session_state._thread = thread
        st.session_state._results = result_container

    # ---------------------------------------------------------------------------
    # Affichage live des logs
    # ---------------------------------------------------------------------------
    # 📘 ─── Suivi en direct (reruns n°2, 3, 4…) ───
    # 📘 Tant que running est vrai : on vide la queue dans st.session_state.logs, on affiche les
    # 📘 100 dernières lignes, on attend 1 s (time.sleep) puis st.rerun() → tout le script repart
    # 📘 d'en haut, revient ici, et recommence. C'est du « polling » (aller voir régulièrement
    # 📘 s'il y a du nouveau). Pendant ce temps le thread continue son travail sans interruption.
    # 💡 Côté FastAPI/React, ce trio thread + queue + polling deviendrait : POST /campaigns (lance
    # 💡 la tâche, renvoie un id) → GET /campaigns/{id}/events en SSE ou WebSocket (le serveur
    # 💡 POUSSE les logs, plus de sleep/rerun) → GET /campaigns/{id}/results. Et une vraie file de
    # 💡 tâches (RQ, Celery, arq…) plutôt qu'un thread : aujourd'hui un redémarrage du process tue
    # 💡 la campagne, et pipeline.py écrit dans os.environ (partagé par tout le process) → deux
    # 💡 campagnes lancées en même temps depuis deux onglets se marcheraient dessus.
    if st.session_state.running or st.session_state.run_done:
        st.markdown("### 📡 Logs en temps réel")
        # 📘 st.empty() réserve un emplacement qu'on remplit ensuite (placeholder.markdown(...)).
        log_placeholder = st.empty()
        status_placeholder = st.empty()

        # Vide la queue dans la liste de logs (drain robuste via queue.Empty)
        q = st.session_state.log_queue
        done = False
        # 📘 get_nowait() prend un message sans attendre ; si la file est vide il lève queue.Empty,
        # 📘 qu'on attrape pour sortir de la boucle (`while True` + `break`).
        # 📘 "__DONE__" = message spécial que pipeline.py envoie toujours en dernier (bloc finally).
        while True:
            try:
                msg = q.get_nowait()
            except queue.Empty:
                break
            if msg == "__DONE__":
                done = True
            else:
                st.session_state.logs.append(msg)

        # Filet de sécurité : si le thread s'est terminé sans qu'on ait vu __DONE__
        # (crash dur improbable), on considère quand même le run comme fini.
        _thr = st.session_state.get("_thread")
        if not done and _thr is not None and not _thr.is_alive():
            done = True

        # 📘 Fin de campagne : running → False, run_done → True, et on copie la liste remplie par le
        # 📘 thread dans st.session_state.prospects (lue par la section Résultats ci-dessous).
        # 📘 hasattr(obj, "nom") teste si l'attribut existe.
        if done:
            st.session_state.running = False
            st.session_state.run_done = True
            if hasattr(st.session_state, "_results"):
                st.session_state.prospects = list(st.session_state._results)

        # Affiche les logs
        # 💡 Sécurité : ces logs contiennent des noms d'entreprises venus d'internet et sont insérés
        # 💡 tels quels dans du HTML (unsafe_allow_html) → risque d'injection HTML. Échappe chaque
        # 💡 ligne avec html.escape(). Rappel : settings.json garde les clés API en clair (seul
        # 💡 gmail_password est exclu) — ne jamais le committer ni l'exposer.
        log_html = "<div class='log-box'>" + "<br>".join(
            st.session_state.logs[-100:]
        ) + "</div>"
        log_placeholder.markdown(log_html, unsafe_allow_html=True)

        # 📘 time.sleep(1) bloque ce rerun 1 s, puis st.rerun() arrête le script ICI et le relance
        # 📘 depuis le début : pendant une campagne, rien en dessous (Résultats…) n'est affiché.
        if st.session_state.running:
            status_placeholder.info("⏳ Prospection en cours…")
            time.sleep(1)
            st.rerun()
        else:
            status_placeholder.success("✅ Prospection terminée !")


    # ---------------------------------------------------------------------------
    # Résultats
    # ---------------------------------------------------------------------------
    # 📘 ─── Résultats ───
    # 📘 Affichés dès que st.session_state.prospects n'est pas vide : après une campagne, après
    # 📘 _restore_last_results (au chargement) ou après « Charger cette campagne » (Statistiques).
    if st.session_state.prospects:
        prospects = st.session_state.prospects
        st.markdown("---")
        st.markdown("## 📊 Résultats")
        if st.session_state.get("_restored_from") and not st.session_state.get("run_done"):
            st.info(
                f"🔄 Campagne rechargée : **{st.session_state['_restored_from']}**. "
                "Ces résultats restent affichés après un rechargement de page ou une coupure. "
                "Relance une prospection pour les remplacer."
            )

        # Métriques
        # 📘 sum(1 for p in ... if cond) = compte les éléments qui vérifient cond.
        no_site     = sum(1 for p in prospects if not p.has_website())
        critical    = sum(1 for p in prospects if p.score < 40)
        avg_score   = int(sum(p.score for p in prospects) / len(prospects))
        emails_ok   = sum(1 for p in prospects if p.email)
        # 💡 Logique métier dans l'UI : le test « mobile = commence par 06/07 » est recopié 4 fois
        # 💡 dans ce fichier (métriques, filtre, badges). À ranger dans une méthode Prospect.is_mobile().
        # 💡 Idem pour les exports CSV/Excel (→ services/export.py), la génération des relances + MAJ
        # 💡 Notion (page Relances), la suppression des fichiers d'historique (Réglages) et les
        # 💡 contrôles « il manque une clé » écrits 3 fois dans page_prospection (→ une fonction).
        # 💡 Une API FastAPI pourrait ensuite réutiliser exactement ces mêmes fonctions.
        mobiles_ok  = sum(1 for p in prospects if p.phone and (
            p.phone.replace(" ", "").startswith("06") or
            p.phone.replace(" ", "").startswith("07")
        ))

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        # 📘 Boucle sur une liste de tuples (colonne, valeur, libellé, couleur) déballés dans 4
        # 📘 variables ; chaque tour dessine une carte HTML (classes CSS définies en haut).
        for col, value, label, color in [
            (m1, len(prospects),  "Total prospects",    "#667eea"),
            (m2, no_site,         "Sans site 🔴",        "#f38ba8"),
            (m3, critical,        "Score < 40 🟡",       "#fab387"),
            (m4, avg_score,       "Score moyen",         "#667eea"),
            (m5, emails_ok,       "📧 Emails trouvés",   "#a6e3a1"),
            (m6, mobiles_ok,      "📱 Mobiles trouvés",  "#a6e3a1"),
        ]:
            with col:
                st.markdown(f"""<div class='metric-card'>
                    <div class='metric-value' style='color:{color}'>{value}</div>
                    <div class='metric-label'>{label}</div>
                </div>""", unsafe_allow_html=True)

        st.markdown("")

        # Filtre
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            filter_opt = st.radio(
                "Afficher :",
                ["Tous", "Sans site uniquement", "Email trouvé", "Mobile trouvé", "Score < 40"],
                horizontal=True,
            )
        with col_f2:
            sort_opt = st.selectbox("Trier par :", ["Opportunité (score ↑)", "Nom (A→Z)", "Note Google (↓)"])

        # Application des filtres
        # 📘 Filtre et tri se font en mémoire, en Python, à chaque rerun (quand tu changes un choix).
        # 📘 sorted(..., key=lambda p: p.name) trie selon la valeur renvoyée par la lambda.
        # 📘 « Opportunité » ne retrie pas : on garde l'ordre déjà calculé par pipeline.py.
        filtered = prospects
        if filter_opt == "Sans site uniquement":
            filtered = [p for p in prospects if not p.has_website()]
        elif filter_opt == "Email trouvé":
            filtered = [p for p in prospects if p.email]
        elif filter_opt == "Mobile trouvé":
            filtered = [p for p in prospects if p.phone and (
                p.phone.replace(" ", "").startswith("06") or
                p.phone.replace(" ", "").startswith("07")
            )]
        elif filter_opt == "Score < 40":
            filtered = [p for p in prospects if p.score < 40]

        if sort_opt == "Nom (A→Z)":
            filtered = sorted(filtered, key=lambda p: p.name)
        elif sort_opt == "Note Google (↓)":
            filtered = sorted(filtered, key=lambda p: p.rating or 0, reverse=True)

        st.markdown(f"### 🏆 {len(filtered)} prospect(s) — triés par {sort_opt.lower()}")

        for p in filtered:
            score_emoji = "🟢" if p.score >= 70 else ("🟡" if p.score >= 40 else "🔴")
            email_badge = "📧✅" if p.email else "📧❌"
            phone_type = ""
            if p.phone:
                num = p.phone.replace(" ", "")
                phone_type = "📱" if (num.startswith("06") or num.startswith("07")) else "☎️"

            header = f"{score_emoji} **{p.name}** — Score {p.score}/100 — {email_badge} {phone_type}"
            # 📘 Un expander par prospect. getattr(p, "dirigeant", "") lit l'attribut s'il existe, sinon
            # 📘 renvoie "" (utile pour d'anciens fichiers JSON sans ce champ).
            with st.expander(header):
                c1, c2 = st.columns([1, 1])
                with c1:
                    if getattr(p, "dirigeant", ""):
                        _pq = f" — {p.dirigeant_qualite}" if p.dirigeant_qualite else ""
                        st.markdown(f"**👤 Dirigeant :** {p.dirigeant}{_pq}")
                    st.markdown(f"**📍 Adresse :** {p.address}")
                    # Téléphone avec badge mobile/fixe
                    if p.phone:
                        num = p.phone.replace(" ", "")
                        is_mobile = num.startswith("06") or num.startswith("07")
                        badge = "📱 Mobile" if is_mobile else "☎️ Fixe"
                        st.markdown(f"**Téléphone :** {p.phone} — `{badge}`")
                    else:
                        st.markdown("**Téléphone :** —")

                    # Email avec statut
                    if p.email:
                        from services.email_check import STATUS_BADGES as _EB
                        _st = getattr(p, "email_status", "") or ""
                        _badge = f" {_EB.get(_st, '')} _{p.email_status_reason}_" if _st else ""
                        st.markdown(f"**📧 Email trouvé :** `{p.email}`{_badge}")
                    else:
                        st.markdown("**📧 Email :** non trouvé sur le site")

                    # Site web + CMS détecté
                    if p.website:
                        cms_badge = f" `{p.cms}`" if p.cms else ""
                        st.markdown(f"**🌐 Site :** [{p.website}]({p.website}){cms_badge}")
                    else:
                        st.markdown("**🌐 Site :** ❌ Aucun site web")

                    st.markdown(f"**🔑 Mot-clé :** `{p.keyword}`")
                    if p.rating:
                        stars = "⭐" * round(p.rating)
                        st.markdown(f"**Note Google :** {stars} {p.rating}/5 ({p.user_ratings_total} avis)")
                    if p.maps_url:
                        st.markdown(f"[📌 Voir sur Google Maps]({p.maps_url})")

                with c2:
                    st.markdown("**🔬 Problèmes détectés :**")
                    if p.issues:
                        for issue in p.issues:
                            short = issue.split("→")[0].strip()
                            st.markdown(f"<span class='issue-chip'>⚠️ {short}</span>", unsafe_allow_html=True)
                    else:
                        st.markdown("✅ Aucun problème majeur détecté")

                st.markdown("**✉️ Brouillon cold email :**")
                st.code(p.email_draft, language=None)

        # ---------------------------------------------------------------------------
        # Export
        # ---------------------------------------------------------------------------
        st.markdown("---")
        st.markdown("### 💾 Export")

        # 📘 st.download_button : bouton qui fait télécharger au navigateur des données préparées en
        # 📘 mémoire. io.StringIO / io.BytesIO = de faux fichiers en RAM (texte / octets) dans lesquels
        # 📘 csv et openpyxl « écrivent » sans rien créer sur le disque.
        # 💡 Pas de st.cache_data dans ce fichier : ces 3 exports (JSON, CSV, Excel) sont reconstruits
        # 💡 à CHAQUE rerun tant que des résultats sont affichés (idem load_history en Statistiques).
        # 💡 Mets la construction dans une fonction décorée @st.cache_data, avec un argument simple
        # 💡 (nom du fichier de campagne), ou génère le fichier seulement au clic.
        import csv, io
        col_e1, col_e2, col_e3 = st.columns(3)

        with col_e1:
            json_data = json.dumps([p.to_dict() for p in filtered], ensure_ascii=False, indent=2)
            st.download_button(
                label="⬇️ Télécharger JSON",
                data=json_data,
                file_name=f"prospects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
            )

        with col_e2:
            csv_buffer = io.StringIO()
            fieldnames = ["name", "dirigeant", "dirigeant_qualite", "keyword", "address", "phone",
                          "email", "website", "cms", "rating", "score", "issues_count",
                          "issues_summary", "maps_url"]
            writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
            writer.writeheader()
            for p in filtered:
                writer.writerow({
                    "name": p.name,
                    "dirigeant": getattr(p, "dirigeant", "") or "",
                    "dirigeant_qualite": getattr(p, "dirigeant_qualite", "") or "",
                    "keyword": p.keyword,
                    "address": p.address,
                    "phone": p.phone or "",
                    "email": p.email or "",
                    "website": p.website or "",
                    "cms": p.cms or "",
                    "rating": p.rating or "",
                    "score": p.score,
                    "issues_count": len(p.issues),
                    "issues_summary": " | ".join(p.issues[:3]),
                    "maps_url": p.maps_url,
                })
            st.download_button(
                label="⬇️ Télécharger CSV",
                data=csv_buffer.getvalue().encode("utf-8-sig"),
                file_name=f"prospects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with col_e3:
            # 📘 openpyxl est optionnel : s'il n'est pas installé, l'import lève ImportError et on
            # 📘 affiche un bouton grisé à la place.
            try:
                import openpyxl
                from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
                from openpyxl.utils import get_column_letter

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Prospects"

                headers = ["Nom", "Mot-clé", "Adresse", "Téléphone", "Email",
                           "Site", "CMS", "Note ⭐", "Score", "Nb problèmes", "Problèmes (top 3)", "Google Maps"]
                col_widths = [30, 15, 40, 15, 32, 40, 12, 8, 8, 12, 70, 50]

                header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
                header_font = Font(color="FFFFFF", bold=True)
                thin_border = Border(
                    left=Side(style="thin"), right=Side(style="thin"),
                    top=Side(style="thin"), bottom=Side(style="thin"),
                )

                # 📘 enumerate(..., 1) numérote à partir de 1 (Excel compte les colonnes depuis 1) ;
                # 📘 zip associe chaque en-tête à sa largeur.
                for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
                    cell = ws.cell(row=1, column=ci, value=h)
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.border = thin_border
                    ws.column_dimensions[get_column_letter(ci)].width = w
                ws.row_dimensions[1].height = 20

                fill_green  = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
                fill_yellow = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
                fill_red    = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

                for ri, p in enumerate(filtered, 2):
                    score_fill = fill_green if p.score >= 70 else (fill_yellow if p.score >= 40 else fill_red)
                    row_vals = [
                        p.name, p.keyword, p.address, p.phone or "",
                        p.email or "", p.website or "", p.cms or "",
                        p.rating or "", p.score, len(p.issues),
                        " | ".join(p.issues[:3]), p.maps_url,
                    ]
                    for ci, val in enumerate(row_vals, 1):
                        cell = ws.cell(row=ri, column=ci, value=val)
                        cell.border = thin_border
                        cell.alignment = Alignment(vertical="center", wrap_text=(ci == 11))
                        if ci == 9:  # Score
                            cell.fill = score_fill
                            cell.font = Font(bold=True)

                ws.freeze_panes = "A2"

                _xls_buf = io.BytesIO()
                wb.save(_xls_buf)
                st.download_button(
                    label="⬇️ Télécharger Excel",
                    data=_xls_buf.getvalue(),
                    file_name=f"prospects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            except ImportError:
                st.button("⬇️ Excel — installe openpyxl", disabled=True, use_container_width=True)
                st.caption("`pip install openpyxl`")

    # ---------------------------------------------------------------------------
    # Sauvegarde profil custom
    # ---------------------------------------------------------------------------
    st.markdown("---")
    # 📘 Enregistre un profil perso via profile_manager.save_custom_profile. ⚠️ Rien dans ce
    # 📘 fichier n'affiche ni ne recharge ces profils (PROFILES / get_profile sont importés mais
    # 📘 inutilisés) : le message « Il apparaîtra dans la liste » ne correspond à aucun écran.
    with st.expander("💾 Sauvegarder ce profil pour une prochaine fois"):
        save_name = st.text_input("Nom du profil", placeholder="Ex: Mon profil Lyon Dev Web")
        if st.button("💾 Sauvegarder") and save_name:
            from profile_manager import save_custom_profile
            from profiles import Profile
            import re, uuid
            # 📘 `re` = expressions régulières : [^a-z0-9] remplace tout caractère non alphanumérique.
            custom_id = "custom_" + re.sub(r"[^a-z0-9]", "_", save_name.lower())[:20]
            new_profile = Profile(
                id=custom_id,
                emoji="⭐",
                name=save_name,
                description=f"Profil personnalisé — {location}",
                keywords=keywords,
                location=location,
                your_title=your_title,
                your_offer=your_offer,
                email_hook=email_hook,
                sms_hook=sms_hook,
                qualification_criteria=[],
                radius=radius,
                max_results=max_results,
            )
            save_custom_profile(new_profile)
            st.success(f"✅ Profil « {save_name} » sauvegardé ! Il apparaîtra dans la liste au prochain lancement.")

# 📘 ═══ SECTION : PAGE « PIPELINE » ═══
# 📘 Le mini-CRM : tous les prospects de la base SQLite, filtrables, avec statut et notes.
# 📘 Lit dans crm_store : status_counts, STATUS_ORDER / STATUS_LABELS, list_prospects
# 📘   (filtres statut / email / recherche), get_events (historique), get_linkedin_templates.
# 📘 Écrit dans crm_store : set_status, set_notes (+ mark_linkedin_sent via le panneau).
def page_pipeline():
    # ---------------------------------------------------------------------------
    # 📋 Pipeline CRM — tous les prospects suivis, par statut
    # ---------------------------------------------------------------------------
    _pipe_counts = {}
    try:
        _pipe_counts = crm_store.status_counts()
    except Exception:
        pass
    _pipe_total = sum(_pipe_counts.values())

    st.title(f"📋 Pipeline — {_pipe_total} prospect(s)")
    st.caption("Tous tes prospects suivis, par statut. Change un statut ou ajoute une note en un clic.")
    if not _pipe_total:
        st.info(
            "Ton pipeline est vide. Lance une prospection : les prospects trouvés "
            "y seront ajoutés automatiquement et tu pourras suivre chacun d'eux "
            "(contacté, intéressé, RDV, client…)."
        )
    else:
        # Compteurs par statut
        _active = [s for s in crm_store.STATUS_ORDER if _pipe_counts.get(s)]
        if _active:
            _cols = st.columns(len(_active))
            for _c, _s in zip(_cols, _active):
                _c.metric(crm_store.STATUS_LABELS[_s], _pipe_counts[_s])

        st.markdown("---")

        # Filtres
        _f1, _f2, _f3 = st.columns([2, 2, 3])
        with _f1:
            _filter_status = st.selectbox(
                "Statut",
                options=["(tous)"] + crm_store.STATUS_ORDER,
                format_func=lambda s: "Tous les statuts" if s == "(tous)" else crm_store.STATUS_LABELS[s],
                key="pipe_status",
            )
        with _f2:
            _filter_email = st.selectbox(
                "Email",
                options=["(tous)", "avec", "sans"],
                format_func=lambda v: {"(tous)": "Avec ou sans email",
                                       "avec": "📧 Avec email seulement",
                                       "sans": "Sans email"}[v],
                key="pipe_email",
            )
        with _f3:
            _filter_search = st.text_input("Rechercher", placeholder="Nom, email, site…", key="pipe_search")

        # 📘 Le filtrage se fait en SQL dans crm_store (WHERE … LIKE …), pas en Python.
        _rows = crm_store.list_prospects(
            status=None if _filter_status == "(tous)" else _filter_status,
            has_email={"(tous)": None, "avec": True, "sans": False}[_filter_email],
            search=_filter_search.strip(),
        )
        st.caption(f"{len(_rows)} prospect(s) affiché(s)")

        for _row in _rows:
            _pid = _row["place_id"]
            _label = f"{crm_store.STATUS_LABELS.get(_row['status'], _row['status'])} · **{_row['name']}**"
            if _row.get("email"):
                _eb = {"valide": " ✅", "risque": " ⚠️", "invalide": " ❌"}.get(_row.get("email_status") or "", "")
                _label += f" · 📧 {_row['email']}{_eb}"
            with st.container(border=True):
                st.markdown(_label)
                _meta = []
                if _row.get("dirigeant"):
                    _q = f" ({_row['dirigeant_qualite']})" if _row.get("dirigeant_qualite") else ""
                    _meta.append(f"👤 {_row['dirigeant']}{_q}")
                if _row.get("phone"):
                    _meta.append(f"📞 {_row['phone']}")
                if _row.get("website"):
                    _meta.append(f"[🌐 site]({_row['website']})")
                if _row.get("score") is not None:
                    _meta.append(f"score {_row['score']}/100")
                if _row.get("last_contact_date"):
                    _meta.append(f"dernier contact {_row['last_contact_date']}")
                if _row.get("followup_step"):
                    _meta.append(f"{_row['followup_step']} relance(s)")
                if _meta:
                    st.caption(" · ".join(_meta))

                _a1, _a2 = st.columns([2, 3])
                with _a1:
                    # 📘 Motif « comparer puis écrire » : le selectbox renvoie la valeur choisie ;
                    # 📘 si elle diffère
                    # 📘 du statut en base, c'est que tu viens de la changer → on écrit puis
                    # 📘 on relance le script.
                    # 📘 (Autre façon de faire : on_change=, comme dans Réglages.)
                    _new_status = st.selectbox(
                        "Statut", options=crm_store.STATUS_ORDER,
                        index=crm_store.STATUS_ORDER.index(_row["status"])
                        if _row["status"] in crm_store.STATUS_ORDER else 0,
                        format_func=lambda s: crm_store.STATUS_LABELS[s],
                        key=f"st_{_pid}", label_visibility="collapsed",
                    )
                    if _new_status != _row["status"]:
                        crm_store.set_status(_pid, _new_status)
                        st.rerun()
                with _a2:
                    _new_notes = st.text_input(
                        "Notes", value=_row.get("notes") or "",
                        placeholder="Note (rappeler en janvier, budget serré…)",
                        key=f"nt_{_pid}", label_visibility="collapsed",
                    )
                    # 📘 Un text_input déclenche un rerun quand tu valides (Entrée ou clic
                    # 📘 ailleurs) : c'est là
                    # 📘 que la différence est détectée et la note enregistrée.
                    if _new_notes != (_row.get("notes") or ""):
                        crm_store.set_notes(_pid, _new_notes)
                        st.toast("Note enregistrée ✅")

                with st.expander("💬 LinkedIn", expanded=False):
                    _linkedin_panel(_row, key_prefix=f"pl_{_pid}")

                _events = crm_store.get_events(_pid, limit=5)
                if _events:
                    with st.expander("🕮 Historique", expanded=False):
                        for _e in _events:
                            st.caption(f"{_e['at'][:16].replace('T', ' ')} — **{_e['kind']}** {_e['detail']}")

# 📘 ═══ SECTION : PAGE « RELANCES » ═══
# 📘 3 blocs : emails programmés (services/scheduler), suivi des réponses IMAP
# 📘 (services/reply_tracker), séquence de relances des contacts sans réponse.
# 📘 ⚠️ Cette page n'utilise PAS crm_store : elle lit/écrit l'historique JSON via
# 📘 history_manager (_load_contacted_data, get_due_followups, mark_followup_sent,
# 📘 mark_as_responded, get_notion_page_id) et met à jour Notion si c'est ton CRM.
# 💡 Deux sources de vérité : Ma journée / Pipeline lisent la base SQLite (crm_store) alors que
# 💡 Relances et Statistiques lisent output/contacted_place_ids.json (history_manager).
# 💡 « ✅ Répondu » ici n'écrit que dans le JSON ; « 💬 A répondu » (Ma journée) n'écrit que
# 💡 dans SQLite. À terme : tout passer par crm_store (et une seule API /prospects).
def page_relances():
    st.title("🔄 Relances")
    st.caption("Séquences de relance, emails programmés et suivi des réponses.")
    # ---------------------------------------------------------------------------
    # Emails programmés
    # ---------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("📬 Emails programmés"):
        from services import scheduler as _sched_ui
        # Garde les identifiants en RAM pour que l'envoi différé fonctionne
        # (ils ne sont jamais écrits sur disque).
        # 📘 On confie le mot de passe Gmail (en RAM seulement) au scheduler, pour que son thread
        # 📘 d'envoi différé puisse envoyer même quand tu n'es pas sur cette page.
        if gmail_address and gmail_password:
            _sched_ui.remember_credentials(gmail_address, gmail_password)
        _stats = _sched_ui.get_stats()
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        col_s1.metric("En attente", _stats["pending"])
        col_s2.metric("En retard", _stats["overdue"])
        col_s3.metric("Envoyés", _stats["sent"])
        col_s4.metric("Total", _stats["total"])

        if _stats["total"] == 0:
            st.caption("Aucun email programmé pour l'instant.")
        else:
            if _stats["overdue"] > 0:
                st.warning(
                    f"⚠️ {_stats['overdue']} email(s) en retard — leur heure d'envoi est passée "
                    "(l'app était probablement éteinte). Ils partent au prochain cycle, "
                    "ou immédiatement avec le bouton ci-dessous."
                )
            if _stats["pending"] > 0:
                st.info(f"⏰ {_stats['pending']} email(s) en attente — vérification toutes les 60 secondes.")
            if not _sched_ui.credentials_available():
                st.error(
                    "🔑 Aucun mot de passe Gmail disponible pour l'envoi différé. "
                    "Renseigne-le dans ⚙️ Réglages, **ou mieux** : ajoute `GMAIL_APP_PASSWORD` "
                    "dans les variables Railway pour que les envois programmés survivent aux redémarrages."
                )
            # 📘 `cond and st.button(...)` : si cond est faux, Python n'évalue pas la suite
            # 📘 (court-circuit) → le bouton n'est même pas affiché.
            if _stats["pending"] > 0 and st.button("📤 Envoyer maintenant les emails dus", use_container_width=True):
                _r = _sched_ui.process_due()
                if _r["sent"]:
                    st.success(f"✅ {_r['sent']} email(s) envoyé(s).")
                if _r["failed"]:
                    st.error(f"❌ {_r['failed']} échec(s) — vérifie tes identifiants Gmail.")
                if _r["skipped_no_credentials"]:
                    st.warning(f"🔑 {_r['skipped_no_credentials']} email(s) non envoyé(s) : mot de passe Gmail manquant.")
                st.rerun()

        st.caption(
            "ℹ️ Les emails programmés ne partent que si l'application tourne. "
            "Si Railway met le service en veille, ils partiront au prochain réveil (rattrapage automatique)."
        )

    # ---------------------------------------------------------------------------
    # Suivi de réponses
    # ---------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("📬 Suivi des réponses (IMAP)"):
        from services import reply_tracker as _rt_ui
        _rt_running = _rt_ui.is_running()
        if _rt_running:
            st.success("✅ Suivi actif — vérifie les réponses Gmail toutes les 5 minutes.")
        elif gmail_address and gmail_password:
            _rt_ui.ensure_running(gmail_address, gmail_password)
            st.info("⏳ Thread de suivi en cours de démarrage…")
        else:
            st.info("💡 Renseigne ton adresse Gmail et ton mot de passe d'application pour activer le suivi automatique des réponses.")
        from history_manager import _load_contacted_data as _lcd
        _cdata = _lcd()
        _responded = sum(1 for v in _cdata.values() if v.get("responded"))
        _total_c   = len(_cdata)
        if _total_c:
            col_rt1, col_rt2 = st.columns(2)
            col_rt1.metric("Prospects contactés", _total_c)
            col_rt2.metric("Réponses reçues", _responded)

    # ---------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("🔄 Relances — contacts sans réponse"):
        from history_manager import get_due_followups, mark_as_responded, mark_followup_sent
        followup_delay = int(os.getenv("FOLLOWUP_DELAY_DAYS", "5"))
        due = get_due_followups(followup_delay)

        from services.mailer import MAX_FOLLOWUPS
        if not due:
            st.success(f"✅ Aucun contact à relancer (seuil : {followup_delay} jours sans réponse).")
        else:
            st.info(
                f"**{len(due)} contact(s)** à relancer — séquence de {MAX_FOLLOWUPS} relances "
                f"à angles distincts, {followup_delay} jours entre chaque message."
            )

            # Bouton pour générer la PROCHAINE relance de la séquence pour chaque contact
            # 📘 Le clic génère pour chaque contact le brouillon de sa relance suivante, AVANCE son étape
            # 📘 (mark_followup_sent) et, si Notion est ton CRM, met à jour le statut Notion. Les
            # 📘 brouillons sont rangés en session pour rester affichés après st.rerun().
            # 📘 Rien n'est envoyé : ce sont des textes à copier ou télécharger.
            if st.button("📝 Générer les prochaines relances", key="gen_followup"):
                from services.google_maps import Prospect as P
                from services.mailer import draft_followup_email
                drafts = []
                for contact in due:
                    next_step = int(contact.get("followup_step", 0)) + 1
                    p = P(
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
                    label = f"{p.name}  ·  relance {next_step}/{MAX_FOLLOWUPS}"
                    drafts.append((label, draft_followup_email(p, step=next_step), contact["place_id"]))
                    mark_followup_sent(contact["place_id"])
                    if crm_type == "notion" and crm_key:
                        from history_manager import get_notion_page_id
                        from services.crm.notion import NotionExporter
                        _np = get_notion_page_id(contact["place_id"])
                        if _np:
                            _status = "clôturé" if next_step >= MAX_FOLLOWUPS else f"relancé ({next_step}/{MAX_FOLLOWUPS})"
                            NotionExporter(crm_key, crm_extra.get("database_id", "")).update_status(_np, _status)
                st.session_state["followup_drafts"] = drafts
                st.success(f"✅ {len(drafts)} relance(s) générée(s).")
                st.rerun()

            # Affichage des drafts générés
            if st.session_state.get("followup_drafts"):
                for name, draft, _ in st.session_state["followup_drafts"]:
                    st.markdown(f"**{name}**")
                    st.code(draft, language=None)
                import io
                # 📘 Malgré son nom, zip_content est un simple texte (.txt) : tous les
                # 📘 brouillons à la suite.
                zip_content = "\n\n" + ("=" * 60 + "\n\n").join(
                    f"{name}\n{draft}" for name, draft, _ in st.session_state["followup_drafts"]
                )
                st.download_button(
                    "⬇️ Télécharger tous les emails de relance (.txt)",
                    data=zip_content.encode("utf-8"),
                    file_name=f"relances_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

            # Liste individuelle avec bouton "A répondu"
            st.markdown("---")
            st.markdown("**Marquer comme répondu :**")
            for contact in due:
                col_name, col_btn = st.columns([4, 1])
                with col_name:
                    date_str = contact.get("first_contact_date", "?")
                    email_str = contact.get("email", "—")
                    st.markdown(f"**{contact['name']}** — contacté le {date_str} — `{email_str}`")
                with col_btn:
                    if st.button("✅ Répondu", key=f"responded_{contact['place_id']}"):
                        mark_as_responded(contact["place_id"])
                        if crm_type == "notion" and crm_key:
                            from history_manager import get_notion_page_id
                            from services.crm.notion import NotionExporter
                            _np = get_notion_page_id(contact["place_id"])
                            if _np:
                                NotionExporter(crm_key, crm_extra.get("database_id", "")).update_status(_np, "répondu")
                        st.rerun()

# 📘 ═══ SECTION : PAGE « STATISTIQUES » ═══
# 📘 Lit : history_manager.load_history (une entrée par campagne, écrite par pipeline.py),
# 📘   _load_contacted_data (contacts + réponses), get_ab_stats (test A/B), les fichiers
# 📘   output/prospects_*.json (bouton « Charger ») et st.session_state.prospects.
# 📘 N'écrit rien sur disque ni dans crm_store : « Charger » remplit seulement
# 📘   st.session_state.prospects, affichés ensuite dans la page Nouvelle campagne.
def page_statistiques():
    st.title("📊 Statistiques")
    st.caption("Tes campagnes passées et leurs résultats.")
    # ---------------------------------------------------------------------------
    # Dashboard de statistiques
    # ---------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("📊 Dashboard — Statistiques globales"):
        # 📘 Importer une fonction « _privée » d'un autre module fonctionne, mais contourne la
        # 📘 convention du « _ » (signe qu'il manque une fonction publique dans history_manager).
        from history_manager import load_history as _lh, _load_contacted_data as _lcd2
        _hist = _lh()
        _cdata2 = _lcd2()

        if not _hist:
            st.info("Lancez au moins une campagne pour voir les statistiques.")
        else:
            _total_runs      = len(_hist)
            _total_prospects = sum(r.get("total_prospects", 0) for r in _hist)
            _total_emails    = sum(r.get("emails_trouvés", 0)  for r in _hist)
            _total_mobiles   = sum(r.get("mobiles_trouvés", 0) for r in _hist)
            _total_sent      = sum(r.get("emails_envoyés", 0)  for r in _hist)
            _total_sms_sent  = sum(r.get("sms_envoyés", 0)     for r in _hist)
            _total_responded = sum(1 for v in _cdata2.values() if v.get("responded"))
            _total_contacted = len(_cdata2)

            # Métriques globales
            dc1, dc2, dc3, dc4, dc5, dc6 = st.columns(6)
            dc1.metric("Campagnes", _total_runs)
            dc2.metric("Prospects total", _total_prospects)
            dc3.metric("Emails trouvés", _total_emails)
            dc4.metric("Emails envoyés", _total_sent)
            dc5.metric("SMS envoyés", _total_sms_sent)
            _rrate = f"{_total_responded / _total_contacted * 100:.0f}%" if _total_contacted else "—"
            dc6.metric("Taux de réponse", _rrate)

            st.markdown("---")

            # Graphique : prospects + emails par campagne (10 dernières)
            try:
                # 📘 pandas : librairie de tableaux de données (DataFrame).
                # 📘 st.bar_chart trace un DataFrame
                # 📘 directement ; set_index choisit la colonne utilisée comme axe horizontal.
                import pandas as _pd

                _runs_data = [{
                    "Campagne": r["date"][:10],
                    "Prospects": r.get("total_prospects", 0),
                    "Emails": r.get("emails_trouvés", 0),
                    "Mobiles": r.get("mobiles_trouvés", 0),
                } for r in reversed(_hist[:10])]
                _df_runs = _pd.DataFrame(_runs_data).set_index("Campagne")
                st.markdown("**Prospects et emails par campagne (10 dernières)**")
                st.bar_chart(_df_runs[["Prospects", "Emails"]])

                # Top mots-clés
                _kw_counts: dict = {}
                for r in _hist:
                    for kw in r.get("keywords", []):
                        _kw_counts[kw] = _kw_counts.get(kw, 0) + r.get("total_prospects", 0)
                if _kw_counts:
                    _top_kw = sorted(_kw_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                    _df_kw = _pd.DataFrame(_top_kw, columns=["Mot-clé", "Prospects"]).set_index("Mot-clé")
                    st.markdown("**Top mots-clés (par nombre de prospects cumulés)**")
                    st.bar_chart(_df_kw)

                # Distribution des scores de la dernière campagne
                if st.session_state.prospects:
                    _scores = [p.score for p in st.session_state.prospects]
                    _bins = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
                    for s in _scores:
                        if s <= 20:    _bins["0-20"]   += 1
                        elif s <= 40:  _bins["21-40"]  += 1
                        elif s <= 60:  _bins["41-60"]  += 1
                        elif s <= 80:  _bins["61-80"]  += 1
                        else:          _bins["81-100"] += 1
                    _df_score = _pd.DataFrame(list(_bins.items()), columns=["Score", "Nombre"]).set_index("Score")
                    st.markdown("**Distribution des scores (campagne en cours)**")
                    st.bar_chart(_df_score)

            except ImportError:
                st.caption("pandas non disponible — install `pandas` pour les graphiques.")

    # ---------------------------------------------------------------------------
    # Test A/B — Statistiques de templates
    # ---------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("🧪 Test A/B — Performance des templates email"):
        from history_manager import get_ab_stats
        ab = get_ab_stats()
        st.caption("Les prospects sont répartis 50/50 entre le template A (narratif) et le template B (court/direct).")
        col_a, col_b = st.columns(2)
        for col, variant, label in [(col_a, "A", "Template A — Narratif"), (col_b, "B", "Template B — Direct")]:
            s = ab.get(variant, {"total": 0, "responded": 0})
            rate = f"{s['responded']/s['total']*100:.0f}%" if s["total"] else "—"
            with col:
                st.markdown(f"**{label}**")
                st.metric("Envoyés", s["total"])
                st.metric("Réponses", s["responded"])
                st.metric("Taux de réponse", rate)

    # ---------------------------------------------------------------------------
    # Historique des campagnes
    # ---------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("🕐 Historique des campagnes"):
        from history_manager import load_history
        history = load_history()
        if not history:
            st.info("Aucune campagne lancée pour l'instant.")
        else:
            st.caption("Clique sur « 📂 Charger » pour réafficher tous les prospects d'une campagne dans l'interface.")
            for _i, run in enumerate(history):
                kw_str = ", ".join(run.get("keywords", [])[:3])
                extra_kw = len(run.get("keywords", [])) - 3
                kw_display = kw_str + (f" +{extra_kw}" if extra_kw > 0 else "")
                src_str = " · ".join(run.get("sources", [])) or "—"
                sector = run.get("target_sector", "")
                with st.container():
                    col_h1, col_h2 = st.columns([3, 1])
                    with col_h1:
                        st.markdown(
                            f"**{run['date']}** — {run['profile']} — {run['location']}"
                            + (f" — *{sector}*" if sector else "")
                        )
                        st.caption(f"Sources : {src_str} | Mots-clés : {kw_display}")
                    with col_h2:
                        st.markdown(f"**{run['total_prospects']}** prospects")
                    # Métriques détaillées
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Sans site", run.get("sans_site", 0))
                    m2.metric("Emails scrapés", run.get("emails_trouvés", 0))
                    m3.metric("Mobiles", run.get("mobiles_trouvés", 0))
                    m4.metric("Emails envoyés", run.get("emails_envoyés", 0))
                    m5.metric("SMS envoyés", run.get("sms_envoyés", 0))
                    # Répartition offres
                    _ot = run.get("offer_types", {})
                    if _ot:
                        _ot_labels = {
                            "creation": "Création", "migration": "Migration",
                            "refonte": "Refonte", "widget": "Widget", "audit": "Audit",
                        }
                        _ot_str = " | ".join(
                            f"{_ot_labels.get(k, k)} ×{v}" for k, v in sorted(_ot.items(), key=lambda x: -x[1])
                        )
                        st.caption(f"Offres proposées : {_ot_str}")
                    if run.get("crm_synchronisés"):
                        st.caption(f"CRM : {run['crm_synchronisés']} synchronisé(s)")
                    # Bouton pour recharger tous les prospects de cette campagne dans l'UI
                    _fichier = run.get("fichier", "")
                    if _fichier and os.path.exists(_fichier):
                        # 📘 key=f"load_camp_{_i}" : l'index de boucle rend chaque bouton unique.
                        if st.button("📂 Charger cette campagne", key=f"load_camp_{_i}", use_container_width=True):
                            try:
                                with open(_fichier, "r", encoding="utf-8") as _cf:
                                    _cdata = json.load(_cf)
                                from services.google_maps import Prospect as _P
                                st.session_state.prospects = [_P.from_dict(d) for d in _cdata]
                                st.session_state["_restored_from"] = f"{run['date']} — {run['profile']}"
                                st.session_state.running = False
                                st.session_state.run_done = False
                                st.toast(f"Campagne du {run['date']} chargée ✅", icon="📂")
                                st.rerun()
                            except Exception as _e:
                                st.error(f"Impossible de charger cette campagne : {_e}")
                    else:
                        st.caption("⚠️ Fichier de résultats introuvable (effacé lors d'un redéploiement).")
                st.divider()

# 📘 ═══ SECTION : PAGE « RÉGLAGES » ═══
# 📘 Réglages de connexion et signature : lus via _cfg, enregistrés via _persist_cfg
# 📘   (session + settings.json ; gmail_password en session seulement).
# 📘 crm_store : get_delay / set_delay, get_linkedin_templates / set_linkedin_template /
# 📘   reset_linkedin_template, get_user_franchises / set_user_franchises.
# 📘 Autres : history_manager.load_contacted_ids + suppression des fichiers JSON d'historique,
# 📘   services/cache (count, clear_all : cache disque des analyses, rien à voir avec st.cache).
def page_reglages():
    st.title("⚙️ Réglages")
    st.caption("Chaque champ est enregistré automatiquement dès que tu le modifies.")

    # 📘 Fonction définie DANS une fonction : un raccourci local pour créer un champ de réglage
    # 📘 « auto-enregistré ». value=_cfg(...) pré-remplit ; key="w_<key>" + on_change=_persist_cfg
    # 📘 enregistrent dès que tu valides la saisie. type="password" masque les secrets (●●●).
    def _field(label, key, env="", secret=False, placeholder="", help_=None):
        return st.text_input(
            label, value=_cfg(key, env), key=f"w_{key}", type="password" if secret else "default",
            placeholder=placeholder, help=help_, on_change=_persist_cfg, args=(key,),
        )

    # ---------------------------------------------------------------------------
    # Connexions & clés API
    # ---------------------------------------------------------------------------
    st.subheader("🔌 Connexions")

    with st.container(border=True):
        st.markdown("**🗺️ Google** — recherche Maps, performance des sites · "
                    "[obtenir une clé ↗](https://console.cloud.google.com/apis/credentials)")
        _field("Clé API Google", "google_api_key", "GOOGLE_PLACES_API_KEY", secret=True, placeholder="AIzaSy…")
        with st.expander("Comment créer cette clé ?"):
            st.markdown(
                "1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → "
                "**Créer des identifiants** → **Clé API**\n"
                "2. Dans **Bibliothèque d'API**, active *Places API*, *PageSpeed Insights API* "
                "(et *Custom Search JSON API* pour la source Google Search)\n"
                "3. Copie la clé (`AIzaSy…`) et colle-la ci-dessus"
            )
        _field("Custom Search Engine ID (source Google Search, optionnel)", "google_cx", "GOOGLE_CX",
               placeholder="017576…:xxxxxxx",
               help_="Créé sur programmablesearchengine.google.com → « Rechercher dans tout le web ».")

    with st.container(border=True):
        st.markdown("**📧 Gmail** — envoi des emails et détection des réponses · "
                    "[mot de passe d'application ↗](https://myaccount.google.com/apppasswords)")
        _field("Adresse Gmail", "gmail_address", "GMAIL_ADDRESS", placeholder="toi@gmail.com")
        _field("Mot de passe d'application (pas ton vrai mot de passe)", "gmail_password",
               "GMAIL_APP_PASSWORD", secret=True, placeholder="xxxx xxxx xxxx xxxx")
        st.caption("🔒 Le mot de passe n'est jamais enregistré sur disque : il reste le temps de la "
                   "session. Pour ne plus le ressaisir, ajoute `GMAIL_APP_PASSWORD` dans les variables Railway.")
        with st.expander("Comment créer un mot de passe d'application ?"):
            st.markdown(
                "1. [myaccount.google.com/security](https://myaccount.google.com/security) → active la "
                "**validation en 2 étapes**\n"
                "2. Cherche **« Mots de passe des applications »** → nom « ProspectionBot » → **Générer**\n"
                "3. Copie les 16 caractères affichés"
            )

    with st.container(border=True):
        st.markdown("**🗂️ CRM** — synchronisation des prospects")
        _crm_opts = ["aucun", "notion", "hubspot"]
        # 📘 Changer de CRM appelle _persist_cfg → rerun → crm_type (calculé en haut du fichier) a
        # 📘 changé, donc les champs Notion ou HubSpot ci-dessous apparaissent.
        st.selectbox(
            "CRM", options=_crm_opts, index=_crm_opts.index(crm_type) if crm_type in _crm_opts else 0,
            format_func=lambda c: {"aucun": "Aucun", "notion": "Notion", "hubspot": "HubSpot"}[c],
            key="w_crm_type", on_change=_persist_cfg, args=("crm_type",),
        )
        if crm_type == "notion":
            _field("Token d'intégration Notion", "notion_api_key", "NOTION_API_KEY", secret=True,
                   placeholder="ntn_… ou secret_…")
            _field("Database ID (ou lien complet de la base)", "notion_database_id", "NOTION_DATABASE_ID",
                   placeholder="c2507703…")
            st.warning("⚠️ Cause n°1 quand « rien ne se passe » : l'intégration n'est pas connectée à la base. "
                       "Ouvre ta base Notion → **⋯** → **Connexions** → ajoute ton intégration.")
        elif crm_type == "hubspot":
            _field("Token d'application privée HubSpot", "hubspot_api_key", "HUBSPOT_API_KEY", secret=True,
                   placeholder="pat-eu1-…",
                   help_="HubSpot → Paramètres → Intégrations → Applications privées. Portées : "
                         "crm.objects.contacts.read / write.")

    with st.container(border=True):
        st.markdown("**📱 SMS (Brevo)** · [obtenir une clé ↗](https://app.brevo.com/settings/keys/api)")
        _field("Clé API Brevo", "brevo_api_key", "BREVO_API_KEY", secret=True, placeholder="xsmtpsib-…")

    with st.container(border=True):
        st.markdown("**🏛️ France Travail** — source « offres d'emploi » (optionnel) · "
                    "[francetravail.io ↗](https://francetravail.io/inscription)")
        _c1, _c2 = st.columns(2)
        with _c1:
            _field("Client ID", "ft_client_id", "FT_CLIENT_ID", placeholder="PAR_xxxx…")
        with _c2:
            _field("Client Secret", "ft_client_secret", "FT_CLIENT_SECRET", secret=True)

    # ---------------------------------------------------------------------------
    # Signature
    # ---------------------------------------------------------------------------
    st.subheader("👤 Ta signature")
    with st.container(border=True):
        _s1, _s2 = st.columns(2)
        with _s1:
            _field("Prénom Nom", "your_name", "YOUR_NAME")
            _field("Email", "your_email", "YOUR_EMAIL")
        with _s2:
            _field("Titre", "your_title", "YOUR_TITLE", placeholder="Développeur web fullstack")
            _field("Site / portfolio / GitHub", "your_website", "YOUR_WEBSITE")

    st.subheader("🧰 Préférences")
    # ---------------------------------------------------------------------------
    # Délais des actions (jours ouvrés)
    # ---------------------------------------------------------------------------
    with st.expander("⏱️ Délais des actions (en jours ouvrés)", expanded=False):
        st.caption(
            "Combien de temps avant qu'une action réapparaisse dans « Ma journée ». "
            "Les week-ends ne comptent pas. Tu peux toujours saisir un délai différent au cas par cas."
        )
        for _a in (crm_store.ACTION_RELANCER, crm_store.ACTION_MAQUETTE,
                   crm_store.ACTION_RAPPELER, crm_store.ACTION_PROPALE):
            # 📘 Même motif « comparer puis écrire » que dans Pipeline : on n'écrit en base que si la
            # 📘 valeur saisie diffère de celle stockée.
            _v = st.number_input(
                crm_store.ACTION_LABELS[_a], min_value=0, max_value=60,
                value=crm_store.get_delay(_a), key=f"delay_{_a}",
            )
            if _v != crm_store.get_delay(_a):
                crm_store.set_delay(_a, int(_v))
                st.toast(f"{crm_store.ACTION_LABELS[_a]} : {_v} j ouvrés ✅")

    # ---------------------------------------------------------------------------
    # Modèles de messages LinkedIn
    # ---------------------------------------------------------------------------
    with st.expander("💬 Modèles de messages LinkedIn", expanded=False):
        from services import linkedin as _li
        st.caption(
            "Variables disponibles : `{prenom}` (du dirigeant), `{entreprise}`, "
            "`{mon_prenom}`, `{mon_titre}`, `{mon_site}`. Sans prénom connu, "
            "« Bonjour {prenom}, » devient automatiquement « Bonjour, »."
        )
        _custom = crm_store.get_linkedin_templates()
        for _k, _lbl in _li.TEMPLATE_LABELS.items():
            st.markdown(f"**{_lbl}**" + ("  · _personnalisé_" if _k in _custom else "  · _par défaut_"))
            _val = st.text_area(
                _lbl, value=_li.get_template(_k, _custom),
                height=90 if _k.startswith("note") else 180,
                key=f"litpl_{_k}", label_visibility="collapsed",
            )
            _preview = _li.render(_val, dirigeant="Jean Dupont", entreprise="ESN Alpha",
                                  mon_nom=your_name or "Kenny", mon_titre=your_title,
                                  mon_site=your_website)
            if _k.startswith("note"):
                _lvl, _msg = _li.note_verdict(_preview)
                st.caption(("✅ " if _lvl == "ok" else "⚠️ ") + _msg + " (aperçu avec « Jean Dupont / ESN Alpha »)")
            _s1, _s2, _ = st.columns([1, 1, 3])
            if _s1.button("💾 Enregistrer", key=f"litpl_save_{_k}", type="primary", use_container_width=True):
                crm_store.set_linkedin_template(_k, _val)
                st.success("Modèle enregistré ✅")
            if _s2.button("↩️ Par défaut", key=f"litpl_reset_{_k}", use_container_width=True,
                          disabled=_k not in _custom):
                crm_store.reset_linkedin_template(_k)
                # 📘 On retire la valeur du widget de la session pour qu'au rerun le text_area reparte du
                # 📘 modèle par défaut (sinon Streamlit réafficherait l'ancien texte saisi).
                st.session_state.pop(f"litpl_{_k}", None)
                st.rerun()
            st.markdown("")

    # ---------------------------------------------------------------------------
    # Franchises exclues
    # ---------------------------------------------------------------------------
    with st.expander("🏢 Franchises exclues de la prospection", expanded=False):
        from services.franchises import FRANCHISES as _BUILTIN
        st.caption(
            f"{len(_BUILTIN)} enseignes nationales sont exclues d'office "
            "(Fitness Park, Laforêt, Century 21, McDonald's, Basic-Fit…) : "
            "le siège décide, pas l'agence locale. Ajoute ici les enseignes "
            "régionales que tu ne veux jamais prospecter, une par ligne."
        )
        _uf = crm_store.get_user_franchises()
        _uf_text = st.text_area(
            "Mes enseignes à exclure", value="\n".join(_uf),
            placeholder="Ti Resto\nMaison Péi", height=120, key="user_franchises_input",
        )
        if st.button("💾 Enregistrer la liste", key="save_franchises"):
            crm_store.set_user_franchises(_uf_text.splitlines())
            st.success("Liste enregistrée ✅")
            st.rerun()
        if _uf:
            st.caption(f"Actuellement : {', '.join(_uf)}")

    # ---------------------------------------------------------------------------
    # Historique
    # ---------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("🗂️ Historique des contacts"):
        from history_manager import load_contacted_ids
        contacted = load_contacted_ids()
        st.write(f"**{len(contacted)}** établissement(s) déjà contacté(s) (ignorés aux prochains runs).")
        if contacted:
            if st.button("🗑️ Réinitialiser l'historique", type="secondary"):
                # On supprime le fichier principal ET la sauvegarde, sinon _load_contacted_data
                # restaure aussitôt les données depuis le backup → reset sans effet.
                # 📘 N'efface que les fichiers JSON d'history_manager ; la base SQLite
                # 📘 crm_store (statuts,
                # 📘 événements) n'est pas touchée.
                removed = 0
                for _fname in ("contacted_place_ids.json", "contacted_place_ids.bak.json"):
                    _path = os.path.join("output", _fname)
                    if os.path.exists(_path):
                        os.remove(_path)
                        removed += 1
                st.success(
                    f"Historique effacé ({removed} fichier(s)). "
                    "Le prochain run reprospectera depuis zéro."
                )
                st.rerun()

    # ---------------------------------------------------------------------------
    # Cache d'analyse
    # ---------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("⚡ Cache d'analyse (performances)"):
        from services import cache as _analysis_cache
        st.caption(
            "Les analyses récentes sont mises en cache pour éviter de refaire "
            "les appels HTTP et PageSpeed pour les mêmes sites."
        )
        n_cached = _analysis_cache.count()
        col_c1, col_c2 = st.columns([3, 1])
        with col_c1:
            st.write(f"**{n_cached}** site(s) actuellement en cache.")
        with col_c2:
            if st.button("🗑️ Vider", key="clear_cache", use_container_width=True, disabled=(n_cached == 0)):
                deleted = _analysis_cache.clear_all()
                st.success(f"✅ {deleted} entrée(s) supprimée(s).")
                st.rerun()

    # ---------------------------------------------------------------------------
    # Délivrabilité — la délivrabilité bat le volume
    # ---------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("📬 Délivrabilité — éviter les spams (à lire avant d'envoyer en masse)"):
        st.markdown("""
    **Règle d'or : la délivrabilité bat le volume.** 100 emails/heure depuis un seul domaine = spam garanti.

    **Avant d'envoyer :**
    - ✅ **SPF, DKIM et DMARC** configurés sur ton domaine d'envoi (dans ta zone DNS). Sans ça, tu pars direct en spam.
    - ✅ **Domaine dédié à la prospection** (ex. `mail-tondomaine.fr`), pas ton domaine principal — pour protéger ta réputation.
    - ✅ **Warmup** : monte en charge progressivement — 5 à 10 emails/jour la 1re semaine, puis augmente sur 4 à 6 semaines.
    - ✅ **Petits volumes ciblés** : 20-50 emails/jour très ciblés > 500 génériques.

    **Réglages du bot déjà en place :**
    - Délai de 3 s entre chaque envoi (anti-rafale).
    - Emails uniques et personnalisés (pas de template identique) → moins de signaux spam.

    **Cap quotidien conseillé** (à respecter côté envoi) :
    """)
        _daily_cap = st.slider("Nombre max d'emails à envoyer par jour", 5, 100, 30, key="deliv_cap")
        st.caption(
            f"Vise ~{_daily_cap}/jour sur un domaine chauffé. En warmup (domaine récent), "
            f"reste sous 10/jour la 1re semaine."
        )
        st.caption("Astuce : teste ta config sur mail-tester.com avant une campagne — un score < 8/10 = risque spam.")


# 📘 ═══ SECTION : NAVIGATION (st.navigation + st.Page) ═══
# 📘 Badge du menu : nombre d'actions en retard + du jour (lu dans crm_store). try/except :
# 📘 si la base est indisponible, le menu s'affiche quand même (badge à 0).
try:
    _sum_nav = crm_store.actions_summary()
    _due_now = _sum_nav["en_retard"] + _sum_nav["aujourdhui"]
except Exception:
    _due_now = 0

# 📘 st.Page(fonction, title=, icon=, url_path=) déclare une page ; le dict les regroupe par
# 📘 rubrique dans la barre latérale ; default=True = page ouverte à l'arrivée ; url_path
# 📘 donne l'adresse (ex. http://localhost:8501/pipeline).
# 📘 st.navigation renvoie la page choisie (d'après l'URL ou le clic) ; _nav.run() exécute SA
# 📘 fonction, et seulement elle. Tout le code de niveau 0 au-dessus a déjà tourné.
# 💡 Taille : ~1900 lignes dans un seul fichier. Découpage simple : un dossier pages/ avec un
# 💡 module par page (pages/ma_journee.py, pages/campagne.py…), un config.py pour _cfg /
# 💡 _persist_cfg, un ui/components.py pour _linkedin_panel. app.py ne garderait que
# 💡 set_page_config, l'initialisation et ce bloc st.navigation (~60 lignes).
# 💡 Passage React + FastAPI : chaque st.Page devient une route React (React Router), chaque
# 💡 lecture/écriture crm_store une route API (GET /actions/due, PATCH /prospects/{id}…),
# 💡 st.session_state → état côté React (useState / React Query), settings → GET/PUT
# 💡 /settings avec les secrets gardés côté serveur (variables d'env), jamais dans le front.
_nav = st.navigation({
    "Au quotidien": [
        st.Page(page_ma_journee, title=f"Ma journée ({_due_now})" if _due_now else "Ma journée",
                icon="☀️", url_path="ma-journee", default=True),
        st.Page(page_pipeline, title="Pipeline", icon="📋", url_path="pipeline"),
        st.Page(page_relances, title="Relances", icon="🔄", url_path="relances"),
    ],
    "Prospecter": [
        st.Page(page_prospection, title="Nouvelle campagne", icon="🔍", url_path="prospection"),
        st.Page(page_statistiques, title="Statistiques", icon="📊", url_path="statistiques"),
    ],
    "Paramètres": [
        st.Page(page_reglages, title="Réglages", icon="⚙️", url_path="reglages"),
    ],
})
_nav.run()
