"""Render raffle notices through real oTree HTTP routes in a disposable project.

No response database or Render service is accessed.  The integration subprocess
receives only copied source files and creates its own SQLite database.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


HTTP_CHECK = r'''
import asyncio
from html.parser import HTMLParser
import re
import unittest

# oTree 6's Starlette adapter predates Python 3.14's event-loop default change.
asyncio.set_event_loop(asyncio.new_event_loop())
from otree.main import setup
setup()
from otree.asgi import app
from otree.database import db
from otree.lookup import url_i_should_be_on
from otree.models import Participant
from otree.session import create_session
from starlette.testclient import TestClient
from conjoint.models import C, Player, screen_out
from conjoint.pages import page_sequence, raffle_registration_is_available

RAFFLE_URL = 'https://bordedata.cl/encuestas/survey/42'
ARMS = ('control_ver_mas', 'timer_mostrar_mas', 'captcha_ver_mas')
session = create_session('colombia_conjoint', num_participants=6)
SESSION_CODE = session.code
PEOPLE = [person.code for person in
          Participant.objects_filter(session=session).order_by('id_in_session')]
db.commit()
client = TestClient(app)


class Links(HTMLParser):
    def __init__(self, document):
        super().__init__()
        self.anchors = []
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.anchors.append(dict(attrs))


def prepare(code, index, arm='control_ver_mas', *, baseline=True,
            excluded=False, all_timeouts=False):
    db.new_session()
    person = Participant.objects_get(code=code)
    person.visited = True
    person._index_in_pages = index
    person.vars['treatment_arm'] = arm
    screening = Player.objects_get(participant=person, round_number=1)
    screening.consent_accepted = baseline
    screening.country_of_residence = 'CL' if baseline else ''
    screening.nationality = 'FI' if baseline else ''
    screening.lived_in_colombia = 'no' if baseline else ''
    if baseline:
        screening.age_years = 35
        screening.gender_identity = 'mujer'
        screening.occupation_status = 'tiempo_completo'
        screening.education_level = 'postgrado'
        screening.voted_last_municipal = 'yes'
        screening.political_interest = 4
        screening.politics_frequency = 'every_day'
        screening.left_right_self_placement = '5'
    if excluded:
        screening.country_of_residence = 'CO'
        screen_out(screening, 'residence_colombia')
    if all_timeouts:
        for round_number in range(C.NUM_PRACTICE_ROUNDS + 1, C.NUM_ROUNDS + 1):
            row = Player.objects_get(participant=person, round_number=round_number)
            row.decision_side = None
            row.decision_candidate_id = None
            row.countdown_expired = True
    url = url_i_should_be_on(code, SESSION_CODE, index)
    db.commit()
    return url


def rendered(url):
    response = client.get(url)
    assert response.status_code == 200, (response.status_code, response.text[:600])
    return response.text


def readable(document):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', document))


class RaffleHTTPTests(unittest.TestCase):
    def assert_no_raffle_link(self, document):
        self.assertNotIn(RAFFLE_URL, document)
        self.assertFalse(any('bordedata.cl' in anchor.get('href', '')
                             for anchor in Links(document).anchors))

    def assert_prize_details(self, document):
        text = readable(document).lower()
        self.assertRegex(text, r'(?:3|tres)\s+(?:tarjetas|gift\s*cards)')
        self.assertRegex(text, r'50[.,\s]?000')
        self.assertIn('camiseta', text)
        self.assertIn('sorpresa', text)
        self.assertIn('sorteo', text)
        self.assertNotRegex(text, r'(?:recibirá|recibirá[nm]|obtendrá)\s+(?:una|su)\s+gift')

    def test_consent_discloses_raffle_without_early_external_link(self):
        document = rendered(prepare(PEOPLE[0], 1, baseline=False))
        self.assertIn('Consentimiento informado', document)
        self.assert_prize_details(document)
        self.assert_no_raffle_link(document)

    def test_both_instruction_stages_have_raffle_reminder_in_every_treatment(self):
        intro_position = next(i for i, page in enumerate(page_sequence, 1)
                              if page.__name__ == 'Intro')
        done_position = (C.NUM_PRACTICE_ROUNDS - 1) * len(page_sequence) + next(
            i for i, page in enumerate(page_sequence, 1)
            if page.__name__ == 'PracticeDone')
        for arm in ARMS:
            for index in (intro_position, done_position):
                with self.subTest(arm=arm, index=index):
                    document = rendered(prepare(PEOPLE[1], index, arm))
                    self.assertIn('Instrucciones', document)
                    text = readable(document).lower()
                    self.assertIn('sorteo', text)
                    self.assertRegex(text, r'(?:final|última pantalla)')
                    self.assertRegex(text, r'(?:clic|click|botón|enlace)')
                    self.assert_no_raffle_link(document)

    def test_eligible_completion_displays_one_exact_link_without_participant_data(self):
        document = rendered(prepare(PEOPLE[2], C.NUM_ROUNDS * len(page_sequence)))
        self.assert_prize_details(document)
        raffle_anchors = [anchor for anchor in Links(document).anchors
                          if 'bordedata.cl' in anchor.get('href', '')]
        self.assertEqual(len(raffle_anchors), 1)
        self.assertEqual(raffle_anchors[0]['href'], RAFFLE_URL)
        text = readable(document).lower()
        self.assertRegex(text, r'(?:clic|click|botón|enlace)')
        self.assertRegex(text, r'(?:no.{0,100}particip|fuera.{0,100}sorteo|sin.{0,100}sorteo)')
        self.assertIn('noopener', raffle_anchors[0].get('rel', ''))
        self.assertIn('noreferrer', raffle_anchors[0].get('rel', ''))
        self.assertEqual(raffle_anchors[0].get('target'), '_blank')
        self.assertEqual(raffle_anchors[0].get('referrerpolicy'), 'no-referrer')

    def test_helper_requires_a_real_terminal_visit_and_complete_eligibility(self):
        final_index = C.NUM_ROUNDS * len(page_sequence)
        prepare(PEOPLE[4], final_index)
        db.new_session()
        person = Participant.objects_get(code=PEOPLE[4])
        last = Player.objects_get(participant=person, round_number=C.NUM_ROUNDS)
        initial = Player.objects_get(participant=person, round_number=1)
        self.assertTrue(raffle_registration_is_available(last))

        person.visited = False
        self.assertFalse(raffle_registration_is_available(last))
        person.visited = True
        person._index_in_pages = final_index - 1
        self.assertFalse(raffle_registration_is_available(last))
        person._index_in_pages = final_index
        previous = Player.objects_get(participant=person, round_number=C.NUM_ROUNDS - 1)
        self.assertFalse(raffle_registration_is_available(previous))
        actual_maximum = person._max_page_index
        person._max_page_index = 0
        self.assertFalse(raffle_registration_is_available(last))
        person._max_page_index = actual_maximum

        for field, disqualifying_value in (
            ('consent_accepted', False), ('country_of_residence', 'CO'),
            ('nationality', 'CO'), ('lived_in_colombia', 'yes'),
            ('age_years', None),
        ):
            with self.subTest(field=field):
                original = initial.field_maybe_none(field)
                setattr(initial, field, disqualifying_value)
                self.assertFalse(raffle_registration_is_available(last))
                setattr(initial, field, original)
        db.rollback()

    def test_screened_out_participant_never_receives_raffle_link(self):
        document = rendered(prepare(PEOPLE[3], C.NUM_ROUNDS * len(page_sequence),
                                    excluded=True))
        self.assertIn('no cumple con los criterios', readable(document))
        self.assert_no_raffle_link(document)

    def test_incomplete_positive_eligibility_does_not_unlock_final_link(self):
        document = rendered(prepare(PEOPLE[4], C.NUM_ROUNDS * len(page_sequence),
                                    baseline=False))
        self.assert_no_raffle_link(document)

    def test_no_choice_timeouts_do_not_disqualify_eligible_completion(self):
        document = rendered(prepare(PEOPLE[5], C.NUM_ROUNDS * len(page_sequence),
                                    'timer_mostrar_mas', all_timeouts=True))
        self.assertEqual(sum(anchor.get('href') == RAFFLE_URL
                             for anchor in Links(document).anchors), 1)
        db.new_session()
        person = Participant.objects_get(code=PEOPLE[5])
        for round_number in range(C.NUM_PRACTICE_ROUNDS + 1, C.NUM_ROUNDS + 1):
            row = Player.objects_get(participant=person, round_number=round_number)
            self.assertIsNone(row.field_maybe_none('decision_side'))
            self.assertIsNone(row.field_maybe_none('decision_candidate_id'))
            self.assertTrue(row.countdown_expired)
        db.rollback()

    def test_experiment_page_sequence_and_timing_unchanged(self):
        self.assertEqual((C.NUM_PRACTICE_ROUNDS, C.NUM_MAIN_ROUNDS,
                          C.NUM_ROUNDS, C.COUNTDOWN_SECONDS), (5, 15, 20, 20))
        self.assertEqual([page.__name__ for page in page_sequence], [
            'Consent', 'CountryResidence', 'Nationality', 'LivedInColombia',
            'Questionnaire', 'Intro', 'Task', 'PracticeDone', 'FollowUp', 'Summary'])


suite = unittest.defaultTestLoader.loadTestsFromTestCase(RaffleHTTPTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
print('DISPOSABLE_RAFFLE_HTTP_CHECK_PASSED')
'''


class DisposableRaffleTests(unittest.TestCase):
    def run_disposable(self, script, success_marker):
        source = Path(__file__).resolve().parent
        interpreter = source / '.venv' / 'bin' / 'python'
        if not interpreter.exists():
            interpreter = Path(sys.executable)
        with tempfile.TemporaryDirectory(prefix='conjoint-raffle-http-') as temporary:
            project = Path(temporary)
            shutil.copy2(source / 'settings.py', project / 'settings.py')
            shutil.copytree(source / 'conjoint', project / 'conjoint',
                            ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(source / '_templates', project / '_templates')
            (project / '_static').symlink_to(source / '_static', target_is_directory=True)
            environment = dict(os.environ)
            environment.update({
                'DATABASE_URL': 'sqlite:///db.sqlite3', 'OTREE_PRODUCTION': '0',
                'OTREE_AUTH_LEVEL': '', 'PYTHONPATH': str(project),
                'OTREE_SECRET_KEY': 'disposable-raffle-test-key-not-a-live-secret',
            })
            for variable in ('OTREE_IN_MEMORY', 'OTREE_EPHEMERAL',
                             'SENTRY_DSN', 'OTREE_ERROR_REPORT_ENDPOINT'):
                environment.pop(variable, None)
            result = subprocess.run([str(interpreter), '-c', textwrap.dedent(script)],
                                    cwd=project, env=environment, capture_output=True,
                                    text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(success_marker, result.stdout)
            return result

    def test_consent_instructions_and_completion_over_real_http_routes(self):
        self.run_disposable(HTTP_CHECK, 'DISPOSABLE_RAFFLE_HTTP_CHECK_PASSED')

    def test_existing_seven_complete_bot_cases_in_disposable_project(self):
        result = self.run_disposable('''
            import asyncio
            import sys
            asyncio.set_event_loop(asyncio.new_event_loop())
            sys.argv = ['otree', 'bots', 'colombia_conjoint']
            from otree.main import execute_from_command_line
            execute_from_command_line()
            print('DISPOSABLE_SEVEN_BOT_CASES_PASSED')
        ''', 'DISPOSABLE_SEVEN_BOT_CASES_PASSED')
        self.assertEqual((result.stdout + result.stderr).count('Bots completed session'), 7)


if __name__ == '__main__':
    unittest.main()
