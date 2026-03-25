from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

import pytest
import os


def load_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "banned-ip-geostat.py"

    loader = SourceFileLoader("banned_ip_geostat", str(module_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None

    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


B = load_module()


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_is_ip_accepts_ipv4_and_rejects_invalid():
    assert B._is_ip("1.2.3.4") is True
    assert B._is_ip("::1") is True
    assert B._is_ip("999.999.1.1") is False
    assert B._is_ip("not-an-ip") is False


def test_load_env_sets_missing_but_does_not_override_existing(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "IPINFO_API_KEY='key1'",
                "OTHER = \"val2\"",
                "EMPTY=",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("IPINFO_API_KEY", raising=False)
    monkeypatch.delenv("OTHER", raising=False)

    B.load_env(str(env_file))
    assert os.environ.get("IPINFO_API_KEY") == "key1"
    assert os.environ.get("OTHER") == "val2"

    monkeypatch.setenv("IPINFO_API_KEY", "existing")
    B.load_env(str(env_file))
    assert os.environ.get("IPINFO_API_KEY") == "existing"


def test_merge_ips_deduplicates_sorts_and_writes(tmp_path):
    ip_file = tmp_path / "ip_list.txt"
    ip_file.write_text("1.1.1.1\n", encoding="utf-8")

    out = B.merge_ips(new_ips=["2.2.2.2", "1.1.1.1"], ip_file=ip_file)
    assert out == ["1.1.1.1", "2.2.2.2"]
    assert ip_file.read_text(encoding="utf-8") == "1.1.1.1\n2.2.2.2\n"


def test_write_org_ips_sorts_org_and_ips(tmp_path):
    org_ips = {
        "OrgB": ["2.2.2.2", "1.1.1.1"],
        "OrgA": ["3.3.3.3"],
    }
    output_file = tmp_path / "org_ips.txt"

    B.write_org_ips(org_ips=org_ips, output_file=output_file)

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


def test_parse_args_defaults(monkeypatch):
    import sys

    monkeypatch.setattr(
        sys, "argv", ["banned-ip-geostat.py"], raising=True
    )
    args = B.parse_args()

    assert args.ip_file == "ip_list.txt"
    assert args.no_banned_script is False
    assert args.env_file == ".env"
    assert args.country_file == "country_count.txt"
    assert args.org_file == "org_count.txt"
    assert args.city_file == "city_count.txt"
    assert args.org_ips_file == "org_ips.txt"
    assert args.api_key is None


def test_preflight_makes_request_and_continues(monkeypatch):
    captured = {}

    def fake_urlopen(req):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        return FakeResponse(b"ok")

    monkeypatch.setattr(B.urllib.request, "urlopen", fake_urlopen)
    B.preflight("my-key")

    assert captured["url"] == "https://api.ipinfo.io/lite/8.8.8.8"
    assert captured["auth"] == "Bearer my-key"


def test_preflight_raises_systemexit_on_url_error(monkeypatch):
    import urllib.error

    def fake_urlopen(_req):
        raise urllib.error.URLError("no-network")

    monkeypatch.setattr(B.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(SystemExit) as e:
        B.preflight("my-key")
    assert e.value.code == 1


def test_get_ip_info_returns_json_and_uses_token(monkeypatch):
    captured = {}

    def fake_urlopen(req):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        return FakeResponse(
            b'{"country":"US","org":"SomeOrg","city":"NYC"}'
        )

    monkeypatch.setattr(B.urllib.request, "urlopen", fake_urlopen)
    info = B.get_ip_info("1.2.3.4", api_key="tok")

    assert info["country"] == "US"
    assert "ipinfo.io/1.2.3.4?token=tok" in captured["url"]
    assert captured["auth"] == "Bearer tok"


def test_fetch_banned_ips_filters_non_ips(monkeypatch, tmp_path):
    fake_script = tmp_path / "check-banned-ips.sh"
    fake_script.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")

    monkeypatch.setattr(B, "BANNED_IPS_SCRIPT", fake_script)

    def fake_run(_args, capture_output=True, text=True):
        return SimpleNamespace(
            returncode=0, stdout="1.2.3.4 not-an-ip ::1 999.999.1.1\n"
        )

    monkeypatch.setattr(B.subprocess, "run", fake_run)
    ips = B.fetch_banned_ips()
    assert ips == ["1.2.3.4", "::1"]


def test_fetch_banned_ips_missing_script_exits(monkeypatch, tmp_path):
    missing = tmp_path / "does-not-exist.sh"
    monkeypatch.setattr(B, "BANNED_IPS_SCRIPT", missing)
    with pytest.raises(SystemExit) as e:
        B.fetch_banned_ips()
    assert e.value.code == 1


def test_load_env_returns_without_file(monkeypatch, tmp_path):
    # Ensure an env var doesn't get created implicitly.
    monkeypatch.setenv("IPINFO_API_KEY", "existing")
    missing = tmp_path / "does-not-exist.env"

    B.load_env(str(missing))
    assert os.environ.get("IPINFO_API_KEY") == "existing"


def test_fetch_banned_ips_exits_on_subprocess_error(monkeypatch, tmp_path):
    fake_script = tmp_path / "check-banned-ips.sh"
    fake_script.write_text("#!/bin/bash\n", encoding="utf-8")
    monkeypatch.setattr(B, "BANNED_IPS_SCRIPT", fake_script)

    def fake_run(_args, capture_output=True, text=True):
        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(B.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as e:
        B.fetch_banned_ips()
    assert e.value.code == 1


def test_print_stats_outputs_expected_lines(capsys):
    from collections import Counter

    counter = Counter({"US": 2, "CA": 1})
    B.print_stats("country code", counter)

    out = capsys.readouterr().out
    assert "Statistics by country code:" in out
    assert "     2  US" in out
    assert "     1  CA" in out


def test_print_org_ips_outputs_expected_lines(capsys):
    org_ips = {"OrgB": ["2.2.2.2"], "OrgA": ["1.1.1.1", "3.3.3.3"]}
    B.print_org_ips(org_ips)

    out = capsys.readouterr().out
    assert "IPs by organisation:" in out
    assert "  OrgA" in out
    assert "    1.1.1.1" in out
    assert "    3.3.3.3" in out


def test_main_happy_path_writes_outputs_and_prints(monkeypatch, tmp_path, capsys):
    ip_file = tmp_path / "ip_list.txt"
    ip_file.write_text("1.2.3.4\n5.6.7.8\n", encoding="utf-8")

    country_file = tmp_path / "country_count.txt"
    org_file = tmp_path / "org_count.txt"
    city_file = tmp_path / "city_count.txt"
    org_ips_file = tmp_path / "org_ips.txt"

    args = SimpleNamespace(
        ip_file=str(ip_file),
        no_banned_script=True,
        env_file=str(tmp_path / ".env"),
        country_file=str(country_file),
        org_file=str(org_file),
        city_file=str(city_file),
        org_ips_file=str(org_ips_file),
        api_key="tok",
    )

    import urllib.error

    monkeypatch.setattr(B, "parse_args", lambda: args)
    monkeypatch.setattr(B, "load_env", lambda _path: None)
    monkeypatch.setattr(B, "preflight", lambda _api_key: None)

    def fake_get_ip_info(ip: str, api_key: str):
        if ip == "1.2.3.4":
            return {"country": "US", "org": "OrgX", "city": "NYC"}
        raise urllib.error.URLError("no-ip-info")

    monkeypatch.setattr(B, "get_ip_info", fake_get_ip_info)

    # Let print_stats/print_org_ips run (to improve coverage there too).
    B.main()

    assert country_file.read_text(encoding="utf-8") == "US\n"
    assert org_file.read_text(encoding="utf-8") == "OrgX\n"
    assert city_file.read_text(encoding="utf-8") == "NYC\n"

    # write_org_ips writes an Org header and the sorted IPs under it.
    assert org_ips_file.read_text(encoding="utf-8") == "\n".join(
        ["OrgX", "  1.2.3.4", ""]
    )

    stdout = capsys.readouterr().out
    assert "Processing 1.2.3.4..." in stdout
    assert "Warning: failed to get info for 5.6.7.8" in stdout


def test_main_exits_when_api_key_missing(monkeypatch, tmp_path):
    import sys
    import urllib.error

    args = SimpleNamespace(
        ip_file=str(tmp_path / "ip_list.txt"),
        no_banned_script=True,
        env_file=str(tmp_path / ".env"),
        country_file=str(tmp_path / "country.txt"),
        org_file=str(tmp_path / "org.txt"),
        city_file=str(tmp_path / "city.txt"),
        org_ips_file=str(tmp_path / "org_ips.txt"),
        api_key=None,
    )

    monkeypatch.setattr(B, "parse_args", lambda: args)
    monkeypatch.setattr(B, "load_env", lambda _p: None)
    monkeypatch.delenv("IPINFO_API_KEY", raising=False)

    with pytest.raises(SystemExit) as e:
        B.main()
    assert e.value.code == 1


def test_main_calls_banned_ip_script_when_no_banned_script_false(monkeypatch, tmp_path, capsys):
    # Exercise the `not args.no_banned_script` branch.
    ip_file = tmp_path / "ip_list.txt"
    country_file = tmp_path / "country_count.txt"
    org_file = tmp_path / "org_count.txt"
    city_file = tmp_path / "city_count.txt"
    org_ips_file = tmp_path / "org_ips.txt"

    args = SimpleNamespace(
        ip_file=str(ip_file),
        no_banned_script=False,
        env_file=str(tmp_path / ".env"),
        country_file=str(country_file),
        org_file=str(org_file),
        city_file=str(city_file),
        org_ips_file=str(org_ips_file),
        api_key="tok",
    )

    monkeypatch.setattr(B, "parse_args", lambda: args)
    monkeypatch.setattr(B, "load_env", lambda _p: None)
    monkeypatch.setattr(B, "preflight", lambda _api_key: None)
    monkeypatch.setattr(B, "fetch_banned_ips", lambda: ["1.2.3.4"])

    # Avoid network: return deterministic info.
    monkeypatch.setattr(
        B,
        "get_ip_info",
        lambda ip, api_key: {"country": "US", "org": "OrgX", "city": "NYC"},
    )

    # Let merge_ips actually write into ip_file so file creation covers that code.
    B.main()

    assert ip_file.exists()
    assert country_file.read_text(encoding="utf-8") == "US\n"
    assert org_file.read_text(encoding="utf-8") == "OrgX\n"
    assert city_file.read_text(encoding="utf-8") == "NYC\n"


def test_main_exits_when_no_banned_script_and_ip_file_missing(monkeypatch, tmp_path):
    ip_file = tmp_path / "missing_ip_list.txt"  # intentionally does not exist

    args = SimpleNamespace(
        ip_file=str(ip_file),
        no_banned_script=True,
        env_file=str(tmp_path / ".env"),
        country_file=str(tmp_path / "country.txt"),
        org_file=str(tmp_path / "org.txt"),
        city_file=str(tmp_path / "city.txt"),
        org_ips_file=str(tmp_path / "org_ips.txt"),
        api_key="tok",
    )

    monkeypatch.setattr(B, "parse_args", lambda: args)
    monkeypatch.setattr(B, "load_env", lambda _p: None)

    with pytest.raises(SystemExit) as e:
        B.main()
    assert e.value.code == 1

