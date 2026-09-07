from datetime import datetime
from typing import Any, Dict, List
import io
import csv
import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from db import load_participants_in_range

EXPORT_MODAL = {
    "type": "modal",
    "callback_id": "export_dates_submit",
    "title": {"type": "plain_text", "text": "Export účastníků"},
    "close": {"type": "plain_text","text": "Zavřít"},
    "submit": {"type": "plain_text", "text": "Potvrdit"}
}

class ExportError(Exception):
    """Base exception for export related errors"""
    pass

def export_data_to_csv(start_date: str, end_date: str, user_id: str, client: WebClient, logger: logging.Logger) -> None:
    """
    Export participant data to CSV and send directly to user via DM.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        user_id: Slack user ID requesting the export
        client: Slack WebClient instance
        logger: Logger instance
        
    Raises:
        ExportError: If export process fails
    """
    try:
        # Validate dates
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            raise ExportError(f"Neplatný formát data: {e}")

        # Load data from database
        data = load_participants_in_range(start_date, end_date)
        required_keys = ["name", "category", "event_name", "status", "note", "start_time", "end_time"]
        
        # Generate CSV content in memory
        csv_buffer = io.StringIO()
        writer = csv.DictWriter(csv_buffer, fieldnames=required_keys)
        writer.writeheader()
        for row in data:
            csv_row = {key: row.get(key, '') for key in required_keys}
            writer.writerow(csv_row)
        
        csv_content = csv_buffer.getvalue()
        csv_buffer.close()

        # Open DM conversation with user to get channel ID
        dm_response = client.conversations_open(users=[user_id])
        dm_channel_id = dm_response["channel"]["id"]
        
        # Upload CSV file directly to user's DM
        filename = f"attendance_{start_date}_to_{end_date}.csv"
        client.files_upload_v2(
            channel=dm_channel_id,
            content=csv_content,
            filename=filename,
            title="Export docházky",
            initial_comment=f"📊 Export docházky od {start_date} do {end_date} obsahuje {len(data)} záznamů.",
        )
        
        logger.info(f"User {user_id} exported {len(data)} records from {start_date} to {end_date}")

    except SlackApiError as e:
        logger.error(f"Slack API error in export: {e}")
        client.chat_postMessage(
            channel=user_id,
            text="❌ Chyba při komunikaci se Slack API. Zkuste to prosím později."
        )
    except ExportError as e:
        logger.error(f"Export error: {e}")
        client.chat_postMessage(
            channel=user_id,
            text=f"❌ Chyba při exportu docházky."
        )
    except Exception as e:
        logger.error(f"Unexpected error during export: {e}")
        client.chat_postMessage(
            channel=user_id,
            text="❌ Neočekávaná chyba při exportu docházky."
        )

def build_date_picker_block(block_id: str, label: str, placeholder: str) -> Dict[str, Any]:
    """Build date picker block."""
    return {
        "type": "input",
        "block_id": block_id,
        "element": {
            "type": "datepicker",
            "action_id": f"{block_id}_select",
            "placeholder": {
                "type": "plain_text",
                "text": placeholder
            }
        },
        "label": {
            "type": "plain_text",
            "text": label
        }
    }

def create_export_blocks() -> List[Dict[str, Any]]:
    """Create blocks for export modal."""
    return [
        build_date_picker_block(
            "start_date",
            "Datum začátku",
            "Vyber datum začátku"
        ),
        build_date_picker_block(
            "end_date", 
            "Datum konce",
            "Vyber datum konce"
        )
    ]

def export_participants(
    ack: Any,
    body: Dict[str, Any],
    client: WebClient,
    logger: logging.Logger
) -> None:
    """
    Show export participants modal.
    
    Args:
        ack: Acknowledge function
        body: Request body 
        client: Slack client instance
        logger: Logger instance
        
    Raises:
        SlackApiError: If modal cannot be opened
    """
    try:
        ack()
        if not (user_id := body.get("user", {}).get("id")):
            raise ValueError("User ID not found")

        blocks = create_export_blocks()
        modal = {**EXPORT_MODAL, "blocks": blocks}
        
        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal
        )
    except SlackApiError as e:
        logger.error(f"Slack API error: {datetime.now()} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error showing export modal: {datetime.now()} - {e}")
        raise
