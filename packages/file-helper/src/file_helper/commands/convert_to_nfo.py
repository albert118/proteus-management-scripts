from pathlib import Path
import json
from datetime import datetime
import textwrap
from xml.sax.saxutils import escape
import os
from logging import Logger
from pathlib import Path

# TODO: output filename is never sanitised.


class NfoMediaConverter():
    """Converts *.info.json files from media-roller to standard nfo files"""

    def __init__(self, dir: Path, logger: Logger):
        if not dir.exists():
            raise ValueError(f'Input directory {dir} does not exist')

        self.cwd = dir
        self.logger = logger

    def write_output(self, contents: str, name: str):
        try:
            output_filename = self.cwd / name
            with open(output_filename, 'x') as f:
                f.write(contents)

            self.logger.debug(f"created output {name}")
        except FileExistsError:
            self.logger.warning(f"pre-existing output found {name} - skipping")
        finally:
            self.logger.info(f"will output to '{name}'")

    def rename_file(self, oldname, newname):
        try:
            os.rename(oldname, newname)
        except FileNotFoundError as e:
            self.logger.warning(f"file was not found while renaming the media file '{oldname}'")
            raise e
        except FileExistsError as e:
            self.logger.warning(f"pre-existing file found while renaming the media file '{oldname}' to '{newname}'")
            raise e
        except Exception as e:
            self.logger.error(f"an error occurred while renaming the media file '{oldname}' to '{newname}'")
            raise e
        finally:
            self.logger.info(f"renamed source media file to '{newname}'")

    def get_json_data_from_target(self) -> tuple[Path, str]:
        try:
            matches = [
                f for f in self.cwd.iterdir()
                if f.is_file() and f.name.endswith(".info.json")
            ]

            if len(matches) == 0:
                raise ValueError('Discovered no *info.json targets.')
            elif len(matches) > 1:
                raise ValueError('Discovered many *info.json targets. Only one can be converted at a time.')

            target = matches[0]

            with open(target, 'r') as f:
                return (target, json.load(f))
        except FileNotFoundError as e:
            print(f"The expected *info.json was not found in the given directory: {self.cwd}")
            raise e
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from info file: {e}")
            raise e

    def convert(self):
        (resolved_target, data) = self.get_json_data_from_target()

        metadata = parse_info_json(data)
        nfo_xml = create_movie_nfo(
            title=metadata['title'],
            plot=metadata['description'],
            genre=metadata['categories'],
            credit=metadata['author'],
            premiered=metadata['upload_date'],
            source=metadata['channel_url']
        )

        # only write the new file, do not remove the original. This can be cleaned up manually
        # after reviewing the conversion was succesful
        self.write_output(nfo_xml, f"{metadata['title']}.nfo")

        # update the name of the associated video file too
        # note we don't copy the video file, as this would create excessive disk usage
        # given this content is typically GB's in size
        # these are all .mp4 files so I can be lazy for now
        # there should be a matching mp4 with the same name is the info file
        original_file_name = resolved_target.parent / resolved_target.name.replace(".info.json", ".mp4")
        new_file_name = resolved_target.parent / Path(f"{metadata['title']}.mp4")
        self.rename_file(original_file_name, new_file_name)


def parse_info_json(info_json):
    description_raw = info_json.get('description').splitlines()
    return {
        "title": info_json.get('title'),
        # only keep the first line of long YouTube descriptions
        "description": description_raw[0] if len(description_raw) >= 1 else "No description",
        "author": info_json.get('channel'),
        # expected format example: 20231108
        "upload_date": datetime.strptime(info_json.get('upload_date'), "%Y%m%d"),
        "channel_url": info_json.get('channel_url'),
        "categories": info_json.get('categories')
    }


def create_movie_nfo(title, plot, genre, credit, premiered, source):
    genres = [genre] if isinstance(genre, str) else (genre or [])
    genre_xml = "\n        ".join(f"<genre>{escape(str(g))}</genre>" for g in genres)
    nfo_data = f"""
    <movie>
        <title>{escape(str(title))}</title>
        <plot>{escape(str(plot))}</plot>
        <url>{escape(str(source))}</url>
        <tag>mediaroller</tag>
        {genre_xml}
        <credits>{escape(str(credit))}</credits>
        <premiered>{datetime.strftime(premiered, "%Y-%m-%d")}</premiered>
    </movie>"""

    return textwrap.dedent(nfo_data).strip()
