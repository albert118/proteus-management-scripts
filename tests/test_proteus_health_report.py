from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "proteus-health-report.py"

    loader = SourceFileLoader("proteus_health_report", str(module_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None

    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


PROTEUS_HEALTH_REPORT = load_module()


def test_get_discord_webhook_reads_and_strips(tmp_path):
    p = tmp_path / "webhook.txt"
    p.write_text("  https://example.com/webhook  \n", encoding="utf-8")

    assert (
        PROTEUS_HEALTH_REPORT.get_discord_webhook(str(p))
        == "https://example.com/webhook"
    )


def test_get_discord_webhook_missing_file_returns_none(tmp_path, capsys):
    missing = tmp_path / "missing.txt"
    assert PROTEUS_HEALTH_REPORT.get_discord_webhook(str(missing)) is None


def test_send_monitor_report_dry_run_builds_sections(monkeypatch):
    # Avoid any webhook I/O
    monkeypatch.setattr(
        PROTEUS_HEALTH_REPORT,
        "get_discord_webhook",
        lambda _path: "http://hook.example",
    )

    out = PROTEUS_HEALTH_REPORT.send_monitor_report(
        logs_warnings=["log1", "log2"],
        caches_warnings=["cache1"],
        tmps_warnings=[],
        disk_warnings=["hdr", "diskwarn"],
        service_statuses=["nginx: active"],
        dns_status=["DNS Resolution: OK (1.2.3.4)"],
        net_stats=["wg0 (monthly): rx 1, tx 2, total 3"],
        dry_run=True,
        webhook_file="does-not-matter.txt",
    )

    assert "**Proteus Health Report**" in out
    assert "Logs Size Warnings" in out
    assert "Caches Size Warnings" in out
    assert "Disk Usage Warning" in out
    assert "Service Statuses" in out
    assert "DNS Resolution" in out
    assert "Network Stats (vnstat)" in out


def test_send_monitor_report_truncates_at_2k(monkeypatch):
    monkeypatch.setattr(
        PROTEUS_HEALTH_REPORT,
        "get_discord_webhook",
        lambda _path: "http://hook.example",
    )

    # Force a huge report body
    big_entry = "x" * 400
    logs_warnings = [big_entry] * 20

    out = PROTEUS_HEALTH_REPORT.send_monitor_report(
        logs_warnings=logs_warnings,
        caches_warnings=[],
        tmps_warnings=[],
        disk_warnings=[],
        service_statuses=[],
        dns_status=[],
        net_stats=[],
        dry_run=True,
        webhook_file="does-not-matter.txt",
    )

    assert "Message truncated" in out
    assert len(out) == 2000


def test_setup_argument_parser_defaults():
    parser = PROTEUS_HEALTH_REPORT.setup_argument_parser()
    defaults = parser.parse_args([])

    assert defaults.dry_run is False
    assert defaults.webhook_file == "discord-webhook-url.txt"
    assert defaults.file_size_threshold == "20M"
    assert defaults.disk_threshold == "50"
    assert isinstance(defaults.services, list)
    assert "nginx" in defaults.services


def test_check_service_statuses(monkeypatch):
    active = {"nginx", "ssh"}

    def fake_run(command, capture_output=True, text=True, shell=True):
        service = command.split()[-1]
        return SimpleNamespace(returncode=0 if service in active else 3)

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT.subprocess, "run", fake_run)

    services = ["nginx", "ssh", "fail2ban", "wg-quick@wg0"]
    out = PROTEUS_HEALTH_REPORT.check_service_statuses(services)

    assert out == [
        "nginx: active",
        "ssh: active",
        "fail2ban: inactive",
        "wg-quick@wg0: inactive",
    ]


def test_check_dns_resolution_ok(monkeypatch):
    def fake_run(command, capture_output=True, text=True, shell=True):
        return SimpleNamespace(returncode=0, stdout="8.8.8.8\n")

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT.subprocess, "run", fake_run)
    assert PROTEUS_HEALTH_REPORT.check_dns_resolution() == [
        "DNS Resolution: OK (8.8.8.8)",
    ]


def test_check_dns_resolution_failed(monkeypatch):
    def fake_run(command, capture_output=True, text=True, shell=True):
        return SimpleNamespace(returncode=0, stdout="")  # no output

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT.subprocess, "run", fake_run)
    assert PROTEUS_HEALTH_REPORT.check_dns_resolution() == [
        "DNS Resolution: FAILED",
    ]


def test_check_network_stats_fallback_when_failed(monkeypatch):
    def fake_run(command, capture_output=True, text=True, shell=True):
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT.subprocess, "run", fake_run)
    assert PROTEUS_HEALTH_REPORT.check_network_stats() == [
        "Network stats unavailable (vnstat failed or not installed)",
    ]


def test_check_network_stats_parses_lines(monkeypatch):
    stdout = "\n".join(
        [
            "eth0 (monthly): rx 1, tx 2, total 3",
            "",
            "eth0 (daily): rx 4, tx 5, total 6",
        ]
    )

    def fake_run(command, capture_output=True, text=True, shell=True):
        return SimpleNamespace(returncode=0, stdout=stdout)

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT.subprocess, "run", fake_run)
    assert PROTEUS_HEALTH_REPORT.check_network_stats() == [
        "eth0 (monthly): rx 1, tx 2, total 3",
        "eth0 (daily): rx 4, tx 5, total 6",
    ]


def test_save_report_to_disk_writes_to_expected_file(monkeypatch, tmp_path):
    report_file = tmp_path / "report.log"
    real_path_class = Path

    def fake_path(p):
        # Map just the script's hard-coded path into tmp.
        p_str = str(p)
        if p_str.startswith("/var/log/proteus-health-reports/"):
            return report_file
        return real_path_class(p_str)

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "Path", fake_path)

    PROTEUS_HEALTH_REPORT.save_report_to_disk("hello-world")

    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "hello-world" in content
