from typing import Dict, List, Any, Optional
from slack_sdk import WebClient
from datetime import datetime
import logging
import config
from db import load_events_by_date_from_db, load_event_from_db, load_user_in_event, load_user_from_db

class EditError(Exception):
    """Base exception for edit related errors"""
    pass

def build_edit_attendance_modal(event: Dict[str, Any], selected_user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build modal for editing attendance"""
    coming_text = config.coming_text
    late_text = config.late_text
    notcoming_text = config.notcoming_text
    
    if event['type'] == "Trénink":
        coming_text = config.coming_training
        late_text = config.late_training
        notcoming_text = config.notcoming_training
    
    status_options = [
        {
            "text": {"type": "plain_text", "text": coming_text},
            "value": "Coming"
        },
        {
            "text": {"type": "plain_text", "text": late_text},
            "value": "Late"
        },
        {
            "text": {"type": "plain_text", "text": notcoming_text},
            "value": "Not Coming"
        }
    ]
    
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Událost:* {event['name']}\n*Typ:* {event['type']}"
            }
        },
        {
            "type": "section",
            "block_id": "user_block",
            "text": {
                "type": "mrkdwn",
                "text": "*Vyberte hráče:*"
            },
            "accessory": {
                "type": "external_select",
                "action_id": "user_select",
                "placeholder": {"type": "plain_text", "text": "Začněte psát jméno..."},
                "min_query_length": 2
            }
        }
    ]
    
    # If user is selected, add their info and pre-fill status
    if selected_user:
        # Update user select with selected value
        blocks[1]["accessory"]["initial_option"] = {
            "text": {"type": "plain_text", "text": selected_user['name']},
            "value": selected_user['user_id']
        }
        
        # Add status input with pre-selected value if exists
        status_block = {
            "type": "input",
            "block_id": "status_block",
            "element": {
                "type": "radio_buttons",
                "action_id": "status_select",
                "options": status_options
            },
            "label": {
                "type": "plain_text",
                "text": "Docházka"
            }
        }
        
        # Pre-select current status if exists
        if selected_user.get('status'):
            for option in status_options:
                if option["value"] == selected_user['status']:
                    status_block["element"]["initial_option"] = option
                    break
        
        blocks.append(status_block)
    
    return {
        "type": "modal",
        "callback_id": f"edit_attendance_{event['id']}",
        "title": {
            "type": "plain_text",
            "text": "Upravit docházku"
        },
        "submit": {
            "type": "plain_text",
            "text": "Uložit"
        },
        "close": {
            "type": "plain_text",
            "text": "Zavřít"
        },
        "blocks": blocks
    }

def show_edit_attendance_for_event(
    client: WebClient,
    logger: logging.Logger,
    event_id: str,
    trigger_id: str
) -> None:
    """Show attendance edit modal for event"""
    try:
        event = load_event_from_db(event_id)
        if not event:
            raise EditError(f"Event with ID {event_id} not found")
        
        modal = build_edit_attendance_modal(event)
        client.views_open(trigger_id=trigger_id, view=modal)
    except Exception as e:
        logger.exception(f"Error showing edit attendance modal: {e}")
        raise EditError("Failed to show attendance edit modal")

def update_edit_attendance_modal(
    client: WebClient,
    logger: logging.Logger,
    event_id: str,
    user_id: str,
    view_id: str
) -> None:
    """Update attendance edit modal with selected user's data"""
    try:
        event = load_event_from_db(event_id)
        if not event:
            raise EditError(f"Event with ID {event_id} not found")
        
        # Load user's attendance for this event
        participant = load_user_in_event(event_id, user_id)
        
        # Build user info dict
        if participant:
            selected_user = participant
        else:
            # User not found in event, load basic user info
            user_info = load_user_from_db(user_id)
            selected_user = {
                'user_id': user_id,
                'name': user_info['name'],
                'status': None
            }
        
        modal = build_edit_attendance_modal(event, selected_user)
        client.views_update(view_id=view_id, view=modal)
        
    except Exception as e:
        logger.exception(f"Error updating edit attendance modal: {e}")
        raise EditError("Failed to update attendance edit modal")

def build_player_category_modal(user_info: Dict[str, Any]) -> Dict[str, Any]:
    """Build modal for player category edit"""
    user_name = user_info['name']
    user_category = user_info.get('category', 'Open')
    
    return {
        "type": "modal",
        "callback_id": f"edit_user_category_{user_info['user_id']}",
        "title": {
            "type": "plain_text",
            "text": "Upravit kategorii"
        },
        "submit": {
            "type": "plain_text",
            "text": "Uložit"
        },
        "close": {
            "type": "plain_text",
            "text": "Zavřít"
        },
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Hráč:* {user_name}"
                }
            },
            {
                "type": "input",
                "block_id": "category_block",
                "element": {
                    "type": "radio_buttons",
                    "action_id": "category_select",
                    "options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Open"
                            },
                            "value": "Open"
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Women"
                            },
                            "value": "Women"
                        }
                    ],
                    "initial_option": {
                        "text": {
                            "type": "plain_text",
                            "text": user_category
                        },
                        "value": user_category
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Kategorie"
                }
            }
        ]
    }

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
        blocks.extend([
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
        ])
        client.views_publish(user_id=user_id, view={"type": "home", "blocks": blocks})
    except Exception as e:
        logger.exception(f"Error showing edit attendance: {e}")
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
        logger.exception(f"Error showing events by day: {e}")
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
        logger.exception(f"Error showing edit attendance players: {e}")
        raise EditError("Failed to show attendance players")

def show_edit_player_category(
    client: WebClient,
    logger: logging.Logger,
    user_id: str,
    trigger_id: str
) -> None:
    """Show player category edit modal"""
    try:
        # Get user info
        user_info = load_user_from_db(user_id)
        if not user_info:
            raise EditError(f"User with ID {user_id} not found")

        modal = build_player_category_modal(user_info)
        client.views_open(trigger_id=trigger_id, view=modal)
    except Exception as e:
        logger.exception(f"Error showing edit player category: {e}")
        raise EditError("Failed to show player category")