#!/usr/bin/env python3
"""Health monitoring script that triggers a health report Discord notification."""

# Ensure logrotate is configured to avoid polluting the disk
# /var/log/ganymede-health-reports/report.log {
#     weekly
#     rotate 1
#     compress
#     notifempty
#     create 644 root root
#     delaycompress
#     missingok
# }

import sys
import argparse
import requests
import subprocess
from pathlib import Path
import datetime
import yaml


def load_config(config_path):
    """Load configuration from YAML file or return defaults if not found."""
    # Try to find config file in same directory as script
    script_dir = Path(__file__).parent
    full_config_path = script_dir / config_path

    if not full_config_path.exists():
        print(
            f"Config file does not exist at {full_config_path}, ensure it exists before running this health report.")
        sys.exit(1)

    config = {}
    if full_config_path.exists():
        try:
            with open(full_config_path, 'r') as f:
                config = yaml.safe_load(f)
                if config is None:
                    config = {}
        except yaml.YAMLError as err:
            print(f"Error parsing config file {full_config_path}: {err}")
            sys.exit(1)
        except FileNotFoundError:
            print(
                f"Config file does not exist at {full_config_path}, ensure it exists before running this health report.")
            sys.exit(1)

    return config


def merge_cli_with_config(args, config):
    """
    Merge CLI arguments with config.
    Currently, only the --config flag overrides config loading.
    All other settings come from the config file.
    """
    # CLI args are now only for runtime flags (--dry-run, --test-webhook)
    # Config file is the single source of truth for all settings
    return config


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


def check_directory_size(paths, threshold):
    """Check directory sizes for the given paths list and threshold."""
    results = []
    for path in paths:
        command = f"du -sh -t {threshold} {path} | sort -hr | head -5"
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=True,
            check=True
        )

        if result.returncode != 0:
            print(
                f"Error running script check to assert disk size of {path} (exit {result.returncode}):\n{result.stderr}")
            sys.exit(1)

        entries = [entry for entry in result.stdout.splitlines()]
        results.extend(entries)

    return results


def check_disk_usage(disk_device, threshold):
    """Check disk usage on the specified device against threshold."""
    command = f"df -hlP {disk_device} | awk -v thr=\"{threshold}\" 'NR==1 {{ print; next }} {{ sub(/%/, \"\", $5); if ($5+0 > thr+0) print }}'"

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=True,
        check=True
    )

    if result.returncode != 0:
        print(
            f"Error running script check to assert disk usage (exit {result.returncode}):\n{result.stderr}")
        sys.exit(1)

    results = [entry for entry in result.stdout.splitlines()]
    return results


def check_service_statuses(services):
    results = []

    for service in services:
        command = f"systemctl -q is-active {service}"
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=True
        )
        status = "active" if result.returncode == 0 else "inactive"
        results.append(f"{service}: {status}")

    return results


def check_dns_resolution(test_domain="google.com"):
    """Check DNS resolution by attempting to resolve the given domain."""
    command = f"dig +short {test_domain} | head -1"
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=True
    )

    if result.returncode == 0 and result.stdout.strip():
        ip_address = result.stdout.strip()
        return [f"DNS Resolution: OK ({ip_address})"]
    else:
        return ["DNS Resolution: FAILED"]


def check_network_stats(interfaces):
    """Run vnstat for chosen interfaces and return ASCII-formatted stats lines."""
    all_lines = []
    for iface in interfaces:
        command = f"vnstat -i {iface} -d | head -8"
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=True
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = [line.rstrip()
                     for line in result.stdout.splitlines() if line.strip()]
            all_lines.extend(lines)
    if not all_lines:
        return ["Network stats unavailable (vnstat failed or not installed)"]
    return all_lines


def check_active_docker_containers():
    """Get list of exited docker containers in table format."""
    command = "docker ps -f 'status=exited' --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'"
    table = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=True
    )

    if table.returncode != 0:
        return ["Docker unavailable or no containers running"]

    lines = [line.rstrip()
             for line in table.stdout.splitlines() if line.strip()]

    if not lines or (len(lines) == 1 and "NAMES" in lines[0]):
        return ["✅️ No inactive docker containers"]

    return lines


def check_power_saving_stats():
    """Parses the audit log file of the power saving script output. Calculates several stats and reports some stats."""
    command = "/home/albertferguson/git/proteus-management-scripts/check-power-usage.sh"
    stats = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=True
    )

    return stats.stdout.strip()


def save_report_to_disk(report_content, report_file_location):
    """Write the report to a new log file (rotation is handled externally, e.g., logrotate)."""
    report_file = Path(report_file_location)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(report_file, "w") as f:
        f.write(f"[{timestamp}]\n{report_content}\n")


def send_monitor_report(config, logs_warnings, caches_warnings, tmps_warnings, disk_warnings, service_statuses, dns_status, net_stats, docker_containers, power_saving_stats, dry_run=False):
    """Compile system monitor report and send to Discord webhook."""
    webhook_file = config['paths']['webhook_file']
    webhook_url = get_discord_webhook(webhook_file)
    if not webhook_url and not dry_run:
        raise ValueError('Cannot send monitor report without webhook config.')

    report_sections = [f"**{config['hostname'].title()} Health Report**"]

    # Use config section toggles to conditionally add sections
    if config['sections']['logs_warnings'] and logs_warnings:
        logs_formatted = "\n".join(f"  • {entry}" for entry in logs_warnings)
        report_sections.append(f"**🗂️ Logs Size Warnings:**\n{logs_formatted}")

    if config['sections']['caches_warnings'] and caches_warnings:
        caches_formatted = "\n".join(
            f"  • {entry}" for entry in caches_warnings)
        report_sections.append(
            f"**🧹 Caches Size Warnings:**\n{caches_formatted}")

    if config['sections']['temp_warnings'] and tmps_warnings:
        tmps_formatted = "\n".join(f"  • {entry}" for entry in tmps_warnings)
        report_sections.append(f"**♨️ Temp Size Warnings:**\n{tmps_formatted}")

    # ie. has header row + data (length of 2 expected)
    if config['sections']['disk_warnings'] and disk_warnings and len(disk_warnings) > 1:
        disk_formatted = "\n".join(f"  • {entry}" for entry in disk_warnings)
        report_sections.append(f"**💽 Disk Usage Warning:**\n{disk_formatted}")

    # Add service status section
    if config['sections']['service_statuses'] and service_statuses:
        service_formatted = "\n".join(
            f"  • {status}" for status in service_statuses)
        report_sections.append(
            f"**🛠️ Service Statuses:**\n{service_formatted}")

    # Add DNS status section
    if config['sections']['dns_resolution'] and dns_status:
        dns_formatted = "\n".join(f"  • {status}" for status in dns_status)
        report_sections.append(f"**🌐 DNS Resolution:**\n{dns_formatted}")

    # Add docker containers section
    if config['sections']['docker_containers'] and docker_containers:
        containers_formatted = "\n".join(docker_containers)
        report_sections.append(
            f"**🐳 Active Docker Containers:**\n```\n{containers_formatted}\n```")

    # Add power saving stats section
    if config['sections']['power_saving_stats'] and power_saving_stats:
        report_sections.append(
            f"**⚡️ Power Saving Stats:**\n```\n{power_saving_stats}\n```")

    # Add network stats section
    if net_stats:
        if isinstance(net_stats, list):
            net_stats = "\n".join(net_stats)
        report_sections.append(
            f"**📶 Network Stats (vnstat):**\n```\n{net_stats}\n```")

    report_message = "\n\n".join(report_sections)

    # Check if the message length is greater than the webhook limit and truncate if necessary
    max_length = 2000
    if len(report_message) > max_length:
        # Reserve space for truncation warning
        warning = "\n\n⚠️ **Message truncated** - Report exceeded 2K char limit!"
        available_length = max_length - len(warning)
        report_message = report_message[:available_length] + warning

    if dry_run:
        print("\n=== DRY RUN - Report Preview ===")
        print(report_message)
        print(f"\nMessage length: {len(report_message)} characters")
    else:
        discord_notification(webhook_url, report_message)

    return report_message


def setup_argument_parser():
    """Set up and return the argument parser for the script."""
    parser = argparse.ArgumentParser(
        description='System monitor script that checks disk usage and service statuses',
        epilog='Configuration is set in health-report.conf.yaml (or custom path via --config).')

    parser.add_argument(
        '--config',
        default='health-report.conf.yaml',
        help='Path to config file (default: health-report.conf.yaml in script directory)')

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print report instead of sending to Discord')

    parser.add_argument(
        '--test-webhook',
        action='store_true',
        help='Send a test notification to the Discord webhook and exit')

    return parser


def main(args) -> None:
    # Load configuration from file
    config = load_config(args.config)

    # Merge CLI arguments with config (CLI takes precedence)
    config = merge_cli_with_config(args, config)

    if args.test_webhook:
        # Test mode: verify webhook works by sending a small test message and exit.
        webhook_url = get_discord_webhook(config['paths']['webhook_file'])
        if not webhook_url:
            print("Error: Discord webhook URL not set or invalid.")
            sys.exit(1)
        discord_notification(
            webhook_url, "**Test**: Proteus Discord webhook is working ✅")
        return

    if not args.dry_run:
        webhook_url = get_discord_webhook(config['paths']['webhook_file'])
        if not webhook_url:
            print("Error: DISCORD_WEBHOOK_URL not set. Ensure it is provided and valid.")
            sys.exit(1)

    # Run enabled checks based on config
    logs_size_warnings = []
    if config['sections']['logs_warnings']:
        logs_size_warnings = check_directory_size(
            config['paths']['logs_directories'],
            config['thresholds']['file_size'])

    caches_size_warnings = []
    if config['sections']['caches_warnings']:
        # For now, caches_warnings uses the same directories from config
        # In future, could separate cache-specific directories
        caches_size_warnings = check_directory_size(
            [d for d in config['paths']['cache_directories'] if 'cache' in d],
            config['thresholds']['file_size'])

    tmps_size_warnings = []
    if config['sections']['temp_warnings']:
        tmps_size_warnings = check_directory_size(
            [d for d in config['paths']['temp_directories']],
            config['thresholds']['file_size'])

    disk_usage_warning = []
    if config['sections']['disk_warnings']:
        disk_usage_warning = check_disk_usage(
            config['paths']['disk_device'],
            config['thresholds']['disk_percent'])

    service_statuses = []
    if config['sections']['service_statuses']:
        service_statuses = check_service_statuses(
            config['services']['to_monitor'])

    dns_status = []
    if config['sections']['dns_resolution']:
        dns_status = check_dns_resolution(config['dns']['test_domain'])

    net_stats = []
    if config['sections']['net_stats']:
        net_stats = check_network_stats(config['network_interfaces'])

    docker_containers = []
    if config['sections']['docker_containers']:
        docker_containers = check_active_docker_containers()

    power_saving_stats = None
    if config['sections']['power_saving_stats']:
        power_saving_stats = check_power_saving_stats()

    # Send disk usage report to Discord
    report_message = send_monitor_report(
        config,
        logs_size_warnings,
        caches_size_warnings,
        tmps_size_warnings,
        disk_usage_warning,
        service_statuses,
        dns_status,
        net_stats,
        docker_containers,
        power_saving_stats,
        dry_run=args.dry_run
    )

    # Always save report to disk for backup
    save_report_to_disk(
        report_message, config['paths']['report_file_location'])


if __name__ == "__main__":
    parser = setup_argument_parser()
    args = parser.parse_args()
    main(args)
