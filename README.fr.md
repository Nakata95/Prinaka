# Prinaka 🐧

Une mascotte de bureau animée basée sur **Prinny** de la série *Disgaea*, développée en Python avec PyQt5.

## Fonctionnalités

- 🐧 Mascotte animée qui se balade sur ton bureau (support multi-écrans)
- 🎨 Plusieurs skins disponibles
- 🔊 Sons au drag, volume réglable
- 🎵 Affichage de la musique en cours de lecture (Spotify, YouTube, etc.)
- 🖥 Fenêtre de stats système (CPU, RAM, disque, réseau, température...)
- 🗑 Taille de la corbeille en temps réel
- 🖱 Compteur de clics et frappes clavier
- ⚠️ Alertes système — bulle persistante pour la RAM, le CPU, le disque, la température et la batterie, chacune avec son interrupteur et son seuil
- 💬 Bulles de dialogue en français / anglais : citations aléatoires et réactions contextuelles (salutations, nuit tardive, paliers de clics/frappes, batterie branchée/débranchée), le tout désactivable
- 🎮 Ne pas déranger — Prinny se cache et reste silencieux pendant une appli en plein écran (jeu, vidéo)
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
  - Changer de skin
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
│   ├── fullscreen.py    # Détection plein écran / présentation
│   ├── tray.py          # Icône de la barre système
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