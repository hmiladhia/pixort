from __future__ import annotations

import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Annotated, Optional

import typer as tp
from rich.progress import track

import filetype
from hachoir.parser import createParser
from hachoir.metadata import extractMetadata
from hachoir.metadata.metadata import Metadata
from PIL import Image, ExifTags


DATETIME_KEY = ExifTags.Base.DateTime
ORIGINAL_DATETIME_KEY = ExifTags.Base.DateTimeOriginal

__author__ = "Dhia Hmila"
__version__ = "0.1.1"
__all__ = ["pixort", "get_date_taken"]


def pixort(
    path: Annotated[str, tp.Argument()] = ".",
    output: Annotated[str, tp.Option("--output", "-o")] = None,
    copy: Annotated[bool, tp.Option("--copy", "-c")] = False,
):
    src_path = Path(path).resolve()
    target_path = Path(output or path)

    file_list = list(iter_files(path))
    for file in track(file_list, description="Processing...\n"):
        # TODO: filter extensions / mime_types

        date = get_date_taken(src_path / file)
        dest_path = from_date_to_path(target_path, date)

        move_or_copy(file, dest_path, do_copy=copy)


def _get_keys(metadata: Metadata, *keys) -> Optional[datetime]:
    for key in keys:
        if not metadata.has(key):
            continue

        return metadata.get(key)

    return None


def extract_hachoir_date(file: Path) -> Optional[datetime]:
    parser = createParser(file.as_posix())
    metadata = extractMetadata(parser)

    return _get_keys(
        metadata,
        "date_time_original",
        "date_time_digitized",
        "last_modification",
        "creation_date",
    )


def extract_pillow_date(file: Path) -> Optional[datetime]:
    with Image.open(str(file)) as pil_img:
        exif = pil_img.getexif()
        if exif_date := exif.get(ORIGINAL_DATETIME_KEY, exif.get(DATETIME_KEY, None)):
            return datetime.strptime(exif_date, "%Y:%m:%d %H:%M:%S")

    return None


def get_date_taken(path: Path) -> Optional[datetime]:
    # TODO: Try regex first

    # Could use hachoir for both video and image
    # but pillow is much faster
    if filetype.is_image(path) and (exif_date := extract_pillow_date(path)):
        return exif_date
    elif (filetype.is_video(path) or filetype.is_audio(path)) and (
        exif_date := extract_hachoir_date(path)
    ):
        return exif_date

    return datetime.fromtimestamp(os.path.getmtime(path))


def iter_files(path: str | Path):
    src_path = Path(path).resolve()
    for file in src_path.glob("**/*"):
        if not file.is_file():
            continue

        yield file


def from_date_to_path(path: Path, date: datetime) -> Path:
    candidate_month = path / f"{date.year}-{date.month:0>2}"
    candidate_day = f"{date.day:0>2}"

    if not candidate_month.exists():
        return candidate_month / candidate_day

    candidate_day = next(
        (
            day.name
            for day in candidate_month.iterdir()
            if day.name.startswith(f"{candidate_day} -")
        ),
        candidate_day,
    )

    return candidate_month / candidate_day


def move_or_copy(src_file: Path, dest_path: Path, do_copy: bool = False):
    # Create if not exists
    dest_path.parent.mkdir(exist_ok=True)
    dest_path.mkdir(exist_ok=True)

    # Move file
    if do_copy:
        shutil.copyfile(src_file, dest_path / src_file.name)
    else:
        shutil.move(src_file, dest_path / src_file.name)


def main():
    from hachoir.core import config

    config.quiet = True
    tp.run(pixort)


if __name__ == "__main__":
    main()
