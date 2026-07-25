import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import yoku_main
from src.yoku.asset_catalog import AssetCatalog, validate_assets
from src.yoku.exceptions import AssetValidationError, VideoRenderError
from src.yoku.product_catalog import ProductCatalog
from src.yoku.script_builder import build_script
from src.yoku.storyboard_builder import build_storyboard
from src.yoku.template_catalog import TemplateCatalog
from src.yoku.video_renderer import (
    build_ffmpeg_command,
    build_render_plan,
    create_video_package,
)

PRODUCT_IDS = (
    "taro-100g",
    "taro-200g",
    "thai-tea-200g",
    "mokko-200g",
    "honey-melon-200g",
)


def _minimal_png(width=1080, height=1440):
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
    )


class ApprovedAssetsVideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.products = ProductCatalog("data/products")
        cls.templates = TemplateCatalog("data/templates")
        cls.assets = AssetCatalog("data/media", cls.products)

    def _complete_taro100_root(self, root):
        manifest = self.assets.load("taro-100g")
        folder = Path(root, *Path(manifest["base_directory"]).parts)
        folder.mkdir(parents=True)
        for item in manifest["assets"].values():
            (folder / item["filename"]).write_bytes(_minimal_png())
        return manifest

    def _storyboard(self, root, template_id="social-result"):
        product = self.products.load("taro-100g")
        template = self.templates.load(template_id)
        script = build_script(product, template)
        manifest = self.assets.load(product["id"])
        report = validate_assets(manifest, root)
        return product, template, build_storyboard(
            product, template, script, manifest, report
        )

    def test_all_manifests_use_approved_schema_v2(self):
        for product_id in PRODUCT_IDS:
            with self.subTest(product_id=product_id):
                manifest = self.assets.load(product_id)
                self.assertEqual(manifest["schema_version"], 2)
                self.assertIn("cta_slide", manifest["assets"])
                for item in manifest["assets"].values():
                    self.assertTrue(item["approved"])
                    self.assertEqual(item["source_type"], "approved_final_slide")

    def test_schema_v2_rejects_unapproved_asset(self):
        manifest = json.loads(json.dumps(self.assets.load("taro-100g")))
        manifest["assets"]["packshot_front"]["approved"] = False
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "taro-100g.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            catalog = AssetCatalog(directory, self.products)
            with self.assertRaises(AssetValidationError):
                catalog.load("taro-100g")

    def test_asset_report_inspects_png_dimensions(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = self._complete_taro100_root(root)
            report = validate_assets(manifest, root)
        self.assertEqual(report["status"], "COMPLETE")
        self.assertEqual(len(report["found"]), len(manifest["assets"]))
        inspection = report["found"][0]["inspection"]
        self.assertEqual(inspection["width"], 1080)
        self.assertEqual(inspection["height"], 1440)

    def test_final_storyboard_scene_uses_cta_slide(self):
        with tempfile.TemporaryDirectory() as root:
            self._complete_taro100_root(root)
            _, _, storyboard = self._storyboard(root)
        final = storyboard["scenes"][-1]
        self.assertEqual(final["recommended_asset_role"], "cta_slide")
        self.assertTrue(final["asset_exists"])
        self.assertTrue(final["asset_approved"])

    def test_render_plan_requires_approved_existing_assets(self):
        with tempfile.TemporaryDirectory() as root:
            self._complete_taro100_root(root)
            _, _, storyboard = self._storyboard(root)
            plan = build_render_plan(storyboard, root)
            self.assertEqual(plan["width"], 1080)
            self.assertEqual(plan["height"], 1920)
            self.assertGreater(plan["total_duration_seconds"], 0)
            storyboard["scenes"][0]["asset_approved"] = False
            with self.assertRaises(VideoRenderError):
                build_render_plan(storyboard, root)

    def test_dry_run_video_package_contract(self):
        with tempfile.TemporaryDirectory() as root:
            self._complete_taro100_root(root)
            product, template, storyboard = self._storyboard(root)
            folder = create_video_package(
                Path(root, "output"),
                product,
                template,
                storyboard,
                root,
                dry_run=True,
                now=datetime(2026, 7, 25, 12, 0, 0),
            )
            self.assertEqual(
                {path.name for path in folder.iterdir()},
                {"render-plan.json", "metadata.json", "review.md"},
            )
            metadata = json.loads(
                (folder / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertFalse(metadata["video_generated"])
            self.assertFalse(metadata["audio_generated"])
            self.assertFalse(metadata["auto_publish"])
            self.assertFalse(metadata["external_services_used"])
            self.assertEqual(
                metadata["planned_duration_seconds"],
                json.loads((folder / "render-plan.json").read_text(encoding="utf-8"))[
                    "total_duration_seconds"
                ],
            )

    def test_ffmpeg_command_enforces_exact_duration(self):
        plan = {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "background": "0xF7F4EE",
            "total_duration_seconds": 12.0,
        }
        command = build_ffmpeg_command(
            "/usr/bin/ffmpeg", Path("slides.ffconcat"), Path("video.mp4"), plan
        )
        self.assertEqual(command[0], "/usr/bin/ffmpeg")
        self.assertIn("libx264", command)
        self.assertIn("-an", command)
        self.assertIn("-t", command)
        self.assertEqual(command[command.index("-t") + 1], "12.0")
        self.assertNotIn("shell", command)

    def test_render_video_cli_dry_run(self):
        with tempfile.TemporaryDirectory() as root:
            self._complete_taro100_root(root)
            output = Path(root, "output")
            with patch.object(
                yoku_main,
                "_catalogs",
                return_value=(self.products, self.templates, self.assets),
            ), redirect_stdout(io.StringIO()):
                code = yoku_main.main([
                    "render-video",
                    "--product", "taro-100g",
                    "--template", "social-result",
                    "--assets-root", root,
                    "--output-dir", str(output),
                    "--dry-run",
                ])
            self.assertEqual(code, 0)
            packages = list(output.iterdir())
            self.assertEqual(len(packages), 1)
            self.assertTrue((packages[0] / "render-plan.json").is_file())


if __name__ == "__main__":
    unittest.main()
