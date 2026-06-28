from __future__ import annotations

from datetime import datetime, date, timedelta
from pathlib import Path
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QIcon, QAction, QPainter, QColor
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
    QCalendarWidget,
    QDialog,
    QFrame,
    QSizePolicy,
)

from remindee.models.reminder import Reminder, FrequencyType
from remindee.models.note_folder import NoteFolder
from remindee.models.user import User
from remindee.services.note_service import NoteService
from remindee.services.notification_service import NotificationService
from remindee.services.scheduler_service import SchedulerService
from remindee.ui.note_editor import NoteEditor
from remindee.ui.note_list_widget import NoteListWidget
from remindee.ui.reminder_card import ReminderCard
from remindee.ui.reminder_dialog import ReminderDialog
from remindee.ui.styles import apply_calendar_palette
from remindee.utils.database import get_session

_ICONS_DIR = Path(__file__).parent.parent / "resources" / "icons"


class _GlassPanel(QWidget):
    """
    Semi-transparent central panel that paints its own backdrop via QPainter.

    Painting directly in paintEvent (with CompositionMode_Source) is the only
    reliable way to write RGBA pixels on macOS under WA_TranslucentBackground —
    QSS background + palette approaches don't always honour the alpha channel
    for plain QWidget children.
    """
    _COLORS: dict[str, QColor] = {
        "light": QColor(255, 248, 242, 240),  # ~94% opaque warm cream — stays white regardless of OS dark mode
        "dark":  QColor(18,  10,  4,   160),  # ~63% warm near-black — frosted dark glass
    }

    def __init__(self, theme: str = "light", parent=None) -> None:
        super().__init__(parent)
        self._color = self._COLORS.get(theme, self._COLORS["light"])

    def set_theme(self, theme: str) -> None:
        self._color = self._COLORS.get(theme, self._COLORS["light"])
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        # CompositionMode_Source writes RGBA directly — no blending with what
        # was already in the backing store, which lets the alpha channel reach
        # the system compositor correctly.
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), self._color)
        p.end()

class _ConfirmDialog(QDialog):
    """Styled Yes/No dialog that respects the app's light and dark themes."""

    def __init__(self, message: str, confirm_label: str = "Delete",
                 parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(20)

        lbl = QLabel(message)
        lbl.setObjectName("ConfirmMsg")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setMinimumHeight(38)
        cancel_btn.setMinimumWidth(90)
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(cancel_btn)

        confirm_btn = QPushButton(confirm_label)
        confirm_btn.setObjectName("DangerBtn")
        confirm_btn.setMinimumHeight(38)
        confirm_btn.setMinimumWidth(90)
        confirm_btn.setDefault(True)
        confirm_btn.clicked.connect(self.accept)
        row.addWidget(confirm_btn)

        layout.addLayout(row)


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

        # Notes state
        self._note_service = NoteService()
        self._folder_tab_ids: dict[int, int] = {}          # folder_id → tab_index
        self._folder_tab_ids_reverse: dict[int, int] = {}  # tab_index → folder_id

        self.setWindowTitle("REMINDEE")
        self.setMinimumSize(940, 640)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._setup_tray()
        self._notification_service = NotificationService(self._tray, scheduler)
        self._build_ui()
        self._connect_scheduler()

        scheduler.start(user.id)
        self._refresh_current_view()

        # Load existing folders at startup
        folders = self._note_service.get_folders(self._user.id)
        for folder in folders:
            self._add_folder_tab(folder)

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
        self._glass_panel = _GlassPanel(self._user.theme)
        self._glass_panel.setObjectName("CentralWidget")
        self.setCentralWidget(self._glass_panel)
        root_layout = QHBoxLayout(self._glass_panel)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())

        self._content_stack = QStackedWidget()
        self._content_stack.setObjectName("ContentArea")
        # Prevent QStackedWidget from filling with its palette colour —
        # _GlassPanel.paintEvent is the sole backdrop painter.
        self._content_stack.setAutoFillBackground(False)
        self._views = [
            self._build_list_view("Today"),
            self._build_list_view("Upcoming"),
            self._build_list_view("All"),
            self._build_calendar_view(),
        ]
        for view in self._views:
            self._content_stack.addWidget(view)

        # Notes view (index 4)
        self._notes_panel = self._build_notes_view()
        self._content_stack.addWidget(self._notes_panel)

        root_layout.addWidget(self._content_stack, stretch=1)

        # FAB — floating button parented to the central widget
        self._fab = QPushButton("+", self._glass_panel)
        self._fab.setObjectName("FAB")
        self._fab.setFixedSize(56, 56)
        self._fab.raise_()
        self._fab.clicked.connect(self._on_fab_clicked)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 24, 14, 16)
        layout.setSpacing(2)

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

        # ── Notes section separator ──────────────────────────────────────────
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: rgba(255,255,255,0.30); margin: 6px 0;")
        layout.addWidget(separator)

        notes_label = QLabel("NOTES")
        notes_label.setObjectName("SectionLabel")
        layout.addWidget(notes_label)

        # "All Notes" tab button (index 4)
        all_notes_btn = self._make_sidebar_btn("  📝  All Notes", 4)
        layout.addWidget(all_notes_btn)
        self._tab_buttons.append(all_notes_btn)

        # Folder container — holds per-folder buttons dynamically
        self._sidebar_folder_container = QWidget()
        folder_layout = QVBoxLayout(self._sidebar_folder_container)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(2)
        layout.addWidget(self._sidebar_folder_container)

        # "+ Folder" button
        add_folder_btn = QPushButton("  + Folder")
        add_folder_btn.setObjectName("AddFolderBtn")
        add_folder_btn.clicked.connect(self._on_add_folder)
        layout.addWidget(add_folder_btn)

        layout.addStretch()

        # Settings button
        settings_btn = QPushButton("  ⚙  Settings")
        settings_btn.setObjectName("SidebarBtn")
        settings_btn.clicked.connect(self._show_settings)
        layout.addWidget(settings_btn)

        self._update_tab_buttons(0)
        return sidebar

    def _make_sidebar_btn(self, text: str, tab_index: int) -> QPushButton:
        """Create a sidebar button that switches to tab_index when clicked."""
        btn = QPushButton(text)
        btn.setObjectName("SidebarBtn")
        btn.setCheckable(False)
        btn.clicked.connect(lambda checked, idx=tab_index: self._switch_tab(idx))
        return btn

    def _build_notes_view(self) -> QWidget:
        """Build the split-pane Notes view: list on the left, editor on the right."""
        container = QWidget()
        container.setObjectName("ContentArea")
        container.setAutoFillBackground(False)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._note_list = NoteListWidget()
        self._note_list.setFixedWidth(260)
        layout.addWidget(self._note_list)

        self._note_editor = NoteEditor()
        layout.addWidget(self._note_editor, stretch=1)

        # Wire signals
        self._note_list.note_selected.connect(self._on_note_selected)
        self._note_list.search_changed.connect(self._on_note_search)
        self._note_editor.note_saved.connect(self._on_note_saved)
        self._note_editor.convert_to_reminder.connect(self._on_note_to_reminder)
        self._note_editor.delete_requested.connect(self._on_note_delete_from_editor)

        return container

    def _build_list_view(self, label: str) -> QWidget:
        container = QWidget()
        container.setObjectName("ContentArea")
        container.setAutoFillBackground(False)
        outer_layout = QVBoxLayout(container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        title = QLabel(label)
        title.setObjectName("ViewTitle")
        outer_layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)

        scroll_content = QWidget()
        scroll_content.setObjectName("ContentArea")
        scroll_content.setAutoFillBackground(False)
        self._cards_layout = None  # will be set per view in refresh

        # store the layout on the scroll_content
        cards_layout = QVBoxLayout(scroll_content)
        cards_layout.setContentsMargins(28, 14, 28, 90)
        cards_layout.setSpacing(12)
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
        container.setAutoFillBackground(False)
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        title = QLabel("Calendar")
        title.setObjectName("ViewTitle")
        outer.addWidget(title)

        # Scroll area so reminder cards below the calendar don't get clipped
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)

        inner = QWidget()
        inner.setObjectName("ContentArea")
        inner.setAutoFillBackground(False)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(28, 14, 28, 90)
        layout.setSpacing(16)

        self._main_calendar = QCalendarWidget()
        self._main_calendar.setObjectName("MainCalendar")
        self._main_calendar.setGridVisible(False)
        self._main_calendar.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        # Only connect `clicked` — selectionChanged also fires on month nav arrows,
        # which caused the calendar to jump months unexpectedly.
        self._main_calendar.clicked.connect(self._on_calendar_date_clicked)
        apply_calendar_palette(self._main_calendar, self._user.theme)
        layout.addWidget(self._main_calendar)

        self._cal_list_label = QLabel("Select a date to see reminders")
        self._cal_list_label.setObjectName("EmptyStateLabel")
        self._cal_list_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._cal_list_label)

        self._cal_cards_layout = QVBoxLayout()
        self._cal_cards_layout.setSpacing(10)
        layout.addLayout(self._cal_cards_layout)
        layout.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll)

        container._view_label = "Calendar"
        return container

    # ── Tab switching ────────────────────────────────────────────────────────

    def _switch_tab(self, index: int) -> None:
        self._active_tab = index
        if index <= 3:
            # Reminder views live at stack indices 0–3
            self._content_stack.setCurrentIndex(index)
            self._refresh_current_view()
        else:
            # Notes view is at stack index 4
            self._content_stack.setCurrentIndex(4)
            if index == 4:
                self._refresh_notes()
            elif index in self._folder_tab_ids_reverse:
                self._refresh_notes(folder_id=self._folder_tab_ids_reverse[index])
        self._update_tab_buttons(index)

    def _update_tab_buttons(self, active: int) -> None:
        for i, btn in enumerate(self._tab_buttons):
            # _tab_buttons[0..3] → reminder tabs, [4] → All Notes,
            # [5+] → per-folder buttons (appended in _add_folder_tab)
            btn.setProperty("active", "true" if i == active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ── Data refresh ─────────────────────────────────────────────────────────

    def _refresh_current_view(self) -> None:
        if self._active_tab == 3:
            self._refresh_calendar_view()
        elif self._active_tab <= 3:
            self._refresh_list_view(self._active_tab)
        # For notes tabs (≥4) refresh is triggered by _switch_tab directly

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
        selected = self._main_calendar.selectedDate()
        if selected.isValid():
            self._on_calendar_date_clicked(selected)

    def _clear_cal_cards(self) -> None:
        while self._cal_cards_layout.count():
            item = self._cal_cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_calendar_date_clicked(self, qdate) -> None:
        self._clear_cal_cards()

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

    # ── Notes refresh ────────────────────────────────────────────────────────

    def _refresh_notes(self, folder_id: int | None = None) -> None:
        """Load notes from DB into the note list widget."""
        if folder_id is not None:
            notes = self._note_service.get_notes_in_folder(self._user.id, folder_id)
        else:
            notes = self._note_service.get_all_notes(self._user.id)
        self._note_list.load_notes(notes)
        self._note_editor.clear()

    def _refresh_notes_preserve_selection(self) -> None:
        """Re-load the note list, keeping the current tab's folder filter."""
        if self._active_tab == 4:
            self._refresh_notes()
        elif self._active_tab in self._folder_tab_ids_reverse:
            self._refresh_notes(folder_id=self._folder_tab_ids_reverse[self._active_tab])

    # ── Note slots ───────────────────────────────────────────────────────────

    @Slot(int)
    def _on_note_selected(self, note_id: int) -> None:
        """Load selected note into the editor."""
        notes = self._note_service.get_all_notes(self._user.id)
        note = next((n for n in notes if n.id == note_id), None)
        if note is None:
            return
        self._note_editor.load_note(note.id, note.title or "", note.body_md or "", note.color_label)

    @Slot(int, str, str)
    def _on_note_saved(self, note_id: int, title: str, body_md: str) -> None:
        """Auto-save: update note in DB and refresh list."""
        self._note_service.update_note(note_id, title=title, body_md=body_md)
        self._refresh_notes_preserve_selection()

    @Slot(int)
    def _on_note_to_reminder(self, note_id: int) -> None:
        """Convert note to reminder: open ReminderDialog pre-filled."""
        notes = self._note_service.get_all_notes(self._user.id)
        note = next((n for n in notes if n.id == note_id), None)
        if note is None:
            return
        kwargs = self._note_service.note_to_reminder_kwargs(note)
        from remindee.ui.reminder_dialog import ReminderDialog
        dialog = ReminderDialog(
            self._user, self._scheduler,
            prefill_name=kwargs["prefill_name"],
            parent=self,
        )
        dialog.reminder_saved.connect(self._on_reminder_saved)
        dialog.exec()

    @Slot(int)
    def _on_note_delete_from_editor(self, note_id: int) -> None:
        """Delete note after confirmation."""
        dlg = _ConfirmDialog("Delete this note?", confirm_label="Delete", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._note_service.delete_note(note_id)
            self._note_editor.clear()
            self._refresh_notes_preserve_selection()

    @Slot(str)
    def _on_note_search(self, query: str) -> None:
        if query.strip():
            notes = self._note_service.search_notes(self._user.id, query.strip())
            self._note_list.load_notes(notes)
        else:
            self._refresh_notes_preserve_selection()

    # ── Folder management ────────────────────────────────────────────────────

    def _on_add_folder(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            folder = self._note_service.create_folder(self._user.id, name.strip())
            self._add_folder_tab(folder)

    def _add_folder_tab(self, folder: NoteFolder) -> None:
        """Add a new folder button to the sidebar and assign a tab index."""
        new_idx = 5 + len(self._folder_tab_ids)
        self._folder_tab_ids[folder.id] = new_idx
        self._folder_tab_ids_reverse[new_idx] = folder.id
        btn = self._make_sidebar_btn(f"  📁  {folder.name}", new_idx)
        self._sidebar_folder_container.layout().addWidget(btn)
        self._tab_buttons.append(btn)

    # ── CRUD actions ─────────────────────────────────────────────────────────

    def _on_fab_clicked(self) -> None:
        """FAB creates a note when on a notes tab, otherwise opens ReminderDialog."""
        if self._active_tab >= 4:
            note = self._note_service.create_note(self._user.id)
            self._refresh_notes()
            self._note_list.select_note(note.id)
            self._note_editor.load_note(note.id, "", "", None)
        else:
            self._open_add_dialog()

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
        dlg = _ConfirmDialog(f'Delete "{reminder.name}"?', parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
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
        dialog.font_changed.connect(self._on_font_changed)
        dialog.exec()

    @Slot(str)
    def _on_theme_changed(self, theme: str) -> None:
        with get_session() as session:
            u = session.get(User, self._user.id)
            if u:
                u.theme = theme
        self._user.theme = theme
        from remindee.ui.styles import apply_theme, _resolve_theme
        apply_theme(QApplication.instance(), theme)
        apply_calendar_palette(self._main_calendar, theme)
        self._glass_panel.set_theme(theme)
        from remindee.utils.vibrancy import enable_mac_vibrancy
        enable_mac_vibrancy(self, dark=(_resolve_theme(theme) == "dark"))

    @Slot(str)
    def _on_font_changed(self, font_name: str) -> None:
        with get_session() as session:
            u = session.get(User, self._user.id)
            if u:
                u.app_font = font_name
        self._user.app_font = font_name
        from PySide6.QtGui import QFont
        QApplication.instance().setFont(QFont(font_name, 13))

    # ── Quick Note (reminder) ────────────────────────────────────────────────

    @Slot()
    def show_quick_note(self) -> None:
        if hasattr(self, "_quick_note") and self._quick_note.isVisible():
            self._quick_note.raise_()
            self._quick_note.activateWindow()
            return
        from remindee.ui.quick_note_dialog import QuickNoteDialog
        dlg = QuickNoteDialog()
        dlg.save_requested.connect(self._on_quick_save)
        dlg.reminder_requested.connect(self._on_quick_reminder)
        self._quick_note = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        # macOS: bring REMINDEE to front so the dialog can receive key events
        try:
            from AppKit import NSApplication
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass

    @Slot(str)
    def _on_quick_save(self, text: str) -> None:
        with get_session() as session:
            r = Reminder(
                user_id      = self._user.id,
                name         = text[:200],
                frequency    = FrequencyType.RARELY,
                font_family  = getattr(self._user, "app_font", None) or "Marker Felt",
                is_active    = True,
                is_done      = False,
            )
            session.add(r)
            session.flush()
            session.refresh(r)
            session.expunge(r)
        self._scheduler.schedule_reminder(r)
        self._refresh_current_view()

    @Slot(str)
    def _on_quick_reminder(self, text: str) -> None:
        from remindee.ui.reminder_dialog import ReminderDialog
        dialog = ReminderDialog(
            self._user, self._scheduler, prefill_name=text, parent=self
        )
        dialog.reminder_saved.connect(self._on_reminder_saved)
        dialog.exec()

    # ── Quick Note (as Note) ─────────────────────────────────────────────────

    @Slot()
    def show_quick_note_as_note(self) -> None:
        """Open QuickNoteDialog; saving creates a Note instead of a Reminder."""
        if hasattr(self, "_quick_note") and self._quick_note.isVisible():
            self._quick_note.raise_()
            self._quick_note.activateWindow()
            return
        from remindee.ui.quick_note_dialog import QuickNoteDialog
        dlg = QuickNoteDialog()
        dlg.save_requested.connect(self._on_quick_note_save)
        dlg.reminder_requested.connect(self._on_quick_reminder)
        self._quick_note = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        try:
            from AppKit import NSApplication
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass

    @Slot(str)
    def _on_quick_note_save(self, text: str) -> None:
        self._note_service.create_note(self._user.id, title=text[:200])
        if self._active_tab >= 4:
            self._refresh_notes_preserve_selection()

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
        # _fab is created inside _build_ui(); guard against Qt firing resizeEvent
        # before _build_ui() completes (e.g. during the super().__init__ geometry pass).
        if not hasattr(self, "_fab"):
            return
        fab = self._fab
        cw = self.centralWidget()
        if cw is None:
            return
        margin = 24
        fab.move(cw.width() - fab.width() - margin, cw.height() - fab.height() - margin)
        fab.raise_()
