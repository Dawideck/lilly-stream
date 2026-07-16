import shutil

import pytest
from PIL import Image

from lilly_stream.timelapse.build import build_gif, build_mp4
from lilly_stream.timelapse.selection import PhotoEntry


def make_fake_photos(tmp_path, count):
    entries = []
    for i in range(count):
        path = tmp_path / f"frame_{i}.jpg"
        Image.new("RGB", (16, 16), color=(i * 10 % 255, 0, 0)).save(path)
        entries.append(PhotoEntry(path=path, timestamp=None))
    return entries


def test_build_gif_creates_file(tmp_path):
    entries = make_fake_photos(tmp_path, 3)
    output = tmp_path / "out.gif"
    build_gif(entries, output, fps=10)
    assert output.exists()
    assert output.stat().st_size > 0


def test_build_gif_raises_on_empty_entries(tmp_path):
    with pytest.raises(ValueError):
        build_gif([], tmp_path / "out.gif", fps=10)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_build_mp4_creates_file(tmp_path):
    entries = make_fake_photos(tmp_path, 3)
    output = tmp_path / "out.mp4"
    build_mp4(entries, output, fps=10)
    assert output.exists()
    assert output.stat().st_size > 0


def test_build_mp4_raises_on_empty_entries(tmp_path):
    with pytest.raises(ValueError):
        build_mp4([], tmp_path / "out.mp4", fps=10)
