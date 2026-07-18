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

## Raspberry Pi (stop-motion server)

This reuses the same venv and camera as the capture daemon above — no separate
install needed beyond re-running `pip install -e .` to pick up the new `Flask`
dependency (already done if you followed the capture daemon steps after this was
added).

1. From `/home/pi/lilly-stream` (or wherever you cloned the repo) with the venv
   active: `lilly-stopmotion-server`. It listens on port 5000 by default.
2. From another machine on the same network, confirm it's reachable:
   `curl -X POST http://<pi-host-or-ip>:5000/snapshot -o test-snapshot.jpg`
3. To pull a date range of the capture daemon's photos without `scp`:
   `curl "http://<pi-host-or-ip>:5000/photos?start=2026-07-01&end=2026-07-18" -o photos.zip`

No systemd service yet for this one — run it in a terminal (or `tmux`/`screen`
session) for now while the stop-motion Mac GUI (a later phase) is in development.

## macOS / any machine (timelapse builder only)

1. Clone this repo and `cd` into it: `git clone <repo-url> lilly-stream && cd lilly-stream`.
2. Install `ffmpeg`: `brew install ffmpeg`.
3. `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.
4. Copy photos from the Pi (e.g. `scp -r pi@<pi-host>:/home/pi/lilly-stream/photos ./photos`).
5. Run `lilly-timelapse` and follow the interactive prompts.
