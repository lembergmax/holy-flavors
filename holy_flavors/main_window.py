from __future__ import annotations

import random
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QCloseEvent, QDesktopServices, QPixmap, QStandardItemModel
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from holy_flavors.catalog import image_cache_path, variant_image_cache_path
from holy_flavors.dialogs import ShoppingListDialog
from holy_flavors.models import CATEGORIES, Catalog, Flavor, ProductVariant, UserFlavorState
from holy_flavors.services import (
    FilterOptions,
    PACKAGE_SIZES,
    calculate_progress,
    filter_and_sort_flavors,
    get_state,
    display_variant_title,
    matching_available_variant,
    preview_import,
)
from holy_flavors.storage import Storage, StorageError
from holy_flavors.styles import CATEGORY_COLORS, HOLY_YELLOW, INK
from holy_flavors.widgets import FlavorCard, FlavorGrid, RatingWidget
from holy_flavors.workers import CatalogRefreshWorker


SORT_OPTIONS = (
    "Category & name",
    "Name",
    "Rating",
    "Availability",
    "Not tried yet",
)
STATUS_FILTERS = (
    "Tried",
    "Not tried yet",
    "Shopping list",
    "Available",
    "Sold out",
    "Archived",
)


class MainWindow(QMainWindow):
    def __init__(
        self,
        storage: Storage,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._storage = storage
        self._catalog = Catalog.empty()
        self._states: dict[str, UserFlavorState] = {}
        self._current_key: str | None = None
        self._updating_detail = False
        self._updating_categories = False
        self._refresh_worker: CatalogRefreshWorker | None = None
        self._load_errors: list[str] = []
        self._load_data()

        self.setWindowTitle("HOLY Flavors")
        self.setMinimumSize(1120, 720)
        self.resize(1480, 900)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(450)
        self._save_timer.timeout.connect(self._save_states)

        self._build_ui()
        self._connect_signals()
        self._refresh_view()
        QTimer.singleShot(0, self._show_load_errors)

    def _load_data(self) -> None:
        try:
            self._catalog = self._storage.load_catalog()
        except StorageError as exc:
            self._load_errors.append(str(exc))
        try:
            self._states = self._storage.load_user_states()
        except StorageError as exc:
            self._load_errors.append(str(exc))

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_header())
        root_layout.addWidget(self._build_progress_band())
        root_layout.addWidget(self._build_content(), 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready · the catalog refreshes only when requested")

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(22, 13, 22, 13)
        layout.setSpacing(12)

        brand = QLabel("HOLY FLAVORS")
        brand.setObjectName("brand")
        layout.addWidget(brand)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search flavors, categories, or notes")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(300)
        self.search_edit.setMaximumWidth(520)
        layout.addWidget(self.search_edit, 1)

        self.shopping_button = QPushButton("Shopping list")
        self.shopping_button.setObjectName("yellowButton")
        layout.addWidget(self.shopping_button)

        self.refresh_button = QPushButton("Refresh catalog")
        self.refresh_button.setObjectName("primaryButton")
        layout.addWidget(self.refresh_button)

        self.data_button = QToolButton()
        self.data_button.setText("Data")
        self.data_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        data_menu = QMenu(self.data_button)
        self.import_action = QAction("Import JSON backup …", self)
        self.export_json_action = QAction("Export JSON backup …", self)
        self.export_csv_action = QAction("Export ratings as CSV …", self)
        data_menu.addAction(self.import_action)
        data_menu.addSeparator()
        data_menu.addAction(self.export_json_action)
        data_menu.addAction(self.export_csv_action)
        self.data_button.setMenu(data_menu)
        layout.addWidget(self.data_button)
        return header

    def _build_progress_band(self) -> QWidget:
        band = QWidget()
        band.setObjectName("progressBand")
        layout = QHBoxLayout(band)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(16)

        stat_box = QVBoxLayout()
        self.progress_value = QLabel("0 / 0")
        self.progress_value.setObjectName("statValue")
        progress_caption = QLabel("Flavors tried")
        stat_box.addWidget(self.progress_value)
        stat_box.addWidget(progress_caption)
        layout.addLayout(stat_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(13)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ background: #4A4A4A; border: 0; border-radius: 6px; }}"
            f"QProgressBar::chunk {{ background: {HOLY_YELLOW}; border-radius: 6px; }}"
        )
        layout.addWidget(self.progress_bar, 1)

        self.category_progress = QLabel("No catalog loaded yet")
        self.category_progress.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.category_progress.setWordWrap(True)
        layout.addWidget(self.category_progress, 2)

        self.average_rating = QLabel("Ø –")
        self.average_rating.setObjectName("statValue")
        layout.addWidget(self.average_rating)
        return band

    def _build_content(self) -> QWidget:
        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.addWidget(self._build_filter_panel())

        self.flavor_grid = FlavorGrid()
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setWidget(self.flavor_grid)
        self.content_splitter.addWidget(self.grid_scroll)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_scroll.setWidget(self._build_detail_panel())
        self.content_splitter.addWidget(self.detail_scroll)
        self.content_splitter.setSizes([205, 850, 390])
        self.content_splitter.setStretchFactor(1, 1)
        self.detail_scroll.hide()
        return self.content_splitter

    def _build_filter_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("filterPanel")
        panel.setMinimumWidth(195)
        panel.setMaximumWidth(235)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 18, 14, 18)
        layout.setSpacing(10)

        title = QLabel("Discover")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.category_group = QButtonGroup(self)
        self.category_group.setExclusive(False)
        self.category_buttons: dict[str, QPushButton] = {}
        for category in ("All", *CATEGORIES):
            button = QPushButton(category)
            button.setObjectName("categoryButton")
            button.setCheckable(True)
            button.setChecked(category == "All")
            self.category_group.addButton(button)
            self.category_buttons[category] = button
            layout.addWidget(button)

        layout.addSpacing(8)
        status_label = QLabel("Filter")
        status_label.setObjectName("brandSmall")
        layout.addWidget(status_label)
        self.status_filter_button = QToolButton()
        self.status_filter_button.setText("All")
        self.status_filter_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.status_filter_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.status_filter_menu = QMenu(self.status_filter_button)
        self.status_actions: dict[str, QAction] = {}
        for status in STATUS_FILTERS:
            action = QAction(status, self)
            action.setCheckable(True)
            self.status_filter_menu.addAction(action)
            self.status_actions[status] = action
        self.status_filter_menu.addSeparator()
        self.clear_status_filters_action = QAction("Clear all filters", self)
        self.status_filter_menu.addAction(self.clear_status_filters_action)
        self.status_filter_button.setMenu(self.status_filter_menu)
        layout.addWidget(self.status_filter_button)

        size_label = QLabel("Package size")
        size_label.setObjectName("brandSmall")
        layout.addWidget(size_label)
        self.size_combo = QComboBox()
        self.size_combo.addItems(PACKAGE_SIZES)
        layout.addWidget(self.size_combo)

        sort_label = QLabel("Sort by")
        sort_label.setObjectName("brandSmall")
        layout.addWidget(sort_label)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(SORT_OPTIONS)
        layout.addWidget(self.sort_combo)

        self.random_button = QPushButton("Surprise me")
        self.random_button.setToolTip("Picks a visible flavor you have not tried yet")
        layout.addWidget(self.random_button)
        layout.addStretch()

        self.catalog_info = QLabel()
        self.catalog_info.setObjectName("muted")
        self.catalog_info.setWordWrap(True)
        layout.addWidget(self.catalog_info)
        return panel

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("detailPanel")
        panel.setMinimumWidth(350)
        panel.setMaximumWidth(450)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 24)
        layout.setSpacing(11)

        close_row = QHBoxLayout()
        close_row.addStretch()
        self.close_detail_button = QToolButton()
        self.close_detail_button.setObjectName("closeDetailButton")
        self.close_detail_button.setText("×")
        self.close_detail_button.setToolTip("Close details")
        self.close_detail_button.setAccessibleName("Close details")
        close_row.addWidget(self.close_detail_button)
        layout.addLayout(close_row)

        self.detail_content = QWidget()
        detail_layout = QVBoxLayout(self.detail_content)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)

        self.detail_image = QLabel()
        self.detail_image.setMinimumHeight(260)
        self.detail_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_layout.addWidget(self.detail_image)

        self.detail_category = QLabel()
        self.detail_category.setObjectName("pill")
        self.detail_category.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        detail_layout.addWidget(self.detail_category)

        self.detail_title = QLabel()
        self.detail_title.setObjectName("detailTitle")
        self.detail_title.setWordWrap(True)
        detail_layout.addWidget(self.detail_title)

        self.detail_status = QLabel()
        self.detail_status.setObjectName("brandSmall")
        detail_layout.addWidget(self.detail_status)

        self.detail_description = QLabel()
        self.detail_description.setObjectName("description")
        self.detail_description.setWordWrap(True)
        detail_layout.addWidget(self.detail_description)

        self.product_button = QPushButton("View product at HOLY")
        detail_layout.addWidget(self.product_button)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #C9C8C1;")
        detail_layout.addWidget(divider)

        self.tried_check = QCheckBox("I have tried this")
        detail_layout.addWidget(self.tried_check)
        rating_label = QLabel("Your rating")
        rating_label.setObjectName("brandSmall")
        detail_layout.addWidget(rating_label)
        rating_row = QHBoxLayout()
        self.rating_widget = RatingWidget()
        rating_row.addWidget(self.rating_widget)
        self.clear_rating_button = QPushButton("Clear")
        self.clear_rating_button.setMaximumWidth(78)
        rating_row.addWidget(self.clear_rating_button)
        rating_row.addStretch()
        detail_layout.addLayout(rating_row)

        note_label = QLabel("Tasting note")
        note_label.setObjectName("brandSmall")
        detail_layout.addWidget(note_label)
        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText(
            "What did you like? How sweet or intense was this flavor?"
        )
        self.note_edit.setMaximumHeight(105)
        detail_layout.addWidget(self.note_edit)

        self.wishlist_check = QCheckBox("Add to shopping list")
        detail_layout.addWidget(self.wishlist_check)

        variant_label = QLabel("Package size")
        variant_label.setObjectName("brandSmall")
        detail_layout.addWidget(variant_label)
        self.variant_combo = QComboBox()
        detail_layout.addWidget(self.variant_combo)

        quantity_row = QHBoxLayout()
        quantity_row.addWidget(QLabel("Quantity"))
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 99)
        quantity_row.addWidget(self.quantity_spin)
        quantity_row.addStretch()
        detail_layout.addLayout(quantity_row)

        detail_layout.addStretch()
        layout.addWidget(self.detail_content)
        return panel

    def _connect_signals(self) -> None:
        self.search_edit.textChanged.connect(self._refresh_cards)
        for category, button in self.category_buttons.items():
            button.toggled.connect(
                lambda checked, value=category: self._category_toggled(value, checked)
            )
        for action in self.status_actions.values():
            action.toggled.connect(self._status_filters_changed)
        self.clear_status_filters_action.triggered.connect(self._clear_status_filters)
        self.size_combo.currentTextChanged.connect(self._size_filter_changed)
        self.sort_combo.currentTextChanged.connect(self._refresh_cards)
        self.flavor_grid.flavor_selected.connect(self._select_flavor)
        self.close_detail_button.clicked.connect(self._close_detail)
        self.random_button.clicked.connect(self._pick_random)
        self.refresh_button.clicked.connect(self._start_refresh)
        self.shopping_button.clicked.connect(self._open_shopping_list)
        self.import_action.triggered.connect(self._import_json)
        self.export_json_action.triggered.connect(self._export_json)
        self.export_csv_action.triggered.connect(self._export_csv)

        self.product_button.clicked.connect(self._open_product)
        self.tried_check.toggled.connect(self._tried_changed)
        self.rating_widget.value_changed.connect(self._rating_changed)
        self.clear_rating_button.clicked.connect(
            lambda: self.rating_widget.set_value(None, emit=True)
        )
        self.note_edit.textChanged.connect(self._note_changed)
        self.wishlist_check.toggled.connect(self._wishlist_changed)
        self.variant_combo.currentIndexChanged.connect(self._variant_changed)
        self.quantity_spin.valueChanged.connect(self._quantity_changed)

    def _refresh_view(self) -> None:
        self._refresh_cards()
        self._update_progress()
        self._update_header_counts()
        self._update_catalog_info()

    def _category_toggled(self, category: str, checked: bool) -> None:
        if self._updating_categories:
            return

        self._updating_categories = True
        try:
            if category == "All":
                if checked:
                    for name, button in self.category_buttons.items():
                        if name != "All":
                            button.setChecked(False)
                elif not self._selected_categories():
                    self.category_buttons["All"].setChecked(True)
            elif checked:
                self.category_buttons["All"].setChecked(False)
            elif not self._selected_categories():
                self.category_buttons["All"].setChecked(True)
        finally:
            self._updating_categories = False
        self._refresh_cards()

    def _selected_categories(self) -> frozenset[str]:
        return frozenset(
            category
            for category in CATEGORIES
            if self.category_buttons[category].isChecked()
        )

    def _selected_statuses(self) -> frozenset[str]:
        return frozenset(
            status for status, action in self.status_actions.items() if action.isChecked()
        )

    def _status_filters_changed(self, _checked: bool = False) -> None:
        statuses = self._selected_statuses()
        current_sort = self.sort_combo.currentText()
        allowed_options = tuple(
            option
            for option in SORT_OPTIONS
            if not ("Tried" in statuses and option == "Not tried yet")
        )
        previous_block_state = self.sort_combo.blockSignals(True)
        self.sort_combo.clear()
        self.sort_combo.addItems(allowed_options)
        self.sort_combo.setCurrentText(
            current_sort if current_sort in allowed_options else "Category & name"
        )
        self.sort_combo.blockSignals(previous_block_state)
        self._update_status_filter_button(statuses)
        self._refresh_cards()

    def _clear_status_filters(self, _checked: bool = False) -> None:
        for action in self.status_actions.values():
            previous_block_state = action.blockSignals(True)
            action.setChecked(False)
            action.blockSignals(previous_block_state)
        self._status_filters_changed()

    def _update_status_filter_button(self, statuses: frozenset[str]) -> None:
        if not statuses:
            self.status_filter_button.setText("All")
            self.status_filter_button.setToolTip("No additional filters active")
        elif len(statuses) == 1:
            self.status_filter_button.setText(next(iter(statuses)))
            self.status_filter_button.setToolTip("One filter active")
        else:
            self.status_filter_button.setText(f"Filter ({len(statuses)})")
            self.status_filter_button.setToolTip(
                "Active: " + ", ".join(status for status in STATUS_FILTERS if status in statuses)
            )

    def _size_filter_changed(self, _package_size: str) -> None:
        self._refresh_cards()
        current = self._current()
        if current is not None:
            self._populate_detail(current[0])

    def _refresh_cards(self) -> None:
        options = FilterOptions(
            search_text=self.search_edit.text(),
            categories=self._selected_categories(),
            statuses=self._selected_statuses(),
            package_size=self.size_combo.currentText(),
            sort_by=self.sort_combo.currentText(),
        )
        flavors = filter_and_sort_flavors(self._catalog, self._states, options)
        cards: list[FlavorCard] = []
        for flavor in flavors:
            card = FlavorCard(
                flavor,
                self._states.get(flavor.source_key, UserFlavorState()),
                self._storage.paths.images_dir,
                matching_available_variant(flavor, self.size_combo.currentText()),
            )
            card.wishlist_toggled.connect(self._card_wishlist_toggled)
            cards.append(card)
        empty_text = (
            "No flavors match the active filters."
            if self._catalog.flavors
            else "No flavors are available yet.\nRefresh the catalog to get started."
        )
        self.flavor_grid.set_cards(cards, empty_text)
        self.flavor_grid.select_card(self._current_key)
        self.statusBar().showMessage(
            f"{len(flavors)} flavors visible · catalog refreshes only when requested"
        )

    def _select_flavor(self, source_key: str) -> None:
        flavor = self._catalog.by_key().get(source_key)
        if flavor is None:
            return
        self._current_key = source_key
        self.flavor_grid.select_card(source_key)
        self._populate_detail(flavor)
        self.detail_scroll.show()

    def _close_detail(self) -> None:
        self._current_key = None
        self.flavor_grid.select_card(None)
        self.detail_scroll.hide()

    def _populate_detail(self, flavor: Flavor) -> None:
        state = get_state(self._states, flavor.source_key)
        self._updating_detail = True
        try:
            self._set_detail_image(flavor, self._display_variant(flavor, state))
            self.detail_category.setText(flavor.category)
            self.detail_category.setStyleSheet(
                f"background: {CATEGORY_COLORS[flavor.category]}; color: {INK};"
            )
            self.detail_title.setText(flavor.name)
            if flavor.archived:
                self.detail_status.setText("Archived · no longer in the current catalog")
            elif flavor.available:
                self.detail_status.setText("Available now")
            else:
                self.detail_status.setText("Currently sold out")
            self.detail_description.setText(
                flavor.description or "No description is available for this flavor."
            )
            self.product_button.setEnabled(bool(flavor.product_url) and not flavor.archived)
            self.tried_check.setChecked(state.tried)
            self.rating_widget.set_value(state.rating)
            self.note_edit.setPlainText(state.note)
            self.wishlist_check.setChecked(state.wishlist)
            self.wishlist_check.setEnabled(not flavor.archived)
            self._populate_variants(flavor, state)
            self.quantity_spin.setValue(state.quantity)
            self.variant_combo.setEnabled(not flavor.archived)
            self.quantity_spin.setEnabled(not flavor.archived)
        finally:
            self._updating_detail = False

    def _display_variant(
        self,
        flavor: Flavor,
        state: UserFlavorState,
    ) -> ProductVariant | None:
        selected = next(
            (
                variant
                for variant in flavor.variants
                if variant.id == state.selected_variant_id
            ),
            None,
        )
        return selected or matching_available_variant(
            flavor,
            self.size_combo.currentText(),
        )

    def _set_detail_image(
        self,
        flavor: Flavor,
        variant: ProductVariant | None = None,
    ) -> None:
        paths: list[Path] = []
        if variant is not None:
            paths.append(variant_image_cache_path(self._storage.paths.images_dir, variant))
        paths.append(image_cache_path(self._storage.paths.images_dir, flavor))
        for path in paths:
            if not path.exists():
                continue
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.detail_image.setPixmap(
                    pixmap.scaled(
                        380,
                        270,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.detail_image.setText("")
                self.detail_image.setStyleSheet("background: #EFEDE6; border-radius: 12px;")
                return
        self.detail_image.setPixmap(QPixmap())
        self.detail_image.setText(flavor.name[:1].upper())
        self.detail_image.setStyleSheet(
            f"background: {CATEGORY_COLORS[flavor.category]}; border-radius: 12px; "
            "font: 900 60pt 'Bahnschrift Condensed';"
        )

    def _populate_variants(
        self,
        flavor: Flavor,
        state: UserFlavorState,
    ) -> None:
        self.variant_combo.clear()
        self.variant_combo.addItem("Choose a package size", None)
        for variant in flavor.variants:
            price = f"€{variant.price_cents / 100:.2f}"
            suffix = "" if variant.available else " · sold out"
            self.variant_combo.addItem(
                f"{display_variant_title(variant.title)} · {price}{suffix}",
                variant.id,
            )
            model = self.variant_combo.model()
            if isinstance(model, QStandardItemModel) and not variant.available:
                item = model.item(self.variant_combo.count() - 1)
                if item:
                    item.setEnabled(False)
            if variant.id == state.selected_variant_id:
                self.variant_combo.setCurrentIndex(self.variant_combo.count() - 1)

    def _update_progress(self) -> None:
        stats = calculate_progress(self._catalog, self._states)
        self.progress_value.setText(f"{stats.tried} / {stats.total}")
        self.progress_bar.setMaximum(max(1, stats.total))
        self.progress_bar.setValue(stats.tried)
        self.average_rating.setText(
            "Avg –"
            if stats.average_rating is None
            else f"Avg {stats.average_rating:.1f} ★"
        )
        self.category_progress.setText(
            "   ".join(
                f"{category}: {tried}/{total}"
                for category, (tried, total) in stats.by_category.items()
            )
            or "No catalog loaded yet"
        )

    def _update_header_counts(self) -> None:
        wishlist_count = sum(state.wishlist for state in self._states.values())
        self.shopping_button.setText(f"Shopping list  {wishlist_count}")

    def _update_catalog_info(self) -> None:
        active = sum(not flavor.archived for flavor in self._catalog.flavors)
        archived = sum(flavor.archived for flavor in self._catalog.flavors)
        if not self._catalog.fetched_at:
            text = "No local catalog yet.\nClick ‘Refresh catalog’."
        else:
            fetched = self._catalog.fetched_at.replace("T", " ").split("+")[0]
            text = f"{active} active flavors\nUpdated: {fetched} UTC"
            if archived:
                text += f"\n{archived} archived"
        self.catalog_info.setText(text)

    def _current(self) -> tuple[Flavor, UserFlavorState] | None:
        if self._current_key is None:
            return None
        flavor = self._catalog.by_key().get(self._current_key)
        if flavor is None:
            return None
        return flavor, get_state(self._states, flavor.source_key)

    def _tried_changed(self, checked: bool) -> None:
        if self._updating_detail:
            return
        current = self._current()
        if current is None:
            return
        flavor, state = current
        if not checked and (state.rating is not None or state.note.strip()):
            answer = QMessageBox.question(
                self,
                "Remove rating",
                "Turning off ‘I have tried this’ will delete the rating and "
                "tasting note. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._updating_detail = True
                self.tried_check.setChecked(True)
                self._updating_detail = False
                return
            state.rating = None
            state.note = ""
            self._updating_detail = True
            self.rating_widget.set_value(None)
            self.note_edit.clear()
            self._updating_detail = False
        state.tried = checked
        self._state_changed(flavor)

    def _rating_changed(self, value: float | None) -> None:
        if self._updating_detail:
            return
        current = self._current()
        if current is None:
            return
        flavor, state = current
        state.rating = value
        if value is not None:
            state.tried = True
            self._updating_detail = True
            self.tried_check.setChecked(True)
            self._updating_detail = False
        self._state_changed(flavor)

    def _note_changed(self) -> None:
        if self._updating_detail:
            return
        current = self._current()
        if current is None:
            return
        _flavor, state = current
        state.note = self.note_edit.toPlainText()
        self._schedule_save()

    def _wishlist_changed(self, checked: bool) -> None:
        if self._updating_detail:
            return
        current = self._current()
        if current is None:
            return
        flavor, state = current
        self._set_wishlist_state(flavor, state, checked)
        if checked and flavor.category == "Syrup" and len(flavor.variants) == 1:
            self._updating_detail = True
            self._populate_variants(flavor, state)
            self._updating_detail = False
        self._state_changed(flavor)

    def _card_wishlist_toggled(self, source_key: str, checked: bool) -> None:
        flavor = self._catalog.by_key().get(source_key)
        if flavor is None or flavor.archived:
            return
        state = get_state(self._states, source_key)
        self._set_wishlist_state(flavor, state, checked)
        self._state_changed(flavor)
        if self._current_key == source_key:
            self._populate_detail(flavor)

    @staticmethod
    def _set_wishlist_state(
        flavor: Flavor,
        state: UserFlavorState,
        checked: bool,
    ) -> None:
        state.wishlist = checked
        if checked and flavor.category == "Syrup" and len(flavor.variants) == 1:
            only_variant = flavor.variants[0]
            if only_variant.available:
                state.selected_variant_id = only_variant.id

    def _variant_changed(self, _index: int) -> None:
        if self._updating_detail:
            return
        current = self._current()
        if current is None:
            return
        flavor, state = current
        value = self.variant_combo.currentData()
        state.selected_variant_id = int(value) if value is not None else None
        selected_variant = next(
            (
                variant
                for variant in flavor.variants
                if variant.id == state.selected_variant_id
            ),
            None,
        )
        self._set_detail_image(flavor, selected_variant)
        self._state_changed(flavor, refresh_cards=False)

    def _quantity_changed(self, value: int) -> None:
        if self._updating_detail:
            return
        current = self._current()
        if current is None:
            return
        _flavor, state = current
        state.quantity = value
        self._schedule_save()

    def _state_changed(self, flavor: Flavor, refresh_cards: bool = True) -> None:
        self._schedule_save()
        self._update_progress()
        self._update_header_counts()
        if refresh_cards:
            self._refresh_cards()
            self.flavor_grid.select_card(flavor.source_key)

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def _save_states(self) -> None:
        try:
            self._storage.save_user_states(self._states)
        except StorageError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def _pick_random(self) -> None:
        visible = filter_and_sort_flavors(
            self._catalog,
            self._states,
            FilterOptions(
                search_text=self.search_edit.text(),
                categories=self._selected_categories(),
                statuses=self._selected_statuses(),
                package_size=self.size_combo.currentText(),
                sort_by=self.sort_combo.currentText(),
            ),
        )
        candidates = [
            flavor
            for flavor in visible
            if not self._states.get(flavor.source_key, UserFlavorState()).tried
            and not flavor.archived
        ]
        if not candidates:
            QMessageBox.information(
                self,
                "No untried flavor",
                "There is no untried flavor in the current view.",
            )
            return
        self._select_flavor(random.choice(candidates).source_key)

    def _open_product(self) -> None:
        current = self._current()
        if current is not None and current[0].product_url:
            QDesktopServices.openUrl(QUrl(current[0].product_url))

    def _open_shopping_list(self) -> None:
        dialog = ShoppingListDialog(
            self._catalog,
            self._states,
            self._schedule_save,
            self,
        )
        dialog.exec()
        self._refresh_cards()
        self._update_header_counts()

    def _start_refresh(self) -> None:
        if self._refresh_worker is not None and self._refresh_worker.isRunning():
            return
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Refreshing …")
        self.statusBar().showMessage("Connecting to HOLY …")
        worker = CatalogRefreshWorker(
            self._catalog,
            self._storage.paths.images_dir,
            self,
        )
        worker.progress.connect(self.statusBar().showMessage)
        worker.completed.connect(self._refresh_completed)
        worker.failed.connect(self._refresh_failed)
        worker.finished.connect(self._refresh_finished)
        self._refresh_worker = worker
        worker.start()

    def _refresh_completed(
        self,
        catalog: Catalog,
        downloaded_images: int,
        failed_images: int,
    ) -> None:
        try:
            self._storage.save_catalog(catalog)
        except StorageError as exc:
            self._refresh_failed(str(exc))
            return
        self._catalog = catalog
        self._refresh_view()
        active_count = sum(not flavor.archived for flavor in catalog.flavors)
        message = (
            f"Updated {active_count} flavors. "
            f"Saved {downloaded_images} new images."
        )
        if failed_images:
            message += f" {failed_images} images could not be downloaded."
        self.statusBar().showMessage(message, 12000)

    def _refresh_failed(self, message: str) -> None:
        QMessageBox.warning(
            self,
            "Refresh failed",
            "The previous catalog remains unchanged.\n\n" + message,
        )
        self.statusBar().showMessage("Refresh failed · previous catalog remains active")

    def _refresh_finished(self) -> None:
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Refresh catalog")

    def _export_json(self) -> None:
        filename, _filter = QFileDialog.getSaveFileName(
            self,
            "Save JSON backup",
            str(Path.home() / "holy-flavors-backup.json"),
            "JSON files (*.json)",
        )
        if not filename:
            return
        try:
            self._storage.export_json(Path(filename), self._states)
            self.statusBar().showMessage(f"Backup saved: {filename}", 8000)
        except StorageError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_csv(self) -> None:
        filename, _filter = QFileDialog.getSaveFileName(
            self,
            "Save CSV export",
            str(Path.home() / "holy-flavors-ratings.csv"),
            "CSV files (*.csv)",
        )
        if not filename:
            return
        try:
            self._storage.export_csv(Path(filename), self._catalog, self._states)
            self.statusBar().showMessage(f"CSV saved: {filename}", 8000)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _import_json(self) -> None:
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose JSON backup",
            str(Path.home()),
            "JSON files (*.json)",
        )
        if not filename:
            return
        try:
            imported = self._storage.read_import(Path(filename))
        except StorageError as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        new_count, changed_count, unchanged_count = preview_import(self._states, imported)
        answer = QMessageBox.question(
            self,
            "Import preview",
            f"New entries: {new_count}\n"
            f"Changed entries: {changed_count}\n"
            f"Unchanged entries: {unchanged_count}\n\n"
            "Imported values win in conflicts. A safety backup is created "
            "automatically before merging. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._storage.create_backup()
            self._states.update(imported)
            self._storage.save_user_states(self._states)
        except (OSError, StorageError) as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self._refresh_view()
        if self._current_key:
            flavor = self._catalog.by_key().get(self._current_key)
            if flavor:
                self._populate_detail(flavor)
        self.statusBar().showMessage("JSON backup merged successfully", 8000)

    def _show_load_errors(self) -> None:
        if self._load_errors:
            QMessageBox.warning(
                self,
                "Some local data could not be loaded",
                "\n\n".join(self._load_errors),
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._refresh_worker is not None and self._refresh_worker.isRunning():
            QMessageBox.information(
                self,
                "Refresh in progress",
                "Please wait until the catalog refresh has finished.",
            )
            event.ignore()
            return
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_states()
        super().closeEvent(event)
