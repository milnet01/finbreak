"""FIBR-0085 — batch statement import, the widget half. Enforces spec.md.

The five invariants that drive real widgets: INV-3 (nothing commits while a
question is outstanding), INV-5 (the displayed account is the targeted account),
INV-7 (an idle auto-lock stops the run), INV-8 (three prompts, then skip) and
INV-14 (``done`` waits for the report). The other eight are headless and live in
``test_batch_import.py``.

Every dialog here is a signal-emitting ``QDialog`` stand-in rather than the real
one — the pattern ``tests/features/dialog_lifecycle/`` established when
FIBR-0065 converted the blocking pop-ups. A fake that emits ``accepted`` is what
makes a non-blocking flow testable at all.

No real statement data and no ``.pdf`` bytes: the one locked-PDF fixture is a
``.pdf``-named file of arbitrary bytes plus a fake decrypt (INV-12).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog

from conftest import _PW, _acct
from finbreak.importers.pdf_importer import PasswordError
from finbreak.models import AccountType, ColumnMapping
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.batch_import import BatchImportService
from finbreak.services.import_ import ImportService
from finbreak.ui import import_batch as import_batch_mod
from finbreak.ui import import_wizard as wizard_mod
from finbreak.ui.import_wizard import _STEP_BATCH, _STEP_MAP, ImportWizardWidget

pytestmark = pytest.mark.features

_HEADER = ["Date", "Details", "Amount"]
_MAPPING = ColumnMapping("Date", "Details", "Amount", None, None, "%Y-%m-%d", False)


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


@pytest.fixture
def profile(service) -> None:
    """Save the profile the CSV fixtures' header matches, so those files need no
    mapping question. A test that WANTS the mapping question writes a CSV with a
    different header instead."""
    ImportService(service.vault).save_profile("test layout", _HEADER, _MAPPING)


def _csv(tmp_path: Path, name: str, rows, header=None) -> str:
    lines = [",".join(header or _HEADER)]
    lines += [",".join(row) for row in rows]
    (tmp_path / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(tmp_path / name)


def _rows(n: int, *, day_from: int = 1, tag: str = "a") -> list[list[str]]:
    return [
        [f"2026-01-{day_from + i:02d}", f"{tag}shop{i}", f"-{i + 1}0.00"]
        for i in range(n)
    ]


def _wizard(qtbot, service) -> ImportWizardWidget:
    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget.show()
    return widget


def _count_rows(conn, account_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE account_id = ?", (account_id,)
    ).fetchone()[0]


def _stub_picker(monkeypatch, account_id: int | None):
    """Patch ``AccountPickerDialog`` with an auto-driven stand-in: accepts with
    ``account_id``, or rejects when it is ``None``."""

    class _Stub(QDialog):
        create_requested = Signal()  # the real dialog's § 3 decision 6 affordance

        def __init__(self, accounts, current_account_id, parent=None, hint=None):
            super().__init__(parent)

        def show(self):
            super().show()
            self.accept() if account_id is not None else self.reject()

        def selected_account_id(self):
            return account_id

    monkeypatch.setattr(import_batch_mod, "AccountPickerDialog", _Stub)


def _stub_password(monkeypatch, *, password: str | None, remember: bool = False):
    """Patch ``PasswordDialog`` with a stand-in that answers on show —
    ``password=None`` cancels. Returns the log of constructions, so a test can
    count PROMPTS (INV-8) rather than decrypt attempts."""
    shown: list[str] = []

    class _Stub(QDialog):
        def __init__(self, account_name, parent=None):
            super().__init__(parent)
            shown.append(account_name)

        def show(self):
            super().show()
            self.accept() if password is not None else self.reject()

        def password(self):
            return password or ""

        def remember(self):
            return remember

    monkeypatch.setattr(wizard_mod, "PasswordDialog", _Stub)
    return shown


def _locked_pdf(monkeypatch, tmp_path: Path, name: str = "locked.pdf") -> str:
    """A ``.pdf``-named file whose decrypt always refuses every password — no
    real PDF bytes, and nothing under this directory to commit (INV-12)."""

    def always_locked(data, password=None):
        raise PasswordError("bad password")

    monkeypatch.setattr(
        "finbreak.services.batch_import.PdfImporter.decrypt_to_plaintext",
        staticmethod(always_locked),
    )
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.7 encrypted")
    return str(path)


# -- INV-3 ------------------------------------------------------------------- #


def test_INV3_no_commit_before_every_question_answered(
    qtbot, service, profile, tmp_path, monkeypatch
):
    """Two legs, because the two halves are enforced by different mechanisms.

    (a) A batch containing one locked PDF whose prompt is LEFT OPEN commits
    nothing at all — including the records that were already `ready`. "Left
    open" is the distinction from a *declined* prompt, which becomes `skipped`
    and does not block the batch.
    (b) A batch reaching REVIEW with one `needs_account` row cannot start.

    Breaks when `Import all` is gated on "at least one ready" alone, which is
    true while another row still has no destination — or no answer at all.
    """
    account = _acct(service)

    # (a) — a prompt that never answers.
    class _NeverAnswers(QDialog):
        def __init__(self, account_name, parent=None):
            super().__init__(parent)

    monkeypatch.setattr(wizard_mod, "PasswordDialog", _NeverAnswers)
    locked = _locked_pdf(monkeypatch, tmp_path)
    good = _csv(tmp_path, "a.csv", _rows(2))

    widget = _wizard(qtbot, service)
    widget._select_files([good, locked])
    # The prompt is up and unanswered: ASK has raised it and nothing came back.
    qtbot.waitUntil(lambda: bool(widget._batch_prompts), timeout=3000)

    files = widget._batch_files
    assert any(f.outcome == "needs_password" for f in files)
    assert not BatchImportService.can_import(files), (
        "no file may be committable while a question is still outstanding"
    )
    assert not widget._batch_review._import_button.isEnabled()
    assert _count_rows(service.vault.connection, account) == 0, (
        "nothing may reach the vault while ASK has an open question"
    )

    # (b) — every question answered, but one row has no destination. A CSV
    # carries no account number, so this is the ordinary state of a CSV batch.
    widget2 = _wizard(qtbot, service)
    widget2._select_files([good, _csv(tmp_path, "b.csv", _rows(2, day_from=5))])
    qtbot.waitUntil(lambda: widget2._stack.currentIndex() == _STEP_BATCH, timeout=3000)
    qtbot.waitUntil(
        lambda: all(f.outcome == "needs_account" for f in widget2._batch_files),
        timeout=3000,
    )
    assert not widget2._batch_review._import_button.isEnabled(), (
        "Import all must stay off while any row still says — pick one —"
    )
    assert _count_rows(service.vault.connection, account) == 0


# -- INV-5 ------------------------------------------------------------------- #


def test_INV5_displayed_account_is_the_targeted_account(
    qtbot, service, profile, tmp_path, monkeypatch
):
    """Three legs, one per route into a destination: a matched file, a
    `needs_account` file given an account on the review screen (which builds its
    FIRST preview via `preview_result`), and an already-`ready` file changed on
    the review screen (which goes through `retarget`).

    The middle leg is the one to watch failing with `retarget` substituted for
    `preview_result`: `retarget` takes an `ImportPreview` and a `needs_account`
    row has none, so a conforming route cannot use it. If the mutation passes,
    the fixture's file already had a preview and the leg tests the wrong route.

    Breaks when a review-row account change updates the cell without
    re-pointing the preview — the FIBR-0086 § 4.5 wrong-account commit reached
    through a new door.
    """
    accounts = AccountService(service.vault)
    first = _acct(service)
    second = accounts.add_account("Second", AccountType.SAVINGS.value).id

    paths = [
        _csv(tmp_path, "a.csv", _rows(2, tag="a")),
        _csv(tmp_path, "b.csv", _rows(3, day_from=10, tag="b")),
    ]
    widget = _wizard(qtbot, service)
    widget._select_files(paths)
    qtbot.waitUntil(
        lambda: all(f.outcome == "needs_account" for f in widget._batch_files),
        timeout=3000,
    )
    files = widget._batch_files
    review = widget._batch_review

    # Leg 1 (the no-preview route) — row 0 has no preview at all, so this must
    # go through `preview_result`.
    assert files[0].preview is None, (
        "a needs_account row reaches the review screen with no preview — the "
        "precondition the preview_result route exists for"
    )
    _stub_picker(monkeypatch, first)
    review._choose_account(0)
    assert files[0].preview is not None
    assert files[0].preview.account_id == first
    assert review._table.item(0, import_batch_mod.COL_ACCOUNT).text() == "Default", (
        "the Account cell must read the account the preview now targets"
    )

    # Leg 2 (the retarget route) — row 0 already has a preview; change it.
    _stub_picker(monkeypatch, second)
    review._choose_account(0)
    assert files[0].preview is not None
    assert files[0].preview.account_id == second, (
        "changing an already-settled row must re-point its preview"
    )
    assert review._table.item(0, import_batch_mod.COL_ACCOUNT).text() == "Second"

    # Leg 3 — the rows land where the screen says. Place row 1 too, then run.
    _stub_picker(monkeypatch, first)
    review._choose_account(1)
    review._import_button.click()
    qtbot.waitUntil(lambda: all(f.outcome == "committed" for f in files), timeout=3000)
    conn = service.vault.connection
    assert (_count_rows(conn, second), _count_rows(conn, first)) == (2, 3), (
        "each file's rows land in the account its review row displayed"
    )


# -- INV-7 ------------------------------------------------------------------- #


def test_INV7_autolock_mid_batch_stops_the_run(
    qtbot, service, profile, tmp_path, monkeypatch
):
    """An idle auto-lock during a batch stops it: the committed file stays
    committed, and NO FURTHER FILE IS ATTEMPTED.

    Watched failing with the two-argument `QTimer.singleShot(0, callable)`. The
    row count alone would not catch that — a resumed turn hits a locked vault
    and its `commit_import` raises, so the second file's rows are missing under
    both the fix and the mutation. What separates them is whether the second
    file was TOUCHED at all: under the mutation the pending callback survives
    the widget's death, `run_step` runs a second time, and the record is left
    `failed` rather than untouched.
    """
    from finbreak.ui.main_window import MainWindow

    account = _acct(service)
    paths = [
        _csv(tmp_path, "a.csv", _rows(2, tag="a")),
        _csv(tmp_path, "b.csv", _rows(2, day_from=10, tag="b")),
    ]

    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    window._open_import()
    widget = window.findChild(ImportWizardWidget)
    assert widget is not None

    widget._select_files(paths)
    qtbot.waitUntil(
        lambda: all(f.outcome == "needs_account" for f in widget._batch_files),
        timeout=3000,
    )
    files = widget._batch_files
    _stub_picker(monkeypatch, account)
    widget._batch_review._choose_account(0)
    widget._batch_review._choose_account(1)

    # Lock the vault the instant the first file has committed — the "between two
    # files" moment. Counting the calls is what makes the mutation observable.
    calls: list[int] = []
    real_step = BatchImportService.run_step

    def locking_step(self, batch_files, index):
        calls.append(index)
        result = real_step(self, batch_files, index)
        if index == 0:
            window._lock()
        return result

    monkeypatch.setattr(BatchImportService, "run_step", locking_step)
    widget._batch_review._import_button.click()
    qtbot.wait(200)  # let every turn the chain could still take, take

    assert calls == [0], (
        f"run_step was called for indices {calls} — the pending callback "
        "survived the widget's death and resumed against a locked vault"
    )
    assert files[1].outcome == "ready", (
        f"the second file's outcome = {files[1].outcome}, expected it to be "
        "left untouched rather than attempted after the lock"
    )
    assert service.unlock(bytearray(_PW)) is True
    assert _count_rows(service.vault.connection, account) == 2, (
        "exactly the first file's rows survive; nothing is half-written"
    )


# -- INV-8 ------------------------------------------------------------------- #


def test_INV8_password_prompts_are_bounded(
    qtbot, service, profile, tmp_path, monkeypatch
):
    """A locked PDF raises at most three USER PROMPTS, after which the file is
    `skipped` and the batch continues.

    Breaks when the re-prompt recurses without a counter — which is exactly what
    `ImportWizardWidget._on_pdf_password` does today, and what a copy-paste of
    it into the batch would reproduce.
    """
    account = _acct(service)
    locked = _locked_pdf(monkeypatch, tmp_path)
    good = _csv(tmp_path, "a.csv", _rows(2))
    prompts = _stub_password(monkeypatch, password="wrong")

    widget = _wizard(qtbot, service)
    widget._select_files([good, locked])
    qtbot.waitUntil(
        lambda: any(f.outcome == "skipped" for f in widget._batch_files),
        timeout=5000,
    )

    assert len(prompts) == 3, (
        f"{len(prompts)} password prompt(s) raised, expected the bound of three"
    )
    files = widget._batch_files
    skipped = [f for f in files if f.outcome == "skipped"]
    assert len(skipped) == 1 and skipped[0].path == locked
    assert "unlock" in skipped[0].reason, (
        f"reason = {skipped[0].reason!r} — it must not claim the user supplied "
        "no password; three wrong ones reach here too"
    )
    # The batch carried on: the CSV still reaches the review screen.
    _stub_picker(monkeypatch, account)
    widget._batch_review._choose_account(
        next(i for i, f in enumerate(files) if f.path == good)
    )
    assert widget._batch_review._import_button.isEnabled(), (
        "a skipped file is the report, not an obstacle — it must not block the run"
    )


def test_INV8_cancelling_a_prompt_skips_that_file_immediately(
    qtbot, service, profile, tmp_path, monkeypatch
):
    """Cancelling a prompt skips that file at once — one prompt, not three.

    `show_modal` wires only `accepted`, so a Cancel is currently unobservable;
    without the batch connecting `rejected` on the dialog it constructs, the
    pass would wait forever on a dialog that has already been freed.
    """
    locked = _locked_pdf(monkeypatch, tmp_path)
    prompts = _stub_password(monkeypatch, password=None)  # rejects on show

    widget = _wizard(qtbot, service)
    widget._select_files([locked, _csv(tmp_path, "a.csv", _rows(2))])
    qtbot.waitUntil(
        lambda: any(f.outcome == "skipped" for f in widget._batch_files),
        timeout=3000,
    )
    assert len(prompts) == 1, (
        f"{len(prompts)} prompt(s) raised, expected a cancel to skip at once"
    )


# -- INV-14 ------------------------------------------------------------------ #


def test_INV14_done_waits_for_the_report(
    qtbot, service, profile, tmp_path, monkeypatch
):
    """`done` is emitted only by the report's Close.

    Never at the end of RUN — which is what the single-file `_on_import` does,
    so it is the natural thing to copy. Never by the batch step's Cancel, and
    never by the `_STEP_MAP` Cancel while the batch is driving that page: all
    three existing steps' Cancel buttons are wired straight to `done`, and
    `MainWindow._on_import_done` answers it by rebuilding the workspace —
    destroying the very table the report is written into.

    The `_STEP_MAP` case is the worst, because it is reached by REUSING that
    page: declining the mapping for one file in a thirty-file batch would tear
    down the whole batch and every answer already given.
    """
    account = _acct(service)
    emissions: list[int] = []

    # (a) — the last record commits.
    widget = _wizard(qtbot, service)
    widget.done.connect(lambda: emissions.append(1))
    widget._select_files(
        [
            _csv(tmp_path, "a.csv", _rows(2)),
            _csv(tmp_path, "b.csv", _rows(2, day_from=9)),
        ]
    )
    qtbot.waitUntil(
        lambda: all(f.outcome == "needs_account" for f in widget._batch_files),
        timeout=3000,
    )
    _stub_picker(monkeypatch, account)
    widget._batch_review._choose_account(0)
    widget._batch_review._choose_account(1)
    widget._batch_review._import_button.click()
    qtbot.waitUntil(
        lambda: all(f.outcome == "committed" for f in widget._batch_files),
        timeout=3000,
    )
    assert emissions == [], "done must not fire when the last record commits"

    # ...and exactly once when the report is dismissed.
    assert widget._batch_review._close_button.isVisible(), (
        "Close appears only once RUN has finished — and it is the one control "
        "that emits done"
    )
    widget._batch_review._close_button.click()
    assert emissions == [1], f"done emitted {len(emissions)} time(s), expected one"

    # (b) — Cancel during a run stops the chain without emitting done.
    cancels: list[int] = []
    widget2 = _wizard(qtbot, service)
    widget2.done.connect(lambda: cancels.append(1))
    widget2._select_files([_csv(tmp_path, "c.csv", _rows(2, day_from=15, tag="c"))])
    qtbot.waitUntil(
        lambda: widget2._batch_files[0].outcome == "needs_account", timeout=3000
    )
    _stub_picker(monkeypatch, account)
    widget2._batch_review._choose_account(0)
    widget2._batch_review._import_button.click()
    widget2._batch_review._cancel_button.click()
    qtbot.wait(100)
    assert cancels == [], "the batch step's Cancel must not emit done"

    # (c) — declining a mapping mid-batch. An unmatched header is what raises
    # the mapping question at all.
    declines: list[int] = []
    odd = _csv(
        tmp_path,
        "odd.csv",
        [["2026-01-02", "shop", "-10.00"]],
        header=["When", "What", "How much"],
    )
    widget3 = _wizard(qtbot, service)
    widget3.done.connect(lambda: declines.append(1))
    widget3._select_files(
        [odd, _csv(tmp_path, "d.csv", _rows(2, day_from=20, tag="d"))]
    )
    qtbot.waitUntil(lambda: widget3._stack.currentIndex() == _STEP_MAP, timeout=3000)
    widget3._on_map_cancel()
    qtbot.wait(100)
    assert declines == [], (
        "declining ONE file's mapping must not tear down the whole batch"
    )
    assert any(f.outcome == "skipped" for f in widget3._batch_files), (
        "the declined file is skipped, and the batch carries on"
    )
