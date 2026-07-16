from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from lilly_stream.alerts import AlertMailer
from lilly_stream.config import Config, SecretsConfig
from lilly_stream.daystate import DayState, DayStateStore
from lilly_stream.storage import free_space_mb, photo_path
from lilly_stream.suntimes import (
    LOCAL_TZ,
    SuntimesCache,
    SuntimesUnavailableError,
    fetch_twilight,
    get_twilight_window,
    is_daylight,
)

log = logging.getLogger(__name__)


def _summary_email(state: DayState, free_mb: float) -> tuple[str, str]:
    subject = f"Daily summary - {state.date.isoformat()}"
    body = f"Photos taken: {state.photos_taken}\nPhotos failed: {state.photos_failed}\nFree disk space: {free_mb:.0f}MB\n"
    return subject, body


def handle_tick(
    *,
    now: datetime,
    config: Config,
    camera,
    mailer: AlertMailer,
    suntimes_cache: SuntimesCache,
    day_state_store: DayStateStore,
    fetch_fn=fetch_twilight,
) -> None:
    today = now.date()
    stored = day_state_store.load()

    if stored is None:
        state = DayState(date=today)
    elif stored.date != today:
        free_mb = free_space_mb(config.capture.storage_dir)
        subject, body = _summary_email(stored, free_mb)
        mailer.send(subject, body)
        state = DayState(date=today)
    else:
        state = stored

    try:
        window = get_twilight_window(
            config.location.lat,
            config.location.lon,
            today,
            suntimes_cache,
            fetch_fn=fetch_fn,
        )
    except SuntimesUnavailableError as exc:
        log.error("Twilight times unavailable: %s", exc)
        day_state_store.save(state)
        return

    if is_daylight(window, now):
        path = photo_path(config.capture.storage_dir, now)
        try:
            camera.capture(path)
        except Exception as exc:
            log.error("Capture failed: %s", exc)
            state.photos_failed += 1
        else:
            state.photos_taken += 1
            state.last_photo_path = str(path)
            state.last_photo_alert_sent = False
            if not state.first_photo_sent:
                mailer.send(
                    f"First photo of the day - {today.isoformat()}",
                    "First photo of the day captured.",
                    attachments=[path],
                )
                state.first_photo_sent = True
    else:
        if state.last_photo_path is not None and not state.last_photo_alert_sent:
            mailer.send(
                f"Last photo of the day - {today.isoformat()}",
                "Last photo of the day captured.",
                attachments=[Path(state.last_photo_path)],
            )
            state.last_photo_alert_sent = True

    free_mb = free_space_mb(config.capture.storage_dir)
    if free_mb < config.disk.warn_threshold_mb:
        if not state.disk_alert_active:
            mailer.send(
                "Low disk space warning",
                f"Free space is {free_mb:.0f}MB, below threshold of {config.disk.warn_threshold_mb}MB.",
            )
            state.disk_alert_active = True
    else:
        state.disk_alert_active = False

    day_state_store.save(state)


def run(config: Config, secrets: SecretsConfig) -> None:
    from lilly_stream.capture.camera import Camera

    camera = Camera()
    mailer = AlertMailer(secrets.gmail_address, secrets.gmail_app_password, config.alerts.recipient)
    suntimes_cache = SuntimesCache(config.state_dir / "sun_times.json")
    day_state_store = DayStateStore(config.state_dir / "day_state.json")

    try:
        while True:
            handle_tick(
                now=datetime.now(LOCAL_TZ),
                config=config,
                camera=camera,
                mailer=mailer,
                suntimes_cache=suntimes_cache,
                day_state_store=day_state_store,
            )
            time.sleep(config.capture.interval_minutes * 60)
    finally:
        camera.close()
