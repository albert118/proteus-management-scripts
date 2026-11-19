from pathlib import PurePath

import pytest

from file_helper.validation.base_matcher import BaseMatcher
from file_helper.validation.matchers import matches_media_junk, matches_movie_conent, matches_provided_junk

AS_STR_AND_PATH = [str, PurePath]


@pytest.mark.parametrize("wrap", AS_STR_AND_PATH)
@pytest.mark.parametrize("name", ["film.mkv", "film.mp4", "film.srt", "film.vtt"])
def test_movie_content_matched(wrap, name):
    assert matches_movie_conent(wrap(name)) is True


@pytest.mark.parametrize("wrap", AS_STR_AND_PATH)
@pytest.mark.parametrize("name", ["notes.txt", "cover.jpg", "noextension"])
def test_non_movie_content_not_matched(wrap, name):
    assert matches_movie_conent(wrap(name)) is False


@pytest.mark.parametrize("wrap", AS_STR_AND_PATH)
def test_provided_junk_matches_listed_extension(wrap):
    assert matches_provided_junk(wrap("a.txt"), garbage_ftypes=["txt"]) is True


@pytest.mark.parametrize("wrap", AS_STR_AND_PATH)
def test_provided_junk_extension_match_is_case_insensitive(wrap):
    assert matches_provided_junk(wrap("a.TXT"), garbage_ftypes=["txt"]) is True


@pytest.mark.parametrize("wrap", AS_STR_AND_PATH)
def test_provided_junk_ignores_unlisted_extension(wrap):
    assert matches_provided_junk(wrap("a.mkv"), garbage_ftypes=["txt"]) is False


@pytest.mark.parametrize("data", [123, None, ["a.txt"]])
def test_non_path_like_inputs_fail_type_check(data):
    assert BaseMatcher(data).is_typed().is_valid() is False


@pytest.mark.parametrize("wrap", AS_STR_AND_PATH)
def test_path_like_inputs_pass_type_check(wrap):
    assert BaseMatcher(wrap("a.txt")).is_typed().is_non_empty().is_valid() is True


def test_empty_string_is_rejected():
    assert matches_movie_conent("") is False
    assert matches_provided_junk("", garbage_ftypes=["txt"]) is False


@pytest.mark.parametrize("wrap", AS_STR_AND_PATH)
def test_media_junk_does_not_match_movie_files(wrap):
    assert matches_media_junk(wrap("film.mkv")) is False
