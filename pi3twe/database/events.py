"""Small, durable SQLite event log with Dutch presentation."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class EventStore:
    def __init__(
        self, path: Path, *, timezone_name: str = "Europe/Amsterdam"
    ) -> None:
        self.path = path
        self._lock = RLock()
        try:
            self._timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Onbekende tijdzone: {timezone_name}") from error

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    category TEXT NOT NULL,
                    message TEXT NOT NULL
                )
                """
            )
            rows = connection.execute("SELECT id, message FROM events").fetchall()
            for row in rows:
                normalized = normalize_message(row["message"])
                if normalized != row["message"]:
                    connection.execute(
                        "UPDATE events SET message = ? WHERE id = ?",
                        (normalized, row["id"]),
                    )

    def add(self, category: str, message: str) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO events(category, message) VALUES (?, ?)",
                (category, normalize_message(message)),
            )

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 100))
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, category, message
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "created_at": self._format_timestamp(row["created_at"]),
                "created_at_utc": f"{row['created_at']}Z",
                "category": row["category"],
                "message": normalize_message(row["message"]),
            }
            for row in rows
        ]

    def _format_timestamp(self, value: str) -> str:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(self._timezone).strftime("%d-%m-%Y %H:%M:%S")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection


def normalize_message(message: str) -> str:
    compact = " ".join(str(message).strip().split())
    relay_match = re.fullmatch(
        r"relay=([12])\s+state=(ON|OFF)", compact, flags=re.IGNORECASE
    )
    if relay_match:
        label = "REPEATER POWER" if relay_match.group(1) == "1" else "REPEATER TX"
        return f"{label} {relay_match.group(2).upper()}"

    named_relay_match = re.fullmatch(
        r"(?:REPEATER\s+POWER|TX|REPEATER\s+TX)\s+(ON|OFF)",
        compact,
        flags=re.IGNORECASE,
    )
    if named_relay_match:
        prefix = (
            "REPEATER POWER"
            if compact.upper().startswith("REPEATER POWER")
            else "REPEATER TX"
        )
        return f"{prefix} {named_relay_match.group(1).upper()}"

    login_match = re.fullmatch(r"Login:\s*(.+)", compact, flags=re.IGNORECASE)
    if login_match:
        return f"INLOGGEN: {login_match.group(1)}"
    logout_match = re.fullmatch(r"Logout:\s*(.+)", compact, flags=re.IGNORECASE)
    if logout_match:
        return f"UITLOGGEN: {logout_match.group(1)}"
    if compact.casefold() == "login mislukt":
        return "INLOGGEN MISLUKT"
    return compact
