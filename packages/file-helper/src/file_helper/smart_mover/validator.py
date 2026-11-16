from os.path import exists


class Validator:
    def __init__(self, data):
        self._data = data
        self._is_valid = True

    def is_typed(self):
        self._is_valid &= type(self._data) == str
        return self

    def is_non_empty(self):
        self._is_valid &= len(self._data) > 0
        return self

    def file_exists(self):
        self._is_valid &= exists(self._data)
        return self

    def is_valid(self): return self._is_valid


def validate(data):
    return (
        Validator(data)
        .is_typed()
        .is_non_empty()
        # .file_exists()
        .is_valid()
    )
