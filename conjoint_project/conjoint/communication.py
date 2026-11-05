"""Procedural explanations, without new database columns or completion rules."""

NOTICE_VERSION = '2026-11-05'
PROCEDURE_EXPORT_FIELDS = (
    'procedure_notice_version',
    'procedure_notice_acknowledged_at_utc',
    'timing_understanding_before_practice_at_utc',
    'timing_understanding_after_practice_at_utc',
)
TIMING_CHECK_ANSWERS = {
    'timing_check_deadline': 'assigned_limit',
    'timing_check_expiry': 'advance_without_choice',
    'timing_check_completion': 'third_missing_ends',
}


def timing_understanding_error(answers, seconds):
    """Explain errors and allow unlimited retries; never reject a participant."""
    if any(answers.get(name) != expected
           for name, expected in TIMING_CHECK_ANSWERS.items()):
        return (
            f'Repasemos las instrucciones: dispone de {seconds} segundos por decisión. '
            'Al terminar el tiempo se guarda su última selección; si no seleccionó '
            'una opción, la plataforma avanza sin registrar una elección. Una tercera '
            'decisión principal sin elección finaliza su participación e impide '
            'acceder al formulario de inscripción al sorteo. Las omisiones de '
            'práctica no cuentan. Puede revisar sus respuestas e intentarlo de nuevo; '
            'equivocarse aquí no lo descalifica.'
        )


TERMINATION_MESSAGES = {
    'insufficient_choices': (
        'Se registraron tres decisiones principales sin una elección de candidato(a). '
        'Según la regla explicada antes de comenzar, se requieren al menos 13 '
        'elecciones de las 15 decisiones principales. Por ese motivo, su '
        'participación finalizó antes de completar el estudio. El límite de '
        'tiempo corresponde a cada decisión, no al tiempo total de la encuesta.'
    ),
    'navigation_reload': (
        'La plataforma detectó una actualización o recarga de la página después '
        'de iniciar la práctica. Según la regla explicada antes de comenzar, '
        'esa acción finaliza la participación para preservar las condiciones '
        'del estudio. Esta finalización no se debe a su elección de candidato(a).'
    ),
    'navigation_history': (
        'La plataforma detectó el uso de la navegación Atrás o Adelante del '
        'navegador después de iniciar la práctica. Según la regla explicada '
        'antes de comenzar, esa acción finaliza la participación para preservar '
        'las condiciones del estudio. Esta finalización no se debe a su '
        'elección de candidato(a).'
    ),
    'navigation_recorded': (
        'La plataforma registró una recarga o el uso de la navegación del '
        'navegador después de iniciar la práctica. Según la regla explicada '
        'antes de comenzar, esa acción impide continuar con el estudio.'
    ),
}
