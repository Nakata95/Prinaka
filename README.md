# Prinaka 🐧

An animated desktop buddy based on **Prinny** from the *Disgaea* series, built with Python and PyQt5.

## Features

- 🐧 Animated mascot that roams your desktop (multi-monitor support)
- 🎨 Multiple skins available
- 🔊 Drag sounds with adjustable volume
- 🎵 Displays currently playing media
- 🖥 System stats window (CPU, RAM, disk, network, temperature...)
- 🗑 Real-time recycle bin size
- 🖱 Click and keystroke counter
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
  - Force an animation
  - Change skin
  - Adjust volume / mute
  - Open system stats
  - Toggle media display
  - Switch language

## Creating a skin

See [SKIN_GUIDE.md](SKIN_GUIDE.md)

## Credits

Developed by [@Nakata95](https://github.com/Nakata95)  
Built with PyQt5 🐍