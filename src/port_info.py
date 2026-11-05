"""
port_info.py
------------
Who is listening on a network port (read-only).

Only looks: it lists the sockets of the PC and the program behind each one. It never
stops a program, and it is not given a process number by anyone: the number comes
from the lookup itself.
"""

import socket
import time

import psutil


def _bound(address: str) -> str:
    if address in ("127.0.0.1", "::1"):
        return "this PC only"
    if address in ("0.0.0.0", "::", ""):
        return "every network interface (reachable from the local network)"
    return f"address {address}"


def _age(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds} s"
    if seconds < 5400:
        return f"{seconds // 60} min"
    if seconds < 172800:
        return f"{seconds // 3600} h"
    return f"{seconds // 86400} d"


def owners(port: int) -> str:
    """
    Describe the programs listening on a TCP port or bound to a UDP port.

    Returns:
        Plain text for the model, or a line starting with 'error:'.
    """
    if not isinstance(port, int) or not 1 <= port <= 65535:
        return "error: the port must be a number from 1 to 65535"
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, OSError) as e:
        return f"error: the list of connections cannot be read ({e})"

    found = {}
    for c in connections:
        if not c.laddr or c.laddr.port != port:
            continue
        listening = c.status == psutil.CONN_LISTEN or (c.type == socket.SOCK_DGRAM and not c.raddr)
        if listening:
            kind = "TCP" if c.type == socket.SOCK_STREAM else "UDP"
            found.setdefault((c.pid, kind, c.laddr.ip), c)
    if not found:
        return f"nothing is listening on port {port}: it is free"

    me = None
    try:
        me = psutil.Process().username()
    except psutil.Error:
        pass
    lines = []
    for (pid, kind, ip) in sorted(found, key=lambda k: (k[0] or 0, k[1], k[2])):
        where = f"{kind} port {port}, open to {_bound(ip)}"
        if not pid:
            lines.append(f"{where}: used by a program that cannot be identified without administrator rights")
            continue
        try:
            proc = psutil.Process(pid)
            name = proc.name()
        except psutil.NoSuchProcess:
            continue
        except psutil.Error:
            lines.append(f"{where}: process {pid}, cannot be read without administrator rights")
            continue
        try:
            path = proc.exe() or "path not available"
        except psutil.Error:
            path = "path not readable"
        try:
            running = f", running for {_age(time.time() - proc.create_time())}"
        except psutil.Error:
            running = ""
        try:
            mine = "started by you" if me and proc.username() == me else "started by another account"
        except psutil.Error:
            mine = "owner unknown"
        lines.append(f"{where}: {name} (process {pid}, {mine}{running}), {path}")
    return "\n".join(lines) if lines else f"nothing is listening on port {port}: it is free"
