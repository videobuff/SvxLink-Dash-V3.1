from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock
import wave

from pi3twe.audio.beeps import write_beeps
from pi3twe.controller.audio_logic import AudioLogic, AudioLogicError, LogicSettings


class AudioLogicTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = LogicSettings(self.root / "settings.sqlite3")
        self.mixer = Mock()
        self.svx = Mock()
        self.svx.state.return_value = {"active": True, "native_ready": True}
        self.logic = AudioLogic(self.settings, self.mixer, self.svx)

    def tearDown(self):
        self.temp.cleanup()

    def test_policy_survives_reopen_and_rx_id_cannot_be_disabled(self):
        self.settings.update({"beep_count": 7, "callsign": "PI3TWE", "news_enabled": True})
        reopened = LogicSettings(self.root / "settings.sqlite3")
        self.assertEqual(reopened.read()["beep_count"], 7)
        for data in ({"rx_audio": False}, {"callgiver": False}, {"beep_count": True}, {"callsign": "x\n[Tx1]"}):
            with self.assertRaises(ValueError):
                reopened.update(data)

    def test_news_never_stops_or_restarts_svxlink_or_changes_mixer(self):
        with self.logic.news():
            self.assertEqual(self.logic.phase, "preparing")
            with self.assertRaises(AudioLogicError):
                with self.logic.change():
                    self.fail("Concurrent changes must be blocked")
        self.svx.control.assert_not_called()
        self.mixer.state.assert_not_called()
        self.mixer.update.assert_not_called()
        self.assertEqual(self.logic.phase, "normal")
        self.assertFalse(self.logic.busy)

    def test_news_requires_running_native_engine(self):
        self.svx.state.return_value = {"active": False, "native_ready": False}
        with self.assertRaises(AudioLogicError):
            with self.logic.news():
                self.fail("Inactive engine accepted news")
        self.svx.control.assert_not_called()

    def test_news_failure_is_reported_without_restarting_engine(self):
        with self.assertRaises(RuntimeError):
            with self.logic.news():
                raise RuntimeError("Native playback failed")
        self.assertEqual(self.logic.phase, "error")
        self.assertIn("Native playback", self.logic.last_error)
        self.svx.control.assert_not_called()

    def test_five_beeps_have_exact_gaps_and_duration(self):
        output = self.root / "beeps.wav"
        write_beeps(output, self.settings.read())
        with wave.open(str(output)) as audio:
            self.assertEqual(audio.getframerate(), 48000)
            samples = audio.readframes(audio.getnframes())
            self.assertEqual(audio.getnframes(), 5 * 5760 + 4 * 5760)
        for index in range(4):
            start = (index * 11520 + 5760) * 2
            self.assertEqual(samples[start:start + 11520], bytes(11520))
