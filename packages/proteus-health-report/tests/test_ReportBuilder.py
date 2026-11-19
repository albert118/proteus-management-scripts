import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import proteus_health_report.ReportBuilder as report_builder_module
from proteus_health_report.ReportBuilder import ReportBuilder
from proteus_health_report.HealthReportConfigParser import HealthReportConfigParser
from proteus_health_report.Configuration import (
    FileReportingSection,
    NetworkingReportingSection,
    ProteusHealthConfig,
    ReportSection,
    SectionsSection,
)
from tests import fakes

DU_ROWS = ["1.2G\t/var/log/big", "600M\t/var/log/medium"]
DF_ROWS = ["Filesystem Size Used Avail Use% Mounted on", "/dev/vda1 20G 18G 2G 90% /"]


def describe_build_report():
    """
    Integration suite that asserts we can
        - load the expected config
        - drive the expected report from the given config
        - produce the expected report
        - load alternative config

    Shell commands are faked (see tests/fakes.py) so the suite is hermetic and behaves the same on Windows and Linux.
    The per-section behaviour is covered in more detail below.
    """
    def it_builds_expected_report_sections_with_default_config(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)
        fake.respond("du -sh", "\n".join(DU_ROWS))
        fake.respond("df -hlP", "\n".join(DF_ROWS))
        config = load_config_from_file()

        result = ReportBuilder(config).build()

        assert result is not None

        # enabled in default config
        assert "**My Host Health Report**" in result
        assert "**🛠️ Service Statuses:**" in result
        assert "  • ssh: active" in result
        assert "**🗂️ Logs Size Warnings:**" in result
        assert "**🧹 Caches Size Warnings:**" in result
        assert "**♨️ Temp Size Warnings:**" in result
        assert "  • 1.2G\t/var/log/big" in result
        assert "**💽 Disk Usage Warning:**" in result
        assert "  • /dev/vda1 20G 18G 2G 90% /" in result

        # disabled in default config
        assert "**🌐 DNS Resolution:**" not in result
        assert "**🐳 Active Docker Containers:**" not in result
        assert "**⚡️ Power Saving Stats:**" not in result
        assert "**📶 Network Stats (vnstat):**" not in result

    def it_passes_the_default_config_directory_globs_to_du_unquoted(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)
        config = load_config_from_file()

        ReportBuilder(config).build()

        du_commands = fake.commands_containing("du -sh")
        assert [c.split()[4] for c in du_commands] == ["/var/log/*", "/var/cache/*", "/tmp/*"]

    def it_send_monitor_report_truncates_at_2k(monkeypatch):
        fakes.fake_subprocess(monkeypatch)
        config = load_config_from_file()
        # produce a large body by requesting the status of many bogus services
        config.report.services_to_monitor = [f"fake_service_{i}" for i in range(400)]

        result = ReportBuilder(config).build()

        assert "**Message truncated** - Report exceeded 2K char limit!" in result
        assert len(result) == 2000


def describe_check_directory_size():
    def it_runs_du_for_each_path_with_the_threshold_and_collects_the_lines(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)
        fake.respond("/a", "1G\t/a/x")
        fake.respond("/b", "2G\t/b/y\n3G\t/b/z")

        result = ReportBuilder(make_config()).check_directory_size(["/a", "/b"], "500M")

        assert result == ["1G\t/a/x", "2G\t/b/y", "3G\t/b/z"]
        assert fake.commands == ["du -sh -t 500M /a | sort -hr | head -5", "du -sh -t 500M /b | sort -hr | head -5"]

    def it_returns_nothing_given_no_output(monkeypatch):
        fakes.fake_subprocess(monkeypatch)

        assert ReportBuilder(make_config()).check_directory_size(["/a"], "500M") == []

    def it_propagates_a_failed_command(monkeypatch):
        def failing_run(*_args, **_kwargs):
            raise subprocess.CalledProcessError(2, "du")

        monkeypatch.setattr(report_builder_module, "subprocess", SimpleNamespace(run=failing_run))

        with pytest.raises(subprocess.CalledProcessError):
            ReportBuilder(make_config()).check_directory_size(["/a"], "500M")


def describe_with_logs_size_warnings():
    def it_does_nothing_when_disabled(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)

        builder = ReportBuilder(make_config(logs_warnings=False)).with_logs_size_warnings()

        assert builder.logs_size_warnings == []
        assert fake.commands == []

    def it_checks_the_configured_log_directories(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch).respond("du -sh", DU_ROWS[0])
        config = make_config(logs_warnings=True, logs_directories=["/var/log/*", "/srv/log"], file_size="1G")

        builder = ReportBuilder(config).with_logs_size_warnings()

        assert builder.logs_size_warnings == [DU_ROWS[0], DU_ROWS[0]]
        assert fake.commands[0] == "du -sh -t 1G /var/log/* | sort -hr | head -5"
        assert fake.commands[1] == "du -sh -t 1G /srv/log | sort -hr | head -5"

    def it_is_rendered_in_the_report(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("du -sh", DU_ROWS[0])

        report = ReportBuilder(make_config(logs_warnings=True)).build()

        assert f"**🗂️ Logs Size Warnings:**\n  • {DU_ROWS[0]}" in report

    def it_is_omitted_from_the_report_given_no_large_directories(monkeypatch):
        fakes.fake_subprocess(monkeypatch)

        report = ReportBuilder(make_config(logs_warnings=True)).build()

        assert "Logs Size Warnings" not in report


def describe_with_caches_size_warnings():
    def it_does_nothing_when_disabled(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)

        builder = ReportBuilder(make_config(caches_warnings=False)).with_caches_size_warnings()

        assert builder.caches_size_warnings == []
        assert fake.commands == []

    def it_only_checks_directories_with_cache_in_the_path(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch).respond("du -sh", "700M\t/var/cache/apt")
        config = make_config(caches_warnings=True, cache_directories=["/var/cache/*", "/var/lib/other"])

        builder = ReportBuilder(config).with_caches_size_warnings()

        assert builder.caches_size_warnings == ["700M\t/var/cache/apt"]
        assert len(fake.commands) == 1
        assert "/var/cache/*" in fake.commands[0]

    def it_is_rendered_in_the_report(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("du -sh", "700M\t/var/cache/apt")

        report = ReportBuilder(make_config(caches_warnings=True)).build()

        assert "**🧹 Caches Size Warnings:**\n  • 700M\t/var/cache/apt" in report


def describe_with_tmps_size_warnings():
    def it_does_nothing_when_disabled(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)

        builder = ReportBuilder(make_config(temp_warnings=False)).with_tmps_size_warnings()

        assert builder.tmps_size_warnings == []
        assert fake.commands == []

    def it_checks_the_configured_temp_directories(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch).respond("du -sh", "900M\t/tmp/build")

        builder = ReportBuilder(make_config(temp_warnings=True, temp_directories=["/tmp/*"])).with_tmps_size_warnings()

        assert builder.tmps_size_warnings == ["900M\t/tmp/build"]
        assert fake.commands == ["du -sh -t 500M /tmp/* | sort -hr | head -5"]

    def it_runs_once_per_build(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)

        ReportBuilder(make_config(temp_warnings=True, temp_directories=["/tmp/*"])).build()

        assert len(fake.commands_containing("/tmp/*")) == 1

    def it_is_rendered_in_the_report(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("du -sh", "900M\t/tmp/build")

        report = ReportBuilder(make_config(temp_warnings=True)).build()

        assert "**♨️ Temp Size Warnings:**\n  • 900M\t/tmp/build" in report


def describe_with_disk_warnings():
    def it_does_nothing_when_disabled(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)

        builder = ReportBuilder(make_config(disk_warnings=False)).with_disk_warnings()

        assert builder.disk_usage_warning == []
        assert fake.commands == []

    def it_checks_the_configured_device_and_threshold(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch).respond("df -hlP", "\n".join(DF_ROWS))
        config = make_config(disk_warnings=True, disk_device="/dev/sda1", disk_percent=75)

        builder = ReportBuilder(config).with_disk_warnings()

        assert builder.disk_usage_warning == DF_ROWS
        assert fake.commands[0].startswith("df -hlP /dev/sda1 | awk")
        assert 'thr="75"' in fake.commands[0]

    def it_is_rendered_given_a_header_and_a_data_row(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("df -hlP", "\n".join(DF_ROWS))

        report = ReportBuilder(make_config(disk_warnings=True)).build()

        assert f"**💽 Disk Usage Warning:**\n  • {DF_ROWS[0]}\n  • {DF_ROWS[1]}" in report

    def it_is_omitted_given_only_a_header_row(monkeypatch):
        # awk always prints the header, and only prints the data row when usage exceeds the threshold
        fakes.fake_subprocess(monkeypatch).respond("df -hlP", DF_ROWS[0])

        report = ReportBuilder(make_config(disk_warnings=True)).build()

        assert "Disk Usage Warning" not in report


def describe_with_service_statuses():
    def it_does_nothing_when_disabled(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)

        builder = ReportBuilder(make_config(service_statuses=False)).with_service_statuses()

        assert builder.service_statuses == []
        assert fake.commands == []

    def it_reports_active_and_inactive_services_by_exit_code(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)
        fake.respond("is-active nginx", returncode=3)
        fake.respond("is-active ssh", returncode=0)
        config = make_config(service_statuses=True, services_to_monitor=["ssh", "nginx"])

        builder = ReportBuilder(config).with_service_statuses()

        assert builder.service_statuses == ["ssh: active", "nginx: inactive"]
        assert fake.commands == ["systemctl -q is-active ssh", "systemctl -q is-active nginx"]

    def it_is_rendered_in_the_report(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("is-active b", returncode=3)

        report = ReportBuilder(make_config(service_statuses=True, services_to_monitor=["a", "b"])).build()

        assert "**🛠️ Service Statuses:**\n  • a: active\n  • b: inactive" in report


def describe_with_dns_status():
    def it_does_nothing_when_disabled(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)

        builder = ReportBuilder(make_config(dns_resolution=False)).with_dns_status()

        assert builder.dns_status == []
        assert fake.commands == []

    def it_reports_the_resolved_address_of_the_first_domain_only(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch).respond("dig", "142.250.0.1\n")
        config = make_config(dns_resolution=True, dns_test_domain=["first.test", "second.test"])

        builder = ReportBuilder(config).with_dns_status()

        assert builder.dns_status == ["DNS Resolution: OK (142.250.0.1)"]
        assert fake.commands == ["dig +short first.test | head -1"]

    def it_reports_failure_given_no_answer(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("dig", "  \n")

        builder = ReportBuilder(make_config(dns_resolution=True)).with_dns_status()

        assert builder.dns_status == ["DNS Resolution: FAILED"]

    def it_reports_failure_given_a_non_zero_exit(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("dig", "142.250.0.1", returncode=9)

        builder = ReportBuilder(make_config(dns_resolution=True)).with_dns_status()

        assert builder.dns_status == ["DNS Resolution: FAILED"]

    def it_reports_failure_without_running_dig_given_no_test_domain(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)

        builder = ReportBuilder(make_config(dns_resolution=True, dns_test_domain=[])).with_dns_status()

        assert builder.dns_status == ["DNS Resolution: FAILED (no test domain configured)"]
        assert fake.commands == []

    def it_is_rendered_in_the_report(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("dig", "1.2.3.4")

        report = ReportBuilder(make_config(dns_resolution=True)).build()

        assert "**🌐 DNS Resolution:**\n  • DNS Resolution: OK (1.2.3.4)" in report


def describe_with_net_stats():
    def it_does_nothing_when_disabled(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)

        builder = ReportBuilder(make_config(net_stats=False)).with_net_stats()

        assert builder.net_stats == []
        assert fake.commands == []

    def it_collects_non_blank_right_trimmed_lines_for_each_interface(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)
        fake.respond("-i eth0", "eth0  daily   \n\n  day  rx  \n")
        fake.respond("-i wg0", "wg0 daily\n")
        config = make_config(net_stats=True, network_interfaces=["eth0", "wg0"])

        builder = ReportBuilder(config).with_net_stats()

        assert builder.net_stats == ["eth0  daily", "  day  rx", "wg0 daily"]
        assert fake.commands == ["vnstat -i eth0 -d | head -8", "vnstat -i wg0 -d | head -8"]

    def it_keeps_output_from_working_interfaces_when_another_fails(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)
        fake.respond("-i eth0", "", returncode=1)
        fake.respond("-i wg0", "wg0 daily")
        config = make_config(net_stats=True, network_interfaces=["eth0", "wg0"])

        builder = ReportBuilder(config).with_net_stats()

        assert builder.net_stats == ["wg0 daily"]

    @pytest.mark.parametrize("stdout,returncode", [("", 1), ("   \n", 0), ("some output", 127)])
    def it_falls_back_to_an_unavailable_message_when_no_interface_produces_output(monkeypatch, stdout, returncode):
        fakes.fake_subprocess(monkeypatch).respond("vnstat", stdout, returncode=returncode)

        builder = ReportBuilder(make_config(net_stats=True)).with_net_stats()

        assert builder.net_stats == ["Network stats unavailable (vnstat failed or not installed)"]

    def it_renders_the_fallback_message_in_the_report(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("vnstat", "", returncode=127)

        report = ReportBuilder(make_config(net_stats=True)).build()

        assert ("**📶 Network Stats (vnstat):**\n```\n"
                "Network stats unavailable (vnstat failed or not installed)\n```") in report

    def it_renders_stats_in_a_code_block(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("vnstat", "line one\nline two")

        report = ReportBuilder(make_config(net_stats=True)).build()

        assert "**📶 Network Stats (vnstat):**\n```\nline one\nline two\n```" in report


def describe_with_docker_containers():
    def it_does_nothing_when_disabled(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)

        builder = ReportBuilder(make_config(docker_containers=False)).with_docker_containers()

        assert builder.docker_containers == []
        assert fake.commands == []

    def it_reports_unavailable_given_a_failed_command(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("docker ps", "", returncode=127)

        builder = ReportBuilder(make_config(docker_containers=True)).with_docker_containers()

        assert builder.docker_containers == ["Docker unavailable or no containers running"]

    @pytest.mark.parametrize("stdout", ["", "\n", "NAMES\tIMAGE\tSTATUS\n"])
    def it_reports_no_inactive_containers_given_no_rows(monkeypatch, stdout):
        fakes.fake_subprocess(monkeypatch).respond("docker ps", stdout)

        builder = ReportBuilder(make_config(docker_containers=True)).with_docker_containers()

        assert builder.docker_containers == ["✅️ No inactive docker containers"]

    def it_lists_exited_containers_as_a_table(monkeypatch):
        table = "NAMES\tIMAGE\tSTATUS\nweb\tnginx\tExited (1) 2 hours ago"
        fakes.fake_subprocess(monkeypatch).respond("docker ps", table + "\n")

        report = ReportBuilder(make_config(docker_containers=True)).build()

        assert f"**🐳 Active Docker Containers:**\n```\n{table}\n```" in report


def describe_with_power_saving_stats():
    def it_does_nothing_when_disabled(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch)

        builder = ReportBuilder(make_config(power_saving_stats=False)).with_power_saving_stats()

        assert builder.power_saving_stats is None
        assert fake.commands == []

    def it_runs_the_packaged_script_and_keeps_trimmed_output(monkeypatch):
        fake = fakes.fake_subprocess(monkeypatch).respond("check-power-usage.sh", "  profile: power-saver\n")

        builder = ReportBuilder(make_config(power_saving_stats=True)).with_power_saving_stats()

        assert builder.power_saving_stats == "profile: power-saver"
        assert Path(fake.commands[0]).name == "check-power-usage.sh"

    def it_is_rendered_in_the_report(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("check-power-usage.sh", "profile: power-saver")

        report = ReportBuilder(make_config(power_saving_stats=True)).build()

        assert "**⚡️ Power Saving Stats:**\n```\nprofile: power-saver\n```" in report

    def it_is_omitted_given_no_output(monkeypatch):
        fakes.fake_subprocess(monkeypatch)

        report = ReportBuilder(make_config(power_saving_stats=True)).build()

        assert "Power Saving Stats" not in report


def describe_build():
    def it_titles_the_report_with_the_hostname(monkeypatch):
        fakes.fake_subprocess(monkeypatch)

        report = ReportBuilder(make_config(hostname="proteus box")).build()

        assert report == "**Proteus Box Health Report**"

    def it_does_not_truncate_a_report_within_the_limit(monkeypatch):
        fakes.fake_subprocess(monkeypatch).respond("du -sh", "x" * 1500)

        report = ReportBuilder(make_config(logs_warnings=True)).build()

        assert "truncated" not in report
        assert len(report) < 2000


def make_config(hostname="My Host", **overrides) -> ProteusHealthConfig:
    """
    Builds a config with every report section disabled. Overrides are routed by name to the section that owns them,
    so tests only state what they care about.
    """
    sections = SectionsSection(
        logs_warnings=False, caches_warnings=False, temp_warnings=False, disk_warnings=False,
        service_statuses=False, dns_resolution=False, net_stats=False, docker_containers=False,
        power_saving_stats=False,
    )
    report = ReportSection(
        hostname=hostname, webhook_file="", report_file_location=Path("report.log"), services_to_monitor=["ssh"])
    networking = NetworkingReportingSection(network_interfaces=["eth0"], dns_test_domain=["google.com"])
    files = FileReportingSection(
        disk_percent=50, file_size="500M", disk_device="/dev/vda1", logs_directories=["/var/log/*"],
        cache_directories=["/var/cache/*"], temp_directories=["/tmp/*"],
    )

    owners = {"sections": sections, "report": report, "networking_reporting": networking, "file_reporting": files}
    for name, value in overrides.items():
        owner = next(key for key, obj in owners.items() if hasattr(obj, name))
        owners[owner] = replace(owners[owner], **{name: value})

    return ProteusHealthConfig(**owners)


def load_config_from_file() -> ProteusHealthConfig:
    """Loads the config file provided in this test environment with debug enabled."""

    config_parser = HealthReportConfigParser().load(app_name="proteus_health_report",
                                                    app_author="Albert Ferguson",
                                                    debug=True
                                                    )
    # Reify the plain INI settings into the strict type contract using the parser
    config: ProteusHealthConfig = config_parser.to_dataclass(ProteusHealthConfig, debug=True)
    return config
