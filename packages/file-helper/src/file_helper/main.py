#!/usr/bin/env python3
"""Some file handling utils."""

from pathlib import Path
import sys
import logging
import argparse
from file_helper.commands.commands import Command
from file_helper.commands.junk_archiver import JunkArchiver
from file_helper.commands.media_junk_archiver import MediaJunkArchiver
from file_helper.commands.convert_to_nfo import NfoMediaConverter

_logger = logging.getLogger(__name__)


def setup_argument_parser():
    """Configure common args for all commands. Binds handlers for specific commands. file_helper.commands for the full list of available commands."""
    parser = argparse.ArgumentParser(
        prog="file-helper",
        description='Some common Python file helper utilities I frequently require including: validation; cleaning; and moving.'
    )

    parser.add_argument(
        '--cwd',
        type=Path,
        help='The current working directory to execute from.'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose mode'
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    collect_garbage_parser = subparsers.add_parser(
        Command.archive_junk.value, help="Clean-up any junk content based on the provided white/blacklist filetypes.")

    collect_garbage_parser = subparsers.add_parser(
        Command.archive_media_libray_junk.value, help="Clean-up the media library junk content.")

    convert_to_nfo_parser = subparsers.add_parser(
        Command.convert_to_nfo.value, help="Converts *.info.json files from media-roller to standard nfo files.")

    return parser


def handle_command(args: argparse.Namespace):
    match args.command:
        case Command.archive_media_libray_junk:
            archiver = MediaJunkArchiver(args.dir, args.archive_dir, _logger)
            archiver.collect()
        case Command.archive_junk:
            archiver = JunkArchiver(args.whitelist, args.blacklist, args.dir, args.archivedir, _logger)
            archiver.collect()
        case Command.convert_to_nfo:
            converter = NfoMediaConverter(args.dir, _logger)
            converter.convert()
        case _:
            raise ValueError(f'unhandled command provided: {args.command}')


def setup_logger(log_level):
    logging.basicConfig(level=log_level)
    return logging.getLogger(__name__)


def main() -> None:
    arg_parser = setup_argument_parser()
    args = arg_parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logger(log_level)

    try:
        handle_command(args.command)
    except Exception as e:
        _logger.error(f'failed to execute with error: {e}')
        sys.exit(1)


if __name__ == "__main__":
    main()
