"""Pure display-time formatting of stored UTC/ISO strings (FIBR-0083).

Qt-core only (no Qt Widgets), so it is unit-testable without a ``qtbot``. Two
entry points turn a stored string into a display string under the user's prefs:

* ``format_date(iso, date_pref)`` — reformats a calendar date. **No timezone**
  parameter by design (INV-2): a statement date is a calendar day, never shifted.
* ``format_timestamp(iso_utc, tz_pref, date_pref, time_pref)`` — converts a UTC
  instant into the user's zone, then formats the date and time halves
  independently (INV-3 / D5).

Each pref is either a concrete value (an IANA zone id, or a Qt format token) or
the sentinel ``"system"`` meaning *resolve dynamically at display time* so the
app follows the OS (D4). A bad/unknown pref falls back to the system default,
and an unparseable input string is returned raw — never an exception to the UI
(INV-6). The date format tokens (``yyyy/MM/dd`` …) are the same ones the
FIBR-0047 date pickers use, so input and display stay consistent (D1).
"""

from PySide6.QtCore import QDate, QDateTime, QLocale, Qt, QTime, QTimeZone

_SHORT = QLocale.FormatType.ShortFormat

# Concrete (token, sample_label) presets — the UI prepends a dynamic "System
# default (<detected>)" item that maps to the "system" sentinel (D5), so these
# tables hold only pinned tokens. Labels are the D5 sample instant rendered by
# each token (Qt renders MMM/MMMM/AP names in English regardless of locale).
DATE_PRESETS: list[tuple[str, str]] = [
    ("yyyy-MM-dd", "2026-07-11"),
    ("yyyy/MM/dd", "2026/07/11"),
    ("dd/MM/yyyy", "11/07/2026"),
    ("MM/dd/yyyy", "07/11/2026"),
    ("dd MMM yyyy", "11 Jul 2026"),
    ("dd MMMM yyyy", "11 July 2026"),
    ("MMM dd, yyyy", "Jul 11, 2026"),
]
TIME_PRESETS: list[tuple[str, str]] = [
    ("HH:mm", "14:30"),
    ("HH:mm:ss", "14:30:00"),
    ("h:mm AP", "2:30 PM"),
]

_DATE_TOKENS = frozenset(token for token, _ in DATE_PRESETS)
_TIME_TOKENS = frozenset(token for token, _ in TIME_PRESETS)


def system_timezone_id() -> str:
    """The system zone id as ``str`` — for the **combo label** only. Zone
    *construction* uses the ``QByteArray`` id directly (see ``_resolve_zone``);
    this decodes it for display."""
    return bytes(QTimeZone.systemTimeZoneId().data()).decode()


def _resolve_zone(tz_pref: str) -> QTimeZone:
    """The pinned zone, or the system zone for ``"system"`` / an invalid id."""
    if tz_pref != "system":
        zone = QTimeZone(tz_pref.encode())
        if zone.isValid():
            return zone
    return QTimeZone(QTimeZone.systemTimeZoneId())


def _fmt_date_part(qdate: QDate, date_pref: str) -> str:
    """Three-way date formatting: a known token renders via that token; anything
    else (``"system"`` or an unknown token) via the system locale (INV-6)."""
    if date_pref in _DATE_TOKENS:
        return qdate.toString(date_pref)
    return QLocale.system().toString(qdate, _SHORT)


def _fmt_time_part(qtime: QTime, time_pref: str) -> str:
    """Three-way time formatting, mirroring ``_fmt_date_part``."""
    if time_pref in _TIME_TOKENS:
        return qtime.toString(time_pref)
    return QLocale.system().toString(qtime, _SHORT)


def format_date(iso: str, date_pref: str) -> str:
    """Reformat a stored ISO calendar date. Unparseable → ``iso`` unchanged."""
    qdate = QDate.fromString(iso, Qt.DateFormat.ISODate)
    if not qdate.isValid():
        return iso
    return _fmt_date_part(qdate, date_pref)


def format_timestamp(iso_utc: str, tz_pref: str, date_pref: str, time_pref: str) -> str:
    """Convert a stored UTC instant into the user's zone, then format the date
    and time halves independently and join with a space. Unparseable →
    ``iso_utc`` unchanged."""
    dt = QDateTime.fromString(iso_utc, Qt.DateFormat.ISODateWithMs)
    if not dt.isValid():
        return iso_utc
    local = dt.toTimeZone(_resolve_zone(tz_pref))
    return (
        _fmt_date_part(local.date(), date_pref)
        + " "
        + _fmt_time_part(local.time(), time_pref)
    )
