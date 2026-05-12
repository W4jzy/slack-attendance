import os
import re
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import Dict, Any, Tuple, List, Callable, Optional
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from db import *
from attendance import *
from events import *
from export import *
from settings import *
from edit import *
from reminders import *
import config
import calendar
import locale

load_dotenv()

# Initialize locale
locale.setlocale(locale.LC_COLLATE, 'cs_CZ.utf8')

# Constants
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
UNKNOWN_USER = "Unknown"
DEFAULT_DATE_FORMAT = '%Y-%m-%d'
DEFAULT_PAGE = 0
DEFAULT_FILTER = "all"
LOCKED_MESSAGE = "Smůla, už je po uzávěrce. Co to příště zkusit včas?"
MAX_RESULTS = 100

ATTENDANCE_STATUSES = {
    "event_attendance_coming": "Coming",
    "event_attendance_late": "Late",
    "event_attendance_not_coming": "Not Coming",
    "coming": "Coming",
    "late": "Late",
    "not_coming": "Not Coming"
}

ATTENDANCE_OPTIONS = [
    {
        "text": {"type": "plain_text", "text": "{coming_training}"},
        "value": "Coming"
    },
    {
        "text": {"type": "plain_text", "text": "{late_training}"},
        "value": "Late"
    },
    {
        "text": {"type": "plain_text", "text": "{notcoming_training}"},
        "value": "Not Coming"
    }
]

DEFAULT_SETTINGS = {
    "coming_text": "Chci",
    "late_text": "Možná",
    "notcoming_text": "Nechci",
    "coming_training": "Přijdu",
    "late_training": "Přijdu později",
    "notcoming_training": "Nepřijdu"
}

FILTER_OPTIONS = {
    "all": "Zobrazit vše",
    "training": "Tréninky",
    "tournament": "Turnaje",
    "other": "Ostatní"
}

FILTER_MODAL = {
    "type": "modal",
    "callback_id": "filter_events",
    "title": {"type": "plain_text", "text": "Nastavit filtr"},
    "close": {"type": "plain_text", "text": "Zavřít"},
    "submit": {"type": "plain_text", "text": "Potvrdit"}
}

FILTER_BLOCKS = {
    "SELECTION": "filter_selection_block",
    "ACTION": "filter_selection"
}

REQUIRED_FIELDS = {
    "name": ("name_block", "name_input"),
    "start_time": ("start_time_block", "start_time_input"),
    "end_time": ("end_time_block", "end_time_input"),
    "lock_time": ("lock_time_block", "lock_time_input"),
    "event_type": ("type_block", "type_input")
}

BLOCK_IDS = {
    "SELECTION": "attendance_selection_block",
    "REASON": "reason"
}

DELETE_EVENT_PATTERN = re.compile(r"delete_event_(\d+)")
EDIT_EVENT_PATTERN = re.compile(r"^edit_event_\d+$")
DUPLICATE_EVENT_PATTERN = re.compile(r"^duplicate_event_\d+$")
SELECT_EVENT_PATTERN = re.compile(r"^select_event_\d+$")
SELECT_USER_PATTERN = re.compile(r"select_edit_user_(\d+)")

MESSAGES = {
    "ERROR": "Prosím, vyplňte všechna povinná pole.",
    "SUCCESS": "Událost {name} byla úspěšně přidána!",
    "DELETE_SUCCESS": "Událost byla úspěšně smazána!",
    "DELETE_ERROR_MESSAGE": "Chyba při mazání události. Zkuste to prosím později.",
    "SHARE_SUCCESS": "Událost byla úspěšně sdílena!"
}

ERROR_MESSAGES = {
    "INVALID_ACTION": "Neplatná akce.",
    "INVALID_NUMBER": "Prosím zadejte platné číslo.",
    "INVALID_RANGE": "Počet duplikátů musí být mezi 1 a 52.",
    "GENERAL_ERROR": "Nastala chyba při duplikaci události.",
    "INVALID_ID": "Neplatné ID události.",
    "EVENT_NOT_FOUND": "Událost nebyla nalezena.",
    "EDIT_ERROR": "Chyba při úpravě události.",
    "INVALID_DATE": "Neplatné datum.",
    "DATE_ORDER": "Datum začátku musí být před datem konce.",
    "EXPORT_ERROR": "Chyba při exportu dat.",
    "USER_NOT_FOUND": "Uživatel nebyl nalezen.",
    "GENERAL_ERROR2": "Nastala chyba při zobrazení událostí.",
    "SELECTION_ERROR": "Chyba při výběru uživatele.",
    "USER_SEARCH": "Chyba při vyhledávání uživatelů.",
    "NO_USERS": "Žádní uživatelé nenalezeni.",
    "INVALID_SELECTION": "Neplatný výběr docházky.",
    "DATE_ERROR": "Chyba při načítání dat.",
    "DB_ERROR": "Chyba při ukládání docházky.",
    "SHARE_ERROR": "Chyba při sdílení události.",
    "ATTENDANCE_ERROR": "Chyba při vyplnění docházky.",
}

EXPORT_BLOCKS = {
    "START_DATE": "start_date",
    "END_DATE": "end_date"
}

DATE_BLOCKS = {
    "PICKER": "date_picker",
    "SELECT": "date_select"
}

MENU_ACTIONS: Dict[str, Callable] = {
    "go_to_add_event": lambda ack, body, client, logger: go_to_add_event(ack, body, client, logger),
    "go_to_all_events": lambda ack, body, client, logger: go_to_all_events(ack, body, client, logger),
    "go_to_settings": lambda ack, body, client, logger: go_to_settings(body, client, logger),
    "go_to_edit_attendance": lambda ack, body, client, logger: go_to_edit_attendance(ack, body, client, logger),
    "go_to_reminders": lambda ack, body, client, logger: go_to_reminders(ack, body, client, logger),
    "mass_insert": lambda ack, body, client, logger: show_mass_insert(body, client, logger),
    "refresh_home_tab": lambda ack, body, client, logger: handle_refresh(ack, body, client, logger)
}

OVERFLOW_ACTIONS: Dict[str, Callable] = {
    "show_details": lambda body, client, logger, event_id: show_event_details(body, client, logger, event_id),
    "show_participants": lambda body, client, logger, event_id: show_participants(body, client, logger, event_id),
    "show_history": lambda body, client, logger, event_id: show_history(body, client, logger, event_id),
    "show_empty": lambda body, client, logger, event_id: show_empty(body, client, logger, event_id),
    "share_event": lambda body, client, logger, event_id: share_event(body, client, logger, event_id)
}

MENU_EDIT: Dict[str, Callable] = {
    "export_participants": lambda ack, body, client, logger: export_participants(ack, body, client, logger),
}


class SlackBotError(Exception):
    """Base exception for slack bot related errors"""
    pass

# Initialize app and client
app = App(token=SLACK_BOT_TOKEN)
client = WebClient(token=SLACK_BOT_TOKEN)

# Initialize logger for reminder loop
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def get_user_by_id(
    user_id: str,
    logger: Optional[logging.Logger] = None
) -> str:
    """
    Get user's real name by their Slack ID.
    
    Args:
        user_id: Slack user ID
        logger: Optional logger instance
        
    Returns:
        str: User's real name or "Unknown" if not found
        
    Raises:
        SlackApiError: If Slack API call fails
    """
    try:
        response = client.users_info(user=user_id)
        return response['user']['profile'].get('real_name', UNKNOWN_USER)
        
    except SlackApiError as e:
        if logger:
            logger.error(f"Slack API error getting user: {datetime.now()} - {e}")
        return UNKNOWN_USER
    except Exception as e:
        if logger:
            logger.error(f"Unexpected error getting user: {datetime.now()} - {e}")
        return UNKNOWN_USER

def get_today_and_last_day_of_next_month() -> Tuple[datetime, str]:
    """
    Get today's date and last day of next month.
    
    Returns:
        Tuple[datetime, str]: Today's datetime and last day of next month as string
    """
    today = datetime.now()
    
    next_month = 1 if today.month == 12 else today.month + 1
    next_year = today.year + 1 if today.month == 12 else today.year
    
    last_day = calendar.monthrange(next_year, next_month)[1]
    last_day_date = datetime(
        next_year,
        next_month,
        last_day
    ).strftime(DEFAULT_DATE_FORMAT)
    
    return today, last_day_date

def get_user_info(client: WebClient, user_id: str) -> Tuple[str, str]:
    """
    Fetch user information from Slack.
    
    Args:
        client: Slack WebClient instance
        user_id: User ID to fetch info for
        
    Returns:
        Tuple containing username and real name
    """
    try:
        user_info = client.users_info(user=user_id)
        display_name = user_info["user"]["profile"].get("display_name")
        real_name = user_info["user"]["profile"].get("real_name")
        return display_name if display_name else real_name, real_name
    except SlackApiError as e:
        raise SlackBotError(f"Failed to fetch user info: {e}")

def show_loading_view(client: WebClient, user_id: str) -> None:
    """
    Display loading message in home tab.
    
    Args:
        client: Slack WebClient instance
        user_id: User ID to show loading message to
    """
    client.views_publish(
        user_id=user_id,
        view={
            "type": "home",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ":hourglass_flowing_sand: *Načítám data...* Prosím chvilku strpení."
                    }
                }
            ]
        }
    )

def show_category_selection(client: WebClient, user_id: str, logger: logging.Logger) -> None:
    """
    Display category selection in home tab.
    
    Args:
        client: Slack WebClient instance
        user_id: User ID to show category selection to
        logger: Logger instance
    """
    try:
        client.views_publish(
            user_id=user_id,
            view={
                "type": "home",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Vyberte kategorii:*"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":large_blue_circle: Open"
                                },
                                "action_id": "select_open_category"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":red_circle: Women"
                                },
                                "action_id": "select_women_category"
                            }
                        ]
                    }
                ]
            }
        )
    except SlackApiError as e:
        logger.error(f"Slack API error showing category selection: {datetime.now()} - {e}")

    except Exception as e:
        logger.error(f"Error showing category selection: {datetime.now()} - {e}")



def update_home_view(client: WebClient, user_id: str, logger: logging.Logger) -> None:
    """
    Update home view with attendance information.
    
    Args:
        client: Slack WebClient instance
        user_id: User ID to update view for
        logger: Logger instance
    """
    try:
        config.load_settings()
        username, real_name = get_user_info(client, user_id)
        show_loading_view(client, user_id)
        check_user(user_id, real_name)
        if check_user_category(user_id):
            show_attendance(client, user_id, logger)
        else:
            show_category_selection(client, user_id, logger)
    except (SlackApiError, SlackBotError) as e:
        logger.error(f"Error updating home view: {e}")
        raise SlackBotError(f"Failed to update home view: {e}")

@app.action("refresh_home_tab")
def handle_refresh(ack: Any, body: Dict[str, Any], client: WebClient, logger: logging.Logger) -> None:
    """Handle refresh action in home tab"""
    try:
        ack()
        user_id = body["user"]["id"]
        update_home_view(client, user_id, logger)
    except Exception as e:
        logger.error(f"Error in refresh handler: {datetime.now()} - {e}")

@app.event("app_home_opened")
def handle_home_opened(event: Dict[str, Any], logger: logging.Logger) -> None:
    """Handle home tab opened event"""
    try:
        if event["tab"] == "home":
            user_id = event["user"]
            update_home_view(client, user_id, logger)
    except Exception as e:
        logger.error(f"Error in home opened handler: {datetime.now()} - {e}")

@app.action("main_menu_overflow")
def handle_main_menu_overflow(ack: Any, body: Dict[str, Any], client: WebClient, logger: logging.Logger) -> None:
    """Handle main menu overflow action selection."""
    try:
        ack()
        selected_option = body['actions'][0]['selected_option']['value']
        if action_handler := MENU_ACTIONS.get(selected_option):
            action_handler(ack, body, client, logger)
    except Exception as e:
        logger.error(f"Error in menu overflow: {datetime.now()} - {e}")

@app.action("events_menu_overflow")
def handle_events_menu_overflow(ack: Any, body: Dict[str, Any], client: WebClient, logger: logging.Logger) -> None:
    """Handle events menu overflow action selection."""
    try:
        ack()
        selected_option = body['actions'][0]['selected_option']['value']
        if action_handler := MENU_ACTIONS.get(selected_option):
            action_handler(ack, body, client, logger)
    except Exception as e:
        logger.error(f"Error in events menu overflow: {datetime.now()} - {e}")

@app.action("go_to_add_event")
def go_to_add_event(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle add event action.
    """
    try:
        ack()
        trigger_id = body["trigger_id"]
        add_event(client, trigger_id, logger)
    except SlackApiError as e:
        logger.error(f"Slack API error in add event: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling add event: {datetime.now()} - {e}")
        raise

@app.action("all_events")
def all_events(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle all events action.
    """
    try:
        ack()
        if not (user_id := body.get("user", {}).get("id")):
            raise ValueError("User ID not found in request body")
        go_to_all_events(ack, body, client, logger)
    except SlackApiError as e:
        logger.error(f"Slack API error in all events: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling all events: {datetime.now()} - {e}")
        raise

@app.action("go_to_edit_attendance")
def go_to_edit_attendance(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle edit attendance action.
    """
    try:
        ack()
        if not (user_id := body.get("user", {}).get("id")):
            raise ValueError("User ID not found in request body")
        show_edit_attendance(client, user_id, logger)
    except SlackApiError as e:
        logger.error(f"Slack API error in edit attendance: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling edit attendance: {datetime.now()} - {e}")
        raise

@app.action("go_to_reminders")
def go_to_reminders(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle action to show reminders list.
    """
    try:
        ack()
        if not (user_id := body.get("user", {}).get("id")):
            raise ValueError("User ID not found in request body")
        show_reminders_list(client, user_id, logger)
    except SlackApiError as e:
        logger.error(f"Slack API error in reminders: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling reminders: {datetime.now()} - {e}")
        raise

@app.action("edit_overflow")
def handle_edit_overflow(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle edit overflow menu actions.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        selected_option = body['actions'][0]['selected_option']['value']
        
        if action_handler := MENU_EDIT.get(selected_option):
            action_handler(ack, body, client, logger)
        else:
            logger.error(f"Unknown overflow action: {selected_option}")
            
    except SlackApiError as e:
        logger.error(f"Slack API error in overflow: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling overflow: {datetime.now()} - {e}")
        raise

@app.action("go_to_all_events")
def go_to_all_events(
    ack: Any,
    body: Dict[str, Any], 
    client: WebClient, 
    logger: logging.Logger
) -> None:
    """
    Navigate to all events view with pagination.
    """
    try:
        ack()
        # Extract page from button value if present, otherwise use default
        page = DEFAULT_PAGE
        if "actions" in body and body["actions"]:
            value = body["actions"][0].get("value")
            if value and value.isdigit():
                page = int(value)
        
        if page < 0:
            raise ValueError("Page number cannot be negative")
            
        if not (user_id := body.get("user", {}).get("id")):
            raise ValueError("User ID not found in request body")
            
        show_events(client, user_id, logger, page)
        
    except SlackApiError as e:
        logger.error(f"Slack API error in events view: {datetime.now()} - {e.response['error']}")
        raise
    except ValueError as e:
        logger.error(f"Invalid input: {datetime.now()} - {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in events view: {datetime.now()} - {str(e)}")
        raise

@app.action(re.compile(r"overflow_menu_(\d+)"))
def handle_overflow_menu(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle overflow menu actions.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        selected_option = body['actions'][0]['selected_option']['value']
        action, event_id = selected_option.rsplit('_', 1)
        
        if action_handler := OVERFLOW_ACTIONS.get(action):
            action_handler(body, client, logger, event_id)
        else:
            logger.error(f"Unknown overflow action: {action}")
            
    except SlackApiError as e:
        logger.error(f"Slack API error in overflow menu: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling overflow menu: {datetime.now()} - {e}")
        raise

def parse_attendance_value(value: str) -> Tuple[int, str]:
    """Parse event_id and user_id from action value."""
    parts = value.split('_')
    return int(parts[1]), parts[3]

def handle_attendance_action(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger,
    status: str
) -> None:
    """
    Handle attendance action.
    
    Args:
        ack: Acknowledge function
        body: Request body
        logger: Logger instance
        status: Attendance status to set
    """
    try:
        ack()
        action_value = body["actions"][0]["value"]
        event_id, user_id = parse_attendance_value(action_value)
        view_id = body["user"]["id"]
        
        insert_participation(event_id, user_id, status)
        show_edit_attendance_players(client, logger, event_id, view_id, user_id)
        
    except ValueError as e:
        logger.error(f"Invalid action value format: {datetime.now()} - {e}")
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
    except Exception as e:
        logger.error(f"Error handling {status.lower()} action: {datetime.now()} - {e}")

@app.action("event_attendance_coming")
def event_coming_action(ack: Any, body: Dict[str, Any], logger: logging.Logger) -> None:
    """Handle coming attendance action."""
    handle_attendance_action(ack, body, logger, ATTENDANCE_STATUSES["event_attendance_coming"])

@app.action("event_attendance_late")
def event_late_action(ack: Any, body: Dict[str, Any], logger: logging.Logger) -> None:
    """Handle late attendance action."""
    handle_attendance_action(ack, body, logger, ATTENDANCE_STATUSES["event_attendance_late"])

@app.action("event_attendance_not_coming")
def event_not_coming_action(ack: Any, body: Dict[str, Any], logger: logging.Logger) -> None:
    """Handle not coming attendance action."""
    handle_attendance_action(ack, body, logger, ATTENDANCE_STATUSES["event_attendance_not_coming"])

@app.action("go_to_attendance")
def go_to_attendance_action(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """
    Handle go to attendance action.
    
    Args:
        ack: Acknowledge function
        body: Request body
        logger: Logger instance
    """
    try:
        ack()
        if not (user_id := body.get("user", {}).get("id")):
            raise ValueError("User ID not found in request body")
        show_attendance(client, user_id, logger)
    except Exception as e:
        logger.error(f"Error in attendance action: {datetime.now()} - {e}")
        raise

def go_to_attendance_page(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger,
    page: int = DEFAULT_PAGE,
    filter: str = DEFAULT_FILTER
) -> None:
    """
    Navigate to specific attendance page.
    
    Args:
        ack: Acknowledge function
        body: Request body
        logger: Logger instance
        page: Page number, defaults to 0
        filter: Filter type, defaults to 'all'
    """
    try:
        ack()
        if not (user_id := body.get("user", {}).get("id")):
            raise ValueError("User ID not found in request body")
        if page < 0:
            raise ValueError("Page number cannot be negative")
        show_attendance(client, user_id, logger, page, filter)
    except Exception as e:
        logger.error(f"Error in attendance page: {datetime.now()} - {e}")
        raise

def parse_participation_value(value: str) -> Tuple[int, int, str]:
    """Parse event_id, page and filter from action value."""
    parts = value.split('_')
    return int(parts[1]), int(parts[2]), parts[3]

def handle_participation_action(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger,
    status: str
) -> None:
    """
    Handle participation action (coming/late/not coming).
    
    Args:
        ack: Acknowledge function
        body: Request body
        logger: Logger instance
        status: Attendance status to set
    """
    try:
        ack()
        action_value = body["actions"][0]["value"]
        event_id, page, filter = parse_participation_value(action_value)
        user_id = body["user"]["id"]
        
        note = body['view']['state']['values'][f'reason_{event_id}'][f'reason_input_{event_id}']['value']
        event = load_event_from_db(event_id)
        
        if datetime.now() > event["lock_time"]:
            client.chat_postMessage(channel=user_id, text=LOCKED_MESSAGE)
        else:
            insert_participation(event_id, user_id, status, note)
            
        go_to_attendance_page(ack, body, logger, page, filter)
        
    except SlackApiError as e:
        logger.error(f"Slack API error in {status} action: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling {status} action: {datetime.now()} - {e}")
        raise

@app.action("coming")
def coming_action(ack: Any, body: Dict[str, Any], logger: logging.Logger) -> None:
    """Handle coming attendance action."""
    handle_participation_action(ack, body, logger, ATTENDANCE_STATUSES["coming"])

@app.action("late")
def late_action(ack: Any, body: Dict[str, Any], logger: logging.Logger) -> None:
    """Handle late attendance action."""
    handle_participation_action(ack, body, logger, ATTENDANCE_STATUSES["late"])

@app.action("not_coming")
def not_coming_action(ack: Any, body: Dict[str, Any], logger: logging.Logger) -> None:
    """Handle not coming attendance action."""
    handle_participation_action(ack, body, logger, ATTENDANCE_STATUSES["not_coming"])

def create_filter_options(saved_filter: str) -> List[Dict[str, Any]]:
    """Create filter radio button options."""
    return [
        {
            "text": {"type": "plain_text", "text": text},
            "value": value
        }
        for value, text in FILTER_OPTIONS.items()
    ]

def build_filter_blocks(saved_filter: str) -> List[Dict[str, Any]]:
    """Build blocks for filter modal."""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Nastavit filtr",
                "emoji": True
            }
        },
        {
            "type": "input",
            "block_id": "filter_selection_block",
            "element": {
                "type": "radio_buttons",
                "action_id": "filter_selection",
                "options": create_filter_options(saved_filter),
                "initial_option": {
                    "text": {
                        "type": "plain_text",
                        "text": FILTER_OPTIONS.get(saved_filter, FILTER_OPTIONS["all"])
                    },
                    "value": saved_filter
                }
            },
            "label": {"type": "plain_text", "text": "Typ události"}
        }
    ]

@app.action("open_filter")
def handle_open_filter(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle opening filter modal.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        user_id = body["user"]["id"]
        saved_filter = body["actions"][0]["value"]
        
        blocks = build_filter_blocks(saved_filter)
        modal = {**FILTER_MODAL, "blocks": blocks}
        
        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal
        )
    except SlackApiError as e:
        logger.error(f"Slack API error opening filter modal: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error opening filter modal: {datetime.now()} - {e}")
        raise

@app.view("filter_events")
def handle_filter_events(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """
    Handle filter events view submission.
    
    Args:
        ack: Acknowledge function
        body: Request body with filter selection
        logger: Logger instance
        
    Raises:
        ValueError: If user ID is not found
        SlackApiError: If Slack API call fails
    """
    try:
        ack()
        if not (user_id := body.get("user", {}).get("id")):
            raise ValueError("User ID not found in request body")

        values = body["view"]["state"]["values"]
        selection_block = values.get(FILTER_BLOCKS["SELECTION"])
        
        selection = (
            selection_block[FILTER_BLOCKS["ACTION"]]["selected_option"]["value"]
            if selection_block
            else DEFAULT_FILTER
        )

        show_attendance(client, user_id, logger, DEFAULT_PAGE, selection)

    except SlackApiError as e:
        logger.error(f"Slack API error in filter events: {datetime.now()} - {e}")
        raise
    except ValueError as e:
        logger.error(f"Invalid input: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in filter events: {datetime.now()} - {e}")
        raise

def parse_page_value(value: str) -> Tuple[int, str]:
    """Parse page number and filter from action value."""
    parts = value.split('_')
    return int(parts[0]), parts[1]

def handle_page_action(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger,
    page_type: str
) -> None:
    """
    Handle pagination action for attendance view.
    
    Args:
        ack: Acknowledge function
        body: Request body
        logger: Logger instance
        page_type: Type of pagination (next/previous)
    """
    try:
        ack()
        action_value = body["actions"][0]["value"]
        page, filter = parse_page_value(action_value)
        
        if not (user_id := body.get("user", {}).get("id")):
            raise ValueError("User ID not found in request body")
            
        if page < 0:
            raise ValueError("Page number cannot be negative")
            
        show_attendance(client, user_id, logger, page, filter)
        
    except SlackApiError as e:
        logger.error(f"Slack API error in {page_type} page: {datetime.now()} - {e}")
        raise
    except ValueError as e:
        logger.error(f"Invalid input for {page_type} page: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling {page_type} page: {datetime.now()} - {e}")
        raise

@app.action("next_attendance_page")
def next_attendance_page_action(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """Handle next page action."""
    handle_page_action(ack, body, logger, "next")

@app.action("previous_attendance_page")
def previous_attendance_page_action(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """Handle previous page action."""
    handle_page_action(ack, body, logger, "previous")

def handle_edit_page_action(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger,
    page_type: str
) -> None:
    """
    Handle edit page navigation.
    
    Args:
        ack: Acknowledge function
        body: Request body
        logger: Logger instance
        page_type: Type of pagination (next/previous)
    """
    try:
        ack()
        page = int(body['actions'][0]['value'])
        
        if not (user_id := body.get("user", {}).get("id")):
            raise ValueError("User ID not found in request body")
            
        if page < 0:
            raise ValueError("Page number cannot be negative")
            
        show_events(client, user_id, logger, page)
        
    except ValueError as e:
        logger.error(f"Invalid {page_type} page value: {datetime.now()} - {e}")
        raise
    except SlackApiError as e:
        logger.error(f"Slack API error in {page_type} page: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling {page_type} page: {datetime.now()} - {e}")
        raise

@app.action("next_edit_page")
def handle_next_edit_page(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """Handle next page action."""
    handle_edit_page_action(ack, body, logger, "next")

@app.action("previous_edit_page")
def handle_previous_edit_page(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """Handle previous page action."""
    handle_edit_page_action(ack, body, logger, "previous")

def get_selected_option_value(values: Dict[str, Any], block_id: str, action_id: str) -> str:
    """Get selected option value from block."""
    selected = values.get(block_id, {}).get(action_id, {}).get('selected_option')
    return selected.get('value', '') if selected else ''

def get_input_value(values: Dict[str, Any], block_id: str, input_id: str, default: str) -> str:
    """Get input value with default."""
    return values.get(block_id, {}).get(input_id, {}).get('value') or default

def save_settings_to_config(settings: Dict[str, str]) -> None:
    """Save settings to config."""
    for key, value in settings.items():
        config.set_setting(key, value)
    config.save_settings()

@app.view("settings_modal")
def handle_save_settings(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """
    Handle settings modal submission.
    
    Args:
        ack: Acknowledge function
        body: Request body containing settings
        logger: Logger instance
    """
    try:
        ack()
        values = body['view']['state']['values']

        # Get text inputs
        settings = {}
        for key, default in DEFAULT_SETTINGS.items():
            settings[key] = get_input_value(
                values, f'{key}_block', f'{key}_input', default
            )

        save_settings_to_config(settings)

    except SlackApiError as e:
        logger.error(f"Slack API error in settings: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling save settings: {datetime.now()} - {e}")
        raise

def validate_event_fields(values: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and extract event fields."""
    event_data = {}
    for field, (block, input_id) in REQUIRED_FIELDS.items():
        if field.endswith('_time'):
            value = values.get(block, {}).get(input_id, {}).get("selected_date_time")
        elif field == 'event_type':
            value = values.get(block, {}).get(input_id, {}).get("selected_option", {}).get("value")
        else:
            value = values.get(block, {}).get(input_id, {}).get("value")
            
        if not value:
            return None
        event_data[field] = value
    
    # Optional fields
    event_data["address"] = values.get("address_block", {}).get("address_input", {}).get("value", "")
    return event_data

@app.view("add_event_modal")
def handle_submit_event(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """
    Handle event submission from modal.
    
    Args:
        ack: Acknowledge function
        body: Request body
        logger: Logger instance
    """
    try:
        values = body["view"]["state"]["values"]
        
        event_data = validate_event_fields(values)
        if not event_data:
            ack(response_action="errors", errors={
                "name_block": MESSAGES["ERROR"]
            })
            return

        ack()
        add_event_to_db(**event_data)
        
    except SlackApiError as e:
        logger.error(f"Slack API error in event submission: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling event submission: {datetime.now()} - {e}")
        raise

def parse_delete_action(value: str) -> Tuple[int, int]:
    """Parse event_id and page from delete action value."""
    parts = value.split('_')
    return int(parts[1]), int(parts[2])

@app.action(DELETE_EVENT_PATTERN)
def delete_event_action(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle event deletion action.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
        
    Raises:
        ValueError: If event ID is invalid
        SlackApiError: If Slack API call fails
    """
    try:
        ack()
        if not (user_id := body.get("user", {}).get("id")):
            raise ValueError("User ID not found in request body")
            
        action_value = body["actions"][0]["value"]
        event_id, page = parse_delete_action(action_value)
        
        delete_event(event_id)
        
        client.chat_postMessage(
            channel=user_id,
            text=MESSAGES["DELETE_SUCCESS"]
        )
        
        go_to_all_events(ack, body, client, logger, page)
        
    except ValueError as e:
        logger.error(f"Invalid delete action value: {datetime.now()} - {e}")
        raise
    except SlackApiError as e:
        logger.error(f"Slack API error in delete event: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error deleting event: {datetime.now()} - {e}")
        client.chat_postMessage(
            channel=user_id,
            text=MESSAGES["DELETE_ERROR_MESSAGE"]
        )
        raise

@app.action(EDIT_EVENT_PATTERN)
def handle_edit_event_action(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle edit event action.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        action_id = body['actions'][0]['action_id']
        event_id = action_id.split('_')[-1]

        if not event_id.isdigit():
            raise ValueError(ERROR_MESSAGES["INVALID_ID"])

        event = load_event_from_db(event_id)
        if not event:
            raise ValueError(ERROR_MESSAGES["EVENT_NOT_FOUND"])

        open_edit_modal(client, body['trigger_id'], event_id, event)
        
    except ValueError as e:
        logger.error(f"Validation error: {datetime.now()} - {e}")
        raise
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling edit event: {datetime.now()} - {e}")
        raise

@app.view(EDIT_EVENT_PATTERN)
def handle_edit_submission(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle edit event submission.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        handle_edit_event_submission(client, body, logger)
        
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
        client.chat_postMessage(
            channel=body["user"]["id"],
            text=ERROR_MESSAGES["EDIT_ERROR"]
        )
    except Exception as e:
        logger.error(f"Error handling submission: {datetime.now()} - {e}")
        client.chat_postMessage(
            channel=body["user"]["id"],
            text=ERROR_MESSAGES["EDIT_ERROR"]
        )

@app.action(re.compile(r"^duplicate_event_\d+$"))
def handle_duplicate_action(ack, body, client, logger):
    ack()
    try:
        action_id = body['actions'][0]['action_id']
        event_id = action_id.split('_')[-1]

        open_duplicate_modal(client, body['trigger_id'], event_id)
    except Exception as e:
        logger.error(f"Error handling duplicate event action: {datetime.now()} - {e}")


@app.view(re.compile(r"^duplicate_event_\d+$"))
def handle_duplicate_submission(ack, body, client, logger):
    ack() 

    try:
        duplicate_count_str = body['view']['state']['values']['duplicate_count_block']['duplicate_count']['value']

        if not duplicate_count_str.isdigit():
            return ack(response_action="errors", errors={
                "duplicate_count_block": "Prosím zadejte platné číslo."
            })

        handle_duplicate_event_submission(client, body, logger)
    except Exception as e:
        logger.error(f"Error handling duplicate event submission: {datetime.now()} - {e}")

@app.action(DUPLICATE_EVENT_PATTERN)
def handle_duplicate_action(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle duplicate event action.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        action_id = body['actions'][0]['action_id']
        event_id = action_id.split('_')[-1]

        if not event_id.isdigit():
            raise ValueError("Invalid event ID")

        open_duplicate_modal(client, body['trigger_id'], event_id)
        
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling duplicate action: {datetime.now()} - {e}")
        raise

@app.view(DUPLICATE_EVENT_PATTERN)
def handle_duplicate_submission(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle duplicate event submission.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        duplicate_count_str = body['view']['state']['values']['duplicate_count_block']['duplicate_count']['value']

        if not duplicate_count_str.isdigit():
            return ack(response_action="errors", errors={
                "duplicate_count_block": ERROR_MESSAGES["INVALID_NUMBER"]
            })

        duplicate_count = int(duplicate_count_str)
        if not 0 < duplicate_count <= 52:
            return ack(response_action="errors", errors={
                "duplicate_count_block": ERROR_MESSAGES["INVALID_RANGE"]
            })

        ack()
        handle_duplicate_event_submission(client, body, logger)
        
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error handling duplicate submission: {datetime.now()} - {e}")
        raise

def validate_export_dates(start_date: str, end_date: str) -> bool:
    """Validate export date range."""
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        return start <= end
    except ValueError:
        return False

@app.view("export_dates_submit")
def handle_export_dates_submission(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle export dates submission.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        state_values = body["view"]["state"]["values"]
        start_date = state_values[EXPORT_BLOCKS["START_DATE"]][f"{EXPORT_BLOCKS['START_DATE']}_select"]["selected_date"]
        end_date = state_values[EXPORT_BLOCKS["END_DATE"]][f"{EXPORT_BLOCKS['END_DATE']}_select"]["selected_date"]
        user_id = body["user"]["id"]

        if not validate_export_dates(start_date, end_date):
            ack(response_action="errors", errors={
                EXPORT_BLOCKS["START_DATE"]: ERROR_MESSAGES["DATE_ORDER"]
            })
            return

        ack()
        export_data_to_csv(start_date, end_date, user_id, client, logger)

    except SlackApiError as e:
        logger.error(f"Slack API error in export: {datetime.now()} - {e}")
        client.chat_postMessage(
            channel=user_id,
            text=ERROR_MESSAGES["EXPORT_ERROR"]
        )
    except Exception as e:
        logger.error(f"Error processing export dates: {datetime.now()} - {e}")
        client.chat_postMessage(
            channel=user_id,
            text=ERROR_MESSAGES["EXPORT_ERROR"]
        )

@app.action("select_date_button")
def handle_date_selection(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle date selection for events view.
    
    Args:
        ack: Acknowledge function
        body: Request body with selected date
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        if not (user_id := body.get("user", {}).get("id")):
            raise ValueError(ERROR_MESSAGES["USER_NOT_FOUND"])
            
        values = body["view"]["state"]["values"]
        date_block = values.get(DATE_BLOCKS["PICKER"], {})
        
        if not (selected_date := date_block.get(DATE_BLOCKS["SELECT"], {}).get("selected_date")):
            raise ValueError(ERROR_MESSAGES["INVALID_DATE"])

        show_events_by_day(client, logger, selected_date, user_id)
        
    except ValueError as e:
        logger.error(f"Validation error: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=str(e))
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=ERROR_MESSAGES["GENERAL_ERROR2"])
    except Exception as e:
        logger.error(f"Error handling date selection: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=ERROR_MESSAGES["GENERAL_ERROR2"])

@app.action(SELECT_EVENT_PATTERN)
def handle_select_event(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle event selection action - opens modal for attendance edit.
    
    Args:
        ack: Acknowledge function
        body: Request body with event selection
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        trigger_id = body["trigger_id"]
            
        action_id = body['actions'][0]['action_id']
        event_id = action_id.split('_')[-1]
        
        if not event_id.isdigit():
            raise ValueError(ERROR_MESSAGES["INVALID_ID"])
            
        show_edit_attendance_for_event(client, logger, event_id, trigger_id)
        
    except ValueError as e:
        logger.error(f"Validation error: {datetime.now()} - {e}")
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
    except Exception as e:
        logger.error(f"Error handling select event: {datetime.now()} - {e}")

def parse_event_id(action_id: str) -> str:
    """Extract event ID from action ID."""
    match = SELECT_USER_PATTERN.match(action_id)
    if not match:
        raise ValueError(ERROR_MESSAGES["INVALID_ID"])
    return match.group(1)

@app.action(SELECT_USER_PATTERN)
def select_participant_in_event(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle participant selection in event.
    
    Args:
        ack: Acknowledge function
        body: Request body with user selection
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        if not (view_user_id := body.get("user", {}).get("id")):
            raise ValueError(ERROR_MESSAGES["USER_NOT_FOUND"])
            
        action_id = body['actions'][0]['action_id']
        event_id = parse_event_id(action_id)
        
        values = body['view']['state']['values']
        if not (selected_user := values.get('user_selection_section', {})
                .get('user_selection', {})
                .get('selected_option', {})
                .get('value')):
            raise ValueError(ERROR_MESSAGES["USER_NOT_FOUND"])

        show_edit_attendance_players(
            client=client,
            logger=logger,
            event_id=event_id,
            view_user_id=view_user_id,
            user_id=selected_user
        )
        
    except ValueError as e:
        logger.error(f"Validation error: {datetime.now()} - {e}")
        client.chat_postMessage(channel=view_user_id, text=str(e))
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
        client.chat_postMessage(channel=view_user_id, text=ERROR_MESSAGES["SELECTION_ERROR"])
    except Exception as e:
        logger.error(f"Error selecting participant: {datetime.now()} - {e}")
        client.chat_postMessage(channel=view_user_id, text=ERROR_MESSAGES["SELECTION_ERROR"])

@app.options("user_selection")
def handle_user_selection_options(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """
    Handle user selection options loading.
    
    Args:
        ack: Acknowledge function
        body: Request body with search input
        logger: Logger instance
    """
    try:
        user_input = body.get("value", "").strip().lower()
        users = load_users_from_db()

        filtered_users = (
            [user for user in users if user_input in user['name'].lower()]
            if user_input
            else users
        )

        # Sort by name and limit results
        sorted_users = sorted(
            filtered_users, 
            key=lambda x: x['name']
        )[:MAX_RESULTS]

        if not sorted_users:
            ack(options=[])
            return

        options = [
            {
                "text": {"type": "plain_text", "text": user['name']},
                "value": user['user_id']
            }
            for user in sorted_users
        ]
        ack(options=options)
        
    except SlackApiError as e:
        logger.error(f"Slack API error in user search: {datetime.now()} - {e}")
        ack(options=[])
    except Exception as e:
        logger.error(f"Error searching users: {datetime.now()} - {e}")
        ack(options=[])

@app.options("user_select")
def handle_user_select_options(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """
    Handle user select options loading (for modal).
    
    Args:
        ack: Acknowledge function
        body: Request body with search input
        logger: Logger instance
    """
    try:
        user_input = body.get("value", "").strip().lower()
        users = load_users_from_db()

        filtered_users = (
            [user for user in users if user_input in user['name'].lower()]
            if user_input
            else users
        )

        # Sort by name and limit results
        sorted_users = sorted(
            filtered_users, 
            key=lambda x: x['name']
        )[:MAX_RESULTS]

        if not sorted_users:
            ack(options=[])
            return

        options = [
            {
                "text": {"type": "plain_text", "text": user['name']},
                "value": user['user_id']
            }
            for user in sorted_users
        ]
        ack(options=options)
        
    except SlackApiError as e:
        logger.error(f"Slack API error in user search: {datetime.now()} - {e}")
        ack(options=[])
    except Exception as e:
        logger.error(f"Error searching users: {datetime.now()} - {e}")
        ack(options=[])

@app.action("user_selection")
def handle_user_selection_action(ack, body, logger):
    """Handle user selection action (no-op)"""
    ack()

@app.action("user_select")
def handle_user_select_in_modal(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle user selection in edit attendance modal - updates modal with user's current status.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        
        # Get selected user
        selected_option = body['actions'][0].get('selected_option')
        if not selected_option:
            return
            
        user_id = selected_option['value']
        
        # Get event_id from callback_id
        view = body['view']
        callback_id = view['callback_id']
        event_id = callback_id.replace('edit_attendance_', '')
        
        # Update modal with user's attendance
        update_edit_attendance_modal(
            client=client,
            logger=logger,
            event_id=event_id,
            user_id=user_id,
            view_id=view['id']
        )
        
    except Exception as e:
        logger.error(f"Error handling user select in modal: {datetime.now()} - {e}")

def get_form_values(values: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Extract and validate form values."""
    selection_block = values.get(BLOCK_IDS["SELECTION"])
    reason_block = values.get(BLOCK_IDS["REASON"])

    selection = (
        selection_block["attendance_selection"]["selected_option"]["value"]
        if selection_block else None
    )
    note = reason_block["reason_input"]["value"] if reason_block else None

    return selection, note

@app.view("mass_input")
def handle_attendance_submit(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle mass attendance submission.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        user_id = body["user"]["id"]
        selection, note = get_form_values(body["view"]["state"]["values"])

        if not selection:
            raise ValueError(ERROR_MESSAGES["INVALID_SELECTION"])

        start_date, end_date = get_today_and_last_day_of_next_month()
        events = load_events_in_range_from_db(start_date, end_date)

        for event in events:
            insert_participation(event["id"], user_id, selection, note)

        show_attendance(client, user_id, logger)

    except ValueError as e:
        logger.error(f"Validation error: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=str(e))
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=ERROR_MESSAGES["DB_ERROR"])
    except Exception as e:
        logger.error(f"Error in mass input: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=ERROR_MESSAGES["DB_ERROR"])

@app.action(re.compile(r"history_(next|prev)_\d+"))
def handle_history_navigation(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """Handle history navigation button clicks."""
    try:
        ack()
        view_id = body["container"]["view_id"]
        event_id = body["view"]["private_metadata"]
        new_page = int(body["actions"][0]["value"])
        
        update_history_view(client, view_id, event_id, new_page, logger)
        
    except Exception as e:
        logger.error(f"Error handling history navigation: {datetime.now()} - {e}")
        raise

@app.action(re.compile(r"participants_(next|prev)_\d+"))
def handle_participants_navigation(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """Handle participant view navigation."""
    try:
        ack()
        view_id = body["container"]["view_id"]
        event_id = body["view"]["private_metadata"]
        new_page = int(body["actions"][0]["value"])
        
        participants = load_participants_from_event(event_id)
        event = load_event_from_db(event_id)
        
        blocks = create_participant_blocks(
            participants,
            event, 
            new_page
        )
        
        client.views_update(
            view_id=view_id,
            view={
                **ATTENDANCE_MODAL_CONFIG,
                "blocks": blocks,
                "private_metadata": str(event_id),
                "callback_id": f"participants_view_{event_id}"
            }
        )
    except Exception as e:
        logger.error(f"Error handling participants navigation: {datetime.now()} - {e}")
        raise

@app.action(re.compile(r"empty_(next|prev)_\d+"))
def handle_empty_navigation(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """Handle empty view navigation."""
    try:
        ack()
        view_id = body["container"]["view_id"]
        event_id = body["view"]["private_metadata"]
        new_page = int(body["actions"][0]["value"])
        
        participants = load_participants_from_event(event_id)

        participant_ids = [participant['user_id'] for participant in participants]

        o_active_players = load_users_by_category("Open")
        w_active_players = load_users_by_category("Women")

        users = load_users_from_db()

        users_dict = {user['user_id']: user['name'] for user in users}

        missing_boys = []
        missing_girls = []
        for player_id in participant_ids:
            player_name = users_dict.get(player_id, player_id)
            if player_id in o_active_players:
                o_active_players.remove(player_id)
            elif player_id in w_active_players:
                w_active_players.remove(player_id)

        missing_boys = sorted((users_dict.get(player_id, player_id) for player_id in o_active_players), key=locale.strxfrm)
        missing_girls = sorted((users_dict.get(player_id, player_id) for player_id in w_active_players), key=locale.strxfrm)

        missing_boys_text = '\n'.join(missing_boys) if missing_boys else "\n"
        missing_girls_text = '\n'.join(missing_girls) if missing_girls else "\n"
        
        blocks = create_empty_blocks(
            missing_boys_text,
            missing_girls_text,
            new_page,
            event_id
        )
        
        client.views_update(
            view_id=view_id,
            view={
                **EMPTY_MODAL_CONFIG,
                "blocks": blocks,
                "private_metadata": str(event_id),
                "callback_id": f"empty_view_{event_id}"
            }
        )
    except Exception as e:
        logger.error(f"Error handling empty navigation: {datetime.now()} - {e}")
        raise

@app.view("share_event")
def handle_share_event_submission(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle event sharing submission.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        user_id = body["user"]["id"]
        event_id = body["view"]["private_metadata"]
        values = body["view"]["state"]["values"]
        text_input = values["message"]["text_input"]["value"]
        channel_id = values["share_channel_block"]["share_channel_select"]["selected_option"]["value"]

        post_event_to_channel(client, user_id, event_id, channel_id, text_input, logger)
        
    except SlackApiError as e:
        logger.error(f"Slack API error in event sharing: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=ERROR_MESSAGES["SHARE_ERROR"])
    except Exception as e:
        logger.error(f"Error sharing event: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=ERROR_MESSAGES["SHARE_ERROR"])

def post_event_to_channel(
    client: WebClient,
    user_id: str,
    event_id: int,
    channel_id: str,
    text: str,
    logger: logging.Logger
) -> None:
    """Post event to channel."""
    try:
        event = load_event_from_db(event_id)
        
        # Get sender information
        if user_id:
            sender_name = get_user_by_id(user_id, logger)
            footer_text = f"\n\n_Odeslal: {sender_name}_"
        else:
            # For future automatic reminders
            footer_text = "\n\n_Automatický reminder_"
        
        # Append footer to message
        message_text = text + footer_text
        
        client.chat_postMessage(
            channel=channel_id,
            text=message_text,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message_text
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Zadat docházku"
                            },
                            "action_id": "attendance_modal",
                            "value": f"event_id_{event_id}"
                        }
                    ]
                }
            ]
        )
        
        if user_id:
            client.chat_postMessage(
                channel=user_id,
                text=MESSAGES["SHARE_SUCCESS"]
            )
        
    except SlackApiError as e:
        logger.error(f"Slack API error in event sharing: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error sharing event: {datetime.now()} - {e}")
        raise

@app.action("attendance_modal")
def handle_attendance_modal(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle attendance modal opening.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        event_id = body["actions"][0]["value"].split('_')[-1]
        open_chat_attendance_modal(body, client, logger, event_id)
        
    except SlackApiError as e:
        logger.error(f"Slack API error in attendance modal: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error opening attendance modal: {datetime.now()} - {e}")
        raise

@app.view("chat_attendance_input")
def handle_chat_attendance_submission(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle chat attendance submission.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        user_id = body["user"]["id"]
        event_id = body["view"]["private_metadata"]
        values = body["view"]["state"]["values"]
        selection = values["attendance_selection_block"]["attendance_selection"]["selected_option"]["value"]
        note = values["reason"]["reason_input"]["value"]

        insert_participation(event_id, user_id, selection, note, logger)
        #show_attendance(client, user_id, logger)
        
    except SlackApiError as e:
        logger.error(f"Slack API error in chat attendance: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=ERROR_MESSAGES["ATTENDANCE_ERROR"])
    except Exception as e:
        logger.error(f"Error in chat attendance: {datetime.now()} - {e}")
        client.chat_postMessage(channel=user_id, text=ERROR_MESSAGES["ATTENDANCE_ERROR"])

@app.action("select_women_category")
def handle_select_women_category(ack: Any, body: Dict[str, Any], client: WebClient, logger: logging.Logger) -> None:
    """
    Handle selection of Women category.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        user_id = body["user"]["id"]
        update_user_category(user_id, "Women", logger)
        show_attendance(client, user_id, logger)
    except Exception as e:
        logger.error(f"Error handling Women category selection: {datetime.now()} - {e}")

@app.action("select_open_category")
def handle_select_open_category(ack: Any, body: Dict[str, Any], client: WebClient, logger: logging.Logger) -> None:
    """
    Handle selection of Open category.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        user_id = body["user"]["id"]
        update_user_category(user_id, "Open", logger)
        show_attendance(client, user_id, logger)
    except Exception as e:
        logger.error(f"Error handling Open category selection: {datetime.now()} - {e}")

@app.action("select_user_category")
def handle_select_user_category(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle selection of user for category editing - opens modal.
    
    Args:
        ack: Acknowledge function
        body: Request body
        client: Slack client instance
        logger: Logger instance
    """
    try:
        ack()
        trigger_id = body["trigger_id"]
        
        values = body['view']['state']['values']
        if not (selected_user := values.get('user_category_selection_section', {})
                .get('user_selection', {})
                .get('selected_option', {})
                .get('value')):
            raise ValueError("Selected user not found")

        show_edit_player_category(
            client=client,
            logger=logger,
            user_id=selected_user,
            trigger_id=trigger_id
        )
        
    except ValueError as e:
        logger.error(f"Validation error: {datetime.now()} - {e}")
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
    except Exception as e:
        logger.error(f"Error handling select user category: {datetime.now()} - {e}")

@app.view(re.compile(r"^edit_user_category_.+$"))
def handle_edit_user_category_submit(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """
    Handle user category edit modal submission.
    
    Args:
        ack: Acknowledge function
        body: Request body
        logger: Logger instance
    """
    try:
        # Extract user_id from callback_id
        callback_id = body['view']['callback_id']
        user_id = callback_id.replace('edit_user_category_', '')
        
        # Get selected category
        values = body['view']['state']['values']
        selected_category = values['category_block']['category_select']['selected_option']['value']
        
        # Update user category
        update_user_category(user_id, selected_category, logger)
        
        ack()
        
    except Exception as e:
        logger.error(f"Error handling edit user category submit: {datetime.now()} - {e}")
        ack()

@app.view(re.compile(r"^edit_attendance_\d+$"))
def handle_edit_attendance_submit(
    ack: Any,
    body: Dict[str, Any],
    logger: logging.Logger
) -> None:
    """
    Handle attendance edit modal submission.
    
    Args:
        ack: Acknowledge function
        body: Request body
        logger: Logger instance
    """
    try:
        # Extract event_id from callback_id
        callback_id = body['view']['callback_id']
        event_id = callback_id.replace('edit_attendance_', '')
        
        # Get selected user and status
        values = body['view']['state']['values']
        
        # Check if user was selected
        user_block = values.get('user_block', {}).get('user_select', {})
        selected_option = user_block.get('selected_option')
        
        if not selected_option:
            ack(response_action="errors", errors={
                "user_block": "Prosím vyberte hráče"
            })
            return
        
        user_id = selected_option['value']
        
        # Check if status was selected
        status_block = values.get('status_block', {}).get('status_select', {})
        status_option = status_block.get('selected_option')
        
        if not status_option:
            ack(response_action="errors", errors={
                "status_block": "Prosím vyberte docházku"
            })
            return
        
        status = status_option['value']
        
        # Save attendance
        insert_participation(
            event_id=event_id,
            user_id=user_id,
            status=status,
            note="",
            logger=logger
        )
        
        ack()
        
    except Exception as e:
        logger.error(f"Error handling edit attendance submit: {datetime.now()} - {e}")
        ack()

# ---------- REMINDER HANDLERS ----------

@app.action("open_add_reminder_modal")
def handle_open_add_reminder_modal(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle action to open add reminder modal.
    """
    try:
        ack()
        open_add_reminder_modal(client, body["trigger_id"], logger)
    except Exception as e:
        logger.error(f"Error opening add reminder modal: {datetime.now()} - {e}")

@app.view("add_reminder_modal")
def handle_add_reminder_submission(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle submission of add reminder modal.
    """
    try:
        ack()
        user_id = body["user"]["id"]
        
        # Extract values from modal
        values = body["view"]["state"]["values"]
        reminder_type = values["reminder_type_block"]["reminder_type_select"]["selected_option"]["value"]
        channel_id = values["channel_block"]["channel_select"]["selected_channel"]
        remind_at_timestamp = values["remind_at_block"]["remind_at_input"]["selected_date_time"]
        days_ahead = int(values["days_ahead_block"]["days_ahead_input"]["value"])
        message = values["message_block"]["message_input"]["value"]
        repeat_type = values["repeat_block"]["repeat_select"]["selected_option"]["value"]
        
        # Convert timestamp to datetime
        remind_at = datetime.fromtimestamp(remind_at_timestamp)
        
        # Convert 'once' to None for database
        if repeat_type == 'once':
            repeat_type = None
        
        # Add reminder to database
        add_reminder_to_db(
            channel_id=channel_id,
            remind_at=remind_at,
            message=message,
            repeat_type=repeat_type,
            reminder_type=reminder_type,
            days_ahead=days_ahead,
            logger=logger
        )
        
        # Send confirmation message
        type_text = "zprávy" if reminder_type == "message" else f"sdílení událostí (+{days_ahead}d)"
        client.chat_postMessage(
            channel=user_id,
            text=f"✅ Reminder byl úspěšně vytvořen! (Typ: {type_text})"
        )
        
        # Refresh reminders list
        show_reminders_list(client, user_id, logger)
        
    except Exception as e:
        logger.error(f"Error handling add reminder submission: {datetime.now()} - {e}")
        client.chat_postMessage(
            channel=user_id,
            text="❌ Chyba při vytváření reminderu."
        )

@app.action(re.compile(r"reminder_overflow_(\d+)"))
def handle_reminder_overflow(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle reminder overflow menu actions.
    """
    try:
        ack()
        selected_option = body["actions"][0]["selected_option"]["value"]
        
        if selected_option.startswith("execute_now_reminder_"):
            reminder_id = int(selected_option.split("_")[-1])
            user_id = body["user"]["id"]
            
            # Execute reminder immediately
            try:
                success = execute_reminder_now(client, reminder_id, logger)
                
                if success:
                    client.chat_postMessage(
                        channel=user_id,
                        text=f"⚡ Reminder {reminder_id} byl úspěšně proveden!"
                    )
                else:
                    client.chat_postMessage(
                        channel=user_id,
                        text=f"❌ Nepodařilo se provést reminder {reminder_id}."
                    )
            except Exception as e:
                logger.error(f"Error executing reminder now: {e}")
                client.chat_postMessage(
                    channel=user_id,
                    text=f"❌ Chyba při provádění reminderu {reminder_id}."
                )
            
            # Refresh reminders list
            show_reminders_list(client, user_id, logger)
            
        elif selected_option.startswith("toggle_reminder_"):
            reminder_id = int(selected_option.split("_")[-1])
            user_id = body["user"]["id"]
            
            # Toggle reminder active status
            try:
                new_status = toggle_reminder_active(reminder_id, logger)
                status_text = "aktivován" if new_status else "deaktivován"
                
                client.chat_postMessage(
                    channel=user_id,
                    text=f"{'✅' if new_status else '⏸️'} Reminder {reminder_id} byl {status_text}."
                )
            except Exception as e:
                logger.error(f"Error toggling reminder: {e}")
                client.chat_postMessage(
                    channel=user_id,
                    text=f"❌ Nepodařilo se změnit stav reminderu {reminder_id}."
                )
            
            # Refresh reminders list
            show_reminders_list(client, user_id, logger)
            
        elif selected_option.startswith("edit_reminder_"):
            reminder_id = int(selected_option.split("_")[-1])
            open_edit_reminder_modal(client, body["trigger_id"], reminder_id, logger)
        elif selected_option.startswith("delete_reminder_"):
            reminder_id = int(selected_option.split("_")[-1])
            user_id = body["user"]["id"]
            
            # Delete reminder
            success = delete_reminder(reminder_id, logger)
            
            if success:
                client.chat_postMessage(
                    channel=user_id,
                    text=f"🗑️ Reminder {reminder_id} byl úspěšně smazán."
                )
            else:
                client.chat_postMessage(
                    channel=user_id,
                    text=f"❌ Reminder {reminder_id} nebyl nalezen."
                )
            
            # Refresh reminders list
            show_reminders_list(client, user_id, logger)
            
    except Exception as e:
        logger.error(f"Error handling reminder overflow: {datetime.now()} - {e}")

@app.view(re.compile(r"edit_reminder_(\d+)"))
def handle_edit_reminder_submission(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Handle submission of edit reminder modal.
    """
    try:
        ack()
        user_id = body["user"]["id"]
        
        # Extract reminder ID from callback_id
        callback_id = body["view"]["callback_id"]
        reminder_id = int(callback_id.split("_")[-1])
        
        # Extract values from modal
        values = body["view"]["state"]["values"]
        reminder_type = values["reminder_type_block"]["reminder_type_select"]["selected_option"]["value"]
        channel_id = values["channel_block"]["channel_select"]["selected_channel"]
        remind_at_timestamp = values["remind_at_block"]["remind_at_input"]["selected_date_time"]
        days_ahead = int(values["days_ahead_block"]["days_ahead_input"]["value"])
        message = values["message_block"]["message_input"]["value"]
        repeat_type = values["repeat_block"]["repeat_select"]["selected_option"]["value"]
        
        # Convert timestamp to datetime
        remind_at = datetime.fromtimestamp(remind_at_timestamp)
        
        # Convert 'once' to None for database
        if repeat_type == 'once':
            repeat_type = None
        
        # Update reminder in database
        update_reminder(
            reminder_id=reminder_id,
            channel_id=channel_id,
            remind_at=remind_at,
            message=message,
            repeat_type=repeat_type,
            reminder_type=reminder_type,
            days_ahead=days_ahead,
            logger=logger
        )
        
        # Send confirmation message
        type_text = "zprávy" if reminder_type == "message" else f"sdílení událostí (+{days_ahead}d)"
        client.chat_postMessage(
            channel=user_id,
            text=f"✅ Reminder {reminder_id} byl úspěšně upraven! (Typ: {type_text})"
        )
        
        # Refresh reminders list
        show_reminders_list(client, user_id, logger)
        
    except Exception as e:
        logger.error(f"Error handling edit reminder submission: {datetime.now()} - {e}")
        client.chat_postMessage(
            channel=user_id,
            text="❌ Chyba při úpravě reminderu."
        )

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    print("\n🛑 Ukončuji aplikaci... Prosím chvilku strpení.")
    sys.exit(0)

# ---------- REMINDER TASK LOOP ----------

reminder_stop_event = threading.Event()

def wait_for_30min_alignment():
    """
    Wait until the current time aligns to :00 or :30 minutes.
    Similar to the before_loop in the reference code.
    """
    while True:
        now = datetime.now()
        minute = now.minute
        second = now.second
        
        # Check if we're at :00 or :30 with 0 seconds
        if minute % 30 == 0 and second == 0:
            logger.info(f"Reminder loop aligned at {now}")
            return
        
        # Calculate next alignment time
        base = now.replace(second=0, microsecond=0)
        add_minutes = (30 - (minute % 30)) % 30
        if add_minutes == 0 and second > 0:
            add_minutes = 30
        
        target = base + timedelta(minutes=add_minutes)
        wait_seconds = (target - now).total_seconds()
        
        # Sleep in small increments to allow for shutdown
        sleep_increment = min(1.0, wait_seconds)
        for _ in range(int(wait_seconds)):
            if reminder_stop_event.is_set():
                return
            time.sleep(sleep_increment)
            if wait_seconds < 1:
                time.sleep(wait_seconds)
                break

def reminder_loop_thread():
    """
    Background thread that processes reminders every 30 minutes.
    """
    logger.info("Starting reminder loop thread...")
    
    # Wait for initial alignment
    wait_for_30min_alignment()
    
    while not reminder_stop_event.is_set():
        try:
            logger.info(f"Processing reminders at {datetime.now()}")
            process_due_reminders(client, logger)
        except Exception as e:
            logger.error(f"Error in reminder loop: {e}")
        
        # Wait 30 minutes (1800 seconds) or until stop event
        for _ in range(1800):
            if reminder_stop_event.is_set():
                logger.info("Stopping reminder loop...")
                return
            time.sleep(1)

def start_reminder_loop():
    """
    Start the reminder loop in a background thread.
    """
    thread = threading.Thread(target=reminder_loop_thread, daemon=True)
    thread.start()
    logger.info("Reminder loop thread started")

if __name__ == "__main__":
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        config.load_settings()
        
        # Start reminder loop in background
        start_reminder_loop()
        
        handler = SocketModeHandler(app, SLACK_APP_TOKEN)
        print("✅ Slack bot úspěšně spuštěn!")
        print("⏰ Reminder loop aktivován (každých 30 minut)")
        print("ℹ️  Pro ukončení použijte Ctrl+C")
        handler.start()
    except KeyboardInterrupt:
        print("\n🛑 Ukončuji aplikaci...")
        reminder_stop_event.set()
        sys.exit(0)
    except Exception as e:
        print(f"❌ Chyba při spuštění aplikace: {e}")
        reminder_stop_event.set()
        sys.exit(1)
