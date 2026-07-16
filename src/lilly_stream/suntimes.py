from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

log = logging.getLogger(__name__)

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
        try:
            return TwilightWindow.from_dict(json.loads(self.cache_path.read_text()))
        except json.JSONDecodeError:
            return None

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
    except Exception as exc:
        log.warning(f"Failed to fetch twilight times for {for_date}: {exc}")
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
