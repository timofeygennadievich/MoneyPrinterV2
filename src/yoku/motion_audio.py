"""Generate a quiet deterministic SFX master with no third-party music."""

import math
import random
import wave
from array import array
from pathlib import Path

from .exceptions import MotionRenderError

SAMPLE_RATE = 44_100
SEED = 20_260_726


def _add_tone(buffer, start, duration, frequency, amplitude, *, sweep=0.0):
    start_index = max(0, int(start * SAMPLE_RATE))
    count = max(1, int(duration * SAMPLE_RATE))
    for offset in range(count):
        index = start_index + offset
        if index >= len(buffer):
            break
        progress = offset / count
        envelope = math.sin(math.pi * progress) ** 2
        phase = 2 * math.pi * (
            frequency * (offset / SAMPLE_RATE)
            + 0.5 * sweep * (offset / SAMPLE_RATE) ** 2
        )
        buffer[index] += amplitude * envelope * math.sin(phase)


def _add_click(buffer, start, frequency=1750.0, amplitude=0.24):
    start_index = max(0, int(start * SAMPLE_RATE))
    count = int(0.14 * SAMPLE_RATE)
    for offset in range(count):
        index = start_index + offset
        if index >= len(buffer):
            break
        seconds = offset / SAMPLE_RATE
        envelope = math.exp(-34 * seconds)
        signal = (
            math.sin(2 * math.pi * frequency * seconds)
            + 0.42 * math.sin(2 * math.pi * frequency * 1.62 * seconds)
        )
        buffer[index] += amplitude * envelope * signal


def _add_whoosh(buffer, start, duration, amplitude, rng):
    start_index = max(0, int(start * SAMPLE_RATE))
    count = max(1, int(duration * SAMPLE_RATE))
    previous = 0.0
    for offset in range(count):
        index = start_index + offset
        if index >= len(buffer):
            break
        progress = offset / count
        envelope = math.sin(math.pi * progress) ** 2
        noise = rng.uniform(-1.0, 1.0)
        previous = 0.86 * previous + 0.14 * noise
        carrier = math.sin(2 * math.pi * (130 + 520 * progress) * offset / SAMPLE_RATE)
        buffer[index] += amplitude * envelope * (0.72 * previous + 0.28 * carrier)


def _add_sprinkle(buffer, start, duration, amplitude, rng):
    event_count = max(5, int(duration * 18))
    for event in range(event_count):
        event_start = start + (event + 0.4 * rng.random()) * duration / event_count
        frequency = 820 + 1700 * rng.random()
        _add_click(buffer, event_start, frequency=frequency, amplitude=amplitude)


def create_sfx_track(profile, output_path):
    """Create subtle original SFX; the video remains fully understandable muted."""
    if not profile.get("audio"):
        return None
    duration = float(profile["duration_seconds"])
    if duration <= 0:
        raise MotionRenderError("Нельзя создать SFX для неположительной длительности.")
    samples = [0.0] * int(math.ceil(duration * SAMPLE_RATE))
    rng = random.Random(SEED)
    beats = profile["beats"]

    _add_whoosh(samples, beats["hook"]["start"] + 0.12, 0.75, 0.10, rng)
    _add_tone(
        samples,
        beats["hook"]["start"] + 0.28,
        0.34,
        330,
        0.09,
        sweep=440,
    )
    _add_whoosh(samples, beats["packshot"]["start"] + 0.08, 0.72, 0.11, rng)
    _add_click(samples, beats["packshot"]["start"] + 0.46, 960, 0.18)
    _add_sprinkle(
        samples,
        beats["transformation"]["start"] + 0.20,
        min(1.2, beats["transformation"]["duration"] * 0.34),
        0.035,
        rng,
    )
    ice_time = beats["transformation"]["start"] + beats["transformation"]["duration"] * 0.68
    for offset, frequency in ((0.0, 1500), (0.11, 2050), (0.24, 1280)):
        _add_click(samples, ice_time + offset, frequency, 0.15)
    _add_whoosh(samples, beats["facts"]["start"] + 0.04, 0.45, 0.08, rng)
    _add_click(samples, beats["facts"]["start"] + 0.35, 720, 0.14)
    _add_click(samples, beats["facts"]["start"] + 0.82, 860, 0.13)
    _add_tone(
        samples,
        beats["final"]["start"] + 0.18,
        min(1.1, beats["final"]["duration"] * 0.42),
        392,
        0.09,
        sweep=196,
    )

    peak = max((abs(value) for value in samples), default=0.0)
    scale = 0.78 / peak if peak > 0.78 else 1.0
    pcm = array("h")
    for sample in samples:
        value = int(max(-1.0, min(1.0, sample * scale)) * 32767)
        pcm.append(value)
        pcm.append(value)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(pcm.tobytes())
    return output_path.resolve()
