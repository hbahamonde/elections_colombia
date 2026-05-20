from otree.api import *
import csv
import json
import random
from pathlib import Path


doc = """
Visual conjoint experiment.

Participants choose between two candidate photos. Candidate metadata is read from:
_static/conjoint/data/dataset.csv

Candidate photos are stored in:
_static/conjoint/images/

The backend records:
- randomized treatment assignment
- practice versus main-experiment round status
- left/right candidate IDs
- image paths
- all candidate-level metadata from dataset.csv
- full candidate CSV rows as JSON backups
- information acquisition behavior
- math-task behavior
- countdown/time-pressure behavior
- timing and mouse-tracking metadata
- post-choice follow-up answers
- final political questionnaire answers
"""


DATASET_COLUMNS = [
    'ID',
    'DEPARTAMENTO',
    'COD_DPTO',
    'MUNICIPIO',
    'COD_MCPIO',
    'Cod_candidato',
    'NOMBRE',
    'Votos',
    'PARTIDO',
    'COD_PARTIDO',
    'GENERO',
    'EDAD',
    'age (estimada)',
    'gender (estimado)',
    'blurness',
    'facequality',
    'yaw_angle',
    'pitch_angle',
    'roll_angle',
    'BD',
    'alto',
    'ancho',
    'fhwr',
    'alto_rot',
    'ancho_rot',
    'fhwr_rot',
    'alto_correg',
    'ancho_correg',
    'fhwr_correg',
    'ranking',
    'partidoFE',
    'ideologia_cat',
    'fhwr_cat',
    'combo_id',
]


FIELD_NAME_MAP = {
    'ID': 'id',
    'DEPARTAMENTO': 'departamento',
    'COD_DPTO': 'cod_dpto',
    'MUNICIPIO': 'municipio',
    'COD_MCPIO': 'cod_mcpio',
    'Cod_candidato': 'cod_candidato',
    'NOMBRE': 'nombre',
    'Votos': 'votos',
    'PARTIDO': 'partido',
    'COD_PARTIDO': 'cod_partido',
    'GENERO': 'genero',
    'EDAD': 'edad',
    'age (estimada)': 'age_estimada',
    'gender (estimado)': 'gender_estimado',
    'blurness': 'blurness',
    'facequality': 'facequality',
    'yaw_angle': 'yaw_angle',
    'pitch_angle': 'pitch_angle',
    'roll_angle': 'roll_angle',
    'BD': 'bd',
    'alto': 'alto',
    'ancho': 'ancho',
    'fhwr': 'fhwr',
    'alto_rot': 'alto_rot',
    'ancho_rot': 'ancho_rot',
    'fhwr_rot': 'fhwr_rot',
    'alto_correg': 'alto_correg',
    'ancho_correg': 'ancho_correg',
    'fhwr_correg': 'fhwr_correg',
    'ranking': 'ranking',
    'partidoFE': 'partido_fe',
    'ideologia_cat': 'ideologia_cat',
    'fhwr_cat': 'fhwr_cat',
    'combo_id': 'combo_id',
}


REALISTIC_VOTE_CHOICES = [
    ['yes', 'Sí'],
    ['no', 'No'],
]


POLITICS_FREQUENCY_CHOICES = [
    ['never', 'Nunca'],
    ['less_than_once_per_week', 'Menos de una vez por semana'],
    ['once_or_twice_per_week', 'Una o dos veces por semana'],
    ['several_times_per_week', 'Varias veces por semana'],
    ['every_day', 'Todos los días'],
]


LIKERT_1_TO_7 = [[i, str(i)] for i in range(1, 8)]
LEFT_RIGHT_0_TO_10 = [[i, str(i)] for i in range(0, 11)]


def clean_value(value):
    if value is None:
        return ''
    return str(value).strip()


def clean_candidate_id(value):
    value = clean_value(value)

    if value.endswith('.0'):
        value = value[:-2]

    return Path(value).stem


def find_image_for_candidate(candidate_id, image_dir):
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp']

    for ext in allowed_extensions:
        image_path = image_dir / f'{candidate_id}{ext}'
        if image_path.exists():
            return image_path.name

    return None


def load_candidate_data():
    project_root = Path(__file__).resolve().parent.parent

    data_path = project_root / '_static' / 'conjoint' / 'data' / 'dataset.csv'
    image_dir = project_root / '_static' / 'conjoint' / 'images'

    if not data_path.exists():
        raise FileNotFoundError(f'dataset.csv not found at: {data_path}')

    if not image_dir.exists():
        raise FileNotFoundError(f'image folder not found at: {image_dir}')

    candidates = {}

    with open(data_path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError('dataset.csv has no header row.')

        missing_columns = [
            column for column in DATASET_COLUMNS
            if column not in reader.fieldnames
        ]

        if missing_columns:
            raise ValueError(
                f'dataset.csv is missing these expected columns: {missing_columns}'
            )

        for raw_row in reader:
            row = {
                clean_value(key): clean_value(value)
                for key, value in raw_row.items()
            }

            candidate_id = clean_candidate_id(row.get('ID'))

            if candidate_id == '':
                continue

            image_filename = find_image_for_candidate(candidate_id, image_dir)

            if image_filename is None:
                continue

            row['ID'] = candidate_id
            row['_image_filename'] = image_filename
            row['_image_path'] = f'conjoint/images/{image_filename}'

            candidate = {
                'id': candidate_id,
                'image_filename': image_filename,
                'image_path': f'conjoint/images/{image_filename}',
                'dataset_row_json': json.dumps(row, ensure_ascii=False),
            }

            for original_name, field_name in FIELD_NAME_MAP.items():
                candidate[field_name] = clean_value(row.get(original_name))

            candidates[candidate_id] = candidate

    if len(candidates) < 2:
        raise ValueError(
            'Need at least two candidate rows with matching image files. '
            f'dataset.csv is at {data_path}. '
            f'Images are expected in {image_dir}.'
        )

    return candidates


CANDIDATE_DATA = load_candidate_data()


class C(BaseConstants):
    NAME_IN_URL = 'conjoint'
    PLAYERS_PER_GROUP = None

    NUM_PRACTICE_ROUNDS = 5
    NUM_MAIN_ROUNDS = 15
    NUM_ROUNDS = NUM_PRACTICE_ROUNDS + NUM_MAIN_ROUNDS

    COUNTDOWN_SECONDS = 10

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
    is_practice_round = models.BooleanField(initial=False)
    main_round_number = models.IntegerField(initial=0)

    treatment_arm = models.StringField()
    timed_task = models.BooleanField(initial=False)
    info_condition = models.StringField()
    countdown_seconds = models.IntegerField(initial=C.COUNTDOWN_SECONDS)
    countdown_expired = models.BooleanField(initial=False)

    left_candidate_id = models.StringField()
    right_candidate_id = models.StringField()

    left_image_path = models.StringField()
    right_image_path = models.StringField()

    left_id = models.StringField(blank=True)
    left_departamento = models.StringField(blank=True)
    left_cod_dpto = models.StringField(blank=True)
    left_municipio = models.StringField(blank=True)
    left_cod_mcpio = models.StringField(blank=True)
    left_cod_candidato = models.StringField(blank=True)
    left_nombre = models.StringField(blank=True)
    left_votos = models.StringField(blank=True)
    left_partido = models.StringField(blank=True)
    left_cod_partido = models.StringField(blank=True)
    left_genero = models.StringField(blank=True)
    left_edad = models.StringField(blank=True)
    left_age_estimada = models.StringField(blank=True)
    left_gender_estimado = models.StringField(blank=True)
    left_blurness = models.StringField(blank=True)
    left_facequality = models.StringField(blank=True)
    left_yaw_angle = models.StringField(blank=True)
    left_pitch_angle = models.StringField(blank=True)
    left_roll_angle = models.StringField(blank=True)
    left_bd = models.StringField(blank=True)
    left_alto = models.StringField(blank=True)
    left_ancho = models.StringField(blank=True)
    left_fhwr = models.StringField(blank=True)
    left_alto_rot = models.StringField(blank=True)
    left_ancho_rot = models.StringField(blank=True)
    left_fhwr_rot = models.StringField(blank=True)
    left_alto_correg = models.StringField(blank=True)
    left_ancho_correg = models.StringField(blank=True)
    left_fhwr_correg = models.StringField(blank=True)
    left_ranking = models.StringField(blank=True)
    left_partido_fe = models.StringField(blank=True)
    left_ideologia_cat = models.StringField(blank=True)
    left_fhwr_cat = models.StringField(blank=True)
    left_combo_id = models.StringField(blank=True)

    right_id = models.StringField(blank=True)
    right_departamento = models.StringField(blank=True)
    right_cod_dpto = models.StringField(blank=True)
    right_municipio = models.StringField(blank=True)
    right_cod_mcpio = models.StringField(blank=True)
    right_cod_candidato = models.StringField(blank=True)
    right_nombre = models.StringField(blank=True)
    right_votos = models.StringField(blank=True)
    right_partido = models.StringField(blank=True)
    right_cod_partido = models.StringField(blank=True)
    right_genero = models.StringField(blank=True)
    right_edad = models.StringField(blank=True)
    right_age_estimada = models.StringField(blank=True)
    right_gender_estimado = models.StringField(blank=True)
    right_blurness = models.StringField(blank=True)
    right_facequality = models.StringField(blank=True)
    right_yaw_angle = models.StringField(blank=True)
    right_pitch_angle = models.StringField(blank=True)
    right_roll_angle = models.StringField(blank=True)
    right_bd = models.StringField(blank=True)
    right_alto = models.StringField(blank=True)
    right_ancho = models.StringField(blank=True)
    right_fhwr = models.StringField(blank=True)
    right_alto_rot = models.StringField(blank=True)
    right_ancho_rot = models.StringField(blank=True)
    right_fhwr_rot = models.StringField(blank=True)
    right_alto_correg = models.StringField(blank=True)
    right_ancho_correg = models.StringField(blank=True)
    right_fhwr_correg = models.StringField(blank=True)
    right_ranking = models.StringField(blank=True)
    right_partido_fe = models.StringField(blank=True)
    right_ideologia_cat = models.StringField(blank=True)
    right_fhwr_cat = models.StringField(blank=True)
    right_combo_id = models.StringField(blank=True)

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

    realistic_vote = models.StringField(
        choices=REALISTIC_VOTE_CHOICES,
        widget=widgets.RadioSelect,
        blank=True,
    )
    decision_factors = models.LongStringField(blank=True)
    rushed_scale = models.IntegerField(
        choices=LIKERT_1_TO_7,
        widget=widgets.RadioSelectHorizontal,
        blank=True,
    )
    info_cost_scale = models.IntegerField(
        choices=LIKERT_1_TO_7,
        widget=widgets.RadioSelectHorizontal,
        blank=True,
    )

    voted_last_municipal = models.StringField(
        choices=REALISTIC_VOTE_CHOICES,
        widget=widgets.RadioSelect,
        blank=True,
    )
    political_interest = models.IntegerField(
        choices=LIKERT_1_TO_7,
        widget=widgets.RadioSelectHorizontal,
        blank=True,
    )
    politics_frequency = models.StringField(
        choices=POLITICS_FREQUENCY_CHOICES,
        widget=widgets.RadioSelect,
        blank=True,
    )
    left_right_self_placement = models.IntegerField(
        choices=LEFT_RIGHT_0_TO_10,
        widget=widgets.RadioSelectHorizontal,
        blank=True,
    )


def available_candidate_ids():
    return list(CANDIDATE_DATA.keys())


def draw_candidates_for_participant():
    ids = available_candidate_ids()
    needed = C.NUM_ROUNDS * 2

    if len(ids) >= needed:
        return random.sample(ids, needed)

    sampled = []

    while len(sampled) < needed:
        sampled.extend(random.sample(ids, 2))

    return sampled[:needed]


def assign_treatment(player):
    participant = player.participant
    demo_treatment_arm = player.session.config.get('demo_treatment_arm')

    if demo_treatment_arm in C.TREATMENT_ARMS:
        participant.vars['treatment_arm'] = demo_treatment_arm
        return

    if 'treatment_arm' not in participant.vars:
        participant.vars['treatment_arm'] = random.choice(C.TREATMENT_ARMS)


def creating_session(subsession):
    for player in subsession.get_players():
        participant = player.participant

        assign_treatment(player)

        if 'drawn_candidates' not in participant.vars:
            participant.vars['drawn_candidates'] = draw_candidates_for_participant()


def ensure_participant_vars(player):
    participant = player.participant

    assign_treatment(player)

    if 'drawn_candidates' not in participant.vars:
        participant.vars['drawn_candidates'] = draw_candidates_for_participant()


def save_candidate_to_player(player, side, candidate):
    setattr(player, f'{side}_image_path', candidate['image_path'])
    setattr(player, f'{side}_dataset_row_json', candidate['dataset_row_json'])

    for field_name in FIELD_NAME_MAP.values():
        setattr(player, f'{side}_{field_name}', candidate.get(field_name, ''))


def assign_candidates(player):
    ensure_participant_vars(player)

    if (
        player.field_maybe_none('left_candidate_id')
        and player.field_maybe_none('right_candidate_id')
    ):
        return

    treatment_arm = player.participant.vars['treatment_arm']

    player.is_practice_round = player.round_number <= C.NUM_PRACTICE_ROUNDS
    player.main_round_number = max(0, player.round_number - C.NUM_PRACTICE_ROUNDS)
    player.treatment_arm = treatment_arm
    player.timed_task = treatment_arm == 'timer_mostrar_mas'
    player.info_condition = treatment_arm
    player.countdown_seconds = C.COUNTDOWN_SECONDS

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

    save_candidate_to_player(player, 'left', left)
    save_candidate_to_player(player, 'right', right)


def candidate_payload(candidate_id):
    candidate = CANDIDATE_DATA[candidate_id]

    return {
        'id': candidate['id'],
        'image_path': candidate['image_path'],
        'ideologia_cat': candidate['ideologia_cat'],
    }
