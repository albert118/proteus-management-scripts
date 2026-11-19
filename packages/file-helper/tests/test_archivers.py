import logging
from pathlib import Path

import pytest

from file_helper.commands.junk_archiver import JunkArchiver
from file_helper.commands.media_junk_archiver import MediaJunkArchiver

LOGGER = logging.getLogger("test")


def touch(path: Path, text: str = "") -> Path:
    path.write_text(text)
    return path


def names(path: Path) -> set[str]:
    return {p.name for p in path.iterdir()}


def test_missing_input_directory_raises(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        JunkArchiver([], ["txt"], tmp_path / "missing", tmp_path / "arch", LOGGER)


def test_archive_directory_is_created(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    JunkArchiver([], ["txt"], src, tmp_path / "arch", LOGGER)
    assert (tmp_path / "arch").is_dir()


def test_existing_archive_directory_is_tolerated(tmp_path):
    src, arch = tmp_path / "src", tmp_path / "arch"
    src.mkdir()
    arch.mkdir()
    JunkArchiver([], ["txt"], src, arch, LOGGER)


def test_blacklisted_files_are_moved_and_others_kept(tmp_path):
    src, arch = tmp_path / "src", tmp_path / "arch"
    src.mkdir()
    touch(src / "a.txt")
    touch(src / "film.mkv")

    JunkArchiver([], ["txt"], src, arch, LOGGER).collect()

    assert names(src) == {"film.mkv"}
    assert names(arch) == {"a.txt"}


def test_whitelist_overrides_blacklist(tmp_path):
    src, arch = tmp_path / "src", tmp_path / "arch"
    src.mkdir()
    touch(src / "a.txt")
    touch(src / "b.nfo")

    JunkArchiver(["txt"], ["txt", "nfo"], src, arch, LOGGER).collect()

    assert names(src) == {"a.txt"}
    assert names(arch) == {"b.nfo"}


def test_relative_cwd_does_not_double_join(tmp_path, monkeypatch):
    # a relative cwd must not be joined onto itself when archiving (fixed in PR #26)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    touch(tmp_path / "src" / "a.txt")

    JunkArchiver([], ["txt"], Path("src"), Path("arch"), LOGGER).collect()

    assert names(tmp_path / "src") == set()
    assert names(tmp_path / "arch") == {"a.txt"}
    assert not (tmp_path / "src" / "src").exists()


def test_existing_destination_file_is_not_overwritten(tmp_path, caplog):
    src, arch = tmp_path / "src", tmp_path / "arch"
    src.mkdir()
    arch.mkdir()
    touch(src / "a.txt", "new")
    touch(arch / "a.txt", "original")

    with caplog.at_level(logging.ERROR, logger="test"):
        JunkArchiver([], ["txt"], src, arch, LOGGER).collect()

    assert (arch / "a.txt").read_text() == "original"
    assert (src / "a.txt").read_text() == "new"
    assert any("a problem occurred" in r.message for r in caplog.records)


def test_no_garbage_leaves_directory_untouched(tmp_path):
    src, arch = tmp_path / "src", tmp_path / "arch"
    src.mkdir()
    touch(src / "film.mkv")

    JunkArchiver([], ["txt"], src, arch, LOGGER).collect()

    assert names(src) == {"film.mkv"}
    assert names(arch) == set()


def test_media_archiver_keeps_movie_content(tmp_path):
    src, arch = tmp_path / "src", tmp_path / "arch"
    src.mkdir()
    touch(src / "film.mkv")
    touch(src / "film.srt")

    MediaJunkArchiver(src, arch, LOGGER).collect()

    assert names(src) == {"film.mkv", "film.srt"}
    assert names(arch) == set()
