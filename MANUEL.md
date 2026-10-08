# Manuel d'utilisation — Prospection Bot

Ce manuel dit **où modifier quoi** et **quoi faire quand quelque chose ne va pas**.
Présentation rapide : [README](README.md).

- [1. Démarrage](#1-démarrage)
- [2. Interface ou ligne de commande : ce qui change](#2-interface-ou-ligne-de-commande--ce-qui-change)
- [3. Je veux modifier… (table de repérage)](#3-je-veux-modifier--table-de-repérage)
- [4. Variables d'environnement](#4-variables-denvironnement)
- [5. Désinscription (STOP)](#5-désinscription-stop)
- [6. Relances](#6-relances)
- [7. Fichiers produits](#7-fichiers-produits)
- [8. Fichier abîmé](#8-fichier-abîmé)
- [9. Tests et méthode TDD](#9-tests-et-méthode-tdd)
- [10. Dépannage](#10-dépannage)
- [11. Limites connues](#11-limites-connues)

---

## 1. Démarrage

```bash
pip install -r requirements.txt          # Python 3.11 (voir .python-version)
cp .env.example .env                     # puis remplir au minimum GOOGLE_PLACES_API_KEY
python -m streamlit run app.py           # interface web (recommandé)
python main.py                           # ou ligne de commande
```

Avant toute modification, vérifier que tout est vert :

```bash
pip install -r requirements-dev.txt
python run_tests.py                      # tous les tests, sans réseau ni crédits
```

---

## 2. Interface ou ligne de commande : ce qui change

Deux parcours existent. **L'interface est la version complète** ; la ligne de commande sert aux lancements
automatiques (cron).

| | Interface (`app.py` → `pipeline.py`) | Ligne de commande (`main.py`) |
|---|---|---|
| Choix service × cible (cuisinistes, piscinistes…) | ✅ | ❌ (mots-clés du `.env`) |
| Sources | Google Maps, Sirène, Pages Jaunes, France Travail, Google Search, CSV LinkedIn | Google Maps |
| Plusieurs villes, critères de sélection | ✅ | ✅ (`.env`) |
| Filtre métier, vérification Sirène, site retrouvé, score d'opportunité | ✅ | ❌ |
| Envoi des mails Gmail (immédiat ou programmé) | ✅ | ❌ (brouillons seulement) |
| SMS Brevo | ✅ (case à cocher) | ✅ (dès qu'une clé Brevo existe) |
| CRM local (pipeline, « Ma journée ») | ✅ | ❌ |
| Marquage « déjà contacté » | Seulement si un mail/SMS est réellement parti | À chaque lancement |
| Relances | Page « Relances » | `python main.py --followup` |
| Désinscription | Refus exclus partout | `python main.py --optout adresse@…` |

**Attention :** une règle de sélection (filtre, refus, déjà contactés) doit être ajoutée **aux deux endroits** :
`pipeline.py` (`run_prospection`) et `main.py` (`run`). Les tests `tests/test_app_pipeline.py` et
`tests/test_pipeline_main.py` attrapent un oubli.

---

## 3. Je veux modifier… (table de repérage)

| Je veux modifier | Fichier | Où |
|---|---|---|
| Les cibles (métiers, mots-clés par secteur) | `target_segments.py` | `TARGET_SEGMENTS` |
| Les métiers reconnus, synonymes, catégories Google, codes NAF | `trades.py` | `TRADES` |
| Les services proposés (accroche, poids du score) | `service_profiles.py` | `SERVICE_PROFILES` |
| Les franchises / distributeurs exclus | `services/franchises.py` (ou page Réglages) | `FRANCHISES`, `AMBIGUOUS` |
| Les critères de sélection (note, avis, site, téléphone…) | `filters.py` | `FilterCriteria` |
| Le score d'opportunité (points de chaque composante) | `services/opportunity.py` | constantes en haut du fichier |
| Les défauts de site détectés et leurs poids | `services/analyzer.py` | `_DEFAULT_WEIGHTS`, fonctions `_check_*` |
| Le texte des mails de l'interface | `services/mailer.py` | `build_dynamic_email`, `ISSUE_COPY` |
| Le texte des relances (séquence de 4) | `services/mailer.py` | `draft_followup_email` |
| La mention STOP / origine de l'adresse | `.env` (`UNSUBSCRIBE_TEXT`) ou `services/mailer.py` | `DEFAULT_UNSUBSCRIBE_TEXT` |
| Le texte du SMS | `services/sms.py` | `_build_sms` (160 caractères max) |
| Les délais du CRM (relance, rappel…) | Page Réglages, ou `crm_store.py` | `DEFAULT_DELAYS` |
| Le seuil « site trop bon pour être contacté » | Interface (curseur) ou `.env` | `CONTACT_SCORE_THRESHOLD` |

---

## 4. Variables d'environnement

Tout se règle dans `.env` (copié depuis `.env.example`). Dans l'interface, les champs de la page **Réglages**
sont pré-remplis avec ces valeurs et sont mémorisés dans `output/settings.json`.

| Variable | Rôle |
|---|---|
| `GOOGLE_PLACES_API_KEY` | **Obligatoire.** Recherche Google Maps (activer « Places API » sur le projet Google Cloud) |
| `NOTION_API_KEY` | CRM Notion (optionnel). Partager la base avec l'intégration |
| `BREVO_API_KEY` | SMS (mobiles 06/07 uniquement) |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | Envoi des mails depuis l'interface (mot de passe d'application, pas le vrai) |
| `SEARCH_KEYWORDS`, `SEARCH_LOCATION` | Ligne de commande : mots-clés (virgules) et villes (séparées par `;`) |
| `SEARCH_RADIUS`, `MAX_RESULTS_PER_KEYWORD` | Rayon (m) et nombre de prospects par mot-clé |
| `MIN_RATING`, `MAX_RATING`, `MIN_REVIEWS`, `MAX_REVIEWS` | Fourchettes de note et d'avis Google |
| `WEBSITE_FILTER`, `PHONE_FILTER`, `EXCLUDE_CLOSED`, `REQUIRE_EMAIL` | Critères de sélection (voir `.env.example`) |
| `CONTACT_SCORE_THRESHOLD` | Qualité de site maximale pour contacter (défaut 70) |
| `FOLLOWUP_DELAY_DAYS` | Jours sans réponse avant relance (défaut 5) |
| `YOUR_NAME`, `YOUR_TITLE`, `YOUR_EMAIL`, `YOUR_WEBSITE` | Signature des mails |
| `UNSUBSCRIBE_TEXT` | Remplace la mention STOP / origine de l'adresse en bas des mails |

---

## 5. Désinscription (STOP)

- **Chaque mail** (premier contact, mails de l'interface, candidature freelance, les 4 relances) se termine,
  après la signature, par une mention qui dit d'où vient l'adresse et comment refuser (« répondez STOP »).
- **Chaque mail envoyé** porte l'en-tête `List-Unsubscribe` : le bouton « Se désabonner » de Gmail t'envoie un
  mail « STOP ».
- **Enregistrer un refus :** `python main.py --optout adresse@exemple.fr`. Il est stocké dans `output/optout.json`.
- **Effet :** la personne est exclue **partout** : recherche (par fiche Google, avant même de visiter son site),
  après analyse (par l'email trouvé), envoi Gmail immédiat **et programmé** (un envoi programmé avant le refus est
  annulé), SMS, relances, et CRM (fiche passée en « blacklist », plus aucune action dans « Ma journée »).
- **Sécurité :** si `optout.json` est abîmé, sa copie de secours est restaurée automatiquement ; s'il n'y en a pas,
  le programme **s'arrête** avant tout appel payant (voir §8).

Le bot ne lit pas ta boîte mail : c'est à toi d'enregistrer les STOP. Ce n'est pas un conseil juridique : les
règles de la prospection B2B par mail (information, droit d'opposition) sont à vérifier auprès de la CNIL.

---

## 6. Relances

- Un prospect contacté est enregistré dans `output/contacted_place_ids.json` (date du 1er et du dernier message).
- La relance suivante est **due** quand le **dernier** message date d'au moins `FOLLOWUP_DELAY_DAYS` jours, sans
  réponse enregistrée, dans la limite de 4 relances, et **jamais** pour un refus STOP.
- **Interface :** page « Relances ». **Ligne de commande :** `python main.py --followup` (un `.txt` par contact
  dans `output/relances_<date>/`). Les relances sont générées, tu les envoies toi-même.

---

## 7. Fichiers produits

Tout est dans `output/` (ignoré par git : **données personnelles, ne jamais les commiter**).

| Fichier | Contenu |
|---|---|
| `prospects_<date>.json` / `.csv` | Prospects retenus (le CSV s'ouvre dans Excel) |
| `contacted_place_ids.json` | Qui a déjà été contacté, quand, réponse, relances |
| `contacted_place_ids.bak.json` | Copie de secours automatique du fichier des contacts |
| `optout.json` (+ `.bak`) | Les refus STOP (+ copie de secours) |
| `history.json` (+ `.bak`) | 50 derniers lancements (+ copie de secours) |
| `*.corrupt` (`.corrupt.1`, `.corrupt.2`…) | Fichier abîmé mis de côté, jamais supprimé ni écrasé |
| `crm.db` | CRM local (pipeline, statuts, « Ma journée ») |
| `pending_emails.json` | Mails programmés (sans aucun mot de passe) |
| `analysis_cache.json` | Analyses de sites réutilisées pendant 30 jours |
| `settings.json` | Réglages de l'interface (sans mot de passe Gmail) |

Ne supprime jamais `contacted_place_ids.json` ni `optout.json` « pour repartir de zéro » : tu recontacterais
tout le monde, y compris des personnes qui ont dit STOP.

---

## 8. Fichier abîmé

**Pourquoi un fichier peut s'abîmer :** une coupure pendant l'écriture, ou une modification à la main qui casse
le JSON. Les écritures du bot sont **atomiques** (fichier temporaire puis remplacement d'un coup) : une coupure
ne laisse plus de fichier à moitié écrit.

**Ce que fait le bot tout seul** (contacts, refus STOP, historique) :

1. Avant chaque écriture, la version précédente lisible est copiée dans la copie de secours.
2. Au chargement, si le fichier est illisible mais que la copie est lisible : le fichier abîmé est renommé en
   `.corrupt`, la copie le remplace, un avertissement « copie de secours restaurée » s'affiche (terminal et
   interface), et le lancement continue. Personne présent dans la copie n'est recontacté.
3. S'il n'y a **aucune** copie lisible (contacts ou refus) : arrêt **avant tout appel Google**, aucun fichier
   modifié. Pour l'historique (simples statistiques), le fichier est mis de côté en `.corrupt` et repart de zéro.

**Ce que tu dois faire :**

- **Après une restauration automatique :** rien d'obligatoire. La copie est la version d'avant la **dernière
  écriture** : ce que cette écriture avait ajouté peut manquer (les contacts du dernier lancement, un « a
  répondu », un STOP récent). Compare avec le `.corrupt` si besoin et ré-enregistre un refus récent avec
  `python main.py --optout adresse@exemple.fr`.
- **Si le bot s'arrête** (« aucune copie de secours lisible ») :
  1. Ne supprime pas le fichier.
  2. Ouvre le fichier et sa copie dans un éditeur ; repère l'erreur JSON (souvent la fin tronquée : accolade ou
     crochet manquant) avec un validateur JSON.
  3. Corrige le fichier, ou remplace-le par une sauvegarde à toi.
  4. Relance : si le fichier est lisible, le bot repart normalement.
- Les `.corrupt` peuvent être supprimés à la main une fois que tu as vérifié qu'il ne manque rien.

---

## 9. Tests et méthode TDD

```bash
python run_tests.py                          # tout, sans réseau (moins d'une minute)
python -m pytest tests/test_unsubscribe.py   # un fichier
python run_tests.py --campaign               # VRAIE API Google : consomme des crédits
```

Les tests de comportement lancent le **vrai parcours** (`main.run`, `pipeline.run_prospection`, les pages de
l'interface) avec de faux services (`tests/fakes.py`) : Google Maps, PageSpeed, Sirène, DNS des emails, sites,
Notion, Brevo, Gmail. Chaque test tourne dans un dossier temporaire (`tests/conftest.py`).

| Fichier | Ce qu'il protège |
|---|---|
| `test_pipeline_main.py` | `python main.py` de bout en bout |
| `test_app_pipeline.py`, `test_app_config.py` | Le parcours de l'interface, et les valeurs saisies dans l'interface |
| `test_services_behavior.py` | Google, Gmail, Notion, SMS, scraping, historique |
| `test_unsubscribe.py` | Désinscription STOP partout |
| `test_safety_files.py` | Fichiers abîmés : écriture sûre, copie, restauration, arrêt |
| `test_mail_contract.py` | Lien entre un défaut détecté et l'accroche du mail |
| `test_qualification_reims.py`, `test_filters.py`, `test_pipeline_selection.py` | Cibles, critères, score d'opportunité |
| `test_pages_run.py` | Chaque page de l'interface s'affiche |
| Autres `test_*.py` | Unitaires (analyse, mails, profils, CRM, Sirène, franchises…) |
| `test_campaign.py` | **Pas** un test automatique : script avec vraie API |

**Boucle de travail pour toute modification :**

1. Décrire le comportement attendu dans un test (`tests/`).
2. Lancer le test : il doit **échouer pour la bonne raison** (le comportement n'existe pas encore).
3. Écrire le minimum de code pour le faire passer.
4. Relancer **toute** la suite (`python run_tests.py`).
5. Un commit par comportement, test et code ensemble, message qui explique l'avant / après.

---

## 10. Dépannage

| Message | Cause / solution |
|---|---|
| `GOOGLE_PLACES_API_KEY manquante` | Clé absente du `.env` / des Réglages |
| `Statut API inattendu (REQUEST_DENIED)` | Places API non activée, clé restreinte ou facturation non activée |
| `Authentification Gmail échouée` | Mot de passe d'application incorrect, ou validation en 2 étapes non activée |
| `⚠️ … copie de secours restaurée automatiquement` | Fichier abîmé remplacé par sa copie : le lancement continue. Voir §8 |
| `Fichier des contacts illisible` / `Fichier de refus illisible` … `aucune copie de secours lisible` | Ni le fichier ni sa copie ne sont lisibles : rien n'a été envoyé ni modifié. Voir §8 |
| Un prospect attendu n'apparaît pas | Regarder l'onglet **Exclus** des résultats : chaque exclusion y figure avec sa raison |
| SMS ignoré pour un prospect | Numéro fixe (04, 01…) : seuls 06/07 reçoivent un SMS |

---

## 11. Limites connues

- Les vrais Google, Gmail, Notion, Brevo et Sirène ne sont jamais appelés par les tests : un changement de leur
  côté ne sera vu qu'en usage réel.
- La ligne de commande et l'interface ont chacune leur version du parcours (voir §2).
- Le SMS ne contient pas de mention STOP (160 caractères) ; les refus sont quand même exclus des SMS.
- Le bot ne lit pas ta boîte mail : les STOP sont à enregistrer avec `--optout`.
- Le bouton « Sauvegarder ce profil » de la page Nouvelle campagne enregistre un profil qui n'est plus relu nulle
  part depuis le passage au choix service × cible.
