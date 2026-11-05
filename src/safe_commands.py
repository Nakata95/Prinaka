"""
safe_commands.py
----------------
The few Windows commands Prinny's local AI may run (see ai_tools.py).

The model never writes a command line. It picks a name from COMMANDS, and at
most one target (a host name or address, for the network commands). Each entry
is a fixed argument list started WITHOUT a shell, so nothing the model or a web
page writes can add a second command, a redirection or an option. Every
command is read-only, needs no administrator rights and is stopped after a
time limit; Prinny is never started elevated and does not ask for it.

To allow one more command, add an entry to COMMANDS. Keep it read-only.
"""

import ctypes
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_OUTPUT  = 3500
NO_WINDOW   = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# A host name or an IPv4 address: letters, digits, dots and dashes, never starting with a dash
HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


@dataclass(frozen=True)
class SafeCommand:
    """One allowed command."""
    argv: tuple                  # fixed arguments; '{target}' is replaced by the validated target
    description: str             # for the model
    needs_target: bool = False
    timeout_s: int = 20
    options: tuple = ()          # the only options that may be added, lower case, written with '/'


COMMANDS = {
    "ipconfig":   SafeCommand(("ipconfig",), "network addresses of this PC", False, 20, ("/all", "/displaydns")),
    "ping":       SafeCommand(("ping", "-n", "4", "{target}"), "test whether a host answers and how fast", True, 20),
    "nslookup":   SafeCommand(("nslookup", "{target}"), "find the address of a host name (DNS)", True, 20),
    "tracert":    SafeCommand(("tracert", "-d", "-h", "15", "-w", "1000", "{target}"), "route to a host", True, 60),
    "netstat":    SafeCommand(("netstat", "-n"), "current network connections", False, 20, ("/a", "/o", "/an", "/ano", "/r")),
    "arp":        SafeCommand(("arp", "-a"), "devices seen on the local network", False, 20),
    "getmac":     SafeCommand(("getmac",), "MAC addresses of the network cards", False, 20, ("/v",)),
    "route":      SafeCommand(("route", "print"), "routing table", False, 20),
    "tasklist":   SafeCommand(("tasklist",), "running programs", False, 20, ("/v", "/svc")),
    "systeminfo": SafeCommand(("systeminfo",), "Windows version and hardware summary", False, 45),
    "driverquery": SafeCommand(("driverquery",), "installed drivers", False, 30),
    "whoami":     SafeCommand(("whoami",), "current Windows user", False, 10, ("/all", "/groups")),
    "hostname":   SafeCommand(("hostname",), "name of this PC", False, 10),
    "vol":        SafeCommand(("cmd", "/c", "vol"), "label of the system drive", False, 10),
    "ver":        SafeCommand(("cmd", "/c", "ver"), "Windows version", False, 10),
    "date_time":  SafeCommand(("cmd", "/c", "date /t & time /t"), "current date and time", False, 10),
}

# Words that tell Prinny the user wants a command typed, not a chat answer
_TRIGGER = re.compile(r"^(?:\W*(?:(?:peux[- ]?tu|tu peux|can you|please|stp|s'il te plait)\s+)*"
                      r"(?:(?:lance|lancer|execute|executer|run|fais|fait|tape|taper|ouvre)\s+)?"
                      r"(?:(?:la|une|the|a|un)\s+)?)"
                      r"(?:commande|command|cmd(?:\.exe)?|invite de commandes?|terminal)(?![a-z])[\s:]*(?:/c\s+)?(.*)$")
_POLITE_END = re.compile(r"\s+(?:stp|s'il te plait|svp|please|merci)\W*$")


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower().replace("’", "'"))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def parse(text: str):
    """
    Understand an explicit command request such as 'cmd ipconfig', 'ip config /all'
    or 'lance la commande ping google.com'.

    Returns:
        None if the message does not ask for a command line. Otherwise
        (name, option, target) when it is an allowed command, or
        (None, '', typed_word) when the user asked for something not allowed.
    """
    match = _TRIGGER.match(_plain(text).strip())
    if not match:
        return None
    rest = _POLITE_END.sub("", match.group(1).strip()).rstrip(" .!?")
    tokens = rest.replace(" -", " /").split()
    if not tokens:
        return None
    # 'ip config', 'net stat', 'task list': glue the first words together until a command name appears
    for count in (1, 2, 3):
        name = "".join(tokens[:count]).replace("_", "")
        name = {"datetime": "date_time", "date": "date_time", "time": "date_time"}.get(name, name)
        if name in COMMANDS:
            args = tokens[count:]
            break
    else:
        return None, "", tokens[0]
    command = COMMANDS[name]
    option = ""
    target = ""
    for arg in args:
        low = arg.lower()
        if not command.options or low not in command.options or option:
            if command.needs_target and not target and HOST.match(arg):
                target = arg
                continue
            if low in ("print", "-a", "/a") and name in ("route", "arp"):
                continue
            return None, "", f"{name} {arg}"
        option = low
    return name, option, target


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

def command_line(name: str, target: str = "", option: str = "") -> list | None:
    """
    The exact arguments for an allowed command, or None if the name is not
    allowed, a needed target is missing, or the target is not a plain host.
    """
    command = COMMANDS.get(name)
    if command is None:
        return None
    target = (target or "").strip()
    option = (option or "").strip().lower().replace("-", "/", 1) if option else ""
    if option and option not in command.options:
        return None
    if command.needs_target:
        if not HOST.match(target):
            return None
    elif target:
        return None
    argv = [part.replace("{target}", target) for part in command.argv]
    if option:
        if argv[0] == "cmd":
            return None
        argv.insert(1, option)
    return argv


def _console_encoding() -> str:
    try:
        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except (AttributeError, OSError):
        return "utf-8"


def run(name: str, target: str = "", option: str = "") -> str:
    """
    Run an allowed command and return its output for the model.

    Returns:
        The text printed by the command (cut to MAX_OUTPUT), or a line starting
        with 'error:' when it is refused, fails or takes too long.
    """
    argv = command_line(name, target, option)
    if argv is None:
        if name in COMMANDS and option:
            return f"error: option not allowed, this command accepts only: {', '.join(COMMANDS[name].options) or 'none'}"
        if name in COMMANDS and COMMANDS[name].needs_target:
            return "error: this command needs a plain host name or address as target (letters, digits, dots, dashes)"
        if name in COMMANDS:
            return "error: this command takes no target"
        return f"error: command not allowed, choose one of {', '.join(COMMANDS)}"
    try:
        result = subprocess.run(
            argv, capture_output=True, timeout=COMMANDS[name].timeout_s,
            creationflags=NO_WINDOW, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return f"error: the command took more than {COMMANDS[name].timeout_s} seconds and was stopped"
    except OSError as e:
        return f"error: could not start the command ({e})"

    text = (result.stdout or result.stderr).decode(_console_encoding(), errors="replace")
    text = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    if len(text) > MAX_OUTPUT:
        text = text[:MAX_OUTPUT] + "\n[output cut]"
    return text or "(no output)"


def display(name: str, target: str = "", option: str = "") -> str:
    """The command as it is shown to the user in the chat."""
    argv = command_line(name, target, option)
    return " ".join(argv) if argv else name
