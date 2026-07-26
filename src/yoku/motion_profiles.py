"""Load and validate deterministic platform profiles for Motion Renderer v2."""

import json
from copy import deepcopy
from pathlib import Path

from .exceptions import MotionRenderError

PLATFORM_ALIASES = {
    "instagram": "reels",
    "instagram-reels": "reels",
    "youtube": "shorts",
    "youtube-shorts": "shorts",
}
REQUIRED_BEATS = ("hook", "packshot", "transformation", "facts", "final")


def _positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _validate_profile(profile_id, profile):
    if not isinstance(profile, dict):
        raise MotionRenderError(f"Профиль {profile_id} должен быть JSON-объектом.")
    for field in ("label", "width", "height", "fps", "duration_seconds", "audio"):
        if field not in profile:
            raise MotionRenderError(f"В профиле {profile_id} отсутствует поле {field}.")
    for field in ("width", "height", "fps", "duration_seconds"):
        if not _positive_number(profile[field]):
            raise MotionRenderError(
                f"Поле {field} профиля {profile_id} должно быть положительным числом."
            )
    if not isinstance(profile["audio"], bool):
        raise MotionRenderError(f"Поле audio профиля {profile_id} должно быть bool.")
    safe_zone = profile.get("safe_zone")
    if not isinstance(safe_zone, dict) or set(safe_zone) != {
        "top", "right", "bottom", "left"
    }:
        raise MotionRenderError(f"Профиль {profile_id}: некорректная safe_zone.")
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in safe_zone.values()
    ):
        raise MotionRenderError(
            f"Профиль {profile_id}: значения safe_zone должны быть целыми >= 0."
        )
    if safe_zone["left"] + safe_zone["right"] >= profile["width"]:
        raise MotionRenderError(f"Профиль {profile_id}: горизонтальная safe_zone слишком велика.")
    if safe_zone["top"] + safe_zone["bottom"] >= profile["height"]:
        raise MotionRenderError(f"Профиль {profile_id}: вертикальная safe_zone слишком велика.")

    beats = profile.get("beats")
    if not isinstance(beats, dict) or tuple(beats) != REQUIRED_BEATS:
        raise MotionRenderError(
            f"Профиль {profile_id}: beats должны идти в порядке "
            f"{', '.join(REQUIRED_BEATS)}."
        )
    previous_start = -1.0
    previous_end = 0.0
    for beat_id in REQUIRED_BEATS:
        beat = beats[beat_id]
        if not isinstance(beat, dict):
            raise MotionRenderError(f"Профиль {profile_id}: beat {beat_id} некорректен.")
        start = beat.get("start")
        duration = beat.get("duration")
        if (
            not isinstance(start, (int, float))
            or isinstance(start, bool)
            or start < 0
            or not _positive_number(duration)
        ):
            raise MotionRenderError(
                f"Профиль {profile_id}: beat {beat_id} имеет неверное время."
            )
        if start < previous_start:
            raise MotionRenderError(
                f"Профиль {profile_id}: beat {beat_id} нарушает порядок сцен."
            )
        if start < previous_end - 0.001:
            raise MotionRenderError(
                f"Профиль {profile_id}: beat {beat_id} пересекается "
                "с предыдущей сценой."
            )
        if start + duration > profile["duration_seconds"] + 0.001:
            raise MotionRenderError(
                f"Профиль {profile_id}: beat {beat_id} выходит за длительность."
            )
        previous_start = start
        previous_end = start + duration
    final_end = beats["final"]["start"] + beats["final"]["duration"]
    if abs(final_end - profile["duration_seconds"]) > 0.001:
        raise MotionRenderError(
            f"Профиль {profile_id}: финальный beat должен заканчиваться "
            "ровно вместе с роликом."
        )


def load_platform_profiles(path):
    """Load the versioned profile file and return validated profile dictionaries."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MotionRenderError(f"Не удалось прочитать профили платформ: {error}") from error
    if payload.get("schema_version") != 1:
        raise MotionRenderError("Поддерживается schema_version=1 профилей платформ.")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise MotionRenderError("Файл профилей не содержит profiles.")
    for profile_id, profile in profiles.items():
        _validate_profile(profile_id, profile)
    return deepcopy(profiles)


def normalize_platforms(value, profiles):
    """Normalize a comma-separated platform list while preserving user order."""
    if isinstance(value, str):
        requested = [item.strip().lower() for item in value.split(",") if item.strip()]
    else:
        requested = [str(item).strip().lower() for item in value if str(item).strip()]
    if not requested:
        raise MotionRenderError("Нужно указать хотя бы одну платформу.")
    normalized = []
    for item in requested:
        profile_id = PLATFORM_ALIASES.get(item, item)
        if profile_id not in profiles:
            allowed = ", ".join(sorted(profiles))
            raise MotionRenderError(
                f"Неизвестная платформа {item}. Доступны: {allowed}."
            )
        if profile_id not in normalized:
            normalized.append(profile_id)
    return normalized
