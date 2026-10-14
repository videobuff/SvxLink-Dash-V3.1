#!/usr/bin/python3
"""Install the rebuilt local-call plugin and the tested dashboard buttons."""
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.geteuid() != 0:
        raise SystemExit('Voer dit script uit met sudo.')
    build = ROOT / '.native-build'
    candidate = build / 'Pi3tweLogic.so'
    manifest = json.loads((build / 'abi-manifest.json').read_text())
    for filename, expected in manifest.items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
            raise SystemExit('SvxLink is gewijzigd; bouw de plugin opnieuw tegen de huidige versie.')
    if not candidate.is_file():
        raise SystemExit('De gebouwde native plugin ontbreekt.')
    status = Path('/run/pi3twe-svxlink/status')
    try:
        current = json.loads((status / 'current.json').read_text())
    except (OSError, ValueError):
        current = {}
    if current.get('phase') in {'before_beeps', 'news', 'after_beeps', 'call'}:
        raise SystemExit('Wacht tot de huidige uitzending is afgerond.')
    backup = Path('/var/backups/pi3twe-call-tests') / datetime.now().strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True, mode=0o700)
    destinations = [Path('/usr/local/lib/pi3twe-svxlink/Pi3tweLogic.so'),
                    Path('/usr/local/share/pi3twe-svxlink/events.tcl')]
    for path in destinations:
        shutil.copy2(path, backup / path.name)
    def services(action):
        subprocess.run(['systemctl', action, 'svxlink-dash.service', 'pi3twe-svxlink.service'], check=True)
    services('stop')
    try:
        for source, target in zip([candidate, ROOT / 'install/pi3twe-svxlink-events/events.tcl'], destinations):
            temporary = target.with_suffix(target.suffix + '.new')
            shutil.copy2(source, temporary)
            temporary.chmod(0o644)
            os.replace(temporary, target)
        spec = importlib.util.spec_from_file_location('pi3twe_migrate', ROOT / 'install/migrate-pi3twe-dashboard.py')
        migrate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migrate)
        migrate.main()
        mode_file = Path('/var/lib/pi3twe-svxdash/svxlink-standby')
        operator_off = mode_file.exists() and mode_file.read_text().strip() == 'uit'
        if not operator_off and not (status / 'call-test-ready').is_file():
            raise RuntimeError('De native calltest is na installatie niet gereed.')
    except Exception:
        for path in destinations:
            temporary = path.with_suffix(path.suffix + '.restore')
            shutil.copy2(backup / path.name, temporary)
            os.replace(temporary, path)
        services('restart')
        raise
    print('Test call RPTR en Test nieuws zijn beschikbaar onder PI3TWE.')
    print('Er is tijdens installatie geen testuitzending gestart.')
    print('Native backup:', backup)


if __name__ == '__main__':
    main()
