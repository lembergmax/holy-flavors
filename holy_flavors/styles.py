from __future__ import annotations


HOLY_YELLOW = "#FFD400"
INK = "#050505"
PAPER = "#F7F6F1"
SKY = "#70D7FF"
RASPBERRY = "#FF65A8"
LEAF = "#75C96B"

CATEGORY_COLORS = {
    "Energy": "#FF5B45",
    "Hydration": SKY,
    "Iced Tea": LEAF,
    "Milkshake": RASPBERRY,
    "Syrup": "#FF9E3D",
}


def application_stylesheet() -> str:
    return f"""
    * {{
        font-family: "Segoe UI";
        font-size: 10pt;
        color: {INK};
    }}
    QMainWindow, QDialog, QWidget#appRoot {{
        background: {PAPER};
    }}
    QWidget#header {{
        background: {HOLY_YELLOW};
        border-bottom: 3px solid {INK};
    }}
    QLabel#brand {{
        font-family: "Bahnschrift Condensed", "Arial Narrow";
        font-size: 27pt;
        font-weight: 900;
        font-style: italic;
    }}
    QLabel#brandSmall {{
        font-family: "Bahnschrift Condensed", "Arial Narrow";
        font-size: 12pt;
        font-weight: 800;
    }}
    QLabel#sectionTitle, QLabel#detailTitle {{
        font-family: "Bahnschrift Condensed", "Arial Narrow";
        font-size: 20pt;
        font-weight: 800;
    }}
    QLabel#detailTitle {{
        font-size: 25pt;
    }}
    QLabel#muted, QLabel#description {{
        color: #5D5D59;
    }}
    QLabel#description {{
        font-size: 10pt;
        line-height: 1.35;
    }}
    QLabel#statValue {{
        font-family: "Bahnschrift Condensed", "Arial Narrow";
        font-size: 20pt;
        font-weight: 800;
    }}
    QWidget#progressBand {{
        background: {INK};
    }}
    QWidget#progressBand QLabel {{
        color: white;
    }}
    QWidget#filterPanel, QWidget#detailPanel {{
        background: white;
        border: 1px solid #D8D7D1;
    }}
    QWidget#detailPanel {{
        border-left: 3px solid {INK};
    }}
    QLineEdit, QComboBox, QTextEdit, QSpinBox {{
        background: white;
        border: 1px solid #A7A69F;
        border-radius: 7px;
        padding: 7px 9px;
        selection-background-color: {HOLY_YELLOW};
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus {{
        border: 2px solid {INK};
    }}
    QComboBox QAbstractItemView {{
        background: white;
        color: {INK};
        border: 2px solid {INK};
        border-radius: 6px;
        padding: 4px;
        outline: 0;
        selection-background-color: {HOLY_YELLOW};
        selection-color: {INK};
    }}
    QComboBox QAbstractItemView::item {{
        background: white;
        color: {INK};
        min-height: 26px;
        padding: 4px 8px;
    }}
    QComboBox QAbstractItemView::item:hover,
    QComboBox QAbstractItemView::item:selected {{
        background: {HOLY_YELLOW};
        color: {INK};
    }}
    QComboBox QAbstractItemView::item:disabled {{
        background: #ECEBE6;
        color: #777670;
    }}
    QMenu {{
        background: white;
        color: {INK};
        border: 2px solid {INK};
        padding: 5px;
    }}
    QMenu::item {{
        background: white;
        color: {INK};
        padding: 7px 22px 7px 10px;
    }}
    QMenu::item:selected {{
        background: {HOLY_YELLOW};
        color: {INK};
    }}
    QMenu::separator {{
        background: #C9C8C1;
        height: 1px;
        margin: 4px 7px;
    }}
    QPushButton, QToolButton {{
        background: white;
        border: 2px solid {INK};
        border-radius: 9px;
        padding: 7px 12px;
        font-weight: 650;
    }}
    QPushButton:hover, QToolButton:hover {{
        background: #FFF4A3;
    }}
    QPushButton:pressed, QToolButton:pressed {{
        background: {INK};
        color: white;
    }}
    QPushButton:disabled, QToolButton:disabled {{
        background: #E6E5E0;
        color: #8A8984;
        border-color: #BEBDB7;
    }}
    QPushButton#primaryButton {{
        background: {INK};
        color: white;
        padding: 9px 15px;
    }}
    QPushButton#primaryButton:hover {{
        background: #2A2A2A;
    }}
    QPushButton#yellowButton {{
        background: {HOLY_YELLOW};
    }}
    QToolButton#closeDetailButton {{
        border: 0;
        border-radius: 16px;
        padding: 0;
        min-width: 32px;
        max-width: 32px;
        min-height: 32px;
        max-height: 32px;
        font-size: 20pt;
        font-weight: 700;
    }}
    QToolButton#closeDetailButton:hover {{
        background: {HOLY_YELLOW};
    }}
    QToolButton#wishlistCardButton {{
        background: white;
        color: {INK};
        border: 2px solid {INK};
        border-radius: 9px;
        padding: 4px 7px;
        font-size: 9pt;
        font-weight: 800;
    }}
    QToolButton#wishlistCardButton:hover {{
        background: #FFF4A3;
    }}
    QToolButton#wishlistCardButton:checked {{
        background: {HOLY_YELLOW};
        color: {INK};
    }}
    QPushButton#categoryButton {{
        text-align: left;
        border: 0;
        border-radius: 0;
        border-left: 4px solid transparent;
        background: transparent;
        padding: 8px 10px;
    }}
    QPushButton#categoryButton:checked {{
        border-left-color: {HOLY_YELLOW};
        background: {INK};
        color: white;
    }}
    QFrame#flavorCard {{
        background: white;
        border: 1px solid #D4D3CC;
        border-radius: 10px;
    }}
    QFrame#flavorCard:hover {{
        border-color: {INK};
    }}
    QFrame#flavorCard[marked="true"] {{
        background: #FFF8C7;
        border: 3px solid {INK};
    }}
    QFrame#flavorCard[selected="true"] {{
        border: 5px solid {HOLY_YELLOW};
    }}
    QFrame#flavorCard[marked="true"][selected="true"] {{
        border: 5px solid {HOLY_YELLOW};
    }}
    QLabel#cardImage {{
        background: #EFEDE6;
        border-top-left-radius: 9px;
        border-top-right-radius: 9px;
    }}
    QLabel#cardName {{
        font-family: "Bahnschrift Condensed", "Arial Narrow";
        font-size: 16pt;
        font-weight: 800;
    }}
    QLabel#pill {{
        border-radius: 8px;
        padding: 2px 7px;
        font-size: 8pt;
        font-weight: 700;
    }}
    QCheckBox {{
        spacing: 8px;
        font-weight: 600;
    }}
    QCheckBox::indicator {{
        width: 19px;
        height: 19px;
        border: 2px solid {INK};
        border-radius: 4px;
        background: white;
    }}
    QCheckBox::indicator:checked {{
        background: {HOLY_YELLOW};
    }}
    QScrollArea {{
        border: 0;
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 11px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: #9A9993;
        min-height: 28px;
        border-radius: 5px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QTableWidget {{
        background: white;
        alternate-background-color: #F2F1EB;
        border: 1px solid #D0CFC8;
        gridline-color: #E1E0DA;
    }}
    QHeaderView::section {{
        background: {INK};
        color: white;
        border: 0;
        padding: 8px;
        font-weight: 700;
    }}
    QStatusBar {{
        background: {INK};
        color: white;
    }}
    QStatusBar QLabel {{
        color: white;
    }}
    """
