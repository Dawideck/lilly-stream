from __future__ import annotations

from pathlib import Path

from lilly_stream.config import load_config
from lilly_stream.storage import available_dates
from lilly_stream.timelapse.build import build_gif, build_mp4
from lilly_stream.timelapse.menu import (
    prompt_text,
    prompt_yes_no,
    select_date_range,
    select_fps,
    select_format,
    select_thinning,
)
from lilly_stream.timelapse.selection import list_entries_in_range


def main() -> None:
    config = load_config(Path("config.yaml"))
    dates = available_dates(config.capture.storage_dir)
    if not dates:
        print("No photos found in storage directory.")
        return

    while True:
        start, end = select_date_range(dates)
        entries = list_entries_in_range(config.capture.storage_dir, start, end)
        if entries:
            break
        print(f"No photos found between {start} and {end}. Please pick a different range.")

    fps = select_fps()
    entries = select_thinning(entries, fps)
    fmt = select_format()

    default_ext = "gif" if fmt == "gif" else "mp4"
    default_name = f"bloom_{start}_to_{end}.{default_ext}"
    filename = prompt_text("Output filename", default_name)

    duration_sec = len(entries) / fps
    print(
        f"\nDate range: {start} to {end}\n"
        f"Frames: {len(entries)}\n"
        f"FPS: {fps}\n"
        f"Estimated duration: {duration_sec:.1f}s\n"
        f"Format: {fmt}\n"
        f"Output: {filename}\n"
    )
    if not prompt_yes_no("Build timelapse with these settings?"):
        print("Cancelled.")
        return

    output_path = Path(filename)
    if fmt in ("mp4", "both"):
        mp4_path = output_path.with_suffix(".mp4")
        print(f"Building mp4 from {len(entries)} frames...")
        build_mp4(entries, mp4_path, fps)
        print(f"Wrote {mp4_path}")
    if fmt in ("gif", "both"):
        gif_path = output_path.with_suffix(".gif")
        print(f"Building gif from {len(entries)} frames...")
        build_gif(entries, gif_path, fps)
        print(f"Wrote {gif_path}")


if __name__ == "__main__":
    main()
