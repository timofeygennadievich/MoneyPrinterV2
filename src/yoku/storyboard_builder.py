"""Build deterministic storyboards from validated scripts and approved media."""

from pathlib import PurePosixPath

ROLE_RULES = (
    (("готов", "результат", "напиток крупным"), "drink_hero"),
    (("упаков", "порци"), "packshot_front"),
    (("приготов", "инструкц", "дозиров"), "preparation"),
    (("детал", "вариант", "подач"), "product_detail"),
)


def _role_for(purpose, voiceover, index, total, declared, preparation_index):
    text = f"{purpose} {voiceover}".casefold()
    if index == total - 1 and "cta_slide" in declared:
        return "cta_slide", preparation_index
    for keywords, role in ROLE_RULES:
        if any(keyword in text for keyword in keywords):
            if role == "preparation":
                candidates = ("preparation_01", "preparation_02")
                selected = candidates[preparation_index % len(candidates)]
                if selected not in declared:
                    selected = "preparation_01"
                return selected, preparation_index + 1
            return role, preparation_index
    fallback = "product_detail" if "product_detail" in declared else "packshot_front"
    return fallback, preparation_index


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
    found = {entry["role"]: entry for entry in asset_report["found"]}
    declared = {
        role: {
            "path": (PurePosixPath(manifest["base_directory"]) / item["filename"]).as_posix(),
            "approved": item.get("approved", False),
            "source_type": item.get("source_type", "legacy_manifest"),
        }
        for role, item in manifest["assets"].items()
    }
    scenes = []
    warnings = []
    preparation_index = 0
    total = len(voiceovers)
    for index, (purpose, voiceover, seconds) in enumerate(
        zip(purposes, voiceovers, durations)
    ):
        role, preparation_index = _role_for(
            purpose,
            voiceover,
            index,
            total,
            declared,
            preparation_index,
        )
        found_entry = found.get(role)
        declared_entry = declared.get(role)
        asset_path = (
            found_entry["path"] if found_entry else
            declared_entry["path"] if declared_entry else None
        )
        asset_exists = found_entry is not None
        asset_approved = bool(
            (found_entry or declared_entry or {}).get("approved", False)
        )
        source_type = (found_entry or declared_entry or {}).get(
            "source_type", "unknown"
        )
        if not asset_exists:
            warnings.append(f"Сцена {index + 1}: отсутствует материал роли {role}.")
        if not asset_approved:
            warnings.append(f"Сцена {index + 1}: материал роли {role} не утверждён.")
        scenes.append({
            "scene_number": index + 1,
            "purpose": purpose,
            "voiceover": voiceover,
            "recommended_asset_role": role,
            "asset_path": asset_path,
            "asset_exists": asset_exists,
            "asset_approved": asset_approved,
            "asset_source_type": source_type,
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
