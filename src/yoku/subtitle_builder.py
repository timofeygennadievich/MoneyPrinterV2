"""Build draft SRT subtitles from storyboard scene timings."""


def _stamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def build_srt(storyboard):
    lines = []
    cursor = 0.0
    for scene in storyboard["scenes"]:
        end = round(cursor + scene["duration_seconds"], 3)
        lines.extend([
            str(scene["scene_number"]),
            f"{_stamp(cursor)} --> {_stamp(end)}",
            scene["voiceover"],
            "",
        ])
        cursor = end
    return "\n".join(lines).rstrip() + "\n"
