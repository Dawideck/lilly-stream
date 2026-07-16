# lilly-stream Design

## Purpose

Record a flower blooming, 24/7, using a Raspberry Pi Zero W + RaspiCam. Capture photos
only during daylight (from first civil light in the morning to last civil light in the
evening, for Kolobrzeg, Poland — no hardcoded seasonal range), and later assemble a
chosen date range of those photos into an MP4/GIF timelapse. The timelapse builder must
also run on macOS.

## Architecture

Single Python package (`lilly_stream`) with shared library code and two CLI entry
points:

- `lilly-capture` — the 24/7 daemon that runs on the Pi Zero W.
- `lilly-timelapse` — the interactive timelapse builder, run on the Pi or a Mac.

Shared library modules used by both:

- `lilly_stream.config` — loads `config.yaml` (+ `secrets.yaml` / env vars).
- `lilly_stream.storage` — photo folder/filename convention (`photos/YYYY-MM-DD/HHMMSS.jpg`),
  shared so the builder reads exactly what the daemon writes.
- `lilly_stream.alerts` — Gmail SMTP email sending, used only by the capture daemon
  today but kept in shared lib since it's not capture-specific.

Rationale: Python is the natural fit because `picamera2` (the current Raspberry Pi
camera stack) is Python-native, and the timelapse builder needs only `ffmpeg`
(subprocess) + `Pillow`, both of which work identically on macOS and Raspberry Pi OS. A
single package with two entry points avoids duplicating the storage convention and
config parsing across two independent codebases.

## Component: capture daemon (`lilly-capture`)

### Light gating

- "First light" / "last light" are defined as **civil twilight begin/end**, not
  sunrise/sunset — this matches the user's intent of "first gleams of light" /
  "last light of the day."
- Once per day (on startup and on local-date rollover), fetch
  `civil_twilight_begin` / `civil_twilight_end` for Kolobrzeg's coordinates
  (54.1755, 15.5836) from the sunrise-sunset.org API (free, no API key).
- Cache the fetched times to `state/sun_times.json`, keyed by the date they're valid
  for.
- If today's fetch fails (no internet, API down), reuse the most recently cached
  times. Sunrise/sunset times drift only ~1-2 minutes/day, so a stale cache is a safe
  approximation. There is no "give up" path for a normal day — only a cold-start with
  zero cache and zero connectivity has no fallback (logged as an error; capture is
  skipped until a fetch succeeds).
- Every capture-loop tick, compare current local time against
  `[civil_twilight_begin, civil_twilight_end]` for today. Capture only when inside that
  window.

### Capture loop

- Sleep for `capture.interval_minutes` (config, default **10 minutes**), wake, check
  the light gate, and if inside the daylight window, capture one photo via
  `picamera2` and save to `photos/YYYY-MM-DD/HHMMSS.jpg`.
- Camera capture failures are caught and logged (and counted toward the daily summary)
  without crashing the loop.
- Per-day state persists to `state/day_state.json`: first-photo-taken flag, last
  captured timestamp, running success/failure counts. Persisting this means a systemd
  restart mid-day does not re-fire the "first photo of the day" alert or lose the day's
  counts.
- Local-date rollover (detected each tick by comparing today's date to the date stored
  in `day_state.json`) triggers the end-of-day summary email using that day's
  accumulated counts, then resets state for the new day.

### Camera stack

Build against `picamera2` (the libcamera-based stack on current Raspberry Pi OS
releases), since the target Pi's OS version is not yet confirmed. The camera capture
call is isolated to a single module (`lilly_stream.capture.camera`) so swapping to the
legacy `picamera` library — if the Pi turns out to be on an older Buster-based image —
is a scoped, single-file change.

### Alerting (Gmail email)

Shared function `alerts.send(subject, body, attachments=[])` using `smtplib` over SSL
with a Gmail address + Google App Password. Triggered by:

- **First photo of the day** — email with that photo attached.
- **Last photo of the day** — fired when a subsequent tick detects the light gate has
  since closed (current time past civil twilight end) since the last successful
  capture; email with that last photo attached.
- **Low disk space** — when free space on the storage volume drops below
  `disk.warn_threshold_mb` (config, default 500MB). Fires once per crossing (i.e. does
  not re-alert every tick while still below threshold) — re-arms once free space rises
  back above the threshold.
- **End-of-day summary** — sent at local-date rollover: photos taken, capture
  failures, and current free disk space for that completed day.

No auto-deletion of photos ever occurs — disk pressure is surfaced via email only, per
explicit user preference (bloom footage should never be silently lost).

### Deployment

Runs as a systemd service (`lilly-capture.service`) with `Restart=on-failure`, enabled
on boot. The repo includes the unit file and a `SETUP.md` covering `picamera2`
installation and `pip install -e .` on the Pi.

## Component: timelapse builder (`lilly-timelapse`)

Fully interactive, numbered-menu driven CLI — no required flags. Flow:

1. **Scan** `storage_dir`, group photos by date, show the available range and total
   count (e.g. "Photos available: 2026-07-01 to 2026-07-16, 1,240 total").
2. **Pick start date** — numbered list of available dates with per-day photo counts.
3. **Pick end date** — same list, filtered to dates ≥ start.
4. **Thinning (optional, default = include everything)** — numbered menu:
   1) Include every photo in range
   2) Every Nth photo (prompts for N)
   3) Target ~N total frames (tool computes the resulting stride)
   Shows resulting frame count and estimated duration (at the fps chosen next) before
   moving on.
5. **Frame rate** — numbered presets (12 / 24 / 30 fps) plus a custom option.
6. **Output format** — 1) MP4  2) GIF  3) Both.
7. **Output filename** — suggested default (`bloom_<start>_to_<end>.mp4`), editable.
8. **Confirmation screen** — recaps date range, frame count, fps, estimated duration,
   format, and filename; yes/no before building.
9. **Build** — MP4 via `ffmpeg` (subprocess, image sequence → H.264); GIF via
   `Pillow` when selected. Progress is shown as frames are processed.

If the selected range yields zero photos (e.g. a Pi outage gap), the tool reports this
and returns to date re-selection rather than failing.

### Frame interval guidance (informational, not enforced by the tool)

Default `capture.interval_minutes: 10` balances smooth motion during the fast
petal-unfurling phase against manageable video length: at 10-minute intervals, a
2-week bloom in Kolobrzeg summer (~17h daylight/day) yields roughly 1,400 photos —
about 58 seconds at 24fps with no thinning needed. The interval is configurable; the
user plans to tune it empirically.

## Config, secrets, and state

**`config.yaml`** (committed):

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

**`secrets.yaml`** (gitignored) or environment variables: Gmail address + Google App
Password. A `secrets.yaml.example` template is committed so setup is unambiguous. The
app password (not the account password) is required because Gmail blocks plain SMTP
login with account credentials.

**Runtime state** (gitignored, regenerated automatically): `state/sun_times.json`
(cached civil twilight times) and `state/day_state.json` (today's counters/flags).
Neither is a secret; both are local cache only.

## Testing

pytest covers the logic that doesn't require hardware or network access:

- Light-gating logic: given fixed civil twilight times and a mocked "now," does the
  gate open/close correctly, including date-rollover behavior.
- Day-state persistence: first/last-photo flags and counters survive a simulated
  restart without duplicate alerts.
- Timelapse date-range and thinning selection: given a set of fake timestamped
  filenames, does the builder select the correct subset for a given range/thinning
  choice.

Camera capture, the sunrise-sunset API call, and email sending are thin I/O wrappers
exercised manually on the real Pi rather than unit-tested — mocking them would mostly
test the mocks, not real behavior.

## Out of scope (v1)

- Auto-deletion/pruning of photos under disk pressure.
- Auto-sync of photos from Pi to Mac/cloud (manual copy for now).
- Variable capture interval by time of day (single fixed interval only).
- Brightness-based darkness detection (API-based civil twilight gating only, with
  cached-time fallback — no image-analysis fallback).
