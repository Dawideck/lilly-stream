# Stop-Motion Phase 1: Pi Server Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Pi-side Flask server for the stop-motion module: on-demand photo snapshot/capture/cleanup endpoints, plus a zip-download endpoint for module 1's interval photos (replacing manual `scp`).

**Architecture:** A single new `lilly_stream.stopmotion` subpackage. `server.py` defines a Flask app factory taking an injected camera object (for testability) and returns a `Flask` app with four routes. `cli.py` wires up the real `Camera`, loads `config.yaml` for the photo storage path, and runs the app. This is Phase 1 of 3 for the stop-motion module (see `docs/superpowers/specs/2026-07-18-stopmotion-design.md`) — the Mac-side GUI and module 1's config/window-mode extension are separate, later plans.

**Tech Stack:** Flask (new dependency), reuses `lilly_stream.capture.camera.Camera` and `lilly_stream.timelapse.selection.list_entries_in_range` unchanged.

## Global Constraints

- Target Python 3.9+. Use `from __future__ import annotations` in every new module.
- Flask, not FastAPI (see spec's rationale: single client, serialized camera access, no benefit from async).
- `/snapshot` is not persisted server-side: capture to a temp file, read the bytes, delete the temp file, return the bytes. No id, no follow-up cleanup call needed for it.
- `/capture` IS temp-persisted server-side (`<tmp_dir>/<uuid>.jpg`) until the client explicitly calls `DELETE /photo/<uuid>` — the client decides accept/discard after receiving the bytes, so the file must survive until that decision arrives.
- `/photos?start=...&end=...` must reuse `lilly_stream.timelapse.selection.list_entries_in_range` unchanged — do not reimplement date-range filtering.
- Camera hardware code (`capture/camera.py` changes, and `stopmotion/cli.py`) has no automated tests — verified manually on the Pi, consistent with the rest of the project's camera-adjacent code.
- New console script: `lilly-stopmotion-server = "lilly_stream.stopmotion.cli:main"`.

---

## Task 1: Extend `Camera` with a fast preview-resolution capture

**Files:**
- Modify: `src/lilly_stream/capture/camera.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Camera.capture_preview(path: Path) -> None` — new method alongside the existing `capture(path: Path) -> None` and `close() -> None`.

No automated test: this touches `picamera2`, which only runs on Raspberry Pi hardware (same situation as the rest of this file, which already has zero automated tests). Verified manually on the Pi in a later step of this plan.

- [ ] **Step 1: Read the current file**

Read `src/lilly_stream/capture/camera.py` to see its exact current contents before editing (it currently has `CameraError`, `Camera.__init__`, `Camera.capture`, `Camera.close`).

- [ ] **Step 2: Add `capture_preview` to the `Camera` class**

Add this method to the `Camera` class in `src/lilly_stream/capture/camera.py`, alongside the existing `capture` method:

```python
    def capture_preview(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            preview_config = self._picam.create_preview_configuration()
            self._picam.switch_mode_and_capture_file(preview_config, str(path))
        except Exception as exc:
            raise CameraError(f"Failed to capture preview to {path}: {exc}") from exc
```

This uses picamera2's `create_preview_configuration()` (a lower-resolution, faster capture mode than the still-image config used by `capture()`) combined with `switch_mode_and_capture_file()`, which temporarily switches the camera to that mode, captures, and switches back — so repeated `/snapshot` calls don't disturb the camera's normal still-capture configuration used by `/capture` or module 1's daemon.

- [ ] **Step 3: Verify the rest of the test suite still passes**

Run: `pytest -v`
Expected: PASS (all existing tests; `capture/camera.py` is not imported by any test, so this change can't break anything under test)

- [ ] **Step 4: Commit**

```bash
git add src/lilly_stream/capture/camera.py
git commit -m "feat: add fast preview-resolution capture to Camera"
```

---

## Task 2: Pi server core — snapshot, capture, and cleanup endpoints

**Files:**
- Create: `src/lilly_stream/stopmotion/__init__.py`
- Create: `src/lilly_stream/stopmotion/server.py`
- Test: `tests/test_stopmotion_server.py`

**Interfaces:**
- Consumes: a `camera` object with `.capture(path: Path) -> None` and `.capture_preview(path: Path) -> None` (duck-typed, matching `Camera` from Task 1).
- Produces: `create_app(camera, *, tmp_dir: Path, storage_dir: Path) -> Flask` — note `storage_dir` is added in Task 3, but the signature is defined here with it as a required keyword argument from the start so Task 3 doesn't need to change every existing test's call site. In this task, `storage_dir` is accepted but not yet used by any route.

- [ ] **Step 1: Write the failing tests**

`tests/test_stopmotion_server.py`:
```python
from __future__ import annotations

from pathlib import Path

from lilly_stream.stopmotion.server import create_app


class FakeCamera:
    def __init__(self):
        self.captured_paths = []
        self.preview_paths = []

    def capture(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"full-res-photo-bytes")
        self.captured_paths.append(path)

    def capture_preview(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"preview-photo-bytes")
        self.preview_paths.append(path)


def make_app(tmp_path, camera=None):
    camera = camera or FakeCamera()
    return create_app(
        camera,
        tmp_dir=tmp_path / "tmp",
        storage_dir=tmp_path / "photos",
    )


def test_snapshot_returns_image_bytes_and_cleans_up(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.post("/snapshot")

    assert response.status_code == 200
    assert response.data == b"preview-photo-bytes"
    assert response.mimetype == "image/jpeg"
    assert list((tmp_path / "tmp").iterdir()) == []


def test_capture_returns_image_bytes_with_photo_id_header(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.post("/capture")

    assert response.status_code == 200
    assert response.data == b"full-res-photo-bytes"
    photo_id = response.headers["X-Photo-Id"]
    assert (tmp_path / "tmp" / f"{photo_id}.jpg").exists()


def test_delete_photo_removes_temp_file(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    capture_response = client.post("/capture")
    photo_id = capture_response.headers["X-Photo-Id"]
    photo_path = tmp_path / "tmp" / f"{photo_id}.jpg"
    assert photo_path.exists()

    delete_response = client.delete(f"/photo/{photo_id}")

    assert delete_response.status_code == 204
    assert not photo_path.exists()


def test_delete_photo_missing_id_is_idempotent(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.delete("/photo/does-not-exist")

    assert response.status_code == 204
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stopmotion_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lilly_stream.stopmotion'`

- [ ] **Step 3: Implement the server**

`src/lilly_stream/stopmotion/__init__.py`: empty file.

`src/lilly_stream/stopmotion/server.py`:
```python
from __future__ import annotations

import uuid
from pathlib import Path

from flask import Flask, Response, send_file


def create_app(camera, *, tmp_dir: Path, storage_dir: Path) -> Flask:
    app = Flask(__name__)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    @app.route("/snapshot", methods=["POST"])
    def snapshot():
        tmp_path = tmp_dir / f"snapshot-{uuid.uuid4()}.jpg"
        camera.capture_preview(tmp_path)
        data = tmp_path.read_bytes()
        tmp_path.unlink()
        return Response(data, mimetype="image/jpeg")

    @app.route("/capture", methods=["POST"])
    def capture():
        photo_id = str(uuid.uuid4())
        photo_path = tmp_dir / f"{photo_id}.jpg"
        camera.capture(photo_path)
        response = send_file(photo_path, mimetype="image/jpeg")
        response.headers["X-Photo-Id"] = photo_id
        return response

    @app.route("/photo/<photo_id>", methods=["DELETE"])
    def delete_photo(photo_id: str):
        photo_path = tmp_dir / f"{photo_id}.jpg"
        if photo_path.exists():
            photo_path.unlink()
        return "", 204

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stopmotion_server.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests, including the 4 new ones)

- [ ] **Step 6: Commit**

```bash
git add src/lilly_stream/stopmotion/__init__.py src/lilly_stream/stopmotion/server.py tests/test_stopmotion_server.py
git commit -m "feat: add Pi-side stopmotion server (snapshot, capture, cleanup)"
```

---

## Task 3: `/photos` zip-download endpoint

**Files:**
- Modify: `src/lilly_stream/stopmotion/server.py`
- Modify: `tests/test_stopmotion_server.py`

**Interfaces:**
- Consumes: `PhotoEntry`, `list_entries_in_range(storage_dir: Path, start_date: date, end_date: date) -> list[PhotoEntry]` from `lilly_stream.timelapse.selection` (unchanged, from module 2).
- Produces: the `GET /photos?start=YYYY-MM-DD&end=YYYY-MM-DD` route, added to the same `create_app` from Task 2. No new public function signatures — `create_app`'s signature is unchanged from Task 2 (it already accepted `storage_dir`).

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_stopmotion_server.py` (append to the existing file, don't remove the Task 2 tests):

```python
import zipfile
from datetime import datetime
from io import BytesIO


def make_photo(storage_dir: Path, day: str, time_str: str) -> None:
    day_dir = storage_dir / day
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / f"{time_str}.jpg").write_bytes(b"fake-jpeg-data")


def test_photos_endpoint_returns_zip_of_matching_date_range(tmp_path):
    storage_dir = tmp_path / "photos"
    make_photo(storage_dir, "2026-07-15", "090000")
    make_photo(storage_dir, "2026-07-16", "090000")
    make_photo(storage_dir, "2026-07-17", "090000")

    app = create_app(
        FakeCamera(),
        tmp_dir=tmp_path / "tmp",
        storage_dir=storage_dir,
    )
    client = app.test_client()

    response = client.get("/photos?start=2026-07-15&end=2026-07-16")

    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    archive = zipfile.ZipFile(BytesIO(response.data))
    names = sorted(archive.namelist())
    assert names == ["2026-07-15/090000.jpg", "2026-07-16/090000.jpg"]
    assert archive.read("2026-07-15/090000.jpg") == b"fake-jpeg-data"


def test_photos_endpoint_empty_range_returns_empty_zip(tmp_path):
    storage_dir = tmp_path / "photos"
    make_photo(storage_dir, "2026-07-15", "090000")

    app = create_app(
        FakeCamera(),
        tmp_dir=tmp_path / "tmp",
        storage_dir=storage_dir,
    )
    client = app.test_client()

    response = client.get("/photos?start=2026-08-01&end=2026-08-02")

    assert response.status_code == 200
    archive = zipfile.ZipFile(BytesIO(response.data))
    assert archive.namelist() == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_stopmotion_server.py -v`
Expected: FAIL — `test_photos_endpoint_...` tests fail with a 404 (route doesn't exist yet); the Task 2 tests still pass.

- [ ] **Step 3: Implement the `/photos` route**

In `src/lilly_stream/stopmotion/server.py`, update the imports and add the new route inside `create_app`:

```python
from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date
from pathlib import Path

from flask import Flask, Response, request, send_file

from lilly_stream.timelapse.selection import list_entries_in_range


def create_app(camera, *, tmp_dir: Path, storage_dir: Path) -> Flask:
    app = Flask(__name__)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    @app.route("/snapshot", methods=["POST"])
    def snapshot():
        tmp_path = tmp_dir / f"snapshot-{uuid.uuid4()}.jpg"
        camera.capture_preview(tmp_path)
        data = tmp_path.read_bytes()
        tmp_path.unlink()
        return Response(data, mimetype="image/jpeg")

    @app.route("/capture", methods=["POST"])
    def capture():
        photo_id = str(uuid.uuid4())
        photo_path = tmp_dir / f"{photo_id}.jpg"
        camera.capture(photo_path)
        response = send_file(photo_path, mimetype="image/jpeg")
        response.headers["X-Photo-Id"] = photo_id
        return response

    @app.route("/photo/<photo_id>", methods=["DELETE"])
    def delete_photo(photo_id: str):
        photo_path = tmp_dir / f"{photo_id}.jpg"
        if photo_path.exists():
            photo_path.unlink()
        return "", 204

    @app.route("/photos", methods=["GET"])
    def photos():
        start = date.fromisoformat(request.args["start"])
        end = date.fromisoformat(request.args["end"])
        entries = list_entries_in_range(storage_dir, start, end)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for entry in entries:
                arcname = f"{entry.path.parent.name}/{entry.path.name}"
                zf.write(entry.path, arcname=arcname)
        buffer.seek(0)

        return send_file(buffer, mimetype="application/zip", download_name="photos.zip")

    return app
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_stopmotion_server.py -v`
Expected: PASS (6 tests: the 4 from Task 2 plus the 2 new ones)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add src/lilly_stream/stopmotion/server.py tests/test_stopmotion_server.py
git commit -m "feat: add zip-download endpoint for module 1's daemon photos"
```

---

## Task 4: CLI entry point, dependency, and deployment docs

**Files:**
- Create: `src/lilly_stream/stopmotion/cli.py`
- Modify: `pyproject.toml`
- Modify: `SETUP.md`

**Interfaces:**
- Consumes: `load_config(config_path: Path) -> Config` from `lilly_stream.config`; `Camera` from `lilly_stream.capture.camera`; `create_app(camera, *, tmp_dir: Path, storage_dir: Path) -> Flask` from `lilly_stream.stopmotion.server`.
- Produces: `main() -> None` (the `lilly-stopmotion-server` console-script entry point).

No automated test: `main()` wires real hardware (camera) and binds a real network port — verified manually on the Pi, matching `capture/cli.py`'s precedent from module 1.

- [ ] **Step 1: Implement the CLI**

`src/lilly_stream/stopmotion/cli.py`:
```python
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from lilly_stream.capture.camera import Camera
from lilly_stream.config import load_config
from lilly_stream.stopmotion.server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the lilly-stream stop-motion Pi server.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--tmp-dir", type=Path, default=Path("stopmotion_tmp"))
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    config = load_config(args.config)
    camera = Camera()
    app = create_app(camera, tmp_dir=args.tmp_dir, storage_dir=config.capture.storage_dir)
    app.run(host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add the Flask dependency and console script**

In `pyproject.toml`, update the `dependencies` list to include Flask, and add the new script under `[project.scripts]`:

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
    "Flask>=3.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[project.scripts]
lilly-capture = "lilly_stream.capture.cli:main"
lilly-timelapse = "lilly_stream.timelapse.cli:main"
lilly-stopmotion-server = "lilly_stream.stopmotion.cli:main"

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Reinstall the package so the new console script and dependency are picked up**

Run: `pip install -e ".[dev]"`
Expected: Flask installs, and `lilly-stopmotion-server` becomes available on `PATH` inside the active venv.

- [ ] **Step 4: Verify the CLI module imports cleanly and the full suite still passes**

Run: `python -c "from lilly_stream.stopmotion.cli import main"`
Expected: no output, no error (this only imports the module; it does not call `main()`, which would try to open a real camera)

Run: `pytest -v`
Expected: PASS (all tests)

- [ ] **Step 5: Add Pi deployment docs**

Add this new subsection to `SETUP.md`, immediately after the existing "Raspberry Pi (capture daemon)" section's numbered steps (before the "macOS / any machine" section):

```markdown
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
```

- [ ] **Step 6: Commit**

```bash
git add src/lilly_stream/stopmotion/cli.py pyproject.toml SETUP.md
git commit -m "feat: add stopmotion server CLI entry point and Pi deployment docs"
```

---

## Self-Review Notes

- **Spec coverage**: all 4 of Phase 1's endpoints from the design spec (`/snapshot`, `/capture`, `DELETE /photo/<uuid>`, `GET /photos`) are covered — Task 2 (snapshot/capture/delete) and Task 3 (photos zip). Camera preview-resolution capture (Task 1) and CLI/deployment (Task 4) round out everything Phase 1 needs to be independently deployable and useful, matching the spec's "Delivery phases" intent.
- **Type consistency verified**: `create_app`'s signature (`camera, *, tmp_dir: Path, storage_dir: Path`) is introduced once in Task 2 and never changes across Task 3/4 — Task 3 only adds a route inside the existing factory, avoiding the signature-churn problem flagged during planning.
- **No placeholders**: every step has complete, runnable code; no "add error handling" hand-waving.
