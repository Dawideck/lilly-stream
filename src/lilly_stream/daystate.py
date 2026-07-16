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
        try:
            return DayState.from_dict(json.loads(self.path.read_text()))
        except json.JSONDecodeError:
            return None

    def save(self, state: DayState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state.to_dict()))
