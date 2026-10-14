"""Coordinate policy, persistence and hardware."""

from __future__ import annotations

import os
import time
from threading import RLock

from pi3twe.database import EventStore, RelayStateStore
from pi3twe.hardware.interfaces import HardwareBundle
from pi3twe.relay import CooldownError, InterlockError, RelayService

from .system_metrics import read_system_metrics


class Controller:
    def __init__(
        self,
        hardware: HardwareBundle,
        relay_service: RelayService,
        events: EventStore,
        relay_states: RelayStateStore,
    ) -> None:
        self.hardware = hardware
        self.relays = relay_service
        self.events = events
        self.relay_states = relay_states
        self._lock = RLock()
        self.radio_control = None

    def set_relay(self, relay_id: int, enabled: bool) -> dict[str, object]:
        with self._lock:
            if relay_id == 2:
                raise InterlockError("TX wordt uitsluitend door SvxLink bestuurd")
            if relay_id == 1 and self.radio_control is not None:
                # Cut the Icom's 12 V first, even if SvxLink is unavailable.
                state = self.relays.set_state(relay_id, enabled)
                self.relay_states.set_desired(relay_id, state)
                try:
                    self.radio_control(enabled)
                except (RuntimeError, OSError) as error:
                    self.events.add("bewaking", f"SVXLINK TX BIJWERKEN MISLUKT: {error}")
            else:
                state = self.relays.set_state(relay_id, enabled)
            self.relay_states.set_desired(relay_id, state)
            self.relay_states.record_actual(self.relays.physical_states())
            action = "ON" if state else "OFF"
            label = "REPEATER POWER" if relay_id == 1 else "REPEATER TX"
            self.events.add("relay", f"{label} {action}")
            return {"id": relay_id, "on": state}

    def initialize_relay_state(self) -> None:
        """Adopt physical state once, otherwise restore the saved state."""
        if not self._relay_available():
            return
        actual = self.relays.physical_states()
        if self.relay_states.adopt_if_empty(actual):
            self.events.add(
                "bewaking",
                "BEGINSTAND VASTGELEGD: "
                f"REPEATER POWER {_on_off(actual[1])}, "
                f"REPEATER TX {_on_off(actual[2])}",
            )
            return
        self.relay_states.record_actual(actual)
        self.reconcile_relays()

    def reconcile_relays(self) -> None:
        """Restore the durable desired state using a safe switching order."""
        with self._lock:
            if not self._relay_available():
                raise RuntimeError("USB-relaismodule niet bereikbaar")

            actual = self.relays.physical_states()
            if self.relay_states.adopt_if_empty(actual):
                self.events.add(
                    "bewaking",
                    "BEGINSTAND VASTGELEGD: "
                    f"REPEATER POWER {_on_off(actual[1])}, "
                    f"REPEATER TX {_on_off(actual[2])}",
                )
                return

            self.relay_states.record_actual(actual)
            desired = self.relay_states.desired()
            # Only POWER belongs to this controller; never reconcile SvxLink TX.
            order = ((1, desired.get(1, False)),)
            for relay_id, target in order:
                if self.relays.physical_states()[relay_id] == target:
                    continue
                try:
                    self.relays.set_state(relay_id, target)
                except CooldownError:
                    continue
                label = "REPEATER POWER" if relay_id == 1 else "REPEATER TX"
                self.events.add(
                    "bewaking", f"STAND HERSTELD: {label} {_on_off(target)}"
                )
            self.relay_states.record_actual(self.relays.physical_states())

    def state(self) -> dict[str, object]:
        relays = self.relays.states()
        for relay in relays:
            relay["managed_by"] = "controller" if relay["id"] == 1 else "svxlink"
        sensors = self.hardware.sensors.read_all()
        return {
            "ok": True,
            "hostname": os.uname().nodename,
            "uptime_s": system_uptime_seconds(),
            "hardware_backend": self.hardware.backend,
            "hardware": {
                "relays": self.hardware.relays.health(),
                "sensors": self.hardware.sensors.health(),
            },
            "system": read_system_metrics(),
            "relays": relays,
            "relay_persistence": [row for row in self.relay_states.snapshot() if row["id"] == 1],
            "sensors": sensors,
            # Backward-compatible fields used by the Raspberry Pi web client.
            "repeater_on": bool(relays[0]["on"]),
            "int": _legacy_sensor(sensors["int"]),
            "ext": _legacy_sensor(sensors["ext"]),
        }

    def _relay_available(self) -> bool:
        health = self.hardware.relays.health()
        return self.hardware.backend == "dummy" or bool(health.get("connected"))


def _legacy_sensor(sensor: dict[str, object]) -> dict[str, object]:
    temperature = sensor["temperature_c"]
    humidity = sensor["humidity_percent"]
    return {
        "temp": "xx.x" if temperature is None else temperature,
        "hum": "xx" if humidity is None else humidity,
        "ok": bool(sensor["available"]),
    }


def _on_off(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


def system_uptime_seconds() -> int:
    """Return elapsed seconds since the Linux server booted."""
    try:
        with open("/proc/uptime", encoding="ascii") as uptime_file:
            return max(0, int(float(uptime_file.read().split()[0])))
    except (FileNotFoundError, OSError, ValueError, IndexError):
        return max(0, int(time.monotonic()))
