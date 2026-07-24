import json
import tempfile
import unittest
from pathlib import Path

from src.yoku.exceptions import CatalogValidationError, InvalidIdentifierError
from src.yoku.template_catalog import TemplateCatalog


class TemplateCatalogTests(unittest.TestCase):
    def setUp(self):
        self.source = Path("data/templates/ozon-recipe.json")

    def test_valid_template_loads(self):
        self.assertFalse(TemplateCatalog(self.source.parent).load("ozon-recipe")["auto_publish"])

    def _catalog(self, update):
        value = json.loads(self.source.read_text(encoding="utf-8"))
        value.update(update)
        temporary = tempfile.TemporaryDirectory()
        Path(temporary.name, "ozon-recipe.json").write_text(json.dumps(value), encoding="utf-8")
        self.addCleanup(temporary.cleanup)
        return TemplateCatalog(temporary.name)

    def test_auto_publish_is_rejected(self):
        with self.assertRaises(CatalogValidationError):
            self._catalog({"auto_publish": True}).load("ozon-recipe")

    def test_manual_review_is_required(self):
        with self.assertRaises(CatalogValidationError):
            self._catalog({"requires_manual_review": False}).load("ozon-recipe")

    def test_bad_duration_is_rejected(self):
        with self.assertRaises(CatalogValidationError):
            self._catalog({"target_duration_seconds": {"min": 20, "max": 15}}).load("ozon-recipe")

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(InvalidIdentifierError):
            TemplateCatalog(self.source.parent).load("../ozon-recipe")
