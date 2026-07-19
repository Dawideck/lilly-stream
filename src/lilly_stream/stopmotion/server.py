from __future__ import annotations

import uuid
import zipfile
from datetime import date
from pathlib import Path

from flask import Flask, Response, request, send_file

from lilly_stream.capture.camera import CameraError
from lilly_stream.timelapse.selection import list_entries_in_range


def create_app(get_camera, *, tmp_dir: Path, storage_dir: Path) -> Flask:
    app = Flask(__name__)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    @app.route("/snapshot", methods=["POST"])
    def snapshot():
        tmp_path = tmp_dir / f"snapshot-{uuid.uuid4()}.jpg"
        try:
            get_camera().capture_preview(tmp_path)
        except CameraError as exc:
            return {"error": str(exc)}, 503
        except Exception as exc:
            return {"error": f"Camera unavailable: {exc}"}, 503
        data = tmp_path.read_bytes()
        tmp_path.unlink()
        return Response(data, mimetype="image/jpeg")

    @app.route("/capture", methods=["POST"])
    def capture():
        photo_id = str(uuid.uuid4())
        photo_path = tmp_dir / f"{photo_id}.jpg"
        try:
            get_camera().capture(photo_path)
        except CameraError as exc:
            return {"error": str(exc)}, 503
        except Exception as exc:
            return {"error": f"Camera unavailable: {exc}"}, 503
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
        try:
            start = date.fromisoformat(request.args["start"])
            end = date.fromisoformat(request.args["end"])
        except ValueError:
            return {"error": "start and end must be ISO dates (YYYY-MM-DD)"}, 400

        entries = list_entries_in_range(storage_dir, start, end)

        zip_path = tmp_dir / f"photos-{uuid.uuid4()}.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
                for entry in entries:
                    arcname = f"{entry.path.parent.name}/{entry.path.name}"
                    zf.write(entry.path, arcname=arcname)

            return send_file(zip_path, mimetype="application/zip", download_name="photos.zip")
        finally:
            zip_path.unlink()

    return app
