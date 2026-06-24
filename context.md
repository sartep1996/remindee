# REMINDEE — Project Context

## What was built

A PySide6 desktop reminder app called **REMINDEE** built from scratch in this session.

---

## Tech stack

| Layer | Library |
|---|---|
| GUI | PySide6 |
| Database | SQLite via SQLAlchemy 2.0 |
| Auth | bcrypt (local) + google-auth-oauthlib (Google OAuth) |
| Scheduling | APScheduler 3.x (BackgroundScheduler, in-memory job store) |
| Notifications | QSystemTrayIcon + custom ActionBubble dialog |
| Config | python-dotenv + platformdirs |

---

## Project structure

```
remindee/
├── main.py                        # entry point (root)
├── remindee/
│   ├── main.py                    # QApplication bootstrap → LoginDialog → MainWindow
│   ├── models/
│   │   ├── base.py                # SQLAlchemy declarative Base
│   │   ├── user.py                # User model (local + Google OAuth fields)
│   │   └── reminder.py            # Reminder model + FrequencyType enum
│   ├── services/
│   │   ├── auth_service.py        # LocalAuthService (bcrypt) + GoogleAuthService
│   │   ├── scheduler_service.py   # SchedulerService + SchedulerSignals(QObject)
│   │   └── notification_service.py# NotificationService + ActionBubble dialog
│   ├── ui/
│   │   ├── styles.py              # Token-based theme system + apply_calendar_palette()
│   │   ├── login_dialog.py        # Login + Register stacked pages, Google OAuth thread
│   │   ├── main_window.py         # MainWindow: sidebar, views, FAB, tray
│   │   ├── reminder_card.py       # ReminderCard widget
│   │   ├── reminder_dialog.py     # Add/Edit reminder dialog with animated calendar
│   │   └── settings_dialog.py     # Theme switcher dialog
│   ├── utils/
│   │   ├── config.py              # dotenv + platformdirs DB path
│   │   └── database.py            # engine, SessionLocal, init_db(), get_session()
│   └── resources/
│       ├── styles.qss             # Token-based stylesheet
│       └── icons/
│           └── tray.png           # System tray icon (32×32 blue circle PNG)
├── requirements.txt
├── pyproject.toml
└── .env.example
```

---

## Key architecture decisions

### Threading
- APScheduler runs in a daemon `BackgroundScheduler` (in-memory job store — avoids QObject pickle error from SQLAlchemy job store)
- Cross-thread signaling: `SchedulerSignals(QObject)` with `triggered = Signal(int)`, emitted from the scheduler thread, auto-queued to the main thread via Qt's `AutoConnection`
- Google OAuth runs in `_OAuthThread(QThread)` so `flow.run_local_server()` doesn't block the UI

### Transparency
- `WA_TranslucentBackground` set on `MainWindow` and `LoginDialog`
- `QMainWindow { background: transparent }` — desktop shows through
- `QWidget#CentralWidget { background: rgba(255,248,242,0.80) }` — 80% opaque warm white backdrop

### Calendar palette fix
- `WA_TranslucentBackground` causes `QCalendarWidget`'s internal `QAbstractItemView` to ignore QSS background rules and render black
- Fix: `apply_calendar_palette(cal, theme)` in `styles.py` sets `QPalette.Base = #FFFCF8` directly — bypasses QSS entirely for cell backgrounds
- Called on every `QCalendarWidget` at construction time and on theme change

### Scheduler job store
- Uses default in-memory job store (NOT SQLAlchemy job store) because the scheduler's `_on_trigger` bound method captures `self` which contains a `QObject` (`SchedulerSignals`), and APScheduler's SQLAlchemy store pickles job state — `QObject` is not picklable
- Jobs are rebuilt from DB on every `start(user_id)` call

### Session management
- Short-lived `get_session()` context manager (commit/rollback/close) per operation
- SQLAlchemy objects are `expunge()`-d before the session closes so they can be used outside

---

## Design system

### Color palette (light theme — default)
| Token | Value | Used for |
|---|---|---|
| Sidebar | `qlineargradient #FF7A45 → #E84515` | Sidebar background |
| CentralWidget | `rgba(255,248,242,0.80)` | Main content backdrop |
| `@accent` | `#FF6B35` | Orange, buttons, badges |
| `@surface_card` | `rgba(255,255,255,0.72)` | Cards |
| `@surface` | `rgba(255,255,255,0.80)` | Inputs, combos |
| `@border` | `rgba(255,107,53,0.18)` | Borders |
| `@text` | `#1C0800` | Primary text |
| `@text2` | `#9A6040` | Secondary text |

### Dark theme
Same orange accent, near-black warm bg (`#0D0804 → #1A0E06`), all surfaces flipped to low-alpha whites.

### Sidebar (always orange regardless of theme)
- Text: white (`rgba(255,255,255,0.95)` for name, `0.62` for email, `0.78` for buttons)
- Active tab: `rgba(255,255,255,0.24)` frosted-glass pill
- Hover: `rgba(255,255,255,0.16)`

### QSS token system
Tokens replaced at runtime by `load_qss(theme)` in `styles.py`. Longer tokens are listed first in the dict to prevent partial replacements (e.g. `@accent_hover` before `@accent`).

---

## Bugs fixed during session

| Bug | Root cause | Fix |
|---|---|---|
| Black calendar cells | `WA_TranslucentBackground` makes `QAbstractItemView` ignore QSS `background` | `apply_calendar_palette()` via `QPalette.Base` |
| Calendar month jumping | `selectionChanged` fires on prev/next arrow clicks, not just date clicks | Removed `selectionChanged`; only `clicked` updates the reminder list |
| Dialog calendar clipped | Animation target 370 px too small for `QCalendarWidget` (~250 px grid + labels) | Raised to 420 px + `adjustSize()` on animation finish |
| Calendar view no scroll | Reminder cards below calendar overflowed off-screen | Wrapped in `QScrollArea` |
| APScheduler pickle error | Bound method referencing `QObject` can't be pickled by SQLAlchemy job store | Switched to in-memory job store |

---

## Running the app

```bash
pip install -r requirements.txt
python3 main.py
```

For Google login: copy `.env.example` → `.env` and fill in `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` from a Google Cloud Console "Desktop App" OAuth client.

Database is stored at `~/Library/Application Support/remindee/remindee.db` (macOS).

---

## Git history (this session)

| Commit | Description |
|---|---|
| `b9d7ce4` | Initial commit (empty repo) |
| `2513d3b` | Full REMINDEE skeleton (26 files, ~2 300 lines) |
| `e3e48a2` | White × orange glassmorphism theme |
| `10116e9` | Calendar scroll area + selectionChanged fix (partial) |
| `a9a32d4` | Root fix: white cells via QPalette, remove month-jumping |
| `c5a9e32` | Orange sidebar + semi-transparent window |
