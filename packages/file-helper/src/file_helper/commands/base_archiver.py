from logging import Logger
from abc import ABC, abstractmethod
from os import mkdir
from pathlib import Path
from shutil import move


class BaseArchiver(ABC):
    """
    Scan the provided directory and splits scanned content into a whitelist (keep) and blacklist (archive).
    Anything matched by the:
        - `matches_media_junk` matcher will be moved to the archive directory
        - `matches_movie_conent` will NOT be touched

    The archive directory is expected to be cleaned up after manual review.

    Call `collect()` when you're ready to execute.
    """

    def __init__(self, dir: Path, archive_directory: Path, logger: Logger):
        if not dir.exists():
            raise ValueError(f'Input directory {dir} does not exist')

        self.cwd = dir
        self.archive_directory = archive_directory
        self.logger = logger

        self.setup_archive_dir()

    def setup_archive_dir(self):
        try:
            mkdir(self.archive_directory)
            self.logger.debug("created archive directory")
        except FileExistsError:
            self.logger.warning("pre-existing archive directory found")
        finally:
            self.logger.info(f"will archive files to '{self.archive_directory}'")

    def archive(self, filename: Path):
        move(filename, self.archive_directory)
        self.logger.debug(f"archived '{filename}'")

    @abstractmethod
    def get_potential_files(self) -> list[Path]: pass

    def collect(self):
        try:
            self.logger.info(f"searching '{self.cwd}' for garbage...")
            potential_files = self.get_potential_files()
            file_count = len(potential_files)

            if file_count > 0:
                self.logger.info(f"{file_count} garbage files found")

                for fn in potential_files:
                    self.archive(fn)

                self.logger.info(f"{file_count} files archived")
            else:
                self.logger.info("no garbage files found, finishing early")
        except Exception as ex:
            self.logger.error(f"a problem occurred, {ex}")
            return
