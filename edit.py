from typing import Dict, List, Any, Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime
import logging
import config
from db import load_events_by_date_from_db, load_event_from_db, load_user_in_event, load_user_from_db

class EditError(Exception):
    """Base exception for edit related errors"""
    pass

def build_user_category_blocks() -> List[Dict[str, Any]]:
    """Build blocks for user category selection and update"""
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Vyberte hráče pro úpravu kategorie*"},
        },
        {
            "type": "actions",
            "block_id": "user_category_selection_section",
            "elements": [
                {
                    "type": "external_select",
                    "action_id": "user_selection",
                    "placeholder": {"type": "plain_text", "text": "Vyberte hráče..."},
                    "min_query_length": 2
                },
                {
                    "type": "button",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Potvrdit"},
                    "action_id": "select_user_category"
                }
            ]
        },
        {"type": "divider"}
    ]

def build_export_blocks() -> List[Dict[str, Any]]:
    """Build blocks for export view"""
    return [
        {
            "type": "actions",
            "elements": [{
                "type": "overflow",
                "options": [{
                    "text": {"type": "plain_text", "text": "Export do CSV"},
                    "value": "export_participants"
                }],
                "action_id": "edit_overflow"
            }]
        }
    ]

def build_back_blocks() -> List[Dict[str, Any]]:
    """Build blocks for back navigation"""
    return [
        {
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": "Zpět"},
                "action_id": "go_to_attendance"
            }]
        }
    ]

def build_header_blocks() -> List[Dict[str, Any]]:
    """Build header blocks for edit view"""
    blocks = []
    
    # Export je nyní vždy dostupný (posílá se do DM)
    blocks.extend(build_export_blocks())
    blocks.extend(build_back_blocks())

    blocks.extend([
        {
            "type": "input",
            "block_id": "date_picker",
            "element": {
                "type": "datepicker",
                "action_id": "date_select",
                "placeholder": {"type": "plain_text", "text": "Vyberte datum"}
            },
            "label": {"type": "plain_text", "text": "Vyberte datum pro zobrazení událostí"}
        },
        {
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": "Vybrat"},
                "value": "select_date",
                "action_id": "select_date_button"
            }]
        },
        {"type": "divider"}
    ])

    return blocks

def build_event_blocks(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build blocks for single event"""
    start_time_str = event['start_time'].strftime('%d.%m.%Y %H:%M')
    end_time_str = event['end_time'].strftime('%d.%m.%Y %H:%M')
    lock_time_str = event['lock_time'].strftime('%d.%m.%Y %H:%M')
    
    return [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*{event['name']}*\nZačátek: {start_time_str}\nKonec: {end_time_str}\nUzávěrka: {lock_time_str}\nTyp: {event['type']}\nAdresa: {event['address'] or 'Nezadáno'}"
        },
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "Vybrat"},
            "action_id": f"select_event_{event['id']}",
        }
    }]

def build_participant_blocks(event: Dict[str, Any], participant: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Build blocks for participant selection and status"""
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Vyber hráče*"},
        },
        {
            "type": "actions",
            "block_id": "user_selection_section",
            "elements": [
                {
                    "type": "external_select",
                    "action_id": "user_selection",
                    "placeholder": {"type": "plain_text", "text": "Vyberte hráče..."},
                    "min_query_length": 2
                },
                {
                    "type": "button",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Potvrdit"},
                    "action_id": f"select_edit_user_{event['id']}"
                }
            ]
        },
        {"type": "divider"}
    ]

    if participant:
        coming_text = config.coming_text
        late_text = config.late_text
        notcoming_text = config.notcoming_text
        
        if event['type'] == "Trénink":
            coming_text = config.coming_training
            late_text = config.late_training
            notcoming_text = config.notcoming_training

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{participant['name']}*"
            }
        })

        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": f"{'🟢 ' if participant.get('status') == 'Coming' else ''}{coming_text}"
                    },
                    "value": f"event_{event['id']}_participant_{participant['user_id']}_coming",
                    "action_id": "event_attendance_coming",
                    **({"style": "primary"} if participant.get('status') == "Coming" else {})
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": f"{'🟡 ' if participant.get('status') == 'Late' else ''}{late_text}"
                    },
                    "value": f"event_{event['id']}_participant_{participant['user_id']}_late",
                    "action_id": "event_attendance_late",
                    **({"style": "primary"} if participant.get('status') == "Late" else {})
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": f"{'🔴 ' if participant.get('status') == 'Not Coming' else ''}{notcoming_text}"
                    },
                    "value": f"event_{event['id']}_participant_{participant['user_id']}_not_coming",
                    "action_id": "event_attendance_not_coming",
                    **({"style": "primary"} if participant.get('status') == "Not Coming" else {})
                }
            ]
        })

    return blocks

def show_edit_attendance(client: WebClient, user_id: str, logger: logging.Logger) -> None:
    """Show initial edit attendance view"""
    try:
        blocks = build_header_blocks()
        blocks.extend(build_user_category_blocks())
        client.views_publish(user_id=user_id, view={"type": "home", "blocks": blocks})
    except Exception as e:
        logger.error(f"Error showing edit attendance: {e}")
        raise EditError("Failed to show edit attendance view")

def show_events_by_day(client: WebClient, logger: logging.Logger, selected_date: datetime, user_id: str) -> None:
    """Show events for selected date"""
    try:
        events = load_events_by_date_from_db(selected_date)
        blocks = build_header_blocks()
        
        for event in events:
            blocks.extend(build_event_blocks(event))

        client.views_publish(user_id=user_id, view={"type": "home", "blocks": blocks})
    except Exception as e:
        logger.error(f"Error showing events by day: {e}")
        raise EditError("Failed to show events")

def show_edit_attendance_players(
    client: WebClient,
    logger: logging.Logger,
    event_id: str,
    view_user_id: str,
    user_id: Optional[str] = None
) -> None:
    """Show attendance edit view for event"""
    try:
        event = load_event_from_db(event_id)
        blocks = build_header_blocks()
        
        # Add event info
        start_time_str = event['start_time'].strftime('%d.%m.%Y %H:%M')
        end_time_str = event['end_time'].strftime('%d.%m.%Y %H:%M')
        lock_time_str = event['lock_time'].strftime('%d.%m.%Y %H:%M')
        
        blocks.extend([
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Docházka", "emoji": True}
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{event['name']}*\nZačátek: {start_time_str}\nKonec: {end_time_str}\nUzávěrka: {lock_time_str}\nTyp: {event['type']}\nAdresa: {event.get('address', 'Nezadáno')}"
                }
            },
            {"type": "divider"}
        ])

        participant = load_user_in_event(event_id, user_id) if user_id else None
        blocks.extend(build_participant_blocks(event, participant))

        client.views_publish(user_id=view_user_id, view={"type": "home", "blocks": blocks})
    except Exception as e:
        logger.error(f"Error showing edit attendance players: {e}")
        raise EditError("Failed to show attendance players")

def show_edit_player_category(
    client: WebClient,
    logger: logging.Logger,
    user_id: str,
    view_user_id: str
) -> None:
    """Show player category edit view"""
    try:
        blocks = build_back_blocks()
        blocks.extend(build_user_category_blocks())

        # Add user info
        user_info = load_user_from_db(user_id)
        if not user_info:
            raise EditError(f"User with ID {user_id} not found")

        user_name = user_info['name']
        user_category = user_info.get('category')

        blocks.extend([
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Úprava kategorie hráče", "emoji": True}
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{user_name}*"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": f"{':large_blue_circle: ' if user_category == 'Open' else ''}Open"
                        },
                        "value": user_id,
                        "action_id": "user_category_open",
                        **({"style": "primary"} if user_category == "Open" else {})
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": f"{'🔴 ' if user_category == 'Women' else ''}Women"
                        },
                        "value": user_id,
                        "action_id": "user_category_women",
                        **({"style": "primary"} if user_category == "Women" else {})
                    }
                ]
            },
            {"type": "divider"}
        ])

        client.views_publish(user_id=view_user_id, view={"type": "home", "blocks": blocks})
    except Exception as e:
        logger.error(f"Error showing edit player category: {e}")
        raise EditError("Failed to show player category")