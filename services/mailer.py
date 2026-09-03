"""
Génère un brouillon de cold email ultra-personnalisé.

Logique de construction :
  - Cas 1 : Pas de site web → offre de création
  - Cas 2 : Site inaccessible → urgence disponibilité
  - Cas 3 : 1 seul problème → mail focus sur ce point précis
  - Cas 4 : 2-3 problèmes → mail avec liste courte
  - Cas 5 : 4+ problèmes → mail audit complet
  - Profil custom → accroche définie par l'utilisateur en priorité
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Dict
from config import config, logger
from services.google_maps import Prospect


# ---------------------------------------------------------------------------
# Style configurable des emails dynamiques
# ---------------------------------------------------------------------------

@dataclass
class EmailStyle:
    intonation: str = "professional"  # "formal" | "professional" | "direct" | "casual"
    length: str = "medium"            # "short" | "medium" | "long"
    salutation: str = "neutral"       # "formal" | "neutral" | "first_name"
    cta: str = "audit"               # "audit" | "call" | "meeting" | "reply"


EMAIL_STYLE_LABELS = {
    "intonation": {
        "formal":       "Formel",
        "professional": "Professionnel",
        "direct":       "Direct",
        "casual":       "Décontracté",
    },
    "length": {
        "short":  "Court (3-4 lignes)",
        "medium": "Moyen (2 paragraphes)",
        "long":   "Long (3 paragraphes)",
    },
    "salutation": {
        "formal":     "Madame, Monsieur,",
        "neutral":    "Bonjour,",
        "first_name": "Bonjour [Prénom],",
    },
    "cta": {
        "audit":   "Je vous propose un audit gratuit — sans engagement.",
        "call":    "Seriez-vous disponible pour un appel de 15 min cette semaine ?",
        "meeting": "Je serais ravi(e) d'en discuter lors d'un rapide échange.",
        "reply":   "N'hésitez pas à me répondre pour en savoir plus.",
    },
}

# Structure : issue_key → {intonation: sentence}
# {name} sera remplacé par le nom du prospect, {cms} par le CMS détecté
ISSUE_COPY = {
    "no_website": {
        "formal":       "Il m'est apparu que {name} ne dispose pas encore de site internet. Dans votre secteur d'activité, cette absence constitue un frein significatif à l'acquisition de nouveaux clients.",
        "professional": "En cherchant {name} en ligne, j'ai constaté l'absence de site web. Dans votre secteur, une présence web est devenue incontournable pour capter de nouveaux clients.",
        "direct":       "{name} n'a pas de site web — vos concurrents captent chaque jour les clients qui vous cherchent sur Google.",
        "casual":       "J'ai voulu consulter votre site web... et je n'en ai pas trouvé ! Dans votre domaine, c'est une vraie opportunité à saisir avant vos concurrents.",
    },
    "site_down": {
        "formal":       "Votre site internet semble actuellement inaccessible, ce qui prive vos clients potentiels de tout accès à votre activité en ligne.",
        "professional": "Votre site est actuellement inaccessible — vos visiteurs tombent sur une erreur et repartent chez la concurrence.",
        "direct":       "Votre site est down. Vos clients ne peuvent pas vous trouver en ligne.",
        "casual":       "Mauvaise nouvelle : votre site est actuellement inaccessible ! Vos clients arrivent sur une page d'erreur...",
    },
    "https": {
        "formal":       "Votre site fonctionne en HTTP non sécurisé, ce qui entraîne l'affichage d'un avertissement de sécurité dans les navigateurs et pénalise votre référencement.",
        "professional": "Votre site n'est pas sécurisé (HTTP) : Google affiche un avertissement à vos visiteurs et pénalise les sites sans HTTPS dans ses résultats.",
        "direct":       "Votre site est en HTTP — pas en HTTPS. Google le déclasse et vos visiteurs voient un avertissement de sécurité.",
        "casual":       "Votre site n'a pas le cadenas HTTPS — les navigateurs affichent un message d'alerte à vos visiteurs, ce qui fait fuir beaucoup de monde.",
    },
    "viewport": {
        "formal":       "Votre site n'est pas optimisé pour les appareils mobiles, alors que plus de 60 % des recherches locales sont effectuées depuis un smartphone.",
        "professional": "Votre site n'est pas adapté aux mobiles — or plus de 60% de vos clients potentiels vous cherchent depuis leur téléphone.",
        "direct":       "Votre site n'est pas responsive. Sur mobile, il est illisible — 60% de vos visiteurs potentiels partent immédiatement.",
        "casual":       "Sur téléphone, votre site est vraiment difficile à lire... Et c'est sur mobile que la plupart des gens vous cherchent !",
    },
    "tracking": {
        "formal":       "Aucun outil de mesure d'audience n'est installé sur votre site, ce qui vous prive de toute donnée sur le comportement de vos visiteurs.",
        "professional": "Votre site ne dispose d'aucun analytics — vous ne savez pas combien de personnes vous visitent, ni comment elles vous ont trouvé.",
        "direct":       "Pas d'analytics sur votre site. Vous pilotez à l'aveugle : impossible de savoir ce qui marche ou non.",
        "casual":       "Votre site n'a pas de stats ! Vous ne pouvez pas savoir combien de personnes le visitent ni ce qu'elles font dessus.",
    },
    "lead_form": {
        "formal":       "Votre site ne propose pas de formulaire de contact, ce qui complique considérablement la prise de contact pour vos visiteurs.",
        "professional": "Votre site n'a pas de formulaire de contact visible — vos visiteurs intéressés n'ont aucun moyen simple de vous joindre.",
        "direct":       "Pas de formulaire sur votre site. Vos visiteurs n'ont aucun moyen facile de vous contacter — vous perdez des leads.",
        "casual":       "Il n'y a pas de formulaire de contact sur votre site — un visiteur intéressé ne sait pas comment vous écrire facilement !",
    },
    "free_builder": {
        "formal":       "Votre site est actuellement construit avec {cms}, un outil grand public qui présente des limitations importantes en matière de référencement et de personnalisation.",
        "professional": "Votre site est sur {cms} — ces plateformes limitent vos options SEO, votre vitesse de chargement et la personnalisation de votre image.",
        "direct":       "Votre site tourne sur {cms}. Ces outils freinent votre référencement Google et donnent une image peu professionnelle.",
        "casual":       "Votre site est sur {cms} — c'est bien pour démarrer, mais ça bloque votre référencement et ça se voit visuellement.",
    },
    "response_time": {
        "formal":       "Votre site présente des temps de chargement élevés, ce qui nuit à l'expérience utilisateur et pénalise votre positionnement dans les résultats Google.",
        "professional": "Votre site est lent à charger sur mobile — Google pénalise les sites qui mettent plus de 3 secondes, et vos visiteurs abandonnent avant même de voir votre contenu.",
        "direct":       "Votre site est lent. Google déclasse les sites lents, et vos visiteurs partent avant que la page charge.",
        "casual":       "Votre site met beaucoup de temps à charger... 3 secondes, c'est le maximum avant que les gens partent sans même voir votre contenu.",
    },
    "title": {
        "formal":       "La balise titre de votre site n'est pas optimisée, ce qui limite significativement votre visibilité dans les résultats de recherche Google.",
        "professional": "La balise titre de votre site (ce qui apparaît dans Google) est absente ou mal renseignée — vous n'apparaissez pas sur vos mots-clés cibles.",
        "direct":       "Votre balise titre est mal configurée — vous n'apparaissez pas sur Google pour les recherches de vos clients.",
        "casual":       "Sur Google, le titre de votre site n'est pas optimisé — du coup vous n'apparaissez pas quand vos clients vous cherchent.",
    },
    "meta_description": {
        "formal":       "La méta-description de votre site est absente ou générique, réduisant votre taux de clics depuis les résultats Google.",
        "professional": "Votre méta-description (le texte affiché sous votre lien dans Google) est absente — c'est une occasion manquée de convaincre les visiteurs de cliquer.",
        "direct":       "Votre description dans Google est vide ou générique. Personne ne clique sur un lien sans description.",
        "casual":       "Dans Google, sous le lien de votre site, il n'y a pas de description... ça donne peu envie de cliquer !",
    },
    "social_links": {
        "formal":       "Votre site ne référence aucun réseau social, privant vos visiteurs d'un moyen de vous suivre et de maintenir le contact avec votre marque.",
        "professional": "Votre site n'affiche aucun lien vers vos réseaux sociaux — une opportunité manquée de fidéliser vos visiteurs.",
        "direct":       "Pas de liens réseaux sociaux sur votre site. Vous perdez des followers potentiels à chaque visite.",
        "casual":       "Vos réseaux sociaux ne sont pas liés depuis votre site — dommage, vous ratez des abonnés !",
    },
    "outdated": {
        "formal":       "Le design de votre site semble dater de plusieurs années, ce qui peut nuire à la perception de professionnalisme et de modernité de votre activité.",
        "professional": "Visuellement, votre site date — un design moderne renforce immédiatement la confiance de vos visiteurs et reflète mieux la qualité de vos services.",
        "direct":       "Votre site est visuellement daté. En 2024, un site vieillissant fait fuir les clients avant même qu'ils lisent votre offre.",
        "casual":       "Honnêtement, votre site a un peu vieilli visuellement — ça peut donner l'impression que votre activité n'est plus très active.",
    },
    "seo_visibility": {
        "formal":       "Votre site présente des limitations de visibilité qui restreignent significativement son trafic organique : il apparaît peu, voire pas, dans les résultats de recherche Google.",
        "professional": "Votre site reçoit probablement très peu de trafic depuis Google — sa structure et son contenu ne sont pas optimisés pour être trouvés par vos clients qui recherchent vos services.",
        "direct":       "Votre site est quasi invisible sur Google. Concrètement, personne ne tombe dessus en cherchant vos services — vous passez à côté de clients chaque jour.",
        "casual":       "En l'état, votre site a du mal à être trouvé sur Google — du coup il reçoit peu de visites, alors qu'il y a un vrai potentiel à capter !",
    },
}

# ---------------------------------------------------------------------------
# Copy créatif (catégorie "creatif") — angle : vos visuels ne reflètent pas votre qualité
# ---------------------------------------------------------------------------

CREATIVE_ISSUE_COPY = {
    "no_gallery": {
        "formal":       "Votre site ne présente pas de galerie de réalisations, ce qui limite significativement la perception de votre savoir-faire par vos visiteurs.",
        "professional": "Votre site n'a pas de galerie photo — vos réalisations sont pourtant votre meilleure carte de visite pour convaincre de nouveaux clients.",
        "direct":       "Pas de galerie sur votre site. Vos clients ne peuvent pas voir votre travail — vous perdez des demandes chaque jour.",
        "casual":       "Dommage, votre site n'a pas de galerie ! Vos clients veulent voir vos créations avant de vous contacter.",
    },
    "no_video": {
        "formal":       "Votre site ne contient pas de vidéo de présentation, alors que ce format génère en moyenne 80 % de conversions supplémentaires.",
        "professional": "Votre site n'a pas de vidéo de présentation — c'est pourtant le format le plus efficace pour convaincre en quelques secondes.",
        "direct":       "Pas de vidéo sur votre site. Les pages avec vidéo convertissent 80 % mieux. Vous laissez des clients partir.",
        "casual":       "Votre site n'a pas de vidéo de présentation — c'est dommage, c'est ce qui convainc le plus vite !",
    },
    "outdated": {
        "formal":       "L'esthétique de votre site ne reflète pas la qualité de vos réalisations — un design moderne renforcerait immédiatement votre crédibilité.",
        "professional": "Visuellement, votre site a vieilli — alors que vos créations méritent un écrin à la hauteur de leur qualité.",
        "direct":       "Votre site est daté visuellement. Un créatif avec un vieux site, ça interroge les clients.",
        "casual":       "Franchement, votre site mériterait un coup de jeune ! Vos créations valent bien mieux que ça.",
    },
    "free_builder": {
        "formal":       "Votre site est construit avec {cms}, un outil qui limite considérablement les possibilités créatives et les performances.",
        "professional": "Votre site tourne sur {cms} — ces plateformes limitent la créativité et donnent une image générique difficile à personnaliser.",
        "direct":       "Votre site est sur {cms}. Pour un créatif, c'est un signal négatif — trop peu personnalisable.",
        "casual":       "Ah, votre site est sur {cms}... Pour quelqu'un dans le créatif, ça peut paraître contradictoire aux clients !",
    },
    "social_links": {
        "formal":       "Votre site ne renvoie vers aucun réseau social, alors que ces plateformes sont essentielles pour valoriser votre travail.",
        "professional": "Votre site n'a pas de liens vers vos réseaux — Instagram et Pinterest sont pourtant essentiels pour valoriser votre travail créatif.",
        "direct":       "Pas de liens réseaux sociaux. Dans le créatif, Instagram est votre vitrine — vous perdez des abonnés à chaque visite.",
        "casual":       "Vos réseaux ne sont pas liés depuis votre site... Dans votre domaine, c'est une vraie vitrine à ne pas négliger !",
    },
    "no_blog": {
        "formal":       "Votre site ne propose pas de contenu éditorial régulier, ce qui limite votre référencement et votre positionnement en tant qu'expert.",
        "professional": "Votre site n'a pas de blog — publier vos coulisses et réflexions renforcerait votre positionnement et votre SEO.",
        "direct":       "Pas de blog sur votre site. Les créatifs qui publient régulièrement sont mieux référencés et perçus comme experts.",
        "casual":       "Un blog ou section actu sur votre site vous aiderait vraiment à vous positionner comme référence dans votre domaine !",
    },
}

# ---------------------------------------------------------------------------
# Copy conseil B2B (catégorie "conseil_b2b") — angle : impact business mesurable
# ---------------------------------------------------------------------------

CONSEIL_ISSUE_COPY = {
    "tracking": {
        "formal":       "L'absence d'outils de mesure sur votre site vous prive de toute donnée sur l'efficacité de vos actions commerciales et marketing.",
        "professional": "Votre site n'a pas d'analytics — impossible de mesurer votre ROI ou de savoir quelles actions amènent réellement des prospects.",
        "direct":       "Pas d'analytics. Vous pilotez votre activité à l'aveugle — impossible de savoir ce qui ramène des clients.",
        "casual":       "Votre site n'a pas de stats ! Vous ne savez pas ce qui marche vraiment dans votre stratégie commerciale.",
    },
    "lead_form": {
        "formal":       "L'absence de formulaire de capture sur votre site vous prive d'un levier essentiel de génération de leads qualifiés.",
        "professional": "Votre site n'a pas de formulaire de prise de contact — chaque visiteur intéressé qui ne peut pas vous contacter facilement est un prospect perdu.",
        "direct":       "Pas de formulaire. Vos visiteurs intéressés n'ont aucun moyen de vous contacter simplement — vous perdez des leads.",
        "casual":       "Il n'y a pas de formulaire sur votre site ! Un prospect qui cherche à vous contacter et n'y arrive pas... il va ailleurs.",
    },
    "title": {
        "formal":       "L'absence de balise titre optimisée compromet votre visibilité sur vos mots-clés professionnels dans les résultats de recherche.",
        "professional": "Votre balise titre n'est pas optimisée — vous n'apparaissez pas quand vos clients cibles cherchent vos services sur Google.",
        "direct":       "Votre titre Google n'est pas configuré. Vos prospects ne vous trouvent pas quand ils cherchent vos services.",
        "casual":       "Sur Google, votre site n'est pas bien référencé sur vos mots-clés pros — vos clients ont du mal à vous trouver.",
    },
    "no_blog": {
        "formal":       "L'absence de contenu à valeur ajoutée prive votre site d'un levier de crédibilité et de génération de trafic organique B2B.",
        "professional": "Votre site n'a pas de blog ou études de cas — c'est pourtant le levier le plus efficace pour générer des prospects B2B qualifiés.",
        "direct":       "Pas de blog, pas de cas clients. Vos prospects B2B cherchent des preuves de votre expertise avant de vous contacter.",
        "casual":       "Un blog avec vos conseils et cas clients vous amènerait bien plus de prospects qualifiés — et vous positionnerait en expert !",
    },
    "https": {
        "formal":       "Votre site opère en HTTP non sécurisé, ce qui peut susciter des réserves légitimes de la part de vos prospects professionnels.",
        "professional": "Votre site n'est pas sécurisé (HTTP) — dans un contexte B2B, cela questionne votre rigueur auprès de vos prospects.",
        "direct":       "Votre site est en HTTP, pas HTTPS. Pour du B2B, ça donne une image peu sérieuse dès le premier regard.",
        "casual":       "Votre site n'a pas le cadenas sécurisé — pour des prospects professionnels, ça peut faire hésiter.",
    },
    "no_service_mention": {
        "formal":       "Votre site ne détaille pas clairement les domaines d'expertise que vous couvrez, ce qui peut freiner la décision d'achat de vos prospects.",
        "professional": "Votre offre de services n'est pas clairement présentée sur votre site — un prospect qui ne comprend pas en 10 secondes ce que vous faites va voir ailleurs.",
        "direct":       "Votre offre n'est pas claire sur votre site. Les prospects B2B abandonnent s'ils ne trouvent pas rapidement ce qu'ils cherchent.",
        "casual":       "Sur votre site, ce que vous faites exactement n'est pas super clair... Vos prospects doivent le deviner !",
    },
}

# ---------------------------------------------------------------------------
# Copy no_service_mention par service_id (sante / terrain / special)
# Angle : je propose quelque chose qui manque à votre offre / organisation
# ---------------------------------------------------------------------------

NO_SERVICE_MENTION_COPY: Dict[str, Dict[str, str]] = {
    "coaching_sportif": {
        "formal":       "En consultant le site de {name}, je n'ai pas trouvé de programme de bien-être ou de coaching sportif à destination de vos équipes — un levier reconnu pour améliorer la productivité et réduire l'absentéisme.",
        "professional": "Je n'ai pas trouvé de programme sport ou bien-être en entreprise sur le site de {name} — c'est souvent là que se joue la différence sur la rétention et la performance des équipes.",
        "direct":       "{name} ne semble pas proposer de programme sport ou bien-être à ses équipes — vos concurrents le font déjà, et ça se voit sur leurs indicateurs RH.",
        "casual":       "Je n'ai rien vu sur le sport ou le bien-être pour vos équipes sur votre site... C'est pourtant un vrai levier de motivation et de productivité !",
    },
    "nutrition": {
        "formal":       "Il ne semble pas que {name} propose d'accompagnement nutritionnel à ses adhérents, alors que la nutrition est le complément naturel à toute démarche sportive ou bien-être.",
        "professional": "Je n'ai pas trouvé de service de nutrition ou diététique sur le site de {name} — une collaboration pourrait enrichir votre offre sans effort supplémentaire de votre part.",
        "direct":       "{name} ne propose pas de suivi nutritionnel — c'est pourtant ce qui fait la différence entre une offre basique et une offre premium.",
        "casual":       "Je n'ai pas trouvé de coach nutrition associé à {name} — ça compléterait super bien ce que vous proposez déjà !",
    },
    "osteopathie": {
        "formal":       "Votre site ne mentionne pas de partenariat ostéopathique ou kinésithérapeutique, alors que le suivi corporel est essentiel à la performance et à la prévention des blessures.",
        "professional": "Je n'ai pas trouvé de service ostéopathique mentionné pour {name} — un partenariat améliorerait concrètement l'expérience et les résultats de vos sportifs.",
        "direct":       "{name} ne propose pas de suivi ostéo à ses sportifs — c'est pourtant ce qui prévient les blessures et fidélise les clients sur le long terme.",
        "casual":       "Pas d'ostéopathe mentionné sur votre site ! Vos sportifs en ont besoin, et ça valorise vraiment votre offre.",
    },
    "psychologie_travail": {
        "formal":       "Votre site ne fait pas mention d'un programme de soutien psychologique ou de prévention du burnout — un investissement que de nombreuses entreprises considèrent désormais comme prioritaire.",
        "professional": "Je n'ai pas trouvé de programme bien-être mental sur le site de {name} — avec les niveaux d'absentéisme et de turnover actuels, c'est devenu un investissement stratégique.",
        "direct":       "{name} ne propose pas de soutien psychologique à ses équipes — vos concurrents le font et constatent une baisse mesurable de l'absentéisme.",
        "casual":       "Je n'ai rien vu sur le bien-être mental ou la prévention burnout sur votre site... C'est un enjeu majeur aujourd'hui pour fidéliser vos équipes.",
    },
    "nettoyage": {
        "formal":       "En consultant le site de {name}, je n'ai pas trouvé mention d'un prestataire de nettoyage professionnel, ce qui laisse penser que vous gérez peut-être cette problématique en interne.",
        "professional": "Je n'ai pas trouvé de prestataire nettoyage mentionné pour {name} — déléguer à un professionnel permettrait de garantir un résultat irréprochable et de libérer du temps à vos équipes.",
        "direct":       "{name} ne semble pas avoir de prestataire nettoyage pro. Déléguer, c'est garantir un environnement impeccable pour vos clients.",
        "casual":       "Votre site ne mentionne pas de service de nettoyage — si vous cherchez un prestataire fiable et flexible, je suis là !",
    },
    "securite_gardiennage": {
        "formal":       "Il ne semble pas que {name} ait mis en place de dispositif de gardiennage ou de sécurité professionnel, ce qui mérite peut-être une attention particulière au regard de vos actifs.",
        "professional": "Je n'ai pas trouvé de prestataire sécurité mentionné pour {name} — la protection de vos locaux et marchandises mérite une solution professionnelle adaptée à votre activité.",
        "direct":       "{name} ne semble pas avoir de prestataire sécurité. Vos locaux et marchandises méritent mieux qu'une solution improvisée.",
        "casual":       "Pas de mention d'un service de gardiennage sur votre site... La sécurité de vos locaux, c'est pas à négliger !",
    },
    "traiteur": {
        "formal":       "En consultant votre site, je n'ai pas trouvé de solution de restauration pour vos événements professionnels — une collaboration pourrait valoriser significativement votre offre.",
        "professional": "Je n'ai pas trouvé de mention d'un traiteur ou service de restauration sur le site de {name} — pour vos réunions et événements, c'est un confort important pour vos équipes et invités.",
        "direct":       "{name} ne semble pas avoir de solution restauration pour ses événements. Vos réunions méritent mieux que des sandwichs commandés en urgence.",
        "casual":       "Pas de traiteur mentionné sur votre site pour vos événements ! Je m'occupe de tout — plateaux repas, buffets, cocktails.",
    },
    "paysagisme": {
        "formal":       "Votre site ne présente pas d'espaces verts aménagés, alors que la qualité des abords d'un établissement contribue directement à la première impression de vos clients et visiteurs.",
        "professional": "Je n'ai pas trouvé de mention d'espaces verts ou de paysagiste pour {name} — une terrasse ou un jardin bien entretenu valorise immédiatement votre image.",
        "direct":       "{name} ne semble pas avoir de solution paysagère. Vos espaces verts sont la première chose que voient vos clients.",
        "casual":       "Pas d'espaces verts mentionnés sur votre site ! Un peu de verdure autour de votre établissement, ça change vraiment l'atmosphère et attire les clients.",
    },
    "architecture_interieure": {
        "formal":       "En consultant le site de {name}, j'ai pensé qu'un réaménagement de vos espaces commerciaux pourrait renforcer l'expérience client et optimiser votre chiffre d'affaires au m².",
        "professional": "Je n'ai pas trouvé de mention d'un projet de décoration ou d'agencement récent pour {name} — un espace bien pensé augmente le panier moyen et la durée de visite de vos clients.",
        "direct":       "L'espace de {name} pourrait être mieux agencé pour maximiser l'expérience client et vos ventes — j'ai quelques idées concrètes à vous proposer.",
        "casual":       "En regardant votre site, je me suis dit que votre espace mériterait peut-être un coup de fraîcheur ! Un bon aménagement, ça booste vraiment les ventes.",
    },
    "impression_signaletique": {
        "formal":       "En regardant la présence de {name}, j'ai pensé que vos supports de communication print pourraient être optimisés pour mieux attirer et informer vos clients.",
        "professional": "Je n'ai pas trouvé mention de supports print récents pour {name} — flyers, enseignes et signalétique bien conçus peuvent augmenter significativement votre trafic en point de vente.",
        "direct":       "{name} pourrait bénéficier de supports print plus percutants. Une bonne enseigne et des flyers bien faits, ça fait la différence en local.",
        "casual":       "Vous avez pensé à mettre à jour vos supports print ? Flyers, enseignes, PLV — ça peut vraiment booster votre visibilité locale !",
    },
    "fleuriste": {
        "formal":       "En consultant le site de {name}, je n'ai pas trouvé de partenariat floral — une collaboration pourrait sublimer vos événements et offrir une expérience mémorable à vos invités.",
        "professional": "Je n'ai pas trouvé de mention d'un fleuriste ou décorateur floral pour {name} — pour vos événements, une décoration florale soignée laisse une impression durable.",
        "direct":       "{name} ne semble pas avoir de fleuriste pour ses événements. Une belle décoration florale, ça se souvient longtemps.",
        "casual":       "Pas de fleuriste mentionné pour vos événements ! Des fleurs fraîches, ça change toute l'ambiance — je serais ravi de collaborer.",
    },
    "animation_enfants": {
        "formal":       "Votre site ne fait pas mention d'animations ou d'espace dédié aux enfants, alors que c'est un levier direct de fidélisation et d'augmentation du panier moyen des familles.",
        "professional": "Je n'ai pas trouvé d'animations enfants sur le site de {name} — les établissements qui proposent des activités pour enfants constatent en moyenne une hausse de 40 % du panier moyen des familles.",
        "direct":       "{name} n'a pas d'animations enfants. Les familles restent plus longtemps et dépensent plus quand les enfants sont occupés.",
        "casual":       "Pas d'espace ou d'animations pour les enfants sur votre site ! C'est vraiment ce qui fidélise les familles et les fait revenir.",
    },
    "coursier": {
        "formal":       "En analysant votre présence en ligne, je n'ai pas trouvé de solution de course express ou de livraison rapide associée à {name}.",
        "professional": "Votre site ne mentionne pas de service de course express — pour des envois sensibles ou urgents, un coursier dédié est souvent plus fiable et discret qu'un prestataire généraliste.",
        "direct":       "{name} n'a pas l'air d'avoir de solution course express. Pour des envois sensibles ou urgents, un prestataire dédié fait la différence.",
        "casual":       "Je n'ai pas vu de service de livraison express pour votre activité — si vous avez des courses urgentes ou discrètes à faire, c'est mon domaine !",
    },
    "cours_particuliers": {
        "formal":       "Votre établissement ne semble pas proposer de dispositif de soutien scolaire ou de cours particuliers, alors qu'une telle offre constituerait un avantage différenciant pour vos familles.",
        "professional": "Je n'ai pas trouvé de mention de cours particuliers associés à {name} — un partenariat enrichirait votre offre et apporterait une vraie valeur ajoutée aux familles que vous accompagnez.",
        "direct":       "{name} ne propose pas de soutien scolaire. C'est pourtant ce que beaucoup de familles recherchent en premier.",
        "casual":       "Pas de cours particuliers sur votre site ! Beaucoup de familles en cherchent — une collaboration serait naturelle.",
    },
    "candidature_spontanee": {
        "formal":       "Je me permets de vous contacter car {name} correspond exactement au type de structure dans laquelle je souhaiterais contribuer et évoluer.",
        "professional": "En consultant le site de {name}, j'ai été convaincu que mon profil et mes compétences pourraient apporter une vraie valeur ajoutée à votre équipe.",
        "direct":       "J'ai regardé ce que fait {name} — et je suis convaincu que mon profil peut apporter quelque chose de concret à votre équipe.",
        "casual":       "J'ai bien regardé ce que vous faites chez {name} et je me suis dit que mon profil pourrait vraiment matcher avec ce dont vous avez besoin !",
    },
    "traduction": {
        "formal":       "Votre site est exclusivement disponible en français, ce qui restreint votre accessibilité aux clients et partenaires internationaux.",
        "professional": "Votre site n'est disponible qu'en français — si vous avez une clientèle ou des partenaires internationaux, une version traduite peut ouvrir rapidement de nouveaux marchés.",
        "direct":       "{name} n'a pas de site en anglais. Vos prospects internationaux ne peuvent pas vous comprendre — vous manquez des opportunités.",
        "casual":       "Votre site n'est qu'en français ! Si vous avez des clients ou partenaires étrangers, une traduction peut vraiment changer la donne.",
    },
}

# Intro neutre pour les services non-web (sante / terrain / special / candidature)
_SERVICE_INTRO = {
    "formal":       "Je me permets de vous contacter au sujet d'une proposition qui pourrait intéresser {name}.",
    "professional": "Je prends contact avec vous car j'ai pensé à une collaboration qui pourrait bénéficier directement à {name}.",
    "direct":       "Je voulais vous parler d'une opportunité concrète pour {name}.",
    "casual":       "Je voulais vous écrire directement parce que j'ai une idée qui pourrait vraiment intéresser {name} !",
}

INTRO_TEMPLATES = {
    "formal": (
        "Je me permets de vous contacter suite à l'analyse de la présence en ligne de {name}. "
        "Voici les principaux points que j'ai identifiés :"
    ),
    "professional": (
        "En cherchant {name} en ligne ce matin, j'ai repéré quelques points "
        "qui méritent une attention rapide :"
    ),
    "direct": "Voilà ce que j'ai trouvé sur {name} en deux minutes :",
    "casual": "J'ai jeté un œil à votre présence en ligne — voilà ce que j'ai vu :",
}

SIGN_OFF = {
    "formal":       "Dans l'attente de votre retour, je reste à votre disposition.\n\nCordialement,",
    "professional": "N'hésitez pas si vous avez la moindre question.\n\nBien à vous,",
    "direct":       "Au plaisir d'échanger,",
    "casual":       "À bientôt j'espère !",
}

# Élément tangible de réassurance (framework : signal → enjeu → risque → RASSURE).
# Placé avant le CTA pour lever le risque perçu d'un échange commercial.
REASSURANCE = {
    "formal":       "Et pour être transparent : si j'estime ne pas pouvoir vous être utile, je vous le dirai clairement — sans discours commercial.",
    "professional": "Et rassurez-vous : si je vois que ça ne vous apporterait rien, je vous le dis franchement — pas de blabla commercial.",
    "direct":       "Et si je ne peux rien pour vous, je vous le dis direct — zéro perte de temps.",
    "casual":       "Et promis, si je vois que ça ne vaut pas le coup pour vous, je vous le dis franchement !",
}


# ---------------------------------------------------------------------------
# Génération dynamique selon audit + style
# ---------------------------------------------------------------------------

_NON_WEB_CATEGORIES = {"sante", "terrain", "special"}


def build_dynamic_email(
    prospect: Prospect,
    style: EmailStyle,
    your_name: str,
    your_title: str,
    your_offer: str,
    service_id: str = "",
    service_category: str = "web_digital",
    target_sector: str = "",
) -> str:
    """
    Génère un email personnalisé selon les résultats de l'audit ET le style choisi.
    Adapte le copy au profil de service (catégorie + service_id).
    """
    intonation = style.intonation
    length = style.length
    cms = prospect.cms or "cet outil"

    # --- Salutation ---
    salutation_map = {
        "formal":     "Madame, Monsieur,",
        "neutral":    "Bonjour,",
        "first_name": "Bonjour,",
    }
    salutation = salutation_map.get(style.salutation, "Bonjour,")

    # --- Sélection du dictionnaire de copy principal ---
    if service_category == "creatif":
        primary_copy = CREATIVE_ISSUE_COPY
    elif service_category == "conseil_b2b":
        primary_copy = CONSEIL_ISSUE_COPY
    else:
        primary_copy = ISSUE_COPY

    keys = list(prospect.issue_keys) if prospect.issue_keys else []
    n_issues = {"short": 1, "medium": 2, "long": 3}.get(length, 2)
    issue_paragraphs: list = []

    # --- Priorité 1 : no_service_mention (services non-web + conseil_b2b) ---
    if "no_service_mention" in keys:
        per_service = NO_SERVICE_MENTION_COPY.get(service_id, {})
        if per_service:
            sentence = per_service.get(intonation, per_service.get("professional", ""))
        else:
            # Fallback générique conseil_b2b si pas de copy spécifique
            fallback = CONSEIL_ISSUE_COPY.get("no_service_mention", {})
            sentence = fallback.get(intonation, fallback.get("professional", ""))
        if sentence:
            sentence = sentence.format(name=prospect.name, cms=cms)
            issue_paragraphs.append(sentence)
        keys = [k for k in keys if k != "no_service_mention"]

    # --- Priorité 2 : french_only spécial traduction (évite doublon avec no_service_mention) ---
    if "french_only" in keys and service_id == "traduction" and not issue_paragraphs:
        per_service = NO_SERVICE_MENTION_COPY.get("traduction", {})
        sentence = per_service.get(intonation, per_service.get("professional", ""))
        if sentence:
            sentence = sentence.format(name=prospect.name, cms=cms)
            issue_paragraphs.append(sentence)
        keys = [k for k in keys if k not in ("french_only", "no_service_mention")]

    # --- Remplissage des autres slots ---
    for key in keys:
        if len(issue_paragraphs) >= n_issues:
            break
        # Essai dans le copy primaire, fallback sur ISSUE_COPY
        copy_dict = primary_copy if key in primary_copy else ISSUE_COPY
        if key in copy_dict:
            sentence = copy_dict[key].get(intonation, copy_dict[key].get("professional", ""))
            if sentence:
                sentence = sentence.format(name=prospect.name, cms=cms)
                issue_paragraphs.append(sentence)

    # --- Fallback : message générique si aucun problème trouvé ---
    if not issue_paragraphs:
        if service_category in _NON_WEB_CATEGORIES and service_id in NO_SERVICE_MENTION_COPY:
            per_service = NO_SERVICE_MENTION_COPY[service_id]
            sentence = per_service.get(intonation, per_service.get("professional", ""))
            issue_paragraphs = [sentence.format(name=prospect.name, cms=cms)]
        else:
            issue_paragraphs = [
                f"En analysant la présence en ligne de {prospect.name}, j'ai identifié "
                "des opportunités d'amélioration qui pourraient booster votre visibilité."
            ]

    # --- Intro ---
    if length == "short":
        intro = ""
    elif service_category in _NON_WEB_CATEGORIES:
        intro = ""  # le copy no_service_mention est auto-suffisant comme intro
    else:
        intro_template = INTRO_TEMPLATES.get(intonation, INTRO_TEMPLATES["professional"])
        intro = intro_template.format(name=prospect.name)

    # --- Proposition de valeur + CTA ---
    # Pour le dev web : le bot formule UNE offre concrète adaptée à l'état du
    # site et au secteur (cf. offers.py). Sinon, value_prop + CTA génériques.
    if service_category == "web_digital":
        from offers import select_offer
        offer = select_offer(prospect, sector=target_sector)
        value_prop = offer.pitch
        cta = offer.cta
    else:
        value_prop = f"{your_offer}." if length != "short" and your_offer else ""
        cta = EMAIL_STYLE_LABELS["cta"].get(style.cta, EMAIL_STYLE_LABELS["cta"]["audit"])

    # --- Signature ---
    sign_off = SIGN_OFF.get(intonation, SIGN_OFF["professional"])
    signature = f"{sign_off}\n{your_name}"
    if your_title:
        signature += f"\n{your_title}"

    # --- Assemblage ---
    parts = [salutation, ""]
    if intro:
        parts.append(intro)
        parts.append("")
    parts.extend(issue_paragraphs)
    parts.append("")
    if value_prop:
        parts.append(value_prop)
        parts.append("")
    parts.append(cta)
    # Élément de réassurance tangible (sauf format court, qu'on garde ramassé)
    if length != "short":
        parts.append("")
        parts.append(REASSURANCE.get(intonation, REASSURANCE["professional"]))
    parts.append("")
    parts.append(signature)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# A/B test helpers
# ---------------------------------------------------------------------------

def get_template_variant(place_id: str) -> str:
    """Assigne le variant A ou B de façon déterministe via le hash du place_id (50/50)."""
    return "A" if int(hashlib.md5(place_id.encode()).hexdigest(), 16) % 2 == 0 else "B"


# ---------------------------------------------------------------------------
# Helpers grammaticaux
# ---------------------------------------------------------------------------

def _pluriel(n: int, mot: str, mot_pluriel: str = "") -> str:
    if n <= 1:
        return mot
    return mot_pluriel if mot_pluriel else mot + "s"


# ---------------------------------------------------------------------------
# Sujets dynamiques
# ---------------------------------------------------------------------------

def _build_subject(prospect: Prospect, n_issues: int) -> str:
    name = prospect.name

    if not prospect.has_website():
        return f"{name} — votre présence en ligne peut tout changer"

    if n_issues == 0:
        return f"{name} — une idée pour aller encore plus loin"

    if n_issues == 1:
        issue_short = prospect.issues[0].split("→")[0].strip().lower()
        return f"{name} — un point à corriger sur votre site"

    if n_issues <= 3:
        return f"{name} — {n_issues} {_pluriel(n_issues, 'point')} d'amélioration identifiés sur votre site"

    return f"{name} — audit rapide de votre présence en ligne"


# ---------------------------------------------------------------------------
# Accroche (1er paragraphe)
# ---------------------------------------------------------------------------

def _build_hook(prospect: Prospect) -> str:
    custom_hook = os.getenv("EMAIL_HOOK", "").strip()
    if custom_hook:
        return custom_hook.format(name=prospect.name)

    if not prospect.has_website():
        return (
            f"En cherchant {prospect.name} sur Google, je n'ai pas trouvé de site web associé à votre établissement. "
            f"C'est souvent la première chose que vos clients potentiels vérifient avant de vous contacter — "
            f"et sans site, vous laissez cette opportunité à vos concurrents."
        )

    if any("inaccessible" in i for i in prospect.issues):
        return (
            f"En visitant le site de {prospect.name} aujourd'hui, j'ai constaté qu'il était inaccessible. "
            f"Chaque heure d'indisponibilité, c'est un client potentiel qui repart chez un concurrent."
        )

    if any("HTTPS" in i for i in prospect.issues):
        return (
            f"En consultant le site de {prospect.name}, j'ai remarqué qu'il fonctionne encore en HTTP "
            f"(connexion non sécurisée). Google pénalise activement ces sites dans ses résultats de recherche, "
            f"et les navigateurs affichent une alerte à vos visiteurs."
        )

    if any("viewport" in i.lower() or "mobile" in i.lower() or "responsive" in i.lower() for i in prospect.issues):
        return (
            f"En visitant le site de {prospect.name} depuis un smartphone, j'ai constaté qu'il n'est pas adapté "
            f"à la navigation mobile. Or, plus de 60 % de vos visiteurs naviguent sur téléphone — "
            f"c'est autant de clients potentiels qui repartent."
        )

    if any("formulaire" in i.lower() for i in prospect.issues):
        return (
            f"En parcourant le site de {prospect.name}, j'ai remarqué l'absence de formulaire de contact visible. "
            f"Des visiteurs intéressés ne savent pas comment vous joindre facilement — "
            f"et une partie repart sans laisser ses coordonnées."
        )

    cms = getattr(prospect, "cms", None)
    free_builders = {"Wix", "Jimdo", "Weebly", "Webnode"}
    if cms and cms in free_builders and any("gratuit" in i.lower() or "outil" in i.lower() or "builder" in i.lower() for i in prospect.issues):
        return (
            f"En visitant le site de {prospect.name}, j'ai constaté qu'il est construit avec {cms}. "
            f"Ces outils sont pratiques au départ, mais ils limitent sérieusement votre référencement naturel "
            f"et votre image professionnelle — et Google le sait."
        )

    if cms in {"WordPress", "Joomla", "Drupal", "PrestaShop"} and prospect.issues:
        return (
            f"En analysant le site de {prospect.name} (construit sous {cms}), "
            f"j'ai identifié {len(prospect.issues)} point(s) qui pénalisent votre visibilité "
            f"et votre taux de conversion."
        )

    if any("tracking" in i.lower() or "analytics" in i.lower() for i in prospect.issues):
        return (
            f"En analysant le site de {prospect.name}, j'ai constaté l'absence d'outils de mesure "
            f"(Google Analytics, etc.). Sans données, impossible de savoir d'où viennent vos visiteurs "
            f"ni quelles actions ils réalisent — tout investissement marketing devient aveugle."
        )

    # Accroche générique si aucun cas précis
    n = len(prospect.issues)
    return (
        f"En analysant la présence en ligne de {prospect.name}, "
        f"j'ai identifié {n} {_pluriel(n, 'point')} qui {_pluriel(n, 'freine', 'freinent')} "
        f"votre visibilité et vos conversions."
    )


# ---------------------------------------------------------------------------
# Corps du mail — bloc problèmes
# ---------------------------------------------------------------------------

def _build_issues_block(prospect: Prospect) -> str:
    issues = prospect.issues
    n = len(issues)

    if n == 0:
        return ""

    if n == 1:
        short = issues[0].split("→")[0].strip()
        detail = issues[0].split("→")[1].strip() if "→" in issues[0] else ""
        block = f"Le point que j'ai noté :\n  • {short}"
        if detail:
            block += f" — {detail}"
        return block

    top = issues[:3]
    label = f"Les {_pluriel(n, 'point principal', 'points principaux')} que j'ai notés :"
    lines = [label]
    for issue in top:
        short = issue.split("→")[0].strip()
        lines.append(f"  • {short}")
    if n > 3:
        lines.append(f"  • … et {n - 3} autre{_pluriel(n - 3, '')} point{_pluriel(n - 3, '')} détecté{_pluriel(n - 3, '')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CTA (appel à l'action)
# ---------------------------------------------------------------------------

def _build_cta(prospect: Prospect) -> str:
    offer = os.getenv("YOUR_OFFER", "").strip()
    n = len(prospect.issues)

    if not prospect.has_website():
        base = (
            "Je serais ravi de vous montrer en 15 minutes ce qu'un site simple, rapide et bien référencé "
            "peut apporter concrètement à votre activité — sans engagement."
        )
    elif n >= 4:
        base = (
            "Je vous propose un audit complet de votre site, gratuit et sans engagement. "
            "Vous repartez avec une feuille de route claire des actions prioritaires à mettre en place."
        )
    elif n >= 2:
        base = (
            "Je serais heureux de vous partager un retour détaillé (gratuit, sans engagement) "
            "avec les corrections à apporter en priorité."
        )
    else:
        base = (
            "Je peux vous proposer une correction rapide de ce point "
            "— sans engagement, avec un résultat visible en quelques jours."
        )

    if offer:
        return f"{base}\n\n({offer})"
    return base


# ---------------------------------------------------------------------------
# Template B — ton court et direct, accroche chiffrée
# ---------------------------------------------------------------------------

def _draft_email_b(prospect: Prospect) -> str:
    """Variante B : email plus court, ton direct, chiffres mis en avant."""
    n = len(prospect.issues)
    cms = getattr(prospect, "cms", None)

    if not prospect.has_website():
        subject = f"{prospect.name} — je n'ai pas trouvé votre site"
        body_lines = [
            "Bonjour,",
            "",
            f"En cherchant {prospect.name} sur Google, je n'ai pas trouvé de site web.",
            "C'est souvent la première chose que vos clients vérifient avant d'appeler.",
            "",
            "Je crée des sites clairs et bien référencés en 2 semaines. Vous seriez intéressé(e) ?",
        ]
    elif any("inaccessible" in i for i in prospect.issues):
        subject = f"{prospect.name} — votre site est inaccessible"
        body_lines = [
            "Bonjour,",
            "",
            "En visitant votre site aujourd'hui, j'ai constaté qu'il était inaccessible.",
            "Chaque heure d'indisponibilité, c'est un client potentiel qui part chez un concurrent.",
            "",
            "Un appel de 15 min suffit pour faire le point. Disponible cette semaine ?",
        ]
    else:
        cms_mention = f" (sous {cms})" if cms else ""
        top = prospect.issues[0].split("→")[0].strip().lower() if prospect.issues else "votre présence en ligne"
        subject = f"{prospect.name} — un point rapide sur votre site"
        body_lines = [
            "Bonjour,",
            "",
            f"J'ai regardé le site de {prospect.name}{cms_mention} et j'ai noté {n} point(s) qui freinent votre visibilité :",
            f"→ {top}",
        ]
        if n > 1:
            second = prospect.issues[1].split("→")[0].strip().lower()
            body_lines.append(f"→ {second}")
        body_lines += [
            "",
            "Je peux vous montrer en 15 minutes comment corriger ça — sans engagement, sans jargon.",
            "Dispo cette semaine ?",
        ]

    signature_parts = [config.your_name, config.your_title]
    if config.your_email:
        signature_parts.append(config.your_email)
    signature = "\n".join(filter(None, signature_parts))

    body = "\n".join(body_lines)
    return f"OBJET : {subject}\n\n{body}\n\n{signature}".strip()


# ---------------------------------------------------------------------------
# Construction finale — dispatche vers A ou B
# ---------------------------------------------------------------------------

def _draft_email_a(prospect: Prospect) -> str:
    """Template A (original) — accroche narrative, argumentée."""
    n_issues = len(prospect.issues)
    subject = _build_subject(prospect, n_issues)
    hook = _build_hook(prospect)
    issues_block = _build_issues_block(prospect)
    cta = _build_cta(prospect)

    signature_parts = [config.your_name, config.your_title]
    if config.your_website:
        signature_parts.append(config.your_website)
    if config.your_email:
        signature_parts.append(config.your_email)
    signature = "\n".join(filter(None, signature_parts))

    parts = [f"OBJET : {subject}", "", "Bonjour,", "", hook]
    if issues_block:
        parts += ["", issues_block]
    parts += ["", cta, ""]
    parts += [
        "15 minutes suffisent pour faire le point — et si je ne peux rien pour vous, je vous le dirai clairement.",
        "",
        "Vous seriez disponible cette semaine ?",
        "",
        "Bonne journée,",
        "",
        signature,
    ]
    return "\n".join(parts).strip()


def draft_email(
    prospect: Prospect,
    style: "EmailStyle | None" = None,
    service_id: str = "",
    service_category: str = "web_digital",
    target_sector: str = "",
) -> str:
    """Dispatche vers le template A ou B selon le hash du place_id (test A/B 50/50).
    Si `style` est fourni, utilise build_dynamic_email adapté au profil de service."""
    if style is not None:
        return build_dynamic_email(
            prospect,
            style,
            your_name=config.your_name,
            your_title=config.your_title,
            your_offer=os.getenv("YOUR_OFFER", "").strip(),
            service_id=service_id,
            service_category=service_category,
            target_sector=target_sector,
        )
    variant = get_template_variant(prospect.place_id)
    return _draft_email_b(prospect) if variant == "B" else _draft_email_a(prospect)


def enrich_with_email(prospect: Prospect) -> Prospect:
    prospect.email_draft = draft_email(prospect)
    variant = get_template_variant(prospect.place_id)
    logger.debug("  ✉️  Brouillon [template %s] généré pour %s.", variant, prospect.name)
    return prospect


# ---------------------------------------------------------------------------
# Email de relance
# ---------------------------------------------------------------------------

# Nombre maximal de relances dans la séquence (après le 1er contact).
MAX_FOLLOWUPS = 4


def _followup_signature() -> str:
    parts = [config.your_name, config.your_title]
    if config.your_email:
        parts.append(config.your_email)
    return "\n".join(filter(None, parts))


def draft_followup_email(prospect: Prospect, step: int = 1) -> str:
    """
    Génère l'email de relance n°`step` (1 à 4) d'une séquence.

    Chaque relance a un ANGLE distinct (58% des réponses arrivent au 1er email,
    42% sur les relances) et adopte la logique « donner avant de recevoir » :
    on propose d'ENVOYER de la valeur plutôt que de demander un créneau.

      1. Rappel doux + offre d'envoyer du concret
      2. Nouvel angle — le résultat/bénéfice, comme une réponse
      3. Autre point de douleur — on relance l'intérêt sous un autre angle
      4. Rupture — dernier message, on referme proprement la porte (mais ouverte)
    """
    step = max(1, min(step, MAX_FOLLOWUPS))
    name = prospect.name
    signature = _followup_signature()

    if step == 1:
        subject = f"{name} — suite à mon message"
        body = [
            "Bonjour,",
            "",
            "Je me permets un petit retour sur mon message de la semaine dernière — "
            "il a pu passer inaperçu, c'est le genre de choses qui arrive vite.",
            "",
            "Pour aller droit au but : je peux vous envoyer 2-3 points concrets et "
            "priorisés à corriger sur votre présence en ligne. Vous en faites ce que "
            "vous voulez, même sans travailler avec moi.",
            "",
            "Ça vous intéresse que je vous les envoie ?",
        ]
    elif step == 2:
        subject = f"{name} — une idée concrète pour vous"
        body = [
            "Bonjour,",
            "",
            "Je reviens vers vous sous un autre angle. La plupart des établissements "
            "que j'accompagne ne cherchent pas « un site » — ils cherchent plus de "
            "demandes entrantes sans y passer leurs soirées.",
            "",
            "Si vous me dites oui, je vous prépare un exemple rapide de ce que ça "
            "pourrait donner pour vous — concret, pas un discours.",
            "",
            "Je vous l'envoie ?",
        ]
    elif step == 3:
        subject = f"{name} — un autre point que j'ai remarqué"
        body = [
            "Bonjour,",
            "",
            "Un dernier angle avant de vous laisser tranquille : au-delà du point "
            "que je vous signalais, il y a souvent un manque à gagner invisible — "
            "des visiteurs intéressés qui repartent sans laisser de trace.",
            "",
            "Je peux vous envoyer un mini-diagnostic écrit (5 min de lecture) qui "
            "pointe où ça fuit. Gratuit, sans rendez-vous à caler.",
            "",
            "Je vous l'envoie ?",
        ]
    else:  # step == 4 — rupture
        subject = f"{name} — je referme le dossier"
        body = [
            "Bonjour,",
            "",
            "Promis, c'est mon dernier message — je ne veux pas encombrer votre boîte "
            "mail. Sans retour de votre part, j'en conclus que ce n'est pas le moment, "
            "et c'est parfaitement OK.",
            "",
            "Si un jour vous voulez transformer votre site en source de clients, "
            "ma porte reste ouverte : répondez simplement à ce mail, même dans six mois.",
            "",
            "Je vous souhaite une belle continuation.",
        ]

    parts = [f"OBJET : {subject}", ""] + body + ["", "Bonne journée,", "", signature]
    return "\n".join(parts).strip()


def enrich_with_followup(prospect: Prospect, step: int = 1) -> Prospect:
    """Remplace le brouillon existant par l'email de relance n°`step`."""
    prospect.email_draft = draft_followup_email(prospect, step=step)
    logger.debug("  🔄 Relance %d/%d générée pour %s.", step, MAX_FOLLOWUPS, prospect.name)
    return prospect
