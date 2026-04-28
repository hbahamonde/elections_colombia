from otree.api import *
import csv
import random
from pathlib import Path


doc = """
Conjoint with:
- pooled candidate draw
- task-level timer randomization
- attribute-level unlocking
- randomized attribute order by subject
- dynamic attribute pricing
- running balance with endowment
"""


def first_nonempty(row, keys):
    for key in keys:
        value = (row.get(key, '') or '').strip()
        if value != '':
            return value
    return ''


def load_candidate_data():
    data_path = (
        Path(__file__).resolve().parent.parent
        / '_static'
        / 'conjoint'
        / 'data'
        / 'dataset.csv'
    )

    if not data_path.exists():
        raise FileNotFoundError(f'dataset.csv not found at: {data_path}')

    rows = {}
    with open(data_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            candidate_id = str(row['ID']).strip()

            vote_share_raw = row.get('porcentajedevotos', '') or '0'
            try:
                vote_share = float(str(vote_share_raw).replace(',', '.'))
            except:
                vote_share = 0.0

            votes_raw = row.get('Votos', '0') or '0'
            try:
                votes = int(float(votes_raw))
            except:
                votes = 0

            occupation = first_nonempty(
                row,
                [
                    'occupation',
                    'OCCUPATION',
                    'ocupacion',
                    'OCUPACION',
                    'ammatti',
                    'AMMATTI',
                ],
            )

            rows[candidate_id] = {
                'id': candidate_id,
                'party': row.get('PARTIDO', '').strip(),
                'age': row.get('age', '').strip() or row.get('EDAD', '').strip(),
                'occupation': occupation,
                'votes': votes,
                'vote_share': vote_share,
                'municipality': row.get('MUNICIPIO', '').strip(),
                'year': row.get('year', '').strip() or row.get('year2', '').strip(),
            }
    return rows


CANDIDATE_DATA = load_candidate_data()


# Temporary toy profile values for development.
# These let the Finnish-version app run even before the Finnish metadata file is available.
# Replace these with real Finnish values later.
TOY_PROFILE_OVERRIDES = {
    '110108': {
        'party': 'Party A',
        'age': '42',
        'occupation': 'Teacher',
    },
    '110702': {
        'party': 'Party B',
        'age': '51',
        'occupation': 'Engineer',
    },
    '113701': {
        'party': 'Party C',
        'age': '36',
        'occupation': 'Nurse',
    },
    '119102': {
        'party': 'Party A',
        'age': '47',
        'occupation': 'Lawyer',
    },
}


def apply_toy_profile_overrides():
    for candidate_id, override in TOY_PROFILE_OVERRIDES.items():
        if candidate_id not in CANDIDATE_DATA:
            CANDIDATE_DATA[candidate_id] = {
                'id': candidate_id,
                'party': '',
                'age': '',
                'occupation': '',
                'votes': 0,
                'vote_share': 0.0,
                'municipality': '',
                'year': '',
            }

        CANDIDATE_DATA[candidate_id]['party'] = override['party']
        CANDIDATE_DATA[candidate_id]['age'] = override['age']
        CANDIDATE_DATA[candidate_id]['occupation'] = override['occupation']


apply_toy_profile_overrides()

def available_candidate_ids():
    image_dir = (
        Path(__file__).resolve().parent.parent
        / '_static'
        / 'conjoint'
        / 'images'
    )

    available = []
    for candidate_id, row in CANDIDATE_DATA.items():
        image_path = image_dir / f'{candidate_id}.jpg'

        if not image_path.exists():
            continue

        party = (row.get('party', '') or '').strip()
        age = (row.get('age', '') or '').strip()
        occupation = (row.get('occupation', '') or '').strip()

        if party != '' and age != '' and occupation != '':
            available.append(candidate_id)

    return available


class Constants(BaseConstants):
    name_in_url = 'conjoint'
    players_per_group = None
    num_rounds = 2

    compare_metric = 'vote_share'
    timer_probability = 0.5

    initial_endowment = 100
    correct_payoff = 30
    incorrect_payoff = -15
    time_penalty_per_second = 1

    # default dynamic pricing structure
    default_info_cost_unit = 2
    default_attribute_weights = {
        'party': 3,
        'occupation': 2,
        'age': 1,
    }

    attribute_keys = ['party', 'age', 'occupation']


def get_attribute_weights(session):
    weights = Constants.default_attribute_weights.copy()

    for attr in weights.keys():
        config_key = f'weight_{attr}'
        if config_key in session.config and session.config[config_key] is not None:
            weights[attr] = int(session.config[config_key])

    return weights


def get_attribute_costs(session):
    weights = get_attribute_weights(session)
    base_unit = session.config.get('info_cost_unit', Constants.default_info_cost_unit)

    costs = {}
    for attr, weight in weights.items():
        direct_cost_key = f'cost_{attr}'
        if direct_cost_key in session.config and session.config[direct_cost_key] is not None:
            costs[attr] = int(session.config[direct_cost_key])
        else:
            costs[attr] = int(base_unit * weight)

    return costs


class Subsession(BaseSubsession):
    pass


def draw_candidates_for_game():
    candidate_pool = available_candidate_ids()
    needed = 2 * Constants.num_rounds

    if len(candidate_pool) < needed:
        raise ValueError(
            f'Not enough eligible candidates with images and metadata. '
            f'Need at least {needed}, found {len(candidate_pool)}.'
        )

    return random.sample(candidate_pool, needed)


def creating_session(subsession):
    if subsession.round_number != 1:
        return

    for player in subsession.get_players():
        if 'initial_endowment' not in player.participant.vars:
            player.participant.vars['initial_endowment'] = Constants.initial_endowment

        if 'point_balance' not in player.participant.vars:
            player.participant.vars['point_balance'] = Constants.initial_endowment

        if 'timed_tasks' not in player.participant.vars:
            player.participant.vars['timed_tasks'] = [
                random.random() < Constants.timer_probability
                for _ in range(Constants.num_rounds)
            ]

        if 'drawn_candidates' not in player.participant.vars:
            player.participant.vars['drawn_candidates'] = draw_candidates_for_game()

        if 'attribute_order' not in player.participant.vars:
            player.participant.vars['attribute_order'] = random.sample(
                Constants.attribute_keys,
                len(Constants.attribute_keys),
            )


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    left_candidate_id = models.StringField()
    right_candidate_id = models.StringField()

    timed_task = models.BooleanField(initial=False)

    left_party_opened = models.BooleanField(initial=False)
    left_age_opened = models.BooleanField(initial=False)
    left_occupation_opened = models.BooleanField(initial=False)

    right_party_opened = models.BooleanField(initial=False)
    right_age_opened = models.BooleanField(initial=False)
    right_occupation_opened = models.BooleanField(initial=False)

    decision_candidate_id = models.StringField(blank=True)
    decision_side = models.StringField(blank=True)

    time_spent_seconds = models.FloatField(initial=0)

    info_cost_spent = models.IntegerField(initial=0)
    time_penalty_applied = models.IntegerField(initial=0)
    accuracy_payoff = models.IntegerField(initial=0)
    task_net_change = models.IntegerField(initial=0)
    balance_after_task = models.IntegerField(initial=0)

    correct = models.BooleanField(initial=False)
    points_earned = models.IntegerField(initial=0)


def ensure_randomization(player):
    if 'initial_endowment' not in player.participant.vars:
        player.participant.vars['initial_endowment'] = Constants.initial_endowment

    if 'point_balance' not in player.participant.vars:
        player.participant.vars['point_balance'] = Constants.initial_endowment

    if 'timed_tasks' not in player.participant.vars:
        player.participant.vars['timed_tasks'] = [
            random.random() < Constants.timer_probability
            for _ in range(Constants.num_rounds)
        ]

    if 'drawn_candidates' not in player.participant.vars:
        player.participant.vars['drawn_candidates'] = draw_candidates_for_game()

    if 'attribute_order' not in player.participant.vars:
        player.participant.vars['attribute_order'] = random.sample(
            Constants.attribute_keys,
            len(Constants.attribute_keys),
        )


def get_candidates_for_round(player):
    ensure_randomization(player)

    drawn = player.participant.vars['drawn_candidates']
    start_idx = (player.round_number - 1) * 2
    end_idx = start_idx + 2

    round_candidates = drawn[start_idx:end_idx]

    if len(round_candidates) != 2:
        raise ValueError(
            f'Round {player.round_number} does not have exactly 2 candidates assigned.'
        )

    return round_candidates


def assign_positions(player):
    round_candidates = get_candidates_for_round(player)
    shuffled = random.sample(list(round_candidates), 2)

    player.left_candidate_id = shuffled[0]
    player.right_candidate_id = shuffled[1]
    player.timed_task = player.participant.vars['timed_tasks'][player.round_number - 1]


def candidate_payload(candidate_id):
    row = CANDIDATE_DATA[candidate_id]
    return dict(
        id=row['id'],
        image_path=f'conjoint/images/{row["id"]}.jpg',
        party=row['party'],
        age=row['age'],
        occupation=row['occupation'],
        votes=row['votes'],
        vote_share=row['vote_share'],
        municipality=row['municipality'],
        year=row['year'],
    )


def get_metric_value(candidate_id):
    row = CANDIDATE_DATA[candidate_id]
    if Constants.compare_metric == 'vote_share':
        return row['vote_share']
    return row['votes']


def get_metric_label():
    if Constants.compare_metric == 'vote_share':
        return 'vote share'
    return 'votes'