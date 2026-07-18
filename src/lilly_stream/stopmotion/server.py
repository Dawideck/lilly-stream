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
