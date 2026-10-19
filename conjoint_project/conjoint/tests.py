from otree.api import Bot, SubmissionMustFail

from . import pages
from .models import C


class PlayerBot(Bot):
    """Exercise each treatment, its practice tasks, and screening exits."""

    cases = [
        'eligible',
        'eligible_timer',
        'eligible_info_cost',
        'eligible_timeout',
        'residence_colombia',
        'nationality_colombian',
        'lived_colombia',
    ]

    def play_round(self):
        excluded_cases = {
            'residence_colombia',
            'nationality_colombian',
            'lived_colombia',
        }
        if self.case in excluded_cases and self.round_number > 1:
            return

        if self.round_number == 1:
            yield pages.Consent, dict(consent_accepted=True)

            yield pages.CountryResidence, dict(
                country_of_residence=(
                    'CO' if self.case == 'residence_colombia' else 'FI'
                )
            )
            if self.case == 'residence_colombia':
                return

            yield pages.Nationality, dict(
                nationality=(
                    'CO' if self.case == 'nationality_colombian' else 'CL'
                )
            )
            if self.case == 'nationality_colombian':
                return

            yield pages.LivedInColombia, dict(
                lived_in_colombia=(
                    'yes' if self.case == 'lived_colombia' else 'no'
                )
            )
            if self.case == 'lived_colombia':
                return

            assert (
                'Utilizando una escala de 1 a 10, donde 1 representa a la '
                'izquierda y 10 a la derecha, ¿en qué posición se ubica Ud.?'
            ) in self.html
            assert (
                'Utilizando una escala de 1 a 7, donde 1 significa nada '
                'interesado(a) y 7 muy interesado(a), ¿Qué tan interesado '
                'está Ud. en la política?'
            ) in self.html

            yield pages.Questionnaire, dict(
                age_years=35,
                gender_identity='mujer',
                gender_identity_other='',
                occupation_status='tiempo_completo',
                occupation_status_other='',
                education_level='postgrado',
                voted_last_municipal='dont_know',
                political_interest=5,
                politics_frequency='several_times_per_week',
                left_right_self_placement='4',
            )

            treatment_by_case = {
                'eligible': 'control_ver_mas',
                'eligible_timer': 'timer_mostrar_mas',
                'eligible_info_cost': 'captcha_ver_mas',
                'eligible_timeout': 'timer_mostrar_mas',
            }
            self.player.participant.vars['treatment_arm'] = treatment_by_case[
                self.case
            ]

            yield pages.Intro

        information_revealed = self.round_number % 2 == 0
        assert self.player.treatment_arm == self.player.participant.vars[
            'treatment_arm'
        ]
        assert self.player.countdown_seconds == 20
        assert self.player.timed_task == (
            self.player.treatment_arm == 'timer_mostrar_mas'
        )

        if self.case == 'eligible_timeout' and self.round_number in {6, 7, 8}:
            texts_opened = self.round_number - 6
            yield pages.Task, dict(
                left_ideology_opened=texts_opened >= 1,
                right_ideology_opened=texts_opened == 2,
                info_cost_task_completed=False,
                info_cost_attempts=0,
                decision_candidate_id='timeout',
                decision_side='timeout',
                stimulus_load_seconds=1.75,
                time_spent_seconds=C.COUNTDOWN_SECONDS,
                time_to_first_choice_seconds=0,
                choice_changes=0,
                learn_more_clicks=texts_opened,
                mouse_distance_px=240.0,
                left_hover_seconds=3.1,
                right_hover_seconds=2.4,
                countdown_expired=True,
            )
            assert self.player.field_maybe_none('decision_candidate_id') is None
            assert self.player.field_maybe_none('decision_side') is None
            assert self.player.learn_more_clicks == texts_opened
            assert self.player.left_ideology_opened == (texts_opened >= 1)
            assert self.player.right_ideology_opened == (texts_opened == 2)
            assert self.player.time_spent_seconds == C.COUNTDOWN_SECONDS
            assert self.player.countdown_expired
            assert self.player.field_maybe_none('realistic_vote') in (None, '')
            assert self.player.field_maybe_none('decision_factors') in (None, '')
            assert self.player.field_maybe_none('rushed_scale') is None
            assert self.player.field_maybe_none('info_cost_scale') is None
            return

        yield pages.Task, dict(
            left_ideology_opened=information_revealed,
            right_ideology_opened=False,
            info_cost_task_completed=information_revealed,
            info_cost_attempts=1 if information_revealed else 0,
            decision_candidate_id=self.player.left_candidate_id,
            decision_side='left',
            stimulus_load_seconds=0.25,
            time_spent_seconds=2.5,
            time_to_first_choice_seconds=1.5,
            choice_changes=0,
            learn_more_clicks=1 if information_revealed else 0,
            mouse_distance_px=120.0,
            left_hover_seconds=1.2,
            right_hover_seconds=0.4,
            countdown_expired=(
                self.case == 'eligible_timeout' and self.round_number == 9
            ),
        )

        if self.round_number == 5:
            yield pages.PracticeDone

        if self.round_number > 5:
            asks_hurry = self.player.treatment_arm in {
                'timer_mostrar_mas', 'control_ver_mas'
            }
            asks_info_cost = (
                self.player.info_condition == 'captcha_ver_mas'
                and information_revealed
            )
            assert ('name="rushed_scale"' in self.html) == asks_hurry
            assert ('name="info_cost_scale"' in self.html) == asks_info_cost
            assert ('value="ideologia_revelada"' in self.html) == information_revealed
            assert (
                'value="focos_programaticos_revelados"' in self.html
            ) == information_revealed

            realistic_vote = 'no' if self.round_number % 3 == 0 else 'yes'
            follow_up = dict(
                realistic_vote=realistic_vote,
                decision_factors=(
                    'ideologia_revelada,focos_programaticos_revelados,'
                    'apariencia_primera_impresion'
                    if information_revealed
                    else 'apariencia_primera_impresion,edad'
                ),
            )
            if realistic_vote == 'no':
                follow_up['decision_factors'] = ''
            if asks_hurry:
                follow_up['rushed_scale'] = 3
                # Require the same item in both arms, also after a "No" vote.
                without_hurry = {
                    key: value for key, value in follow_up.items()
                    if key != 'rushed_scale'
                }
                yield SubmissionMustFail(
                    pages.FollowUp, without_hurry, error_fields=['__all__']
                )
                assert 'Por favor, indique qué tan apurado se sintió.' in self.html
            if asks_info_cost:
                follow_up['info_cost_scale'] = 2
                without_info_cost = {
                    key: value for key, value in follow_up.items()
                    if key != 'info_cost_scale'
                }
                yield SubmissionMustFail(
                    pages.FollowUp, without_info_cost, error_fields=['__all__']
                )
                assert 'Por favor, indique qué tanto le costó informarse.' in self.html
            if not information_revealed:
                invalid_factor = dict(
                    follow_up,
                    realistic_vote='yes',
                    decision_factors='ideologia_revelada',
                )
                yield SubmissionMustFail(
                    pages.FollowUp, invalid_factor, error_fields=['__all__']
                )
            yield pages.FollowUp, follow_up
            assert self.player.field_maybe_none('rushed_scale') == (
                3 if asks_hurry else None
            )
            assert self.player.field_maybe_none('info_cost_scale') == (
                2 if asks_info_cost else None
            )
            if realistic_vote == 'no':
                assert self.player.field_maybe_none('decision_factors') in (None, '')
