import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

import pytest

from file_helper.commands.convert_to_nfo import NfoMediaConverter, create_movie_nfo, parse_info_json

LOGGER = logging.getLogger("test")

FULL = {
    "title": "My Clip",
    "description": "First line\nSecond line",
    "channel": "Chan",
    "upload_date": "20231108",
    "channel_url": "https://example.com/c",
    "categories": ["Comedy", "Music"],
}


def test_parse_keeps_first_description_line_and_parses_date():
    parsed = parse_info_json(FULL)
    assert parsed["description"] == "First line"
    assert parsed["upload_date"] == datetime(2023, 11, 8)
    assert parsed["author"] == "Chan"
    assert parsed["categories"] == ["Comedy", "Music"]


def test_parse_empty_description_falls_back():
    assert parse_info_json({**FULL, "description": ""})["description"] == "No description"


@pytest.mark.parametrize("key", ["description", "upload_date"])
def test_parse_raises_when_required_key_missing(key):
    data = {k: v for k, v in FULL.items() if k != key}
    with pytest.raises((AttributeError, TypeError)):
        parse_info_json(data)


@pytest.mark.parametrize(
    ("key", "output_key"),
    [("title", "title"), ("channel", "author"), ("channel_url", "channel_url"), ("categories", "categories")],
)
def test_parse_tolerates_missing_optional_key(key, output_key):
    data = {k: v for k, v in FULL.items() if k != key}
    assert parse_info_json(data)[output_key] is None


def nfo(**overrides):
    args = dict(title="T", plot="P", genre=["G"], credit="C", premiered=datetime(2023, 11, 8), source="S")
    return create_movie_nfo(**{**args, **overrides})


def test_nfo_is_well_formed_with_expected_fields():
    root = ET.fromstring(nfo())
    assert root.tag == "movie"
    assert root.findtext("title") == "T"
    assert root.findtext("premiered") == "2023-11-08"
    assert root.findtext("credits") == "C"
    assert root.findtext("url") == "S"


def test_nfo_escapes_xml_special_characters():
    root = ET.fromstring(nfo(title="A & B <i>", plot="x < y"))
    assert root.findtext("title") == "A & B <i>"
    assert root.findtext("plot") == "x < y"


def test_nfo_emits_one_genre_element_per_category():
    root = ET.fromstring(nfo(genre=["Comedy", "Music"]))
    assert [g.text for g in root.findall("genre")] == ["Comedy", "Music"]


@pytest.mark.parametrize("genre", [None, []])
def test_nfo_without_categories_has_no_genre(genre):
    assert ET.fromstring(nfo(genre=genre)).findall("genre") == []


def test_converter_requires_existing_directory(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        NfoMediaConverter(tmp_path / "missing", LOGGER)


def test_convert_writes_nfo_and_renames_media(tmp_path):
    (tmp_path / "abc.info.json").write_text(json.dumps(FULL))
    (tmp_path / "abc.mp4").write_bytes(b"x")

    NfoMediaConverter(tmp_path, LOGGER).convert()

    assert (tmp_path / "My Clip.mp4").exists()
    assert not (tmp_path / "abc.mp4").exists()
    assert (tmp_path / "abc.info.json").exists()
    assert ET.fromstring((tmp_path / "My Clip.nfo").read_text()).findtext("title") == "My Clip"


def test_convert_rejects_no_or_many_info_files(tmp_path):
    converter = NfoMediaConverter(tmp_path, LOGGER)
    with pytest.raises(ValueError, match="no"):
        converter.convert()
    (tmp_path / "a.info.json").write_text("{}")
    (tmp_path / "b.info.json").write_text("{}")
    with pytest.raises(ValueError, match="many"):
        converter.convert()
