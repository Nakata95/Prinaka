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
- ⚠️ System alerts — persistent bubble for RAM, CPU, disk, temperature and battery, each with its own on/off switch and threshold
- 💬 Speech bubbles in English / French: random quotes and contextual reactions (greetings, late night, click/keystroke milestones, battery plugged in/out), all optional
- 🎮 Do not disturb — Prinny hides and stays silent while a full-screen app (game, video) is running
- 🧷 System tray icon to show/hide Prinny or quit
- 🚀 Optional launch at Windows startup
- 🎮 Discord Rich Presence — custom profiles with live preview, one-click switching from the right-click menu, auto-reconnect
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
  - Choose a behavior, set up dialogues, system alerts and options (startup, do not disturb)
  - Open system stats window
  - Switch language (EN / FR)
  - Credits / Quit

## System alerts

Right-click → **System alerts**. Each alert has an *Enabled* switch and a threshold:

| Alert | Triggers when | Default |
|-------|---------------|---------|
| RAM | usage ≥ 80% | on |
| CPU | usage ≥ 90% for about 30 seconds | off |
| Disk | system drive ≥ 90% full | on |
| Temperature | CPU ≥ 85°C (not available on every PC) | off |
| Battery | ≤ 20% and not charging (laptops only) | on |

A single persistent bubble lists every active alert and disappears once they are all back to normal. Prinny only reacts (sound + animation) when an alert *starts*. The bubble hides temporarily when another notification appears.

## Dialogues

Right-click → **Dialogues**: turn random quotes and contextual reactions on or off, and choose how often Prinny talks (rare / normal / frequent). Quotes are in `assets/quotes.json`, by language and category: add your own lines there.

## Do not disturb

While Windows reports a full-screen app, game or presentation, Prinny hides and shows nothing. He comes back when it ends. Turn it off in right-click → **Options**.

## Discord Rich Presence

Right-click → **Discord Rich Presence**:

- Pick a saved profile to apply it instantly (the active one is checked), or **Stop presence**
- **Manage profiles…** opens the editor: details, state, images, up to 2 buttons, elapsed timer, with a live preview
- **Restore at startup** re-applies the last active profile when Prinaka launches
- If Discord is closed, the presence starts as soon as it opens, and is re-applied if the connection drops

> The Discord Rich Presence menu is currently hidden. Set `PRESENCE_ENABLED = True` in `src/prinny.py` to bring it back.

You need a Client ID from the [Discord Developer Portal](https://discord.com/developers/applications). Profiles are stored in `assets/presences.json`.

## Project structure

```
Prinaka/
├── src/
│   ├── main.py          # Entry point
│   ├── features.py      # Quotes, reactions, alerts, do-not-disturb, tray (mixed into Prinny)
│   ├── alerts.py        # RAM / CPU / disk / temperature / battery alert rules
│   ├── reactions.py     # When Prinny comments on something
│   ├── quotes.py        # Localized quote picker
│   ├── fullscreen.py    # Full-screen / presentation detection
│   ├── tray.py          # System tray icon
│   ├── startup.py       # Launch at Windows startup
│   ├── discord_presence.py # Discord Rich Presence (connection, reconnect, profiles)
│   ├── presence_window.py  # Profile manager window + live preview
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