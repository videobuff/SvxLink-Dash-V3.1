import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
from flask import Flask

from pi3twe.routes import bp
from pi3twe.runtime import Runtime
from pi3twe.hardware.factory import create_hardware
from pi3twe.watchdog.news_scheduler import NewsScheduler
from datetime import datetime, timezone


class ControlsTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = Mock()
        self.engine.state.return_value = {'active': True, 'native_ready': True}
        self.engine.status_directory = Path(self.temp.name) / 'status'
        self.rt = Runtime(self.temp.name, hardware=create_hardware('dummy'), engine=self.engine, mixer=Mock())
        self.rt.controller.initialize_relay_state()
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='test-only')
        self.app.register_blueprint(bp)
        self.app.extensions['pi3twe'] = self.rt
        self.client = self.app.test_client()
        self.headers = {'X-CSRF-Token': 'test-token'}
        with self.client.session_transaction() as session:
            session['authorised'] = True
            session['pi3twe_csrf'] = 'test-token'

    def request(self, path, method='POST', **kwargs):
        return self.client.open('/pi3twe/api/' + path, method=method, headers=self.headers, **kwargs)

    def bulletin(self):
        return self.rt.news.create(original_filename='bulletin.wav', suffix='.wav',
                                   valid_from='2026-10-14T00:00:00+00:00', valid_until='2026-10-21T00:00:00+00:00')

    def test_power_reaches_physical_relay_and_persists(self):
        self.assertEqual(self.request('power/on').status_code, 200)
        self.assertTrue(self.rt.hardware.relays.get_state(1))
        self.assertTrue(self.rt.relay_states.desired()[1])
        self.assertEqual(self.request('power/off').status_code, 200)
        self.assertFalse(self.rt.hardware.relays.get_state(1))
        self.assertFalse(self.rt.relay_states.desired()[1])
        self.engine.radio_power.assert_called_with(False)

    def test_no_direct_tx_control(self):
        self.assertEqual(self.request('power/tx').status_code, 400)
        self.assertFalse(self.rt.hardware.relays.get_state(2))

    def test_auth_and_csrf_before_any_hardware_action(self):
        self.assertEqual(self.client.post('/pi3twe/api/power/on').status_code, 403)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.request('power/on').status_code, 401)
        self.assertFalse(self.rt.hardware.relays.get_state(1))

    def test_mode_off_persists_flag_and_stops_engine(self):
        self.assertEqual(self.request('mode/uit').status_code, 200)
        self.assertEqual((self.rt.directory / 'svxlink-standby').read_text(), 'uit\n')
        self.engine.control.assert_called_with('stop')

    def test_standby_survives_power_on(self):
        self.request('mode/standby')
        self.request('power/on')
        self.engine.radio_power.assert_called_with(False)
        self.assertTrue(self.rt.mode.standby)

    def test_news_upload_validates_audio_and_starts_disabled(self):
        with patch('pi3twe.routes.validate_audio') as validator:
            response = self.request('news', data={'audio': (io.BytesIO(b'test audio'), 'my.wav'),
                                    'valid_from': '2026-10-14T10:00', 'valid_until': '2026-10-21T10:00'})
        self.assertEqual(response.status_code, 201)
        validator.assert_called_once()
        item = response.json['item']
        self.assertFalse(item['enabled'])
        self.assertEqual(item['valid_from'], '2026-10-14T08:00:00+00:00')
        self.assertTrue((self.rt.media / item['filename']).exists())

    def test_invalid_upload_leaves_no_record_or_file(self):
        with patch('pi3twe.routes.validate_audio', side_effect=ValueError('Invalid audio')):
            response = self.request('news', data={'audio': (io.BytesIO(b'invalid'), 'file.wav'),
                                    'valid_from': '2026-10-14T10:00', 'valid_until': '2026-10-21T10:00'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rt.news.list(), [])
        self.assertEqual(list(self.rt.media.iterdir()), [])

    def test_failed_final_save_rolls_back_metadata(self):
        with patch('pi3twe.routes.validate_audio'), patch('pi3twe.routes.os.replace', side_effect=OSError('Disk full')):
            response = self.request('news', data={'audio': (io.BytesIO(b'audio'), 'file.wav'),
                                    'valid_from': '2026-10-14T10:00', 'valid_until': '2026-10-21T10:00'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.rt.news.list(), [])

    def test_invalid_period_does_not_save_upload(self):
        response = self.request('news', data={'audio': (io.BytesIO(b'audio'), 'file.wav'),
                                 'valid_from': '2026-10-21T10:00', 'valid_until': '2026-10-14T10:00'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rt.news.list(), [])

    def test_manual_news_requires_permission_power_and_engine(self):
        item = self.bulletin()
        self.assertEqual(self.request(f"news/{item['id']}/play").status_code, 400)
        self.rt.player.transmit_enabled = True
        self.assertEqual(self.request(f"news/{item['id']}/play").status_code, 400)
        self.rt.controller.set_relay(1, True)
        self.engine.state.return_value = {'active': False, 'native_ready': False}
        self.assertEqual(self.request(f"news/{item['id']}/play").status_code, 400)

    def test_delete_is_blocked_for_current_news(self):
        item = self.bulletin()
        self.rt._pending = item['label']
        self.assertEqual(self.request(f"news/{item['id']}", method='DELETE').status_code, 400)
        self.assertEqual(len(self.rt.news.list()), 1)

    def test_policy_failure_restores_settings(self):
        old = self.rt.settings.read()
        self.engine.apply_policy.side_effect = RuntimeError('No reply')
        response = self.request('logic', method='PUT', json={'news_enabled': True})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.rt.settings.read(), old)
        self.assertFalse(self.rt.player.transmit_enabled)

    def test_hourly_claim_survives_new_runtime(self):
        item = self.bulletin()
        self.rt.news.update(item['id'], valid_from=item['valid_from'], valid_until=item['valid_until'], enabled=True)
        player = Mock(transmit_enabled=True)
        scheduler = NewsScheduler(self.rt.news, self.rt.events, player, self.rt.media)
        now = datetime(2026, 10, 14, 11, 1, tzinfo=timezone.utc)
        scheduler._check_once(now)
        reopened = Runtime(self.temp.name, hardware=create_hardware('dummy'), engine=self.engine, mixer=Mock())
        scheduler = NewsScheduler(reopened.news, reopened.events, player, reopened.media)
        scheduler._check_once(now)
        player.play.assert_called_once()

    def test_analog_feedback_is_rejected_while_svxlink_runs(self):
        response = self.request('audio', method='PUT', json={'enabled': True})
        self.assertEqual(response.status_code, 400)
        self.rt.mixer.update.assert_not_called()
        response = self.request('stream', method='PUT', json={'stream_source': 'analog'})
        self.assertEqual(response.status_code, 400)

    def test_only_one_scheduler_process_may_start(self):
        self.rt.start()
        self.addCleanup(self.rt.stop)
        second = Runtime(self.temp.name, hardware=create_hardware('dummy'), engine=self.engine, mixer=Mock())
        with self.assertRaises(RuntimeError):
            second.start()
        self.assertIsNone(second._owner)

    def test_metrics_preserves_existing_metric_names(self):
        from pi3twe.metrics import prometheus_metrics
        text = prometheus_metrics(self.rt.controller.state())
        self.assertIn('pi3twe_relay_on{relay="1",name="Repeater POWER"}', text)
        self.assertIn('pi3twe_nuc_uptime_seconds', text)

    def test_call_requires_power_normal_mode_and_native_capability(self):
        response = self.request('test/call')
        self.assertEqual(response.status_code, 400)
        self.rt.controller.set_relay(1, True)
        response = self.request('test/call')
        self.assertEqual(response.status_code, 400)
        self.engine.test_repeater_call.assert_not_called()

    def test_call_does_not_depend_on_news_permission_or_touch_echolink(self):
        from threading import Event
        entered = Event()
        release = Event()
        finished = Event()
        self.rt.controller.set_relay(1, True)
        self.engine.state.return_value = {'active': True, 'native_ready': True, 'call_test_available': True}
        def play_call():
            entered.set()
            release.wait(2)
            finished.set()
        self.engine.test_repeater_call.side_effect = play_call
        try:
            response = self.request('test/call')
            self.assertEqual(response.status_code, 202)
            self.assertTrue(entered.wait(1))
            self.assertTrue(self.rt.busy)
            self.assertFalse(self.rt.player.transmit_enabled)
            self.assertEqual(self.request('test/call').status_code, 400)
            self.engine.control.assert_not_called()
            self.engine.test_repeater_call.assert_called_once()
        finally:
            release.set()
            self.assertTrue(finished.wait(1))
            self.rt._play_lock.acquire(timeout=1)
            self.rt._play_lock.release()

    def test_call_endpoint_rejects_missing_csrf(self):
        self.assertEqual(self.client.post('/pi3twe/api/test/call').status_code, 403)
        self.engine.test_repeater_call.assert_not_called()
