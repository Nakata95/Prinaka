"""
system_stats.py
---------------
System statistics collection for Prinaka.

Covers:
- CPU usage and temperature
- RAM usage
- Disk usage
- Network speed and latency
- Recycle bin size (Windows only)
"""

import os
import platform
import socket
import time

import psutil


# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------

def get_cpu_usage() -> float:
    """
    Return the current CPU usage as a percentage.

    Returns:
        Float between 0.0 and 100.0.
    """
    return psutil.cpu_percent()


def get_cpu_temperature() -> str:
    """
    Return the current CPU temperature as a formatted string.

    Tries psutil sensors first, then falls back to WMI on Windows.
    Returns 'N/A' if temperature cannot be read.

    Returns:
        Temperature string (e.g. '65.0°C') or 'N/A'.
    """
    # Try psutil sensors (Linux / some Windows setups)
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            if "coretemp" in temps:
                return f"{temps['coretemp'][0].current:.1f}°C"
            # Take the first available sensor
            first = next(iter(temps.values()))
            if first:
                return f"{first[0].current:.1f}°C"
    except AttributeError:
        pass
    except Exception:
        pass

    # Fallback: WMI (Windows)
    if platform.system() == "Windows":
        try:
            import wmi
            w = wmi.WMI(namespace="root\\wmi")
            temps = w.MSAcpi_ThermalZoneTemperature()
            if temps:
                temp_c = temps[0].CurrentTemperature / 10 - 273.15
                return f"{temp_c:.1f}°C"
        except Exception:
            pass

    return "N/A"


# ---------------------------------------------------------------------------
# RAM
# ---------------------------------------------------------------------------

def get_ram_usage() -> dict:
    """
    Return current RAM usage information.

    Returns:
        Dict with keys:
            - percent (float): usage percentage
            - used_gb (int): used RAM in GB
            - total_gb (int): total RAM in GB
    """
    ram = psutil.virtual_memory()
    return {
        "percent":  ram.percent,
        "used_gb":  ram.used  // (1024 ** 3),
        "total_gb": ram.total // (1024 ** 3),
    }


# ---------------------------------------------------------------------------
# Disk
# ---------------------------------------------------------------------------

def get_disk_usage(path: str = "/") -> dict:
    """
    Return disk usage information for the given path.

    Args:
        path: Mount point to check. Defaults to '/' (C: on Windows).

    Returns:
        Dict with keys:
            - used_gb (int): used space in GB
            - total_gb (int): total space in GB
            - free_gb (int): free space in GB
            - free_percent (float): percentage of free space
    """
    import shutil
    disk = shutil.disk_usage(path)
    return {
        "used_gb":      disk.used  // (1024 ** 3),
        "total_gb":     disk.total // (1024 ** 3),
        "free_gb":      disk.free  // (1024 ** 3),
        "free_percent": (disk.free / disk.total) * 100,
    }


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

class NetworkMonitor:
    """
    Tracks network speed by comparing successive psutil snapshots.

    Must be instantiated once and reused — do not create a new instance
    every second or speed calculations will be wrong.

    Usage:
        monitor = NetworkMonitor()
        # call every second via a QTimer:
        stats = monitor.get_stats()
    """

    def __init__(self):
        self._last_net  = psutil.net_io_counters()
        self._last_time = time.time()

    def _human_speed(self, bps: float) -> str:
        """
        Convert bytes per second to a human-readable string.

        Args:
            bps: Speed in bytes per second.

        Returns:
            Formatted string (e.g. '1.2 MB/s').
        """
        if bps < 1024:
            return f"{bps:.1f} B/s"
        elif bps < 1024 ** 2:
            return f"{bps / 1024:.1f} KB/s"
        else:
            return f"{bps / 1024 ** 2:.1f} MB/s"

    def _human_total(self, total_bytes: int) -> str:
        """
        Convert a byte total to a human-readable string.

        Args:
            total_bytes: Total bytes.

        Returns:
            Formatted string (e.g. '1.20 GB').
        """
        if total_bytes >= 1024 ** 3:
            return f"{total_bytes / (1024 ** 3):.2f} GB"
        elif total_bytes >= 1024 ** 2:
            return f"{total_bytes / (1024 ** 2):.2f} MB"
        else:
            return f"{total_bytes} B"

    def get_stats(self) -> dict:
        """
        Return current network statistics.

        Returns:
            Dict with keys:
                - latency_ms (int): ping to 8.8.8.8 in milliseconds, or -1
                - sent_total (str): total bytes sent since boot
                - recv_total (str): total bytes received since boot
                - sent_speed (str): current upload speed
                - recv_speed (str): current download speed
        """
        # Latency
        latency_ms = -1
        try:
            start = time.time()
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            latency_ms = int((time.time() - start) * 1000)
        except Exception:
            pass

        # Speed
        now     = time.time()
        net     = psutil.net_io_counters()
        delta   = max(now - self._last_time, 0.001)  # avoid division by zero

        sent_speed = (net.bytes_sent - self._last_net.bytes_sent) / delta
        recv_speed = (net.bytes_recv - self._last_net.bytes_recv) / delta

        self._last_net  = net
        self._last_time = now

        return {
            "latency_ms": latency_ms,
            "sent_total": self._human_total(net.bytes_sent),
            "recv_total": self._human_total(net.bytes_recv),
            "sent_speed": self._human_speed(sent_speed),
            "recv_speed": self._human_speed(recv_speed),
        }


# ---------------------------------------------------------------------------
# Recycle Bin (Windows only)
# ---------------------------------------------------------------------------

def get_recycle_bin_stats() -> str:
    """
    Return the size of the Windows Recycle Bin as a formatted string.

    Only works on Windows. Returns 'N/A' on other platforms.

    Returns:
        Formatted string (e.g. '1.20 MB') or 'N/A'.
    """
    if platform.system() != "Windows":
        return "N/A"

    try:
        recycle_path = "C:\\$Recycle.Bin"
        total_size   = 0
        file_count   = 0

        for root, dirs, files in os.walk(recycle_path):
            for f in files:
                try:
                    fp = os.path.join(root, f)
                    total_size += os.path.getsize(fp)
                    file_count += 1
                except Exception:
                    pass

        if file_count == 0:
            return "Empty"
        elif total_size >= 1024 ** 3:
            return f"{total_size / (1024 ** 3):.2f} GB"
        elif total_size >= 1024 ** 2:
            return f"{total_size / (1024 ** 2):.2f} MB"
        else:
            return f"{total_size} B"

    except Exception as e:
        return f"N/A ({e})"