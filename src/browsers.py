"""
browsers.py
-----------
Opens a web address in the user's default browser, or in another installed one,
optionally in a private window (see ai_tools.py).

The program that is started is never named by the model: it is looked up here,
in Windows' own list of installed browsers (the 'App Paths' registry keys) or
in the browser's usual install folder. The browser gets one fixed private-mode
option and the address, started without a command shell. The caller checks the
address first (ai_tools.safe_web_url).

A private window is never replaced by a normal one: when it cannot be done, the
call fails instead of quietly opening the page in the open session.
"""

import os
import subprocess
import webbrowser
import winreg
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT = "default"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
APP_PATHS = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
URL_CHOICE = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"


@dataclass(frozen=True)
class Browser:
    label: str
    exe: str                 # name registered in 'App Paths'
    private_flag: str        # makes it open a private window
    progids: tuple           # beginnings of the Windows ProgId when it is the default browser
    folders: tuple = ()      # fallbacks under Program Files / LocalAppData, if not registered


BROWSERS = {
    "chrome":  Browser("Chrome", "chrome.exe", "--incognito", ("ChromeHTML",),
                       (r"Google\Chrome\Application\chrome.exe",)),
    "edge":    Browser("Edge", "msedge.exe", "--inprivate", ("MSEdgeHTM", "MSEdgeMHT"),
                       (r"Microsoft\Edge\Application\msedge.exe",)),
    "firefox": Browser("Firefox", "firefox.exe", "-private-window", ("FirefoxURL",),
                       (r"Mozilla Firefox\firefox.exe",)),
    "brave":   Browser("Brave", "brave.exe", "--incognito", ("BraveHTML",),
                       (r"BraveSoftware\Brave-Browser\Application\brave.exe",)),
    "opera":   Browser("Opera", "opera.exe", "--private", ("OperaStable", "Opera"),
                       (r"Opera\opera.exe", r"Programs\Opera\opera.exe")),
    "vivaldi": Browser("Vivaldi", "vivaldi.exe", "--incognito", ("VivaldiHTM",),
                       (r"Vivaldi\Application\vivaldi.exe", r"Programs\Vivaldi\vivaldi.exe")),
}

# What people write for each browser
ALIASES = {"google chrome": "chrome", "microsoft edge": "edge", "mozilla firefox": "firefox",
           "mozilla": "firefox", "brave browser": "brave", "opera gx": "opera"}


class BrowserError(Exception):
    """The page could not be opened as asked."""


# ---------------------------------------------------------------------------
# Finding browsers
# ---------------------------------------------------------------------------

def _registry(root, path: str, name: str = ""):
    try:
        with winreg.OpenKey(root, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def find_executable(key: str) -> str | None:
    """Full path of an installed browser, or None."""
    browser = BROWSERS[key]
    candidates = []
    for root, prefix in ((winreg.HKEY_LOCAL_MACHINE, ""), (winreg.HKEY_CURRENT_USER, ""),
                         (winreg.HKEY_LOCAL_MACHINE, "WOW6432Node\\")):
        value = _registry(root, APP_PATHS.replace("Software\\", f"Software\\{prefix}", 1) + "\\" + browser.exe)
        if value:
            candidates.append(str(value).strip('"'))
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
        candidates += [os.path.join(base, folder) for folder in browser.folders if base]
    for path in candidates:
        if os.path.isfile(path) and os.path.basename(path).lower() == browser.exe:
            return path
    return None


def installed() -> dict:
    """Installed browsers: key -> path."""
    return {key: path for key in BROWSERS if (path := find_executable(key))}


def default_browser() -> str | None:
    """Key of the user's default browser, or None when it is not one of BROWSERS."""
    progid = str(_registry(winreg.HKEY_CURRENT_USER, URL_CHOICE, "ProgId") or "")
    for key, browser in BROWSERS.items():
        if any(progid.startswith(prefix) for prefix in browser.progids):
            return key
    return None


def normalize(name: str) -> str:
    """'Google Chrome', ' EDGE ', '' -> 'chrome', 'edge', 'default'."""
    name = " ".join(str(name or "").lower().split())
    name = ALIASES.get(name, name)
    return name if name in BROWSERS else DEFAULT


# ---------------------------------------------------------------------------
# Opening
# ---------------------------------------------------------------------------

def open_url(url: str, browser: str = DEFAULT, private: bool = False) -> str:
    """
    Open `url`, already checked by the caller (http or https only).

    Args:
        browser: A key of BROWSERS, or 'default' for the user's default browser.
        private: Open a private window (incognito / InPrivate / private window).

    Returns:
        A short description of what was done, e.g. 'Firefox (private)'.

    Raises:
        BrowserError: the browser is not installed, or a private window is
            wanted and cannot be made.
    """
    if not url.lower().startswith(("http://", "https://")):
        raise BrowserError("only http and https addresses can be opened")

    key = browser if browser in BROWSERS else DEFAULT
    if key == DEFAULT:
        if not private:
            webbrowser.open(url)
            return "default browser"
        key = default_browser()
        if key is None:
            raise BrowserError("the default browser is not one this app knows for private windows; "
                               f"name one of: {', '.join(b.label for b in BROWSERS.values())}")

    path = find_executable(key)
    if path is None:
        have = ", ".join(BROWSERS[k].label for k in installed()) or "none found"
        raise BrowserError(f"{BROWSERS[key].label} is not installed (installed: {have})")

    argv = [path] + ([BROWSERS[key].private_flag] if private else []) + [url]
    try:
        subprocess.Popen(argv, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        raise BrowserError(f"could not start {BROWSERS[key].label} ({e})") from e
    return f"{BROWSERS[key].label}{' (private)' if private else ''}"
