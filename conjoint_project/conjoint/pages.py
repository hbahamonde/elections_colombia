from otree.api import Page

from .models import C, assign_candidates, candidate_payload


class Intro(Page):
    def is_displayed(self):
        return self.round_number == 1

    def vars_for_template(self):
        return {
            'num_practice_rounds': C.NUM_PRACTICE_ROUNDS,
            'num_main_rounds': C.NUM_MAIN_ROUNDS,
            'countdown_seconds': C.COUNTDOWN_SECONDS,
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
        'countdown_expired',
    ]

    def vars_for_template(self):
        assign_candidates(self.player)

        return {
            'round_number': self.round_number,
            'total_rounds': C.NUM_ROUNDS,
            'num_practice_rounds': C.NUM_PRACTICE_ROUNDS,
            'num_main_rounds': C.NUM_MAIN_ROUNDS,
            'is_practice_round': self.player.is_practice_round,
            'main_round_number': self.player.main_round_number,
            'treatment_arm': self.player.treatment_arm,
            'timed_task': self.player.timed_task,
            'info_condition': self.player.info_condition,
            'countdown_seconds': C.COUNTDOWN_SECONDS,
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
        if self.player.timed_task and values.get('decision_side') == 'timeout':
            return

        if not values.get('decision_candidate_id'):
            return 'Por favor, seleccione una opción antes de continuar.'


class FollowUp(Page):
    form_model = 'player'

    form_fields = [
        'realistic_vote',
        'decision_factors',
        'rushed_scale',
        'info_cost_scale',
    ]

    def is_displayed(self):
        return self.round_number > C.NUM_PRACTICE_ROUNDS

    def vars_for_template(self):
        return {
            'main_round_number': self.player.main_round_number,
            'num_main_rounds': C.NUM_MAIN_ROUNDS,
            'timed_task': self.player.timed_task,
            'info_condition': self.player.info_condition,
        }

    def error_message(self, values):
        if not values.get('realistic_vote'):
            return 'Por favor, responda si habría votado por un(a) candidato(a) así en la realidad.'

        if values.get('realistic_vote') == 'yes' and not values.get('decision_factors'):
            return 'Por favor, seleccione al menos un factor que haya considerado.'

        if self.player.timed_task and values.get('rushed_scale') is None:
            return 'Por favor, indique qué tan apurado se sintió.'

        if self.player.info_condition == 'captcha_ver_mas' and values.get('info_cost_scale') is None:
            return 'Por favor, indique qué tanto le costó informarse.'


class Questionnaire(Page):
    form_model = 'player'

    form_fields = [
        'voted_last_municipal',
        'political_interest',
        'politics_frequency',
        'left_right_self_placement',
    ]

    def is_displayed(self):
        return self.round_number == C.NUM_ROUNDS

    def error_message(self, values):
        required_fields = [
            'voted_last_municipal',
            'political_interest',
            'politics_frequency',
            'left_right_self_placement',
        ]

        if any(values.get(field) in [None, ''] for field in required_fields):
            return 'Por favor, responda todas las preguntas antes de continuar.'


class Summary(Page):
    def is_displayed(self):
        return self.round_number == C.NUM_ROUNDS

    def vars_for_template(self):
        main_rounds = [
            p for p in self.player.in_all_rounds()
            if not p.is_practice_round
        ]

        return {
            'rounds': main_rounds,
            'num_main_rounds': C.NUM_MAIN_ROUNDS,
        }


page_sequence = [Intro, Task, FollowUp, Questionnaire, Summary]
