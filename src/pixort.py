from __future__ import annotations

import os
import re
import shutil
import concurrent.futures
from pathlib import Path
from datetime import datetime
from functools import partial
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
__version__ = "0.2.1"
__all__ = ["pixort", "get_date_taken"]

_DATE_REGEX = re.compile(
    "(?P<year>\d{4}):(?P<month>\d{2}):(?P<day>\d{2})(?P<etc>\s\d{2}:\d{2}:\d{2})"
)


def pixort(
    path: Annotated[str, tp.Argument()] = ".",
    output: Annotated[str, tp.Option("--output", "-o")] = None,
    n_workers: Annotated[Optional[int], tp.Option("--workers", "-w")] = None,
    excluded_extensions: Annotated[list[str], tp.Option("--exclude", "-e")] = None,
    copy: Annotated[bool, tp.Option("--copy", "-c")] = False,
) -> list[bool]:
    target_path = Path(output or path)

    process_func = partial(
        process_one, target_path, copy, set(excluded_extensions or {})
    )
    files_list = list(iter_files(path))

    if n_workers == 1:
        return [process_func(file) for file in track(files_list)]

    with concurrent.futures.ThreadPoolExecutor(n_workers) as ex:
        futures = [ex.submit(process_func, file) for file in files_list]

        return [
            f.result()
            for f in track(
                concurrent.futures.as_completed(futures),
                total=len(futures),
            )
        ]


# -- Date Extraction --
def _get_keys(metadata: Metadata, *keys) -> Optional[datetime]:
    for key in keys:
        if not metadata.has(key):
            continue

        return metadata.get(key)

    return None


def extract_hachoir_date(file: str) -> Optional[datetime]:
    parser = createParser(file)
    metadata = extractMetadata(parser)

    return _get_keys(
        metadata,
        "date_time_original",
        "date_time_digitized",
        "last_modification",
        "creation_date",
    )


def _try_hard(exif_date: str) -> str:
    if not (match := _DATE_REGEX.match(exif_date)):
        return None

    year, month, day, etc = map(match.group, ["year", "month", "day", "etc"])
    if int(month) == 0:
        month = "01"
    if int(day) == 0:
        day = "01"

    return f"{year}:{month}:{day}{etc}"


def extract_pillow_date(file: str) -> Optional[datetime]:
    with Image.open(str(file)) as pil_img:
        exif = pil_img.getexif()
        exif_date = exif.get(ORIGINAL_DATETIME_KEY, exif.get(DATETIME_KEY, None))
        if exif_date is None:
            return exif_date

        if exif_date := _try_hard(exif_date):
            return datetime.strptime(exif_date, "%Y:%m:%d %H:%M:%S")

    return None


def get_date_taken(path: str) -> Optional[datetime]:
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


# -- Workers --
def iter_files(path: str | Path):
    src_path = Path(path).resolve()
    for file in src_path.glob("**/*"):
        if not file.is_file():
            continue

        yield file


def process_one(
    target_path: Path, copy: bool, excluded_extensions: set, file: Path
) -> bool:
    if file.suffix in excluded_extensions:
        return False

    date = get_date_taken(file.as_posix())
    dest_path = from_date_to_path(target_path, date)

    return move_or_copy(file, dest_path, do_copy=copy)


# -- Move to Target --
def from_date_to_path(path: Path, date: datetime) -> Path:
    candidate_month = path / f"{date.year}-{date.month:0>2}"
    candidate_day = f"{date.year}-{date.month:0>2}-{date.day:0>2}"

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


def move_or_copy(src_file: Path, dest_path: Path, do_copy: bool = False) -> bool:
    # Create if not exists
    dest_path.parent.mkdir(exist_ok=True)
    dest_path.mkdir(exist_ok=True)

    # Move file
    if do_copy:
        shutil.copy2(src_file, dest_path / src_file.name)
    else:
        shutil.move(src_file, dest_path / src_file.name)

    return True


# -- CLI --
def main():
    from hachoir.core import config

    config.quiet = True
    tp.run(pixort)


if __name__ == "__main__":
    main()
