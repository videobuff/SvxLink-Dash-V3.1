"""Relay state changes and cooldown protection."""

from __future__ import annotations

import time
from threading import RLock

from pi3twe.hardware.interfaces import RelayHardware


class CooldownError(RuntimeError):
    def __init__(self, relay_id: int, retry_after: float) -> None:
        super().__init__(f"Relay {relay_id} cooldown active")
        self.relay_id = relay_id
        self.retry_after = max(0.0, retry_after)


class InterlockError(RuntimeError):
    """Raised when a requested relay transition is unsafe."""


class RelayService:
    def __init__(self, hardware: RelayHardware, cooldown_seconds: float) -> None:
        self._hardware = hardware
        self._cooldown_seconds = max(0.0, cooldown_seconds)
        self._last_changed: dict[int, float] = {}
        self._lock = RLock()

    def set_state(self, relay_id: int, enabled: bool) -> bool:
        with self._lock:
            self._validate_relay(relay_id)
            self._validate_interlock(relay_id, enabled)
            current = self._hardware.get_state(relay_id)
            if current == enabled:
                return current

            now = time.monotonic()
            elapsed = now - self._last_changed.get(relay_id, float("-inf"))
            if elapsed < self._cooldown_seconds and not (relay_id == 1 and not enabled):
                raise CooldownError(relay_id, self._cooldown_seconds - elapsed)

            self._hardware.set_state(relay_id, enabled)
            self._last_changed[relay_id] = now
            return enabled

    def physical_states(self) -> dict[int, bool]:
        with self._lock:
            return {
                relay_id: self._hardware.get_state(relay_id)
                for relay_id in range(1, self._hardware.count() + 1)
            }

    def states(self) -> list[dict[str, object]]:
        return [
            {
                "id": relay_id,
                "name": "Repeater POWER" if relay_id == 1 else "Repeater TX",
                "on": self._hardware.get_state(relay_id),
            }
            for relay_id in range(1, self._hardware.count() + 1)
        ]

    def _validate_relay(self, relay_id: int) -> None:
        if relay_id < 1 or relay_id > self._hardware.count():
            raise ValueError(f"Onbekend relais: {relay_id}")

    def _validate_interlock(self, relay_id: int, enabled: bool) -> None:
        if relay_id == 2 and enabled and not self._hardware.get_state(1):
            raise InterlockError(
                "REPEATER TX kan alleen AAN als REPEATER POWER AAN is"
            )
