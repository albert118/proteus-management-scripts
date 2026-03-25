#!/usr/bin/env python3
"""Health monitoring script that triggers a health report Discord notification."""

# Ensure logrotate is configured to avoid polluting the disk
# /var/log/proteus-health-reports/report.log {
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
    except requests.exceptions.HTTPError as err:
        print(f"Failed to trigger Discord notifier webhook: {err}")


def check_directory_size(path, threshold):
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

    results = [entry for entry in result.stdout.splitlines()]
    return results


def check_disk_usage(threshold):
    # /dev/vda1 is the primary disk on this machine
    command = f"df -hlP /dev/vda1 | awk -v thr=\"{threshold}\" 'NR==1 {{ print; next }} {{ sub(/%/, \"\", $5); if ($5+0 > thr+0) print }}'"

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


def check_dns_resolution():
    """Check DNS resolution by attempting to resolve google.com."""
    command = "dig +short google.com | head -1"
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


def check_network_stats():
    """Run vnstat for chosen interfaces and return a concise monthly/daily summary."""
    # Use awk to extract just the monthly and daily bandwidth lines.
    command = r"""vnstat -i eth0 wg0 2>/dev/null | awk -F'|' '
/ since / { iface=$1; gsub(/^ +| +$/,"",iface); split(iface,a," "); iface=a[1]; next }
/^ *20[0-9][0-9]-/ {
  line=$0; gsub(/^ +| +$/,"",line);
  split(line,parts,"|");
  n=split(parts[1],a," "); rx=a[n];
  gsub(/^ +| +$/,"",parts[2]); tx=parts[2];
  gsub(/^ +| +$/,"",parts[3]); total=parts[3];
  print iface " (monthly): rx " rx ", tx " tx ", total " total;
}
/^ *today/ {
  line=$0; gsub(/^ +| +$/,"",line);
  split(line,parts,"|");
  n=split(parts[1],a," "); rx=a[n];
  gsub(/^ +| +$/,"",parts[2]); tx=parts[2];
  gsub(/^ +| +$/,"",parts[3]); total=parts[3];
  print iface " (daily): rx " rx ", tx " tx ", total " total;
}
'"""

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=True
    )

    if result.returncode != 0 or not result.stdout.strip():
        return ["Network stats unavailable (vnstat failed or not installed)"]

    return [line for line in result.stdout.splitlines() if line.strip()]


def save_report_to_disk(report_content):
    """Write the report to a new log file (rotation is handled externally, e.g., logrotate)."""
    report_file = Path("/var/log/proteus-health-reports/report.log")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(report_file, "w") as f:
        f.write(f"[{timestamp}]\n{report_content}\n")


def send_monitor_report(logs_warnings, caches_warnings, tmps_warnings, disk_warnings, service_statuses, dns_status, net_stats, dry_run=False, webhook_file='discord-webhook-url.txt'):
    """Compile system monitor report and send to Discord webhook."""

    webhook_url = get_discord_webhook(webhook_file)
    if not webhook_url and not dry_run:
        return

    report_sections = ["**Proteus Health Report**"]

    if logs_warnings:
        logs_formatted = "\n".join(f"  • {entry}" for entry in logs_warnings)
        report_sections.append(f"**🗂️ Logs Size Warnings:**\n{logs_formatted}")

    if caches_warnings:
        caches_formatted = "\n".join(
            f"  • {entry}" for entry in caches_warnings)
        report_sections.append(
            f"**🧹 Caches Size Warnings:**\n{caches_formatted}")

    if tmps_warnings:
        tmps_formatted = "\n".join(f"  • {entry}" for entry in tmps_warnings)
        report_sections.append(f"**♨️ Temp Size Warnings:**\n{tmps_formatted}")

    # ie. has header row + data (length of 2 expected)
    if disk_warnings and len(disk_warnings) > 1:
        disk_formatted = "\n".join(f"  • {entry}" for entry in disk_warnings)
        report_sections.append(f"**💽 Disk Usage Warning:**\n{disk_formatted}")

    # Add service status section
    if service_statuses:
        service_formatted = "\n".join(
            f"  • {status}" for status in service_statuses)
        report_sections.append(
            f"**🛠️ Service Statuses:**\n{service_formatted}")

    # Add DNS status section
    if dns_status:
        dns_formatted = "\n".join(f"  • {status}" for status in dns_status)
        report_sections.append(f"**🌐 DNS Resolution:**\n{dns_formatted}")

    # Add network stats section
    if net_stats:
        net_formatted = "\n".join(f"  • {line}" for line in net_stats)
        report_sections.append(
            f"**📶 Network Stats (vnstat):**\n{net_formatted}")

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
        description='System monitor script that checks disk usage and service statuses')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print report instead of sending to Discord')
    parser.add_argument('--webhook-file', default='discord-webhook-url.txt',
                        help='Path to Discord webhook URL file (default: discord-webhook-url.txt)')
    parser.add_argument('--file-size-threshold', default='20M',
                        help='File size threshold for warnings (default: 20M)')
    parser.add_argument('--disk-threshold', default='50',
                        help='Disk usage percentage threshold for warnings (default: 50)')
    parser.add_argument('--services', nargs='+', default=['nginx', 'ssh', 'fail2ban', 'wg-quick@wg0', 'ufw', 'crontab-guru-dashboard'],
                        help='Services to monitor (default: nginx ssh fail2ban wg-quick@wg0 ufw crontab-guru-dashboard)')
    parser.add_argument('--test-webhook', action='store_true',
                        help='Send a test notification to the Discord webhook and exit')
    return parser


def main() -> None:
    parser = setup_argument_parser()
    args = parser.parse_args()

    if args.test_webhook:
        # Test mode: verify webhook works by sending a small test message and exit.
        webhook_url = get_discord_webhook(args.webhook_file)
        if not webhook_url:
            print("Error: Discord webhook URL not set or invalid.")
            sys.exit(1)
        discord_notification(
            webhook_url, "**Test**: Proteus Discord webhook is working ✅")
        return

    if not args.dry_run and not args.webhook_file:
        print("Error: DISCORD_WEBHOOK_URL not set. Ensure that the file source exists.")
        sys.exit(1)

    if not args.dry_run:
        webhook_url = get_discord_webhook(args.webhook_file)
        if not webhook_url:
            print("Error: DISCORD_WEBHOOK_URL not set. Ensure it is provided and valid.")
            sys.exit(1)

    # check disk usage for well known directories
    logs_size_warnings = check_directory_size(
        "/var/log/*", args.file_size_threshold)
    caches_size_warnings = check_directory_size(
        "/var/cache/*", args.file_size_threshold)
    tmps_size_warnings = check_directory_size(
        "/tmp/*", args.file_size_threshold)

    # check disk usage
    disk_usage_warning = check_disk_usage(args.disk_threshold)

    # check known services are active
    service_statuses = check_service_statuses(args.services)

    # check DNS resolution
    dns_status = check_dns_resolution()

    # check network stats
    net_stats = check_network_stats()

    # Send disk usage report to Discord
    report_message = send_monitor_report(
        logs_size_warnings,
        caches_size_warnings,
        tmps_size_warnings,
        disk_usage_warning,
        service_statuses,
        dns_status,
        net_stats,
        dry_run=args.dry_run,
        webhook_file=args.webhook_file
    )

    # Always save report to disk for backup
    save_report_to_disk(report_message)


if __name__ == "__main__":
    main()
