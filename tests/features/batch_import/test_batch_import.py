"""FIBR-0085 — batch statement import. Enforces tests/features/batch_import/spec.md.

The headless half: everything in ``services/batch_import.py`` that the design
spec's § 4.1 claims is testable without Qt — the SCAN classify/parse/match
ladder, the stored-password ladder, ``cumulative_counts``, the REVIEW
re-derivation, the caps, and the per-file RUN step. INV-3, INV-5, INV-7, INV-8
and INV-14 drive real widgets and live in ``test_batch_import_ui.py``.

Every fixture is synthetic (INV-12): CSV text built in the body, OFX assembled
from the same tag builders the ``ofx_import`` suite uses, and a **fake** decrypt
in place of any locked PDF — no ``.pdf`` bytes are committed under this
directory at all. One leg (FIBR-0252 INV-4) reaches across to the SB suite's
committed ``family_a_zero_fee.pdf``, the way ``tests/features/forecast`` already
does: a real statement PDF is the only thing that can carry a RowError through
the whole scan ladder, and it is synthetic too. No real statement data, no
network (testing.md § 6).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from conftest import _PW, _acct
from finbreak.importers.base import ParseResult
from finbreak.importers.pdf_importer import PasswordError
from finbreak.models import AccountType, ColumnMapping, TransactionDraft
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.batch_import import (
    BatchImportService,
    next_question,
    stored_passwords,
)
from finbreak.services.import_ import ImportService

pytestmark = pytest.mark.features

_OFX_HEADER = (
    "OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\n"
    "ENCODING:USASCII\r\nCHARSET:1252\r\nCOMPRESSION:NONE\r\nOLDFILEUID:NONE\r\n"
    "NEWFILEUID:NONE\r\n\r\n"
)


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


_HEADER = ["Date", "Details", "Amount"]
_MAPPING = ColumnMapping("Date", "Details", "Amount", None, None, "%Y-%m-%d", False)

# The SB suite's committed synthetic fixtures — nothing is committed under this
# directory (see the module docstring); FIBR-0252 INV-4 reaches across for the
# one statement that carries a RowError.
_SB_FIXTURES = Path(__file__).parent.parent / "standard_bank_pdf" / "fixtures"


@pytest.fixture
def batch(service) -> BatchImportService:
    # Save the profile the CSV fixtures' header matches, so SCAN resolves their
    # mapping the way a returning user's batch does. An UNmatched header is the
    # mapping question, which belongs to ASK — a widget pass, exercised by
    # INV-3's first leg in the UI suite, not here.
    ImportService(service.vault).save_profile("test layout", _HEADER, _MAPPING)
    return BatchImportService(service.vault)


# -- synthetic fixture builders --------------------------------------------- #


def _csv(rows: list[tuple[str, str, str]]) -> str:
    """A minimal three-column statement CSV — the header the seeded import
    profile-less path maps by hand in the tests below."""
    lines = [",".join(_HEADER)]
    lines += [f"{date},{desc},{amount}" for date, desc, amount in rows]
    return "\n".join(lines) + "\n"


def _write(tmp_path: Path, name: str, rows: list[tuple[str, str, str]]) -> str:
    path = tmp_path / name
    path.write_text(_csv(rows), encoding="utf-8")
    return str(path)


def _rows(n: int, *, day_from: int = 1, tag: str = "a") -> list[tuple[str, str, str]]:
    """``n`` distinct rows. ``tag`` varies the description, so two calls with the
    same ``day_from`` and different tags share no dedup key."""
    return [
        (f"2026-01-{day_from + i:02d}", f"{tag}shop{i}", f"-{i + 1}0.00")
        for i in range(n)
    ]


def _ofx_txn(dtposted: str, trnamt: str, name: str, fitid: str) -> str:
    return (
        "<STMTTRN>\n<TRNTYPE>DEBIT\n"
        f"<DTPOSTED>{dtposted}\n<TRNAMT>{trnamt}\n<NAME>{name}\n<FITID>{fitid}\n"
        "</STMTTRN>\n"
    )


def _ofx_stmt(txns: str, acctid: str, start: str, end: str) -> str:
    return (
        "<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>\n"
        f"<STMTRS><CURDEF>ZAR<BANKACCTFROM><BANKID>250655<ACCTID>{acctid}"
        "<ACCTTYPE>CHECKING</BANKACCTFROM>\n"
        f"<BANKTRANLIST><DTSTART>{start}\n<DTEND>{end}\n{txns}</BANKTRANLIST>\n"
        f"<LEDGERBAL><BALAMT>0.00<DTASOF>{end}</LEDGERBAL>\n"
        "</STMTRS></STMTTRNRS></BANKMSGSRSV1>"
    )


def _write_ofx(tmp_path: Path, name: str, *statements: str) -> str:
    path = tmp_path / name
    body = _OFX_HEADER + "<OFX>\n" + "\n".join(statements) + "\n</OFX>\n"
    path.write_bytes(body.encode())
    return str(path)


# -- driver helpers ---------------------------------------------------------- #
#
# The widget arms one `QTimer.singleShot(0, self, ...)` per turn (§ 4.7); a
# headless test walks the same per-index steps in a plain loop, so both drive
# byte-identical service code.


def _scan_all(batch, files) -> None:
    index = 0
    while index < len(files):
        index = batch.scan_step(files, index)


def _run_all(batch, files) -> None:
    index = 0
    while index < len(files):
        index = batch.run_step(files, index)


def _place(batch, files, account_id: int) -> None:
    """Settle every `needs_account` record on `account_id` — the review-screen
    step every CSV batch needs, since a CSV carries no account number (§ 3
    decision 5)."""
    for record in files:
        if record.outcome == "needs_account":
            batch.set_account(record, account_id)


def _count_rows(conn, account_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE account_id = ?", (account_id,)
    ).fetchone()[0]


# -- INV-1 / INV-2 ----------------------------------------------------------- #


def test_INV1_failure_does_not_abort_batch(service, batch, tmp_path, monkeypatch):
    """A file whose commit raises does not stop the batch — the later files are
    still attempted, and the failure is recorded on the failing record only.

    Breaks when the run step lets the exception out of the per-file call, so the
    chain is never re-armed and files 3..N are silently dropped.
    """
    account = _acct(service)
    paths = [
        _write(tmp_path, "a.csv", _rows(2, day_from=1, tag="a")),
        _write(tmp_path, "b.csv", _rows(2, day_from=5, tag="b")),
        _write(tmp_path, "c.csv", _rows(2, day_from=9, tag="c")),
    ]
    real_commit = ImportService.commit_import

    def wedged(self, preview, period_start, period_end, source_filename):
        if Path(source_filename).name == "b.csv":
            raise ValueError("this statement could not be committed")
        return real_commit(self, preview, period_start, period_end, source_filename)

    monkeypatch.setattr(ImportService, "commit_import", wedged)

    files = batch.build(paths)
    _scan_all(batch, files)
    _place(batch, files, account)
    batch.review(files)
    _run_all(batch, files)

    outcomes = [record.outcome for record in files]
    assert outcomes == ["committed", "failed", "committed"], (
        f"outcomes = {outcomes}, expected the middle file to fail alone"
    )
    assert "could not be committed" in files[1].reason, (
        f"the failed record's reason = {files[1].reason!r}, expected the "
        "commit's own message"
    )
    assert files[0].result is not None and files[2].result is not None, (
        "the files either side of the failure must carry their ImportResult"
    )


def test_INV2_per_file_transaction_boundary(service, batch, tmp_path, monkeypatch):
    """Each file commits in its own transaction: after the mid-batch failure of
    INV-1, the earlier files' rows AND their statement_periods records are
    present, and the failed file has written neither.

    Breaks when the run is wrapped in an outer `owned_transaction`, whose bare
    BEGIN would raise on the first inner call.
    """
    account = _acct(service)
    paths = [
        _write(tmp_path, "a.csv", _rows(2, day_from=1, tag="a")),
        _write(tmp_path, "b.csv", _rows(2, day_from=5, tag="b")),
        _write(tmp_path, "c.csv", _rows(2, day_from=9, tag="c")),
    ]
    real_commit = ImportService.commit_import

    def wedged(self, preview, period_start, period_end, source_filename):
        if Path(source_filename).name == "b.csv":
            raise ValueError("this statement could not be committed")
        return real_commit(self, preview, period_start, period_end, source_filename)

    monkeypatch.setattr(ImportService, "commit_import", wedged)

    files = batch.build(paths)
    _scan_all(batch, files)
    _place(batch, files, account)
    batch.review(files)
    _run_all(batch, files)

    # RE-OPEN the vault before asserting. Querying the connection that did the
    # writing proves nothing about transaction boundaries: the vault runs with
    # `isolation_level = ""`, so that connection can see its OWN uncommitted
    # writes. Against a run wrapped in a single never-committed outer
    # transaction, a same-connection assertion passes and the invariant is
    # vacuous — only a fresh connection reads what actually landed on disk.
    service.lock()
    assert service.unlock(bytearray(_PW)) is True
    conn = service.vault.connection

    assert _count_rows(conn, account) == 4, (
        "only the two surviving files' rows may be present (2 + 2)"
    )
    sources = sorted(
        row[0]
        for row in conn.execute(
            "SELECT source_filename FROM statement_periods WHERE account_id = ?",
            (account,),
        )
    )
    assert sources == ["a.csv", "c.csv"], (
        f"statement_periods = {sources}, expected no row for the failed file"
    )


# -- INV-4 ------------------------------------------------------------------- #


def test_INV4_reviewed_counts_are_the_committed_counts(
    service, batch, tmp_path
) -> None:
    """The New AND Duplicate counts on the review step are what the run
    delivers, for two files in one batch that overlap each other.

    Watched failing twice, per the design spec's § 7: once with
    `cumulative_counts` removed entirely (the second file then reads 8 new · 0
    duplicate, against the empty vault both previews were built for), and once
    with only `new_count` made cumulative (4 new · 0 duplicate — the four shared
    rows vanish from New without appearing under Duplicate, so the row no longer
    accounts for the file's transactions at all). The second assertion below is
    the one that catches the second shape.
    """
    account = _acct(service)
    shared = _rows(4, day_from=1, tag="s")
    first = _write(tmp_path, "jan.csv", shared + _rows(2, day_from=20, tag="x"))
    second = _write(tmp_path, "janfeb.csv", shared + _rows(4, day_from=24, tag="y"))

    files = batch.build([first, second])
    _scan_all(batch, files)
    _place(batch, files, account)
    batch.review(files)

    reviewed = [(f.new_count, f.duplicate_count) for f in files]
    assert reviewed == [(6, 0), (4, 4)], (
        f"reviewed (new, duplicate) = {reviewed}, expected the second file's "
        "four shared rows under Duplicate and not under New"
    )

    _run_all(batch, files)

    for record in files:
        assert record.result is not None, f"{record.path} did not commit"
        assert (record.result.inserted_count, record.result.duplicate_count) == (
            record.new_count,
            record.duplicate_count,
        ), (
            f"{Path(record.path).name}: committed "
            f"({record.result.inserted_count}, {record.result.duplicate_count}) "
            f"!= reviewed ({record.new_count}, {record.duplicate_count})"
        )
    total = _count_rows(service.vault.connection, account)
    assert total == sum(f.new_count for f in files) == 10, (
        f"vault holds {total} rows, expected the sum of the reviewed New counts"
    )


# -- INV-9 ------------------------------------------------------------------- #


def test_INV9_stored_passwords_tried_once_each(service, batch, tmp_path, monkeypatch):
    """Each DISTINCT remembered password is tried at most once per file, before
    any prompt — three accounts, two of them holding the same string.

    Watched failing with the de-duplication removed from `stored_passwords`:
    the working password is the LAST one, so an undeduped ladder makes three
    password-bearing attempts rather than two. The no-password attempt that
    opens the ladder is not counted — asserting a bare total of two would fail
    against conforming code, which makes three calls in all.
    """
    accounts = AccountService(service.vault)
    for name, password in (("A", "alpha"), ("B", "alpha"), ("C", "bravo")):
        account = accounts.add_account(name, AccountType.CURRENT.value)
        accounts.set_pdf_password(account.id, password)

    attempts: list[str] = []

    def fake_decrypt(data, password=None):
        if password:
            attempts.append(password)
        if password != "bravo":
            raise PasswordError("bad password")
        return b"%PDF-plaintext"

    class _StubSb:
        def parse(self, plaintext, exponent, password=None):
            return ParseResult(
                drafts=[TransactionDraft(1, "2026-01-01", -1000, "shop")],
                errors=[],
                period_start="2026-01-01",
                period_end="2026-01-31",
            )

    monkeypatch.setattr(
        "finbreak.services.batch_import.PdfImporter.decrypt_to_plaintext",
        staticmethod(fake_decrypt),
    )
    monkeypatch.setattr("finbreak.services.batch_import.StandardBankImporter", _StubSb)

    locked = tmp_path / "locked.pdf"
    locked.write_bytes(b"%PDF-1.7 encrypted")

    files = batch.build([str(locked)])
    _scan_all(batch, files)

    assert attempts == ["alpha", "bravo"], (
        f"password-bearing decrypt attempts = {attempts}, expected each distinct "
        "stored password once, in account order"
    )
    assert files[0].outcome != "needs_password", (
        "a stored password unlocked the file, so no prompt may be raised"
    )


def test_INV9_stored_passwords_dedups_and_keeps_order() -> None:
    """The primitive on its own — the de-duplication INV-9 rests on."""
    stored = {1: "alpha", 2: "alpha", 3: "bravo", 4: None}
    assert stored_passwords(
        [type("A", (), {"id": i})() for i in (1, 2, 3, 4)], stored.get
    ) == ["alpha", "bravo"]


# -- INV-10 ------------------------------------------------------------------ #


def test_INV10_already_imported_is_recomputed_both_ways(service, batch, tmp_path):
    """`already_imported` is re-derived in BOTH directions on every REVIEW pass.

    Three legs, one per way the two-part test can move: an unchanged re-import
    reports `already_imported`; the same span re-issued with extra rows reports
    `ready`; and a record sitting at `already_imported` that is RETARGETED to a
    different account returns to `ready` and commits its rows. The third leg is
    what a one-way `ready -> already_imported` flip loses — silently, since RUN
    commits only `ready` records.
    """
    accounts = AccountService(service.vault)
    first = _acct(service)
    second = accounts.add_account("Second", AccountType.CURRENT.value).id
    rows = _rows(3, day_from=1, tag="r")
    path = _write(tmp_path, "jan.csv", rows)

    # Land it once, so the span and its rows exist.
    files = batch.build([path])
    _scan_all(batch, files)
    _place(batch, files, first)
    batch.review(files)
    _run_all(batch, files)
    assert files[0].outcome == "committed"

    # Leg 1 — the identical file again: the span exists and nothing is new.
    again = batch.build([path])
    _scan_all(batch, again)
    _place(batch, again, first)
    batch.review(again)
    assert again[0].outcome == "already_imported", (
        f"outcome = {again[0].outcome}, expected the unchanged re-import to "
        "report already_imported"
    )

    # Leg 2 — the same span re-issued with three extra transactions.
    reissued = _write(
        tmp_path, "jan-reissued.csv", rows + _rows(3, day_from=1, tag="extra")
    )
    grown = batch.build([reissued])
    _scan_all(batch, grown)
    _place(batch, grown, first)
    batch.review(grown)
    assert grown[0].outcome == "ready", (
        f"outcome = {grown[0].outcome}, expected a re-issue carrying new rows "
        "over the same dates to stay importable"
    )

    # Leg 3 — retarget the already_imported record to the OTHER account.
    batch.set_account(again[0], second)
    batch.review(again)
    assert again[0].outcome == "ready", (
        f"outcome = {again[0].outcome}, expected a retargeted record to return "
        "to ready — a one-way flip strands it unimportable forever"
    )
    _run_all(batch, again)
    assert _count_rows(service.vault.connection, second) == 3, (
        "the retargeted record's rows must land in the account it now names"
    )


def test_INV10_a_peers_retarget_returns_a_record_to_ready(service, batch, tmp_path):
    """The transition `review` alone must make — and the one leg 3 above cannot.

    Leg 3 calls `set_account` on the very record it then checks, and
    `set_account` already sets `ready` itself, so a one-way `review` (flip to
    `already_imported`, never back) passes it. The move that ONLY `review` can
    make is on a record nobody touched: X is `already_imported` because a batch
    PEER claimed its drafts, the peer is retargeted elsewhere, X's cumulative
    new count rises again, and X must return to `ready`.

    Under a one-way derivation X stays `already_imported` forever and RUN — which
    commits only `ready` records — drops it without a word. That is the silent
    data loss INV-10 exists for.
    """
    accounts = AccountService(service.vault)
    first = _acct(service)
    second = accounts.add_account("Second", AccountType.CURRENT.value).id

    # An earlier import records the SPAN for `first` while carrying different
    # rows — so the span-exists half of the two-part test holds for P and X
    # without their rows being in the vault.
    # The SAME date span as P and X below (three rows from 2026-01-01), with
    # different descriptions — so it records the span without contributing any
    # matching dedup key. A shorter file would record a DIFFERENT span and
    # `id_for_span` would miss, leaving X plain `ready`.
    span_only = _write(tmp_path, "span.csv", _rows(3, day_from=1, tag="z"))
    seed = batch.build([span_only])
    _scan_all(batch, seed)
    _place(batch, seed, first)
    batch.review(seed)
    _run_all(batch, seed)

    # P and X are identical files covering that same span.
    shared = _rows(3, day_from=1, tag="p")
    peer = _write(tmp_path, "p.csv", shared)
    twin = _write(tmp_path, "x.csv", shared)
    files = batch.build([peer, twin])
    _scan_all(batch, files)
    _place(batch, files, first)
    batch.review(files)

    p, x = files
    assert (p.outcome, x.outcome) == ("ready", "already_imported"), (
        f"outcomes = {(p.outcome, x.outcome)} — the precondition is that X is "
        "already_imported ONLY because its peer claimed the same drafts"
    )

    # Retarget the PEER. Nothing touches X.
    batch.set_account(p, second)
    batch.review(files)

    assert x.outcome == "ready", (
        f"X's outcome = {x.outcome}. Its peer moved to another account, so its "
        "rows are new again — a one-way derivation strands it unimportable"
    )
    _run_all(batch, files)
    assert x.result is not None and x.result.inserted_count == 3, (
        "X must commit the rows the review screen said it would"
    )


# -- INV-11 ------------------------------------------------------------------ #


def test_INV11_batch_caps(service, batch, tmp_path, monkeypatch):
    """Both caps bind, and neither raises.

    Leg 1 pins that the file cap counts SELECTED FILES and is applied before
    anything is read: the 201 paths do not exist, so a build that touched the
    disk would report `failed`, not `not_attempted`. Leg 2 drives the draft cap
    with a small stand-in — INV-11 proves the cap is enforced, not that 200,000
    is the right number (design spec § 11).
    """
    # Leg 1 — over the file cap. The refusal must SURVIVE THE SCAN: marking the
    # records in `build` and then letting the chain read them anyway leaves the
    # cap purely decorative. Real, REAL files here, so "nothing was read" is
    # observable as `parsed is None` rather than as an incidental failure.
    over = [
        _write(tmp_path, f"over{i:03d}.csv", _rows(1, day_from=1, tag=f"o{i}"))
        for i in range(201)
    ]
    refused = batch.build(over)
    assert len(refused) == 201
    assert {record.outcome for record in refused} == {"not_attempted"}
    assert "limit" in refused[0].reason, (
        f"reason = {refused[0].reason!r}, expected it to name the size limit"
    )
    _scan_all(batch, refused)
    assert {record.outcome for record in refused} == {"not_attempted"}, (
        "the scan re-scanned a refused batch — the file cap is decorative if "
        "SCAN does not honour it"
    )
    assert all(record.parsed is None for record in refused), (
        "a refused file must never be read, let alone parsed and held in memory"
    )

    # Leg 1b — the boundary. EXACTLY the cap is allowed; a `>=` comparison here
    # would refuse a legitimate 200-file batch, which is a user-visible bug the
    # over-cap leg alone cannot see.
    at_cap = [str(tmp_path / f"over{i:03d}.csv") for i in range(200)]
    assert {r.outcome for r in batch.build(at_cap)} == {"waiting"}, (
        "a selection of exactly the cap is allowed through"
    )

    # Leg 2 — the draft cap. `>=` before each file, per INV-11's "once 200,000
    # are held"; the stand-in is small because INV-11 proves the cap is
    # enforced, not that 200,000 is well chosen (design spec § 11).
    monkeypatch.setattr("finbreak.services.batch_import._MAX_BATCH_DRAFTS", 4)
    paths = [
        _write(tmp_path, f"{n}.csv", _rows(2, day_from=1 + 4 * i, tag=n))
        for i, n in enumerate(("a", "b", "c"))
    ]
    files = batch.build(paths)
    _scan_all(batch, files)

    # 2 drafts after a (< 4, so b is scanned), 4 after b (>= 4, so c is not).
    # This pins the comparison as well as the cap: under `>` rather than `>=`,
    # c would be scanned too.
    assert files[2].outcome == "not_attempted", (
        f"outcome = {files[2].outcome}, expected the scan to stop once the "
        "draft cap was reached"
    )
    assert "limit" in files[2].reason
    assert files[0].parsed is not None and files[1].parsed is not None, (
        "the files scanned before the cap keep their parse"
    )
    assert files[2].parsed is None, "the capped file must not have been read"


def test_INV11_the_draft_cap_binds_an_answered_file_too(
    service, batch, tmp_path, monkeypatch
):
    """§ 4.3: an answered file "runs the rest of the ladder, INCLUDING the
    draft-cap check".

    The cap lives on the scan STEP, but ASK re-enters the ladder through
    `answer`, which is a different door. Without the check there, a batch of
    unmapped CSVs walks past the cap by one file per question answered — the
    memory bound § 10 argues for is then not a bound at all.
    """
    monkeypatch.setattr("finbreak.services.batch_import._MAX_BATCH_DRAFTS", 3)
    # An unmatched header, so this file is a mapping QUESTION rather than a scan.
    # Names chosen so the UNMAPPED file sorts FIRST: it must reach
    # `needs_mapping` while the batch is still under the cap, and the big file
    # must push it over afterwards. Reversed, the scan cap refuses the odd file
    # before it can become a question and the ASK door is never exercised.
    odd = tmp_path / "a-odd.csv"
    odd.write_text("When,What,How much\n2026-01-02,shop,-10.00\n", encoding="utf-8")
    paths = [str(odd), _write(tmp_path, "b-big.csv", _rows(4, day_from=1, tag="b"))]

    files = batch.build(paths)
    _scan_all(batch, files)
    held = batch.draft_total(files)
    assert held >= 3, "precondition: the first file alone already reaches the cap"

    pending = next_question(files)
    assert pending is not None and pending.outcome == "needs_mapping"
    batch.answer(
        files,
        pending,
        ColumnMapping("When", "What", "How much", None, None, "%Y-%m-%d", False),
    )

    assert batch.draft_total(files) == held, (
        f"drafts grew {held} -> {batch.draft_total(files)} — an answered file "
        "parsed past the cap the scan had already stopped at"
    )
    assert pending.outcome == "not_attempted", (
        f"outcome = {pending.outcome}, expected the answered file to be refused "
        "by the same cap the scan honours"
    )


def test_INV3_nothing_is_importable_until_every_file_is_settled(
    service, batch, tmp_path
):
    """`Import all` must stay off while ANY record is still unsettled —
    including one merely `waiting` to be scanned.

    This is the headless half of INV-3, and it is what stops RUN starting
    mid-SCAN. The batch table is on screen from the first scan turn (§ 6), so a
    button enabled the moment file 1 matches is a button the user can press
    while thirty files are still unread: the run then commits against a review
    table showing New = 0 for every row (nothing has been counted yet), which is
    a direct INV-4 breach, and every later file is silently never asked.

    An OFX file is used because it carries its own account number and so reaches
    `ready` unaided — a CSV always stops at `needs_account`, which would gate the
    button on a different clause and make the test vacuous.
    """
    accounts = AccountService(service.vault)
    accounts.add_account("One", AccountType.CURRENT.value, account_number="000123456")

    matched = _write_ofx(
        tmp_path,
        "bank.ofx",
        _ofx_stmt(
            _ofx_txn("20260105", "-10.00", "shop one", "F1"),
            "000123456",
            "20260101",
            "20260131",
        ),
    )
    later = _write(tmp_path, "zz-later.csv", _rows(2, day_from=10, tag="l"))

    files = batch.build([matched, later])
    index = batch.scan_step(files, 0)  # ONE turn: file 1 only
    assert files[0].outcome == "ready", "precondition: the OFX matched its account"
    assert files[index].outcome == "waiting", "precondition: file 2 is unscanned"

    assert not BatchImportService.can_import(files), (
        "Import all was live with a file still waiting to be scanned — RUN can "
        "then start while the SCAN chain is still armed"
    )


# -- INV-13 ------------------------------------------------------------------ #


def test_INV13_undated_file_fails_before_commit(service, batch, tmp_path, monkeypatch):
    """A record whose parse yields EITHER period endpoint None never reaches
    `commit_import` — two legs, one per endpoint, since both are independently
    `str | None`.

    Breaks when either endpoint is passed through: it reaches
    `ImportService._validate_span`, whose `date.fromisoformat(None)` surfaces
    "period endpoints must be valid ISO-8601 dates" — a message about malformed
    dates for a file that had none at all. Guarding only `period_start` leaves
    the second leg red.
    """
    account = _acct(service)
    commits: list[str] = []
    real_commit = ImportService.commit_import

    def counting(self, preview, period_start, period_end, source_filename):
        commits.append(source_filename)
        return real_commit(self, preview, period_start, period_end, source_filename)

    monkeypatch.setattr(ImportService, "commit_import", counting)

    # Leg 1 — a real CSV whose every date is unparseable, so the parse yields no
    # dated row and both endpoints come back None.
    undated = _write(tmp_path, "undated.csv", [("not-a-date", "shop", "-10.00")] * 2)
    files = batch.build([undated])
    _scan_all(batch, files)
    assert files[0].outcome == "failed", (
        f"outcome = {files[0].outcome}, expected an undated file to fail at SCAN"
    )
    assert "date" in files[0].reason.lower(), (
        f"reason = {files[0].reason!r}, expected it to name the absent dates"
    )

    # Leg 2 — a start with no end. Only a synthetic ParseResult can produce it:
    # a real parse sets both endpoints or neither.
    class _HalfDated:
        def parse(self, text, mapping, exponent):
            return ParseResult(
                drafts=[TransactionDraft(1, "2026-01-01", -1000, "shop")],
                errors=[],
                period_start="2026-01-01",
                period_end=None,
            )

    monkeypatch.setattr("finbreak.services.batch_import.CsvImporter", _HalfDated)
    half = _write(tmp_path, "half.csv", _rows(1))
    files = batch.build([half])
    _scan_all(batch, files)
    _place(batch, files, account)
    batch.review(files)
    _run_all(batch, files)

    assert files[0].outcome == "failed", (
        f"outcome = {files[0].outcome}, expected a half-dated parse to fail too"
    )
    assert commits == [], (
        f"commit_import was called for {commits}, expected an undated record "
        "never to reach it"
    )


# -- INV-15 ------------------------------------------------------------------ #


def test_INV15_multi_statement_ofx_fans_out(service, batch, tmp_path):
    """One OFX file carrying N statements produces N records, each with its own
    account, preview and review row. No statement is discarded.

    Breaks when SCAN stores `OfxImporter.parse`'s LIST into the single `parsed`
    slot and keeps only `[0]` — which reads as natural, because every other
    format returns one ParseResult.
    """
    accounts = AccountService(service.vault)
    one = accounts.add_account(
        "One", AccountType.CURRENT.value, account_number="000123456"
    ).id
    two = accounts.add_account(
        "Two", AccountType.SAVINGS.value, account_number="000999888"
    ).id

    path = _write_ofx(
        tmp_path,
        "bank.ofx",
        _ofx_stmt(
            _ofx_txn("20260105", "-10.00", "shop one", "F1"),
            "000123456",
            "20260101",
            "20260131",
        ),
        _ofx_stmt(
            _ofx_txn("20260206", "-20.00", "shop two", "F2")
            + _ofx_txn("20260207", "-30.00", "shop three", "F3"),
            "000999888",
            "20260201",
            "20260228",
        ),
    )

    files = batch.build([path])
    _scan_all(batch, files)

    assert len(files) == 2, (
        f"{len(files)} record(s) for a two-statement OFX — every statement after "
        "the first was discarded"
    )
    assert [f.statement_index for f in files] == [0, 1]
    assert [f.path for f in files] == [path, path], (
        "both records share the file they were fanned out of"
    )
    assert {f.account_id for f in files} == {one, two}, (
        f"account_ids = {[f.account_id for f in files]}, expected each statement "
        "matched to its own account by its printed number"
    )

    batch.review(files)
    _run_all(batch, files)

    conn = service.vault.connection
    assert (_count_rows(conn, one), _count_rows(conn, two)) == (1, 2), (
        "each statement's rows land in its own account"
    )
    periods = StatementPeriodRepository(conn)
    assert periods.id_for_span(one, "2026-01-01", "2026-01-31") is not None
    assert periods.id_for_span(two, "2026-02-01", "2026-02-28") is not None


# -- FIBR-0252 INV-4 (service half) ------------------------------------------ #


def test_FIBR0252_error_count_is_set_for_a_standard_bank_file(service, batch):
    """FIBR-0252 INV-4 — a Standard Bank file with an unimportable row lands a
    non-zero `error_count` on its record.

    `error_count` is a FIBR-0085 § 4.2 deliverable that had no test at all, and
    on the Standard Bank path it was a constant zero: `_settle_parse` sets it
    from `len(parsed.errors)`, and `StandardBankImporter.parse` returned `[]`.

    Goes through the REAL `PdfImporter.decrypt_to_plaintext` via `_scan_pdf` —
    the fixture is unencrypted, so the `password=None` rung of the ladder returns
    usable plaintext and this suite's fake decrypt is not involved.

    The rendered half of INV-4 is `test_batch_import_ui.py::
    test_FIBR0252_errors_column_shows_the_count`: `BatchReviewWidget._number`
    returns `""` for a zero, so the field and its rendering are separate claims
    and only the second is what the user sees.
    """
    _acct(service)
    files = batch.build([str(_SB_FIXTURES / "family_a_zero_fee.pdf")])
    _scan_all(batch, files)

    assert len(files) == 1
    assert files[0].error_count == 1, (
        f"error_count = {files[0].error_count} — the statement's waived-fee row "
        "was dropped without being counted"
    )
