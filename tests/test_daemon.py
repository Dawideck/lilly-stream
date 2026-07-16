from datetime import date, datetime
from zoneinfo import ZoneInfo

from lilly_stream.capture.daemon import handle_tick
from lilly_stream.config import AlertsConfig, CaptureConfig, Config, DiskConfig, LocationConfig
from lilly_stream.daystate import DayStateStore
from lilly_stream.suntimes import SuntimesCache, TwilightWindow

WARSAW = ZoneInfo("Europe/Warsaw")


class FakeCamera:
    def __init__(self, fail=False):
        self.fail = fail
        self.captured = []

    def capture(self, path):
        if self.fail:
            raise RuntimeError("camera error")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")
        self.captured.append(path)


class FakeMailer:
    def __init__(self):
        self.sent = []

    def send(self, subject, body, attachments=None):
        self.sent.append((subject, body, attachments or []))


def make_config(tmp_path) -> Config:
    return Config(
        location=LocationConfig(name="Kolobrzeg, PL", lat=54.1755, lon=15.5836),
        capture=CaptureConfig(interval_minutes=10, storage_dir=tmp_path / "photos"),
        disk=DiskConfig(warn_threshold_mb=1),
        alerts=AlertsConfig(recipient="you@example.com"),
        state_dir=tmp_path / "state",
    )


def fixed_window(d: date) -> TwilightWindow:
    return TwilightWindow(
        date=d,
        civil_dawn=datetime(d.year, d.month, d.day, 5, 0, tzinfo=WARSAW),
        civil_dusk=datetime(d.year, d.month, d.day, 21, 0, tzinfo=WARSAW),
    )


def make_stores(config):
    cache = SuntimesCache(config.state_dir / "sun_times.json")
    store = DayStateStore(config.state_dir / "day_state.json")
    return cache, store


def test_tick_during_daylight_captures_and_sends_first_photo_alert(tmp_path):
    config = make_config(tmp_path)
    camera = FakeCamera()
    mailer = FakeMailer()
    cache, store = make_stores(config)

    handle_tick(
        now=datetime(2026, 7, 16, 12, 0, tzinfo=WARSAW),
        config=config, camera=camera, mailer=mailer,
        suntimes_cache=cache, day_state_store=store,
        fetch_fn=lambda lat, lon, d: fixed_window(d),
    )

    assert len(camera.captured) == 1
    assert any("First photo" in s for s, _, _ in mailer.sent)
    state = store.load()
    assert state.photos_taken == 1
    assert state.first_photo_sent is True


def test_second_tick_same_day_does_not_resend_first_photo_alert(tmp_path):
    config = make_config(tmp_path)
    camera = FakeCamera()
    mailer = FakeMailer()
    cache, store = make_stores(config)
    fetch_fn = lambda lat, lon, d: fixed_window(d)

    handle_tick(now=datetime(2026, 7, 16, 12, 0, tzinfo=WARSAW), config=config, camera=camera,
                mailer=mailer, suntimes_cache=cache, day_state_store=store, fetch_fn=fetch_fn)
    handle_tick(now=datetime(2026, 7, 16, 12, 10, tzinfo=WARSAW), config=config, camera=camera,
                mailer=mailer, suntimes_cache=cache, day_state_store=store, fetch_fn=fetch_fn)

    first_photo_alerts = [s for s, _, _ in mailer.sent if "First photo" in s]
    assert len(first_photo_alerts) == 1
    assert store.load().photos_taken == 2


def test_tick_outside_daylight_does_not_capture(tmp_path):
    config = make_config(tmp_path)
    camera = FakeCamera()
    mailer = FakeMailer()
    cache, store = make_stores(config)

    handle_tick(now=datetime(2026, 7, 16, 2, 0, tzinfo=WARSAW), config=config, camera=camera,
                mailer=mailer, suntimes_cache=cache, day_state_store=store,
                fetch_fn=lambda lat, lon, d: fixed_window(d))

    assert camera.captured == []


def test_tick_after_dusk_sends_last_photo_alert_once(tmp_path):
    config = make_config(tmp_path)
    camera = FakeCamera()
    mailer = FakeMailer()
    cache, store = make_stores(config)
    fetch_fn = lambda lat, lon, d: fixed_window(d)

    handle_tick(now=datetime(2026, 7, 16, 20, 55, tzinfo=WARSAW), config=config, camera=camera,
                mailer=mailer, suntimes_cache=cache, day_state_store=store, fetch_fn=fetch_fn)
    handle_tick(now=datetime(2026, 7, 16, 21, 5, tzinfo=WARSAW), config=config, camera=camera,
                mailer=mailer, suntimes_cache=cache, day_state_store=store, fetch_fn=fetch_fn)
    handle_tick(now=datetime(2026, 7, 16, 21, 15, tzinfo=WARSAW), config=config, camera=camera,
                mailer=mailer, suntimes_cache=cache, day_state_store=store, fetch_fn=fetch_fn)

    last_photo_alerts = [s for s, _, _ in mailer.sent if "Last photo" in s]
    assert len(last_photo_alerts) == 1


def test_day_rollover_sends_summary_and_resets_state(tmp_path):
    config = make_config(tmp_path)
    camera = FakeCamera()
    mailer = FakeMailer()
    cache, store = make_stores(config)
    fetch_fn = lambda lat, lon, d: fixed_window(d)

    handle_tick(now=datetime(2026, 7, 16, 12, 0, tzinfo=WARSAW), config=config, camera=camera,
                mailer=mailer, suntimes_cache=cache, day_state_store=store, fetch_fn=fetch_fn)
    handle_tick(now=datetime(2026, 7, 17, 12, 0, tzinfo=WARSAW), config=config, camera=camera,
                mailer=mailer, suntimes_cache=cache, day_state_store=store, fetch_fn=fetch_fn)

    summaries = [(s, b) for s, b, _ in mailer.sent if "summary" in s.lower()]
    assert len(summaries) == 1
    subject, body = summaries[0]
    assert "disk" in body.lower()
    assert "MB" in body
    state = store.load()
    assert state.date == date(2026, 7, 17)
    assert state.photos_taken == 1


def test_camera_failure_is_counted_and_does_not_crash(tmp_path):
    config = make_config(tmp_path)
    camera = FakeCamera(fail=True)
    mailer = FakeMailer()
    cache, store = make_stores(config)

    handle_tick(now=datetime(2026, 7, 16, 12, 0, tzinfo=WARSAW), config=config, camera=camera,
                mailer=mailer, suntimes_cache=cache, day_state_store=store,
                fetch_fn=lambda lat, lon, d: fixed_window(d))

    assert store.load().photos_failed == 1


def test_low_disk_space_alert_fires_once(tmp_path):
    config = make_config(tmp_path)
    config.disk.warn_threshold_mb = 10**9
    camera = FakeCamera()
    mailer = FakeMailer()
    cache, store = make_stores(config)
    fetch_fn = lambda lat, lon, d: fixed_window(d)

    handle_tick(now=datetime(2026, 7, 16, 12, 0, tzinfo=WARSAW), config=config, camera=camera,
                mailer=mailer, suntimes_cache=cache, day_state_store=store, fetch_fn=fetch_fn)
    handle_tick(now=datetime(2026, 7, 16, 12, 10, tzinfo=WARSAW), config=config, camera=camera,
                mailer=mailer, suntimes_cache=cache, day_state_store=store, fetch_fn=fetch_fn)

    disk_alerts = [s for s, _, _ in mailer.sent if "disk" in s.lower()]
    assert len(disk_alerts) == 1
