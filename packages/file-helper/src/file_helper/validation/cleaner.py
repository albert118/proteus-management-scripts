from logging import Logger


class Cleaner:
    """Clean a given string."""

    def __init__(self, data: str):
        self._data = data

    def clean_edges(self):
        self._data = self._data.strip()
        return self

    def clean_full_stops(self):
        self._data = self._data.replace('.', ' ')
        return self

    def clean(self): return self._data


def clean_file_name(fn: str, logger: Logger) -> str:

    try:
        return (
            Cleaner(fn)
            .clean_edges()
            .clean_full_stops()
            .clean()
        )
    except Exception as e:
        logger.error(f"error when cleaning data '{e}'")
        raise
