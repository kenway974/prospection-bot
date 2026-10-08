# Manuel d'utilisation — Prospection Bot

Ce manuel dit **où modifier quoi**. Pour une présentation rapide, voir le [README](README.md).

- [1. Démarrage en 5 minutes](#1-démarrage-en-5-minutes)
- [2. Interface ou ligne de commande : ce qui change](#2-interface-ou-ligne-de-commande--ce-qui-change)
- [3. Je veux modifier… (table de repérage)](#3-je-veux-modifier--table-de-repérage)
- [4. Clés API et variables d'environnement](#4-clés-api-et-variables-denvironnement)
- [5. Modifier les messages (mails, relances, SMS)](#5-modifier-les-messages-mails-relances-sms)
- [6. Adapter l'approche à un secteur (profils)](#6-adapter-lapproche-à-un-secteur-profils)
- [7. Le score et les critères d'analyse](#7-le-score-et-les-critères-danalyse)
- [8. Désinscription (STOP)](#8-désinscription-stop)
- [9. Relances](#9-relances)
- [10. Fichiers produits](#10-fichiers-produits)
- [11. Tests et méthode TDD](#11-tests-et-méthode-tdd)
- [12. Hébergement](#12-hébergement)
- [13. Dépannage](#13-dépannage)
- [14. Limites connues](#14-limites-connues)

---

## 1. Démarrage en 5 minutes

```bash
pip install -r requirements.txt          # Python 3.11 (voir .python-version)
cp .env.example .env                     # puis remplir au minimum GOOGLE_PLACES_API_KEY
python -m streamlit run app.py           # interface web
# ou, en ligne de commande :
python main.py
```

Avant de faire quoi que ce soit d'autre, vérifier que tout est vert :

```bash
pip install -r requirements-dev.txt
python run_tests.py                      # tous les tests sans réseau, quelques secondes
```

---

## 2. Interface ou ligne de commande : ce qui change

Le projet a **deux parcours** qui font presque la même chose. Ils ne sont pas identiques :

| | Interface (`app.py`) | Ligne de commande (`main.py`) |
|---|---|---|
| Profils de secteur (accroche, mots-clés, poids du score) | ✅ | ❌ (lit seulement le `.env`) |
| Envoi des mails via Gmail | ✅ (case à cocher) | ❌ (génère seulement les brouillons) |
| Envoi des SMS Brevo | ✅ (case à cocher) | ✅ (dès qu'une clé Brevo existe) |
| Sync Notion | ✅ (si clé saisie) | ✅ (si clé dans `.env`) |
| Relances | ✅ (onglet Relances) | ✅ `python main.py --followup` |
| Désinscription | ✅ (les refus sont exclus) | ✅ `python main.py --optout adresse@…` |
| Planification (cron) | ❌ | ✅ |

**Attention :** toute modification de la logique du parcours (filtres, ordre des étapes) doit être faite
**aux deux endroits** : `main.py` (fonction `run`) et `app.py` (fonction `run_prospection`). Les tests de
comportement (`tests/test_pipeline_main.py` et `tests/test_app_pipeline.py`) existent pour attraper un oubli.

Étapes communes, dans l'ordre : recherche Google → filtre note → déjà contactés → refus STOP →
analyse des sites → refus par email → seuil de score → génération des mails → tri → sauvegarde →
Notion → (Gmail) → (SMS) → marquage « contacté » → historique.

---

## 3. Je veux modifier… (table de repérage)

| Je veux modifier | Fichier | Où |
|---|---|---|
| Le texte du premier mail | `services/mailer.py` | `_build_subject`, `_build_hook`, `_build_issues_block`, `_build_cta`, `draft_email` |
| Le texte de la relance | `services/mailer.py` | `draft_followup_email` |
| La mention STOP / origine de l'adresse | `.env` (`UNSUBSCRIBE_TEXT`) ou `services/mailer.py` | `DEFAULT_UNSUBSCRIBE_TEXT` |
| L'accroche d'un secteur | `profiles.py` | champ `email_hook` du profil (`{name}` = nom du prospect) |
| Le texte du SMS | `services/sms.py` | `_build_sms` (160 caractères max) ou `sms_hook` du profil |
| Mots-clés et ville d'un secteur | `profiles.py` | `keywords`, `location` du profil |
| Les poids du score pour un secteur | `profiles.py` | `check_weight_overrides` du profil |
| Les poids du score pour tous | `services/analyzer.py` | `CRITICAL_WEIGHT`, `MAJOR_WEIGHT`, `MINOR_WEIGHT`, `_DEFAULT_WEIGHTS` |
| Le seuil « site trop bon pour être contacté » | `.env` | `CONTACT_SCORE_THRESHOLD` (défaut 70) |
| Le seuil « site lent » | `services/analyzer.py` | `SLOW_RESPONSE_THRESHOLD_S` (défaut 3 s) |
| Les constructeurs de sites détectés (Wix…) | `services/analyzer.py` | `_FREE_BUILDERS` |
| Les scripts de suivi détectés (Analytics…) | `services/analyzer.py` | `_TRACKING_SIGNATURES` |
| Les faux emails ignorés au scraping | `services/analyzer.py` | `_EMAIL_BLACKLIST` |
| Les pages /contact explorées | `services/analyzer.py` | liste dans `_scrape_email` |
| Le CRM Notion (base cible, colonnes) | `services/notion_sync.py` | `DATABASE_ID`, `push_prospect` |
| Le délai avant relance | `.env` | `FOLLOWUP_DELAY_DAYS` (défaut 5) |
| Le délai entre deux mails / SMS | `services/gmail.py`, `services/sms.py` | `DELAY_BETWEEN_MAILS`, `DELAY_BETWEEN_SMS` |
| Les dossiers de sortie | `config.py` | `output_dir` (mais `history_manager.py` et `optout_manager.py` écrivent en dur dans `output/`) |

---

## 4. Clés API et variables d'environnement

Tout se règle dans `.env` (copié depuis `.env.example`). Dans l'interface, les champs sont pré-remplis avec
ces valeurs et peuvent être modifiés à la volée sans toucher au fichier.

### Clés

| Variable | Obligatoire | À quoi ça sert | Où l'obtenir |
|---|---|---|---|
| `GOOGLE_PLACES_API_KEY` | **Oui** | Trouver les entreprises (API Places classique, URLs `/maps/api/place/…`) | console.cloud.google.com → Identifiants. Activer « Places API » sur le projet |
| `NOTION_API_KEY` | Non | Créer une fiche par prospect dans ton CRM | notion.so/my-integrations, puis **partager la base avec l'intégration** |
| `BREVO_API_KEY` | Non | Envoyer des SMS (mobiles 06/07 uniquement) | app.brevo.com/settings/keys/api |
| `GMAIL_ADDRESS` | Non | Adresse d'envoi des mails | Ton compte Gmail |
| `GMAIL_APP_PASSWORD` | Non | Mot de passe d'application (pas ton vrai mot de passe) | myaccount.google.com/apppasswords (validation en 2 étapes requise) |

`GMAIL_ADDRESS` et `GMAIL_APP_PASSWORD` ne sont lus **que par l'interface**. `main.py` n'envoie pas de mail.

### Recherche

| Variable | Défaut | Rôle |
|---|---|---|
| `SEARCH_KEYWORDS` | `restaurant,boulangerie` | Mots-clés séparés par des virgules |
| `SEARCH_LOCATION` | `Lyon, France` | Ville ou zone |
| `SEARCH_RADIUS` | `10000` | Rayon en mètres (max 50000) |
| `MAX_RESULTS_PER_KEYWORD` | `5` | Prospects traités par mot-clé. **Chaque prospect coûte 1 appel Places Details** |

### Qualification

| Variable | Défaut | Rôle |
|---|---|---|
| `MIN_RATING` | `3.0` | Note Google minimale. Un prospect **sans note** n'est pas exclu |
| `CONTACT_SCORE_THRESHOLD` | `70` | On ne contacte que les prospects dont le score est **≤** ce seuil |
| `ANALYSIS_WORKERS` | `5` | Sites analysés en parallèle |
| `FOLLOWUP_DELAY_DAYS` | `5` | Jours sans réponse avant relance |

### Identité (signature des mails et SMS)

`YOUR_NAME`, `YOUR_TITLE`, `YOUR_EMAIL`, `YOUR_WEBSITE`. L'e-mail est aussi celui qui reçoit les « STOP ».

### Optionnelles (textes)

| Variable | Rôle |
|---|---|
| `EMAIL_HOOK` | Remplace la phrase d'accroche du mail. `{name}` = nom du prospect. Dans l'interface, c'est rempli par le profil |
| `SMS_HOOK` | Remplace le texte du SMS (tronqué à 160 caractères) |
| `YOUR_OFFER` | Phrase ajoutée entre parenthèses après l'appel à l'action |
| `UNSUBSCRIBE_TEXT` | Remplace la mention STOP / origine de l'adresse en bas des mails |

### Notion : base cible et colonnes

L'identifiant de la base est **écrit en dur** dans `services/notion_sync.py` (`DATABASE_ID`). C'est ta base
actuelle. Pour en utiliser une autre, remplace cet identifiant. La base doit avoir exactement ces colonnes :

| Colonne | Type Notion |
|---|---|
| `Entreprise` | Titre |
| `Tel standard` | Téléphone |
| `Récap propal` | Texte |
| `Status` | Texte (valeur écrite : « à contacter ») |
| `mail1` | Texte (le brouillon complet) |
| `Email` | Email |
| `LinkedIn` | URL (le bot y met le site web du prospect) |

Un prospect déjà présent (même nom ou même téléphone) n'est pas recréé.

---

## 5. Modifier les messages (mails, relances, SMS)

### Premier mail — `services/mailer.py`

Le mail est assemblé par `draft_email` à partir de 5 morceaux :

1. **Sujet** (`_build_subject`) : selon le nombre de problèmes (aucun site, 0, 1, 2–3, 4 et plus).
2. **Accroche** (`_build_hook`) : si `EMAIL_HOOK` est défini, c'est lui. Sinon la première règle qui
   correspond : pas de site, site inaccessible, HTTP, mobile, formulaire, tracking, sinon phrase générique.
3. **Bloc problèmes** (`_build_issues_block`) : jusqu'à 3 problèmes en liste, puis « … et N autres ».
4. **Appel à l'action** (`_build_cta`) : selon le nombre de problèmes. `YOUR_OFFER` s'ajoute à la fin.
5. **Signature** puis **mention STOP** (`_build_footer`).

⚠️ **Piège connu :** l'accroche choisit son cas en cherchant des mots (« HTTPS », « viewport », « formulaire »,
« tracking »…) dans les messages d'`analyzer.py`. Si tu reformules un message dans l'analyseur, vérifie que le
mot cherché y est encore. Les tests de `tests/test_mail_contract.py` échouent si le lien est cassé.

### Relance — `draft_followup_email`

Texte court, sans bloc de problèmes. Reprend le premier problème détecté s'il est connu (sinon « votre présence
en ligne »). La mention STOP y est aussi.

### SMS — `services/sms.py`

`_build_sms` : texte par défaut ou `SMS_HOOK`, tronqué à 160 caractères. Seuls les **mobiles (06/07)** reçoivent
un SMS, convertis en `+33…`. L'expéditeur affiché est ton prénom (11 caractères max).
Le SMS ne contient **pas** de mention STOP (voir [limites](#14-limites-connues)).

---

## 6. Adapter l'approche à un secteur (profils)

Un **profil** = toute la configuration d'un secteur. Champs (`profiles.py`, classe `Profile`) :

| Champ | Rôle |
|---|---|
| `id` | Identifiant unique, sans espace (`"plombier"`) |
| `emoji`, `name`, `description` | Affichage dans la liste déroulante |
| `keywords` | Mots-clés de recherche Google |
| `location` | Ville pré-remplie dans l'interface |
| `radius`, `max_results` | **Non lus par l'interface actuelle** (le rayon et le nombre de prospects se règlent avec les curseurs) |
| `your_title`, `your_offer` | Titre dans la signature, offre en une phrase |
| `email_hook` | Accroche du mail (`{name}` = nom du prospect) |
| `sms_hook` | Texte du SMS |
| `qualification_criteria` | Notes pour toi, non utilisées par le code |
| `check_weight_overrides` | Poids du score propres au secteur, ex. `{"social_links": 15}` |

### Ajouter un secteur dans le code

Ajouter un `Profile(...)` dans la liste `PROFILES` de `profiles.py` :

```python
Profile(
    id="plombier",
    emoji="🔧",
    name="Plombier",
    description="Cible les agences immobilières et syndics pour de la sous-traitance.",
    keywords=["agence immobilière", "syndic de copropriété"],
    location="Lyon, France",
    your_title="Plombier chauffagiste",
    your_offer="Interventions rapides sur vos biens en gestion",
    email_hook="Je suis plombier près de chez vous. {name} gère sans doute des urgences ; "
               "je peux intervenir sous 24 h.",
    sms_hook="Plombier dispo sous 24 h pour vos urgences. On en parle ?",
    qualification_criteria=["Gère des biens", "Pas de plombier partenaire cité"],
),
```

Puis lancer `python run_tests.py` : `tests/test_profiles.py` vérifie les règles (accroche présente, SMS ≤ 160 caractères…).

### Ajouter un secteur depuis l'interface

Choisir « Profil Custom », remplir les champs, cliquer sur la sauvegarde. Le profil est écrit dans
`profiles_custom.json` (à la racine, ignoré par git) et **réapparaît dans la liste au prochain lancement**.
Si son `id` est celui d'un profil prédéfini, il le remplace.

### Clés de `check_weight_overrides`

`https`, `response_time`, `viewport`, `title`, `meta_description`, `tracking`, `lead_form`, `free_builder`,
`social_links`, `outdated`. Les profils ne sont lus que par l'interface, pas par `main.py`.

---

## 7. Le score et les critères d'analyse

Le score part de **100** et perd des points pour chaque problème détecté. **Plus il est bas, plus il y a à vendre.**
Cas particuliers : pas de site = **0** ; site inaccessible = **5**.

| Check (clé) | Problème détecté | Poids par défaut |
|---|---|---|
| `https` | Site en HTTP | 15 |
| `viewport` | Pas de balise viewport (pas adapté au mobile) | 15 |
| `tracking` | Aucun Analytics / GTM / pixel Facebook / Hotjar / Clarity | 15 |
| `lead_form` | Aucun formulaire ni champ email | 15 |
| `response_time` | Réponse plus lente que 3 s | 10 |
| `title` | Balise `<title>` absente | 10 |
| `free_builder` | Wix, Jimdo, Webnode, Weebly… | 10 |
| `outdated` | Copyright vieux de 3 ans ou plus | 10 |
| `meta_description` | Meta description absente | 5 |
| `social_links` | Aucun lien réseau social | 5 |

Un prospect est **contacté** si son score est **≤ `CONTACT_SCORE_THRESHOLD`**. Résultats triés du plus bas
(meilleure opportunité) au plus haut.

**Ajouter un nouveau check :** (1) écrire le test dans `tests/test_analyzer.py` ; (2) ajouter la fonction
`_check_xxx` et sa constante `CHECK_XXX` dans `services/analyzer.py` ; (3) l'ajouter à `_DEFAULT_WEIGHTS` et à
`analyze_prospect` ; (4) si le mail doit en parler, ajouter un cas dans `_build_hook` et dans
`tests/test_mail_contract.py`.

---

## 8. Désinscription (STOP)

**Ce qui est en place**

- Chaque mail (premier contact et relance) précise **d'où vient l'adresse** et comment refuser : répondre « STOP ».
- Chaque mail envoyé par le bot porte l'en-tête `List-Unsubscribe` : Gmail affiche un bouton « Se désabonner »
  qui t'envoie un mail dont l'objet est `STOP`.
- Les refus sont enregistrés dans `output/optout.json` et **exclus partout** : recherche, analyse, envoi Gmail,
  SMS, relances (CLI et interface).

**Ce que tu dois faire quand quelqu'un répond STOP**

```bash
python main.py --optout adresse@exemple.fr
```

La personne n'est plus jamais contactée, quelle que soit la fiche Google par laquelle elle serait retrouvée,
tant que son adresse est la même.

**Sécurité :** si `output/optout.json` ou `output/contacted_place_ids.json` est illisible, le programme restaure
automatiquement sa copie de secours (`.bak`) et continue en le signalant. S'il n'existe aucune copie lisible, il
**s'arrête** avant tout appel payant, dit pourquoi et ne touche à aucun fichier. Il vaut mieux ne rien envoyer que
recontacter quelqu'un qui a refusé. Détails : §10, « Fichier abîmé ».

**À savoir** — le bot ne lit pas ta boîte mail : c'est à toi d'enregistrer les STOP. Ce n'est pas un conseil
juridique : pour la prospection B2B par mail, les règles (information de la personne, droit d'opposition) sont
précisées par la CNIL, à vérifier avant tout envoi en masse.

---

## 9. Relances

- Un prospect contacté est enregistré dans `output/contacted_place_ids.json` avec sa date.
- Il est **dû** si : contacté depuis au moins `FOLLOWUP_DELAY_DAYS` jours, pas de réponse enregistrée, relance pas
  déjà générée, et **pas de refus STOP**.
- **Ligne de commande :** `python main.py --followup` écrit un `.txt` par contact dans `output/relances_<date>/`.
- **Interface :** onglet « Relances » : génération des mails, téléchargement, et bouton pour marquer un contact
  comme ayant répondu.
- Les relances sont **générées**, pas envoyées : tu les envoies toi-même.

---

## 10. Fichiers produits

Tout est dans `output/` (ignoré par git : **ce sont des données personnelles, ne jamais les commiter**).

| Fichier | Contenu |
|---|---|
| `prospects_<date>.json` / `.csv` | Prospects retenus (le CSV s'ouvre dans Excel) |
| `prospects_<date>_emails/` | Un brouillon `.txt` par prospect |
| `contacted_place_ids.json` | Qui a déjà été contacté, quand, réponse, relance |
| `optout.json` | Les refus STOP |
| `history.json` | 50 derniers lancements (stats) |
| `*.bak` (`contacted_place_ids.json.bak`, `optout.json.bak`, `history.json.bak`) | Copie de secours automatique : la version précédente, refaite avant chaque écriture |
| `*.corrupt` (puis `.corrupt.1`, `.corrupt.2`…) | Fichier abîmé mis de côté, jamais supprimé ni écrasé |
| `relances_<date>/` | Brouillons de relance |
| `rapport_test_<date>.json` | Rapport des tests de campagne (API réelle) |

Ne supprime jamais `contacted_place_ids.json` ni `optout.json` « pour repartir de zéro » : tu recontacterais tout le monde.

### Fichier abîmé

**Pourquoi un fichier peut s'abîmer :** une coupure (courant, plantage, disque plein) pendant son écriture, ou une
modification à la main qui casse le JSON. Les écritures du bot sont **atomiques** (fichier temporaire puis
remplacement d'un coup) : une coupure ne laisse plus de fichier à moitié écrit. Reste le cas d'une modification manuelle
ou d'un disque défaillant.

**Ce que fait le bot tout seul** (contacts, refus STOP, historique) :

1. Avant chaque écriture, la version précédente lisible est copiée en `<fichier>.bak`.
2. Au chargement, si `<fichier>` est illisible mais que `<fichier>.bak` est lisible : le fichier abîmé est renommé en
   `<fichier>.corrupt`, le `.bak` le remplace, un avertissement `⚠️ … copie de secours restaurée` s'affiche (terminal
   et interface), et le lancement continue. Personne présent dans la copie n'est recontacté.
3. S'il n'y a **aucune** copie lisible (contacts ou refus) : arrêt avant tout appel Google, aucun fichier modifié.
   Pour l'historique (simples statistiques), le fichier est mis de côté en `.corrupt` et l'historique repart de zéro.

**Ce que tu dois faire :**

- **Après une restauration automatique** : rien d'obligatoire. Le `.bak` est la version d'avant la **dernière
  écriture** : ce que cette écriture avait ajouté peut manquer (en général, les contacts du dernier lancement, un
  « a répondu » ou un STOP récent). Compare avec `<fichier>.corrupt` si besoin, et ré-enregistre un refus récent avec
  `python main.py --optout adresse@exemple.fr`.
- **Si le bot s'arrête** (« aucune copie de secours lisible ») :
  1. Ne supprime pas le fichier (tu recontacterais tout le monde, y compris des STOP).
  2. Ouvre `output/<fichier>` et `output/<fichier>.bak` dans un éditeur ; repère l'erreur JSON (souvent la fin
     tronquée : accolade ou crochet manquant) avec un validateur JSON.
  3. Corrige le fichier, ou remplace-le par une sauvegarde à toi.
  4. Relance : si le fichier est lisible, le bot repart normalement.
- Les fichiers `.corrupt` peuvent être supprimés à la main une fois que tu as vérifié qu'il ne manque rien.

---

## 11. Tests et méthode TDD

**Règle du projet : on n'écrit pas de code sans un test rouge avant.**

### Lancer

```bash
python run_tests.py                          # tout, sans réseau (quelques secondes)
python -m pytest tests/test_unsubscribe.py   # un fichier
python -m pytest -k "relance" -q             # par mot-clé
python run_tests.py --campaign               # VRAIE API Google, consomme des crédits
```

### Où sont les tests

| Fichier | Ce qu'il protège |
|---|---|
| `test_analyzer.py`, `test_mailer.py`, `test_profiles.py` | Unitaires : checks, textes, profils |
| `test_pipeline_main.py` | **Comportement** : `python main.py` de bout en bout |
| `test_app_pipeline.py`, `test_app_config.py` | **Comportement** : le parcours de l'interface |
| `test_services_behavior.py` | Google, Gmail, Notion, SMS, scraping, historique |
| `test_unsubscribe.py` | Désinscription partout |
| `test_safety_files.py` | Fichiers abîmés : écriture atomique, copie `.bak`, restauration automatique, arrêt s'il n'y a rien de fiable (contacts, refus STOP, historique) |
| `test_mail_contract.py` | Lien entre messages d'analyse et accroche du mail |
| `test_profiles_ui.py` | Interface Streamlit testée avec `AppTest` |
| `test_campaign.py` | **Pas** un test automatique : script avec vraie API |

### Les faux services (`tests/fakes.py`, `tests/conftest.py`)

- `web` : faux Google Places, faux sites, faux Notion, faux Brevo. Déclarer un scénario :
  `web.add_place("boulangerie", "p1", "Chez Zoé", website="https://zoe.fr", html=GOOD_SITE)`.
- `smtp` : faux serveur Gmail ; les mails envoyés sont dans `smtp.sent`.
- `clean_config` : valeurs de config fixes, indépendantes de ton `.env`.
- `app_module` : importe `app.py` (l'interface) et remet à la fin du test tout ce que `run_prospection` modifie.
- Chaque test tourne dans un dossier temporaire : `output/` n'est jamais touché. `time.sleep` est neutralisé.

### Boucle de travail pour toute nouvelle fonctionnalité

1. **Rouge** : écrire un test qui décrit ce que l'utilisateur doit voir ; le lancer ; **vérifier qu'il échoue
   pour la bonne raison** (pas une faute de frappe).
2. **Vert** : écrire le minimum de code pour le faire passer.
3. **Nettoyer** : refactorer, relancer toute la suite.
4. Un commit par idée, tests et code ensemble.

Exemple : ajouter « ne jamais contacter les pharmacies ».

```python
# tests/test_pipeline_main.py
def test_les_pharmacies_sont_exclues(web, clean_config):
    web.add_place("boulangerie", "p1", "Pharmacie du Centre", website=None)
    web.add_place("boulangerie", "p2", "Chez Zoé", website=None)
    main.run()
    assert [p["name"] for p in read_json_outputs()] == ["Chez Zoé"]
```

Lancer → rouge → modifier `main.py` **et** `app.py` → vert.

### Ce qui n'est pas couvert (voir aussi §14)

Les vrais serveurs (Google, Gmail, Notion, Brevo) ne sont jamais appelés par les tests : un changement chez
eux ne sera vu qu'en usage réel ou avec `--campaign`. Les boutons d'envoi et de lancement de l'interface ne
sont pas cliqués par un test ; leur logique est testée via `run_prospection`.

---

## 12. Hébergement

Le `Procfile` lance `streamlit run app.py` sur `$PORT` (Python 3.11).
⚠️ Sur beaucoup d'hébergeurs, le disque est **éphémère** : `output/` peut être effacé à chaque redémarrage, et
avec lui l'historique des contacts et **la liste des refus STOP**. Je n'ai pas vérifié ton hébergeur. Si tu
déploies, utilise un volume persistant ou garde une copie de `output/optout.json` et `output/contacted_place_ids.json`.

---

## 13. Dépannage

| Message | Cause probable |
|---|---|
| `GOOGLE_PLACES_API_KEY manquante` | Clé absente du `.env` |
| `Statut API inattendu (REQUEST_DENIED)` | Places API non activée, clé restreinte, ou facturation non activée |
| `Authentification Gmail échouée` | Mot de passe d'application incorrect, ou validation en 2 étapes non activée |
| `BREVO_API_KEY manquante → SMS ignoré` | Clé Brevo absente |
| SMS ignoré pour un prospect | Numéro fixe (04, 01…) : seuls 06/07 reçoivent un SMS |
| Aucune fiche Notion créée | Base non partagée avec l'intégration, ou colonnes de noms différents (§4) |
| `⚠️ … copie de secours restaurée automatiquement` | Fichier abîmé remplacé par son `.bak` : le lancement continue. Voir §10 « Fichier abîmé » |
| `Fichier des contacts illisible` / `Fichier de refus illisible` … `aucune copie de secours lisible` | Ni le fichier ni son `.bak` ne sont lisibles : rien n'a été envoyé ni modifié. Réparer le JSON (§10 « Fichier abîmé »), relancer |
| « Aucun nouveau prospect à traiter » | Tous déjà contactés, refusés ou exclus : élargir mots-clés ou zone |
| « Aucun prospect sous le seuil » | Les sites trouvés sont trop bons : relever `CONTACT_SCORE_THRESHOLD` ou changer de secteur |

---

## 14. Limites connues

- **Deux parcours à maintenir** (`main.py` et `app.py`) : toute modification de logique est à faire deux fois.
  Les tests de comportement attrapent un oubli, ils ne le préviennent pas.
- **SMS sans mention STOP** : le SMS est tronqué à 160 caractères ; la mention n'y est pas. Les refus sont
  quand même exclus des SMS s'ils sont enregistrés.
- **STOP à enregistrer à la main** (`--optout`) : le bot ne lit pas ta boîte mail ; l'interface n'a pas de bouton dédié.
- **Accroche liée au texte des messages d'analyse** (voir §5), protégée par des tests mais pas indépendante du texte.
- **Les vrais services ne sont pas testés automatiquement** (voir §11).
- **Identifiant Notion en dur** dans `services/notion_sync.py`.
- **Scraping d'emails** : prend la première adresse trouvée sur la page d'accueil ou une page /contact ; ce n'est
  pas forcément l'adresse du décideur.
