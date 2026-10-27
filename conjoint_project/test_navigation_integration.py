"""Exercise real Chrome navigation against a disposable local oTree server.

All participants are synthetic. The child receives no remote database or Render
configuration, creates SQLite inside a temporary source copy, and binds only to
127.0.0.1. Browser requests to every other origin are blocked. Nothing is sent
to Render and no real response file is opened.
"""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen


SERVER = r'''
import asyncio
from pathlib import Path
import os
asyncio.set_event_loop(asyncio.new_event_loop())
from otree.main import setup
setup()
from otree.asgi import app
from otree.database import db, engine
from otree.models import Participant
from otree.session import create_session
from otree.lookup import url_i_should_be_on
from conjoint.models import C, Player, assign_candidates
from quota_monitor_data import (_metadata, _page_layout, _load_records,
                                _aggregate_records)
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

assert Path(engine.url.database).resolve() == Path.cwd() / 'db.sqlite3'
session = create_session('colombia_conjoint', num_participants=12)
session_code = session.code
codes = [person.code for person in
         Participant.objects_filter(session=session).order_by('id_in_session')]
db.commit()

def prepare(request):
    person = Participant.objects_get(code=codes[int(request.query_params['person'])])
    index = int(request.query_params.get('index', '6'))
    person.visited = True
    person._index_in_pages = index
    person.vars['treatment_arm'] = request.query_params.get('arm', 'control_ver_mas')
    baseline = Player.objects_get(participant=person, round_number=1)
    baseline.consent_accepted = True
    baseline.country_of_residence = 'CL'
    baseline.nationality = 'FI'
    baseline.lived_in_colombia = 'no'
    baseline.age_years = 35
    baseline.gender_identity = 'mujer'
    baseline.education_level = 'postgrado'
    baseline.occupation_status = 'estudia'
    baseline.voted_last_municipal = 'yes'
    baseline.political_interest = 4
    baseline.politics_frequency = 'every_day'
    baseline.left_right_self_placement = '5'
    if index == 59:
        row = Player.objects_get(participant=person, round_number=6)
        assign_candidates(row)
        row.decision_candidate_id = row.left_candidate_id
        row.decision_side = 'left'
    if index == 200:
        for row in Player.objects_filter(participant=person):
            assign_candidates(row)
            row.decision_candidate_id = row.left_candidate_id
            row.decision_side = 'left'
        for number in range(6, 6 + int(request.query_params.get('missings', '0'))):
            row = Player.objects_get(participant=person, round_number=number)
            row.decision_candidate_id = None
            row.decision_side = None
            row.countdown_expired = True
    db.commit()
    return JSONResponse({'code': person.code,
        'url': url_i_should_be_on(person.code, session_code, index)})

def state(request):
    person = Participant.objects_get(code=codes[int(request.query_params['person'])])
    metadata = _metadata()
    selected = person.session
    layout = _page_layout(selected, metadata)
    snapshot = _aggregate_records('testing', metadata, layout,
                                 *_load_records(selected, metadata), {})
    return JSONResponse({'vars': dict(person._vars or {}),
        'page_index': person._index_in_pages,
        'participant_rows': len(list(Participant.objects_filter(session=selected))),
        'player_rows': len(list(Player.objects_filter(participant=person))),
        'tasks': [{'round': row.round_number,
                   'choice': row.field_maybe_none('decision_candidate_id'),
                   'expired': row.field_maybe_none('countdown_expired'),
                   'seconds': row.field_maybe_none('time_spent_seconds')}
                  for row in Player.objects_filter(participant=person)],
        'summary': snapshot['summary']})

app.router.routes[:0] = [
    Route('/__test__/prepare', prepare), Route('/__test__/state', state),
    Route('/__test__/ready', lambda request: JSONResponse({'ready': True})),
]
uvicorn.run(app, host='127.0.0.1', port=int(os.environ['NAVIGATION_TEST_PORT']),
            log_level='error', access_log=False)
'''


BROWSER = r'''
const {chromium} = require(process.env.NAVIGATION_TEST_PLAYWRIGHT);
const assert = require('node:assert/strict');
const base = process.env.NAVIGATION_TEST_URL;
const origin = new URL(base).origin;
const passed = [];
passed.push = function(message) {
  process.stderr.write(message + '\n');
  return Array.prototype.push.call(this, message);
};

(async () => {
  const browser = await chromium.launch({channel: 'chrome', headless: true});
  const context = await browser.newContext({viewport: {width: 1280, height: 850}});
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin === origin) return route.continue();
    return route.abort();
  });
  const errors = [];
  context.on('page', page => page.on('pageerror', error => errors.push(error.message)));
  async function state(person) {
    return (await context.request.get(`${base}/__test__/state?person=${person}`)).json();
  }
  async function prepare(person, index=6, arm='control_ver_mas') {
    return (await context.request.get(`${base}/__test__/prepare?person=${person}&index=${index}&arm=${arm}`)).json();
  }
  async function waitFlag(person, expected) {
    for(let attempt=0; attempt<80; attempt++) {
      const actual = await state(person);
      if(Boolean(actual.vars.navigation_violation) === expected) return actual;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error(`Navigation flag mismatch for synthetic person ${person}: ${JSON.stringify(await state(person))}`);
  }
  async function ready(page) {
    await page.waitForFunction(() => document.getElementById('stimulus-status')?.textContent === 'Fotografías listas.');
  }
  async function stopped(page, person, reason) {
    await page.waitForFunction(() => document.body.innerText.toLowerCase().includes('incompleta'));
    const actual = await state(person);
    assert.equal(actual.vars.study_terminated, true);
    assert.equal(actual.vars.study_termination_reason, reason);
    assert.ok(actual.vars.study_terminated_at_utc);
    assert.equal(await page.locator('#choose-left').count(), 0);
    assert.equal(await page.locator('a[href*="bordedata.cl"]').count(), 0);
    assert.equal(actual.player_rows, 20, 'Every original task row is retained.');
    assert.equal(actual.participant_rows, 12, 'No participant is deleted.');
    return actual;
  }
  async function start(person, arm='control_ver_mas') {
    const fixture = await prepare(person, 6, arm);
    const page = await context.newPage();
    await page.goto(base + fixture.url);
    assert.match(await page.locator('body').innerText(), /(?:actualice|recargue|refresque)/i);
    await page.locator('button.otree-btn-next').click();
    await ready(page);
    return page;
  }

  // Ordinary, untimed progress must never be mistaken for prohibited history.
  for(const [person, arm] of [[0,'control_ver_mas'],[1,'captcha_ver_mas']]) {
    const page = await start(person, arm);
    for(let task=0; task<2; task++) {
      await page.locator('#choose-left').click();
      await page.locator('#next-btn').click();
      await ready(page);
    }
    const actual = await state(person);
    assert.equal(Boolean(actual.vars.navigation_violation), false);
    assert.equal(actual.vars.navigation_monitoring_started, true);
    passed.push(`${arm}: normal practice advances remain clean`);
    await page.close();
  }

  // Reload must stop immediately, even without a submitted task outcome.
  const timed = await start(2, 'timer_mostrar_mas');
  await timed.locator('#learn-left').click();
  await timed.locator('#choose-right').click();
  await timed.waitForTimeout(1700);
  await timed.reload();
  const reloaded = await waitFlag(2, true);
  assert.equal(reloaded.vars.navigation_reload_count, 1);
  const terminatedReload = await stopped(timed, 2, 'navigation_reload');
  assert.equal(terminatedReload.page_index, 7, 'Unsubmitted task must not advance.');
  assert.equal(terminatedReload.tasks[0].choice, null, 'A partial choice is not fabricated as submitted.');
  assert.ok(terminatedReload.vars.navigation_partial_task, 'Last observed task telemetry is retained.');
  const partial = JSON.parse(terminatedReload.vars.navigation_partial_task);
  assert.equal(partial.submitted, false);
  assert.equal(partial.fields.decision_side, 'right');
  assert.equal(partial.fields.left_ideology_opened, true);
  assert.ok(partial.fields.learn_more_clicks >= 1);
  await timed.reload();
  await stopped(timed, 2, 'navigation_reload');
  passed.push('Timed reload stops immediately, retains partial telemetry and never grants a restart');
  await timed.close();

  // A genuine browser Back, including oTree's stale-URL redirect, is recorded.
  const back = await start(3);
  await back.locator('#choose-left').click();
  await back.locator('#next-btn').click();
  await ready(back);
  await back.goBack({waitUntil:'domcontentloaded'});
  await waitFlag(3, true);
  await stopped(back, 3, 'navigation_history');
  await back.goForward({waitUntil:'domcontentloaded'});
  await stopped(back, 3, 'navigation_history');
  passed.push('Real browser Back and Forward cannot resume a terminated participation');
  await back.close();

  // The deadline's normal automatic advance must not generate a violation.
  const auto = await start(4, 'timer_mostrar_mas');
  const initial = auto.url();
  await auto.waitForURL(url => url.toString() !== initial, {timeout: 15000});
  await ready(auto);
  assert.equal(Boolean((await state(4)).vars.navigation_violation), false);
  passed.push('Automatic nine-second advance is not a navigation violation');
  await auto.close();

  // Initial instructions precede the rule; the participant may reread/reload.
  const introFixture = await prepare(5);
  const intro = await context.newPage();
  await intro.goto(base + introFixture.url);
  await intro.reload();
  assert.equal(Boolean((await state(5)).vars.navigation_violation), false);
  passed.push('Reload before acknowledging initial instructions is not penalized');
  await intro.close();

  // Validation redisplays a form normally, without implying a reload or Back.
  const invalidFixture = await prepare(7, 59);
  const invalid = await context.newPage();
  await invalid.goto(base + invalidFixture.url);
  await Promise.all([
    invalid.waitForNavigation(),
    invalid.evaluate(() => document.getElementById('form').submit())
  ]);
  assert.equal(Boolean((await state(7)).vars.navigation_violation), false);
  assert.ok(await invalid.locator('.otree-form-errors').count() > 0);
  passed.push('A normal form validation error is not a navigation violation');
  await invalid.close();

  // Final-screen revisits and raffle return must not retroactively invalidate.
  const finalFixture = await prepare(6, 200);
  const final = await context.newPage();
  await final.goto(base + finalFixture.url);
  await final.reload();
  assert.equal(Boolean((await state(6)).vars.navigation_violation), false);
  passed.push('Final-screen reload is not penalized');
  await final.close();

  // A later URL/POST cannot bypass a persisted stop or expose the final link.
  const bypass = await prepare(3, 200);
  const blocked = await context.newPage();
  await blocked.goto(base + bypass.url);
  await stopped(blocked, 3, 'navigation_history');
  const posted = await context.request.post(base + bypass.url, {form: {}});
  assert.equal(posted.status(), 200);
  assert.match(await posted.text(), /incompleta/i);
  assert.doesNotMatch(await posted.text(), /bordedata\.cl/);
  const finished = await state(3);
  assert.equal(finished.vars.navigation_violation, true);
  assert.ok(finished.summary.eligible_navigation_incomplete >= 1);
  passed.push('Direct final GET/POST stays blocked; flagged cases remain separately counted');
  await blocked.close();

  // A disconnected live channel cannot lose the flag at the next normal POST.
  const noSocket = await browser.newContext({viewport: {width:1280, height:850}});
  await noSocket.route('**/*', route => new URL(route.request().url()).origin === origin
    ? route.continue() : route.abort());
  await noSocket.routeWebSocket('**', socket => socket.close());
  const postFixture = await prepare(8);
  const post = await noSocket.newPage();
  post.on('pageerror', error => errors.push(error.message));
  await post.goto(base + postFixture.url);
  await post.locator('button.otree-btn-next').click();
  await ready(post);
  await post.reload();
  await waitFlag(8, true);
  await stopped(post, 8, 'navigation_reload');
  assert.equal((await state(8)).page_index, 7);
  passed.push('Disconnected live socket falls back to evidence-only POST and stops without advancing');
  await noSocket.close();

  // An image-loading failure is repaired in place, without a browser reload.
  const retryFixture = await prepare(5, 6, 'timer_mostrar_mas');
  const retry = await context.newPage();
  let failedOnce = false;
  await retry.route('**/*', route => {
    if (route.request().resourceType() === 'image' && !failedOnce) {
      failedOnce = true;
      return route.abort();
    }
    return route.continue();
  });
  await retry.goto(base + retryFixture.url);
  await retry.locator('button.otree-btn-next').click();
  await retry.locator('#stimulus-error').waitFor({state:'visible'});
  await retry.locator('.retry-btn').click();
  await ready(retry);
  assert.equal(Boolean((await state(5)).vars.navigation_violation), false);
  assert.equal(await retry.locator('#timer').innerText(), '9');
  passed.push('Actual image failure and in-place retry remain clean with a full first deadline');
  await retry.close();

  // First two missed MAIN choices are allowed; the third makes 13/15 impossible.
  const missingFixture = await prepare(9, 57, 'timer_mostrar_mas');
  const missing = await context.newPage();
  await missing.goto(base + missingFixture.url);
  for (const expectedIndex of [67, 77]) {
    await ready(missing);
    await missing.waitForURL(url => url.toString().includes(`/${expectedIndex}`), {timeout:15000});
    const actual = await state(9);
    assert.equal(Boolean(actual.vars.study_terminated), false);
    assert.equal(Boolean(actual.vars.navigation_violation), false);
  }
  await stopped(missing, 9, 'insufficient_choices');
  const missingState = await state(9);
  assert.equal(missingState.page_index, 77, 'Stop on the actual third submitted task.');
  assert.equal(missingState.vars.study_termination_submitted_round, 8);
  assert.equal(missingState.tasks.filter(row => row.expired).length, 3);
  assert.ok(missingState.tasks.filter(row => row.round >= 9).every(row => row.choice === null));
  passed.push('Two missing main choices allowed; third stops immediately, with reason and all raw rows retained');
  await missing.close();

  // A legitimate completion with thirteen choices still has its original link.
  const allowedFixture = await context.request.get(`${base}/__test__/prepare?person=10&index=200&arm=timer_mostrar_mas&missings=2`);
  const allowedUrl = (await allowedFixture.json()).url;
  const allowed = await context.newPage();
  await allowed.goto(base + allowedUrl);
  assert.equal(await allowed.locator('a[href="https://bordedata.cl/encuestas/survey/42"]').count(), 1);
  assert.equal(Boolean((await state(10)).vars.study_terminated), false);
  passed.push('Eligible final-screen 13/15 completion retains the exact existing raffle link');
  await allowed.close();

  // Even a stale/manual final index cannot make twelve choices complete.
  const deniedFixture = await context.request.get(`${base}/__test__/prepare?person=11&index=200&missings=3`);
  const denied = await context.newPage();
  await denied.goto(base + (await deniedFixture.json()).url);
  assert.match(await denied.locator('body').innerText(), /incompleta/i);
  assert.equal(await denied.locator('a[href*="bordedata.cl"]').count(), 0);
  passed.push('Final-screen eligibility guard withholds raffle below thirteen valid choices');
  await denied.close();

  assert.deepEqual(errors, [], 'No uncaught application JavaScript errors.');
  await browser.close();
  console.log(JSON.stringify({passed}, null, 2));
})().catch(error => {console.error(error); process.exit(1);});
'''


class NavigationBrowserTests(unittest.TestCase):
    def test_real_chrome_navigation_and_persisted_flags(self):
        source = Path(__file__).resolve().parent
        interpreter = source / '.venv' / 'bin' / 'python'
        if not interpreter.exists():
            interpreter = Path(sys.executable)
        runtime = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
        node = shutil.which('node') or str(runtime / 'bin/node')
        playwright = runtime / 'node_modules/playwright'
        self.assertTrue(playwright.exists(), 'Install Playwright before this browser-only test.')
        with socket.socket() as available:
            available.bind(('127.0.0.1', 0))
            port = available.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix='conjoint-navigation-browser-') as temporary:
            project = Path(temporary)
            for name in ('settings.py', 'completion_rules.py', 'quota_monitor_data.py'):
                shutil.copy2(source / name, project / name)
            shutil.copytree(source / 'conjoint', project / 'conjoint',
                            ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(source / '_templates', project / '_templates')
            (project / '_static').symlink_to(source / '_static', target_is_directory=True)
            environment = {key: value for key, value in os.environ.items()
                if not any(part in key.upper() for part in
                           ('DATABASE', 'POSTGRES', 'RENDER', 'SENTRY', 'OTREE'))}
            base = f'http://127.0.0.1:{port}'
            environment.update(DATABASE_URL='sqlite:///db.sqlite3', OTREE_PRODUCTION='0',
                OTREE_AUTH_LEVEL='', PYTHONPATH=str(project),
                OTREE_SECRET_KEY='disposable-navigation-test-not-a-live-secret',
                NAVIGATION_TEST_PORT=str(port), NAVIGATION_TEST_URL=base,
                NAVIGATION_TEST_PLAYWRIGHT=str(playwright))
            with tempfile.TemporaryFile(mode='w+') as server_log:
                server = subprocess.Popen([str(interpreter), '-c', SERVER], cwd=project,
                    env=environment, stdout=server_log, stderr=server_log, text=True)
                try:
                    for _ in range(100):
                        if server.poll() is not None:
                            break
                        try:
                            with urlopen(base + '/__test__/ready', timeout=0.2) as response:
                                if response.status == 200:
                                    break
                        except OSError:
                            time.sleep(0.05)
                    else:
                        self.fail('Disposable oTree server did not become ready.')
                    self.assertIsNone(server.poll(), 'Disposable server stopped unexpectedly.')
                    result = subprocess.run([node, '-e', BROWSER], cwd=project,
                        env=environment, capture_output=True, text=True, timeout=150)
                    print(result.stdout, end='')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(len(json.loads(result.stdout)['passed']), 14)
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)
                    server_log.seek(0)
                    diagnostics = server_log.read()
                    if 'Traceback' in diagnostics:
                        print(diagnostics)


if __name__ == '__main__':
    unittest.main()
