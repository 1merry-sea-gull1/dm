from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from motor_tuner.ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("DM Motor Tuner")
    app.setOrganizationName("DM Wheel-Legged")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    if "--smoke-test" in sys.argv:
        QTimer.singleShot(800, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
