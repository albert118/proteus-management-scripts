from file_helper.commands.base_archiver import BaseArchiver
from file_helper.validation.matchers import matches_provided_junk


class JunkArchiver(BaseArchiver):
    """Scan a directory for junk content based on the provided filetype whitelist + blaclist lists. Content will be archived to the configured archival directory"""

    def __init__(self, whitelist: list[str], blacklist: list[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.garbage_extensions = [ext for ext in blacklist if ext not in whitelist]

    def get_potential_files(self):
        kwargs = {"garbage_ftypes": self.garbage_extensions}
        return [f for f in self.cwd.iterdir() if matches_provided_junk(f, **kwargs)]
