"""Build and render deterministic Yoku Tea motion campaigns with HyperFrames."""

import html
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .claims_guard import check_claims
from .exceptions import MotionRenderError
from .motion_assets import (
    load_motion_assets,
    prepare_motion_assets_from_reference,
)
from .motion_audio import create_sfx_track
from .motion_profiles import load_platform_profiles, normalize_platforms
from .motion_qa import create_qa_artifacts, mark_visual_review

TEMPLATE_ID = "product-transformation"
PLACEHOLDER_PATTERN = re.compile(r"__[A-Z0-9_]+__")
DEPENDENCY_VERSIONS = {
    "hyperframes": "0.7.72",
    "gsap": "3.15.0",
    "@sparticuz/chromium": "149.0.0",
}
ASSET_USE_FILENAMES = {
    "logo": ("logo-hook.png", "logo-final.png"),
    "drink": (
        "drink-hook.png",
        "drink-transform.png",
        "drink-facts.png",
        "drink-final.png",
    ),
    "packshot": (
        "packshot-main.png",
        "packshot-facts.png",
        "packshot-final.png",
    ),
    "powder": ("powder.png",),
    "toppings": ("toppings.png",),
}
PLATFORM_OUTPUT_SLUGS = {
    "ozon": "ozon",
    "reels": "instagram-reels",
    "shorts": "youtube-shorts",
}


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _short_product_name(product):
    name = str(product["name"]).strip()
    match = re.fullmatch(
        r"Смесь\s+(.+?)\s+для\s+Bubble\s+Tea",
        name,
        flags=re.IGNORECASE,
    )
    short_name = match.group(1) if match else name
    return short_name[:1].upper() + short_name[1:]


def _final_lines(positioning):
    positioning = str(positioning).strip()
    marker = " как в кафе"
    index = positioning.casefold().rfind(marker)
    if index > 0:
        return positioning[:index], positioning[index + 1 :]
    words = positioning.split()
    split_at = max(1, len(words) // 2)
    return " ".join(words[:split_at]), " ".join(words[split_at:])


def _format_number(value):
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def _validate_motion_facts(product):
    for field in (
        "package_weight_g",
        "servings",
        "dosage_g_per_drink",
        "drink_volume_ml",
    ):
        if not _positive_number(product.get(field)):
            raise MotionRenderError(f"Карточка товара: неверное значение {field}.")
    copy = " ".join(
        (
            f'Упаковка {_format_number(product["package_weight_g"])} г',
            f'{_format_number(product["servings"])} порций',
            f'{_format_number(product["dosage_g_per_drink"])} г на напиток',
            f'для напитка {_format_number(product["drink_volume_ml"])} мл',
            str(product["positioning"]),
        )
    )
    report = check_claims(copy, product)
    if report["status"] != "PASS":
        messages = "; ".join(item["message"] for item in report["errors"])
        raise MotionRenderError(f"Claims Guard остановил motion-рендер: {messages}")
    return report


def _font_face_css(brand_assets_root, project_assets):
    brand_assets_root = Path(brand_assets_root).resolve()
    regular = brand_assets_root / "nt-somic-regular.ttf"
    bold = brand_assets_root / "nt-somic-bold.ttf"
    if not regular.is_file() or not bold.is_file():
        return (
            '@font-face { font-family: "Yoku Sans"; '
            'src: local("Arial"); font-style: normal; font-weight: 400 900; }'
        ), False
    shutil.copy2(regular, project_assets / regular.name)
    shutil.copy2(bold, project_assets / bold.name)
    css = """
      @font-face {
        font-family: "Yoku Sans";
        src: url("./assets/nt-somic-regular.ttf") format("truetype");
        font-style: normal;
        font-weight: 400;
        font-display: block;
      }

      @font-face {
        font-family: "Yoku Sans";
        src: url("./assets/nt-somic-bold.ttf") format("truetype");
        font-style: normal;
        font-weight: 700 900;
        font-display: block;
      }
    """.strip()
    return css, True


def _template_replacements(product, profile, font_css):
    beats = profile["beats"]
    short_name = _short_product_name(product)
    final_line_one, final_line_two = _final_lines(product["positioning"])
    text_values = {
        "PRODUCT_SHORT": short_name,
        "PACKAGE_WEIGHT": f'{_format_number(product["package_weight_g"])} г',
        "SERVINGS": _format_number(product["servings"]),
        "DOSAGE": f'{_format_number(product["dosage_g_per_drink"])} г',
        "DRINK_VOLUME": f'{_format_number(product["drink_volume_ml"])} мл',
        "POSITIONING": product["positioning"],
        "FINAL_LINE_ONE": final_line_one,
        "FINAL_LINE_TWO": final_line_two,
    }
    replacements = {
        f"__{key}__": html.escape(str(value), quote=True)
        for key, value in text_values.items()
    }
    replacements.update(
        {
            "__FONT_FACE_CSS__": font_css,
            "__SAFE_TOP__": str(profile["safe_zone"]["top"]),
            "__SAFE_RIGHT__": str(profile["safe_zone"]["right"]),
            "__SAFE_BOTTOM__": str(profile["safe_zone"]["bottom"]),
            "__SAFE_LEFT__": str(profile["safe_zone"]["left"]),
            "__ROOT_DURATION__": _format_number(profile["duration_seconds"]),
            "__TIMING_JSON__": json.dumps(
                {
                    "duration": profile["duration_seconds"],
                    "beats": beats,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).replace("</", "<\\/"),
        }
    )
    for beat_id, beat in beats.items():
        prefix = beat_id.upper()
        replacements[f"__{prefix}_START__"] = _format_number(beat["start"])
        replacements[f"__{prefix}_DURATION__"] = _format_number(beat["duration"])
    return replacements


def render_template(template_text, product, profile, font_css):
    """Inject trusted catalog data and deterministic platform timing."""
    rendered = template_text
    for token, value in _template_replacements(product, profile, font_css).items():
        rendered = rendered.replace(token, value)
    unresolved = sorted(set(PLACEHOLDER_PATTERN.findall(rendered)))
    if unresolved:
        raise MotionRenderError(
            "В motion-шаблоне остались плейсхолдеры: " + ", ".join(unresolved)
        )
    if "http://" in rendered or "https://" in rendered:
        raise MotionRenderError("Motion-шаблон не должен загружать сетевые ресурсы.")
    return rendered


def build_motion_project(
    project_dir,
    product,
    profile_id,
    profile,
    motion_assets,
    *,
    template_path,
    gsap_path,
    brand_assets_root,
):
    """Create one self-contained HyperFrames project using approved local assets."""
    project_dir = Path(project_dir).resolve()
    project_assets = project_dir / "assets"
    project_assets.mkdir(parents=True, exist_ok=False)
    template_path = Path(template_path).resolve()
    gsap_path = Path(gsap_path).resolve()
    if not template_path.is_file():
        raise MotionRenderError(f"Motion-шаблон не найден: {template_path}")
    if not gsap_path.is_file():
        raise MotionRenderError(f"Локальный GSAP не найден: {gsap_path}")

    shutil.copy2(gsap_path, project_assets / "gsap.min.js")
    for role, source in motion_assets["paths"].items():
        for filename in ASSET_USE_FILENAMES[role]:
            shutil.copy2(Path(source), project_assets / filename)
    font_css, embedded_fonts = _font_face_css(brand_assets_root, project_assets)
    template_text = template_path.read_text(encoding="utf-8")
    index_text = render_template(template_text, product, profile, font_css)
    (project_dir / "index.html").write_text(index_text, encoding="utf-8")
    config = {
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
        "paths": {
            "blocks": "compositions",
            "components": "compositions/components",
            "assets": "assets",
        },
        "media": {"autoProxy": False},
    }
    (project_dir / "hyperframes.json").write_text(
        _json_text(config),
        encoding="utf-8",
    )
    metadata = {
        "schema_version": 1,
        "template_id": TEMPLATE_ID,
        "product_id": product["id"],
        "platform": profile_id,
        "profile": profile,
        "embedded_brand_fonts": embedded_fonts,
        "asset_source_sha256": motion_assets["manifest"].get("source_sha256"),
        "dependencies": DEPENDENCY_VERSIONS,
        "network_assets": False,
        "auto_publish": False,
    }
    (project_dir / "project-metadata.json").write_text(
        _json_text(metadata),
        encoding="utf-8",
    )
    return project_dir


def _resolve_executable(value, label):
    value = str(value)
    if "/" in value or "\\" in value:
        path = Path(value).resolve()
        if path.is_file():
            return str(path)
    found = shutil.which(value)
    if found:
        return found
    raise MotionRenderError(f"{label} не найден: {value}")


def _run_logged(command, *, cwd, env, log_path, timeout):
    result = subprocess.run(
        [str(item) for item in command],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "$ " + " ".join(str(item) for item in command) + "\n\n"
        + result.stdout
        + ("\n[stderr]\n" + result.stderr if result.stderr else ""),
        encoding="utf-8",
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "неизвестная ошибка").strip()
        raise MotionRenderError(
            f"Команда завершилась с кодом {result.returncode}: {detail[-1800:]}"
        )
    return result


def _resolve_browser(repo_root, runtime_dir, browser_path):
    if browser_path:
        return _resolve_executable(browser_path, "Chromium")
    node = _resolve_executable("node", "Node.js")
    helper = Path(repo_root) / "scripts" / "yoku_chromium_path.mjs"
    result = subprocess.run(
        [node, str(helper), str(runtime_dir)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "неизвестная ошибка").strip()
        raise MotionRenderError(f"Не удалось подготовить Chromium: {detail[-1600:]}")
    output = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not output:
        raise MotionRenderError("Скрипт Chromium не вернул путь к браузеру.")
    return _resolve_executable(output[-1], "Chromium")


def _render_env(browser_path, cache_dir):
    env = os.environ.copy()
    cache_dir = Path(cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "HYPERFRAMES_NO_TELEMETRY": "1",
            "HYPERFRAMES_BROWSER_PATH": str(browser_path),
            "PRODUCER_HEADLESS_SHELL_PATH": str(browser_path),
            "PRODUCER_LOW_MEMORY_MODE": "1",
            "XDG_CACHE_HOME": str(cache_dir),
            "TMPDIR": str(cache_dir),
        }
    )
    return env


def _normalize_video(raw_path, final_path, profile, sfx_path, ffmpeg):
    video_filter = f'fps={int(profile["fps"])},format=yuv420p'
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(raw_path),
    ]
    if sfx_path:
        command.extend(["-i", str(sfx_path)])
    command.extend(
        [
            "-map", "0:v:0",
            "-vf", video_filter,
        ]
    )
    if sfx_path:
        command.extend(
            [
                "-map", "1:a:0",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
            ]
        )
    else:
        command.append("-an")
    command.extend(
        [
            "-t", f'{float(profile["duration_seconds"]):.3f}',
            "-r", str(profile["fps"]),
            "-c:v", "libx264",
            "-preset", "slow",
            "-crf", "17",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(final_path),
        ]
    )
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if (
        result.returncode != 0
        or not Path(final_path).is_file()
        or Path(final_path).stat().st_size == 0
    ):
        detail = (result.stderr or result.stdout or "неизвестная ошибка").strip()
        raise MotionRenderError(f"FFmpeg не смог собрать master MP4: {detail[-1600:]}")


def _campaign_report(folder, product, platforms, results, dry_run):
    status = "DRY_RUN" if dry_run else (
        "TECHNICAL_PASS_VISUAL_PENDING"
        if all(item["technical_status"] == "PASS" for item in results)
        else "FAIL"
    )
    payload = {
        "schema_version": 1,
        "status": status,
        "product_id": product["id"],
        "template_id": TEMPLATE_ID,
        "platforms": platforms,
        "results": results,
        "requires_manual_review": True,
        "auto_publish": False,
        "external_uploads": False,
    }
    (folder / "campaign-report.json").write_text(_json_text(payload), encoding="utf-8")
    lines = [
        f'# Motion campaign — {product["name"]}',
        "",
        f"Status: **{status}**",
        "",
        "| Platform | Duration | Audio | Technical QA |",
        "|---|---:|---:|---:|",
    ]
    for item in results:
        lines.append(
            f'| {item["platform_label"]} | {item["duration_seconds"]:.1f} s | '
            f'{"yes" if item["audio"] else "no"} | {item["technical_status"]} |'
        )
    lines.extend(
        [
            "",
            "Publication is disabled. Every final file requires visual review.",
        ]
    )
    (folder / "campaign-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def finalize_campaign_visual_review(folder, notes_by_platform):
    """Mark every proof as visually reviewed and finalize the campaign report."""
    folder = Path(folder).resolve()
    report_path = folder / "campaign-report.json"
    try:
        campaign = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MotionRenderError(f"Не удалось прочитать campaign report: {error}") from error
    results = campaign.get("results")
    if not isinstance(results, list) or not results:
        raise MotionRenderError("Campaign report не содержит результатов.")
    for result in results:
        platform_id = result.get("platform")
        notes = notes_by_platform.get(platform_id)
        if not notes:
            raise MotionRenderError(
                f"Не переданы visual notes для платформы {platform_id}."
            )
        qa_path = folder / result["qa_json"]
        mark_visual_review(qa_path, notes)
        result["visual_status"] = "PASS"
    if not all(
        item.get("technical_status") == "PASS"
        and item.get("visual_status") == "PASS"
        for item in results
    ):
        raise MotionRenderError("Не все версии прошли technical и visual QA.")
    campaign["status"] = "PASS"
    report_path.write_text(_json_text(campaign), encoding="utf-8")
    markdown_path = folder / "campaign-report.md"
    if markdown_path.is_file():
        markdown = markdown_path.read_text(encoding="utf-8")
        markdown = markdown.replace(
            "Status: **TECHNICAL_PASS_VISUAL_PENDING**",
            "Status: **PASS**",
        ).replace(
            "Publication is disabled. Every final file requires visual review.",
            "Technical and visual QA passed. Publication remains disabled.",
        )
        markdown_path.write_text(markdown, encoding="utf-8")
    run_metadata_path = folder / "run-metadata.json"
    if run_metadata_path.is_file():
        run_metadata = json.loads(run_metadata_path.read_text(encoding="utf-8"))
        run_metadata["status"] = "PASS"
        run_metadata["visual_review"] = "PASS"
        run_metadata_path.write_text(_json_text(run_metadata), encoding="utf-8")
    return campaign


def create_motion_campaign(
    output_dir,
    product,
    platforms,
    *,
    repo_root,
    motion_assets_root,
    brand_assets_root,
    profile_config,
    template_path,
    extraction_spec_path=None,
    reference_video=None,
    prepare_from_reference=False,
    overwrite_motion_assets=False,
    ffmpeg="ffmpeg",
    ffprobe="ffprobe",
    hyperframes=None,
    browser_path=None,
    now=None,
    dry_run=False,
):
    """Create three local masters and QA proofs; never upload or publish them."""
    repo_root = Path(repo_root).resolve()
    profile_map = load_platform_profiles(profile_config)
    platform_ids = normalize_platforms(platforms, profile_map)
    claims_report = _validate_motion_facts(product)
    ffmpeg_executable = str(ffmpeg)
    ffprobe_executable = str(ffprobe)
    if prepare_from_reference or not dry_run:
        ffmpeg_executable = _resolve_executable(ffmpeg, "FFmpeg")
        ffprobe_executable = _resolve_executable(ffprobe, "FFprobe")

    if prepare_from_reference:
        if not reference_video or not extraction_spec_path:
            raise MotionRenderError(
                "Для подготовки ассетов нужны reference_video и extraction_spec_path."
            )
        motion_assets = prepare_motion_assets_from_reference(
            reference_video,
            extraction_spec_path,
            motion_assets_root,
            ffmpeg=ffmpeg_executable,
            ffprobe=ffprobe_executable,
            overwrite=overwrite_motion_assets,
        )
    else:
        motion_assets = load_motion_assets(
            motion_assets_root,
            expected_product_id=product["id"],
        )

    now = now or datetime.now()
    folder = Path(output_dir).resolve() / (
        f'{now:%Y%m%d-%H%M%S}_{product["id"]}_{TEMPLATE_ID}_campaign'
    )
    try:
        folder.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        raise MotionRenderError(f"Не удалось создать папку кампании: {error}") from error

    gsap_path = repo_root / "node_modules" / "gsap" / "dist" / "gsap.min.js"
    hyperframes_value = hyperframes or (
        repo_root / "node_modules" / ".bin" / "hyperframes"
    )
    hyperframes_executable = None
    browser_executable = None
    env = None
    if not dry_run:
        hyperframes_executable = _resolve_executable(
            hyperframes_value,
            "HyperFrames",
        )
        browser_executable = _resolve_browser(
            repo_root,
            Path(output_dir).resolve() / ".yoku-chromium-runtime",
            browser_path,
        )
        env = _render_env(
            browser_executable,
            Path(output_dir).resolve() / ".yoku-runtime-cache",
        )

    results = []
    projects_root = folder / "projects"
    projects_root.mkdir()
    for profile_id in platform_ids:
        profile = profile_map[profile_id]
        project_dir = projects_root / profile_id
        build_motion_project(
            project_dir,
            product,
            profile_id,
            profile,
            motion_assets,
            template_path=template_path,
            gsap_path=gsap_path,
            brand_assets_root=brand_assets_root,
        )
        result = {
            "platform": profile_id,
            "platform_label": profile["label"],
            "duration_seconds": float(profile["duration_seconds"]),
            "audio": bool(profile["audio"]),
            "project": str(project_dir.relative_to(folder)),
            "technical_status": "DRY_RUN" if dry_run else "PENDING",
        }
        if not dry_run:
            logs_dir = folder / "logs" / profile_id
            caption_bottom = (
                profile["height"] - profile["safe_zone"]["bottom"]
            ) / profile["height"]
            caption_zone = (
                f"x0=0;y0={caption_bottom:.4f};x1=1;y1=1;"
                "severity=warning;seek=.25,.5,.75"
            )
            _run_logged(
                [
                    hyperframes_executable,
                    "check",
                    "--json",
                    "--samples=13",
                    "--at-transitions",
                    "--max-transition-samples=80",
                    "--snapshots",
                    f"--caption-zone={caption_zone}",
                    "--frame-check=severity=error;seek=.25,.5,.75;tol=4",
                    str(project_dir),
                ],
                cwd=repo_root,
                env=env,
                log_path=logs_dir / "hyperframes-check.log",
                timeout=300,
            )
            raw_path = project_dir / "renders" / f"{profile_id}-hyperframes.mp4"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            _run_logged(
                [
                    hyperframes_executable,
                    "render",
                    "--output", str(raw_path),
                    "--fps", str(profile["fps"]),
                    "--quality", "high",
                    "--workers", "1",
                    "--crf", "16",
                    "--no-browser-gpu",
                    "--low-memory-mode",
                    "--strict",
                    str(project_dir),
                ],
                cwd=repo_root,
                env=env,
                log_path=logs_dir / "hyperframes-render.log",
                timeout=2400,
            )
            if not raw_path.is_file() or raw_path.stat().st_size == 0:
                raise MotionRenderError(
                    f"HyperFrames не создал ожидаемый файл: {raw_path}"
                )
            sfx_path = None
            if profile["audio"]:
                sfx_path = create_sfx_track(profile, project_dir / "audio" / "sfx.wav")
            final_path = folder / (
                f'{product["id"]}-{PLATFORM_OUTPUT_SLUGS[profile_id]}.mp4'
            )
            _normalize_video(
                raw_path,
                final_path,
                profile,
                sfx_path,
                ffmpeg_executable,
            )
            qa = create_qa_artifacts(
                final_path,
                profile_id,
                profile,
                folder / "qa" / profile_id,
                ffmpeg=ffmpeg_executable,
                ffprobe=ffprobe_executable,
            )
            if qa["status"] != "PASS":
                raise MotionRenderError(
                    f"Технический QA {profile_id} завершился со статусом FAIL."
                )
            result.update(
                {
                    "technical_status": qa["status"],
                    "video": str(final_path.relative_to(folder)),
                    "cover": str(Path(qa["cover"]).relative_to(folder)),
                    "contact_sheet": str(
                        Path(qa["contact_sheet"]).relative_to(folder)
                    ),
                    "qa_json": str(Path(qa["json"]).relative_to(folder)),
                    "qa_markdown": str(Path(qa["markdown"]).relative_to(folder)),
                }
            )
        results.append(result)

    campaign = _campaign_report(folder, product, platform_ids, results, dry_run)
    (folder / "claims-report.json").write_text(
        _json_text(claims_report),
        encoding="utf-8",
    )
    (folder / "run-metadata.json").write_text(
        _json_text(
            {
                "schema_version": 1,
                "status": campaign["status"],
                "product_id": product["id"],
                "template_id": TEMPLATE_ID,
                "dependencies": DEPENDENCY_VERSIONS,
                "browser": browser_executable,
                "telemetry": False,
                "network_assets": False,
                "auto_publish": False,
                "source_asset_manifest": motion_assets["manifest"],
            }
        ),
        encoding="utf-8",
    )
    return folder
