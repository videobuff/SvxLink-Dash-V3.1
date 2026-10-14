"""Safe in-memory hardware used until the USB devices are available."""

from __future__ import annotations

from threading import RLock


class DummyRelayHardware:
    """Two process-local relay outputs which start in the OFF state."""

    def __init__(self, relay_count: int = 2) -> None:
        self._states = {relay_id: False for relay_id in range(1, relay_count + 1)}
        self._lock = RLock()

    def count(self) -> int:
        return len(self._states)

    def get_state(self, relay_id: int) -> bool:
        with self._lock:
            self._validate(relay_id)
            return self._states[relay_id]

    def set_state(self, relay_id: int, enabled: bool) -> None:
        with self._lock:
            self._validate(relay_id)
            self._states[relay_id] = bool(enabled)

    def health(self) -> dict[str, object]:
        return {
            "backend": "dummy",
            "connected": False,
            "message": "Dummy relay backend; no physical outputs are connected",
        }

    def _validate(self, relay_id: int) -> None:
        if relay_id not in self._states:
            raise ValueError(f"Unknown relay: {relay_id}")


class DummySensorHardware:
    """Unavailable sensor values with an explicit dummy status."""

    def read_all(self) -> dict[str, dict[str, object]]:
        return {
            "int": {
                "name": "Binnen",
                "temperature_c": None,
                "humidity_percent": None,
                "available": False,
            },
            "ext": {
                "name": "Buiten",
                "temperature_c": None,
                "humidity_percent": None,
                "available": False,
            },
        }

    def health(self) -> dict[str, object]:
        return {
            "backend": "dummy",
            "connected": False,
            "message": "Dummy sensor backend; no physical sensors are connected",
        }
