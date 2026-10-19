"""Recruitment semantics tests, plus an isolated oTree ORM integration test.

Run with the project's Python interpreter. The ORM test copies only source
files to a temporary directory and creates a new SQLite database there; it
never opens the project's response database or a configured remote database.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import quota_monitor_data as monitor


def metadata():
    genders = [('mujer', 'Mujer'), ('hombre', 'Hombre'), ('otra', 'Otra'),
               ('prefiero_no_responder', 'Prefiero no responder')]
    countries = [('CL', 'Chile'), ('FI', 'Finlandia'), ('CO', 'Colombia')]
    return {
        'practice_rounds': 5, 'main_rounds': 15, 'total_rounds': 20,
        'treatments': list(monitor.TREATMENT_LABELS),
        'exclusion_labels': {
            'residence_colombia': 'Residencia en Colombia',
            'nationality_colombian': 'Nacionalidad colombiana',
            'lived_colombia': 'Vivió en Colombia',
            'currently_in_colombia': 'Vive en Colombia',
            'lived_prefer_not_to_answer': 'No respondió residencia anterior',
        },
        'dimensions': [
            {'key': 'age_band', 'label': 'Edad',
             'choices': [('18_29', '18–29'), ('30_44', '30–44'),
                         ('45_59', '45–59'), ('60_plus', '60+')]},
            {'key': 'gender_identity', 'label': 'Género', 'choices': genders},
            {'key': 'country_of_residence', 'label': 'Residencia',
             'choices': countries, 'compact': True},
            {'key': 'nationality', 'label': 'Nacionalidad',
             'choices': countries, 'compact': True},
            {'key': 'education_level', 'label': 'Educación',
             'choices': [('postgrado', 'Postgrado')]},
            {'key': 'occupation_status', 'label': 'Ocupación',
             'choices': [('estudia', 'Estudia')]},
        ],
    }


def layout():
    return {'questionnaire': 5, 'summary': 200, 'max_page_index': 200,
            'tasks': {round_number: (round_number - 1) * 10 + 7
                      for round_number in range(6, 21)}}


def participant(participant_id, index, treatment='control_ver_mas', **extra):
    return {
        'id': participant_id, 'visited': index > 0, '_index_in_pages': index,
        '_max_page_index': 200, '_vars': {'treatment_arm': treatment},
        '_is_bot': False, 'is_browser_bot': False, **extra,
    }


def baseline(participant_id, **extra):
    return {
        'participant_id': participant_id, 'consent_accepted': True,
        'country_of_residence': 'CL', 'nationality': 'FI', 'lived_in_colombia': 'no',
        'screening_excluded': False, 'screening_exclusion_reason': '',
        'age_years': 61, 'gender_identity': 'mujer',
        'education_level': 'postgrado', 'occupation_status': 'estudia',
        'treatment_arm': None, **extra,
    }


def task(participant_id, round_number, *, selected=True, expired=False):
    return {
        'participant_id': participant_id, 'round_number': round_number,
        'left_candidate_id': 'private-left-profile',
        'right_candidate_id': 'private-right-profile',
        'decision_candidate_id': 'private-left-profile' if selected else None,
        'decision_side': 'left' if selected else None,
        'countdown_expired': expired,
    }


def recruitment_fixture():
    participants = [
        participant(1, 0, 'timer_mostrar_mas'),
        participant(2, 2),
        participant(3, 200),
        participant(4, 5),
        participant(5, 57, 'captcha_ver_mas'),
        participant(6, 200, 'timer_mostrar_mas'),
        participant(7, 199),
        participant(8, 200, _vars={'screening_excluded': True,
                                  'screening_exclusion_reason': 'lived_colombia'}),
        participant(9, 4),
        participant(10, 7),
        participant(11, 200, _is_bot=True),
    ]
    baselines = {
        2: {'consent_accepted': True},
        3: baseline(3, country_of_residence='CO', screening_excluded=True,
                    screening_exclusion_reason='residence_colombia'),
        4: baseline(4, age_years=None, gender_identity=None),
        5: baseline(5, age_years=65),
        6: baseline(6),
        7: baseline(7, age_years=40, gender_identity='hombre'),
        8: {},
        9: {'consent_accepted': True, 'country_of_residence': 'FI'},
        10: baseline(10, age_years=29, gender_identity='otra'),
        11: baseline(11),
    }
    task_rows = [task(person, round_number) for person in (6, 7, 11)
                 for round_number in range(6, 21)]
    for row in task_rows:
        if row['participant_id'] == 6 and row['round_number'] == 6:
            row.update(task(6, 6, selected=False, expired=True))
        if row['participant_id'] == 6 and row['round_number'] == 7:
            row['countdown_expired'] = True
    # A rendered Task already has candidate IDs but has not yet been submitted.
    task_rows.append(task(5, 6, selected=False))
    return participants, baselines, task_rows


class AggregateSemanticsTests(unittest.TestCase):
    def snapshot(self, targets=None, mode='official'):
        return monitor._aggregate_records(mode, metadata(), layout(),
                                          *recruitment_fixture(), targets or {})

    def test_soft_launch_completions_count_toward_462_without_reset(self):
        arms = list(monitor.TREATMENT_LABELS)
        people = [participant(i, 200, arms[(i - 1) % len(arms)])
                  for i in range(1, 31)]
        baselines = {i: baseline(i) for i in range(1, 31)}
        task_rows = [task(i, round_number) for i in range(1, 31)
                     for round_number in range(6, 21)]
        first_wave = monitor._aggregate_records(
            'official', metadata(), layout(), people, baselines, task_rows, {})
        self.assertEqual(first_wave['summary']['eligible_completed'], 30)
        self.assertEqual(first_wave['summary']['main_tasks_submitted'], 450)
        self.assertEqual(462 - first_wave['summary']['eligible_completed'], 432)

        # Continuing recruitment retains the initial 30. There is no reset or
        # offset between the soft launch and the remaining 432 completions.
        people.extend(participant(i, 200, arms[(i - 1) % len(arms)])
                      for i in range(31, 463))
        people.extend(participant(i, 0) for i in range(463, 601))
        baselines.update({i: baseline(i) for i in range(31, 463)})
        task_rows.extend(task(i, round_number) for i in range(31, 463)
                         for round_number in range(6, 21))
        full_sample = monitor._aggregate_records(
            'official', metadata(), layout(), people, baselines, task_rows, {})
        self.assertEqual(full_sample['summary']['assigned'], 600)
        self.assertEqual(full_sample['summary']['not_started'], 138)
        self.assertEqual(full_sample['summary']['eligible_completed'], 462)
        self.assertEqual(full_sample['summary']['main_tasks_submitted'], 6930)
        self.assertEqual(sum(row['completed'] for row in full_sample['treatments']), 462)

    def test_people_not_rounds_and_mutually_exclusive_recruitment_statuses(self):
        summary = self.snapshot()['summary']
        self.assertEqual(summary['assigned'], 10)
        self.assertEqual(summary['not_started'], 1)
        self.assertEqual(summary['started'], 9)
        self.assertEqual(summary['screened_out'], 2)
        self.assertEqual(summary['screening_pending'], 2)
        self.assertEqual(summary['screening_passed'], 5)
        self.assertEqual(summary['baseline_pending'], 1)
        self.assertEqual(summary['eligible_baseline_complete'], 4)
        self.assertEqual(summary['eligible_in_progress'], 3)
        self.assertEqual(summary['eligible_completed'], 1)
        self.assertEqual(summary['assigned'], sum(summary[key] for key in (
            'not_started', 'screening_pending', 'screened_out', 'baseline_pending',
            'eligible_in_progress', 'eligible_completed',
        )))

    def test_task_submission_final_followup_and_timeout_are_distinct(self):
        summary = self.snapshot()['summary']
        self.assertEqual(summary['all_main_tasks_submitted'], 2)
        self.assertEqual(summary['eligible_completed'], 1)
        self.assertEqual(summary['main_tasks_submitted'], 30)
        self.assertEqual(summary['main_tasks_with_selection'], 29)
        self.assertEqual(summary['main_tasks_no_selection'], 1)
        self.assertEqual(summary['deadline_expiries'], 2)
        self.assertEqual(summary['participants_with_timeouts'], 1)

    def test_targets_use_completed_not_pending_and_are_not_invented(self):
        snapshot = self.snapshot({'gender_identity': {'mujer': 1},
                                  'age_gender': {'60_plus__mujer': 2}})
        gender = next(dimension for dimension in snapshot['quota_dimensions']
                      if dimension['key'] == 'gender_identity')
        woman = next(row for row in gender['rows'] if row['key'] == 'mujer')
        self.assertEqual(woman['completed'], 1)
        self.assertEqual(woman['in_progress'], 1)
        self.assertTrue(woman['is_full'])
        age_row = next(row for row in snapshot['age_gender']['rows']
                       if row['key'] == '60_plus')
        older_woman = next(cell for cell in age_row['cells']
                           if cell['gender_key'] == 'mujer')
        self.assertEqual(older_woman['remaining'], 1)
        self.assertFalse(older_woman['is_full'])
        self.assertEqual(older_woman['progress_percent'], 50)
        self.assertTrue(snapshot['targets_configured'])
        empty_targets = self.snapshot({'gender_identity': {'mujer': True, 'hombre': '231'}})
        self.assertFalse(empty_targets['targets_configured'])
        self.assertTrue(all(row['target'] is None
                            for dimension in empty_targets['quota_dimensions']
                            for row in dimension['rows']))

    def test_treatment_balance_counts_eligible_cohorts_not_preallocation(self):
        arms = {row['key']: row for row in self.snapshot()['treatments']}
        self.assertEqual(arms['timer_mostrar_mas']['eligible_baseline_complete'], 1)
        self.assertEqual(arms['timer_mostrar_mas']['completed'], 1)
        self.assertEqual(arms['captcha_ver_mas']['in_progress'], 1)
        self.assertEqual(arms['control_ver_mas']['in_progress'], 2)

    def test_aggregate_payload_does_not_reveal_identifiers_or_free_text(self):
        participants, baselines, task_rows = recruitment_fixture()
        baselines[6]['nationality'] = 'PRIVATE_FREE_TEXT'
        baselines[6]['gender_identity_other'] = 'PRIVATE_GENDER_DESCRIPTION'
        participants[5]['code'] = 'PRIVATE_PARTICIPANT_CODE'
        participants[5]['label'] = 'PRIVATE_LABEL'
        participants[5]['_vars']['political_attitude'] = 'PRIVATE_POLITICS'
        snapshot = monitor._aggregate_records('official', metadata(), layout(),
                                              participants, baselines, task_rows, {})
        serialized = json.dumps(snapshot, ensure_ascii=False)
        for forbidden in ('PRIVATE_', 'private-left-profile', 'private-right-profile',
                          'participant_id', 'decision_candidate_id', 'political_attitude'):
            self.assertNotIn(forbidden, serialized)
        nationality = next(dimension for dimension in snapshot['quota_dimensions']
                           if dimension['key'] == 'nationality')
        self.assertEqual(nationality['rows'][-1]['key'], 'unknown')
        self.assertEqual(nationality['rows'][-1]['completed'], 1)

    def test_screening_requires_positive_answers_not_absence_of_exclusion(self):
        self.assertFalse(monitor._screening_passed({}, None))
        self.assertFalse(monitor._screening_passed(baseline(1, consent_accepted=False), None))
        self.assertTrue(monitor._screening_passed(baseline(1), None))
        self.assertEqual(monitor._exclusion_reason(baseline(1, nationality='Colombiana'), {}),
                         'nationality_colombian')

    def test_incompatible_session_page_layout_fails_closed(self):
        participants, baselines, task_rows = recruitment_fixture()
        participants[0]['_max_page_index'] = 160
        with self.assertRaises(monitor.MonitorConfigurationError):
            monitor._aggregate_records('official', metadata(), layout(),
                                       participants, baselines, task_rows, {})

    def test_boolean_strings_are_not_truthy_by_accident(self):
        for value in (False, 'false', 'False', '0', 0, '', None):
            self.assertFalse(monitor._boolean(value))
        for value in (True, 'true', 'TRUE', '1', 1):
            self.assertTrue(monitor._boolean(value))
        with self.assertRaises(monitor.MonitorConfigurationError):
            monitor._boolean('not-a-boolean')


class SessionSelectionTests(unittest.TestCase):
    def build(self, session, mode='official'):
        with patch.dict(os.environ, {'MONITOR_MODE': mode}, clear=False), \
             patch.object(monitor, '_metadata', return_value=metadata()), \
             patch.object(monitor, '_selected_session', return_value=session), \
             patch.object(monitor, '_page_layout', return_value=layout()), \
             patch.object(monitor, '_load_records', return_value=recruitment_fixture()) as loader:
            snapshot = monitor.build_monitor_snapshot()
        return snapshot, loader.call_count

    def test_no_active_session_does_not_fall_back_to_other_sessions(self):
        snapshot, calls = self.build(None)
        self.assertEqual(snapshot['status'], 'no_active_session')
        self.assertEqual(snapshot['summary']['assigned'], 0)
        self.assertEqual(calls, 0)

    def test_official_and_testing_modes_never_mix(self):
        testing = SimpleNamespace(config={'official_data_collection': 'false'}, is_demo=False)
        official = SimpleNamespace(config={'official_data_collection': True}, is_demo=False)
        for session, mode in ((testing, 'official'), (official, 'testing')):
            snapshot, calls = self.build(session, mode)
            self.assertEqual(snapshot['status'], 'mode_mismatch')
            self.assertEqual(snapshot['summary']['assigned'], 0)
            self.assertEqual(calls, 0)
        snapshot, calls = self.build(testing, 'testing')
        self.assertEqual(snapshot['status'], 'ready')
        self.assertEqual(snapshot['summary']['assigned'], 11)
        self.assertEqual(calls, 1)

    def test_demo_sessions_do_not_count_as_official_recruitment(self):
        demo = SimpleNamespace(config={'official_data_collection': True}, is_demo=True)
        snapshot, calls = self.build(demo)
        self.assertEqual(snapshot['status'], 'mode_mismatch')
        self.assertEqual(calls, 0)

    def test_invalid_mode_or_flag_returns_safe_empty_state(self):
        session = SimpleNamespace(config={'official_data_collection': 'invalid'}, is_demo=False)
        snapshot, calls = self.build(session)
        self.assertEqual(snapshot['status'], 'configuration_error')
        self.assertEqual(calls, 0)
        snapshot, calls = self.build(session, 'all-sessions')
        self.assertEqual(snapshot['status'], 'configuration_error')
        self.assertEqual(calls, 0)


ORM_CHECK = r'''
import json
import os
from otree.main import setup
setup()
from otree.database import db
from otree.models import Participant
from otree.session import create_session
from otree.room import ROOM_DICT
from conjoint.models import Player, C
from quota_monitor_data import build_monitor_snapshot, _page_layout, _metadata

session = create_session('colombia_conjoint', num_participants=5,
                         room_name='colombia_study',
                         modified_session_config_fields={'official_data_collection': True})
positions = _page_layout(session, _metadata())
people = list(Participant.objects_filter(session=session).order_by('id_in_session'))

def fill_baseline(person, gender='mujer'):
    row = Player.objects_get(session=session, participant=person, round_number=1)
    row.consent_accepted = True
    row.country_of_residence = 'CL'
    row.nationality = 'FI'
    row.lived_in_colombia = 'no'
    row.age_years = 61
    row.gender_identity = gender
    row.education_level = 'postgrado'
    row.occupation_status = 'estudia'
    return row

# A no-choice timeout remains a completed task; an expiry after a selection does too.
complete = people[0]
complete.visited = True
complete._index_in_pages = positions['summary']
complete.vars['treatment_arm'] = 'timer_mostrar_mas'
fill_baseline(complete)
for round_number in range(C.NUM_PRACTICE_ROUNDS + 1, C.NUM_ROUNDS + 1):
    row = Player.objects_get(session=session, participant=complete, round_number=round_number)
    row.left_candidate_id = 'left-private'
    row.right_candidate_id = 'right-private'
    if round_number == C.NUM_PRACTICE_ROUNDS + 1:
        row.countdown_expired = True
    else:
        row.decision_side = 'left'
        row.decision_candidate_id = 'left-private'
        row.countdown_expired = round_number == C.NUM_PRACTICE_ROUNDS + 2

excluded = people[1]
excluded.visited = True
excluded._index_in_pages = positions['summary']
screening = fill_baseline(excluded)
screening.country_of_residence = 'CO'
screening.screening_excluded = True
screening.screening_exclusion_reason = 'residence_colombia'

pending = people[2]
pending.visited = True
pending._index_in_pages = positions['tasks'][6]
fill_baseline(pending, 'hombre')

# Another official session has data but must not be enumerated or combined.
other = create_session('colombia_conjoint', num_participants=2,
                       modified_session_config_fields={'official_data_collection': True})
db.commit()
db.new_session()
with db._db.no_autoflush:
    snapshot = build_monitor_snapshot()
    assert not db._db.dirty, 'reading aggregates marked ORM records dirty'
    assert not db._db.new, 'reading aggregates created ORM records'
db.rollback()
assert snapshot['status'] == 'ready', snapshot
assert snapshot['summary']['assigned'] == 5, snapshot['summary']
assert snapshot['summary']['eligible_completed'] == 1, snapshot['summary']
assert snapshot['summary']['screened_out'] == 1, snapshot['summary']
assert snapshot['summary']['eligible_in_progress'] == 1, snapshot['summary']
assert snapshot['summary']['all_main_tasks_submitted'] == 1, snapshot['summary']
assert snapshot['summary']['main_tasks_submitted'] == 15, snapshot['summary']
assert snapshot['summary']['main_tasks_no_selection'] == 1, snapshot['summary']
assert snapshot['summary']['deadline_expiries'] == 2, snapshot['summary']
assert snapshot['summary']['participants_with_timeouts'] == 1, snapshot['summary']
serialized = json.dumps(snapshot)
assert 'left-private' not in serialized
assert all(person.code not in serialized for person in people)
assert session.code not in serialized and other.code not in serialized

# Explicit server configuration can select one other session; URL input is absent.
os.environ['MONITOR_SESSION_CODE'] = other.code
snapshot = build_monitor_snapshot()
assert snapshot['summary']['assigned'] == 2, snapshot
os.environ.pop('MONITOR_SESSION_CODE')
ROOM_DICT['colombia_study'].set_session(None)
db.commit()
snapshot = build_monitor_snapshot()
assert snapshot['status'] == 'no_active_session', snapshot
assert snapshot['summary']['assigned'] == 0
print('DISPOSABLE_ORM_CHECK_PASSED')
'''


class DisposableOrmTests(unittest.TestCase):
    @unittest.skipUnless('site-packages' in str(Path(sys.executable).parent)
                         or Path('.venv/bin/python').exists(),
                         'run with the project virtual environment for oTree integration')
    def test_selected_session_orm_projection_and_read_only_snapshot(self):
        source = Path(__file__).resolve().parent
        interpreter = source / '.venv' / 'bin' / 'python'
        if not interpreter.exists():
            interpreter = Path(sys.executable)
        with tempfile.TemporaryDirectory(prefix='conjoint-monitor-orm-') as temporary:
            project = Path(temporary)
            shutil.copy2(source / 'settings.py', project / 'settings.py')
            shutil.copy2(source / 'quota_monitor_data.py', project / 'quota_monitor_data.py')
            shutil.copytree(source / 'conjoint', project / 'conjoint',
                            ignore=shutil.ignore_patterns('__pycache__'))
            (project / '_static').symlink_to(source / '_static', target_is_directory=True)
            environment = dict(os.environ)
            environment.update({
                'DATABASE_URL': 'sqlite:///db.sqlite3', 'OTREE_PRODUCTION': '0',
                'MONITOR_MODE': 'official', 'MONITOR_ROOM': 'colombia_study',
                'MONITOR_SESSION_CODE': '', 'PYTHONPATH': str(project),
            })
            environment.pop('OTREE_IN_MEMORY', None)
            environment.pop('OTREE_EPHEMERAL', None)
            result = subprocess.run([str(interpreter), '-c', textwrap.dedent(ORM_CHECK)],
                                    cwd=project, env=environment, capture_output=True,
                                    text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('DISPOSABLE_ORM_CHECK_PASSED', result.stdout)


if __name__ == '__main__':
    unittest.main()
