"""Hourly news-bulletin scheduler."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread

from pi3twe.audio.news import NewsPlaybackError, NewsPlayer
from pi3twe.database import EventStore, NewsStore

LOGGER = logging.getLogger(__name__)


class NewsScheduler:
    def __init__(
        self,
        store: NewsStore,
        events: EventStore,
        player: NewsPlayer,
        media_directory: Path,
        *,
        interval_seconds: float = 5,
    ) -> None:
        self._store = store
        self._events = events
        self._player = player
        self._media_directory = media_directory
        self._interval = max(1.0, interval_seconds)
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
        for item in self._store.list():
            if not self._store.is_due(item, now):
                continue
            if not self._store.claim_hour(item["id"], slot_text):
                continue
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
