"""
defender.py
-----------
Windows Defender relay for Prinaka.

Prinny does not detect malware itself: it reads what Microsoft Defender
reports (through PowerShell, locally, nothing is sent anywhere) and can ask
Defender to scan a file.

- read_detections(): detections and their threat names
- new_detections(): what appeared since the last reading
- ScanJob: scans one file in a background thread

The PowerShell calls are slow (one to two seconds), so callers run them in a
background thread.
"""

import json
import os
import subprocess
import threading
from dataclasses import dataclass, field

from PyQt5.QtCore import QObject, pyqtSignal


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

READ_TIMEOUT_S = 30
SCAN_TIMEOUT_S = 600

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Reads the detection history joined with the threat catalog. Prints "[]"
# when there is nothing and "null" when Defender is not usable.
READ_SCRIPT = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
try {
    $status = Get-MpComputerStatus -ErrorAction Stop
    if (-not $status.AntivirusEnabled) { 'null'; exit }
    $threats = @{}
    Get-MpThreat -ErrorAction SilentlyContinue | ForEach-Object { $threats[[string]$_.ThreatID] = $_ }
    $rows = @(Get-MpThreatDetection -ErrorAction SilentlyContinue | ForEach-Object {
        $threat = $threats[[string]$_.ThreatID]
        [pscustomobject]@{
            id        = [string]$_.ThreatID
            time      = $_.InitialDetectionTime.ToString('o')
            resources = @($_.Resources)
            process   = [string]$_.ProcessName
            name      = if ($threat) { [string]$threat.ThreatName } else { '' }
            active    = if ($threat) { [bool]$threat.IsActive } else { $false }
        }
    })
    ConvertTo-Json -InputObject $rows -Compress -Depth 4
} catch { 'null' }
"""

# The path comes from the environment: never pasted into the script text
SCAN_SCRIPT = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
try {
    Start-MpScan -ScanType CustomScan -ScanPath $env:PRINAKA_SCAN_PATH -ErrorAction Stop
    'ok'
} catch { 'error: ' + $_.Exception.Message }
"""


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Detection:
    """One entry of Defender's detection history."""
    id: str
    time: str                       # ISO string, only used as an identity
    name: str                       # threat name, '' if unknown
    active: bool                    # still present / not yet remediated
    resources: tuple = field(default_factory=tuple)   # affected files or items
    process: str = ""

    @property
    def key(self) -> str:
        return f"{self.id}|{self.time}"

    @property
    def title(self) -> str:
        return self.name or self.id

    @property
    def target(self) -> str:
        """Short description of what was affected: a file name when there is one."""
        for resource in self.resources:
            path = resource.split("->")[0].replace("file:_", "").strip()
            if path:
                return os.path.basename(path.rstrip("\\/")) or path
        return ""


def parse_detections(text: str):
    """
    Turn READ_SCRIPT's output into detections.

    Returns:
        A list of Detection, or None when Defender is not usable or the
        output is not understood.
    """
    text = (text or "").strip()
    if not text or text == "null":
        return None
    try:
        rows = json.loads(text)
    except ValueError:
        return None
    if isinstance(rows, dict):    # a single row may come back as an object
        rows = [rows]
    if not isinstance(rows, list):
        return None

    detections = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        resources = row.get("resources") or []
        if isinstance(resources, str):
            resources = [resources]
        detections.append(Detection(
            id=str(row["id"]),
            time=str(row.get("time", "")),
            name=str(row.get("name") or ""),
            active=bool(row.get("active")),
            resources=tuple(str(r) for r in resources),
            process=str(row.get("process") or ""),
        ))
    return detections


def new_detections(seen: set, detections: list) -> list:
    """
    Detections not reported yet; marks them as seen.

    Args:
        seen: Set of detection keys already reported (updated in place).
        detections: Current detections.
    """
    fresh = [d for d in detections if d.key not in seen]
    seen.update(d.key for d in fresh)
    return fresh


def matches_path(detection: Detection, path: str) -> bool:
    """True if a detection concerns this file (Defender writes 'file:_C:\\...')."""
    wanted = os.path.normcase(os.path.abspath(path))
    return any(wanted in os.path.normcase(resource) for resource in detection.resources)


# ---------------------------------------------------------------------------
# PowerShell
# ---------------------------------------------------------------------------

def _powershell(script: str, timeout: int, env_extra: dict | None = None) -> str | None:
    env = dict(os.environ, **(env_extra or {}))
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, timeout=timeout, env=env, creationflags=NO_WINDOW,
        )
        return result.stdout.decode("utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[defender] PowerShell failed: {e}")
        return None


def read_detections():
    """
    Read Defender's detections.

    Returns:
        A list of Detection (possibly empty), or None if Defender is off,
        replaced by another antivirus, or unreachable.
    """
    return parse_detections(_powershell(READ_SCRIPT, READ_TIMEOUT_S))


# ---------------------------------------------------------------------------
# Scanning one file
# ---------------------------------------------------------------------------

class ScanJob(QObject):
    """
    Scans one file with Defender in a background thread.

    finished(dict) carries 'path', 'status' ('clean', 'threat' or 'error')
    and 'threats' (names found).
    """

    finished = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self, path: str) -> None:
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._run, args=(path,), daemon=True).start()

    def _run(self, path: str) -> None:
        result = {"path": path, "status": "error", "threats": [], "reason": ""}
        try:
            before = read_detections()
            known = {d.key for d in before or []}

            output = (_powershell(SCAN_SCRIPT, SCAN_TIMEOUT_S, {"PRINAKA_SCAN_PATH": path}) or "").strip()
            if output != "ok":
                result["reason"] = output.removeprefix("error:").strip() or "no answer from PowerShell"
            elif before is None:
                result["reason"] = "Defender unavailable"
            else:
                after = read_detections()
                if after is None:
                    result["reason"] = "Defender unavailable"
                else:
                    found = [d for d in after if d.key not in known and matches_path(d, path)]
                    result["threats"] = sorted({d.title for d in found})
                    result["status"] = "threat" if found else "clean"
        finally:
            self._running = False
            self.finished.emit(result)
