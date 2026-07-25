"""Create an atomic storyboard package for human review."""

import json
import shutil
from datetime import datetime
from pathlib import Path

from .exceptions import StoryboardPackageError


def _atomic_write(path, text):
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def create_storyboard_package(
    output_dir,
    product,
    template,
    storyboard,
    asset_report,
    subtitles,
    now=None,
):
    now = now or datetime.now()
    folder = Path(output_dir) / (
        f'{now:%Y%m%d-%H%M%S}_{product["id"]}_{template["id"]}_storyboard'
    )
    try:
        folder.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        raise StoryboardPackageError(f"Не удалось создать папку: {error}") from error
    metadata = {
        "product_id": product["id"],
        "template_id": template["id"],
        "status": "draft",
        "requires_manual_review": True,
        "auto_publish": False,
        "video_generated": False,
        "external_services_used": False,
    }
    shot_list = "\n".join(
        ["# Shot list", ""]
        + [
            (
                f'{scene["scene_number"]}. {scene["purpose"]} — '
                f'{scene["recommended_asset_role"]} — '
                f'{scene["duration_seconds"]:.1f} сек.'
            )
            for scene in storyboard["scenes"]
        ]
    ) + "\n"
    voiceover = "\n".join(
        scene["voiceover"] for scene in storyboard["scenes"]
    ) + "\n"
    review = """# Проверка раскадровки

- [ ] Проверена упаковка
- [ ] Этикетка соответствует реальному товару
- [ ] Проверен готовый напиток
- [ ] Проверены дозировка и количество порций
- [ ] Проверены все тексты на экране
- [ ] Добавлены отсутствующие обязательные материалы
- [ ] Проверены субтитры
- [ ] Разрешено переходить к сборке видео
"""
    files = {
        "storyboard.json": _json_text(storyboard),
        "shot-list.md": shot_list,
        "voiceover.txt": voiceover,
        "subtitles-draft.srt": subtitles,
        "asset-report.json": _json_text(asset_report),
        "metadata.json": _json_text(metadata),
        "review.md": review,
    }
    try:
        for name, text in files.items():
            _atomic_write(folder / name, text)
    except OSError as error:
        shutil.rmtree(folder, ignore_errors=True)
        raise StoryboardPackageError(f"Не удалось записать пакет: {error}") from error
    return folder.resolve()
