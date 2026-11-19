import proteus_health_report.main as patient
from proteus_health_report.HealthReportConfigParser import HealthReportConfigParser
from proteus_health_report.Configuration import ProteusHealthConfig
import re
from types import SimpleNamespace
import pytest
from pathlib import Path
from tests import fakes


def describe_arg_parsing():
    def it_sets_expected_defaults():
        parser = patient.setup_argument_parser()
        defaults = parser.parse_args([])

        assert defaults.dry_run is False
        assert defaults.test_webhook is False
        assert defaults.debug is False


def describe_main_entrypoint():
    def it_should_run_and_persist_report_with_default_config(monkeypatch, tmp_path):
        fake = fakes.fake_subprocess(monkeypatch)
        fake.respond("du -sh", "1.2G /var/log/big")
        fake.respond("df -hlP", "Filesystem Size Used Avail Use% Mounted on\n/dev/vda1 20G 18G 2G 90% /")
        config = load_config_from_file()
        config.report.report_file_location = tmp_path / "report.log"
        args_dict = {
            'dry_run': True,
            'test_webhook': False,
            'debug': True
        }

        patient.run(SimpleNamespace(**args_dict), config)

        assert config.report.report_file_location.exists()
        report_content = config.report.report_file_location.read_text(encoding="utf-8")
        assert report_content is not None

        # should include a datetime stamp header
        assert re.search(r"\[\d{8}_\d{6}\]", report_content)
        assert re.search(r"\[\d{8}_\d{6}\]", report_content)

        # enabled in default config
        assert "**My Host Health Report**" in report_content
        assert "**🛠️ Service Statuses:**" in report_content

        # enabled in default config, populated from the faked du/df output
        assert "**🗂️ Logs Size Warnings:**" in report_content
        assert "**🧹 Caches Size Warnings:**" in report_content
        assert "**♨️ Temp Size Warnings:**" in report_content
        assert "  • 1.2G /var/log/big" in report_content
        assert "**💽 Disk Usage Warning:**" in report_content
        assert "  • /dev/vda1 20G 18G 2G 90% /" in report_content

        # disabled in default config
        assert "**🌐 DNS Resolution:**" not in report_content
        assert "**🐳 Active Docker Containers:**" not in report_content
        assert "**⚡️ Power Saving Stats:**" not in report_content
        assert "**📶 Network Stats (vnstat):**" not in report_content

    def it_should_merge_user_provided_config(monkeypatch, tmp_path):
        fakes.fake_subprocess(monkeypatch)
        report_path = Path(tmp_path / "report__it_should_merge_user_provided_config.txt")
        test_report_title = 'it_should_merge_user_provided_config'
        write_test_config_file(test_report_title, report_path)

        config = load_config_from_file()
        args_dict = {
            'dry_run': True,
            'test_webhook': False,
            'debug': True
        }

        patient.run(SimpleNamespace(**args_dict), config)

        assert report_path.exists()
        report_content = report_path.read_text(encoding="utf-8")
        assert report_content is not None

        # overriden by the test config
        assert f"**{test_report_title.title()} Health Report**" in report_content

    def it_should_exit_with_code_given_discord_webhook_not_provided_and_testing_webhook(monkeypatch, tmp_path):
        report_path = Path(tmp_path / "report__it_should_merge_user_provided_config.txt")
        test_report_title = 'it_should_exit_with_code_given_discord_webhook_not_provided_and_testing_webhook'
        write_test_config_file(test_report_title, report_path)

        with pytest.raises(SystemExit) as exc_info:
            config = load_config_from_file()
            args_dict = {
                'dry_run': True,
                'test_webhook': True,  # <--
                'debug': True
            }
            patient.run(SimpleNamespace(**args_dict), config)
        assert exc_info.value.code == 1


def load_config_from_file() -> patient.ProteusHealthConfig:
    """Loads the config file provided in this test environment with debug enabled."""

    config_parser = HealthReportConfigParser().load(app_name="proteus_health_report",
                                                    app_author="Albert Ferguson",
                                                    debug=True
                                                    )
    # Reify the plain INI settings into the strict type contract using the parser
    config: ProteusHealthConfig = config_parser.to_dataclass(ProteusHealthConfig, debug=True)
    return config


def write_test_config_file(test_host_name: str, report_path: Path):
    """Create and write a fake config file for testing. This is .gitignored and generated per-test run."""

    fake_config_path = Path(__file__).parent.parent.resolve() / "src" / "proteus_health_report" / ".config.local.ini"

    fake_config_content = f"""
[report]
hostname={test_host_name}
report_file_location="{report_path}"
webhook_file=""
services_to_monitor="ssh"
    """

    fake_config_path.write_text(fake_config_content, encoding="utf-8")

    assert fake_config_path.exists()


@pytest.fixture(scope="session", autouse=True)
def global_teardown():
    yield
    fake_config_path = Path(__file__).parent.parent.resolve() / "src" / "proteus_health_report" / ".config.local.ini"
    fake_config_path.unlink(missing_ok=True)
