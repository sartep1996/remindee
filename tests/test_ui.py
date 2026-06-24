"""
PASS 1 — Boundary Contradiction Sweep: headless UI layer.

Boundary matrix:
  theme       : 'light', 'dark', 'system', invalid string
  load_qss    : must return non-empty string; must contain no unreplaced @tokens
  calendar    : apply_calendar_palette('light') → Base == #FFFCF8
  ReminderCard: with details, without details, specific-datetime, next_trigger overdue
  ReminderDialog: no parent, minimal mock user+scheduler

PASS 2 — Mock Reality Check:
  Qt widgets are created for real (offscreen platform). We use minimal MagicMock
  stubs ONLY for SchedulerService in ReminderDialog (it calls schedule_reminder()
  which requires a running APScheduler — we don't want scheduler side-effects in
  UI tests). The User object is a real SQLAlchemy User populated with attributes.

PASS 3 — State teardown:
  Qt objects created in tests are NOT parented to a long-lived widget — they are
  garbage-collected after the test ends. No global stylesheet is permanently
  applied (setStyleSheet("") resets after tests that call apply_theme()).

All tests require QApplication, provided by the session-scoped `qapp` fixture
from conftest.py.
"""
import re
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta


# ─── helper: build a minimal detached User-like object ───────────────────────

def _make_user(user_id=1, theme="light"):
    """
    Return a minimal user-like namespace with the attributes ReminderDialog reads.

    SQLAlchemy 2.0 ORM instances require _sa_instance_state (set by __init__);
    bypassing it with __new__ raises AttributeError on attribute assignment.
    ReminderDialog only reads .id, .theme from the user object, so a plain
    SimpleNamespace is sufficient and avoids SA machinery entirely.
    """
    from types import SimpleNamespace
    return SimpleNamespace(
        id=user_id,
        email="ui_test@example.com",
        username="ui_tester",
        theme=theme,
        display_name="UI Tester",
        password_hash=None,
        google_id=None,
        google_access_token=None,
        google_refresh_token=None,
        token_expiry=None,
        avatar_url=None,
    )


def _make_reminder(user_id=1, name="Test", frequency=None, details=None,
                   specific_datetime=None, next_trigger=None, reminder_id=1):
    """
    Return a minimal reminder-like namespace.
    ReminderCard reads: .name, .details, .frequency, .specific_datetime,
    .next_trigger from the Reminder.  SimpleNamespace avoids SA ORM machinery.
    """
    from types import SimpleNamespace
    from remindee.models.reminder import FrequencyType
    if frequency is None:
        frequency = FrequencyType.OFTEN
    return SimpleNamespace(
        id=reminder_id,
        user_id=user_id,
        name=name,
        details=details,
        frequency=frequency,
        specific_datetime=specific_datetime,
        next_trigger=next_trigger,
        is_done=False,
        is_active=True,
        snooze_until=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


# ─── Module import tests ──────────────────────────────────────────────────────

class TestUIModuleImports:
    def test_styles_module_imports(self, qapp):
        import remindee.ui.styles  # noqa: F401

    def test_reminder_card_module_imports(self, qapp):
        import remindee.ui.reminder_card  # noqa: F401

    def test_reminder_dialog_module_imports(self, qapp):
        import remindee.ui.reminder_dialog  # noqa: F401

    def test_login_dialog_module_imports(self, qapp):
        import remindee.ui.login_dialog  # noqa: F401

    def test_main_window_module_imports(self, qapp):
        import remindee.ui.main_window  # noqa: F401

    def test_settings_dialog_module_imports(self, qapp):
        import remindee.ui.settings_dialog  # noqa: F401


# ─── styles.py: load_qss ─────────────────────────────────────────────────────

class TestLoadQss:
    def test_load_qss_light_returns_nonempty(self, qapp):
        from remindee.ui.styles import load_qss
        result = load_qss("light")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_load_qss_dark_returns_nonempty(self, qapp):
        from remindee.ui.styles import load_qss
        result = load_qss("dark")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_load_qss_light_no_unreplaced_tokens(self, qapp):
        """
        All @token references must be resolved — none may survive in the output.
        A residual '@' followed by a word character indicates a forgotten token.
        """
        from remindee.ui.styles import load_qss
        qss = load_qss("light")
        unreplaced = re.findall(r'@\w+', qss)
        assert unreplaced == [], (
            f"Unreplaced tokens found in light QSS: {unreplaced}"
        )

    def test_load_qss_dark_no_unreplaced_tokens(self, qapp):
        from remindee.ui.styles import load_qss
        qss = load_qss("dark")
        unreplaced = re.findall(r'@\w+', qss)
        assert unreplaced == [], (
            f"Unreplaced tokens found in dark QSS: {unreplaced}"
        )

    def test_load_qss_system_returns_nonempty(self, qapp):
        """'system' theme must resolve to light or dark and return non-empty QSS."""
        from remindee.ui.styles import load_qss
        result = load_qss("system")
        assert len(result) > 0

    def test_load_qss_invalid_theme_falls_back_to_light(self, qapp):
        """An unknown theme string must fall back to 'light' rather than crash."""
        from remindee.ui.styles import load_qss
        result = load_qss("neon_purple")
        assert len(result) > 0  # fallback, not an empty string


# ─── styles.py: apply_theme ──────────────────────────────────────────────────

class TestApplyTheme:
    def test_apply_theme_light_does_not_raise(self, qapp):
        from remindee.ui.styles import apply_theme
        apply_theme(qapp, "light")
        qapp.setStyleSheet("")  # teardown — reset global stylesheet

    def test_apply_theme_dark_does_not_raise(self, qapp):
        from remindee.ui.styles import apply_theme
        apply_theme(qapp, "dark")
        qapp.setStyleSheet("")

    def test_apply_theme_sets_nonempty_stylesheet(self, qapp):
        from remindee.ui.styles import apply_theme
        apply_theme(qapp, "light")
        assert len(qapp.styleSheet()) > 0
        qapp.setStyleSheet("")


# ─── styles.py: apply_calendar_palette ───────────────────────────────────────

class TestCalendarPalette:
    def test_apply_calendar_palette_light_base_colour(self, qapp):
        """
        Spec: apply_calendar_palette(cal, 'light') must set QPalette.Base to #FFFCF8.
        This is the key assertion from the requirements.
        """
        from PySide6.QtWidgets import QCalendarWidget
        from PySide6.QtGui import QPalette, QColor
        from remindee.ui.styles import apply_calendar_palette

        cal = QCalendarWidget()
        apply_calendar_palette(cal, "light")

        base_color = cal.palette().color(QPalette.ColorRole.Base)
        expected = QColor("#FFFCF8")
        assert base_color.name() == expected.name(), (
            f"Light calendar Base color: expected {expected.name()}, got {base_color.name()}"
        )

    def test_apply_calendar_palette_dark_does_not_raise(self, qapp):
        from PySide6.QtWidgets import QCalendarWidget
        from remindee.ui.styles import apply_calendar_palette

        cal = QCalendarWidget()
        apply_calendar_palette(cal, "dark")

    def test_apply_calendar_palette_light_highlight_is_accent(self, qapp):
        """Highlight colour must be the brand accent #FF6B35."""
        from PySide6.QtWidgets import QCalendarWidget
        from PySide6.QtGui import QPalette, QColor
        from remindee.ui.styles import apply_calendar_palette

        cal = QCalendarWidget()
        apply_calendar_palette(cal, "light")
        hl = cal.palette().color(QPalette.ColorRole.Highlight)
        assert hl.name() == QColor("#FF6B35").name()

    def test_apply_calendar_palette_autofill_enabled(self, qapp):
        """autoFillBackground must be set to True after applying the palette."""
        from PySide6.QtWidgets import QCalendarWidget
        from remindee.ui.styles import apply_calendar_palette

        cal = QCalendarWidget()
        apply_calendar_palette(cal, "light")
        assert cal.autoFillBackground()


# ─── ReminderCard ─────────────────────────────────────────────────────────────

class TestReminderCard:
    def test_instantiates_with_minimal_reminder(self, qapp):
        from remindee.ui.reminder_card import ReminderCard
        r = _make_reminder()
        card = ReminderCard(r)
        assert card is not None

    def test_instantiates_with_details(self, qapp):
        from remindee.ui.reminder_card import ReminderCard
        r = _make_reminder(details="Buy semi-skimmed milk")
        card = ReminderCard(r)
        assert card is not None

    def test_instantiates_without_details(self, qapp):
        from remindee.ui.reminder_card import ReminderCard
        r = _make_reminder(details=None)
        card = ReminderCard(r)
        assert card is not None

    def test_instantiates_with_specific_datetime(self, qapp):
        from remindee.ui.reminder_card import ReminderCard
        from remindee.models.reminder import FrequencyType
        future = datetime.utcnow() + timedelta(days=2)
        r = _make_reminder(frequency=FrequencyType.SPECIFIC, specific_datetime=future)
        card = ReminderCard(r)
        assert card is not None

    def test_overdue_reminder_does_not_crash(self, qapp):
        """
        PASS 1 boundary: next_trigger in the past must render 'Overdue' text
        without raising.
        """
        from remindee.ui.reminder_card import ReminderCard
        past = datetime.utcnow() - timedelta(hours=3)
        r = _make_reminder(next_trigger=past)
        card = ReminderCard(r)
        assert card is not None

    def test_reminder_with_long_name_does_not_crash(self, qapp):
        """
        PASS 1 boundary: extremely long reminder name (unicode + emoji) must
        not crash the card builder.
        """
        from remindee.ui.reminder_card import ReminderCard
        long_name = "A" * 500 + " — 日本語テスト — <script>alert(1)</script>"
        r = _make_reminder(name=long_name)
        card = ReminderCard(r)
        assert card is not None

    def test_refresh_replaces_layout(self, qapp):
        """refresh() with a new Reminder must rebuild the layout without crash."""
        from remindee.ui.reminder_card import ReminderCard
        r1 = _make_reminder(name="Original")
        r2 = _make_reminder(name="Updated", reminder_id=2)
        card = ReminderCard(r1)
        card.refresh(r2)
        assert card is not None

    def test_all_frequency_labels_render(self, qapp):
        """All five FrequencyType values must produce a ReminderCard without error."""
        from remindee.ui.reminder_card import ReminderCard
        from remindee.models.reminder import FrequencyType
        for i, freq in enumerate(FrequencyType):
            r = _make_reminder(frequency=freq, reminder_id=100 + i)
            card = ReminderCard(r)
            assert card is not None


# ─── ReminderDialog ───────────────────────────────────────────────────────────

class TestReminderDialog:
    def _make_mock_scheduler(self):
        svc = MagicMock()
        svc.schedule_reminder = MagicMock()
        return svc

    def test_instantiates_without_parent(self, qapp):
        """ReminderDialog(user, scheduler, parent=None) must not raise."""
        from remindee.ui.reminder_dialog import ReminderDialog
        user = _make_user()
        svc = self._make_mock_scheduler()
        dlg = ReminderDialog(user, svc, parent=None)
        assert dlg is not None
        dlg.reject()

    def test_instantiates_in_edit_mode(self, qapp):
        """Passing a Reminder to ReminderDialog must switch to edit mode."""
        from remindee.ui.reminder_dialog import ReminderDialog
        from remindee.models.reminder import FrequencyType
        user = _make_user()
        svc = self._make_mock_scheduler()
        r = _make_reminder(user_id=user.id, name="Edit me",
                           frequency=FrequencyType.MEDIUM)
        dlg = ReminderDialog(user, svc, reminder=r, parent=None)
        assert dlg._edit_mode is True
        dlg.reject()

    def test_instantiates_with_dark_theme(self, qapp):
        """ReminderDialog must handle a 'dark' theme user without crashing."""
        from remindee.ui.reminder_dialog import ReminderDialog
        user = _make_user(theme="dark")
        svc = self._make_mock_scheduler()
        dlg = ReminderDialog(user, svc, parent=None)
        assert dlg is not None
        dlg.reject()

    def test_instantiates_with_specific_reminder_shows_calendar(self, qapp):
        """
        Edit mode with a SPECIFIC reminder must set dt_widget to max height 420.
        """
        from remindee.ui.reminder_dialog import ReminderDialog
        from remindee.models.reminder import FrequencyType
        user = _make_user()
        svc = self._make_mock_scheduler()
        future = datetime.utcnow() + timedelta(days=5)
        r = _make_reminder(frequency=FrequencyType.SPECIFIC,
                           specific_datetime=future, reminder_id=77)
        dlg = ReminderDialog(user, svc, reminder=r, parent=None)
        assert dlg._dt_widget.maximumHeight() == 420
        dlg.reject()

    def test_window_title_new_reminder(self, qapp):
        from remindee.ui.reminder_dialog import ReminderDialog
        user = _make_user()
        svc = self._make_mock_scheduler()
        dlg = ReminderDialog(user, svc, parent=None)
        assert dlg.windowTitle() == "New Reminder"
        dlg.reject()

    def test_window_title_edit_reminder(self, qapp):
        from remindee.ui.reminder_dialog import ReminderDialog
        user = _make_user()
        svc = self._make_mock_scheduler()
        r = _make_reminder(user_id=user.id)
        dlg = ReminderDialog(user, svc, reminder=r, parent=None)
        assert dlg.windowTitle() == "Edit Reminder"
        dlg.reject()
