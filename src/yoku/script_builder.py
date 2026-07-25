"""Build a deterministic script solely from validated catalog facts."""


def build_script(product, template):
    facts = [
        f'{product["servings"]} порций',
        f'{product["package_weight_g"]} г в упаковке',
        f'по {product["dosage_g_per_drink"]} г на напиток',
        f'объём напитка {product["drink_volume_ml"]} мл',
        f'произведено в {product["country_of_origin"]}',
        product["positioning"],
    ]
    substitutions = {
        "product_name": product["name"],
        "brand": product["brand"],
        "servings": product["servings"],
        "package_weight_g": product["package_weight_g"],
        "dosage_g_per_drink": product["dosage_g_per_drink"],
        "drink_volume_ml": product["drink_volume_ml"],
        "country_of_origin": product["country_of_origin"],
        "positioning": product["positioning"],
        "cta": template["cta_template"],
    }
    script = " ".join(
        sentence.format_map(substitutions) for sentence in template["script_sentences"]
    )
    return {
        "title": f'{product["name"]} — {product["servings"]} порций дома',
        "script": script,
        "description": f'{product["name"]} {product["brand"]} для домашнего приготовления Bubble Tea.',
        "facts_used": facts,
        "product_id": product["id"],
        "template_id": template["id"],
    }
