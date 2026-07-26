#!/usr/bin/env python3
"""Extract the embedded NT Somic subsets from a user-supplied Yoku brandbook."""

import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path


def _font_descriptor(font):
    descriptor = font.get("/FontDescriptor")
    if descriptor:
        return descriptor.get_object()
    descendants = font.get("/DescendantFonts")
    if descendants:
        descendant = descendants[0].get_object()
        descriptor = descendant.get("/FontDescriptor")
        if descriptor:
            return descriptor.get_object()
    return None


def _font_bytes(font):
    descriptor = _font_descriptor(font)
    if descriptor is None:
        return None
    for key in ("/FontFile2", "/FontFile3", "/FontFile"):
        stream = descriptor.get(key)
        if stream:
            return stream.get_object().get_data()
    return None


def _unicode_map(font):
    """Return PDF CID -> Unicode mappings from the font's ToUnicode CMap."""
    stream = font.get("/ToUnicode")
    if not stream:
        return {}
    text = stream.get_object().get_data().decode("latin1")
    mapping = {}
    for start, end, target in re.findall(
        r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
        text,
    ):
        source_start = int(start, 16)
        source_end = int(end, 16)
        unicode_start = int(target, 16)
        for offset, cid in enumerate(range(source_start, source_end + 1)):
            mapping[cid] = unicode_start + offset
    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, flags=re.DOTALL):
        for source, target in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
            block,
        ):
            mapping.setdefault(int(source, 16), int(target, 16))
    return mapping


def _restore_unicode_cmap(data, cid_to_unicode):
    """Restore a browser-readable cmap omitted from PDF-embedded CID fonts."""
    try:
        from fontTools.ttLib import TTFont, newTable
        from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
    except ImportError as error:
        raise RuntimeError(
            "Для восстановления cmap нужен fonttools: python -m pip install fonttools"
        ) from error

    font = TTFont(io.BytesIO(data))
    glyph_order = font.getGlyphOrder()
    unicode_to_glyph = {
        unicode_value: glyph_order[cid]
        for cid, unicode_value in cid_to_unicode.items()
        if 0 <= cid < len(glyph_order) and 0 <= unicode_value <= 0xFFFF
    }
    if not unicode_to_glyph:
        raise RuntimeError("ToUnicode не дал пригодных соответствий для cmap.")
    cmap_table = newTable("cmap")
    cmap_table.tableVersion = 0
    cmap_table.tables = []
    for platform_id, encoding_id in ((0, 3), (3, 1)):
        subtable = CmapSubtable.newSubtable(4)
        subtable.platformID = platform_id
        subtable.platEncID = encoding_id
        subtable.language = 0
        subtable.cmap = unicode_to_glyph
        cmap_table.tables.append(subtable)
    font["cmap"] = cmap_table
    if "post" not in font:
        post = newTable("post")
        post.formatType = 3.0
        post.italicAngle = 0
        post.underlinePosition = -100
        post.underlineThickness = 50
        post.isFixedPitch = 0
        post.minMemType42 = 0
        post.maxMemType42 = 0
        post.minMemType1 = 0
        post.maxMemType1 = 0
        font["post"] = post
    output = io.BytesIO()
    font.save(output)
    return output.getvalue(), len(unicode_to_glyph)


def extract_fonts(pdf_path, output_dir):
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError(
            "Для извлечения шрифтов нужен pypdf: python -m pip install pypdf"
        ) from error

    pdf_path = Path(pdf_path).resolve()
    output_dir = Path(output_dir).resolve()
    if not pdf_path.is_file():
        raise RuntimeError(f"Брендбук не найден: {pdf_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(pdf_path))
    candidates = {"bold": [], "regular": []}
    for page in reader.pages:
        resources = page.get("/Resources")
        if not resources:
            continue
        fonts = resources.get_object().get("/Font")
        if not fonts:
            continue
        for reference in fonts.get_object().values():
            font = reference.get_object()
            base_name = str(font.get("/BaseFont", "")).lower()
            if "ntsomic" not in base_name:
                continue
            style = "bold" if "bold" in base_name else "regular"
            data = _font_bytes(font)
            if data:
                candidates[style].append(
                    (len(data), base_name, data, _unicode_map(font))
                )

    result = {}
    for style, values in candidates.items():
        if not values:
            raise RuntimeError(f"В брендбуке не найден встроенный NT Somic {style}.")
        _, source_name, data, cid_to_unicode = max(
            values,
            key=lambda value: (len(value[3]), value[0]),
        )
        data, unicode_glyphs = _restore_unicode_cmap(data, cid_to_unicode)
        target = output_dir / f"nt-somic-{style}.ttf"
        target.write_bytes(data)
        result[style] = {
            "path": str(target),
            "source_font": source_name,
            "size_bytes": target.stat().st_size,
            "sha256": hashlib.sha256(data).hexdigest(),
            "unicode_glyphs": unicode_glyphs,
        }
    manifest = {
        "schema_version": 1,
        "source_file": pdf_path.name,
        "fonts": result,
        "distribution": "local_only_not_committed",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Извлечь локальные NT Somic из брендбука Yoku Tea"
    )
    parser.add_argument("brandbook", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/yoku/brand"),
    )
    args = parser.parse_args(argv)
    try:
        manifest = extract_fonts(args.brandbook, args.output_dir)
    except RuntimeError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
