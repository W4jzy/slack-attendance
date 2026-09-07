"""Local maintenance commands; never connects to Slack or sends messages."""
import argparse
from configparser import ConfigParser
import os
import re
from pathlib import Path
import subprocess
import tempfile

import config
from db import connect_to_db
from runtime import load_environment
from migrate import run as run_migrations

ROOT = Path(__file__).resolve().parent
def migrate(connection):
    """Compatibility entry point; all changes use the versioned SQL runner."""
    run_migrations('migrate', connection)


def check(connection):
    run_migrations('check', connection)
    config.load_settings()
    group = config.get_setting('admin_group')
    if not group or group in {'None', 'GROUP_ID'} or group.startswith('REPLACE_'):
        raise RuntimeError('Set settings.admin_group in the configuration')
    for name, prefix in [('SLACK_BOT_TOKEN', 'xoxb-'), ('SLACK_APP_TOKEN', 'xapp-')]:
        value = os.getenv(name, '')
        if not value.startswith(prefix) or 'replace' in value.lower():
            raise RuntimeError(f'Set {name} in the environment file')
    cursor = connection.cursor()
    try:
        for table, columns in {
            'events': 'id, name, start_time, end_time, lock_time, type, address',
            'users': 'user_id, name, category',
            'participants': 'id, user_id, event_id, status, note',
            'history': 'id, event_id, user_id, timestamp, old_status, new_status, old_note, new_note',
            'reminders': 'id, channel_id, remind_at, message, repeat_type, active, reminder_type, days_ahead',
        }.items():
            cursor.execute(f'SELECT {columns} FROM {table} LIMIT 0')
            cursor.fetchall()
    finally:
        cursor.close()


def backup(destination):
    parser = ConfigParser(interpolation=None)
    parser.read(config.config_path(), encoding='utf-8')
    def quote(value):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'
    # A private temporary option file keeps credentials out of argv/process listings.
    with tempfile.TemporaryDirectory() as directory:
        defaults = Path(directory) / 'client.cnf'
        defaults.write_text('[client]\n' + '\n'.join(
            f'{key}={quote(parser.get("database", key, fallback="3306" if key == "port" else None))}'
            for key in ('host', 'port', 'user', 'password')
        ), encoding='utf-8')
        os.chmod(defaults, 0o600)
        with open(destination, 'xb') as output:
            os.chmod(destination, 0o600)
            subprocess.run(['mariadb-dump', f'--defaults-extra-file={defaults}',
                            '--single-transaction', '--quick', '--hex-blob',
                            '--skip-lock-tables', '--', parser.get('database', 'database')],
                           stdout=output, check=True)


def provision_database():
    """Create a local MariaDB database/account using root socket authentication."""
    parser = ConfigParser(interpolation=None)
    parser.read(config.config_path(), encoding='utf-8')
    host = parser.get('database', 'host')
    if host not in {'localhost', '127.0.0.1'}:
        raise RuntimeError('Automatic provisioning supports only local MariaDB')
    name = parser.get('database', 'database')
    user = parser.get('database', 'user')
    password = parser.get('database', 'password')
    if not all(re.fullmatch(r'[A-Za-z0-9_]+', value) for value in (name, user)):
        raise RuntimeError('Database and user names must contain only letters, digits, underscores')
    if user == 'root' or name.lower() in {'mysql', 'sys', 'information_schema', 'performance_schema'}:
        raise RuntimeError('Choose a dedicated application database/account')
    if not password or '\n' in password or '\r' in password:
        raise RuntimeError('Set a nonempty single-line database password')
    # Set SQL mode explicitly so quote escaping has a known meaning.
    escaped_password = password.replace("'", "''")
    sql = f"""SET SESSION sql_mode = 'NO_BACKSLASH_ESCAPES';
CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_czech_ci;
"""
    for account_host in ('localhost', '127.0.0.1'):
        sql += f"""CREATE USER IF NOT EXISTS '{user}'@'{account_host}' IDENTIFIED BY '{escaped_password}';
GRANT ALL PRIVILEGES ON `{name}`.* TO '{user}'@'{account_host}';
"""
    result = subprocess.run(['mariadb', '--user=root', '--protocol=socket'],
                            input=sql, text=True, capture_output=True)
    if result.returncode:
        # MariaDB errors may echo the SQL containing the password.
        raise RuntimeError('Database provisioning failed; verify MariaDB root socket access and configuration')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'migrate', 'status', 'dry-run', 'backup', 'provision'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    load_environment()
    if args.command == 'provision':
        provision_database()
    elif args.command == 'backup':
        if not args.output:
            parser.error('backup requires --output')
        backup(args.output)
    else:
        connection = connect_to_db()
        try:
            if args.command in {'migrate', 'status', 'dry-run'}:
                run_migrations(args.command, connection)
            else:
                check(connection)
        finally:
            connection.close()
    print(f'{args.command}: OK')


if __name__ == '__main__':
    main()
