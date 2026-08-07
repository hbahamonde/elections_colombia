from os import environ


IS_PRODUCTION = environ.get('OTREE_PRODUCTION') == '1'

SESSION_CONFIGS = [
    dict(
        name='conjoint_random',
        display_name='Conjoint experiment - RANDOM assignment',
        app_sequence=['conjoint'],
        num_demo_participants=1,
    ),

    dict(
        name='conjoint_demo_timer',
        display_name='Conjoint DEMO - Grupo presión del tiempo',
        app_sequence=['conjoint'],
        num_demo_participants=1,
        demo_treatment_arm='timer_mostrar_mas',
    ),

    dict(
        name='conjoint_demo_math',
        display_name='Conjoint DEMO - Grupo costo información',
        app_sequence=['conjoint'],
        num_demo_participants=1,
        demo_treatment_arm='captcha_ver_mas',
    ),

    dict(
        name='conjoint_demo_control',
        display_name='Conjoint DEMO - Grupo control',
        app_sequence=['conjoint'],
        num_demo_participants=1,
        demo_treatment_arm='control_ver_mas',
    ),
]

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.00,
    participation_fee=0.00,
    doc="",
)

PARTICIPANT_FIELDS = []
SESSION_FIELDS = []

LANGUAGE_CODE = 'en'
REAL_WORLD_CURRENCY_CODE = 'USD'
USE_POINTS = False

ADMIN_USERNAME = environ.get('OTREE_ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

DEMO_PAGE_INTRO_HTML = """ """

SECRET_KEY = environ.get('OTREE_SECRET_KEY', 'local-development-only')

if IS_PRODUCTION and not ADMIN_PASSWORD:
    raise RuntimeError('OTREE_ADMIN_PASSWORD must be set in production.')

if IS_PRODUCTION and SECRET_KEY == 'local-development-only':
    raise RuntimeError('OTREE_SECRET_KEY must be set in production.')
