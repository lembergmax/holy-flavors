from __future__ import annotations

import unittest

from holy_flavors.models import Catalog, Flavor, ProductVariant, UserFlavorState
from holy_flavors.services import (
    FilterOptions,
    apply_package_size_to_cart,
    build_cart_url,
    calculate_progress,
    display_variant_title,
    filter_and_sort_flavors,
    matching_available_variant,
    preview_import,
    validate_cart,
)


def flavor(
    key: str,
    name: str,
    category: str = "Energy",
    available: bool = True,
    archived: bool = False,
) -> Flavor:
    return Flavor(
        source_key=key,
        name=name,
        category=category,
        description=f"Beschreibung {name}",
        product_url=f"https://de.holy.com/products/{key}",
        image_url="",
        variants=(ProductVariant(100 + len(key), "50 Portionen", 3999, available),),
        archived=archived,
    )


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = flavor("energy:a", "Alpha")
        self.second = flavor("hydration:b", "Beta", "Hydration", available=False)
        self.archived = flavor("energy:c", "Alt", archived=True)
        self.catalog = Catalog((self.first, self.second, self.archived), "now")

    def test_filter_search_status_and_sort(self) -> None:
        states = {
            self.first.source_key: UserFlavorState(tried=True, rating=4.5),
            self.second.source_key: UserFlavorState(note="spritzig"),
        }

        searched = filter_and_sort_flavors(
            self.catalog,
            states,
            FilterOptions(search_text="spritzig"),
        )
        archived = filter_and_sort_flavors(
            self.catalog,
            states,
            FilterOptions(statuses=frozenset({"Archived"})),
        )

        self.assertEqual(["Beta"], [item.name for item in searched])
        self.assertEqual(["Alt"], [item.name for item in archived])

    def test_filter_combines_selected_categories(self) -> None:
        filtered = filter_and_sort_flavors(
            self.catalog,
            {},
            FilterOptions(categories=frozenset({"Energy", "Hydration"})),
        )
        hydration_only = filter_and_sort_flavors(
            self.catalog,
            {},
            FilterOptions(categories=frozenset({"Hydration"})),
        )

        self.assertEqual(["Alpha", "Beta"], [item.name for item in filtered])
        self.assertEqual(["Beta"], [item.name for item in hydration_only])

    def test_filter_combines_multiple_statuses_as_intersection(self) -> None:
        states = {
            self.first.source_key: UserFlavorState(tried=True, wishlist=True),
            self.second.source_key: UserFlavorState(tried=True, wishlist=True),
        }

        filtered = filter_and_sort_flavors(
            self.catalog,
            states,
            FilterOptions(
                statuses=frozenset({"Tried", "Shopping list", "Available"}),
            ),
        )

        self.assertEqual(["Alpha"], [item.name for item in filtered])

    def test_package_size_filter_requires_matching_available_variant(self) -> None:
        sized_flavor = Flavor(
            source_key="energy:sized",
            name="Sized",
            category="Energy",
            description="Test",
            product_url="https://de.holy.com/products/sized",
            image_url="https://cdn.example/product.png",
            variants=(
                ProductVariant(
                    1,
                    "1 Portion",
                    199,
                    True,
                    "https://cdn.example/sample.png",
                ),
                ProductVariant(
                    2,
                    "10 Portionen",
                    1299,
                    False,
                    "https://cdn.example/box.png",
                ),
                ProductVariant(
                    3,
                    "50 Portionen mit gratis Shaker",
                    3999,
                    True,
                    "https://cdn.example/tub.png",
                ),
            ),
        )
        catalog = Catalog((sized_flavor,), "now")

        samples = filter_and_sort_flavors(
            catalog,
            {},
            FilterOptions(package_size="Sample · 1 serving"),
        )
        boxes = filter_and_sort_flavors(
            catalog,
            {},
            FilterOptions(package_size="Box · 10 servings"),
        )
        tubs = filter_and_sort_flavors(
            catalog,
            {},
            FilterOptions(package_size="Tub · 50 servings"),
        )

        self.assertEqual([sized_flavor], samples)
        self.assertEqual([], boxes)
        self.assertEqual([sized_flavor], tubs)
        self.assertEqual(
            "https://cdn.example/sample.png",
            matching_available_variant(sized_flavor, "Sample · 1 serving").image_url,
        )

    def test_common_shopify_variant_titles_are_displayed_in_english(self) -> None:
        self.assertEqual(
            "50 servings with free shaker",
            display_variant_title("50 Portionen mit gratis Shaker"),
        )
        self.assertEqual("Mango", display_variant_title("Mango"))

    def test_progress_excludes_archived_flavors(self) -> None:
        states = {
            self.first.source_key: UserFlavorState(tried=True, rating=4.5),
            self.archived.source_key: UserFlavorState(tried=True, rating=5.0),
        }

        stats = calculate_progress(self.catalog, states)

        self.assertEqual((1, 2), (stats.tried, stats.total))
        self.assertEqual(4.5, stats.average_rating)

    def test_cart_url_contains_all_selected_variants_deterministically(self) -> None:
        third = flavor("milkshake:c", "Gamma", "Milkshake")
        catalog = Catalog((*self.catalog.flavors, third), "now")
        states = {
            self.first.source_key: UserFlavorState(
                wishlist=True,
                selected_variant_id=self.first.variants[0].id,
                quantity=2,
            ),
            self.second.source_key: UserFlavorState(
                wishlist=True,
                selected_variant_id=self.second.variants[0].id,
            ),
            third.source_key: UserFlavorState(
                wishlist=True,
                selected_variant_id=third.variants[0].id,
                quantity=3,
            ),
        }
        self.assertEqual(1, len(validate_cart(catalog, states)))
        states[self.second.source_key].wishlist = False

        url = build_cart_url(catalog, states)

        self.assertEqual(
            "https://de.holy.com/cart/"
            f"{self.first.variants[0].id}:2,{third.variants[0].id}:3?storefront=true",
            url,
        )

    def test_cart_rejects_missing_variant_and_empty_list(self) -> None:
        states = {self.first.source_key: UserFlavorState(wishlist=True)}
        self.assertEqual(
            "Please choose a package size.",
            validate_cart(self.catalog, states)[0].message,
        )
        with self.assertRaises(ValueError):
            build_cart_url(self.catalog, states)
        with self.assertRaises(ValueError):
            build_cart_url(self.catalog, {})

    def test_package_size_can_be_applied_to_cart_where_available(self) -> None:
        sample = Flavor(
            source_key="energy:sample",
            name="Sample",
            category="Energy",
            description="Test",
            product_url="https://de.holy.com/products/sample",
            image_url="",
            variants=(
                ProductVariant(1, "1 Portion", 199, True),
                ProductVariant(2, "50 Portionen", 3999, True),
            ),
        )
        box_only = Flavor(
            source_key="energy:box",
            name="Box",
            category="Energy",
            description="Test",
            product_url="https://de.holy.com/products/box",
            image_url="",
            variants=(ProductVariant(3, "10 Portionen", 1299, True),),
        )
        catalog = Catalog((sample, box_only), "now")
        states = {
            sample.source_key: UserFlavorState(wishlist=True),
            box_only.source_key: UserFlavorState(wishlist=True),
        }

        changed = apply_package_size_to_cart(catalog, states, "Tub · 50 servings")

        self.assertEqual(1, changed)
        self.assertEqual(2, states[sample.source_key].selected_variant_id)
        self.assertIsNone(states[box_only.source_key].selected_variant_id)

    def test_import_preview_distinguishes_new_changed_and_unchanged(self) -> None:
        current = {
            "same": UserFlavorState(tried=True),
            "changed": UserFlavorState(rating=2.0),
        }
        imported = {
            "same": UserFlavorState(tried=True),
            "changed": UserFlavorState(rating=4.0),
            "new": UserFlavorState(wishlist=True),
        }

        self.assertEqual((1, 1, 1), preview_import(current, imported))


if __name__ == "__main__":
    unittest.main()
