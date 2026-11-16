import proteus_health_report.utils as patient
import re
from tests import fakes
from pathlib import Path


def describe_save_report_to_disk():
    def it_writes_to_file_with_contents_and_timestamp(tmp_path):
        report_file = Path(tmp_path / "test-report.log")
        fake_content = "hello-world"
        # Matches [YYYYMMDD_HHMMSS]
        expected_timestamp_re = r"\[\d{8}_\d{6}\]"

        patient.save_report_to_disk(fake_content, report_file)

        assert report_file.exists()
        content = report_file.read_text(encoding="utf-8")

        assert re.match(expected_timestamp_re, content) is not None
        assert content.endswith(f"{fake_content}\n")

    def it_makes_parent_directories_if_missing(tmp_path):
        report_file = Path(tmp_path / "grandparent/parent/test-report.log")
        fake_content = "hello-world"
        patient.save_report_to_disk(fake_content, report_file)
        assert report_file.exists()

    def it_allows_existing_directories(tmp_path):
        report_file = Path(tmp_path / "test-report.log")
        fake_content = "hello-world"
        patient.save_report_to_disk(fake_content, report_file)

        patient.save_report_to_disk(fake_content, report_file)

        assert report_file.exists()


def describe_discord_webhook():
    def it_reads_and_strips_when_getting_hook_url(tmp_path):
        fake_webhook = "https://example.com/webhook"
        fake_path = tmp_path / "webhook.txt"
        fake_path.write_text(f"  {fake_webhook}  \n", encoding="utf-8")

        result = patient.get_discord_webhook(str(fake_path))
        assert result == fake_webhook

    def it_returns_none_when_when_getting_hook_url_and_not_in_file(tmp_path):
        missing = tmp_path / "missing.txt"
        assert patient.get_discord_webhook(str(missing)) is None

    def it_sends_notification_given_webhook_url_and_message(monkeypatch, capsys):
        fake_webhook = "https://fake.lan/webhook?12345678"
        fake_message = "hello world!"
        fakes.fake_webhook_call(monkeypatch, status_code=200)

        success = patient.discord_notification(fake_webhook, fake_message)

        out = capsys.readouterr().out
        assert "Triggered Discord notifier webhook\n" == out
        assert success

    def it_fails_when_sending_notification_given_bad_response(monkeypatch, capsys):
        fake_webhook = "https://fake.lan/webhook?12345678"
        fake_message = "hello world!"
        fakes.fake_webhook_call(monkeypatch, status_code=500)

        success = patient.discord_notification(fake_webhook, fake_message)

        out = capsys.readouterr().out
        assert "Failed to trigger Discord notifier webhook: 500 Client/Server Error\n" == out
        assert not success
