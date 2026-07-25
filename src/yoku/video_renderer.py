"""Render a local vertical MP4 from approved storyboard assets only."""

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .exceptions import VideoRenderError

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _inside_root(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def build_render_plan(storyboard, root, width=1080, height=1920, fps=30):
    """Resolve and validate every approved image used by the storyboard."""
    root = Path(root).resolve()
    if width <= 0 or height <= 0 or fps <= 0:
        raise VideoRenderError("Размеры кадра и fps должны быть положительными.")
    scenes = []
    for scene in storyboard["scenes"]:
        if not scene.get("asset_exists"):
            raise VideoRenderError(
                f'Сцена {scene["scene_number"]}: файл ассета отсутствует.'
            )
        if not scene.get("asset_approved"):
            raise VideoRenderError(
                f'Сцена {scene["scene_number"]}: ассет не утверждён.'
            )
        asset_path = scene.get("asset_path")
        if not isinstance(asset_path, str) or not asset_path:
            raise VideoRenderError(
                f'Сцена {scene["scene_number"]}: путь ассета отсутствует.'
            )
        local_path = (root / asset_path).resolve()
        if not _inside_root(local_path, root):
            raise VideoRenderError("Путь ассета выходит за пределы корневой папки.")
        if local_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise VideoRenderError(
                f"Для слайдового MP4 разрешены только изображения: {local_path.suffix}"
            )
        if not local_path.is_file():
            raise VideoRenderError(f"Файл ассета не найден: {asset_path}")
        duration = scene.get("duration_seconds")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 1.5:
            raise VideoRenderError("Длительность каждой сцены должна быть не меньше 1.5 сек.")
        scenes.append({
            "scene_number": scene["scene_number"],
            "asset_role": scene["recommended_asset_role"],
            "asset_path": asset_path,
            "local_path": str(local_path),
            "duration_seconds": round(float(duration), 1),
            "source_type": scene.get("asset_source_type", "unknown"),
        })
    if not scenes:
        raise VideoRenderError("Раскадровка не содержит сцен.")
    return {
        "product_id": storyboard["product_id"],
        "template_id": storyboard["template_id"],
        "width": int(width),
        "height": int(height),
        "fps": int(fps),
        "background": "0xF7F4EE",
        "total_duration_seconds": round(
            sum(scene["duration_seconds"] for scene in scenes), 1
        ),
        "scenes": scenes,
    }


def _ffconcat_text(plan):
    lines = ["ffconcat version 1.0"]
    for scene in plan["scenes"]:
        escaped = scene["local_path"].replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
        lines.append(f'duration {scene["duration_seconds"]:.1f}')
    last = plan["scenes"][-1]["local_path"].replace("'", "'\\''")
    lines.append(f"file '{last}'")
    return "\n".join(lines) + "\n"


def build_ffmpeg_command(ffmpeg, concat_path, output_path, plan):
    filter_value = (
        f'scale={plan["width"]}:{plan["height"]}:'
        'force_original_aspect_ratio=decrease,'
        f'pad={plan["width"]}:{plan["height"]}:'
        '(ow-iw)/2:(oh-ih)/2:'
        f'color={plan["background"]},format=yuv420p'
    )
    return [
        ffmpeg,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_path),
        "-vf", filter_value,
        "-r", str(plan["fps"]),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        str(output_path),
    ]


def create_video_package(
    output_dir,
    product,
    template,
    storyboard,
    assets_root,
    *,
    ffmpeg="ffmpeg",
    width=1080,
    height=1920,
    fps=30,
    now=None,
    dry_run=False,
):
    """Create an atomic local render package; never publish it."""
    plan = build_render_plan(storyboard, assets_root, width, height, fps)
    now = now or datetime.now()
    folder = Path(output_dir) / (
        f'{now:%Y%m%d-%H%M%S}_{product["id"]}_{template["id"]}_video'
    )
    try:
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "render-plan.json").write_text(_json_text(plan), encoding="utf-8")
        concat_path = folder / ".slides.ffconcat"
        concat_path.write_text(_ffconcat_text(plan), encoding="utf-8")
        output_path = folder / "video.mp4"
        metadata = {
            "product_id": product["id"],
            "template_id": template["id"],
            "status": "draft",
            "requires_manual_review": True,
            "auto_publish": False,
            "video_generated": False,
            "audio_generated": False,
            "external_services_used": False,
            "render_mode": "approved_final_slides",
            "width": width,
            "height": height,
            "fps": fps,
        }
        if not dry_run:
            executable = shutil.which(ffmpeg)
            if executable is None:
                raise VideoRenderError("FFmpeg не найден в PATH.")
            command = build_ffmpeg_command(executable, concat_path, output_path, plan)
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if result.returncode != 0 or not output_path.is_file():
                detail = (result.stderr or result.stdout or "неизвестная ошибка").strip()
                raise VideoRenderError(f"FFmpeg завершился с ошибкой: {detail[-1200:]}")
            metadata["video_generated"] = True
            metadata["video_file"] = output_path.name
        (folder / "metadata.json").write_text(_json_text(metadata), encoding="utf-8")
        (folder / "review.md").write_text(
            "# Проверка видео\n\n"
            "- [ ] Проверено соответствие упаковки SKU\n"
            "- [ ] Проверены все финальные слайды\n"
            "- [ ] Проверена длительность сцен\n"
            "- [ ] Проверена читаемость текста\n"
            "- [ ] Проверено отсутствие обрезки\n"
            "- [ ] Разрешена публикация вручную\n",
            encoding="utf-8",
        )
        concat_path.unlink(missing_ok=True)
        return folder.resolve()
    except (OSError, subprocess.SubprocessError, VideoRenderError) as error:
        shutil.rmtree(folder, ignore_errors=True)
        if isinstance(error, VideoRenderError):
            raise
        raise VideoRenderError(f"Не удалось создать видео-пакет: {error}") from error
