from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.settings import APP_STYLE, ensure_app_directories


def main() -> int:
    ensure_app_directories()
    app = QApplication(sys.argv)
    app.setApplicationName("Data Comparison Video Maker")
    app.setStyleSheet(APP_STYLE)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
