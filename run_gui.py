
"""Launch the APSA desktop GUI."""

import sys

from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    app.setApplicationName(
        "APSA Load Flow Simulator"
    )

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
