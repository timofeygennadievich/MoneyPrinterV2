"""Load and validate safe local content templates."""

import json
from pathlib import Path
from string import Formatter

from .exceptions import CatalogItemNotFoundError, CatalogValidationError
from .product_catalog import _validate_id

REQUIRED_FIELDS = {
    "schema_version", "id", "format", "purpose", "language", "hook_template",
    "scene_templates", "cta_template", "target_duration_seconds",
    "requires_manual_review", "auto_publish", "intended_channels",
    "script_sentences",
}
ALLOWED_PLACEHOLDERS = {
    "product_name", "brand", "servings", "package_weight_g",
    "dosage_g_per_drink", "drink_volume_ml", "country_of_origin",
    "positioning", "cta",
}


def _validate_script_sentences(sentences):
    if not isinstance(sentences, list) or not sentences or not all(
        isinstance(sentence, str) and sentence.strip() for sentence in sentences
    ):
        raise CatalogValidationError("script_sentences должен быть непустым списком непустых строк.")
    formatter = Formatter()
    for sentence in sentences:
        try:
            fields = formatter.parse(sentence)
            for _, field_name, format_spec, conversion in fields:
                if field_name is not None and field_name not in ALLOWED_PLACEHOLDERS:
                    raise CatalogValidationError(
                        f"Недопустимый placeholder в script_sentences: {field_name}"
                    )
                if field_name is not None and (format_spec or conversion):
                    raise CatalogValidationError(
                        "Форматирование и преобразование placeholders запрещены."
                    )
        except ValueError as error:
            raise CatalogValidationError(
                f"Некорректный placeholder в script_sentences: {error}"
            ) from error


class TemplateCatalog:
    def __init__(self, directory):
        self.directory = Path(directory)

    def load(self, template_id):
        _validate_id(template_id)
        path = self.directory / f"{template_id}.json"
        if not path.is_file():
            raise CatalogItemNotFoundError(f"Шаблон не найден: {template_id}")
        try:
            with path.open("r", encoding="utf-8") as stream:
                template = json.load(stream)
        except (json.JSONDecodeError, OSError) as error:
            raise CatalogValidationError(f"Не удалось прочитать шаблон {template_id}: {error}") from error
        if not isinstance(template, dict):
            raise CatalogValidationError("Шаблон должен быть JSON-объектом.")
        missing = sorted(REQUIRED_FIELDS - template.keys())
        if missing:
            raise CatalogValidationError(f"В шаблоне отсутствуют поля: {', '.join(missing)}")
        if template["id"] != template_id:
            raise CatalogValidationError("ID внутри шаблона не совпадает с именем файла.")
        if template["schema_version"] != 1:
            raise CatalogValidationError("schema_version шаблона должен быть равен 1.")
        for field in ("format", "purpose", "language", "hook_template", "cta_template"):
            if not isinstance(template[field], str) or not template[field].strip():
                raise CatalogValidationError(f"Поле {field} должно быть непустой строкой.")
        channels = template["intended_channels"]
        if not isinstance(channels, list) or not channels or not all(isinstance(channel, str) and channel.strip() for channel in channels):
            raise CatalogValidationError("intended_channels должен быть непустым списком непустых строк.")
        duration = template["target_duration_seconds"]
        if (
            not isinstance(duration, dict)
            or set(("min", "max")) - duration.keys()
            or not all(isinstance(duration[key], (int, float)) and not isinstance(duration[key], bool) for key in ("min", "max"))
            or duration["min"] <= 0
            or duration["min"] >= duration["max"]
        ):
            raise CatalogValidationError("Длительность должна содержать положительные min и max, где min < max.")
        scenes = template["scene_templates"]
        if not isinstance(scenes, list) or not scenes or not all(isinstance(scene, str) and scene.strip() for scene in scenes):
            raise CatalogValidationError("scene_templates должен быть непустым списком строк.")
        _validate_script_sentences(template["script_sentences"])
        if template["requires_manual_review"] is not True:
            raise CatalogValidationError("Для шаблона обязательно ручное согласование.")
        if template["auto_publish"] is not False:
            raise CatalogValidationError("Автоматическая публикация должна быть отключена.")
        return template

    def list(self):
        """Return every valid content template, ordered by its identifier."""
        return [self.load(path.stem) for path in sorted(self.directory.glob("*.json"))]


def load_template(template_id, directory):
    return TemplateCatalog(directory).load(template_id)
