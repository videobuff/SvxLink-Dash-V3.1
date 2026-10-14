#!/usr/bin/python3
"""Migrate the existing PI3TWE NUC to the integrated SvxDash, preserving local data."""
from contextlib import closing
from datetime import datetime
import grp
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TARGET = Path('/opt/dashboard')
STATE = Path('/var/lib/pi3twe-svxdash')
OLD = Path('/opt/pi3twe/pi3twe-controller/database')


def run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True)


def user_service(*args, check=True):
    account = pwd.getpwnam('erik')
    return run('/usr/sbin/runuser', '-u', 'erik', '--', '/usr/bin/env',
               f'XDG_RUNTIME_DIR=/run/user/{account.pw_uid}',
               f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{account.pw_uid}/bus',
               '/usr/bin/systemctl', '--user', *args, check=check)


def copy_file(source, target, mode=0o644):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(mode)


def main():
    if os.geteuid() != 0:
        raise SystemExit('Voer dit migratiescript uit met sudo.')
    for filename in ['app.py', 'pi3twe/runtime.py', 'templates/pi3twe.html', 'static/pi3twe.js']:
        if not (ROOT / filename).is_file():
            raise SystemExit('Ontbrekende broncode: ' + filename)
    # Complete checks before stopping the running installation.
    test_env = {**os.environ, 'PI3TWE_CONTROL_ENABLED': '0'}
    subprocess.run(['/usr/bin/python3', '-W', 'error::ResourceWarning', '-m', 'unittest',
                    'discover', '-s', 'tests', '-v'], cwd=ROOT, env=test_env, check=True, capture_output=True, text=True)
    for executable in ['/usr/bin/ffmpeg', '/usr/bin/ffprobe', '/usr/bin/usbrelay', '/usr/local/bin/svxlink']:
        if not Path(executable).is_file():
            raise SystemExit('Benodigd programma ontbreekt: ' + executable)
    try:
        current = json.loads(Path('/run/pi3twe-svxlink/status/current.json').read_text())
    except (OSError, ValueError):
        current = {}
    if current.get('phase') in {'before_beeps', 'news', 'after_beeps'}:
        raise SystemExit('Er speelt nieuws. Wacht tot de uitzending is afgerond.')
    account = pwd.getpwnam('svxlink')
    audio_group = grp.getgrnam('audio').gr_gid
    backup = Path('/var/backups/pi3twe-svxdash') / datetime.now().strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True, mode=0o700)
    backup.chmod(0o700)
    saved_files = {}
    paths = ['/etc/systemd/system/svxlink-dash.service', '/etc/systemd/system/pi3twe-svxlink.service',
             '/etc/sudoers.d/svxlink-dash', '/etc/tmpfiles.d/pi3twe-svxdash.conf',
             '/etc/apache2/sites-available/pi3twe.conf', '/etc/prometheus/prometheus.yml']
    helpers = ['pi3twe-svxlink-ptt', 'pi3twe-svxlink-mode-check', 'pi3twe-svxlink-control', 'pi3twe-dashboard-control']
    paths += ['/usr/local/sbin/' + name for name in helpers]
    for filename in paths:
        p = Path(filename)
        if p.is_file():
            copy = backup / filename.strip('/').replace('/', '__')
            shutil.copy2(p, copy)
            saved_files[filename] = str(copy)
        else:
            saved_files[filename] = None
    (backup / 'files.json').write_text(json.dumps(saved_files, indent=2))
    shutil.copytree(TARGET, backup / 'dashboard', ignore=shutil.ignore_patterns('__pycache__', '.git'))
    old_enabled = run('/usr/bin/systemctl', 'is-enabled', 'pi3twe.service', check=False).stdout.strip() == 'enabled'
    old_user_enabled = user_service('is-enabled', 'pi3twe-svxlink-dash.service', check=False).stdout.strip() == 'enabled'
    old_mic_enabled = user_service('is-enabled', 'pi3twe-mic-gain.service', check=False).stdout.strip() == 'enabled'
    state_existed = STATE.exists()
    old_identity = {}
    for directory in ['/run/pi3twe-transmitter', '/var/log/pi3twe-svxlink', '/run/pi3twe-svxlink']:
        d = Path(directory)
        if d.exists():
            for p in [d, *d.rglob('*')]:
                if not p.is_symlink():
                    st = p.stat()
                    old_identity[str(p)] = [st.st_uid, st.st_gid, st.st_mode & 0o7777]
    for p in [TARGET, *TARGET.rglob('*')]:
        if not p.is_symlink():
            st = p.stat()
            old_identity[str(p)] = [st.st_uid, st.st_gid, st.st_mode & 0o7777]
    for filename in ['/etc/pi3twe/pi3twe-stream-source', '/etc/pi3twe/pi3twe-rf-monitor.conf']:
        p = Path(filename)
        if p.exists():
            st = p.stat()
            old_identity[filename] = [st.st_uid, st.st_gid, st.st_mode & 0o7777]
    (backup / 'identities.json').write_text(json.dumps(old_identity))
    try:
        user_service('stop', 'pi3twe-svxlink-dash.service')
        run('/usr/bin/systemctl', 'stop', 'svxlink-dash.service', 'pi3twe.service', 'pi3twe-svxlink.service')
        STATE.mkdir(mode=0o770, exist_ok=True)
        if not (STATE / 'pi3twe.sqlite3').exists() and (OLD / 'pi3twe.sqlite3').exists():
            with closing(sqlite3.connect(f'file:{OLD / "pi3twe.sqlite3"}?mode=ro', uri=True)) as source, \
                 closing(sqlite3.connect(STATE / 'pi3twe.sqlite3')) as destination:
                source.backup(destination)
        if not (STATE / 'news').exists():
            if (OLD / 'news').is_dir():
                shutil.copytree(OLD / 'news', STATE / 'news')
            else:
                (STATE / 'news').mkdir()
        (STATE / 'svxlink-news').mkdir(exist_ok=True)
        if not state_existed and (OLD / 'svxlink-standby').exists():
            shutil.copy2(OLD / 'svxlink-standby', STATE / 'svxlink-standby')
        if not (STATE / 'dashboard-secret').exists():
            (STATE / 'dashboard-secret').write_text(secrets.token_hex(32) + '\n')
        for p in [STATE, *STATE.rglob('*')]:
            os.chown(p, account.pw_uid, audio_group)
            p.chmod(0o770 if p.is_dir() else 0o660)
        (STATE / 'dashboard-secret').chmod(0o600)
        tracked = run('/usr/bin/git', '-c', f'safe.directory={ROOT}', '-C', str(ROOT), 'ls-files', '-z').stdout.split('\0')
        for relative in filter(None, tracked):
            if relative.startswith('config/') and '.example.' not in relative:
                continue
            src = ROOT / relative
            if not src.is_file():
                continue
            dst = TARGET / relative
            copy_file(src, dst, src.stat().st_mode & 0o777)
            os.chown(dst, account.pw_uid, audio_group)
        for directory in ['pi3twe', 'templates', 'static', 'services', 'models', 'hw_platforms', 'renderers']:
            for p in (TARGET / directory).rglob('__pycache__/*.pyc'):
                p.unlink()  # Discard interpreter cache; no runtime data.
        for name in helpers:
            copy_file(ROOT / 'install' / name, '/usr/local/sbin/' + name, 0o755)
        for service in ['svxlink-dash.service', 'pi3twe-svxlink.service']:
            copy_file(ROOT / 'install' / service, '/etc/systemd/system/' + service)
        copy_file(ROOT / 'install/pi3twe-svxdash.tmpfiles', '/etc/tmpfiles.d/pi3twe-svxdash.conf')
        run('/usr/bin/systemd-tmpfiles', '--create', '/etc/tmpfiles.d/pi3twe-svxdash.conf')
        for directory in ['/run/pi3twe-transmitter', '/var/log/pi3twe-svxlink', '/run/pi3twe-svxlink']:
            d = Path(directory)
            if d.exists():
                for p in [d, *d.rglob('*')]:
                    if not p.is_symlink():
                        os.chown(p, account.pw_uid, audio_group)
                d.chmod(0o770 if directory.endswith('transmitter') else 0o750)
        Path('/run/pi3twe-transmitter/route.lock').chmod(0o660)
        for filename in ['/etc/pi3twe/pi3twe-stream-source', '/etc/pi3twe/pi3twe-rf-monitor.conf']:
            p = Path(filename)
            if p.exists():
                os.chown(p, account.pw_uid, audio_group)
                p.chmod(0o660)
        sudoers = Path('/etc/sudoers.d/svxlink-dash')
        sudoers.write_text('svxlink ALL=(root) NOPASSWD: ' + ', '.join([
            '/usr/local/sbin/pi3twe-svxlink-control ' + action for action in ['start', 'stop', 'restart']
        ] + ['/usr/local/sbin/pi3twe-dashboard-control ' + action for action in ['restart-all', 'restart-rf', 'reboot', 'shutdown']]) + '\n')
        sudoers.chmod(0o440)
        run('/usr/sbin/visudo', '-cf', str(sudoers))
        run('/usr/bin/systemctl', 'daemon-reload')
        run('/usr/bin/systemctl', 'start', 'pi3twe-svxlink.service')
        run('/usr/bin/systemctl', 'start', 'svxlink-dash.service')
        # Authenticate only for a read-only health check; never print cookies/secrets.
        from flask import Flask
        probe_app = Flask('migration-probe')
        probe_app.secret_key = (STATE / 'dashboard-secret').read_text().strip()
        cookie = probe_app.session_interface.get_signing_serializer(probe_app).dumps({'authorised': True})
        last_error = None
        for attempt in range(30):
            try:
                request = urllib.request.Request('http://127.0.0.1:5000/pi3twe/api/state', headers={'Cookie': 'session=' + cookie})
                with urllib.request.urlopen(request, timeout=3) as response:
                    health = json.load(response)
                if not health.get('ok') or health['radio']['hardware_backend'] != 'usbrelay':
                    raise RuntimeError('Het nieuwe dashboard is niet gereed')
                off = (STATE / 'svxlink-standby').exists() and (STATE / 'svxlink-standby').read_text().strip() == 'uit'
                if not off and not health['mode']['engine'].get('native_ready'):
                    raise RuntimeError('Wachten op de SvxLink-engine')
                break
            except Exception as error:
                last_error = error
                time.sleep(1)
        else:
            raise RuntimeError('Dashboardcontrole mislukt: ' + str(last_error))
        if not (STATE / 'svxlink-standby').exists() or (STATE / 'svxlink-standby').read_text().strip() != 'uit':
            if not health['mode']['engine'].get('native_ready'):
                raise RuntimeError('SvxLink is na de migratie niet gereed')
        apache = Path('/etc/apache2/sites-available/pi3twe.conf')
        if apache.exists():
            apache.write_text(apache.read_text().replace('http://127.0.0.1:3001/', 'http://127.0.0.1:5000/'))
            run('/usr/sbin/apache2ctl', 'configtest')
            run('/usr/bin/systemctl', 'reload', 'apache2.service')
        prometheus = Path('/etc/prometheus/prometheus.yml')
        if prometheus.exists():
            prometheus.write_text(prometheus.read_text().replace('127.0.0.1:3001', '127.0.0.1:5000'))
            run('/usr/bin/systemctl', 'try-reload-or-restart', 'prometheus.service')
        run('/usr/bin/systemctl', 'disable', 'pi3twe.service')
        user_service('disable', 'pi3twe-svxlink-dash.service')
        user_service('disable', '--now', 'pi3twe-mic-gain.service')
        run('/usr/bin/systemctl', 'enable', 'svxlink-dash.service')
    except Exception:
        print('Migratie mislukt. De vorige installatie wordt hersteld.', file=sys.stderr)
        run('/usr/bin/systemctl', 'stop', 'svxlink-dash.service', 'pi3twe-svxlink.service', check=False)
        for filename, saved in saved_files.items():
            p = Path(filename)
            if saved:
                shutil.copy2(saved, p)
            elif p.exists():
                p.unlink()
        for src in (backup / 'dashboard').rglob('*'):
            if src.is_file():
                dst = TARGET / src.relative_to(backup / 'dashboard')
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        for filename, (uid, gid, mode) in old_identity.items():
            p = Path(filename)
            if p.exists() and not p.is_symlink():
                os.chown(p, uid, gid)
                p.chmod(mode)
        run('/usr/bin/systemctl', 'daemon-reload', check=False)
        run('/usr/bin/systemctl', 'start', 'pi3twe.service', 'pi3twe-svxlink.service', 'svxlink-dash.service', check=False)
        if old_enabled:
            run('/usr/bin/systemctl', 'enable', 'pi3twe.service', check=False)
        user_service('start', 'pi3twe-svxlink-dash.service', check=False)
        if old_user_enabled:
            user_service('enable', 'pi3twe-svxlink-dash.service', check=False)
        if old_mic_enabled:
            user_service('enable', 'pi3twe-mic-gain.service', check=False)
        run('/usr/bin/systemctl', 'reload', 'apache2.service', check=False)
        run('/usr/bin/systemctl', 'try-reload-or-restart', 'prometheus.service', check=False)
        print('Backup:', backup, file=sys.stderr)
        raise
    print('SvxDash draait op http://192.168.2.127:5000 — PI3TWE-menu toegevoegd.')
    print('Oude controller en oude dashboardservice zijn gestopt en uitgeschakeld.')
    print('Backup:', backup)
    print('Bestaande instellingen, bulletins en gebeurtenissen zijn behouden.')


if __name__ == '__main__':
    main()
