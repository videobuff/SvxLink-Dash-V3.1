"""Background monitor that restores durable relay state."""

from __future__ import annotations

import logging
from threading import Event, Thread

from pi3twe.controller import Controller
from pi3twe.database import EventStore

LOGGER = logging.getLogger(__name__)
FAILURES_BEFORE_REPORTING = 3


class RelayMonitor:
    def __init__(
        self, controller: Controller, events: EventStore, interval_seconds: float
    ) -> None:
        self._controller = controller
        self._events = events
        self._interval = max(0.5, interval_seconds)
        self._stop = Event()
        self._thread = Thread(
            target=self._run, name="pi3twe-relaisbewaking", daemon=True
        )
        self._last_error = ""
        self._failure_count = 0
        self._error_reported = False

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval + 1)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._check_once()

    def _check_once(self) -> None:
        try:
            self._controller.reconcile_relays()
        except Exception as error:  # keep 24/7 monitor alive
            message = str(error) or error.__class__.__name__
            LOGGER.warning("Relaisbewaking: %s", message)
            self._failure_count += 1
            self._last_error = message
            if (
                self._failure_count >= FAILURES_BEFORE_REPORTING
                and not self._error_reported
            ):
                self._events.add("bewaking", f"RELAISBEWAKING STORING: {message}")
                self._error_reported = True
        else:
            if self._error_reported:
                self._events.add("bewaking", "RELAISBEWAKING HERSTELD")
            self._failure_count = 0
            self._last_error = ""
            self._error_reported = False
