"""MuseSplit entry point."""

from __future__ import annotations

import logging
import shutil
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

try:
    from .config import resolve_app_paths
    from .constants import APP_NAME, DEFAULT_MODEL
    from .logger import configure_logging
    from .ui.main_window import MainWindow
    from .ui.theme import app_stylesheet
except ImportError:
    # Fallback for script-like execution contexts (e.g. some bundled entry modes).
    from musesplit.config import resolve_app_paths
    from musesplit.constants import APP_NAME, DEFAULT_MODEL
    from musesplit.logger import configure_logging
    from musesplit.ui.main_window import MainWindow
    from musesplit.ui.theme import app_stylesheet

LOGGER = logging.getLogger(__name__)


def _check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def main() -> int:
    paths = resolve_app_paths()
    configure_logging(log_file=paths.logs_dir / "musesplit.log")
    LOGGER.info("Starting MuseSplit")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(app_stylesheet())

    if not _check_ffmpeg():
        LOGGER.error("ffmpeg not found in PATH")
        QMessageBox.critical(
            None,
            APP_NAME,
            "ffmpeg was not found in PATH. Install ffmpeg and restart the app.",
        )
        return 1

    window = MainWindow(paths=paths, model_name=DEFAULT_MODEL)
    window.show()
    LOGGER.info("Main window shown")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
