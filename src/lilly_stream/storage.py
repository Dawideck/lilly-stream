from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def photo_path(storage_dir: Path, timestamp: datetime) -> Path:
    date_dir = storage_dir / timestamp.strftime("%Y-%m-%d")
    return date_dir / f"{timestamp.strftime('%H%M%S')}.jpg"


def parse_timestamp(path: Path) -> datetime:
    date_str = path.parent.name
    time_str = path.stem
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H%M%S")


def list_photos(storage_dir: Path) -> list[Path]:
    if not storage_dir.exists():
        return []
    return sorted(storage_dir.glob("*/*.jpg"), key=parse_timestamp)


def available_dates(storage_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for photo in list_photos(storage_dir):
        date_str = photo.parent.name
        counts[date_str] = counts.get(date_str, 0) + 1
    return dict(sorted(counts.items()))


def free_space_mb(path: Path) -> float:
    target = path if path.exists() else path.parent
    usage = shutil.disk_usage(target)
    return usage.free / (1024 * 1024)
