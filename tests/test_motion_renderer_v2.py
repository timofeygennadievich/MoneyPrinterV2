import hashlib
import io
import json
import tempfile
import unittest
import wave
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import yoku_main
from src.yoku.exceptions import MotionAssetError, MotionRenderError
from src.yoku.motion_assets import load_motion_assets
from src.yoku.motion_audio import create_sfx_track
from src.yoku.motion_profiles import load_platform_profiles, normalize_platforms
from src.yoku.motion_qa import mark_visual_review
from src.yoku.motion_renderer import (
    ASSET_USE_FILENAMES,
    build_motion_project,
    create_motion_campaign,
    render_template,
)
from src.yoku.product_catalog import ProductCatalog


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf\xc0\xf0"
    b"\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND"
    b"\xaeB`\x82"
)
ROLES = ("logo", "drink", "packshot", "powder", "toppings")


def _motion_pack(root, product_id="taro-100g"):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    assets = {}
    for role in ROLES:
        path = root / f"{role}.png"
        path.write_bytes(PNG_1X1)
        assets[role] = {
            "filename": path.name,
            "approved": True,
            "source_type": "approved_test_reference",
            "sha256": hashlib.sha256(PNG_1X1).hexdigest(),
        }
    manifest = {
        "schema_version": 1,
        "product_id": product_id,
        "source_reference": "approved-test.mp4",
        "source_sha256": "a" * 64,
        "assets": assets,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    return load_motion_assets(root, expected_product_id=product_id)


class MotionRendererV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product = ProductCatalog("data/products").load("taro-100g")
        cls.profiles = load_platform_profiles("data/motion/platforms.json")
        cls.template_text = Path(
            "motion/templates/product-transformation/index.html"
        ).read_text(encoding="utf-8")

    def test_platform_profiles_are_distinct_and_aliases_normalize(self):
        self.assertEqual(
            normalize_platforms(
                "ozon,instagram-reels,youtube-shorts,ozon",
                self.profiles,
            ),
            ["ozon", "reels", "shorts"],
        )
        self.assertEqual(self.profiles["ozon"]["duration_seconds"], 10.5)
        self.assertFalse(self.profiles["ozon"]["audio"])
        self.assertTrue(self.profiles["reels"]["audio"])
        self.assertTrue(self.profiles["shorts"]["audio"])

    def test_profile_rejects_overlapping_scenes(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "schema_version": 1,
                "profiles": {"ozon": deepcopy(self.profiles["ozon"])},
            }
            payload["profiles"]["ozon"]["beats"]["packshot"]["start"] = 1.0
            path = Path(directory, "profiles.json")
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(MotionRenderError):
                load_platform_profiles(path)

    def test_template_uses_catalog_facts_without_network_or_direct_cta(self):
        rendered = render_template(
            self.template_text,
            self.product,
            self.profiles["ozon"],
            '@font-face { font-family: "Yoku Sans"; src: local("Arial"); }',
        )
        self.assertNotIn("__ROOT_DURATION__", rendered)
        self.assertNotIn("http://", rendered)
        self.assertNotIn("https://", rendered)
        self.assertIn("5 напитков", rendered)
        self.assertIn("20 г на 300 мл", rendered)
        self.assertIn("Бабл-ти дома как в кафе", rendered)
        self.assertNotIn("Купить", rendered)
        self.assertNotIn("без сахара", rendered.casefold())
        self.assertIn('data-duration="10.5"', rendered)
        self.assertIn('window.__timelines["yoku-product-transformation"]', rendered)

    def test_motion_manifest_hash_and_product_scope_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = _motion_pack(directory)
            self.assertEqual(set(pack["paths"]), set(ROLES))
            Path(pack["paths"]["drink"]).write_bytes(PNG_1X1 + b"changed")
            with self.assertRaises(MotionAssetError):
                load_motion_assets(directory, expected_product_id="taro-100g")
            with self.assertRaises(MotionAssetError):
                load_motion_assets(directory, expected_product_id="mokko-200g")

    def test_build_project_is_self_contained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = _motion_pack(root / "pack")
            gsap = root / "gsap.min.js"
            gsap.write_text("window.gsap={};", encoding="utf-8")
            project = build_motion_project(
                root / "project",
                self.product,
                "ozon",
                self.profiles["ozon"],
                pack,
                template_path="motion/templates/product-transformation/index.html",
                gsap_path=gsap,
                brand_assets_root=root / "brand",
            )
            self.assertTrue((project / "index.html").is_file())
            self.assertTrue((project / "hyperframes.json").is_file())
            self.assertEqual(
                {path.name for path in (project / "assets").iterdir()},
                {
                    "gsap.min.js",
                    *(
                        filename
                        for filenames in ASSET_USE_FILENAMES.values()
                        for filename in filenames
                    ),
                },
            )
            html = (project / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("https://", html)
            metadata = json.loads(
                (project / "project-metadata.json").read_text(encoding="utf-8")
            )
            self.assertFalse(metadata["network_assets"])
            self.assertFalse(metadata["auto_publish"])

    def test_dry_run_builds_all_platform_projects_without_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            gsap = repo / "node_modules/gsap/dist/gsap.min.js"
            gsap.parent.mkdir(parents=True)
            gsap.write_text("window.gsap={};", encoding="utf-8")
            pack_root = root / "pack"
            _motion_pack(pack_root)
            folder = create_motion_campaign(
                root / "output",
                self.product,
                "ozon,reels,shorts",
                repo_root=repo,
                motion_assets_root=pack_root,
                brand_assets_root=root / "brand",
                profile_config="data/motion/platforms.json",
                template_path="motion/templates/product-transformation/index.html",
                now=datetime(2026, 7, 26, 12, 0, 0),
                dry_run=True,
            )
            report = json.loads(
                (folder / "campaign-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "DRY_RUN")
            self.assertEqual(
                {path.name for path in (folder / "projects").iterdir()},
                {"ozon", "reels", "shorts"},
            )
            self.assertFalse(report["auto_publish"])
            self.assertFalse(report["external_uploads"])

    def test_sfx_is_deterministic_and_exact_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            first = create_sfx_track(
                self.profiles["reels"],
                Path(directory, "first.wav"),
            )
            second = create_sfx_track(
                self.profiles["reels"],
                Path(directory, "second.wav"),
            )
            self.assertEqual(
                hashlib.sha256(first.read_bytes()).hexdigest(),
                hashlib.sha256(second.read_bytes()).hexdigest(),
            )
            with wave.open(str(first), "rb") as stream:
                duration = stream.getnframes() / stream.getframerate()
                self.assertAlmostEqual(duration, 15.0, places=3)
                self.assertEqual(stream.getnchannels(), 2)

    def test_render_campaign_cli_routes_platforms_without_publication(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            yoku_main,
            "create_motion_campaign",
            return_value=Path(directory, "campaign"),
        ) as create:
            with redirect_stdout(io.StringIO()):
                code = yoku_main.main(
                    [
                        "render-campaign",
                        "--product",
                        "taro-100g",
                        "--platforms",
                        "ozon,reels,shorts",
                        "--motion-assets-root",
                        directory,
                        "--output-dir",
                        directory,
                        "--dry-run",
                    ]
                )
        self.assertEqual(code, 0)
        self.assertEqual(create.call_args.args[2], "ozon,reels,shorts")
        self.assertTrue(create.call_args.kwargs["dry_run"])

    def test_visual_review_requires_technical_pass_and_records_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "video-qa.json")
            markdown = path.with_suffix(".md")
            path.write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "visual_review": {
                            "status": "PENDING",
                            "cover": "cover.png",
                            "contact_sheet": "sheet.jpg",
                        },
                    }
                ),
                encoding="utf-8",
            )
            markdown.write_text("Visual review: **PENDING**\n", encoding="utf-8")
            result = mark_visual_review(path, ["Упаковка не искажена."])
            self.assertEqual(result["visual_review"]["status"], "PASS")
            self.assertIn(
                "Visual review: **PASS**",
                markdown.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
