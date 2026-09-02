from pathlib import Path
import datetime
import requests


def save_report_to_disk(report_content, report_file_location):
    """Write the report to a new log file (rotation is handled externally, e.g., logrotate)."""
    report_file = Path(report_file_location)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(report_file, "w") as f:
        f.write(f"[{timestamp}]\n{report_content}\n")


def get_discord_webhook(filename) -> None | str:
    try:
        with open(filename, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print("Discord webhook config file not found, ensure it exists with a valid webhook URL.")
        return None


def discord_notification(webhook, message):
    data = {
        "content": message
    }
    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(webhook, json=data, headers=headers)

    try:
        response.raise_for_status()
        print("Triggered Discord notifier webhook")
        return True
    except requests.exceptions.HTTPError as err:
        print(f"Failed to trigger Discord notifier webhook: {err}")
        return False
