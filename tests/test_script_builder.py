import unittest

from src.yoku.product_catalog import ProductCatalog
from src.yoku.script_builder import build_script
from src.yoku.template_catalog import TemplateCatalog


class ScriptBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product = ProductCatalog("data/products").load("taro-100g")
        cls.template = TemplateCatalog("data/templates").load("ozon-recipe")
        cls.result = build_script(cls.product, cls.template)

    def test_expected_structure(self):
        self.assertEqual(set(self.result), {"title", "script", "description", "facts_used", "product_id", "template_id"})

    def test_uses_catalog_facts(self):
        for value in ("100", "5", "20", "300", "Тайвань", "Yoku Tea"):
            self.assertIn(value, self.result["script"])

    def test_does_not_invent_recipe(self):
        lowered = self.result["script"].lower()
        for word in ("вода", "молоко", "лёд", "температур"):
            self.assertNotIn(word, lowered)
