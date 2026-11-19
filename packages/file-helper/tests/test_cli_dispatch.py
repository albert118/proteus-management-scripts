import logging
from pathlib import Path

import pytest

from file_helper import main as fh_main
from file_helper.commands.commands import CLIArgs, Command


class Recorder:
    calls: list = []

    def __init__(self, *args):
        self.args = args
        Recorder.calls.append(self)

    def collect(self):
        self.action = "collect"

    def convert(self):
        self.action = "convert"


@pytest.fixture(autouse=True)
def fake_handlers(monkeypatch):
    Recorder.calls = []
    for name in ("MediaJunkArchiver", "JunkArchiver", "NfoMediaConverter"):
        monkeypatch.setattr(fh_main, name, type(name, (Recorder,), {}))


def parse(*argv):
    return fh_main.setup_argument_parser().parse_args(list(argv), namespace=CLIArgs())


def test_archive_junk_routes_to_junk_archiver(tmp_path):
    args = parse("--cwd", str(tmp_path), "archive_junk", "--archive-dir", str(tmp_path / "a"),
                 "--whitelist", "jpg", "--blacklist", "txt", "nfo")
    fh_main.handle_command(args)

    (call,) = Recorder.calls
    assert type(call).__name__ == "JunkArchiver"
    whitelist, blacklist, cwd, archive_dir, logger = call.args
    assert whitelist == ["jpg"]
    assert blacklist == ["txt", "nfo"]
    assert cwd == Path(tmp_path)
    assert archive_dir == tmp_path / "a"
    assert isinstance(logger, logging.Logger)
    assert call.action == "collect"


def test_archive_media_library_junk_routes_to_media_archiver(tmp_path):
    args = parse("--cwd", str(tmp_path), "archive_media_libray_junk", "--archive-dir", str(tmp_path / "a"))
    fh_main.handle_command(args)

    (call,) = Recorder.calls
    assert type(call).__name__ == "MediaJunkArchiver"
    assert call.args[:2] == (Path(tmp_path), tmp_path / "a")
    assert call.action == "collect"


def test_convert_to_nfo_routes_to_converter(tmp_path):
    fh_main.handle_command(parse("--cwd", str(tmp_path), "convert_to_nfo"))

    (call,) = Recorder.calls
    assert type(call).__name__ == "NfoMediaConverter"
    assert call.args[0] == Path(tmp_path)
    assert call.action == "convert"


def test_every_command_has_a_subparser(tmp_path):
    for command in Command:
        extra = ["--archive-dir", str(tmp_path)] if command is not Command.convert_to_nfo else []
        assert parse("--cwd", str(tmp_path), command.value, *extra).command == command


def test_unknown_command_is_rejected():
    with pytest.raises(SystemExit):
        parse("nope")


def test_unhandled_command_raises():
    with pytest.raises(ValueError, match="unhandled command"):
        fh_main.handle_command(CLIArgs(command="other"))


def test_main_exits_non_zero_when_command_fails(monkeypatch, tmp_path):
    def boom(args):
        raise RuntimeError("boom")

    monkeypatch.setattr(fh_main, "handle_command", boom)
    monkeypatch.setattr("sys.argv", ["fh", "--cwd", str(tmp_path), "convert_to_nfo"])
    with pytest.raises(SystemExit) as exc:
        fh_main.main()
    assert exc.value.code == 1
