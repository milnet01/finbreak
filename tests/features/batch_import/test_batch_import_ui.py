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

No real statement data and no ``.pdf`` bytes committed here: the one locked-PDF
fixture is a ``.pdf``-named file of arbitrary bytes plus a fake decrypt
(INV-12). One leg (FIBR-0252 INV-4) reaches across to the SB suite's committed
``family_a_zero_fee.pdf`` — synthetic too, and the only thing that can carry a
RowError through the real scan ladder into a rendered cell.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPushButton

from conftest import _PW, _acct
from finbreak.importers.pdf_importer import PasswordError
from finbreak.models import AccountType, ColumnMapping
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.batch_import import BatchFile, BatchImportService
from finbreak.services.import_ import ImportResult, ImportService
from finbreak.ui import import_batch as import_batch_mod
from finbreak.ui import import_wizard as wizard_mod
from finbreak.ui.account_picker import AccountPickerDialog
from finbreak.ui.import_wizard import _STEP_BATCH, _STEP_MAP, ImportWizardWidget

pytestmark = pytest.mark.features

_HEADER = ["Date", "Details", "Amount"]
_MAPPING = ColumnMapping("Date", "Details", "Amount", None, None, "%Y-%m-%d", False)

# The SB suite's committed synthetic fixtures — nothing binary lives under this
# directory; FIBR-0252 INV-4's render half reaches across for the one statement
# that carries a RowError.
_SB_FIXTURES = Path(__file__).parent.parent / "standard_bank_pdf" / "fixtures"


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


_OFX_HEADER = (
    "OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\n"
    "ENCODING:USASCII\r\nCHARSET:1252\r\nCOMPRESSION:NONE\r\nOLDFILEUID:NONE\r\n"
    "NEWFILEUID:NONE\r\n\r\n"
)


def _ofx(tmp_path: Path, name: str, acctid: str) -> str:
    """A one-transaction OFX naming ``acctid`` — the only format here that
    reaches `ready` unaided, because it carries its own account number. A CSV
    always stops at `needs_account`."""
    body = (
        _OFX_HEADER + "<OFX>\n"
        "<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>\n"
        f"<STMTRS><CURDEF>ZAR<BANKACCTFROM><BANKID>250655<ACCTID>{acctid}"
        "<ACCTTYPE>CHECKING</BANKACCTFROM>\n"
        "<BANKTRANLIST><DTSTART>20260101\n<DTEND>20260131\n"
        "<STMTTRN>\n<TRNTYPE>DEBIT\n<DTPOSTED>20260105\n<TRNAMT>-10.00\n"
        "<NAME>shop\n<FITID>F1\n</STMTTRN>\n</BANKTRANLIST>\n"
        "<LEDGERBAL><BALAMT>0.00<DTASOF>20260131</LEDGERBAL>\n"
        "</STMTRS></STMTTRNRS></BANKMSGSRSV1>\n</OFX>\n"
    )
    (tmp_path / name).write_bytes(body.encode())
    return str(tmp_path / name)


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
        def __init__(self, account_name, parent=None, remember_text=None):
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
    # A MATCHED file, so the batch really does hold a `ready` record. With two
    # CSVs (neither of which carries an account number) every record stops at
    # `needs_account`, `can_import` returns False on its "at least one ready"
    # clause alone, and BOTH legs pass against the exact implementation INV-3
    # names as the break — the leg would be asserting nothing.
    AccountService(service.vault).add_account(
        "Matched", AccountType.CURRENT.value, account_number="000123456"
    )

    # (a) — a prompt that never answers.
    class _NeverAnswers(QDialog):
        def __init__(self, account_name, parent=None, remember_text=None):
            super().__init__(parent)

    monkeypatch.setattr(wizard_mod, "PasswordDialog", _NeverAnswers)
    locked = _locked_pdf(monkeypatch, tmp_path)
    good = _ofx(tmp_path, "a-bank.ofx", "000123456")

    widget = _wizard(qtbot, service)
    widget._select_files([good, locked])
    # The prompt is up and unanswered: ASK has raised it and nothing came back.
    qtbot.waitUntil(lambda: bool(widget._batch_prompts), timeout=3000)

    files = widget._batch_files
    assert any(f.outcome == "needs_password" for f in files)
    assert any(f.outcome == "ready" for f in files), (
        "precondition: a record IS committable on its own merits, so the "
        "assertion below turns on the outstanding question and nothing else"
    )
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
        lambda: any(f.outcome == "needs_account" for f in widget2._batch_files),
        timeout=3000,
    )
    files2 = widget2._batch_files
    assert any(f.outcome == "ready" for f in files2), (
        "precondition: the OFX matched, so only the unplaced CSV is in question"
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
    matched_id = accounts.add_account(
        "Matched", AccountType.CURRENT.value, account_number="000123456"
    ).id

    # Leg 0 — the MATCHED route, which INV-5 names first: `match_account` runs
    # BEFORE the first preview is built, so a matched file arrives already
    # pointing at its own account and the cell agrees with the preview without
    # anyone touching the picker. Neither of the other two legs covers it,
    # because a CSV carries no account number to match on.
    matched_widget = _wizard(qtbot, service)
    matched_widget._select_files(
        [_ofx(tmp_path, "m-bank.ofx", "000123456"), _csv(tmp_path, "z.csv", _rows(1))]
    )
    qtbot.waitUntil(
        lambda: matched_widget._batch_files[0].outcome == "ready", timeout=3000
    )
    hit = matched_widget._batch_files[0]
    assert hit.preview is not None and hit.preview.account_id == matched_id, (
        "a matched file's FIRST preview must already target the matched account "
        "— building it before match_account runs is the wrong-account commit"
    )
    assert (
        matched_widget._batch_review._table.item(0, import_batch_mod.COL_ACCOUNT).text()
        == "Matched"
    )

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


# -- one run at a time -------------------------------------------------------- #


def test_a_second_import_all_cannot_arm_a_second_run(
    qtbot, service, profile, tmp_path, monkeypatch
):
    """RUN starts once. A second `Import all` must not rewind the index and arm
    a second chain alongside the first.

    Two chains stepping the same `_batch_index` advance it twice per turn, so
    roughly every other file is skipped by both — never committed, and never
    reported as skipped either. This is the same defect that let `Import all` be
    pressed mid-SCAN; the button being off during the run is one guard and the
    phase check is the other, because a queued click can still arrive.
    """
    account = _acct(service)
    widget = _wizard(qtbot, service)
    widget._select_files(
        [
            _csv(tmp_path, "a.csv", _rows(2, day_from=1, tag="a")),
            _csv(tmp_path, "b.csv", _rows(2, day_from=6, tag="b")),
            _csv(tmp_path, "c.csv", _rows(2, day_from=11, tag="c")),
        ]
    )
    qtbot.waitUntil(
        lambda: all(f.outcome == "needs_account" for f in widget._batch_files),
        timeout=3000,
    )
    _stub_picker(monkeypatch, account)
    for row in range(3):
        widget._batch_review._choose_account(row)

    indices: list[int] = []
    real_step = BatchImportService.run_step

    def logging_step(self, batch_files, index):
        indices.append(index)
        if index == 0:
            # QUEUE the second press rather than calling it inline. Called from
            # inside `run_step`, the rewind to index 0 is immediately overwritten
            # by `_run_next`'s own `self._batch_index = run_step(...)` assignment
            # — so the defect hides and the test passes against it. A real click
            # arrives between turns, which is what this reproduces. Delivered to
            # the slot rather than the button, so the test still holds if the
            # button's own disabling is what regresses.
            QTimer.singleShot(0, widget, widget._on_batch_import)
        return real_step(self, batch_files, index)

    monkeypatch.setattr(BatchImportService, "run_step", logging_step)
    widget._batch_review._import_button.click()
    qtbot.wait(300)

    assert indices == [0, 1, 2], (
        f"run_step saw indices {indices} — a second chain was armed, so the "
        "index was rewound and files were stepped by two passes at once"
    )
    assert not widget._batch_review._import_button.isEnabled(), (
        "Import all must be off while the run is in flight"
    )
    assert all(f.outcome == "committed" for f in widget._batch_files), (
        "every file still commits exactly once"
    )
    assert _count_rows(service.vault.connection, account) == 6


# -- the reused mapping form -------------------------------------------------- #


def test_the_mapping_form_does_not_carry_one_files_answers_into_the_next(
    qtbot, service, tmp_path, monkeypatch
):
    """§ 4.1 reuses `_STEP_MAP` per file. Everything it does NOT refill must be
    reset between records, or the previous file's answers are silently applied
    to the next one.

    "Amounts are reversed" is the sharp one: left ticked, it FLIPS EVERY SIGN on
    the following file — income becomes expenditure and the whole dashboard
    moves. Nothing refills it here, because the record is `needs_mapping`
    precisely when no saved profile matched, so `_apply_profile_to_combos` (the
    one place that would) is unreachable on this path.
    """
    first = _csv(
        tmp_path,
        "a-odd.csv",
        [["2026-01-02", "shop", "-10.00"]],
        header=["When", "What", "How much"],
    )
    second = _csv(
        tmp_path,
        "b-other.csv",
        [["2026-01-03", "shop", "-20.00"]],
        header=["Day", "Payee", "Value"],
    )
    widget = _wizard(qtbot, service)
    widget._select_files([first, second])
    qtbot.waitUntil(lambda: widget._stack.currentIndex() == _STEP_MAP, timeout=3000)
    assert widget._batch_asking is not None
    assert Path(widget._batch_asking.path).name == "a-odd.csv"

    # Answer file 1 with the reversal ticked and a debit/credit style.
    widget._invert_amount.setChecked(True)
    widget._on_map_next()

    qtbot.waitUntil(
        lambda: (
            widget._batch_asking is not None
            and Path(widget._batch_asking.path).name == "b-other.csv"
        ),
        timeout=3000,
    )
    assert widget._stack.currentIndex() == _STEP_MAP
    assert not widget._invert_amount.isChecked(), (
        "the second file's mapping form arrived still holding the first file's "
        "'Amounts are reversed' tick — every amount in it would import "
        "sign-flipped"
    )
    assert widget._amount_style.currentIndex() == 0, (
        "the amount style must start from the single-column default too"
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
    # Wait for the REPORT, not merely for the last commit. `_run_next` sets the
    # final outcome to `committed` in one turn and only reaches `finish()` in the
    # next, armed with `singleShot(0)` — so the outcomes-only condition is true
    # one whole turn before Close exists. Whether `waitUntil`'s poll lands before
    # or after that queued turn is scheduler luck: it wins on a developer desktop
    # and lost on a loaded CI runner (run 31622538238 red, the identical test
    # green on the very next push). `_batch_phase` is set to "report" in the same
    # slot invocation as `finish()`, with no event loop between them, so this
    # condition cannot observe a finished run whose Close has not appeared.
    qtbot.waitUntil(
        lambda: (
            all(f.outcome == "committed" for f in widget._batch_files)
            and widget._batch_phase == "report"
        ),
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
    widget2._select_files(
        [
            _csv(tmp_path, "c.csv", _rows(2, day_from=15, tag="c")),
            _csv(tmp_path, "e.csv", _rows(2, day_from=18, tag="e")),
            _csv(tmp_path, "f.csv", _rows(2, day_from=21, tag="f")),
        ]
    )
    qtbot.waitUntil(
        lambda: all(f.outcome == "needs_account" for f in widget2._batch_files),
        timeout=3000,
    )
    _stub_picker(monkeypatch, account)
    for row in range(3):
        widget2._batch_review._choose_account(row)

    # Cancel the INSTANT the first file has committed. Waiting on a condition
    # cannot do this: `qtbot.waitUntil` pumps the event loop, so the whole
    # three-file chain finishes before the first poll returns and the click
    # lands on an already-finished run — testing the wrong branch entirely.
    # Interposing on `run_step` is the same trick INV-7 uses, for the same
    # reason: a chain of `singleShot(0)` turns has no gap to click in.
    real_step = BatchImportService.run_step

    def cancelling_step(self, batch_files, index):
        result = real_step(self, batch_files, index)
        if index == 0:
            widget2._batch_review._cancel_button.click()
        return result

    monkeypatch.setattr(BatchImportService, "run_step", cancelling_step)
    widget2._batch_review._import_button.click()
    qtbot.wait(200)
    assert widget2._batch_files[0].outcome == "committed", (
        "precondition: the run really did commit a prefix before the cancel"
    )
    assert cancels == [], "the batch step's Cancel must not emit done"
    assert widget2._batch_review._close_button.isVisible(), (
        "a cancelled run still leaves the report standing, with its Close"
    )
    assert any(f.outcome == "not_attempted" for f in widget2._batch_files), (
        "the files the cancel stopped short of must say so"
    )

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
    # Click the REAL button. INV-14's named break is that a Cancel "stays wired
    # to `done`" — a regression to `cancel.clicked.connect(self.done)` leaves
    # `_on_map_cancel` itself perfectly correct, so calling the slot directly
    # would pass straight through the defect.
    map_cancel = next(
        button
        for button in widget3._stack.widget(_STEP_MAP).findChildren(QPushButton)
        if button.text() == "Cancel"
    )
    map_cancel.click()
    qtbot.wait(100)
    assert declines == [], (
        "declining ONE file's mapping must not tear down the whole batch"
    )
    assert any(f.outcome == "skipped" for f in widget3._batch_files), (
        "the declined file is skipped, and the batch carries on"
    )


# -- FIBR-0252 INV-4 (render half) ------------------------------------------- #


def test_FIBR0252_errors_column_shows_the_count(qtbot, service, profile, tmp_path):
    """FIBR-0252 INV-4 — the review table's Errors column shows the count for a
    Standard Bank file with an unimportable row.

    The separate half of `test_batch_import.py::
    test_FIBR0252_error_count_is_set_for_a_standard_bank_file`, and not a
    duplicate of it: `BatchReviewWidget._number` renders `""` for a zero, so a
    correct `error_count` that never reaches a cell looks identical to the
    defect from the user's side — and the cell is the only half the user sees.

    Two files, because one is a configuration the app never reaches: a
    single-file selection is routed to `_select_file` (the preview flow) by
    `ImportWizardWidget._on_files_chosen`, and `_select_files` is documented for
    two or more. The CSV also keeps the assertion honest — its Errors cell must
    stay blank while the statement's reads `1`.
    """
    # Not discarded by accident: `_acct` creates nothing, it returns the seeded
    # account's id. Calling it asserts the vault HAS an account, which is the
    # precondition for `match_account` to run and find no match — the reason
    # both records stop at `needs_account` rather than going `ready`.
    _acct(service)
    widget = _wizard(qtbot, service)
    widget._select_files(
        [
            str(_SB_FIXTURES / "family_a_zero_fee.pdf"),
            _csv(tmp_path, "plain.csv", _rows(2)),
        ]
    )
    qtbot.waitUntil(
        lambda: (
            len(widget._batch_files) == 2
            and all(f.outcome == "needs_account" for f in widget._batch_files)
        ),
        timeout=3000,
    )
    # Precondition, so a wait that fell through could not leave this leg reading
    # a table SCAN had not filled yet.
    statement = next(
        row
        for row, record in enumerate(widget._batch_files)
        if record.path.endswith("family_a_zero_fee.pdf")
    )
    assert widget._batch_files[statement].parsed is not None, (
        "the fixture must have parsed"
    )

    table = widget._batch_review._table
    cells = [
        table.item(row, import_batch_mod.COL_ERRORS).text()
        for row in range(table.rowCount())
    ]
    assert cells[statement] == "1", (
        f"Errors cells read {cells!r} — the statement's unreadable row must be "
        "counted where the user can see it"
    )
    assert cells[1 - statement] == "", (
        f"Errors cells read {cells!r} — a clean file's cell stays blank, so the "
        "count draws the eye only when it matters"
    )


# -- FIBR-0254 (the per-file report line) ------------------------------------ #


def test_FIBR0254_report_line_owns_its_unreadable_rows(qtbot, service):
    """FIBR-0254 — the unreadable-row clause belongs to the outcome, not to
    `committed` alone, and one row reads as one row.

    `error_count` is set during SCAN, before any outcome is known, and the
    Errors column renders it whatever the outcome turns out to be. Appending
    the clause only on the `committed` branch therefore let an
    `already_imported` row's Status say "nothing new in this file" while the
    cell beside it read 4 — one table row contradicting itself.

    Each leg asserts its own precondition (the count is really on the record,
    the committed line really rendered its counts), because a `report_line`
    that appended nothing at all would otherwise satisfy the negative checks.
    """
    review = _wizard(qtbot, service)._batch_review

    already = BatchFile(path="a.pdf", outcome="already_imported", error_count=4)
    assert already.error_count == 4, "precondition: the Errors cell would read 4"
    assert "4 rows couldn't be read" in review.report_line(already), (
        "an already-imported file with unreadable rows must say so"
    )

    one = BatchFile(path="b.pdf", outcome="already_imported", error_count=1)
    line = review.report_line(one)
    assert "1 row couldn't be read" in line, f"singular expected, got {line!r}"
    assert "1 rows" not in line

    committed = BatchFile(
        path="c.csv",
        outcome="committed",
        error_count=2,
        result=ImportResult(
            inserted_count=3, duplicate_count=0, error_count=2, period_recorded=True
        ),
    )
    committed_line = review.report_line(committed)
    assert "3 added" in committed_line, "precondition: the committed counts render"
    assert "2 rows couldn't be read" in committed_line, (
        "the committed branch keeps the clause it always had"
    )

    clean = BatchFile(path="d.csv", outcome="already_imported", error_count=0)
    assert "couldn't be read" not in review.report_line(clean), (
        "a file with no unreadable rows says nothing about unreadable rows"
    )


def test_file_labels_costs_a_fixed_number_of_passes_over_the_set() -> None:
    """FIBR-0327 — each File label is a question about the whole set: does this
    basename repeat, does the parent disambiguate it, is this one of several
    statements fanned out of the same file.

    Answering it a row at a time re-tallied the set per row, so a batch cost
    O(N^2) on every refresh — and the chain this renders "can be hundreds of
    files long", by ``refresh``'s own account.

    Measured as PASSES OVER THE SET rather than as elapsed time, so the test
    says the same thing on a loaded machine: whatever the labelling costs, it
    must not read the set more times just because the set got longer.
    """

    class _CountingList(list):
        passes = 0

        def __iter__(self):
            type(self).passes += 1
            return super().__iter__()

    def passes_for(count: int) -> int:
        _CountingList.passes = 0
        files = _CountingList(
            BatchFile(path=f"/statements/{i}/statement.pdf") for i in range(count)
        )
        labels = import_batch_mod.file_labels(files)
        assert len(labels) == count, "one label per row, whatever the tally costs"
        return _CountingList.passes

    small, large = passes_for(2), passes_for(60)
    assert small == large, (
        "FIBR-0327: labelling must read the file set a fixed number of times, "
        "not once per row.\n"
        f"  2 files: {small} passes\n  60 files: {large} passes"
    )


def test_account_cell_is_reachable_without_a_mouse(
    qtbot, service, profile, tmp_path, monkeypatch
):
    """FIBR-0327 — a keyboard-only user must be able to place a statement.

    ``cellClicked`` was the only route into ``_choose_account``, and the table
    sets ``NoEditTriggers``, which removes the edit-key route as well. So the
    Account cell could be reached with the arrow keys and there was nothing to
    press once you were on it: a keyboard-only user could not finish a batch at
    all.

    Every other test in this file calls ``_choose_account`` directly, which is
    exactly why the suite never saw this. This one presses a key on the TABLE
    and touches nothing private.
    """
    path = _csv(tmp_path, "a.csv", _rows(2))
    widget = _wizard(qtbot, service)
    widget._select_files([path])
    qtbot.waitUntil(
        lambda: widget._batch_files[0].outcome == "needs_account", timeout=3000
    )
    review = widget._batch_review
    assert review._table.item(0, import_batch_mod.COL_ACCOUNT).text() == "— pick one —"

    _stub_picker(monkeypatch, _acct(service))
    review._table.setCurrentCell(0, import_batch_mod.COL_ACCOUNT)
    qtbot.keyClick(review._table, Qt.Key.Key_Return)

    assert review._table.item(0, import_batch_mod.COL_ACCOUNT).text() == "Default", (
        "FIBR-0327: the Account cell must have a keyboard route — with "
        "NoEditTriggers set, cellClicked alone leaves a keyboard-only user "
        "unable to give any statement a destination"
    )


def test_unplaced_row_opens_a_picker_that_has_chosen_nothing(
    qtbot, service, profile, tmp_path
):
    """FIBR-0327 — the "— pick one —" sentinel must not be a lie.

    An unplaced row passes ``-1`` as the current account, and
    ``select_combo_data`` leaves the selection alone when ``findData`` misses —
    so the picker opened with the FIRST account already chosen and OK live. A
    user who believed the row's own wording and pressed OK filed the statement
    against whichever account happened to come first, silently and
    irreversibly.

    Drives the REAL dialog rather than the stand-in the rest of this file
    patches in: the defect is in the dialog, so a stub cannot carry it.
    """
    path = _csv(tmp_path, "a.csv", _rows(2))
    widget = _wizard(qtbot, service)
    widget._select_files([path])
    qtbot.waitUntil(
        lambda: widget._batch_files[0].outcome == "needs_account", timeout=3000
    )
    review = widget._batch_review
    review._choose_account(0)

    dialog = review.findChild(AccountPickerDialog)
    assert dialog is not None, "the picker must open for an unplaced row"
    assert dialog.selected_account_id() is None, (
        "FIBR-0327: a row with no destination must open a picker with no "
        "account chosen — anything else preselects one the user never picked"
    )
    ok = next(
        button
        for box in dialog.findChildren(QDialogButtonBox)
        if (button := box.button(QDialogButtonBox.StandardButton.Ok)) is not None
    )
    assert not ok.isEnabled(), "OK must not be live while nothing is chosen"

    # The outcome, not the mechanism: confirming an untouched picker must leave
    # the row exactly as unplaced as its own cell says it is.
    dialog.accept()
    assert widget._batch_files[0].account_id is None
    assert review._table.item(0, import_batch_mod.COL_ACCOUNT).text() == "— pick one —"
