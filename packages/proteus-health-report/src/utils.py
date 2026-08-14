import os
import yaml
from pathlib import Path
import datetime


def deep_merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(base_path, override_path=None):
    """Load the provided base config and optionally override with addtional user config if provided."""

    # Try to find config file in same directory as script
    script_dir = Path(__file__).parent
    full_config_path = script_dir / base_path

    try:
        config = {}

        with open(base_path, 'r') as f:
            config = yaml.safe_load(f) or {}

        if override_path and os.path.exists(override_path):
            with open(override_path, 'r') as f:
                override_config = yaml.safe_load(f) or {}
            config = deep_merge(config, override_config)
        return config
    except yaml.YAMLError as e:
        msg = f"Error parsing config {base_path} with optional override {override_path}: {e}" if override_path is not None else f"Error parsing config {base_path}: {e}"
        raise ValueError(msg)
    except FileNotFoundError:
        raise FileExistsError(f"Config file not found {full_config_path}.")


def save_report_to_disk(report_content, report_file_location):
    """Write the report to a new log file (rotation is handled externally, e.g., logrotate)."""
    report_file = Path(report_file_location)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(report_file, "w") as f:
        f.write(f"[{timestamp}]\n{report_content}\n")
