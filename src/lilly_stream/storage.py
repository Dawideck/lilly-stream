from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


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
    dated: list[tuple[Path, datetime]] = []
    for path in storage_dir.glob("*/*.jpg"):
        try:
            dated.append((path, parse_timestamp(path)))
        except ValueError:
            log.warning(f"Skipping photo with unparseable timestamp: {path}")
    dated.sort(key=lambda item: item[1])
    return [path for path, _ in dated]


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
