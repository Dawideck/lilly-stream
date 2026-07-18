# Stop-Motion Frame-by-Frame Builder — Design

## Purpose

A third `lilly-stream` module for shooting frame-by-frame stop-motion sequences: the
Pi (camera attached) serves photos on demand over the network; a Mac-side GUI shows a
live-ish preview with onion skinning, lets the user accept/discard each shot, and
maintains a branching history of takes so the user can jump back to any earlier frame
and shoot a new sequence from there without losing the original. It also gains the
ability to bulk-download module 1's interval photos over the network (replacing manual
`scp`), and to remotely view/edit module 1's daemon configuration — including two new
daylight-window modes for the capture daemon itself.

This spec extends the existing, already-deployed `lilly-stream` project (modules 1
and 2, described in `docs/superpowers/specs/2026-07-16-lilly-stream-design.md`).
Modules 1 (`lilly-capture`) and 2 (`lilly-timelapse`) are untouched except for the
window-mode extension described in Section 8 — this is additive, not a rewrite.

## Architecture

New subpackage: `lilly_stream.stopmotion`, split along the Pi/Mac boundary:

- **Pi side** (`stopmotion/server.py`) — a Flask app, run manually for now (later
  possibly a systemd unit, matching `lilly-capture.service`'s pattern). Opens one
  `Camera` instance at startup (reusing the existing, unmodified
  `lilly_stream.capture.camera.Camera`) and keeps it warm for the session's lifetime.
- **Mac side** — the frame-history/branching data model, the HTTP client talking to
  the Pi, onion-skin compositing, the preview-video builder (reusing module 2's
  `timelapse.build.build_mp4`), and the Flask+browser GUI.

Two new console-script entry points: `lilly-stopmotion-server` (Pi side) and
`lilly-stopmotion` (Mac side GUI).

**Why Flask over FastAPI**: the API is simple (5 endpoints, one client, and camera
access is inherently serialized — only one photo can be in flight at a time), so
FastAPI's main strength (async concurrency) buys nothing here. FastAPI also needs an
ASGI server (Uvicorn) plus Pydantic as extra dependencies — a heavier footprint on a
Pi Zero W for no corresponding benefit at this scope.

## Pi-side server (`stopmotion/server.py`)

Five endpoints, all serialized through the one open `Camera` instance:

1. **`POST /snapshot`** — captures a quick, lower-resolution preview image (not saved
   to disk) and returns the JPEG bytes directly.
2. **`POST /capture`** — captures a full-resolution photo via the same
   `Camera.capture()` module 1 uses, saves it to a temp location on the Pi
   (`stopmotion_tmp/<uuid>.jpg`), and returns the image bytes plus that `<uuid>`. This
   Pi-side copy is a temporary holding copy — the Mac is authoritative once it has the
   bytes.
3. **`DELETE /photo/<uuid>`** — deletes that temp file. Called by the Mac immediately
   after every capture, accepted or discarded, so the Pi never accumulates rejected or
   duplicate frames.
4. **`GET /photos?start=YYYY-MM-DD&end=YYYY-MM-DD`** — filters *module 1's* daemon
   photo store (`config.yaml`'s `capture.storage_dir` — a different dataset from the
   stop-motion session frames) using the existing
   `lilly_stream.timelapse.selection.list_entries_in_range`, and streams the matches
   back as a single zip archive. Lets the Mac pull a date range directly instead of
   `scp -r`'ing the whole `photos/` directory.
5. **`GET /config`** / **`PUT /config`** — read/write `alerts.recipient` and
   `capture.interval_minutes`/`window_mode`/offset/hardcoded fields (`config.yaml`),
   and `gmail_address`/`gmail_app_password` (`secrets.yaml`). `PUT` writes the files
   then runs `sudo systemctl restart lilly-capture` so changes take effect
   immediately — requires a one-time deployment step on the Pi: a passwordless-sudo
   rule scoped to exactly that one systemctl command, so the Flask process itself
   never needs to run as root. `GET` returns the real values (including
   `gmail_app_password`) since this is a LAN-only, single-user tool; the Mac GUI is
   responsible for masking it in the UI (see below).

`CameraError` (existing, from module 1) raised inside `/snapshot` or `/capture`
returns an HTTP 500 with a message, distinct from a connection failure — so the Mac
GUI can tell "Pi is up but the shot failed" from "can't reach the Pi at all."

## Mac-side frame history & branching model (`stopmotion/session.py`)

**Storage layout**, per named session:
```
stopmotion_sessions/<session_name>/
  frames/<frame_id>.jpg     # pool of accepted frames, each stored exactly once
  session.json                # the tree structure
```

**Data model** — git-like on purpose:

- Each accepted frame is a node: `{id, parent_id, filename, captured_at}`.
  `parent_id` is `null` only for the session's very first frame.
- `session.json` tracks `current_tip`: the frame id new captures attach to next
  (equivalent to git's `HEAD`).
- A "take" is not a separately stored concept — it's the path from root to any frame,
  reconstructed by walking `parent_id` back to `null` and reversing. Browsing history
  and resuming from an earlier frame is just "set `current_tip` to that frame's id" (a
  checkout); the next accepted capture becomes a new child of whatever `current_tip`
  is, which is what creates a branch. A frame can have multiple children — no take is
  ever destroyed by branching from it.

**Frame ids vs. the Pi's temp-file uuids** are two separate identifiers: the Pi's
`/capture` response uuid exists only so the Mac can issue
`DELETE /photo/<uuid>` for cleanup. Once the Mac accepts a shot, it mints its own
permanent `frame_id` for the session tree.

**Durability**: `session.json` is rewritten on every accepted capture and every tip
switch — not batched, since losing in-progress GUI state on a crash would mean losing
real, hard-to-redo shooting work.

**Sessions**: on GUI startup, resume the most recently active session or pick/create
one from a list (similar to how `lilly-timelapse` lists available dates).

## Mac-side GUI & capture flow (`stopmotion/webapp.py` + `stopmotion/client.py`)

`stopmotion/client.py` is a thin `PiClient` wrapping the Pi's HTTP endpoints
(`.snapshot()`, `.capture()`, `.delete_photo(id)`, `.download_photos(start, end)`,
`.get_config()`, `.put_config(...)`)  — the only place HTTP details live.

`stopmotion/webapp.py` is a Flask app serving one main page (HTML + JS):

- **Live view**: a "Refresh Preview" button (or `r` keybind) calls
  `PiClient.snapshot()`, then Pillow-composites the result with the current-tip
  frame's image at low opacity (onion skin) and displays it. On-demand, not
  continuous polling.
- **Capture**: Space (or a Capture button) calls `PiClient.capture()` directly,
  independent of whether the preview was just refreshed. The returned full-res photo
  is shown with **Accept**(`a`)/**Discard**(`d`):
  - *Accept*: save into `frames/<new_frame_id>.jpg`, append to `session.json` (parent
    = old `current_tip`), advance `current_tip`, then `DELETE` the Pi's temp copy.
  - *Discard*: `DELETE` the Pi's temp copy; nothing touches the session tree.
- **History**: a filmstrip of every frame in the tree (chronological). Clicking a
  frame checks it out (`current_tip` = that frame) and returns to the live view.
- **Preview video**: "Generate Preview" builds an MP4 from the current take's frame
  sequence (root → `current_tip`, walked via `parent_id`) using the existing
  `timelapse.build.build_mp4`, written to one fixed per-session temp path (overwritten
  each generation, so it never accumulates), played inline via `<video>`, deleted on
  clean GUI shutdown.
- **Settings** (see Section 8 below for the module-1 fields it edits): two parts —
  "Pi connection" (host/port, purely local to the Mac's own `config.yaml`, no Pi
  endpoint involved — edits `stopmotion.pi_host`/`pi_port` and re-tests the
  connection on save) and "Daemon settings" (shown once a Pi connection is
  established; fetched via `GET /config`, saved via `PUT /config`, which also
  restarts `lilly-capture` on the Pi). The Gmail app-password field displays masked
  (`••••••••`) with a reveal toggle, rather than being hidden entirely or shown by
  default.

## Config & error handling

New `stopmotion:` section in the existing `config.yaml`:
```yaml
stopmotion:
  pi_host: "raspberrypi.local"   # bare hostname/IP — this is for HTTP requests to
                                    # the Flask server, not SSH, so no "user@" prefix
  pi_port: 5000
  session_dir: "./stopmotion_sessions"
```

- **Network errors** (Pi unreachable/timeout): every `PiClient` call has a timeout;
  failures surface as a non-crashing error banner ("Can't reach the Pi at `<host>`")
  with a retry option.
- **Camera failures**: `CameraError` from `/snapshot`/`/capture` surfaces distinctly
  from a connection failure (see Pi-side server section above).
- **`session.json` corruption**: unlike module 1's disposable sun-times/day-state
  caches (safe to silently drop), a corrupted `session.json` is the only record of how
  frame files relate to each other — the images would still exist, just orphaned. This
  fails loudly: the GUI refuses to open that session and shows the parse error rather
  than silently starting an empty tree, which could hide or overwrite salvageable
  state.

## Extending module 1's daylight-window modes (`suntimes.py`, `daemon.py`, `config.py`)

A real behavior change to the already-deployed capture daemon — `is_daylight`/
`get_twilight_window` currently only support "API-derived civil twilight."

**New config fields** (`config.yaml`'s `capture:` section):
```yaml
capture:
  interval_minutes: 10
  storage_dir: "./photos"
  window_mode: "api_offset"       # "api_offset" | "hardcoded"
  start_offset_minutes: 0           # api_offset mode: shifts civil dawn; negative = earlier
  end_offset_minutes: 0             # api_offset mode: shifts civil dusk; negative = earlier
  hardcoded_start: "06:00"           # hardcoded mode only
  hardcoded_end: "20:00"             # hardcoded mode only
```

**New pure functions in `suntimes.py`** (independently unit-testable, no
network/hardware):
- `apply_offset(window, start_offset_minutes, end_offset_minutes) -> TwilightWindow`
  — shifts `civil_dawn`/`civil_dusk` by the given (possibly negative) minute offsets.
- `hardcoded_window(for_date, start_time, end_time) -> TwilightWindow` — builds a
  window directly from two fixed local `HH:MM` times combined with a date, bypassing
  the API/cache entirely.

**`daemon.handle_tick` branches on `config.capture.window_mode`**: `"hardcoded"`
skips the suntimes cache/fetch path entirely and calls `hardcoded_window`;
`"api_offset"` calls the existing `get_twilight_window` (unchanged — API + cache
fallback logic stays exactly as it is) and pipes the result through `apply_offset`
before the `is_daylight` check.

This needs test coverage extending `test_suntimes.py`/`test_daemon.py`, and a
redeploy (`git pull` + `systemctl restart lilly-capture`) once merged — the same
manual motion done during initial Pi deployment, which the new `PUT /config`
restart-on-save endpoint (Section on Pi-side server) automates going forward.

## Testing

- **`session.py`**: pure logic (add frame, switch tip, walk take root→tip), fully
  unit tested with `tmp_path`, no network/hardware — same style as
  `timelapse/selection.py`.
- **`client.py`** (`PiClient`): unit tested by mocking `requests` calls, same pattern
  as `alerts.py`/`smtplib`.
- **`server.py`**: tested via Flask's test client with a fake `Camera` injected (same
  dependency-injection pattern `daemon.handle_tick` already uses) — exercises
  routing/uuid/cleanup logic without real hardware. The real `Camera` class stays
  hardware-only/manually verified, as in module 1.
- **`webapp.py`**: thin route handlers (gluing `session.py` + `client.py` +
  `build_mp4`) get request/response tests via Flask's test client with a fake
  `PiClient`; interactive browser behavior (spacebar handling, live onion-skin
  refresh) is manually verified, matching the project's convention for I/O-heavy
  orchestration layers.
- **`suntimes.apply_offset`/`hardcoded_window`**: pure functions, fully unit tested
  with fixed datetimes, no network.

## Delivery phases (branching strategy)

Delivered as three sequential feature branches, each merged to `main` before the next
starts — not one branch holding the whole module until the end:

1. **Pi server core** — `POST /snapshot`, `POST /capture`, `DELETE /photo/<uuid>`,
   `GET /photos` (zip download). No dependency on anything else in this spec;
   deployable and useful standalone (replaces manual `scp` for module 2 immediately).
2. **Module 1 window-mode extension + remote config** — `apply_offset`/
   `hardcoded_window` in `suntimes.py`, the `window_mode` branch in
   `daemon.handle_tick`, the new `config.yaml` fields, and the Pi server's
   `GET`/`PUT /config` endpoint (including the systemd-restart step and its sudoers
   prerequisite). Independent of phase 1's endpoints; exists to expose these new
   fields remotely.
3. **Mac-side stop-motion GUI** — `session.py`, `client.py`, `webapp.py` (live view,
   onion skin, capture/accept/discard, history, preview video, settings page). Depends
   on phase 1 (capture endpoints) and phase 2 (config endpoint + fields for the
   settings page).

Each phase gets its own implementation plan (`writing-plans`), subagent-driven
implementation, task/whole-branch review, and merge — mirroring how modules 1 and 2
were built.

## Out of scope (this spec)

- Frame editing tools (crop, exposure, etc.) — explicitly deferred by the user for a
  later design pass.
- Continuous live video streaming preview (chose on-demand snapshot refresh instead).
- Multi-user/concurrent sessions — single user, single Pi, single active session.
- Automatic take naming/labeling beyond the frame tree itself (a "take" is just a path
  through the tree, not a separately named entity).
