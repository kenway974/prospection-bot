# Comportements de l'application — à choisir

**Mode d'emploi** : coche `[x]` ce qu'on garde, laisse `[ ]` ce qu'on jette, ajoute une ligne si quelque chose manque.
Ensuite, chaque ligne cochée devient un test, puis le code.
La liste mélange ce que fait l'app aujourd'hui, des besoins probables et les cas d'erreur.

---

## 1. Lancer une recherche

- [ ] Je choisis un ou plusieurs métiers (mots-clés) et une ou plusieurs villes
- [ ] Je choisis un profil de cible prédéfini (cuisinistes, piscinistes, restaurants…) qui remplit les mots-clés
- [ ] Je choisis un rayon de recherche autour de la ville
- [ ] Je fixe un nombre maximum de résultats par mot-clé
- [ ] L'app lance aussi des synonymes du métier (« cuisiniste » → « cuisine sur mesure »), 3 requêtes maximum
- [ ] L'app m'affiche une estimation du coût Google avant de lancer
- [ ] L'app refuse de lancer si aucune ville n'est saisie, et me dit pourquoi
- [ ] L'app refuse de lancer si aucun mot-clé n'est saisi, et me dit pourquoi
- [ ] L'app s'arrête proprement si la clé Google manque, avec un message qui dit où la mettre
- [ ] Si Google ne renvoie rien, l'app le dit au lieu de planter
- [ ] Si Google répond en erreur (quota, clé refusée), l'app affiche l'erreur exacte et s'arrête sans rien envoyer
- [ ] Si le réseau coupe pendant la recherche, l'app garde ce qui a déjà été trouvé
- [ ] Je peux arrêter une recherche en cours
- [ ] Je vois la progression en direct (étape, nombre de prospects traités)
- [ ] Je peux sauvegarder une recherche (métiers + villes + critères) et la relancer plus tard
- [ ] Je peux programmer une recherche récurrente (ex. chaque lundi)

## 2. Trouver d'autres sources de prospects

- [ ] Google Maps (fiches d'établissements)
- [ ] Entreprises récemment créées (registre Sirène / BODACC), filtrées par activité, zone et date de création
- [ ] Import d'une liste CSV que j'ai déjà
- [ ] Les critères Google (note, avis) ne s'appliquent pas aux autres sources

## 3. Filtrer les prospects

- [ ] Exclure les établissements fermés définitivement
- [ ] Exclure au-dessus d'une note Google maximale
- [ ] Exclure en dessous / au-dessus d'un nombre d'avis
- [ ] Ne pas exclure un établissement sans note
- [ ] Filtrer : avec site / sans site / peu importe
- [ ] Filtrer : avec téléphone / mobile seulement / peu importe
- [ ] Filtrer : email obligatoire (appliqué après la recherche d'email)
- [ ] Exclure les franchises et chaînes connues (liste fournie + ma propre liste)
- [ ] Ne pas exclure un indépendant dont le nom ressemble à une enseigne (mot entier seulement)
- [ ] Exclure les établissements hors métier (restaurant dans une recherche « cuisiniste », école, cours de cuisine…)
- [ ] Marquer « à vérifier » au lieu d'exclure quand le métier n'est pas confirmé
- [ ] Vérifier l'entreprise dans le registre Sirène (active, code d'activité cohérent)
- [ ] Une panne du registre Sirène ne fait exclure personne
- [ ] Chaque exclusion a une raison lisible, une seule ligne par prospect
- [ ] Je vois la liste des exclus et pourquoi
- [ ] Je peux repêcher à la main un prospect exclu
- [ ] Un même établissement trouvé par deux mots-clés n'est traité qu'une fois
- [ ] Un prospect déjà contacté n'est jamais repris
- [ ] Les prospects exclus sont remplacés par d'autres pour atteindre le nombre demandé, sans appel payant inutile

## 4. Analyser le site du prospect

- [ ] Retrouver le site quand il manque sur la fiche Google (domaines devinés à partir du nom)
- [ ] N'adopter un site deviné que si la page confirme l'entreprise (même téléphone ou nom + ville)
- [ ] Ne jamais adopter le site d'un homonyme : le signaler « à confirmer »
- [ ] Ne jamais visiter d'adresse interne ou locale (sécurité)
- [ ] Signaler un site sur un domaine étranger
- [ ] Contrôles : HTTPS, temps de réponse, adaptation mobile, titre, méta-description, H1, contenu trop léger, noindex
- [ ] Contrôles : formulaire de contact, outil de suivi (Analytics, pixel), liens réseaux sociaux
- [ ] Contrôles : site fait avec un outil gratuit (Wix…), copyright ancien (site abandonné)
- [ ] Score de vitesse Google (PageSpeed)
- [ ] Score de qualité du site sur 100, avec des poids réglables par profil
- [ ] Je peux désactiver un contrôle (poids 0)
- [ ] Un site inaccessible = prospect à fort potentiel, pas une erreur
- [ ] Une page trop lourde n'est lue qu'en partie (pas de blocage)
- [ ] Les analyses sont mises en cache pendant N jours ; changer les poids invalide le cache
- [ ] Les analyses périmées sont supprimées du cache
- [ ] Je peux vider le cache

## 5. Trouver le contact

- [ ] Récupérer l'email sur le site (lien mailto, texte, pages contact)
- [ ] Ignorer les faux emails techniques (exemple@, images, noreply…)
- [ ] Vérifier l'email : syntaxe, faute de frappe connue (avec suggestion), adresse jetable, domaine qui reçoit des mails
- [ ] Une panne DNS ne fait pas rejeter un email
- [ ] Ne jamais envoyer à un email invalide, même si je force l'envoi
- [ ] Signaler une adresse générique (contact@, info@) sans la rejeter
- [ ] Trouver le dirigeant (registre des entreprises) seulement si la correspondance est sûre
- [ ] Ignorer une holding comme dirigeant
- [ ] Saluer le dirigeant par son nom ; sinon une salutation neutre, sans rien inventer
- [ ] Générer le lien de recherche LinkedIn du dirigeant
- [ ] Distinguer mobile et fixe

## 6. Classer les prospects

- [ ] Score d'opportunité sur 100 : sans site, site faible, sans formulaire, peu d'avis… montent ; présence déjà solide, pas de téléphone, drapeaux « à vérifier » baissent
- [ ] Je vois le détail du calcul de chaque score
- [ ] Les meilleures opportunités sont en premier
- [ ] Seuil de score réglable pour décider qui contacter
- [ ] Choisir l'offre adaptée : création (sans site), migration (Wix…), refonte (site vieux / beaucoup de problèmes), audit (site correct)
- [ ] Bénéfice de l'offre adapté au secteur

## 7. Écrire les messages

- [ ] Mail personnalisé : objet et accroche selon le problème détecté
- [ ] Le mail cite au maximum 3 problèmes
- [ ] Mail sans site : pas de liste de problèmes vide
- [ ] Appel à l'action différent selon le score
- [ ] Accroche personnalisée par profil
- [ ] Signature (nom, titre) configurable dans l'interface
- [ ] Mode candidature freelance : mail sans audit du site, avec portfolio
- [ ] Séquence de relances (jusqu'à 4) avec des angles différents
- [ ] SMS de 160 caractères maximum, mobiles uniquement
- [ ] Message LinkedIn (invitation + message) sans variable non remplie ni ligne vide
- [ ] Je relis et je modifie chaque brouillon avant l'envoi
- [ ] Les brouillons sont enregistrés en fichiers texte

## 8. Envoyer

- [ ] Rien n'est envoyé sans que je coche « envoyer »
- [ ] Envoi par Gmail (mot de passe d'application)
- [ ] Mauvais mot de passe Gmail : message clair, pas de plantage, personne marqué contacté
- [ ] Bilan de l'envoi : envoyés, ignorés, échecs
- [ ] Limite quotidienne d'envois (bonne réputation du domaine)
- [ ] Délai entre deux envois
- [ ] Programmer un envoi à une date / heure
- [ ] Un envoi programmé n'est jamais perdu, même si l'app redémarre
- [ ] Aucun mot de passe écrit sur le disque
- [ ] SMS via Brevo ; sans clé Brevo rien n'est envoyé ; une erreur Brevo compte comme échec
- [ ] Seul un envoi réussi marque le prospect comme contacté
- [ ] Une recherche sans envoi ne marque personne comme contacté

## 9. Désinscription (STOP)

- [ ] Chaque mail dit d'où vient l'adresse et comment refuser (« répondez STOP »)
- [ ] Mention de désinscription après la signature, une seule fois, texte personnalisable
- [ ] En-tête de désinscription en un clic dans les mails envoyés
- [ ] J'enregistre un refus (interface ou ligne de commande)
- [ ] Une réponse « STOP » reçue est enregistrée automatiquement
- [ ] Un refus est définitif : plus aucun mail, SMS, relance ni envoi programmé
- [ ] Un refus sort le prospect du CRM et de « Ma journée »
- [ ] Un refus est reconnu par email ou par fiche Google, sans tenir compte de la casse ni des espaces
- [ ] Le site d'un refus n'est même pas visité

## 10. Suivi et relances

- [ ] Détection automatique des réponses Gmail (toutes les 5 min)
- [ ] Un prospect qui a répondu n'est plus relancé
- [ ] Relance proposée après N jours sans réponse (délai réglable)
- [ ] Une relance déjà envoyée n'est pas reproposée
- [ ] Page « Ma journée » : actions dues aujourd'hui et en retard, les plus en retard d'abord
- [ ] Actions de suivi (rappeler, envoyer une maquette…) avec délai en jours ouvrés
- [ ] Une réponse annule la relance prévue
- [ ] Historique (timeline) de chaque prospect

## 11. CRM

- [ ] CRM local : statut de chaque prospect (nouveau, contacté, répondu, rendez-vous, client, perdu…)
- [ ] Un statut avancé n'est jamais dégradé par un nouveau contact
- [ ] Un email connu n'est pas effacé par un résultat vide
- [ ] Liste noire : jamais reprospecté
- [ ] Export vers Notion : une fiche par prospect, pas de doublon ; une erreur Notion ne crée rien
- [ ] Sans clé Notion, aucun appel Notion
- [ ] Export CSV lisible par Excel
- [ ] Rapport JSON de chaque campagne

## 12. Statistiques

- [ ] Nombre de campagnes, prospects, contactés, réponses, taux de réponse
- [ ] Résultats par métier et par ville
- [ ] Historique des 50 dernières campagnes

## 13. Fichiers et sécurité des données

- [ ] Écriture sûre : une coupure pendant l'écriture laisse le fichier intact
- [ ] Copie de secours de la version précédente
- [ ] Fichier abîmé : restauration depuis la copie, fichier abîmé mis de côté, jamais supprimé
- [ ] Fichier abîmé sans copie : arrêt avant tout appel payant ou tout envoi, message qui dit quoi faire
- [ ] Fichier momentanément inaccessible : « réessayez », sans le traiter comme abîmé
- [ ] Deux enregistrements simultanés ne s'écrasent pas
- [ ] L'interface affiche un message clair au lieu de planter
- [ ] Les clés API restent dans `.env`, jamais dans le code ni dans les rapports
- [ ] Je peux réinitialiser l'historique des contacts (avec confirmation)
- [ ] Sauvegarde / export complet de mes données en un clic

## 14. Réglages

- [ ] Clés API saisies dans l'interface ou dans `.env`
- [ ] Tester chaque clé (Google, Gmail, Brevo, Notion) avec un bouton
- [ ] Profils de service (mon offre, mon titre) prédéfinis et personnalisés
- [ ] Profils de cible prédéfinis et personnalisés ; un profil perso remplace le prédéfini de même nom
- [ ] Mes réglages sont retrouvés au prochain lancement

## 15. Ligne de commande

- [ ] Lancer une campagne sans interface
- [ ] Générer seulement les relances dues
- [ ] Enregistrer un refus STOP
- [ ] Valeur invalide : arrêt avec un message clair

## 16. Respect des règles

- [ ] Respect des conditions Google : pas de scraping de Google, quotas respectés
- [ ] Prospection B2B conforme RGPD : offre liée au métier, origine de l'adresse, refus facile
- [ ] Respect des entrepreneurs qui ont refusé la diffusion dans Sirène
- [ ] Durée de conservation des données des prospects jamais contactés (purge automatique)

---

## Mes ajouts

- [ ]
