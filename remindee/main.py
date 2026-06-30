from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from remindee.models.user import User
from remindee.utils.database import init_db, get_session
from remindee.services.scheduler_service import SchedulerService
from remindee.ui.main_window import MainWindow
from remindee.ui.styles import apply_theme

_GUEST_EMAIL = "local@remindee.app"


def _get_or_create_guest() -> User:
    """Return (or create) the single local guest account, no login needed."""
    with get_session() as session:
        user = session.query(User).filter_by(email=_GUEST_EMAIL).first()
        if user is None:
            user = User(email=_GUEST_EMAIL, display_name="Local User", theme="light")
            session.add(user)
            session.flush()
        session.expunge(user)
        return user


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

    user = _get_or_create_guest()
    apply_theme(app, user.theme)

    window = MainWindow(user, scheduler)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
