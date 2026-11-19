from file_helper.validation.base_matcher import BaseMatcher
from file_helper.smart_mover.cleaner import clean_file_name
from os.path import splitext


GARBAGE_FILES = [
    "RARBG.txt",
    "RARBG com.txt",
    "repack.txt",
    "[TGx]Downloaded from torrentgalaxy to .txt",
    "Torrent downloaded from SilverTorrent org.txt",
    "Torrent seeded from Secureboxes net.txt"
]

GARBAGE_FTYPES = [
    "nfo",
    "exe",
    "txt",
    "website"
]

COVER_IMAGE_FTYPESS = {
    "jpg"
}

GARBAGE_MEDIA = [
    "WWW YIFY-TORRENTS COM.jpg",
    "www YTS AM.jpg",
    "www YTS LT.jpg",
    "WWW YTS TO.jpg",
    "www YTS AM.jpg",
    "www YTS MX.jpg"
    "Sample.mkv",
    "Cover.jpg",
    "Screenshot.png",  # any variation,
    "folder.jpg"
]


def get_ftype(fn: str):
    _, fType = splitext(fn)
    return fType.replace('.', '').lower()


def get_fname(fn: str, apply_cleaning=True):
    fName, _ = splitext(fn)

    if apply_cleaning:
        cleaned_fn = clean_file_name(fName)
        return (cleaned_fn, _)

    return (fName, _)


class JunkMatcher(BaseMatcher):
    def is_garbage_type(self):
        self._is_valid &= get_ftype(self._data) in GARBAGE_FTYPES
        return self

    def is_given_garabage_type(self, **kwargs):
        garbage_ftypes = kwargs.pop("garbage_ftypes", [])

        if (len(garbage_ftypes) == 0):
            self._is_valid = True
            return self

        self._is_valid &= get_ftype(self._data) in garbage_ftypes
        return self

    def is_known_garbage(self):
        self._is_valid &= get_ftype(self._data) in GARBAGE_FTYPES
        return self

    def is_known_garbage_media(self):
        self._is_valid &= get_ftype(self._data) in GARBAGE_MEDIA
        return self

    def is_custom_cover_photo(self, **kwargs):
        remove_custom_cover_photo = kwargs.pop("remove_custom_cover_photo", False)

        if remove_custom_cover_photo:
            self._is_valid &= get_ftype(self._data) in COVER_IMAGE_FTYPESS

        return self
