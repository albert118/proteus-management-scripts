import importlib
import pkgutil

import pytest

import file_helper


def _module_names():
    return [m.name for m in pkgutil.walk_packages(file_helper.__path__, "file_helper.")]


def test_modules_are_discovered():
    assert "file_helper.main" in _module_names()


@pytest.mark.parametrize("name", _module_names())
def test_module_imports(name):
    # Catches case-mismatched and dangling imports that a case-insensitive filesystem hides.
    importlib.import_module(name)
