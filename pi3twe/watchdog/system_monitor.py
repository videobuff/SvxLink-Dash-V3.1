"""Log sustained Linux host health warnings and recoveries."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event, Thread

from pi3twe.controller.system_metrics import read_system_metrics
from pi3twe.database import EventStore

FAILURES_BEFORE_REPORTING = 3


class SystemMonitor:
    def __init__(
        self,
        events: EventStore,
        interval_seconds: float,
        metrics_reader: Callable[[], dict[str, object]] = read_system_metrics,
    ) -> None:
        self._events = events
        self._interval = max(1.0, interval_seconds)
        self._metrics_reader = metrics_reader
        self._stop = Event()
        self._thread = Thread(
            target=self._run, name="pi3twe-systeembewaking", daemon=True
        )
        self._counts: dict[str, int] = {}
        self._reported: set[str] = set()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval + 1)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._check_once()

    def _check_once(self) -> None:
        metrics = self._metrics_reader()
        checks = {
            "disk": (
                float(metrics["disk_free_percent"]) <= 20,
                float(metrics["disk_free_percent"]) > 22,
                f"SCHIJFRUIMTE LAAG: {metrics['disk_free_percent']}% VRIJ",
                "SCHIJFRUIMTE HERSTELD",
            ),
            "cpu": (
                float(metrics["cpu_load_percent"]) >= 90,
                float(metrics["cpu_load_percent"]) < 80,
                f"CPU-BELASTING HOOG: {metrics['cpu_load_percent']}%",
                "CPU-BELASTING HERSTELD",
            ),
        }
        for key, (warning, recovered, warning_message, recovery_message) in checks.items():
            if warning:
                self._counts[key] = self._counts.get(key, 0) + 1
                if (
                    self._counts[key] >= FAILURES_BEFORE_REPORTING
                    and key not in self._reported
                ):
                    self._events.add("bewaking", warning_message)
                    self._reported.add(key)
            elif recovered:
                self._counts[key] = 0
                if key in self._reported:
                    self._events.add("bewaking", recovery_message)
                    self._reported.remove(key)
