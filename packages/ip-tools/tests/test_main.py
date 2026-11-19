import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ip_tools import main as patient
from tests import fakes


@pytest.fixture
def clean_env(monkeypatch):
    """Restore the variables load_env writes into os.environ after each test."""
    for name in ("IPINFO_API_KEY", "OTHER", "EMPTY"):
        monkeypatch.setenv(name, "placeholder")
        monkeypatch.delenv(name)


@pytest.fixture
def captured_geostat_run(monkeypatch):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(patient.banned_ip_geostat, "run", fake_run)
    return captured


def describe_load_env():
    def it_sets_missing_but_does_not_override_existing(clean_env, monkeypatch, tmp_path):
        dotenv_file = fakes.create_fake_dotenv(tmp_path)

        patient.load_env(str(dotenv_file))
        assert os.environ.get("IPINFO_API_KEY") == "key1"
        assert os.environ.get("OTHER") == "val2"

        monkeypatch.setenv("IPINFO_API_KEY", "existing")
        patient.load_env(str(dotenv_file))
        assert os.environ.get("IPINFO_API_KEY") == "existing"

    def it_strips_quotes_and_whitespace_and_skips_comments(clean_env, tmp_path):
        patient.load_env(str(fakes.create_fake_dotenv(tmp_path)))

        assert os.environ["IPINFO_API_KEY"] == "key1"
        assert os.environ["OTHER"] == "val2"
        assert os.environ["EMPTY"] == ""
        assert "# comment" not in os.environ

    def it_returns_without_file(monkeypatch, tmp_path):
        monkeypatch.setenv("IPINFO_API_KEY", "existing")

        patient.load_env(str(tmp_path / "does-not-exist.env"))

        assert os.environ.get("IPINFO_API_KEY") == "existing"


def describe_setup_argument_parser():
    def it_has_expected_defaults():
        args = patient.setup_argument_parser().parse_args([])

        assert args.ip_file == Path("ip_list.txt")
        assert args.no_banned_script is False
        assert args.env_file == Path(".env")
        assert args.country_file == Path("country_count.txt")
        assert args.org_file == Path("org_count.txt")
        assert args.city_file == Path("city_count.txt")
        assert args.org_ips_file == Path("org_ips.txt")
        assert args.api_key is None

    def it_parses_overrides():
        args = patient.setup_argument_parser().parse_args(
            ["--ip-file", "my.txt", "--no-banned-script", "--api-key", "k"])

        assert args.ip_file == Path("my.txt")
        assert args.no_banned_script is True
        assert args.api_key == "k"


def describe_run():
    def _args(tmp_path, **overrides):
        args_dict, *_ = fakes.create_dummy_args(tmp_path)
        args_dict.update(overrides)
        return SimpleNamespace(**args_dict)

    def it_passes_arguments_through_to_geostat(clean_env, captured_geostat_run, tmp_path):
        args = _args(tmp_path, no_banned_script=True)

        patient.run(args)

        assert captured_geostat_run["api_key"] == "tok"
        assert captured_geostat_run["ip_file"] == Path(args.ip_file)
        assert captured_geostat_run["country_file"] == args.country_file
        assert captured_geostat_run["org_file"] == args.org_file
        assert captured_geostat_run["city_file"] == args.city_file
        assert captured_geostat_run["org_ips_file"] == args.org_ips_file
        assert captured_geostat_run["no_banned_script"] is True

    def it_prefers_api_key_flag_over_environment(monkeypatch, captured_geostat_run, tmp_path):
        monkeypatch.setenv("IPINFO_API_KEY", "from-env")

        patient.run(_args(tmp_path, api_key="from-flag"))

        assert captured_geostat_run["api_key"] == "from-flag"

    def it_falls_back_to_environment_when_flag_is_absent(monkeypatch, captured_geostat_run, tmp_path):
        monkeypatch.setenv("IPINFO_API_KEY", "from-env")

        patient.run(_args(tmp_path, api_key=None))

        assert captured_geostat_run["api_key"] == "from-env"

    def it_exits_when_no_api_key_is_available(monkeypatch, captured_geostat_run, tmp_path):
        monkeypatch.delenv("IPINFO_API_KEY", raising=False)

        with pytest.raises(SystemExit) as e:
            patient.run(_args(tmp_path, api_key=None))

        assert e.value.code == 1
        assert captured_geostat_run == {}


def describe_main():
    def _stub_network(monkeypatch):
        geostat = patient.banned_ip_geostat
        fakes.fake_api_interaction(geostat, monkeypatch)
        monkeypatch.setattr(geostat, "preflight", lambda _api_key: None)

    def it_runs_end_to_end_and_writes_output_files(clean_env, monkeypatch, tmp_path):
        _stub_network(monkeypatch)
        ip_file = tmp_path / "ips.txt"
        ip_file.write_text("1.2.3.4\n2.3.4.5\n", encoding="utf-8")
        env_file = tmp_path / ".env"
        env_file.write_text("IPINFO_API_KEY=tok\n", encoding="utf-8")
        outputs = {name: tmp_path / f"{name}.txt"
                   for name in ("country", "org", "city", "org_ips")}
        monkeypatch.setattr(sys, "argv", [
            "ip-tools",
            "--no-banned-script",
            "--ip-file", str(ip_file),
            "--env-file", str(env_file),
            "--country-file", str(outputs["country"]),
            "--org-file", str(outputs["org"]),
            "--city-file", str(outputs["city"]),
            "--org-ips-file", str(outputs["org_ips"]),
        ])

        patient.main()

        assert outputs["country"].read_text(encoding="utf-8") == "US\nUS\n"
        assert outputs["org"].read_text(encoding="utf-8") == "OrgX\nOrgX\n"
        assert outputs["city"].read_text(encoding="utf-8") == "NYC\nNYC\n"
        assert outputs["org_ips"].read_text(
            encoding="utf-8") == "OrgX\n  1.2.3.4\n  2.3.4.5\n"

    def it_exits_when_ip_file_is_missing_under_no_banned_script(clean_env, monkeypatch, tmp_path):
        _stub_network(monkeypatch)
        monkeypatch.setattr(sys, "argv", [
            "ip-tools",
            "--no-banned-script",
            "--api-key", "tok",
            "--ip-file", str(tmp_path / "missing.txt"),
            "--env-file", str(tmp_path / "missing.env"),
        ])

        with pytest.raises(SystemExit) as e:
            patient.main()

        assert e.value.code == 1

    def it_uses_api_key_flag_over_env_file(clean_env, monkeypatch, captured_geostat_run, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("IPINFO_API_KEY=from-file\n", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", [
            "ip-tools", "--api-key", "from-flag", "--env-file", str(env_file)])

        patient.main()

        assert captured_geostat_run["api_key"] == "from-flag"

    def it_exits_when_api_key_missing_everywhere(clean_env, monkeypatch, captured_geostat_run, tmp_path):
        monkeypatch.setattr(sys, "argv", [
            "ip-tools", "--env-file", str(tmp_path / "missing.env")])

        with pytest.raises(SystemExit) as e:
            patient.main()

        assert e.value.code == 1
