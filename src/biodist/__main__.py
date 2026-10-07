"""Entry point: launch the BioDist GUI."""

from __future__ import annotations

import sys


def _apply_dark(app):
    """Deterministic dark-grey Fusion theme so every widget (incl. the non-native
    color picker) matches, regardless of the host OS theme."""
    from PySide6.QtGui import QColor, QPalette

    app.setStyle("Fusion")
    win = QColor("#2b2b2b")
    base = QColor("#232323")
    text = QColor("#e0e0e0")
    hi = QColor("#3d6ea5")
    p = QPalette()
    p.setColor(QPalette.Window, win)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Base, base)
    p.setColor(QPalette.AlternateBase, win)
    p.setColor(QPalette.ToolTipBase, win)
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.Button, win)
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.Highlight, hi)
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor("#7a7a7a"))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#7a7a7a"))
    app.setPalette(p)


def _set_app_user_model_id(app_id):
    """Windows: an explicit AppUserModelID makes the taskbar group the app under its own
    icon (pythonw.exe otherwise shows the generic Python icon). No-op elsewhere."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:  # noqa: BLE001 — non-Windows or blocked; harmless
        pass


def _splash():
    """The icon and a word, on screen before the rest of BioDist is imported and built."""
    from pathlib import Path

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from PySide6.QtWidgets import QSplashScreen

    pm = QPixmap(320, 150)
    pm.fill(QColor("#2b2b2b"))
    p = QPainter(pm)
    icon = QPixmap(str(Path(__file__).with_name("assets") / "biodist.png"))
    if not icon.isNull():
        p.drawPixmap(20, 35, icon.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    p.setPen(QColor("#e0e0e0"))
    f = p.font()
    f.setPointSize(16)
    p.setFont(f)
    p.drawText(120, 70, "BioDist")
    f.setPointSize(9)
    p.setFont(f)
    p.setPen(QColor("#8d8d8d"))
    p.drawText(120, 95, "starting…")
    p.end()
    s = QSplashScreen(pm)
    s.show()
    return s


def main() -> int:
    from PySide6.QtWidgets import QApplication

    _set_app_user_model_id("BioDist")  # before the first window: the taskbar's icon
    app = QApplication(sys.argv)
    splash = _splash()
    app.processEvents()

    from . import app as _app
    from .app import APP_NAME, MainWindow, _app_icon   # the slow part: on screen meanwhile

    app.setApplicationName(APP_NAME)   # NB: no setApplicationDisplayName — Qt would append " - BioDist"
    icon = _app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    _apply_dark(app)
    if not _app.options_found():
        from PySide6.QtWidgets import QMessageBox
        splash.hide()
        if QMessageBox.question(
                None, APP_NAME, f"No options file in {_app.APP_DIR}.\n\nCreate one with the "
                "standard options? (No: the standard options for now — the file is written as "
                "soon as an option is changed.)") == QMessageBox.Yes:
            _app._save_prefs()
        splash.show()
    win = MainWindow()
    win.showMaximized()                # a 1366x768 laptop has no room to spare
    splash.finish(win)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
