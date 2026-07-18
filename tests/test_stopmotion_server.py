from __future__ import annotations

import zipfile
from datetime import datetime
from io import BytesIO
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
