from unittest import TestCase

from pi3twe.watchdog.relay_monitor import FAILURES_BEFORE_REPORTING, RelayMonitor


class StubController:
    def __init__(self) -> None:
        self.error: Exception | None = None

    def reconcile_relays(self) -> None:
        if self.error:
            raise self.error


class StubEvents:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def add(self, category: str, message: str) -> None:
        self.messages.append(message)


class RelayMonitorTest(TestCase):
    def setUp(self) -> None:
        self.controller = StubController()
        self.events = StubEvents()
        self.monitor = RelayMonitor(self.controller, self.events, 1)

    def test_single_startup_failure_is_not_logged_as_outage(self) -> None:
        self.controller.error = RuntimeError("USB-relaismodule niet bereikbaar")
        self.monitor._check_once()
        self.controller.error = None
        self.monitor._check_once()

        self.assertEqual(self.events.messages, [])

    def test_persistent_failure_and_recovery_are_logged_once(self) -> None:
        self.controller.error = RuntimeError("USB-relaismodule niet bereikbaar")
        for _ in range(FAILURES_BEFORE_REPORTING + 2):
            self.monitor._check_once()

        self.assertEqual(
            self.events.messages,
            ["RELAISBEWAKING STORING: USB-relaismodule niet bereikbaar"],
        )

        self.controller.error = None
        self.monitor._check_once()
        self.monitor._check_once()
        self.assertEqual(
            self.events.messages,
            [
                "RELAISBEWAKING STORING: USB-relaismodule niet bereikbaar",
                "RELAISBEWAKING HERSTELD",
            ],
        )
