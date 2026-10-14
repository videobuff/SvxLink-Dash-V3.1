from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pi3twe.database import EventStore, RelayStateStore
from pi3twe.hardware import create_hardware
from pi3twe.relay import RelayService
from pi3twe.controller import Controller


class RelayStateTest(TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "test.sqlite3"
        self.store = RelayStateStore(self.database)
        self.store.initialize()
        self.events = EventStore(self.database)
        self.events.initialize()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_first_start_adopts_physical_state(self) -> None:
        hardware = create_hardware("dummy")
        hardware.relays.set_state(1, True)
        controller = Controller(
            hardware, RelayService(hardware.relays, 0), self.events, self.store
        )
        controller.initialize_relay_state()
        self.assertEqual(self.store.desired(), {1: True, 2: False})

    def test_saved_power_is_restored_but_old_tx_setting_is_ignored(self) -> None:
        self.store.adopt_if_empty({1: True, 2: True})
        hardware = create_hardware("dummy")
        controller = Controller(
            hardware, RelayService(hardware.relays, 0), self.events, self.store
        )
        controller.initialize_relay_state()
        self.assertTrue(hardware.relays.get_state(1))
        self.assertFalse(hardware.relays.get_state(2))

    def test_old_tx_desired_state_is_not_applied(self) -> None:
        self.store.adopt_if_empty({1: False, 2: True})
        hardware = create_hardware("dummy")
        controller = Controller(
            hardware, RelayService(hardware.relays, 0), self.events, self.store
        )
        controller.initialize_relay_state()
        self.assertEqual(self.store.desired(), {1: False, 2: True})
        self.assertFalse(hardware.relays.get_state(2))

    def test_watchdog_does_not_override_active_svxlink_tx(self):
        self.store.adopt_if_empty({1: True, 2: False})
        hardware = create_hardware("dummy")
        hardware.relays.set_state(1, True)
        hardware.relays.set_state(2, True)
        controller = Controller(hardware, RelayService(hardware.relays, 0), self.events, self.store)
        controller.reconcile_relays()
        self.assertTrue(hardware.relays.get_state(2))
        hardware.relays.set_state(2, False)
        self.store.set_desired(2, True)
        controller.reconcile_relays()
        self.assertFalse(hardware.relays.get_state(2))

    def test_power_off_is_immediate_despite_cooldown_and_failed_command(self):
        hardware = create_hardware("dummy")
        controller = Controller(hardware, RelayService(hardware.relays, 60), self.events, self.store)
        controller.initialize_relay_state()
        controller.set_relay(1, True)
        def unavailable(enabled):
            self.assertFalse(hardware.relays.get_state(1))
            self.assertFalse(self.store.desired()[1])
            raise OSError(30, "Read-only file system")
        controller.radio_control = unavailable
        controller.set_relay(1, False)
        controller.reconcile_relays()
        self.assertFalse(hardware.relays.get_state(1))
