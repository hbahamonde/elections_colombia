"""GET-only recruitment monitoring with credentials separate from oTree admin."""

import base64
import binascii
import hmac
import logging
import os
from pathlib import Path

from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
PUBLIC_SNAPSHOT_KEYS = frozenset({
    'status', 'message', 'mode', 'updated_at', 'summary', 'treatments',
    'quota_dimensions', 'age_gender', 'exclusions', 'targets_configured',
    'main_task_count',
})
MONITOR_ROUTE_NAMES = frozenset({
    'monitor_dashboard', 'monitor_slash', 'monitor_data',
    'monitor_dashboard_css', 'monitor_dashboard_js',
})
SECURITY_HEADERS = {
    'Cache-Control': 'no-store, private, max-age=0',
    'Pragma': 'no-cache',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
    'X-Robots-Tag': 'noindex, nofollow, noarchive',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    'Content-Security-Policy': (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; font-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; "
        "object-src 'none'"
    ),
}


def _authenticate(request):
    """Authenticate before opening files or entering the database read path."""
    username = os.environ.get('MONITOR_USERNAME', '')
    password = os.environ.get('MONITOR_PASSWORD', '')
    if not username or not password:
        return Response(
            'El acceso al monitor todavía no está configurado.',
            status_code=503,
            media_type='text/plain',
            headers=SECURITY_HEADERS,
        )

    authorized = False
    scheme, separator, credentials = request.headers.get('authorization', '').partition(' ')
    if separator and scheme.lower() == 'basic':
        try:
            decoded = base64.b64decode(credentials, validate=True).decode('utf-8')
            supplied_username, separator, supplied_password = decoded.partition(':')
            if separator:
                username_matches = hmac.compare_digest(
                    supplied_username.encode('utf-8'), username.encode('utf-8')
                )
                password_matches = hmac.compare_digest(
                    supplied_password.encode('utf-8'), password.encode('utf-8')
                )
                authorized = username_matches & password_matches
        except (ValueError, binascii.Error, UnicodeDecodeError):
            pass

    if not authorized:
        headers = dict(SECURITY_HEADERS)
        headers['WWW-Authenticate'] = 'Basic realm="Recruitment monitor", charset="UTF-8"'
        return Response(
            'Se requieren las credenciales del monitor.',
            status_code=401,
            media_type='text/plain',
            headers=headers,
        )
    return None


def _file_response(filename, media_type):
    # Only callers' fixed filenames are accepted; no path comes from a request.
    try:
        content = (PROJECT_ROOT / filename).read_text(encoding='utf-8')
        response_class = HTMLResponse if media_type == 'text/html' else Response
        return response_class(content, media_type=media_type, headers=SECURITY_HEADERS)
    except OSError:
        LOGGER.exception('Recruitment monitor asset unavailable')
        return Response(
            'El monitor no está disponible en este momento.',
            status_code=503,
            media_type='text/plain',
            headers=SECURITY_HEADERS,
        )


def monitor_dashboard(request):
    denied = _authenticate(request)
    if denied is not None:
        return denied
    return _file_response('monitor_dashboard.html', 'text/html')


def monitor_dashboard_css(request):
    denied = _authenticate(request)
    if denied is not None:
        return denied
    return _file_response('monitor_dashboard.css', 'text/css')


def monitor_dashboard_js(request):
    denied = _authenticate(request)
    if denied is not None:
        return denied
    return _file_response('monitor_dashboard.js', 'application/javascript')


def monitor_slash(request):
    denied = _authenticate(request)
    if denied is not None:
        return denied
    return RedirectResponse('/monitor', status_code=307, headers=SECURITY_HEADERS)


def _read_snapshot():
    # Imported lazily so importing routes cannot initialize or access oTree data.
    from otree.database import db
    from quota_monitor_data import build_monitor_snapshot
    from sqlalchemy import text

    try:
        with db._db.no_autoflush:
            connection = db._db.connection()
            if connection.dialect.name == 'postgresql':
                connection.execute(text('SET TRANSACTION READ ONLY'))
            return build_monitor_snapshot()
    finally:
        # The enclosing oTree middleware owns this request's session. Roll back
        # its read transaction; its normal final commit then has nothing to save.
        db.rollback()


def monitor_data(request):
    denied = _authenticate(request)
    if denied is not None:
        return denied
    try:
        snapshot = _read_snapshot()
        if not isinstance(snapshot, dict) or set(snapshot) - PUBLIC_SNAPSHOT_KEYS:
            raise ValueError('Unexpected fields in recruitment monitor snapshot')
        return JSONResponse(snapshot, headers=SECURITY_HEADERS)
    except Exception:
        LOGGER.exception('Recruitment monitor snapshot unavailable')
        return JSONResponse(
            {'status': 'error', 'message': 'No se pudo actualizar el monitor.'},
            status_code=500,
            headers=SECURITY_HEADERS,
        )


def build_monitor_routes():
    return [
        Route('/monitor', monitor_dashboard, methods=['GET', 'HEAD'], name='monitor_dashboard'),
        Route('/monitor/', monitor_slash, methods=['GET', 'HEAD'], name='monitor_slash'),
        Route('/monitor/data', monitor_data, methods=['GET', 'HEAD'], name='monitor_data'),
        Route(
            '/monitor/assets/dashboard.css', monitor_dashboard_css,
            methods=['GET', 'HEAD'], name='monitor_dashboard_css',
        ),
        Route(
            '/monitor/assets/dashboard.js', monitor_dashboard_js,
            methods=['GET', 'HEAD'], name='monitor_dashboard_js',
        ),
    ]
