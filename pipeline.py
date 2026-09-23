"""
pipeline.py — Orchestration d'une campagne de prospection.

Enchaîne : recherche multi-sources → dédoublonnage/exclusions → analyse →
filtrage → emails → CRM → envois → historique.

Totalement indépendant de l'interface : aucun import de Streamlit.
Interface d'entrée/sortie :
  - params           : dict de configuration de la campagne
  - log_q            : queue.Queue où sont poussées les lignes de log
                       ("__DONE__" est toujours envoyé en dernier)
  - result_container : liste remplie avec les Prospect qualifiés

Ce découplage permet de lancer une campagne depuis n'importe quel front
(Streamlit aujourd'hui, une API FastAPI demain) sans rien réécrire.
"""

from __future__ import annotations

import json
import os
import queue
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial


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
    def debug(self, msg: str, *a):   pass  # bruit interne (pagination, PageSpeed, CMS…) → masqué de l'UI
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
        import services.crm.notion as crmno_mod
        gm_mod.logger = ui_logger
        an_mod.logger = ui_logger
        ma_mod.logger = ui_logger
        no_mod.logger = ui_logger
        crmno_mod.logger = ui_logger

        # Recharge aussi le config dans chaque module
        gm_mod.config = c
        an_mod.config = c
        no_mod.config = c

        from services.google_maps import fetch_raw_candidates, build_prospect
        from services.analyzer import analyze_prospect
        from services.mailer import enrich_with_email, draft_email, EmailStyle as _EmailStyle
        from services.crm import get_exporter
        from history_manager import load_contacted_ids, mark_as_contacted
        from services import cache as _cache_mod
        from services.sources import (
            search_sirene, search_pages_jaunes,
            search_france_travail, search_google_custom, SOURCE_LABELS,
        )
        from services.sources.linkedin_csv import parse_linkedin_csv
        _cache_mod.set_ttl(params.get("cache_ttl_days", 30))

        os.makedirs(c.output_dir, exist_ok=True)

        target_per_kw   = params["max_results"]
        min_rating      = params.get("min_rating", 3.0)
        threshold       = params.get("contact_score_threshold", 100)
        score_direction = params.get("score_direction", "asc")
        weight_overrides = params.get("weight_overrides", {})
        candidacy_mode  = params.get("service_category", "") == "freelance"
        # Exclusion des franchises et grandes enseignes (siège décide, pas le local)
        from services.franchises import is_franchise as _is_franchise
        exclude_franchises = params.get("exclude_franchises", True)
        _user_franchises = params.get("user_franchises", [])
        _franchise_hits: list = []   # exclusions venant des sources non-Maps
        if candidacy_mode:
            log_q.put(
                "[--] 🧑‍💻 Mode candidature freelance : on N'AUDITE PAS les sites, "
                "on récupère toutes les cibles + leur contact."
            )
        already_contacted = load_contacted_ids()
        # La base CRM fait aussi foi : elle exclut en plus les clients, les
        # « pas intéressé » et la blacklist (pas seulement les déjà-contactés).
        try:
            import crm_store as _crm
            _crm_excluded = _crm.contacted_place_ids()
            _extra = len(_crm_excluded - already_contacted)
            already_contacted = already_contacted | _crm_excluded
            if _extra:
                log_q.put(f"[--] ⛔ {_extra} prospect(s) exclu(s) via le CRM (client, pas intéressé ou blacklist).")
        except Exception:
            pass
        if already_contacted:
            log_q.put(
                f"[--] 📓 {len(already_contacted)} établissement(s) déjà contacté(s) "
                "seront ignorés (réinitialisable dans « Historique des contacts »)."
            )
        sources = params.get("source_types", [params.get("source_type", "google_maps")])

        all_qualified: list = []
        seen: set = set()
        workers = params.get("analysis_workers", 5)
        _maps_text_calls = 0
        _maps_detail_calls = 0
        _funnel_raw = 0          # total candidats bruts récupérés (toutes sources)
        _funnel_candidates = 0   # total candidats après note mini, avant analyse
        _emails_sent = 0
        _sms_sent = 0
        _crm_synced = 0
        _emails_scheduled = 0

        def _analyse_and_filter(candidates: list, label: str) -> list:
            """Analyse un lot de prospects et filtre par score. Retourne la liste qualifiée."""
            if not candidates:
                return []
            batch = candidates[:target_per_kw * 3]
            detection_kws = params.get("detection_keywords", [])
            with ThreadPoolExecutor(max_workers=min(workers, len(batch))) as ex:
                analyzed = list(ex.map(
                    partial(
                        analyze_prospect,
                        weight_overrides=weight_overrides,
                        detection_keywords=detection_kws or None,
                        candidacy=candidacy_mode,
                    ),
                    batch,
                ))
            # Mode candidature : aucune note, on garde toutes les cibles
            if candidacy_mode:
                for p in analyzed:
                    log_q.put(f"[--] ✅ {p.name} — cible retenue")
                return analyzed
            qualified = []
            rejected_scores: list = []
            for p in analyzed:
                qualifies = (p.score >= threshold if score_direction == "desc" else p.score <= threshold)
                if qualifies:
                    qualified.append(p)
                    log_q.put(f"[--] ✅ {p.name} — score {p.score}/100")
                else:
                    rejected_scores.append(p.score)
            # Funnel : on montre noir sur blanc où meurent les prospects
            if rejected_scores:
                _op = "≥" if score_direction == "desc" else "≤"
                log_q.put(
                    f"[--] 📊 [{label}] analysés {len(analyzed)} → qualifiés {len(qualified)} | "
                    f"rejetés par le score : {len(rejected_scores)} "
                    f"(scores {min(rejected_scores)}-{max(rejected_scores)}, "
                    f"seuil {_op} {threshold})"
                )
            return qualified

        def _dedup(candidates: list) -> list:
            """Retire les déjà contactés, les doublons et les franchises."""
            out = []
            for p in candidates:
                if p.place_id in seen or p.place_id in already_contacted:
                    continue
                if exclude_franchises:
                    _hit, _brand = _is_franchise(p.name, _user_franchises)
                    if _hit:
                        _franchise_hits.append((p.name, _brand))
                        continue
                seen.add(p.place_id)
                out.append(p)
            return out

        # ── LinkedIn CSV : traitement hors boucle mots-clés ──────────────────
        if "linkedin_csv" in sources:
            csv_content = params.get("linkedin_content", "")
            if not csv_content:
                if len(sources) == 1:
                    log_q.put("[--] ❌ Aucun fichier CSV LinkedIn fourni.")
            else:
                raw_li = parse_linkedin_csv(csv_content, "LinkedIn")
                li_ok = _dedup(raw_li)
                log_q.put(f"[--] 📎 {len(li_ok)} contact(s) LinkedIn à analyser…")
                all_qualified.extend(_analyse_and_filter(li_ok, "LinkedIn"))

        # ── Boucle par mot-clé (toutes sources hors LinkedIn) ────────────────
        kw_sources = [s for s in sources if s != "linkedin_csv"]
        if kw_sources:
            for kw in params["keywords"]:
                src_labels_str = " + ".join(SOURCE_LABELS.get(s, s) for s in kw_sources)
                log_q.put(f"[--] 🔍 [{src_labels_str}] '{kw}' — objectif {target_per_kw}…")

                candidates: list = []

                for source in kw_sources:
                    if source == "google_maps":
                        # ── Phase 1 : Text Search ──
                        # On ne récupère que ce qui est utile (≈ objectif × 3, plafonné à 60) :
                        # évite de paginer inutilement quand l'objectif est petit.
                        _max_raw = max(20, min(target_per_kw * 3, 60))
                        raw_candidates = fetch_raw_candidates(kw, max_raw=_max_raw)
                        _maps_text_calls += 1
                        _funnel_raw += len(raw_candidates)
                        if not raw_candidates:
                            log_q.put(f"[--] ❌ Aucun résultat Google Maps pour '{kw}'.")
                            continue

                        skip_contacted = skip_seen = 0
                        skip_franchise: list = []
                        raw_to_build: list = []
                        for raw in raw_candidates:
                            if len(raw_to_build) >= target_per_kw * 4:
                                break
                            pid = raw.get("place_id", "")
                            if not pid:
                                continue
                            if pid in seen:
                                skip_seen += 1; continue
                            if pid in already_contacted:
                                skip_contacted += 1; continue
                            # Franchises écartées AVANT Place Details : on ne paie
                            # pas l'appel API pour un prospect qu'on jette ensuite.
                            if exclude_franchises:
                                _is_fr, _brand = _is_franchise(raw.get("name", ""), _user_franchises)
                                if _is_fr:
                                    skip_franchise.append((raw.get("name", ""), _brand))
                                    continue
                            seen.add(pid)
                            raw_to_build.append(raw)

                        if not raw_to_build:
                            log_q.put(f"[--] ⚠️  [Google Maps] tous déjà contactés ou vus pour '{kw}'.")
                            continue

                        # ── Phase 2 : Place Details en parallèle ──
                        with ThreadPoolExecutor(max_workers=min(workers, len(raw_to_build))) as ex:
                            built_list = list(ex.map(partial(build_prospect, keyword=kw), raw_to_build))
                        _maps_detail_calls += len(raw_to_build)

                        skip_api = skip_rating = 0
                        for p in built_list:
                            if p is None:
                                skip_api += 1
                            elif p.rating is not None and p.rating < min_rating:
                                skip_rating += 1
                            else:
                                candidates.append(p)

                        if skip_franchise:
                            _noms = ", ".join(f"{n} ({b})" for n, b in skip_franchise[:5])
                            _reste = f" +{len(skip_franchise) - 5}" if len(skip_franchise) > 5 else ""
                            log_q.put(
                                f"[--] 🏢 {len(skip_franchise)} franchise(s) écartée(s) pour '{kw}' : {_noms}{_reste}"
                            )

                        if skip_api or skip_rating:
                            reasons = []
                            if skip_api:    reasons.append(f"{skip_api} erreur(s) API")
                            if skip_rating: reasons.append(f"{skip_rating} note(s) trop basse(s)")
                            log_q.put(f"[--] ⚠️  [Google Maps] {' | '.join(reasons)} pour '{kw}'.")

                    else:
                        # ── Sources alternatives : retournent directement des Prospects ──
                        src_label = SOURCE_LABELS.get(source, source)
                        if source == "sirene":
                            raw = search_sirene(kw, params["location"], target_per_kw * 3)
                        elif source == "pages_jaunes":
                            raw = search_pages_jaunes(kw, params["location"], target_per_kw * 3)
                        elif source == "france_travail":
                            raw = search_france_travail(
                                kw, params["location"], target_per_kw * 3,
                                client_id=params.get("ft_client_id", ""),
                                client_secret=params.get("ft_client_secret", ""),
                            )
                        elif source == "google_search":
                            raw = search_google_custom(
                                kw, params["location"], target_per_kw * 3,
                                cx=params.get("google_cx", ""),
                            )
                        else:
                            raw = []

                        deduped = _dedup(raw)
                        if not deduped:
                            log_q.put(f"[--] ⚠️  0 résultat {src_label} pour '{kw}'.")
                        else:
                            candidates.extend(deduped)

                if not candidates:
                    log_q.put(f"[--] ⚠️  0 candidat(s) au total pour '{kw}'.")
                    continue

                _funnel_candidates += len(candidates)

                # ── Phase 3+4 : Analyse + filtre score (commun toutes sources) ──
                kw_qualified = _analyse_and_filter(candidates, kw)[:target_per_kw]
                log_q.put(f"[--] {'✅' if len(kw_qualified) >= target_per_kw else '⚠️ '} {len(kw_qualified)}/{target_per_kw} qualifiés pour '{kw}'.")
                all_qualified.extend(kw_qualified)

        all_prospects = all_qualified
        # Estimation du coût Google Maps du run (tarifs Places API : ~0,032$/Text Search, ~0,017$/Place Details)
        if _maps_text_calls:
            _maps_cost = _maps_text_calls * 0.032 + _maps_detail_calls * 0.017
            log_q.put(
                f"[--] 🗺️  Google Maps : {_maps_text_calls} Text Search"
                f" + {_maps_detail_calls} Place Details"
                f" ≈ ${_maps_cost:.2f} ce run"
            )
        # Récap funnel : où meurent les prospects, étape par étape
        if candidacy_mode:
            log_q.put(
                f"[--] 🧮 Funnel : {_funnel_raw} bruts récupérés → "
                f"{_funnel_candidates} candidats (après dédup + note ≥ {min_rating}) → "
                f"{len(all_prospects)} cibles retenues (mode candidature, aucun filtre de score)."
            )
            if _funnel_raw > 0 and _funnel_candidates == 0:
                log_q.put("[--] 💡 Tous les bruts ont été éliminés en amont (déjà contactés, doublons entre mots-clés, ou erreurs API).")
        else:
            log_q.put(
                f"[--] 🧮 Funnel : {_funnel_raw} bruts récupérés → "
                f"{_funnel_candidates} candidats analysés (après dédup + note ≥ {min_rating}) → "
                f"{len(all_prospects)} qualifiés (seuil score {threshold})."
            )
            if _funnel_raw > 0 and _funnel_candidates == 0:
                log_q.put("[--] 💡 Tous les bruts ont été éliminés en amont (déjà contactés, doublons entre mots-clés, ou erreurs API).")
            elif _funnel_candidates > 0 and len(all_prospects) <= 2:
                log_q.put("[--] 💡 Assez de candidats mais peu qualifiés : monte « Score max à contacter » (les sites sont trop bons pour le seuil actuel).")
        log_q.put(f"[--] 📋 {len(all_prospects)} {'cible(s) retenue(s)' if candidacy_mode else 'prospect(s) qualifiés'} au total.")

        # Emails
        style_dict = params.get("email_style", {})
        _email_style = _EmailStyle(
            intonation=style_dict.get("intonation", "professional"),
            length=style_dict.get("length", "medium"),
            salutation=style_dict.get("salutation", "neutral"),
            cta=style_dict.get("cta", "audit"),
        )
        _svc_id  = params.get("service_id", "")
        _svc_cat = params.get("service_category", "web_digital")
        _tgt_sec = params.get("target_sector", "")
        for _p in all_prospects:
            _p.email_draft = draft_email(
                _p, style=_email_style, service_id=_svc_id,
                service_category=_svc_cat, target_sector=_tgt_sec,
            )
        all_prospects = list(all_prospects)

        # 4. Tri
        reverse_sort = (score_direction == "desc")
        all_prospects.sort(key=lambda p: p.score, reverse=reverse_sort)

        # Les prospects sont prêts pour l'affichage → on remplit le conteneur lu par
        # l'interface MAINTENANT, avant les étapes à risque (CRM, Gmail, SMS, historique).
        # Ainsi une erreur réseau en aval ne fait jamais disparaître les résultats.
        result_container.extend(all_prospects)

        # 5. Sauvegarde locale
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(c.output_dir, f"prospects_{ts}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in all_prospects], f, ensure_ascii=False, indent=2)

        # 6. Export CRM
        _crm_type = params.get("crm_type", "aucun")
        crm_exporter = get_exporter(
            _crm_type,
            params.get("crm_key", ""),
            **params.get("crm_extra", {}),
        )
        notion_page_ids: dict = {}
        if _crm_type not in ("aucun", ""):
            if not params.get("crm_key", ""):
                log_q.put(f"[--] ⚠️  CRM {_crm_type} : clé API manquante — export ignoré.")
            elif _crm_type == "notion" and not params.get("crm_extra", {}).get("database_id"):
                log_q.put("[--] ⚠️  Notion : Database ID manquant — export ignoré.")
            elif crm_exporter:
                log_q.put(f"[--] 📤 Export CRM ({_crm_type})…")
                try:
                    # Pré-vérification d'accès (Notion) pour un diagnostic clair
                    if _crm_type == "notion" and hasattr(crm_exporter, "verify_access"):
                        _ok, _msg = crm_exporter.verify_access()
                        if not _ok:
                            log_q.put(f"[--] ❌ Notion : {_msg}")
                            raise RuntimeError("accès Notion refusé")
                    _created = crm_exporter.export(all_prospects)
                    if hasattr(crm_exporter, "_last_exported_ids"):
                        notion_page_ids = crm_exporter._last_exported_ids
                    _crm_synced = _created if isinstance(_created, int) else len(all_prospects)
                    if _crm_synced > 0:
                        log_q.put(f"[--] ✅ {_crm_synced} fiche(s) créée(s) dans {_crm_type}.")
                    else:
                        log_q.put(
                            f"[--] ⚠️  Aucune fiche créée dans {_crm_type} — "
                            "soit tous les prospects sont déjà présents (doublons), "
                            "soit un nom de propriété ne correspond pas (voir l'erreur ci-dessus)."
                        )
                except RuntimeError:
                    pass  # message déjà loggé par verify_access
                except Exception as _crm_exc:
                    log_q.put(f"[--] ❌ Erreur export {_crm_type} : {_crm_exc}")

        # 7. Gmail — enveloppé dans try/except : une erreur d'envoi ne doit JAMAIS
        # empêcher la suite du run (SMS, historique) de s'exécuter.
        if params["send_emails"] and params["gmail_address"] and params["gmail_password"]:
            try:
                _with_email = [p for p in all_prospects if p.email]
                _without_email = len(all_prospects) - len(_with_email)
                if params.get("email_send_mode") == "⏰ Programmé" and params.get("sched_date"):
                    from datetime import datetime as _dtime
                    from services import scheduler as _sched_mod
                    _send_at = _dtime.strptime(
                        f"{params['sched_date']} {params.get('sched_time', '09:00')}",
                        "%Y-%m-%d %H:%M",
                    ).timestamp()
                    _n_sched = 0
                    for _p in all_prospects:
                        if not _p.email or not _p.email_draft:
                            continue
                        _sched_mod.add_pending(
                            place_id=_p.place_id,
                            name=_p.name,
                            email=_p.email,
                            draft=_p.email_draft,
                            gmail_address=params["gmail_address"],
                            gmail_password=params["gmail_password"],
                            send_at=_send_at,
                            notion_page_id=notion_page_ids.get(_p.place_id, ""),
                            notion_api_key=params.get("crm_key", "") if params.get("crm_type") == "notion" else "",
                        )
                        _n_sched += 1
                    _emails_scheduled = _n_sched
                    log_q.put(
                        f"[--] ⏰ {_n_sched} email(s) programmé(s) pour le "
                        f"{params['sched_date']} à {params.get('sched_time', '09:00')}."
                    )
                elif not _with_email:
                    log_q.put(
                        f"[--] ⚠️  Envoi email activé mais aucun prospect n'a d'adresse email scrapée "
                        f"({_without_email} prospect(s) sans email trouvé sur leur site)."
                    )
                else:
                    log_q.put(f"[--] 📤 Envoi email vers {len(_with_email)} prospect(s)…")
                    if _without_email:
                        log_q.put(f"[--] ℹ️  {_without_email} prospect(s) ignoré(s) — email non trouvé sur leur site.")
                    from services.gmail import send_all
                    _email_stats = send_all(_with_email, params["gmail_address"], params["gmail_password"])
                    _emails_sent = _email_stats["sent"]
                    log_q.put(
                        f"[--] {'✅' if _email_stats['sent'] else '⚠️ '} Email : "
                        f"{_email_stats['sent']} envoyé(s) | "
                        f"{_email_stats['skipped']} ignoré(s) | "
                        f"{_email_stats['failed']} échec(s)."
                    )
                    if _email_stats["failed"]:
                        log_q.put("[--] ❌ Vérifie ton adresse Gmail et le mot de passe d'application (pas le mot de passe habituel).")
                    if notion_page_ids and params.get("crm_type") == "notion" and params.get("crm_key"):
                        from services.crm.notion import NotionExporter
                        _nu = NotionExporter(params["crm_key"], params.get("crm_extra", {}).get("database_id", ""))
                        for _p in all_prospects:
                            if _p.email:
                                _pid = notion_page_ids.get(_p.place_id)
                                if _pid:
                                    _nu.update_status(_pid, "contacté")
            except Exception as _mail_exc:
                log_q.put(f"[--] ❌ Erreur envoi email : {_mail_exc}")
        elif params["send_emails"]:
            if not params["gmail_address"]:
                log_q.put("[--] ⚠️  Envoi email activé mais adresse Gmail manquante.")
            elif not params["gmail_password"]:
                log_q.put("[--] ⚠️  Envoi email activé mais mot de passe d'application Gmail manquant.")

        # 8. SMS Brevo — même principe : erreur isolée, ne bloque jamais la suite.
        if params["send_sms"] and params["brevo_key"]:
            try:
                _with_mobile = [p for p in all_prospects if p.phone and (
                    p.phone.replace(" ", "").startswith("06") or
                    p.phone.replace(" ", "").startswith("07")
                )]
                if not _with_mobile:
                    log_q.put("[--] ⚠️  SMS activé mais aucun prospect avec numéro mobile (06/07) trouvé.")
                else:
                    log_q.put(f"[--] 📱 Envoi SMS vers {len(_with_mobile)} mobile(s)…")
                    from services.sms import send_all_sms
                    _sms_stats = send_all_sms(all_prospects)
                    _sms_sent = _sms_stats["sent"]
                    log_q.put(
                        f"[--] {'✅' if _sms_stats['sent'] else '⚠️ '} SMS : "
                        f"{_sms_stats['sent']} envoyé(s) | "
                        f"{_sms_stats['skipped']} ignoré(s) | "
                        f"{_sms_stats['failed']} échec(s)."
                    )
                    if _sms_stats["failed"]:
                        log_q.put("[--] ❌ Vérifie ta clé Brevo API dans la sidebar.")
            except Exception as _sms_exc:
                log_q.put(f"[--] ❌ Erreur envoi SMS : {_sms_exc}")
        elif params["send_sms"] and not params["brevo_key"]:
            log_q.put("[--] ⚠️  SMS activé mais clé Brevo manquante.")

        # 9. Marquage des prospects contactés — UNIQUEMENT si un envoi a réellement
        # eu lieu (email envoyé/programmé ou SMS). Sinon c'est un run d'exploration :
        # on ne « brûle » pas les prospects, ils restent disponibles aux prochains runs.
        _something_sent = (_emails_sent > 0) or (_sms_sent > 0) or (_emails_scheduled > 0)
        try:
            if _something_sent:
                mark_as_contacted(all_prospects, notion_page_ids=notion_page_ids)
                log_q.put(
                    f"[--] 📓 {len(all_prospects)} prospect(s) marqué(s) comme contactés "
                    "(ignorés aux prochains runs)."
                )
            else:
                log_q.put(
                    "[--] ℹ️  Run d'exploration (aucun envoi) — prospects NON marqués comme "
                    "contactés, ils resteront disponibles au prochain run."
                )
        except Exception as _mark_exc:
            log_q.put(f"[--] ❌ Erreur marquage contacts : {_mark_exc}")

        # 10. Historique
        from history_manager import save_run
        emails_found = sum(1 for p in all_prospects if p.email)
        mobiles_found = sum(1 for p in all_prospects if p.phone and (
            p.phone.replace(" ", "").startswith("06") or
            p.phone.replace(" ", "").startswith("07")
        ))
        # Répartition des types d'offres (dev web uniquement)
        _offer_types: dict = {}
        if params.get("service_category", "web_digital") == "web_digital":
            try:
                from offers import select_offer as _select_offer
                for _p in all_prospects:
                    _ot = _select_offer(_p, sector=params.get("target_sector", "")).offer_type
                    _offer_types[_ot] = _offer_types.get(_ot, 0) + 1
            except Exception:
                pass
        _source_labels = [SOURCE_LABELS.get(s, s) for s in sources]
        save_run(
            profile_name=params.get("profile_name", "Custom"),
            location=params["location"],
            keywords=params["keywords"],
            total=len(all_prospects),
            no_site=sum(1 for p in all_prospects if not p.has_website()),
            emails_found=emails_found,
            mobiles_found=mobiles_found,
            output_file=json_path,
            emails_sent=_emails_sent,
            sms_sent=_sms_sent,
            crm_synced=_crm_synced,
            offer_types=_offer_types,
            sources=_source_labels,
            target_sector=params.get("target_sector", ""),
        )

        # 11. Base CRM — campagne + prospects (statuts et notes existants préservés)
        try:
            import crm_store as _crm
            _cid = _crm.add_campaign(
                profile=params.get("profile_name", "Custom"),
                location=params["location"],
                keywords=params["keywords"],
                sources=_source_labels,
                target_sector=params.get("target_sector", ""),
                total_prospects=len(all_prospects),
                sans_site=sum(1 for p in all_prospects if not p.has_website()),
                emails_trouves=emails_found,
                mobiles_trouves=mobiles_found,
                emails_envoyes=_emails_sent,
                sms_envoyes=_sms_sent,
                crm_synchronises=_crm_synced,
                offer_types=_offer_types,
                fichier=json_path,
            )
            _new = _crm.upsert_prospects(
                all_prospects, campaign_id=_cid,
                sector=params.get("target_sector", ""),
                service_id=params.get("service_id", ""),
            )
            if _something_sent:
                _contacted_ids = [p.place_id for p in all_prospects]
                _crm.mark_contacted(
                    _contacted_ids,
                    channel="email" if (_emails_sent or _emails_scheduled) else "sms",
                )
                # Relance automatique programmée : elle sera annulée d'elle-même
                # si le prospect répond (mark_responded efface l'action).
                _delay = _crm.get_delay(_crm.ACTION_RELANCER)
                for _cid_p in _contacted_ids:
                    _crm.set_next_action(_cid_p, _crm.ACTION_RELANCER, delay_days=_delay)
                log_q.put(
                    f"[--] ⏳ Relance programmée dans {_delay} jour(s) ouvré(s) pour "
                    f"{len(_contacted_ids)} prospect(s) — annulée automatiquement s'ils répondent."
                )
            log_q.put(f"[--] 🗃️  CRM : {_new} nouveau(x) prospect(s) ajouté(s) au pipeline.")
        except Exception as _crmdb_exc:
            log_q.put(f"[--] ⚠️  Enregistrement CRM impossible : {_crmdb_exc}")

    except Exception as exc:
        log_q.put(f"[--] ❌ Erreur critique : {exc}")
    finally:
        # __DONE__ est toujours envoyé, exactement une fois — l'interface ne reste
        # jamais bloquée sur « en cours », même en cas d'erreur en cours de route.
        log_q.put("__DONE__")
