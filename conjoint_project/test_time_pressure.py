"""Simulate the nine-second study only in a disposable local project.

Run ``.venv/bin/python test_time_pressure.py``. Source files are copied into a
temporary directory, DATABASE_URL is replaced with temporary SQLite, and no
production endpoint is contacted. Actual rendered task JavaScript is executed
by Node's built-in VM with a deterministic clock and a small simulated DOM.
This complements oTree's HTTP/form/export tests without needing a browser or
waiting nine real seconds for each timeout. No simulated response is retained.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


# This script runs in the disposable child process, not the actual project.
DISPOSABLE_CHECK = r'''
import asyncio
import csv
import io
import json
from pathlib import Path
import re
import subprocess
import unittest
from unittest.mock import patch

asyncio.set_event_loop(asyncio.new_event_loop())
from otree.main import setup
setup()
from otree.asgi import app
from otree.database import db, engine
from otree.lookup import url_i_should_be_on
from otree.models import Participant
from otree.session import create_session
from starlette.testclient import TestClient
from conjoint.models import (C, CANDIDATE_DATA, Player, assign_candidates,
                             custom_export, ensure_participant_vars)
from conjoint.pages import page_sequence
from completion_rules import classify_completion
from quota_monitor_data import _metadata, _page_layout

ARMS = ('control_ver_mas', 'timer_mostrar_mas', 'captcha_ver_mas')
session = create_session('colombia_conjoint', num_participants=12)
people = list(Participant.objects_filter(session=session).order_by('id_in_session'))
with patch('conjoint.models.random.choice', side_effect=ARMS * 4) as treatment_draw:
    # With old-format oTree apps initialization can be lazy at the first page.
    # Run that actual helper for every round to test stable assignment directly.
    for person in people:
        for row in Player.objects_filter(participant=person).order_by('round_number'):
            ensure_participant_vars(row)
    assert treatment_draw.call_count == 12, 'Assignment must happen once per person.'
    assert all(call.args == (C.TREATMENT_ARMS,) for call in treatment_draw.call_args_list)
codes = [person.code for person in people]
session_code = session.code
layout = _page_layout(session, _metadata())
assert str(Path(engine.url.database).resolve()).startswith(str(Path.cwd()))
assert Path(engine.url.database).resolve() == Path.cwd() / 'db.sqlite3'
db.commit()
client = TestClient(app)


def prepare(code, index):
    """Position a simulated eligible participant at a local oTree page."""
    db.new_session()
    person = Participant.objects_get(code=code)
    person.visited = True
    person._index_in_pages = index
    baseline = Player.objects_get(participant=person, round_number=1)
    baseline.consent_accepted = True
    baseline.country_of_residence = 'CL'
    baseline.nationality = 'FI'
    baseline.lived_in_colombia = 'no'
    baseline.age_years = 40
    baseline.gender_identity = 'mujer'
    baseline.education_level = 'postgrado'
    baseline.occupation_status = 'estudia'
    url = url_i_should_be_on(code, person.session.code, index)
    db.commit()
    return url


def rendered(code, index):
    url = prepare(code, index)
    response = client.get(url)
    assert response.status_code == 200, response.text[:800]
    return url, response.text


def readable(document):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', document))


def row_for(code, round_number):
    person = Participant.objects_get(code=code)
    return Player.objects_get(participant=person, round_number=round_number)


def post_and_advance(url, payload):
    response = client.post(url, data=payload)
    while response.status_code in (302, 303, 307):
        response = client.get(response.headers['location'])
    return response


# Use six rendered pages: practice and main decision in each actual arm.
specimens = {}
for person_index, arm in enumerate(ARMS):
    for round_number in (1, 6):
        task_index = (round_number - 1) * len(page_sequence) + 7
        _, html = rendered(codes[person_index], task_index)
        specimens[f'{arm}:{round_number}'] = html

node_result = subprocess.run(
    [__import__('os').environ['CONJOINT_TEST_NODE'], 'javascript_timer_check.js'],
    input=json.dumps(specimens), text=True, capture_output=True, timeout=30,
)
assert node_result.returncode == 0, node_result.stdout + node_result.stderr
javascript_results = json.loads(node_result.stdout)
print('JavaScript scenarios passed:', javascript_results['passed'])


class NineSecondTests(unittest.TestCase):
    def test_each_arm_is_fixed_across_five_practice_and_fifteen_main_tasks(self):
        db.new_session()
        for person_index, code in enumerate(codes):
            person = Participant.objects_get(code=code)
            original_arm = ARMS[person_index % 3]
            seen = set()
            for round_number in range(1, 21):
                row = Player.objects_get(participant=person, round_number=round_number)
                assign_candidates(row)
                self.assertEqual(person.vars['treatment_arm'], original_arm)
                self.assertEqual(row.treatment_arm, original_arm)
                self.assertEqual(row.info_condition, original_arm)
                self.assertEqual(row.timed_task, original_arm == 'timer_mostrar_mas')
                self.assertEqual(row.countdown_seconds, 9)
                self.assertEqual(row.is_practice_round, round_number <= 5)
                self.assertEqual(row.main_round_number, max(0, round_number - 5))
                self.assertNotIn(row.left_candidate_id, seen)
                self.assertNotIn(row.right_candidate_id, seen)
                self.assertNotEqual(row.left_candidate_id, row.right_candidate_id)
                seen.update((row.left_candidate_id, row.right_candidate_id))
            self.assertEqual(len(seen), 40)
        db.commit()

    def test_instructions_match_actual_arm_before_and_after_practice(self):
        for person_index, arm in enumerate(ARMS):
            for instruction_index in (6, 48):
                with self.subTest(arm=arm, instruction_index=instruction_index):
                    _, html = rendered(codes[person_index], instruction_index)
                    text = readable(html)
                    self.assertIn('Instrucciones', text)
                    if arm == 'timer_mostrar_mas':
                        self.assertIn('9 segundos para cada decisión', text)
                        self.assertNotIn('20 segundos', text)
                        self.assertIn('automáticamente', text)
                        self.assertNotIn('resolver correctamente una suma', text)
                    elif arm == 'captcha_ver_mas':
                        self.assertIn('resolver correctamente una suma', text)
                        self.assertNotIn('segundos para cada decisión', text)
                        self.assertNotIn('plataforma avanzará automáticamente', text)
                    else:
                        self.assertNotIn('segundos para cada decisión', text)
                        self.assertNotIn('resolver correctamente una suma', text)
                        self.assertNotIn('plataforma avanzará automáticamente', text)

    def test_timeout_posts_preserve_zero_one_two_opened_texts_and_skip_followups(self):
        for opened_count, person_index in enumerate((4, 7, 10)):
            with self.subTest(opened_texts=opened_count):
                code = codes[person_index]
                url, _ = rendered(code, 57)  # Main decision 1, actual timed arm.
                payload = javascript_results[f'timeout_{opened_count}']['fields']
                response = post_and_advance(url, payload)
                self.assertEqual(response.status_code, 200, response.text[:800])
                self.assertNotIn('¿habría votado usted', readable(response.text).lower())
                self.assertIn('Decisión 2 de 15', readable(response.text))
                db.new_session()
                row = row_for(code, 6)
                self.assertIsNone(row.field_maybe_none('decision_candidate_id'))
                self.assertIsNone(row.field_maybe_none('decision_side'))
                self.assertTrue(row.countdown_expired)
                self.assertEqual(row.time_spent_seconds, 9)
                self.assertEqual(row.stimulus_load_seconds, 0)
                self.assertEqual(row.learn_more_clicks, opened_count)
                self.assertEqual(row.left_ideology_opened, opened_count >= 1)
                self.assertEqual(row.right_ideology_opened, opened_count == 2)
                self.assertEqual(row.mouse_distance_px, 5)
                self.assertAlmostEqual(row.left_hover_seconds, 8.5)
                for name in ('realistic_vote', 'decision_factors',
                             'rushed_scale', 'info_cost_scale'):
                    self.assertIn(row.field_maybe_none(name), (None, ''))

    def test_expiry_preserves_a_choice_already_registered_and_asks_followups(self):
        code = codes[1]
        url, _ = rendered(code, 57)
        db.new_session()
        row = row_for(code, 6)
        payload = dict(javascript_results['selected_at_expiry']['fields'])
        payload['decision_candidate_id'] = row.left_candidate_id
        response = post_and_advance(url, payload)
        self.assertEqual(response.status_code, 200, response.text[:800])
        self.assertIn('¿habría votado usted', readable(response.text).lower())
        db.new_session()
        saved = row_for(code, 6)
        self.assertEqual(saved.decision_candidate_id, saved.left_candidate_id)
        self.assertEqual(saved.decision_side, 'left')
        self.assertTrue(saved.countdown_expired)
        self.assertAlmostEqual(saved.time_to_first_choice_seconds, 8.999)

    def test_completion_rule_still_allows_two_but_not_three_missing_main_choices(self):
        for valid, expected in ((15, True), (14, True), (13, True), (12, False)):
            result = classify_completion(eligible=True, reached_final_screen=True,
                                         submitted_main_tasks=15, valid_main_choices=valid)
            self.assertEqual(result['study_complete'], expected)
            self.assertEqual(result['main_tasks_missing_selection'], 15 - valid)
        result = classify_completion(eligible=True, reached_final_screen=False,
                                     submitted_main_tasks=14, valid_main_choices=14)
        self.assertFalse(result['study_complete'])

    def test_previous_twenty_second_responses_keep_their_original_metadata(self):
        # Emulate pre-upgrade stored rows. Existing responses are not rewritten
        # and a returning person never practices20 but receives9 on later tasks.
        db.new_session()
        previous = create_session('colombia_conjoint', num_participants=2)
        previous_people = list(Participant.objects_filter(session=previous).order_by('id_in_session'))
        started, untouched = previous_people
        first = Player.objects_get(participant=started, round_number=1)
        started.vars['treatment_arm'] = 'timer_mostrar_mas'
        assign_candidates(first)
        first.countdown_seconds = 20
        first.decision_side = 'left'
        first.decision_candidate_id = first.left_candidate_id
        first.time_spent_seconds = 16.5
        first.left_ideology_opened = True
        del started.vars['countdown_seconds']
        saved = (first.left_candidate_id, first.right_candidate_id,
                 first.countdown_seconds, first.decision_candidate_id,
                 first.time_spent_seconds, first.left_ideology_opened)
        ensure_participant_vars(first)
        assign_candidates(first)
        self.assertEqual(started.vars['countdown_seconds'], 20)
        self.assertEqual(saved, (first.left_candidate_id, first.right_candidate_id,
                                first.countdown_seconds, first.decision_candidate_id,
                                first.time_spent_seconds, first.left_ideology_opened))
        for round_number in (5, 6, 20):
            future = Player.objects_get(participant=started, round_number=round_number)
            assign_candidates(future)
            self.assertEqual(future.countdown_seconds, 20)
            self.assertEqual(future.treatment_arm, 'timer_mostrar_mas')
        started_code = started.code
        untouched_code = untouched.code
        for row in Player.objects_filter(participant=untouched):
            row.countdown_seconds = 20  # Old database default, no stimulus shown.
        untouched.vars['treatment_arm'] = 'timer_mostrar_mas'
        db.commit()
        for index in (6, 48):
            _, html = rendered(started_code, index)
            self.assertIn('20 segundos para cada decisión', readable(html))
        _, html = rendered(untouched_code, 6)
        self.assertIn('9 segundos para cada decisión', readable(html))
        _, html = rendered(untouched_code, 7)
        self.assertIn('let countdownSeconds = 9;', html)

    def test_z_export_contains_arm_deadline_task_ids_choices_and_profile_telemetry(self):
        db.new_session()
        players = list(Player.objects_filter(session=session).order_by('id'))
        header, *values = list(custom_export(players))
        self.assertEqual(len(header), len(set(header)))
        expected = ('treatment_arm', 'timed_task', 'info_condition', 'countdown_seconds',
                    'is_practice_round', 'main_round_number', 'countdown_expired',
                    'decision_candidate_id', 'decision_side', 'left_candidate_id',
                    'right_candidate_id', 'left_texto', 'right_texto',
                    'left_dataset_row_json', 'right_dataset_row_json',
                    'left_ideology_opened', 'right_ideology_opened',
                    'learn_more_clicks', 'info_cost_attempts', 'info_cost_task_completed',
                    'time_spent_seconds', 'time_to_first_choice_seconds',
                    'stimulus_load_seconds', 'choice_changes', 'mouse_distance_px',
                    'left_hover_seconds', 'right_hover_seconds')
        self.assertTrue(all('player.' + field in header for field in expected))
        records = [dict(zip(header, value)) for value in values]
        for record in records:
            self.assertEqual(record['player.countdown_seconds'], 9)
            self.assertIn(record['player.treatment_arm'], ARMS)
            self.assertEqual(record['player.timed_task'],
                             record['player.treatment_arm'] == 'timer_mostrar_mas')
            for side in ('left', 'right'):
                candidate = CANDIDATE_DATA[record[f'player.{side}_candidate_id']]
                self.assertEqual(record[f'player.{side}_dataset_row_json'], candidate['dataset_row_json'])
                self.assertEqual(record[f'player.{side}_texto'], candidate['texto'])
        missing = next(record for record in records
                       if record['participant.code'] == codes[4]
                       and record['subsession.round_number'] == 6)
        self.assertIsNone(missing['player.decision_candidate_id'])
        self.assertEqual(missing['player.countdown_expired'], True)
        self.assertEqual(missing['player.main_round_number'], 1)


result = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(NineSecondTests))
if not result.wasSuccessful():
    raise SystemExit(1)
print('DISPOSABLE_NINE_SECOND_CHECK_PASSED')
'''


# The actual Task.html script is extracted from oTree's rendered HTML. Only
# browser services (DOM, image events, animation frames and clocks) are mocked.
JAVASCRIPT_CHECK = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const specimens = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = {passed: []};

async function task(arm, round=6, imageState='ready') {
  const html = specimens[`${arm}:${round}`];
  const script = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)]
    .map(match => match[1]).find(source => source.includes('function beginDecision()'));
  assert.ok(script, 'Run actual rendered task JavaScript.');
  let now = 0, nextTimer = 1;
  const timers = new Map(), animation = [];
  const elements = new Map();
  class Element {
    constructor(id, value='') {
      this.id=id; this.value=value; this.disabled=true; this.hidden=false;
      this.style={setProperty(){}}; this.textContent=''; this.listeners={};
      this.classList={add(){}, remove(){}};
      this.complete=imageState !== 'delayed';
      this.naturalWidth=imageState === 'failed' ? 0 : 400;
      this.naturalHeight=this.naturalWidth;
    }
    addEventListener(name, callback){(this.listeners[name] ||= []).push(callback);}
    removeEventListener(name, callback){this.listeners[name]=(this.listeners[name]||[]).filter(fn=>fn!==callback);}
    dispatch(name,event={}){for(const fn of [...(this.listeners[name]||[])]) fn(event);}
    setAttribute(){}
    matches(){return false;}
    getBoundingClientRect(){return {top:100};}
    decode(){return Promise.resolve();}
  }
  for (const match of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)) {
    const value=match[0].match(/\bvalue="([^"]*)"/);
    elements.set(match[1],new Element(match[1],value ? value[1] : ''));
  }
  const form = new Element('form'); form.submissions=[];
  const fields=()=>Object.fromEntries([...elements].filter(([id])=>id.startsWith('id_')).map(([id,node])=>[id.slice(3),node.value]));
  class HTMLFormElement {}
  HTMLFormElement.prototype.submit=function(){this.submissions.push(fields());};
  elements.get('next-btn').form=form;
  const controls=[...html.matchAll(/<[^>]+data-task-control[^>]*>/g)]
    .map(match=>match[0].match(/id="([^"]+)"/)).filter(Boolean).map(match=>elements.get(match[1]));
  const document={
    getElementById:id=>elements.get(id)||null,
    querySelector:()=>new Element('wrapper'),
    querySelectorAll:()=>controls,
    addEventListener(){},
  };
  function schedule(fn,delay,interval){const id=nextTimer++;timers.set(id,{fn,at:now+delay,interval});return id;}
  const context=vm.createContext({document,HTMLFormElement,performance:{now:()=>now},
    window:{innerHeight:900,addEventListener(){}},
    requestAnimationFrame:fn=>animation.push(fn),
    setInterval:(fn,delay)=>schedule(fn,delay,delay),
    setTimeout:(fn,delay)=>schedule(fn,delay,0),
    clearInterval:id=>timers.delete(id),clearTimeout:id=>timers.delete(id),console});
  vm.runInContext(script,context);
  const invoke=(name,...args)=>vm.runInContext(`${name}(...${JSON.stringify(args)})`,context);
  async function settle(){for(let step=0;step<12;step++)await Promise.resolve();while(animation.length)animation.shift()();}
  function advance(milliseconds){
    const end=now+milliseconds;
    while(true){
      const due=[...timers].filter(([,timer])=>timer.at<=end).sort((a,b)=>a[1].at-b[1].at||a[0]-b[0]);
      if(!due.length)break;
      const [id,timer]=due[0];now=timer.at;
      if(timer.interval)timer.at+=timer.interval;else timers.delete(id);
      timer.fn();
    }
    now=end;
  }
  const choose=(side='left')=>invoke('chooseCandidate',side==='left'?'candidate-left':'candidate-right',side);
  const manualSubmit=()=>{
    const event={prevented:false,preventDefault(){this.prevented=true;}};
    form.dispatch('submit',event);if(!event.prevented)HTMLFormElement.prototype.submit.call(form);
  };
  await settle();
  return {context,invoke,elements,form,fields,advance,settle,choose,manualSubmit,
    load(){for(const side of ['left','right'])elements.get(`${side}-candidate-image`).dispatch('load');},
    clockJump(milliseconds){now+=milliseconds;}};
}

async function check(name,run){await run();results.passed.push(name);}
(async()=>{
  for(const round of [1,6]){
    for(const opened of [0,1,2]){
      await check(`timed ${round===1?'practice':'main'} timeout with ${opened} texts`,async()=>{
        const t=await task('timer_mostrar_mas',round);
        assert.equal(t.elements.get('timer').textContent,9);
        t.advance(500);t.invoke('startHover','left');
        t.invoke('updateMouseDistance',{clientX:0,clientY:0});
        t.invoke('updateMouseDistance',{clientX:3,clientY:4});
        if(opened>=1)t.invoke('startReveal','left');
        if(opened===2)t.invoke('startReveal','right');
        t.advance(8499);assert.equal(t.form.submissions.length,0);
        t.advance(1);assert.equal(t.form.submissions.length,1);
        const fields=t.form.submissions[0];
        assert.equal(fields.time_spent_seconds,'9.000');
        assert.equal(fields.decision_side,'timeout');
        assert.equal(fields.countdown_expired,'True');
        assert.equal(Number(fields.learn_more_clicks),opened);
        assert.equal(fields.left_ideology_opened,opened>=1?'True':'False');
        assert.equal(fields.right_ideology_opened,opened===2?'True':'False');
        assert.equal(fields.mouse_distance_px,'5.00');
        assert.equal(fields.left_hover_seconds,'8.500');
        const before=JSON.stringify(t.fields());
        t.advance(1000);t.choose();t.invoke('startReveal','left');t.invoke('autoAdvanceAfterTimeout');
        assert.equal(t.form.submissions.length,1);assert.equal(JSON.stringify(t.fields()),before);
        if(round===6)results[`timeout_${opened}`]={fields};
      });
    }
  }
  await check('choice at 8.999 seconds retained when deadline advances',async()=>{
    const t=await task('timer_mostrar_mas');t.advance(8999);t.choose();t.advance(1);
    assert.equal(t.form.submissions.length,1);
    assert.equal(t.form.submissions[0].decision_side,'left');
    assert.equal(t.form.submissions[0].time_to_first_choice_seconds,'8.999');
    assert.equal(t.form.submissions[0].countdown_expired,'True');
    results.selected_at_expiry={fields:t.form.submissions[0]};
  });
  await check('choice at exact deadline rejected even if timer callback delayed',async()=>{
    const t=await task('timer_mostrar_mas');t.clockJump(9000);t.choose();
    assert.equal(t.form.submissions.length,1);assert.equal(t.fields().decision_side,'timeout');
  });
  await check('changes of choice and manual early submission recorded',async()=>{
    const t=await task('timer_mostrar_mas');t.advance(1000);t.choose();t.advance(2000);t.choose('right');
    t.advance(1500);t.manualSubmit();t.advance(10000);
    assert.equal(t.form.submissions.length,1);
    assert.equal(t.fields().decision_side,'right');assert.equal(Number(t.fields().choice_changes),1);
    assert.equal(t.fields().time_to_first_choice_seconds,'1.000');
    assert.equal(t.fields().time_spent_seconds,'4.500');assert.equal(t.fields().countdown_expired,'False');
  });
  await check('slow images do not consume decision time',async()=>{
    const t=await task('timer_mostrar_mas',6,'delayed');t.advance(12000);t.choose();
    assert.equal(t.form.submissions.length,0);assert.equal(t.fields().decision_side,'');
    t.load();await t.settle();assert.equal(t.fields().stimulus_load_seconds,'12.000');
    t.advance(8999);assert.equal(t.form.submissions.length,0);t.advance(1);
    assert.equal(t.form.submissions.length,1);assert.equal(t.fields().time_spent_seconds,'9.000');
  });
  await check('failed image prevents interaction and prevents starting timer',async()=>{
    const t=await task('timer_mostrar_mas',6,'failed');t.advance(60000);t.choose();
    assert.equal(t.form.submissions.length,0);assert.equal(t.fields().time_spent_seconds,'0');
    assert.equal(t.elements.get('stimulus-error').hidden,false);
  });
  for(const arm of ['control_ver_mas','captcha_ver_mas']){
    for(const round of [1,6]){
      await check(`${arm} ${round===1?'practice':'main'} remains untimed after 60 seconds`,async()=>{
        const t=await task(arm,round);t.advance(60000);
        assert.equal(t.form.submissions.length,0);assert.equal(t.fields().countdown_expired,'False');
        t.invoke('startReveal','left');
        if(arm==='captcha_ver_mas'){
          assert.equal(t.fields().left_ideology_opened,'False');
          t.elements.get('left-cost-answer').value='-1';t.invoke('checkCostTask','left');
          assert.equal(t.fields().left_ideology_opened,'False');
          t.elements.get('left-cost-answer').value=vm.runInContext('captchaAnswers.left',t.context);
          t.invoke('checkCostTask','left');
          assert.equal(t.fields().info_cost_task_completed,'True');
          assert.equal(Number(t.fields().info_cost_attempts),2);
        }
        assert.equal(t.fields().left_ideology_opened,'True');
        t.choose();t.manualSubmit();assert.equal(t.form.submissions.length,1);
        assert.equal(t.fields().time_spent_seconds,'60.000');
      });
    }
  }
  process.stdout.write(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''


class DisposableTimePressureTests(unittest.TestCase):
    def test_nine_second_http_javascript_and_exports(self):
        source = Path(__file__).resolve().parent
        interpreter = source / '.venv' / 'bin' / 'python'
        if not interpreter.exists():
            interpreter = Path(sys.executable)
        node = shutil.which('node')
        if not node:
            bundled_node = (Path.home() / '.cache' / 'codex-runtimes' /
                            'codex-primary-runtime' / 'dependencies' / 'node' / 'bin' / 'node')
            if bundled_node.exists():
                node = str(bundled_node)
        self.assertIsNotNone(node, 'Node is required to execute the actual task JavaScript.')
        with tempfile.TemporaryDirectory(prefix='conjoint-nine-second-') as temporary:
            project = Path(temporary)
            for filename in ('settings.py', 'quota_monitor_data.py', 'completion_rules.py'):
                shutil.copy2(source / filename, project / filename)
            shutil.copytree(source / 'conjoint', project / 'conjoint',
                            ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(source / '_templates', project / '_templates')
            (project / '_static').symlink_to(source / '_static', target_is_directory=True)
            # The harness is copied as ordinary test source, never into the app.
            (project / 'javascript_timer_check.js').write_text(JAVASCRIPT_CHECK)
            environment = {key: value for key, value in os.environ.items()
                           if not any(part in key.upper() for part in
                                      ('DATABASE', 'POSTGRES', 'RENDER', 'SENTRY', 'OTREE'))}
            environment.update({
                'DATABASE_URL': 'sqlite:///db.sqlite3', 'OTREE_PRODUCTION': '0',
                'OTREE_AUTH_LEVEL': '', 'PYTHONPATH': str(project),
                'OTREE_SECRET_KEY': 'disposable-nine-second-test-not-a-live-secret',
                'CONJOINT_TEST_NODE': node,
            })
            result = subprocess.run([str(interpreter), '-c', DISPOSABLE_CHECK],
                                    cwd=project, env=environment, capture_output=True,
                                    text=True, timeout=120)
            print(result.stdout, end='')
            print(result.stderr, end='')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('DISPOSABLE_NINE_SECOND_CHECK_PASSED', result.stdout)


if __name__ == '__main__':
    unittest.main()
