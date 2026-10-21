#!/usr/bin/python3
"""Check the CALL/NEWS protocol with dummy RX and TX; never use radio hardware."""
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import time
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory(prefix='pi3twe-native-test-') as directory:
        root = Path(directory)
        status = root / 'status'
        status.mkdir()
        (root / 'modules').mkdir()
        config = root / 'svxlink.conf'
        config.write_text(f'''[GLOBAL]
LOGICS=RepeaterLogic
LOGIC_CORE_PATH={ROOT / '.native-build'}
MODULE_PATH=/usr/local/lib/svxlink
CFG_DIR={root / 'modules'}
CARD_SAMPLE_RATE=48000
[RepeaterLogic]
TYPE=Pi3twe
RX=Rx1
TX=Tx1
CALLSIGN=PI3TWE
EVENT_HANDLER={ROOT / 'install/pi3twe-svxlink-events/events.tcl'}
DEFAULT_LANG=nl_NL
COMMAND_PTY={root / 'command'}
PI3TWE_SPOOL={root}
PI3TWE_STATUS={status}
PI3TWE_RADIO_ENABLED=1
SHORT_IDENT_INTERVAL=0
LONG_IDENT_INTERVAL=0
SHORT_CW_ID_ENABLE=1
SHORT_VOICE_ID_ENABLE=0
SHORT_ANNOUNCE_ENABLE=0
LONG_VOICE_ID_ENABLE=0
CW_CPM=100
CW_PITCH=800
IDLE_TIMEOUT=1
[Rx1]
TYPE=Dummy
[Tx1]
TYPE=Dummy
''')
        env = {**os.environ, 'LD_LIBRARY_PATH': '/usr/local/lib/svxlink:/usr/local/lib'}
        with (root / 'engine.log').open('w+') as log:
            engine = subprocess.Popen(['/usr/local/bin/svxlink', '--config=' + str(config)],
                                      stdout=log, stderr=subprocess.STDOUT, env=env)
            port = None
            try:
                deadline = time.monotonic() + 10
                while not (status / 'call-test-ready').is_file():
                    if engine.poll() is not None or time.monotonic() > deadline:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    time.sleep(.05)
                port = os.open(root / 'command', os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                def send(command, arguments='', token=None):
                    token = token or uuid.uuid4().hex
                    os.write(port, f'{command} {token} {arguments}\n'.encode())
                    return token
                def wait(token, expected, seconds=5):
                    deadline = time.monotonic() + seconds
                    latest = None
                    while time.monotonic() < deadline:
                        try:
                            latest = json.loads((status / (token + '.json')).read_text())
                        except FileNotFoundError:
                            pass
                        if latest and latest['phase'] == expected:
                            return latest
                        time.sleep(.03)
                    raise AssertionError(f'Expected {expected}, got {latest}')
                wait(send('RADIO','0'),'done')
                wait(send('CALL'),'power_off')
                wait(send('RADIO','1'),'done')
                wait(send('CALL','unexpected'),'error')
                call = send('CALL')
                wait(call,'call')
                wait(send('CALL'),'busy')
                wait(send('RADIO','0'),'done')
                wait(call,'cancelled')
                wait(send('RADIO','1'),'done')
                call = send('CALL')
                wait(call,'call')
                wait(call,'done',40)
                token = uuid.uuid4().hex
                with wave.open(str(root / (token + '.wav')), 'wb') as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(16000)
                    audio.writeframes(bytes(3200 * 2))
                send('NEWS','0 200',token)
                wait(token,'done',15)
                log.flush()
                log.seek(0)
                output = log.read()
                assert 'Playing short CW ID' in output, output
                assert 'Failed to load' not in output, output
                print('Native CALL: Power guard, busy guard, argument validation, cancellation and completion OK')
                print('Native NEWS still completes after CALL; RX/TX are Dummy and no EchoLink module is loaded')
            except Exception:
                log.seek(0)
                print(log.read())
                raise
            finally:
                if port is not None:
                    os.close(port)
                engine.terminate()
                try:
                    engine.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    engine.kill()
                    engine.wait()


if __name__ == '__main__':
    main()
