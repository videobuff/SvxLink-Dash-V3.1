from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
import wave

from pi3twe.audio.news import NewsPlaybackError, NewsPlayer
from pi3twe.controller.audio_logic import AudioLogic, LogicSettings


class NewsPlayerTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = LogicSettings(self.root / "settings.sqlite3", news_enabled=True)
        self.svx = Mock()
        self.svx.state.return_value = {"active": True, "native_ready": True}
        self.svx.status_directory = self.root / "status"
        self.svx.status_directory.mkdir()
        self.logic = AudioLogic(self.settings, Mock(), self.svx)
        self.player = NewsPlayer(transmit_enabled=True, svxlink=self.svx, logic=self.logic, spool_directory=self.root / "spool")
        self.media = self.root / "news.wav"
        with wave.open(str(self.media), "wb") as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)
            output.writeframes(bytes(1600 * 2))

    def tearDown(self):
        self.temp.cleanup()

    def test_safety_block_prevents_any_engine_command(self):
        self.player.transmit_enabled = False
        with self.assertRaises(NewsPlaybackError):
            self.player.play(self.media, "nieuws001")
        self.svx.send_command.assert_not_called()

    def test_news_is_queued_once_and_engine_remains_running(self):
        self.svx.command_status.side_effect = [{"phase": phase} for phase in ("before_beeps", "news", "after_beeps", "done")]
        with patch.object(self.player, "_prepare", return_value=(1080, 100)), patch("pi3twe.audio.news.time.sleep"):
            self.player.play(self.media, "nieuws001")
        self.assertEqual(self.svx.send_command.call_count, 1)
        command, token, arguments = self.svx.send_command.call_args.args
        self.assertEqual(command, "NEWS")
        self.assertEqual(len(token), 32)
        self.assertEqual(arguments, "1080 100")
        self.svx.control.assert_not_called()
        self.assertEqual(self.logic.phase, "normal")
        self.assertFalse(self.player.busy)

    def test_prepare_creates_mono_pcm_with_beeps_before_and_after(self):
        output = self.root / "prepared.wav"
        intro, duration = self.player._prepare(self.media, output, self.settings.read())
        self.assertEqual((intro, duration), (1080, 100))
        with wave.open(str(output)) as audio:
            self.assertEqual((audio.getnchannels(), audio.getsampwidth(), audio.getframerate()), (1, 2, 16000))
            data = audio.readframes(audio.getnframes())
        signal_bytes = 17280 * 2
        self.assertEqual(data[:signal_bytes], data[-signal_bytes:])
        self.assertEqual(data[signal_bytes:signal_bytes + 3200], bytes(3200))

    def test_engine_error_does_not_restart_engine(self):
        self.svx.command_status.return_value = {"phase": "power_off"}
        with patch.object(self.player, "_prepare", return_value=(100, 100)), self.assertRaises(NewsPlaybackError):
            self.player.play(self.media, "nieuws001")
        self.svx.control.assert_not_called()
        self.assertFalse(self.player.busy)

    def test_transport_failure_cancels_only_the_news_job(self):
        self.svx.command_status.side_effect = [RuntimeError("Lost acknowledgement"), {"phase": "cancelled"}]
        with patch.object(self.player, "_prepare", return_value=(100, 100)), self.assertRaises(NewsPlaybackError):
            self.player.play(self.media, "nieuws001")
        self.assertEqual([call.args[0] for call in self.svx.send_command.call_args_list], ["NEWS", "CANCEL"])
        self.assertEqual(self.svx.send_command.call_args_list[0].args[1], self.svx.send_command.call_args_list[1].args[1])
        self.svx.control.assert_not_called()
