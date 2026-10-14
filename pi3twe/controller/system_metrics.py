"""Read Linux host health values without external command dependencies."""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path


_cpu_lock = threading.Lock()
_previous_cpu_times: tuple[int, int] | None = None


def read_system_metrics() -> dict[str, object]:
    cpu_count = max(1, os.cpu_count() or 1)
    load_1, load_5, load_15 = os.getloadavg()
    disk = shutil.disk_usage("/")
    return {
        "cpu_load_percent": _cpu_usage_percent(),
        "cpu_count": cpu_count,
        "load_average": [round(load_1, 2), round(load_5, 2), round(load_15, 2)],
        "disk_free_percent": round(disk.free / disk.total * 100, 1),
        "disk_free_bytes": disk.free,
        "disk_total_bytes": disk.total,
        "cpu_temperature_c": _hwmon_temperature("k10temp"),
        "soc_temperature_c": _hwmon_temperature("radeon"),
    }


def _cpu_usage_percent() -> float:
    """Return CPU busy time since the previous reading, bounded to 0-100%."""
    global _previous_cpu_times

    try:
        fields = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0].split()
        values = [int(value) for value in fields[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
    except (FileNotFoundError, OSError, IndexError, ValueError):
        return 0.0

    with _cpu_lock:
        previous = _previous_cpu_times
        _previous_cpu_times = (total, idle)

    if previous is None:
        total_delta, idle_delta = total, idle
    else:
        total_delta = total - previous[0]
        idle_delta = idle - previous[1]

    if total_delta <= 0:
        return 0.0
    busy_percent = (total_delta - idle_delta) / total_delta * 100
    return round(max(0.0, min(100.0, busy_percent)), 1)


def _hwmon_temperature(driver: str) -> float | None:
    for name_path in Path("/sys/class/hwmon").glob("hwmon*/name"):
        try:
            if name_path.read_text(encoding="ascii").strip() != driver:
                continue
            raw = name_path.with_name("temp1_input").read_text(encoding="ascii")
            return round(int(raw.strip()) / 1000, 1)
        except (FileNotFoundError, OSError, ValueError):
            continue
    return None
