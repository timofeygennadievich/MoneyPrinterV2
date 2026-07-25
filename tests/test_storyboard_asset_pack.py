import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import yoku_main
from src.yoku.asset_catalog import AssetCatalog, validate_assets
from src.yoku.claims_guard import check_claims
from src.yoku.exceptions import AssetValidationError
from src.yoku.product_catalog import ProductCatalog
from src.yoku.script_builder import build_script
from src.yoku.storyboard_builder import build_storyboard
from src.yoku.storyboard_package import create_storyboard_package
from src.yoku.subtitle_builder import build_srt
from src.yoku.template_catalog import TemplateCatalog

PRODUCT_IDS = (
    "taro-100g",
    "taro-200g",
    "thai-tea-200g",
    "mokko-200g",
    "honey-melon-200g",
)
TEMPLATE_IDS = ("ozon-recipe", "ozon-objection", "social-result")


class StoryboardAssetPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.products = ProductCatalog("data/products")
        cls.templates = TemplateCatalog("data/templates")
        cls.assets = AssetCatalog("data/media", cls.products)

    def test_all_manifests_load(self):
        self.assertEqual(
            [manifest["product_id"] for manifest in self.assets.list()],
            sorted(PRODUCT_IDS),
        )

    def _invalid_manifest(self, update):
        value = self.assets.load("taro-200g")
        value = json.loads(json.dumps(value, ensure_ascii=False))
        update(value)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name, "taro-200g.json")
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return AssetCatalog(temporary.name, self.products)

    def test_manifest_product_id_must_match_filename(self):
        catalog = self._invalid_manifest(
            lambda value: value.update({"product_id": "mokko-200g"})
        )
        with self.assertRaises(AssetValidationError):
            catalog.load("taro-200g")

    def test_path_traversal_and_absolute_paths_are_rejected(self):
        for base_directory in ("../assets", "/tmp/assets", "assets\\unsafe"):
            with self.subTest(base_directory=base_directory):
                catalog = self._invalid_manifest(
                    lambda value, base_directory=base_directory: value.update(
                        {"base_directory": base_directory}
                    )
                )
                with self.assertRaises(AssetValidationError):
                    catalog.load("taro-200g")

    def test_unknown_extension_is_rejected(self):
        catalog = self._invalid_manifest(
            lambda value: value["assets"]["packshot_front"].update(
                {"filename": "packshot-front.exe"}
            )
        )
        with self.assertRaises(AssetValidationError):
            catalog.load("taro-200g")

    def test_missing_assets_are_reported_by_requirement(self):
        with tempfile.TemporaryDirectory() as root:
            report = validate_assets(self.assets.load("taro-200g"), root)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(
            {item["role"] for item in report["missing_required"]},
            {"packshot_front", "drink_hero"},
        )
        self.assertIn(
            "preparation_01",
            {item["role"] for item in report["missing_optional"]},
        )

    def test_validate_assets_cli_strict_and_non_strict(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(yoku_main, "ROOT", Path(root)), patch.object(
                yoku_main,
                "_catalogs",
                return_value=(self.products, self.templates, self.assets),
            ), redirect_stdout(io.StringIO()):
                self.assertEqual(
                    yoku_main.main(["validate-assets", "--product", "taro-200g"]),
                    0,
                )
                self.assertEqual(
                    yoku_main.main([
                        "validate-assets",
                        "--product",
                        "taro-200g",
                        "--strict",
                    ]),
                    1,
                )

    def test_list_assets_is_read_only(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root, "output")
            with patch.object(yoku_main, "ROOT", Path(root)), patch.object(
                yoku_main,
                "_catalogs",
                return_value=(self.products, self.templates, self.assets),
            ), redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(yoku_main.main(["list-assets"]), 0)
            self.assertFalse(output.exists())
            for product_id in PRODUCT_IDS:
                self.assertIn(product_id, stdout.getvalue())

    def _storyboard(self, template_id, root):
        product = self.products.load("taro-200g")
        template = self.templates.load(template_id)
        script = build_script(product, template)
        self.assertEqual(check_claims(script["script"], product)["status"], "PASS")
        manifest = self.assets.load(product["id"])
        report = validate_assets(manifest, root)
        return product, template, report, build_storyboard(
            product,
            template,
            script,
            manifest,
            report,
        )

    def test_storyboards_are_distinct_safe_and_product_scoped(self):
        with tempfile.TemporaryDirectory() as root:
            storyboards = {
                template_id: self._storyboard(template_id, root)[3]
                for template_id in TEMPLATE_IDS
            }
        self.assertEqual(
            len({json.dumps(value, sort_keys=True) for value in storyboards.values()}),
            len(TEMPLATE_IDS),
        )
        for template_id, storyboard in storyboards.items():
            template = self.templates.load(template_id)
            self.assertGreaterEqual(
                storyboard["total_duration_seconds"],
                template["target_duration_seconds"]["min"],
            )
            self.assertLessEqual(
                storyboard["total_duration_seconds"],
                template["target_duration_seconds"]["max"],
            )
            self.assertGreaterEqual(
                min(scene["duration_seconds"] for scene in storyboard["scenes"]),
                1.5,
            )
            for scene in storyboard["scenes"]:
                self.assertIn("assets/yoku/products/taro-200g/", scene["asset_path"])
                self.assertFalse(scene["asset_exists"])
            self.assertTrue(storyboard["warnings"])

    def test_srt_times_are_sequential(self):
        with tempfile.TemporaryDirectory() as root:
            storyboard = self._storyboard("ozon-recipe", root)[3]
        srt = build_srt(storyboard)
        self.assertIn("00:00:00,000 -->", srt)
        self.assertEqual(srt.count("-->"), len(storyboard["scenes"]))
        self.assertIn(storyboard["scenes"][0]["voiceover"], srt)

    def test_storyboard_package_contract_and_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            product, template, report, storyboard = self._storyboard(
                "ozon-recipe",
                root,
            )
            folder = create_storyboard_package(
                root,
                product,
                template,
                storyboard,
                report,
                build_srt(storyboard),
                now=datetime(2026, 7, 25, 12, 0, 0),
            )
            self.assertEqual(
                {path.name for path in folder.iterdir()},
                {
                    "storyboard.json",
                    "shot-list.md",
                    "voiceover.txt",
                    "subtitles-draft.srt",
                    "asset-report.json",
                    "metadata.json",
                    "review.md",
                },
            )
            metadata = json.loads(
                (folder / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertFalse(metadata["auto_publish"])
            self.assertFalse(metadata["video_generated"])
            self.assertFalse(metadata["external_services_used"])

    def test_claims_fail_does_not_create_storyboard_package(self):
        with tempfile.TemporaryDirectory() as root, patch(
            "src.yoku_main.check_claims",
            return_value={
                "status": "FAIL",
                "errors": [{"message": "test"}],
                "warnings": [],
                "checked_facts": {},
            },
        ), patch.object(yoku_main, "ROOT", Path(root)), patch.object(
            yoku_main,
            "_catalogs",
            return_value=(self.products, self.templates, self.assets),
        ), redirect_stdout(io.StringIO()):
            code = yoku_main.main([
                "storyboard",
                "--product",
                "taro-200g",
                "--template",
                "ozon-recipe",
                "--output-dir",
                str(Path(root, "output")),
            ])
            self.assertEqual(code, 1)
            self.assertFalse(Path(root, "output").exists())


if __name__ == "__main__":
    unittest.main()
