from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
)

from remindee.models.user import User


class SettingsDialog(QDialog):
    theme_changed = Signal(str)

    def __init__(self, user: User, parent=None) -> None:
        super().__init__(parent)
        self._user = user
        self.setWindowTitle("Settings")
        self.setMinimumWidth(340)
        self.setModal(True)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Settings")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        layout.addWidget(self._lbl("Theme"))
        self._theme_combo = QComboBox()
        self._theme_combo.setObjectName("FreqCombo")
        self._theme_combo.addItems(["System Default", "Dark", "Light"])
        current = self._user.theme
        mapping = {"system": 0, "dark": 1, "light": 2}
        self._theme_combo.setCurrentIndex(mapping.get(current, 0))
        layout.addWidget(self._theme_combo)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _lbl(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setObjectName("FormLabel")
        return l

    def _save(self) -> None:
        idx = self._theme_combo.currentIndex()
        themes = ["system", "dark", "light"]
        self.theme_changed.emit(themes[idx])
        self.accept()
