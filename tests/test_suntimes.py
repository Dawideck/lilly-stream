from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from lilly_stream.suntimes import (
    SuntimesCache,
    SuntimesUnavailableError,
    TwilightWindow,
    get_twilight_window,
    is_daylight,
)

WARSAW = ZoneInfo("Europe/Warsaw")


def make_window(d: date) -> TwilightWindow:
    return TwilightWindow(
        date=d,
        civil_dawn=datetime(d.year, d.month, d.day, 5, 0, tzinfo=WARSAW),
        civil_dusk=datetime(d.year, d.month, d.day, 21, 0, tzinfo=WARSAW),
    )


def test_cache_round_trip(tmp_path):
    cache = SuntimesCache(tmp_path / "sun_times.json")
    window = make_window(date(2026, 7, 16))
    cache.save(window)
    assert cache.load() == window


def test_cache_load_missing_returns_none(tmp_path):
    cache = SuntimesCache(tmp_path / "sun_times.json")
    assert cache.load() is None


def test_get_twilight_window_uses_fetch_and_caches(tmp_path):
    cache = SuntimesCache(tmp_path / "sun_times.json")
    fetched = make_window(date(2026, 7, 16))
    result = get_twilight_window(
        54.1755, 15.5836, date(2026, 7, 16), cache, fetch_fn=lambda lat, lon, d: fetched
    )
    assert result == fetched
    assert cache.load() == fetched


def test_get_twilight_window_falls_back_to_cache_on_fetch_failure(tmp_path):
    cache = SuntimesCache(tmp_path / "sun_times.json")
    cached = make_window(date(2026, 7, 15))
    cache.save(cached)

    def failing_fetch(lat, lon, d):
        raise ConnectionError("no network")

    result = get_twilight_window(54.1755, 15.5836, date(2026, 7, 16), cache, fetch_fn=failing_fetch)
    assert result == cached


def test_get_twilight_window_raises_when_no_cache_and_fetch_fails(tmp_path):
    cache = SuntimesCache(tmp_path / "sun_times.json")

    def failing_fetch(lat, lon, d):
        raise ConnectionError("no network")

    with pytest.raises(SuntimesUnavailableError):
        get_twilight_window(54.1755, 15.5836, date(2026, 7, 16), cache, fetch_fn=failing_fetch)


def test_is_daylight_true_inside_window():
    window = make_window(date(2026, 7, 16))
    assert is_daylight(window, datetime(2026, 7, 16, 12, 0, tzinfo=WARSAW)) is True


def test_is_daylight_false_before_dawn():
    window = make_window(date(2026, 7, 16))
    assert is_daylight(window, datetime(2026, 7, 16, 3, 0, tzinfo=WARSAW)) is False


def test_is_daylight_false_after_dusk():
    window = make_window(date(2026, 7, 16))
    assert is_daylight(window, datetime(2026, 7, 16, 22, 0, tzinfo=WARSAW)) is False
