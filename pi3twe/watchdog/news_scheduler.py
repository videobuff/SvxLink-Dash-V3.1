"""Hourly news-bulletin scheduler."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Thread

from pi3twe.audio.news import NewsPlaybackError, NewsPlayer
from pi3twe.database import EventStore, NewsStore

LOGGER = logging.getLogger(__name__)

SVXLINK_LOG = Path("/var/log/pi3twe-svxlink/svxlink.log")
# The hourly identification (time + weather) must finish before news starts.
IDENT_START_GRACE = timedelta(seconds=15)
IDENT_MAX_WAIT = timedelta(seconds=90)


def _log_events(log_file: Path, size: int = 65536):
    """Yield (time, text) for SvxLink log lines, oldest first."""
    try:
        with log_file.open("rb") as source:
            source.seek(0, 2)
            source.seek(max(0, source.tell() - size))
            lines = source.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return
    for line in lines:
        stamp, sep, text = line.partition(": ")
        if not sep:
            continue
        try:
            when = datetime.strptime(stamp, "%a %b %d %H:%M:%S %Y").astimezone()
        except ValueError:
            continue
        yield when, text


def hourly_ident_done(now: datetime, log_file: Path = SVXLINK_LOG) -> bool:
    """True when the identification of this hour has finished transmitting.

    Waits for the transmitter to switch off after "Sending long/short
    identification". Proceeds anyway when no identification started within
    IDENT_START_GRACE or when IDENT_MAX_WAIT has passed, so a running QSO
    can never block the news.
    """
    slot = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if now >= slot + IDENT_MAX_WAIT:
        return True
    ident_at = None
    for when, text in _log_events(log_file):
        if when < slot or when > now:
            continue
        if ident_at is None and "identification..." in text:
            ident_at = when
        elif ident_at is not None and "Turning the transmitter OFF" in text:
            return now >= when + timedelta(seconds=1)
    return ident_at is None and now >= slot + IDENT_START_GRACE


class NewsScheduler:
    def __init__(
        self,
        store: NewsStore,
        events: EventStore,
        player: NewsPlayer,
        media_directory: Path,
        *,
        interval_seconds: float = 5,
        ident_done=hourly_ident_done,
    ) -> None:
        self._store = store
        self._events = events
        self._player = player
        self._media_directory = media_directory
        self._interval = max(1.0, interval_seconds)
        self._ident_done = ident_done
        self._stop = Event()
        self._thread = Thread(target=self._run, name="pi3twe-nieuwsplanner", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval + 1)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._check_once(datetime.now(timezone.utc))

    def _check_once(self, now: datetime) -> None:
        if not self._player.transmit_enabled:
            return
        slot = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        slot_text = slot.isoformat()
        # Only one bulletin per hour: the newest one that is due.
        due = [item for item in self._store.list() if self._store.is_due(item, now)]
        if not due:
            return
        item = max(due, key=lambda entry: entry["id"])
        if not self._ident_done(now):
            return
        if not self._store.claim_hour(item["id"], slot_text):
            return
        try:
            self._player.play(self._media_directory / item["filename"], item["label"])
        except NewsPlaybackError as error:
            message = f"NIEUWS {item['label']} NIET UITGEZONDEN: {error}"
            LOGGER.warning(message)
            self._events.add("nieuws", message)
        except Exception as error:
            LOGGER.exception("Onverwachte fout in nieuwsspeler")
            self._events.add("nieuws", f"NIEUWS {item['label']} STORING: {error}")
        else:
            self._events.add("nieuws", f"NIEUWS {item['label']} UITGEZONDEN")
