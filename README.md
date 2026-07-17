# lilly-stream

Records a flower blooming with a Raspberry Pi Zero W + camera, then builds a timelapse from the photos.

- **`lilly-capture`** — runs 24/7 on the Pi. Takes a photo every N minutes, but only during daylight (civil twilight to civil twilight, computed daily for Kolobrzeg, Poland via the [sunrise-sunset.org](https://sunrise-sunset.org/api) API, with local caching so a network hiccup never stops capture). Sends Gmail alerts for the first and last photo of the day, low disk space, and an end-of-day summary.
- **`lilly-timelapse`** — an interactive, numbered-menu CLI (runs on the Pi or on macOS) that picks a date range from the captured photos, optionally thins the frame count, and assembles an MP4 and/or GIF via `ffmpeg`/Pillow.

## Setup

See [SETUP.md](SETUP.md) for full installation steps — flashing the Pi, installing `picamera2` and `ffmpeg`, configuring Gmail alerts, and enabling the systemd service.

## Configuration

`config.yaml` (committed) holds location, capture interval, disk-space threshold, and the alert recipient:

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

Gmail credentials go in a gitignored `secrets.yaml` (copy `secrets.yaml.example`) or the `LILLY_GMAIL_ADDRESS` / `LILLY_GMAIL_APP_PASSWORD` environment variables — never in `config.yaml`.

## Project layout

```
src/lilly_stream/
  config.py         config + secrets loading
  storage.py         photo path convention (YYYY-MM-DD/HHMMSS.jpg) and disk-space helpers
  suntimes.py         civil twilight fetch + daily cache
  daystate.py          per-day capture counters/flags, survives restarts
  alerts.py             Gmail SMTP mailer
  capture/
    camera.py            picamera2 wrapper
    daemon.py             the capture loop's decision logic
    cli.py                 lilly-capture entry point
  timelapse/
    selection.py          date-range + frame-thinning logic
    build.py                MP4 (ffmpeg) / GIF (Pillow) assembly
    menu.py                  interactive numbered-menu prompts
    cli.py                    lilly-timelapse entry point
deploy/lilly-capture.service   systemd unit for the Pi
```

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

Design and implementation-plan documents live under `docs/superpowers/`.
