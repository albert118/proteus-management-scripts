import proteus_health_report.notifier as patient
from proteus_health_report.Configuration import ReportSection, ProteusHealthConfig
import pytest
from pathlib import Path


def describe_notifier():
    def it_raises_value_error_without_webhook_config_given_not_a_dry_run():
        with pytest.raises(ValueError, match="Cannot send monitor report without webhook config."):
            fake_config = build_fake_config()
            fake_config.report.webhook_file = Path('./test_notifier.py')  # type: ignore
            patient.notify(fake_config, "fake message", dry_run=False)

    def it_respects_dry_run_when_enabled():
        try:
            fake_config = build_fake_config()
            fake_config.report.webhook_file = Path('./test_notifier.py')  # type: ignore
            patient.notify(fake_config, "fake message", dry_run=True)
        except Exception as e:
            pytest.fail(f'should not raise any exception but raised {e}')


def build_fake_config() -> ProteusHealthConfig:
    report_section = ReportSection(
        hostname='http://fake.fake',
        webhook_file='1234',
        report_file_location=None,  # type: ignore
        services_to_monitor=[],
    )

    return ProteusHealthConfig(
        report=report_section,
        sections=None,  # type: ignore
        networking_reporting=None,  # type: ignore
        file_reporting=None  # type: ignore
    )
