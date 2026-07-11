"""FIBR-0083 slice 1 — the pure datetime_format formatter. See spec.md.

Qt-core only; no qtbot. The ``"system"`` legs assert **by delegation** to
``QLocale.system()`` / ``systemTimeZoneId()`` so they hold on any runner
locale/zone (no env-pinning, no CI flake); the token / explicit-zone legs are
hermetic — Qt's ``QDate``/``QTime.toString(token)`` renders month/AP names in
English regardless of locale, so their outputs are fixed.
"""

import inspect

from PySide6.QtCore import QDate, QDateTime, QLocale, Qt, QTime, QTimeZone

from finbreak.datetime_format import (
    DATE_PRESETS,
    TIME_PRESETS,
    format_date,
    format_timestamp,
    system_timezone_id,
)

_SHORT = QLocale.FormatType.ShortFormat
_ISO = Qt.DateFormat.ISODate
_ISOMS = Qt.DateFormat.ISODateWithMs

# The D5 sample instant the preset labels are computed against.
_SAMPLE_DATE_ISO = "2026-07-11"
_SAMPLE_DATE = QDate(2026, 7, 11)
_SAMPLE_TIME = QTime(14, 30, 0)

# A representative stored UTC timestamp (Argon2 repos write isoformat() with µs).
_TS = "2026-07-11T06:49:15.506928+00:00"


# ---- INV-2: dates reformatted, never timezone-converted ---------------------


def test_format_date_reformats_without_tz_shift():
    assert format_date("2025-06-19", "yyyy/MM/dd") == "2025/06/19"
    assert format_date("2025-06-19", "dd/MM/yyyy") == "19/06/2025"


def test_format_date_signature_takes_no_timezone_argument():
    assert list(inspect.signature(format_date).parameters) == ["iso", "date_pref"]


# ---- INV-3: timestamps converted UTC -> pinned zone, then formatted ---------


def test_format_timestamp_converts_utc_to_zone_then_formats():
    assert (
        format_timestamp(_TS, "Africa/Johannesburg", "yyyy/MM/dd", "HH:mm")
        == "2026/07/11 08:49"
    )


def test_format_timestamp_parses_instant_without_fractional_seconds():
    assert (
        format_timestamp(
            "2026-07-11T06:49:15+00:00", "Africa/Johannesburg", "yyyy/MM/dd", "HH:mm"
        )
        == "2026/07/11 08:49"
    )


# ---- INV-4: "system" legs assert by delegation (locale/zone independent) -----


def test_format_date_system_delegates_to_system_locale():
    qdate = QDate.fromString(_SAMPLE_DATE_ISO, _ISO)
    expected = QLocale.system().toString(qdate, _SHORT)
    assert format_date(_SAMPLE_DATE_ISO, "system") == expected


def test_format_timestamp_all_system_delegates_to_system_zone_and_locale():
    dt = QDateTime.fromString(_TS, _ISOMS).toTimeZone(
        QTimeZone(QTimeZone.systemTimeZoneId())
    )
    expected = (
        QLocale.system().toString(dt.date(), _SHORT)
        + " "
        + QLocale.system().toString(dt.time(), _SHORT)
    )
    assert format_timestamp(_TS, "system", "system", "system") == expected


# ---- INV-6: fail-safe on bad/unknown pref; raw on unparseable input ----------


def test_bad_date_token_falls_back_to_system():
    assert format_date(_SAMPLE_DATE_ISO, "bogus") == format_date(
        _SAMPLE_DATE_ISO, "system"
    )


def test_bad_zone_falls_back_to_system_zone():
    assert format_timestamp(_TS, "Not/AZone", "system", "system") == format_timestamp(
        _TS, "system", "system", "system"
    )


def test_bad_time_token_falls_back_to_system_half():
    assert format_timestamp(
        _TS, "Africa/Johannesburg", "yyyy/MM/dd", "bogus"
    ) == format_timestamp(_TS, "Africa/Johannesburg", "yyyy/MM/dd", "system")


def test_unparseable_date_returned_raw():
    assert format_date("not-a-date", "yyyy/MM/dd") == "not-a-date"


def test_unparseable_timestamp_returned_raw():
    assert (
        format_timestamp("garbage", "Africa/Johannesburg", "yyyy/MM/dd", "HH:mm")
        == "garbage"
    )


# ---- D5: the two format halves are composed independently -------------------


def test_timestamp_composes_a_system_and_a_token_half_independently():
    dt = QDateTime.fromString(_TS, _ISOMS).toTimeZone(QTimeZone(b"Africa/Johannesburg"))
    # system date half + known time token
    assert format_timestamp(_TS, "Africa/Johannesburg", "system", "HH:mm") == (
        QLocale.system().toString(dt.date(), _SHORT) + " 08:49"
    )
    # known date token + system time half
    assert format_timestamp(_TS, "Africa/Johannesburg", "yyyy/MM/dd", "system") == (
        "2026/07/11 " + QLocale.system().toString(dt.time(), _SHORT)
    )


# ---- D1/D5: preset tables ---------------------------------------------------


def test_date_presets_are_concrete_self_consistent_pairs():
    assert isinstance(DATE_PRESETS, list) and DATE_PRESETS
    for token, label in DATE_PRESETS:
        assert isinstance(token, str) and isinstance(label, str)
        assert token != "system"
        assert _SAMPLE_DATE.toString(token) == label


def test_time_presets_are_concrete_self_consistent_pairs():
    assert isinstance(TIME_PRESETS, list) and TIME_PRESETS
    for token, label in TIME_PRESETS:
        assert isinstance(token, str) and isinstance(label, str)
        assert token != "system"
        assert _SAMPLE_TIME.toString(token) == label


def test_every_date_preset_token_routes_through_format_date():
    for token, _label in DATE_PRESETS:
        assert format_date(_SAMPLE_DATE_ISO, token) == _SAMPLE_DATE.toString(token)


def test_system_timezone_id_decodes_qt_system_zone():
    assert system_timezone_id() == QTimeZone.systemTimeZoneId().data().decode()
