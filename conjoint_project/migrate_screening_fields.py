"""Add the Colombia screening fields without deleting existing oTree data."""

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
    ADD COLUMN IF NOT EXISTS screening_exclusion_reason VARCHAR
"""

SQLITE_COLUMNS = {
    'country_of_residence': 'VARCHAR',
    'nationality': 'VARCHAR',
    'lived_in_colombia': 'VARCHAR',
    'screening_excluded': 'BOOLEAN NOT NULL DEFAULT 0',
    'screening_exclusion_reason': 'VARCHAR',
}


def migrate_postgres(database_url):
    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.conjoint_player')")
            table_name = cursor.fetchone()[0]

            if table_name is None:
                print(
                    'Screening migration skipped: '
                    'conjoint_player will be created at startup.'
                )
                return

            cursor.execute(POSTGRES_COLUMNS_SQL)

    print('PostgreSQL screening migration complete.')


def migrate_sqlite(database_path):
    if not database_path.exists():
        print('Screening migration skipped: local database does not exist yet.')
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
                'Screening migration skipped: '
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

    print('Local SQLite screening migration complete.')


database_url = environ.get('DATABASE_URL', '')

if database_url.startswith(('postgres://', 'postgresql://')):
    migrate_postgres(database_url)
else:
    migrate_sqlite(Path(__file__).resolve().with_name('db.sqlite3'))
