"""FIBR-0065 INV-1 / INV-4 — the crash-class regression guard + the no-leak gate.

No content-widget pop-up may block the event loop via ``dialog.exec()``: the H-B
crash (auto-lock during a nested ``exec()`` loop → deleted-C++-object
``RuntimeError``) can only exist where a blocking ``exec()`` does. A source grep
over the four converted files asserts the only surviving ``.exec(`` is the Home
context ``QMenu`` (a pop-up menu, not a modal dialog — out of scope).

INV-4 locks the other half of the bargain: dropping ``exec()`` means the dialog is
no longer owned by a nested loop, so ``show_modal`` must free it itself on a
*normal* close. Every other ``shiboken6.isValid`` assertion in the suite is
lock-driven; these two cover the accept and reject paths.
"""

from __future__ import annotations

import re
from pathlib import Path

import shiboken6
from PySide6.QtWidgets import QDialog, QWidget

import finbreak.ui as ui_pkg
from conftest import _pump_deferred_delete
from finbreak.ui.modal import show_modal

_UI_DIR = Path(ui_pkg.__file__).parent
# Five members since FIBR-0085: `import_batch.py` is a content widget like the
# rest, and a new UI module sits OUTSIDE this guard until it is named here — a
# guard that silently does not cover new code is worse than no guard.
_FILES = (
    "home.py",
    "rules.py",
    "statements.py",
    "import_wizard.py",
    "import_batch.py",
)
# Two tokens, not one (FIBR-0085 INV-6). `.exec(` catches `dialog.exec()`, but a
# modal `QProgressDialog` driven by a bare `QApplication.processEvents()` loop
# carries no `.exec(` token at all — it would pass the original grep untouched
# while re-entering the event loop exactly as FIBR-0065 forbids. The batch
# import is the first feature with a long-running loop and therefore the first
# with a reason to reach for that pattern, so the guard names it too. It binds
# the whole `_FILES` set, which tightens it for the four older members free.
_EXEC = re.compile(r"\.exec\(|processEvents")

# -- INV-7 (coverage guard) --------------------------------------------------- #
#
# _FILES above is hand-maintained, and the INV-1 grep only ever looks at its five
# names. A UI module created and never added to it is not a failing case for
# INV-1 — it is an ABSENT one: the grep has nothing to iterate, so it passes
# while covering nothing (FIBR-0277). Every module under ``ui/`` that is not in
# _FILES must have a written reason here for why INV-1 does not need to cover
# it, so a new module silently falls into neither and turns this test red
# instead of shrinking INV-1's coverage unnoticed.
_NOT_CONTENT_WIDGETS: dict[str, str] = {
    # -- QDialog subclasses shown non-blocking (show_modal or main_window's
    #    tracked _open_dialog), never .exec()-ed by the module that defines them --
    "account_create.py": (
        "CreateAccountDialog: a QDialog, but shown non-blocking via show_modal "
        "from the import wizard's no_match outcome (import_wizard.py:677) — no "
        ".exec(/processEvents token in this file."
    ),
    "account_picker.py": (
        "AccountPickerDialog: a QDialog, shown non-blocking via show_modal from "
        "statements.py's Change-account action (statements.py:198) — no banned "
        "token here."
    ),
    "alerts_dialog.py": (
        "AlertsDialog: a QDialog; its own docstring says it is opened through "
        "the shell's tracked _open_dialog path — 'never exec()' — and this file "
        "contains no banned token."
    ),
    "backup_export.py": (
        "BackupExportDialog: a QDialog, shown non-blocking via main_window's "
        "tracked _open_dialog (main_window.py:1004); it only collects a "
        "password, the shell does the actual export separately. No banned "
        "token here."
    ),
    "backup_restore.py": (
        "BackupRestoreDialog: a QDialog, shown non-blocking via main_window's "
        "tracked _open_dialog (main_window.py:1182), same pattern as "
        "backup_export.py. No banned token here."
    ),
    "backup_verify.py": (
        "BackupVerifyDialog: a QDialog, shown non-blocking via main_window's "
        "tracked _open_dialog (main_window.py:1058). No banned token here."
    ),
    "category_picker.py": (
        "CategoryPickerDialog: a QDialog, shown non-blocking via show_modal "
        "from transactions.py's Set-category action (transactions.py:407-413). "
        "No banned token here."
    ),
    "export_dialog.py": (
        "ExportDialog: a QDialog; its own docstring states it outright — "
        "'shown non-blocking, never exec()-ed (FIBR-0065 INV-1)'. No banned "
        "token here."
    ),
    "first_run.py": (
        "FirstRunDialog: a QDialog, shown non-blocking via main_window's "
        "tracked _open_dialog (main_window.py:636); its own docstring calls it "
        "a 'non-blocking application-modal QDialog'. No banned token here."
    ),
    "manual_entry.py": (
        "ManualEntryDialog: a QDialog; its own docstring says it is 'Shown "
        "non-blocking (setModal(True) + show())'. No banned token here."
    ),
    "password_dialog.py": (
        "PasswordDialog: a QDialog, shown non-blocking via show_modal from "
        "import_wizard.py (lines 816-817 and 1540-1552). No banned token here."
    ),
    "set_hint.py": (
        "SetHintDialog: a QDialog, shown non-blocking via main_window's "
        "tracked _open_dialog (main_window.py:1090ff, read back via "
        "self._dialog). No banned token here."
    ),
    "settings.py": (
        "SettingsDialog: a QDialog; its own docstring says it is 'Shown "
        "non-blocking (setModal(True) + show())'. No banned token here."
    ),
    "unlock.py": (
        "UnlockDialog: a QDialog; its own docstring calls it a 'non-blocking "
        "application-modal QDialog' shown via main_window's tracked "
        "_open_dialog (main_window.py:647). No banned token here."
    ),
    "update_dialog.py": (
        "UpdateDialog: a QDialog; its own docstring says it is opened through "
        "the shell's tracked _open_dialog path — 'never exec() — INV-9'. No "
        "banned token here."
    ),
    # -- the two individually-defended exec()/QMenu cases --------------------- #
    "start_over.py": (
        "StartOverDialog: a QDialog. Its own docstring flags it as the app's "
        "one exec()-driven dialog, but that call is issued by the CALLER "
        "(main_window.py:1147, see the main_window.py entry below) — this file "
        "itself defines the class and contains no .exec(/processEvents token."
    ),
    "main_window.py": (
        "The application shell. It contains the app's ONE surviving blocking "
        "dialog.exec() (line 1147, on StartOverDialog) — a deliberate, "
        "out-of-scope exemption, not an oversight: _on_start_over is reachable "
        "only via UnlockDialog.start_over_requested (wired in "
        "_open_unlock_dialog, itself reachable only from _show_unlock's three "
        "call sites — initial startup, the locked placeholder's Unlock button, "
        "and the pre-login restore-cancelled route — none of which run while "
        "the vault is unlocked), so the vault is already LOCKED whenever this "
        "exec() runs and the FIBR-0065 auto-lock-during-nested-exec crash "
        "class — which needs a live, unlocked vault behind the paused code — "
        "cannot fire there. Every other dialog main_window opens goes through "
        "its own tracked, non-blocking _open_dialog slot."
    ),
    "transactions.py": (
        "TransactionsView: the Transactions tab. It opens CategoryPickerDialog "
        "and RuleEditDialog non-blocking via show_modal (lines 407-436), and "
        "its right-click menu is a QMenu — menu.exec( at line 384 — the "
        "identical shape to the existing home.py exemption above (a pop-up "
        "menu, not a modal dialog, out of scope)."
    ),
    # -- content-widget tabs that own no dialog at all (inline forms, or -------
    #    direct-apply actions with no modal step) --------------------------- #
    "accounts.py": (
        "AccountsWidget: the Accounts tab; its add/edit form is inline in the "
        "widget, not a QDialog at all — no pop-up to guard."
    ),
    "categories.py": (
        "CategoriesWidget: the Categories tab; its add/edit form is inline in "
        "the widget, not a QDialog — no pop-up to guard."
    ),
    "forecast.py": (
        "ForecastWidget: the Forecast tab; presentation-only, no dialog and no pop-up."
    ),
    "recurring.py": (
        "RecurringWidget: the Recurring tab; its own docstring says actions "
        "apply directly — 'no modal' — no QDialog at all."
    ),
    "transfers.py": (
        "TransfersWidget: the Transfers tab; its own docstring says actions "
        "apply directly — 'no modal' — no QDialog at all."
    ),
    # -- pure helpers: no QDialog, no pop-up ----------------------------------- #
    "_amount.py": (
        "no QDialog and no pop-up: pure money-string formatting helper shared "
        "by home.py and transactions.py."
    ),
    "charts.py": (
        "no QDialog and no pop-up: pure chart-builder functions shared by "
        "home.py and the PDF export."
    ),
    "_clipboard.py": (
        "no QDialog and no pop-up: a QObject clipboard-clear timer helper."
    ),
    "_datetime_prefs.py": (
        "no QDialog and no pop-up: shared combo-builder widgets consumed "
        "inside settings.py's and first_run.py's own dialogs — it builds "
        "controls, it does not itself show anything."
    ),
    "icons.py": "no QDialog and no pop-up: a toolbar icon loader.",
    "__init__.py": "package docstring only — no code, no dialog, no pop-up.",
    "modal.py": (
        "the show_modal helper ITSELF — the non-blocking replacement INV-1 "
        "exists to enforce. It defines no QDialog subclass and calls no "
        ".exec(/processEvents."
    ),
    "month_summary.py": (
        "MonthSummaryStrip: a presentation-only QWidget (template phrasing for "
        "the Home dashboard); no QDialog, no pop-up."
    ),
    "_password_hint.py": (
        "no QDialog and no pop-up: a QSettings adapter for the plaintext password hint."
    ),
    "_table_state.py": (
        "no QDialog and no pop-up: a QTableWidget sort + remembered-column-width mixin."
    ),
    "theme.py": (
        "no QDialog and no pop-up: the app-wide palette/stylesheet system "
        "(ThemeController)."
    ),
    "_unlock_throttle.py": (
        "no QDialog and no pop-up: a QSettings adapter for the failed-unlock "
        "backoff state."
    ),
    "_update_worker.py": (
        "no QDialog and no pop-up: off-GUI-thread QThread workers for the "
        "update check/download."
    ),
    "_widgets.py": (
        "no QDialog and no pop-up: a shared combo-preselect helper function."
    ),
    "_worker.py": (
        "no QDialog and no pop-up: the off-GUI-thread Argon2id derivation "
        "QThread worker."
    ),
}


def test_INV7_every_ui_module_is_classified() -> None:
    """FIBR-0277 — the coverage-hole guard. _FILES is hand-maintained and INV-1's
    grep only iterates its five names, so a UI module created and never added to
    either list is silently uncovered rather than failing. This asserts every
    ``*.py`` under ``ui/`` is accounted for in exactly one of the two sets, so
    the omission turns this test red instead of shrinking INV-1's reach."""
    on_disk = {p.name for p in _UI_DIR.glob("*.py")}
    known = set(_FILES) | set(_NOT_CONTENT_WIDGETS)
    unclassified = on_disk - known
    assert not unclassified, (
        "the following ui/*.py modules are in neither _FILES nor "
        "_NOT_CONTENT_WIDGETS, so INV-1's grep silently does not cover them: "
        + ", ".join(sorted(unclassified))
        + ". Add each one to _FILES (if it can own a modal pop-up) or to "
        "_NOT_CONTENT_WIDGETS with a written, specific reason why it does not "
        "need INV-1's coverage."
    )
    # The converse also matters: an entry naming a file that no longer exists is
    # dead documentation, and it would silently mask a rename landing unclassified
    # under its new name.
    stale = known - on_disk
    assert not stale, (
        "the following names in _FILES / _NOT_CONTENT_WIDGETS no longer exist "
        "under ui/: " + ", ".join(sorted(stale))
    )


def test_INV1_no_blocking_dialog_exec_in_content_widgets() -> None:
    offenders: list[str] = []
    for name in _FILES:
        for lineno, line in enumerate((_UI_DIR / name).read_text().splitlines(), 1):
            if not _EXEC.search(line):
                continue
            # Sole exemption: the Home right-click context menu (a QMenu, not a
            # modal dialog; reads no dialog object after, out of scope).
            if name == "home.py" and "menu.exec(" in line:
                continue
            offenders.append(f"{name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "a blocking .exec( or an event-pumping processEvents was found — both "
        "re-enter the event loop, which is the FIBR-0065 crash class. Convert to "
        "the non-blocking show_modal pattern, and drive a long loop one turn per "
        "QTimer.singleShot (FIBR-0065 INV-1 / FIBR-0085 INV-6):\n"
        + "\n".join(offenders)
    )


# -- INV-4 (no leak) --------------------------------------------------------- #


def test_INV4_accept_runs_slot_on_a_live_dialog_then_frees_it(qtbot) -> None:
    """The accept path: ``on_accept`` still sees a live dialog (``deleteLater`` is
    deferred, which is *why* the helper uses it), and the dialog is gone once the
    DeferredDelete queue is flushed."""
    parent = QWidget()
    qtbot.addWidget(parent)
    dialog = QDialog(parent)
    alive_during_slot: list[bool] = []

    show_modal(dialog, lambda: alive_during_slot.append(shiboken6.isValid(dialog)))
    dialog.accept()

    assert alive_during_slot == [True], "on_accept must run, and on a live dialog"
    _pump_deferred_delete()
    assert not shiboken6.isValid(dialog), "the dialog is freed on accept"


def test_INV4_reject_frees_the_dialog_without_running_the_slot(qtbot) -> None:
    """The reject path: ``finished`` fires on reject too, so the dialog is freed —
    but ``accepted`` does not, so ``on_accept`` must not run."""
    parent = QWidget()
    qtbot.addWidget(parent)
    dialog = QDialog(parent)
    calls: list[int] = []

    show_modal(dialog, lambda: calls.append(1))
    dialog.reject()

    assert calls == [], "on_accept must not run on reject"
    _pump_deferred_delete()
    assert not shiboken6.isValid(dialog), "the dialog is freed on reject"
