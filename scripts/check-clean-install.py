#!/usr/bin/env python3
"""Read-only checks of a provisioned recovery install; no relays or services."""
import configparser
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.build_svxlink import ensure_language_pack, build_svxlink_configuration
from services.version_service import get_svxlink_engine_version

assert get_svxlink_engine_version() == '1.10.2@26.05.2'
assert Path('/var/lib/pi3twe-svxdash/svxlink-standby').read_text().strip() == 'uit'
manifest = json.loads(Path('/usr/local/lib/pi3twe-svxlink/manifest.json').read_text())
for filename, checksum in manifest.items():
    assert hashlib.sha256(Path(filename).read_bytes()).hexdigest() == checksum
model = json.loads(Path('/opt/dashboard/config/node_model.json').read_text())
assert model['language']['default'] == 'nl_NL'
assert not model.get('dashboard_auth')
assert not model.get('echolink', {}).get('enabled')
assert not model.get('reflector', {}).get('enabled')
assert ensure_language_pack(model) == '/usr/share/svxlink/sounds/nl_NL'
result = build_svxlink_configuration(model, restart=False)
assert result['success'], result
assert not result['service_restarted']
config = configparser.ConfigParser(interpolation=None, strict=False)
config.read('/etc/pi3twe/svxlink/svxlink.conf')
assert config['RepeaterLogic']['DEFAULT_LANG'] == 'nl_NL'
assert Path('/etc/pi3twe/svxlink/svxlink.d/ModuleMetarInfo.conf').is_file()
assert Path('/usr/share/svxlink/events.d/local/RepeaterLogicType.tcl').is_file()
for name in ['svxlink-dash.service', 'pi3twe-svxlink.service']:
    assert not list(Path('/etc/systemd/system').glob('*.wants/' + name))
subprocess.run(['visudo', '-cf', '/etc/sudoers.d/svxlink-dash'], check=True)
subprocess.run(['systemd-analyze', 'verify', '/etc/systemd/system/svxlink-dash.service',
                '/etc/systemd/system/pi3twe-svxlink.service'], check=True)
print('Clean install: engine version, ABI, Dutch pack/config after rebuild, modules, sudoers and units OK; mode UIT; no auto-start.')
