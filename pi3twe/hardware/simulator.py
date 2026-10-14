"""Temporary indoor and Open-Meteo outdoor sensor simulation."""

from __future__ import annotations

import json
import time
from threading import RLock
from typing import Callable
from urllib.parse import urlencode
from urllib.request import urlopen

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HENGELO_LATITUDE = 52.265
HENGELO_LONGITUDE = 6.793


class SimulatedSensorHardware:
    """Fixed indoor values and cached current weather for Hengelo."""

    def __init__(
        self,
        *,
        cache_seconds: float = 300,
        fetcher: Callable[[str, float], dict[str, object]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cache_seconds = cache_seconds
        self.fetcher = fetcher or _fetch_json
        self.clock = clock
        self._outdoor: dict[str, object] | None = None
        self._last_attempt = float("-inf")
        self._error: str | None = None
        self._lock = RLock()

    def read_all(self) -> dict[str, dict[str, object]]:
        with self._lock:
            now = self.clock()
            if now - self._last_attempt >= self.cache_seconds:
                self._last_attempt = now
                self._refresh_outdoor()
            outdoor = self._outdoor or {
                "name": "Buiten",
                "temperature_c": None,
                "humidity_percent": None,
                "available": False,
                "simulated": True,
                "source": "Open-Meteo Hengelo",
            }
            return {
                "int": {
                    "name": "Binnen",
                    "temperature_c": 20.0,
                    "humidity_percent": 50.0,
                    "available": True,
                    "simulated": True,
                    "source": "Vaste testwaarde",
                },
                "ext": dict(outdoor),
            }

    def health(self) -> dict[str, object]:
        with self._lock:
            return {
                "backend": "simulator",
                "connected": self._outdoor is not None,
                "message": (
                    "Simulatie: Binnen vast; Buiten via Open-Meteo (Hengelo)"
                    if not self._error
                    else f"Open-Meteo tijdelijk niet bereikbaar: {self._error}"
                ),
            }

    def _refresh_outdoor(self) -> None:
        query = urlencode(
            {
                "latitude": HENGELO_LATITUDE,
                "longitude": HENGELO_LONGITUDE,
                "current": "temperature_2m,relative_humidity_2m",
                "timezone": "Europe/Amsterdam",
            }
        )
        try:
            payload = self.fetcher(f"{OPEN_METEO_URL}?{query}", 5.0)
            current = payload["current"]
            temperature = float(current["temperature_2m"])
            humidity = float(current["relative_humidity_2m"])
            if not -80 <= temperature <= 60 or not 0 <= humidity <= 100:
                raise ValueError("meetwaarde buiten geldig bereik")
            self._outdoor = {
                "name": "Buiten",
                "temperature_c": round(temperature, 1),
                "humidity_percent": round(humidity, 1),
                "available": True,
                "simulated": True,
                "source": "Open-Meteo Hengelo",
            }
            self._error = None
        except (KeyError, TypeError, ValueError, OSError) as error:
            self._error = str(error) or type(error).__name__


def _fetch_json(url: str, timeout: float) -> dict[str, object]:
    with urlopen(url, timeout=timeout) as response:  # nosec: fixed trusted API host
        return json.load(response)
