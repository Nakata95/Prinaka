# Skin Creation Guide 🎨

This guide explains how to create a custom skin for Prinaka.

## Folder Structure

A skin is a folder placed inside `assets/sprites/` containing 7 animation subfolders:

```
assets/sprites/
└── my_skin/
    ├── idle/        # standing still
    ├── walk/        # walking
    ├── drag/        # being dragged
    ├── fall/        # falling / jumping
    ├── inspect/     # looking at something
    ├── hype/        # excited / happy
    └── fail/        # failure / punishment
```

## Sprite Format

- **Format** : `.png` with transparent background
- **Naming** : `1.png`, `2.png`, `3.png`... (plain integers only)
- **Recommended size** : 165x165 px (can vary, see below)

## Recommended Frame Count

| Animation | Minimum frames |
|-----------|----------------|
| idle      | 4              |
| walk      | 4              |
| drag      | 2              |
| fall      | 2              |
| inspect   | 4              |
| hype      | 4              |
| fail      | 4              |

## Custom Size

If your skin uses a size other than 165x165, declare it in `src/prinny.py`:

```python
self.skin_sizes = {
    "my_skin": (200, 200),  # width, height in pixels
}
```

## Custom Sounds (optional)

You can add skin-specific sounds in:
```
assets/sounds/my_skin/
```
Files must be `.wav` format, named `1.wav`, `2.wav`...  
If no sounds are found for the skin, the `default` sounds are used instead.