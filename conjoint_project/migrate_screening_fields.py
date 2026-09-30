"""Add project fields without deleting existing oTree data."""

import sqlite3
from os import environ
from pathlib import Path

import psycopg2


POSTGRES_COLUMNS_SQL = """
ALTER TABLE conjoint_player
    ADD COLUMN IF NOT EXISTS country_of_residence VARCHAR,
    ADD COLUMN IF NOT EXISTS nationality VARCHAR,
    ADD COLUMN IF NOT EXISTS lived_in_colombia VARCHAR,
    ADD COLUMN IF NOT EXISTS screening_excluded BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS screening_exclusion_reason VARCHAR,
    ADD COLUMN IF NOT EXISTS left_ideology_text TEXT,
    ADD COLUMN IF NOT EXISTS right_ideology_text TEXT,
    ADD COLUMN IF NOT EXISTS left_codigo VARCHAR,
    ADD COLUMN IF NOT EXISTS left_ideologia VARCHAR,
    ADD COLUMN IF NOT EXISTS left_sexo VARCHAR,
    ADD COLUMN IF NOT EXISTS left_dominancia VARCHAR,
    ADD COLUMN IF NOT EXISTS left_edad_categoria VARCHAR,
    ADD COLUMN IF NOT EXISTS left_nombre_base_final VARCHAR,
    ADD COLUMN IF NOT EXISTS left_texto TEXT,
    ADD COLUMN IF NOT EXISTS right_codigo VARCHAR,
    ADD COLUMN IF NOT EXISTS right_ideologia VARCHAR,
    ADD COLUMN IF NOT EXISTS right_sexo VARCHAR,
    ADD COLUMN IF NOT EXISTS right_dominancia VARCHAR,
    ADD COLUMN IF NOT EXISTS right_edad_categoria VARCHAR,
    ADD COLUMN IF NOT EXISTS right_nombre_base_final VARCHAR,
    ADD COLUMN IF NOT EXISTS right_texto TEXT
"""

SQLITE_COLUMNS = {
    'country_of_residence': 'VARCHAR',
    'nationality': 'VARCHAR',
    'lived_in_colombia': 'VARCHAR',
    'screening_excluded': 'BOOLEAN NOT NULL DEFAULT 0',
    'screening_exclusion_reason': 'VARCHAR',
    'left_ideology_text': 'TEXT',
    'right_ideology_text': 'TEXT',
    'left_codigo': 'VARCHAR',
    'left_ideologia': 'VARCHAR',
    'left_sexo': 'VARCHAR',
    'left_dominancia': 'VARCHAR',
    'left_edad_categoria': 'VARCHAR',
    'left_nombre_base_final': 'VARCHAR',
    'left_texto': 'TEXT',
    'right_codigo': 'VARCHAR',
    'right_ideologia': 'VARCHAR',
    'right_sexo': 'VARCHAR',
    'right_dominancia': 'VARCHAR',
    'right_edad_categoria': 'VARCHAR',
    'right_nombre_base_final': 'VARCHAR',
    'right_texto': 'TEXT',
}


def migrate_postgres(database_url):
    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.conjoint_player')")
            table_name = cursor.fetchone()[0]

            if table_name is None:
                print(
                    'Project schema migration skipped: '
                    'conjoint_player will be created at startup.'
                )
                return

            cursor.execute(POSTGRES_COLUMNS_SQL)

    print('PostgreSQL project schema migration complete.')


def migrate_sqlite(database_path):
    if not database_path.exists():
        print(
            'Project schema migration skipped: '
            'local database does not exist yet.'
        )
        return

    with sqlite3.connect(database_path) as connection:
        table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'conjoint_player'
            """
        ).fetchone()

        if table_exists is None:
            print(
                'Project schema migration skipped: '
                'conjoint_player will be created at startup.'
            )
            return

        existing_columns = {
            row[1]
            for row in connection.execute('PRAGMA table_info(conjoint_player)')
        }
        for column_name, column_type in SQLITE_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(
                    f'ALTER TABLE conjoint_player '
                    f'ADD COLUMN {column_name} {column_type}'
                )

    print('Local SQLite project schema migration complete.')


database_url = environ.get('DATABASE_URL', '')

if database_url.startswith(('postgres://', 'postgresql://')):
    migrate_postgres(database_url)
else:
    migrate_sqlite(Path(__file__).resolve().with_name('db.sqlite3'))
