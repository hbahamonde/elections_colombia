from otree.api import Bot

from . import pages


class PlayerBot(Bot):
    """Exercise the complete eligible-participant path in all 20 rounds."""

    def play_round(self):
        if self.round_number == 1:
            yield pages.Consent, dict(consent_accepted=True)
            yield pages.CountryResidence, dict(country_of_residence='FI')
            yield pages.Nationality, dict(nationality='CL')
            yield pages.LivedInColombia, dict(lived_in_colombia='no')
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
            yield pages.Intro

        yield pages.Task, dict(
            left_ideology_opened=True,
            right_ideology_opened=False,
            info_cost_task_completed=True,
            info_cost_attempts=1,
            decision_candidate_id=self.player.left_candidate_id,
            decision_side='left',
            time_spent_seconds=2.5,
            time_to_first_choice_seconds=1.5,
            choice_changes=0,
            learn_more_clicks=1,
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
                decision_factors='apariencia; información programática',
            )
            if self.player.timed_task:
                follow_up['rushed_scale'] = 3
            if self.player.info_condition == 'captcha_ver_mas':
                follow_up['info_cost_scale'] = 2
            yield pages.FollowUp, follow_up
