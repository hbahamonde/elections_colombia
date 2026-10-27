"""Navigation validation and disposable oTree checks; never open live data."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from conjoint.navigation import (
    MAX_NAVIGATION_EVENTS, bounded_partial_task, merge_navigation_events, submitted_task_rounds,
)
from types import SimpleNamespace
from completion_rules import classify_completion


class NavigationMergeTests(unittest.TestCase):
    def merge(self, values=None, events=None, current=200):
        def lookup(index):
            if index == 200:
                return 'Summary', 20
            if index == 5:
                return 'Questionnaire', 1
            return 'Task', 1
        return merge_navigation_events(
            values or {}, events or [], current_page_index=current,
            max_page_index=200, lookup_page=lookup,
            now=datetime(2026, 10, 27, 12, tzinfo=timezone.utc),
        )

    def test_pre_instruction_events_do_not_exclude(self):
        data, ack = self.merge(events=[{'id': 'a', 'type': 'reload', 'page_index': 7}])
        self.assertEqual(data, {})
        self.assertEqual(ack, [])

    def test_reload_history_and_retry_are_persisted_once(self):
        events = [{'id': 'a', 'type': 'reload', 'page_index': 7},
                  {'id': 'b', 'type': 'history', 'page_index': 17}]
        values, ack = self.merge({'navigation_monitoring_started': True}, events)
        self.assertEqual(ack, ['a', 'b'])
        self.assertTrue(values['navigation_violation'])
        self.assertEqual(values['navigation_reload_count'], 1)
        self.assertEqual(values['navigation_history_count'], 1)
        stored = json.loads(values['navigation_events'])
        self.assertEqual(stored[0]['server_utc'], '2026-10-27T12:00:00.000+00:00')
        repeated, ack = self.merge(values, events)
        self.assertEqual(repeated, values)
        self.assertEqual(ack, ['a', 'b'])

    def test_final_screen_reload_is_ignored_but_earlier_queued_event_is_recorded(self):
        events = [{'id': 'final', 'type': 'reload', 'page_index': 200},
                  {'id': 'prior', 'type': 'history', 'page_index': 197}]
        data, ack = self.merge({'navigation_monitoring_started': True}, events)
        self.assertEqual(ack, ['final', 'prior'])
        self.assertEqual(data['navigation_history_count'], 1)
        self.assertEqual(data['navigation_reload_count'], 0)
        self.assertEqual(len(json.loads(data['navigation_events'])), 1)
        only_final, _ = self.merge({'navigation_monitoring_started': True}, events[:1])
        self.assertNotIn('navigation_violation', only_final)

    def test_malformed_future_and_screening_events_cannot_change_status(self):
        events = [None, {}, {'id': 'x', 'type': 'history', 'page_index': True},
                  {'id': 'x', 'type': 'history', 'page_index': 18},
                  {'id': 'x', 'type': 'reload', 'page_index': 5},
                  {'id': 'x', 'type': 'bad', 'page_index': 7},
                  {'id': '<script>', 'type': 'reload', 'page_index': 7}]
        data, ack = self.merge({'navigation_monitoring_started': True}, events, current=17)
        self.assertEqual(data, {'navigation_monitoring_started': True})
        self.assertEqual(ack, [])

    def test_log_is_bounded(self):
        values = {'navigation_monitoring_started': True}
        for batch in range(12):
            values, _ = self.merge(values, [
                {'id': f'{batch}-{i}', 'type': 'reload', 'page_index': 7}
                for i in range(20)])
        self.assertEqual(len(json.loads(values['navigation_events'])), MAX_NAVIGATION_EVENTS)
        self.assertEqual(values['navigation_reload_count'], MAX_NAVIGATION_EVENTS)

    def test_completion_preserves_final_arrival_and_choices_but_excludes_flagged_case(self):
        for final in (False, True):
            result = classify_completion(
                eligible=True, reached_final_screen=final,
                submitted_main_tasks=15, valid_main_choices=15,
                navigation_violation=True)
            self.assertFalse(result['study_complete'])
            self.assertEqual(result['completion_status'], 'navigation_incomplete')
            self.assertEqual(result['eligible_final_screen_completion'], final)
            self.assertEqual(result['main_tasks_with_selection'], 15)

    def test_stop_round_counts_only_its_real_submitted_task(self):
        indices = {6: 57, 7: 67, 8: 77, 9: 87}
        values = {'study_terminated': True, 'study_termination_page_index': 77,
                  'study_termination_submitted_round': 8}
        self.assertEqual(submitted_task_rounds(77, indices, values), {6, 7, 8})
        self.assertEqual(submitted_task_rounds(77, indices, {}), {6, 7})
        values['study_termination_submitted_round'] = 9
        self.assertEqual(submitted_task_rounds(77, indices, values), {6, 7})

    def test_partial_telemetry_is_bounded_and_never_fabricates_a_choice(self):
        player = SimpleNamespace(
            participant=SimpleNamespace(_index_in_pages=77), round_number=8,
            field_maybe_none=lambda name: {'left_candidate_id': 'left', 'right_candidate_id': 'right'}[name],
        )
        fields = {'time_spent_seconds': '4.1', 'learn_more_clicks': '2',
                  'left_ideology_opened': 'True', 'mouse_distance_px': 'NaN',
                  'decision_side': 'left', 'decision_candidate_id': 'WRONG',
                  'unrelated_personal_information': 'must-not-be-stored'}
        snapshot = {'page_index': 77, 'fields': fields}
        result = bounded_partial_task(player, snapshot, lambda index: ('Task', 8))
        self.assertFalse(result['submitted'])
        self.assertEqual(result['fields'], {
            'time_spent_seconds': 4.1, 'learn_more_clicks': 2, 'left_ideology_opened': True,
        })
        snapshot['page_index'] = 87
        self.assertIsNone(bounded_partial_task(player, snapshot, lambda index: ('Task', 9)))


OTREE_CHECK = r'''
import asyncio, json, re
asyncio.set_event_loop(asyncio.new_event_loop())
from otree.main import setup
setup()
from otree.database import db
from otree.export import get_rows_for_wide_csv
from otree.models import Participant
from otree.session import create_session
from sqlalchemy import inspect
from conjoint.models import Player, custom_export, C
from conjoint.pages import Intro, Task, PracticeDone, FollowUp, Summary
from conjoint.navigation import start_navigation_monitoring
from quota_monitor_data import _metadata, _page_layout, _load_records, _aggregate_records

session = create_session('colombia_conjoint', num_participants=3)
people = list(Participant.objects_filter(session=session))
layout = _page_layout(session, _metadata())
for person in people:
    person.visited = True
    person._index_in_pages = layout['summary']
    baseline = Player.objects_get(participant=person, round_number=1)
    baseline.consent_accepted = True
    baseline.country_of_residence = 'CL'
    baseline.nationality = 'FI'
    baseline.lived_in_colombia = 'no'
    baseline.age_years = 40
    baseline.gender_identity = 'mujer'
    baseline.education_level = 'postgrado'
    baseline.occupation_status = 'estudia'
    for row in Player.objects_filter(participant=person):
        row.left_candidate_id = 'left-profile'
        row.right_candidate_id = 'right-profile'
        row.decision_side = 'left'
        row.decision_candidate_id = 'left-profile'
start_navigation_monitoring(people[0])
row = Player.objects_get(participant=people[0], round_number=C.NUM_ROUNDS)
payload = {'navigation_events': [{'id': 'test-reload', 'type': 'reload', 'page_index': 7}]}
reply = Summary.live_method(row, payload)
assert reply[row.id_in_group]['navigation_ack'] == ['test-reload']
assert reply[row.id_in_group]['navigation_violation'] is True
Summary.live_method(row, payload)
assert people[0].vars['navigation_reload_count'] == 1
start_navigation_monitoring(people[1])
people[1]._index_in_pages = 17
mid = Player.objects_get(participant=people[1], round_number=2)
Task.live_method(mid, {
    'navigation_events': [{'id': 'test-history', 'type': 'history', 'page_index': 17}],
    'navigation_task': {'page_index': 17, 'fields': {'time_spent_seconds': '4.1',
                        'learn_more_clicks': '2', 'decision_side': 'left',
                        'decision_candidate_id': 'left-profile'}},
})
partial = json.loads(people[1].vars['navigation_partial_task'])
assert partial['fields']['time_spent_seconds'] == 4.1
assert partial['submitted'] is False
assert mid.time_spent_seconds == 0
# The third participant represents an untouched historical record.
db.commit()
assert not db._db.dirty
all_rows = list(Player.objects_filter(session=session))
export = list(custom_export(all_rows))
records = [dict(zip(export[0], values)) for values in export[1:]]
for person in people:
    personal = [r for r in records if r['participant.code'] == person.code]
    assert len(personal) == C.NUM_ROUNDS
    if person == people[0]:
        assert all(r['completion_status'] == 'navigation_incomplete' for r in personal)
        assert all(r['participant.navigation_reload_count'] == 1 for r in personal)
    elif person == people[1]:
        assert all(r['completion_status'] == 'navigation_incomplete' for r in personal)
    else:
        assert all(r['study_complete'] for r in personal)
        assert all(r['participant.navigation_violation'] is None for r in personal)
assert not db._db.dirty
snapshot = _aggregate_records('official', _metadata(), layout, *_load_records(session, _metadata()), {})
assert snapshot['summary']['eligible_completed'] == 1
assert snapshot['summary']['eligible_navigation_incomplete'] == 2
assert snapshot['summary']['eligible_in_progress'] == 0
assert snapshot['summary']['eligible_final_screen_completion'] == 2
assert sum(r['navigation_incomplete'] for r in snapshot['treatments']) == 2
assert sum(r['completed_total'] for r in snapshot['quota_dimensions']) == len(_metadata()['dimensions'])
assert all(not col.name.startswith('navigation_') for col in Participant.__table__.columns)
assert all(not col.name.startswith('navigation_') for col in Player.__table__.columns)
assert all(callable(Page.live_method) for Page in (Intro, Task, PracticeDone, FollowUp, Summary))
wide = get_rows_for_wide_csv(session.code)
wide_records = [dict(zip(wide[0], values)) for values in wide[1:]]
assert wide_records[0]['participant.navigation_violation'] == 1
assert wide_records[0]['participant.navigation_reload_count'] == 1
assert wide_records[2]['participant.navigation_monitoring_started'] == ''

# Exercise the real inherited Page.post through local ASGI HTTP only. No socket
# is opened: pending browser events must survive the final form submission.
from otree.asgi import app
from otree.lookup import url_i_should_be_on
from starlette.testclient import TestClient
client = TestClient(app)
http_session = create_session('colombia_conjoint', num_participants=6)
http_codes = [p.code for p in Participant.objects_filter(session=http_session)]
http_session_code = http_session.code
http_layout = _page_layout(http_session, _metadata())
for code in http_codes:
    person = Participant.objects_get(code=code)
    person.visited = True
    person._index_in_pages = http_layout['summary'] - 1
    person.vars['treatment_arm'] = 'control_ver_mas'
    start_navigation_monitoring(person)
    baseline = Player.objects_get(participant=person, round_number=1)
    baseline.consent_accepted = True
    baseline.country_of_residence = 'CL'
    baseline.nationality = 'FI'
    baseline.lived_in_colombia = 'no'
    baseline.age_years = 40
    baseline.gender_identity = 'mujer'
    baseline.education_level = 'postgrado'
    baseline.occupation_status = 'estudia'
    for task in Player.objects_filter(participant=person):
        task.treatment_arm = 'control_ver_mas'
        task.info_condition = 'control_ver_mas'
        task.left_candidate_id = 'left-profile'
        task.right_candidate_id = 'right-profile'
        task.decision_side = 'left'
        task.decision_candidate_id = 'left-profile'
db.commit()
last_index = http_layout['summary'] - 1
event = {'id': 'queued-final-post', 'type': 'reload', 'page_index': last_index}
hidden_values = [json.dumps([event, event]), '{invalid', ' ' * 32769,
                 json.dumps([{'id': 'bad', 'type': 'invalid', 'page_index': last_index}])]
for code, hidden in zip(http_codes, hidden_values):
    response = client.post(url_i_should_be_on(code, http_session_code, last_index), data={
        'realistic_vote': 'yes', 'decision_factors': 'apariencia_primera_impresion',
        'rushed_scale': '3', '_study_navigation_events': hidden,
    }, allow_redirects=False)
    assert response.status_code in ((200,) if code == http_codes[0] else (302, 303, 307)), response.text[:1000]
    db.new_session()
    person = Participant.objects_get(code=code)
    assert person._index_in_pages == (last_index if code == http_codes[0] else http_layout['summary'])
    assert person.vars.get('navigation_violation', False) == (code == http_codes[0])
    if code == http_codes[0]:
        assert person.vars['navigation_reload_count'] == 1
    rows = list(Player.objects_filter(participant=person))
    exported = list(custom_export(rows))
    item = dict(zip(exported[0], exported[1]))
    assert item['completion_status'] == ('navigation_incomplete' if code == http_codes[0] else 'complete')

# Failed form validation must not discard the pending navigation evidence.
code = http_codes[4]
response = client.post(url_i_should_be_on(code, http_session_code, last_index), data={
    '_study_navigation_events': json.dumps([event]),
}, allow_redirects=False)
assert response.status_code == 200, response.text[:1000]
db.new_session()
person = Participant.objects_get(code=code)
assert person._index_in_pages == last_index
assert person.vars['navigation_violation'] is True

# The initial Intro POST starts monitoring only after ignoring its own events.
code = http_codes[5]
person = Participant.objects_get(code=code)
person._index_in_pages = 6
for key in list(person.vars):
    if key.startswith('navigation_'):
        del person.vars[key]
db.commit()
response = client.post(url_i_should_be_on(code, http_session_code, 6), data={
    '_study_navigation_events': json.dumps([{'id': 'initial', 'type': 'reload', 'page_index': 6}]),
}, allow_redirects=False)
assert response.status_code in (302, 303, 307), response.text[:1000]
db.new_session()
person = Participant.objects_get(code=code)
assert person.vars['navigation_monitoring_started'] is True
assert person.vars['navigation_violation'] is False
assert person._index_in_pages == 7

# An actual third main timeout records the current POST, then stops on that
# Task URL. The first two main timeouts and all practice timeouts are allowed.
from conjoint.models import assign_candidates
timeout_session = create_session('colombia_conjoint', num_participants=2)
timeout_codes = [p.code for p in Participant.objects_filter(session=timeout_session)]
timeout_session_code = timeout_session.code
timeout_layout = _page_layout(timeout_session, _metadata())
for offset, code in enumerate(timeout_codes):
    person = Participant.objects_get(code=code)
    person.visited = True
    person.vars['treatment_arm'] = 'timer_mostrar_mas'
    person._index_in_pages = 57 if offset == 0 else 7
    baseline = Player.objects_get(participant=person, round_number=1)
    baseline.consent_accepted = True
    baseline.country_of_residence = 'CL'
    baseline.nationality = 'FI'
    baseline.lived_in_colombia = 'no'
    baseline.age_years = 40
    baseline.gender_identity = 'mujer'
    baseline.education_level = 'postgrado'
    baseline.occupation_status = 'estudia'
    for task in Player.objects_filter(participant=person):
        assign_candidates(task)
db.commit()
timeout_payload = {
    'left_ideology_opened': 'True', 'right_ideology_opened': 'False',
    'info_cost_task_completed': 'False', 'info_cost_attempts': '0',
    'decision_candidate_id': 'timeout', 'decision_side': 'timeout',
    'stimulus_load_seconds': '0.1', 'time_spent_seconds': '9',
    'time_to_first_choice_seconds': '0',
    'choice_changes': '0', 'learn_more_clicks': '1', 'mouse_distance_px': '15',
    'left_hover_seconds': '2', 'right_hover_seconds': '0', 'countdown_expired': 'True',
}
for i, index in enumerate((57, 67, 77), 1):
    response = client.post(url_i_should_be_on(timeout_codes[0], timeout_session_code, index),
                           data=timeout_payload, allow_redirects=False)
    assert response.status_code in ((200,) if i == 3 else (302, 303, 307)), re.sub('<[^>]+>', ' ', response.text)[:6000]
    db.new_session()
    person = Participant.objects_get(code=timeout_codes[0])
    assert person.vars.get('study_terminated', False) == (i == 3)
    if i == 3:
        assert person._index_in_pages == 77
        assert person.vars['study_termination_reason'] == 'insufficient_choices'
        assert person.vars['study_termination_submitted_round'] == 8
        rows = list(Player.objects_filter(participant=person))
        exported = list(custom_export(rows))
        item = dict(zip(exported[0], exported[1]))
        assert item['main_tasks_submitted'] == 3, item
        assert item['main_tasks_with_selection'] == 0
        assert item['completion_status'] == 'terminated_insufficient_choices'
        saved = Player.objects_get(participant=person, round_number=8)
        assert saved.time_spent_seconds == 9
        assert saved.learn_more_clicks == 1
        assert saved.field_maybe_none('decision_candidate_id') is None
        blocked = client.post(url_i_should_be_on(timeout_codes[0], timeout_session_code, 77),
                              data={'decision_side': 'left', 'decision_candidate_id': saved.left_candidate_id},
                              allow_redirects=False)
        assert blocked.status_code == 200
        db.new_session()
        saved = Player.objects_get(participant=Participant.objects_get(code=timeout_codes[0]), round_number=8)
        assert saved.field_maybe_none('decision_candidate_id') is None
        snapshot = _aggregate_records('official', _metadata(), timeout_layout,
                                      *_load_records(Participant.objects_get(code=timeout_codes[0]).session, _metadata()), {})
        assert snapshot['summary']['eligible_terminated_incomplete'] == 1
        assert snapshot['summary']['main_tasks_submitted'] == 3

for index in (7, 17, 27):
    response = client.post(url_i_should_be_on(timeout_codes[1], timeout_session_code, index),
                           data=timeout_payload, allow_redirects=False)
    assert response.status_code in (302, 303, 307), response.text[:1500]
    db.new_session()
    assert not Participant.objects_get(code=timeout_codes[1]).vars.get('study_terminated', False)
print('DISPOSABLE_NAVIGATION_CHECK_PASSED')
'''


class DisposableNavigationTests(unittest.TestCase):
    def test_json_export_monitor_and_inherited_live_handlers(self):
        source = Path(__file__).resolve().parent
        interpreter = source / '.venv' / 'bin' / 'python'
        if not interpreter.exists():
            interpreter = Path(sys.executable)
        with tempfile.TemporaryDirectory(prefix='conjoint-navigation-backend-') as temporary:
            project = Path(temporary)
            for name in ('settings.py', 'completion_rules.py', 'quota_monitor_data.py'):
                shutil.copy2(source / name, project / name)
            shutil.copytree(source / 'conjoint', project / 'conjoint',
                            ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(source / '_templates', project / '_templates')
            (project / '_static').symlink_to(source / '_static', target_is_directory=True)
            environment = dict(os.environ)
            environment.update({'DATABASE_URL': 'sqlite:///db.sqlite3', 'OTREE_PRODUCTION': '0',
                                'OTREE_AUTH_LEVEL': '', 'PYTHONPATH': str(project),
                                'OTREE_SECRET_KEY': 'disposable-navigation-check'})
            for name in ('OTREE_IN_MEMORY', 'OTREE_EPHEMERAL', 'SENTRY_DSN', 'OTREE_ERROR_REPORT_ENDPOINT'):
                environment.pop(name, None)
            completed = subprocess.run([str(interpreter), '-c', OTREE_CHECK], cwd=project,
                                       env=environment, capture_output=True, text=True, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn('DISPOSABLE_NAVIGATION_CHECK_PASSED', completed.stdout)


if __name__ == '__main__':
    unittest.main()
