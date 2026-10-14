"""Durable news-bulletin schedules and hourly claim tracking."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


class NewsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = RLock()

    def initialize(self) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS news_bulletins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT UNIQUE NOT NULL,
                    filename TEXT UNIQUE NOT NULL,
                    original_filename TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_until TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
                    last_played_slot TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def create(
        self, *, original_filename: str, suffix: str, valid_from: str, valid_until: str
    ) -> dict[str, Any]:
        self._validate_period(valid_from, valid_until)
        with self._lock, closing(self._connect()) as connection, connection:
            next_number = connection.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM news_bulletins"
            ).fetchone()[0]
            label = f"nieuws{next_number:03d}"
            filename = f"{label}{suffix.lower()}"
            cursor = connection.execute(
                """
                INSERT INTO news_bulletins(
                    label, filename, original_filename, valid_from, valid_until
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (label, filename, original_filename, valid_from, valid_until),
            )
            bulletin_id = cursor.lastrowid
        return self.get(int(bulletin_id))

    def list(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM news_bulletins ORDER BY id DESC"
            ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, bulletin_id: int) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM news_bulletins WHERE id = ?", (bulletin_id,)
            ).fetchone()
        if not row:
            raise ValueError("Nieuwsitem bestaat niet")
        return self._row(row)

    def update(
        self,
        bulletin_id: int,
        *,
        valid_from: str,
        valid_until: str,
        enabled: bool,
    ) -> dict[str, Any]:
        self._validate_period(valid_from, valid_until)
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                UPDATE news_bulletins
                SET valid_from = ?, valid_until = ?, enabled = ?,
                    last_played_slot = CASE WHEN enabled = ? THEN last_played_slot ELSE NULL END
                WHERE id = ?
                """,
                (valid_from, valid_until, int(enabled), int(enabled), bulletin_id),
            )
            if not cursor.rowcount:
                raise ValueError("Nieuwsitem bestaat niet")
        return self.get(bulletin_id)

    def delete(self, bulletin_id: int) -> dict[str, Any]:
        item = self.get(bulletin_id)
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM news_bulletins WHERE id = ?", (bulletin_id,))
        return item

    def claim_hour(self, bulletin_id: int, slot: str) -> bool:
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                UPDATE news_bulletins SET last_played_slot = ?
                WHERE id = ? AND enabled = 1
                  AND (last_played_slot IS NULL OR last_played_slot != ?)
                """,
                (slot, bulletin_id, slot),
            )
            return bool(cursor.rowcount)

    @staticmethod
    def is_due(item: dict[str, Any], now: datetime) -> bool:
        current = now.astimezone(timezone.utc)
        start = datetime.fromisoformat(item["valid_from"])
        end = datetime.fromisoformat(item["valid_until"])
        slot = current.replace(minute=0, second=0, microsecond=0)
        return bool(item["enabled"] and start <= slot < end and current < slot.replace(minute=5))

    @staticmethod
    def _validate_period(valid_from: str, valid_until: str) -> None:
        try:
            start = datetime.fromisoformat(valid_from)
            end = datetime.fromisoformat(valid_until)
        except (TypeError, ValueError) as error:
            raise ValueError("Ongeldige datum of tijd") from error
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("Datum en tijd moeten een tijdzone bevatten")
        if end <= start:
            raise ValueError("'Tot' moet later zijn dan 'vanaf'")

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "label": row["label"],
            "filename": row["filename"],
            "original_filename": row["original_filename"],
            "valid_from": row["valid_from"],
            "valid_until": row["valid_until"],
            "enabled": bool(row["enabled"]),
            "last_played_slot": row["last_played_slot"],
        }

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection
