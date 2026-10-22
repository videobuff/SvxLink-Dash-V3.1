"""Authenticated PI3TWE pages and API inside SvxDash."""
import hmac
import os
from pathlib import Path
import secrets
import subprocess
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, current_app, jsonify, render_template, request, session, send_file

bp = Blueprint('pi3twe', __name__, url_prefix='/pi3twe')
ZONE = ZoneInfo('Europe/Amsterdam')


def runtime():
    service = current_app.extensions.get('pi3twe')
    if service is None:
        raise RuntimeError('PI3TWE-bediening is nog niet geïnstalleerd')
    return service


@bp.before_request
def authenticate():
    if not session.get('authorised'):
        return jsonify(ok=False, error='Log eerst in op SvxDash'), 401
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        token = session.get('pi3twe_csrf', '')
        if not token or not hmac.compare_digest(token, request.headers.get('X-CSRF-Token', '')):
            return jsonify(ok=False, error='Ververs de pagina en probeer opnieuw'), 403


@bp.errorhandler(ValueError)
def invalid(error):
    return jsonify(ok=False, error=str(error)), 400


@bp.errorhandler(RuntimeError)
@bp.errorhandler(OSError)
def unavailable(error):
    current_app.logger.warning('PI3TWE operation failed: %s', error)
    return jsonify(ok=False, error=str(error)), 503


@bp.get('/')
def page():
    session.setdefault('pi3twe_csrf', secrets.token_hex(32))
    return render_template('pi3twe.html', csrf_token=session['pi3twe_csrf'])


@bp.get('/api/state')
def state():
    return jsonify(ok=True, **runtime().state())


@bp.post('/api/power/<action>')
def power(action):
    if action not in {'on', 'off'}:
        raise ValueError('Kies Power aan of uit')
    rt = runtime()
    result = rt.controller.set_relay(1, action == 'on')
    return jsonify(ok=True, relay=result)


@bp.post('/api/mode/<mode>')
def mode(mode):
    rt = runtime()
    if rt.busy and mode == 'aan':
        raise ValueError('Wacht tot de nieuwsuitzending is afgerond')
    result = rt.mode.set(mode, rt.controller.relays.physical_states()[1])
    rt.events.add('beheer', 'SVXLINK ' + mode.upper())
    return jsonify(ok=True, **result)


@bp.post('/api/test/call')
def test_call():
    runtime().test_call()
    return jsonify(ok=True, started=True), 202


@bp.put('/api/logic')
def logic():
    return jsonify(ok=True, settings=runtime().update_settings(request.get_json(silent=True)))


def local_datetime(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            raise ValueError()
        return parsed.replace(tzinfo=ZONE).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        raise ValueError('Vul een geldige lokale datum en tijd in')


def news_payload(item):
    result = dict(item)
    for key in ['valid_from', 'valid_until']:
        result[key + '_input'] = datetime.fromisoformat(item[key]).astimezone(ZONE).strftime('%Y-%m-%dT%H:%M')
    now = datetime.now(timezone.utc)
    result['within_period'] = datetime.fromisoformat(item['valid_from']) <= now < datetime.fromisoformat(item['valid_until'])
    return result


@bp.get('/api/news')
def list_news():
    return jsonify(ok=True, items=[news_payload(item) for item in runtime().news.list()])


def validate_audio(path):
    try:
        result = subprocess.run(['/usr/bin/ffprobe', '-v', 'error', '-select_streams', 'a:0',
                                 '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', str(path)],
                                capture_output=True, text=True, check=True, timeout=20)
        if result.stdout.strip() != 'audio':
            raise ValueError('Het bestand bevat geen leesbare audio')
    except (subprocess.SubprocessError, OSError) as error:
        raise ValueError('Het audiobestand kon niet worden gelezen') from error


@bp.post('/api/news')
def upload_news():
    rt = runtime()
    upload = request.files.get('audio')
    if not upload or not upload.filename:
        raise ValueError('Kies een audiobestand')
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in {'.mp3', '.wav', '.ogg', '.flac', '.m4a'}:
        raise ValueError('Gebruik MP3, WAV, OGG, FLAC of M4A')
    start = local_datetime(request.form.get('valid_from'))
    end = local_datetime(request.form.get('valid_until'))
    rt.news._validate_period(start, end)
    temporary = rt.media / ('.upload-' + uuid.uuid4().hex + suffix)
    item = None
    try:
        upload.save(temporary)
        validate_audio(temporary)
        item = rt.news.create(original_filename=Path(upload.filename).name, suffix=suffix,
                              valid_from=start, valid_until=end)
        os.replace(temporary, rt.media / item['filename'])
    except Exception:
        if item:
            rt.news.delete(item['id'])
        raise
    finally:
        temporary.unlink(missing_ok=True)
    rt.events.add('nieuws', f"NIEUWS {item['label']} GEÜPLOAD")
    return jsonify(ok=True, item=news_payload(item)), 201


@bp.put('/api/news/<int:bulletin_id>')
def update_news(bulletin_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('enabled'), bool):
        raise ValueError('Geef aan of het bulletin actief is')
    rt = runtime()
    item = rt.news.update(bulletin_id, valid_from=local_datetime(data.get('valid_from')),
                          valid_until=local_datetime(data.get('valid_until')), enabled=data['enabled'])
    rt.events.add('nieuws', f"NIEUWS {item['label']} BIJGEWERKT")
    return jsonify(ok=True, item=news_payload(item))


@bp.post('/api/news/<int:bulletin_id>/play')
def play_news(bulletin_id):
    item = runtime().play(bulletin_id)
    return jsonify(ok=True, item=news_payload(item)), 202


@bp.delete('/api/news/<int:bulletin_id>')
def delete_news(bulletin_id):
    runtime().delete(bulletin_id)
    return jsonify(ok=True)


@bp.get('/api/news/<int:bulletin_id>/audio')
def preview_news(bulletin_id):
    rt = runtime()
    item = rt.news.get(bulletin_id)
    return send_file(rt.media / item['filename'], conditional=True)


@bp.put('/api/audio')
def audio():
    rt = runtime()
    data = request.get_json(silent=True) or {}
    with rt.logic.change():
        if data.get('enabled') is True and rt.engine.state()['active']:
            raise ValueError('SvxLink beheert de audio; analoge loopback blijft uit')
        result = rt.mixer.update(enabled=data.get('enabled') is True,
                                 input_percent=data.get('input_percent'),
                                 monitor_percent=data.get('monitor_percent'),
                                 master_percent=data.get('master_percent'))
        rt.events.add('beheer', 'AUDIOVOLUMES GEWIJZIGD')
    return jsonify(ok=True, **result)


def register(app):
    app.register_blueprint(bp)
    @app.get('/metrics')
    def pi3twe_metrics():
        from .metrics import prometheus_metrics
        rt = app.extensions.get('pi3twe')
        if rt is None:
            return Response('PI3TWE runtime unavailable\n', status=503, mimetype='text/plain')
        return Response(prometheus_metrics(rt.controller.state()), mimetype='text/plain')
    if os.environ.get('PI3TWE_CONTROL_ENABLED') == '1':
        from .runtime import Runtime
        directory = Path(os.environ.get('PI3TWE_STATE_DIRECTORY', '/var/lib/pi3twe-svxdash'))
        app.secret_key = (directory / 'dashboard-secret').read_text().strip()
        rt = Runtime(directory)
        app.extensions['pi3twe'] = rt
        app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
        rt.start()
