import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import migrate


class FakeCursor:
    def __init__(self, applied=None, fail_on=None, locked=False, table_exists=False):
        self.applied = dict(applied or {})
        self.table_exists = table_exists or bool(applied)
        self.fail_on = fail_on
        self.locked = locked
        self.queries = []
        self.rows = []
        self.with_rows = False
        self.closed = False

    def execute(self, query, params=None):
        self.queries.append((query, params))
        if self.fail_on and self.fail_on in query:
            raise RuntimeError('simulated SQL failure')
        self.rows = []
        if query.startswith('SELECT DATABASE'):
            self.rows = [{'name': 'attendance'}]
        elif 'GET_LOCK' in query:
            self.rows = [{'acquired': 0 if self.locked else 1}]
        elif 'RELEASE_LOCK' in query:
            self.rows = [{'released': 1}]
        elif 'information_schema.TABLES' in query:
            self.rows = [{'count': int(self.table_exists)}]
        elif query.startswith('SELECT version'):
            self.rows = list(self.applied.values())
        elif query.startswith('CREATE TABLE IF NOT EXISTS schema_migrations'):
            self.table_exists = True
        elif query.startswith('INSERT INTO schema_migrations'):
            version, name, checksum = params
            self.applied[version] = {'version': version, 'name': name, 'checksum': checksum, 'applied_at': 'now'}
        self.with_rows = bool(self.rows)

    def fetchone(self):
        return self.rows.pop(0)

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows

    def nextset(self):
        self.with_rows = False
        return None

    def close(self):
        self.closed = True


def history(migration):
    return {'version': migration.version, 'name': migration.name,
            'checksum': migration.checksum, 'applied_at': 'now'}


class ParserTests(unittest.TestCase):
    def test_quoted_semicolons_and_comments(self):
        sql = "-- ignored;\nSELECT 'a; -- b', 'it''s fine;', `a;b`; # ignored;\nDO/* block; */ 0;"
        self.assertEqual(migrate.split_sql_statements(sql),
                         ["SELECT 'a; -- b', 'it''s fine;', `a;b`", 'DO  0'])

    def test_unterminated_sql_is_rejected(self):
        for sql in ["SELECT 'broken", 'SELECT 1 /* broken', '/*! executable */ SELECT 1']:
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                migrate.split_sql_statements(sql)

    def test_mysql_line_comment_after_expression(self):
        self.assertEqual(migrate.split_sql_statements('SELECT 1-- comment;\n; DO 0;'), ['SELECT 1', 'DO 0'])

    def test_all_result_sets_are_drained(self):
        cursor = MagicMock()
        cursor.with_rows = True
        cursor.nextset.side_effect = [True, None]
        migrate.consume_cursor_results(cursor)
        self.assertEqual(cursor.fetchall.call_count, 2)


class DiscoveryTests(unittest.TestCase):
    def test_numeric_order_and_normalized_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '010_later.sql').write_bytes(b'DO 0;\r\n')
            (root / '002_earlier.sql').write_text('DO 0;\n', encoding='utf-8')
            found = migrate.discover_migrations(root)
            self.assertEqual([m.version for m in found], ['002', '010'])
            self.assertEqual(found[0].checksum, found[1].checksum)

    def test_duplicate_numeric_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ['001_first.sql', '0001_duplicate.sql']:
                (root / name).write_text('DO 0;', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
                migrate.discover_migrations(root)

    def test_invalid_or_empty_sql_is_rejected(self):
        for name, sql in [('wrong.sql', 'DO 0;'), ('001_empty.sql', '-- comment'),
                          ('001_use.sql', 'USE another_db;'), ('001_proc.sql', 'DELIMITER $$')]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                (Path(directory) / name).write_text(sql, encoding='utf-8')
                with self.assertRaises(RuntimeError):
                    migrate.discover_migrations(directory)

    def test_snapshot_matches_numbered_migrations(self):
        root = migrate.MIGRATIONS_DIR.parent
        snapshot = migrate.split_sql_statements((root / 'db.sql').read_text(encoding='utf-8'))
        statements = [sql for migration in migrate.discover_migrations()
                      for sql in migrate.read_migration_statements(migration)]
        self.assertEqual(snapshot, statements)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.first = migrate.Migration('001', 'first', 'CREATE TABLE IF NOT EXISTS example (id INT);')
        self.second = migrate.Migration('002', 'second', 'DO 0;')
        self.discovery = patch.object(migrate, 'discover_migrations', return_value=[self.first, self.second])
        self.discovery.start()
        self.addCleanup(self.discovery.stop)

    def run_command(self, command, cursor):
        connection = MagicMock()
        connection.cursor.return_value = cursor
        with contextlib.redirect_stdout(io.StringIO()):
            migrate.run(command, connection)
        return connection

    def test_empty_database_applies_once_and_records_checksums(self):
        cursor = FakeCursor()
        self.run_command('migrate', cursor)
        self.assertEqual(cursor.applied['001']['checksum'], self.first.checksum)
        self.assertEqual(set(cursor.applied), {'001', '002'})
        cursor.queries.clear()
        self.run_command('migrate', cursor)
        self.assertFalse(any('example' in q or q.startswith('INSERT') for q, _ in cursor.queries))
        self.assertTrue(cursor.closed)

    def test_status_and_dry_run_are_read_only(self):
        for command in ['status', 'dry-run']:
            with self.subTest(command=command):
                cursor = FakeCursor()
                connection = self.run_command(command, cursor)
                self.assertTrue(all(q.startswith('SELECT') for q, _ in cursor.queries))
                connection.commit.assert_not_called()
                self.assertFalse(cursor.table_exists)

    def test_applied_file_cannot_be_modified_or_removed(self):
        for row in [dict(history(self.first), checksum='changed'),
                    dict(history(self.first), name='renamed')]:
            with self.assertRaisesRegex(RuntimeError, 'renamed or modified'):
                migrate.validate_migration_history([self.first], {'001': row})
        with self.assertRaisesRegex(RuntimeError, 'no matching'):
            migrate.validate_migration_history([], {'001': history(self.first)})

    def test_out_of_order_insertion_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'gap'):
            migrate.validate_migration_history([self.first, self.second], {'002': history(self.second)})

    def test_failed_statement_is_not_recorded_and_lock_is_released(self):
        cursor = FakeCursor(fail_on='DO 0')
        connection = MagicMock()
        connection.cursor.return_value = cursor
        with self.assertRaisesRegex(RuntimeError, '002_second failed at statement 1'):
            migrate.run('migrate', connection)
        self.assertEqual(set(cursor.applied), {'001'})
        connection.rollback.assert_called_once()
        self.assertTrue(any('RELEASE_LOCK' in q for q, _ in cursor.queries))
        cursor.fail_on = None
        self.run_command('migrate', cursor)
        self.assertEqual(set(cursor.applied), {'001', '002'})

    def test_lock_contention_prevents_schema_changes(self):
        cursor = FakeCursor(locked=True)
        with self.assertRaisesRegex(RuntimeError, 'Another database migration'):
            self.run_command('migrate', cursor)
        self.assertTrue(all(q.startswith('SELECT') for q, _ in cursor.queries))
        self.assertFalse(any('RELEASE_LOCK' in q for q, _ in cursor.queries))

    def test_check_requires_all_migrations(self):
        with self.assertRaisesRegex(RuntimeError, 'Pending'):
            self.run_command('check', FakeCursor())
        self.run_command('check', FakeCursor(applied={'001': history(self.first), '002': history(self.second)}))

    def test_owned_connection_is_closed_after_failure(self):
        cursor = FakeCursor(locked=True)
        connection = MagicMock()
        connection.cursor.return_value = cursor
        with patch.object(migrate, 'connect_to_db', return_value=connection), self.assertRaises(RuntimeError):
            migrate.run('migrate')
        connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
