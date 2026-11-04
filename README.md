# Prinaka 🐧

An animated desktop buddy based on **Prinny** from the *Disgaea* series, built with Python and PyQt5.

## Features

- 🐧 Animated mascot that roams your desktop (multi-monitor support)
- 🎨 Multiple skins available
- 📏 Adjustable size (75% to 200%), remembered between sessions
- 🔊 Drag sounds with adjustable volume
- 🎵 Follows Spotify (or any media app) and shows the current track in a bubble
- ▶️ Mini player — cover, title, progress bar, previous / play-pause / next and seek, for Spotify
- 🖥 System stats window (CPU, RAM, disk, network, temperature...)
- 🗑 Real-time recycle bin size
- 🖱 Click and keystroke counter
- ⚠️ System alerts — persistent bubble for RAM, CPU, disk, temperature and battery, each with its own on/off switch and threshold
- 💬 Speech bubbles in English / French: random quotes and contextual reactions (greetings, late night, click/keystroke milestones, battery plugged in/out), all optional
- 📡 Compact network monitor (latency, upload, download) to keep on top of an online game or a call
- 🎮 Do not disturb — Prinny hides and stays silent while a full-screen app (game, video) is running
- 🛡 Windows Defender relay — alerts when Defender finds a threat, and a "Scan a file" entry (nothing leaves your PC)
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
  - Change skin and size
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

## Mini player

Right-click (or tray icon) → **Mini player**: cover art, title, artist, a progress bar (click or drag to seek) and previous / play-pause / next, shuffle and repeat buttons (click repeat to go off → all → this track → off). It controls Spotify through Windows' media controls, so it works with the desktop app and the Store version. By default Prinny only follows Spotify (right-click → **Spotify only**); untick it to follow any media app (browser, Windows Media Player...). The window never takes the keyboard focus.

## Network monitor

Right-click (or tray icon) → **Network monitor**: a small always-on-top window with your latency in ms and live upload / download speeds, no totals. It never takes the keyboard focus, so a running game keeps it. The 🔓 button makes it click-through; close it from the menu or the tray icon to unlock it. It works over windowed and borderless games; some games in exclusive full screen hide every overlay.

The system info window and this one use the same button to open *and* close them, even if one was dragged out of sight, and reopen in the middle of the screen when their position is lost.

## Security (Windows Defender)

Right-click → **Security**. Prinny does not detect malware himself: he reads what Microsoft Defender reports, locally, and relays it.

- **Watch Windows Defender** (on by default): every minute Prinny checks Defender's detections. A threat that is still present stays in the alert bubble until Defender has dealt with it, and a system notification is shown so you see it even with Prinny hidden. A threat Defender already neutralized shows a one-off bubble. Old history is ignored at launch.
- **Scan a file…**: pick a file (a download, an Office document...) and Defender scans it; Prinny tells you whether a threat was found.
- **Open Windows Security** opens Defender's own window.

It needs Microsoft Defender to be your active antivirus; with another antivirus the menu says so.

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
│   ├── defender.py      # Windows Defender relay (detections, file scan)
│   ├── fullscreen.py    # Full-screen / presentation detection
│   ├── tray.py          # System tray icon
│   ├── menu_style.py    # Shared look of the context menus
│   ├── player_window.py # Mini media player
│   ├── network_window.py # Compact network overlay
│   ├── floating.py      # Base of the overlay windows (drag, position, recovery)
│   ├── stat_widgets.py  # Gauges and graphs shared by the info windows
│   ├── poller.py        # Background thread reading slow stats
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