from otree.api import *
import csv
import random
from pathlib import Path


doc = """
Toy conjoint:
- 2 tasks
- 2 candidate photos per task
- left/right randomized
- hidden expandable info
- one timed task and one untimed task
- subjects guess who got more votes
"""


def load_candidate_data():
    data_path = Path(__file__).parent / 'static' / 'conjoint' / 'data' / 'dataset.csv'
    rows = {}
    with open(data_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            candidate_id = str(row['ID']).strip()
            rows[candidate_id] = {
                'id': candidate_id,
                'party': row.get('PARTIDO', '').strip(),
                'ideology': row.get('ideologia_cat', '').strip(),
                'age': row.get('age', '').strip() or row.get('EDAD', '').strip(),
                'votes': int(float(row.get('Votos', 0) or 0)),
            }
    return rows


CANDIDATE_DATA = load_candidate_data()


class C(BaseConstants):
    NAME_IN_URL = 'conjoint'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 2

    BASE_POINTS = 100
    TIME_PENALTY_PER_SECOND = 2

    TOY_PAIRS = [
        ('110108', '113701'),
        ('110702', '119102'),
    ]


class Subsession(BaseSubsession):
    pass


def creating_session(subsession: Subsession):
    if subsession.round_number != 1:
        return

    for player in subsession.get_players():
        timed_round = random.choice([1, 2])
        player.participant.vars['timed_round'] = timed_round

        pair_order = C.TOY_PAIRS.copy()
        random.shuffle(pair_order)
        player.participant.vars['pair_order'] = pair_order


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    left_candidate_id = models.StringField()
    right_candidate_id = models.StringField()

    left_info_opened = models.BooleanField(initial=False)
    right_info_opened = models.BooleanField(initial=False)

    timed_task = models.BooleanField(initial=False)

    decision_candidate_id = models.StringField(blank=True)
    decision_side = models.StringField(blank=True)

    time_spent_seconds = models.FloatField(initial=0)

    correct = models.BooleanField(initial=False)
    points_earned = models.IntegerField(initial=0)


def get_pair_for_round(player: Player):
    pair_order = player.participant.vars['pair_order']
    pair = pair_order[player.round_number - 1]
    return pair


def assign_positions(player: Player):
    pair = get_pair_for_round(player)
    shuffled = random.sample(list(pair), 2)
    player.left_candidate_id = shuffled[0]
    player.right_candidate_id = shuffled[1]
    player.timed_task = (player.round_number == player.participant.vars['timed_round'])


def candidate_payload(candidate_id):
    row = CANDIDATE_DATA[candidate_id]
    return dict(
        id=row['id'],
        image_path=f'conjoint/images/{row["id"]}.jpg',
        party=row['party'],
        ideology=row['ideology'],
        age=row['age'],
        votes=row['votes'],
    )


class Intro(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1


class Task(Page):
    form_model = 'player'
    form_fields = [
        'left_info_opened',
        'right_info_opened',
        'decision_candidate_id',
        'decision_side',
        'time_spent_seconds',
    ]

    @staticmethod
    def vars_for_template(player: Player):
        assign_positions(player)

        left = candidate_payload(player.left_candidate_id)
        right = candidate_payload(player.right_candidate_id)

        return dict(
            round_number=player.round_number,
            total_rounds=C.NUM_ROUNDS,
            left_candidate=left,
            right_candidate=right,
            timed_task=player.timed_task,
            base_points=C.BASE_POINTS,
            time_penalty=C.TIME_PENALTY_PER_SECOND,
        )

    @staticmethod
    def error_message(player: Player, values):
        if not values.get('decision_candidate_id'):
            return 'Please choose one candidate before continuing.'

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        left_votes = CANDIDATE_DATA[player.left_candidate_id]['votes']
        right_votes = CANDIDATE_DATA[player.right_candidate_id]['votes']

        if left_votes > right_votes:
            winning_id = player.left_candidate_id
        else:
            winning_id = player.right_candidate_id

        player.correct = (player.decision_candidate_id == winning_id)

        if player.correct:
            if player.timed_task:
                penalty = int(player.time_spent_seconds * C.TIME_PENALTY_PER_SECOND)
                player.points_earned = max(0, C.BASE_POINTS - penalty)
            else:
                player.points_earned = C.BASE_POINTS
        else:
            player.points_earned = 0

        player.payoff = cu(player.points_earned)

        total_points = player.participant.vars.get('conjoint_points', 0)
        player.participant.vars['conjoint_points'] = total_points + player.points_earned


class Summary(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == C.NUM_ROUNDS

    @staticmethod
    def vars_for_template(player: Player):
        rounds = player.in_all_rounds()
        return dict(
            rounds=rounds,
            total_points=player.participant.vars.get('conjoint_points', 0),
            timed_round=player.participant.vars.get('timed_round'),
        )


page_sequence = [Intro, Task, Summary]