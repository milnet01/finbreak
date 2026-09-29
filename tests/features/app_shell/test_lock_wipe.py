"""FIBR-0367 audit row 30 — a lock wipes what EVERY screen holds, at lock time.

`_clear_decrypted_rows` empties item models and asks each widget for
`clear_rows`. Tables were covered; the Transfers, Recurring and Home tabs, the
import wizard and its batch review kept their decrypted values in Python lists,
labels and charts for as long as `deleteLater` is held back — the whole time a
nested modal loop is open at auto-lock (FIBR-0216). The audit found it by
scanning for marker data after a lock, and these tests do the same: they assert
the OUTCOME (no marker anywhere the dead workspace can still reach), not a list
of attributes, so a tab or field added later is covered without editing them.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtCharts import QChartView
from PySide6.QtCore import QAbstractItemModel, QModelIndex, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from conftest import _PW
from finbreak.models import ColumnMapping
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.import_ import ImportService
from finbreak.services.recurring import RecurringService
from finbreak.services.transfer_detection import TransferDetectionService
from finbreak.ui.main_window import MainWindow

pytestmark = pytest.mark.features

MARK = "ZZMARK"
# The recurring amount, in minor units. Its digits appear in every figure the
# Home tab derives from it (net, totals, donut, recurring tile), none of which
# carries the text marker.
DIGITS = "987654"
_NON_DIGIT = re.compile(r"\D")


@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    yield svc
    svc.lock()


def _add(svc: AuthService, account_id: int, when: date, minor: int, desc: str) -> int:
    return TransactionRepository(svc.vault.connection).add(
        account_id, when.isoformat(), minor, desc
    )


def _seed(svc: AuthService) -> None:
    """Marker data every data tab shows: a recurring series (one confirmed, one
    suggested), a transfer pair confirmed and one suggested, and an account whose
    name carries the marker."""
    today = date.today()
    first = AccountRepository(svc.vault.connection).list_all()[0].id
    other = AccountService(svc.vault).add_account(f"{MARK} Savings", "savings").id
    for k in range(4):
        _add(svc, first, today - timedelta(days=30 * k), -int(DIGITS), f"{MARK} Stream")
        _add(svc, first, today - timedelta(days=30 * k + 2), -4321, f"{MARK} Gym")
    recurring = RecurringService(svc.vault)
    stream = next(i for i in recurring.candidates(today) if "stream" in i.merchant_key)
    recurring.confirm(stream.direction, stream.merchant_key)
    old = today - timedelta(days=45)
    debit = _add(svc, first, old, -50000, f"{MARK} to savings")
    credit = _add(svc, other, old, 50000, f"{MARK} from cheque")
    TransferDetectionService(svc.vault).confirm(debit, credit)
    older = today - timedelta(days=75)
    _add(svc, first, older, -70000, f"{MARK} to savings again")
    _add(svc, other, older, 70000, f"{MARK} from cheque again")


def _holds_marker(value: str) -> bool:
    return MARK in value or DIGITS in _NON_DIGIT.sub("", value)


def _scan_python(obj, path: str, hits: list[str], seen: set[int], depth: int = 0):
    """Every string or number reachable from `obj` through plain Python data.

    Stops at a QObject (the widget walk reaches those itself, and following
    one leads out of the workspace), and at modules, classes and callables."""
    if depth > 8:
        return
    if isinstance(obj, str):
        if _holds_marker(obj):
            hits.append(path)
        return
    if isinstance(obj, bool) or obj is None or isinstance(obj, Enum):
        return
    if isinstance(obj, (int, Decimal, float)):
        if DIGITS in _NON_DIGIT.sub("", str(obj)):
            hits.append(path)
        return
    if isinstance(obj, (bytes, bytearray)):
        if MARK.encode() in obj:
            hits.append(path)
        return
    if isinstance(obj, (QObject, type, Path)) or callable(obj):
        return
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, dict):
        for key, value in obj.items():
            _scan_python(key, f"{path}[key]", hits, seen, depth + 1)
            _scan_python(value, f"{path}[{key!r}]", hits, seen, depth + 1)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for i, value in enumerate(obj):
            _scan_python(value, f"{path}[{i}]", hits, seen, depth + 1)
    elif dataclasses.is_dataclass(obj):
        for field in dataclasses.fields(obj):
            value = getattr(obj, field.name, None)
            _scan_python(value, f"{path}.{field.name}", hits, seen, depth + 1)
    elif hasattr(obj, "__dict__"):
        for name, value in vars(obj).items():
            _scan_python(value, f"{path}.{name}", hits, seen, depth + 1)


def _model_texts(model: QAbstractItemModel, parent: QModelIndex | None = None):
    parent = parent if parent is not None else QModelIndex()
    for row in range(model.rowCount(parent)):
        for col in range(max(model.columnCount(parent), 1)):
            index = model.index(row, col, parent)
            for role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
                value = model.data(index, role)
                if value is not None:
                    yield str(value)
            if col == 0:
                yield from _model_texts(model, index)


def _chart_texts(view: QChartView):
    chart = view.chart()
    if chart is None:
        return
    yield chart.title()
    for series in chart.series():
        yield series.name()
        for part in ("slices", "barSets"):
            for item in getattr(series, part, lambda: [])():
                yield item.label()
    for axis in chart.axes():
        yield axis.titleText()
        yield from getattr(axis, "categories", lambda: [])()


def _survivors(root: QWidget) -> list[str]:
    """Where the marker is still held under `root`: Python attributes, item
    models, combo boxes, labels, text fields and charts."""
    hits: list[str] = []
    seen: set[int] = set()
    for widget in [root, *root.findChildren(QWidget)]:
        name = widget.objectName() or type(widget).__name__
        # The widget itself is a QObject, which _scan_python stops at; its own
        # Python attributes are where a tab keeps its parallel lists.
        for attr, value in getattr(widget, "__dict__", {}).items():
            _scan_python(value, f"{name}.{attr}", hits, seen)
        texts: list[str] = []
        if isinstance(widget, QLabel):
            texts.append(widget.text())
        elif isinstance(widget, QLineEdit):
            texts.append(widget.text())
        elif isinstance(widget, (QPlainTextEdit, QTextEdit)):
            texts.append(widget.toPlainText())
        elif isinstance(widget, QComboBox):
            texts.extend(widget.itemText(i) for i in range(widget.count()))
        elif isinstance(widget, QChartView):
            texts.extend(_chart_texts(widget))
        if isinstance(widget, QAbstractItemView) and widget.model() is not None:
            texts.extend(_model_texts(widget.model()))
        hits.extend(f"{name}: {t!r}" for t in texts if _holds_marker(t))
    return sorted(set(hits))


def _unlocked(qtbot, service) -> MainWindow:
    service.first_run(bytearray(_PW), "ZAR")
    _seed(service)
    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    return window


def test_row30_lock_leaves_no_decrypted_value_in_any_tab(qtbot, service):
    window = _unlocked(qtbot, service)
    workspace = window.centralWidget().currentWidget()
    for index in range(workspace.count()):  # every tab refreshes on activation
        workspace.setCurrentIndex(index)
    for tab in ("tab_home", "tab_transfers", "tab_recurring", "tab_transactions"):
        assert _survivors(workspace.findChild(QWidget, tab)), (
            f"precondition: {tab} must show marker data before the lock, or this "
            "test asserts nothing about it."
        )

    service._on_idle_timeout()  # no deferred-delete pump — the window under test

    assert shiboken6.isValid(workspace), "the deferred-delete window is the subject"
    survived = _survivors(workspace)
    assert not survived, (
        "decrypted values outlived the lock in the still-alive workspace:\n  "
        + "\n  ".join(survived)
    )


_HEADER = ["Date", "Details", "Amount"]
_MAPPING = ColumnMapping("Date", "Details", "Amount", None, None, "%Y-%m-%d", False)


def _statement(tmp_path: Path, name: str) -> str:
    amount = f"-{DIGITS[:4]}.{DIGITS[4:]}"
    body = ",".join(_HEADER) + f"\n2026-07-01,{MARK} coffee,{amount}\n"
    (tmp_path / name).write_text(body, encoding="utf-8")
    return str(tmp_path / name)


@pytest.mark.parametrize("batch", [False, True], ids=["one-file", "batch-review"])
def test_row30_lock_wipe_reaches_the_import_wizard(qtbot, service, tmp_path, batch):
    """The wizard is the live widget while it is open, so `_clear_live` hands it
    to the same wipe. Its parsed statement — and, for a batch, the review
    step's file list — must go too."""
    window = _unlocked(qtbot, service)
    window._open_import()
    wizard = window._live
    if batch:
        # A saved layout lets both files through to the review step unasked.
        ImportService(service.vault).save_profile("layout", _HEADER, _MAPPING)
        wizard._select_files(
            [_statement(tmp_path, "a.csv"), _statement(tmp_path, "b.csv")]
        )
        qtbot.waitUntil(lambda: len(wizard._batch_review._files) == 2, timeout=5000)
    else:
        wizard._select_file(_statement(tmp_path, "a.csv"))
    before = _survivors(wizard)
    assert before, "precondition: the wizard must hold the parsed statement"

    service._on_idle_timeout()

    assert shiboken6.isValid(wizard), "the deferred-delete window is the subject"
    survived = _survivors(wizard)
    assert not survived, (
        "the import wizard kept decrypted statement data after the lock:\n  "
        + "\n  ".join(survived)
    )
