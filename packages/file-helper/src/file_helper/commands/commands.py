import argparse
from enum import Enum
from pathlib import Path


class Command(Enum):
    """The commands parsable by this utility. Each invokes a distinct submodule."""
    archive_junk = "archive_junk"
    archive_media_libray_junk = "archive_media_libray_junk"
    convert_to_nfo = "convert_to_nfo"


class CLIArgs(argparse.Namespace):
    command: Command
    cwd: Path
    verbose: bool
