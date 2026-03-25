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
