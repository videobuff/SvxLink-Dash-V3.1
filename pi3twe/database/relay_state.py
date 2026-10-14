"""Durable desired and observed relay states."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from threading import RLock
from typing import Any


class RelayStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = RLock()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS relay_state (
                    relay_id INTEGER PRIMARY KEY CHECK (relay_id IN (1, 2)),
                    desired_on INTEGER NOT NULL CHECK (desired_on IN (0, 1)),
                    actual_on INTEGER NOT NULL CHECK (actual_on IN (0, 1)),
                    desired_updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def adopt_if_empty(self, states: dict[int, bool]) -> bool:
        with self._lock, closing(self._connect()) as connection, connection:
            if connection.execute("SELECT COUNT(*) FROM relay_state").fetchone()[0]:
                return False
            connection.executemany(
                """
                INSERT INTO relay_state(relay_id, desired_on, actual_on)
                VALUES (?, ?, ?)
                """,
                [(relay_id, int(state), int(state)) for relay_id, state in states.items()],
            )
            return True

    def set_desired(self, relay_id: int, enabled: bool) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE relay_state
                SET desired_on = ?, desired_updated_at = CURRENT_TIMESTAMP
                WHERE relay_id = ?
                """,
                (int(enabled), relay_id),
            )

    def record_actual(self, states: dict[int, bool]) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.executemany(
                """
                UPDATE relay_state
                SET actual_on = ?, observed_at = CURRENT_TIMESTAMP
                WHERE relay_id = ?
                """,
                [(int(state), relay_id) for relay_id, state in states.items()],
            )

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT relay_id, desired_on, actual_on,
                       desired_updated_at, observed_at
                FROM relay_state
                ORDER BY relay_id
                """
            ).fetchall()
        return [
            {
                "id": row["relay_id"],
                "name": (
                    "Repeater POWER" if row["relay_id"] == 1 else "Repeater TX"
                ),
                "desired_on": bool(row["desired_on"]),
                "actual_on": bool(row["actual_on"]),
                "desired_updated_at": row["desired_updated_at"],
                "observed_at": row["observed_at"],
            }
            for row in rows
        ]

    def desired(self) -> dict[int, bool]:
        return {row["id"]: row["desired_on"] for row in self.snapshot()}

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection
