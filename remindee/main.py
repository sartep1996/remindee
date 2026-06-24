from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from remindee.utils.database import init_db
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
    app.setQuitOnLastWindowClosed(False)

    # Initialize DB tables
    init_db()

    # Apply default light (white + orange) theme before showing anything
    apply_theme(app, "light")

    scheduler = SchedulerService()

    # Connect quit signal to clean up scheduler
    app.aboutToQuit.connect(scheduler.stop)

    login = LoginDialog()
    result = login.exec()

    if result != LoginDialog.DialogCode.Accepted or login.current_user is None:
        sys.exit(0)

    user = login.current_user

    # Apply user's saved theme preference
    apply_theme(app, user.theme)

    window = MainWindow(user, scheduler)
    window.show()

    # macOS: apply NSVisualEffectView vibrancy (frosted-glass blur).
    # processEvents() ensures the native NSWindow exists before we touch it.
    app.processEvents()
    from remindee.utils.vibrancy import enable_mac_vibrancy
    enable_mac_vibrancy(window, dark=(user.theme == "dark"))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
