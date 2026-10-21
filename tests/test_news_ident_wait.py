import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from pi3twe.watchdog.news_scheduler import NewsScheduler, hourly_ident_done

SLOT = datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc)


def log_line(when, text):
    return when.astimezone().strftime("%a %b %d %H:%M:%S %Y") + ": " + text + "\n"


class HourlyIdentWaitTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = Path(self.temp.name) / "svxlink.log"

    def write(self, *entries):
        self.log.write_text("".join(log_line(SLOT + timedelta(seconds=s), t) for s, t in entries))

    def done(self, seconds):
        return hourly_ident_done(SLOT + timedelta(seconds=seconds), self.log)

    def test_waits_while_identification_transmits(self):
        self.write((-30, "Tx1: Turning the transmitter OFF"),
                   (0, "RepeaterLogic: Sending long identification..."),
                   (0, "Tx1: Turning the transmitter ON"))
        self.assertFalse(self.done(20))
        self.assertFalse(self.done(60))

    def test_starts_after_identification_finished(self):
        self.write((0, "RepeaterLogic: Sending long identification..."),
                   (0, "Tx1: Turning the transmitter ON"),
                   (38, "Tx1: Turning the transmitter OFF"))
        self.assertFalse(self.done(38))
        self.assertTrue(self.done(40))

    def test_off_before_identification_is_ignored(self):
        self.write((0, "Tx1: Turning the transmitter OFF"),
                   (1, "RepeaterLogic: Sending long identification..."),
                   (1, "Tx1: Turning the transmitter ON"))
        self.assertFalse(self.done(10))

    def test_no_identification_waits_only_grace_period(self):
        self.write((-600, "RepeaterLogic: Sending long identification..."),
                   (-560, "Tx1: Turning the transmitter OFF"))
        self.assertFalse(self.done(5))
        self.assertTrue(self.done(16))

    def test_long_transmission_never_blocks_news(self):
        self.write((0, "RepeaterLogic: Sending long identification..."),
                   (0, "Tx1: Turning the transmitter ON"))
        self.assertTrue(self.done(91))

    def test_missing_log_does_not_block_news(self):
        self.assertTrue(hourly_ident_done(SLOT + timedelta(seconds=16), self.log))

    def test_scheduler_does_not_claim_while_waiting(self):
        store = Mock()
        store.list.return_value = [{"id": 1, "filename": "n.wav", "label": "nieuws"}]
        store.is_due.return_value = True
        player = Mock(transmit_enabled=True)
        scheduler = NewsScheduler(store, Mock(), player, Path(self.temp.name),
                                  ident_done=lambda now: False)
        scheduler._check_once(SLOT + timedelta(seconds=20))
        store.claim_hour.assert_not_called()
        player.play.assert_not_called()


class OneBulletinPerHourTest(unittest.TestCase):
    def scheduler(self, items, claimed=()):
        store = Mock()
        store.list.return_value = items
        store.is_due.side_effect = lambda item, now: item.get("due", True)
        store.claim_hour.side_effect = lambda bulletin_id, slot: bulletin_id not in claimed
        player = Mock(transmit_enabled=True)
        scheduler = NewsScheduler(store, Mock(), player, Path("/tmp"), ident_done=lambda now: True)
        return scheduler, store, player

    def test_only_newest_due_bulletin_is_played(self):
        items = [{"id": 9, "filename": "n9.wav", "label": "nieuws009"},
                 {"id": 7, "filename": "n7.wav", "label": "nieuws007"}]
        scheduler, store, player = self.scheduler(items)
        scheduler._check_once(SLOT + timedelta(seconds=60))
        player.play.assert_called_once_with(Path("/tmp/n9.wav"), "nieuws009")

    def test_newest_not_due_falls_back_to_older(self):
        items = [{"id": 9, "filename": "n9.wav", "label": "nieuws009", "due": False},
                 {"id": 7, "filename": "n7.wav", "label": "nieuws007"}]
        scheduler, store, player = self.scheduler(items)
        scheduler._check_once(SLOT + timedelta(seconds=60))
        player.play.assert_called_once_with(Path("/tmp/n7.wav"), "nieuws007")

    def test_no_second_bulletin_after_newest_played(self):
        items = [{"id": 9, "filename": "n9.wav", "label": "nieuws009"},
                 {"id": 7, "filename": "n7.wav", "label": "nieuws007"}]
        scheduler, store, player = self.scheduler(items, claimed={9})
        scheduler._check_once(SLOT + timedelta(seconds=120))
        player.play.assert_not_called()


if __name__ == "__main__":
    unittest.main()
