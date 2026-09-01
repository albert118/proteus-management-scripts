import os
import yaml
from pathlib import Path
import datetime
import shutil
from importlib.resources import files


def get_package_config_path(default_config_path="health-report.conf.yaml"):
    """Pytest will not resolve the package name but in prod this is preferred"""

    package_name = "proteus_health_report"

    package_config_path = (
        files(package_name)
        .joinpath(default_config_path)
    )

    return package_config_path


def deep_merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(base_path, override_path=None):
    """
    Load the provided base config and optionally override with addtional user config if provided.
    - if no config exists at all, then a default config file will be generated from the package defaults
    - if an override path is given, then the custom config file be used
    - custom config is deep-merged with the base config
    """

    # Try to find config file in same directory as script
    # TODO: whack I'm too tired
    script_dir = Path(__file__).parent.parent
    full_config_path = script_dir / base_path

    try:
        config = {}

        # ensure that the base config exists
        if not Path(base_path).exists():
            package_config_path = get_package_config_path()
            print(
                f'creating default config at {full_config_path} from {package_config_path}')

            # Copy the default file to the user's directory
            with package_config_path.open("r") as src, open(full_config_path, "w") as dst:
                shutil.copyfileobj(src, dst)

        print(base_path)
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
