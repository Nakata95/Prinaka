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
- 💬 Chat with Prinny through a local AI (Ollama) — he understands orders and acts: move, stop, jump, express himself, go to a place on the screen, skin, size, volume, music, computer status, and he can search the web to answer your questions. The conversation stays on your PC
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
  - Force an animation (idle, walk, inspect, hype, punish, grimace, shrug, attack, shocked, cry, free)
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

## Chat with Prinny (local AI)

Right-click (or tray icon) → **Chat with Prinny**: a chat window where you write to Prinny, who answers in character. He also understands requests and acts: "move!", "stop moving!", "jump!", "go wild!", "keep busy!", "go to the far right of the screen", "set the summer skin", "volume to 20", "next track", "how much RAM am I using?". Behavior orders (move, stay still, express, keep busy, punish, free) last until the next one, like the **Behavior** menu. A small grey line shows each action he performed.

The model runs **on your PC** with [Ollama](https://ollama.com): the conversation is sent nowhere. The one exception is web search (see below).

1. Install Ollama (ollama.com) and start it.
2. Download the model: `ollama pull qwen3:8b` (about 5 GB; it fits in 8 GB of video memory or runs on the CPU, more slowly).
3. Open the chat. Another model can be set with the `ai_model` key, for example one of the same size that supports tool calls.

Prinny can only do what `src/ai_tools.py` lists: open a site or a search in your browser, run a few harmless commands, diagnose the PC, search the web, change behavior, run to a place on the screen (sometimes jumping), jump, change skin or size, play an animation, set the volume or mute, control music playback and read the computer's status. The tools are only offered when your message looks like an order: plain conversation never triggers an action. He opens no file and no program and changes nothing on your PC. The model is unloaded from memory after 5 idle minutes. A small model can be wrong: the real state (skin, volume...) is always visible in the interface.

**Web search.** When you ask a factual question ("what is…", "who is…", "explain…", "do you know…", or something he cannot answer), Prinny searches the web then answers from the results, shown by a small grey line. Only the search words leave your PC, not the conversation. He queries DuckDuckGo, with no account or key; when DuckDuckGo blocks him (it can after many searches in a row) he falls back to Wikipedia, which knows people, places, games and terms but not niche topics. He only reads titles and snippets, never a whole page, and obeys no instruction found in a result. Switch: right-click → **Web search for the AI** (on by default). On current events a small model can be wrong even with the results in front of it.

**Browser.** "Go to youtube", "open the Wikipedia site", "do a search on…" or "look that up on google" open your **default browser** (unlike the web search above, here you do the reading). The address opened is shown in the chat. Only `http(s)` addresses with a real domain name are accepted: no file, no `javascript:`, no Windows settings, no IP address, no login in the address. Searches go through DuckDuckGo; change the engine with the `search_engine_url` key (for example `https://www.google.com/search?q={q}`).

You can also ask for **another browser** ("open wikipedia with Firefox") or **private browsing** ("go to youtube in private browsing", "in incognito", "in InPrivate"), alone or together. Chrome, Edge, Firefox, Brave, Opera and Vivaldi are recognised, as long as they are installed; Prinny finds them in Windows' own list of browsers, never from a path given by the AI. Each browser gets its own private option (`--incognito`, `--inprivate`, `-private-window`, `--private`). A private request is never replaced by a normal window: if it cannot be done (browser missing, default browser unknown), Prinny says so and opens nothing.

**Spotify.** "Launch Spotify" opens the app; "play Get Lucky by Daft Punk" or "play some Mozart" starts it if needed and plays what you ask for. Prinny looks the track's link up on the web, then hands it to Spotify like a link clicked in a browser would. If he cannot find the exact track, he only opens the search in Spotify and tells you to press play. Pause, next and previous go through Windows' media controls.

**Commands.** Prinny never receives a free command line: a small model can be wrong or manipulated, and nothing guarantees that a command it wrote is harmless. He picks from the closed list in `src/safe_commands.py`: `ipconfig`, `ping`, `nslookup`, `tracert`, `netstat -n`, `arp`, `getmac`, `route`, `tasklist`, `systeminfo`, `driverquery`, `whoami`, `hostname`, `vol`, `ver`, date and time, with a few safe options (`ipconfig /all`, `netstat -ano`...). Type `cmd ipconfig` (or `ip config`, `lance la commande ping google.com`) in the chat and it runs immediately, without the model; anything else (`del`, `&`, `;`...) is refused. All are read-only, need no administrator rights, and are started without a command shell (nothing can be added behind them: no `&`, `|`, option or redirection), with a time limit, and the exact command is shown in the chat. For the target of `ping`, `nslookup` and `tracert` only a plain host name or address is accepted. To allow one more, add an entry to `COMMANDS` (read-only).

**He acts out the conversation.** While he works on a message he keeps busy (the inspection animation). When he cannot do something or does not know, he shrugs; when he is clowning around he pulls a face; when he is happy he cheers. The mood is picked by a second small call to the model after the answer is on screen, then checked by the code (a shrug needs an answer that really says "I don't know" or "I can't", a grimace needs goofing off), so most answers stay calm. It never interrupts an order you gave, a walk to a destination or a jump. Now and then, rarely, he also shrugs or makes a face on his own (not with the Gentleman skin, where those poses are nearly the same as standing still).

**Things on the desktop.** Right-click menu → **Drop a fish** (or ask in the chat: "drop a fish"). The fish falls from the top of the screen and runs away from Prinny, slower than he runs, but it jumps high and often to get over him. He goes after it on his own, unless you gave him an order. If he touches it while it is on the ground, he cheers with the fish held up in his raised hand (his "Express yourself" animation), then eats it (his "Eat" animation, back turned with crumbs flying; the skins with big accessories keep their "Keep busy" animation instead). You can take the fish with the mouse: carry it, dangle it in front of Prinny (he runs after it but cannot catch a fish you hold), or throw it (it keeps the speed of your gesture). While at least one fish is on the desktop, flames burn in Prinny's eyes (not on the Summer and Kurtis skins, whose eyes are hidden or different, nor when his eyes are shut). If you keep a fish over Prinny's head for too long (6 seconds), he starts to cry until you let it go. You can throw Prinny himself the same way: drag him and let go with a fast gesture, he flies, bounces off the edges of the screen and lands. At most two fish at a time; nothing is saved.

**A dish.** Right-click menu → **Put down a dish** (or ask in the chat). A dish (a bowl of ramen or a ham on a plate, at random) drops from the top of the screen; Prinny goes to it, lifts the dish in his raised hand, then eats with it in front of him until it is empty, puts it down and it is cleared away.

**A fight.** Right-click menu → **Fight the Rabbit**, **Fight the Pumpkin** or **Fight 3 Bats** or **Fight the Wrestler** (or ask in the chat). When the Wrestler lands a blow he does not just push Prinny back: he throws him up, jumps over him, stands on him and crushes him into the ground, and the impact sends Prinny flying. The bats come in a group of three and are fragile: it is a one-against-three, with dives, dodges, a spin that cuts through them and a finale where the swarm sometimes wins. The opponent drops in and the two of them fight a staged, manga-style duel that is different every time: both strike at once and are thrown back, one dodges by jumping over the other, one is hit and sent flying, a taunt... then a finale where either of them can win, one time in two. Taking Prinny with the mouse stops the fight.

**For developers.** *Git projects* (right-click menu): add the root folder of your projects and Prinny reminds you, in a bubble, when changes stay uncommitted for 3 hours, commits stay unpushed for 2 hours, or the remote moved on (counted from your last fetch; each problem is reported once, again only if it gets worse or comes back after being solved; nothing is downloaded). It only runs `git status` and `git log`, never changes anything, and turns off `core.fsmonitor` so a repository cannot start a program. Ask "where am I on Prinaka?" in the chat to see the state. He can never commit or push. *Reminders*: "remind me in 25 min to drink", "wake me at 22:30", "list my reminders", "cancel them" ring with a bubble, a sound and a system notification (so you see it even in a full-screen game). Reminders are kept in memory only and are lost when Prinaka quits. *Ports*: "who uses port 3000?" or "port already in use" gives the program behind the port, its process number, its path and whether it is open to the network. It only looks: Prinny never closes a program.

**Diagnostic.** "Why is my PC slow?", "I'm out of space", "my network lags", "do I have a virus?": Prinny reads, read-only, the most demanding programs, the disks, the network latency and Windows Defender's detections, then explains what he sees. He never closes or deletes anything himself.

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
│   ├── ai.py            # Local AI: Ollama dialogue and tool calls
│   ├── ai_tools.py      # The actions the AI is allowed to take
│   ├── websearch.py     # The AI's web search (DuckDuckGo, Wikipedia fallback)
│   ├── safe_commands.py # The read-only commands the AI may run
│   ├── browsers.py      # Open a site in a browser, optionally in private browsing
│   ├── spotify_control.py # Start Spotify and play a requested track
│   ├── dev_tools.py       # Git projects watch and reminders (menu, bubbles)
│   ├── git_watch.py       # Read-only git status and log of the registered projects
│   ├── reminders.py       # Timers and reminders (in memory)
│   ├── world.py           # The fish on the desktop and Prinny's hunt for it
│   ├── food.py            # The dish Prinny goes to eat
│   ├── fight.py           # The staged fights (Rabbit, Pumpkin, Bats, Wrestler)
│   ├── port_info.py       # Which program listens on a port (read-only)
│   ├── ai_assistant.py  # AI chat and actions (mixed into Prinny)
│   ├── chat_window.py   # Chat window
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