"""Operator modes; standby survives both POWER changes and service restarts."""
from pathlib import Path
from threading import RLock


class SvxLinkMode:
    def __init__(self, engine, standby_file):
        self.engine = engine
        self.standby_file = Path(standby_file)
        self._lock = RLock()

    @property
    def standby(self):
        try:
            self.standby_file.stat()
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return True  # Fail closed if the operator setting cannot be read.

    def state(self):
        engine = self.engine.state()
        mode = 'uit' if not engine['active'] else 'standby' if self.standby else 'aan'
        return {'mode': mode, 'standby': self.standby, 'engine': engine}

    def set(self, mode, power_enabled):
        if mode not in {'aan', 'standby', 'uit'}:
            raise ValueError('Kies AAN, STANDBY of UIT')
        with self._lock:
            if mode == 'aan':
                self.standby_file.unlink(missing_ok=True)
            else:
                temporary = self.standby_file.with_suffix('.tmp')
                temporary.write_text(mode + '\n')
                temporary.replace(self.standby_file)
            engine = self.engine.state()
            if mode == 'uit':
                # Stop must remain possible even if the native command port fails.
                if engine.get('native_ready'):
                    try:
                        self.engine.radio_power(False)
                    except (RuntimeError, OSError):
                        pass
                self.engine.control('stop')
            elif not engine['active']:
                self.engine.control('start')
            elif engine.get('native_ready'):
                self.engine.radio_power(bool(power_enabled) and mode == 'aan')
            return self.state()
