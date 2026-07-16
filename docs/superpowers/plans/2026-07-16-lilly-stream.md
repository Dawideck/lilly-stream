# lilly-stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Pi Zero W capture daemon that photographs a blooming flower during daylight only (civil twilight, Kolobrzeg, Poland), emails alerts via Gmail, and a cross-platform interactive CLI that assembles a chosen date range of those photos into an MP4/GIF timelapse.

**Architecture:** Single Python package `lilly_stream` (src-layout) with shared library modules (config, storage convention, suntimes, day-state, alerts) and two console-script entry points: `lilly-capture` (24/7 Pi daemon) and `lilly-timelapse` (interactive timelapse builder, runs on Mac or Pi).

**Tech Stack:** Python 3.9+, `pyyaml`, `requests`, `Pillow`, stdlib `smtplib`/`email`/`zoneinfo`/`shutil`, `picamera2` (Pi-only, lazily imported), external `ffmpeg` binary (not a pip dependency), `pytest` for tests.

## Global Constraints

- Target Python 3.9+ (Raspberry Pi OS default). Use `from __future__ import annotations` in every module to allow `X | None` / `list[X]` syntax.
- Photo storage convention is exact and shared: `<storage_dir>/YYYY-MM-DD/HHMMSS.jpg`. Both the capture daemon and the timelapse builder must use `lilly_stream.storage.photo_path` / `parse_timestamp` — never construct these paths inline elsewhere.
- Daylight window = civil twilight begin/end (not sunrise/sunset) from the sunrise-sunset.org API for lat `54.1755`, lon `15.5836` (Kolobrzeg, PL), converted to `Europe/Warsaw` local time. On fetch failure, reuse the most recently cached window; only raise if no cache exists at all.
- No automatic deletion of photos, ever, under any disk-space condition.
- Gmail credentials (`gmail_address`, `gmail_app_password`) load only from a gitignored `secrets.yaml` or `LILLY_GMAIL_ADDRESS`/`LILLY_GMAIL_APP_PASSWORD` env vars — never from `config.yaml`, never committed.
- `picamera2` is imported lazily, only inside `lilly_stream/capture/camera.py`, so the timelapse builder and the full test suite run without it installed (it's a Raspberry Pi OS system package, not a pip dependency of this project).
- `ffmpeg` is an external binary on `PATH`, not a Python dependency; MP4-building tests skip gracefully if it's absent.
- Default capture interval is 10 minutes (`capture.interval_minutes` in config.yaml), user-tunable.

---

## Task 1: Project scaffolding + config loader

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `config.yaml`
- Create: `secrets.yaml.example`
- Create: `src/lilly_stream/__init__.py`
- Create: `src/lilly_stream/config.py`
- Create: `tests/__init__.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` (dataclass: `location: LocationConfig`, `capture: CaptureConfig`, `disk: DiskConfig`, `alerts: AlertsConfig`, `state_dir: Path`), `SecretsConfig` (dataclass: `gmail_address: str`, `gmail_app_password: str`), `ConfigError(Exception)`, `load_config(config_path: Path) -> Config`, `load_secrets(secrets_path: Path) -> SecretsConfig`.

- [ ] **Step 1: Create project scaffolding files**

`pyproject.toml`:
```toml
[project]
name = "lilly-stream"
version = "0.1.0"
description = "Flower-blooming timelapse: Pi camera capture daemon + timelapse builder"
requires-python = ">=3.9"
dependencies = [
    "pyyaml>=6.0",
    "requests>=2.31",
    "Pillow>=10.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[project.scripts]
lilly-capture = "lilly_stream.capture.cli:main"
lilly-timelapse = "lilly_stream.timelapse.cli:main"

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
venv/
*.egg-info/
photos/
state/
secrets.yaml
*.mp4
*.gif
```

`config.yaml`:
```yaml
location:
  name: "Kolobrzeg, PL"
  lat: 54.1755
  lon: 15.5836
capture:
  interval_minutes: 10
  storage_dir: "./photos"
disk:
  warn_threshold_mb: 500
alerts:
  recipient: "you@example.com"
```

`secrets.yaml.example`:
```yaml
gmail_address: "your-account@gmail.com"
gmail_app_password: "xxxx xxxx xxxx xxxx"
```

`src/lilly_stream/__init__.py`: empty file.

`tests/__init__.py`: empty file.

- [ ] **Step 2: Create a virtualenv and install the package in editable mode**

Run:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```
Expected: install succeeds, `lilly-capture` and `lilly-timelapse` commands appear on `PATH` (they'll fail to run correctly until later tasks — that's expected here).

- [ ] **Step 3: Write the failing test for config loading**

`tests/test_config.py`:
```python
from pathlib import Path

import pytest

from lilly_stream.config import ConfigError, load_config, load_secrets


def test_load_config_reads_all_sections(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
location:
  name: "Kolobrzeg, PL"
  lat: 54.1755
  lon: 15.5836
capture:
  interval_minutes: 10
  storage_dir: "./photos"
disk:
  warn_threshold_mb: 500
alerts:
  recipient: "you@example.com"
"""
    )
    config = load_config(config_path)
    assert config.location.name == "Kolobrzeg, PL"
    assert config.location.lat == 54.1755
    assert config.capture.interval_minutes == 10
    assert config.capture.storage_dir == Path("./photos")
    assert config.disk.warn_threshold_mb == 500
    assert config.alerts.recipient == "you@example.com"
    assert config.state_dir == Path("state")


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does_not_exist.yaml")


def test_load_secrets_from_file(tmp_path):
    secrets_path = tmp_path / "secrets.yaml"
    secrets_path.write_text(
        'gmail_address: "me@gmail.com"\ngmail_app_password: "abcd efgh ijkl mnop"\n'
    )
    secrets = load_secrets(secrets_path)
    assert secrets.gmail_address == "me@gmail.com"
    assert secrets.gmail_app_password == "abcd efgh ijkl mnop"


def test_load_secrets_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LILLY_GMAIL_ADDRESS", "env@gmail.com")
    monkeypatch.setenv("LILLY_GMAIL_APP_PASSWORD", "envpass")
    secrets = load_secrets(tmp_path / "does_not_exist.yaml")
    assert secrets.gmail_address == "env@gmail.com"
    assert secrets.gmail_app_password == "envpass"


def test_load_secrets_missing_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("LILLY_GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("LILLY_GMAIL_APP_PASSWORD", raising=False)
    with pytest.raises(ConfigError):
        load_secrets(tmp_path / "does_not_exist.yaml")
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lilly_stream.config'`

- [ ] **Step 5: Implement the config loader**

`src/lilly_stream/config.py`:
```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


class ConfigError(Exception):
    """Raised when config or secrets are missing or invalid."""


@dataclass
class LocationConfig:
    name: str
    lat: float
    lon: float


@dataclass
class CaptureConfig:
    interval_minutes: int
    storage_dir: Path


@dataclass
class DiskConfig:
    warn_threshold_mb: int


@dataclass
class AlertsConfig:
    recipient: str


@dataclass
class SecretsConfig:
    gmail_address: str
    gmail_app_password: str


@dataclass
class Config:
    location: LocationConfig
    capture: CaptureConfig
    disk: DiskConfig
    alerts: AlertsConfig
    state_dir: Path


def load_config(config_path: Path) -> Config:
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")
    raw = yaml.safe_load(config_path.read_text())

    location = LocationConfig(**raw["location"])
    capture = CaptureConfig(
        interval_minutes=raw["capture"]["interval_minutes"],
        storage_dir=Path(raw["capture"]["storage_dir"]),
    )
    disk = DiskConfig(**raw["disk"])
    alerts = AlertsConfig(**raw["alerts"])

    return Config(
        location=location,
        capture=capture,
        disk=disk,
        alerts=alerts,
        state_dir=Path("state"),
    )


def load_secrets(secrets_path: Path) -> SecretsConfig:
    if secrets_path.exists():
        raw = yaml.safe_load(secrets_path.read_text())
        return SecretsConfig(
            gmail_address=raw["gmail_address"],
            gmail_app_password=raw["gmail_app_password"],
        )

    gmail_address = os.environ.get("LILLY_GMAIL_ADDRESS")
    gmail_app_password = os.environ.get("LILLY_GMAIL_APP_PASSWORD")
    if not gmail_address or not gmail_app_password:
        raise ConfigError(
            "Gmail credentials not found: provide secrets.yaml or set "
            "LILLY_GMAIL_ADDRESS / LILLY_GMAIL_APP_PASSWORD"
        )
    return SecretsConfig(gmail_address=gmail_address, gmail_app_password=gmail_app_password)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore config.yaml secrets.yaml.example src/lilly_stream/__init__.py src/lilly_stream/config.py tests/__init__.py tests/test_config.py
git commit -m "feat: add project scaffolding and config loader"
```

---

## Task 2: Storage module (photo path convention)

**Files:**
- Create: `src/lilly_stream/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces: `photo_path(storage_dir: Path, timestamp: datetime) -> Path`, `parse_timestamp(path: Path) -> datetime`, `list_photos(storage_dir: Path) -> list[Path]`, `available_dates(storage_dir: Path) -> dict[str, int]`, `free_space_mb(path: Path) -> float`.

- [ ] **Step 1: Write the failing tests**

`tests/test_storage.py`:
```python
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


def test_available_dates_counts_per_day(tmp_path):
    (tmp_path / "2026-07-16").mkdir()
    (tmp_path / "2026-07-16" / "090000.jpg").write_bytes(b"")
    (tmp_path / "2026-07-16" / "100000.jpg").write_bytes(b"")

    assert available_dates(tmp_path) == {"2026-07-16": 2}


def test_free_space_mb_returns_positive_number(tmp_path):
    assert free_space_mb(tmp_path) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lilly_stream.storage'`

- [ ] **Step 3: Implement the storage module**

`src/lilly_stream/storage.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/lilly_stream/storage.py tests/test_storage.py
git commit -m "feat: add photo storage path convention and scanning"
```

---

## Task 3: Suntimes module (civil twilight fetch + cache)

**Files:**
- Create: `src/lilly_stream/suntimes.py`
- Test: `tests/test_suntimes.py`

**Interfaces:**
- Consumes: `requests` (pip dependency, already in `pyproject.toml`).
- Produces: `TwilightWindow` (dataclass: `date: date`, `civil_dawn: datetime`, `civil_dusk: datetime`), `SuntimesUnavailableError(Exception)`, `SuntimesCache` (class: `__init__(cache_path: Path)`, `load() -> TwilightWindow | None`, `save(window: TwilightWindow) -> None`), `fetch_twilight(lat: float, lon: float, for_date: date) -> TwilightWindow`, `get_twilight_window(lat: float, lon: float, for_date: date, cache: SuntimesCache, fetch_fn=fetch_twilight) -> TwilightWindow`, `is_daylight(window: TwilightWindow, now: datetime) -> bool`, `LOCAL_TZ` (`ZoneInfo("Europe/Warsaw")`).

- [ ] **Step 1: Write the failing tests**

`tests/test_suntimes.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_suntimes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lilly_stream.suntimes'`

- [ ] **Step 3: Implement the suntimes module**

`src/lilly_stream/suntimes.py`:
```python
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

LOCAL_TZ = ZoneInfo("Europe/Warsaw")
API_URL = "https://api.sunrise-sunset.org/json"


class SuntimesUnavailableError(Exception):
    """Raised when today's twilight times can't be fetched and no cache exists."""


@dataclass
class TwilightWindow:
    date: date
    civil_dawn: datetime
    civil_dusk: datetime

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "civil_dawn": self.civil_dawn.isoformat(),
            "civil_dusk": self.civil_dusk.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict) -> TwilightWindow:
        return TwilightWindow(
            date=date.fromisoformat(data["date"]),
            civil_dawn=datetime.fromisoformat(data["civil_dawn"]),
            civil_dusk=datetime.fromisoformat(data["civil_dusk"]),
        )


def fetch_twilight(lat: float, lon: float, for_date: date) -> TwilightWindow:
    response = requests.get(
        API_URL,
        params={"lat": lat, "lng": lon, "date": for_date.isoformat(), "formatted": 0},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "OK":
        raise SuntimesUnavailableError(f"API returned status {payload.get('status')}")
    results = payload["results"]
    dawn_utc = datetime.fromisoformat(results["civil_twilight_begin"])
    dusk_utc = datetime.fromisoformat(results["civil_twilight_end"])
    return TwilightWindow(
        date=for_date,
        civil_dawn=dawn_utc.astimezone(LOCAL_TZ),
        civil_dusk=dusk_utc.astimezone(LOCAL_TZ),
    )


class SuntimesCache:
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path

    def load(self) -> TwilightWindow | None:
        if not self.cache_path.exists():
            return None
        return TwilightWindow.from_dict(json.loads(self.cache_path.read_text()))

    def save(self, window: TwilightWindow) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(window.to_dict()))


def get_twilight_window(
    lat: float,
    lon: float,
    for_date: date,
    cache: SuntimesCache,
    fetch_fn=fetch_twilight,
) -> TwilightWindow:
    try:
        window = fetch_fn(lat, lon, for_date)
    except Exception:
        cached = cache.load()
        if cached is not None:
            return cached
        raise SuntimesUnavailableError(
            f"Could not fetch twilight times for {for_date} and no cache exists"
        )
    cache.save(window)
    return window


def is_daylight(window: TwilightWindow, now: datetime) -> bool:
    return window.civil_dawn <= now <= window.civil_dusk
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_suntimes.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/lilly_stream/suntimes.py tests/test_suntimes.py
git commit -m "feat: add civil twilight fetch, cache, and daylight gating"
```

---

## Task 4: Day-state module

**Files:**
- Create: `src/lilly_stream/daystate.py`
- Test: `tests/test_daystate.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces: `DayState` (dataclass: `date: date`, `photos_taken: int = 0`, `photos_failed: int = 0`, `first_photo_sent: bool = False`, `last_photo_path: str | None = None`, `last_photo_alert_sent: bool = False`, `disk_alert_active: bool = False`), `DayStateStore` (class: `__init__(path: Path)`, `load() -> DayState | None`, `save(state: DayState) -> None`).

- [ ] **Step 1: Write the failing tests**

`tests/test_daystate.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_daystate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lilly_stream.daystate'`

- [ ] **Step 3: Implement the day-state module**

`src/lilly_stream/daystate.py`:
```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path


@dataclass
class DayState:
    date: date
    photos_taken: int = 0
    photos_failed: int = 0
    first_photo_sent: bool = False
    last_photo_path: str | None = None
    last_photo_alert_sent: bool = False
    disk_alert_active: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["date"] = self.date.isoformat()
        return data

    @staticmethod
    def from_dict(data: dict) -> DayState:
        data = dict(data)
        data["date"] = date.fromisoformat(data["date"])
        return DayState(**data)


class DayStateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> DayState | None:
        if not self.path.exists():
            return None
        return DayState.from_dict(json.loads(self.path.read_text()))

    def save(self, state: DayState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state.to_dict()))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_daystate.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/lilly_stream/daystate.py tests/test_daystate.py
git commit -m "feat: add per-day capture state persistence"
```

---

## Task 5: Alerts module (Gmail email)

**Files:**
- Create: `src/lilly_stream/alerts.py`
- Test: `tests/test_alerts.py`

**Interfaces:**
- Consumes: nothing (stdlib `smtplib`/`email` only).
- Produces: `AlertMailer` (class: `__init__(gmail_address: str, gmail_app_password: str, recipient: str)`, `send(subject: str, body: str, attachments: list[Path] | None = None) -> None`).

- [ ] **Step 1: Write the failing tests**

`tests/test_alerts.py`:
```python
from unittest.mock import MagicMock, patch

from lilly_stream.alerts import AlertMailer


@patch("lilly_stream.alerts.smtplib.SMTP_SSL")
def test_send_logs_in_and_sends_message(mock_smtp_ssl):
    smtp_instance = MagicMock()
    mock_smtp_ssl.return_value.__enter__.return_value = smtp_instance

    mailer = AlertMailer("me@gmail.com", "app-password", "recipient@example.com")
    mailer.send("Subject", "Body text")

    mock_smtp_ssl.assert_called_once_with("smtp.gmail.com", 465)
    smtp_instance.login.assert_called_once_with("me@gmail.com", "app-password")
    assert smtp_instance.send_message.call_count == 1
    sent_msg = smtp_instance.send_message.call_args[0][0]
    assert sent_msg["Subject"] == "Subject"
    assert sent_msg["To"] == "recipient@example.com"


@patch("lilly_stream.alerts.smtplib.SMTP_SSL")
def test_send_with_attachment(mock_smtp_ssl, tmp_path):
    smtp_instance = MagicMock()
    mock_smtp_ssl.return_value.__enter__.return_value = smtp_instance

    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake-jpeg-bytes")

    mailer = AlertMailer("me@gmail.com", "app-password", "recipient@example.com")
    mailer.send("Subject", "Body", attachments=[photo])

    sent_msg = smtp_instance.send_message.call_args[0][0]
    attachments = list(sent_msg.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "photo.jpg"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_alerts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lilly_stream.alerts'`

- [ ] **Step 3: Implement the alerts module**

`src/lilly_stream/alerts.py`:
```python
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path


class AlertMailer:
    def __init__(self, gmail_address: str, gmail_app_password: str, recipient: str):
        self.gmail_address = gmail_address
        self.gmail_app_password = gmail_app_password
        self.recipient = recipient

    def send(self, subject: str, body: str, attachments: list[Path] | None = None) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.gmail_address
        message["To"] = self.recipient
        message.set_content(body)

        for attachment in attachments or []:
            message.add_attachment(
                attachment.read_bytes(),
                maintype="image",
                subtype="jpeg",
                filename=attachment.name,
            )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(self.gmail_address, self.gmail_app_password)
            smtp.send_message(message)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_alerts.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/lilly_stream/alerts.py tests/test_alerts.py
git commit -m "feat: add Gmail SMTP alert mailer"
```

---

## Task 6: Camera module (picamera2 wrapper)

**Files:**
- Create: `src/lilly_stream/capture/__init__.py`
- Create: `src/lilly_stream/capture/camera.py`

**Interfaces:**
- Consumes: `picamera2.Picamera2` (Pi-only system package, imported lazily inside `Camera.__init__`).
- Produces: `CameraError(Exception)`, `Camera` (class: `__init__()`, `capture(path: Path) -> None`, `close() -> None`).

No automated test: `picamera2` requires actual Raspberry Pi camera hardware and is not installable on macOS or in CI. This module is verified manually in Task 8 by running the daemon on the real Pi.

- [ ] **Step 1: Implement the camera module**

`src/lilly_stream/capture/__init__.py`: empty file.

`src/lilly_stream/capture/camera.py`:
```python
from __future__ import annotations

from pathlib import Path


class CameraError(Exception):
    """Raised when a photo capture fails."""


class Camera:
    def __init__(self):
        from picamera2 import Picamera2

        self._picam = Picamera2()
        self._picam.configure(self._picam.create_still_configuration())
        self._picam.start()

    def capture(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._picam.capture_file(str(path))
        except Exception as exc:
            raise CameraError(f"Failed to capture photo to {path}: {exc}") from exc

    def close(self) -> None:
        self._picam.stop()
```

- [ ] **Step 2: Verify the rest of the test suite still passes without picamera2 installed**

Run: `pytest -v`
Expected: PASS (all tests from Tasks 1-5 still pass; `capture/camera.py` is not imported by any test, so its `picamera2` import is never triggered)

- [ ] **Step 3: Commit**

```bash
git add src/lilly_stream/capture/__init__.py src/lilly_stream/capture/camera.py
git commit -m "feat: add picamera2 capture wrapper"
```

---

## Task 7: Capture daemon tick logic

**Files:**
- Create: `src/lilly_stream/capture/daemon.py`
- Test: `tests/test_daemon.py`

**Interfaces:**
- Consumes: `Config`, `SecretsConfig` from `lilly_stream.config`; `photo_path`, `free_space_mb` from `lilly_stream.storage`; `SuntimesCache`, `get_twilight_window`, `is_daylight`, `fetch_twilight`, `SuntimesUnavailableError`, `LOCAL_TZ` from `lilly_stream.suntimes`; `DayState`, `DayStateStore` from `lilly_stream.daystate`; `AlertMailer` from `lilly_stream.alerts`; `Camera` from `lilly_stream.capture.camera` (imported lazily inside `run`, not at module top).
- Produces: `handle_tick(*, now: datetime, config: Config, camera, mailer: AlertMailer, suntimes_cache: SuntimesCache, day_state_store: DayStateStore, fetch_fn=fetch_twilight) -> None`, `run(config: Config, secrets: SecretsConfig) -> None`. `camera` parameter only needs a `.capture(path: Path) -> None` method (duck-typed, so tests can pass a fake).

- [ ] **Step 1: Write the failing tests**

`tests/test_daemon.py`:
```python
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

    summaries = [s for s, _, _ in mailer.sent if "summary" in s.lower()]
    assert len(summaries) == 1
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_daemon.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lilly_stream.capture.daemon'`

- [ ] **Step 3: Implement the daemon tick logic**

`src/lilly_stream/capture/daemon.py`:
```python
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


def _summary_email(state: DayState) -> tuple[str, str]:
    subject = f"Daily summary - {state.date.isoformat()}"
    body = f"Photos taken: {state.photos_taken}\nPhotos failed: {state.photos_failed}\n"
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
        subject, body = _summary_email(stored)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_daemon.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests from Tasks 1-7)

- [ ] **Step 6: Commit**

```bash
git add src/lilly_stream/capture/daemon.py tests/test_daemon.py
git commit -m "feat: add capture daemon tick logic with light gating and alerting"
```

---

## Task 8: Capture CLI entry point + systemd deployment

**Files:**
- Create: `src/lilly_stream/capture/cli.py`
- Create: `deploy/lilly-capture.service`
- Create: `SETUP.md`

**Interfaces:**
- Consumes: `load_config`, `load_secrets` from `lilly_stream.config`; `run` from `lilly_stream.capture.daemon`.
- Produces: `main() -> None` (the `lilly-capture` console-script entry point).

No automated test: this is the process entry point wiring real hardware (camera) and real network (SMTP, sunrise API). Verified manually in Step 3 below, on the actual Pi.

- [ ] **Step 1: Implement the capture CLI**

`src/lilly_stream/capture/cli.py`:
```python
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from lilly_stream.capture.daemon import run
from lilly_stream.config import load_config, load_secrets


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the lilly-stream capture daemon.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--secrets", type=Path, default=Path("secrets.yaml"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    config = load_config(args.config)
    secrets = load_secrets(args.secrets)
    run(config, secrets)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add the systemd unit and setup docs**

`deploy/lilly-capture.service`:
```ini
[Unit]
Description=lilly-stream capture daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/pi/lilly-stream
ExecStart=/home/pi/lilly-stream/.venv/bin/lilly-capture
Restart=on-failure
RestartSec=10
User=pi

[Install]
WantedBy=multi-user.target
```

`SETUP.md`:
```markdown
# Setup

## Raspberry Pi (capture daemon)

1. Flash Raspberry Pi OS (Bullseye or later) with the camera interface enabled via `raspi-config`.
2. Install system packages: `sudo apt update && sudo apt install -y python3-picamera2 python3-venv git`.
3. Clone this repo to `/home/pi/lilly-stream`.
4. Create a venv that can see the system `picamera2` package:
   `python3 -m venv --system-site-packages /home/pi/lilly-stream/.venv`
5. `source .venv/bin/activate && pip install -e .` (no `[dev]` needed on the Pi).
6. Copy `secrets.yaml.example` to `secrets.yaml` and fill in a Gmail address and a
   [Google App Password](https://myaccount.google.com/apppasswords) (not your normal
   password — Gmail rejects plain SMTP login with account passwords).
7. Edit `config.yaml` if you want a different capture interval, disk threshold, or
   alert recipient.
8. Install and enable the systemd service:
   ```bash
   sudo cp deploy/lilly-capture.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now lilly-capture
   ```
9. Verify it's running: `sudo systemctl status lilly-capture` and `journalctl -u lilly-capture -f`.
10. Confirm end-to-end: wait for the next daylight tick and check that a photo appears
    under `photos/<today>/` and a "First photo of the day" email arrives.

## macOS / any machine (timelapse builder only)

1. Install `ffmpeg`: `brew install ffmpeg`.
2. `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.
3. Copy photos from the Pi (e.g. `scp -r pi@<pi-host>:/home/pi/lilly-stream/photos ./photos`).
4. Run `lilly-timelapse` and follow the interactive prompts.
```

- [ ] **Step 3: Manual verification on the Pi**

This step has no automated pytest command — it is hardware verification. After
completing `SETUP.md` steps 1-9 on the actual Pi Zero W:
- Confirm `sudo systemctl status lilly-capture` shows `active (running)`.
- During a daylight period, confirm a new file appears under `photos/<today>/` within
  one capture interval.
- Confirm a "First photo of the day" email with a photo attachment arrives in the
  configured recipient's inbox.
- Stop the service (`sudo systemctl stop lilly-capture`), restart it
  (`sudo systemctl start lilly-capture`), and confirm the next capture does **not**
  re-send a "First photo of the day" email for the same day (state persistence works).

- [ ] **Step 4: Commit**

```bash
git add src/lilly_stream/capture/cli.py deploy/lilly-capture.service SETUP.md
git commit -m "feat: add capture daemon CLI entry point and Pi deployment docs"
```

---

## Task 9: Timelapse selection module

**Files:**
- Create: `src/lilly_stream/timelapse/__init__.py`
- Create: `src/lilly_stream/timelapse/selection.py`
- Test: `tests/test_selection.py`

**Interfaces:**
- Consumes: `list_photos`, `parse_timestamp` from `lilly_stream.storage`.
- Produces: `PhotoEntry` (dataclass: `path: Path`, `timestamp: datetime`), `list_entries_in_range(storage_dir: Path, start_date: date, end_date: date) -> list[PhotoEntry]`, `thin_every_nth(entries: list[PhotoEntry], n: int) -> list[PhotoEntry]`, `thin_to_target_count(entries: list[PhotoEntry], target: int) -> list[PhotoEntry]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_selection.py`:
```python
from datetime import date, datetime
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
    entries = [PhotoEntry(path=Path(f"{i}.jpg"), timestamp=datetime(2026, 7, 15, 9, i)) for i in range(100)]
    result = thin_to_target_count(entries, 10)
    assert 8 <= len(result) <= 12


def test_thin_to_target_count_returns_all_when_fewer_than_target():
    entries = [PhotoEntry(path=Path(f"{i}.jpg"), timestamp=datetime(2026, 7, 15, 9, i)) for i in range(5)]
    assert thin_to_target_count(entries, 10) == entries
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_selection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lilly_stream.timelapse'`

- [ ] **Step 3: Implement the selection module**

`src/lilly_stream/timelapse/__init__.py`: empty file.

`src/lilly_stream/timelapse/selection.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_selection.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/lilly_stream/timelapse/__init__.py src/lilly_stream/timelapse/selection.py tests/test_selection.py
git commit -m "feat: add timelapse date-range and frame-thinning selection"
```

---

## Task 10: Timelapse build module (ffmpeg + Pillow)

**Files:**
- Create: `src/lilly_stream/timelapse/build.py`
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `PhotoEntry` from `lilly_stream.timelapse.selection`; external `ffmpeg` binary (subprocess); `Pillow` (`PIL.Image`).
- Produces: `build_mp4(entries: list[PhotoEntry], output_path: Path, fps: int) -> None`, `build_gif(entries: list[PhotoEntry], output_path: Path, fps: int) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_build.py`:
```python
import shutil

import pytest
from PIL import Image

from lilly_stream.timelapse.build import build_gif, build_mp4
from lilly_stream.timelapse.selection import PhotoEntry


def make_fake_photos(tmp_path, count):
    entries = []
    for i in range(count):
        path = tmp_path / f"frame_{i}.jpg"
        Image.new("RGB", (16, 16), color=(i * 10 % 255, 0, 0)).save(path)
        entries.append(PhotoEntry(path=path, timestamp=None))
    return entries


def test_build_gif_creates_file(tmp_path):
    entries = make_fake_photos(tmp_path, 3)
    output = tmp_path / "out.gif"
    build_gif(entries, output, fps=10)
    assert output.exists()
    assert output.stat().st_size > 0


def test_build_gif_raises_on_empty_entries(tmp_path):
    with pytest.raises(ValueError):
        build_gif([], tmp_path / "out.gif", fps=10)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_build_mp4_creates_file(tmp_path):
    entries = make_fake_photos(tmp_path, 3)
    output = tmp_path / "out.mp4"
    build_mp4(entries, output, fps=10)
    assert output.exists()
    assert output.stat().st_size > 0


def test_build_mp4_raises_on_empty_entries(tmp_path):
    with pytest.raises(ValueError):
        build_mp4([], tmp_path / "out.mp4", fps=10)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_build.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lilly_stream.timelapse.build'`

- [ ] **Step 3: Implement the build module**

`src/lilly_stream/timelapse/build.py`:
```python
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from lilly_stream.timelapse.selection import PhotoEntry


def build_mp4(entries: list[PhotoEntry], output_path: Path, fps: int) -> None:
    if not entries:
        raise ValueError("No entries to build a video from")

    frame_duration = 1 / fps
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for entry in entries:
            f.write(f"file '{entry.path.resolve()}'\n")
            f.write(f"duration {frame_duration}\n")
        f.write(f"file '{entries[-1].path.resolve()}'\n")
        filelist_path = f.name

    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", filelist_path,
            "-vsync", "vfr",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def build_gif(entries: list[PhotoEntry], output_path: Path, fps: int) -> None:
    if not entries:
        raise ValueError("No entries to build a GIF from")

    from PIL import Image

    frames = [Image.open(entry.path) for entry in entries]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / fps),
        loop=0,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_build.py -v`
Expected: PASS (4 tests; the `test_build_mp4_creates_file` test runs only if `ffmpeg` is on `PATH`, otherwise it's skipped)

- [ ] **Step 5: Commit**

```bash
git add src/lilly_stream/timelapse/build.py tests/test_build.py
git commit -m "feat: add MP4/GIF timelapse assembly via ffmpeg and Pillow"
```

---

## Task 11: Timelapse interactive menu + CLI entry point

**Files:**
- Create: `src/lilly_stream/timelapse/menu.py`
- Create: `src/lilly_stream/timelapse/cli.py`
- Test: `tests/test_menu.py`

**Interfaces:**
- Consumes: `thin_every_nth`, `thin_to_target_count`, `PhotoEntry` from `lilly_stream.timelapse.selection`; `list_entries_in_range` from `lilly_stream.timelapse.selection`; `build_mp4`, `build_gif` from `lilly_stream.timelapse.build`; `available_dates` from `lilly_stream.storage`; `load_config` from `lilly_stream.config`.
- Produces (menu.py): `prompt_choice(prompt: str, options: list[str], input_fn=input) -> int`, `prompt_int(prompt: str, minimum: int = 1, input_fn=input) -> int`, `prompt_text(prompt: str, default: str, input_fn=input) -> str`, `prompt_yes_no(prompt: str, input_fn=input) -> bool`, `select_date_range(available: dict[str, int], input_fn=input) -> tuple[date, date]`, `select_thinning(entries: list[PhotoEntry], fps: int, input_fn=input) -> list[PhotoEntry]`, `select_fps(input_fn=input) -> int`, `select_format(input_fn=input) -> str` (`"mp4"|"gif"|"both"`).
- Produces (cli.py): `main() -> None` (the `lilly-timelapse` console-script entry point).

- [ ] **Step 1: Write the failing tests for the menu primitives**

`tests/test_menu.py`:
```python
from datetime import date, datetime
from pathlib import Path

from lilly_stream.timelapse.menu import (
    prompt_choice,
    prompt_int,
    prompt_text,
    prompt_yes_no,
    select_date_range,
    select_fps,
    select_format,
    select_thinning,
)
from lilly_stream.timelapse.selection import PhotoEntry


def fake_input(responses):
    it = iter(responses)
    return lambda prompt="": next(it)


def test_prompt_choice_returns_valid_index():
    assert prompt_choice("Pick:", ["a", "b", "c"], input_fn=fake_input(["2"])) == 1


def test_prompt_choice_reprompts_on_invalid():
    assert prompt_choice("Pick:", ["a", "b"], input_fn=fake_input(["9", "abc", "1"])) == 0


def test_prompt_int_reprompts_below_minimum():
    assert prompt_int("N:", minimum=5, input_fn=fake_input(["2", "5"])) == 5


def test_prompt_text_returns_default_on_blank():
    assert prompt_text("Name", "default.mp4", input_fn=fake_input([""])) == "default.mp4"


def test_prompt_text_returns_input_when_given():
    assert prompt_text("Name", "default.mp4", input_fn=fake_input(["custom.mp4"])) == "custom.mp4"


def test_prompt_yes_no_accepts_y_and_n():
    assert prompt_yes_no("Continue?", input_fn=fake_input(["y"])) is True
    assert prompt_yes_no("Continue?", input_fn=fake_input(["n"])) is False


def test_select_date_range_picks_start_and_end():
    available = {"2026-07-14": 5, "2026-07-15": 6, "2026-07-16": 4}
    start, end = select_date_range(available, input_fn=fake_input(["2", "1"]))
    assert start == date(2026, 7, 15)
    assert end == date(2026, 7, 15)


def test_select_fps_preset():
    assert select_fps(input_fn=fake_input(["2"])) == 24


def test_select_fps_custom():
    assert select_fps(input_fn=fake_input(["4", "18"])) == 18


def test_select_format_returns_expected_strings():
    assert select_format(input_fn=fake_input(["1"])) == "mp4"
    assert select_format(input_fn=fake_input(["2"])) == "gif"
    assert select_format(input_fn=fake_input(["3"])) == "both"


def make_entries(n):
    return [PhotoEntry(path=Path(f"{i}.jpg"), timestamp=datetime(2026, 7, 15, 9, 0)) for i in range(n)]


def test_select_thinning_include_all():
    entries = make_entries(10)
    assert select_thinning(entries, fps=24, input_fn=fake_input(["1"])) == entries


def test_select_thinning_every_nth():
    entries = make_entries(10)
    result = select_thinning(entries, fps=24, input_fn=fake_input(["2", "3"]))
    assert len(result) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_menu.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lilly_stream.timelapse.menu'`

- [ ] **Step 3: Implement the menu module**

`src/lilly_stream/timelapse/menu.py`:
```python
from __future__ import annotations

from datetime import date

from lilly_stream.timelapse.selection import PhotoEntry, thin_every_nth, thin_to_target_count


def prompt_choice(prompt: str, options: list[str], input_fn=input) -> int:
    while True:
        print(prompt)
        for i, option in enumerate(options, start=1):
            print(f"  {i}) {option}")
        raw = input_fn("> ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(f"Please enter a number between 1 and {len(options)}.")


def prompt_int(prompt: str, minimum: int = 1, input_fn=input) -> int:
    while True:
        raw = input_fn(f"{prompt} ").strip()
        if raw.isdigit() and int(raw) >= minimum:
            return int(raw)
        print(f"Please enter a number >= {minimum}.")


def prompt_text(prompt: str, default: str, input_fn=input) -> str:
    raw = input_fn(f"{prompt} [{default}]: ").strip()
    return raw if raw else default


def prompt_yes_no(prompt: str, input_fn=input) -> bool:
    while True:
        raw = input_fn(f"{prompt} [y/n] ").strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Please answer y or n.")


def select_date_range(available: dict[str, int], input_fn=input) -> tuple[date, date]:
    dates = list(available.keys())
    labels = [f"{d} ({available[d]} photos)" for d in dates]

    start_idx = prompt_choice("Select start date:", labels, input_fn)
    end_dates = dates[start_idx:]
    end_labels = labels[start_idx:]
    end_idx = prompt_choice("Select end date:", end_labels, input_fn)

    return date.fromisoformat(dates[start_idx]), date.fromisoformat(end_dates[end_idx])


def select_thinning(entries: list[PhotoEntry], fps: int, input_fn=input) -> list[PhotoEntry]:
    choice = prompt_choice(
        "How many photos should be included?",
        ["Include every photo in range", "Every Nth photo", "Target ~N total frames"],
        input_fn,
    )
    if choice == 0:
        return entries
    if choice == 1:
        n = prompt_int("Include every Nth photo (N):", minimum=1, input_fn=input_fn)
        return thin_every_nth(entries, n)
    target = prompt_int("Target total frame count:", minimum=1, input_fn=input_fn)
    return thin_to_target_count(entries, target)


def select_fps(input_fn=input) -> int:
    choice = prompt_choice("Choose frame rate:", ["12 fps", "24 fps", "30 fps", "Custom"], input_fn)
    presets = [12, 24, 30]
    if choice < 3:
        return presets[choice]
    return prompt_int("Enter custom fps:", minimum=1, input_fn=input_fn)


def select_format(input_fn=input) -> str:
    choice = prompt_choice("Choose output format:", ["MP4", "GIF", "Both"], input_fn)
    return ["mp4", "gif", "both"][choice]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_menu.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Implement the timelapse CLI entry point**

`src/lilly_stream/timelapse/cli.py`:
```python
from __future__ import annotations

from pathlib import Path

from lilly_stream.config import load_config
from lilly_stream.storage import available_dates
from lilly_stream.timelapse.build import build_gif, build_mp4
from lilly_stream.timelapse.menu import (
    prompt_text,
    prompt_yes_no,
    select_date_range,
    select_fps,
    select_format,
    select_thinning,
)
from lilly_stream.timelapse.selection import list_entries_in_range


def main() -> None:
    config = load_config(Path("config.yaml"))
    dates = available_dates(config.capture.storage_dir)
    if not dates:
        print("No photos found in storage directory.")
        return

    while True:
        start, end = select_date_range(dates)
        entries = list_entries_in_range(config.capture.storage_dir, start, end)
        if entries:
            break
        print(f"No photos found between {start} and {end}. Please pick a different range.")

    fps = select_fps()
    entries = select_thinning(entries, fps)
    fmt = select_format()

    default_ext = "gif" if fmt == "gif" else "mp4"
    default_name = f"bloom_{start}_to_{end}.{default_ext}"
    filename = prompt_text("Output filename", default_name)

    duration_sec = len(entries) / fps
    print(
        f"\nDate range: {start} to {end}\n"
        f"Frames: {len(entries)}\n"
        f"FPS: {fps}\n"
        f"Estimated duration: {duration_sec:.1f}s\n"
        f"Format: {fmt}\n"
        f"Output: {filename}\n"
    )
    if not prompt_yes_no("Build timelapse with these settings?"):
        print("Cancelled.")
        return

    output_path = Path(filename)
    if fmt in ("mp4", "both"):
        mp4_path = output_path if fmt == "mp4" else output_path.with_suffix(".mp4")
        build_mp4(entries, mp4_path, fps)
        print(f"Wrote {mp4_path}")
    if fmt in ("gif", "both"):
        gif_path = output_path if fmt == "gif" else output_path.with_suffix(".gif")
        build_gif(entries, gif_path, fps)
        print(f"Wrote {gif_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Manual verification of the full interactive flow**

No automated test for `main()` itself (it's pure interactive I/O orchestration of
already-tested pieces). Verify manually:
```bash
mkdir -p photos/2026-07-15 photos/2026-07-16
python3 -c "from PIL import Image; [Image.new('RGB', (64,64)).save(f'photos/2026-07-15/{h:02d}0000.jpg') for h in range(9, 18)]"
python3 -c "from PIL import Image; [Image.new('RGB', (64,64)).save(f'photos/2026-07-16/{h:02d}0000.jpg') for h in range(9, 18)]"
lilly-timelapse
```
Expected: the numbered menus appear in order (start date, end date, thinning, fps,
format, filename, confirmation), and a valid `.mp4` (and/or `.gif`) file is produced
at the end containing the 18 test frames (or fewer, if thinning was chosen).

- [ ] **Step 7: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests across every task)

- [ ] **Step 8: Commit**

```bash
git add src/lilly_stream/timelapse/menu.py src/lilly_stream/timelapse/cli.py tests/test_menu.py
git commit -m "feat: add interactive timelapse builder CLI"
```

---

## Self-Review Notes

- **Spec coverage:** civil-twilight gating with cached fallback (Task 3, 7), 10-minute configurable interval (Task 1 config, Task 7 loop), local disk storage with manual copy (Task 2, SETUP.md), Gmail alerting for first/last photo + low disk + daily summary (Task 5, 7), systemd deployment (Task 8), interactive numbered-menu timelapse builder with date range + optional thinning + MP4/GIF output (Tasks 9-11). All spec sections have a corresponding task.
- **Config/secrets split:** `Config` intentionally excludes Gmail credentials so `lilly-timelapse` never requires Gmail secrets to run — only `lilly-capture` calls `load_secrets`.
- **Type consistency verified:** `photo_path`/`parse_timestamp` (Task 2) are the single source of truth for the storage convention, reused unchanged by `daemon.py` (Task 7) and `selection.py` (Task 9). `AlertMailer.send` signature (Task 5) matches every call site in `daemon.py` (Task 7). `PhotoEntry` (Task 9) is reused unchanged by `build.py` (Task 10) and `menu.py`/`cli.py` (Task 11).
