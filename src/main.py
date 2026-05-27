"""
main.py
-------
Entry point for Prinaka.

Initialises the Qt application, creates the Prinny widget, and starts
the event loop.
"""

import sys
from PyQt5.QtWidgets import QApplication
from prinny import Prinny


def main() -> None:
    """Launch the Prinaka application."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep running even if info window closes

    prinny = Prinny()
    prinny.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()