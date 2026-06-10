"""
Interface Streamlit — Prospection B2B automatisée.
Lance avec : streamlit run app.py
"""

import json
import os
import queue
import threading
import time
from datetime import datetime
from typing import Optional

import streamlit as st

# ---------------------------------------------------------------------------
# Config page (doit être le 1er appel Streamlit)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Prospection B2B",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS custom
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Sidebar — Configuration
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🎯 Prospection B2B")
    st.markdown("---")

    st.markdown("### 🔑 Clés API")

    st.markdown(
        "**Google Places API Key** "
        "— [Obtenir ici ↗](https://console.cloud.google.com/apis/credentials)"
    )
    google_key = st.text_input(
        "Google Places API Key",
        type="password",
        value=os.getenv("GOOGLE_PLACES_API_KEY", ""),
        placeholder="AIzaSy...",
        label_visibility="collapsed",
    )

    st.markdown(
        "**Notion API Key** "
        "— [Créer une intégration ↗](https://www.notion.so/my-integrations)"
    )
    notion_key = st.text_input(
        "Notion API Key",
        type="password",
        value=os.getenv("NOTION_API_KEY", ""),
        placeholder="secret_...",
        label_visibility="collapsed",
    )

    st.markdown(
        "**Brevo API Key** "
        "— [Obtenir ici ↗](https://app.brevo.com/settings/keys/api)"
    )
    brevo_key = st.text_input(
        "Brevo API Key",
        type="password",
        value=os.getenv("BREVO_API_KEY", ""),
        placeholder="xsmtpsib-...",
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("### 📧 Gmail (optionnel)")

    st.markdown("**Adresse Gmail**")
    gmail_address = st.text_input(
        "Adresse Gmail",
        value=os.getenv("GMAIL_ADDRESS", ""),
        placeholder="toi@gmail.com",
        label_visibility="collapsed",
    )

    st.markdown(
        "**Mot de passe d'application** "
        "— [Générer ici ↗](https://myaccount.google.com/apppasswords) *(pas ton vrai mdp)*"
    )
    gmail_password = st.text_input(
        "Mot de passe d'application",
        type="password",
        value=os.getenv("GMAIL_APP_PASSWORD", ""),
        placeholder="xxxx xxxx xxxx xxxx",
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("### 👤 Ta signature")
    your_name = st.text_input("Prénom", value=os.getenv("YOUR_NAME", "Kenny"))
    your_title = st.text_input("Titre", value=os.getenv("YOUR_TITLE", "Développeur Web Freelance"))
    your_email = st.text_input("Ton email", value=os.getenv("YOUR_EMAIL", ""))
    your_website = st.text_input("Ton site", value=os.getenv("YOUR_WEBSITE", ""))

    st.markdown("---")
    st.caption("🔒 Tes clés restent sur ta machine. Rien n'est envoyé à l'extérieur.")


# ---------------------------------------------------------------------------
# Titre principal
# ---------------------------------------------------------------------------
from profiles import PROFILES, get_profile

st.markdown("# 🎯 Prospection B2B Automatisée")
st.markdown("Trouve des prospects locaux, analyse leur besoin et génère des cold emails/SMS en un clic.")
st.markdown("---")

# ---------------------------------------------------------------------------
# Sélection du profil
# ---------------------------------------------------------------------------
st.markdown("### 🧩 Choisissez votre profil")

profile_options = {f"{p.emoji} {p.name}": p for p in PROFILES}
selected_label = st.selectbox(
    "Profil de prospection",
    options=list(profile_options.keys()),
    index=0,
    label_visibility="collapsed",
)
selected_profile = profile_options[selected_label]
st.caption(f"*{selected_profile.description}*")

st.markdown("---")

# ---------------------------------------------------------------------------
# Critères de recherche — pré-remplis depuis le profil
# ---------------------------------------------------------------------------
st.markdown("### 📍 Configurez votre campagne")

col1, col2 = st.columns([2, 1])

with col1:
    location = st.text_input(
        "📌 Ville / Zone géographique",
        value=selected_profile.location or os.getenv("SEARCH_LOCATION", "Lyon, France"),
        placeholder="Paris, France",
    )
    keywords_raw = st.text_area(
        "🔑 Mots-clés cibles (un par ligne)",
        value="\n".join(selected_profile.keywords),
        height=150,
        placeholder="restaurant\nboulangerie\ncoiffeur",
    )
    keywords = [k.strip() for k in keywords_raw.splitlines() if k.strip()]

    st.markdown("**✉️ Accroche email** *(personnalisable)*")
    email_hook = st.text_area(
        "Accroche email",
        value=selected_profile.email_hook,
        height=100,
        label_visibility="collapsed",
        help="Utilisez {name} pour insérer le nom du prospect",
    )

    st.markdown("**📱 Accroche SMS** *(max 160 caractères)*")
    sms_hook = st.text_input(
        "Accroche SMS",
        value=selected_profile.sms_hook,
        label_visibility="collapsed",
    )
    if len(sms_hook) > 160:
        st.warning(f"⚠️ SMS trop long : {len(sms_hook)}/160 caractères")

with col2:
    st.markdown("**⚙️ Paramètres**")
    your_offer = st.text_area(
        "🎁 Mon offre",
        value=selected_profile.your_offer,
        height=80,
        help="Décrivez votre offre en 1-2 phrases",
    )
    max_results = st.slider("Prospects par mot-clé", 1, 20, 5)
    min_rating = st.slider(
        "Note Google minimum ⭐",
        min_value=1.0, max_value=5.0, value=3.0, step=0.5,
        help="Les établissements en dessous de cette note sont ignorés (probablement en difficulté)",
    )
    score_threshold = st.slider(
        "Score max à contacter",
        min_value=0, max_value=100, value=100,
        help="100 = tous les prospects. Baisse pour ne garder que les sites avec beaucoup de problèmes.",
    )
    radius = st.select_slider(
        "Rayon de recherche",
        options=[1000, 2000, 5000, 10000, 20000, 50000],
        value=10000,
        format_func=lambda x: f"{x//1000} km",
    )
    send_emails = st.toggle("📧 Envoyer les emails auto", value=False)
    if send_emails:
        st.warning("⚠️ Seuls les prospects avec un email trouvé recevront un mail.")
    send_sms_toggle = st.toggle("📱 Envoyer les SMS auto", value=False)
    if send_sms_toggle:
        st.warning("⚠️ Seuls les numéros mobiles (06/07) recevront un SMS.")

st.markdown("---")


# ---------------------------------------------------------------------------
# Logger qui alimente la queue Streamlit
# ---------------------------------------------------------------------------
class QueueLogger:
    def __init__(self, q: queue.Queue):
        self.q = q

    def _emit(self, level: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.q.put(f"[{ts}] {level} {msg}")

    def info(self, msg: str, *a):    self._emit("ℹ️ ", msg % a if a else msg)
    def debug(self, msg: str, *a):   self._emit("🔍", msg % a if a else msg)
    def warning(self, msg: str, *a): self._emit("⚠️ ", msg % a if a else msg)
    def error(self, msg: str, *a):   self._emit("❌", msg % a if a else msg)
    def critical(self, msg: str, *a):self._emit("🔴", msg % a if a else msg)


# ---------------------------------------------------------------------------
# Thread de prospection
# ---------------------------------------------------------------------------
def run_prospection(params: dict, log_q: queue.Queue, result_container: list):
    """Tourne dans un thread séparé pour ne pas bloquer l'UI."""
    try:
        # Force les variables d'env AVANT tout import de config
        os.environ["GOOGLE_PLACES_API_KEY"] = params["google_key"]
        os.environ["NOTION_API_KEY"] = params["notion_key"]
        os.environ["BREVO_API_KEY"] = params["brevo_key"]
        os.environ["SEARCH_LOCATION"] = params["location"]
        os.environ["SEARCH_KEYWORDS"] = ",".join(params["keywords"])
        os.environ["SEARCH_RADIUS"] = str(params["radius"])
        os.environ["MAX_RESULTS_PER_KEYWORD"] = str(params["max_results"])
        os.environ["YOUR_NAME"] = params["your_name"]
        os.environ["YOUR_TITLE"] = params["your_title"]
        os.environ["YOUR_EMAIL"] = params["your_email"]
        os.environ["YOUR_WEBSITE"] = params["your_website"]
        os.environ["YOUR_OFFER"] = params.get("your_offer", "")
        os.environ["EMAIL_HOOK"] = params.get("email_hook", "")
        os.environ["SMS_HOOK"] = params.get("sms_hook", "")

        # Recharge la config avec les nouvelles valeurs
        import config as cfg_module
        from config import Config
        cfg_module.config = Config()
        c = cfg_module.config

        # Remplace le logger global par notre QueueLogger
        ui_logger = QueueLogger(log_q)
        cfg_module.logger = ui_logger

        import services.google_maps as gm_mod
        import services.analyzer as an_mod
        import services.mailer as ma_mod
        import services.notion_sync as no_mod
        gm_mod.logger = ui_logger
        an_mod.logger = ui_logger
        ma_mod.logger = ui_logger
        no_mod.logger = ui_logger

        # Recharge aussi le config dans chaque module
        gm_mod.config = c
        an_mod.config = c
        no_mod.config = c

        from services.google_maps import fetch_raw_candidates, build_prospect
        from services.analyzer import analyze_prospect
        from services.mailer import enrich_with_email
        from services.notion_sync import sync_all
        from history_manager import load_contacted_ids, mark_as_contacted

        os.makedirs(c.output_dir, exist_ok=True)

        target_per_kw = params["max_results"]
        min_rating    = params.get("min_rating", 3.0)
        threshold     = params.get("contact_score_threshold", 100)
        weight_overrides = params.get("weight_overrides", {})
        already_contacted = load_contacted_ids()

        all_qualified: list = []
        seen: set = set()

        # Boucle principale : pour chaque mot-clé, cherche jusqu'à target_per_kw qualifiés
        for kw in params["keywords"]:
            log_q.put(f"[--] 🔍 Recherche '{kw}' — objectif {target_per_kw} qualifiés…")
            raw_candidates = fetch_raw_candidates(kw)

            if not raw_candidates:
                log_q.put(f"[--] ❌ Aucun résultat Google pour '{kw}' — vérifiez le mot-clé ou la zone.")
                continue

            kw_qualified: list = []
            skip_contacted = skip_seen = skip_api = skip_rating = skip_score = 0

            for raw in raw_candidates:
                if len(kw_qualified) >= target_per_kw:
                    break

                place_id = raw.get("place_id", "")
                if not place_id:
                    continue
                if place_id in seen:
                    skip_seen += 1
                    continue
                if place_id in already_contacted:
                    skip_contacted += 1
                    continue
                seen.add(place_id)

                prospect = build_prospect(raw, kw)
                if not prospect:
                    skip_api += 1
                    continue

                if prospect.rating is not None and prospect.rating < min_rating:
                    skip_rating += 1
                    continue

                analyzed = analyze_prospect(prospect, weight_overrides)

                if analyzed.score <= threshold:
                    kw_qualified.append(analyzed)
                    log_q.put(
                        f"[--] ✅ [{len(kw_qualified)}/{target_per_kw}] {prospect.name}"
                        f" — score {analyzed.score}/100"
                    )
                else:
                    skip_score += 1

            found = len(kw_qualified)
            if found < target_per_kw:
                reasons = []
                if skip_contacted: reasons.append(f"{skip_contacted} déjà contacté(s)")
                if skip_score:     reasons.append(f"{skip_score} site(s) trop bon(s) pour le seuil ({threshold}/100)")
                if skip_rating:    reasons.append(f"{skip_rating} note(s) Google trop basse(s) (< {min_rating}⭐)")
                if skip_api:       reasons.append(f"{skip_api} erreur(s) API Google")
                if skip_seen:      reasons.append(f"{skip_seen} doublon(s) inter-mots-clés")
                reason_str = " | ".join(reasons) if reasons else "Google épuisé"
                log_q.put(f"[--] ⚠️  {found}/{target_per_kw} qualifiés pour '{kw}' → {reason_str}.")
            else:
                log_q.put(f"[--] ✅ {found}/{target_per_kw} qualifiés pour '{kw}'.")
            all_qualified.extend(kw_qualified)

        all_prospects = all_qualified
        log_q.put(f"[--] 📋 {len(all_prospects)} prospect(s) qualifiés au total.")

        # Emails
        all_prospects = [enrich_with_email(p) for p in all_prospects]

        # 4. Tri
        all_prospects.sort(key=lambda p: p.score)

        # 5. Sauvegarde locale
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(c.output_dir, f"prospects_{ts}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in all_prospects], f, ensure_ascii=False, indent=2)

        # 6. Notion
        if params["notion_key"]:
            sync_all(all_prospects)

        # 7. Gmail
        if params["send_emails"] and params["gmail_address"] and params["gmail_password"]:
            from services.gmail import send_all
            send_all(all_prospects, params["gmail_address"], params["gmail_password"])

        # 8. SMS Brevo
        if params["send_sms"] and params["brevo_key"]:
            from services.sms import send_all_sms
            send_all_sms(all_prospects)

        # 9. Marquage des prospects contactés (avec infos complètes pour les relances)
        mark_as_contacted(all_prospects)

        # 10. Historique
        from history_manager import save_run
        emails_found = sum(1 for p in all_prospects if p.email)
        mobiles_found = sum(1 for p in all_prospects if p.phone and (
            p.phone.replace(" ", "").startswith("06") or
            p.phone.replace(" ", "").startswith("07")
        ))
        save_run(
            profile_name=params.get("profile_name", "Custom"),
            location=params["location"],
            keywords=params["keywords"],
            total=len(all_prospects),
            no_site=sum(1 for p in all_prospects if not p.has_website()),
            emails_found=emails_found,
            mobiles_found=mobiles_found,
            output_file=json_path,
        )

        result_container.extend(all_prospects)
        log_q.put("__DONE__")

    except Exception as exc:
        log_q.put(f"[--] ❌ Erreur critique : {exc}")
        log_q.put("__DONE__")


# ---------------------------------------------------------------------------
# Bouton de lancement
# ---------------------------------------------------------------------------
col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
with col_btn2:
    launch = st.button(
        "🚀 Lancer la prospection",
        disabled=st.session_state.running or not google_key or not keywords or not location,
    )

if not google_key:
    st.info("👈 Renseigne ta clé Google Places dans la barre latérale pour commencer.")

# ---------------------------------------------------------------------------
# Démarrage du thread
# ---------------------------------------------------------------------------
if launch and not st.session_state.running:
    st.session_state.running = True
    st.session_state.run_done = False
    st.session_state.logs = []
    st.session_state.prospects = []
    st.session_state.log_queue = queue.Queue()

    result_container = []

    params = {
        "google_key": google_key,
        "notion_key": notion_key,
        "brevo_key": brevo_key,
        "location": location,
        "keywords": keywords,
        "radius": radius,
        "max_results": max_results,
        "your_name": your_name,
        "your_title": your_title or selected_profile.your_title,
        "your_email": your_email,
        "your_website": your_website,
        "your_offer": your_offer,
        "email_hook": email_hook,
        "sms_hook": sms_hook,
        "profile_id": selected_profile.id,
        "profile_name": f"{selected_profile.emoji} {selected_profile.name}",
        "weight_overrides": selected_profile.check_weight_overrides,
        "min_rating": min_rating,
        "contact_score_threshold": score_threshold,
        "analysis_workers": int(os.getenv("ANALYSIS_WORKERS", "5")),
        "send_emails": send_emails,
        "gmail_address": gmail_address,
        "gmail_password": gmail_password,
        "send_sms": send_sms_toggle,
    }

    thread = threading.Thread(
        target=run_prospection,
        args=(params, st.session_state.log_queue, result_container),
        daemon=True,
    )
    thread.start()
    st.session_state._thread = thread
    st.session_state._results = result_container

# ---------------------------------------------------------------------------
# Affichage live des logs
# ---------------------------------------------------------------------------
if st.session_state.running or st.session_state.run_done:
    st.markdown("### 📡 Logs en temps réel")
    log_placeholder = st.empty()
    status_placeholder = st.empty()

    # Vide la queue dans la liste de logs
    q = st.session_state.log_queue
    while not q.empty():
        msg = q.get_nowait()
        if msg == "__DONE__":
            st.session_state.running = False
            st.session_state.run_done = True
            if hasattr(st.session_state, "_results"):
                st.session_state.prospects = list(st.session_state._results)
        else:
            st.session_state.logs.append(msg)

    # Affiche les logs
    log_html = "<div class='log-box'>" + "<br>".join(
        st.session_state.logs[-100:]
    ) + "</div>"
    log_placeholder.markdown(log_html, unsafe_allow_html=True)

    if st.session_state.running:
        status_placeholder.info("⏳ Prospection en cours…")
        time.sleep(1)
        st.rerun()
    else:
        status_placeholder.success("✅ Prospection terminée !")


# ---------------------------------------------------------------------------
# Résultats
# ---------------------------------------------------------------------------
if st.session_state.prospects:
    prospects = st.session_state.prospects
    st.markdown("---")
    st.markdown("## 📊 Résultats")

    # Métriques
    no_site     = sum(1 for p in prospects if not p.has_website())
    critical    = sum(1 for p in prospects if p.score < 40)
    avg_score   = int(sum(p.score for p in prospects) / len(prospects))
    emails_ok   = sum(1 for p in prospects if p.email)
    mobiles_ok  = sum(1 for p in prospects if p.phone and (
        p.phone.replace(" ", "").startswith("06") or
        p.phone.replace(" ", "").startswith("07")
    ))

    m1, m2, m3, m4, m5, m6 = st.columns(6)
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
        with st.expander(header):
            c1, c2 = st.columns([1, 1])
            with c1:
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
                    st.markdown(f"**📧 Email trouvé :** `{p.email}`")
                else:
                    st.markdown("**📧 Email :** non trouvé sur le site")

                # Site web
                if p.website:
                    st.markdown(f"**🌐 Site :** [{p.website}]({p.website})")
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

    import csv, io
    col_e1, col_e2 = st.columns(2)

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
        fieldnames = ["name", "keyword", "address", "phone", "email", "website",
                      "rating", "score", "issues_count", "issues_summary", "maps_url"]
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        for p in filtered:
            writer.writerow({
                "name": p.name,
                "keyword": p.keyword,
                "address": p.address,
                "phone": p.phone or "",
                "email": p.email or "",
                "website": p.website or "",
                "rating": p.rating or "",
                "score": p.score,
                "issues_count": len(p.issues),
                "issues_summary": " | ".join(p.issues[:3]),
                "maps_url": p.maps_url,
            })
        st.download_button(
            label="⬇️ Télécharger CSV (Excel)",
            data=csv_buffer.getvalue().encode("utf-8-sig"),
            file_name=f"prospects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

# ---------------------------------------------------------------------------
# Sauvegarde profil custom
# ---------------------------------------------------------------------------
st.markdown("---")
with st.expander("💾 Sauvegarder ce profil pour une prochaine fois"):
    save_name = st.text_input("Nom du profil", placeholder="Ex: Mon profil Lyon Dev Web")
    if st.button("💾 Sauvegarder") and save_name:
        from profile_manager import save_custom_profile
        from profiles import Profile
        import re, uuid
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
        for run in history:
            kw_str = ", ".join(run.get("keywords", [])[:3])
            st.markdown(
                f"**{run['date']}** — {run['profile']} — {run['location']} — "
                f"`{kw_str}` — "
                f"**{run['total_prospects']}** prospects | "
                f"📧 {run['emails_trouvés']} emails | "
                f"📱 {run['mobiles_trouvés']} mobiles"
            )
            st.divider()

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
            import json as _json
            history_path = os.path.join("output", "contacted_place_ids.json")
            if os.path.exists(history_path):
                os.remove(history_path)
            st.success("Historique effacé. Le prochain run reprospecttra depuis zéro.")
            st.rerun()

# ---------------------------------------------------------------------------
# Relances
# ---------------------------------------------------------------------------
st.markdown("---")
with st.expander("🔄 Relances — contacts sans réponse"):
    from history_manager import get_due_followups, mark_as_responded, mark_followup_sent
    followup_delay = int(os.getenv("FOLLOWUP_DELAY_DAYS", "5"))
    due = get_due_followups(followup_delay)

    if not due:
        st.success(f"✅ Aucun contact à relancer (seuil : {followup_delay} jours sans réponse).")
    else:
        st.info(f"**{len(due)} contact(s)** à relancer — contactés il y a plus de {followup_delay} jours sans réponse.")

        # Bouton pour générer tous les emails de relance d'un coup
        if st.button("📝 Générer tous les emails de relance", key="gen_followup"):
            from services.google_maps import Prospect as P
            from services.mailer import draft_followup_email
            drafts = []
            for contact in due:
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
                drafts.append((p.name, draft_followup_email(p), contact["place_id"]))
                mark_followup_sent(contact["place_id"])
            st.session_state["followup_drafts"] = drafts
            st.success(f"✅ {len(drafts)} email(s) de relance générés.")
            st.rerun()

        # Affichage des drafts générés
        if st.session_state.get("followup_drafts"):
            for name, draft, _ in st.session_state["followup_drafts"]:
                st.markdown(f"**{name}**")
                st.code(draft, language=None)
            import io
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
                    st.rerun()
