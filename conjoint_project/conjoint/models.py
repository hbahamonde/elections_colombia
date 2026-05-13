from otree.api import *
import csv
import json
import random
from pathlib import Path


doc = """
Image conjoint experiment.

Participants choose between two candidate photos. Photos are stored in:
_static/conjoint/images/

Candidate metadata is read from:
_static/conjoint/data/dataset.csv

Participants only see ideology when assigned to an information treatment.
The backend records candidate IDs and the full CSV row for each candidate shown.
"""


def clean_value(value):
    if value is None:
        return ''
    return str(value).strip()


def clean_candidate_id(value):
    value = clean_value(value)

    if value.endswith('.0'):
        value = value[:-2]

    return Path(value).stem


def load_candidate_data():
    app_root = Path(__file__).resolve().parent.parent

    data_path = app_root / '_static' / 'conjoint' / 'data' / 'dataset.csv'
    image_dir = app_root / '_static' / 'conjoint' / 'images'

    if not data_path.exists():
        raise FileNotFoundError(f'dataset.csv not found at: {data_path}')

    if not image_dir.exists():
        raise FileNotFoundError(f'image folder not found at: {image_dir}')

    candidates = {}

    with open(data_path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError('dataset.csv has no header row.')

        required_columns = ['ID', 'ideologia_cat']
        missing_columns = [
            column for column in required_columns
            if column not in reader.fieldnames
        ]

        if missing_columns:
            raise ValueError(
                f'dataset.csv is missing required columns: {missing_columns}'
            )

        for raw_row in reader:
            row = {
                clean_value(key): clean_value(value)
                for key, value in raw_row.items()
            }

            candidate_id = clean_candidate_id(row.get('ID'))

            if candidate_id == '':
                continue

            image_filename = f'{candidate_id}.jpg'
            image_path = image_dir / image_filename

            if not image_path.exists():
                continue

            candidates[candidate_id] = {
                'id': candidate_id,
                'image_filename': image_filename,
                'image_path': f'conjoint/images/{image_filename}',
                'ideologia_cat': clean_value(row.get('ideologia_cat')),
                'nombre': clean_value(row.get('NOMBRE')),
                'partido': clean_value(row.get('PARTIDO')),
                'genero': clean_value(row.get('GENERO')),
                'edad': clean_value(row.get('EDAD')),
                'votos': clean_value(row.get('Votos')),
                'dataset_row_json': json.dumps(row, ensure_ascii=False),
            }

    if len(candidates) < 2:
        available_images = sorted(path.name for path in image_dir.glob('*.jpg'))

        raise ValueError(
            'Need at least two candidate rows with matching photos. '
            f'dataset.csv is at {data_path}. '
            f'Images are expected in {image_dir}. '
            f'Currently found these jpg files: {available_images}'
        )

    return candidates


CANDIDATE_DATA = load_candidate_data()


class C(BaseConstants):
    NAME_IN_URL = 'conjoint'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 4

    INITIAL_ENDOWMENT = 100

    TREATMENT_ARMS = [
        'timer_mostrar_mas',
        'captcha_ver_mas',
        'control_ver_mas',
    ]


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    treatment_arm = models.StringField()
    timed_task = models.BooleanField(initial=False)
    info_condition = models.StringField()

    left_candidate_id = models.StringField()
    right_candidate_id = models.StringField()

    left_image_path = models.StringField()
    right_image_path = models.StringField()

    left_ideologia_cat = models.StringField(blank=True)
    right_ideologia_cat = models.StringField(blank=True)

    left_nombre = models.StringField(blank=True)
    right_nombre = models.StringField(blank=True)

    left_partido = models.StringField(blank=True)
    right_partido = models.StringField(blank=True)

    left_genero = models.StringField(blank=True)
    right_genero = models.StringField(blank=True)

    left_edad = models.StringField(blank=True)
    right_edad = models.StringField(blank=True)

    left_votos = models.StringField(blank=True)
    right_votos = models.StringField(blank=True)

    left_dataset_row_json = models.LongStringField(blank=True)
    right_dataset_row_json = models.LongStringField(blank=True)

    left_ideology_opened = models.BooleanField(initial=False)
    right_ideology_opened = models.BooleanField(initial=False)

    info_cost_task_completed = models.BooleanField(initial=False)
    info_cost_attempts = models.IntegerField(initial=0)

    captcha_left_a = models.IntegerField(initial=0)
    captcha_left_b = models.IntegerField(initial=0)
    captcha_right_a = models.IntegerField(initial=0)
    captcha_right_b = models.IntegerField(initial=0)

    decision_candidate_id = models.StringField(blank=True)

    decision_side = models.StringField(blank=True)

    time_spent_seconds = models.FloatField(initial=0)
    time_to_first_choice_seconds = models.FloatField(initial=0)

    choice_changes = models.IntegerField(initial=0)
    learn_more_clicks = models.IntegerField(initial=0)

    mouse_distance_px = models.FloatField(initial=0)
    left_hover_seconds = models.FloatField(initial=0)
    right_hover_seconds = models.FloatField(initial=0)

    balance_after_task = models.IntegerField(initial=0)


def available_candidate_ids():
    return list(CANDIDATE_DATA.keys())


def draw_candidates_for_participant():
    ids = available_candidate_ids()
    random.shuffle(ids)

    needed = C.NUM_ROUNDS * 2

    if len(ids) >= needed:
        return ids[:needed]

    sampled = []

    while len(sampled) < needed:
        sampled.extend(random.sample(ids, 2))

    return sampled[:needed]


def creating_session(subsession):
    for player in subsession.get_players():
        participant = player.participant

        if 'point_balance' not in participant.vars:
            participant.vars['point_balance'] = C.INITIAL_ENDOWMENT

        if 'treatment_arm' not in participant.vars:
            participant.vars['treatment_arm'] = random.choice(C.TREATMENT_ARMS)

        if 'drawn_candidates' not in participant.vars:
            participant.vars['drawn_candidates'] = draw_candidates_for_participant()


def ensure_participant_vars(player):
    participant = player.participant

    if 'point_balance' not in participant.vars:
        participant.vars['point_balance'] = C.INITIAL_ENDOWMENT

    if 'treatment_arm' not in participant.vars:
        participant.vars['treatment_arm'] = random.choice(C.TREATMENT_ARMS)

    if 'drawn_candidates' not in participant.vars:
        participant.vars['drawn_candidates'] = draw_candidates_for_participant()


def assign_candidates(player):
    ensure_participant_vars(player)

    if (
        player.field_maybe_none('left_candidate_id')
        and player.field_maybe_none('right_candidate_id')
    ):
        return

    treatment_arm = player.participant.vars['treatment_arm']

    player.treatment_arm = treatment_arm
    player.timed_task = treatment_arm == 'timer_mostrar_mas'
    player.info_condition = treatment_arm

    if player.captcha_left_a == 0:
        player.captcha_left_a = random.randint(2, 20)
        player.captcha_left_b = random.randint(2, 20)

    if player.captcha_right_a == 0:
        player.captcha_right_a = random.randint(2, 20)
        player.captcha_right_b = random.randint(2, 20)

        while (
            player.captcha_right_a == player.captcha_left_a
            and player.captcha_right_b == player.captcha_left_b
        ):
            player.captcha_right_a = random.randint(2, 20)
            player.captcha_right_b = random.randint(2, 20)

    drawn = player.participant.vars['drawn_candidates']


    start = (player.round_number - 1) * 2
    pair = drawn[start:start + 2]

    if len(pair) < 2:
        pair = random.sample(available_candidate_ids(), 2)

    left_id, right_id = random.sample(pair, 2)

    left = CANDIDATE_DATA[left_id]
    right = CANDIDATE_DATA[right_id]

    player.left_candidate_id = left_id
    player.right_candidate_id = right_id

    player.left_image_path = left['image_path']
    player.right_image_path = right['image_path']

    player.left_ideologia_cat = left['ideologia_cat']
    player.right_ideologia_cat = right['ideologia_cat']

    player.left_nombre = left['nombre']
    player.right_nombre = right['nombre']

    player.left_partido = left['partido']
    player.right_partido = right['partido']

    player.left_genero = left['genero']
    player.right_genero = right['genero']

    player.left_edad = left['edad']
    player.right_edad = right['edad']

    player.left_votos = left['votos']
    player.right_votos = right['votos']

    player.left_dataset_row_json = left['dataset_row_json']
    player.right_dataset_row_json = right['dataset_row_json']


def candidate_payload(candidate_id):
    candidate = CANDIDATE_DATA[candidate_id]

    return {
        'id': candidate['id'],
        'image_path': candidate['image_path'],
        'ideologia_cat': candidate['ideologia_cat'],
    }