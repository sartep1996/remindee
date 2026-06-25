from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QWidget,
    QSizePolicy,
)

from remindee.models.user import User
from remindee.ui.reminder_dialog import _FONT_GROUPS


class SettingsDialog(QDialog):
    theme_changed = Signal(str)
    font_changed  = Signal(str)

    def __init__(self, user: User, parent=None) -> None:
        super().__init__(parent)
        self._user = user
        self.setWindowTitle("Settings")
        self.setMinimumWidth(360)
        self.setModal(True)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # ── Title row with expand toggle ──────────────────────────────────────
        title_row = QHBoxLayout()
        title = QLabel("Settings")
        title.setObjectName("DialogTitle")
        title_row.addWidget(title, stretch=1)

        self._expand_btn = QPushButton("•••")
        self._expand_btn.setObjectName("ExpandBtn")
        self._expand_btn.setFixedSize(34, 34)
        self._expand_btn.setToolTip("More options")
        self._expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand_btn.setCheckable(True)
        self._expand_btn.clicked.connect(self._toggle_advanced)
        title_row.addWidget(self._expand_btn)
        layout.addLayout(title_row)

        # ── Theme (always visible) ────────────────────────────────────────────
        layout.addWidget(self._lbl("Theme"))
        self._theme_combo = QComboBox()
        self._theme_combo.setObjectName("FreqCombo")
        self._theme_combo.addItems(["System Default", "Dark", "Light"])
        mapping = {"system": 0, "dark": 1, "light": 2}
        self._theme_combo.setCurrentIndex(mapping.get(self._user.theme, 0))
        layout.addWidget(self._theme_combo)

        # ── Expandable advanced section ───────────────────────────────────────
        self._adv_widget = QWidget()
        self._adv_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        adv_layout = QVBoxLayout(self._adv_widget)
        adv_layout.setContentsMargins(0, 6, 0, 0)
        adv_layout.setSpacing(10)

        adv_layout.addWidget(self._lbl("App Font"))
        self._font_combo = QComboBox()
        self._font_combo.setObjectName("FontPicker")

        font_model = QStandardItemModel()
        for group_name, fonts in _FONT_GROUPS:
            header = QStandardItem(f"  {group_name}")
            header.setEnabled(False)
            header.setFont(QFont("Helvetica Neue", 10))
            font_model.appendRow(header)
            for f in fonts:
                item = QStandardItem(f"  {f}")
                item.setFont(QFont(f, 13))
                item.setData(f, Qt.ItemDataRole.UserRole)
                font_model.appendRow(item)
        self._font_combo.setModel(font_model)

        current_font = getattr(self._user, "app_font", None) or "Marker Felt"
        model = self._font_combo.model()
        for i in range(model.rowCount()):
            item = model.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == current_font:
                self._font_combo.setCurrentIndex(i)
                break
        else:
            self._font_combo.setCurrentIndex(1)

        self._font_combo.currentIndexChanged.connect(self._on_font_combo_changed)
        self._on_font_combo_changed(self._font_combo.currentIndex())
        adv_layout.addWidget(self._font_combo)

        self._adv_widget.setMaximumHeight(0)
        layout.addWidget(self._adv_widget)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FormLabel")
        return lbl

    def _on_font_combo_changed(self, index: int) -> None:
        font_name = self._font_combo.currentData(Qt.ItemDataRole.UserRole)
        if font_name:
            self._font_combo.setFont(QFont(font_name, 13))

    def _toggle_advanced(self, checked: bool) -> None:
        target = 115 if checked else 0
        anim = QPropertyAnimation(self._adv_widget, b"maximumHeight")
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim.setStartValue(self._adv_widget.maximumHeight())
        anim.setEndValue(target)
        if checked:
            anim.finished.connect(self.adjustSize)
        anim.start()
        self._anim = anim

    def _save(self) -> None:
        themes = ["system", "dark", "light"]
        self.theme_changed.emit(themes[self._theme_combo.currentIndex()])

        font_name = (
            self._font_combo.currentData(Qt.ItemDataRole.UserRole) or "Marker Felt"
        )
        self.font_changed.emit(font_name)

        self.accept()
