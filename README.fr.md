# Prinaka 🐧

Un shimeji de bureau animé basé sur le personnage **Prinny** de la série *Disgaea*, développé en Python avec PyQt5.

## Fonctionnalités

- 🐧 Mascotte animée qui se balade sur ton bureau (support multi-écrans)
- 🎨 Plusieurs skins disponibles
- 🔊 Sons au drag, volume réglable
- 🎵 Affichage de la musique en cours de lecture
- 🖥 Fenêtre de stats système (CPU, RAM, disque, réseau, température...)
- 🗑 Taille de la corbeille en temps réel
- 🖱 Compteur de clics et frappes clavier
- 💬 Bulles de dialogue aléatoires
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
  - Forcer une animation
  - Changer de skin
  - Régler le volume / muet
  - Afficher les stats système
  - Activer/désactiver l'affichage média

## Créer un skin

Voir [SKIN_GUIDE.md](SKIN_GUIDE.md)

## Crédits

Développé par [@Nakata95](https://github.com/Nakata95)  
Fait avec PyQt5 🐍