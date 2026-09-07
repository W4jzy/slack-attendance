"""Versioned SQL migrations for Slack Attendance, adapted from DiscordAttendance."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import re

from db import connect_to_db
from runtime import load_environment

MIGRATIONS_DIR = Path(__file__).resolve().parent / 'migrations'
LOGGER = logging.getLogger('db-migrations')


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    sql: str

    @property
    def checksum(self):
        return hashlib.sha256(self.sql.encode('utf-8')).hexdigest()


def discover_migrations(directory=None):
    directory = Path(directory or MIGRATIONS_DIR)
    if not directory.is_dir():
        raise RuntimeError(f'Migrations directory not found: {directory}')
    migrations = []
    seen = set()
    for path in sorted(directory.glob('*.sql')):
        match = re.fullmatch(r'(\d{3,})_([a-z0-9_]+)\.sql', path.name)
        if not match:
            raise RuntimeError(f'Invalid migration filename: {path.name}')
        version, name = match.groups()
        if int(version) in seen:
            raise RuntimeError(f'Duplicate migration version: {version}')
        seen.add(int(version))
        migration = Migration(version, name, path.read_text(encoding='utf-8-sig'))
        statements = read_migration_statements(migration)
        if not statements:
            raise RuntimeError(f'Empty migration: {path.name}')
        for statement in statements:
            if re.match(r'(?i)^(USE|DELIMITER)\b', statement):
                raise RuntimeError(f'USE and DELIMITER are unsupported: {path.name}')
        migrations.append(migration)
    if not migrations:
        raise RuntimeError('No migration files found')
    return sorted(migrations, key=lambda migration: int(migration.version))


def split_sql_statements(sql: str) -> list[str]:
    """
    Split SQL script into statements while respecting quoted strings.

    This intentionally keeps the format simple: migrations should avoid stored
    procedures and custom DELIMITER blocks.
    """
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    i = 0

    while i < len(sql):
        char = sql[i]
        next_char = sql[i + 1] if i + 1 < len(sql) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
                current.append(char)
            i += 1
            continue

        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                i += 2
            else:
                i += 1
            continue

        if quote is None:
            if char == "-" and next_char == "-":
                after = sql[i + 2] if i + 2 < len(sql) else ""
                if not after or after.isspace():
                    line_comment = True
                    i += 2
                    continue
            if char == "/" and next_char == "*":
                if i + 2 < len(sql) and sql[i + 2] == "!":
                    raise ValueError("Executable SQL comments are unsupported")
                current.append(" ")
                block_comment = True
                i += 2
                continue
            if char == "#":
                line_comment = True
                i += 1
                continue
            if char in ("'", '"', "`"):
                quote = char
                current.append(char)
                i += 1
                continue
            if char == ";":
                statement = "".join(current).strip()
                if statement:
                    statements.append(statement)
                current = []
                i += 1
                continue

            current.append(char)
            i += 1
            continue

        current.append(char)
        if escaped:
            escaped = False
        elif char == "\\" and quote != "`":
            escaped = True
        elif char == quote:
            quote = None
        i += 1

    if quote is not None or block_comment:
        raise ValueError("Unterminated SQL quote or comment")
    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements


def read_migration_statements(migration: Migration) -> list[str]:
    return split_sql_statements(migration.sql)


def consume_cursor_results(cursor) -> None:
    """Drain result sets so mysql-connector accepts the next statement.

    Some valid migration statements can return rows. mysql-connector requires
    every result set to be consumed before it accepts the next statement.
    """
    while True:
        if cursor.with_rows:
            cursor.fetchall()
        if not cursor.nextset():
            break


def load_applied_migrations(cursor):
    # status and dry-run must not create even the bookkeeping table.
    cursor.execute("SELECT COUNT(*) AS count FROM information_schema.TABLES "
                   "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'schema_migrations'")
    if not cursor.fetchone()['count']:
        return {}
    cursor.execute('SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version')
    return {row['version']: row for row in cursor.fetchall()}


def validate_migration_history(migrations, applied):
    discovered = {migration.version: migration for migration in migrations}
    for version, row in applied.items():
        migration = discovered.get(version)
        if migration is None:
            raise RuntimeError(f'Applied migration {version} has no matching SQL file')
        if row['name'] != migration.name or row['checksum'] != migration.checksum:
            raise RuntimeError(f'Applied migration {version} was renamed or modified; restore its original file')
    highest = max((int(version) for version in applied), default=-1)
    if any(int(m.version) < highest and m.version not in applied for m in migrations):
        raise RuntimeError('Migration history has a gap; new migrations must follow applied versions')


def apply_migration(connection, cursor, migration):
    LOGGER.info('Applying %s_%s', migration.version, migration.name)
    try:
        for number, statement in enumerate(read_migration_statements(migration), start=1):
            try:
                cursor.execute(statement)
                consume_cursor_results(cursor)
            except Exception as exc:
                raise RuntimeError(
                    f'Migration {migration.version}_{migration.name} failed at statement {number}. '
                    'DDL may already be committed; correct the cause and retry or restore the backup.'
                ) from exc
        cursor.execute('INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)',
                       (migration.version, migration.name, migration.checksum))
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def run(command, connection=None):
    if command not in {'migrate', 'status', 'dry-run', 'check'}:
        raise ValueError(f'Unknown command: {command}')
    migrations = discover_migrations()
    owns_connection = connection is None
    connection = connection or connect_to_db()
    cursor = None
    lock_name = None
    try:
        cursor = connection.cursor(dictionary=True)
        if command == 'migrate':
            cursor.execute('SELECT DATABASE() AS name')
            name = cursor.fetchone()['name']
            candidate = 'slack-attendance:' + hashlib.sha256(name.encode()).hexdigest()[:40]
            cursor.execute('SELECT GET_LOCK(%s, 0) AS acquired', (candidate,))
            if cursor.fetchone()['acquired'] != 1:
                raise RuntimeError('Another database migration is running')
            lock_name = candidate
        applied = load_applied_migrations(cursor)
        validate_migration_history(migrations, applied)
        pending = [m for m in migrations if m.version not in applied]
        if command == 'check':
            if pending:
                raise RuntimeError('Pending database migrations; run python migrate.py migrate')
            return
        if command in {'status', 'dry-run'}:
            for migration in migrations:
                row = applied.get(migration.version)
                state = f"APPLIED ({row['applied_at']})" if row else 'PENDING'
                print(f'{state} {migration.version}_{migration.name}')
                if command == 'dry-run' and not row:
                    for statement in read_migration_statements(migration):
                        print(statement + ';')
            print(f'{len(applied)} applied, {len(pending)} pending')
            return
        cursor.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(32) NOT NULL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            checksum CHAR(64) NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci''')
        connection.commit()
        for migration in pending:
            apply_migration(connection, cursor, migration)
        LOGGER.info('%d migration(s) applied', len(pending))
    finally:
        try:
            if lock_name is not None:
                cursor.execute('SELECT RELEASE_LOCK(%s)', (lock_name,))
                consume_cursor_results(cursor)
        finally:
            if cursor is not None:
                cursor.close()
            if owns_connection:
                connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'dry-run', 'migrate', 'check'])
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format='%(message)s')
    load_environment()
    try:
        run(args.command)
        return 0
    except Exception as exc:
        LOGGER.error('%s', exc, exc_info=args.verbose)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())


