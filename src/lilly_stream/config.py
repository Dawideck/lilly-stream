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
