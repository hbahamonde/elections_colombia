from otree.api import Page
import json
from .models import (
    Constants, Subsession, Group, Player,
    assign_positions, candidate_payload,
    get_metric_value, get_metric_label,
    get_attribute_costs, get_attribute_weights,
)


class Intro(Page):
    def is_displayed(self):
        return self.round_number == 1

    def vars_for_template(self):
        attribute_costs = get_attribute_costs(self.session)
        attribute_weights = get_attribute_weights(self.session)

        return dict(
            initial_endowment=self.player.participant.vars.get('initial_endowment', Constants.initial_endowment),
            current_balance=self.player.participant.vars.get('point_balance', Constants.initial_endowment),
            correct_payoff=Constants.correct_payoff,
            incorrect_payoff_display=abs(Constants.incorrect_payoff),
            time_penalty_per_second=Constants.time_penalty_per_second,
            party_cost=attribute_costs['party'],
            age_cost=attribute_costs['age'],
            occupation_cost=attribute_costs['occupation'],
            party_weight=attribute_weights['party'],
            age_weight=attribute_weights['age'],
            occupation_weight=attribute_weights['occupation'],
        )


class Task(Page):
    form_model = 'player'
    form_fields = [
        'left_party_opened',
        'left_age_opened',
        'left_occupation_opened',
        'right_party_opened',
        'right_age_opened',
        'right_occupation_opened',
        'decision_candidate_id',
        'decision_side',
        'time_spent_seconds',
        'info_cost_spent',
    ]

    def vars_for_template(self):
        assign_positions(self.player)

        left = candidate_payload(self.player.left_candidate_id)
        right = candidate_payload(self.player.right_candidate_id)

        left_metric = get_metric_value(self.player.left_candidate_id)
        right_metric = get_metric_value(self.player.right_candidate_id)

        if left_metric > right_metric:
            winner_side = 'left'
            winner_id = self.player.left_candidate_id
            winner_metric = left_metric
        else:
            winner_side = 'right'
            winner_id = self.player.right_candidate_id
            winner_metric = right_metric

        attribute_order = self.player.participant.vars.get('attribute_order', Constants.attribute_keys)
        attribute_costs = get_attribute_costs(self.session)
        attribute_weights = get_attribute_weights(self.session)

        return dict(
            round_number=self.round_number,
            total_rounds=Constants.num_rounds,
            left_candidate=left,
            right_candidate=right,
            timed_task=self.player.timed_task,
            metric_label=get_metric_label(),
            winner_side=winner_side,
            winner_id=winner_id,
            winner_metric=winner_metric,
            current_balance=self.player.participant.vars.get('point_balance', Constants.initial_endowment),
            correct_payoff=Constants.correct_payoff,
            incorrect_payoff=Constants.incorrect_payoff,
            time_penalty_per_second=Constants.time_penalty_per_second,
            attribute_order_json=json.dumps(attribute_order),
            attribute_costs_json=json.dumps(attribute_costs),
            attribute_weights_json=json.dumps(attribute_weights),
        )

    def error_message(self, values):
        if not values.get('decision_candidate_id'):
            return 'Please choose one candidate before continuing.'

    def before_next_page(self):
        left_metric = get_metric_value(self.player.left_candidate_id)
        right_metric = get_metric_value(self.player.right_candidate_id)

        if left_metric > right_metric:
            winning_id = self.player.left_candidate_id
        else:
            winning_id = self.player.right_candidate_id

        self.player.correct = (self.player.decision_candidate_id == winning_id)

        if self.player.correct:
            self.player.accuracy_payoff = Constants.correct_payoff
        else:
            self.player.accuracy_payoff = Constants.incorrect_payoff

        if self.player.correct and self.player.timed_task:
            self.player.time_penalty_applied = int(
                self.player.time_spent_seconds * Constants.time_penalty_per_second
            )
        else:
            self.player.time_penalty_applied = 0

        self.player.task_net_change = (
            self.player.accuracy_payoff
            - self.player.time_penalty_applied
            - self.player.info_cost_spent
        )

        old_balance = self.player.participant.vars.get('point_balance', Constants.initial_endowment)
        new_balance = max(0, old_balance + self.player.task_net_change)

        self.player.balance_after_task = new_balance
        self.player.participant.vars['point_balance'] = new_balance
        self.player.points_earned = self.player.task_net_change


class Summary(Page):
    def is_displayed(self):
        return self.round_number == Constants.num_rounds

    def vars_for_template(self):
        rounds = self.player.in_all_rounds()
        return dict(
            rounds=rounds,
            initial_endowment=self.player.participant.vars.get('initial_endowment', Constants.initial_endowment),
            final_balance=self.player.participant.vars.get('point_balance', Constants.initial_endowment),
            timed_tasks=self.player.participant.vars.get('timed_tasks', []),
            attribute_order=self.player.participant.vars.get('attribute_order', Constants.attribute_keys),
            metric_label=get_metric_label(),
        )


page_sequence = [Intro, Task, Summary]