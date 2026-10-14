"""Select hardware without leaking backend details into other modules."""

from __future__ import annotations

import os

from .dummy import DummyRelayHardware, DummySensorHardware
from .interfaces import HardwareBundle
from .simulator import SimulatedSensorHardware
from .usbrelay import UsbRelayHardware


def create_hardware(backend: str) -> HardwareBundle:
    selected = backend.strip().lower()
    sensor_backend = os.environ.get("PI3TWE_SENSOR_BACKEND", "dummy").strip().lower()
    if sensor_backend == "dummy":
        sensors = DummySensorHardware()
    elif sensor_backend == "simulator":
        sensors = SimulatedSensorHardware()
    else:
        raise ValueError(f"Unsupported PI3TWE sensor backend: {sensor_backend}")
    if selected == "dummy":
        return HardwareBundle(
            relays=DummyRelayHardware(relay_count=2),
            sensors=sensors,
            backend=selected,
        )
    if selected == "usbrelay":
        module_id = os.environ.get("PI3TWE_USB_RELAY_ID", "").strip()
        if not module_id:
            raise ValueError(
                "PI3TWE_USB_RELAY_ID is required for the usbrelay backend"
            )
        tx_channel = int(os.environ.get("PI3TWE_TX_RELAY_CHANNEL", "2"))
        return HardwareBundle(
            relays=UsbRelayHardware(module_id, relay_channels=(1, tx_channel)),
            sensors=sensors,
            backend=selected,
        )
    raise ValueError(f"Unsupported PI3TWE hardware backend: {backend}")
