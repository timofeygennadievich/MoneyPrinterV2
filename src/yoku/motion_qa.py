"""Technical verification and proof artifacts for encoded campaign videos."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

from .exceptions import MotionRenderError


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_video(path, ffprobe="ffprobe"):
    command = [
        ffprobe,
        "-v", "error",
        "-show_entries",
        (
            "format=duration,size,format_name:"
            "stream=index,codec_type,codec_name,profile,pix_fmt,width,height,"
            "avg_frame_rate,r_frame_rate,nb_frames,sample_rate,channels"
        ),
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "неизвестная ошибка").strip()
        raise MotionRenderError(f"FFprobe завершился с ошибкой: {detail[-1200:]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise MotionRenderError("FFprobe вернул некорректный JSON.") from error


def _rate(value):
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        denominator_value = float(denominator)
        return float(numerator) / denominator_value if denominator_value else 0.0
    return float(value)


def _decode_check(path, ffmpeg):
    command = [
        ffmpeg,
        "-v", "error",
        "-i", str(path),
        "-map", "0:v:0",
        "-f", "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "status": "PASS" if result.returncode == 0 and not result.stderr.strip() else "FAIL",
        "detail": result.stderr.strip(),
    }


def _black_frame_check(path, ffmpeg):
    command = [
        ffmpeg,
        "-hide_banner",
        "-i", str(path),
        "-vf", "blackdetect=d=0.08:pix_th=0.10:pic_th=0.985",
        "-an",
        "-f", "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    matches = re.findall(
        r"black_start:(?P<start>[\d.]+)\s+black_end:(?P<end>[\d.]+)"
        r"\s+black_duration:(?P<duration>[\d.]+)",
        result.stderr,
    )
    intervals = [
        {"start": float(start), "end": float(end), "duration": float(duration)}
        for start, end, duration in matches
    ]
    return {
        "status": "PASS" if result.returncode == 0 and not intervals else "FAIL",
        "intervals": intervals,
    }


def _cover(path, output_path, duration, ffmpeg):
    timestamp = max(0.0, duration - min(1.0, duration * 0.08))
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", f"{timestamp:.3f}",
        "-i", str(path),
        "-frames:v", "1",
        "-vf", "scale=1080:1920:flags=lanczos",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not Path(output_path).is_file():
        detail = (result.stderr or result.stdout or "неизвестная ошибка").strip()
        raise MotionRenderError(f"Не удалось создать обложку: {detail[-1000:]}")


def _contact_sheet(path, output_path, duration, ffmpeg):
    sample_fps = 10.0 / duration
    filter_value = (
        f"fps={sample_fps:.8f},"
        "scale=300:534:force_original_aspect_ratio=decrease,"
        "pad=300:534:(ow-iw)/2:(oh-ih)/2:color=white,"
        "tile=5x2:padding=12:margin=12:color=white"
    )
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(path),
        "-vf", filter_value,
        "-frames:v", "1",
        "-q:v", "2",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not Path(output_path).is_file():
        detail = (result.stderr or result.stdout or "неизвестная ошибка").strip()
        raise MotionRenderError(f"Не удалось создать контактный лист: {detail[-1000:]}")


def create_qa_artifacts(
    video_path,
    profile_id,
    profile,
    output_dir,
    *,
    ffmpeg="ffmpeg",
    ffprobe="ffprobe",
):
    """Validate the encoded MP4 and create its cover, contact sheet and reports."""
    video_path = Path(video_path).resolve()
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise MotionRenderError(f"Готовый MP4 отсутствует или пуст: {video_path}")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    probe = probe_video(video_path, ffprobe)
    video_streams = [
        stream for stream in probe.get("streams", [])
        if stream.get("codec_type") == "video"
    ]
    audio_streams = [
        stream for stream in probe.get("streams", [])
        if stream.get("codec_type") == "audio"
    ]
    if len(video_streams) != 1:
        raise MotionRenderError("Ожидается ровно одна видеодорожка.")
    video = video_streams[0]
    duration = float(probe["format"]["duration"])
    fps = _rate(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    expected_frames = round(float(profile["duration_seconds"]) * float(profile["fps"]))
    actual_frames = int(video.get("nb_frames") or round(duration * fps))
    tolerance = 1 / float(profile["fps"]) + 0.035

    checks = {
        "dimensions": {
            "status": "PASS" if (
                int(video.get("width", 0)) == int(profile["width"])
                and int(video.get("height", 0)) == int(profile["height"])
            ) else "FAIL",
            "actual": [video.get("width"), video.get("height")],
            "expected": [profile["width"], profile["height"]],
        },
        "duration": {
            "status": "PASS" if (
                abs(duration - float(profile["duration_seconds"])) <= tolerance
            ) else "FAIL",
            "actual": duration,
            "expected": profile["duration_seconds"],
            "tolerance": tolerance,
        },
        "fps": {
            "status": "PASS" if abs(fps - float(profile["fps"])) <= 0.01 else "FAIL",
            "actual": fps,
            "expected": profile["fps"],
        },
        "frame_count": {
            "status": "PASS" if abs(actual_frames - expected_frames) <= 1 else "FAIL",
            "actual": actual_frames,
            "expected": expected_frames,
        },
        "codec": {
            "status": "PASS" if video.get("codec_name") == "h264" else "FAIL",
            "actual": video.get("codec_name"),
            "expected": "h264",
        },
        "pixel_format": {
            "status": "PASS" if video.get("pix_fmt") == "yuv420p" else "FAIL",
            "actual": video.get("pix_fmt"),
            "expected": "yuv420p",
        },
        "audio": {
            "status": "PASS" if bool(audio_streams) == bool(profile["audio"]) else "FAIL",
            "actual_streams": len(audio_streams),
            "expected_streams": 1 if profile["audio"] else 0,
            "codec": audio_streams[0].get("codec_name") if audio_streams else None,
        },
        "decode": _decode_check(video_path, ffmpeg),
        "black_frames": _black_frame_check(video_path, ffmpeg),
    }
    status = "PASS" if all(
        check["status"] == "PASS" for check in checks.values()
    ) else "FAIL"

    cover_path = output_dir / f"{video_path.stem}-cover.png"
    contact_sheet_path = output_dir / f"{video_path.stem}-contact-sheet.jpg"
    _cover(video_path, cover_path, duration, ffmpeg)
    _contact_sheet(video_path, contact_sheet_path, duration, ffmpeg)
    report = {
        "schema_version": 1,
        "status": status,
        "platform": profile_id,
        "video_file": video_path.name,
        "sha256": _sha256(video_path),
        "size_bytes": video_path.stat().st_size,
        "probe": probe,
        "checks": checks,
        "visual_review": {
            "status": "PENDING",
            "contact_sheet": contact_sheet_path.name,
            "cover": cover_path.name,
        },
    }
    json_path = output_dir / f"{video_path.stem}-qa.json"
    markdown_path = output_dir / f"{video_path.stem}-qa.md"
    json_path.write_text(_json_text(report), encoding="utf-8")
    lines = [
        f"# QA — {video_path.name}",
        "",
        f"Technical status: **{status}**",
        "",
        f"- Platform: {profile['label']}",
        f"- Resolution: {video.get('width')}×{video.get('height')}",
        f"- Duration: {duration:.3f} s",
        f"- FPS: {fps:.3f}",
        f"- Frames: {actual_frames}",
        f"- Codec: {video.get('codec_name')} / {video.get('profile')}",
        f"- Pixel format: {video.get('pix_fmt')}",
        f"- Audio tracks: {len(audio_streams)}",
        f"- SHA-256: `{report['sha256']}`",
        "",
        "Visual review: **PENDING**",
        "",
        f"- Cover: `{cover_path.name}`",
        f"- Contact sheet: `{contact_sheet_path.name}`",
    ]
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "status": status,
        "report": report,
        "json": str(json_path),
        "markdown": str(markdown_path),
        "cover": str(cover_path),
        "contact_sheet": str(contact_sheet_path),
    }


def mark_visual_review(qa_json_path, notes):
    """Record a completed human/agent visual review beside technical QA."""
    qa_json_path = Path(qa_json_path).resolve()
    if not isinstance(notes, list) or not notes or not all(
        isinstance(note, str) and note.strip() for note in notes
    ):
        raise MotionRenderError("Visual review требует непустой список заметок.")
    try:
        report = json.loads(qa_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MotionRenderError(f"Не удалось прочитать QA JSON: {error}") from error
    if report.get("status") != "PASS":
        raise MotionRenderError(
            "Visual review нельзя подтвердить до успешного технического QA."
        )
    visual = report.get("visual_review")
    if not isinstance(visual, dict):
        raise MotionRenderError("QA JSON не содержит visual_review.")
    visual.update(
        {
            "status": "PASS",
            "reviewer": "Codex visual inspection",
            "notes": [note.strip() for note in notes],
        }
    )
    qa_json_path.write_text(_json_text(report), encoding="utf-8")
    markdown_path = qa_json_path.with_suffix(".md")
    if markdown_path.is_file():
        markdown = markdown_path.read_text(encoding="utf-8")
        markdown = markdown.replace(
            "Visual review: **PENDING**",
            "Visual review: **PASS**",
        )
        markdown += "\nVisual notes:\n\n" + "\n".join(
            f"- {note.strip()}" for note in notes
        ) + "\n"
        markdown_path.write_text(markdown, encoding="utf-8")
    return report
