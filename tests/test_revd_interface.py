import configparser
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]

class RevDTests(TestCase):
    def setUp(self):
        loader = SourceFileLoader('revd_supervisor', str(ROOT / 'install/pi3twe-svxlink-ptt'))
        self.mod = module_from_spec(spec_from_loader(loader.name, loader))
        loader.exec_module(self.mod)
        self.calls = []
        self.mod.relay = lambda channel, state: self.calls.append((channel, state))
        self.mod.revd_interface = lambda: True
        self.mod.standby_on = lambda: False
        self.mod.time = Mock()

    def test_receive_keeps_hardware_cor_enabled(self):
        self.mod.receive()
        self.assertEqual(self.calls, [(3, False), (4, False)])

    def test_shutdown_removes_hardware_enable(self):
        self.mod.receive(shutdown=True)
        self.assertEqual(self.calls, [(3, False), (4, False), (2, False)])

    def test_transmit_only_requests_ptt(self):
        self.assertTrue(self.mod.transmit())
        self.assertEqual(self.calls, [(3, True)])

    def test_standby_never_requests_ptt(self):
        self.mod.standby_on = lambda: True
        self.assertFalse(self.mod.transmit())
        self.assertEqual(self.calls, [])

    def test_mode_enable_and_disable(self):
        self.mod.hardware_enable(True)
        self.mod.hardware_enable(False)
        self.assertEqual(self.calls, [(2, True), (2, False)])

    def test_legacy_sequence_preserved(self):
        self.mod.revd_interface = lambda: False
        self.mod.transmit()
        self.mod.receive()
        self.assertEqual(self.calls, [(2, True), (4, True), (3, True), (3, False), (4, False), (2, False)])

    def test_only_hardware_profile_disables_software_repeat(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.mod.PTY_LINK = root / 'ptt'
            original = root / 'original.conf'
            original.write_text('[GLOBAL]\n[RepeaterLogic]\n[Tx1]\n')
            for enabled in [True, False]:
                output = self.mod.runtime_config(original, interface_revd=enabled)
                config = configparser.ConfigParser()
                config.read(output)
                self.assertEqual(config['RepeaterLogic']['NO_REPEAT'], str(int(enabled)))
                self.assertEqual(config['RepeaterLogic']['MUTE_RX_ON_TX'], '0')
