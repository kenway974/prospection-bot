# 🎯 Prospection B2B Automatisée

Script Python + interface web pour trouver des prospects locaux, analyser leur présence en ligne et envoyer des cold emails/SMS personnalisés — le tout en un clic.

---

## Ce que ça fait

1. **Recherche** des commerces et entreprises via Google Places (par mots-clés + ville)
2. **Analyse** automatique de leur site web (SEO, HTTPS, mobile, tracking, formulaires…)
3. **Scrape** leur email de contact directement sur leur site
4. **Génère** un cold email personnalisé selon ce qui a été détecté
5. **Synchronise** les prospects dans ta base Notion
6. **Envoie** les emails via Gmail et/ou les SMS via Brevo (optionnel)

---

## Installation

```bash
# 1. Cloner ou télécharger le projet
cd prospection

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Créer le fichier de config
cp .env.example .env
# → Remplir les clés API dans .env

# 4. Lancer l'interface web
python -m streamlit run app.py

# OU lancer en ligne de commande
python main.py
```

---

## Clés API nécessaires

| Service | Utilité | Lien |
|---------|---------|------|
| **Google Places** | Trouver les entreprises | [console.cloud.google.com](https://console.cloud.google.com/apis/credentials) |
| **Notion** | Sync CRM | [notion.so/my-integrations](https://www.notion.so/my-integrations) |
| **Brevo** | Envoi SMS | [app.brevo.com/settings/keys/api](https://app.brevo.com/settings/keys/api) |
| **Gmail** | Envoi emails | Mot de passe d'app sur [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) |

Seule **Google Places** est obligatoire. Les autres sont optionnelles.

---

## Structure du projet

```
prospection/
│
├── app.py                  → Interface Streamlit (UI web)
├── main.py                 → Point d'entrée ligne de commande
├── config.py               → Config centralisée + logger
├── profiles.py             → 10 profils de prospection prédéfinis
├── profile_manager.py      → Sauvegarde/chargement des profils custom
├── history_manager.py      → Historique des campagnes
├── requirements.txt
├── .env.example            → Modèle de config à copier en .env
│
├── services/
│   ├── google_maps.py      → Appels API Google Places → liste de prospects
│   ├── analyzer.py         → Analyse du site web + scraping email
│   ├── mailer.py           → Génération du cold email personnalisé
│   ├── notion_sync.py      → Sync vers la BDD Notion
│   ├── gmail.py            → Envoi email via SMTP Gmail
│   └── sms.py              → Envoi SMS via API Brevo
│
└── output/                 → Résultats générés automatiquement
    ├── prospects_YYYYMMDD_HHMMSS.json
    ├── prospects_YYYYMMDD_HHMMSS.csv
    ├── prospects_YYYYMMDD_HHMMSS_emails/
    └── history.json
```

---

## Profils disponibles

| Profil | Cible | Angle |
|--------|-------|-------|
| 💻 Dev Web | Commerces sans site / site vieillissant | Création / refonte |
| 🚚 Coursier | Restaurants, épiceries, pharmacies | Livraison express |
| 💐 Fleuriste | Salles de mariage, hôtels | Collaboration événements |
| 📸 Photographe | Restaurants, hôtels, immo | Shooting pro |
| 🏋️ Coach Sportif | Entreprises, RH | Bien-être au travail |
| 📱 Social Media | PME sans réseaux sociaux | Gestion réseaux |
| 🧹 Nettoyage | Bureaux, restaurants, hôtels | Contrat nettoyage |
| 🎯 Consultant Marketing | PME locales | Audit + stratégie |
| 🔍 Chercheur d'emploi | Entreprises qui recrutent | Candidature spontanée |
| ⚙️ Custom | Tout | Libre |

Chaque profil est modifiable depuis l'interface et sauvegardable sous un nom personnalisé.

---

## Analyse du site — ce qui est vérifié

| Check | Ce que ça détecte |
|-------|------------------|
| HTTPS | Site non sécurisé |
| Viewport | Site non responsive (mobile) |
| Title / Meta description | SEO de base absent |
| Favicon | Manque de professionnalisme |
| Formulaire | Pas de capture de lead |
| Tracking | Pas de Google Analytics / GTM / Pixel |
| Vitesse | Temps de réponse > 3s |
| Builder gratuit | Wix, Jimdo, Weebly… |
| Réseaux sociaux | Aucun lien social |
| Email | Scraping mailto + page /contact |

Score sur 100 — plus le score est bas, plus il y a d'opportunités.

---

## Accès depuis un autre appareil (démo / mobile)

```bash
# Accès sur le même WiFi
python -m streamlit run app.py --server.address 0.0.0.0
# → http://TON_IP_LOCAL:8501

# Accès depuis n'importe où (ngrok)
ngrok http 8501
# → URL publique temporaire
```

---

## Variables d'environnement (.env)

```env
# Obligatoire
GOOGLE_PLACES_API_KEY=AIzaSy...

# Notion CRM
NOTION_API_KEY=secret_...

# Brevo SMS
BREVO_API_KEY=xsmtpsib-...

# Gmail
GMAIL_ADDRESS=toi@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# Critères par défaut (modifiables dans l'UI)
SEARCH_KEYWORDS=restaurant,boulangerie,garage
SEARCH_LOCATION=Lyon, France
SEARCH_RADIUS=10000
MAX_RESULTS_PER_KEYWORD=5

# Signature
YOUR_NAME=Kenny
YOUR_TITLE=Développeur Web Freelance
YOUR_EMAIL=kenny@example.com
YOUR_WEBSITE=https://kennydev.fr
```

---

## Tests

### Tests unitaires (rapides, sans API)

Vérifient le bon fonctionnement de l'analyzer, du mailer et des profils — aucune clé API requise.

```bash
python run_tests.py --unit
```

75 tests couvrent :
- Tous les checks du site web (HTTPS, mobile, SEO, tracking, formulaires…)
- La cohérence des emails générés (sujet singulier/pluriel, accroche selon le diagnostic, CTA adapté au score)
- La validité des 10 profils prédéfinis (keywords, hooks, SMS ≤ 160 chars…)
- La sauvegarde/chargement/suppression des profils custom

### Tests d'intégration multi-villes (avec API)

Lance de vraies campagnes sur plusieurs villes et génère un rapport de métriques.

```bash
# Toutes les campagnes (5 villes × plusieurs keywords)
python run_tests.py --campaign

# Une ville spécifique
python run_tests.py --campaign --filtre "Lyon"

# Limiter le nombre de prospects par mot-clé
python run_tests.py --campaign --max 2
```

Campagnes incluses par défaut :
- Dev Web — Lyon
- Dev Web — Paris 13
- Dev Web — Bordeaux
- Photographe — Paris
- Social Media Manager — Marseille

Le rapport est sauvegardé dans `output/rapport_test_YYYYMMDD_HHMMSS.json` et affiche dans la console :
- Total prospects / taux sans site / taux email trouvé / taux mobile
- Score moyen par campagne
- Top issues les plus fréquentes
- Top 5 meilleures opportunités toutes villes confondues

### Tout lancer d'un coup

```bash
python run_tests.py --all
```

---

## Sécurité

- Les clés API restent **sur ta machine**, elles ne transitent jamais vers un serveur externe
- Le fichier `.env` est **exclu du git** (ajoute-le dans `.gitignore` avant de partager le code)
- Ne jamais partager tes clés dans un chat, email ou screenshot
