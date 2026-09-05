from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QStandardItemModel
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from holy_flavors.models import Catalog, Flavor, UserFlavorState
from holy_flavors.services import build_cart_url, display_variant_title, validate_cart


class ShoppingListDialog(QDialog):
    def __init__(
        self,
        catalog: Catalog,
        states: dict[str, UserFlavorState],
        changed_callback: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._catalog = catalog
        self._states = states
        self._changed_callback = changed_callback
        self.setWindowTitle("Shopping list")
        self.resize(970, 560)
        self._build_ui()
        self._rebuild()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Your shopping list")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Choose an available package size for every flavor. "
            "You will complete the order on the HOLY website."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Flavor", "Category", "Package size", "Quantity", ""]
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.issue_label = QLabel()
        self.issue_label.setWordWrap(True)
        layout.addWidget(self.issue_label)

        buttons = QHBoxLayout()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        self.cart_button = QPushButton("Open cart in browser")
        self.cart_button.setObjectName("primaryButton")
        self.cart_button.clicked.connect(self._open_cart)
        buttons.addWidget(close_button)
        buttons.addStretch()
        buttons.addWidget(self.cart_button)
        layout.addLayout(buttons)

    def _rebuild(self) -> None:
        wishlist = [
            flavor
            for flavor in self._catalog.flavors
            if self._states.get(flavor.source_key, UserFlavorState()).wishlist
        ]
        self.table.setRowCount(len(wishlist))
        for row, flavor in enumerate(wishlist):
            state = self._states[flavor.source_key]
            self.table.setItem(row, 0, QTableWidgetItem(flavor.name))
            self.table.setItem(row, 1, QTableWidgetItem(flavor.category))
            combo = self._variant_combo(flavor, state)
            combo.currentIndexChanged.connect(
                lambda _index, key=flavor.source_key, widget=combo: self._variant_changed(key, widget)
            )
            self.table.setCellWidget(row, 2, combo)

            quantity = QSpinBox()
            quantity.setRange(1, 99)
            quantity.setValue(state.quantity)
            quantity.valueChanged.connect(
                lambda value, key=flavor.source_key: self._quantity_changed(key, value)
            )
            self.table.setCellWidget(row, 3, quantity)

            remove = QPushButton("Remove")
            remove.clicked.connect(
                lambda _checked=False, key=flavor.source_key: self._remove(key)
            )
            self.table.setCellWidget(row, 4, remove)
        self._update_issues()

    def _variant_combo(
        self,
        flavor: Flavor,
        state: UserFlavorState,
    ) -> QComboBox:
        combo = QComboBox()
        combo.addItem("Choose a package size", None)
        for variant in flavor.variants:
            price = f"€{variant.price_cents / 100:.2f}"
            suffix = "" if variant.available else " · sold out"
            combo.addItem(
                f"{display_variant_title(variant.title)} · {price}{suffix}",
                variant.id,
            )
            model = combo.model()
            if isinstance(model, QStandardItemModel) and not variant.available:
                item = model.item(combo.count() - 1)
                if item:
                    item.setEnabled(False)
            if variant.id == state.selected_variant_id:
                combo.setCurrentIndex(combo.count() - 1)
        return combo

    def _variant_changed(self, key: str, combo: QComboBox) -> None:
        value = combo.currentData()
        self._states[key].selected_variant_id = int(value) if value is not None else None
        self._changed_callback()
        self._update_issues()

    def _quantity_changed(self, key: str, value: int) -> None:
        self._states[key].quantity = value
        self._changed_callback()

    def _remove(self, key: str) -> None:
        self._states[key].wishlist = False
        self._changed_callback()
        self._rebuild()

    def _update_issues(self) -> None:
        wishlist_count = sum(state.wishlist for state in self._states.values())
        issues = validate_cart(self._catalog, self._states)
        self.cart_button.setEnabled(wishlist_count > 0 and not issues)
        if not wishlist_count:
            self.issue_label.setText("Your shopping list is empty.")
            self.issue_label.setStyleSheet("color: #5D5D59;")
        elif issues:
            lines = [f"• {issue.flavor_name}: {issue.message}" for issue in issues]
            self.issue_label.setText("Please fix these items first:\n" + "\n".join(lines))
            self.issue_label.setStyleSheet("color: #A3261B; font-weight: 650;")
        else:
            self.issue_label.setText(
                f"{wishlist_count} flavors are ready for the cart."
            )
            self.issue_label.setStyleSheet("color: #257331; font-weight: 650;")

    def _open_cart(self) -> None:
        url = build_cart_url(self._catalog, self._states)
        lines = []
        for flavor in self._catalog.flavors:
            state = self._states.get(flavor.source_key, UserFlavorState())
            if not state.wishlist:
                continue
            variant = next(
                item for item in flavor.variants if item.id == state.selected_variant_id
            )
            lines.append(
                f"• {flavor.name} – {display_variant_title(variant.title)} "
                f"× {state.quantity}"
            )
        message = (
            "The following items will be opened in a new HOLY cart:\n\n"
            + "\n".join(lines)
            + "\n\nThis may replace an existing HOLY cart in your browser. "
            "Checkout and payment happen exclusively on the HOLY website."
        )
        answer = QMessageBox.question(
            self,
            "Open cart",
            message,
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Open:
            QDesktopServices.openUrl(QUrl(url))
