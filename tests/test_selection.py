from datetime import date, datetime, timedelta
from pathlib import Path

from lilly_stream.timelapse.selection import (
    PhotoEntry,
    list_entries_in_range,
    thin_every_nth,
    thin_to_target_count,
)


def make_photos(tmp_path, entries):
    for day_str, times in entries.items():
        day_dir = tmp_path / day_str
        day_dir.mkdir()
        for t in times:
            (day_dir / f"{t}.jpg").write_bytes(b"")
    return tmp_path


def test_list_entries_in_range_filters_by_date(tmp_path):
    storage = make_photos(tmp_path, {
        "2026-07-14": ["090000"],
        "2026-07-15": ["090000", "100000"],
        "2026-07-16": ["090000"],
    })
    result = list_entries_in_range(storage, date(2026, 7, 15), date(2026, 7, 15))
    assert len(result) == 2
    assert all(e.timestamp.date() == date(2026, 7, 15) for e in result)


def test_list_entries_in_range_sorted_chronologically(tmp_path):
    storage = make_photos(tmp_path, {"2026-07-15": ["100000", "090000"]})
    result = list_entries_in_range(storage, date(2026, 7, 15), date(2026, 7, 15))
    assert [e.timestamp.strftime("%H%M%S") for e in result] == ["090000", "100000"]


def test_list_entries_empty_range_returns_empty(tmp_path):
    storage = make_photos(tmp_path, {"2026-07-15": ["090000"]})
    result = list_entries_in_range(storage, date(2026, 8, 1), date(2026, 8, 2))
    assert result == []


def test_thin_every_nth_keeps_every_nth():
    entries = [PhotoEntry(path=Path(f"{i}.jpg"), timestamp=datetime(2026, 7, 15, 9, i)) for i in range(10)]
    result = thin_every_nth(entries, 3)
    assert [e.timestamp.minute for e in result] == [0, 3, 6, 9]


def test_thin_every_nth_n1_keeps_all():
    entries = [PhotoEntry(path=Path(f"{i}.jpg"), timestamp=datetime(2026, 7, 15, 9, i)) for i in range(5)]
    assert thin_every_nth(entries, 1) == entries


def test_thin_to_target_count_reduces_to_approximately_target():
    base_time = datetime(2026, 7, 15, 9, 0, 0)
    entries = [PhotoEntry(path=Path(f"{i}.jpg"), timestamp=base_time + timedelta(seconds=i)) for i in range(100)]
    result = thin_to_target_count(entries, 10)
    assert 8 <= len(result) <= 12


def test_thin_to_target_count_returns_all_when_fewer_than_target():
    entries = [PhotoEntry(path=Path(f"{i}.jpg"), timestamp=datetime(2026, 7, 15, 9, i)) for i in range(5)]
    assert thin_to_target_count(entries, 10) == entries
