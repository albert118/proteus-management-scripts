import logging

from file_helper.smart_mover.mover import SmartMover


def test_create_parent_folder_creates_directory(tmp_path):
    result = SmartMover().create_parent_folder("Movie", str(tmp_path))
    assert (tmp_path / "Movie").is_dir()
    assert result == str(tmp_path / "Movie")


def test_create_parent_folder_existing_directory_warns(tmp_path, caplog):
    (tmp_path / "Movie").mkdir()

    with caplog.at_level(logging.WARNING):
        result = SmartMover().create_parent_folder("Movie", str(tmp_path))

    assert any("already exists" in r.message for r in caplog.records)
    # `return` inside `finally` swallows the re-raised FileExistsError, so the path is still returned.
    assert result == str(tmp_path / "Movie")
