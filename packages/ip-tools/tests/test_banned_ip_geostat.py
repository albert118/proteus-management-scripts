from collections import Counter
from types import SimpleNamespace
import urllib.error

import pytest

from ip_tools import banned_ip_geostat as patient
from tests import fakes


def describe_helpers():
    def it_is_ip_accepts_ipv4_and_rejects_invalid():
        assert patient._is_ip("1.2.3.4") is True
        assert patient._is_ip("::1") is True
        assert patient._is_ip("999.999.1.1") is False
        assert patient._is_ip("not-an-ip") is False

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
