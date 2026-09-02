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
from proteus_health_report.ReportBuilder import ReportBuilder
from proteus_health_report.Configuration import ProteusHealthConfig
import proteus_health_report.utils as utils
from proteus_health_report.HealthReportConfigParser import HealthReportConfigParser
from proteus_health_report.notifier import notify


def setup_argument_parser():
    """Set up and return the argument parser for the script."""
    parser = argparse.ArgumentParser(
        description='System monitor script that checks disk usage and service statuses',
        epilog='Configuration is set in health-report.conf.yaml (or custom path via --config).')

    parser.add_argument(
        '--base-config',
        required=False,
        default="health-report.conf.yaml",
        help='Path to user base config file. This is the expected default configuration that the report ships with.')

    parser.add_argument(
        '--config',
        required=False,
        help='Path to user defined config file. Allows configuring the report sections, etc. as preferred by the user.')

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print report instead of sending to Discord')

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Print debug logs')

    parser.add_argument(
        '--test-webhook',
        action='store_true',
        help='Send a test notification to the Discord webhook and exit')

    return parser


def run(args, config: ProteusHealthConfig) -> None:
    if args.test_webhook:
        # Test mode: verify webhook works by sending a small test message and exit.
        webhook_url = utils.get_discord_webhook(config.report.webhook_file)
        if not webhook_url:
            print("Error: Discord webhook URL not set or invalid.")
            sys.exit(1)
        utils.discord_notification(
            webhook_url, "**Test**: Proteus Discord webhook is working ✅")
        return

    if not args.dry_run:
        webhook_url = utils.get_discord_webhook(config.report.webhook_file)
        if not webhook_url:
            print("Error: DISCORD_WEBHOOK_URL not set. Ensure it is provided and valid.")
            sys.exit(1)

    report_message = ReportBuilder(config).build()
    notify(config, report_message, dry_run=args.dry_run)
    # always save report to disk for posterity
    utils.save_report_to_disk(report_message, config.report.report_file_location)


def main() -> None:
    arg_parser = setup_argument_parser()
    args = arg_parser.parse_args()

    config_parser = HealthReportConfigParser().load(app_name="ProteusHealth", app_author="Proteus", debug=args.debug)
    # Reify the plain INI settings into the strict type contract using the parser
    config: ProteusHealthConfig = config_parser.to_dataclass(ProteusHealthConfig, debug=args.debug)

    run(args, config)


if __name__ == "__main__":
    main()
