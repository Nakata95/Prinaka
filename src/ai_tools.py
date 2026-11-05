"""
ai_tools.py
-----------
The actions the local model is allowed to take (see ai.py).

The list is closed on purpose: the model can only call these tools, each with
validated arguments, and none of them changes a file, a program or a git project (git_status only reads).
Tools that change the interface run on the GUI thread (gui=True); the
read-only ones run in the chat thread.
"""

import os
import platform
import re
import time
import unicodedata
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

import psutil

import browsers
import defender
import git_watch
import media
import reminders
import safe_commands
import spotify_control
import system_stats
import websearch
from utils import get_current_language


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANIMATION_NAMES  = ("idle", "walk", "inspect", "hype", "fail")
MEDIA_ACTIONS    = {"play_pause": "toggle", "next": "next", "previous": "previous"}
MAX_ANIM_SECONDS = 15
SEARCH_TOOL      = "web_search"
NOTHING_OPENED   = ("Nothing was opened. Tell the user so, and ask what they prefer instead; "
                    "do not open anything else and do not say you will")
MAX_URL          = 500
_HOST            = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
DIAGNOSTIC_TOPICS = ("all", "performance", "disk", "network", "security")
TOP_PROCESSES    = 5
SAMPLE_SECONDS   = 0.6       # CPU use of a process needs two readings this far apart
# Thresholds above which a finding is reported to the model
WARN_RAM, WARN_DISK, WARN_LATENCY_MS, WARN_UPTIME_DAYS = 85, 90, 150, 7
MAX_JUMPS        = 5
PLACES           = ("left", "right", "center")
JUMP_DIRECTIONS  = ("up", "left", "right")
# What each behaviour means, for the model (same list as the right-click menu)
BEHAVIORS        = ("free", "stay_still", "keep_moving", "keep_busy", "express", "punish")


@dataclass
class Tool:
    """One callable action: its description for the model and the code to run."""
    name: str
    description: str
    properties: dict            # JSON-schema properties of the arguments
    required: tuple
    run: Callable[[dict], str]
    gui: bool = True            # True: run on the GUI thread
    describe: Callable[[dict], str] | None = None    # what to show next to the action (an address...)

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": self.properties,
                           "required": list(self.required)},
        }}


def _duration(seconds: float) -> str:
    """'25 minutes', '2 h 05 min', for the model."""
    minutes = round(seconds / 60)
    if minutes < 1:
        return f"{int(seconds)} seconds"
    if minutes < 60:
        return f"{minutes} minutes"
    return f"{minutes // 60} h {minutes % 60:02d} min"


def _plain(text: str) -> str:
    """Lower case without accents, so 'Arrête' matches 'arrete'."""
    decomposed = unicodedata.normalize("NFD", text.lower().replace("’", "'"))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def looks_like_order(text: str, words: str) -> bool:
    """
    True if a message may be an order or a request about something Prinny can do.

    A small model calls tools for plain chatter too ("you start again" became a
    punishment), so the tools are only offered when the message contains one of
    these words. Over-matching is harmless: the model still decides.

    Args:
        words: Comma separated word stems, from the 'ai_action_words' text.
    """
    plain = _plain(text)
    return any(stem.strip() and _plain(stem.strip()) in plain for stem in words.split(","))


def select_tools(text: str, order_words: str, search_words: str) -> set | None:
    """
    Names of the tools the model may use for this message (None = all of them).

    - action tools only for something that looks like an order (see looks_like_order)
    - web search for an order too, a question or a request to look something up;
      a plain remark gets no tool at all
    """
    chosen = set()
    if looks_like_order(text, order_words):
        chosen.add("*")
    if "?" in text or looks_like_order(text, search_words):
        chosen.add(SEARCH_TOOL)
    return chosen


def _top_processes() -> tuple:
    """(top by CPU, top by memory) as 'name: value' strings, one line per program (not per process)."""
    procs = list(psutil.process_iter(["name"]))
    for proc in procs:
        try:
            proc.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(SAMPLE_SECONDS)
    cpu, memory = {}, {}
    cores = psutil.cpu_count() or 1
    for proc in procs:
        try:
            name = proc.info["name"] or "?"
            if name == "System Idle Process":    # the unused CPU, not a program
                continue
            cpu[name] = cpu.get(name, 0.0) + proc.cpu_percent(None) / cores
            memory[name] = memory.get(name, 0) + proc.memory_info().rss
        except psutil.Error:
            continue
    by_cpu = sorted(cpu.items(), key=lambda kv: kv[1], reverse=True)[:TOP_PROCESSES]
    by_mem = sorted(memory.items(), key=lambda kv: kv[1], reverse=True)[:TOP_PROCESSES]
    return ([f"{name} {value:.0f}%" for name, value in by_cpu],
            [f"{name} {value / 1024 ** 3:.1f} GB" for name, value in by_mem])


def run_diagnostic(topic: str) -> str:
    """
    Read-only look at the PC for the model to explain: facts first, then the
    points that deserve attention. Nothing is closed, deleted or changed.
    """
    lines, findings = [], []
    want = lambda name: topic in ("all", name)

    if want("performance"):
        cpu = psutil.cpu_percent(interval=0.3)
        ram = system_stats.get_ram_usage()
        by_cpu, by_mem = _top_processes()
        lines += [f"CPU: {cpu:.0f}%", f"RAM: {ram['percent']:.0f}% ({ram['used_gb']} of {ram['total_gb']} GB)",
                  "Top programs by CPU: " + ", ".join(by_cpu), "Top programs by memory: " + ", ".join(by_mem)]
        temperature = system_stats.get_cpu_temperature()
        if temperature != "N/A":
            lines.append(f"CPU temperature: {temperature}")
        days = system_stats.get_uptime_seconds() / 86400
        lines.append(f"Uptime: {days:.1f} days")
        if ram["percent"] >= WARN_RAM:
            findings.append(f"RAM is almost full ({ram['percent']:.0f}%): the biggest users are {', '.join(by_mem[:3])}")
        if cpu >= 80:
            findings.append(f"CPU is busy ({cpu:.0f}%): {', '.join(by_cpu[:3])}")
        if days >= WARN_UPTIME_DAYS:
            findings.append(f"the PC has not been restarted for {days:.0f} days")

    if want("disk"):
        for drive in system_stats.get_fixed_drives():
            free = drive["free"] / 1024 ** 3
            lines.append(f"Disk {drive['mount']}: {drive['percent']:.0f}% used, {free:.0f} GB free of {drive['total'] / 1024 ** 3:.0f} GB")
            if drive["percent"] >= WARN_DISK:
                findings.append(f"disk {drive['mount']} is almost full ({free:.0f} GB free)")

    if want("network"):
        latency = system_stats.measure_latency()
        if latency < 0:
            lines.append("Network: no answer from the internet (offline or blocked)")
            findings.append("the PC seems offline")
        else:
            lines.append(f"Network latency: {latency} ms")
            if latency >= WARN_LATENCY_MS:
                findings.append(f"network latency is high ({latency} ms)")

    if want("security"):
        detections = defender.read_detections()
        if detections is None:
            lines.append("Windows Defender: unavailable (another antivirus or turned off)")
        else:
            active = [d for d in detections if d.active]
            lines.append(f"Windows Defender: {len(active)} active threat(s), {len(detections)} in its history")
            for d in active:
                findings.append(f"active threat {d.title}" + (f" ({d.target})" if d.target else ""))

    lines.append("Points needing attention: " + ("; ".join(findings) if findings else "none, everything looks normal"))
    return "\n".join(lines)


def safe_web_url(text: str) -> str | None:
    """
    A web address the browser may be sent to, or None.

    Only http(s) with a real domain name: no other scheme (file:, javascript:,
    ms-settings:...), no login in the address, no raw IP address, no local name.
    A bare 'youtube.com' gets https://.
    """
    text = str(text or "").strip()
    if not text or len(text) > MAX_URL or any(c.isspace() or ord(c) < 32 for c in text):
        return None
    if "://" not in text:
        if ":" in text.split("/")[0]:      # 'javascript:...', 'mailto:...'
            return None
        text = "https://" + text
    parts = urllib.parse.urlsplit(text)
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme not in ("http", "https") or parts.username or parts.password:
        return None
    if not _HOST.match(host) or re.fullmatch(r"[0-9.]+", host):
        return None
    return text


BROWSER_OPTIONS = {
    "browser": {"type": "string", "enum": ["default", *browsers.BROWSERS],
                "description": "default unless the user names a browser"},
    "private": {"type": "boolean", "description": "true for private browsing / incognito / InPrivate, default false"},
}


def _browser_note(args: dict) -> str:
    """' (Firefox, private)' for what is shown next to the action; empty for a plain default-browser opening."""
    key = browsers.normalize(args.get("browser"))
    private = _boolean(args.get("private", False))
    if key == browsers.DEFAULT and not private:
        return ""
    label = browsers.BROWSERS[key].label if key != browsers.DEFAULT else "default"
    return f" ({label}{', private' if private else ''})"


def _number(args: dict, key: str, default=None):
    """A numeric argument, whatever the model wrote ('50', 50.0, ...)."""
    try:
        return float(args.get(key, default))
    except (TypeError, ValueError):
        return default


def _boolean(value) -> bool:
    return value if isinstance(value, bool) else str(value).strip().lower() in ("true", "1", "yes", "oui")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def build_tools(prinny) -> dict:
    """The tools bound to a Prinny widget, by name."""
    from prinny import SIZE_PERCENTS

    def set_skin(args: dict) -> str:
        name = str(args.get("name", "")).lower()
        if name not in prinny._skins:
            return f"error: unknown skin, choose one of {', '.join(prinny._skins)}"
        prinny.change_skin(name)
        return f"skin is now {name}"

    def set_size(args: dict) -> str:
        percent = _number(args, "percent")
        if percent is None or int(percent) not in SIZE_PERCENTS:
            return f"error: size must be one of {', '.join(map(str, SIZE_PERCENTS))}"
        prinny.set_size(int(percent))
        return f"size is now {int(percent)}%"

    def play_animation(args: dict) -> str:
        name = str(args.get("name", "")).lower()
        if name not in ANIMATION_NAMES:
            return f"error: unknown animation, choose one of {', '.join(ANIMATION_NAMES)}"
        seconds = min(max(_number(args, "seconds", 4), 1), MAX_ANIM_SECONDS)
        prinny.perform_animation(name, seconds)
        return f"playing {name} for {seconds:g} seconds"

    def move_to(args: dict) -> str:
        place = str(args.get("place", "")).lower()
        if place not in PLACES:
            return f"error: place must be one of {', '.join(PLACES)}"
        prinny.walk_to(place)
        return f"walking to the {place} of the screen"

    def jump(args: dict) -> str:
        direction = str(args.get("direction", "up")).lower()
        if direction not in JUMP_DIRECTIONS:
            return f"error: direction must be one of {', '.join(JUMP_DIRECTIONS)}"
        times = int(min(max(_number(args, "times", 1), 1), MAX_JUMPS))
        prinny.jump(direction, times)
        return f"jumping {direction}, {times} time(s)"

    def set_behavior(args: dict) -> str:
        mode = str(args.get("mode", "")).lower()
        if mode not in BEHAVIORS:
            return f"error: mode must be one of {', '.join(BEHAVIORS)}"
        prinny.set_behavior(mode)
        return f"behavior is now {mode}"

    def diagnostic(args: dict) -> str:
        topic = str(args.get("topic", "all")).lower()
        if topic not in DIAGNOSTIC_TOPICS:
            return f"error: topic must be one of {', '.join(DIAGNOSTIC_TOPICS)}"
        return run_diagnostic(topic)

    def open_in_browser(url: str, args: dict) -> str:
        """Open an address as asked: which browser, private window or not."""
        asked = " ".join(str(args.get("browser") or "").lower().split())
        browser = browsers.normalize(asked)
        if asked and asked not in ("default", "defaut", "par defaut", "par défaut") and browser == browsers.DEFAULT:
            return (f"error: unknown browser, it can be one of {', '.join(browsers.BROWSERS)} or default. "
                    f"{NOTHING_OPENED}")
        try:
            where = browsers.open_url(url, browser, _boolean(args.get("private", False)))
        except browsers.BrowserError as e:
            return f"error: {e}. {NOTHING_OPENED}"
        return f"opened in {where}"

    def open_website(args: dict) -> str:
        url = safe_web_url(args.get("url"))
        if url is None:
            return "error: that is not a valid web address (give https://domain.tld)"
        return f"{open_in_browser(url, args)}: {url}"

    def open_search(args: dict) -> str:
        query = " ".join(str(args.get("query", "")).split())[:200]
        if not query:
            return "error: query is empty"
        template = str(prinny.config.get("search_engine_url"))
        if "{q}" not in template or safe_web_url(template.replace("{q}", "x")) is None:
            template = "https://duckduckgo.com/?q={q}"
        url = template.replace("{q}", urllib.parse.quote_plus(query))
        return f"{open_in_browser(url, args)}: search for '{query}'"

    def spotify_launch(args: dict) -> str:
        try:
            return f"Spotify {spotify_control.launch()}"
        except spotify_control.SpotifyError as e:
            return f"error: {e}"

    def spotify_play(args: dict) -> str:
        try:
            return spotify_control.play(str(args.get("query", "")), get_current_language(), str(args.get("kind", "")))
        except spotify_control.SpotifyError as e:
            return f"error: {e}"

    def run_command(args: dict) -> str:
        return safe_commands.run(str(args.get("command", "")).lower(), str(args.get("target", "") or ""),
                                 str(args.get("option", "") or ""))

    def git_status(args: dict) -> str:
        if not git_watch.available():
            return "error: git is not installed"
        paths = prinny.git_paths()
        if not paths:
            return "error: no git project registered; the user adds one in the right-click menu, Git projects"
        wanted = " ".join(str(args.get("project", "")).split()).lower()
        if wanted:
            paths = [p for p in paths if wanted in os.path.basename(p.rstrip("\\/")).lower()]
            if not paths:
                return f"error: no registered project matches '{wanted}'"
        return "\n".join(git_watch.summary(git_watch.read(p)) for p in paths)

    def set_timer(args: dict) -> str:
        try:
            seconds = reminders.seconds_until(args.get("minutes"), str(args.get("at", "") or ""))
            prinny._reminders.add(seconds, str(args.get("label", "") or ""))
        except reminders.ReminderError as e:
            return f"error: {e}"
        due = datetime.now() + timedelta(seconds=seconds)
        return f"reminder set for {due:%H:%M}, in {_duration(seconds)}"

    def list_timers(args: dict) -> str:
        active = prinny._reminders.active()
        if not active:
            return "no active reminder"
        return "\n".join(f"{label or '(no label)'}: in {_duration(left)}" for label, left in active)

    def cancel_timers(args: dict) -> str:
        count = prinny._reminders.cancel(str(args.get("label", "") or ""))
        return f"{count} reminder(s) cancelled" if count else "error: no reminder matched"

    def web_search(args: dict) -> str:
        if not prinny.config.get("web_search_enabled"):
            return "error: web search is turned off by the user (right-click menu), tell them"
        query = str(args.get("query", "")).strip()
        if not query:
            return "error: query is empty"
        try:
            return websearch.format_results(websearch.search(query, get_current_language()))
        except websearch.SearchError as e:
            return f"error: search failed, {e}"

    def set_volume(args: dict) -> str:
        level = _number(args, "level")
        if level is None:
            return "error: level must be a number from 0 to 100"
        level = int(min(max(level, 0), 100))
        prinny.change_volume(level)
        return f"volume is now {level}%"

    def set_muted(args: dict) -> str:
        muted = _boolean(args.get("muted", True))
        prinny.set_muted(muted)
        return "muted" if muted else "unmuted"

    def media_control(args: dict) -> str:
        action = MEDIA_ACTIONS.get(str(args.get("action", "")))
        if action is None:
            return f"error: action must be one of {', '.join(MEDIA_ACTIONS)}"
        source = media.SOURCE_SPOTIFY if prinny.config.get("media_spotify_only") else media.SOURCE_ANY
        media.send_command(source, action)
        return "sent"

    def get_status(args: dict) -> str:
        lines = [f"PC name: {platform.node()}", f"CPU: {psutil.cpu_percent(interval=0.3):.0f}%"]
        ram = system_stats.get_ram_usage()
        lines.append(f"RAM: {ram['percent']:.0f}% ({ram['used_gb']} of {ram['total_gb']} GB)")
        disk = system_stats.get_disk_usage()
        lines.append(f"Disk: {disk['free_gb']} GB free of {disk['total_gb']} GB")
        battery = system_stats.get_battery()
        if battery:
            lines.append(f"Battery: {battery['percent']:.0f}%, {'charging' if battery['plugged'] else 'on battery'}")
        lines.append(f"Uptime: {system_stats.get_uptime_seconds() // 3600} hours")

        source = media.SOURCE_SPOTIFY if prinny.config.get("media_spotify_only") else media.SOURCE_ANY
        state = media.get_media_state(source)
        if state:
            lines.append(f"Music: {state['title']} by {state['artist'] or 'unknown'} "
                         f"({'playing' if state['playing'] else 'paused'})")
        else:
            lines.append("Music: nothing playing")
        return "\n".join(lines)

    tools = [
        Tool("set_skin", "Change Prinny's skin.",
             {"name": {"type": "string", "enum": list(prinny._skins)}}, ("name",), set_skin),
        Tool("set_size", "Change Prinny's size in percent.",
             {"percent": {"type": "integer", "enum": list(SIZE_PERCENTS)}}, ("percent",), set_size),
        Tool("play_animation", "Only when asked for a short one-off animation: play it for a few seconds, then go back to normal "
             "(hype = happy, fail = grumpy, inspect = looking around).",
             {"name": {"type": "string", "enum": list(ANIMATION_NAMES)},
              "seconds": {"type": "integer", "description": f"1 to {MAX_ANIM_SECONDS}, default 4"}},
             ("name",), play_animation),
        Tool("move_to", "Make Prinny walk to the left side, the right side or the center of the screen.",
             {"place": {"type": "string", "enum": list(PLACES)}}, ("place",), move_to),
        Tool("jump", "Make Prinny jump, on the spot or toward a side, once or several times.",
             {"direction": {"type": "string", "enum": list(JUMP_DIRECTIONS), "description": "default up"},
              "times": {"type": "integer", "description": f"1 to {MAX_JUMPS}, default 1"}},
             (), jump),
        Tool("set_behavior", "Give Prinny an order about what he does, until told otherwise. "
             "keep_moving: move, walk around, run around. stay_still: stop moving, stay quiet and still. "
             "express: go wild, express yourself, dance, party. keep_busy: get busy, look around, inspect, "
             "do something. punish: be grumpy, punish yourself. free: do whatever you want again, back to normal.",
             {"mode": {"type": "string", "enum": list(BEHAVIORS)}}, ("mode",), set_behavior),
        Tool("set_volume", "Set the volume of Prinny's sounds, from 0 to 100.",
             {"level": {"type": "integer"}}, ("level",), set_volume),
        Tool("set_muted", "Mute or unmute Prinny's sounds.",
             {"muted": {"type": "boolean"}}, ("muted",), set_muted),
        Tool("media_control", "Control the music player: pause or resume, next track, previous track.",
             {"action": {"type": "string", "enum": list(MEDIA_ACTIONS)}}, ("action",),
             media_control, gui=False),
        Tool("open_website", "Open a website in the user's default browser, or in the browser they name, optionally in a "
             "private window (private, incognito, InPrivate). Only when the user asks to go to or open a site. Give the "
             "full address, e.g. https://www.youtube.com; never invent an address you are unsure of (use open_search "
             "instead).",
             {"url": {"type": "string"}, **BROWSER_OPTIONS}, ("url",), open_website, gui=False,
             describe=lambda a: f"{safe_web_url(a.get('url')) or ''}{_browser_note(a)}"),
        Tool("open_search", "Open a web search in the user's default browser, or the browser they name, optionally in a "
             "private window, to be read by the user. Use it when the user asks to search or look something up himself "
             "(\"fais une recherche\", \"cherche X sur google\"); never to find an answer yourself.",
             {"query": {"type": "string"}, **BROWSER_OPTIONS}, ("query",), open_search, gui=False,
             describe=lambda a: f"{' '.join(str(a.get('query', '')).split())[:80]}{_browser_note(a)}"),
        Tool("spotify_launch", "Start the Spotify app (without playing anything). Only when the user asks to open or "
             "launch Spotify.", {}, (), spotify_launch, gui=False),
        Tool("spotify_play", "Start Spotify if needed and play the song, album, playlist or artist the user asks for. "
             "Give the title and the artist as the query. For pause, next or previous on what already plays, use "
             "media_control instead.",
             {"query": {"type": "string", "description": "title and artist, e.g. 'Get Lucky Daft Punk'; just the name for a playlist"},
              "kind": {"type": "string", "enum": list(spotify_control.KINDS),
                       "description": "playlist if the user says playlist, album if album, artist if only an artist; else track"}},
             ("query",), spotify_play, gui=False,
             describe=lambda a: " ".join(str(a.get("query", "")).split())[:80]),
        Tool("run_command", "Run one harmless read-only Windows command and read its output. Allowed: "
             + "; ".join(f"{name} ({c.description})" for name, c in safe_commands.COMMANDS.items())
             + ". Options allowed: " + "; ".join(f"{n} {' '.join(c.options)}" for n, c in safe_commands.COMMANDS.items() if c.options)
             + ". ping, nslookup and tracert need a host name or address as target. 'cmd ipconfig' or 'ip config' means ipconfig. Nothing else can be run: "
             "no deleting, installing, editing or anything needing administrator rights.",
             {"command": {"type": "string", "enum": list(safe_commands.COMMANDS)},
              "target": {"type": "string", "description": "host name or address, only for ping, nslookup, tracert"},
              "option": {"type": "string", "description": "optional, e.g. /all for ipconfig; only the options listed for the command"}},
             ("command",), run_command, gui=False,
             describe=lambda a: safe_commands.display(str(a.get("command", "")).lower(), str(a.get("target", "") or ""),
                                                      str(a.get("option", "") or ""))),
        Tool("git_status", "Read-only state of the user's registered git projects: branch, changed files and since when, "
             "commits not pushed or to pull, last commits. Use it when the user asks where they stand on a project, "
             "what is not committed or pushed. It changes nothing; you can never commit or push.",
             {"project": {"type": "string", "description": "part of the project name; empty for all projects"}},
             (), git_status, gui=False,
             describe=lambda a: " ".join(str(a.get("project", "")).split())[:60]),
        Tool("set_timer", "Set a reminder or timer that rings later with a bubble and a sound. Give either minutes (a number, "
             "'in 25 minutes' = 25, 'in 2 hours' = 120) or at (a time of day HH:MM, e.g. 22:30), plus a short label "
             "of what to remind. Several reminders can exist at once.",
             {"minutes": {"type": "number"}, "at": {"type": "string", "description": "time of day, HH:MM"},
              "label": {"type": "string", "description": "what to remind, a few words"}},
             (), set_timer,
             describe=lambda a: f"{' '.join(str(a.get('label', '')).split())[:60]}"),
        Tool("list_timers", "List the active reminders and the time left.", {}, (), list_timers),
        Tool("cancel_timers", "Cancel reminders: those whose label contains the given words, or all of them if no label.",
             {"label": {"type": "string"}}, (), cancel_timers),
        Tool("web_search", "Search the internet to find an answer for yourself. Only for a fact you do not know or that changes (news, weather, "
             "prices, scores, rules, a specific game, technique or product), never for opinions or small talk. "
             "Write short search words.",
             {"query": {"type": "string"}}, ("query",), web_search, gui=False),
        Tool("diagnostic", "Investigate a problem on the computer, read-only: slow PC (top programs by CPU and memory), "
             "full disk, network lag or no internet, viruses or threats. Use it when the user complains or asks "
             "why something is slow or wrong; it returns facts and the points needing attention. It changes nothing.",
             {"topic": {"type": "string", "enum": list(DIAGNOSTIC_TOPICS), "description": "default all"}},
             (), diagnostic, gui=False),
        Tool("get_status", "Read the computer's state (CPU, RAM, disk, battery, uptime) and the current music. Only when the user asks about the computer or the music.",
             {}, (), get_status, gui=False),
    ]
    return {tool.name: tool for tool in tools}
