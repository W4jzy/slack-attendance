from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import logging
import config

# Constants
DEFAULT_OPTION = {"text": {"type": "plain_text", "text": "Žádná hodnota"}, "value": "None"}

class SettingsError(Exception):
    """Base exception for settings related errors"""
    pass

def fetch_user_groups(client: WebClient, logger: logging.Logger) -> List[Dict[str, Any]]:
    """Fetch user groups from Slack"""
    try:
        response = client.usergroups_list()
        user_groups = [
            {"text": {"type": "plain_text", "text": group["name"]}, "value": group["id"]}
            for group in response["usergroups"]
        ]
        user_groups.insert(0, DEFAULT_OPTION)
        return user_groups
    except SlackApiError as e:
        logger.error(f"Error fetching user groups: {e}")
        return [DEFAULT_OPTION]

def fetch_channels(client: WebClient, logger: logging.Logger) -> List[Dict[str, Any]]:
    """Fetch all channels from Slack (public + private) with pagination"""
    try:
        channels = []
        cursor = None

        while True:
            response = client.conversations_list(
                types="public_channel,private_channel",
                exclude_archived=True,
                limit=200,
                cursor=cursor
            )
            batch = [
                {"text": {"type": "plain_text", "text": channel["name"]}, "value": channel["id"]}
                for channel in response["channels"]
            ]
            channels.extend(batch)

            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        channels.insert(0, DEFAULT_OPTION)
        return channels

    except SlackApiError as e:
        logger.error(f"Error fetching channels: {e}")
        return [DEFAULT_OPTION]

def get_initial_option(id: Optional[str], array: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Get initial option for a select menu"""
    if not id or id == "None":
        return DEFAULT_OPTION["text"]["text"], DEFAULT_OPTION["value"]
    
    for item in array:
        if item["value"] == id:
            return item["text"]["text"], item["value"]
    return DEFAULT_OPTION["text"]["text"], DEFAULT_OPTION["value"]

def build_settings_blocks(channels: List[Dict], config_values: Dict) -> List[Dict]:
    """Build settings view blocks"""
    exp_n, exp_v = get_initial_option(config_values["export_channel"], channels)

    return [
        # Header section
        {
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": "Zpět"},
                "action_id": "go_to_attendance"
            }]
        },
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Nastavení aplikace",
                "emoji": True
            }
        },
        {
            "type": "input",
            "block_id": "export_channel_block",
            "element": {
                "type": "static_select",
                "action_id": "export_channel_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Vyberte kanál pro export"
                },
                "options": channels,
                "initial_option": {
                    "text": {
                        "type": "plain_text",
                        "text": exp_n,
                    },
                    "value": exp_v
                },
            },
            "label": {
                "type": "plain_text",
                "text": "Exportní kanál"
            }
        },
        {
            "type": "input",
            "block_id": "coming_text_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "coming_text_input",
                "initial_value": config_values["coming_text"]
            },
            "label": {
                "type": "plain_text",
                "text": "Text pro 'Chci'"
            }
        },
        {
            "type": "input",
            "block_id": "late_text_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "late_text_input",
                "initial_value": config_values["late_text"]
            },
            "label": {
                "type": "plain_text",
                "text": "Text pro 'Ještě nevím'"
            }
        },
        {
            "type": "input",
            "block_id": "notcoming_text_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "notcoming_text_input",
                "initial_value": config_values["notcoming_text"]
            },
            "label": {
                "type": "plain_text",
                "text": "Text pro 'Nechci'"
            }
        },
        {
            "type": "input",
            "block_id": "coming_training_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "coming_training_input",
                "initial_value": config_values["coming_training"]
            },
            "label": {
                "type": "plain_text",
                "text": "Text pro 'Přijdu' (trénink)"
            }
        },
        {
            "type": "input",
            "block_id": "late_training_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "late_training_input",
                "initial_value": config_values["late_training"]
            },
            "label": {
                "type": "plain_text",
                "text": "Text pro 'Přijdu později' (trénink)"
            }
        },
        {
            "type": "input",
            "block_id": "notcoming_training_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "notcoming_training_input",
                "initial_value": config_values["notcoming_training"]
            },
            "label": {
                "type": "plain_text",
                "text": "Text pro 'Nepřijdu' (trénink)"
            }
        },
        {
            "type": "actions",
            "block_id": "save_settings_block",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Uložit nastavení"
                    },
                    "style": "primary",
                    "action_id": "save_settings"
                }
            ]
        }
    ]

def show_settings(client: WebClient, user_id: str, logger: logging.Logger) -> None:
    """
    Show settings form to user.
    
    Args:
        client: Slack WebClient instance
        user_id: User ID to show settings to
        logger: Logger instance
        
    Raises:
        SettingsError: If settings cannot be displayed
    """
    try:
        # Fetch required data
        channels = fetch_channels(client, logger)

        # Build and publish view
        blocks = build_settings_blocks(channels, config.config)
        
        client.views_publish(
            user_id=user_id,
            view={
                "type": "home",
                "blocks": blocks
            }
        )

    except SlackApiError as e:
        logger.error(f"Slack API error in settings: {e}")
        client.chat_postMessage(
            channel=user_id,
            text="❌ Chyba při načítání nastavení. Zkuste to prosím později."
        )
    except SettingsError as e:
        logger.error(f"Settings error: {e}")
        client.chat_postMessage(
            channel=user_id,
            text="❌ Chyba při načítání nastavení. Zkuste to prosím později."
        )
    except Exception as e:
        logger.error(f"Error displaying settings: {e}")
        client.chat_postMessage(
            channel=user_id,
            text="❌ Neočekávaná chyba při zobrazení nastavení."
        )

def go_to_settings(body: Dict[str, Any], client: WebClient, logger: logging.Logger) -> None:
    """
    Handle the action to go to settings.
    """
    try:
        user_id = body["user"]["id"]
        show_settings(client, user_id, logger)
    except Exception as e:
        logger.error(f"Error: {datetime.now()} - {e}")