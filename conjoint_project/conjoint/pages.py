from otree.api import Page

from .models import (
    C,
    assign_candidates,
    candidate_payload,
    ensure_participant_vars,
    mentions_colombia,
    player_is_eligible,
    player_was_screened_out,
    screen_out,
)


class Consent(Page):
    form_model = 'player'
    form_fields = ['consent_accepted']

    def is_displayed(self):
        return self.round_number == 1

    def error_message(self, values):
        if not values.get('consent_accepted'):
            return 'Para participar en el estudio, debe aceptar el consentimiento informado.'


class CountryResidence(Page):
    form_model = 'player'
    form_fields = ['country_of_residence']

    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )

    def error_message(self, values):
        if not (values.get('country_of_residence') or '').strip():
            return 'Por favor, indique el país donde reside actualmente.'

    def before_next_page(self):
        if mentions_colombia(self.player.country_of_residence):
            screen_out(self.player, 'residence_colombia')


class Nationality(Page):
    form_model = 'player'
    form_fields = ['nationality']

    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )

    def error_message(self, values):
        if not (values.get('nationality') or '').strip():
            return 'Por favor, indique su nacionalidad.'

    def before_next_page(self):
        if mentions_colombia(self.player.nationality):
            screen_out(self.player, 'nationality_colombian')


class LivedInColombia(Page):
    form_model = 'player'
    form_fields = ['lived_in_colombia']

    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )

    def error_message(self, values):
        if not values.get('lived_in_colombia'):
            return 'Por favor, seleccione una opción.'

    def before_next_page(self):
        exclusion_reasons = {
            'yes': 'lived_colombia',
            'currently': 'currently_in_colombia',
            'prefer_not_to_answer': 'lived_prefer_not_to_answer',
        }
        reason = exclusion_reasons.get(self.player.lived_in_colombia)
        if reason:
            screen_out(self.player, reason)


class Intro(Page):
    def is_displayed(self):
        return self.round_number == 1 and player_is_eligible(self.player)

    def vars_for_template(self):
        ensure_participant_vars(self.player)

        treatment_arm = self.participant.vars.get('treatment_arm', '')

        return {
            'is_practice_done_page': False,
            'num_practice_rounds': C.NUM_PRACTICE_ROUNDS,
            'num_main_rounds': C.NUM_MAIN_ROUNDS,
            'countdown_seconds': C.COUNTDOWN_SECONDS,
            'treatment_arm': treatment_arm,
            'is_timer_group': treatment_arm == 'timer_mostrar_mas',
            'is_info_cost_group': treatment_arm == 'captcha_ver_mas',
            'is_control_group': treatment_arm == 'control_ver_mas',
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

    def is_displayed(self):
        return player_is_eligible(self.player)

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


class PracticeDone(Page):
    template_name = 'conjoint/Intro.html'

    def is_displayed(self):
        return (
            self.round_number == C.NUM_PRACTICE_ROUNDS
            and player_is_eligible(self.player)
        )

    def vars_for_template(self):
        ensure_participant_vars(self.player)

        treatment_arm = self.participant.vars.get('treatment_arm', '')

        return {
            'is_practice_done_page': True,
            'num_practice_rounds': C.NUM_PRACTICE_ROUNDS,
            'num_main_rounds': C.NUM_MAIN_ROUNDS,
            'countdown_seconds': C.COUNTDOWN_SECONDS,
            'treatment_arm': treatment_arm,
            'is_timer_group': treatment_arm == 'timer_mostrar_mas',
            'is_info_cost_group': treatment_arm == 'captcha_ver_mas',
            'is_control_group': treatment_arm == 'control_ver_mas',
        }


class FollowUp(Page):
    form_model = 'player'

    form_fields = [
        'realistic_vote',
        'decision_factors',
        'rushed_scale',
        'info_cost_scale',
    ]

    def is_displayed(self):
        return (
            self.round_number > C.NUM_PRACTICE_ROUNDS
            and player_is_eligible(self.player)
        )

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


class GeneralQuestionsIntro(Page):
    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )


class Age(Page):
    form_model = 'player'
    form_fields = ['age_years']

    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )

    def error_message(self, values):
        age = values.get('age_years')

        if age is None:
            return 'Por favor, indique su edad.'

        if age < 18 or age > 65:
            return 'Por favor, indique una edad entre 18 y 65 años.'


class Gender(Page):
    form_model = 'player'
    form_fields = ['gender_identity', 'gender_identity_other']

    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )

    def error_message(self, values):
        if not values.get('gender_identity'):
            return 'Por favor, seleccione una opción.'

        if (
            values.get('gender_identity') == 'otra'
            and not values.get('gender_identity_other')
        ):
            return 'Por favor, describa la opción con la que se identifica.'


class Occupation(Page):
    form_model = 'player'
    form_fields = ['occupation_status', 'occupation_status_other']

    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )

    def error_message(self, values):
        if not values.get('occupation_status'):
            return 'Por favor, seleccione una opción.'

        if (
            values.get('occupation_status') == 'otra'
            and not values.get('occupation_status_other')
        ):
            return 'Por favor, describa su situación ocupacional.'


class Education(Page):
    form_model = 'player'
    form_fields = ['education_level']

    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )

    def error_message(self, values):
        if not values.get('education_level'):
            return 'Por favor, seleccione una opción.'


class VotedLastMunicipal(Page):
    form_model = 'player'
    form_fields = ['voted_last_municipal']

    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )

    def error_message(self, values):
        if not values.get('voted_last_municipal'):
            return 'Por favor, seleccione una opción.'


class PoliticalInterest(Page):
    form_model = 'player'
    form_fields = ['political_interest']

    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )

    def error_message(self, values):
        if values.get('political_interest') is None:
            return 'Por favor, seleccione una opción.'


class PoliticsFrequency(Page):
    form_model = 'player'
    form_fields = ['politics_frequency']

    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )

    def error_message(self, values):
        if not values.get('politics_frequency'):
            return 'Por favor, seleccione una opción.'


class LeftRightPlacement(Page):
    form_model = 'player'
    form_fields = ['left_right_self_placement']

    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )

    def error_message(self, values):
        if not values.get('left_right_self_placement'):
            return 'Por favor, seleccione una opción.'


class Summary(Page):
    def is_displayed(self):
        return self.round_number == C.NUM_ROUNDS

    def vars_for_template(self):
        return {'screened_out': player_was_screened_out(self.player)}


page_sequence = [
    Consent,
    CountryResidence,
    Nationality,
    LivedInColombia,
    GeneralQuestionsIntro,
    Age,
    Gender,
    Occupation,
    Education,
    VotedLastMunicipal,
    PoliticalInterest,
    PoliticsFrequency,
    LeftRightPlacement,
    Intro,
    Task,
    PracticeDone,
    FollowUp,
    Summary,
]
