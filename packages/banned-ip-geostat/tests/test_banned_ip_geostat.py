import banned_ip_geostat as patient
import pytest
from tests import fakes
from pathlib import Path
from types import SimpleNamespace
import os


def describe_helpers():
    def it_is_ip_accepts_ipv4_and_rejects_invalid():
        assert patient._is_ip("1.2.3.4") is True
        assert patient._is_ip("::1") is True
        assert patient._is_ip("999.999.1.1") is False
        assert patient._is_ip("not-an-ip") is False

    def it_load_env_sets_missing_but_does_not_override_existing(monkeypatch, tmp_path):
        dotenv_file = fakes.create_fake_dotenv(tmp_path)

        monkeypatch.delenv("IPINFO_API_KEY", raising=False)
        monkeypatch.delenv("OTHER", raising=False)

        patient.load_env(str(dotenv_file))
        assert os.environ.get("IPINFO_API_KEY") == "key1"
        assert os.environ.get("OTHER") == "val2"

        monkeypatch.setenv("IPINFO_API_KEY", "existing")
        patient.load_env(str(dotenv_file))
        assert os.environ.get("IPINFO_API_KEY") == "existing"

    def it_merge_ips_deduplicates_sorts_and_writes(tmp_path):
        ip_file = tmp_path / "ip_list.txt"
        ip_file.write_text("1.1.1.1\n", encoding="utf-8")

        out = patient.merge_ips(
            new_ips=["2.2.2.2", "1.1.1.1"], ip_file=ip_file)
        assert out == ["1.1.1.1", "2.2.2.2"]
        assert ip_file.read_text(encoding="utf-8") == "1.1.1.1\n2.2.2.2\n"

    def it_write_org_ips_sorts_org_and_ips(tmp_path):
        org_ips = {
            "OrgB": ["2.2.2.2", "1.1.1.1"],
            "OrgA": ["3.3.3.3"],
        }
        output_file = tmp_path / "org_ips.txt"

        patient.write_org_ips(org_ips=org_ips, output_file=output_file)

        assert output_file.read_text(encoding="utf-8") == "\n".join(
            [
                "OrgA",
                "  3.3.3.3",
                "OrgB",
                "  1.1.1.1",
                "  2.2.2.2",
                "",
            ]
        )

    def it_parse_args_defaults(monkeypatch):
        import sys

        monkeypatch.setattr(
            sys, "argv", ["banned-ip-geostat.py"], raising=True
        )
        args = patient.parse_args()

        assert args.ip_file == "ip_list.txt"
        assert args.no_banned_script is False
        assert args.env_file == ".env"
        assert args.country_file == "country_count.txt"
        assert args.org_file == "org_count.txt"
        assert args.city_file == "city_count.txt"
        assert args.org_ips_file == "org_ips.txt"
        assert args.api_key is None

    def it_preflight_makes_request_and_continues(monkeypatch):
        captured = {}

        def fake_urlopen(req):
            captured["url"] = req.full_url
            captured["auth"] = req.headers.get("Authorization")
            return fakes.FakeResponse(b"ok")

        monkeypatch.setattr(patient.urllib.request, "urlopen", fake_urlopen)
        patient.preflight("my-key")

        assert captured["url"] == "https://api.ipinfo.io/lite/8.8.8.8"
        assert captured["auth"] == "Bearer my-key"

    def it_preflight_raises_systemexit_on_url_error(monkeypatch):
        import urllib.error

        def fake_urlopen(_req):
            raise urllib.error.URLError("no-network")

        monkeypatch.setattr(patient.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(SystemExit) as e:
            patient.preflight("my-key")
        assert e.value.code == 1

    def it_get_ip_info_returns_json_and_uses_token(monkeypatch):
        captured = {}

        def fake_urlopen(req):
            captured["url"] = req.full_url
            captured["auth"] = req.headers.get("Authorization")
            return fakes.FakeResponse(
                b'{"country":"US","org":"SomeOrg","city":"NYC"}'
            )

        monkeypatch.setattr(patient.urllib.request, "urlopen", fake_urlopen)
        info = patient.get_ip_info("1.2.3.4", api_key="tok")

        assert info["country"] == "US"
        assert "ipinfo.io/1.2.3.4?token=tok" in captured["url"]
        assert captured["auth"] == "Bearer tok"

    def it_fetch_banned_ips_filters_non_ips(monkeypatch, tmp_path):
        fake_script = tmp_path / "check-banned-ips.sh"
        fake_script.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")

        monkeypatch.setattr(patient, "BANNED_IPS_SCRIPT", fake_script)

        def fake_run(_args, capture_output=True, text=True):
            return SimpleNamespace(
                returncode=0, stdout="1.2.3.4 not-an-ip ::1 999.999.1.1\n"
            )

        monkeypatch.setattr(patient.subprocess, "run", fake_run)
        ips = patient.fetch_banned_ips()
        assert ips == ["1.2.3.4", "::1"]

    def it_fetch_banned_ips_missing_script_exits(monkeypatch, tmp_path):
        missing = tmp_path / "does-not-exist.sh"
        monkeypatch.setattr(patient, "BANNED_IPS_SCRIPT", missing)
        with pytest.raises(SystemExit) as e:
            patient.fetch_banned_ips()
        assert e.value.code == 1

    def it_load_env_returns_without_file(monkeypatch, tmp_path):
        # Ensure an env var doesn't get created implicitly.
        monkeypatch.setenv("IPINFO_API_KEY", "existing")
        missing = tmp_path / "does-not-exist.env"

        patient.load_env(str(missing))
        assert os.environ.get("IPINFO_API_KEY") == "existing"

    def it_fetch_banned_ips_exits_on_subprocess_error(monkeypatch, tmp_path):
        fake_script = tmp_path / "check-banned-ips.sh"
        fake_script.write_text("#!/bin/bash\n", encoding="utf-8")
        monkeypatch.setattr(patient, "BANNED_IPS_SCRIPT", fake_script)

        def fake_run(_args, capture_output=True, text=True):
            return SimpleNamespace(returncode=1, stdout="", stderr="boom")

        monkeypatch.setattr(patient.subprocess, "run", fake_run)

        with pytest.raises(SystemExit) as e:
            patient.fetch_banned_ips()
        assert e.value.code == 1

    def it_print_stats_outputs_expected_lines(capsys):
        from collections import Counter

        counter = Counter({"US": 2, "CA": 1})
        patient.print_stats("country code", counter)

        out = capsys.readouterr().out
        assert "Statistics by country code:" in out
        assert "     2  US" in out
        assert "     1  CA" in out

    def it_print_org_ips_outputs_expected_lines(capsys):
        org_ips = {"OrgB": ["2.2.2.2"], "OrgA": ["1.1.1.1", "3.3.3.3"]}
        patient.print_org_ips(org_ips)

        out = capsys.readouterr().out
        assert "IPs by organisation:" in out
        assert "  OrgA" in out
        assert "    1.1.1.1" in out
        assert "    3.3.3.3" in out


def describe_main_entrypoint():
    def it_should_run(monkeypatch, tmp_path):
        fakes.fake_api_interaction(patient, monkeypatch)
        args_dict, _, _, _, _, _ = fakes.create_dummy_args(tmp_path)

        monkeypatch.setattr(patient, "parse_args", lambda: args_dict)
        monkeypatch.setattr(patient, "load_env", lambda _p: None)
        monkeypatch.setattr(patient, "preflight", lambda _api_key: None)
        monkeypatch.setattr(patient, "fetch_banned_ips", lambda: ["1.2.3.4"])

        patient.main(SimpleNamespace(**args_dict))

    def it_should_write_output_files(monkeypatch, tmp_path):
        fakes.fake_api_interaction(patient, monkeypatch)
        args_dict, ip_file, country_file, org_file, city_file, org_ips_file = fakes.create_dummy_args(
            tmp_path)

        monkeypatch.setattr(patient, "parse_args", lambda: args_dict)
        monkeypatch.setattr(patient, "load_env", lambda _p: None)
        monkeypatch.setattr(patient, "preflight", lambda _api_key: None)
        monkeypatch.setattr(patient, "fetch_banned_ips", lambda: ["1.2.3.4"])

        patient.main(SimpleNamespace(**args_dict))

        assert ip_file.exists()
        assert country_file.read_text(encoding="utf-8") == "US\n"
        assert org_file.read_text(encoding="utf-8") == "OrgX\n"
        assert city_file.read_text(encoding="utf-8") == "NYC\n"
        assert org_ips_file.read_text(encoding="utf-8") == "OrgX\n  1.2.3.4\n"

    def it_main_exits_when_no_banned_script_and_ip_file_missing(monkeypatch, tmp_path):
        fakes.fake_api_interaction(patient, monkeypatch)
        args_dict, _, _, _, _, _ = fakes.create_dummy_args(tmp_path)

        monkeypatch.setattr(patient, "parse_args", lambda: args_dict)
        monkeypatch.setattr(patient, "load_env", lambda _p: None)

        with pytest.raises(SystemExit) as e:
            patient.main(SimpleNamespace(**args_dict))
        assert e.value.code == 1

    def it_main_exits_when_api_key_missing(monkeypatch, tmp_path):
        fakes.fake_api_interaction(patient, monkeypatch)
        args_dict, _, _, _, _, _ = fakes.create_dummy_args(tmp_path)

        monkeypatch.setattr(patient, "parse_args", lambda: args_dict)
        monkeypatch.setattr(patient, "load_env", lambda _p: None)
        monkeypatch.delenv("IPINFO_API_KEY", raising=False)

        with pytest.raises(SystemExit) as e:
            patient.main(SimpleNamespace(**args_dict))
        assert e.value.code == 1
