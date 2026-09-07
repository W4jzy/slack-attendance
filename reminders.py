from db import (
    deactivate_reminder,
    get_all_reminders,
    get_due_reminders,
    load_events_by_date_from_db,
    load_reminder_from_db,
    update_reminder_next_time,
)
from typing import Dict, List, Any
from slack_sdk import WebClient
from datetime import datetime, timedelta
import logging
import calendar

# Constants
REMINDER_MODAL_CONFIG = {
    "type": "modal",
    "title": {"type": "plain_text", "text": "Připomínky"},
    "close": {"type": "plain_text", "text": "Zavřít"}
}

REPEAT_TYPES = [
    {"text": {"type": "plain_text", "text": "Jednorázově"}, "value": "once"},
    {"text": {"type": "plain_text", "text": "Denně"}, "value": "daily"},
    {"text": {"type": "plain_text", "text": "Týdně"}, "value": "weekly"},
    {"text": {"type": "plain_text", "text": "Měsíčně"}, "value": "monthly"}
]

class ReminderError(Exception):
    """Base exception for reminder related errors"""
    pass


def build_add_reminder_modal() -> Dict[str, Any]:
    """
    Build modal view for adding a new reminder.
    
    Returns:
        Dict[str, Any]: Modal view configuration
    """
    return {
        "type": "modal",
        "callback_id": "add_reminder_modal",
        "title": {"type": "plain_text", "text": "Přidat připomínku"},
        "submit": {"type": "plain_text", "text": "Vytvořit"},
        "close": {"type": "plain_text", "text": "Zrušit"},
        "blocks": [
            {
                "type": "input",
                "block_id": "reminder_type_block",
                "element": {
                    "type": "radio_buttons",
                    "action_id": "reminder_type_select",
                    "options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Zpráva"
                            },
                            "value": "message"
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Sdílet události"
                            },
                            "value": "share_events"
                        }
                    ],
                    "initial_option": {
                        "text": {
                            "type": "plain_text",
                            "text": "Zpráva"
                        },
                        "value": "message"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Typ připomínky"
                }
            },
            {
                "type": "input",
                "block_id": "channel_block",
                "element": {
                    "type": "channels_select",
                    "action_id": "channel_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Vyberte kanál"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Kanál"
                }
            },
            {
                "type": "input",
                "block_id": "remind_at_block",
                "element": {
                    "type": "datetimepicker",
                    "action_id": "remind_at_input"
                },
                "label": {
                    "type": "plain_text",
                    "text": "Datum a čas reminderu"
                }
            },
            {
                "type": "input",
                "block_id": "days_ahead_block",
                "element": {
                    "type": "number_input",
                    "action_id": "days_ahead_input",
                    "is_decimal_allowed": False,
                    "min_value": "0",
                    "max_value": "30",
                    "initial_value": "0",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "0 = dnes, 1 = zítra, 7 = za týden..."
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Dny dopředu (pro sdílení událostí)"
                },
                "hint": {
                    "type": "plain_text",
                    "text": "Kolik dní dopředu hledat události ke sdílení (ignorováno pro typ 'Zpráva')"
                }
            },
            {
                "type": "input",
                "block_id": "message_block",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "message_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Text zprávy"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Zpráva"
                }
            },
            {
                "type": "input",
                "block_id": "repeat_block",
                "element": {
                    "type": "static_select",
                    "action_id": "repeat_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Vyberte typ opakování"
                    },
                    "options": REPEAT_TYPES,
                    "initial_option": REPEAT_TYPES[0]
                },
                "label": {
                    "type": "plain_text",
                    "text": "Opakování"
                }
            }
        ]
    }


def build_edit_reminder_modal(reminder: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build modal view for editing an existing reminder.
    
    Args:
        reminder: Reminder data from database
        
    Returns:
        Dict[str, Any]: Modal view configuration
    """
    # Find the matching repeat type option
    repeat_value = reminder.get('repeat_type') or 'once'
    initial_option = next(
        (opt for opt in REPEAT_TYPES if opt['value'] == repeat_value),
        REPEAT_TYPES[0]
    )
    
    # Get reminder type
    reminder_type = reminder.get('reminder_type', 'message')
    reminder_type_options = [
        {
            "text": {"type": "plain_text", "text": "Zpráva"},
            "value": "message"
        },
        {
            "text": {"type": "plain_text", "text": "Sdílet události"},
            "value": "share_events"
        }
    ]
    initial_reminder_type = next(
        (opt for opt in reminder_type_options if opt['value'] == reminder_type),
        reminder_type_options[0]
    )
    
    # Convert datetime to timestamp for datetimepicker
    remind_at = reminder['remind_at']
    if isinstance(remind_at, datetime):
        remind_at_timestamp = int(remind_at.timestamp())
    else:
        remind_at_timestamp = int(datetime.fromisoformat(str(remind_at)).timestamp())
    
    days_ahead = str(reminder.get('days_ahead', 0))
    
    return {
        "type": "modal",
        "callback_id": f"edit_reminder_{reminder['id']}",
        "title": {"type": "plain_text", "text": "Upravit připomínku"},
        "submit": {"type": "plain_text", "text": "Uložit"},
        "close": {"type": "plain_text", "text": "Zrušit"},
        "blocks": [
            {
                "type": "input",
                "block_id": "reminder_type_block",
                "element": {
                    "type": "radio_buttons",
                    "action_id": "reminder_type_select",
                    "options": reminder_type_options,
                    "initial_option": initial_reminder_type
                },
                "label": {
                    "type": "plain_text",
                    "text": "Typ připomínky"
                }
            },
            {
                "type": "input",
                "block_id": "channel_block",
                "element": {
                    "type": "channels_select",
                    "action_id": "channel_select",
                    "initial_channel": reminder['channel_id'],
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Vyberte kanál"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Kanál"
                }
            },
            {
                "type": "input",
                "block_id": "remind_at_block",
                "element": {
                    "type": "datetimepicker",
                    "action_id": "remind_at_input",
                    "initial_date_time": remind_at_timestamp
                },
                "label": {
                    "type": "plain_text",
                    "text": "Datum a čas připomínky"
                }
            },
            {
                "type": "input",
                "block_id": "days_ahead_block",
                "element": {
                    "type": "number_input",
                    "action_id": "days_ahead_input",
                    "is_decimal_allowed": False,
                    "min_value": "0",
                    "max_value": "30",
                    "initial_value": days_ahead,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "0 = dnes, 1 = zítra, 7 = za týden..."
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Dny dopředu (pro sdílení událostí)"
                },
                "hint": {
                    "type": "plain_text",
                    "text": "Kolik dní dopředu hledat události ke sdílení (ignorováno pro typ 'Zpráva')"
                }
            },
            {
                "type": "input",
                "block_id": "message_block",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "message_input",
                    "multiline": True,
                    "initial_value": reminder['message'],
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Text zprávy"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Zpráva"
                }
            },
            {
                "type": "input",
                "block_id": "repeat_block",
                "element": {
                    "type": "static_select",
                    "action_id": "repeat_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Vyberte typ opakování"
                    },
                    "options": REPEAT_TYPES,
                    "initial_option": initial_option
                },
                "label": {
                    "type": "plain_text",
                    "text": "Opakování"
                }
            }
        ]
    }


def build_reminders_list_view(client: WebClient, logger: logging.Logger) -> List[Dict[str, Any]]:
    """
    Build blocks for reminders list view.
    
    Args:
        client: Slack WebClient instance
        logger: Logger instance
        
    Returns:
        List[Dict[str, Any]]: List of blocks for the view
    """
    blocks = []
    
    # Header with back button and add reminder button
    blocks.extend([
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Zpět"},
                    "action_id": "go_to_all_events"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Přidat připomínku"},
                    "style": "primary",
                    "action_id": "open_add_reminder_modal"
                }
            ]
        },
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Připomínky",
                "emoji": True
            }
        },
        {"type": "divider"}
    ])
    
    # Get all reminders (active and inactive)
    try:
        reminders = get_all_reminders(logger=logger)
        
        if not reminders:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_Žádné připomínky._"
                }
            })
        else:
            for reminder in reminders:
                remind_at = reminder['remind_at']
                if isinstance(remind_at, datetime):
                    remind_at_str = remind_at.strftime("%d.%m.%Y %H:%M")
                else:
                    remind_at_str = str(remind_at)
                
                repeat_type = reminder.get('repeat_type') or 'once'
                repeat_labels = {
                    'once': 'Jednorázově',
                    'daily': 'Denně',
                    'weekly': 'Týdně',
                    'monthly': 'Měsíčně'
                }
                repeat_label = repeat_labels.get(repeat_type, repeat_type)
                
                # Reminder type
                reminder_type = reminder.get('reminder_type', 'message')
                type_emoji = "💬" if reminder_type == "message" else "📅"
                type_label = "Zpráva" if reminder_type == "message" else "Sdílet události"
                
                # Days ahead (for share_events type)
                days_ahead = reminder.get('days_ahead', 0)
                days_ahead_text = f" (+{days_ahead}d)" if reminder_type == "share_events" and days_ahead > 0 else ""
                
                # Status indicator
                is_active = reminder.get('active', 1)
                status_emoji = "✅" if is_active else "⏸️"
                toggle_text = "Deaktivovat" if is_active else "Aktivovat"
                
                # Get channel name
                try:
                    channel_info = client.conversations_info(channel=reminder['channel_id'])
                    channel_name = channel_info['channel']['name']
                except Exception as e:
                    logger.warning(f"Could not get channel info: {e}")
                    channel_name = reminder['channel_id']
                
                message_preview = reminder['message'][:80]
                if len(reminder['message']) > 80:
                    message_preview += "..."
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{status_emoji} *ID {reminder['id']}* {type_emoji} {type_label}{days_ahead_text}\n"
                                f"📅 {remind_at_str} | 🔁 {repeat_label} | 📢 #{channel_name}\n"
                                f"💬 _{message_preview}_"
                    },
                    "accessory": {
                        "type": "overflow",
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "⚡ Provést teď"
                                },
                                "value": f"execute_now_reminder_{reminder['id']}"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": toggle_text
                                },
                                "value": f"toggle_reminder_{reminder['id']}"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Upravit"
                                },
                                "value": f"edit_reminder_{reminder['id']}"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Smazat"
                                },
                                "value": f"delete_reminder_{reminder['id']}"
                            }
                        ],
                        "action_id": f"reminder_overflow_{reminder['id']}"
                    }
                })
                blocks.append({"type": "divider"})
    
    except Exception as e:
        logger.exception(f"Error loading reminders: {e}")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "❌ _Chyba při načítání reminderů._"
            }
        })
    
    return blocks


def show_reminders_list(client: WebClient, user_id: str, logger: logging.Logger) -> None:
    """
    Show the reminders list view to user.
    
    Args:
        client: Slack WebClient instance
        user_id: User ID to show view to
        logger: Logger instance
    """
    try:
        blocks = build_reminders_list_view(client, logger)
        client.views_publish(
            user_id=user_id,
            view={"type": "home", "blocks": blocks}
        )
    except Exception as e:
        logger.exception(f"Error showing reminders list: {e}")
        raise ReminderError("Failed to show reminders list")


def open_add_reminder_modal(client: WebClient, trigger_id: str, logger: logging.Logger) -> None:
    """
    Open modal for adding a new reminder.
    
    Args:
        client: Slack WebClient instance
        trigger_id: Trigger ID from the interaction
        logger: Logger instance
    """
    try:
        view = build_add_reminder_modal()
        client.views_open(trigger_id=trigger_id, view=view)
    except Exception as e:
        logger.exception(f"Error opening add reminder modal: {e}")
        raise ReminderError("Failed to open add reminder modal")


def open_edit_reminder_modal(client: WebClient, trigger_id: str, reminder_id: int, logger: logging.Logger) -> None:
    """
    Open modal for editing an existing reminder.
    
    Args:
        client: Slack WebClient instance
        trigger_id: Trigger ID from the interaction
        reminder_id: ID of the reminder to edit
        logger: Logger instance
    """
    try:
        reminder = load_reminder_from_db(reminder_id, logger=logger)
        if not reminder:
            raise ReminderError(f"Reminder {reminder_id} not found")
        
        view = build_edit_reminder_modal(reminder)
        client.views_open(trigger_id=trigger_id, view=view)
    except Exception as e:
        logger.exception(f"Error opening edit reminder modal: {e}")
        raise ReminderError("Failed to open edit reminder modal")


def calculate_next_reminder_time(current_time: datetime, repeat_type: str) -> datetime:
    """
    Calculate the next reminder time based on repeat type.
    
    Args:
        current_time: Current reminder time
        repeat_type: Type of repetition ('daily', 'weekly', 'monthly')
        
    Returns:
        datetime: Next reminder time
    """
    if isinstance(current_time, str):
        current_time = datetime.fromisoformat(current_time)
    
    if repeat_type == "daily":
        return current_time + timedelta(days=1)
    
    elif repeat_type == "weekly":
        return current_time + timedelta(weeks=1)
    
    elif repeat_type == "monthly":
        # Simple "next month" approach
        month = current_time.month + 1
        year = current_time.year
        if month > 12:
            month = 1
            year += 1
        day = min(current_time.day, calendar.monthrange(year, month)[1])
        return current_time.replace(year=year, month=month, day=day)
    
    else:
        raise ValueError(f"Unknown repeat type: {repeat_type}")


def process_due_reminders(client: WebClient, logger: logging.Logger) -> None:
    """
    Process all due reminders - send messages/share events and update/deactivate them.
    
    Args:
        client: Slack WebClient instance
        logger: Logger instance
    """
    try:
        due_reminders = get_due_reminders(logger=logger)
        
        if not due_reminders:
            return
        
        for reminder in due_reminders:
            reminder_id = reminder['id']
            channel_id = reminder['channel_id']
            message = reminder['message']
            repeat_type = reminder.get('repeat_type')
            reminder_type = reminder.get('reminder_type', 'message')
            days_ahead = reminder.get('days_ahead', 0)
            delivery_failed = False
            
            # Process based on reminder type
            if reminder_type == 'share_events':
                # Calculate target date for events
                remind_at = reminder['remind_at']
                if isinstance(remind_at, datetime):
                    target_date = remind_at + timedelta(days=days_ahead)
                else:
                    target_date = datetime.fromisoformat(str(remind_at)) + timedelta(days=days_ahead)
                
                target_date_str = target_date.strftime('%Y-%m-%d')
                
                # Get events on target date
                try:
                    events_on_date = load_events_by_date_from_db(target_date_str, logger=logger)
                    
                    if events_on_date:
                        # Share each event to the channel
                        for event in events_on_date:
                            try:
                                # Build event message
                                start_time_str = event['start_time'].strftime('%d.%m.%Y %H:%M')
                                end_time_str = event['end_time'].strftime('%d.%m.%Y %H:%M')
                                
                                event_message = (
                                    f"{message}\n\n"
                                    f"📅 *{event['name']}*\n\n"
                                    f"📍 {event.get('address', 'Adresa není specifikována')}\n"
                                    f"🕐 Začátek: {start_time_str}\n"
                                    f"🕑 Konec: {end_time_str}\n"
                                    f"🏷️ Typ: {event['type']}\n\n"
                                    f"_Automatický reminder_"
                                )
                                
                                # Send message with blocks (text + attendance button)
                                client.chat_postMessage(
                                    channel=channel_id,
                                    text=event_message,
                                    blocks=[
                                        {
                                            "type": "section",
                                            "text": {
                                                "type": "mrkdwn",
                                                "text": event_message
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
                                                    "value": f"event_id_{event['id']}"
                                                }
                                            ]
                                        }
                                    ]
                                )
                                logger.info(f"Shared event {event['id']} from reminder {reminder_id} to channel {channel_id}")
                            except Exception as e:
                                logger.exception(f"Failed to share event {event['id']} from reminder {reminder_id}: {e}")
                                delivery_failed = True
                    else:
                        # No events found - send the custom message
                        try:
                            client.chat_postMessage(
                                channel=channel_id,
                                text=f"{message}\n\n_Automatický reminder_"
                            )
                            logger.info(f"Sent no-events message from reminder {reminder_id} to channel {channel_id}")
                        except Exception as e:
                            logger.exception(f"Failed to send no-events message from reminder {reminder_id}: {e}")
                            delivery_failed = True
                            
                except Exception as e:
                    logger.exception(f"Failed to process share_events reminder {reminder_id}: {e}")
                    continue
                    
            else:
                # Standard message reminder
                try:
                    client.chat_postMessage(
                        channel=channel_id,
                        text=f"⏰ *Reminder:*\n{message}"
                    )
                    logger.info(f"Sent reminder {reminder_id} to channel {channel_id}")
                except Exception as e:
                    logger.exception(f"Failed to send reminder {reminder_id}: {e}")
                    continue
            
            if delivery_failed:
                continue

            # Update or deactivate based on repeat type
            if not repeat_type or repeat_type == 'once':
                # One-time reminder - deactivate it
                deactivate_reminder(reminder_id, logger=logger)
                logger.info(f"Deactivated one-time reminder {reminder_id}")
            else:
                # Repeating reminder - calculate next time
                try:
                    current_time = reminder['remind_at']
                    next_time = calculate_next_reminder_time(current_time, repeat_type)
                    now = datetime.now()
                    while next_time <= now:
                        next_time = calculate_next_reminder_time(next_time, repeat_type)
                    update_reminder_next_time(reminder_id, next_time, logger=logger)
                    logger.info(f"Updated reminder {reminder_id} to next time: {next_time}")
                except Exception as e:
                    logger.exception(f"Failed to update reminder {reminder_id}: {e}")
                    # Deactivate on error to prevent infinite loops
                    deactivate_reminder(reminder_id, logger=logger)
    
    except Exception as e:
        logger.exception(f"Error processing due reminders: {e}")
        raise ReminderError("Failed to process due reminders")


def execute_reminder_now(client: WebClient, reminder_id: int, logger: logging.Logger) -> bool:
    """
    Execute a specific reminder immediately, regardless of its scheduled time.
    
    Args:
        client: Slack WebClient instance
        reminder_id: ID of the reminder to execute
        logger: Logger instance
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Load reminder data
        reminder = load_reminder_from_db(reminder_id, logger=logger)
        if not reminder:
            logger.error(f"Reminder {reminder_id} not found")
            return False
        
        channel_id = reminder['channel_id']
        message = reminder['message']
        reminder_type = reminder.get('reminder_type', 'message')
        days_ahead = reminder.get('days_ahead', 0)
        
        # Process based on reminder type
        if reminder_type == 'share_events':
            # Calculate target date for events (from NOW, not from remind_at)
            target_date = datetime.now() + timedelta(days=days_ahead)
            target_date_str = target_date.strftime('%Y-%m-%d')
            
            # Get events on target date
            try:
                events_on_date = load_events_by_date_from_db(target_date_str, logger=logger)
                
                if events_on_date:
                    # Share each event to the channel
                    for event in events_on_date:
                        try:
                            # Build event message
                            start_time_str = event['start_time'].strftime('%d.%m.%Y %H:%M')
                            end_time_str = event['end_time'].strftime('%d.%m.%Y %H:%M')
                            
                            event_message = (\
                                f"{message}\n\n"
                                f"📅 *{event['name']}*\n\n"
                                f"📍 {event.get('address', 'Adresa není specifikována')}\n"
                                f"🕐 Začátek: {start_time_str}\n"
                                f"🕑 Konec: {end_time_str}\n"
                                f"🏷️ Typ: {event['type']}\n\n"
                                f"_Manuálně spuštěný reminder_"
                            )
                            
                            # Send message with blocks (text + attendance button)
                            client.chat_postMessage(
                                channel=channel_id,
                                text=event_message,
                                blocks=[
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": event_message
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
                                                "value": f"event_id_{event['id']}"
                                            }
                                        ]
                                    }
                                ]
                            )
                            logger.info(f"Manually shared event {event['id']} from reminder {reminder_id} to channel {channel_id}")
                        except Exception as e:
                            logger.exception(f"Failed to share event {event['id']} from reminder {reminder_id}: {e}")
                else:
                    # No events found - send the custom message
                    try:
                        client.chat_postMessage(
                            channel=channel_id,
                            text=f"{message}\n\n_Manuálně spuštěný reminder_"
                        )
                        logger.info(f"Sent no-events message from reminder {reminder_id} to channel {channel_id}")
                    except Exception as e:
                        logger.exception(f"Failed to send no-events message from reminder {reminder_id}: {e}")
                        return False
                        
            except Exception as e:
                logger.exception(f"Failed to process share_events reminder {reminder_id}: {e}")
                return False
                
        else:
            # Standard message reminder
            try:
                client.chat_postMessage(
                    channel=channel_id,
                    text=f"⏰ *Reminder:*\n{message}"
                )
                logger.info(f"Manually sent reminder {reminder_id} to channel {channel_id}")
            except Exception as e:
                logger.exception(f"Failed to send reminder {reminder_id}: {e}")
                return False
        
        return True
        
    except Exception as e:
        logger.exception(f"Error executing reminder {reminder_id} now: {e}")
        return False
