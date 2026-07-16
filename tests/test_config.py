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
