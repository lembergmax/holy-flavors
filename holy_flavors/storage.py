from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from holy_flavors.models import Catalog, UserFlavorState, utc_now_iso
from holy_flavors.services import display_variant_title


class StorageError(RuntimeError):
    """Raised when persisted application data is invalid or unavailable."""


@dataclass(frozen=True, slots=True)
class AppPaths:
    project_dir: Path

    @property
    def data_dir(self) -> Path:
        return self.project_dir / "data"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def catalog_file(self) -> Path:
        return self.data_dir / "catalog_cache.json"

    @property
    def user_state_file(self) -> Path:
        return self.data_dir / "user_state.json"

    def ensure(self) -> None:
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)


class Storage:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.paths.ensure()

    def load_catalog(self) -> Catalog:
        if not self.paths.catalog_file.exists():
            return Catalog.empty()
        payload = self._read_json(self.paths.catalog_file)
        try:
            return Catalog.from_dict(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise StorageError(f"The local catalog is invalid: {exc}") from exc

    def save_catalog(self, catalog: Catalog) -> None:
        self._write_json(self.paths.catalog_file, catalog.to_dict())

    def load_user_states(self) -> dict[str, UserFlavorState]:
        if not self.paths.user_state_file.exists():
            return {}
        payload = self._read_json(self.paths.user_state_file)
        try:
            states = payload.get("flavors", {})
            if not isinstance(states, dict):
                raise TypeError("'flavors' must be an object")
            return {
                str(key): UserFlavorState.from_dict(value)
                for key, value in states.items()
            }
        except (TypeError, ValueError) as exc:
            raise StorageError(f"The ratings file is invalid: {exc}") from exc

    def save_user_states(self, states: dict[str, UserFlavorState]) -> None:
        payload = {
            "schema_version": 1,
            "updated_at": utc_now_iso(),
            "flavors": {
                key: state.to_dict() for key, state in sorted(states.items())
            },
        }
        self._write_json(self.paths.user_state_file, payload)

    def export_json(
        self,
        destination: Path,
        states: dict[str, UserFlavorState],
    ) -> None:
        payload = {
            "schema_version": 1,
            "exported_at": utc_now_iso(),
            "flavors": {
                key: state.to_dict() for key, state in sorted(states.items())
            },
        }
        self._write_json(destination, payload)

    def read_import(self, source: Path) -> dict[str, UserFlavorState]:
        payload = self._read_json(source)
        try:
            data = payload.get("flavors", {})
            if not isinstance(data, dict):
                raise TypeError("'flavors' must be an object")
            return {
                str(key): UserFlavorState.from_dict(value)
                for key, value in data.items()
            }
        except (TypeError, ValueError) as exc:
            raise StorageError(f"The selected backup is invalid: {exc}") from exc

    def create_backup(self) -> Path | None:
        if not self.paths.user_state_file.exists():
            return None
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = self.paths.backups_dir / f"user_state-{timestamp}.json"
        shutil.copy2(self.paths.user_state_file, destination)
        return destination

    def export_csv(
        self,
        destination: Path,
        catalog: Catalog,
        states: dict[str, UserFlavorState],
    ) -> None:
        with destination.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(
                [
                    "Category",
                    "Flavor",
                    "Tried",
                    "Rating",
                    "Note",
                    "Shopping list",
                    "Variant",
                    "Quantity",
                    "Availability",
                    "Product link",
                ]
            )
            for flavor in sorted(catalog.flavors, key=lambda item: (item.category, item.name)):
                state = states.get(flavor.source_key, UserFlavorState())
                variant = next(
                    (
                        item
                        for item in flavor.variants
                        if item.id == state.selected_variant_id
                    ),
                    None,
                )
                writer.writerow(
                    [
                        flavor.category,
                        flavor.name,
                        "Yes" if state.tried else "No",
                        "" if state.rating is None else str(state.rating).replace(".", ","),
                        state.note,
                        "Yes" if state.wishlist else "No",
                        display_variant_title(variant.title) if variant else "",
                        state.quantity,
                        (
                            "Archived"
                            if flavor.archived
                            else "Available" if flavor.available else "Sold out"
                        ),
                        flavor.product_url,
                    ]
                )

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"{path.name} could not be read: {exc}") from exc
        if not isinstance(payload, dict):
            raise StorageError(f"{path.name} must contain a JSON object.")
        return payload

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                delete=False,
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)
            os.replace(temporary_path, path)
        except OSError as exc:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
            raise StorageError(f"{path.name} could not be saved: {exc}") from exc
