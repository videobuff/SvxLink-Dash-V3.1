#!/usr/bin/python3
"""Install the Rev D interface supervisor without changing the dashboard/plugin."""
from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
TARGET = Path('/usr/local/sbin/pi3twe-svxlink-ptt')
PROFILE = Path('/etc/pi3twe/interface-profile')
SERVICE = 'pi3twe-svxlink.service'

def main():
    if os.geteuid() != 0:
        raise SystemExit('Voer dit script uit met sudo.')
    subprocess.run(['python3', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_revd_interface.py', '-v'], cwd=ROOT, check=True)
    backup = Path('/var/backups/pi3twe-revd-interface') / datetime.now().strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(TARGET, backup / TARGET.name)
    previous = PROFILE.read_bytes() if PROFILE.exists() else None
    if previous is not None:
        (backup / 'interface-profile').write_bytes(previous)
    active = subprocess.run(['systemctl', 'is-active', '--quiet', SERVICE]).returncode == 0
    subprocess.run(['systemctl', 'stop', SERVICE], check=True)
    try:
        temp = TARGET.with_suffix('.new')
        shutil.copy2(ROOT / 'install/pi3twe-svxlink-ptt', temp)
        temp.chmod(0o755)
        os.replace(temp, TARGET)
        PROFILE.write_text('revd\n')
        PROFILE.chmod(0o644)
        if active:
            Path('/run/pi3twe-svxlink/status/ready').unlink(missing_ok=True)
            subprocess.run(['systemctl', 'start', SERVICE], check=True)
            deadline = time.monotonic() + 20
            while not Path('/run/pi3twe-svxlink/status/ready').is_file():
                if time.monotonic() > deadline:
                    raise RuntimeError('SvxLink wordt niet gereed na de interfacewijziging.')
                time.sleep(.2)
    except Exception:
        subprocess.run(['systemctl', 'stop', SERVICE], check=False)
        shutil.copy2(backup / TARGET.name, TARGET)
        if previous is None:
            PROFILE.unlink(missing_ok=True)
        else:
            PROFILE.write_bytes(previous)
        if active:
            subprocess.run(['systemctl', 'start', SERVICE], check=True)
        raise
    print('Rev D-interface ingesteld. USB 2 = continue vrijgave; USB 3 = PTT; USB 4 ongebruikt.')
    print('Softwarematige RX-doorvoer uit; hardware RX-doorvoer blijft actief.')
    print('Backup:', backup)
    print('Bij AAN + Power aan wordt de hardwarevrijgave actief; COR kan dan zenden.')

if __name__ == '__main__':
    main()
