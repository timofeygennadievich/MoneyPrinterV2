"""Command line entry point for the safe Yoku Tea Video Factory MVP."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yoku.asset_catalog import AssetCatalog, validate_assets
from yoku.claims_guard import check_claims
from yoku.exceptions import YokuError
from yoku.product_catalog import ProductCatalog
from yoku.review_package import create_review_package
from yoku.script_builder import build_script
from yoku.storyboard_builder import build_storyboard
from yoku.storyboard_package import create_storyboard_package
from yoku.subtitle_builder import build_srt
from yoku.template_catalog import TemplateCatalog


def build_parser():
    parser = argparse.ArgumentParser(description="Yoku Tea: безопасные контент-пакеты")
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="сформировать безопасный черновик")
    generate.add_argument("--product", required=True)
    generate.add_argument("--template", required=True)
    generate.add_argument("--output-dir", type=Path, default=ROOT / "output")

    commands.add_parser("list-products", help="показать карточки товаров")
    commands.add_parser("list-templates", help="показать шаблоны контента")
    commands.add_parser("list-assets", help="показать состояние медиаматериалов")

    validate = commands.add_parser("validate-assets", help="проверить медиаматериалы")
    validate.add_argument("--product", required=True)
    validate.add_argument("--strict", action="store_true")

    storyboard = commands.add_parser("storyboard", help="сформировать раскадровку")
    storyboard.add_argument("--product", required=True)
    storyboard.add_argument("--template", required=True)
    storyboard.add_argument("--output-dir", type=Path, default=ROOT / "output")
    return parser


def _catalogs():
    products = ProductCatalog(ROOT / "data" / "products")
    templates = TemplateCatalog(ROOT / "data" / "templates")
    assets = AssetCatalog(ROOT / "data" / "media", products)
    return products, templates, assets


def _print_asset_report(report):
    print(f'{report["product_id"]}: {report["status"]}')
    for title, key in (
        ("Найдены", "found"),
        ("Нет обязательных", "missing_required"),
        ("Нет необязательных", "missing_optional"),
    ):
        print(f"{title}:")
        entries = report[key]
        if not entries:
            print("  —")
        for entry in entries:
            print(f'  {entry["role"]}: {entry["path"]}')


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        products, templates, assets = _catalogs()
        if args.command == "list-products":
            for product in products.list():
                print(
                    f'{product["id"]} — {product["name"]}, '
                    f'{product["package_weight_g"]} г, {product["servings"]} порций'
                )
            return 0
        if args.command == "list-templates":
            for template in templates.list():
                duration = template["target_duration_seconds"]
                print(
                    f'{template["id"]} — {template["purpose"]}, '
                    f'{duration["min"]}–{duration["max"]} секунд'
                )
            return 0
        if args.command == "list-assets":
            for manifest in assets.list():
                report = validate_assets(manifest, ROOT)
                print(f'{manifest["product_id"]} — {report["status"]}')
            return 0
        if args.command == "validate-assets":
            report = validate_assets(assets.load(args.product), ROOT)
            _print_asset_report(report)
            if args.strict and report["status"] == "INCOMPLETE":
                return 1
            return 0

        product = products.load(args.product)
        template = templates.load(args.template)
        script_result = build_script(product, template)
        claims_report = check_claims(script_result["script"], product)
        if claims_report["status"] == "FAIL":
            print("Claims Guard: FAIL")
            for error in claims_report["errors"]:
                print(f'- {error["message"]}')
            return 1

        if args.command == "storyboard":
            manifest = assets.load(args.product)
            asset_report = validate_assets(manifest, ROOT)
            storyboard = build_storyboard(
                product,
                template,
                script_result,
                manifest,
                asset_report,
            )
            subtitles = build_srt(storyboard)
            folder = create_storyboard_package(
                args.output_dir,
                product,
                template,
                storyboard,
                asset_report,
                subtitles,
            )
            print(folder)
            return 0

        folder = create_review_package(
            args.output_dir,
            product,
            template,
            script_result,
            claims_report,
        )
        print(folder)
        return 0
    except YokuError as error:
        print(f"Ошибка: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
