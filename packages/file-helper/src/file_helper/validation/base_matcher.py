from os import PathLike
from os.path import exists


class BaseMatcher:
    """
    A base class to implement 'matchers' from. Matchers find specific content to be handled
    based on patterns and strategies.
    """

    def __init__(self, data):
        self._data = data
        self._is_valid = True

    def is_typed(self):
        self._is_valid &= isinstance(self._data, (str, PathLike))
        return self

    def is_non_empty(self):
        self._is_valid &= len(str(self._data)) > 0
        return self

    def file_exists(self):
        self._is_valid &= exists(self._data)
        return self

    def is_valid(self): return self._is_valid
