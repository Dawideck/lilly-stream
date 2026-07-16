from datetime import datetime
from pathlib import Path

from lilly_stream.storage import (
    available_dates,
    free_space_mb,
    list_photos,
    parse_timestamp,
    photo_path,
)


def test_photo_path_builds_expected_layout():
    result = photo_path(Path("/data/photos"), datetime(2026, 7, 16, 14, 5, 30))
    assert result == Path("/data/photos/2026-07-16/140530.jpg")


def test_parse_timestamp_is_inverse_of_photo_path():
    path = photo_path(Path("/data/photos"), datetime(2026, 7, 16, 14, 5, 30))
    assert parse_timestamp(path) == datetime(2026, 7, 16, 14, 5, 30)


def test_list_photos_sorted_chronologically(tmp_path):
    (tmp_path / "2026-07-16").mkdir()
    (tmp_path / "2026-07-15").mkdir()
    (tmp_path / "2026-07-16" / "090000.jpg").write_bytes(b"")
    (tmp_path / "2026-07-15" / "180000.jpg").write_bytes(b"")
    (tmp_path / "2026-07-15" / "080000.jpg").write_bytes(b"")

    result = list_photos(tmp_path)

    assert result == [
        tmp_path / "2026-07-15" / "080000.jpg",
        tmp_path / "2026-07-15" / "180000.jpg",
        tmp_path / "2026-07-16" / "090000.jpg",
    ]


def test_list_photos_empty_dir_returns_empty_list(tmp_path):
    assert list_photos(tmp_path / "missing") == []


def test_list_photos_skips_malformed_filename_without_crashing(tmp_path):
    (tmp_path / "2026-07-15").mkdir()
    (tmp_path / "2026-07-15" / "080000.jpg").write_bytes(b"")
    (tmp_path / "2026-07-15" / "not-a-time.jpg").write_bytes(b"")
    (tmp_path / "2026-07-16").mkdir()
    (tmp_path / "2026-07-16" / "090000.jpg").write_bytes(b"")

    result = list_photos(tmp_path)

    assert result == [
        tmp_path / "2026-07-15" / "080000.jpg",
        tmp_path / "2026-07-16" / "090000.jpg",
    ]


def test_available_dates_counts_per_day(tmp_path):
    (tmp_path / "2026-07-16").mkdir()
    (tmp_path / "2026-07-16" / "090000.jpg").write_bytes(b"")
    (tmp_path / "2026-07-16" / "100000.jpg").write_bytes(b"")

    assert available_dates(tmp_path) == {"2026-07-16": 2}


def test_free_space_mb_returns_positive_number(tmp_path):
    assert free_space_mb(tmp_path) > 0
