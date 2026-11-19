from file_helper.smart_mover.cleaner import clean_file_name
from file_helper.smart_mover.validator import validate
import logging
from os import listdir, mkdir
from os.path import splitext, isfile, join
import shutil

_logger = logging.getLogger(__name__)


def get_file_info(fn: str):
    fName, fType = splitext(fn)

    cleaned_fn = clean_file_name(fName)
    cleaned_fType = fType.replace('.', '')

    return (cleaned_fn, cleaned_fType)


class SmartMover:
    def smart_move_directory(self, dir):
        potential_files = self.get_potential_files(dir)
        self.smart_move_files(potential_files, dir)

    def smart_move_file(self, fn, grandparent=None):
        try:
            cleaned_folder_name = self.pre_process(fn)
            new_parent = self.create_parent_folder(cleaned_folder_name, grandparent)
            self.move_to_new_parent(fn, new_parent, grandparent)
        except:
            return

    def smart_move_files(self, fns, source_dir):
        for fn in fns:
            self.smart_move_file(fn, source_dir)

    def create_parent_folder(self, folder_name, grandparent=None):
        new_dir = folder_name

        if (grandparent):
            new_dir = join(grandparent, folder_name)

        try:
            mkdir(new_dir)
            _logger.debug(f"created directory '{new_dir}'")
        except FileExistsError:
            _logger.warn(f"cannot create directory as it already exists '{folder_name}'")
            raise
        finally:
            return new_dir

    def move_to_new_parent(self, fn, dst, grandparent=None):
        src_fn = fn
        if (grandparent):
            src_fn = join(grandparent, fn)

        try:
            shutil.move(src_fn, dst)
            _logger.debug(f"moved file '{src_fn}' to directory '{dst}'")
        except Exception as e:
            _logger.warn(f"encountered exception: '{e}'")

    def get_potential_files(self, dir):
        potential_files = [f for f in listdir(dir) if isfile(join(dir, f))]
        return potential_files

    def pre_process(self, fn):
        if (not validate(fn)):
            message = f"couldn't validate the file name: '{fn}', no moves were made"
            _logger.error(message)
            raise ValueError(message)

        fName, _ = get_file_info(fn)
        return fName
