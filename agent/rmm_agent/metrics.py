from __future__ import annotations

import platform
import socket
import time
import uuid
from typing import Any

import psutil


def collect_hello() -> dict[str, Any]:
    uname = platform.uname()
    return {
        "os": uname.system,
        "os_version": f"{uname.release} {uname.version}",
        "arch": uname.machine,
        "hostname": socket.gethostname(),
        "primary_ip": _primary_ip(),
        "mac_addresses": _macs(),
    }


def collect_heartbeat() -> dict[str, Any]:
    cpu = psutil.cpu_percent(interval=None)
    vm = psutil.virtual_memory()
    # Use the root/system drive for the top-line number. Full per-disk breakdown
    # can be added later when the UI needs it.
    try:
        disk = psutil.disk_usage("/")
        disk_percent = disk.percent
    except Exception:
        disk_percent = None

    try:
        load1, load5, load15 = psutil.getloadavg()
    except (AttributeError, OSError):
        load1 = load5 = load15 = None

    uptime = int(time.time() - psutil.boot_time())

    return {
        "observed_at": time.time(),
        "cpu_percent": cpu,
        "mem_percent": vm.percent,
        "mem_total": vm.total,
        "mem_used": vm.used,
        "disk_percent": disk_percent,
        "loadavg": [load1, load5, load15],
        "uptime_seconds": uptime,
    }


def _primary_ip() -> str | None:
    # Open a UDP socket to a bogus external address; the OS picks the source IP for
    # the default route without sending a packet. Works offline.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return None


def _macs() -> list[str]:
    try:
        out: list[str] = []
        addrs = psutil.net_if_addrs()
        for iface, records in addrs.items():
            if iface.startswith(("lo", "docker", "veth", "br-")):
                continue
            for r in records:
                # psutil uses AF_LINK on most platforms; fall back to family value 17 (AF_PACKET on Linux)
                if r.family.name in ("AF_LINK", "AF_PACKET"):
                    if r.address and r.address != "00:00:00:00:00:00":
                        out.append(r.address)
        return out
    except Exception:
        # Last-resort: uuid.getnode gives a MAC-like 48-bit value
        try:
            n = uuid.getnode()
            mac = ":".join(f"{(n >> ele) & 0xff:02x}" for ele in range(40, -1, -8))
            return [mac]
        except Exception:
            return []
