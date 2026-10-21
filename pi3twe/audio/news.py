"""Prepare news media and ask the running SvxLink engine to broadcast it."""
from __future__ import annotations

import subprocess
import time
import uuid
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock



class NewsPlaybackError(RuntimeError):
    pass


class NewsPlayer:
    def __init__(self, *, transmit_enabled: bool, svxlink, logic,
                 spool_directory: Path):
        self.transmit_enabled = transmit_enabled
        self.svxlink = svxlink
        self.logic = logic
        self.spool_directory = spool_directory
        self.spool_directory.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self.current_label = None

    @property
    def busy(self):
        return self._lock.locked()

    def play(self, path: Path, label: str):
        if not self.transmit_enabled:
            raise NewsPlaybackError("Nieuwsuitzending is geblokkeerd in de audiologica")
        if not path.is_file():
            raise NewsPlaybackError("Audiobestand ontbreekt")
        if not self._lock.acquire(blocking=False):
            raise NewsPlaybackError("Er wordt al een nieuwsitem afgespeeld")
        self.current_label = label
        token = uuid.uuid4().hex
        queued = False
        safe_cleanup = True
        media = self.spool_directory / f"{token}.wav"
        try:
            with self.logic.news() as settings:
                intro_ms, news_ms = self._prepare(path, media, settings)
                self.svxlink.send_command("NEWS", token, f"{intro_ms} {news_ms}")
                queued = True
                safe_cleanup = False
                deadline = time.monotonic() + (2 * intro_ms + news_ms) / 1000 + 15
                while time.monotonic() < deadline:
                    state = self.svxlink.command_status(token)
                    if state:
                        phase = state["phase"]
                        if phase == "done":
                            safe_cleanup = True
                            return
                        if phase in {"error", "busy", "power_off", "cancelled"}:
                            safe_cleanup = True
                            reason = {"power_off": "repeater-power staat uit", "busy": "er speelt al nieuws",
                                      "error": "afspelen is mislukt", "cancelled": "nieuws is afgebroken"}[phase]
                            raise NewsPlaybackError("SvxLink: " + reason)
                        self.logic.phase = phase
                    time.sleep(.1)
                raise NewsPlaybackError("SvxLink heeft nieuws niet tijdig afgerond")
        except Exception as error:
            if queued and not safe_cleanup:
                try:
                    self.svxlink.send_command("CANCEL", token)
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        state = self.svxlink.command_status(token)
                        if state and state["phase"] in {"done", "cancelled", "error", "idle"}:
                            safe_cleanup = True
                            break
                        time.sleep(.1)
                except Exception:
                    pass  # SvxLink's own bounded queue watchdog remains responsible.
            if isinstance(error, NewsPlaybackError):
                raise
            raise NewsPlaybackError(str(error)) from error
        finally:
            try:
                if safe_cleanup:
                    media.unlink(missing_ok=True)
                    try:
                        (self.svxlink.status_directory / f"{token}.json").unlink(missing_ok=True)
                    except OSError:
                        pass  # A cleanup failure must not strand the playback lock.
            finally:
                self.current_label = None
                self._lock.release()

    def _prepare(self, path, output, settings):
        with TemporaryDirectory(prefix="pi3twe-news-") as directory:
            decoded = Path(directory) / "news.wav"
            subprocess.run(["/usr/bin/ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(path),
                            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(decoded)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            with wave.open(str(decoded)) as news, wave.open(str(output), "wb") as destination:
                destination.setnchannels(1)
                destination.setsampwidth(2)
                destination.setframerate(16000)
                if news.getnframes() > 16000 * 1800:
                    raise NewsPlaybackError("Nieuwsbestand duurt langer dan 30 minuten")
                if not news.getnframes():
                    raise NewsPlaybackError("Nieuwsbestand bevat geen audio")
                news_ms = round(news.getnframes() * 1000 / 16000)
                while chunk := news.readframes(16000):
                    destination.writeframes(chunk)
            return 0, news_ms
