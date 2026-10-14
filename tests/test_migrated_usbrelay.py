import subprocess
from unittest import TestCase

from pi3twe.hardware.usbrelay import UsbRelayError, UsbRelayHardware


class FakeUsbRelay:
    def __init__(self) -> None:
        self.states = {1: False, 2: False}
        self.connected = True
        self.commands: list[list[str]] = []

    def __call__(self, command):
        self.commands.append(list(command))
        if not self.connected:
            return subprocess.CompletedProcess(command, 1, "", "device unavailable")
        if len(command) == 2:
            key, value = command[1].split("=")
            channel = int(key.rsplit("_", 1)[1])
            self.states[channel] = value == "1"
        output = "\n".join(
            f"HURTM_{channel}={int(enabled)}"
            for channel, enabled in self.states.items()
        )
        return subprocess.CompletedProcess(command, 0, output + "\n", "")


class UsbRelayHardwareTest(TestCase):
    def setUp(self) -> None:
        self.fake = FakeUsbRelay()
        self.hardware = UsbRelayHardware(
            "HURTM", runner=self.fake, cache_seconds=0
        )

    def test_reads_both_channels(self) -> None:
        self.fake.states = {1: True, 2: False}
        self.assertTrue(self.hardware.get_state(1))
        self.assertFalse(self.hardware.get_state(2))

    def test_switches_and_verifies_channel(self) -> None:
        self.hardware.set_state(2, True)
        self.assertTrue(self.fake.states[2])
        self.assertIn(["/usr/bin/usbrelay", "HURTM_2=1"], self.fake.commands)

    def test_disconnect_keeps_last_known_state_and_reports_unhealthy(self) -> None:
        self.fake.states[1] = True
        self.assertTrue(self.hardware.get_state(1))
        self.fake.connected = False
        self.assertTrue(self.hardware.get_state(1))
        self.assertFalse(self.hardware.health()["connected"])

    def test_write_fails_when_disconnected(self) -> None:
        self.fake.connected = False
        with self.assertRaises(UsbRelayError):
            self.hardware.set_state(1, True)

    def test_invalid_module_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            UsbRelayHardware("bad id", runner=self.fake)
