from __future__ import annotations

from datetime import date

from lilly_stream.timelapse.selection import PhotoEntry, thin_every_nth, thin_to_target_count


def prompt_choice(prompt: str, options: list[str], input_fn=input) -> int:
    while True:
        print(prompt)
        for i, option in enumerate(options, start=1):
            print(f"  {i}) {option}")
        raw = input_fn("> ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(f"Please enter a number between 1 and {len(options)}.")


def prompt_int(prompt: str, minimum: int = 1, input_fn=input) -> int:
    while True:
        raw = input_fn(f"{prompt} ").strip()
        if raw.isdigit() and int(raw) >= minimum:
            return int(raw)
        print(f"Please enter a number >= {minimum}.")


def prompt_text(prompt: str, default: str, input_fn=input) -> str:
    raw = input_fn(f"{prompt} [{default}]: ").strip()
    return raw if raw else default


def prompt_yes_no(prompt: str, input_fn=input) -> bool:
    while True:
        raw = input_fn(f"{prompt} [y/n] ").strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Please answer y or n.")


def select_date_range(available: dict[str, int], input_fn=input) -> tuple[date, date]:
    dates = list(available.keys())
    labels = [f"{d} ({available[d]} photos)" for d in dates]

    start_idx = prompt_choice("Select start date:", labels, input_fn)
    end_dates = dates[start_idx:]
    end_labels = labels[start_idx:]
    end_idx = prompt_choice("Select end date:", end_labels, input_fn)

    return date.fromisoformat(dates[start_idx]), date.fromisoformat(end_dates[end_idx])


def select_thinning(entries: list[PhotoEntry], fps: int, input_fn=input) -> list[PhotoEntry]:
    choice = prompt_choice(
        "How many photos should be included?",
        ["Include every photo in range", "Every Nth photo", "Target ~N total frames"],
        input_fn,
    )
    if choice == 0:
        result = entries
        print(f"Selected {len(result)} frames (~{len(result) / fps:.1f}s at {fps}fps)")
        return result
    if choice == 1:
        n = prompt_int("Include every Nth photo (N):", minimum=1, input_fn=input_fn)
        result = thin_every_nth(entries, n)
        print(f"Selected {len(result)} frames (~{len(result) / fps:.1f}s at {fps}fps)")
        return result
    target = prompt_int("Target total frame count:", minimum=1, input_fn=input_fn)
    result = thin_to_target_count(entries, target)
    print(f"Selected {len(result)} frames (~{len(result) / fps:.1f}s at {fps}fps)")
    return result


def select_fps(input_fn=input) -> int:
    choice = prompt_choice("Choose frame rate:", ["12 fps", "24 fps", "30 fps", "Custom"], input_fn)
    presets = [12, 24, 30]
    if choice < 3:
        return presets[choice]
    return prompt_int("Enter custom fps:", minimum=1, input_fn=input_fn)


def select_format(input_fn=input) -> str:
    choice = prompt_choice("Choose output format:", ["MP4", "GIF", "Both"], input_fn)
    return ["mp4", "gif", "both"][choice]
