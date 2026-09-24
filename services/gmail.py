"""
Envoi de cold emails via SMTP Gmail.

Prérequis :
  - Activer la validation en 2 étapes sur le compte Google
  - Générer un "Mot de passe d'application" (myaccount.google.com/apppasswords)
  - Renseigner GMAIL_ADDRESS et GMAIL_APP_PASSWORD dans .env / l'interface
"""

# 📘 `from __future__ import annotations` : permet d'écrire des annotations de type modernes
# 📘 (ex. `tuple[str, str]`, `list[Prospect]`) même sur des versions de Python plus anciennes.
from __future__ import annotations

# 📘 `import X` charge un module (une "boîte à outils"). Ici, que des modules de la bibliothèque
# 📘 standard de Python (rien à installer) :
# 📘 - smtplib : parle le protocole SMTP, celui qu'on utilise pour ENVOYER des emails ;
# 📘 - time : gestion du temps (ici `time.sleep` pour faire une pause) ;
# 📘 - email.mime : fabrique un email "bien formé" (en-têtes Subject/From/To + corps).
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

# 📘 `from X import Y` : on n'importe que Y depuis le module X. `config` = les réglages de
# 📘 l'app (config.py), `logger` = l'objet qui écrit les messages de log (infos, erreurs).
# 📘 `Prospect` = la classe qui représente une entreprise prospectée (services/google_maps.py).
from config import config, logger
from services.google_maps import Prospect


# 📘 ─── À QUOI SERT CE FICHIER ───
# 📘 Rôle : ENVOYER réellement les cold emails via le serveur SMTP de Gmail, un par un,
# 📘         avec une pause entre chaque envoi.
# 📘 Appelé par : pipeline.py (send_all, envoi immédiat en fin de campagne) et
# 📘              services/scheduler.py (send_email, pour les envois programmés).
# 📘 Appelle : le serveur smtp.gmail.com (port 587, chiffré via STARTTLS) ; le texte des
# 📘           emails vient de services/mailer.py (brouillons stockés dans p.email_draft).
# 📘 Concepts Python à retenir ici : constantes en MAJUSCULES, fonctions et valeurs de
# 📘   retour, tuple, dict, boucle for, `with` (gestionnaire de contexte), try/except,
# 📘   f-string, getattr, time.sleep.
#
# 📘 Constantes : par convention, un nom en MAJUSCULES = une valeur qu'on ne modifie pas.
# 📘 587 est le port SMTP "submission" : la connexion démarre en clair puis passe en
# 📘 chiffré avec STARTTLS (voir plus bas).
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
# 📘 POURQUOI une pause : envoyer des dizaines de mails d'un coup ressemble à du spam pour
# 📘 Gmail (risque de blocage du compte et de mails classés en indésirables = mauvaise
# 📘 "délivrabilité").
DELAY_BETWEEN_MAILS = 3   # secondes entre chaque envoi (anti-spam)


# 📘 `def nom(paramètre: type) -> type_retour:` déclare une fonction. Le `_` au début du
# 📘 nom est une convention : fonction "privée", utilisée seulement dans ce fichier.
# 📘 Elle renvoie un tuple (deux valeurs d'un coup) : (sujet, corps).
# 📘 Le brouillon attendu ressemble à : "OBJET : ...", une ligne vide, puis le corps.
def _parse_subject(draft: str) -> tuple[str, str]:
    """Extrait le sujet et le corps du brouillon généré par mailer.py."""
    # 📘 .strip() enlève les espaces/retours à la ligne au début et à la fin ;
    # 📘 .splitlines() découpe le texte en une liste de lignes.
    lines = draft.strip().splitlines()
    subject = ""
    body_lines = []
    in_body = False

    # 📘 Petite "machine à états" : tant qu'on n'a pas vu la ligne vide qui suit l'objet,
    # 📘 in_body vaut False ; ensuite toutes les lignes vont dans le corps.
    for line in lines:
        if line.startswith("OBJET :") and not in_body:
            subject = line.replace("OBJET :", "").strip()
        elif line.strip() == "" and not in_body and subject:
            in_body = True
        elif in_body:
            body_lines.append(line)

    # 📘 "\n".join(liste) recolle les lignes en un seul texte, séparées par des retours ligne.
    body = "\n".join(body_lines).strip()
    # 📘 Si le brouillon n'a PAS de ligne "OBJET :" (c'est le cas des emails produits par
    # 📘 mailer.build_dynamic_email), subject et body reviennent vides : send_email prend
    # 📘 alors un sujet par défaut et envoie le brouillon entier comme corps.
    return subject, body


# 📘 Fonction principale d'envoi d'UN email. `prospect_name: str = ""` = paramètre
# 📘 optionnel avec une valeur par défaut.
def send_email(
    to_address: str,
    draft: str,
    gmail_address: str,
    gmail_app_password: str,
    prospect_name: str = "",
) -> bool:
    """
    Envoie un email via SMTP Gmail.
    Retourne True si succès, False sinon.
    """
    # 📘 "Déballage" de tuple : la fonction renvoie 2 valeurs, on les range dans 2 variables.
    subject, body = _parse_subject(draft)
    if not subject:
        # 📘 f-string : f"...{variable}..." insère la valeur de la variable dans le texte.
        subject = f"Votre présence en ligne — {prospect_name}"
    if not body:
        body = draft

    # 📘 On construit l'email au format MIME (le format standard des emails). "alternative"
    # 📘 prévoit plusieurs versions du même contenu (texte brut / HTML) ; ici seule la
    # 📘 version texte brut est jointe. msg["Subject"] = ... remplit les en-têtes comme un dict.
    # 💡 Ajouter une version HTML + un en-tête "List-Unsubscribe" (lien de désinscription)
    # 💡 améliorerait la délivrabilité et la conformité RGPD de la prospection B2B.
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = to_address
    # 📘 "utf-8" : l'encodage qui permet les accents (é, à, ç…) sans caractères cassés.
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # 📘 try/except : on "essaie" un bloc ; si une erreur (exception) survient, on saute dans
    # 📘 le `except` correspondant au lieu de faire planter toute l'app.
    try:
        # 📘 `with ... as server:` = gestionnaire de contexte : la connexion est AUTOMATIQUEMENT
        # 📘 fermée à la sortie du bloc, même en cas d'erreur. timeout=15 : abandon après 15 s.
        # 📘 Étapes SMTP : ehlo (on se présente) → starttls (on chiffre la connexion, sinon le mot
        # 📘 de passe circulerait en clair) → login → sendmail.
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            # 📘 On se connecte avec un "mot de passe d'application" Google, pas le vrai mot de passe
            # 📘 du compte : il se révoque à tout moment sans toucher au compte principal.
            server.login(gmail_address, gmail_app_password)
            server.sendmail(gmail_address, to_address, msg.as_string())
        # 📘 logger.info("... %s", valeur) : le %s est remplacé par la valeur (formatage du logger).
        logger.info("    📤 Mail envoyé → %s (%s)", prospect_name, to_address)
        return True
    # 📘 On attrape d'abord l'erreur précise (mauvais identifiants) pour un message clair,
    # 📘 puis `Exception` = "toute autre erreur" (réseau, adresse refusée…). Jamais de crash :
    # 📘 la fonction renvoie simplement False.
    except smtplib.SMTPAuthenticationError:
        logger.error("    ❌ Authentification Gmail échouée. Vérifiez le mot de passe d'application.")
        return False
    except Exception as exc:
        logger.error("    ❌ Erreur envoi mail (%s) : %s", prospect_name, exc)
        return False


# 📘 Envoie à TOUTE une liste de prospects et renvoie des statistiques dans un dict.
# 📘 `list[Prospect]` = "une liste d'objets Prospect" ; `dict[str, int]` = clés texte → nombres.
def send_all(
    prospects: list[Prospect],
    gmail_address: str,
    gmail_app_password: str,
) -> dict[str, int]:
    """
    Envoie les cold emails à tous les prospects qui ont un email renseigné.
    Retourne un dict {sent, skipped, failed}.
    """
    # 📘 Un dict (dictionnaire) associe des clés à des valeurs : stats["sent"] vaut 0 au départ.
    stats = {"sent": 0, "skipped": 0, "failed": 0}

    # 📘 Garde-fou : sans identifiants on ne tente rien, tous les prospects sont "ignorés".
    if not gmail_address or not gmail_app_password:
        logger.warning("Identifiants Gmail manquants → envoi ignoré.")
        stats["skipped"] = len(prospects)
        return stats

    logger.info("")
    logger.info("📤 Envoi des cold emails…")

    # 📘 Boucle `for` : on traite les prospects un par un. `continue` passe directement au
    # 📘 prospect suivant sans exécuter la suite de la boucle.
    for p in prospects:
        if not p.email_draft:
            stats["skipped"] += 1
            continue

        # On utilise l'email stocké dans le prospect (renseigné manuellement ou via enrichissement futur)
        # 📘 getattr(objet, "attribut", défaut) lit un attribut, ou renvoie le défaut s'il n'existe pas.
        to_address = getattr(p, "email", None)
        if not to_address:
            logger.debug("    ⏭️  %s : pas d'email → ignoré", p.name)
            stats["skipped"] += 1
            continue

        # 📘 Appel avec des arguments nommés (to_address=...) : plus lisible, l'ordre n'importe plus.
        success = send_email(
            to_address=to_address,
            draft=p.email_draft,
            gmail_address=gmail_address,
            gmail_app_password=gmail_app_password,
            prospect_name=p.name,
        )
        if success:
            stats["sent"] += 1
            # 📘 time.sleep(3) met le programme en pause 3 secondes (anti-spam, voir DELAY_BETWEEN_MAILS).
            # 📘 Attention : cette pause BLOQUE le code appelant pendant ce temps.
            # 💡 Envoyer via une file de tâches (ex. RQ/Celery + Redis, ou un worker séparé) éviterait de
            # 💡 bloquer l'app pendant une grosse campagne, et permettrait des retries automatiques
            # 💡 (nouvelle tentative avec délai croissant) sur les erreurs réseau temporaires.
            time.sleep(DELAY_BETWEEN_MAILS)
        else:
            stats["failed"] += 1

    # 💡 Réutiliser UNE seule connexion SMTP pour tout le lot (au lieu d'une par mail) serait
    # 💡 plus rapide ; et un plafond d'envois/jour protégerait le compte Gmail (quotas Google).
    logger.info(
        "   → %d envoyé(s) | %d ignoré(s) | %d échec(s)",
        stats["sent"], stats["skipped"], stats["failed"],
    )
    return stats
