from __future__ import annotations

from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, QSize, Slot
from PySide6.QtGui import QIcon, QAction, QPixmap
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QMenu,
    QApplication,
    QFrame,
    QCalendarWidget,
    QMessageBox,
    QSizePolicy,
)

from remindee.models.reminder import Reminder, FrequencyType
from remindee.models.user import User
from remindee.services.notification_service import NotificationService
from remindee.services.scheduler_service import SchedulerService
from remindee.ui.reminder_card import ReminderCard
from remindee.ui.reminder_dialog import ReminderDialog
from remindee.utils.database import get_session

_ICONS_DIR = Path(__file__).parent.parent / "resources" / "icons"

_SIDEBAR_TABS = [
    ("📅", "Today"),
    ("📆", "Upcoming"),
    ("📋", "All"),
    ("🗓", "Calendar"),
]


class MainWindow(QMainWindow):
    def __init__(self, user: User, scheduler: SchedulerService) -> None:
        super().__init__()
        self._user = user
        self._scheduler = scheduler
        self._active_tab = 0

        self.setWindowTitle("REMINDEE")
        self.setMinimumSize(900, 620)

        self._setup_tray()
        self._notification_service = NotificationService(self._tray, scheduler)
        self._build_ui()
        self._connect_scheduler()

        scheduler.start(user.id)
        self._refresh_current_view()

    # ── Tray ────────────────────────────────────────────────────────────────

    def _setup_tray(self) -> None:
        icon_path = _ICONS_DIR / "tray.png"
        icon = QIcon(str(icon_path)) if icon_path.exists() else QApplication.style().standardIcon(
            QApplication.style().StandardPixmap.SP_ComputerIcon
        )

        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("REMINDEE")

        tray_menu = QMenu()
        show_action = QAction("Open REMINDEE", self)
        show_action.triggered.connect(self._show_window)
        tray_menu.addAction(show_action)

        new_action = QAction("New Reminder", self)
        new_action.triggered.connect(self._open_add_dialog)
        tray_menu.addAction(new_action)

        tray_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        tray_menu.addAction(quit_action)

        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())

        self._content_stack = QStackedWidget()
        self._content_stack.setObjectName("ContentArea")
        self._views = [
            self._build_list_view("Today"),
            self._build_list_view("Upcoming"),
            self._build_list_view("All"),
            self._build_calendar_view(),
        ]
        for view in self._views:
            self._content_stack.addWidget(view)
        root_layout.addWidget(self._content_stack, stretch=1)

        # FAB — floating button parented to the central widget
        self._fab = QPushButton("+", central)
        self._fab.setObjectName("FAB")
        self._fab.setFixedSize(56, 56)
        self._fab.raise_()
        self._fab.clicked.connect(self._open_add_dialog)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(4)

        # App branding
        app_lbl = QLabel("REMINDEE")
        app_lbl.setObjectName("AppTitle")
        app_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(app_lbl)

        # User info
        display = self._user.display_name or self._user.email.split("@")[0]
        name_lbl = QLabel(display)
        name_lbl.setObjectName("UserName")
        layout.addWidget(name_lbl)

        email_lbl = QLabel(self._user.email)
        email_lbl.setObjectName("UserEmail")
        layout.addWidget(email_lbl)

        layout.addSpacing(16)

        self._tab_buttons: list[QPushButton] = []
        for i, (icon_char, label) in enumerate(_SIDEBAR_TABS):
            btn = QPushButton(f"  {icon_char}  {label}")
            btn.setObjectName("SidebarBtn")
            btn.setCheckable(False)
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            layout.addWidget(btn)
            self._tab_buttons.append(btn)

        layout.addStretch()

        # Settings button
        settings_btn = QPushButton("  ⚙  Settings")
        settings_btn.setObjectName("SidebarBtn")
        settings_btn.clicked.connect(self._show_settings)
        layout.addWidget(settings_btn)

        self._update_tab_buttons(0)
        return sidebar

    def _build_list_view(self, label: str) -> QWidget:
        container = QWidget()
        container.setObjectName("ContentArea")
        outer_layout = QVBoxLayout(container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        title = QLabel(label)
        title.setObjectName("ViewTitle")
        outer_layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_content.setObjectName("ContentArea")
        self._cards_layout = None  # will be set per view in refresh

        # store the layout on the scroll_content
        cards_layout = QVBoxLayout(scroll_content)
        cards_layout.setContentsMargins(24, 12, 24, 80)
        cards_layout.setSpacing(10)
        cards_layout.addStretch()

        scroll.setWidget(scroll_content)
        outer_layout.addWidget(scroll)

        # Tag for refresh: store references
        container._title_label = title
        container._cards_layout = cards_layout
        container._scroll_content = scroll_content
        container._view_label = label

        return container

    def _build_calendar_view(self) -> QWidget:
        container = QWidget()
        container.setObjectName("ContentArea")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 80)
        layout.setSpacing(12)

        title = QLabel("Calendar")
        title.setObjectName("ViewTitle")
        layout.addWidget(title)

        self._main_calendar = QCalendarWidget()
        self._main_calendar.setObjectName("MainCalendar")
        self._main_calendar.setGridVisible(True)
        self._main_calendar.clicked.connect(self._on_calendar_date_clicked)
        layout.addWidget(self._main_calendar)

        self._cal_list_label = QLabel("Select a date to see reminders")
        self._cal_list_label.setObjectName("EmptyStateLabel")
        self._cal_list_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._cal_list_label)

        self._cal_cards_layout = QVBoxLayout()
        self._cal_cards_layout.setSpacing(8)
        layout.addLayout(self._cal_cards_layout)

        container._view_label = "Calendar"
        return container

    # ── Tab switching ────────────────────────────────────────────────────────

    def _switch_tab(self, index: int) -> None:
        self._active_tab = index
        self._content_stack.setCurrentIndex(index)
        self._update_tab_buttons(index)
        self._refresh_current_view()

    def _update_tab_buttons(self, active: int) -> None:
        for i, btn in enumerate(self._tab_buttons):
            btn.setProperty("active", "true" if i == active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ── Data refresh ─────────────────────────────────────────────────────────

    def _refresh_current_view(self) -> None:
        if self._active_tab == 3:
            self._refresh_calendar_view()
        else:
            self._refresh_list_view(self._active_tab)

    def _get_reminders_for_view(self, label: str) -> list[Reminder]:
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_end = today_start + timedelta(days=1)
        upcoming_end = today_start + timedelta(days=8)

        with get_session() as session:
            q = session.query(Reminder).filter_by(
                user_id=self._user.id, is_active=True, is_done=False
            )
            if label == "Today":
                q = q.filter(Reminder.next_trigger >= today_start, Reminder.next_trigger < today_end)
            elif label == "Upcoming":
                q = q.filter(
                    Reminder.next_trigger >= today_end,
                    Reminder.next_trigger < upcoming_end,
                )
            reminders = q.order_by(Reminder.next_trigger).all()
            for r in reminders:
                session.expunge(r)
        return reminders

    def _refresh_list_view(self, index: int) -> None:
        view = self._views[index]
        label = view._view_label
        cards_layout = view._cards_layout

        # Clear existing cards (leave the stretch at the end)
        while cards_layout.count() > 1:
            item = cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        reminders = self._get_reminders_for_view(label)

        if not reminders:
            empty = QLabel("No reminders here yet. Click + to add one!")
            empty.setObjectName("EmptyStateLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cards_layout.insertWidget(0, empty)
            return

        for i, reminder in enumerate(reminders):
            card = ReminderCard(reminder)
            card.edit_requested.connect(self._open_edit_dialog)
            card.done_requested.connect(self._mark_done)
            card.delete_requested.connect(self._delete_reminder)
            cards_layout.insertWidget(i, card)

    def _refresh_calendar_view(self) -> None:
        # Clear cal cards
        while self._cal_cards_layout.count():
            item = self._cal_cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        selected = self._main_calendar.selectedDate()
        if selected.isValid():
            self._on_calendar_date_clicked(selected)

    def _on_calendar_date_clicked(self, qdate) -> None:
        while self._cal_cards_layout.count():
            item = self._cal_cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        day_start = datetime(qdate.year(), qdate.month(), qdate.day())
        day_end = day_start + timedelta(days=1)

        with get_session() as session:
            reminders = (
                session.query(Reminder)
                .filter_by(user_id=self._user.id, is_active=True, is_done=False)
                .filter(
                    Reminder.next_trigger >= day_start,
                    Reminder.next_trigger < day_end,
                )
                .all()
            )
            for r in reminders:
                session.expunge(r)

        if not reminders:
            self._cal_list_label.setText(
                f"No reminders on {qdate.toString('MMM d, yyyy')}"
            )
            return

        self._cal_list_label.setText(
            f"{len(reminders)} reminder(s) on {qdate.toString('MMM d, yyyy')}"
        )
        for reminder in reminders:
            card = ReminderCard(reminder)
            card.edit_requested.connect(self._open_edit_dialog)
            card.done_requested.connect(self._mark_done)
            card.delete_requested.connect(self._delete_reminder)
            self._cal_cards_layout.addWidget(card)

    # ── CRUD actions ─────────────────────────────────────────────────────────

    def _open_add_dialog(self) -> None:
        dialog = ReminderDialog(self._user, self._scheduler, parent=self)
        dialog.reminder_saved.connect(self._on_reminder_saved)
        dialog.exec()

    def _open_edit_dialog(self, reminder: Reminder) -> None:
        # Re-fetch from DB to get fresh state
        with get_session() as session:
            r = session.get(Reminder, reminder.id)
            if r:
                session.expunge(r)
        dialog = ReminderDialog(self._user, self._scheduler, reminder=r, parent=self)
        dialog.reminder_saved.connect(self._on_reminder_saved)
        dialog.exec()

    def _mark_done(self, reminder: Reminder) -> None:
        with get_session() as session:
            r = session.get(Reminder, reminder.id)
            if r:
                r.is_done = True
                r.is_active = False
        self._scheduler.remove_reminder(reminder.id)
        self._refresh_current_view()

    def _delete_reminder(self, reminder: Reminder) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Reminder",
            f'Delete "{reminder.name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._scheduler.remove_reminder(reminder.id)
            with get_session() as session:
                r = session.get(Reminder, reminder.id)
                if r:
                    session.delete(r)
            self._refresh_current_view()

    @Slot(object)
    def _on_reminder_saved(self, reminder: Reminder) -> None:
        self._refresh_current_view()

    # ── Scheduler signal ─────────────────────────────────────────────────────

    def _connect_scheduler(self) -> None:
        self._scheduler.signals.triggered.connect(self._on_reminder_triggered)

    @Slot(int)
    def _on_reminder_triggered(self, reminder_id: int) -> None:
        with get_session() as session:
            r = session.get(Reminder, reminder_id)
            if r and r.is_active and not r.is_done:
                session.expunge(r)
            else:
                return
        self._notification_service.notify(r)
        self._refresh_current_view()

    # ── Settings ─────────────────────────────────────────────────────────────

    def _show_settings(self) -> None:
        from remindee.ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self._user, parent=self)
        dialog.theme_changed.connect(self._on_theme_changed)
        dialog.exec()

    @Slot(str)
    def _on_theme_changed(self, theme: str) -> None:
        with get_session() as session:
            u = session.get(User, self._user.id)
            if u:
                u.theme = theme
        self._user.theme = theme
        from remindee.ui.styles import apply_theme
        apply_theme(QApplication.instance(), theme)

    # ── Window events ────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "REMINDEE",
            "Running in the background. Right-click the tray icon to quit.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Keep FAB in bottom-right corner of the central widget
        fab = self._fab
        cw = self.centralWidget()
        margin = 24
        fab.move(cw.width() - fab.width() - margin, cw.height() - fab.height() - margin)
        fab.raise_()
