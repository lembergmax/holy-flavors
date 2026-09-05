from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QScrollArea

from holy_flavors.main_window import MainWindow
from holy_flavors.catalog import image_cache_path, variant_image_cache_path
from holy_flavors.models import Catalog, Flavor, ProductVariant, UserFlavorState
from holy_flavors.storage import AppPaths, Storage
from holy_flavors.styles import application_stylesheet
from holy_flavors.widgets import FlavorCard, FlavorGrid, RatingWidget


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_rating_widget_accepts_half_steps_and_keyboard(self) -> None:
        widget = RatingWidget()
        widget.show()
        widget.set_value(2.5)

        QTest.keyClick(widget, Qt.Key.Key_Right)
        QTest.keyClick(widget, Qt.Key.Key_Delete)

        self.assertIsNone(widget.value)

    def test_dropdown_popups_have_explicit_high_contrast_styles(self) -> None:
        stylesheet = application_stylesheet()

        self.assertIn("QComboBox QAbstractItemView", stylesheet)
        self.assertIn("selection-background-color: #FFD400", stylesheet)
        self.assertIn("selection-color: #050505", stylesheet)
        self.assertIn("QMenu::item:selected", stylesheet)

    def test_selected_card_has_thick_yellow_border(self) -> None:
        stylesheet = application_stylesheet()

        self.assertIn('QFrame#flavorCard[selected="true"]', stylesheet)
        self.assertIn("border: 5px solid #FFD400", stylesheet)
        self.assertIn(
            'QFrame#flavorCard[marked="true"][selected="true"]',
            stylesheet,
        )

    def test_categories_can_be_combined_and_all_resets_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            window = MainWindow(Storage(AppPaths(Path(temporary_directory))))

            window.category_buttons["Energy"].click()
            window.category_buttons["Hydration"].click()

            self.assertFalse(window.category_buttons["All"].isChecked())
            self.assertTrue(window.category_buttons["Energy"].isChecked())
            self.assertTrue(window.category_buttons["Hydration"].isChecked())

            window.category_buttons["All"].click()

            self.assertTrue(window.category_buttons["All"].isChecked())
            self.assertFalse(window.category_buttons["Energy"].isChecked())
            self.assertFalse(window.category_buttons["Hydration"].isChecked())
            window.close()

    def test_tried_view_hides_untried_sort_option(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            window = MainWindow(Storage(AppPaths(Path(temporary_directory))))
            window.sort_combo.setCurrentText("Not tried yet")

            window.status_actions["Tried"].setChecked(True)

            self.assertEqual(-1, window.sort_combo.findText("Not tried yet"))
            self.assertEqual("Category & name", window.sort_combo.currentText())

            window.clear_status_filters_action.trigger()

            self.assertGreaterEqual(window.sort_combo.findText("Not tried yet"), 0)
            window.close()

    def test_status_filters_can_be_combined_and_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            window = MainWindow(Storage(AppPaths(Path(temporary_directory))))

            window.status_actions["Tried"].setChecked(True)
            window.status_actions["Shopping list"].setChecked(True)
            window.status_actions["Available"].setChecked(True)

            self.assertEqual(
                frozenset({"Tried", "Shopping list", "Available"}),
                window._selected_statuses(),
            )
            self.assertEqual("Filter (3)", window.status_filter_button.text())

            window.clear_status_filters_action.trigger()

            self.assertEqual(frozenset(), window._selected_statuses())
            self.assertEqual("All", window.status_filter_button.text())
            window.close()

    def test_package_size_is_applied_alongside_status_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = Storage(AppPaths(Path(temporary_directory)))
            flavor = Flavor(
                source_key="energy:test",
                name="Test Raptor",
                category="Energy",
                description="Himbeere",
                product_url="https://de.holy.com/products/test",
                image_url="",
                variants=(
                    ProductVariant(123, "1 Portion", 199, True),
                    ProductVariant(124, "50 Portionen", 3999, False),
                ),
            )
            storage.save_catalog(Catalog((flavor,), "now"))
            window = MainWindow(storage)
            window.status_actions["Available"].setChecked(True)

            window.size_combo.setCurrentText("Sample · 1 serving")
            sample_count = len(window.flavor_grid._cards)
            window.size_combo.setCurrentText("Tub · 50 servings")
            tub_count = len(window.flavor_grid._cards)

            self.assertEqual(1, sample_count)
            self.assertEqual(0, tub_count)
            window.close()

    def test_card_uses_filtered_variant_image_before_product_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            images_dir = Path(temporary_directory)
            variant = ProductVariant(
                123,
                "1 Portion",
                199,
                True,
                "https://cdn.example/sample.png",
            )
            flavor = Flavor(
                source_key="energy:test",
                name="Test Raptor",
                category="Energy",
                description="Himbeere",
                product_url="https://de.holy.com/products/test",
                image_url="https://cdn.example/product.png",
                variants=(variant,),
            )
            product_image = QImage(20, 20, QImage.Format.Format_RGB32)
            product_image.fill(QColor("red"))
            product_image.save(str(image_cache_path(images_dir, flavor)), "PNG")
            sample_image = QImage(20, 20, QImage.Format.Format_RGB32)
            sample_image.fill(QColor("green"))
            sample_image.save(str(variant_image_cache_path(images_dir, variant)), "PNG")

            card = FlavorCard(
                flavor,
                UserFlavorState(),
                images_dir,
                variant,
            )
            rendered_image = card.image_label.pixmap().toImage()

            self.assertEqual(
                QColor("green"),
                rendered_image.pixelColor(
                    rendered_image.width() // 2,
                    rendered_image.height() // 2,
                ),
            )

    def test_main_window_starts_from_local_catalog_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = Storage(AppPaths(Path(temporary_directory)))
            catalog = Catalog(
                (
                    Flavor(
                        source_key="energy:test",
                        name="Test Raptor",
                        category="Energy",
                        description="Himbeere",
                        product_url="https://de.holy.com/products/test",
                        image_url="",
                        variants=(ProductVariant(123, "10 Portionen", 1249, True),),
                    ),
                ),
                "now",
            )
            storage.save_catalog(catalog)
            window = MainWindow(storage)
            window.show()
            self.app.processEvents()

            window._select_flavor("energy:test")
            window.rating_widget.set_value(4.5, emit=True)
            window._save_states()
            reloaded = storage.load_user_states()

            self.assertEqual(1, window.progress_bar.value())
            self.assertTrue(reloaded["energy:test"].tried)
            self.assertEqual(4.5, reloaded["energy:test"].rating)
            window.close()

    def test_flavor_grid_reflows_when_scroll_area_width_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            images_dir = Path(temporary_directory)
            grid = FlavorGrid()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(grid)
            cards = [
                FlavorCard(
                    Flavor(
                        source_key=f"energy:{index}",
                        name=f"Sorte {index}",
                        category="Energy",
                        description="Test",
                        product_url="https://de.holy.com",
                        image_url="",
                        variants=(ProductVariant(index + 1, "Box", 1000, True),),
                    ),
                    UserFlavorState(),
                    images_dir,
                )
                for index in range(6)
            ]
            grid.set_cards(cards)

            scroll.resize(1000, 600)
            scroll.show()
            self.app.processEvents()
            wide_fourth_card_y = cards[3].y()

            scroll.resize(500, 600)
            self.app.processEvents()
            narrow_fourth_card_y = cards[3].y()

            scroll.resize(1000, 600)
            self.app.processEvents()

            self.assertGreater(narrow_fourth_card_y, wide_fourth_card_y)
            self.assertEqual(wide_fourth_card_y, cards[3].y())
            scroll.close()

    def test_detail_sidebar_opens_on_selection_and_closes_with_button(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = Storage(AppPaths(Path(temporary_directory)))
            flavor = Flavor(
                source_key="energy:test",
                name="Test Raptor",
                category="Energy",
                description="Himbeere",
                product_url="https://de.holy.com/products/test",
                image_url="",
                variants=(ProductVariant(123, "10 Portionen", 1249, True),),
            )
            storage.save_catalog(Catalog((flavor,), "now"))
            window = MainWindow(storage)

            self.assertTrue(window.detail_scroll.isHidden())

            window._select_flavor(flavor.source_key)

            self.assertFalse(window.detail_scroll.isHidden())
            self.assertEqual(flavor.source_key, window._current_key)

            window.close_detail_button.click()

            self.assertTrue(window.detail_scroll.isHidden())
            self.assertIsNone(window._current_key)
            self.assertFalse(bool(window.flavor_grid._cards[0].property("selected")))
            window.close()

    def test_card_wishlist_button_marks_item_without_opening_details(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = Storage(AppPaths(Path(temporary_directory)))
            flavor = Flavor(
                source_key="energy:test",
                name="Test Raptor",
                category="Energy",
                description="Himbeere",
                product_url="https://de.holy.com/products/test",
                image_url="",
                variants=(ProductVariant(123, "10 Portionen", 1249, True),),
            )
            storage.save_catalog(Catalog((flavor,), "now"))
            window = MainWindow(storage)
            card = window.flavor_grid._cards[0]

            card.wishlist_button.click()
            window._save_states()

            self.assertTrue(window._states[flavor.source_key].wishlist)
            self.assertTrue(bool(window.flavor_grid._cards[0].property("marked")))
            self.assertEqual("✓ Saved", window.flavor_grid._cards[0].wishlist_button.text())
            self.assertEqual("Shopping list  1", window.shopping_button.text())
            self.assertTrue(window.detail_scroll.isHidden())
            self.assertTrue(storage.load_user_states()[flavor.source_key].wishlist)
            window.close()


if __name__ == "__main__":
    unittest.main()
