"""Snapshot battery / RAM / CPU / disk / network for the wake greeting."""

import re
import socket
import subprocess

from echo.config import PSUTIL_OK

if PSUTIL_OK:
    import psutil


def get_system_health():
    health = {}
    if not PSUTIL_OK:
        return health

    # Battery
    try:
        bat = psutil.sensors_battery()
        if bat:
            health['battery_percent'] = bat.percent
            health['battery_plugged'] = bat.power_plugged
        else:
            health['battery_percent'] = None
    except Exception:
        health['battery_percent'] = None

    # RAM
    try:
        mem = psutil.virtual_memory()
        health['ram_total_gb'] = round(mem.total / (1024**3), 1)
        health['ram_available_gb'] = round(mem.available / (1024**3), 1)
        health['ram_percent_used'] = mem.percent
    except Exception:
        health['ram_percent_used'] = None

    # CPU
    try:
        health['cpu_percent'] = psutil.cpu_percent(interval=0.5)
    except Exception:
        health['cpu_percent'] = None

    # Disk
    try:
        disk = psutil.disk_usage('C:\\')
        health['disk_free_gb'] = round(disk.free / (1024**3), 1)
        health['disk_percent_used'] = round(disk.percent, 1)
    except Exception:
        health['disk_free_gb'] = None

    # Internet + WiFi
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        health['internet'] = True
    except (socket.timeout, OSError):
        health['internet'] = False

    try:
        result = subprocess.run(
            ['netsh', 'wlan', 'show', 'interfaces'],
            capture_output=True, text=True, timeout=3)
        for line in result.stdout.split('\n'):
            if 'SSID' in line and 'BSSID' not in line:
                health['wifi_name'] = line.split(':', 1)[1].strip()
                break
            if 'Signal' in line:
                health['wifi_signal'] = line.split(':', 1)[1].strip()
    except Exception:
        pass

    # Ping
    try:
        result = subprocess.run(
            ['ping', '-n', '1', '-w', '1000', '8.8.8.8'],
            capture_output=True, text=True, timeout=3)
        for line in result.stdout.split('\n'):
            m = re.search(r'time[<=](\d+)', line, re.IGNORECASE)
            if m:
                health['ping_ms'] = int(m.group(1))
    except Exception:
        pass

    return health
