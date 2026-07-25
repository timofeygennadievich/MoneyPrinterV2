"""Load, validate and inspect approved local media manifests."""

import json
import struct
from pathlib import Path, PurePosixPath

from .exceptions import AssetValidationError, CatalogItemNotFoundError
from .product_catalog import _validate_id

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".mp4"}
APPROVED_SOURCE_TYPES = {
    "approved_final_slide",
    "approved_packshot",
    "approved_photo",
    "approved_video",
}
SUPPORTED_SCHEMA_VERSIONS = {1, 2}


def _safe_relative_path(value, *, field):
    if not isinstance(value, str) or not value.strip():
        raise AssetValidationError(f"{field} должен быть непустой строкой.")
    if "\\" in value:
        raise AssetValidationError(f"{field} не должен содержать обратные слеши.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", "..") for part in path.parts):
        raise AssetValidationError(f"{field} должен быть безопасным относительным путём.")
    return path


def _validate_filename(value):
    path = _safe_relative_path(value, field="filename")
    if len(path.parts) != 1 or value.startswith("."):
        raise AssetValidationError(
            "filename должен быть обычным именем файла без каталогов и скрытых файлов."
        )
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise AssetValidationError(f"Недопустимое расширение файла: {path.suffix}")
    return value


def _png_dimensions(path):
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Некорректный PNG-файл.")
    return struct.unpack(">II", header[16:24])


def _jpeg_dimensions(path):
    with path.open("rb") as stream:
        if stream.read(2) != b"\xff\xd8":
            raise ValueError("Некорректный JPEG-файл.")
        while True:
            byte = stream.read(1)
            if not byte:
                break
            if byte != b"\xff":
                continue
            marker = stream.read(1)
            while marker == b"\xff":
                marker = stream.read(1)
            if marker in {b"\xd8", b"\xd9"}:
                continue
            length_bytes = stream.read(2)
            if len(length_bytes) != 2:
                break
            length = struct.unpack(">H", length_bytes)[0]
            if marker in {
                b"\xc0", b"\xc1", b"\xc2", b"\xc3", b"\xc5", b"\xc6",
                b"\xc7", b"\xc9", b"\xca", b"\xcb", b"\xcd", b"\xce", b"\xcf",
            }:
                data = stream.read(5)
                if len(data) != 5:
                    break
                height, width = struct.unpack(">HH", data[1:5])
                return width, height
            stream.seek(max(length - 2, 0), 1)
    raise ValueError("Не удалось определить размеры JPEG-файла.")


def inspect_asset(path):
    """Return deterministic local metadata without external libraries."""
    path = Path(path)
    suffix = path.suffix.lower()
    result = {"size_bytes": path.stat().st_size, "extension": suffix}
    if suffix == ".png":
        width, height = _png_dimensions(path)
    elif suffix in {".jpg", ".jpeg"}:
        width, height = _jpeg_dimensions(path)
    else:
        return result
    result.update({
        "width": width,
        "height": height,
        "aspect_ratio": round(width / height, 4) if height else None,
    })
    return result


class AssetCatalog:
    def __init__(self, directory, product_catalog):
        self.directory = Path(directory)
        self.product_catalog = product_catalog

    def load(self, product_id):
        _validate_id(product_id)
        path = self.directory / f"{product_id}.json"
        if not path.is_file():
            raise CatalogItemNotFoundError(f"Медиаманифест не найден: {product_id}")
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise AssetValidationError(
                f"Не удалось прочитать медиаманифест {product_id}: {error}"
            ) from error
        if not isinstance(manifest, dict):
            raise AssetValidationError("Медиаманифест должен быть JSON-объектом.")
        for field in ("schema_version", "product_id", "base_directory", "assets"):
            if field not in manifest:
                raise AssetValidationError(f"В медиаманифесте отсутствует поле: {field}")
        schema_version = manifest["schema_version"]
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise AssetValidationError("Поддерживаются schema_version=1 и schema_version=2.")
        if manifest["product_id"] != product_id:
            raise AssetValidationError("product_id не совпадает с именем файла.")
        self.product_catalog.load(product_id)
        base = _safe_relative_path(manifest["base_directory"], field="base_directory")
        expected = PurePosixPath("assets/yoku/products") / product_id
        if base != expected:
            raise AssetValidationError(
                f"base_directory должен быть {expected.as_posix()}."
            )
        assets = manifest["assets"]
        if not isinstance(assets, dict) or not assets:
            raise AssetValidationError("assets должен быть непустым объектом.")
        for role, item in assets.items():
            _validate_id(role.replace("_", "-"))
            if not isinstance(item, dict):
                raise AssetValidationError(f"Материал {role} должен быть объектом.")
            required_fields = {"filename", "required", "description"}
            if schema_version >= 2:
                required_fields.update({"approved", "source_type"})
            for field in sorted(required_fields):
                if field not in item:
                    raise AssetValidationError(
                        f"У материала {role} отсутствует поле {field}."
                    )
            _validate_filename(item["filename"])
            if not isinstance(item["required"], bool):
                raise AssetValidationError(
                    f"required материала {role} должен быть bool."
                )
            if not isinstance(item["description"], str) or not item["description"].strip():
                raise AssetValidationError(
                    f"description материала {role} должен быть непустой строкой."
                )
            if schema_version >= 2:
                if item["approved"] is not True:
                    raise AssetValidationError(
                        f"Материал {role} должен быть явно утверждён: approved=true."
                    )
                if item["source_type"] not in APPROVED_SOURCE_TYPES:
                    raise AssetValidationError(
                        f"Недопустимый source_type материала {role}: {item['source_type']}"
                    )
        return manifest

    def list(self):
        return [self.load(path.stem) for path in sorted(self.directory.glob("*.json"))]


def validate_assets(manifest, root):
    root = Path(root)
    found = []
    missing_required = []
    missing_optional = []
    warnings = []
    for role, item in manifest["assets"].items():
        relative = PurePosixPath(manifest["base_directory"]) / item["filename"]
        entry = {
            "role": role,
            "path": relative.as_posix(),
            "description": item["description"],
            "approved": item.get("approved", False),
            "source_type": item.get("source_type", "legacy_manifest"),
        }
        local_path = root / Path(*relative.parts)
        if local_path.is_file():
            try:
                entry["inspection"] = inspect_asset(local_path)
            except (OSError, ValueError) as error:
                warnings.append(f"{role}: не удалось проверить файл: {error}")
            found.append(entry)
        elif item["required"]:
            missing_required.append(entry)
        else:
            missing_optional.append(entry)
    if manifest["schema_version"] < 2:
        warnings.append("Используется legacy-манифест без явного утверждения ассетов.")
    return {
        "status": "COMPLETE" if not missing_required else "INCOMPLETE",
        "product_id": manifest["product_id"],
        "found": found,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "warnings": warnings,
    }
