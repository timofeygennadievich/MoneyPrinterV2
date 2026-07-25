"""Build deterministic storyboards from validated scripts and media manifests."""

from pathlib import PurePosixPath

ROLE_RULES = (
    (("готов", "результат", "напиток крупным"), "drink_hero"),
    (("упаков", "порци"), "packshot_front"),
    (("приготов", "инструкц"), "preparation_01"),
    (("детал",), "product_detail"),
)


def _role_for(purpose, index):
    text = purpose.casefold()
    for keywords, role in ROLE_RULES:
        if any(keyword in text for keyword in keywords):
            return role
    return "product_detail" if index else "drink_hero"


def _durations(texts, minimum, maximum):
    scene_floor = 1.5
    scene_count = len(texts)
    estimated = round(sum(max(len(text), 1) for text in texts) / 13, 1)
    target = min(maximum, max(minimum, estimated, scene_count * scene_floor))
    weights = [max(len(text), 1) for text in texts]
    remaining = target - scene_count * scene_floor
    total_weight = sum(weights)
    values = [
        scene_floor + (remaining * weight / total_weight if total_weight else 0)
        for weight in weights
    ]
    rounded = [round(value, 1) for value in values]
    rounded[-1] = round(rounded[-1] + round(target - sum(rounded), 1), 1)
    return rounded


def build_storyboard(product, template, script_result, manifest, asset_report):
    sentences = template["script_sentences"]
    purposes = list(template["scene_templates"])
    if len(purposes) != len(sentences):
        purposes = (purposes + ["Проверить сцену вручную."] * len(sentences))[:len(sentences)]
    substitutions = {
        "product_name": product["name"],
        "brand": product["brand"],
        "servings": product["servings"],
        "package_weight_g": product["package_weight_g"],
        "dosage_g_per_drink": product["dosage_g_per_drink"],
        "drink_volume_ml": product["drink_volume_ml"],
        "country_of_origin": product["country_of_origin"],
        "positioning": product["positioning"],
        "cta": template["cta_template"],
    }
    voiceovers = [sentence.format_map(substitutions) for sentence in sentences]
    duration_range = template["target_duration_seconds"]
    durations = _durations(
        voiceovers,
        duration_range["min"],
        duration_range["max"],
    )
    found = {entry["role"]: entry["path"] for entry in asset_report["found"]}
    declared = {
        role: (PurePosixPath(manifest["base_directory"]) / item["filename"]).as_posix()
        for role, item in manifest["assets"].items()
    }
    scenes = []
    warnings = []
    for index, (purpose, voiceover, seconds) in enumerate(
        zip(purposes, voiceovers, durations),
        1,
    ):
        role = _role_for(purpose, index - 1)
        asset_path = found.get(role) or declared.get(role)
        asset_exists = role in found
        if not asset_exists:
            warnings.append(f"Сцена {index}: отсутствует материал роли {role}.")
        scenes.append({
            "scene_number": index,
            "purpose": purpose,
            "voiceover": voiceover,
            "recommended_asset_role": role,
            "asset_path": asset_path,
            "asset_exists": asset_exists,
            "duration_seconds": seconds,
            "on_screen_text": voiceover,
            "manual_review_notes": (
                "Проверить соответствие реальному товару и читаемость текста."
            ),
        })
    return {
        "product_id": product["id"],
        "template_id": template["id"],
        "title": script_result["title"],
        "total_duration_seconds": round(sum(durations), 1),
        "scenes": scenes,
        "warnings": warnings,
    }
