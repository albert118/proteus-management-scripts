from proteus_health_report.ReportBuilder import ReportBuilder
from proteus_health_report.HealthReportConfigParser import HealthReportConfigParser
from proteus_health_report.Configuration import ProteusHealthConfig, SectionsSection, NetworkingReportingSection, FileReportingSection


def describe_build_report():
    """
    Integration suite that asserts we can
        - load the expected config
        - drive the expected report from the given config
        - produce the expected report
        - load alternative config

    This could be a distinct set of unittests for each unit. However, this is more valuable as an integration suite
    to prove this contract is functional in one pass. What I do not want to maintain is distinct fake configs for each
    unit in addition to the real config (files).
    """
    def it_builds_expected_report_sections_with_default_config():
        config = load_config_from_file()

        result = ReportBuilder(config).build()

        assert result is not None

        # enabled in default config
        assert "**My Host Health Report**" in result
        assert "**🛠️ Service Statuses:**" in result

        # disabled in default config
        assert "**🗂️ Logs Size Warnings:**" not in result
        assert "**🧹 Caches Size Warnings:**" not in result
        assert "**♨️ Temp Size Warnings:**" not in result
        assert "**💽 Disk Usage Warning:**" not in result
        assert "**🌐 DNS Resolution:**" not in result
        assert "**🐳 Active Docker Containers:**" not in result
        assert "**⚡️ Power Saving Stats:**" not in result
        assert "**📶 Network Stats (vnstat):**" not in result

    def it_send_monitor_report_truncates_at_2k():
        config = load_config_from_file()
        # produce a large body by requesting the status of many bogus services
        # however, this will take time as we are ACTUALLY running this code to check for these services
        # so I'm not adding many of these tests
        config.report.services_to_monitor = [f"fake_service_{i}" for i in range(400)]

        result = ReportBuilder(config).build()

        assert "**Message truncated** - Report exceeded 2K char limit!" in result
        assert len(result) == 2000


def load_config_from_file() -> ProteusHealthConfig:
    """Loads the config file provided in this test environment with debug enabled."""

    config_parser = HealthReportConfigParser().load(app_name="proteus_health_report",
                                                    app_author="Albert Ferguson",
                                                    debug=True
                                                    )
    # Reify the plain INI settings into the strict type contract using the parser
    config: ProteusHealthConfig = config_parser.to_dataclass(ProteusHealthConfig, debug=True)
    return config
