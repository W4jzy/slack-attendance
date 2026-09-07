import importlib
import logging
import os
from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import MagicMock, patch

import attendance
import config
import manage
from slack_sdk.errors import SlackApiError


class AttendanceActionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'SLACK_BOT_TOKEN': 'xoxb-test', 'SLACK_APP_TOKEN': 'xapp-test',
                                    'ATTENDANCE_CONFIG': str(manage.ROOT / 'config.ini.example')}), \
             patch('slack_sdk.WebClient.auth_test', return_value={
                 'ok': True, 'team_id': 'T1', 'user_id': 'U1', 'bot_id': 'B1'}):
            cls.bot = importlib.import_module('bot')

    def setUp(self):
        self.body = {'user': {'id': 'U1'}, 'actions': [{'value': 'coming_42_2_training'}],
                     'view': {'state': {'values': {}}},
                     'state': {'values': {'reason_42': {'reason_input_42': {'value': 'test note'}}}}}
        self.event = {'lock_time': datetime.now() + timedelta(hours=1)}
        self.ack, self.logger, self.client = MagicMock(), MagicMock(), MagicMock()

    def run_action(self, refresh_error=None, save_error=None):
        with patch.object(self.bot, 'client', self.client), \
             patch.object(self.bot, 'load_event_from_db', return_value=self.event), \
             patch.object(self.bot, 'insert_participation', side_effect=save_error) as save, \
             patch.object(self.bot, 'show_attendance', side_effect=refresh_error) as refresh:
            self.bot.handle_participation_action(self.ack, self.body, self.logger, 'Coming')
        return save, refresh

    def test_top_level_state_is_saved_and_same_page_is_refreshed(self):
        save, refresh = self.run_action()
        save.assert_called_once_with(42, 'U1', 'Coming', 'test note', self.logger, enforce_lock=True)
        refresh.assert_called_once_with(self.client, 'U1', self.logger, 2, 'training')
        self.ack.assert_called_once_with()

    def test_legacy_view_state_and_explicit_empty_note(self):
        self.body['view']['state'] = self.body.pop('state')
        self.assertEqual(self.bot.attendance_note(self.body, 42, 'U1'), 'test note')
        self.body['state'] = {'values': {'reason_42': {'reason_input_42': {'value': None}}}}
        self.assertIsNone(self.bot.attendance_note(self.body, 42, 'U1'))

    def test_missing_state_preserves_existing_note(self):
        self.body.pop('state')
        with patch.object(self.bot, 'load_user_in_event', return_value={'note': 'saved note'}):
            save, refresh = self.run_action()
        self.assertEqual(save.call_args.args[3], 'saved note')
        refresh.assert_called_once()

    def test_saved_but_refresh_failed_has_distinct_feedback_and_traceback(self):
        self.run_action(refresh_error=attendance.AttendanceError('publish failed'))
        self.assertIn('je uložená', self.client.chat_postMessage.call_args.kwargs['text'])
        self.logger.exception.assert_called_once()
        self.assertTrue(self.logger.exception.call_args.args[-1])

    def test_save_failure_does_not_claim_success(self):
        _, refresh = self.run_action(save_error=RuntimeError('db unavailable'))
        refresh.assert_not_called()
        self.assertIn('nepodařilo uložit', self.client.chat_postMessage.call_args.kwargs['text'])
        self.assertFalse(self.logger.exception.call_args.args[-1])

    def test_locked_event_is_not_written_and_view_is_refreshed(self):
        self.event['lock_time'] = datetime.now() - timedelta(seconds=1)
        save, refresh = self.run_action()
        save.assert_not_called()
        refresh.assert_called_once()


class AttendanceViewTests(TestCase):
    def test_group_api_failure_still_publishes_updated_attendance(self):
        config.update_global_variables()
        client = MagicMock()
        client.usergroups_users_list.side_effect = SlackApiError('missing_scope', {'error': 'missing_scope'})
        event = {'id': 42, 'name': 'Training', 'type': 'Trénink', 'start_time': datetime.now(),
                 'lock_time': datetime.now() + timedelta(hours=1)}
        with patch.object(attendance, 'load_events_from_db', return_value=[event]), \
             patch.object(attendance, 'load_participants_for_user', return_value=[
                 {'event_id': 42, 'status': 'Coming', 'note': ''}]):
            attendance.show_attendance(client, 'U1', MagicMock())
        blocks = client.views_publish.call_args.kwargs['view']['blocks']
        coming = [element for block in blocks for element in block.get('elements', [])
                  if element.get('action_id') == 'coming'][0]
        self.assertEqual(coming['style'], 'primary')
        self.assertTrue(coming['text']['text'].startswith('🟢'))

    def test_publish_failure_propagates_to_caller(self):
        client = MagicMock()
        client.usergroups_users_list.return_value = {'users': []}
        client.views_publish.side_effect = SlackApiError('invalid_blocks', {'error': 'invalid_blocks'})
        with patch.object(attendance, 'load_events_from_db', return_value=[]), \
             patch.object(attendance, 'load_participants_for_user', return_value=[]), \
             self.assertRaises(attendance.AttendanceError):
            attendance.show_attendance(client, 'U1', logging.getLogger('test'))
