"""FIBR-0085 — batch statement import. Enforces tests/features/batch_import/spec.md.

The headless half: everything in ``services/batch_import.py`` that the design
spec's § 4.1 claims is testable without Qt — the SCAN classify/parse/match
ladder, the stored-password ladder, ``cumulative_counts``, the REVIEW
re-derivation, the caps, and the per-file RUN step. INV-3, INV-5, INV-7, INV-8
and INV-14 drive real widgets and live in ``test_batch_import_ui.py``.

Every fixture is synthetic (INV-12): CSV text built in the body, OFX assembled
from the same tag builders the ``ofx_import`` suite uses, and a **fake** decrypt
in place of any locked PDF — no ``.pdf`` bytes are committed under this
directory at all. No real statement data, no network (testing.md § 6).
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


# -- INV-11 ------------------------------------------------------------------ #


def test_INV11_batch_caps(service, batch, tmp_path, monkeypatch):
    """Both caps bind, and neither raises.

    Leg 1 pins that the file cap counts SELECTED FILES and is applied before
    anything is read: the 201 paths do not exist, so a build that touched the
    disk would report `failed`, not `not_attempted`. Leg 2 drives the draft cap
    with a small stand-in — INV-11 proves the cap is enforced, not that 200,000
    is the right number (design spec § 11).
    """
    missing = [str(tmp_path / f"nope{i:03d}.csv") for i in range(201)]
    refused = batch.build(missing)
    assert len(refused) == 201
    assert {record.outcome for record in refused} == {"not_attempted"}, (
        "an over-cap selection is refused whole, before any file is read"
    )
    assert "limit" in refused[0].reason, (
        f"reason = {refused[0].reason!r}, expected it to name the size limit"
    )

    monkeypatch.setattr("finbreak.services.batch_import._MAX_BATCH_DRAFTS", 3)
    paths = [
        _write(tmp_path, f"{n}.csv", _rows(2, day_from=1 + 4 * i, tag=n))
        for i, n in enumerate(("a", "b", "c"))
    ]
    files = batch.build(paths)
    _scan_all(batch, files)

    assert files[2].outcome == "not_attempted", (
        f"outcome = {files[2].outcome}, expected the scan to stop once the "
        "draft cap was reached"
    )
    assert "limit" in files[2].reason
    assert files[0].parsed is not None and files[1].parsed is not None, (
        "the files scanned before the cap keep their parse"
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
