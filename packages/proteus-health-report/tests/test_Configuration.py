import configparser
from dataclasses import fields
from importlib import resources
from pathlib import Path

import pytest

from proteus_health_report.Configuration import ProteusHealthConfig
from proteus_health_report.HealthReportConfigParser import HealthReportConfigParser


def describe_configuration_schema_contract():
    """
    default_config.ini and the ProteusHealthConfig dataclasses are two halves of one contract: the INI is the
    documented user surface, the dataclasses are what the code consumes. These tests fail when one drifts from the other.
    """
    def it_has_an_ini_section_for_every_dataclass_section():
        ini = load_default_ini()

        assert set(ini.sections()) == {f.name for f in fields(ProteusHealthConfig)}

    def it_has_an_ini_option_for_every_dataclass_field():
        ini = load_default_ini()

        for section_field in fields(ProteusHealthConfig):
            expected = {f.name for f in fields(section_field.type)}
            assert set(ini.options(section_field.name)) == expected, f"[{section_field.name}] options differ"

    def it_reifies_the_packaged_default_into_the_dataclasses():
        config = load_default_ini().to_dataclass(ProteusHealthConfig)

        assert config.report.hostname == "My Host"
        assert config.report.webhook_file == "discord-webhook-url.txt"
        assert config.report.report_file_location == Path("~/logs/proteus_health_report/report.log")
        assert config.report.services_to_monitor == ["ssh"]
        assert config.file_reporting.disk_percent == 50
        assert config.file_reporting.file_size == "500M"
        assert config.file_reporting.disk_device == "/dev/vda1"
        assert config.networking_reporting.network_interfaces == ["eth0"]
        assert config.networking_reporting.dns_test_domain == ["google.com"]

    def it_strips_quotes_from_the_default_directory_lists():
        config = load_default_ini().to_dataclass(ProteusHealthConfig)

        assert config.file_reporting.logs_directories == ["/var/log/*"]
        assert config.file_reporting.cache_directories == ["/var/cache/*"]
        assert config.file_reporting.temp_directories == ["/tmp/*"]

    def it_enables_only_the_cheap_sections_by_default():
        sections = load_default_ini().to_dataclass(ProteusHealthConfig).sections

        assert sections.logs_warnings and sections.caches_warnings and sections.temp_warnings
        assert sections.disk_warnings and sections.service_statuses
        assert not (sections.dns_resolution or sections.net_stats or sections.docker_containers
                    or sections.power_saving_stats)

    def it_requires_every_option_that_has_no_dataclass_default(tmp_path):
        partial = tmp_path / "partial.ini"
        partial.write_text("[report]\nhostname=only", encoding="utf-8")
        config = HealthReportConfigParser()
        config.load_hierarchy([partial])

        with pytest.raises(configparser.NoOptionError):
            config.to_dataclass(ProteusHealthConfig)


def load_default_ini() -> HealthReportConfigParser:
    config = HealthReportConfigParser()
    config.load_hierarchy([resources.files("proteus_health_report").joinpath("default_config.ini")])
    return config
