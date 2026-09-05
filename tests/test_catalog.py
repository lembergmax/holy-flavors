from __future__ import annotations

import unittest
from unittest.mock import Mock

import requests

from holy_flavors.catalog import CatalogClient, CatalogError, merge_catalog, parse_collection
from holy_flavors.models import Catalog, Flavor, ProductVariant


def powder_product(
    product_type: str,
    title: str = "Test Sorte",
    handle: str = "test-sorte",
    available: bool = True,
) -> dict:
    return {
        "id": 1,
        "title": title,
        "handle": handle,
        "body_html": "<p>Fruchtig &amp; frisch</p>",
        "product_type": product_type,
        "variants": [
            {
                "id": 101,
                "title": "50 Portionen",
                "price": "39.99",
                "available": available,
                "featured_image": {"src": "https://cdn.example/dose.png"},
            }
        ],
        "images": [{"src": "https://cdn.example/test.png"}],
    }


class CatalogParserTests(unittest.TestCase):
    def test_parses_all_powder_categories(self) -> None:
        categories = (
            ("Energy", "01 - Energy Bundle"),
            ("Hydration", "03 - Hydration Bundle"),
            ("Iced Tea", "02 - Iced Tea Bundle"),
            ("Milkshake", "32 - Milkshake Bundle"),
        )

        for category, product_type in categories:
            with self.subTest(category=category):
                flavors = parse_collection(
                    category,
                    product_type,
                    [
                        powder_product(product_type),
                        powder_product("12 - Value Pack", "Starter", "starter"),
                    ],
                )
                self.assertEqual(1, len(flavors))
                self.assertEqual(category, flavors[0].category)
                self.assertEqual("Fruchtig & frisch", flavors[0].description)
                self.assertEqual(3999, flavors[0].variants[0].price_cents)
                self.assertEqual(
                    "https://cdn.example/dose.png",
                    flavors[0].variants[0].image_url,
                )

    def test_syrup_variants_become_individual_flavors(self) -> None:
        products = [
            {
                "title": "3er Box Syrup",
                "handle": "3er-set",
                "product_type": "43 - Syrup Bundle",
                "body_html": "",
                "variants": [
                    {"id": 1, "title": "Mango", "price": "9.99", "available": True},
                    {"id": 2, "title": "Peach", "price": "9.99", "available": False},
                ],
                "images": [{"src": "https://cdn.example/syrup.png"}],
            }
        ]

        flavors = parse_collection("Syrup", "43 - Syrup Bundle", products)

        self.assertEqual(["Mango", "Peach"], [item.name for item in flavors])
        self.assertTrue(flavors[0].available)
        self.assertFalse(flavors[1].available)
        self.assertEqual("syrup:3er-set:mango", flavors[0].source_key)

    def test_invalid_price_fails_instead_of_corrupting_catalog(self) -> None:
        product = powder_product("01 - Energy Bundle")
        product["variants"][0]["price"] = "kein-preis"

        with self.assertRaises(CatalogError):
            parse_collection("Energy", "01 - Energy Bundle", [product])

    def test_missing_flavor_is_archived_and_can_reappear(self) -> None:
        old_flavor = Flavor(
            source_key="energy:old",
            name="Old",
            category="Energy",
            description="",
            product_url="",
            image_url="",
            variants=(ProductVariant(1, "50 Portionen", 3999, True),),
        )
        previous = Catalog((old_flavor,), "old")

        archived = merge_catalog(previous, Catalog.empty())
        reappeared = merge_catalog(
            archived,
            Catalog((old_flavor,), "new"),
        )

        self.assertTrue(archived.flavors[0].archived)
        self.assertFalse(reappeared.flavors[0].archived)

    def test_partial_collection_failure_aborts_complete_refresh(self) -> None:
        session = Mock()
        session.headers = {}
        session.get.side_effect = requests.Timeout("Hydration nicht erreichbar")
        client = CatalogClient(session=session)

        with self.assertRaises(CatalogError):
            client.fetch_catalog()


if __name__ == "__main__":
    unittest.main()
