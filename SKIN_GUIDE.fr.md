# Guide de création de skins 🎨

Ce guide explique comment créer un skin personnalisé pour Prinaka.

## Structure des dossiers

Un skin est un dossier placé dans `assets/sprites/` contenant 7 sous-dossiers d'animations :

```
assets/sprites/
└── mon_skin/
    ├── idle/        # au repos
    ├── walk/        # marche
    ├── drag/        # en train d'être glissé
    ├── fall/        # chute / saut
    ├── inspect/     # regarde quelque chose
    ├── hype/        # content / excité
    └── fail/        # échec / punition
```

## Format des sprites

- **Format** : `.png` avec fond transparent
- **Nommage** : `1.png`, `2.png`, `3.png`... (chiffres entiers uniquement)
- **Taille recommandée** : 165x165 px (peut varier, voir ci-dessous)

## Nombre de frames recommandé

| Animation | Frames minimum |
|-----------|----------------|
| idle      | 4              |
| walk      | 4              |
| drag      | 2              |
| fall      | 2              |
| inspect   | 4              |
| hype      | 4              |
| fail      | 4              |

## Taille personnalisée

Si ton skin a une taille différente de 165x165, déclare-la dans `src/prinny.py` :

```python
self.skin_sizes = {
    "mon_skin": (200, 200),  # largeur, hauteur en pixels
}
```

## Sons personnalisés (optionnel)

Tu peux ajouter des sons spécifiques à ton skin dans :
```
assets/sounds/mon_skin/
```
Les fichiers doivent être au format `.wav`, nommés `1.wav`, `2.wav`...  
Si aucun son n'est trouvé pour le skin, les sons `default` sont utilisés.