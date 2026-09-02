from pathlib import Path
import datetime


def save_report_to_disk(report_content, report_file_location):
    """Write the report to a new log file (rotation is handled externally, e.g., logrotate)."""
    report_file = Path(report_file_location)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(report_file, "w") as f:
        f.write(f"[{timestamp}]\n{report_content}\n")
