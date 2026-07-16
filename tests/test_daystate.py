from datetime import date

from lilly_stream.daystate import DayState, DayStateStore


def test_store_round_trip(tmp_path):
    store = DayStateStore(tmp_path / "day_state.json")
    state = DayState(
        date=date(2026, 7, 16),
        photos_taken=5,
        photos_failed=1,
        first_photo_sent=True,
        last_photo_path="photos/2026-07-16/120000.jpg",
        last_photo_alert_sent=False,
        disk_alert_active=False,
    )
    store.save(state)
    assert store.load() == state


def test_store_load_missing_returns_none(tmp_path):
    store = DayStateStore(tmp_path / "day_state.json")
    assert store.load() is None


def test_store_load_corrupted_json_returns_none(tmp_path):
    store = DayStateStore(tmp_path / "day_state.json")
    # Write invalid/truncated JSON to simulate power loss during write
    (tmp_path / "day_state.json").write_text('{"date": "2026-07-16", "photos_taken": 5')
    assert store.load() is None
