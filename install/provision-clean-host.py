#!/usr/bin/env python3
"""Provision a fresh host after building SvxLink. Never start radio services."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = Path('/opt/dashboard')
STATE = Path('/var/lib/pi3twe-svxdash')


def main():
    if os.geteuid() != 0:
        raise SystemExit('Gebruik sudo.')
    if TARGET.exists() or Path('/etc/pi3twe').exists():
        raise SystemExit('Alleen voor een schone installatie; niets gewijzigd.')
    subprocess.run(['python3', '-W', 'error::ResourceWarning', '-m', 'unittest', 'discover', '-s', 'tests'],
                   cwd=ROOT, env={**os.environ, 'PI3TWE_CONTROL_ENABLED': '0'}, check=True)
    archive = ROOT / 'assets/nl_NL.tar.xz'
    expected = (ROOT / 'assets/SHA256SUMS').read_text().split()[0]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise SystemExit('Checksum Nederlands geluidspakket onjuist.')
    plugin = ROOT / '.native-build/Pi3tweLogic.so'
    if not plugin.is_file():
        raise SystemExit('Bouw eerst de native plugin.')
    shutil.copytree(ROOT, TARGET, ignore=shutil.ignore_patterns(
        '.git', '__pycache__', '.native-build', '.venv*', '*.sqlite3', '*.sqlite3-*',
        'node_model.json', 'wifi.json', 'talkgroups.json', 'backups', '*.log'))
    for folder in [STATE, STATE / 'news', STATE / 'svxlink-news',
                   TARGET / 'backups', Path('/etc/pi3twe/svxlink/svxlink.d'),
                   Path('/var/lib/svxlink-dash/sounds/idents'), Path('/var/lib/svxlink-dash/backups')]:
        folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'config/node_model.pi3twe.example.json', TARGET / 'config/node_model.json')
    (STATE / 'dashboard-secret').write_text(secrets.token_hex(32) + '\n')
    (STATE / 'dashboard-secret').chmod(0o600)
    (STATE / 'svxlink-standby').write_text('uit\n')
    Path('/etc/pi3twe/pi3twe-stream-source').write_text('sdr\n')
    Path('/etc/pi3twe/interface-profile').write_text('revd\n')
    # Keep the official 26.05.2 event files and modules together.
    share = Path('/usr/share/svxlink')
    share.mkdir(parents=True, exist_ok=True)
    shutil.copytree('/usr/local/share/svxlink', share, dirs_exist_ok=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(share / 'sounds', filter='data')
    local = share / 'events.d/local'
    local.mkdir(exist_ok=True)
    for name in ['Logic.tcl', 'RepeaterLogicType.tcl', 'CW.tcl']:
        shutil.copy2(share / 'events.d' / name, local / name)
    core = Path('/usr/local/lib/pi3twe-svxlink')
    core.mkdir(parents=True, exist_ok=True)
    shutil.copy2(plugin, core / plugin.name)
    files = [Path('/usr/local/bin/svxlink'), Path('/usr/local/lib/svxlink/RepeaterLogic.so')]
    (core / 'manifest.json').write_text(json.dumps({str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, indent=2) + '\n')
    events = Path('/usr/local/share/pi3twe-svxlink')
    events.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'install/pi3twe-svxlink-events/events.tcl', events / 'events.tcl')
    for name in ['pi3twe-svxlink-ptt', 'pi3twe-svxlink-mode-check', 'pi3twe-svxlink-control',
                 'pi3twe-svxlink-audio-init', 'pi3twe-svxlink-check', 'pi3twe-dashboard-control']:
        dest = Path('/usr/local/sbin') / name
        shutil.copy2(ROOT / 'install' / name, dest)
        dest.chmod(0o755)
    for name in ['pi3twe-svxlink.service', 'svxlink-dash.service']:
        shutil.copy2(ROOT / 'install' / name, Path('/etc/systemd/system') / name)
    Path('/etc/systemd/system/pi3twe-audio-init.service').write_text('''[Unit]
Description=PI3TWE analoge audiolus uitschakelen
After=sound.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/pi3twe-svxlink-audio-init
RemainAfterExit=yes
''')
    dropin = Path('/etc/systemd/system/pi3twe-svxlink.service.d')
    dropin.mkdir(exist_ok=True)
    (dropin / 'svxlink26.conf').write_text('[Service]\nEnvironment=LD_LIBRARY_PATH=/usr/local/lib/svxlink:/usr/local/lib\n')
    shutil.copy2(ROOT / 'install/pi3twe-svxdash.tmpfiles', '/etc/tmpfiles.d/pi3twe-svxdash.conf')
    Path('/etc/udev/rules.d/49-pi3twe-relay.rules').write_text(
        'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="16c0", ATTRS{idProduct}=="05df", GROUP="plugdev", MODE="0660"\n')
    commands = ['/usr/local/sbin/pi3twe-svxlink-control ' + x for x in ['start', 'stop', 'restart']]
    commands += ['/usr/local/sbin/pi3twe-dashboard-control ' + x for x in ['restart-all', 'restart-rf', 'reboot', 'shutdown']]
    sudoers = Path('/etc/sudoers.d/svxlink-dash')
    sudoers.write_text('svxlink ALL=(root) NOPASSWD: ' + ', '.join(commands) + '\n')
    sudoers.chmod(0o440)
    subprocess.run(['visudo', '-cf', str(sudoers)], check=True)
    for folder in [TARGET, STATE, Path('/etc/pi3twe'), local, Path('/var/lib/svxlink-dash')]:
        subprocess.run(['chown', '-R', 'svxlink:audio', str(folder)], check=True)
    subprocess.run(['chmod', '-R', 'o-rwx', str(STATE)], check=True)
    # Stock help/parrot configurations are required even when no account is enabled.
    shutil.copytree('/usr/local/etc/svxlink/svxlink.d' if Path('/usr/local/etc/svxlink/svxlink.d').is_dir() else '/etc/svxlink/svxlink.d', '/etc/pi3twe/svxlink/svxlink.d', dirs_exist_ok=True)
    # Generate initial configs without running the upstream deploy/restart flow.
    import sys
    sys.path.insert(0, str(ROOT))
    from services.build_svxlink import render_all
    model = json.loads((TARGET / 'config/node_model.json').read_text())
    for name, text in render_all(model).items():
        dest = Path('/etc/pi3twe/svxlink') / (name if name == 'svxlink.conf' else 'svxlink.d/' + name)
        if not dest.resolve().is_relative_to(Path('/etc/pi3twe/svxlink')):
            raise RuntimeError('Unexpected rendered path: ' + name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        shutil.chown(dest, user='svxlink', group='audio')
    subprocess.run(['chown', '-R', 'svxlink:audio', '/etc/pi3twe'], check=True)
    from pi3twe.controller.audio_logic import LogicSettings
    LogicSettings(STATE / 'pi3twe.sqlite3')
    shutil.chown(STATE / 'pi3twe.sqlite3', user='svxlink', group='audio')
    (STATE / 'pi3twe.sqlite3').chmod(0o660)
    print('Provisioning voltooid. Modus UIT; services NIET gestart of ingeschakeld.')


if __name__ == '__main__':
    main()
