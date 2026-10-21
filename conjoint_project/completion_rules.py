"""Shared, read-only completion rules for recruitment and researcher exports.

Finishing the questionnaire and meeting the analytical completion threshold are
separate events. A completed study requires all 15 main tasks to be submitted
and at least 13 valid candidate choices. Practice responses and intentionally
inapplicable follow-up questions do not enter this rule.
"""

MIN_VALID_MAIN_CHOICES = 13


def choice_is_valid(task):
    """Require the recorded candidate ID to match its recorded left/right side."""
    side = task.get('decision_side')
    if side not in {'left', 'right'}:
        return False
    chosen = task.get('decision_candidate_id')
    displayed = task.get(f'{side}_candidate_id')
    return bool(chosen is not None and chosen != '' and chosen == displayed)


def classify_completion(*, eligible, reached_final_screen, submitted_main_tasks,
                        valid_main_choices, main_task_count=15):
    """Return a reproducible status without changing any stored response.

    An expired timer with a previously registered valid choice still counts as
    a choice. Up to two submitted main tasks may have no valid choice. Reaching
    the last screen alone is not sufficient, and no-choice tasks remain missing
    responses rather than being imputed or replaced by a candidate.
    """
    counts = (submitted_main_tasks, valid_main_choices, main_task_count)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in counts):
        raise ValueError('Completion counts must be integers.')
    if not 0 <= valid_main_choices <= submitted_main_tasks <= main_task_count:
        raise ValueError('Completion counts are inconsistent.')
    if main_task_count < MIN_VALID_MAIN_CHOICES:
        raise ValueError('The study has fewer tasks than its completion threshold.')

    final_screen_completion = bool(eligible and reached_final_screen)
    complete = bool(
        final_screen_completion
        and submitted_main_tasks == main_task_count
        and valid_main_choices >= MIN_VALID_MAIN_CHOICES
    )
    if not eligible:
        status = 'ineligible'
    elif complete:
        status = 'complete'
    elif reached_final_screen:
        status = 'finished_insufficient_choices'
    else:
        status = 'in_progress'
    return {
        'eligible_final_screen_completion': final_screen_completion,
        'study_complete': complete,
        'main_tasks_submitted': submitted_main_tasks,
        'main_tasks_with_selection': valid_main_choices,
        'main_tasks_missing_selection': submitted_main_tasks - valid_main_choices,
        'minimum_valid_main_choices': MIN_VALID_MAIN_CHOICES,
        'completion_status': status,
    }
