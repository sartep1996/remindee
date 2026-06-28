from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QWidget,
)

from remindee.models.user import User
from remindee.services.auth_service import LocalAuthService, GoogleAuthService


class _OAuthThread(QThread):
    auth_complete = Signal(object)
    auth_failed = Signal(str)

    def __init__(self, service: GoogleAuthService) -> None:
        super().__init__()
        self._service = service

    def run(self) -> None:
        try:
            credentials = self._service.run_local_server()
            self.auth_complete.emit(credentials)
        except Exception as exc:
            self.auth_failed.emit(str(exc))


class LoginDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.current_user: Optional[User] = None
        self._local_auth = LocalAuthService()
        self._google_auth = GoogleAuthService()
        self._oauth_thread: Optional[_OAuthThread] = None

        # Login screen uses the system UI font, not the app-wide Marker Felt
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
        self.setWindowTitle("REMINDEE — Sign In")
        self.setMinimumWidth(440)
        self.setModal(True)
        self.setObjectName("LoginDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._login_page = self._build_login_page()
        self._register_page = self._build_register_page()
        self._stack.addWidget(self._login_page)
        self._stack.addWidget(self._register_page)

    # ── Login page ─────────────────────────────────────────────────────────

    def _build_login_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("LoginPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(11)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("REMINDEE")
        title.setObjectName("AppTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Simple & elegant reminders")
        sub.setObjectName("AppSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)
        layout.addSpacing(16)

        layout.addWidget(self._lbl("Email"))
        self._login_email = QLineEdit()
        self._login_email.setObjectName("FormInput")
        self._login_email.setPlaceholderText("you@example.com")
        layout.addWidget(self._login_email)

        layout.addWidget(self._lbl("Password"))
        self._login_pw = QLineEdit()
        self._login_pw.setObjectName("FormInput")
        self._login_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._login_pw.setPlaceholderText("••••••••")
        self._login_pw.returnPressed.connect(self._do_login)
        layout.addWidget(self._login_pw)

        self._login_error = QLabel("")
        self._login_error.setObjectName("ErrorLabel")
        self._login_error.hide()
        layout.addWidget(self._login_error)

        login_btn = QPushButton("Sign In")
        login_btn.setObjectName("PrimaryBtn")
        login_btn.clicked.connect(self._do_login)
        layout.addWidget(login_btn)

        if self._google_auth.is_configured():
            google_btn = QPushButton("  Sign in with Google")
            google_btn.setObjectName("SecondaryBtn")
            google_btn.clicked.connect(self._do_google_login)
            layout.addWidget(google_btn)

        layout.addSpacing(8)
        reg_row = QHBoxLayout()
        reg_row.addWidget(QLabel("Don't have an account?"))
        reg_link = QPushButton("Register")
        reg_link.setObjectName("LinkBtn")
        reg_link.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        reg_row.addWidget(reg_link)
        reg_row.addStretch()
        layout.addLayout(reg_row)

        return page

    # ── Register page ─────────────────────────────────────────────────────

    def _build_register_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("RegisterPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Create Account")
        title.setObjectName("AppTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(16)

        layout.addWidget(self._lbl("Username"))
        self._reg_username = QLineEdit()
        self._reg_username.setObjectName("FormInput")
        self._reg_username.setPlaceholderText("Your name")
        layout.addWidget(self._reg_username)

        layout.addWidget(self._lbl("Email"))
        self._reg_email = QLineEdit()
        self._reg_email.setObjectName("FormInput")
        self._reg_email.setPlaceholderText("you@example.com")
        layout.addWidget(self._reg_email)

        layout.addWidget(self._lbl("Password"))
        self._reg_pw = QLineEdit()
        self._reg_pw.setObjectName("FormInput")
        self._reg_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._reg_pw.setPlaceholderText("Min. 6 characters")
        layout.addWidget(self._reg_pw)

        layout.addWidget(self._lbl("Confirm Password"))
        self._reg_pw2 = QLineEdit()
        self._reg_pw2.setObjectName("FormInput")
        self._reg_pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self._reg_pw2.setPlaceholderText("Repeat password")
        self._reg_pw2.returnPressed.connect(self._do_register)
        layout.addWidget(self._reg_pw2)

        self._reg_error = QLabel("")
        self._reg_error.setObjectName("ErrorLabel")
        self._reg_error.hide()
        layout.addWidget(self._reg_error)

        reg_btn = QPushButton("Create Account")
        reg_btn.setObjectName("PrimaryBtn")
        reg_btn.clicked.connect(self._do_register)
        layout.addWidget(reg_btn)

        layout.addSpacing(8)
        back_row = QHBoxLayout()
        back_row.addWidget(QLabel("Already have an account?"))
        back_link = QPushButton("Sign In")
        back_link.setObjectName("LinkBtn")
        back_link.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        back_row.addWidget(back_link)
        back_row.addStretch()
        layout.addLayout(back_row)

        return page

    # ── Auth actions ─────────────────────────────────────────────────────

    def _do_login(self) -> None:
        email = self._login_email.text().strip()
        password = self._login_pw.text()
        if not email or not password:
            self._login_error.setText("Please enter email and password.")
            self._login_error.show()
            return
        user = self._local_auth.login(email, password)
        if user is None:
            self._login_error.setText("Invalid email or password.")
            self._login_error.show()
            return
        self.current_user = user
        self.accept()

    def _do_register(self) -> None:
        username = self._reg_username.text().strip()
        email = self._reg_email.text().strip()
        pw = self._reg_pw.text()
        pw2 = self._reg_pw2.text()

        if not username or not email or not pw:
            self._show_reg_error("All fields are required.")
            return
        if pw != pw2:
            self._show_reg_error("Passwords do not match.")
            return
        if len(pw) < 6:
            self._show_reg_error("Password must be at least 6 characters.")
            return
        if self._local_auth.email_exists(email):
            self._show_reg_error("An account with that email already exists.")
            return
        try:
            user = self._local_auth.register(username, email, pw)
        except Exception as exc:
            self._show_reg_error(f"Registration failed: {exc}")
            return
        self.current_user = user
        self.accept()

    def _do_google_login(self) -> None:
        self._google_auth.create_flow()
        self._oauth_thread = _OAuthThread(self._google_auth)
        self._oauth_thread.auth_complete.connect(self._on_google_auth_complete)
        self._oauth_thread.auth_failed.connect(self._on_google_auth_failed)
        self._oauth_thread.start()
        self._login_error.setText("Browser opened — please sign in with Google…")
        self._login_error.setStyleSheet("color: #5b8cff;")
        self._login_error.show()

    def _on_google_auth_complete(self, credentials) -> None:
        try:
            user = self._google_auth.get_or_create_user(credentials)
        except Exception as exc:
            self._login_error.setText(f"Google login failed: {exc}")
            self._login_error.setStyleSheet("")
            self._login_error.show()
            return
        self._login_error.hide()
        self.current_user = user
        self.accept()

    def _on_google_auth_failed(self, msg: str) -> None:
        self._login_error.setText(f"Google login cancelled or failed: {msg}")
        self._login_error.setStyleSheet("")
        self._login_error.show()

    def _show_reg_error(self, msg: str) -> None:
        self._reg_error.setText(msg)
        self._reg_error.show()

    def _lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FormLabel")
        return lbl
