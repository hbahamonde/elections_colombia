"""Read-only, aggregate recruitment statistics for the selected oTree session.

The caller owns the database transaction. In particular, it must disable
autoflush and roll back/close its read transaction. This module never commits,
initializes a participant, changes a session, or exposes participant records.
Imports of oTree are deliberately deferred so pure tests never open a database.
"""

from collections import Counter
from datetime import datetime, timezone
import os
import re
import unicodedata


class MonitorConfigurationError(ValueError):
    """A selected session cannot be interpreted using the current study."""


SUMMARY_KEYS = (
    'assigned', 'not_started', 'started', 'screening_pending', 'screened_out',
    'screening_passed', 'baseline_pending', 'eligible_baseline_complete',
    'eligible_in_progress', 'eligible_completed', 'all_main_tasks_submitted',
    'main_tasks_submitted', 'main_tasks_with_selection', 'main_tasks_no_selection',
    'deadline_expiries', 'participants_with_timeouts',
)

TREATMENT_LABELS = {
    'timer_mostrar_mas': 'Tiempo limitado',
    'captcha_ver_mas': 'Costo de información',
    'control_ver_mas': 'Sin restricciones',
}


def _boolean(value):
    """Parse configuration booleans without treating the string 'false' as true."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'true', '1', 'yes'}:
            return True
        if normalized in {'false', '0', 'no', ''}:
            return False
    if value is None:
        return False
    raise MonitorConfigurationError('La configuración del modo no es válida.')


def _metadata():
    from conjoint import models
    from conjoint.countries import COUNTRY_CHOICES

    return {
        'practice_rounds': models.C.NUM_PRACTICE_ROUNDS,
        'main_rounds': models.C.NUM_MAIN_ROUNDS,
        'total_rounds': models.C.NUM_ROUNDS,
        'treatments': list(models.C.TREATMENT_ARMS),
        'exclusion_labels': dict(models.SCREENING_EXCLUSION_LABELS),
        'dimensions': [
            {'key': 'age_band', 'label': 'Edad',
             'choices': list(models.AGE_BAND_CHOICES)},
            {'key': 'gender_identity', 'label': 'Género',
             'choices': list(models.GENDER_CHOICES)},
            {'key': 'country_of_residence', 'label': 'País de residencia',
             'choices': list(COUNTRY_CHOICES), 'compact': True},
            {'key': 'nationality', 'label': 'Nacionalidad',
             'choices': list(COUNTRY_CHOICES), 'compact': True},
            {'key': 'education_level', 'label': 'Educación',
             'choices': list(models.EDUCATION_CHOICES)},
            {'key': 'occupation_status', 'label': 'Ocupación',
             'choices': list(models.OCCUPATION_CHOICES)},
        ],
    }


def _selected_session():
    """Select exactly one server-configured session, never enumerate sessions."""
    from otree.models import Session
    from otree.room import ROOM_DICT

    session_code = os.environ.get('MONITOR_SESSION_CODE', '').strip()
    if session_code:
        if len(session_code) > 64 or not session_code.isalnum():
            raise MonitorConfigurationError('La sesión del visor no está configurada correctamente.')
        return Session.objects_filter(code=session_code).first()
    room_name = os.environ.get('MONITOR_ROOM', 'colombia_study').strip()
    room = ROOM_DICT.get(room_name)
    if room is None:
        raise MonitorConfigurationError('La sala del visor no está configurada correctamente.')
    return room.get_session()


def _page_layout(session, metadata):
    """Derive global indexes from the complete app/page sequence, not UI labels."""
    from otree.common import get_constants, get_pages_module

    app_sequence = session.config.get('app_sequence', [])
    if not isinstance(app_sequence, (list, tuple)) or app_sequence.count('conjoint') != 1:
        raise MonitorConfigurationError('La sesión activa no corresponde a este estudio.')
    index = 1
    questionnaire = None
    summary = None
    task_indices = {}
    for app_name in app_sequence:
        constants = get_constants(app_name)
        num_rounds = constants.get_normalized('num_rounds')
        pages = get_pages_module(app_name).page_sequence
        for round_number in range(1, num_rounds + 1):
            for page in pages:
                if app_name == 'conjoint':
                    if page.__name__ == 'Questionnaire' and round_number == 1:
                        questionnaire = index
                    if page.__name__ == 'Task' and round_number > metadata['practice_rounds']:
                        task_indices[round_number] = index
                    if page.__name__ == 'Summary' and round_number == metadata['total_rounds']:
                        summary = index
                index += 1
    if (
        questionnaire is None or summary is None
        or len(task_indices) != metadata['main_rounds']
    ):
        raise MonitorConfigurationError('La secuencia de la sesión no coincide con este estudio.')
    return {
        'questionnaire': questionnaire,
        'summary': summary,
        'tasks': task_indices,
        'max_page_index': index - 1,
    }


def _load_records(session, metadata):
    """Project only fields needed for recruitment; never load political responses."""
    from otree.models import Participant
    from conjoint.models import Player

    participant_names = (
        'id', 'visited', '_index_in_pages', '_max_page_index', '_vars',
        '_is_bot', 'is_browser_bot',
    )
    participants = [
        dict(zip(participant_names, row))
        for row in Participant.objects_filter(session=session).with_entities(
            *(getattr(Participant, name) for name in participant_names)
        )
    ]
    baseline_names = (
        'participant_id', 'consent_accepted', 'country_of_residence', 'nationality',
        'lived_in_colombia', 'screening_excluded', 'screening_exclusion_reason',
        'age_years', 'gender_identity', 'education_level', 'occupation_status',
        'treatment_arm',
    )
    baselines = {
        row[0]: dict(zip(baseline_names, row))
        for row in Player.objects_filter(session=session, round_number=1).with_entities(
            *(getattr(Player, name) for name in baseline_names)
        )
    }
    task_names = (
        'participant_id', 'round_number', 'countdown_expired', 'decision_side',
        'decision_candidate_id', 'left_candidate_id', 'right_candidate_id',
    )
    task_rows = [
        dict(zip(task_names, row))
        for row in Player.objects_filter(session=session).filter(
            Player.round_number > metadata['practice_rounds']
        ).with_entities(*(getattr(Player, name) for name in task_names))
    ]
    return participants, baselines, task_rows


def _present(value):
    return value is not None and value != ''


def _is_colombia(value):
    text = unicodedata.normalize('NFKD', str(value or '').strip().casefold())
    text = ''.join(character for character in text if not unicodedata.combining(character))
    return text == 'co' or re.search(r'\bcolomb', text) is not None


def _exclusion_reason(baseline, participant_vars):
    reason = baseline.get('screening_exclusion_reason') or participant_vars.get(
        'screening_exclusion_reason'
    )
    if reason:
        return reason
    if _is_colombia(baseline.get('country_of_residence')):
        return 'residence_colombia'
    if _is_colombia(baseline.get('nationality')):
        return 'nationality_colombian'
    reason = {
        'yes': 'lived_colombia', 'currently': 'currently_in_colombia',
        'prefer_not_to_answer': 'lived_prefer_not_to_answer',
    }.get(baseline.get('lived_in_colombia'))
    if reason:
        return reason
    if _boolean(baseline.get('screening_excluded')) or _boolean(
        participant_vars.get('screening_excluded')
    ):
        return 'other'
    return None


def _screening_passed(baseline, reason):
    return (
        reason is None
        and _boolean(baseline.get('consent_accepted'))
        and _present(baseline.get('country_of_residence'))
        and _present(baseline.get('nationality'))
        and baseline.get('lived_in_colombia') == 'no'
    )


def _age_band(value):
    if isinstance(value, bool):
        return None
    try:
        age = int(value)
    except (TypeError, ValueError):
        return None
    if age != value or not 18 <= age <= 65:
        return None
    if age <= 29:
        return '18_29'
    if age <= 44:
        return '30_44'
    if age <= 59:
        return '45_59'
    return '60_plus'


def _target(targets, dimension, category):
    dimension_targets = targets.get(dimension, {})
    if not isinstance(dimension_targets, dict):
        return None
    target = dimension_targets.get(category)
    if isinstance(target, int) and not isinstance(target, bool) and target > 0:
        return target
    return None


def _progress(completed, in_progress, target):
    return {
        'completed': completed,
        'in_progress': in_progress,
        'target': target,
        'remaining': max(0, target - completed) if target else None,
        'is_full': bool(target and completed >= target),
        'progress_percent': round(100 * completed / target, 1) if target else None,
    }


def _quota_dimensions(completed, in_progress, metadata, targets):
    dimensions = []
    for dimension in metadata['dimensions']:
        key = dimension['key']
        labels = dict(dimension['choices'])

        def category(baseline):
            value = _age_band(baseline.get('age_years')) if key == 'age_band' else baseline.get(key)
            if not _present(value):
                return None
            return value if value in labels else 'unknown'

        completed_counts = Counter(category(record) for record in completed)
        progress_counts = Counter(category(record) for record in in_progress)
        rows = []
        for category_key, label in dimension['choices']:
            count = completed_counts[category_key]
            pending = progress_counts[category_key]
            target = _target(targets, key, category_key)
            if dimension.get('compact') and not (count or pending or target):
                continue
            rows.append({
                'key': category_key, 'label': label,
                **_progress(count, pending, target),
            })
        if completed_counts['unknown'] or progress_counts['unknown']:
            rows.append({
                'key': 'unknown', 'label': 'Sin categoría reconocida',
                **_progress(completed_counts['unknown'], progress_counts['unknown'], None),
            })
        dimensions.append({
            'key': key, 'label': dimension['label'],
            'completed_total': len(completed), 'in_progress_total': len(in_progress),
            'missing_completed': completed_counts[None],
            'missing_in_progress': progress_counts[None],
            'rows': rows,
        })
    return dimensions


def _age_gender(completed, in_progress, metadata, targets):
    definitions = {dimension['key']: dimension for dimension in metadata['dimensions']}
    genders = definitions['gender_identity']['choices']

    def counts(records):
        return Counter(
            (_age_band(record.get('age_years')), record.get('gender_identity'))
            for record in records
        )

    completed_counts = counts(completed)
    progress_counts = counts(in_progress)
    rows = []
    for age_key, age_label in definitions['age_band']['choices']:
        cells = []
        for gender_key, _gender_label in genders:
            cells.append({
                'gender_key': gender_key,
                **_progress(
                    completed_counts[(age_key, gender_key)],
                    progress_counts[(age_key, gender_key)],
                    _target(targets, 'age_gender', f'{age_key}__{gender_key}'),
                ),
            })
        rows.append({'key': age_key, 'label': age_label, 'cells': cells})
    known_ages = set(dict(definitions['age_band']['choices']))
    known_genders = set(dict(genders))

    def unmatched(counter):
        return sum(count for (age, gender), count in counter.items()
                   if age not in known_ages or gender not in known_genders)

    return {
        'columns': [{'key': key, 'label': label} for key, label in genders],
        'rows': rows,
        'missing_completed': unmatched(completed_counts),
        'missing_in_progress': unmatched(progress_counts),
    }


def _empty_snapshot(mode, metadata, status, message):
    return {
        'status': status, 'message': message, 'mode': mode,
        'updated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'main_task_count': metadata['main_rounds'],
        'summary': {key: 0 for key in SUMMARY_KEYS},
        'treatments': [
            {'key': key, 'label': TREATMENT_LABELS.get(key, 'Otra condición'),
             'eligible_baseline_complete': 0, 'in_progress': 0, 'completed': 0}
            for key in metadata['treatments']
        ],
        'quota_dimensions': _quota_dimensions([], [], metadata, {}),
        'age_gender': _age_gender([], [], metadata, {}),
        'exclusions': [
            {'key': key, 'label': label, 'count': 0}
            for key, label in metadata['exclusion_labels'].items()
        ],
        'targets_configured': False,
    }


def _aggregate_records(mode, metadata, layout, participants, baselines, task_rows, targets):
    """Aggregate primitives; used unchanged by the ORM reader and pure tests."""
    snapshot = _empty_snapshot(mode, metadata, 'ready', '')
    summary = snapshot['summary']
    completed = []
    in_progress = []
    treatment_counts = {key: Counter() for key in metadata['treatments']}
    exclusion_counts = Counter()
    tasks_by_participant = {}
    for row in task_rows:
        tasks_by_participant.setdefault(row['participant_id'], {})[row['round_number']] = row

    for participant in participants:
        # Official recruitment cannot be increased by browser/command-line bots.
        if mode == 'official' and (
            _boolean(participant.get('_is_bot')) or _boolean(participant.get('is_browser_bot'))
        ):
            continue
        participant_id = participant['id']
        baseline = baselines.get(participant_id, {})
        participant_vars = participant.get('_vars') or {}
        if not isinstance(participant_vars, dict):
            participant_vars = {}
        index = participant.get('_index_in_pages') or 0
        if participant.get('_max_page_index') != layout['max_page_index']:
            raise MonitorConfigurationError('La secuencia de la sesión no coincide con este estudio.')
        summary['assigned'] += 1
        if not _boolean(participant.get('visited')):
            summary['not_started'] += 1
            continue
        summary['started'] += 1
        reason = _exclusion_reason(baseline, participant_vars)
        if reason:
            summary['screened_out'] += 1
            exclusion_counts[reason if reason in metadata['exclusion_labels'] else 'other'] += 1
            continue
        if not _screening_passed(baseline, reason):
            summary['screening_pending'] += 1
            continue
        summary['screening_passed'] += 1
        baseline_complete = index > layout['questionnaire'] and all(
            _present(baseline.get(key))
            for key in ('age_years', 'gender_identity', 'education_level', 'occupation_status')
        )
        if not baseline_complete:
            summary['baseline_pending'] += 1
            continue
        summary['eligible_baseline_complete'] += 1
        is_complete = index >= layout['summary']
        cohort = 'completed' if is_complete else 'in_progress'
        (completed if is_complete else in_progress).append(baseline)
        summary['eligible_completed' if is_complete else 'eligible_in_progress'] += 1
        treatment = participant_vars.get('treatment_arm') or baseline.get('treatment_arm')
        if treatment in treatment_counts:
            treatment_counts[treatment]['eligible_baseline_complete'] += 1
            treatment_counts[treatment][cohort] += 1
        else:
            treatment_counts.setdefault('unknown', Counter())['eligible_baseline_complete'] += 1
            treatment_counts['unknown'][cohort] += 1
        submitted_rounds = [round_number for round_number, task_index in layout['tasks'].items()
                            if index > task_index]
        summary['all_main_tasks_submitted'] += len(submitted_rounds) == metadata['main_rounds']
        participant_had_timeout = False
        for round_number in submitted_rounds:
            summary['main_tasks_submitted'] += 1
            task = tasks_by_participant.get(participant_id, {}).get(round_number, {})
            chosen = (
                task.get('decision_side') in {'left', 'right'}
                and _present(task.get('decision_candidate_id'))
                and task.get('decision_candidate_id') in {
                    task.get('left_candidate_id'), task.get('right_candidate_id')
                }
            )
            summary['main_tasks_with_selection' if chosen else 'main_tasks_no_selection'] += 1
            expired = _boolean(task.get('countdown_expired'))
            summary['deadline_expiries'] += expired
            participant_had_timeout = participant_had_timeout or (expired and not chosen)
        summary['participants_with_timeouts'] += participant_had_timeout

    snapshot['treatments'] = [
        {'key': key, 'label': TREATMENT_LABELS.get(key, 'Sin condición reconocida'),
         'eligible_baseline_complete': counts['eligible_baseline_complete'],
         'in_progress': counts['in_progress'], 'completed': counts['completed']}
        for key, counts in treatment_counts.items()
    ]
    snapshot['quota_dimensions'] = _quota_dimensions(completed, in_progress, metadata, targets)
    snapshot['age_gender'] = _age_gender(completed, in_progress, metadata, targets)
    snapshot['targets_configured'] = any(
        row['target'] is not None
        for dimension in snapshot['quota_dimensions'] for row in dimension['rows']
    ) or any(cell['target'] is not None for row in snapshot['age_gender']['rows'] for cell in row['cells'])
    for row in snapshot['exclusions']:
        row['count'] = exclusion_counts[row['key']]
    if exclusion_counts['other']:
        snapshot['exclusions'].append({'key': 'other', 'label': 'Otro filtro de elegibilidad',
                                       'count': exclusion_counts['other']})
    return snapshot


def build_monitor_snapshot():
    """Return JSON-safe aggregates for the single session selected by the server."""
    metadata = _metadata()
    mode = os.environ.get('MONITOR_MODE', 'official').strip().lower()
    if mode not in {'official', 'testing'}:
        return _empty_snapshot('official', metadata, 'configuration_error',
                               'El modo del visor debe ser oficial o de pruebas.')
    try:
        session = _selected_session()
        if session is None:
            return _empty_snapshot(mode, metadata, 'no_active_session',
                                   'No hay una sesión activa seleccionada para este visor.')
        config = session.config or {}
        is_official = _boolean(config.get('official_data_collection', False))
        if is_official != (mode == 'official') or (
            mode == 'official' and (
                _boolean(getattr(session, 'is_demo', False))
                or _boolean(config.get('use_browser_bots', False))
            )
        ):
            return _empty_snapshot(mode, metadata, 'mode_mismatch',
                                   'La sesión seleccionada no corresponde al modo de este visor.')
        layout = _page_layout(session, metadata)
        participants, baselines, task_rows = _load_records(session, metadata)
        targets = config.get('quota_targets', {}) or {}
        if not isinstance(targets, dict):
            raise MonitorConfigurationError('Los objetivos de cuota no están configurados correctamente.')
        return _aggregate_records(mode, metadata, layout, participants, baselines, task_rows, targets)
    except MonitorConfigurationError as error:
        return _empty_snapshot(mode, metadata, 'configuration_error', str(error))
