#!/usr/bin/python3
"""Apply plain repeater identification and the requested five-beep cadence."""
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DATABASE = Path('/var/lib/pi3twe-svxdash/pi3twe.sqlite3')
EVENTS = Path('/usr/local/share/pi3twe-svxlink/events.tcl')


def main():
    if os.geteuid() != 0:
        raise SystemExit('Voer dit script uit met sudo.')
    with closing(sqlite3.connect(f'file:{DATABASE}?mode=ro', uri=True)) as db:
        old = json.loads(db.execute('SELECT settings FROM audio_logic WHERE id=1').fetchone()[0])
    if old['callsign'] != 'PI3TWE':
        raise SystemExit('De ingestelde repeater-call is niet PI3TWE; controleer het roepletterveld.')
    try:
        current = json.loads(Path('/run/pi3twe-svxlink/status/current.json').read_text())
    except (OSError, ValueError):
        current = {}
    if current.get('phase') in {'call', 'before_beeps', 'news', 'after_beeps'}:
        raise SystemExit('Wacht tot de huidige test of nieuwsuitzending is afgerond.')
    backup = Path('/var/backups/pi3twe-ident-beeps') / datetime.now().strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(EVENTS, backup / 'events.tcl')
    (backup / 'audio-logic.json').write_text(json.dumps(old, indent=2) + '\n')
    changes = {'beep_count': 5, 'beep_frequency_hz': 600, 'beep_duration_ms': 250, 'beep_gap_ms': 750}
    try:
        shutil.copy2(ROOT / 'install/pi3twe-svxlink-events/events.tcl', EVENTS)
        with closing(sqlite3.connect(DATABASE)) as db, db:
            latest = json.loads(db.execute('SELECT settings FROM audio_logic WHERE id=1').fetchone()[0])
            latest.update(changes)
            db.execute('UPDATE audio_logic SET settings=? WHERE id=1', (json.dumps(latest),))
        subprocess.run(['systemctl', 'restart', 'pi3twe-svxlink.service'], check=True)
    except Exception:
        shutil.copy2(backup / 'events.tcl', EVENTS)
        with closing(sqlite3.connect(DATABASE)) as db, db:
            db.execute('UPDATE audio_logic SET settings=? WHERE id=1', (json.dumps(old),))
        subprocess.run(['systemctl', 'restart', 'pi3twe-svxlink.service'], check=False)
        raise
    print('Repeater-call: alleen PI3TWE, zonder /R. EchoLink-call blijft apart.')
    print('Vijf piepjes: 600 Hz, 250 ms toon + 750 ms pauze = één start per seconde.')
    print('Backup:', backup)


if __name__ == '__main__':
    main()
