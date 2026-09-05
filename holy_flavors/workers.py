from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from holy_flavors.catalog import CatalogClient, cache_catalog_images, merge_catalog
from holy_flavors.models import Catalog


class CatalogRefreshWorker(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal(object, int, int)
    failed = pyqtSignal(str)

    def __init__(
        self,
        previous_catalog: Catalog,
        images_dir: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._previous_catalog = previous_catalog
        self._images_dir = images_dir

    def run(self) -> None:
        try:
            self.progress.emit("Loading catalog from HOLY …")
            client = CatalogClient()
            current = client.fetch_catalog()
            merged = merge_catalog(self._previous_catalog, current)
            self.progress.emit("Preparing product images for offline use …")
            downloaded, failed = cache_catalog_images(
                merged,
                self._images_dir,
                client.session,
            )
            self.completed.emit(merged, downloaded, failed)
        except Exception as exc:  # QThread must report failures to the UI thread.
            self.failed.emit(str(exc))
