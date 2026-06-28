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
│   │   ├── reminder_card.py       # ReminderCard widget + full card art system
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

## Card art system (`reminder_card.py`)

Every card gets unique deterministic art driven by a 31-bit seed:

```python
seed = (reminder.id or abs(hash(reminder.name))) & 0x7FFFFFFF
```

Same reminder ID → same seed → same art every time. Three derived values:

| Variable | Formula | Purpose |
|---|---|---|
| `_is_dark` | `(seed * 11 + 5) % 5 == 0` | ~20% of cards get dark backgrounds |
| palette | `_SCHEMES[seed % 20]` | Which of the 20 colour schemes |
| style | `(seed * 17 + 5) % 8` | Which of the 8 structural art styles |

### 20 palettes (`_SCHEMES`)
All 3–5 `QColor` entries. A-colour luminance ≥ 90 enforced so light cards stay vivid (not muddy). Examples: Neon Electric, Fire Drama, Cool Futuristic, Sunset Aurora, Jewel Tones, Candy, Tropical, Midnight Cobalt, Acid Punk, Cyberpunk Night, Ink & Gold, …

### 8 art styles (`_STYLES`)
Each function takes `(painter, rect, rng, palette)`:

| Index | Name | Visual |
|---|---|---|
| 0 | `_style_mega_blob` | Off-centre radial blob + 2 accent blobs |
| 1 | `_style_parallel_lines` | 5–9 thick diagonal stripes |
| 2 | `_style_big_rect` | 3 nested gradient rectangles |
| 3 | `_style_corner_wedge` | Gradient wedge from a corner |
| 4 | `_style_triangle` | Fan of triangles from one edge |
| 5 | `_style_diagonal_split` | 3-zone diagonal A + accent stripe + B |
| 6 | `_style_dot_field` | Grid of radial-gradient circles |
| 7 | `_style_ring` | Concentric colour rings |

### Dark cards
- Base fill from `_DARK_BASES` (20 near-black tinted colours, one per palette)
- `_draw_base` gradient skipped (would be invisible on dark)
- Card text, badges, and buttons receive per-widget `setStyleSheet()` overrides to warm cream (`rgba(238,222,205,0.97)` primary, `rgba(190,165,140,0.90)` secondary)
- Uses `setFrameShape(QFrame.Shape.NoFrame)` + `setAutoFillBackground(False)` — all painting is done in custom `paintEvent` to avoid Qt auto-fill overriding the art

### Veil + grain
- Light cards: `QColor(255, 255, 255, 72)` white veil over art for readability
- Dark cards: `QColor(0, 0, 0, 55)` black veil
- ~40% of cards also get 250–380 film-grain dots (`_draw_grain`) for texture

---

## Notification bubble (`notification_service.py` — `ActionBubble`)

A 430 px wide `QDialog` with `FramelessWindowHint + WA_TranslucentBackground`.

### Animation
- **Slide-in**: `QPropertyAnimation` on `b"pos"` from below-screen to bottom-right corner, 480 ms `OutCubic` easing
- **Border rotation**: 50 fps `QTimer` increments `self._phase` by 1.4°/tick → full rotation in ~4.3 s
- **Breathing veil**: `sin(self._pulse)` modulates veil opacity ±14 alpha units for a gentle breathing effect

### Painting (layered)
1. Animated `QConicalGradient` border ring (outer path `subtracted` inner path = donut shape)
2. Opaque base fill via `CompositionMode_Source` (required to write solid RGBA on transparent window)
3. Card art — `_draw_base` (light only) + `_STYLES[style]` — **same seed as the matching card**
4. Frosted breathing veil (120–134 alpha dark / 150–164 alpha light)

The notification art always matches the card it was triggered by.

### Buttons
- **Done**: marks `is_done = True`, removes from scheduler, closes
- **Snooze 30m**: sets `snooze_until` + `next_trigger` to +30 min, reschedules, closes
- **Dismiss (✕)**: closes only
- `closeEvent` stops the animation timer and fires `on_close_cb` to remove from active-bubbles dict

---

## Edit Reminder dialog (`reminder_dialog.py`)

### Visual matching
In edit mode the dialog computes the same seed/palette/style/dark as the card:

```python
seed          = reminder.id & 0x7FFFFFFF
self._art_dark    = (seed * 11 + 5) % 5 == 0
self._art_style   = (seed * 17 + 5) % len(_STYLES)
self._art_palette = _SCHEMES[seed % len(_SCHEMES)]
```

`paintEvent` draws the same base + style + heavier veil (alpha 148 dark / 168 light) so the dialog always looks like an enlarged version of the card being edited.

### Dark-mode form widgets
When `_art_dark` is `True`, every widget gets a per-widget `setStyleSheet()` override:
- Labels: `_label_ss()` → warm cream dimmed text
- Inputs / QTextEdit / QTimeEdit: `_input_ss()` → translucent white background, cream text
- QComboBox: dark background + dark dropdown popup via full `QComboBox { … } QComboBox QAbstractItemView { … }` string
- Cancel button: glassy white-tinted style
- Error label: `rgba(255,120,100,0.95)` (visible red on dark)

### Keyboard behaviour
- `QLineEdit.returnPressed → _save`
- `save_btn.setDefault(True)` + `setAutoDefault(True)`
- `cancel_btn.setAutoDefault(False)` — must not steal Enter
- `keyPressEvent` override: Enter saves (unless focus is in `QTextEdit`, where it inserts newline); Esc rejects

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

## Bugs fixed

| Bug | Root cause | Fix |
|---|---|---|
| Black calendar cells | `WA_TranslucentBackground` makes `QAbstractItemView` ignore QSS `background` | `apply_calendar_palette()` via `QPalette.Base` |
| Calendar month jumping | `selectionChanged` fires on prev/next arrow clicks, not just date clicks | Removed `selectionChanged`; only `clicked` updates the reminder list |
| Dialog calendar clipped | Animation target 370 px too small for `QCalendarWidget` (~250 px grid + labels) | Raised to 420 px + `adjustSize()` on animation finish |
| Calendar view no scroll | Reminder cards below calendar overflowed off-screen | Wrapped in `QScrollArea` |
| APScheduler pickle error | Bound method referencing `QObject` can't be pickled by SQLAlchemy job store | Switched to in-memory job store |
| Card art style distribution | `(seed >> 3) % 8` made IDs 1–7 all map to style 0 | Changed to `(seed * 17 + 5) % 8` — uniform distribution |
| Crash after `p.end()` | Code used `QPainter` after manually calling `p.end()` | Removed `p.end()` — Qt handles cleanup when painter goes out of scope |
| Art bleeding into card corners | No clip path before drawing | Added `QPainterPath.addRoundedRect` clip in `paintEvent` |
| Double border on cards | `setFrameShape(StyledPanel)` draws a platform border on top of custom painted border | Changed to `setFrameShape(QFrame.Shape.NoFrame)` |
| Concentric ring formula broken | `r = max_r - i * ring_w * 0.05` was non-monotonic | Fixed to `outer = max_r - i * band; inner = max(0, outer - (band - gap))` |
| Parallel lines drawn horizontal | Style function used horizontal stripe logic | Rewrote using slope-based `drawLine` for true diagonal stripes |
| Dark palettes muddy on light cards | A-colours like `QColor(139,0,0)` (lum = 20) wash out | All A-colours now have luminance ≥ 90 |
| Dialog not matching card art | Dialog ignored `_is_dark` and always drew a light veil | Dialog now mirrors exact card seed logic: `_art_dark`, `_art_style`, correct veil and text colours |

---

## Running the app

```bash
pip install -r requirements.txt
python3 main.py
```

For Google login: copy `.env.example` → `.env` and fill in `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` from a Google Cloud Console "Desktop App" OAuth client.

Database is stored at `~/Library/Application Support/remindee/remindee.db` (macOS).

---

## Git history

| Commit | Branch | Description |
|---|---|---|
| `b9d7ce4` | main | Initial commit (empty repo) |
| `2513d3b` | main | Full REMINDEE skeleton (26 files, ~2 300 lines) |
| `e3e48a2` | main | White × orange glassmorphism theme |
| `10116e9` | main | Calendar scroll area + selectionChanged fix |
| `a9a32d4` | main | White cells via QPalette, remove month-jumping |
| `c5a9e32` | main | Orange sidebar + semi-transparent window |
| `0b57b64` | feature/varied-card-art | 8 geometric card art primitives + glassmorphism |
| `0f0fb67` | feature/varied-card-art | Bold distinct card art fixes (clip, border, rings, lines) |
| `77f55a3` | feature/varied-card-art | 20 vivid palettes, grain, dark cards (~20%) |
| `7b305b2` | feature/varied-card-art | Animated glassmorphic notification bubble |
| `fb230cf` | feature/varied-card-art | Gradient background + Enter-to-save for ReminderDialog |
| `5c919da` | feature/varied-card-art | Dialog art matches card exactly (dark mode fix) |
| `81eec94` | feature/varied-card-art | Notification inner background uses card art system |
