import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import yoku_main


class CliTests(unittest.TestCase):
    def test_generate_creates_exact_package(self):
        with tempfile.TemporaryDirectory() as output:
            process = subprocess.run(
                [sys.executable, "src/yoku_main.py", "generate", "--product", "taro-100g", "--template", "ozon-recipe", "--output-dir", output],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            folder = next(Path(output).iterdir())
            self.assertEqual({item.name for item in folder.iterdir()}, {"brief.json", "script.txt", "claims-report.json", "metadata.json", "review.md"})
            self.assertEqual(json.loads((folder / "claims-report.json").read_text(encoding="utf-8"))["status"], "PASS")
            self.assertFalse(json.loads((folder / "metadata.json").read_text(encoding="utf-8"))["auto_publish"])

    def test_invalid_product_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as output:
            code = yoku_main.main(["generate", "--product", "missing", "--template", "ozon-recipe", "--output-dir", output])
            self.assertNotEqual(code, 0)
            self.assertEqual(list(Path(output).iterdir()), [])

    def test_fail_does_not_create_package(self):
        with tempfile.TemporaryDirectory() as output, patch("src.yoku_main.check_claims", return_value={"status": "FAIL", "errors": [{"message": "test"}], "warnings": [], "checked_facts": {}}):
            code = yoku_main.main(["generate", "--product", "taro-100g", "--template", "ozon-recipe", "--output-dir", output])
            self.assertEqual(code, 1)
            self.assertEqual(list(Path(output).iterdir()), [])
