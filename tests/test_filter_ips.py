from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest


def load_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "filter-ips.py"

    loader = SourceFileLoader("filter_ips", str(module_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None

    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


F = load_module()


def test_filter_ips_writes_distinct_sorted_ips(tmp_path, monkeypatch):
    out = tmp_path / "ip_list.txt"
    out.write_text("2.2.2.2\n1.1.1.1\n", encoding="utf-8")

    # Simulate CLI: filter-ips.py <ips...> -o <output>
    monkeypatch.setattr(
        __import__("sys"),
        "argv",
        [
            "filter-ips.py",
            "3.3.3.3",
            "2.2.2.2",
            "4.4.4.4",
            "-o",
            str(out),
        ],
        raising=True,
    )

    F.main()

    assert out.read_text(encoding="utf-8") == "1.1.1.1\n2.2.2.2\n3.3.3.3\n4.4.4.4\n"

