from file_helper.validation.matchers import matches_movie_conent, matches_media_junk
from file_helper.commands.base_archiver import BaseArchiver


class MediaJunkArchiver(BaseArchiver):
    """Scan a directory for media content junk and archive it. This whitelists known 'good' media that is desirable to keep."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # currently I do prefer to do this but should make this configurable
        self.trash_cover_art = True

        if self.trash_cover_art:
            self.logger.warning("trash_cover_art enabled: will archive any custom cover photos")

    def get_potential_files(self):
        return [f for f in self.cwd.iterdir() if self.should_archive(f)]

    def should_archive(self, file):
        return (
            file.exists()
            and not matches_movie_conent(file)
            and matches_media_junk(file, remove_custom_cover_photo=self.trash_cover_art)
        )
