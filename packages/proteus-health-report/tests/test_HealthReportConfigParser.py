import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pytest

import proteus_health_report.HealthReportConfigParser as parser_module
from proteus_health_report.HealthReportConfigParser import HealthReportConfigParser

APP_NAME = "proteus_health_report"


def describe_get_clean_string():
    def it_strips_wrapping_double_quotes():
        assert parse("[s]\nk=\"hello\"").get_clean_string("s", "k") == "hello"

    def it_strips_wrapping_single_quotes():
        assert parse("[s]\nk='hello'").get_clean_string("s", "k") == "hello"

    def it_trims_whitespace_inside_the_quotes():
        assert parse("[s]\nk=\"  hello  \"").get_clean_string("s", "k") == "hello"

    def it_leaves_unquoted_values_alone():
        assert parse("[s]\nk=hello").get_clean_string("s", "k") == "hello"

    def it_leaves_mismatched_quotes_alone():
        assert parse("[s]\nk=\"hello'").get_clean_string("s", "k") == "\"hello'"

    def it_raises_given_a_missing_option():
        with pytest.raises(configparser.NoOptionError):
            parse("[s]\nk=v").get_clean_string("s", "missing")


def describe_getlist():
    def it_splits_comma_separated_values_and_trims_items():
        assert parse("[s]\nk=a, b ,c").getlist("s", "k") == ["a", "b", "c"]

    def it_drops_empty_items():
        assert parse("[s]\nk=a,,b,").getlist("s", "k") == ["a", "b"]

    def it_parses_json_arrays():
        assert parse("[s]\nk=[\"a\", \"b\"]").getlist("s", "k") == ["a", "b"]

    def it_falls_back_to_comma_splitting_given_invalid_json():
        assert parse("[s]\nk=[a, b]").getlist("s", "k") == ["[a", "b]"]

    @pytest.mark.parametrize("raw,expected", [
        ('"/var/log/*"', ["/var/log/*"]),
        ("'/var/log/*'", ["/var/log/*"]),
        ('"/var/log/*", "/tmp/*"', ["/var/log/*", "/tmp/*"]),
        ("'a', 'b'", ["a", "b"]),
        ('"a,b"', ["a", "b"]),
    ])
    def it_strips_quotes_so_shell_globs_can_expand(raw, expected):
        assert parse(f"[s]\nk={raw}").getlist("s", "k") == expected

    def it_returns_the_fallback_given_a_missing_option():
        assert parse("[s]\nk=v").getlist("s", "missing", fallback=["x"]) == ["x"]

    def it_raises_given_a_missing_option_and_no_fallback():
        with pytest.raises(configparser.NoOptionError):
            parse("[s]\nk=v").getlist("s", "missing")


def describe_gettypedlist():
    def it_casts_items_to_the_requested_type():
        assert parse("[s]\nk=1, 2, 3").gettypedlist("s", "k", cast_type=int) == [1, 2, 3]

    def it_casts_booleans_using_the_ini_truth_map():
        assert parse("[s]\nk=yes, off, 1, FALSE").gettypedlist("s", "k", cast_type=bool) == [True, False, True, False]

    def it_wraps_cast_failures_in_a_parsing_error():
        with pytest.raises(configparser.ParsingError, match="to int"):
            parse("[s]\nk=1, two").gettypedlist("s", "k", cast_type=int)

    def it_wraps_invalid_booleans_in_a_parsing_error():
        with pytest.raises(configparser.ParsingError, match="to bool"):
            parse("[s]\nk=maybe").gettypedlist("s", "k", cast_type=bool)

    def it_returns_the_fallback_given_a_missing_option():
        assert parse("[s]\nk=1").gettypedlist("s", "missing", cast_type=int, fallback=[9]) == [9]

    def it_returns_the_fallback_given_a_missing_section():
        assert parse("[s]\nk=1").gettypedlist("missing", "k", cast_type=int, fallback=[9]) == [9]

    def it_raises_given_a_missing_option_and_no_fallback():
        with pytest.raises(configparser.NoOptionError):
            parse("[s]\nk=1").gettypedlist("s", "missing", cast_type=int)

    def it_raises_given_a_missing_section_and_no_fallback():
        # has_option() is False for an unknown section, so this surfaces as NoOptionError
        with pytest.raises(configparser.NoOptionError):
            parse("[s]\nk=1").gettypedlist("missing", "k", cast_type=int)


def describe_get_typed():
    @pytest.mark.parametrize("raw,cast_type,expected", [
        ("true", bool, True),
        ("no", bool, False),
        ("42", int, 42),
        ("1.5", float, 1.5),
        ('"hello"', str, "hello"),
        ('"/some/dir"', Path, Path("/some/dir")),
    ])
    def it_casts_scalars(raw, cast_type, expected):
        assert parse(f"[s]\nk={raw}").get_typed("s", "k", cast_type) == expected

    def it_casts_bare_list_to_strings():
        assert parse("[s]\nk=a, b").get_typed("s", "k", list) == ["a", "b"]

    def it_casts_parameterised_lists_to_the_item_type():
        assert parse("[s]\nk=1, 2").get_typed("s", "k", List[int]) == [1, 2]

    def it_casts_parameterised_boolean_lists():
        assert parse("[s]\nk=true, false").get_typed("s", "k", List[bool]) == [True, False]

    def it_raises_given_a_non_numeric_int():
        with pytest.raises(ValueError):
            parse("[s]\nk=abc").get_typed("s", "k", int)

    def it_wraps_custom_cast_failures_in_a_parsing_error():
        def explode(_value):
            raise ValueError("nope")

        with pytest.raises(configparser.ParsingError, match="cannot be cast"):
            parse("[s]\nk=abc").get_typed("s", "k", explode)


def describe_to_dataclass():
    def it_maps_sections_and_options_to_nested_dataclasses():
        result = parse("[inner]\nname=\"abc\"\ncount=3").to_dataclass(Root)

        assert result == Root(inner=Inner(name="abc", count=3))

    def it_uses_the_dataclass_default_given_a_missing_option():
        result = parse("[defaulted]\nname=x").to_dataclass(DefaultedRoot)

        assert result.defaulted == Defaulted(name="x", count=7, tags=["t"])

    def it_raises_given_a_missing_option_without_a_default():
        with pytest.raises(configparser.NoOptionError):
            parse("[inner]\nname=abc").to_dataclass(Root)

    def it_raises_given_a_non_dataclass_target():
        with pytest.raises(TypeError, match="must be a valid @dataclass"):
            parse("[s]\nk=v").to_dataclass(dict)

    def it_raises_given_a_section_field_that_is_not_a_dataclass():
        with pytest.raises(TypeError, match="nested section dataclass"):
            parse("[s]\nk=v").to_dataclass(BadRoot)


def describe_load_hierarchy():
    def it_lets_later_files_override_earlier_ones(tmp_path):
        first = write(tmp_path / "first.ini", "[s]\na=1\nb=1")
        second = write(tmp_path / "second.ini", "[s]\nb=2")
        config = HealthReportConfigParser()

        loaded = config.load_hierarchy([first, second])

        assert loaded == [str(first), str(second)]
        assert config.get("s", "a") == "1"
        assert config.get("s", "b") == "2"

    def it_skips_missing_files(tmp_path):
        present = write(tmp_path / "present.ini", "[s]\na=1")
        config = HealthReportConfigParser()

        assert config.load_hierarchy([tmp_path / "missing.ini", present]) == [str(present)]


def describe_load():
    def it_creates_the_user_config_from_the_packaged_default_when_missing(tmp_path, isolate_load):
        user_config = isolate_load(tmp_path)

        HealthReportConfigParser().load(APP_NAME, "author")

        assert user_config.exists()
        assert user_config.read_text(encoding="utf-8") == packaged_default().read_text(encoding="utf-8")

    def it_does_not_create_the_user_config_when_debugging(tmp_path, isolate_load):
        user_config = isolate_load(tmp_path)

        config = HealthReportConfigParser().load(APP_NAME, "author", debug=True)

        assert not user_config.exists()
        assert len(config.loaded_files) == 1

    def it_loads_defaults_then_user_then_local_override_in_order(tmp_path, isolate_load):
        user_config = isolate_load(tmp_path)
        write(user_config, "[report]\nhostname=from-user\nservices_to_monitor=from-user")
        write(tmp_path / ".config.local.ini", "[report]\nhostname=from-local")

        config = HealthReportConfigParser().load(APP_NAME, "author")

        assert [Path(p).name for p in config.loaded_files] == ["default_config.ini", "config.ini", ".config.local.ini"]
        assert config.get_clean_string("report", "hostname") == "from-local"
        assert config.get_clean_string("report", "services_to_monitor") == "from-user"
        # untouched by either override
        assert config.get_clean_string("file_reporting", "file_size") == "500M"

    def it_does_not_overwrite_an_existing_user_config(tmp_path, isolate_load):
        user_config = isolate_load(tmp_path)
        write(user_config, "[report]\nhostname=mine")

        HealthReportConfigParser().load(APP_NAME, "author")

        assert user_config.read_text(encoding="utf-8") == "[report]\nhostname=mine"

    def it_falls_back_to_home_when_xdg_config_home_is_unset(tmp_path, monkeypatch, isolate_load):
        isolate_load(tmp_path)
        monkeypatch.setenv("XDG_CONFIG_HOME", "placeholder")  # registers the variable for restoration
        monkeypatch.delenv("XDG_CONFIG_HOME")
        monkeypatch.setenv("HOME", str(tmp_path / "home"))

        HealthReportConfigParser().load(APP_NAME, "author")

        assert os.environ["XDG_CONFIG_HOME"] == os.path.join(str(tmp_path / "home"), ".config")

    def it_keeps_an_existing_xdg_config_home(tmp_path, monkeypatch, isolate_load):
        isolate_load(tmp_path)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.setenv("HOME", str(tmp_path / "home"))

        HealthReportConfigParser().load(APP_NAME, "author")

        assert os.environ["XDG_CONFIG_HOME"] == str(tmp_path / "xdg")


@pytest.fixture
def isolate_load(monkeypatch):
    """
    Points the user config dir and the local override location at tmp_path so load() never touches the real
    user config or the source tree. Returns the user config path (not created).
    """
    def apply(tmp_path: Path) -> Path:
        user_dir = tmp_path / "user-config"

        class FakePlatformDirs:
            def __init__(self, *_args, **_kwargs):
                self.user_config_dir = str(user_dir)

        monkeypatch.setattr(parser_module, "PlatformDirs", FakePlatformDirs)
        # load() resolves .config.local.ini beside this module's __file__
        monkeypatch.setattr(parser_module, "__file__", str(tmp_path / "HealthReportConfigParser.py"))
        return user_dir / "config.ini"

    return apply


def packaged_default() -> Path:
    from importlib import resources
    return Path(str(resources.files(APP_NAME).joinpath("default_config.ini")))


def parse(text: str) -> HealthReportConfigParser:
    config = HealthReportConfigParser()
    config.read_string(text)
    return config


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@dataclass
class Inner:
    name: str
    count: int


@dataclass
class Root:
    inner: Inner


@dataclass
class Defaulted:
    name: str
    count: int = 7
    tags: List[str] = field(default_factory=lambda: ["t"])


@dataclass
class DefaultedRoot:
    defaulted: Defaulted


@dataclass
class BadRoot:
    s: str
