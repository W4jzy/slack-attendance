from typing import List, Dict, Any, Optional, Set, NamedTuple
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime
import logging
from db import *
from bot import get_usergroup_members
import config
import locale
from dataclasses import dataclass, field

# Constants
DAY_SHORT = {
    "Monday": "Po",
    "Tuesday": "Út",
    "Wednesday": "St",
    "Thursday": "Čt",
    "Friday": "Pá",
    "Saturday": "So",
    "Sunday": "Ne"
}

FILTER_DB = {
    "training": "Trénink",
    "tournament": "Turnaj",
    "other": "Ostatní"
}

MAX_BLOCKS = 50 

ATTENDANCE_MODAL_CONFIG = {
    "type": "modal",
    "callback_id": "participants_modal",
    "title": {"type": "plain_text", "text": "Účastníci"},
    "close": {"type": "plain_text", "text": "Zavřít"}
}

HISTORY_PAGE_SIZE = 50
HISTORY_MODAL_CONFIG = {
    "type": "modal",
    "title": {"type": "plain_text", "text": "Historie změn"},
    "close": {"type": "plain_text", "text": "Zavřít"}
}

EMPTY_MODAL_CONFIG = {
    "type": "modal",
    "title": {"type": "plain_text", "text": "Nevyplnění"},
    "close": {"type": "plain_text", "text": "Zavřít"}
}

class AttendanceError(Exception):
    """Base exception for attendance related errors"""
    pass

class ParticipantCount(NamedTuple):
    men: int
    women: int
    other: int
    total: int

@dataclass
class ParticipantGroup:
    men: List[str] = field(default_factory=list)
    women: List[str] = field(default_factory=list)
    other: List[str] = field(default_factory=list)

def build_attendance_blocks(
    events: List[Dict],
    user_attendance: List[Dict],
    is_admin: bool,
    page: int = 0,
    filter: str = "all"
) -> List[Dict[str, Any]]:
    """Build attendance view blocks
    
    Args:
        events: List of events to display
        user_attendance: List of user's attendance records
        is_admin: Whether the user is an admin
        page: Page number for pagination
        filter: Filter type for events
        
    Returns:
        List of block elements for the view
    """
    blocks = []
    
    # Add header blocks based on user type
    if is_admin:
        blocks.extend([
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Aktualizováno: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "overflow",
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Obnovit"
                                },
                                "value": "refresh_home_tab"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Upravit docházku"
                                },
                                "value": "go_to_edit_attendance"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Upravit nastavení"
                                },
                                "value": "go_to_settings"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Upravit události"
                                },
                                "value": "go_to_all_events"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Vyplnit hromadně"
                                },
                                "value": "mass_insert"
                            }
                        ],
                        "action_id": "main_menu_overflow"
                    }
                ]
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Filtr"
                        },
                        "action_id": f"open_filter",
                        "value": filter
                    }
                ]
            },
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Nadcházející události",
                    "emoji": True
                }
            }
        ])
    else:
        blocks.extend([
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Aktualizováno: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "overflow",
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Vyplnit hromadně"
                                },
                                "value": "mass_insert"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Obnovit"
                                },
                                "value": "refresh_home_tab"
                            }
                        ],
                        "action_id": "main_menu_overflow"
                    }
                ]
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Filtr"
                        },
                        "action_id": f"open_filter",
                        "value": filter
                    }
                ]
            },
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Nadcházející události",
                    "emoji": True
                }
            },
        ])

    events_on_page = events[page * MAX_BLOCKS // 5 : (page + 1) * MAX_BLOCKS // 5]

    # Add event blocks
    for event in events_on_page:
        is_locked = datetime.now() > event["lock_time"]
        
        coming_text = config.coming_text
        late_text = config.late_text
        notcoming_text = config.notcoming_text

        user_participant = next((p for p in user_attendance if p["event_id"] == event["id"]), None)
        user_note = (user_participant["note"] if user_participant and "note" in user_participant else "") or ""

        start_time_str = event['start_time'].strftime('%d.%m.%Y %H:%M')
        start_time_day = event['start_time'].strftime('%A')

        event_type=""
        if event['type'] == 'Trénink':
            event_type = f":large_blue_square: {event['type']}"
            coming_text = config.coming_training
            late_text = config.late_training
            notcoming_text = config.notcoming_training
        elif event['type'] == 'Turnaj':
            event_type = f":large_red_square: {event['type']}"
        else:
            event_type = f":large_yellow_square: {event['type']}"

        if config.active_men_players and config.active_women_players:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{event['name']}*\n{DAY_SHORT.get(start_time_day)} {start_time_str}" + (" - `Uzamčeno`" if is_locked else "") + f"\n{event_type}",
                },
                "accessory": {
                    "type": "overflow",
                    "options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Zobrazit účastníky"
                            },
                            "value": f"show_participants_{event['id']}"
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Zobrazit detaily"
                            },
                            "value": f"show_details_{event['id']}"
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Zobrazit historii"
                            },
                            "value": f"show_history_{event['id']}"
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Zobrazit nevyplněné"
                            },
                            "value": f"show_empty_{event['id']}"
                        }
                        
                    ],
                    "action_id": f"overflow_menu_{event['id']}"
                }
            })
        else:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{event['name']}* - {start_time_str}" + (" - Uzamčeno" if is_locked else "") + f"\n{event['type']}",
                },
                "accessory": {
                    "type": "overflow",
                    "options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Zobrazit účastníky"
                            },
                            "value": f"show_participants_{event['id']}"
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Zobrazit detaily"
                            },
                            "value": f"show_details_{event['id']}"
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Zobrazit historii"
                            },
                            "value": f"show_history_{event['id']}"
                        }                            
                    ],
                    "action_id": f"overflow_menu_{event['id']}"
                }
            })

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Docházka*"
            }
        })

        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": f"{'🟢 ' if user_participant and user_participant['status'] == 'Coming' else ''}{coming_text}"
                    },
                    "value": f"coming_{event['id']}_{page}_{filter}",
                    "action_id": "coming",
                    **({"style": "primary"} if user_participant and user_participant["status"] == "Coming" else {})
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": f"{'🟡 ' if user_participant and user_participant['status'] == 'Late' else ''}{late_text}"
                    },
                    "value": f"late_{event['id']}_{page}_{filter}",
                    "action_id": "late",
                    **({"style": "primary"} if user_participant and user_participant["status"] == "Late" else {})
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": f"{'🔴 ' if user_participant and user_participant['status'] == 'Not Coming' else ''}{notcoming_text}"
                    },
                    "value": f"notcoming_{event['id']}_{page}_{filter}",
                    "action_id": "not_coming",
                    **({"style": "primary"} if user_participant and user_participant["status"] == "Not Coming" else {})
                }
            ]
            })

        blocks.append({
            "type": "input",
            "block_id": f"reason_{event['id']}",
            "element": {
                "type": "plain_text_input",
                "action_id": f"reason_input_{event['id']}",
                "initial_value": user_note,
                "placeholder": {
                    "type": "plain_text",
                    "text": "Zadejte důvod nebo poznámku..."
                }
            },
            "label": {
                "type": "plain_text",
                "text": "Důvod / Poznámka"
            }
        })

        blocks.append({
            "type": "divider"
        })

    # Add pagination blocks
    if (page + 1) * MAX_BLOCKS // 5 < len(events):
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Pokračovat na další stránku"
                    },
                    "value": f"{page + 1}_{filter}",
                    "action_id": "next_attendance_page"
                }
            ]
        })
    
    if page > 0:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Zpět na předchozí stránku"
                    },
                    "value": f"{page - 1}_{filter}",
                    "action_id": "previous_attendance_page"
                }
            ]
        })

    return blocks

def show_attendance(
    client: WebClient,
    user_id: str,
    logger: logging.Logger,
    page: int = 0,
    filter: str = "all"
) -> None:
    """Show attendance form to user.
    
    Args:
        client: Slack WebClient instance
        user_id: User ID to show attendance to
        logger: Logger instance
        page: Page number for pagination
        filter: Filter type for events
        
    Raises:
        AttendanceError: If attendance cannot be displayed
    """
    try:
        # Load data
        events = load_events_from_db() if filter == "all" else load_events_by_type_from_db(FILTER_DB.get(filter))
        user_attendance = load_participants_for_user(user_id)
        
        # Check admin status
        attendance_admins = client.usergroups_users_list(usergroup=config.admin_group)
        is_admin = user_id in attendance_admins['users']

        # Build and publish view
        blocks = build_attendance_blocks(events, user_attendance, is_admin, page, filter)
        
        client.views_publish(
            user_id=user_id,
            view={
                "type": "home",
                "blocks": blocks
            }
        )

    except SlackApiError as e:
        logger.error(f"Slack API error in attendance: {e}")
        client.chat_postMessage(
            channel=user_id,
            text="❌ Chyba při načítání docházky. Zkuste to prosím později."
        )
    except Exception as e:
        logger.error(f"Error displaying attendance: {e}")
        client.chat_postMessage(
            channel=user_id,
            text="❌ Neočekávaná chyba při zobrazení docházky."
        )

def show_mass_insert(
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Opens a modal for mass attendance input.
    """
    try:
        user_id = body["user"]["id"]
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Vyplnit hromadně tréninky",
                    "emoji": True
                }
            },
            {
                "type": "input",
                "block_id": "attendance_selection_block",
                "element": {
                    "type": "radio_buttons",
                    "action_id": "attendance_selection",
                    "options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": f"{config.coming_training}"
                            },
                            "value": "Coming"
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": f"{config.late_training}"
                            },
                            "value": "Late"
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": f"{config.notcoming_training}"
                            },
                            "value": "Not Coming"
                        }
                    ]
                },
                "label": {
                    "type": "plain_text",
                    "text": "Docházka"
                }
            },
            {
                "type": "input",
                "block_id": "reason",
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "reason_input",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Zadejte důvod nebo poznámku..."
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Důvod / Poznámka"
                }
            }
        ]

        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "mass_input",
                "title": {
                    "type": "plain_text",
                    "text": "Vyplnit hromadně"
                },
                "close": {
                    "type": "plain_text",
                    "text": "Zavřít"
                },
                "submit": {
                    "type": "plain_text",
                    "text": "Potvrdit"
                },
                "blocks": blocks
            }
        )
    except Exception as e:
         logger.error(f"Error opening modal: {e}")

def format_participant_name(participant: Dict[str, Any]) -> str:
    """Format participant name with optional note."""
    return f"{participant['name']} - {participant['note']}" if participant.get('note') else participant['name']

def get_participant_groups(
    participants: List[Dict[str, Any]],
    status: str,
    o_active_players: List[str],
    w_active_players: List[str]
) -> ParticipantGroup:
    """Group participants by gender and status."""
    group = ParticipantGroup()
    for p in participants:
        if p["status"] != status:
            continue
            
        name = format_participant_name(p)
        if p['user_id'] in o_active_players:
            group.men.append(name)
        elif p['user_id'] in w_active_players:
            group.women.append(name)
        else:
            group.other.append(name)
    return group

def format_status_section(
    status_text: str,
    emoji: str,
    group: ParticipantGroup
) -> str:
    """Format status section with counts and names."""
    total = len(group.men) + len(group.women) + len(group.other)
    return (
        f"{emoji} {total} *{status_text}* "
        f"( {len(group.men)} :mens: {len(group.women)} :womens: )\n"
        f"{chr(10).join(group.men + group.women + group.other)}\n"
    )

def create_participant_navigation(current_page: int, event_id: str) -> Dict[str, Any]:
    """Create navigation for participant status pages."""
    elements = []
    if current_page > 0:
        elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "◀️ Předchozí"},
            "action_id": f"participants_prev_{event_id}",
            "value": str(current_page - 1),
            "style": "primary"
        })
    
    if current_page < 2:  # 3 pages total (0,1,2)
        elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "Další ▶️"},
            "action_id": f"participants_next_{event_id}",
            "value": str(current_page + 1),
            "style": "primary"
        })
    
    return {
        "type": "actions",
        "elements": elements
    } if elements else None

def create_participant_blocks(
    participants: List[Dict], 
    event: Dict,
    o_active_players: List[str],
    w_active_players: List[str],
    page: int
) -> List[Dict]:
    """Create blocks for participant view with pagination."""
    status_map = [("Coming", "🟢"), ("Late", "🟡"), ("Not Coming", "🔴")]
    current_status, emoji = status_map[page]
    
    status_text = (
        config.coming_training if current_status == "Coming" and event['type'] == "Trénink"
        else config.late_training if current_status == "Late" and event['type'] == "Trénink"
        else config.notcoming_training if current_status == "Not Coming" and event['type'] == "Trénink"
        else config.coming_text if current_status == "Coming"
        else config.late_text if current_status == "Late"
        else config.notcoming_text
    )
    
    group = get_participant_groups(participants, current_status, o_active_players, w_active_players)
    section = format_status_section(status_text, emoji, group)
    
    blocks = [{
        "type": "section",
        "text": {"type": "mrkdwn", "text": section}
    }]
    
    nav = create_participant_navigation(page, event['id'])
    if nav:
        blocks.append(nav)
    
    return blocks

def show_participants(
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger,
    event_id: str,
    page: int = 0
) -> None:
    """Show event participants in a modal view with pagination."""
    try:
        participants = load_participants_from_event(event_id)
        event = load_event_from_db(event_id)
        o_active_players, w_active_players = get_usergroup_members(client, logger)
        
        blocks = create_participant_blocks(
            participants, 
            event,
            o_active_players,
            w_active_players,
            page
        )
        
        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                **ATTENDANCE_MODAL_CONFIG,
                "blocks": blocks,
                "private_metadata": str(event_id),
                "callback_id": f"participants_view_{event_id}"
            }
        )
    except SlackApiError as e:
        logger.error(f"Slack API error showing participants: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error showing participants: {datetime.now()} - {e}")
        raise

def format_note(note: str) -> str:
    """Format note text if present."""
    return f" ({note})" if note and note.strip() else ""

def format_change_text(change: Dict[str, Any]) -> str:
    """Format history change text."""
    old_note = format_note(change['old_note'])
    new_note = format_note(change['new_note'])
    
    return (
        f"*{change['name']}*: `{change['old_status']}`{old_note} -> "
        f"`{change['new_status']}`{new_note} | {change['timestamp'].strftime('%d.%m.%Y %H:%M')}"
    )

def create_history_navigation(total_items: int, current_page: int, event_id: str) -> Dict[str, Any]:
    """Create navigation buttons for history modal."""
    total_pages = (total_items + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE
    
    elements = []
    if current_page > 0:
        elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "◀️ Předchozí"},
            "action_id": f"history_prev_{event_id}",
            "value": str(current_page - 1),
            "style": "primary"
        })
        
    if current_page < total_pages - 1:
        elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "Další ▶️"},
            "action_id": f"history_next_{event_id}", 
            "value": str(current_page + 1),
            "style": "primary"
        })
        
    return {
        "type": "actions",
        "elements": elements
    } if elements else None

def create_history_blocks(history: List[Dict[str, Any]], page: int, event_id: str) -> List[Dict[str, Any]]:
    """Create blocks for history modal with pagination."""
    start = page * HISTORY_PAGE_SIZE
    end = start + HISTORY_PAGE_SIZE
    page_items = history[start:end]
    
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": format_change_text(change)
            }
        }
        for change in page_items
    ]
    
    nav = create_history_navigation(len(history), page, event_id)
    if nav:
        blocks.append(nav)
        
    return blocks

def show_history(
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger,
    event_id: str,
    page: int = 0
) -> None:
    """Show event history in a modal view with pagination."""
    try:
        history = load_history_from_event(event_id)
        blocks = create_history_blocks(history, page, event_id)
        
        view = {
            **HISTORY_MODAL_CONFIG,
            "blocks": blocks,
            "private_metadata": event_id,
            "callback_id": f"history_view_{event_id}"
        }
        
        client.views_open(
            trigger_id=body["trigger_id"],
            view=view
        )
    except SlackApiError as e:
        logger.error(f"Slack API error showing history: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error showing history: {datetime.now()} - {e}")
        raise

def update_history_view(
    client: WebClient,
    view_id: str,
    event_id: str,
    page: int,
    logger: logging.Logger
) -> None:
    """Update history modal view with new page."""
    try:
        history = load_history_from_event(event_id)
        blocks = create_history_blocks(history, page, event_id)
        
        view = {
            **HISTORY_MODAL_CONFIG,
            "blocks": blocks,
            "private_metadata": event_id,
            "callback_id": f"history_view_{event_id}"
        }
        
        client.views_update(
            view_id=view_id,
            view=view
        )
    except Exception as e:
        logger.error(f"Error updating history view: {datetime.now()} - {e}")
        raise

def get_missing_players(
    participant_ids: Set[str],
    active_players: List[str],
    users_dict: Dict[str, str]
) -> List[str]:
    """Get sorted list of missing players."""
    missing = set(active_players) - set(participant_ids)
    return sorted(
        (users_dict.get(player_id, player_id) for player_id in missing),
        key=locale.strxfrm
    )

def create_empty_navigation(current_page: int, event_id: str) -> Dict[str, Any]:
    """Create navigation for empty players status pages."""
    elements = []
    if current_page > 0:
        elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "◀️ Předchozí"},
            "action_id": f"empty_prev_{event_id}",
            "value": str(current_page - 1),
            "style": "primary"
        })
    
    if current_page < 2:  # 3 pages total (0,1,2)
        elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "Další ▶️"},
            "action_id": f"empty_next_{event_id}",
            "value": str(current_page + 1),
            "style": "primary"
        })
    
    return {
        "type": "actions",
        "elements": elements
    } if elements else None

def create_empty_blocks(
    missing_boys: List[str],
    missing_girls: List[str],
    remaining: List[str],
    page: int = 0,
    event_id: str = ""
) -> List[Dict]:
    """Create blocks for empty modal with pagination."""
    status_map = [
        (":mens: *Nevyplnění open hráči*", missing_boys),
        (":womens: *Nevyplněné women hráčky*", missing_girls),
        ("⚪ *Nazařazení hráči*", remaining)
    ]
    current_title, current_list = status_map[page]
    
    blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{current_title}\n{current_list}"
        }
    }]
    
    nav = create_empty_navigation(page, event_id)
    if nav:
        blocks.append(nav)
        
    return blocks

def show_empty(
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger,
    event_id: str,
    page: int = 0
) -> None:
    try:
        participants = load_participants_from_event(event_id)

        participant_ids = [participant['user_id'] for participant in participants]

        o_active_players, w_active_players = get_usergroup_members(client, logger)

        users = load_users_from_db()

        users_dict = {user['user_id']: user['name'] for user in users}

        remaining_participants = []
        missing_boys = []
        missing_girls = []
        for player_id in participant_ids:
            player_name = users_dict.get(player_id, player_id)
            if player_id in o_active_players:
                o_active_players.remove(player_id)
            elif player_id in w_active_players:
                w_active_players.remove(player_id)
            else:
                remaining_participants.append(player_name)

        missing_boys = sorted((users_dict.get(player_id, player_id) for player_id in o_active_players), key=locale.strxfrm)
        missing_girls = sorted((users_dict.get(player_id, player_id) for player_id in w_active_players), key=locale.strxfrm)

        remaining_participants.sort()

        missing_boys_text = '\n'.join(missing_boys) if missing_boys else "\n"
        missing_girls_text = '\n'.join(missing_girls) if missing_girls else "\n"
        remaining_text = '\n'.join(remaining_participants) if remaining_participants else "\n"
        
        blocks = create_empty_blocks(
            missing_boys_text,
            missing_girls_text, 
            remaining_text,
            page,
            event_id
        )
        
        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                **EMPTY_MODAL_CONFIG,
                "blocks": blocks,
                "private_metadata": str(event_id),
                "callback_id": f"empty_view_{event_id}"
            }
        )
        
    except SlackApiError as e:
        logger.error(f"Slack API error showing empty: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error showing empty: {datetime.now()} - {e}")
        raise
