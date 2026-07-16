from datetime import date, datetime
from pathlib import Path

from lilly_stream.timelapse.menu import (
    prompt_choice,
    prompt_int,
    prompt_text,
    prompt_yes_no,
    select_date_range,
    select_fps,
    select_format,
    select_thinning,
)
from lilly_stream.timelapse.selection import PhotoEntry


def fake_input(responses):
    it = iter(responses)
    return lambda prompt="": next(it)


def test_prompt_choice_returns_valid_index():
    assert prompt_choice("Pick:", ["a", "b", "c"], input_fn=fake_input(["2"])) == 1


def test_prompt_choice_reprompts_on_invalid():
    assert prompt_choice("Pick:", ["a", "b"], input_fn=fake_input(["9", "abc", "1"])) == 0


def test_prompt_int_reprompts_below_minimum():
    assert prompt_int("N:", minimum=5, input_fn=fake_input(["2", "5"])) == 5


def test_prompt_text_returns_default_on_blank():
    assert prompt_text("Name", "default.mp4", input_fn=fake_input([""])) == "default.mp4"


def test_prompt_text_returns_input_when_given():
    assert prompt_text("Name", "default.mp4", input_fn=fake_input(["custom.mp4"])) == "custom.mp4"


def test_prompt_yes_no_accepts_y_and_n():
    assert prompt_yes_no("Continue?", input_fn=fake_input(["y"])) is True
    assert prompt_yes_no("Continue?", input_fn=fake_input(["n"])) is False


def test_select_date_range_picks_start_and_end():
    available = {"2026-07-14": 5, "2026-07-15": 6, "2026-07-16": 4}
    start, end = select_date_range(available, input_fn=fake_input(["2", "1"]))
    assert start == date(2026, 7, 15)
    assert end == date(2026, 7, 15)


def test_select_fps_preset():
    assert select_fps(input_fn=fake_input(["2"])) == 24


def test_select_fps_custom():
    assert select_fps(input_fn=fake_input(["4", "18"])) == 18


def test_select_format_returns_expected_strings():
    assert select_format(input_fn=fake_input(["1"])) == "mp4"
    assert select_format(input_fn=fake_input(["2"])) == "gif"
    assert select_format(input_fn=fake_input(["3"])) == "both"


def make_entries(n):
    return [PhotoEntry(path=Path(f"{i}.jpg"), timestamp=datetime(2026, 7, 15, 9, 0)) for i in range(n)]


def test_select_thinning_include_all():
    entries = make_entries(10)
    assert select_thinning(entries, fps=24, input_fn=fake_input(["1"])) == entries


def test_select_thinning_every_nth():
    entries = make_entries(10)
    result = select_thinning(entries, fps=24, input_fn=fake_input(["2", "3"]))
    assert len(result) == 4
