"""Shared builders for the FIBR-0083 timezone / date / time preference combos.

``SettingsDialog`` and ``FirstRunDialog`` present the identical three controls,
so this is their single definition (coding.md § 1.3). Pure Qt-Widgets glue over
the pure formatter in :mod:`finbreak.datetime_format`.

The one translatable string — the ``System default (<detected>)`` label — stays
in each *dialog* as a literal ``self.tr(...)`` call (so ``lupdate`` can extract
it, INV-7) and is passed in here already rendered; everything below is data
(zone ids, format samples), shown verbatim and never ``tr()``-wrapped.
"""

from __future__ import annotations

from PySide6.QtCore import QDate, QLocale, QTime, QTimeZone
from PySide6.QtWidgets import QComboBox

from finbreak.datetime_format import DATE_PRESETS, TIME_PRESETS
from finbreak.services.auth import DATETIME_SYSTEM, DateTimePrefs
from finbreak.ui._widgets import select_combo_data

# The fixed preview instant every combo row renders — including the System row,
# so its preview lines up with the preset rows below it (D5). Same instant the
# preset sample_labels use.
_SAMPLE_DATE = QDate(2026, 7, 11)
_SAMPLE_TIME = QTime(14, 30, 0)
_SHORT = QLocale.FormatType.ShortFormat


def system_date_sample_label() -> str:
    """The detected system-locale rendering of the sample date, for the System
    default row's ``(<detected>)`` (e.g. ``7/11/26``)."""
    return QLocale.system().toString(_SAMPLE_DATE, _SHORT)


def system_time_sample_label() -> str:
    """The detected system-locale rendering of the sample time (e.g. ``2:30 PM``)."""
    return QLocale.system().toString(_SAMPLE_TIME, _SHORT)


def _available_zone_ids() -> list[str]:
    return sorted(bytes(z.data()).decode() for z in QTimeZone.availableTimeZoneIds())


def populate_datetime_combos(
    tz: QComboBox,
    date: QComboBox,
    time: QComboBox,
    *,
    system_tz_label: str,
    system_date_label: str,
    system_time_label: str,
    current: DateTimePrefs,
) -> None:
    """Fill the three combos with a prepended System-default item (mapped to the
    ``"system"`` sentinel) then the concrete choices, and preselect ``current``.
    Every item's ``userData`` is the stored token (D5). Only the timezone combo
    is editable — its completer gives type-to-search over the host's zone ids
    (the count follows the platform's tzdata, so it is not fixed), with
    ``NoInsert`` so free text can't create a new item. A pinned id this host does
    not enumerate is added anyway, so it round-trips rather than degrading."""
    tz.addItem(system_tz_label, DATETIME_SYSTEM)
    available = _available_zone_ids()
    if current.timezone != DATETIME_SYSTEM and current.timezone not in available:
        # The stored id is pinned but this host's tzdata does not enumerate it —
        # a vault is portable (backup/restore, or the same person on two
        # machines) and zone ids really are renamed between tzdata releases
        # (Europe/Kiev -> Europe/Kyiv, Asia/Rangoon -> Asia/Yangon). Offer it
        # anyway, so the preselect below can find it.
        #
        # Without this the combo rests on item 0 (System): `select_combo_data`
        # leaves the selection unchanged on a miss, and `read_datetime_prefs` is
        # unguarded, so the next Save — of ANY setting, since `_on_save` writes
        # all of them — silently repoints every timestamp at the machine's local
        # zone. That is a wrong-day render for a transaction near midnight, from
        # a preference the user never touched.
        available = [current.timezone, *available]
    for zone_id in available:
        tz.addItem(zone_id, zone_id)  # label == data: the id, shown verbatim
    tz.setEditable(True)
    tz.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    select_combo_data(tz, current.timezone)

    date.addItem(system_date_label, DATETIME_SYSTEM)
    for token, label in DATE_PRESETS:
        date.addItem(label, token)
    select_combo_data(date, current.date_format)

    time.addItem(system_time_label, DATETIME_SYSTEM)
    for token, label in TIME_PRESETS:
        time.addItem(label, token)
    select_combo_data(time, current.time_format)


def _read_token(combo: QComboBox) -> str:
    """A non-editable combo's stored token — always a ``str`` (a preset token or
    the sentinel); a defensive non-``str`` degrades to ``"system"``."""
    data = combo.currentData()
    return data if isinstance(data, str) else DATETIME_SYSTEM


def _read_timezone(combo: QComboBox) -> str:
    """The timezone the FIELD is showing — which is not always the selected item.

    On an editable combo, typing text that matches no item leaves ``currentIndex``
    (and so ``currentData()``) on the PREVIOUS one while the field displays what
    was typed. Measured: select Africa/Johannesburg, type ``Europe/Kyiv``, and
    ``currentData()`` still reads ``Africa/Johannesburg``.

    So the old guard, which keyed on ``currentData()`` not being a ``str``, could
    never fire: a free-typed zone this host does not enumerate silently persisted
    the zone the user had just replaced, with the field showing the new one. Since
    the pinned zone decides what "today" is, that is a wrong-day render from a
    preference the user believes they changed (FIBR-0327).

    The text decides whenever it disagrees with the selected item, honouring any
    valid id (D4 "override to pin"); only text that names no zone at all degrades
    to ``"system"``, so the field never persists a non-``str``.
    """
    index = combo.currentIndex()
    typed = combo.currentText().strip()
    if index >= 0 and typed == combo.itemText(index):
        data = combo.itemData(index)
        return data if isinstance(data, str) else DATETIME_SYSTEM
    if QTimeZone(typed.encode()).isValid():
        return typed
    return DATETIME_SYSTEM


def read_datetime_prefs(
    tz: QComboBox, date: QComboBox, time: QComboBox
) -> DateTimePrefs:
    """Build the ``DateTimePrefs`` to persist from the three combos' current
    selections (the D3/D4 persist rule)."""
    return DateTimePrefs(
        timezone=_read_timezone(tz),
        date_format=_read_token(date),
        time_format=_read_token(time),
    )
