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
- ⚠️ Alerte RAM — bulle de notification persistante quand la RAM dépasse 80% (activable/désactivable)
- 💬 Bulles de dialogue aléatoires
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
  - Activer/désactiver l'alerte RAM
  - Ouvrir la fenêtre de stats système
  - Changer de langue (FR / EN)
  - Crédits / Quitter

## Alerte RAM

Quand l'utilisation de la RAM atteint **80% ou plus**, Prinaka affiche une bulle persistante au-dessus de la tête de Prinny avec le pourcentage en temps réel. La bulle disparaît automatiquement quand la RAM repasse sous le seuil.

- Si une autre notification s'affiche (média, citation), la bulle d'alerte se cache temporairement puis revient automatiquement
- L'alerte peut être activée ou désactivée depuis le menu clic droit
- Une fois déclenchée, l'alerte ne se répète pas tant que la RAM n'est pas repassée sous 80%

## Structure du projet

```
Prinaka/
├── src/
│   ├── main.py          # Point d'entrée
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