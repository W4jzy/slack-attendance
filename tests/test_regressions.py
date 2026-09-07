import importlib
import logging
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import access
import config
import db
import manage
import reminders


class ConfigurationTests(unittest.TestCase):
    def test_missing_file_reports_config_error(self):
        with self.assertRaises(config.ConfigError):
            config.load_settings('does-not-exist.ini')

    def test_utf8_percent_and_database_section_survive_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.ini'
            path.write_text('[settings]\nadmin_group=S123\ncoming_text=Přijdu 100%\n'
                            '[database]\npassword=abc%123\n', encoding='utf-8')
            config.load_settings(path)
            config.save_settings(path)
            config.load_settings(path)
            self.assertEqual(config.coming_text, 'Přijdu 100%')
            self.assertIn('abc%123', path.read_text(encoding='utf-8'))


class AuthorizationTests(unittest.TestCase):
    def action(self, name, selected=''):
        return {'type': 'block_actions', 'user': {'id': 'U1'}, 'actions': [
            {'action_id': name, 'selected_option': {'value': selected}}]}

    def test_admin_routes_and_ordinary_attendance(self):
        for name in ['delete_event_12', 'event_attendance_coming', 'reminder_overflow_1']:
            self.assertTrue(access.requires_admin(self.action(name)))
        self.assertTrue(access.requires_admin(self.action('main_menu_overflow', 'go_to_settings')))
        self.assertTrue(access.requires_admin({'type': 'view_submission', 'view': {'callback_id': 'edit_attendance_1'}}))
        for name in ['coming', 'attendance_modal', 'refresh_home_tab']:
            self.assertFalse(access.requires_admin(self.action(name)))

    def test_denied_request_never_reaches_handler(self):
        config.admin_group = 'S1'
        client, next_handler = MagicMock(), MagicMock()
        client.usergroups_users_list.return_value = {'users': ['U2']}
        response = access.authorize_admin(self.action('delete_event_1'), client, MagicMock(), next_handler)
        self.assertEqual(response.status, 200)
        next_handler.assert_not_called()
        client.usergroups_users_list.side_effect = RuntimeError('API unavailable')
        access.authorize_admin(self.action('delete_event_1'), client, MagicMock(), next_handler)
        next_handler.assert_not_called()

    def test_allowed_request_continues(self):
        config.admin_group = 'S1'
        client, next_handler = MagicMock(), MagicMock()
        client.usergroups_users_list.return_value = {'users': ['U1']}
        access.authorize_admin(self.action('delete_event_1'), client, MagicMock(), next_handler)
        next_handler.assert_called_once()


class AttendanceTransactionTests(unittest.TestCase):
    def setUp(self):
        config.update_global_variables()
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value
        self.cursor.fetchone.return_value = {'type': 'Trénink', 'lock_time': datetime.now() + timedelta(days=1)}
        self.cursor.fetchall.return_value = []
        self.connection_patch = patch.object(db, 'connect_to_db', return_value=self.connection)
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)

    def test_attendance_and_history_commit_together(self):
        db.insert_participation(1, 'U1', 'Coming', enforce_lock=True)
        queries = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertIn('FOR UPDATE', queries[0])
        self.assertTrue(any('INSERT INTO participants' in q for q in queries))
        self.assertTrue(any('INSERT INTO history' in q for q in queries))
        self.connection.commit.assert_called_once()
        self.connection.close.assert_called_once()

    def test_history_failure_rolls_back_attendance(self):
        self.cursor.execute.side_effect = [None, None, None, RuntimeError('history failed')]
        with self.assertRaises(db.DatabaseError):
            db.insert_participation(1, 'U1', 'Coming')
        self.connection.commit.assert_not_called()
        self.connection.rollback.assert_called_once()

    def test_expired_modal_cannot_change_attendance(self):
        self.cursor.fetchone.return_value['lock_time'] = datetime.now() - timedelta(seconds=1)
        with self.assertRaises(db.DatabaseError):
            db.insert_participation(1, 'U1', 'Coming', enforce_lock=True)
        self.connection.commit.assert_not_called()
        self.assertEqual(self.cursor.execute.call_count, 1)


class ReminderTests(unittest.TestCase):
    def test_month_end_uses_real_calendar(self):
        self.assertEqual(reminders.calculate_next_reminder_time(datetime(2028, 1, 31), 'monthly'), datetime(2028, 2, 29))
        self.assertEqual(reminders.calculate_next_reminder_time(datetime(2028, 4, 30), 'monthly'), datetime(2028, 5, 30))

    def test_failed_share_is_not_deactivated(self):
        reminder = {'id': 1, 'channel_id': 'C1', 'message': 'Reminder', 'remind_at': datetime.now(),
                    'reminder_type': 'share_events', 'repeat_type': 'once', 'days_ahead': 0}
        client = MagicMock()
        client.chat_postMessage.side_effect = RuntimeError('offline')
        with patch.object(reminders, 'get_due_reminders', return_value=[reminder]), \
             patch.object(reminders, 'load_events_by_date_from_db', return_value=[]), \
             patch.object(reminders, 'deactivate_reminder') as deactivate:
            reminders.process_due_reminders(client, MagicMock())
            deactivate.assert_not_called()

    def test_missed_repetition_advances_into_future(self):
        reminder = {'id': 1, 'channel_id': 'C1', 'message': 'Reminder',
                    'remind_at': datetime.now() - timedelta(days=10), 'repeat_type': 'daily'}
        with patch.object(reminders, 'get_due_reminders', return_value=[reminder]), \
             patch.object(reminders, 'update_reminder_next_time') as update:
            reminders.process_due_reminders(MagicMock(), MagicMock())
            self.assertGreater(update.call_args.args[1], datetime.now())


class ProvisionTests(unittest.TestCase):
    def test_provision_escapes_password_without_changing_existing_accounts(self):
        parser = MagicMock()
        values = {'host': 'localhost', 'database': 'attendance', 'user': 'attendance', "password": "a'b\\c%123"}
        parser.get.side_effect = lambda section, key: values[key]
        with patch.object(manage, 'ConfigParser', return_value=parser), \
             patch.object(manage.subprocess, 'run', return_value=MagicMock(returncode=0)) as run:
            manage.provision_database()
        sql = run.call_args.kwargs['input']
        self.assertIn("NO_BACKSLASH_ESCAPES", sql)
        self.assertIn("IDENTIFIED BY 'a''b\\c%123'", sql)
        self.assertNotIn('ALTER USER', sql)
        self.assertNotIn(values['password'], str(run.call_args.args))

    def test_system_database_is_rejected(self):
        parser = MagicMock()
        values = {'host': 'localhost', 'database': 'mysql', 'user': 'attendance', 'password': 'test'}
        parser.get.side_effect = lambda section, key: values[key]
        with patch.object(manage, 'ConfigParser', return_value=parser), \
             patch.object(manage.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                manage.provision_database()
        run.assert_not_called()


class SlackRegistrationTests(unittest.TestCase):
    def test_import_and_unique_duplicate_handlers_without_network(self):
        with patch.dict(os.environ, {'SLACK_BOT_TOKEN': 'xoxb-test', 'SLACK_APP_TOKEN': 'xapp-test',
                                    'ATTENDANCE_CONFIG': str(manage.ROOT / 'config.ini.example')}), \
             patch('slack_sdk.WebClient.auth_test', return_value={
                 'ok': True, 'team_id': 'T1', 'user_id': 'U1', 'bot_id': 'B1'}):
            bot = importlib.import_module('bot')
        names = [listener.ack_function.__name__ for listener in bot.app._listeners]
        self.assertEqual(names.count('handle_duplicate_action'), 1)
        self.assertEqual(names.count('handle_duplicate_submission'), 1)
        self.assertIn('handle_chat_attendance_submission', names)


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    unittest.main()
