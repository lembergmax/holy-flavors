from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from holy_flavors.models import Catalog, Flavor, ProductVariant, UserFlavorState
from holy_flavors.storage import AppPaths, Storage, StorageError


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.temporary_directory.name)
        self.storage = Storage(AppPaths(self.project_dir))
        self.flavor = Flavor(
            source_key="energy:test",
            name="Äpfel & Beeren",
            category="Energy",
            description="Frisch",
            product_url="https://de.holy.com/products/test",
            image_url="",
            variants=(ProductVariant(123, "10 Portionen", 1249, True),),
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_catalog_and_user_state_survive_reload(self) -> None:
        catalog = Catalog((self.flavor,), "2026-09-04T00:00:00+00:00")
        states = {
            self.flavor.source_key: UserFlavorState(
                tried=True,
                rating=4.5,
                note="Sehr fruchtig",
                wishlist=True,
                selected_variant_id=123,
                quantity=2,
            )
        }

        self.storage.save_catalog(catalog)
        self.storage.save_user_states(states)

        self.assertEqual(catalog, self.storage.load_catalog())
        self.assertEqual(states, self.storage.load_user_states())

    def test_invalid_user_json_is_reported(self) -> None:
        self.storage.paths.user_state_file.write_text("{kaputt", encoding="utf-8")

        with self.assertRaises(StorageError):
            self.storage.load_user_states()

    def test_import_export_and_backup(self) -> None:
        states = {"energy:test": UserFlavorState(tried=True, rating=3.5)}
        self.storage.save_user_states(states)
        export_file = self.project_dir / "backup.json"

        self.storage.export_json(export_file, states)
        imported = self.storage.read_import(export_file)
        backup = self.storage.create_backup()

        self.assertEqual(states, imported)
        self.assertIsNotNone(backup)
        self.assertTrue(backup.exists())

    def test_csv_uses_semicolon_and_utf8_bom(self) -> None:
        destination = self.project_dir / "export.csv"
        states = {
            self.flavor.source_key: UserFlavorState(
                tried=True,
                rating=4.5,
                note="Süß; aber gut",
                wishlist=True,
                selected_variant_id=123,
            )
        }

        self.storage.export_csv(destination, Catalog((self.flavor,), "now"), states)

        raw = destination.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        with destination.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        self.assertEqual("Äpfel & Beeren", rows[1][1])
        self.assertEqual("4,5", rows[1][3])
        self.assertEqual("Süß; aber gut", rows[1][4])

    def test_out_of_range_rating_is_rejected(self) -> None:
        payload = {
            "schema_version": 1,
            "flavors": {"energy:test": {"rating": 4.3}},
        }
        self.storage.paths.user_state_file.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

        with self.assertRaises(StorageError):
            self.storage.load_user_states()


if __name__ == "__main__":
    unittest.main()
