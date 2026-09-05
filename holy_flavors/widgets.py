from __future__ import annotations

import math
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from holy_flavors.catalog import image_cache_path, variant_image_cache_path
from holy_flavors.models import Flavor, ProductVariant, UserFlavorState
from holy_flavors.styles import CATEGORY_COLORS, HOLY_YELLOW, INK


CARD_WIDTH = 218
GRID_MARGIN = 18
GRID_HORIZONTAL_SPACING = 14


class RatingWidget(QWidget):
    value_changed = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value: float | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Rating from 0.5 to 5 stars")
        self.setToolTip("Click or use arrow keys · Delete clears the rating")
        self.setMinimumSize(190, 40)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    @property
    def value(self) -> float | None:
        return self._value

    def set_value(self, value: float | None, emit: bool = False) -> None:
        normalized = None if value is None else min(5.0, max(0.5, round(value * 2) / 2))
        if normalized == self._value:
            return
        self._value = normalized
        self.update()
        if emit:
            self.value_changed.emit(self._value)

    def sizeHint(self) -> QSize:
        return QSize(190, 40)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        star_size = 30.0
        gap = 7.0
        top = (self.height() - star_size) / 2
        paths: list[QPainterPath] = []
        for index in range(5):
            left = index * (star_size + gap)
            path = _star_path(QRectF(left, top, star_size, star_size))
            paths.append(path)
            painter.fillPath(path, QColor("#D4D2C9"))
            painter.setPen(QPen(QColor(INK), 1.0))
            painter.drawPath(path)

        if self._value is not None:
            fill_width = (self._value / 5.0) * (5 * star_size + 4 * gap)
            painter.save()
            painter.setClipRect(QRectF(0, 0, fill_width, self.height()))
            for path in paths:
                painter.fillPath(path, QColor(HOLY_YELLOW))
                painter.setPen(QPen(QColor(INK), 1.0))
                painter.drawPath(path)
            painter.restore()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        total_width = 5 * 30.0 + 4 * 7.0
        position = max(0.0, min(total_width, event.position().x()))
        halves = max(1, min(10, math.ceil((position / total_width) * 10)))
        self.set_value(halves / 2, emit=True)
        self.setFocus()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.set_value(None, emit=True)
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            self.set_value(max(0.5, (self._value or 1.0) - 0.5), emit=True)
            return
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            self.set_value(min(5.0, (self._value or 0.0) + 0.5), emit=True)
            return
        if event.key() == Qt.Key.Key_Home:
            self.set_value(0.5, emit=True)
            return
        if event.key() == Qt.Key.Key_End:
            self.set_value(5.0, emit=True)
            return
        super().keyPressEvent(event)


class FlavorCard(QFrame):
    selected = pyqtSignal(str)
    wishlist_toggled = pyqtSignal(str, bool)

    def __init__(
        self,
        flavor: Flavor,
        state: UserFlavorState,
        images_dir: Path,
        display_variant: ProductVariant | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.flavor = flavor
        self._images_dir = images_dir
        self._display_variant = display_variant
        self.setObjectName("flavorCard")
        self.setProperty("selected", False)
        self.setProperty("marked", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(218, 290)
        self.setToolTip(f"Open {flavor.name}")
        self._build_ui()
        self.update_state(state)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(7)

        self.image_label = QLabel()
        self.image_label.setObjectName("cardImage")
        self.image_label.setFixedHeight(164)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_image()
        layout.addWidget(self.image_label)

        meta = QHBoxLayout()
        meta.setContentsMargins(11, 0, 11, 0)
        self.category_label = QLabel(self.flavor.category)
        self.category_label.setObjectName("pill")
        color = CATEGORY_COLORS[self.flavor.category]
        self.category_label.setStyleSheet(f"background: {color}; color: #050505;")
        self.availability_label = QLabel()
        self.availability_label.setObjectName("pill")
        meta.addWidget(self.category_label)
        meta.addStretch()
        meta.addWidget(self.availability_label)
        layout.addLayout(meta)

        self.name_label = QLabel(self.flavor.name)
        self.name_label.setObjectName("cardName")
        self.name_label.setWordWrap(True)
        self.name_label.setMaximumHeight(48)
        self.name_label.setContentsMargins(11, 0, 11, 0)
        layout.addWidget(self.name_label)

        state_row = QHBoxLayout()
        state_row.setContentsMargins(11, 0, 11, 0)
        self.rating_label = QLabel()
        self.markers_label = QLabel()
        self.markers_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        state_row.addWidget(self.rating_label)
        state_row.addStretch()
        state_row.addWidget(self.markers_label)
        layout.addLayout(state_row)

        accent = QFrame()
        accent.setFixedHeight(5)
        accent.setStyleSheet(f"background: {color}; border: 0;")
        layout.addWidget(accent)

        self.wishlist_button = QToolButton(self)
        self.wishlist_button.setObjectName("wishlistCardButton")
        self.wishlist_button.setCheckable(True)
        self.wishlist_button.setFixedSize(104, 32)
        self.wishlist_button.move(10, 10)
        self.wishlist_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wishlist_button.toggled.connect(self._wishlist_button_toggled)
        self.wishlist_button.raise_()

    def _set_image(self) -> None:
        paths: list[Path] = []
        if self._display_variant is not None:
            paths.append(
                variant_image_cache_path(self._images_dir, self._display_variant)
            )
        paths.append(image_cache_path(self._images_dir, self.flavor))
        for path in paths:
            if not path.exists():
                continue
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.image_label.setPixmap(
                    pixmap.scaled(
                        202,
                        154,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        color = CATEGORY_COLORS[self.flavor.category]
        self.image_label.setStyleSheet(f"background: {color};")
        self.image_label.setText(self.flavor.name[:1].upper())
        font = QFont("Bahnschrift Condensed", 44, 900)
        self.image_label.setFont(font)

    def update_state(self, state: UserFlavorState) -> None:
        if self.flavor.archived:
            self.availability_label.setText("Archived")
            self.availability_label.setStyleSheet("background: #D0CFC8;")
        elif self.flavor.available:
            self.availability_label.setText("Available")
            self.availability_label.setStyleSheet("background: #DDF4DD;")
        else:
            self.availability_label.setText("Sold out")
            self.availability_label.setStyleSheet("background: #FFD4D0;")
        self.rating_label.setText(
            "Not rated" if state.rating is None else f"{state.rating:.1f} ★"
        )
        self._set_marked(state.wishlist)
        self.wishlist_button.setEnabled(not self.flavor.archived)
        markers = []
        if state.tried:
            markers.append("✓")
        if state.wishlist:
            markers.append("♥ List")
        self.markers_label.setText("  ".join(markers))

    def _wishlist_button_toggled(self, checked: bool) -> None:
        self._set_marked(checked)
        self.wishlist_toggled.emit(self.flavor.source_key, checked)

    def _set_marked(self, marked: bool) -> None:
        self.setProperty("marked", marked)
        previous_block_state = self.wishlist_button.blockSignals(True)
        self.wishlist_button.setChecked(marked)
        self.wishlist_button.setText("✓ Saved" if marked else "+ Save")
        self.wishlist_button.setToolTip(
            "Remove from shopping list" if marked else "Add to shopping list"
        )
        self.wishlist_button.blockSignals(previous_block_state)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.flavor.source_key)
            event.accept()
            return
        super().mousePressEvent(event)


class FlavorGrid(QWidget):
    flavor_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(18, 18, 18, 18)
        self._layout.setHorizontalSpacing(14)
        self._layout.setVerticalSpacing(14)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._cards: list[FlavorCard] = []
        self._column_count = 0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._empty_label = QLabel(
            "No flavors are available yet.\nRefresh the catalog to get started."
        )
        self._empty_label.setObjectName("muted")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setMinimumHeight(260)

    def set_cards(
        self,
        cards: list[FlavorCard],
        empty_text: str = "No flavors match the active filters.",
    ) -> None:
        for card in self._cards:
            self._layout.removeWidget(card)
            card.hide()
            card.deleteLater()
        self._layout.removeWidget(self._empty_label)
        self._empty_label.hide()
        self._empty_label.setText(empty_text)
        self._cards = cards
        self._column_count = 0
        for card in self._cards:
            card.selected.connect(self.flavor_selected.emit)
        self._arrange()

    def select_card(self, source_key: str | None) -> None:
        for card in self._cards:
            card.set_selected(card.flavor.source_key == source_key)

    def _arrange(self) -> None:
        if not self._cards:
            self._column_count = 0
            self._empty_label.show()
            self._layout.addWidget(self._empty_label, 0, 0)
            return

        available_width = max(1, self.width() - 2 * GRID_MARGIN)
        columns = max(
            1,
            (available_width + GRID_HORIZONTAL_SPACING)
            // (CARD_WIDTH + GRID_HORIZONTAL_SPACING),
        )
        if columns == self._column_count:
            return

        for card in self._cards:
            self._layout.removeWidget(card)
        for index, card in enumerate(self._cards):
            self._layout.addWidget(card, index // columns, index % columns)
        self._column_count = columns
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        return QSize(CARD_WIDTH + 2 * GRID_MARGIN, 0)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._arrange()


def _star_path(rect: QRectF) -> QPainterPath:
    center = rect.center()
    outer_radius = rect.width() / 2
    inner_radius = outer_radius * 0.45
    path = QPainterPath()
    for point_index in range(10):
        radius = outer_radius if point_index % 2 == 0 else inner_radius
        angle = math.radians(-90 + point_index * 36)
        point = QPointF(
            center.x() + math.cos(angle) * radius,
            center.y() + math.sin(angle) * radius,
        )
        if point_index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path
