"""Contracts implemented by all PI3TWE hardware backends."""

from dataclasses import dataclass
from typing import Protocol


class RelayHardware(Protocol):
    def count(self) -> int: ...

    def get_state(self, relay_id: int) -> bool: ...

    def set_state(self, relay_id: int, enabled: bool) -> None: ...

    def health(self) -> dict[str, object]: ...


class SensorHardware(Protocol):
    def read_all(self) -> dict[str, dict[str, object]]: ...

    def health(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class HardwareBundle:
    relays: RelayHardware
    sensors: SensorHardware
    backend: str
