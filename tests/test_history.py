from datetime import datetime
import unittest
from unittest.mock import MagicMock, patch

import attendance


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.change = {'name': 'Player', 'old_status': 'Coming', 'new_status': 'Late',
                       'old_note': None, 'new_note': 'Later', 'timestamp': datetime(2026, 9, 7)}

    def test_opens_before_database_query_then_updates_same_modal(self):
        client = MagicMock()
        client.views_open.return_value = {'view': {'id': 'V1'}}
        def load(*args, **kwargs):
            client.views_open.assert_called_once()
            return [self.change]
        with patch.object(attendance, 'load_history_from_event', side_effect=load):
            attendance.show_history({'trigger_id': 'trigger'}, client, MagicMock(), 42)
        update = client.views_update.call_args.kwargs
        self.assertEqual(update['view_id'], 'V1')
        self.assertEqual(update['view']['private_metadata'], '42')
        self.assertIn('Player', update['view']['blocks'][0]['text']['text'])

    def test_empty_history_is_visible(self):
        blocks = attendance.create_history_blocks([], 0, '42')
        self.assertEqual(len(blocks), 1)
        self.assertIn('žádné změny', blocks[0]['text']['text'])

    def test_out_of_range_page_is_clamped(self):
        for page in [-1, 100]:
            blocks = attendance.create_history_blocks([self.change], page, '42')
            self.assertIn('Player', blocks[0]['text']['text'])

    def test_navigation_last_page(self):
        changes = [self.change] * (attendance.HISTORY_PAGE_SIZE + 1)
        blocks = attendance.create_history_blocks(changes, 1, '42')
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[-1]['elements'][0]['action_id'], 'history_prev_42')
        self.assertEqual(len(blocks[-1]['elements']), 1)

    def test_database_error_is_displayed_and_logged(self):
        client, logger = MagicMock(), MagicMock()
        with patch.object(attendance, 'load_history_from_event', side_effect=RuntimeError('database offline')):
            with self.assertRaisesRegex(RuntimeError, 'database offline'):
                attendance.update_history_view(client, 'V1', '42', 0, logger)
        logger.exception.assert_called_once()
        text = client.views_update.call_args.kwargs['view']['blocks'][0]['text']['text']
        self.assertIn('nepodařilo načíst', text)


if __name__ == '__main__':
    unittest.main()
