from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

from holy_flavors import __version__
from holy_flavors.main_window import MainWindow
from holy_flavors.storage import AppPaths, Storage
from holy_flavors.styles import application_stylesheet


def main() -> int:
    QCoreApplication.setApplicationName("HOLY Flavors")
    QCoreApplication.setApplicationVersion(__version__)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(application_stylesheet())

    project_dir = Path(__file__).resolve().parent
    window = MainWindow(Storage(AppPaths(project_dir)))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
