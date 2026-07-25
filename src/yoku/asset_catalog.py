"""Load and validate local media manifests without tracking real media files."""

import json
from pathlib import Path, PurePosixPath

from .exceptions import AssetValidationError, CatalogItemNotFoundError
from .product_catalog import ProductCatalog, _validate_id

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".mp4"}


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
        if manifest["schema_version"] != 1:
            raise AssetValidationError("Поддерживается schema_version=1.")
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
            for field in ("filename", "required", "description"):
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
        return manifest

    def list(self):
        return [self.load(path.stem) for path in sorted(self.directory.glob("*.json"))]


def validate_assets(manifest, root):
    root = Path(root)
    found = []
    missing_required = []
    missing_optional = []
    for role, item in manifest["assets"].items():
        relative = PurePosixPath(manifest["base_directory"]) / item["filename"]
        entry = {
            "role": role,
            "path": relative.as_posix(),
            "description": item["description"],
        }
        local_path = root / Path(*relative.parts)
        if local_path.is_file():
            found.append(entry)
        elif item["required"]:
            missing_required.append(entry)
        else:
            missing_optional.append(entry)
    return {
        "status": "COMPLETE" if not missing_required else "INCOMPLETE",
        "product_id": manifest["product_id"],
        "found": found,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "warnings": [],
    }
