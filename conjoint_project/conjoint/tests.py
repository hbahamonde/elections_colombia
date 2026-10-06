from otree.api import Bot

from . import pages


class PlayerBot(Bot):
    """Exercise the eligible path and every Colombian screening exit."""

    cases = [
        'eligible',
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

            if self.case == 'eligible_timeout':
                self.player.participant.vars['treatment_arm'] = 'timer_mostrar_mas'

            yield pages.Intro

        information_revealed = self.round_number % 2 == 0

        if self.case == 'eligible_timeout' and self.round_number == 6:
            yield pages.Task, dict(
                left_ideology_opened=True,
                right_ideology_opened=True,
                info_cost_task_completed=False,
                info_cost_attempts=0,
                decision_candidate_id='timeout',
                decision_side='timeout',
                time_spent_seconds=10.0,
                time_to_first_choice_seconds=0,
                choice_changes=0,
                learn_more_clicks=2,
                mouse_distance_px=240.0,
                left_hover_seconds=3.1,
                right_hover_seconds=2.4,
                countdown_expired=True,
            )
            return

        yield pages.Task, dict(
            left_ideology_opened=information_revealed,
            right_ideology_opened=False,
            info_cost_task_completed=information_revealed,
            info_cost_attempts=1 if information_revealed else 0,
            decision_candidate_id=self.player.left_candidate_id,
            decision_side='left',
            time_spent_seconds=2.5,
            time_to_first_choice_seconds=1.5,
            choice_changes=0,
            learn_more_clicks=1 if information_revealed else 0,
            mouse_distance_px=120.0,
            left_hover_seconds=1.2,
            right_hover_seconds=0.4,
            countdown_expired=False,
        )

        if self.round_number == 5:
            yield pages.PracticeDone

        if self.round_number > 5:
            follow_up = dict(
                realistic_vote='yes',
                decision_factors=(
                    'ideologia_revelada,focos_programaticos_revelados,'
                    'apariencia_primera_impresion'
                    if information_revealed
                    else 'apariencia_primera_impresion,edad'
                ),
            )
            if self.player.timed_task:
                follow_up['rushed_scale'] = 3
            if (
                self.player.info_condition == 'captcha_ver_mas'
                and information_revealed
            ):
                follow_up['info_cost_scale'] = 2
            yield pages.FollowUp, follow_up
