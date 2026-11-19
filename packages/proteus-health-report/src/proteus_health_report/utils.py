from pathlib import Path
import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def save_report_to_disk(report_content, report_file: Path):
    """Write the report to a new log file (rotation is handled externally, e.g., logrotate)."""
    report_file.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"[{timestamp}]\n{report_content}\n")


def get_discord_webhook(filename) -> None | str:
    try:
        with open(filename, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"A valid Discord webhook file not found at {filename}")
        return None


def discord_notification(webhook, message):
    data = {
        "content": message
    }
    headers = {
        "Content-Type": "application/json"
    }

    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"]
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    response = session.post(webhook, json=data, headers=headers, timeout=10)

    try:
        response.raise_for_status()
        print("Triggered Discord notifier webhook")
        return True
    except requests.exceptions.HTTPError as err:
        print(f"Failed to trigger Discord notifier webhook: {err}")
        return False
