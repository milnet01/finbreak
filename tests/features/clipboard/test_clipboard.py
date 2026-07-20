"""FIBR-0032 — clipboard copy + auto-clear for sensitive values.

Enforces tests/features/clipboard/spec.md. The ``ClipboardAutoClear`` unit legs
(INV-3/4/7) drive the injected-seam helper against the real
``QGuiApplication.clipboard()`` and clear it on teardown; the UI legs
(INV-1/2/6/8) drive ``TransactionsView`` with a **recording fake** clipboard; the
Settings + service legs (INV-5) drive ``SettingsDialog`` / ``AuthService``. Every
vault lives under ``tmp_path``; no network, no real data.
"""

import pytest
from PySide6.QtCore import QObject, QPoint
from PySide6.QtGui import QClipboard, QGuiApplication
from PySide6.QtWidgets import QComboBox, QMenu

from conftest import _PW
from finbreak.errors import VaultLockedError
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.settings import SettingsRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.auth import (
    ALLOWED_CLIPBOARD_CLEAR_SECONDS,
    DEFAULT_CLIPBOARD_CLEAR_SECONDS,
    AuthService,
)
from finbreak.services.categorization import CategorizationService
from finbreak.services.transactions import TransactionService
from finbreak.ui._clipboard import ClipboardAutoClear
from finbreak.ui.settings import SettingsDialog

pytestmark = pytest.mark.features

_COL_AMOUNT = 1
_COL_DESCRIPTION = 3


# --------------------------------------------------------------------------- #
# Fixtures + helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


@pytest.fixture
def clip(qtbot):
    """The real system clipboard, cleared before and after so no UI test pollutes
    it (spec Exit criteria — helper tests restore/clear the global clipboard)."""
    c = QGuiApplication.clipboard()
    c.clear(QClipboard.Mode.Clipboard)
    yield c
    c.clear(QClipboard.Mode.Clipboard)


class RecordingClipboard(ClipboardAutoClear):
    """A ``ClipboardAutoClear`` subclass that only records what ``copy`` receives —
    so the annotated UI legs stay mypy-clean (the injection param is typed
    ``ClipboardAutoClear | None``) without touching the real clipboard. Skips the
    base ``__init__`` (no QClipboard/timer needed) but stays a real ``QObject`` so
    the view can ``setParent`` it."""

    def __init__(self) -> None:
        QObject.__init__(self)
        self.copied: list[str] = []

    def copy(self, text: str) -> None:
        self.copied.append(text)


def _view(service, clipboard=None):
    from finbreak.ui.transactions import TransactionsView

    return TransactionsView(
        TransactionService(service.vault),
        CategorizationService(service.vault),
        clipboard=clipboard,
    )


def _first_account(service):
    return AccountRepository(service.vault.connection).list_all()[0].id


def _add_txn(service, description, amount=-1000, occurred_on="2026-01-05"):
    return TransactionRepository(service.vault.connection).add(
        _first_account(service), occurred_on, amount, description
    )


def _row_of(view, description):
    for r in range(view._table.rowCount()):
        if view._table.item(r, _COL_DESCRIPTION).text() == description:
            return r
    raise AssertionError(f"no visible row for {description!r}")


# --------------------------------------------------------------------------- #
# INV-1 / INV-6 — the copy affordances exist; no secret action is offered
# --------------------------------------------------------------------------- #
def _stub_menu_class(recorded):
    """A ``QMenu`` subclass whose ``exec`` is non-blocking and records the built menu's
    non-separator action texts. Patched over ``transactions.QMenu`` so a test can
    inspect the live-menu contents (the real ``menu.exec()`` blocks the loop, so the
    project's context-menu pattern otherwise drives the named slots directly)."""

    class _StubMenu(QMenu):
        def exec(self, *args, **kwargs):
            recorded.extend(a.text() for a in self.actions() if not a.isSeparator())
            return None

    return _StubMenu


def test_INV1_context_menu_offers_copy_actions(qtbot, service, monkeypatch):
    import finbreak.ui.transactions as txn_mod

    txn = _add_txn(service, "COFFEE SHOP")
    view = _view(service, RecordingClipboard())
    qtbot.addWidget(view)
    view._select_txn(txn)

    recorded: list[str] = []
    monkeypatch.setattr(txn_mod, "QMenu", _stub_menu_class(recorded))
    view._show_context_menu(QPoint(0, 0))
    # The separator (text "") is presentational grouping, not part of the contract.
    assert recorded == ["Copy amount", "Copy description", "Set category…"]


def test_INV1_no_menu_without_selection(qtbot, service, monkeypatch):
    import finbreak.ui.transactions as txn_mod

    _add_txn(service, "COFFEE SHOP")
    view = _view(service, RecordingClipboard())
    qtbot.addWidget(view)

    recorded: list[str] = []
    monkeypatch.setattr(txn_mod, "QMenu", _stub_menu_class(recorded))
    view._show_context_menu(QPoint(0, 0))  # nothing selected
    assert recorded == [], "the menu early-returns with no row selected"


# --------------------------------------------------------------------------- #
# INV-2 — what gets copied (rendered amount cell text / in-memory description)
# --------------------------------------------------------------------------- #
def test_INV2_copy_amount_pushes_rendered_cell_text(qtbot, service):
    txn = _add_txn(service, "COFFEE SHOP", amount=-123456)
    fake = RecordingClipboard()
    view = _view(service, fake)
    qtbot.addWidget(view)
    view._select_txn(txn)

    row = _row_of(view, "COFFEE SHOP")
    expected = view._table.item(row, _COL_AMOUNT).text()
    assert expected, "the rendered amount cell is non-empty"
    view._on_copy_amount()
    assert fake.copied == [expected], "copy-amount pushes the WYSIWYG cell text"


def test_INV2_copy_description_pushes_in_memory_description(qtbot, service):
    txn = _add_txn(service, "COFFEE SHOP")
    fake = RecordingClipboard()
    view = _view(service, fake)
    qtbot.addWidget(view)
    view._select_txn(txn)
    view._on_copy_description()
    assert fake.copied == ["COFFEE SHOP"]


def test_INV2_copy_slots_no_selection_write_nothing(qtbot, service):
    _add_txn(service, "COFFEE SHOP")
    fake = RecordingClipboard()
    view = _view(service, fake)
    qtbot.addWidget(view)
    view._on_copy_amount()  # nothing selected
    view._on_copy_description()
    assert fake.copied == [], "no selection -> nothing copied, no raise"


# --------------------------------------------------------------------------- #
# INV-8 — copy is lock-safe (no vault read), with a positive control
# --------------------------------------------------------------------------- #
def test_INV8_copy_is_lock_safe(qtbot, service):
    txn = _add_txn(service, "COFFEE SHOP", amount=-123456)
    fake = RecordingClipboard()
    view = _view(service, fake)
    qtbot.addWidget(view)
    view._select_txn(txn)
    row = _row_of(view, "COFFEE SHOP")
    expected_amount = view._table.item(row, _COL_AMOUNT).text()

    service.lock()
    # Positive control: a genuine vault read DOES raise in this locked state, so a
    # non-raising copy proves lock-safety rather than an un-locked fixture.
    with pytest.raises(VaultLockedError):
        view._transactions.base_currency()

    view._on_copy_amount()  # must not raise
    view._on_copy_description()  # must not raise
    assert fake.copied == [expected_amount, "COFFEE SHOP"]


# --------------------------------------------------------------------------- #
# INV-3 — auto-clear, guarded (arm + interval, clear-if-ours, real elapse)
# --------------------------------------------------------------------------- #
def test_INV3_copy_arms_timer_with_interval(clip):
    helper = ClipboardAutoClear(clip, seconds_provider=lambda: 30)
    helper.copy("secret")
    assert clip.text() == "secret"
    assert helper._timer.isActive()
    assert helper._timer.interval() == 30_000


def test_INV3_clear_if_ours_clears_unchanged(clip):
    helper = ClipboardAutoClear(clip, seconds_provider=lambda: 30)
    helper.copy("secret")
    helper.clear_if_ours()
    assert clip.text() == "", "an unchanged clipboard is wiped on timeout"


def test_INV3_clear_if_ours_leaves_changed(clip):
    helper = ClipboardAutoClear(clip, seconds_provider=lambda: 30)
    helper.copy("secret")
    clip.setText("user copied this since")
    helper.clear_if_ours()
    assert clip.text() == "user copied this since", "a changed clipboard is left alone"


def test_INV3_real_elapse_auto_clears(qtbot, clip):
    """The timeout -> clear_if_ours wiring actually fires and wipes our value — a
    mis-wired connection would pass every other leg yet never auto-clear."""
    helper = ClipboardAutoClear(clip, seconds_provider=lambda: 1)
    helper.copy("secret")
    with qtbot.waitSignal(helper._timer.timeout, timeout=5000):
        pass
    qtbot.waitUntil(lambda: clip.text() == "", timeout=1000)


# --------------------------------------------------------------------------- #
# INV-4 — configurable + "Never" (live-per-copy provider; 0 arms no timer)
# --------------------------------------------------------------------------- #
def test_INV4_provider_read_live_per_copy(clip):
    seconds = 10
    helper = ClipboardAutoClear(clip, seconds_provider=lambda: seconds)
    helper.copy("a")
    assert helper._timer.interval() == 10_000
    seconds = 30  # a mid-session Settings change
    helper.copy("b")
    assert helper._timer.interval() == 30_000, "the provider is re-read each copy"


def test_INV4_never_arms_no_timer(clip):
    helper = ClipboardAutoClear(clip, seconds_provider=lambda: 0)
    helper.copy("secret")
    assert clip.text() == "secret", "0 == Never still copies the value"
    assert not helper._timer.isActive(), "no clear timer is armed at Never"


# --------------------------------------------------------------------------- #
# INV-7 — clipboard mode only (Selection buffer untouched) + source backstop
# --------------------------------------------------------------------------- #
def test_INV7_selection_buffer_untouched(clip):
    if not clip.supportsSelection():
        pytest.skip("no X11 Selection buffer on this platform (offscreen CI)")
    clip.setText("sentinel", QClipboard.Mode.Selection)
    helper = ClipboardAutoClear(clip, seconds_provider=lambda: 30)
    helper.copy("secret")
    helper.clear_if_ours()
    assert clip.text(QClipboard.Mode.Selection) == "sentinel", (
        "the middle-click Selection buffer is never written or cleared (D6)"
    )


def test_INV7_source_never_references_selection():
    """CI-gated backstop: the Selection-buffer runtime leg skips under offscreen CI,
    so a static check guarantees ``_clipboard.py`` never touches Selection mode."""
    from pathlib import Path

    import finbreak.ui._clipboard as mod

    source = Path(mod.__file__).read_text()
    assert "Selection" not in source, (
        "_clipboard.py must never reference QClipboard.Selection (D6)"
    )


# --------------------------------------------------------------------------- #
# INV-5 — AuthService getter/setter (the clauses the combo can't reach)
# --------------------------------------------------------------------------- #
def test_INV5_getter_default_when_absent(service):
    assert service.clipboard_clear_seconds() == DEFAULT_CLIPBOARD_CLEAR_SECONDS == 30


def test_INV5_getter_reads_stored_valid(service):
    SettingsRepository(service.vault.connection).set("clipboard_clear_seconds", "10")
    assert service.clipboard_clear_seconds() == 10


def test_INV5_getter_non_int_falls_back(service):
    SettingsRepository(service.vault.connection).set("clipboard_clear_seconds", "abc")
    assert service.clipboard_clear_seconds() == 30


def test_INV5_getter_out_of_set_falls_back(service):
    SettingsRepository(service.vault.connection).set("clipboard_clear_seconds", "99")
    assert service.clipboard_clear_seconds() == 30


def test_INV5_setter_rejects_out_of_set(service):
    before = service.clipboard_clear_seconds()
    with pytest.raises(ValueError):
        service.set_clipboard_clear_seconds(99)  # not in ALLOWED
    row = SettingsRepository(service.vault.connection).get("clipboard_clear_seconds")
    assert row is None, "no write on a rejected value"
    assert service.clipboard_clear_seconds() == before


def test_INV5_setter_persists_valid(service):
    service.set_clipboard_clear_seconds(60)
    assert service.clipboard_clear_seconds() == 60


# --------------------------------------------------------------------------- #
# INV-5 — the SettingsDialog combo (preselect, allowed set, Save persists)
# --------------------------------------------------------------------------- #
def _clip_combo(dialog):
    combo = dialog.findChild(QComboBox, "settings_clipboard_clear")
    assert combo is not None
    return combo


def test_INV5_settings_combo_preselects_stored(qtbot, service):
    service.set_clipboard_clear_seconds(60)
    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    assert _clip_combo(dialog).currentData() == 60


def test_INV5_settings_combo_offers_allowed(qtbot, service):
    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    combo = _clip_combo(dialog)
    assert {combo.itemData(i) for i in range(combo.count())} == set(
        ALLOWED_CLIPBOARD_CLEAR_SECONDS
    )


def test_INV5_settings_save_persists(qtbot, service):
    dialog = SettingsDialog(service, "ZAR")
    qtbot.addWidget(dialog)
    combo = _clip_combo(dialog)
    combo.setCurrentIndex(combo.findData(10))
    dialog._on_save()
    assert service.clipboard_clear_seconds() == 10
