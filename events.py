from typing import Dict, List, Any, Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime, timedelta
import logging
from db import *

# Constants
MAX_BLOCKS_PER_PAGE = 50
DEFAULT_EVENT_TYPES = [
    {"text": {"type": "plain_text", "text": "Trénink"}, "value": "Trénink"},
    {"text": {"type": "plain_text", "text": "Turnaj"}, "value": "Turnaj"},
    {"text": {"type": "plain_text", "text": "Ostatní"}, "value": "Ostatní"}
]
MODAL_CONFIG = {
    "type": "modal",
    "callback_id": "details",
    "title": {"type": "plain_text", "text": "Detaily"},
    "close": {"type": "plain_text", "text": "Zavřít"},
}

EVENT_FIELDS = {
    "name": ("event_name_block", "event_name"),
    "type": ("event_type_block", "event_type"),
    "address": ("event_address_block", "event_address"),
    "lock_time": ("event_lock_time_block", "event_lock_time")
}

MESSAGES = {
    "SUCCESS": "Událost {name} byla upravena.",
    "ERROR": "Nastala chyba při editaci události.",
    "VALIDATION": "Prosím vyplňte všechna povinná pole."
}

MESSAGES_DUPLICATION = {
    "SUCCESS": "Událost {name} byla duplikována {count} krát.",
    "ERROR": "Nastala chyba při duplikaci události.",
    "VALIDATION": "Neplatný počet duplikátů.",
    "NOT_FOUND": "Událost nebyla nalezena."
}

class EventError(Exception):
    """Base exception for event related errors"""
    pass

def build_event_form_blocks() -> List[Dict[str, Any]]:
    """Build blocks for event creation form"""
    return [
        {
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": "Zpět"},
                "action_id": "all_events"
            }]
        },
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Přidat novou událost",
                "emoji": True
            }
        },
        {
            "type": "input",
            "block_id": "name_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "name_input",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Název události"
                }
            },
            "label": {
                "type": "plain_text",
                "text": "Název události"
            }
        },
        {
            "type": "input",
            "block_id": "start_time_block",
            "element": {
                "type": "datetimepicker",
                "action_id": "start_time_input"
            },
            "label": {
                "type": "plain_text",
                "text": "Datum a čas začátku"
            }
        },
        {
            "type": "input",
            "block_id": "end_time_block",
            "element": {
                "type": "datetimepicker",
                "action_id": "end_time_input"
            },
            "label": {
                "type": "plain_text",
                "text": "Datum a čas konce"
            }
        },
        {
            "type": "input",
            "block_id": "lock_time_block",
            "element": {
                "type": "datetimepicker",
                "action_id": "lock_time_input"
            },
            "label": {
                "type": "plain_text",
                "text": "Datum a čas uzamčení"
            }
        },
        {
            "type": "input",
            "block_id": "type_block",
            "element": {
                "type": "static_select",
                "action_id": "type_input",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Vyberte typ události"
                },
                "options": DEFAULT_EVENT_TYPES
            },
            "label": {
                "type": "plain_text",
                "text": "Typ události"
            }
        },
        {
            "type": "input",
            "block_id": "address_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "address_input",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Adresa místa (volitelná)"
                }
            },
            "label": {
                "type": "plain_text",
                "text": "Adresa místa"
            },
            "optional": True
        },
        {
            "type": "actions",
            "block_id": "submit_block",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Přidat událost"
                    },
                    "style": "primary",
                    "action_id": "submit_event"
                }
            ]
        }
    ]

def build_event_list_blocks(events: List[Dict], page: int) -> List[Dict[str, Any]]:
    """Build blocks for event list view"""
    blocks = []
    
    # Add header actions
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Přidat událost"},
                "action_id": "go_to_add_event"
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Zpět"},
                "action_id": "go_to_attendance"
            }
        ]
    })

    events_on_page = events[page * MAX_BLOCKS_PER_PAGE // 5 : (page + 1) * MAX_BLOCKS_PER_PAGE // 5]

    for event in events_on_page:
        start_time_str = event['start_time'].strftime('%d.%m.%Y %H:%M')
        end_time_str = event['end_time'].strftime('%d.%m.%Y %H:%M')
        lock_time_str = event['lock_time'].strftime('%d.%m.%Y %H:%M')

        blocks.extend([
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{event['name']}*\nZačátek: {start_time_str}\nKonec: {end_time_str}\nUzávěrka: {lock_time_str}\nTyp: {event['type']}\nAdresa: {event['address']}"
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Smazat"
                    },
                    "style": "danger",
                    "action_id": f"delete_event_{event['id']}",
                    "value": f"delete_{event['id']}_{page}",
                    "confirm": {
                        "title": {
                            "type": "plain_text",
                            "text": "Opravdu chcete smazat tuto událost?"
                        },
                        "text": {
                            "type": "mrkdwn",
                            "text": f"Událost *{event['name']}* bude nenávratně smazána."
                        },
                        "confirm": {
                            "type": "plain_text",
                            "text": "Smazat"
                        },
                        "deny": {
                            "type": "plain_text",
                            "text": "Zrušit"
                        }
                    }
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Editovat"
                        },
                        "action_id": f"edit_event_{event['id']}"
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
                            "text": "Duplikovat"
                        },
                        "action_id": f"duplicate_event_{event['id']}"
                    }
                ]
            },
            {
                "type": "divider"
            }
        ])

    if (page + 1) * MAX_BLOCKS_PER_PAGE // 5 < len(events):
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Pokračovat na další stránku"
                    },
                    "value": f"{page + 1}",
                    "action_id": "next_edit_page"
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
                    "value": f"{page - 1}",
                    "action_id": "previous_edit_page"
                }
            ]
        })

    return blocks

def add_event(client: WebClient, user_id: str, logger: logging.Logger) -> None:
    """
    Show event creation form to user.
    
    Args:
        client: Slack WebClient instance
        user_id: User ID to show form to
        logger: Logger instance
    """
    try:
        blocks = build_event_form_blocks()
        client.views_publish(
            user_id=user_id,
            view={"type": "home", "blocks": blocks}
        )
    except Exception as e:
        logger.error(f"Error showing event form: {e}")
        raise EventError("Failed to show event creation form")

def show_events(client: WebClient, user_id: str, logger: logging.Logger, page: int = 0) -> None:
    """
    Show list of events to user.
    
    Args:
        client: Slack WebClient instance 
        user_id: User ID to show events to
        logger: Logger instance
        page: Page number for pagination
    """
    try:
        events = load_events_from_db()
        upcoming_events = sorted(
            [e for e in events if e["start_time"] > datetime.now()],
            key=lambda e: e["start_time"]
        )

        if not upcoming_events:
            client.views_publish(
                user_id=user_id,
                view={
                    "type": "home",
                    "blocks": [
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Přidat událost"
                                    },
                                    "action_id": "go_to_add_event"
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Zpět"
                                    },
                                    "action_id": f"go_to_attendance"
                                }
                            ]
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Žádné nadcházející tréninky nejsou naplánované."
                            }
                        }
                    ]
                }
            )
            return

        blocks = build_event_list_blocks(upcoming_events, page)
        
        client.views_publish(
            user_id=user_id,
            view={"type": "home", "blocks": blocks}
        )

    except Exception as e:
        logger.error(f"Error displaying events: {e}")
        raise EventError("Failed to display events")

def open_duplicate_modal(client: WebClient, trigger_id: str, event_id: str) -> None:
    client.views_open(
        trigger_id=trigger_id,
        view={
            "type": "modal",
            "callback_id": f"duplicate_event_{event_id}",
            "title": {
                "type": "plain_text",
                "text": "Duplikovat událost"
            },
            "blocks": [
                {
                    "type": "input",
                    "block_id": "duplicate_count_block",
                    "element": {
                        "type": "number_input",
                        "is_decimal_allowed": False,
                        "min_value": "1",
                        "max_value": "10",
                        "action_id": "duplicate_count",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Zadejte počet duplikací"
                        }
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Počet duplikací"
                    }
                }
            ],
            "close": {
                "type": "plain_text",
                "text": "Zavřít"
            },
            "submit": {
                "type": "plain_text",
                "text": "Potvrdit"
            }
        }
    )

def open_edit_modal(client: WebClient, trigger_id: str, event_id: str, event: Dict[str, Any]) -> None:
    unix_timestamp = event['lock_time'].timestamp()

    blocks = []

    blocks.append({
        "type": "input",
        "block_id": "event_name_block",
        "element": {
            "type": "plain_text_input",
            "action_id": "event_name",
            "initial_value": event['name'],
        },
        "label": {
            "type": "plain_text",
            "text": "Název události"
        }
    })
    blocks.append({
        "type": "input",
        "block_id": "event_type_block",
        "element": {
            "type": "static_select",
            "action_id": "event_type",
            "placeholder": {
                "type": "plain_text",
                "text": "Vyberte typ události"
            },
            "options": DEFAULT_EVENT_TYPES,
            "initial_option": {
                "text": {
                    "type": "plain_text",
                    "text": event['type']
                },
                "value": event['type']
            }
        },
        "label": {
            "type": "plain_text",
            "text": "Typ"
        }
    })
    blocks.append({
        "type": "input",
        "block_id": "event_lock_time_block",
        "element": {
            "type": "datetimepicker",
            "action_id": "event_lock_time",
            "initial_date_time": unix_timestamp,
        },
        "label": {
            "type": "plain_text",
            "text": "Datum a čas uzamčení"
        }
    })

    if event['address']:
        blocks.append({
            "type": "input",
            "block_id": "event_address_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "event_address",
                "initial_value": event['address'],
            },
            "label": {
                "type": "plain_text",
                "text": "Adresa"
            },
            "optional": True,
        })
    else:
        blocks.append({
            "type": "input",
            "block_id": "event_address_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "event_address",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Adresa místa (volitelná)"
                }
            },
            "label": {
                "type": "plain_text",
                "text": "Adresa"
            },
            "optional": True,
        })

    client.views_open(
        trigger_id=trigger_id,
        view={
            "type": "modal",
            "callback_id": f"edit_event_{event_id}",
            "title": {
                "type": "plain_text",
                "text": "Editace události"
            },
            "close": {
                "type": "plain_text",
                "text": "Zavřít"
            },
            "blocks": blocks,
            "submit": {
                "type": "plain_text",
                "text": "Potvrdit"
            }
        }
    )

def format_event_details(event: Dict[str, Any]) -> str:
    """Format event details for display."""
    return (
        f"*{event['name']}*\n\n"
        f"*Začátek:* {event['start_time'].strftime('%d.%m.%Y %H:%M')}\n\n"
        f"*Konec:* {event['end_time'].strftime('%d.%m.%Y %H:%M')}\n\n"
        f"*Uzávěrka:* {event['lock_time'].strftime('%d.%m.%Y %H:%M')}\n\n"
        f"*Typ:* {event['type']}\n\n"
        f"*Adresa:* {event['address']}"
    )

def create_details_blocks(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create blocks for event details modal."""
    return [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": format_event_details(event)
        }
    }]

def show_event_details(
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger,
    event_id: str
) -> None:
    """
    Show event details in a modal.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        event_id: ID of the event
        logger: Logger instance
        
    Raises:
        SlackApiError: If modal cannot be opened
        ValueError: If event is not found
    """
    try:
        event = load_event_from_db(event_id)
        if not event:
            raise ValueError(f"Event {event_id} not found")

        blocks = create_details_blocks(event)
        modal = {**MODAL_CONFIG, "blocks": blocks}
        
        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal
        )
    except SlackApiError as e:
        logger.error(f"Slack API error showing event details: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error showing event details: {datetime.now()} - {e}")
        raise

def validate_event_data(values: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and extract event data from form values."""
    event_data = {}
    for field, (block, input_id) in EVENT_FIELDS.items():
        if field == "type":
            value = values[block][input_id]["selected_option"]["value"]
        elif field == "lock_time":
            value = values[block][input_id]["selected_date_time"]
        else:
            value = values[block][input_id]["value"]
            
        if not value and field != "address":
            return None
        event_data[field] = value
    return event_data

def handle_edit_event_submission(
    client: WebClient,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """
    Handle event edit submission.
    
    Args:
        client: Slack WebClient instance
        body: Request body with event data
        logger: Logger instance
        
    Raises:
        ValueError: If required fields are missing
        SlackApiError: If Slack API call fails
    """
    try:
        event_id = body['view']['callback_id'].split('_')[-1]
        values = body['view']['state']['values']
        user_id = body['user']['id']

        event_data = validate_event_data(values)
        if not event_data:
            raise ValueError(MESSAGES["VALIDATION"])

        update_event(
            name=event_data["name"],
            event_type=event_data["type"],
            address=event_data["address"],
            lock_timestamp=event_data["lock_time"],
            event_id=event_id
        )

        client.chat_postMessage(
            channel=user_id,
            text=MESSAGES["SUCCESS"].format(name=event_data["name"])
        )

        show_events(client, user_id, logger)
        
    except ValueError as e:
        logger.error(f"Validation error: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=str(e))
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=MESSAGES["ERROR"])
    except Exception as e:
        logger.error(f"Error editing event: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=MESSAGES["ERROR"])

def validate_duplicate_count(count: int) -> bool:
    """Validate duplicate count is within allowed range."""
    return 0 < count <= 52  # Max one year of weekly duplicates

def duplicate_event(event: Dict[str, Any], weeks_offset: int) -> Dict[str, Any]:
    """Create duplicate of event with offset."""
    new_event = event.copy()
    offset = timedelta(weeks=weeks_offset)
    
    new_event['start_time'] += offset
    new_event['end_time'] += offset
    new_event['lock_time'] += offset
    
    return new_event

def handle_duplicate_event_submission(
    client: WebClient,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """
    Handle event duplication submission.
    
    Args:
        client: Slack WebClient instance
        body: Request body with duplication data
        logger: Logger instance
        
    Raises:
        ValueError: If duplicate count is invalid
        SlackApiError: If Slack API call fails
    """
    try:
        event_id = body['view']['callback_id'].split('_')[-1]
        duplicate_count = int(body['view']['state']['values']
                            ['duplicate_count_block']['duplicate_count']['value'])
        
        if not validate_duplicate_count(duplicate_count):
            raise ValueError(MESSAGES_DUPLICATION["VALIDATION"])

        original_event = load_event_from_db(event_id)
        if not original_event:
            raise ValueError(MESSAGES_DUPLICATION["NOT_FOUND"])

        for i in range(duplicate_count):
            new_event = duplicate_event(original_event, i + 1)
            duplicate_event_to_db(
                name=new_event['name'],
                start_time=new_event['start_time'],
                end_time=new_event['end_time'],
                lock_time=new_event['lock_time'],
                event_type=new_event['type'],
                address=new_event['address']
            )

        client.chat_postMessage(
            channel=body['user']['id'],
            text=MESSAGES_DUPLICATION["SUCCESS"].format(
                name=original_event['name'],
                count=duplicate_count
            )
        )

        show_events(client, body['user']['id'], logger)
        
    except ValueError as e:
        logger.error(f"Validation error: {datetime.now()} - {e}")
        client.chat_postMessage(
            channel=body['user']['id'],
            text=str(e)
        )
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error duplicating event: {datetime.now()} - {e}")
        client.chat_postMessage(
            channel=body['user']['id'],
            text=MESSAGES_DUPLICATION["ERROR"]
        )

