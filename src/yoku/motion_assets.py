"""Prepare and verify approved layered assets for Motion Renderer v2."""

import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath

from .asset_catalog import inspect_asset
from .exceptions import MotionAssetError

MOTION_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
REQUIRED_MOTION_ROLES = ("logo", "drink", "packshot", "powder", "toppings")


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_filename(value):
    if not isinstance(value, str) or not value:
        raise MotionAssetError("Имя motion-ассета должно быть непустой строкой.")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or len(path.parts) != 1
        or any(part in ("", "..") for part in path.parts)
        or value.startswith(".")
        or "\\" in value
    ):
        raise MotionAssetError(f"Небезопасное имя motion-ассета: {value}")
    if path.suffix.lower() not in MOTION_IMAGE_EXTENSIONS:
        raise MotionAssetError(f"Недопустимый формат motion-ассета: {path.suffix}")
    return value


def _load_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MotionAssetError(f"Не удалось прочитать {label}: {error}") from error


def _probe_reference(reference_video, ffprobe):
    command = [
        ffprobe,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json",
        str(reference_video),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "неизвестная ошибка").strip()
        raise MotionAssetError(f"FFprobe не смог проверить референс: {detail[-1000:]}")
    try:
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
        duration = float(payload["format"]["duration"])
        width = int(stream["width"])
        height = int(stream["height"])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise MotionAssetError("FFprobe вернул неполные данные о референсе.") from error
    return {"duration": duration, "width": width, "height": height}


def prepare_motion_assets_from_reference(
    reference_video,
    extraction_spec_path,
    output_dir,
    *,
    ffmpeg="ffmpeg",
    ffprobe="ffprobe",
    overwrite=False,
):
    """Extract object crops from an approved pilot without redrawing product art."""
    reference_video = Path(reference_video).resolve()
    if not reference_video.is_file():
        raise MotionAssetError(f"Референсное видео не найдено: {reference_video}")
    spec = _load_json(extraction_spec_path, "спецификацию извлечения")
    if spec.get("schema_version") != 1:
        raise MotionAssetError("Поддерживается schema_version=1 извлечения ассетов.")
    product_id = spec.get("product_id")
    assets_spec = spec.get("assets")
    if not isinstance(product_id, str) or not isinstance(assets_spec, dict):
        raise MotionAssetError("Спецификация извлечения не содержит product_id/assets.")
    if tuple(assets_spec) != REQUIRED_MOTION_ROLES:
        raise MotionAssetError(
            "Спецификация должна содержать роли: "
            + ", ".join(REQUIRED_MOTION_ROLES)
        )

    reference = _probe_reference(reference_video, ffprobe)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists() and not overwrite:
        return load_motion_assets(output_dir, expected_product_id=product_id)

    manifest_assets = {}
    for role in REQUIRED_MOTION_ROLES:
        item = assets_spec[role]
        filename = _safe_filename(item.get("filename"))
        timestamp = item.get("timestamp_seconds")
        crop = item.get("crop")
        if (
            not isinstance(timestamp, (int, float))
            or isinstance(timestamp, bool)
            or timestamp < 0
            or timestamp > reference["duration"]
        ):
            raise MotionAssetError(f"Роль {role}: неверный timestamp_seconds.")
        if not isinstance(crop, dict) or set(crop) != {"width", "height", "x", "y"}:
            raise MotionAssetError(f"Роль {role}: crop должен содержать width/height/x/y.")
        if not all(
            isinstance(crop[key], int)
            and not isinstance(crop[key], bool)
            and crop[key] >= (1 if key in {"width", "height"} else 0)
            for key in crop
        ):
            raise MotionAssetError(f"Роль {role}: crop содержит неверные значения.")
        if crop["x"] + crop["width"] > reference["width"] or (
            crop["y"] + crop["height"] > reference["height"]
        ):
            raise MotionAssetError(f"Роль {role}: crop выходит за границы видео.")

        target = output_dir / filename
        if target.exists() and not overwrite:
            raise MotionAssetError(
                f"Файл уже существует без --overwrite: {target.name}"
            )
        filter_value = (
            f'crop={crop["width"]}:{crop["height"]}:{crop["x"]}:{crop["y"]},'
            "format=rgba"
        )
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-ss", f"{float(timestamp):.3f}",
            "-i", str(reference_video),
            "-frames:v", "1",
            "-vf", filter_value,
            str(target),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
            detail = (result.stderr or result.stdout or "неизвестная ошибка").strip()
            raise MotionAssetError(
                f"Не удалось извлечь ассет {role}: {detail[-1000:]}"
            )
        manifest_assets[role] = {
            "filename": filename,
            "approved": True,
            "source_type": spec["source_kind"],
            "sha256": _sha256(target),
            "inspection": inspect_asset(target),
        }

    manifest = {
        "schema_version": 1,
        "product_id": product_id,
        "source_reference": reference_video.name,
        "source_sha256": _sha256(reference_video),
        "source_inspection": reference,
        "assets": manifest_assets,
    }
    manifest_path.write_text(_json_text(manifest), encoding="utf-8")
    return {
        "root": str(output_dir),
        "manifest": manifest,
        "paths": {
            role: str(output_dir / manifest_assets[role]["filename"])
            for role in REQUIRED_MOTION_ROLES
        },
    }


def load_motion_assets(root, *, expected_product_id=None):
    """Validate approval flags, paths and hashes for a prepared motion asset pack."""
    root = Path(root).resolve()
    manifest_path = root / "manifest.json"
    manifest = _load_json(manifest_path, "motion manifest")
    if manifest.get("schema_version") != 1:
        raise MotionAssetError("Поддерживается schema_version=1 motion manifest.")
    if expected_product_id and manifest.get("product_id") != expected_product_id:
        raise MotionAssetError(
            "Motion manifest относится к другому SKU: "
            f'{manifest.get("product_id")} вместо {expected_product_id}.'
        )
    assets = manifest.get("assets")
    if not isinstance(assets, dict) or tuple(assets) != REQUIRED_MOTION_ROLES:
        raise MotionAssetError(
            "Motion manifest должен содержать роли: "
            + ", ".join(REQUIRED_MOTION_ROLES)
        )
    paths = {}
    for role in REQUIRED_MOTION_ROLES:
        item = assets[role]
        if not isinstance(item, dict) or item.get("approved") is not True:
            raise MotionAssetError(f"Motion-ассет {role} не утверждён.")
        filename = _safe_filename(item.get("filename"))
        path = (root / filename).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise MotionAssetError(f"Motion-ассет {role} выходит за пределы root.") from error
        if not path.is_file():
            raise MotionAssetError(f"Motion-ассет {role} не найден: {filename}")
        if _sha256(path) != item.get("sha256"):
            raise MotionAssetError(f"Контрольная сумма motion-ассета {role} не совпала.")
        paths[role] = str(path)
    return {"root": str(root), "manifest": manifest, "paths": paths}
