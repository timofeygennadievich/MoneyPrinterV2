"""Command line entry point for the safe Yoku Tea Video Factory."""

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
from yoku.video_renderer import create_video_package


def _add_assets_root(parser):
    parser.add_argument(
        "--assets-root",
        type=Path,
        default=ROOT,
        help="корень, содержащий assets/yoku/products",
    )


def build_parser():
    parser = argparse.ArgumentParser(description="Yoku Tea: безопасные контент-пакеты")
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="сформировать безопасный черновик")
    generate.add_argument("--product", required=True)
    generate.add_argument("--template", required=True)
    generate.add_argument("--output-dir", type=Path, default=ROOT / "output")

    commands.add_parser("list-products", help="показать карточки товаров")
    commands.add_parser("list-templates", help="показать шаблоны контента")

    list_assets = commands.add_parser("list-assets", help="показать состояние медиаматериалов")
    _add_assets_root(list_assets)

    validate = commands.add_parser("validate-assets", help="проверить медиаматериалы")
    validate.add_argument("--product", required=True)
    validate.add_argument("--strict", action="store_true")
    _add_assets_root(validate)

    storyboard = commands.add_parser("storyboard", help="сформировать раскадровку")
    storyboard.add_argument("--product", required=True)
    storyboard.add_argument("--template", required=True)
    storyboard.add_argument("--output-dir", type=Path, default=ROOT / "output")
    _add_assets_root(storyboard)

    render = commands.add_parser("render-video", help="собрать локальный вертикальный MP4")
    render.add_argument("--product", required=True)
    render.add_argument("--template", required=True)
    render.add_argument("--output-dir", type=Path, default=ROOT / "output")
    render.add_argument("--width", type=int, default=1080)
    render.add_argument("--height", type=int, default=1920)
    render.add_argument("--fps", type=int, default=30)
    render.add_argument("--ffmpeg", default="ffmpeg")
    render.add_argument("--dry-run", action="store_true")
    _add_assets_root(render)
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
            approval = "approved" if entry.get("approved") else "not-approved"
            print(f'  {entry["role"]}: {entry["path"]} [{approval}]')
    for warning in report.get("warnings", []):
        print(f"Предупреждение: {warning}")


def _build_checked_storyboard(products, templates, assets, args):
    product = products.load(args.product)
    template = templates.load(args.template)
    script_result = build_script(product, template)
    claims_report = check_claims(script_result["script"], product)
    if claims_report["status"] == "FAIL":
        print("Claims Guard: FAIL")
        for error in claims_report["errors"]:
            print(f'- {error["message"]}')
        return None
    manifest = assets.load(args.product)
    asset_report = validate_assets(manifest, args.assets_root)
    storyboard = build_storyboard(
        product,
        template,
        script_result,
        manifest,
        asset_report,
    )
    return product, template, script_result, claims_report, asset_report, storyboard


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
                report = validate_assets(manifest, args.assets_root)
                print(f'{manifest["product_id"]} — {report["status"]}')
            return 0
        if args.command == "validate-assets":
            report = validate_assets(assets.load(args.product), args.assets_root)
            _print_asset_report(report)
            if args.strict and report["status"] == "INCOMPLETE":
                return 1
            return 0

        if args.command in {"storyboard", "render-video"}:
            checked = _build_checked_storyboard(products, templates, assets, args)
            if checked is None:
                return 1
            product, template, _, _, asset_report, storyboard = checked
            if args.command == "storyboard":
                folder = create_storyboard_package(
                    args.output_dir,
                    product,
                    template,
                    storyboard,
                    asset_report,
                    build_srt(storyboard),
                )
            else:
                folder = create_video_package(
                    args.output_dir,
                    product,
                    template,
                    storyboard,
                    args.assets_root,
                    ffmpeg=args.ffmpeg,
                    width=args.width,
                    height=args.height,
                    fps=args.fps,
                    dry_run=args.dry_run,
                )
            print(folder)
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
