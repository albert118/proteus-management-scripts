
from proteus_health_report.ReportBuilder import ReportBuilder
from proteus_health_report.Configuration import ProteusHealthConfig
import proteus_health_report.utils as utils


def notify(config: ProteusHealthConfig, message: str, dry_run=False) -> None:
    """Send of the message notification using the configured Discord webhook"""
    webhook_url = utils.get_discord_webhook(config.report.webhook_file)
    if not webhook_url and not dry_run:
        raise ValueError('Cannot send monitor report without webhook config.')

    if dry_run:
        print("\n=== DRY RUN - Report Preview ===")
        print(message)
        print(f"\nMessage length: {len(message)} characters")
    else:
        utils.discord_notification(webhook_url, message)
