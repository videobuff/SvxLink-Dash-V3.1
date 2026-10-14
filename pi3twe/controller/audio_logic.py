"""Persistent audio policy for the continuously running SvxLink engine."""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from threading import Lock


class AudioLogicError(RuntimeError):
    pass


class LogicSettings:
    DEFAULTS = {
        "rx_audio": True, "callgiver": True, "callsign": "PI3TWE",
        "id_interval_minutes": 10, "news_enabled": False,
        "beep_count": 5, "beep_frequency_hz": 1000,
        "beep_duration_ms": 120, "beep_gap_ms": 120,
    }

    def __init__(self, database: Path, *, news_enabled=False):
        self.database = database
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS audio_logic (id INTEGER PRIMARY KEY CHECK(id=1), settings TEXT NOT NULL)")
            initial = {**self.DEFAULTS, "news_enabled": news_enabled}
            connection.execute("INSERT OR IGNORE INTO audio_logic VALUES (1, ?)", (json.dumps(initial),))

    def read(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            row = connection.execute("SELECT settings FROM audio_logic WHERE id=1").fetchone()
        return {**self.DEFAULTS, **json.loads(row[0])}

    def update(self, data):
        if not isinstance(data, dict):
            raise ValueError("Gebruik een object met logica-instellingen")
        if set(data) - set(self.DEFAULTS):
            raise ValueError("Onbekende logica-instelling")
        values = {**self.read(), **data}
        if values["rx_audio"] is not True or values["callgiver"] is not True:
            raise ValueError("RX-audio en callgever blijven altijd onderdeel van de normale werking")
        if not isinstance(values["news_enabled"], bool):
            raise ValueError("Nieuws toegestaan moet aan of uit zijn")
        if not isinstance(values["callsign"], str) or not re.fullmatch(r"[A-Z0-9]{3,12}(?:/[A-Z0-9]{1,6})?", values["callsign"]):
            raise ValueError("Gebruik een geldige roepletter in hoofdletters")
        for name, low, high in (
            ("id_interval_minutes", 1, 60), ("beep_count", 1, 10),
            ("beep_frequency_hz", 300, 2500), ("beep_duration_ms", 50, 1000),
            ("beep_gap_ms", 50, 1000),
        ):
            value = values[name]
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{name}: kies een geheel getal van {low} tot {high}")
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE audio_logic SET settings=? WHERE id=1", (json.dumps(values),))
        return values


class AudioLogic:
    def __init__(self, settings, mixer, svxlink):
        self.settings = settings
        self.mixer = mixer
        self.svxlink = svxlink
        self._lock = Lock()
        self.phase = "normal"
        self.last_error = None

    @property
    def busy(self):
        return self._lock.locked()

    def state(self):
        engine = self.svxlink.state()
        return {"settings": self.settings.read(), "phase": self.phase,
                "busy": self.busy, "last_error": self.last_error,
                "standby": bool(getattr(self, "mode", None) and self.mode.standby),
                "normal_active": engine["active"] and engine.get("native_ready", False)}

    @contextmanager
    def change(self):
        if not self._lock.acquire(blocking=False):
            raise AudioLogicError("De audio is bezig; wacht tot de nieuwsuitzending is afgerond")
        try:
            yield
        finally:
            self._lock.release()

    @contextmanager
    def news(self):
        with self.change():
            if getattr(self, "mode", None) and self.mode.standby:
                raise AudioLogicError("SvxLink staat in STANDBY of UIT; kies eerst AAN om nieuws uit te zenden")
            state = self.svxlink.state()
            if not state["active"] or not state.get("native_ready", False):
                raise AudioLogicError("Start eerst de normale SvxLink-werking")
            self.last_error = None
            self.phase = "preparing"
            try:
                yield self.settings.read()
            except Exception as error:
                self.last_error = str(error)
                self.phase = "error"
                raise
            else:
                self.phase = "normal"

    def start_normal(self):
        with self.change():
            previous = self.mixer.state()
            try:
                self.mixer.update(enabled=False, input_percent=previous["input_percent"],
                                  monitor_percent=previous["monitor_percent"], master_percent=previous["master_percent"])
                if getattr(self, "mode", None):
                    self.mode.set("aan", self.power_enabled())
                else:
                    self.svxlink.control("start")
            except Exception:
                self.mixer.update(enabled=previous["enabled"], input_percent=previous["input_percent"],
                                  monitor_percent=previous["monitor_percent"], master_percent=previous["master_percent"])
                raise
            self.phase = "normal"
            self.last_error = None
        return self.state()
