import hashlib
import json
import random

from otree.api import Page

from .navigation import (
    navigation_config, navigation_violation_recorded, raw_participant_vars,
    record_navigation_events, start_navigation_monitoring, study_is_terminated,
    submitted_task_rounds, terminate_participant,
)

from .models import (
    C,
    assign_candidates,
    candidate_payload,
    ensure_participant_vars,
    mentions_colombia,
    player_is_eligible,
    player_was_screened_out,
    profile_is_complete,
    screen_out,
)


RAFFLE_REGISTRATION_URL = 'https://bordedata.cl/encuestas/survey/42'


def raffle_registration_is_available(player):
    """Offer the external draw only after eligible study completion.

    Up to two submitted main tasks may lack a choice. A third missing main
    choice or a detected navigation violation prevents completion and access.
    The registration form is never sent participant codes or questionnaire answers.
    """
    participant = player.participant
    max_index = participant._max_page_index or 0
    if (
        player.round_number != C.NUM_ROUNDS
        or not participant.visited
        or max_index <= 0
        or participant._index_in_pages < max_index
        or player_was_screened_out(player)
    ):
        return False

    baseline = player.in_round(C.SCREENING_ROUND)
    residence = baseline.field_maybe_none('country_of_residence')
    nationality = baseline.field_maybe_none('nationality')
    baseline_eligible = bool(
        baseline.field_maybe_none('consent_accepted')
        and residence
        and nationality
        and not mentions_colombia(residence)
        and not mentions_colombia(nationality)
        and baseline.field_maybe_none('lived_in_colombia') == 'no'
        and not player_was_screened_out(baseline)
        and profile_is_complete(baseline)
    )
    return baseline_eligible and study_completion_for_player(player)['study_complete']


def study_completion_for_player(player):
    """Read actual submitted rounds, including a documented fail-fast POST."""
    from completion_rules import choice_is_valid, classify_completion
    from quota_monitor_data import _page_layout

    participant = player.participant
    values = raw_participant_vars(participant)
    layout = _page_layout(player.session, {
        'practice_rounds': C.NUM_PRACTICE_ROUNDS,
        'main_rounds': C.NUM_MAIN_ROUNDS, 'total_rounds': C.NUM_ROUNDS,
    })
    index = participant._index_in_pages or 0
    rounds = submitted_task_rounds(index, layout['tasks'], values)
    tasks = player.in_rounds(C.NUM_PRACTICE_ROUNDS + 1, C.NUM_ROUNDS)
    valid = sum(choice_is_valid({
        name: task.field_maybe_none(name)
        for name in ('decision_side', 'decision_candidate_id',
                     'left_candidate_id', 'right_candidate_id')
    }) for task in tasks if task.round_number in rounds)
    baseline = player.in_round(C.SCREENING_ROUND)
    eligible = bool(
        participant.visited
        and participant._max_page_index == layout['max_page_index']
        and baseline.field_maybe_none('consent_accepted')
        and baseline.field_maybe_none('country_of_residence')
        and baseline.field_maybe_none('nationality')
        and not mentions_colombia(baseline.field_maybe_none('country_of_residence'))
        and not mentions_colombia(baseline.field_maybe_none('nationality'))
        and baseline.field_maybe_none('lived_in_colombia') == 'no'
        and not player_was_screened_out(baseline)
        and profile_is_complete(baseline)
    )
    return classify_completion(
        eligible=eligible, reached_final_screen=index >= layout['summary'],
        submitted_main_tasks=len(rounds), valid_main_choices=valid,
        main_task_count=C.NUM_MAIN_ROUNDS,
        navigation_violation=navigation_violation_recorded(values),
        terminated=study_is_terminated(values),
        termination_reason=values.get('study_termination_reason', ''),
    )


VISUAL_DECISION_FACTOR_OPTIONS = (
    ('apariencia_primera_impresion', 'Su apariencia o primera impresión'),
    ('edad', 'La edad que aparentaba'),
    ('genero', 'El género que percibió'),
)

REVEALED_TEXT_DECISION_FACTOR_OPTIONS = (
    (
        'ideologia_revelada',
        'La ideología que vio (izquierda, centro o derecha)',
    ),
    ('focos_programaticos_revelados', 'Los focos temáticos que vio'),
)

OTHER_DECISION_FACTOR_OPTION = ('otra_razon', 'Otra razón')

VISUAL_DECISION_FACTOR_KEYS = {
    value for value, _label in VISUAL_DECISION_FACTOR_OPTIONS
} | {OTHER_DECISION_FACTOR_OPTION[0]}

REVEALED_TEXT_DECISION_FACTOR_KEYS = {
    value for value, _label in REVEALED_TEXT_DECISION_FACTOR_OPTIONS
}


def revealed_candidate_information(player):
    """Whether the participant actually saw either profile's hidden text."""
    return bool(player.left_ideology_opened or player.right_ideology_opened)


def perceived_hurry_is_measured(player):
    """Use the same hurry item in the timed condition and its baseline."""
    return player.treatment_arm in {'timer_mostrar_mas', 'control_ver_mas'}


def candidate_choice_was_registered(player):
    """Whether the participant submitted one of the two displayed profiles."""
    decision_side = player.field_maybe_none('decision_side')
    decision_candidate_id = player.field_maybe_none('decision_candidate_id')
    return (
        decision_side in {'left', 'right'}
        and decision_candidate_id
        in {player.left_candidate_id, player.right_candidate_id}
    )


def selected_decision_factors(raw_value):
    return {
        value.strip()
        for value in (raw_value or '').split(',')
        if value.strip()
    }


def randomized_decision_factor_options(player):
    """Return eligible factors in a stable random order, with "other" last."""
    options = list(VISUAL_DECISION_FACTOR_OPTIONS)
    if revealed_candidate_information(player):
        options.extend(REVEALED_TEXT_DECISION_FACTOR_OPTIONS)

    seed_material = (
        f'{player.participant.code}:{player.round_number}:decision-factors'
    )
    seed = int.from_bytes(
        hashlib.sha256(seed_material.encode('utf-8')).digest()[:16],
        byteorder='big',
    )
    random.Random(seed).shuffle(options)
    options.append(OTHER_DECISION_FACTOR_OPTION)

    return [
        {'value': value, 'label': label}
        for value, label in options
    ]


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
        if not values.get('country_of_residence'):
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
        if not values.get('nationality'):
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


class NavigationPage(Page):
    def _termination_response(self, reason=None):
        from otree.templating import render

        values = raw_participant_vars(self.participant)
        reason = reason or values.get('study_termination_reason') or 'incomplete'
        return render('conjoint/Terminated.html', {
            'study_termination_reason': reason, 'termination_reason': reason,
        })

    def _must_stop(self):
        if self.__class__.__name__ == 'Summary' and player_was_screened_out(self.player):
            return False
        values = raw_participant_vars(self.participant)
        if study_is_terminated(values):
            return True
        if navigation_violation_recorded(values):
            # An older recorded flag remains disqualifying after this update.
            terminate_participant(self.participant, 'navigation_recorded')
            return True
        return False

    def get(self):
        if self._must_stop():
            return self._termination_response()
        if (
            self.__class__.__name__ == 'Summary'
            and not player_was_screened_out(self.player)
            and not study_completion_for_player(self.player)['study_complete']
        ):
            return self._termination_response('insufficient_choices')
        return super().get()

    def _increment_index_in_pages(self):
        if not study_is_terminated(raw_participant_vars(self.participant)):
            return super()._increment_index_in_pages()

    def post(self):
        # The regular form POST is a bounded fallback for an unacknowledged
        # live event. Record it in the same transaction before advancing, so a
        # final follow-up submission cannot outrun its navigation report.
        form_data = self._form_data
        raw_events = form_data.get('_study_navigation_events') if form_data is not None else None
        if isinstance(raw_events, str) and len(raw_events) <= 32768:
            try:
                events = json.loads(raw_events)
            except (TypeError, ValueError):
                events = None
            if isinstance(events, list):
                payload = {'navigation_events': events}
                raw_task = form_data.get('_study_navigation_task')
                if isinstance(raw_task, str) and len(raw_task) <= 8192:
                    try:
                        payload['navigation_task'] = json.loads(raw_task)
                    except (TypeError, ValueError):
                        pass
                record_navigation_events(self.player, payload)
        if self._must_stop():
            return self._termination_response()
        if (
            self.__class__.__name__ == 'Summary'
            and not player_was_screened_out(self.player)
            and not study_completion_for_player(self.player)['study_complete']
        ):
            return self._termination_response('insufficient_choices')
        response = super().post()
        if self._must_stop():
            return self._termination_response()
        return response

    def js_vars(self):
        config = navigation_config(self.player, self.__class__.__name__)
        config['request_method'] = self.request.method
        return {'study_navigation': config}

    @staticmethod
    def live_method(player, data):
        return record_navigation_events(player, data)


class Intro(NavigationPage):
    def is_displayed(self):
        return self.round_number == 1 and player_is_eligible(self.player)

    def vars_for_template(self):
        ensure_participant_vars(self.player)

        treatment_arm = self.participant.vars.get('treatment_arm', '')

        return {
            'is_practice_done_page': False,
            'num_practice_rounds': C.NUM_PRACTICE_ROUNDS,
            'num_main_rounds': C.NUM_MAIN_ROUNDS,
            'countdown_seconds': self.participant.vars['countdown_seconds'],
            'treatment_arm': treatment_arm,
            'is_timer_group': treatment_arm == 'timer_mostrar_mas',
            'is_info_cost_group': treatment_arm == 'captcha_ver_mas',
            'is_control_group': treatment_arm == 'control_ver_mas',
        }

    def before_next_page(self):
        # Reading/reloading the initial instructions itself is not a violation.
        start_navigation_monitoring(self.participant)


class Task(NavigationPage):
    form_model = 'player'

    form_fields = [
        'left_ideology_opened',
        'right_ideology_opened',
        'info_cost_task_completed',
        'info_cost_attempts',
        'decision_candidate_id',
        'decision_side',
        'stimulus_load_seconds',
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
            'countdown_seconds': self.player.countdown_seconds,
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

    def before_next_page(self):
        # The browser uses a temporary sentinel so a timed-out form can be
        # submitted. Store the absence of a choice as a genuine missing value.
        if self.player.field_maybe_none('decision_side') == 'timeout':
            self.player.decision_candidate_id = None
            self.player.decision_side = None
        if self.round_number > C.NUM_PRACTICE_ROUNDS:
            from completion_rules import choice_is_valid, MIN_VALID_MAIN_CHOICES

            tasks = self.player.in_rounds(C.NUM_PRACTICE_ROUNDS + 1, self.round_number)
            missing = sum(not choice_is_valid({
                name: task.field_maybe_none(name)
                for name in ('decision_side', 'decision_candidate_id',
                             'left_candidate_id', 'right_candidate_id')
            }) for task in tasks)
            if missing > C.NUM_MAIN_ROUNDS - MIN_VALID_MAIN_CHOICES:
                terminate_participant(
                    self.participant, 'insufficient_choices',
                    submitted_round=self.round_number,
                )


class PracticeDone(NavigationPage):
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
            'countdown_seconds': self.participant.vars['countdown_seconds'],
            'treatment_arm': treatment_arm,
            'is_timer_group': treatment_arm == 'timer_mostrar_mas',
            'is_info_cost_group': treatment_arm == 'captcha_ver_mas',
            'is_control_group': treatment_arm == 'control_ver_mas',
        }


class FollowUp(NavigationPage):
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
            and candidate_choice_was_registered(self.player)
        )

    def vars_for_template(self):
        information_revealed = revealed_candidate_information(self.player)

        return {
            'main_round_number': self.player.main_round_number,
            'num_main_rounds': C.NUM_MAIN_ROUNDS,
            'timed_task': self.player.timed_task,
            'show_rushed_scale': perceived_hurry_is_measured(self.player),
            'info_condition': self.player.info_condition,
            'information_revealed': information_revealed,
            'decision_factor_options': randomized_decision_factor_options(
                self.player
            ),
            'show_info_cost_scale': (
                self.player.info_condition == 'captcha_ver_mas'
                and information_revealed
            ),
        }

    def error_message(self, values):
        if not values.get('realistic_vote'):
            return (
                'Por favor, indique si habría votado por el/la candidato(a) '
                'que acaba de elegir en una elección real.'
            )

        factors = selected_decision_factors(values.get('decision_factors'))

        if values.get('realistic_vote') == 'yes' and not factors:
            return 'Por favor, seleccione al menos un factor que haya considerado.'

        allowed_factors = set(VISUAL_DECISION_FACTOR_KEYS)
        if revealed_candidate_information(self.player):
            allowed_factors.update(REVEALED_TEXT_DECISION_FACTOR_KEYS)

        if not factors.issubset(allowed_factors):
            return (
                'Una de las alternativas seleccionadas no corresponde a la '
                'información que vio. Por favor, revise su respuesta.'
            )

        if (
            perceived_hurry_is_measured(self.player)
            and values.get('rushed_scale') is None
        ):
            return 'Por favor, indique qué tan apurado se sintió.'

        if (
            self.player.info_condition == 'captcha_ver_mas'
            and revealed_candidate_information(self.player)
            and values.get('info_cost_scale') is None
        ):
            return 'Por favor, indique qué tanto le costó informarse.'

    def before_next_page(self):
        if self.player.realistic_vote != 'yes':
            self.player.decision_factors = ''

        if not revealed_candidate_information(self.player):
            self.player.info_cost_scale = None


class Questionnaire(Page):
    form_model = 'player'
    form_fields = [
        'age_years',
        'gender_identity',
        'gender_identity_other',
        'occupation_status',
        'occupation_status_other',
        'education_level',
        'voted_last_municipal',
        'political_interest',
        'politics_frequency',
        'left_right_self_placement',
    ]

    def is_displayed(self):
        return (
            self.round_number == C.SCREENING_ROUND
            and player_is_eligible(self.player)
        )

    def error_message(self, values):
        if values.get('age_years') is None:
            return 'Por favor, indique su edad.'
        if not values.get('gender_identity'):
            return 'Por favor, indique con qué opción se identifica.'
        if (
            values.get('gender_identity') == 'otra'
            and not (values.get('gender_identity_other') or '').strip()
        ):
            return 'Por favor, describa la opción con la que se identifica.'
        if not values.get('occupation_status'):
            return 'Por favor, indique su situación ocupacional.'
        if (
            values.get('occupation_status') == 'otra'
            and not (values.get('occupation_status_other') or '').strip()
        ):
            return 'Por favor, describa su situación ocupacional.'
        if not values.get('education_level'):
            return 'Por favor, indique su nivel educacional.'
        if not values.get('voted_last_municipal'):
            return 'Por favor, responda la pregunta sobre la elección municipal.'
        if values.get('political_interest') is None:
            return 'Por favor, indique su interés en la política.'
        if not values.get('politics_frequency'):
            return 'Por favor, indique con qué frecuencia sigue la política.'
        if not values.get('left_right_self_placement'):
            return 'Por favor, indique su ubicación política.'

    def before_next_page(self):
        if self.player.gender_identity != 'otra':
            self.player.gender_identity_other = ''
        if self.player.occupation_status != 'otra':
            self.player.occupation_status_other = ''


class Summary(NavigationPage):
    def is_displayed(self):
        return self.round_number == C.NUM_ROUNDS

    def vars_for_template(self):
        return {
            'screened_out': player_was_screened_out(self.player),
            'raffle_registration_url': (
                RAFFLE_REGISTRATION_URL
                if raffle_registration_is_available(self.player)
                else ''
            ),
        }


page_sequence = [
    Consent,
    CountryResidence,
    Nationality,
    LivedInColombia,
    Questionnaire,
    Intro,
    Task,
    PracticeDone,
    FollowUp,
    Summary,
]
