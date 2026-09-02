import proteus_health_report as patient
import pytest
from tests import fakes
import re
from types import SimpleNamespace


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


def describe_send_report():
    def it_raises_value_error_without_webhook_config():
        with pytest.raises(ValueError, match="Cannot send monitor report without webhook config."):
            report_request = fakes.build_empty_report()
            report_request['config']['paths']['webhook_file'] = 'asdasdasdsasa'
            report_request['dry_run'] = False
            patient.send_monitor_report(**report_request)

    def it_attempts_to_network_when_dry_run_is_disabled(monkeypatch):
        with pytest.raises(RuntimeError, match="External network call blocked! Use pytest-mock or responses to mock it."):
            report_request = fakes.build_empty_report()
            report_request['dry_run'] = False
            fakes.patch_fake_webhook(monkeypatch)
            patient.send_monitor_report(**report_request)

    def it_respects_dry_run_when_enabled():
        try:
            report_request = fakes.build_empty_report()
            out = patient.send_monitor_report(**report_request)
        except Exception as e:
            pytest.fail(f'should not raise any exception but raised {e}')

    def it_builds_expected_report_sections():
        report_request = fakes.build_report_with_sections()
        out = patient.send_monitor_report(**report_request)

        assert "**Fake Test Host Health Report**" in out
        assert "**🗂️ Logs Size Warnings:**" in out
        assert "**🧹 Caches Size Warnings:**" in out
        assert "**♨️ Temp Size Warnings:**" in out
        assert "**💽 Disk Usage Warning:**" in out
        assert "**🛠️ Service Statuses:**" in out
        assert "**🌐 DNS Resolution:**" in out
        assert "**🐳 Active Docker Containers:**" in out
        assert "**⚡️ Power Saving Stats:**" in out
        assert "**📶 Network Stats (vnstat):**" in out

    def it_send_monitor_report_truncates_at_2k():
        report_request = fakes.build_report_with_sections()
        # Force a huge report body
        big_entry = "x" * 400
        report_request['logs_warnings'] = [big_entry] * 20
        out = patient.send_monitor_report(**report_request)
        assert "Message truncated" in out
        assert len(out) == 2000


def describe_arg_parsing():
    def it_sets_expected_defaults():
        parser = patient.setup_argument_parser()
        defaults = parser.parse_args([])

        assert defaults.dry_run is False
        assert defaults.test_webhook is False
        assert defaults.config is None


def describe_main_entrypoint():
    def it_should_run_and_persist_report(tmp_path):
        fake_webhook = "https://example.com/webhook"
        fake_webhook_path = tmp_path / "webhook.txt"
        fake_webhook_path.write_text(fake_webhook, encoding="utf-8")

        fake_config_path = tmp_path / "health-report.conf.yaml"
        fake_config_content = fakes.get_fake_config_yaml()
        fake_config_content = fake_config_content.replace(
            "__WEBHOOK_FILE__", str(fake_webhook_path))

        report_path = tmp_path / "results.log"
        fake_config_content = fake_config_content.replace(
            "__REPORT_FILE__", str(report_path))

        fake_config_path.write_text(fake_config_content, encoding="utf-8")

        args_dict = {
            "base_config": fake_config_path,
            'dry_run': True,
            'webhook_file': fake_webhook_path,
            'config': fake_config_path,
            'test_webhook': False
        }
        patient.run(SimpleNamespace(**args_dict))

        assert report_path.exists()
        report_content = report_path.read_text(encoding="utf-8")
        assert report_content is not None

    def it_should_raise_type_error_given_no_config_path(monkeypatch, tmp_path):
        with pytest.raises(TypeError, match=re.escape("unsupported operand type(s) for /: 'PosixPath' and 'NoneType'")):
            fake_webhook = "https://example.com/webhook"
            fake_webhook_path = tmp_path / "webhook.txt"
            fake_webhook_path.write_text(fake_webhook, encoding="utf-8")

            fake_config_path = tmp_path / "health-report.conf.yaml"
            fake_config_content = fakes.get_fake_config_yaml()
            fake_config_content = fake_config_content.replace(
                "__WEBHOOK_FILE__", str(fake_webhook_path))

            report_path = tmp_path / "results.log"
            fake_config_content = fake_config_content.replace(
                "__REPORT_FILE__", str(report_path))

            fake_config_path.write_text(fake_config_content, encoding="utf-8")

            args_dict = {
                "base_config": None,  # <--
                'dry_run': True,
                'webhook_file': fake_webhook_path,
                'config': None,
                'test_webhook': False
            }
            patient.run(SimpleNamespace(**args_dict))

    def it_should_merge_user_provided_config(monkeypatch, tmp_path):
        fake_webhook = "https://example.com/webhook"
        fake_webhook_path = tmp_path / "webhook.txt"
        fake_webhook_path.write_text(fake_webhook, encoding="utf-8")

        fake_config_path = tmp_path / "health-report.conf.yaml"
        fake_config_content = fakes.get_fake_config_yaml()
        fake_config_content = fake_config_content.replace(
            "__WEBHOOK_FILE__", str(fake_webhook_path))

        report_path = tmp_path / "results.log"
        fake_config_content = fake_config_content.replace(
            "__REPORT_FILE__", str(report_path))

        fake_config_path.write_text(fake_config_content, encoding="utf-8")

        fake_user_config_path = tmp_path / "my-config.yaml"
        fake_user_config_content = fakes.get_fake_user_config_yaml()
        fake_user_config_path.write_text(
            fake_user_config_content, encoding="utf-8")

        args_dict = {
            "base_config": fake_config_path,
            'dry_run': True,
            'webhook_file': fake_webhook_path,
            'config': fake_user_config_path,
            'test_webhook': False
        }
        patient.run(SimpleNamespace(**args_dict))

        assert report_path.exists()
        report_content = report_path.read_text(encoding="utf-8")

        # updated by user config
        assert "**Different Hostname!! Health Report**" in report_content

        # disabled by user config
        assert "**🗂️ Logs Size Warnings:**" not in report_content
        assert "**🧹 Caches Size Warnings:**" not in report_content
        assert "**♨️ Temp Size Warnings:**" not in report_content

    def it_should_exit_with_code_given_discord_webhook_not_provided_and_testing_webhook(monkeypatch, tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            fake_config_path = tmp_path / "health-report.conf.yaml"
            fake_config_content = fakes.get_fake_config_yaml()

            report_path = tmp_path / "results.log"
            fake_config_content = fake_config_content.replace(
                "__REPORT_FILE__", str(report_path))

            fake_config_path.write_text(fake_config_content, encoding="utf-8")

            args_dict = {
                "base_config": fake_config_path,
                'dry_run': True,
                'config': fake_config_path,
                'test_webhook': True
            }
            patient.run(SimpleNamespace(**args_dict))
        assert exc_info.value.code == 1
