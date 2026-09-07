"""Server-side authorization for administrative Slack interactions."""
import re

import config


ADMIN_ACTIONS = {
    'go_to_add_event', 'all_events', 'go_to_all_events', 'go_to_settings',
    'go_to_edit_attendance', 'go_to_reminders', 'edit_overflow',
    'event_attendance_coming', 'event_attendance_late', 'event_attendance_not_coming',
    'next_edit_page', 'previous_edit_page', 'select_date_button',
    'user_selection', 'user_select', 'select_user_category', 'open_add_reminder_modal',
}
ADMIN_PATTERN = re.compile(
    r'^(delete_event_|edit_event_|duplicate_event_|select_event_|select_edit_user_|reminder_overflow_)'
)
ADMIN_VIEWS = {'settings_modal', 'add_event_modal', 'export_dates_submit',
               'share_event', 'add_reminder_modal'}


def requires_admin(body):
    callback = body.get('view', {}).get('callback_id', '')
    if body.get('type') == 'view_submission':
        return callback in ADMIN_VIEWS or callback.startswith(
            ('edit_event_', 'duplicate_event_', 'edit_user_category_',
             'edit_attendance_', 'edit_reminder_')
        )
    actions = body.get('actions', [])
    if body.get('type') == 'block_suggestion':
        return body.get('action_id') in {'user_selection', 'user_select'}
    for action in actions:
        action_id = action.get('action_id', '')
        selected = (action.get('selected_option') or {}).get('value', '')
        if action_id in ADMIN_ACTIONS or ADMIN_PATTERN.match(action_id):
            return True
        if action_id in {'main_menu_overflow', 'events_menu_overflow'} and selected in ADMIN_ACTIONS:
            return True
        if action_id.startswith('overflow_menu_') and selected.startswith('share_event_'):
            return True
    return False


def authorize_admin(body, client, logger, next):
    if requires_admin(body):
        from slack_bolt.response import BoltResponse
        try:
            members = client.usergroups_users_list(usergroup=config.admin_group)['users']
            allowed = body.get('user', {}).get('id') in members
        except Exception:
            logger.exception('Unable to verify administrator membership')
            allowed = False
        if not allowed:
            logger.warning('Rejected administrative interaction from %s', body.get('user', {}).get('id'))
            if body.get('type') == 'view_submission':
                return BoltResponse(status=200, body={
                    'response_action': 'update', 'view': {
                        'type': 'modal', 'title': {'type': 'plain_text', 'text': 'Přístup zamítnut'},
                        'close': {'type': 'plain_text', 'text': 'Zavřít'},
                        'blocks': [{'type': 'section', 'text': {
                            'type': 'mrkdwn', 'text': 'Tato akce vyžaduje administrátorská práva.'}}],
                    },
                })
            return BoltResponse(status=200, body={'options': []} if body.get('type') == 'block_suggestion' else '')
    return next()
