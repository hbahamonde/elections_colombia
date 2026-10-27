"""Record observable reload/history events in existing participant JSON.

The browser reports navigation through oTree's participant-scoped live channel.
No route, table or SQL column is added. Signals are observable browser events,
not a claim that every navigation can be detected. Event logs and counters are
capped at 200 entries so a malformed client cannot grow response storage.
"""

from datetime import datetime, timezone
import json
import math
import re


NAVIGATION_EXPORT_FIELDS = (
    'navigation_monitoring_started',
    'navigation_violation',
    'navigation_reload_count',
    'navigation_history_count',
    'navigation_events',
    'navigation_partial_task',
)
TERMINATION_EXPORT_FIELDS = (
    'study_terminated',
    'study_termination_reason',
    'study_terminated_at_utc',
    'study_termination_page_index',
    'study_termination_submitted_round',
)
PROTECTED_PAGE_NAMES = frozenset({'Intro', 'Task', 'PracticeDone', 'FollowUp'})
MAX_NAVIGATION_EVENTS = 200
MAX_NAVIGATION_BATCH = 20
_EVENT_ID = re.compile(r'^[A-Za-z0-9:_-]{1,128}$')


def raw_participant_vars(participant):
    """Reading .vars itself marks JSON dirty, so exports use the raw dict."""
    values = participant._vars
    return values if isinstance(values, dict) else {}


def navigation_violation_recorded(values):
    """Only a recorded true flag excludes a case; historical nulls do not."""
    return values.get('navigation_violation') is True


def study_is_terminated(values):
    return values.get('study_terminated') is True


def termination_values(values, reason, page_index, *, submitted_round=None, now=None):
    """Preserve the first stop and every response; never move the page index."""
    result = dict(values)
    if not study_is_terminated(result):
        result.update({
            'study_terminated': True,
            'study_termination_reason': reason,
            'study_terminated_at_utc': (now or datetime.now(timezone.utc)).isoformat(timespec='milliseconds'),
            'study_termination_page_index': page_index,
        })
        if submitted_round is not None:
            result['study_termination_submitted_round'] = submitted_round
    return result


def terminate_participant(participant, reason, *, submitted_round=None):
    values = raw_participant_vars(participant)
    updated = termination_values(values, reason, participant._index_in_pages,
                                 submitted_round=submitted_round)
    if updated != values:
        participant.vars.update(updated)


def submitted_task_rounds(index, task_indices, values):
    """Include a stopped Task only when its actual POST was recorded.

    Usually submission is inferred from advancing past Task. A fail-fast stop
    preserves the current URL, so the third missing submission is explicitly
    documented rather than treating unvisited later tasks as submitted.
    """
    submitted = {round_number for round_number, page_index in task_indices.items()
                 if index > page_index}
    stopped_round = values.get('study_termination_submitted_round')
    if (
        study_is_terminated(values)
        and isinstance(stopped_round, int) and not isinstance(stopped_round, bool)
        and task_indices.get(stopped_round) == values.get('study_termination_page_index') == index
    ):
        submitted.add(stopped_round)
    return submitted


def start_navigation_monitoring(participant):
    if raw_participant_vars(participant).get('navigation_monitoring_started') is True:
        return
    values = participant.vars
    values['navigation_monitoring_started'] = True
    values.setdefault('navigation_violation', False)
    values.setdefault('navigation_reload_count', 0)
    values.setdefault('navigation_history_count', 0)
    values.setdefault('navigation_events', '[]')
    values.setdefault('study_terminated', False)


def navigation_config(player, page_name):
    participant = player.participant
    if page_name in {'Task', 'PracticeDone', 'FollowUp'}:
        # Also covers a participant entering an already-open task after deploy.
        start_navigation_monitoring(participant)
    values = raw_participant_vars(participant)
    return {
        'participant_code': participant.code,
        'page_index': participant._index_in_pages,
        'page_name': page_name,
        'round_number': player.round_number,
        'enabled': values.get('navigation_monitoring_started') is True,
        'final_screen': page_name == 'Summary',
        'violation': navigation_violation_recorded(values),
        'study_terminated': study_is_terminated(values),
    }


def merge_navigation_events(values, events, *, current_page_index,
                            max_page_index, lookup_page, now=None):
    """Pure merge for validation/tests. lookup_page returns name and round.

    A final-screen event is acknowledged without flagging it. Queued events
    from earlier protected pages remain valid on arrival at the final screen.
    Re-delivering the same event ID is idempotent.
    """
    result = dict(values)
    if not isinstance(events, list):
        return result, []
    try:
        stored = json.loads(result.get('navigation_events') or '[]')
    except (TypeError, ValueError):
        stored = []
    if not isinstance(stored, list):
        stored = []
    stored = [item for item in stored if isinstance(item, dict)][:MAX_NAVIGATION_EVENTS]
    seen = {item.get('id') for item in stored}
    acknowledgements = []
    timestamp = (now or datetime.now(timezone.utc)).isoformat(timespec='milliseconds')
    started = result.get('navigation_monitoring_started') is True
    for event in events[:MAX_NAVIGATION_BATCH]:
        if not isinstance(event, dict):
            continue
        event_id = event.get('id')
        event_type = event.get('type')
        page_index = event.get('page_index')
        if (
            not isinstance(event_id, str) or not _EVENT_ID.fullmatch(event_id)
            or event_type not in {'reload', 'history'}
            or isinstance(page_index, bool) or not isinstance(page_index, int)
            or not 1 <= page_index <= min(current_page_index, max_page_index)
        ):
            continue
        try:
            page_name, round_number = lookup_page(page_index)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if page_name == 'Summary':
            acknowledgements.append(event_id)
            continue
        if not started or page_name not in PROTECTED_PAGE_NAMES:
            continue
        acknowledgements.append(event_id)
        if event_id in seen or len(stored) >= MAX_NAVIGATION_EVENTS:
            continue
        seen.add(event_id)
        stored.append({
            'id': event_id, 'type': event_type,
            'server_utc': timestamp, 'page_index': page_index,
            'page_name': page_name, 'round_number': round_number,
        })
        result['navigation_violation'] = True
        result = termination_values(
            result, f'navigation_{event_type}', current_page_index, now=now,
        )
    if stored:
        result['navigation_events'] = json.dumps(stored, ensure_ascii=True, separators=(',', ':'))
        result['navigation_reload_count'] = sum(item.get('type') == 'reload' for item in stored)
        result['navigation_history_count'] = sum(item.get('type') == 'history' for item in stored)
    return result, acknowledgements


def record_navigation_events(player, payload):
    from otree.lookup import get_page_lookup

    participant = player.participant
    original = raw_participant_vars(participant)

    def lookup_page(index):
        lookup = get_page_lookup(participant._session_code, index)
        if lookup.app_name != 'conjoint':
            raise ValueError('Navigation is outside this experiment.')
        return lookup.page_class.__name__, lookup.round_number

    updated, acknowledgements = merge_navigation_events(
        original,
        payload.get('navigation_events') if isinstance(payload, dict) else None,
        current_page_index=participant._index_in_pages or 0,
        max_page_index=participant._max_page_index or 0,
        lookup_page=lookup_page,
    )
    if (
        isinstance(payload, dict) and navigation_violation_recorded(updated)
        and 'navigation_partial_task' not in updated
    ):
        partial = bounded_partial_task(player, payload.get('navigation_task'), lookup_page)
        if partial is not None:
            updated['navigation_partial_task'] = json.dumps(partial, separators=(',', ':'))
    if updated != original:
        participant.vars.update(updated)
    reply = {
        'navigation_ack': acknowledgements,
        'navigation_violation': navigation_violation_recorded(updated),
        'study_terminated': study_is_terminated(updated),
    }
    if reply['study_terminated']:
        reply['termination_url'] = participant._url_i_should_be_on()
    return {player.id_in_group: reply}


def bounded_partial_task(player, snapshot, lookup_page):
    """Keep actual interrupted-task telemetry separate from submitted answers."""
    if not isinstance(snapshot, dict):
        return None
    page_index = snapshot.get('page_index')
    if (
        isinstance(page_index, bool) or not isinstance(page_index, int)
        or page_index != player.participant._index_in_pages
    ):
        return None
    try:
        page_name, round_number = lookup_page(page_index)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if page_name != 'Task' or round_number != player.round_number:
        return None
    fields = snapshot.get('fields')
    if not isinstance(fields, dict):
        return None
    cleaned = {}
    for name in ('left_ideology_opened', 'right_ideology_opened',
                 'info_cost_task_completed', 'countdown_expired'):
        value = fields.get(name)
        if isinstance(value, bool):
            cleaned[name] = value
        elif isinstance(value, str) and value.lower() in {'true', 'false', '0', '1'}:
            cleaned[name] = value.lower() in {'true', '1'}
    for name in ('info_cost_attempts', 'choice_changes', 'learn_more_clicks'):
        value = fields.get(name)
        try:
            number = int(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if not isinstance(value, bool) and 0 <= number <= 1000000:
            cleaned[name] = number
    for name in ('stimulus_load_seconds', 'time_spent_seconds',
                 'time_to_first_choice_seconds', 'mouse_distance_px',
                 'left_hover_seconds', 'right_hover_seconds'):
        value = fields.get(name)
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if not isinstance(value, bool) and math.isfinite(number) and 0 <= number <= 1000000000:
            cleaned[name] = number
    side = fields.get('decision_side')
    candidate = fields.get('decision_candidate_id')
    if side in {'left', 'right'} and candidate == player.field_maybe_none(f'{side}_candidate_id'):
        cleaned['decision_side'] = side
        cleaned['decision_candidate_id'] = candidate
    if not cleaned:
        return None
    return {
        'page_index': page_index, 'round_number': round_number,
        'server_utc': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
        'submitted': False, 'fields': cleaned,
    }
