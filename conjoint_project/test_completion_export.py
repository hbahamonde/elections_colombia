"""Validate the read-only oTree completion export in a disposable project.

The real response database and configured remote database are never opened.
Only source code is copied; all test responses are created in temporary SQLite.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


EXPORT_CHECK = r'''
import asyncio
import csv
import io
import unittest
from sqlalchemy import inspect

asyncio.set_event_loop(asyncio.new_event_loop())
from otree.main import setup
setup()
from otree.database import db, engine
from otree.export import custom_export_app, get_custom_export_functions, get_fields_for_csv
from otree.models import Participant
from otree.session import create_session
from conjoint.models import C, Player, custom_export
from quota_monitor_data import _metadata, _page_layout

session = create_session('colombia_conjoint', num_participants=10)
people = list(Participant.objects_filter(session=session).order_by('id_in_session'))
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
    # All practice choices exist, but none may improve the main-task count.
    for row in Player.objects_filter(participant=person):
        row.left_candidate_id = 'candidate-left'
        row.right_candidate_id = 'candidate-right'
        row.decision_side = 'left'
        row.decision_candidate_id = 'candidate-left'

def main_row(person, task):
    return Player.objects_get(participant=person,
                              round_number=C.NUM_PRACTICE_ROUNDS + task)

def missing(person, tasks):
    for task in tasks:
        row = main_row(person, task)
        row.decision_side = None
        row.decision_candidate_id = None
        row.countdown_expired = True

missing(people[0], [1, 2])
missing(people[1], [1, 2, 3])
main_row(people[2], 1).countdown_expired = True
people[3].visited = False
excluded = Player.objects_get(participant=people[4], round_number=1)
excluded.country_of_residence = 'CO'
excluded.screening_excluded = True
people[5]._index_in_pages = layout['tasks'][C.NUM_ROUNDS]
people[6]._max_page_index = 360
people[7]._is_bot = True
people[8].is_browser_bot = True
missing(people[9], [1, 2])
main_row(people[9], 3).decision_side = 'right'  # wrong side for candidate-left
db.commit()

def stored_values():
    return {
        model.__tablename__: list(db._db.query(*model.__table__.columns).order_by(model.id))
        for model in (Participant, Player)
    }

before = stored_values()
columns_before = {
    table: [column['name'] for column in inspect(engine).get_columns(table)]
    for table in inspect(engine).get_table_names()
}
assert not db._db.dirty
players = list(Player.objects_filter(session=session).order_by('id'))
exported = list(custom_export(players))
header, rows = exported[0], exported[1:]
records = [dict(zip(header, row)) for row in rows]
by_person = {
    person.code: [row for row in records if row['participant.code'] == person.code]
    for person in people
}


class CompletionExportTests(unittest.TestCase):
    def test_completion_threshold_and_participant_status_are_repeated_on_all_rounds(self):
        expected = [
            ('complete', 15, 13, 2),
            ('finished_insufficient_choices', 15, 12, 3),
            ('complete', 15, 15, 0),
            ('ineligible', 15, 15, 0),
            ('ineligible', 15, 15, 0),
            ('in_progress', 14, 14, 0),
            ('incompatible_layout', None, None, None),
            ('ineligible', 15, 15, 0),
            ('ineligible', 15, 15, 0),
            ('finished_insufficient_choices', 15, 12, 3),
        ]
        for person, (status, submitted, valid, missing_count) in zip(people, expected):
            with self.subTest(person=person.id_in_session):
                self.assertEqual(len(by_person[person.code]), C.NUM_ROUNDS)
                for row in by_person[person.code]:
                    self.assertEqual(row['completion_status'], status)
                    self.assertEqual(row['study_complete'], status == 'complete')
                    self.assertEqual(row['main_tasks_submitted'], submitted)
                    self.assertEqual(row['main_tasks_with_selection'], valid)
                    self.assertEqual(row['main_tasks_missing_selection'], missing_count)
                    self.assertEqual(row['minimum_valid_main_choices'], 13)

    def test_every_original_player_export_field_and_value_is_preserved(self):
        self.assertEqual(len(header), len(set(header)))
        self.assertEqual(len(rows), len(players))
        self.assertTrue(all(len(row) == len(header) for row in rows))
        fields = get_fields_for_csv(Player)
        self.assertTrue(all('player.' + name in header for name in fields))
        for record, player in zip(records, players):
            self.assertEqual(record['session.code'], session.code)
            self.assertEqual(record['participant.code'], player.participant.code)
            self.assertEqual(record['subsession.round_number'], player.round_number)
            for name in fields:
                self.assertEqual(record['player.' + name], player.field_maybe_none(name))
        self.assertIsNone(by_person[people[0].code][5]['player.decision_candidate_id'])
        self.assertIsNone(by_person[people[0].code][5]['player.realistic_vote'])

    def test_standard_otree_discovers_and_writes_custom_csv(self):
        self.assertIs(get_custom_export_functions('conjoint')['custom_export'], custom_export)
        output = io.StringIO()
        custom_export_app('conjoint', output, session_code=session.code)
        csv_rows = list(csv.DictReader(io.StringIO(output.getvalue())))
        self.assertEqual(len(csv_rows), 10 * C.NUM_ROUNDS)
        first = next(row for row in csv_rows if row['participant.code'] == people[0].code)
        self.assertEqual(first['study_complete'], '1')
        self.assertEqual(first['main_tasks_with_selection'], '13')
        legacy = next(row for row in csv_rows if row['participant.code'] == people[6].code)
        self.assertEqual(legacy['completion_status'], 'incompatible_layout')
        self.assertEqual(legacy['main_tasks_with_selection'], '')

    def test_empty_export_retains_the_original_and_computed_header(self):
        empty = list(custom_export([]))
        self.assertEqual(empty, [header])

    def test_export_does_not_modify_response_values_schema_or_orm_state(self):
        self.assertEqual(stored_values(), before)
        self.assertEqual(columns_before, {
            table: [column['name'] for column in inspect(engine).get_columns(table)]
            for table in inspect(engine).get_table_names()
        })
        self.assertFalse(db._db.dirty)
        self.assertFalse(db._db.new)
        self.assertFalse(db._db.deleted)

result = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(CompletionExportTests))
assert result.wasSuccessful()
print('DISPOSABLE_COMPLETION_EXPORT_CHECK_PASSED')
'''


class DisposableCompletionExportTests(unittest.TestCase):
    def test_read_only_completion_export_through_native_otree_api(self):
        source = Path(__file__).resolve().parent
        interpreter = source / '.venv' / 'bin' / 'python'
        if not interpreter.exists():
            interpreter = Path(sys.executable)
        with tempfile.TemporaryDirectory(prefix='conjoint-completion-export-') as temporary:
            project = Path(temporary)
            for filename in ('settings.py', 'quota_monitor_data.py', 'completion_rules.py'):
                shutil.copy2(source / filename, project / filename)
            shutil.copytree(source / 'conjoint', project / 'conjoint',
                            ignore=shutil.ignore_patterns('__pycache__'))
            (project / '_static').symlink_to(source / '_static', target_is_directory=True)
            environment = dict(os.environ)
            environment.update({
                'DATABASE_URL': 'sqlite:///db.sqlite3', 'OTREE_PRODUCTION': '0',
                'OTREE_AUTH_LEVEL': '', 'PYTHONPATH': str(project),
                'OTREE_SECRET_KEY': 'disposable-export-check-not-a-live-secret',
            })
            for variable in ('OTREE_IN_MEMORY', 'OTREE_EPHEMERAL',
                             'SENTRY_DSN', 'OTREE_ERROR_REPORT_ENDPOINT'):
                environment.pop(variable, None)
            result = subprocess.run([str(interpreter), '-c', textwrap.dedent(EXPORT_CHECK)],
                                    cwd=project, env=environment, capture_output=True,
                                    text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('DISPOSABLE_COMPLETION_EXPORT_CHECK_PASSED', result.stdout)


if __name__ == '__main__':
    unittest.main()
