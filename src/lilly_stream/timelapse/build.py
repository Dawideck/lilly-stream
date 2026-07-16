from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from lilly_stream.timelapse.selection import PhotoEntry


def build_mp4(entries: list[PhotoEntry], output_path: Path, fps: int) -> None:
    if not entries:
        raise ValueError("No entries to build a video from")

    frame_duration = 1 / fps
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for entry in entries:
            f.write(f"file '{entry.path.resolve()}'\n")
            f.write(f"duration {frame_duration}\n")
        f.write(f"file '{entries[-1].path.resolve()}'\n")
        filelist_path = f.name

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", filelist_path,
                "-vsync", "vfr",
                "-pix_fmt", "yuv420p",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        Path(filelist_path).unlink()


def build_gif(entries: list[PhotoEntry], output_path: Path, fps: int) -> None:
    if not entries:
        raise ValueError("No entries to build a GIF from")

    from PIL import Image

    frames = [Image.open(entry.path) for entry in entries]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / fps),
        loop=0,
    )
