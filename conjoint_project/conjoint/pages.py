from otree.api import Page

from .models import C, assign_candidates, candidate_payload


class Intro(Page):
    def is_displayed(self):
        return self.round_number == 1

    def vars_for_template(self):
        return {
            'initial_endowment': C.INITIAL_ENDOWMENT,
            'current_balance': self.participant.vars.get(
                'point_balance',
                C.INITIAL_ENDOWMENT,
            ),
            'treatment_arm': self.participant.vars.get('treatment_arm', ''),
        }


class Task(Page):
    form_model = 'player'

    form_fields = [
        'left_ideology_opened',
        'right_ideology_opened',
        'info_cost_task_completed',
        'info_cost_attempts',
        'decision_candidate_id',
        'decision_side',
        'time_spent_seconds',
        'time_to_first_choice_seconds',
        'choice_changes',
        'learn_more_clicks',
        'mouse_distance_px',
        'left_hover_seconds',
        'right_hover_seconds',
    ]

    def vars_for_template(self):
        assign_candidates(self.player)

        return {
            'round_number': self.round_number,
            'total_rounds': C.NUM_ROUNDS,
            'current_balance': self.participant.vars.get(
                'point_balance',
                C.INITIAL_ENDOWMENT,
            ),
            'treatment_arm': self.player.treatment_arm,
            'timed_task': self.player.timed_task,
            'info_condition': self.player.info_condition,
            'left_candidate': candidate_payload(self.player.left_candidate_id),
            'right_candidate': candidate_payload(self.player.right_candidate_id),
            'captcha_left_a': self.player.captcha_left_a,
            'captcha_left_b': self.player.captcha_left_b,
            'captcha_left_sum': self.player.captcha_left_a + self.player.captcha_left_b,
            'captcha_right_a': self.player.captcha_right_a,
            'captcha_right_b': self.player.captcha_right_b,
            'captcha_right_sum': self.player.captcha_right_a + self.player.captcha_right_b,
        }

    def error_message(self, values):
        if not values.get('decision_candidate_id'):
            return 'Por favor, seleccione una opción antes de continuar.'

    def before_next_page(self):
        old_balance = self.participant.vars.get(
            'point_balance',
            C.INITIAL_ENDOWMENT,
        )

        self.player.balance_after_task = old_balance
        self.participant.vars['point_balance'] = old_balance


class Summary(Page):
    def is_displayed(self):
        return self.round_number == C.NUM_ROUNDS

    def vars_for_template(self):
        return {
            'rounds': self.player.in_all_rounds(),
            'initial_endowment': C.INITIAL_ENDOWMENT,
            'final_balance': self.participant.vars.get(
                'point_balance',
                C.INITIAL_ENDOWMENT,
            ),
            'treatment_arm': self.participant.vars.get('treatment_arm', ''),
        }


page_sequence = [Intro, Task, Summary]