import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

load_dotenv()

client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))

try:
    response = client.usergroups_list()
    for group in response["usergroups"]:
        print(f"Name: {group['name']}, ID: {group['id']}")
except SlackApiError as e:
    print(f"Error fetching user groups: {e.response['error']}")
