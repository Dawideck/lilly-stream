from __future__ import annotations

from pathlib import Path


class CameraError(Exception):
    """Raised when a photo capture fails."""


class Camera:
    def __init__(self):
        from picamera2 import Picamera2

        self._picam = Picamera2()
        self._picam.configure(self._picam.create_still_configuration())
        self._picam.start()

    def capture(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._picam.capture_file(str(path))
        except Exception as exc:
            raise CameraError(f"Failed to capture photo to {path}: {exc}") from exc

    def capture_preview(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            preview_config = self._picam.create_preview_configuration()
            self._picam.switch_mode_and_capture_file(preview_config, str(path))
        except Exception as exc:
            raise CameraError(f"Failed to capture preview to {path}: {exc}") from exc

    def close(self) -> None:
        self._picam.stop()
