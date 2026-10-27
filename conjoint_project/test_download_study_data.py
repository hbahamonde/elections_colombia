"""Exercise the R downloader against disposable, synthetic HTTP fixtures.

No Render service, participant link, real password, or study database is used.
The fixture reproduces oTree 6's cookie-and-CSRF admin login and export routes.
All downloaded responses are invented and confined to temporary directories.
"""

import csv
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from urllib.parse import parse_qs, urlsplit


PROJECT = Path(__file__).resolve().parent
R_SCRIPT = PROJECT / 'visual_conjoint_design.R'
SESSION_CODE = 'test1234'
DUMMY_PASSWORD = 'synthetic-fixture-password-not-a-secret'
CSRF_TOKEN = '1234567890'


LOAD_DOWNLOAD_FUNCTIONS = r'''
    # Load only this named chunk. Sourcing the complete research script would
    # refresh the live export, clear the environment, analyze data and knit the
    # paper. None of those actions belongs in a disposable downloader test.
    .test_script <- readLines(Sys.getenv("TEST_R_SCRIPT"), warn = FALSE)
    .test_start <- which(.test_script == "## ---- download-functions")
    stopifnot(length(.test_start) == 1L)
    .test_boundaries <- which(trimws(.test_script) == "## ----")
    .test_end <- .test_boundaries[.test_boundaries > .test_start][1L]
    stopifnot(!is.na(.test_end), .test_end > .test_start + 1L)
    eval(parse(text = .test_script[seq.int(.test_start + 1L, .test_end - 1L)]),
         envir = globalenv())
    rm(.test_script, .test_start, .test_boundaries, .test_end)
'''


REAL_OTREE_HTTP_CHECK = r'''
import asyncio
import csv
from io import StringIO
import re

asyncio.set_event_loop(asyncio.new_event_loop())
from otree.main import setup
setup()
from otree.asgi import app
from otree.database import db
from otree.models import Participant
from otree.session import create_session
from starlette.testclient import TestClient

session = create_session(
    'colombia_conjoint', num_participants=2, room_name='colombia_study',
    label='SYNTHETIC_OFFICIAL_EXPORT_TEST',
    modified_session_config_fields={'official_data_collection': True})
code = session.code
create_session('colombia_conjoint', num_participants=1,
               label='SYNTHETIC_OTHER_SESSION')
db.commit()

client = TestClient(app)
unauthorized = client.get('/ExportWide', params={'session_code': code}, allow_redirects=False)
assert unauthorized.status_code in (302, 303, 307), unauthorized.status_code
assert unauthorized.headers['location'].endswith('/login')
login = client.get('/login')
assert login.status_code == 200
csrf = re.search(r'name="csrftoken" value="([^"]+)"', login.text).group(1)
assert client.post('/login', data={
    'username': 'admin', 'password': 'synthetic-fixture-password-not-a-secret',
    'csrftoken': 'wrong-csrf-token'}, allow_redirects=False).status_code == 403
failed = client.post('/login', data={
    'username': 'admin', 'password': 'incorrect-password', 'csrftoken': csrf},
    allow_redirects=False)
assert failed.status_code == 200 and 'Login failed' in failed.text
authenticated = client.post('/login', data={
    'username': 'admin', 'password': 'synthetic-fixture-password-not-a-secret',
    'csrftoken': csrf}, allow_redirects=False)
assert authenticated.status_code == 302
room = client.get('/room_with_session/colombia_study')
assert room.status_code == 200, room.text[:500]
assert f'/SessionMonitor/{code}' in room.text
download = client.get('/ExportWide', params={
    'session_code': code, 'format': 'csv_bom'})
assert download.status_code == 200, download.text[:500]
assert download.headers['content-type'] == 'text/csv'
assert 'attachment;' in download.headers['content-disposition']
assert download.content.startswith(b'\xef\xbb\xbf')
rows = list(csv.DictReader(StringIO(download.content.decode('utf-8-sig'))))
assert len(rows) == 2, len(rows)
assert all(row['session.code'] == code for row in rows)
assert all(row['participant.visited'] == '0' for row in rows)
assert all(row['session.config.official_data_collection'] == '1' for row in rows)
assert any(key.startswith('conjoint.20.player.') for key in rows[0])
db.new_session()
assert Participant.objects_filter().count() == 3
assert not any(person.visited for person in Participant.objects_filter())
db.rollback()
print('DISPOSABLE_OTREE_LOGIN_EXPORT_CHECK_PASSED')
'''


def synthetic_csv(*, session_code=SESSION_CODE, official='True', revision='first'):
    """600 allocated slots, 31 started, of whom 30 reached the final page."""
    stream = StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow([
        'participant.code', 'participant.visited', 'participant._index_in_pages',
        'participant._max_page_index', 'participant.time_started_utc',
        'session.code', 'session.config.official_data_collection',
        'conjoint.1.player.consent_accepted',
        'conjoint.6.player.decision_candidate_id',
        'conjoint.6.player.decision_side', 'sample.free_text', 'sample.revision',
    ])
    for number in range(1, 601):
        started = number <= 31
        complete = number <= 30
        text = (
            'Candidata "María", política y educación' if number == 1 else
            'NA' if number == 2 else '' if number == 3 else
            'Ideología: Izquierda. Mujer, género y equidad.'
        )
        writer.writerow([
            f'p{number:07d}', int(started),
            200 if complete else 60 if started else 0, 200,
            '2026-10-21 06:00:00' if started else '', session_code, official,
            int(started), '001234' if complete else '',
            'L' if complete else '', text, revision,
        ])
    return b'\xef\xbb\xbf' + stream.getvalue().encode('utf-8')


class ExportFixture:
    def __init__(self):
        self.mode = 'valid'
        self.revision = 'first'
        self.requests = []
        self.latest_payload = None
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def reply(self, status, body=b'', content_type='text/html', cookie=None,
                      location=None):
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                if cookie:
                    self.send_header('Set-Cookie', cookie)
                if location:
                    self.send_header('Location', location)
                if content_type == 'text/csv':
                    self.send_header('Content-Disposition',
                                     'attachment; filename="all_apps_wide-2026-10-21.csv"')
                self.end_headers()
                self.wfile.write(body)

            def authenticated(self):
                cookie = SimpleCookie(self.headers.get('Cookie', ''))
                return ('session' in cookie and
                        cookie['session'].value == 'authenticated-session')

            def do_GET(self):
                target = urlsplit(self.path)
                fixture.requests.append(('GET', target.path, parse_qs(target.query)))
                if target.path == '/login':
                    if fixture.mode == 'login_html':
                        return self.reply(200, b'<html>Unexpected sign-in page</html>')
                    return self.reply(
                        200,
                        ('<html><form method="post">'
                         f'<input type="hidden" name="csrftoken" value="{CSRF_TOKEN}">'
                         '<input name="username"><input name="password" type="password">'
                         '</form></html>').encode(),
                        cookie='session=csrf-session; Path=/; HttpOnly; SameSite=lax',
                    )
                if target.path not in (
                    '/room_with_session/colombia_study', '/ExportWide'
                ):
                    return self.reply(404, b'No participant-start route exists in this fixture.')
                if not self.authenticated():
                    return self.reply(302, location='/login')
                if target.path == '/room_with_session/colombia_study':
                    code = 'wrong5678' if fixture.mode == 'wrong_room' else SESSION_CODE
                    return self.reply(
                        200,
                        ('<html><p>Session <code>' + code + '</code> is taking place '
                         'in this room.</p><a href="/SessionMonitor/' + code + '">'
                         'Monitor the session</a></html>').encode(),
                    )
                query = parse_qs(target.query)
                if query != {'session_code': [SESSION_CODE], 'format': ['csv_bom']}:
                    return self.reply(400, b'Explicit single-session CSV query required.')
                if fixture.mode == 'export_html':
                    return self.reply(200, b'<html><h1>Admin Login</h1></html>')
                if fixture.mode == 'invalid_csv':
                    payload = b'\xef\xbb\xbfparticipant.code,session.code\r\np1,test1234,EXTRA\r\n'
                else:
                    payload = synthetic_csv(
                        session_code='wrong5678' if fixture.mode == 'wrong_csv_session'
                        else SESSION_CODE,
                        official='False' if fixture.mode == 'nonofficial_csv' else 'True',
                        revision=fixture.revision,
                    )
                fixture.latest_payload = payload
                self.reply(200, payload, content_type='text/csv')

            def do_POST(self):
                target = urlsplit(self.path)
                length = int(self.headers.get('Content-Length', '0'))
                form = parse_qs(self.rfile.read(length).decode())
                # Record only field names, not even the invented password.
                fixture.requests.append(('POST', target.path, sorted(form)))
                if target.path != '/login':
                    return self.reply(405, b'Only admin authentication POST is permitted.')
                cookie = SimpleCookie(self.headers.get('Cookie', ''))
                if ('session' not in cookie or cookie['session'].value != 'csrf-session'
                        or form.get('csrftoken') != [CSRF_TOKEN]):
                    return self.reply(403, b'CSRF verification failed')
                if (form.get('username') != ['admin'] or
                        form.get('password') != [DUMMY_PASSWORD]):
                    return self.reply(200, b'<html>Login failed</html>')
                self.reply(302, cookie='session=authenticated-session; Path=/; HttpOnly',
                           location='/demo')

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.origin = f'http://127.0.0.1:{self.server.server_address[1]}'

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@unittest.skipUnless(shutil.which('Rscript'), 'Rscript must be installed')
class RDownloadIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe = subprocess.run(
            [shutil.which('Rscript'), '--vanilla', '-e',
             'stopifnot(requireNamespace("httr", quietly=TRUE), '
             'requireNamespace("xml2", quietly=TRUE))'],
            capture_output=True, text=True, timeout=60,
        )
        if probe.returncode:
            raise unittest.SkipTest('R packages httr and xml2 must already be installed')

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='colombia-r-export-test-')
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / 'exports'
        self.fixture = ExportFixture().__enter__()
        self.addCleanup(self.fixture.__exit__, None, None, None)

    def run_r(self, extra='', *, password=DUMMY_PASSWORD, expect_failure=False):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('OTREE_', 'MONITOR_')) and key != 'DATABASE_URL'}
        env.update(
            TEST_R_SCRIPT=str(R_SCRIPT), TEST_SERVER=self.fixture.origin,
            TEST_SESSION=SESSION_CODE, TEST_PASSWORD=password,
            TEST_OUTPUT=str(self.output),
        )
        invocation = LOAD_DOWNLOAD_FUNCTIONS + '''
            fetch <- function() download_study_data(
              server_url = Sys.getenv("TEST_SERVER"),
              expected_session = Sys.getenv("TEST_SESSION"),
              username = "admin", password = Sys.getenv("TEST_PASSWORD"),
              output_dir = Sys.getenv("TEST_OUTPUT"))
        '''
        if expect_failure:
            invocation += '''
                failure <- tryCatch({fetch(); NULL}, error = identity)
                stopifnot(inherits(failure, "error"))
            '''
        else:
            invocation += '''
                study <- fetch()
                stopifnot(nrow(study$all_allocated) == 600L,
                          nrow(study$started) == 31L,
                          identical(study$session_code, Sys.getenv("TEST_SESSION")),
                          identical(study$all_allocated$sample.free_text[1L],
                                    'Candidata "María", política y educación'),
                          identical(study$all_allocated$sample.free_text[2L], "NA"),
                          is.na(study$all_allocated$sample.free_text[3L]),
                          identical(study$all_allocated[[
                            "conjoint.6.player.decision_candidate_id"]][1L], "001234"),
                          sum(study$all_allocated[["participant._index_in_pages"]] ==
                              "200") == 30L,
                          all(study$all_allocated$session.code == Sys.getenv("TEST_SESSION")),
                          file.exists(study$latest_file), file.exists(study$snapshot_file))
            '''
        result = subprocess.run(
            [shutil.which('Rscript'), '--vanilla', '-e', invocation + extra],
            env=env, capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(password, result.stdout + result.stderr)
        return result

    def assert_only_allowed_requests(self):
        allowed = {
            ('GET', '/login'), ('POST', '/login'),
            ('GET', '/room_with_session/colombia_study'), ('GET', '/ExportWide'),
        }
        self.assertTrue(self.fixture.requests)
        for method, path, _parameters in self.fixture.requests:
            self.assertIn((method, path), allowed)
            self.assertNotIn('/room/colombia_study', path)
            self.assertNotIn('/InitializeParticipant', path)

    def run_r_with_mock_keychain(self, checks, *, stored=None,
                                 prompt_password=DUMMY_PASSWORD,
                                 deny_read=False):
        """Exercise credential reuse without accessing this Mac's Keychain.

        Only this mocked credentials adapter opts the loopback HTTP fixture in
        to remembering credentials. The real downloader must not do so.
        """
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(('OTREE_', 'MONITOR_', 'KEYRING_'))
                       and key != 'DATABASE_URL'}
        environment.update(
            TEST_R_SCRIPT=str(R_SCRIPT), TEST_SERVER=self.fixture.origin,
            TEST_SESSION=SESSION_CODE, TEST_PASSWORD=DUMMY_PASSWORD,
            TEST_PROMPT_PASSWORD=prompt_password,
            TEST_STORED_PASSWORD=stored or '', TEST_DENY_READ=str(int(deny_read)),
            TEST_OUTPUT=str(self.output),
        )
        invocation = LOAD_DOWNLOAD_FUNCTIONS + r'''
            state <- new.env(parent = emptyenv())
            state$value <- Sys.getenv("TEST_STORED_PASSWORD")
            state$prompts <- 0L
            state$reads <- 0L
            state$writes <- 0L
            state$lists <- 0L
            expected_service <- paste0("colombia-otree-export:",
                                       Sys.getenv("TEST_SERVER"))
            backend <- list(
              list = function(service = NULL, ...) {
                stopifnot(identical(service, expected_service))
                state$lists <- state$lists + 1L
                if (nzchar(state$value)) {
                  data.frame(service = service, username = "admin")
                } else {
                  data.frame(service = character(), username = character())
                }
              },
              get = function(service, username = NULL, ...) {
                stopifnot(identical(service, expected_service),
                          identical(username, "admin"))
                state$reads <- state$reads + 1L
                if (Sys.getenv("TEST_DENY_READ") == "1") {
                  stop("Synthetic Keychain access denied")
                }
                state$value
              },
              set_with_value = function(service, username = NULL,
                                        password = NULL, ...) {
                stopifnot(identical(service, expected_service),
                          identical(username, "admin"))
                state$writes <- state$writes + 1L
                state$value <- password
                invisible(NULL)
              }
            )
            .study_keychain_backend <- function(...) backend
            .study_prompt_password <- function(...) {
              state$prompts <- state$prompts + 1L
              Sys.getenv("TEST_PROMPT_PASSWORD")
            }
            original_credentials <- .study_credentials
            .study_credentials <- function(server_url, username, password,
                                           use_keychain) {
              original_credentials(server_url, username, password,
                                   use_keychain = TRUE)
            }
            fetch <- function(password = "") download_study_data(
              server_url = Sys.getenv("TEST_SERVER"),
              expected_session = Sys.getenv("TEST_SESSION"), username = "admin",
              password = password, output_dir = Sys.getenv("TEST_OUTPUT"))
        '''
        result = subprocess.run(
            [shutil.which('Rscript'), '--vanilla', '-e', invocation + checks],
            env=environment, capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for secret in {DUMMY_PASSWORD, prompt_password, stored} - {None, ''}:
            self.assertNotIn(secret, result.stdout + result.stderr)
        return result

    def test_mock_keychain_prompts_once_then_reuses_successful_password(self):
        self.run_r_with_mock_keychain(r'''
            first <- fetch()
            stopifnot(state$prompts == 1L, state$writes == 1L,
                      state$reads == 0L, nrow(first$started) == 31L)
            second <- fetch()
            stopifnot(state$prompts == 1L, state$writes == 1L,
                      state$reads == 1L, nrow(second$started) == 31L,
                      identical(state$value, Sys.getenv("TEST_PASSWORD")),
                      !identical(first$snapshot_file, second$snapshot_file))
        ''')
        self.assertEqual(len(list((self.output / 'snapshots').glob('*.csv'))), 2)
        self.assert_only_allowed_requests()

    def test_mock_keychain_explicit_password_overrides_old_entry(self):
        self.run_r_with_mock_keychain(r'''
            study <- fetch(password = Sys.getenv("TEST_PASSWORD"))
            stopifnot(state$prompts == 0L, state$reads == 0L,
                      state$writes == 1L,
                      identical(state$value, Sys.getenv("TEST_PASSWORD")),
                      nrow(study$started) == 31L)
        ''', stored='obsolete-synthetic-password')
        self.assert_only_allowed_requests()

    def test_mock_keychain_failed_login_does_not_store_prompted_password(self):
        self.run_r_with_mock_keychain(r'''
            failure <- tryCatch({fetch(); NULL}, error = identity)
            stopifnot(inherits(failure, "error"), state$prompts == 1L,
                      state$writes == 0L, !nzchar(state$value),
                      !dir.exists(Sys.getenv("TEST_OUTPUT")))
        ''', prompt_password='incorrect-synthetic-password')
        self.assert_only_allowed_requests()

    def test_mock_keychain_wrong_session_does_not_store_after_valid_login(self):
        self.fixture.mode = 'wrong_room'
        self.run_r_with_mock_keychain(r'''
            failure <- tryCatch({fetch(); NULL}, error = identity)
            stopifnot(inherits(failure, "error"), state$prompts == 1L,
                      state$writes == 0L, !nzchar(state$value),
                      !dir.exists(Sys.getenv("TEST_OUTPUT")))
        ''')
        self.assert_only_allowed_requests()

    def test_mock_keychain_loopback_guard_never_accesses_real_backend(self):
        self.run_r_with_mock_keychain(r'''
            .study_credentials <- original_credentials
            .study_keychain_backend <- function(...) {
              stop("Loopback must never access a real credential backend")
            }
            study <- fetch()
            stopifnot(state$prompts == 1L, state$reads == 0L,
                      state$writes == 0L, state$lists == 0L,
                      nrow(study$started) == 31L)
        ''')
        self.assert_only_allowed_requests()

    def test_mock_keychain_stale_password_does_not_silently_prompt_or_overwrite(self):
        self.run_r_with_mock_keychain(r'''
            failure <- tryCatch({fetch(); NULL}, error = identity)
            stopifnot(inherits(failure, "error"), state$prompts == 0L,
                      state$reads == 1L, state$writes == 0L,
                      identical(state$value, Sys.getenv("TEST_STORED_PASSWORD")),
                      !dir.exists(Sys.getenv("TEST_OUTPUT")))
        ''', stored='obsolete-synthetic-password')
        self.assert_only_allowed_requests()

    def test_mock_keychain_denial_does_not_prompt_overwrite_or_contact_server(self):
        self.run_r_with_mock_keychain(r'''
            failure <- tryCatch({fetch(); NULL}, error = identity)
            stopifnot(inherits(failure, "error"), state$prompts == 0L,
                      state$reads == 1L, state$writes == 0L,
                      !dir.exists(Sys.getenv("TEST_OUTPUT")))
        ''', stored=DUMMY_PASSWORD, deny_read=True)
        self.assertEqual(self.fixture.requests, [])

    def test_loading_only_download_chunk_has_no_automatic_side_effects(self):
        env = dict(os.environ, TEST_R_SCRIPT=str(R_SCRIPT), TEST_OUTPUT=str(self.output))
        invocation = r'''
            .test_sentinel <- "existing workspace contents are preserved"
        ''' + LOAD_DOWNLOAD_FUNCTIONS + r'''
            stopifnot(is.function(download_study_data),
                      identical(.test_sentinel,
                                "existing workspace contents are preserved"),
                      !exists("download", inherits = FALSE),
                      !exists("dat", inherits = FALSE),
                      !exists("tasks", inherits = FALSE),
                      !dir.exists(Sys.getenv("TEST_OUTPUT")))
        '''
        result = subprocess.run(
            [shutil.which('Rscript'), '--vanilla', '-e', invocation],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.fixture.requests, [])

    def test_download_and_refresh_keep_all_raw_rows_and_previous_snapshot(self):
        self.run_r()
        first_payload = self.fixture.latest_payload
        latest = self.output / 'latest.csv'
        first_snapshots = list((self.output / 'snapshots').glob('*.csv'))
        self.assertEqual(len(first_snapshots), 1)
        first_snapshot = first_snapshots[0]
        self.assertEqual(latest.read_bytes(), first_payload)
        self.assertEqual(first_snapshot.read_bytes(), first_payload)
        self.assertRegex(first_snapshot.name, r'conjoint_test1234_\d{8}T\d{6}Z_')
        self.fixture.revision = 'second'
        self.run_r()
        snapshots = list((self.output / 'snapshots').glob('*.csv'))
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(first_snapshot.read_bytes(), first_payload)
        self.assertEqual(latest.read_bytes(), self.fixture.latest_payload)
        self.assertNotEqual(latest.read_bytes(), first_payload)
        self.assertEqual(latest.stat().st_mode & 0o777, 0o600)
        self.assertEqual(first_snapshot.stat().st_mode & 0o777, 0o600)
        self.assert_only_allowed_requests()

    def test_invalid_responses_do_not_replace_previous_latest_or_snapshot(self):
        self.run_r()
        latest = self.output / 'latest.csv'
        valid_payload = latest.read_bytes()
        snapshots = {path.name: path.read_bytes()
                     for path in (self.output / 'snapshots').glob('*.csv')}
        for mode in (
            'wrong_password', 'login_html', 'export_html', 'wrong_room',
            'wrong_csv_session', 'nonofficial_csv', 'invalid_csv',
        ):
            with self.subTest(mode=mode):
                self.fixture.mode = mode
                self.run_r(password='incorrect-synthetic-password'
                           if mode == 'wrong_password' else DUMMY_PASSWORD,
                           expect_failure=True)
                self.assertEqual(latest.read_bytes(), valid_payload)
                self.assertEqual(
                    {path.name: path.read_bytes()
                     for path in (self.output / 'snapshots').glob('*.csv')},
                    snapshots,
                )
        self.assert_only_allowed_requests()


class DisposableOTreeExportTests(unittest.TestCase):
    def test_installed_otree_cookie_csrf_and_session_filtered_csv_contract(self):
        interpreter = PROJECT / '.venv' / 'bin' / 'python'
        if not interpreter.exists():
            interpreter = Path(sys.executable)
        with tempfile.TemporaryDirectory(prefix='colombia-otree-export-test-') as temporary:
            project = Path(temporary)
            for name in ('settings.py', 'completion_rules.py', 'quota_monitor_data.py'):
                shutil.copy2(PROJECT / name, project / name)
            shutil.copytree(PROJECT / 'conjoint', project / 'conjoint',
                            ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(PROJECT / '_templates', project / '_templates')
            (project / '_static').symlink_to(PROJECT / '_static', target_is_directory=True)
            environment = {key: value for key, value in os.environ.items()
                           if not key.startswith(('OTREE_', 'MONITOR_'))
                           and key not in ('DATABASE_URL', 'SENTRY_DSN')}
            environment.update({
                'DATABASE_URL': 'sqlite:///db.sqlite3', 'OTREE_PRODUCTION': '0',
                'OTREE_AUTH_LEVEL': 'STUDY', 'PYTHONPATH': str(project),
                'OTREE_ADMIN_USERNAME': 'admin', 'OTREE_ADMIN_PASSWORD': DUMMY_PASSWORD,
                'OTREE_SECRET_KEY': 'disposable-export-test-not-a-live-secret',
            })
            result = subprocess.run(
                [str(interpreter), '-c', textwrap.dedent(REAL_OTREE_HTTP_CHECK)],
                cwd=project, env=environment, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('DISPOSABLE_OTREE_LOGIN_EXPORT_CHECK_PASSED', result.stdout)
            self.assertTrue((project / 'db.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
