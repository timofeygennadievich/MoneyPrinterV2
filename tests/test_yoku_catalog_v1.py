import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src import yoku_main
from src.yoku.claims_guard import check_claims
from src.yoku.product_catalog import ProductCatalog
from src.yoku.script_builder import build_script
from src.yoku.template_catalog import TemplateCatalog


PRODUCT_IDS = (
    "taro-100g", "taro-200g", "thai-tea-200g", "mokko-200g",
    "honey-melon-200g",
)
TEMPLATE_IDS = ("ozon-recipe", "ozon-objection", "social-result")


class YokuCatalogV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.products = ProductCatalog("data/products")
        cls.templates = TemplateCatalog("data/templates")

    def test_all_products_load_and_ids_are_unique(self):
        products = [self.products.load(product_id) for product_id in PRODUCT_IDS]
        self.assertEqual(len({product["id"] for product in products}), len(PRODUCT_IDS))

    def test_new_product_facts(self):
        expected = {
            "package_weight_g": 200,
            "servings": 7,
            "dosage_g_per_drink": 28,
            "drink_volume_ml": 400,
            "country_of_origin": "Тайвань",
        }
        for product_id in PRODUCT_IDS[1:]:
            with self.subTest(product_id=product_id):
                product = self.products.load(product_id)
                self.assertEqual({key: product[key] for key in expected}, expected)

    def test_all_templates_load_with_safety_flags(self):
        for template_id in TEMPLATE_IDS:
            with self.subTest(template_id=template_id):
                template = self.templates.load(template_id)
                self.assertTrue(template["requires_manual_review"])
                self.assertFalse(template["auto_publish"])

    def test_builder_does_not_add_taro_to_other_products(self):
        template = self.templates.load("ozon-recipe")
        for product_id in PRODUCT_IDS[2:]:
            with self.subTest(product_id=product_id):
                script = build_script(self.products.load(product_id), template)["script"]
                self.assertNotIn("таро", script.casefold())

    def test_every_product_script_passes_claims_guard(self):
        template = self.templates.load("ozon-recipe")
        for product_id in PRODUCT_IDS:
            with self.subTest(product_id=product_id):
                product = self.products.load(product_id)
                script = build_script(product, template)["script"]
                self.assertEqual(check_claims(script, product)["status"], "PASS")

    def _assert_list_command(self, command, expected_ids):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary, "output")
            with patch.object(yoku_main, "ROOT", Path(temporary)), redirect_stdout(io.StringIO()) as stdout:
                # Preserve read-only catalog access while making any accidental output observable.
                with patch.object(yoku_main, "ProductCatalog", lambda _path: self.products), \
                     patch.object(yoku_main, "TemplateCatalog", lambda _path: self.templates):
                    code = yoku_main.main([command])
            self.assertEqual(code, 0)
            for item_id in expected_ids:
                self.assertIn(item_id, stdout.getvalue())
            self.assertFalse(output_dir.exists())

    def test_list_products_is_read_only(self):
        self._assert_list_command("list-products", PRODUCT_IDS)

    def test_list_templates_is_read_only(self):
        self._assert_list_command("list-templates", TEMPLATE_IDS)
