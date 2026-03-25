from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

import pytest
import runpy


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


def test_discord_notification_success_prints(capsys, monkeypatch):
    class FakeOK:
        def raise_for_status(self):
            return None

    def fake_post(_webhook, json=None, headers=None):
        return FakeOK()

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT.requests, "post", fake_post)

    PROTEUS_HEALTH_REPORT.discord_notification("http://hook", "msg")
    out = capsys.readouterr().out
    assert "Triggered Discord notifier webhook" in out


def test_discord_notification_http_error_prints(capsys, monkeypatch):
    class FakeBad:
        def raise_for_status(self):
            import requests

            raise requests.exceptions.HTTPError("bad")

    def fake_post(_webhook, json=None, headers=None):
        return FakeBad()

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT.requests, "post", fake_post)

    PROTEUS_HEALTH_REPORT.discord_notification("http://hook", "msg")
    out = capsys.readouterr().out
    assert "Failed to trigger Discord notifier webhook" in out


def test_check_directory_size_exits_on_subprocess_error(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=1, stderr="boom", stdout=""
        )

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as e:
        PROTEUS_HEALTH_REPORT.check_directory_size("/tmp/*", "20M")
    assert e.value.code == 1


def test_check_disk_usage_exits_on_subprocess_error(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stderr="boom", stdout="")

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as e:
        PROTEUS_HEALTH_REPORT.check_disk_usage("50")
    assert e.value.code == 1


def test_send_monitor_report_returns_none_when_webhook_missing_and_not_dry_run(
    monkeypatch,
):
    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "get_discord_webhook", lambda _p: None)

    out = PROTEUS_HEALTH_REPORT.send_monitor_report(
        logs_warnings=[],
        caches_warnings=[],
        tmps_warnings=[],
        disk_warnings=[],
        service_statuses=[],
        dns_status=[],
        net_stats=[],
        dry_run=False,
        webhook_file="missing.txt",
    )
    assert out is None


def test_send_monitor_report_includes_tmps_warnings(monkeypatch):
    monkeypatch.setattr(
        PROTEUS_HEALTH_REPORT,
        "get_discord_webhook",
        lambda _path: "http://hook.example",
    )

    out = PROTEUS_HEALTH_REPORT.send_monitor_report(
        logs_warnings=[],
        caches_warnings=[],
        tmps_warnings=["tmp1", "tmp2"],
        disk_warnings=[],
        service_statuses=[],
        dns_status=[],
        net_stats=[],
        dry_run=True,
        webhook_file="does-not-matter.txt",
    )
    assert "Temp Size Warnings" in out
    assert "tmp1" in out


def test_send_monitor_report_calls_discord_notification_when_not_dry_run(
    monkeypatch,
):
    called = {}

    def fake_discord_notification(webhook, message):
        called["webhook"] = webhook
        called["message"] = message

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "discord_notification", fake_discord_notification)
    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "get_discord_webhook", lambda _p: "http://hook.example")

    PROTEUS_HEALTH_REPORT.send_monitor_report(
        logs_warnings=["log1"],
        caches_warnings=[],
        tmps_warnings=[],
        disk_warnings=["hdr", "diskwarn"],
        service_statuses=[],
        dns_status=[],
        net_stats=[],
        dry_run=False,
        webhook_file="does-not-matter.txt",
    )

    assert called["webhook"] == "http://hook.example"
    assert "log1" in called["message"]


def test_main_dry_run_flow_runs_checks_and_saves_report(monkeypatch, tmp_path):
    # Prevent any disk/system side effects
    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "get_discord_webhook", lambda _p: None)
    monkeypatch.setattr(
        PROTEUS_HEALTH_REPORT,
        "check_directory_size",
        lambda _p, _t: ["dir-warning"],
    )
    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "check_disk_usage", lambda _t: ["disk"])
    monkeypatch.setattr(
        PROTEUS_HEALTH_REPORT,
        "check_service_statuses",
        lambda _s: ["nginx: active"],
    )
    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "check_dns_resolution", lambda: ["DNS Resolution: OK (1.2.3.4)"])
    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "check_network_stats", lambda: ["net"])

    saved = {}

    def fake_send_monitor_report(
        logs_warnings,
        caches_warnings,
        tmps_warnings,
        disk_warnings,
        service_statuses,
        dns_status,
        net_stats,
        dry_run=False,
        webhook_file="discord-webhook-url.txt",
    ):
        assert dry_run is True
        assert logs_warnings == ["dir-warning"]
        return "report-body"

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "send_monitor_report", fake_send_monitor_report)
    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "save_report_to_disk", lambda report_content: saved.update({"content": report_content}))

    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["proteus-health-report.py", "--dry-run", "--webhook-file", str(tmp_path / "x")],
        raising=True,
    )

    PROTEUS_HEALTH_REPORT.main()
    assert saved["content"] == "report-body"


def test_main_test_webhook_sends_test_and_returns(monkeypatch, tmp_path):
    called = {}

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "get_discord_webhook", lambda _p: "http://hook.example")

    def fake_discord_notification(webhook_url, message):
        called["webhook"] = webhook_url
        called["message"] = message

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "discord_notification", fake_discord_notification)
    monkeypatch.setattr(PROTEUS_HEALTH_REPORT, "save_report_to_disk", lambda _c: (_ for _ in ()).throw(AssertionError("should not save")))

    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["proteus-health-report.py", "--test-webhook", "--webhook-file", str(tmp_path / "x")],
        raising=True,
    )

    PROTEUS_HEALTH_REPORT.main()

    assert called["webhook"] == "http://hook.example"
    assert "Proteus Discord webhook is working" in called["message"]


def test_check_directory_size_returns_stdout_lines_on_success(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0, stderr="", stdout="a\nb\n"
        )

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT.subprocess, "run", fake_run)
    assert PROTEUS_HEALTH_REPORT.check_directory_size("/tmp/*", "20M") == [
        "a",
        "b",
    ]


def test_check_disk_usage_returns_stdout_lines_on_success(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0, stderr="", stdout="row1\nrow2\n"
        )

    monkeypatch.setattr(PROTEUS_HEALTH_REPORT.subprocess, "run", fake_run)
    assert PROTEUS_HEALTH_REPORT.check_disk_usage("50") == ["row1", "row2"]


def test_main_test_webhook_exits_when_webhook_missing(tmp_path, monkeypatch):
    # Let get_discord_webhook hit the FileNotFoundError path.
    missing = tmp_path / "does-not-exist.txt"

    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "proteus-health-report.py",
            "--test-webhook",
            "--webhook-file",
            str(missing),
        ],
        raising=True,
    )

    with pytest.raises(SystemExit) as e:
        PROTEUS_HEALTH_REPORT.main()
    assert e.value.code == 1


def test_main_exits_when_webhook_file_empty_and_not_dry_run(monkeypatch):
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["proteus-health-report.py", "--webhook-file", ""],
        raising=True,
    )

    with pytest.raises(SystemExit) as e:
        PROTEUS_HEALTH_REPORT.main()
    assert e.value.code == 1


def test_main_exits_when_webhook_url_missing_and_not_dry_run(tmp_path, monkeypatch):
    import sys

    missing = tmp_path / "discord-webhook-url.txt"

    monkeypatch.setattr(
        sys,
        "argv",
        ["proteus-health-report.py", "--webhook-file", str(missing)],
        raising=True,
    )

    with pytest.raises(SystemExit) as e:
        PROTEUS_HEALTH_REPORT.main()
    assert e.value.code == 1


def test_proteus_health_report_entrypoint_runs_main(monkeypatch, tmp_path):
    import builtins
    import subprocess as sp
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "proteus-health-report.py"

    report_path = tmp_path / "proteus-health-report.log"
    real_open = builtins.open

    def fake_open(file, mode="r", *args, **kwargs):
        if str(file).startswith("/var/log/proteus-health-reports/report.log"):
            return real_open(report_path, mode, *args, **kwargs)
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    def fake_run(command, capture_output=True, text=True, shell=True, check=False):
        cmd = command if isinstance(command, str) else str(command)

        if cmd.startswith("du -sh -t"):
            return SimpleNamespace(returncode=0, stdout="warn1\nwarn2\n", stderr="")
        if cmd.startswith("df -hlP /dev/vda1"):
            return SimpleNamespace(
                returncode=0,
                stdout="Filesystem\n/dev/vda1 10G 9G 55% / \n",
                stderr="",
            )
        if cmd.startswith("systemctl -q is-active"):
            # Always mark services active.
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd.startswith("dig +short google.com"):
            return SimpleNamespace(returncode=0, stdout="8.8.8.8\n", stderr="")
        if cmd.startswith("vnstat -i"):
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "eth0 (monthly): rx 1, tx 2, total 3\n"
                    "eth0 (daily): rx 4, tx 5, total 6\n"
                ),
                stderr="",
            )

        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(sp, "run", fake_run)

    webhook_file = tmp_path / "webhook.txt"
    webhook_file.write_text("http://hook.example", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "proteus-health-report.py",
            "--dry-run",
            "--webhook-file",
            str(webhook_file),
        ],
        raising=True,
    )

    runpy.run_path(str(script_path), run_name="__main__")

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "Proteus Health Report" in content
