"""Own radio policy and background tasks within the single dashboard process."""
import atexit
import fcntl
import logging
import os
from pathlib import Path
from threading import Event, Lock, Thread

from .audio.mixer import AudioMixer
from .audio.news import NewsPlayer
from .controller import Controller
from .controller.audio_logic import AudioLogic, LogicSettings
from .controller.rf_monitor import RfMonitor
from .controller.stream_source import StreamSource
from .controller.svxlink import SvxLink
from .controller.svxlink_mode import SvxLinkMode
from .database import EventStore, NewsStore, RelayStateStore
from .hardware.factory import create_hardware
from .relay import RelayService
from .watchdog.news_scheduler import NewsScheduler
from .watchdog.relay_monitor import RelayMonitor
from .watchdog.system_monitor import SystemMonitor


class Runtime:
    def __init__(self, directory, *, hardware=None, engine=None, mixer=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / 'pi3twe.sqlite3'
        self.media = self.directory / 'news'
        self.media.mkdir(exist_ok=True)
        self.events = EventStore(self.database)
        self.news = NewsStore(self.database)
        self.relay_states = RelayStateStore(self.database)
        for store in [self.events, self.news, self.relay_states]:
            store.initialize()
        self.hardware = hardware or create_hardware(os.environ.get('PI3TWE_HARDWARE_BACKEND', 'dummy'))
        self.controller = Controller(self.hardware, RelayService(self.hardware.relays, 3), self.events, self.relay_states)
        self.engine = engine or SvxLink(control_command=('sudo', '-n', '/usr/local/sbin/pi3twe-svxlink-control'))
        self.mode = SvxLinkMode(self.engine, self.directory / 'svxlink-standby')
        self.settings = LogicSettings(self.database)
        self.mixer = mixer or AudioMixer()
        self.logic = AudioLogic(self.settings, self.mixer, self.engine)
        self.logic.mode = self.mode
        self.logic.power_enabled = lambda: self.controller.relays.physical_states()[1]
        self.player = NewsPlayer(transmit_enabled=self.settings.read()['news_enabled'],
                                 svxlink=self.engine, logic=self.logic,
                                 spool_directory=self.directory / 'svxlink-news')
        self.stream = StreamSource()
        self.rf = RfMonitor(restart_command=('sudo', '-n', '/usr/local/sbin/pi3twe-dashboard-control', 'restart-rf'))
        self._play_lock = Lock()
        self._edit_lock = Lock()
        self._pending = None
        self._stop = Event()
        self._threads = []
        self._owner = None
        self.controller.radio_control = self._radio_power

    def _radio_power(self, enabled):
        if self.engine.state().get('native_ready'):
            self.engine.radio_power(enabled and not self.mode.standby)

    def start(self):
        # Refuse a second scheduler/relay reconciler, even with multiple WSGI workers.
        self._owner = (self.directory / 'dashboard-runtime.lock').open('a+')
        try:
            fcntl.flock(self._owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self._owner.close()
            self._owner = None
            raise RuntimeError('PI3TWE-bediening draait al in een ander proces') from error
        self.controller.initialize_relay_state()
        self._monitors = [RelayMonitor(self.controller, self.events, 2),
                          SystemMonitor(self.events, 10),
                          NewsScheduler(self.news, self.events, self.player, self.media)]
        for monitor in self._monitors:
            monitor.start()
        thread = Thread(target=self._policy_monitor, name='pi3twe-policy', daemon=True)
        thread.start()
        self._threads.append(thread)
        self.events.add('systeem', 'PI3TWE BEDIENING GESTART IN SVXDASH')
        atexit.register(self.stop)

    def stop(self):
        self._stop.set()
        for monitor in getattr(self, '_monitors', []):
            monitor.stop()
        for thread in self._threads:
            thread.join(timeout=3)
        if self._owner:
            self._owner.close()
            self._owner = None

    def _policy_monitor(self):
        applied = None
        while not self._stop.wait(2):
            try:
                stamp = (self.engine.status_directory / 'ready').stat().st_mtime_ns
                settings = self.settings.read()
                target = (stamp, settings['callsign'], settings['id_interval_minutes'])
                if target != applied:
                    self.engine.apply_policy(settings)
                    applied = target
            except (OSError, RuntimeError):
                logging.getLogger(__name__).debug('Waiting for SvxLink policy port')

    @property
    def busy(self):
        return self._pending is not None or self.player.busy

    def play(self, bulletin_id):
        with self._edit_lock:
            if not self.player.transmit_enabled:
                raise ValueError('Schakel eerst nieuwsuitzendingen in')
            if not self._play_lock.acquire(blocking=False):
                raise ValueError('Er wordt al een nieuwsbulletin uitgezonden')
            try:
                item = self.news.get(bulletin_id)
                if not self.controller.relays.physical_states()[1]:
                    raise ValueError('Repeater Power staat uit')
                state = self.mode.state()
                if state['mode'] != 'aan' or not state['engine'].get('native_ready'):
                    raise ValueError('Zet SvxLink eerst op AAN')
                if self.player.busy:
                    raise ValueError('Er wordt al een nieuwsbulletin uitgezonden')
                self._pending = item['label']
            except Exception:
                self._play_lock.release()
                raise
            def run():
                try:
                    self.player.play(self.media / item['filename'], item['label'])
                except Exception as error:
                    self.events.add('nieuws', f"NIEUWS {item['label']} MISLUKT: {error}")
                else:
                    self.events.add('nieuws', f"NIEUWS {item['label']} HANDMATIG UITGEZONDEN")
                finally:
                    self._pending = None
                    self._play_lock.release()
            Thread(target=run, name='pi3twe-manual-news', daemon=True).start()
            return item

    def test_call(self):
        with self._edit_lock:
            state = self.mode.state()
            if not self.controller.relays.physical_states()[1]:
                raise ValueError('Repeater Power staat uit')
            if state['mode'] != 'aan' or not state['engine'].get('native_ready'):
                raise ValueError('Zet SvxLink eerst op AAN')
            if not state['engine'].get('call_test_available'):
                raise ValueError('Installeer eerst de uitbreiding voor Test call RPTR')
            if self.player.busy or not self._play_lock.acquire(blocking=False):
                raise ValueError('Er is al een uitzending actief')
            self._pending = 'Callgever RPTR'
            def run():
                try:
                    with self.logic.change():
                        self.logic.phase = 'call'
                        self.engine.test_repeater_call()
                except Exception as error:
                    self.logic.last_error = str(error)
                    self.events.add('test', 'CALL RPTR TEST MISLUKT: ' + str(error))
                else:
                    self.logic.last_error = None
                    self.events.add('test', 'CALL RPTR TEST AFGEROND')
                finally:
                    self.logic.phase = 'normal'
                    self._pending = None
                    self._play_lock.release()
            Thread(target=run, name='pi3twe-repeater-call-test', daemon=True).start()
            self.events.add('test', 'CALL RPTR TEST GESTART')

    def delete(self, bulletin_id):
        with self._edit_lock:
            item = self.news.get(bulletin_id)
            if item['label'] in {self._pending, self.player.current_label}:
                raise ValueError('Dit bulletin wordt nu uitgezonden')
            self.news.delete(bulletin_id)
            (self.media / item['filename']).unlink(missing_ok=True)
            self.events.add('nieuws', f"NIEUWS {item['label']} VERWIJDERD")

    def update_settings(self, data):
        with self.logic.change():
            previous = self.settings.read()
            settings = self.settings.update(data)
            try:
                if self.engine.state().get('native_ready'):
                    self.engine.apply_policy(settings)
            except Exception:
                self.settings.update(previous)
                raise
            self.player.transmit_enabled = settings['news_enabled']
            self.events.add('beheer', 'NIEUWS- EN CALLGEVERINSTELLINGEN GEWIJZIGD')
            return settings

    def state(self):
        output = {'radio': self.controller.state(), 'mode': self.mode.state(),
                  'logic': self.logic.state(), 'news_busy': self.busy,
                  'current_news': self._pending or self.player.current_label,
                  'events': self.events.recent(20)}
        for name, source in [('audio', self.mixer), ('stream', self.stream), ('rf', self.rf)]:
            try:
                output[name] = source.state()
            except (RuntimeError, OSError) as error:
                output[name] = {'error': str(error)}
        return output
