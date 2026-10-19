"""HTTP/authentication tests; fixtures never access an experiment database."""

import base64
from contextlib import nullcontext
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient

import monitor_routes
import monitor_server


TEST_CREDENTIALS = ('test-monitor-viewer', 'test-only-password-not-a-live-secret')


class MonitorHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='monitor-http-test-')
        self.root = Path(self.temporary.name)
        for filename, content in {
            'monitor_dashboard.html': '<!doctype html><h1>Recruitment monitor</h1>',
            'monitor_dashboard.css': 'body { color: black; }',
            'monitor_dashboard.js': 'document.title = "Recruitment monitor";',
        }.items():
            (self.root / filename).write_text(content, encoding='utf-8')
        self.env_patch = patch.dict(os.environ, {
            'MONITOR_USERNAME': TEST_CREDENTIALS[0],
            'MONITOR_PASSWORD': TEST_CREDENTIALS[1],
        })
        self.env_patch.start()
        self.root_patch = patch.object(monitor_routes, 'PROJECT_ROOT', self.root)
        self.root_patch.start()
        self.reader_patch = patch.object(monitor_routes, '_read_snapshot')
        self.reader = self.reader_patch.start()
        self.reader.return_value = {
            'status': 'ok', 'mode': 'testing', 'summary': {'started': 2},
            'treatments': [], 'quota_dimensions': [], 'age_gender': [],
            'exclusions': [], 'targets_configured': False, 'main_task_count': 15,
        }
        self.client = TestClient(Starlette(routes=monitor_routes.build_monitor_routes()))

    def tearDown(self):
        self.reader_patch.stop()
        self.root_patch.stop()
        self.env_patch.stop()
        self.temporary.cleanup()

    def assert_security_headers(self, response):
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        self.assertNotIn('Access-Control-Allow-Origin', response.headers)

    def test_unconfigured_credentials_fail_closed_without_admin_fallback(self):
        with patch.dict(os.environ, {
            'MONITOR_USERNAME': '', 'MONITOR_PASSWORD': '',
            'OTREE_ADMIN_USERNAME': TEST_CREDENTIALS[0],
            'OTREE_ADMIN_PASSWORD': TEST_CREDENTIALS[1],
        }):
            for path in ('/monitor', '/monitor/', '/monitor/data', '/monitor/assets/dashboard.js'):
                response = self.client.get(path, auth=TEST_CREDENTIALS, allow_redirects=False)
                self.assertEqual(response.status_code, 503)
                self.assert_security_headers(response)
        self.reader.assert_not_called()

    def test_every_endpoint_requires_authentication_before_reading_data(self):
        for path in (
            '/monitor', '/monitor/', '/monitor/data',
            '/monitor/assets/dashboard.css', '/monitor/assets/dashboard.js',
        ):
            for method in ('get', 'head'):
                # Starlette 0.14's requests adapter needs streaming HEAD checks
                # with current urllib3; the live server uses standard HEAD semantics.
                response = getattr(self.client, method)(
                    path, allow_redirects=False, stream=(method == 'head')
                )
                self.assertEqual(response.status_code, 401)
                self.assertIn('Basic realm=', response.headers['WWW-Authenticate'])
                self.assert_security_headers(response)
        self.reader.assert_not_called()

    def test_wrong_malformed_and_url_credentials_cannot_authenticate(self):
        headers = (
            {'Authorization': 'Bearer not-a-monitor-token'},
            {'Authorization': 'Basic !!!'},
            {'Authorization': 'Basic ' + base64.b64encode(b'no-colon').decode()},
            {'Authorization': 'Basic ' + base64.b64encode(b'\xff:bad').decode()},
        )
        for header in headers:
            self.assertEqual(self.client.get('/monitor/data', headers=header).status_code, 401)
        self.assertEqual(
            self.client.get('/monitor/data', auth=(TEST_CREDENTIALS[0], 'wrong')).status_code,
            401,
        )
        self.assertEqual(
            self.client.get('/monitor/data?password=' + TEST_CREDENTIALS[1]).status_code,
            401,
        )
        self.reader.assert_not_called()

    def test_authenticated_html_and_fixed_assets_are_served_with_security_headers(self):
        for path, content_type in (
            ('/monitor', 'text/html'),
            ('/monitor/assets/dashboard.css', 'text/css'),
            ('/monitor/assets/dashboard.js', 'application/javascript'),
        ):
            response = self.client.get(path, auth=TEST_CREDENTIALS)
            self.assertEqual(response.status_code, 200)
            self.assertIn(content_type, response.headers['Content-Type'])
            self.assertNotIn('unsafe-inline', response.headers['Content-Security-Policy'])
            self.assert_security_headers(response)
        self.reader.assert_not_called()

    def test_authenticated_json_and_head(self):
        response = self.client.get('/monitor/data', auth=TEST_CREDENTIALS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary']['started'], 2)
        self.assert_security_headers(response)
        response = self.client.head('/monitor/data', auth=TEST_CREDENTIALS, stream=True)
        self.assertEqual(response.status_code, 200)
        self.assert_security_headers(response)

    def test_authenticated_trailing_slash_redirect(self):
        response = self.client.get('/monitor/', auth=TEST_CREDENTIALS, allow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers['Location'], '/monitor')
        self.assert_security_headers(response)
        self.reader.assert_not_called()

    def test_mutating_methods_and_unlisted_files_are_not_routes(self):
        for path in ('/monitor', '/monitor/data', '/monitor/assets/dashboard.js'):
            for method in ('post', 'put', 'patch', 'delete', 'options'):
                response = getattr(self.client, method)(path, auth=TEST_CREDENTIALS)
                self.assertEqual(response.status_code, 405)
        for path in ('/monitor/assets/settings.py', '/monitor/assets/db.sqlite3'):
            self.assertEqual(self.client.get(path, auth=TEST_CREDENTIALS).status_code, 404)
        self.reader.assert_not_called()

    def test_unexpected_fields_fail_closed_instead_of_exposing_participant_records(self):
        self.reader.return_value = {'status': 'ok', 'participant_rows': [{'code': 'private'}]}
        with self.assertLogs('monitor_routes', level='ERROR'):
            response = self.client.get('/monitor/data', auth=TEST_CREDENTIALS)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('participant_rows', response.text)
        self.assertNotIn('private', response.text)
        self.assert_security_headers(response)

    def test_snapshot_errors_have_generic_responses(self):
        self.reader.side_effect = RuntimeError('internal database diagnostic')
        with self.assertLogs('monitor_routes', level='ERROR'):
            response = self.client.get('/monitor/data', auth=TEST_CREDENTIALS)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('internal database diagnostic', response.text)
        self.assertNotIn('Traceback', response.text)
        self.assert_security_headers(response)


class MonitorTransactionTests(unittest.TestCase):
    def exercise_read(self, dialect, raises=False):
        connection = MagicMock()
        connection.dialect.name = dialect
        session = SimpleNamespace(no_autoflush=nullcontext(), connection=lambda: connection)
        database = SimpleNamespace(_db=session, rollback=MagicMock())
        builder = MagicMock(return_value={'status': 'ok'})
        if raises:
            builder.side_effect = RuntimeError('read failed')
        modules = {
            'otree.database': SimpleNamespace(db=database),
            'quota_monitor_data': SimpleNamespace(build_monitor_snapshot=builder),
        }
        with patch.dict(sys.modules, modules):
            if raises:
                with self.assertRaises(RuntimeError):
                    monitor_routes._read_snapshot()
            else:
                self.assertEqual(monitor_routes._read_snapshot(), {'status': 'ok'})
        database.rollback.assert_called_once_with()
        return connection

    def test_postgres_transaction_is_read_only_and_rolled_back(self):
        connection = self.exercise_read('postgresql')
        self.assertEqual(str(connection.execute.call_args[0][0]), 'SET TRANSACTION READ ONLY')

    def test_sqlite_read_uses_existing_session_and_rolls_back(self):
        connection = self.exercise_read('sqlite')
        connection.execute.assert_not_called()

    def test_failure_also_rolls_back(self):
        self.exercise_read('postgresql', raises=True)


class MonitorLauncherTests(unittest.TestCase):
    def test_normal_production_command_and_original_routes_are_preserved(self):
        original_route = Route('/participant-original', lambda request: Response('original'))
        app = SimpleNamespace(router=SimpleNamespace(routes=[original_route]))
        setup = MagicMock()
        command = MagicMock()
        modules = {
            'otree.main': SimpleNamespace(setup=setup),
            'otree.asgi': SimpleNamespace(app=app),
            'otree.cli.prodserver1of2': SimpleNamespace(Command=command),
        }
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {}, clear=False):
            with patch.object(monitor_server, 'version', return_value='6.0.15'):
                monitor_server.main(['127.0.0.1:8766'])
            self.assertEqual(os.environ['USE_TIMEOUT_WORKER'], '1')
        setup.assert_called_once_with()
        command.return_value.handle.assert_called_once_with(addrport='127.0.0.1:8766')
        self.assertIs(app.router.routes[-1], original_route)
        self.assertEqual(
            {route.name for route in app.router.routes[:-1]},
            monitor_routes.MONITOR_ROUTE_NAMES,
        )

    def test_untested_otree_version_fails_before_setup(self):
        setup = MagicMock()
        with patch.dict(sys.modules, {'otree.main': SimpleNamespace(setup=setup)}):
            with patch.object(monitor_server, 'version', return_value='99.0'):
                with self.assertRaises(RuntimeError):
                    monitor_server.main([])
        setup.assert_not_called()


if __name__ == '__main__':
    unittest.main()
