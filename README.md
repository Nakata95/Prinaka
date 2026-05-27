# Prinaka 🐧

An animated desktop buddy based on **Prinny** from the *Disgaea* series, built with Python and PyQt5.

## Features

- 🐧 Animated mascot that roams your desktop (multi-monitor support)
- 🎨 Multiple skins available
- 🔊 Drag sounds with adjustable volume
- 🎵 Displays currently playing media (Spotify, YouTube, etc.)
- 🖥 System stats window (CPU, RAM, disk, network, temperature...)
- 🗑 Real-time recycle bin size
- 🖱 Click and keystroke counter
- ⚠️ RAM alert — persistent bubble notification when RAM exceeds 80% (toggleable)
- 💬 Random speech bubbles
- 🌐 English / French language support
- ⚙️ Settings saved between sessions

## Installation

```bash
git clone https://github.com/Nakata95/Prinaka.git
cd Prinaka
pip install -r requirements.txt
python src/main.py
```

> ⚠️ **Windows only** for now (requires `wmi`, `pywin32`, `winsdk`)

## Usage

- **Left click + drag** : move Prinny around
- **Right click** : open the menu
  - Force an animation (idle, walk, inspect, hype, punish, free)
  - Change skin
  - Adjust volume / mute
  - Toggle current media display
  - Toggle RAM alert notification
  - Open system stats window
  - Switch language (EN / FR)
  - Credits / Quit

## RAM Alert

When RAM usage reaches **80% or more**, Prinaka displays a persistent bubble above Prinny's head showing the current usage percentage. The bubble updates in real time and disappears automatically when RAM drops back below the threshold.

- If another notification appears (media, quote), the alert bubble hides temporarily and comes back automatically
- The alert can be enabled or disabled from the right-click menu
- Once triggered, the alert won't fire again until RAM drops below 80% and rises again

## Project structure

```
Prinaka/
├── src/
│   ├── main.py          # Entry point
│   ├── prinny.py        # Main widget (animation, physics, menu)
│   ├── info_window.py   # System stats window
│   ├── speech_bubble.py # Speech bubble widget
│   ├── config.py        # Settings manager (QSettings)
│   ├── media.py         # Windows media detection
│   ├── system_stats.py  # CPU, RAM, disk, network, recycle bin
│   ├── utils.py         # Shared utilities + localisation
│   └── listeners.py     # Mouse/keyboard counters
├── assets/
│   ├── sprites/         # Skin folders with animation frames
│   ├── sounds/          # WAV files per skin
│   ├── locales/         # en.json / fr.json
│   └── quotes.json      # Random speech bubble quotes
├── README.md
├── README.fr.md
├── SKIN_GUIDE.md
├── SKIN_GUIDE.fr.md
└── requirements.txt
```

## Creating a skin

See [SKIN_GUIDE.md](SKIN_GUIDE.md)

## Credits

Developed by [@Nakata95](https://github.com/Nakata95)  
Built with PyQt5 🐍