from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pi3twe.database import NewsStore


class NewsStoreTest(TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.store = NewsStore(Path(self.temporary_directory.name) / "news.sqlite3")
        self.store.initialize()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_item_is_due_once_at_top_of_each_hour(self) -> None:
        item = self.store.create(
            original_filename="bulletin.mp3",
            suffix=".mp3",
            valid_from="2026-08-02T10:00:00+00:00",
            valid_until="2026-08-03T10:00:00+00:00",
        )
        item = self.store.update(
            item["id"],
            valid_from=item["valid_from"],
            valid_until=item["valid_until"],
            enabled=True,
        )
        now = datetime(2026, 8, 2, 11, 2, tzinfo=timezone.utc)
        self.assertTrue(self.store.is_due(item, now))
        self.assertTrue(self.store.claim_hour(item["id"], "2026-08-02T11:00:00+00:00"))
        self.assertFalse(self.store.claim_hour(item["id"], "2026-08-02T11:00:00+00:00"))
        self.assertFalse(
            self.store.is_due(item, datetime(2026, 8, 2, 11, 5, tzinfo=timezone.utc))
        )

    def test_invalid_period_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.create(
                original_filename="bulletin.mp3",
                suffix=".mp3",
                valid_from="2026-08-03T10:00:00+00:00",
                valid_until="2026-08-02T10:00:00+00:00",
            )
