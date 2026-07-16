from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from lilly_stream.storage import list_photos, parse_timestamp


@dataclass
class PhotoEntry:
    path: Path
    timestamp: datetime


def list_entries_in_range(storage_dir: Path, start_date: date, end_date: date) -> list[PhotoEntry]:
    entries = []
    for photo in list_photos(storage_dir):
        ts = parse_timestamp(photo)
        if start_date <= ts.date() <= end_date:
            entries.append(PhotoEntry(path=photo, timestamp=ts))
    return entries


def thin_every_nth(entries: list[PhotoEntry], n: int) -> list[PhotoEntry]:
    if n < 1:
        raise ValueError("n must be >= 1")
    return entries[::n]


def thin_to_target_count(entries: list[PhotoEntry], target: int) -> list[PhotoEntry]:
    if target < 1:
        raise ValueError("target must be >= 1")
    if len(entries) <= target:
        return list(entries)
    stride = max(1, len(entries) // target)
    return thin_every_nth(entries, stride)
