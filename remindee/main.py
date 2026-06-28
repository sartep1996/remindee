from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from remindee.utils.database import init_db, get_session
from remindee.models.user import User as _User
from remindee.services.scheduler_service import SchedulerService
from remindee.ui.login_dialog import LoginDialog
from remindee.ui.main_window import MainWindow
from remindee.ui.styles import apply_theme


def main() -> None:
    # Enable HiDPI on all platforms
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("REMINDEE")
    app.setApplicationDisplayName("REMINDEE")
    app.setFont(QFont("Marker Felt", 13))
    app.setQuitOnLastWindowClosed(False)

    # Initialize DB tables
    init_db()

    # Apply default light (white + orange) theme before showing anything
    apply_theme(app, "light")

    scheduler = SchedulerService()
    from remindee.services.keyboard_service import KeyboardService
    keyboard_service = KeyboardService()

    # Connect quit signal to clean up scheduler and keyboard listener
    app.aboutToQuit.connect(scheduler.stop)
    app.aboutToQuit.connect(keyboard_service.stop)

    # ── Temporary: skip login if a user already exists in the DB ──────────────
    user = None
    with get_session() as session:
        db_user = session.query(_User).first()
        if db_user is not None:
            session.expunge(db_user)
            user = db_user

    if user is None:
        login = LoginDialog()
        result = login.exec()
        if result != LoginDialog.DialogCode.Accepted or login.current_user is None:
            sys.exit(0)
        user = login.current_user
    # ── End temporary bypass ───────────────────────────────────────────────────

    # Apply user's saved preferences
    apply_theme(app, user.theme)
    app.setFont(QFont(getattr(user, "app_font", None) or "Marker Felt", 13))

    window = MainWindow(user, scheduler)
    keyboard_service.quick_note_triggered.connect(window.show_quick_note)
    keyboard_service.note_triggered.connect(window.show_quick_note_as_note)
    window.show()

    # macOS: apply NSVisualEffectView vibrancy (frosted-glass blur).
    # processEvents() ensures the native NSWindow exists before we touch it.
    app.processEvents()
    from remindee.utils.vibrancy import enable_mac_vibrancy
    enable_mac_vibrancy(window, dark=(user.theme == "dark"))

    keyboard_service.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
