from datetime import datetime
from typing import Dict, List, Any
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

def build_settings_blocks(config_values: Dict) -> List[Dict]:
    """Build settings view blocks"""
    return [
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
        }
    ]

def show_settings(client: WebClient, trigger_id: str, logger: logging.Logger) -> None:
    """
    Show settings modal to user.
    
    Args:
        client: Slack WebClient instance
        trigger_id: Trigger ID from action to open modal
        logger: Logger instance
        
    Raises:
        SettingsError: If settings cannot be displayed
    """
    try:
        # Build and open modal
        blocks = build_settings_blocks(config.config)
        
        client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "settings_modal",
                "title": {
                    "type": "plain_text",
                    "text": "Nastavení aplikace"
                },
                "blocks": blocks,
                "submit": {
                    "type": "plain_text",
                    "text": "Uložit"
                },
                "close": {
                    "type": "plain_text",
                    "text": "Zavřít"
                }
            }
        )

    except SlackApiError as e:
        logger.error(f"Slack API error in settings: {e}")
        raise SettingsError(f"Failed to open settings modal: {e}")
    except Exception as e:
        logger.error(f"Error displaying settings: {e}")
        raise SettingsError(f"Unexpected error displaying settings: {e}")

def go_to_settings(body: Dict[str, Any], client: WebClient, logger: logging.Logger) -> None:
    """
    Handle the action to go to settings.
    """
    try:
        trigger_id = body["trigger_id"]
        show_settings(client, trigger_id, logger)
    except Exception as e:
        logger.error(f"Error: {datetime.now()} - {e}")