# Prinaka 🐧

Une mascotte de bureau animée basée sur **Prinny** de la série *Disgaea*, développée en Python avec PyQt5.

## Fonctionnalités

- 🐧 Mascotte animée qui se balade sur ton bureau (support multi-écrans)
- 🎨 Plusieurs skins disponibles
- 📏 Taille réglable (75 % à 200 %), mémorisée entre les sessions
- 🔊 Sons au drag, volume réglable
- 🎵 Suit Spotify (ou n'importe quelle appli média) et affiche le titre en cours dans une bulle
- ▶️ Mini lecteur — pochette, titre, barre de progression, précédent / lecture-pause / suivant et déplacement dans le morceau, pour Spotify
- 🖥 Fenêtre de stats système (CPU, RAM, disque, réseau, température...)
- 🗑 Taille de la corbeille en temps réel
- 🖱 Compteur de clics et frappes clavier
- ⚠️ Alertes système — bulle persistante pour la RAM, le CPU, le disque, la température et la batterie, chacune avec son interrupteur et son seuil
- 💬 Bulles de dialogue en français / anglais : citations aléatoires et réactions contextuelles (salutations, nuit tardive, paliers de clics/frappes, batterie branchée/débranchée), le tout désactivable
- 📡 Moniteur réseau compact (latence, envoi, réception) à garder au-dessus d'un jeu en ligne ou d'un appel
- 🎮 Ne pas déranger — Prinny se cache et reste silencieux pendant une appli en plein écran (jeu, vidéo)
- 🛡 Relais Windows Defender — alerte quand Defender trouve une menace, et une entrée « Analyser un fichier » (rien ne quitte ton PC)
- 💬 Discussion avec Prinny grâce à une IA locale (Ollama) — il comprend tes ordres et agit : bouger, s'arrêter, sauter, s'exprimer, aller à un endroit de l'écran, skin, taille, volume, musique, état de l'ordinateur, et il peut chercher sur le web pour répondre à tes questions. La conversation reste sur ton PC
- 🧷 Icône dans la barre système pour afficher/masquer Prinny ou quitter
- 🚀 Lancement optionnel au démarrage de Windows
- 🎮 Discord Rich Presence — profils personnalisés avec aperçu en direct, changement en un clic depuis le menu clic droit, reconnexion automatique
- 🌐 Support anglais / français
- ⚙️ Paramètres sauvegardés entre les sessions

## Installation

```bash
git clone https://github.com/Nakata95/Prinaka.git
cd Prinaka
pip install -r requirements.txt
python src/main.py
```

> ⚠️ **Windows uniquement** pour le moment (dépendances `wmi`, `pywin32`, `winsdk`)

## Utilisation

- **Clic gauche + glisser** : déplacer Prinny
- **Clic droit** : ouvrir le menu
  - Forcer une animation (immobile, marche, inspecte, hype, punition, libre)
  - Changer de skin et de taille
  - Régler le volume / muet
  - Activer/désactiver l'affichage du média en cours
  - Choisir un comportement, régler les dialogues, les alertes système et les options (démarrage, ne pas déranger)
  - Ouvrir la fenêtre de stats système
  - Changer de langue (FR / EN)
  - Crédits / Quitter

## Alertes système

Clic droit → **Alertes système**. Chaque alerte a un interrupteur *Activée* et un seuil :

| Alerte | Se déclenche quand | Par défaut |
|--------|--------------------|------------|
| RAM | utilisation ≥ 80% | activée |
| CPU | utilisation ≥ 90% pendant environ 30 secondes | désactivée |
| Disque | disque système rempli à ≥ 90% | activée |
| Température | CPU ≥ 85°C (indisponible sur certains PC) | désactivée |
| Batterie | ≤ 20% et pas en charge (portables uniquement) | activée |

Une seule bulle persistante liste toutes les alertes actives et disparaît quand tout est revenu à la normale. Prinny ne réagit (son + animation) qu'au *début* d'une alerte. La bulle se cache temporairement quand une autre notification s'affiche.

## Dialogues

Clic droit → **Dialogues** : active ou désactive les citations aléatoires et les réactions contextuelles, et règle la fréquence (rare / normale / fréquente). Les citations sont dans `assets/quotes.json`, par langue et par catégorie : tu peux y ajouter tes propres phrases.

## Mini lecteur

Clic droit (ou icône de la barre système) → **Mini lecteur** : pochette, titre, artiste, barre de progression (clic ou glisser pour se déplacer dans le morceau) et boutons précédent / lecture-pause / suivant, aléatoire et répétition (un clic sur répétition passe de désactivée → tout → ce morceau → désactivée). Il pilote Spotify via les commandes média de Windows, donc il marche avec l'appli de bureau comme avec la version Store. Par défaut Prinny ne suit que Spotify (clic droit → **Spotify uniquement**) ; décoche pour suivre n'importe quelle appli média (navigateur, Lecteur Windows Media...). La fenêtre ne prend jamais le focus clavier.

## Moniteur réseau

Clic droit (ou icône de la barre système) → **Moniteur réseau** : une petite fenêtre toujours au premier plan avec ta latence en ms et les débits d'envoi / réception en direct, sans les totaux. Elle ne prend jamais le focus clavier, donc un jeu en cours le garde. Le bouton 🔓 la rend « traversante » pour les clics ; ferme-la depuis le menu ou l'icône de la barre système pour la déverrouiller. Elle fonctionne au-dessus des jeux en fenêtré ou sans bordure ; certains jeux en plein écran exclusif masquent toutes les superpositions.

La fenêtre Infos système et celle-ci s'ouvrent et se ferment avec le même bouton, même si l'une a été tirée hors de vue, et se rouvrent au milieu de l'écran quand leur position est perdue.

## Sécurité (Windows Defender)

Clic droit → **Sécurité**. Prinny ne détecte pas les virus lui-même : il lit ce que Microsoft Defender signale, en local, et le relaie.

- **Surveiller Windows Defender** (activé par défaut) : chaque minute, Prinny regarde les détections de Defender. Une menace encore présente reste dans la bulle d'alerte jusqu'à ce que Defender s'en soit occupé, et une notification système s'affiche pour que tu la voies même si Prinny est caché. Une menace déjà neutralisée donne une bulle ponctuelle. L'ancien historique est ignoré au lancement.
- **Analyser un fichier…** : choisis un fichier (un téléchargement, un document Office...) et Defender l'analyse ; Prinny dit si une menace a été trouvée.
- **Ouvrir Sécurité Windows** ouvre la fenêtre de Defender.

Il faut que Microsoft Defender soit ton antivirus actif ; avec un autre antivirus, le menu l'indique.

## Discuter avec Prinny (IA locale)

Clic droit (ou icône de la barre système) → **Discuter avec Prinny** : une fenêtre de chat où tu écris à Prinny, qui répond avec son caractère. Il comprend aussi des demandes et agit : « bouge ! », « arrête de bouger ! », « saute ! », « déchaîne-toi ! », « occupe-toi ! », « va tout à droite de l'écran », « mets le skin summer », « baisse le volume à 20 », « passe au morceau suivant », « combien de RAM j'utilise ? ». Les ordres de comportement (bouger, s'arrêter, s'exprimer, s'occuper, punition, libre) durent jusqu'au prochain, comme dans le menu **Comportement**. Un petit message gris indique chaque action réalisée.

Le modèle tourne **sur ton PC** avec [Ollama](https://ollama.com) : la conversation n'est envoyée nulle part. Seule exception, la recherche web (voir plus bas).

1. Installe Ollama (ollama.com) et lance-le.
2. Télécharge le modèle : `ollama pull qwen3:8b` (environ 5 Go ; il tient dans 8 Go de mémoire vidéo ou tourne sur le processeur, plus lentement).
3. Ouvre la discussion. Un autre modèle se règle avec la clé `ai_model`, par exemple un modèle de la même taille compatible avec les appels d'outils.

Prinny ne peut faire que ce que listent `src/ai_tools.py` : ouvrir un site ou une recherche dans ton navigateur, lancer quelques commandes inoffensives, diagnostiquer le PC, chercher sur le web, changer de comportement, courir jusqu'à un endroit de l'écran (en sautant parfois), sauter, changer de skin ou de taille, lancer une animation, régler le volume ou le son, piloter la lecture de la musique et lire l'état de l'ordinateur. Les outils ne lui sont proposés que si ton message ressemble à un ordre : une simple discussion ne déclenche jamais d'action. Il n'ouvre aucun fichier ni programme et ne modifie rien sur ton PC. Le modèle est déchargé de la mémoire après 5 minutes d'inactivité. Un petit modèle peut se tromper : l'état réel (skin, volume...) reste visible dans l'interface.

**Recherche web.** Quand tu poses une question factuelle (« c'est quoi… », « qui est… », « explique… », « tu connais… », ou une question à laquelle il ne sait pas répondre), Prinny cherche sur le web puis répond à partir des résultats, ce qu'indique un petit message gris. Seuls les mots de la recherche quittent ton PC, pas la conversation. Il interroge DuckDuckGo, sans compte ni clé ; si DuckDuckGo le bloque (ça arrive après beaucoup de recherches d'affilée), il se rabat sur Wikipedia, qui connaît les personnes, lieux, jeux et termes mais pas les sujets pointus. Il ne lit que les titres et extraits, jamais une page entière, et ne suit aucune consigne trouvée dans un résultat. Interrupteur : clic droit → **Recherche web pour l'IA** (activée par défaut). Sur l'actualité, un petit modèle peut se tromper même avec les résultats sous les yeux.

**Navigateur.** « Va sur youtube », « ouvre le site de Wikipedia », « fais une recherche sur… » ou « cherche ça sur google » ouvrent ton **navigateur par défaut** (la différence avec la recherche web ci-dessus : là, c'est toi qui lis). L'adresse ouverte s'affiche dans le chat. Seules les adresses `http(s)` avec un vrai nom de domaine sont acceptées : ni fichier, ni `javascript:`, ni paramètres Windows, ni adresse IP, ni identifiant dans l'adresse. Les recherches passent par DuckDuckGo ; change de moteur avec la clé `search_engine_url` (par exemple `https://www.google.com/search?q={q}`).

Tu peux aussi demander **un autre navigateur** (« ouvre wikipedia avec Firefox ») ou **la navigation privée** (« va sur youtube en navigation privée », « en incognito », « en InPrivate »), seuls ou ensemble. Chrome, Edge, Firefox, Brave, Opera et Vivaldi sont reconnus, à condition d'être installés ; Prinny les retrouve dans la liste des navigateurs de Windows, jamais à partir d'un chemin donné par l'IA. Chaque navigateur reçoit sa propre option privée (`--incognito`, `--inprivate`, `-private-window`, `--private`). Une demande privée n'est jamais remplacée par une fenêtre normale : si elle est impossible (navigateur absent, navigateur par défaut inconnu), Prinny le dit et n'ouvre rien.

**Spotify.** « Lance Spotify » ouvre l'appli ; « mets Get Lucky de Daft Punk » ou « joue du Mozart » la lance si besoin et joue ce que tu demandes. Prinny cherche le lien du morceau sur le web, puis le donne à Spotify comme le ferait un lien cliqué dans un navigateur. S'il ne trouve pas le morceau exact, il ouvre seulement la recherche dans Spotify et te dit d'appuyer sur lecture. Pause, suivant et précédent passent par les commandes média de Windows.

**Commandes.** Prinny ne reçoit jamais de ligne de commande libre : un petit modèle peut se tromper ou être manipulé, et rien ne garantit qu'une commande écrite par lui soit inoffensive. Il choisit dans la liste fermée de `src/safe_commands.py` : `ipconfig`, `ping`, `nslookup`, `tracert`, `netstat -n`, `arp`, `getmac`, `route`, `tasklist`, `systeminfo`, `driverquery`, `whoami`, `hostname`, `vol`, `ver`, date et heure, avec quelques options sûres (`ipconfig /all`, `netstat -ano`…). Écris `cmd ipconfig` (ou `ip config`, `lance la commande ping google.com`) dans le chat : elle part tout de suite, sans passer par le modèle ; tout le reste (`del`, `&`, `;`…) est refusé. Toutes sont en lecture seule, sans droits administrateur, lancées sans interpréteur de commandes (rien ne peut s'ajouter derrière : pas de `&`, de `|`, d'option ou de redirection), avec une limite de temps, et la commande exacte s'affiche dans le chat. Pour la cible de `ping`, `nslookup` et `tracert`, seul un nom d'hôte ou une adresse simple est accepté. Pour en autoriser une de plus, ajoute une entrée à `COMMANDS` (en lecture seule).

**Pour les développeurs.** *Projets git* (menu clic droit) : ajoute le dossier racine de tes projets et Prinny te prévient, dans une bulle, quand des modifications restent sans commit depuis 3 heures, des commits ne sont pas poussés depuis 2 heures, ou que le dépôt distant a avancé (compté depuis ton dernier fetch ; chaque problème n'est signalé qu'une fois, de nouveau seulement s'il s'aggrave ou revient après avoir été réglé : rien n'est téléchargé). Il ne lance que `git status` et `git log`, ne modifie rien, et désactive `core.fsmonitor` pour qu'un dépôt ne puisse pas démarrer un programme. Demande « où j'en suis sur Prinaka ? » dans le chat pour voir l'état. Il ne peut jamais commiter ni pousser. *Rappels* : « rappelle-moi dans 25 min de boire », « réveille-moi à 22h30 », « liste mes rappels », « annule-les » sonnent avec une bulle, un son et une notification système (visible même dans un jeu en plein écran). Les rappels ne sont gardés qu'en mémoire : ils sont perdus quand Prinaka se ferme.

**Diagnostic.** « Pourquoi mon PC est lent ? », « j'ai plus de place », « mon réseau rame », « j'ai un virus ? » : Prinny lit en lecture seule les programmes les plus gourmands, les disques, la latence réseau et les détections de Windows Defender, puis t'explique ce qu'il voit. Il ne ferme et ne supprime jamais rien lui-même.

## Ne pas déranger

Quand Windows signale une appli, un jeu ou une présentation en plein écran, Prinny se cache et n'affiche rien. Il revient à la fin. Désactivable dans clic droit → **Options**.

## Discord Rich Presence

Clic droit → **Discord Rich Presence** :

- Choisis un profil enregistré pour l'appliquer instantanément (le profil actif est coché), ou **Arrêter la présence**
- **Gérer les profils…** ouvre l'éditeur : détails, état, images, jusqu'à 2 boutons, temps écoulé, avec aperçu en direct
- **Relancer au démarrage** réapplique le dernier profil actif au lancement de Prinaka
- Si Discord est fermé, la présence démarre dès son ouverture, et se réapplique si la connexion saute

> Le menu Discord Rich Presence est actuellement masqué. Mets `PRESENCE_ENABLED = True` dans `src/prinny.py` pour le réafficher.

Il faut un Client ID depuis le [Portail Développeur Discord](https://discord.com/developers/applications). Les profils sont stockés dans `assets/presences.json`.

## Structure du projet

```
Prinaka/
├── src/
│   ├── main.py          # Point d'entrée
│   ├── features.py      # Citations, réactions, alertes, ne pas déranger, tray (mixin de Prinny)
│   ├── alerts.py        # Règles d'alerte RAM / CPU / disque / température / batterie
│   ├── reactions.py     # Quand Prinny commente quelque chose
│   ├── quotes.py        # Sélection des citations par langue
│   ├── defender.py      # Relais Windows Defender (détections, analyse de fichier)
│   ├── ai.py            # IA locale : dialogue avec Ollama et appels d'outils
│   ├── ai_tools.py      # Les actions que l'IA a le droit de faire
│   ├── websearch.py     # Recherche web de l'IA (DuckDuckGo, secours Wikipedia)
│   ├── safe_commands.py # Les commandes en lecture seule que l'IA peut lancer
│   ├── browsers.py      # Ouvrir un site dans un navigateur, éventuellement en navigation privée
│   ├── spotify_control.py # Lancer Spotify et jouer un morceau demandé
│   ├── dev_tools.py       # Surveillance des projets git et rappels (menu, bulles)
│   ├── git_watch.py       # Lecture seule de git status et log des projets enregistrés
│   ├── reminders.py       # Minuteurs et rappels (en mémoire)
│   ├── ai_assistant.py  # Chat et actions de l'IA (mixin de Prinny)
│   ├── chat_window.py   # Fenêtre de discussion
│   ├── fullscreen.py    # Détection plein écran / présentation
│   ├── tray.py          # Icône de la barre système
│   ├── menu_style.py    # Style commun des menus contextuels
│   ├── player_window.py # Mini lecteur média
│   ├── network_window.py # Superposition réseau compacte
│   ├── floating.py      # Base des fenêtres flottantes (déplacement, position, récupération)
│   ├── stat_widgets.py  # Jauges et graphiques partagés par les fenêtres d'infos
│   ├── poller.py        # Thread de lecture des mesures lentes
│   ├── startup.py       # Lancement au démarrage de Windows
│   ├── discord_presence.py # Rich Presence Discord (connexion, reconnexion, profils)
│   ├── presence_window.py  # Fenêtre de gestion des profils + aperçu
│   ├── prinny.py        # Widget principal (animation, physique, menu)
│   ├── info_window.py   # Fenêtre de stats système
│   ├── speech_bubble.py # Widget bulle de dialogue
│   ├── config.py        # Gestionnaire de paramètres (QSettings)
│   ├── media.py         # Détection média Windows
│   ├── system_stats.py  # CPU, RAM, disque, réseau, corbeille
│   ├── utils.py         # Utilitaires partagés + localisation
│   └── listeners.py     # Compteurs souris/clavier
├── assets/
│   ├── sprites/         # Dossiers de skins avec frames d'animation
│   ├── sounds/          # Fichiers WAV par skin
│   ├── locales/         # en.json / fr.json
│   └── quotes.json      # Citations pour les bulles aléatoires
├── README.md
├── README.fr.md
├── SKIN_GUIDE.md
├── SKIN_GUIDE.fr.md
└── requirements.txt
```

## Créer un skin

Voir [SKIN_GUIDE.fr.md](SKIN_GUIDE.fr.md)

## Crédits

Développé par [@Nakata95](https://github.com/Nakata95)  
Fait avec PyQt5 🐍