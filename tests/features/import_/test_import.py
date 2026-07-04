"""FIBR-0007 — P05 CSV import. Enforces tests/features/import_/spec.md.

The pure `CsvImporter` (text + `ColumnMapping` -> `ParseResult`), the
`ImportService` orchestrator (match/save profiles, multiset-delta dedup, the
atomic write + coverage-period record), the `import_profiles` /
`statement_periods` repositories, the extended `TransactionRepository`, the
v3->v4 forward migration, and the non-modal import-wizard screen. Headless
layers tested directly; the wizard round-trips (INV-10) use the pytest-qt
`qtbot` fixture. Every on-disk vault uses `tmp_path`; CSV fixtures are tiny
in-repo strings — no real financial data, no network (testing.md § 6).
"""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from conftest import _PW, build_v3_vault, keyed_connection
from finbreak.crypto import SALT_LEN, derive_key
from finbreak.importers.csv_importer import CsvImporter, read_header
from finbreak.migrations import LATEST_SCHEMA_VERSION, run_migrations
from finbreak.models import ColumnMapping
from finbreak.repositories.import_profiles import ImportProfileRepository
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.import_ import ImportService, signature_for
from finbreak.services.transactions import TransactionService

pytestmark = pytest.mark.features

HEADER = ["Date", "Details", "Amount"]
SINGLE = ColumnMapping("Date", "Details", "Amount", None, None, "%Y-%m-%d", False)
DC_HEADER = ["Date", "Details", "Debit", "Credit"]
DEBIT_CREDIT = ColumnMapping(
    "Date", "Details", None, "Debit", "Credit", "%Y-%m-%d", False
)


@pytest.fixture
def paths(tmp_path) -> tuple[Path, Path]:
    return tmp_path / "vault.db", tmp_path / "vault.kdf.json"


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates straight to v4
    yield svc
    svc.lock()


def _csv(header: list[str], rows: list[list[str]]) -> str:
    return "\n".join([",".join(header)] + [",".join(r) for r in rows]) + "\n"


def _acct(service: AuthService) -> int:
    return AccountService(service.vault).list_accounts()[0].id


def _do_import(imp: ImportService, text: str, mapping, account_id, source="stmt.csv"):
    preview = imp.preview(text, mapping, account_id)
    # Every _do_import call-site imports at least one row, so the derived period
    # is present — assert it (documents the precondition + narrows str | None).
    assert preview.period_start is not None and preview.period_end is not None
    return imp.commit_import(preview, preview.period_start, preview.period_end, source)


def _write_csv(tmp_path: Path, name: str, header, rows) -> Path:
    path = tmp_path / name
    path.write_text(_csv(header, rows), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# INV-1 — profile CRUD + signature round-trip + upsert
# --------------------------------------------------------------------------- #
def test_INV1_profile_repo_crud_and_signature_lookup(service):
    repo = ImportProfileRepository(service.vault.connection)
    sig = signature_for(HEADER)
    pid = repo.add("MyBank", sig, SINGLE)
    assert isinstance(pid, int)

    got = repo.get(pid)
    assert got is not None
    assert got.name == "MyBank" and got.signature == sig
    assert got.date_column == "Date" and got.description_column == "Details"
    assert got.amount_column == "Amount"
    assert got.debit_column is None and got.credit_column is None
    assert got.date_format == "%Y-%m-%d" and got.invert_amount == 0
    assert got.created_at, "created_at is a well-formed timestamp"

    assert [p.id for p in repo.list_all()] == [pid]
    assert repo.get_by_signature(sig).id == pid
    assert repo.get_by_signature("no-such-signature") is None

    # column_mapping() round-trips the mapping recipe back out of the record.
    mapping = got.column_mapping()
    assert mapping.amount_column == "Amount" and mapping.debit_column is None


def test_INV1_save_profile_upserts_by_signature(service):
    imp = ImportService(service.vault)
    imp.save_profile("First", HEADER, SINGLE)
    # A second save under the SAME header/signature updates in place, not a dup.
    other = ColumnMapping("Date", "Details", "Amount", None, None, "%d/%m/%Y", True)
    imp.save_profile("Second", HEADER, other)

    rows = ImportProfileRepository(service.vault.connection).list_all()
    assert len(rows) == 1, "upsert-by-signature, not a duplicate row"
    assert rows[0].name == "Second", "name overwritten"
    assert rows[0].date_format == "%d/%m/%Y" and rows[0].invert_amount == 1


def test_INV1_match_profile_returns_saved_none_or_raises(service):
    imp = ImportService(service.vault)
    assert imp.match_profile(HEADER) is None, "no profile yet"
    imp.save_profile("MyBank", HEADER, SINGLE)
    matched = imp.match_profile(HEADER)
    assert matched is not None and matched.name == "MyBank"
    assert imp.match_profile(["Other", "Columns"]) is None
    with pytest.raises(ValueError):
        imp.match_profile(["Date", "Amount", "Amount"])  # duplicate header names


# --------------------------------------------------------------------------- #
# INV-2 — signature is the exact header fingerprint
# --------------------------------------------------------------------------- #
def test_INV2_signature_is_exact_fingerprint():
    base = signature_for(["Date", "Amount", "Details"])
    assert base == signature_for(["Date", "Amount", "Details"]), "identical -> equal"
    assert base != signature_for(["date", "amount", "details"]), "case is significant"
    assert base != signature_for([" Date ", "Amount", "Details"]), "spacing significant"
    assert base != signature_for(["Amount", "Date", "Details"]), "order is significant"


def test_INV2_duplicate_header_names_refused():
    with pytest.raises(ValueError):
        signature_for(["Date", "Amount", "Amount"])


# --------------------------------------------------------------------------- #
# INV-3 — CSV parsing to transaction drafts
# --------------------------------------------------------------------------- #
def test_INV3_draft_fields_row_number_and_stripped_description():
    text = _csv(HEADER, [["2026-01-01", "  Coffee  ", "-10.00"]])
    draft = CsvImporter().parse(text, SINGLE, 2).drafts[0]
    assert draft.row_number == 1, "1-based over data rows"
    assert draft.occurred_on == "2026-01-01"
    assert draft.amount_minor == -1000
    assert draft.description == "Coffee", "parse_transaction trims the description"


def test_INV3a_signed_amount_keeps_sign_and_inverts():
    text = _csv(
        HEADER, [["2026-01-01", "In", "+123.45"], ["2026-01-02", "Out", "-10.00"]]
    )
    result = CsvImporter().parse(text, SINGLE, 2)
    assert [d.amount_minor for d in result.drafts] == [12345, -1000]
    assert result.errors == []
    inv = ColumnMapping("Date", "Details", "Amount", None, None, "%Y-%m-%d", True)
    inverted = CsvImporter().parse(
        _csv(HEADER, [["2026-01-01", "x", "123.45"]]), inv, 2
    )
    assert inverted.drafts[0].amount_minor == -12345


def test_INV3b_debit_negative_credit_positive():
    text = _csv(
        DC_HEADER,
        [["2026-01-01", "ATM", "10.00", ""], ["2026-01-02", "Pay", "", "200.00"]],
    )
    result = CsvImporter().parse(text, DEBIT_CREDIT, 2)
    assert [d.amount_minor for d in result.drafts] == [-1000, 20000]
    assert result.errors == []


def test_INV3c_date_format_reemitted_iso():
    mapping = ColumnMapping("Date", "Details", "Amount", None, None, "%d/%m/%Y", False)
    result = CsvImporter().parse(
        _csv(HEADER, [["31/01/2026", "Rent", "-100.00"]]), mapping, 2
    )
    assert result.drafts[0].occurred_on == "2026-01-31"


def test_INV3d_over_precise_amount_is_row_error_not_rounded():
    result = CsvImporter().parse(
        _csv(HEADER, [["2026-01-01", "Odd", "1.234"]]), SINGLE, 2
    )
    assert result.drafts == [], "not silently rounded to 1.23"
    assert [e.row_number for e in result.errors] == [1]


def test_INV3_period_is_min_max_of_draft_dates():
    rows = [
        ["2026-01-05", "a", "-1.00"],
        ["2026-01-02", "b", "-1.00"],
        ["2026-01-09", "c", "-1.00"],
    ]
    result = CsvImporter().parse(_csv(HEADER, rows), SINGLE, 2)
    assert result.period_start == "2026-01-02" and result.period_end == "2026-01-09"


# --------------------------------------------------------------------------- #
# INV-4 — per-row errors collected, never silent; valid rows still import
# --------------------------------------------------------------------------- #
def test_INV4_row_errors_collected_valid_rows_still_import():
    rows = [
        ["2026-01-01", "Good", "-10.00"],  # 1 ok
        ["nope", "BadDate", "-1.00"],  # 2 unparseable date
        ["2026-01-03", "", "-1.00"],  # 3 blank description
        ["2026-01-04", "BadAmt", "abc"],  # 4 non-numeric (InvalidOperation)
        ["2026-01-05", "Zero", "0.00"],  # 5 zero amount
        ["2026-01-06", "Good2", "5.00"],  # 6 ok
    ]
    result = CsvImporter().parse(_csv(HEADER, rows), SINGLE, 2)
    assert [d.row_number for d in result.drafts] == [1, 6], "valid rows still import"
    assert sorted(e.row_number for e in result.errors) == [2, 3, 4, 5]


def test_INV4_short_ragged_row_is_error_not_crash():
    # A row with fewer cells than the header -> DictReader pads with None; the
    # importer must guard it up-front (Decimal(None)/None.strip() would crash).
    text = "Date,Details,Amount\n2026-01-01,OnlyTwo\n2026-01-02,Fine,-3.00\n"
    result = CsvImporter().parse(text, SINGLE, 2)
    assert [d.row_number for d in result.drafts] == [2]
    assert [e.row_number for e in result.errors] == [1]


def test_INV4_debit_credit_malformed_pairs_are_errors():
    rows = [
        ["2026-01-01", "BothEmpty", "", ""],  # 1 neither populated
        ["2026-01-02", "BothSet", "10.00", "5.00"],  # 2 both populated
        ["2026-01-03", "NegMag", "-10.00", ""],  # 3 negative magnitude
        ["2026-01-04", "OK", "", "20.00"],  # 4 ok
    ]
    result = CsvImporter().parse(_csv(DC_HEADER, rows), DEBIT_CREDIT, 2)
    assert [d.row_number for d in result.drafts] == [4]
    assert sorted(e.row_number for e in result.errors) == [1, 2, 3]


def test_INV4_zero_data_rows_yields_no_drafts_and_none_period():
    result = CsvImporter().parse("Date,Details,Amount\n", SINGLE, 2)
    assert result.drafts == [] and result.errors == []
    assert result.period_start is None and result.period_end is None


def test_INV4_empty_file_has_no_header():
    with pytest.raises(ValueError):
        read_header("")


def test_read_header_returns_fieldnames():
    assert read_header("Date,Details,Amount\n1,2,3\n") == ["Date", "Details", "Amount"]


# --------------------------------------------------------------------------- #
# Service-layer mapping-config validation (D3/D5/D10)
# --------------------------------------------------------------------------- #
def test_service_rejects_bad_mapping_config(service):
    imp = ImportService(service.vault)
    acct = _acct(service)
    text = _csv(HEADER, [["2026-01-05", "a", "-1.00"]])
    no_style = ColumnMapping("Date", "Details", None, None, None, "%Y-%m-%d", False)
    missing_col = ColumnMapping(
        "Date", "Details", "Missing", None, None, "%Y-%m-%d", False
    )
    both_styles = ColumnMapping(
        "Date", "Details", "Amount", "Debit", "Credit", "%Y-%m-%d", False
    )
    for bad in (no_style, missing_col, both_styles):
        with pytest.raises(ValueError):
            imp.preview(text, bad, acct)
    with pytest.raises(ValueError):
        imp.save_profile("bad", HEADER, no_style)


# --------------------------------------------------------------------------- #
# INV-5 — dedup is multiset-delta (description normalised)
# --------------------------------------------------------------------------- #
def test_INV5_zero_on_reimport(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    text = _csv(
        HEADER,
        [["2026-01-01", "Coffee", "-10.00"], ["2026-01-31", "Salary", "1000.00"]],
    )
    r1 = _do_import(imp, text, SINGLE, acct)
    assert r1.inserted_count == 2
    after_first = TransactionRepository(conn).count_for_account(acct)
    r2 = _do_import(imp, text, SINGLE, acct)
    assert r2.inserted_count == 0 and r2.duplicate_count == 2
    assert TransactionRepository(conn).count_for_account(acct) == after_first


def test_INV5_overlap_adds_only_new(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    t1 = _csv(
        HEADER,
        [
            ["2026-01-01", "A", "-1.00"],
            ["2026-01-02", "B", "-2.00"],
            ["2026-01-03", "C", "-3.00"],
        ],
    )
    t2 = _csv(
        HEADER,
        [
            ["2026-01-02", "B", "-2.00"],
            ["2026-01-03", "C", "-3.00"],
            ["2026-01-04", "D", "-4.00"],
        ],
    )
    _do_import(imp, t1, SINGLE, acct)
    r = _do_import(imp, t2, SINGLE, acct)
    assert r.inserted_count == 1
    assert {t.description for t in TransactionRepository(conn).list_all()} == {
        "A",
        "B",
        "C",
        "D",
    }


def test_INV5_genuine_repeats_kept_first_time(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    text = _csv(
        HEADER, [["2026-01-01", "Coffee", "-10.00"], ["2026-01-01", "Coffee", "-10.00"]]
    )
    assert _do_import(imp, text, SINGLE, acct).inserted_count == 2, (
        "both kept first time"
    )
    assert _do_import(imp, text, SINGLE, acct).inserted_count == 0, "zero on re-import"
    assert TransactionRepository(conn).count_for_account(acct) == 2


def test_INV5_dedup_against_manual_row(service):
    acct = _acct(service)
    TransactionService(service.vault).add_transaction(
        acct, "2026-01-01", "-10.00", "Coffee"
    )
    imp = ImportService(service.vault)
    r = _do_import(
        imp, _csv(HEADER, [["2026-01-01", "Coffee", "-10.00"]]), SINGLE, acct
    )
    assert r.inserted_count == 0 and r.duplicate_count == 1


def test_INV5_normalised_description_dedups_case_and_space(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    _do_import(
        imp, _csv(HEADER, [["2026-01-01", "POS  Coffee", "-10.00"]]), SINGLE, acct
    )
    r = _do_import(
        imp, _csv(HEADER, [["2026-01-01", "pos coffee", "-10.00"]]), SINGLE, acct
    )
    assert r.inserted_count == 0, "case/whitespace-only difference dedups"
    assert TransactionRepository(conn).count_for_account(acct) == 1


# --------------------------------------------------------------------------- #
# INV-6 — coverage period recorded + span-deduped
# --------------------------------------------------------------------------- #
def test_INV6_period_recorded(service):
    imp, acct = ImportService(service.vault), _acct(service)
    text = _csv(HEADER, [["2026-01-05", "a", "-1.00"], ["2026-01-20", "b", "-2.00"]])
    result = _do_import(imp, text, SINGLE, acct, source="/home/user/jan-stmt.csv")
    assert result.period_recorded is True
    periods = StatementPeriodRepository(service.vault.connection).list_for_account(acct)
    assert len(periods) == 1
    p = periods[0]
    assert p.period_start == "2026-01-05" and p.period_end == "2026-01-20"
    assert p.source_filename == "jan-stmt.csv", "stored as basename, not the full path"
    assert p.imported_at


def test_INV6_span_deduped(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    text = _csv(HEADER, [["2026-01-05", "a", "-1.00"], ["2026-01-20", "b", "-2.00"]])
    _do_import(imp, text, SINGLE, acct)
    _do_import(imp, text, SINGLE, acct)  # same span -> no 2nd period row
    assert len(StatementPeriodRepository(conn).list_for_account(acct)) == 1
    text2 = _csv(HEADER, [["2026-02-01", "c", "-1.00"], ["2026-02-10", "d", "-2.00"]])
    _do_import(imp, text2, SINGLE, acct)  # different span -> adds one
    assert len(StatementPeriodRepository(conn).list_for_account(acct)) == 2


def test_INV6_skip_period_but_import_new_transactions(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    text1 = _csv(HEADER, [["2026-01-01", "a", "-1.00"], ["2026-01-31", "b", "-2.00"]])
    _do_import(imp, text1, SINGLE, acct)
    # same span [01-01, 01-31], plus one new row inside it
    text2 = _csv(
        HEADER,
        [
            ["2026-01-01", "a", "-1.00"],
            ["2026-01-15", "c", "-3.00"],
            ["2026-01-31", "b", "-2.00"],
        ],
    )
    result = _do_import(imp, text2, SINGLE, acct)
    assert result.inserted_count == 1 and result.period_recorded is False
    assert len(StatementPeriodRepository(conn).list_for_account(acct)) == 1
    assert TransactionRepository(conn).count_for_account(acct) == 3


def test_INV6_zero_rows_no_period(service):
    imp, acct = ImportService(service.vault), _acct(service)
    preview = imp.preview("Date,Details,Amount\n", SINGLE, acct)
    assert preview.period_start is None and preview.period_end is None
    assert len(preview.drafts) == 0


def test_INV6_rejects_inverted_or_malformed_span(service):
    imp, acct = ImportService(service.vault), _acct(service)
    preview = imp.preview(_csv(HEADER, [["2026-01-05", "a", "-1.00"]]), SINGLE, acct)
    with pytest.raises(ValueError):
        imp.commit_import(preview, "2026-02-01", "2026-01-01", "s.csv")  # inverted
    with pytest.raises(ValueError):
        imp.commit_import(preview, "not-a-date", "2026-01-06", "s.csv")  # malformed


def test_INV6_fresh_span_zero_delta_still_records_period(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    text = _csv(HEADER, [["2026-01-05", "a", "-1.00"], ["2026-01-20", "b", "-2.00"]])
    _do_import(imp, text, SINGLE, acct)  # records span [01-05, 01-20]
    preview = imp.preview(text, SINGLE, acct)  # all-duplicate
    assert preview.new_count == 0 and len(preview.drafts) == 2
    result = imp.commit_import(
        preview, "2026-01-01", "2026-01-31", "s.csv"
    )  # fresh span
    assert result.inserted_count == 0 and result.period_recorded is True
    assert len(StatementPeriodRepository(conn).list_for_account(acct)) == 2


# --------------------------------------------------------------------------- #
# INV-7 — atomic write across both tables
# --------------------------------------------------------------------------- #
def test_INV7_atomic_write_rolls_back_both_tables(service):
    imp, acct, conn = (
        ImportService(service.vault),
        _acct(service),
        service.vault.connection,
    )
    text = _csv(HEADER, [["2026-01-05", "a", "-1.00"], ["2026-01-20", "b", "-2.00"]])
    preview = imp.preview(text, SINGLE, acct)

    class _FailAtPeriodInsert:
        """Raise on the first `INSERT INTO statement_periods` — after BEGIN and
        every transaction INSERT — so the ROLLBACK must undo those inserts."""

        def __init__(self, real):
            self._real = real

        def execute(self, sql, *a):
            if "INSERT INTO statement_periods" in sql:
                raise RuntimeError("injected failure at statement_periods INSERT")
            return self._real.execute(sql, *a)

        def __getattr__(self, name):
            return getattr(self._real, name)

    class _StandInVault:
        def __init__(self, connection):
            self._connection = connection

        @property
        def connection(self):
            return self._connection

    wedge = ImportService(_StandInVault(_FailAtPeriodInsert(conn)))
    with pytest.raises(RuntimeError):
        wedge.commit_import(preview, preview.period_start, preview.period_end, "s.csv")

    # SAME connection, before any reopen: neither transactions nor a period row.
    assert TransactionRepository(conn).count_for_account(acct) == 0
    assert StatementPeriodRepository(conn).list_for_account(acct) == []
    # And a retry on the real service imports cleanly.
    assert _do_import(imp, text, SINGLE, acct).inserted_count == 2


# --------------------------------------------------------------------------- #
# INV-8 — v3->v4 migration: forward-only, atomic, idempotent, tables untouched
# --------------------------------------------------------------------------- #
def test_INV8_v3_upgrades_to_v4_creates_tables_others_untouched(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    build_v3_vault(vault_path, sidecar_path, salt, [("2026-01-01", -100, "a")])

    conn = keyed_connection(vault_path, salt)
    before_tx = conn.execute(
        "SELECT id, amount_minor, description FROM transactions"
    ).fetchall()
    before_acct = conn.execute("SELECT id, name, type FROM accounts").fetchall()
    before_cats = conn.execute("SELECT id, name, kind FROM categories").fetchall()

    run_migrations(conn)  # v3 -> v4
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 4
    assert conn.execute("SELECT count(*) FROM import_profiles").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM statement_periods").fetchone()[0] == 0

    assert (
        conn.execute(
            "SELECT id, amount_minor, description FROM transactions"
        ).fetchall()
        == before_tx
    )
    assert conn.execute("SELECT id, name, type FROM accounts").fetchall() == before_acct
    assert (
        conn.execute("SELECT id, name, kind FROM categories").fetchall() == before_cats
    )
    conn.close()


def test_INV8_atomic_rollback_on_second_create_leaves_v3(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    build_v3_vault(vault_path, sidecar_path, salt, [])
    conn = keyed_connection(vault_path, salt)

    class _FailAtStatementPeriods:
        """Raise on `CREATE TABLE statement_periods` (the 2nd CREATE), after the
        1st CREATE — so the ROLLBACK must undo the import_profiles CREATE."""

        def __init__(self, real):
            self._real = real

        def execute(self, sql, *a):
            if "CREATE TABLE statement_periods" in sql:
                raise RuntimeError("injected failure at statement_periods CREATE")
            return self._real.execute(sql, *a)

        def __getattr__(self, name):
            return getattr(self._real, name)

    with pytest.raises(RuntimeError):
        run_migrations(_FailAtStatementPeriods(conn))

    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 3
    for table in ("import_profiles", "statement_periods"):
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            is None
        ), f"the {table} CREATE was rolled back"
    conn.close()


def test_INV8_idempotent_at_v4(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    build_v3_vault(vault_path, sidecar_path, salt, [])
    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)  # v3 -> v4
    run_migrations(conn)  # re-run: no-op at v4
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 4
    conn.close()


def test_INV8_first_run_vault_is_v4_with_empty_import_tables(service):
    conn = service.vault.connection
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 4
    assert conn.execute("SELECT count(*) FROM import_profiles").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM statement_periods").fetchone()[0] == 0


def test_INV8_latest_schema_version_is_4():
    assert LATEST_SCHEMA_VERSION == 4


# --------------------------------------------------------------------------- #
# INV-9 — a changed header is unmapped, never mis-parsed
# --------------------------------------------------------------------------- #
def test_INV9_changed_header_returns_no_match(service):
    imp = ImportService(service.vault)
    imp.save_profile("MyBank", HEADER, SINGLE)
    renamed = ["Date", "Description", "Amount"]  # "Details" -> "Description"
    assert imp.match_profile(renamed) is None, "a renamed column is a fresh layout"


# --------------------------------------------------------------------------- #
# INV-10 — import-wizard UI round-trip (qtbot)
# --------------------------------------------------------------------------- #
def test_INV10a_matching_profile_skips_mapping(qtbot, service, tmp_path):
    from finbreak.ui.import_wizard import ImportWizardWidget

    acct = _acct(service)
    ImportService(service.vault).save_profile("MyBank", HEADER, SINGLE)
    path = _write_csv(
        tmp_path, "stmt.csv", HEADER, [["2026-01-05", "Coffee", "-10.00"]]
    )

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    widget._select_file(str(path))

    assert widget._stack.currentIndex() == 2, "auto-matched -> straight to preview"
    assert widget._preview_table.rowCount() == 1


def test_INV10b_no_match_shows_mapping_and_saves_profile(qtbot, service, tmp_path):
    from finbreak.ui.import_wizard import ImportWizardWidget

    acct = _acct(service)
    path = _write_csv(
        tmp_path, "stmt.csv", HEADER, [["2026-01-05", "Coffee", "-10.00"]]
    )

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == 1, "no profile -> mapping step"

    widget._column_combos["date"].setCurrentIndex(
        widget._column_combos["date"].findData("Date")
    )
    widget._column_combos["description"].setCurrentIndex(
        widget._column_combos["description"].findData("Details")
    )
    widget._amount_style.setCurrentIndex(widget._amount_style.findData("single"))
    widget._column_combos["amount"].setCurrentIndex(
        widget._column_combos["amount"].findData("Amount")
    )
    widget._date_format.setText("%Y-%m-%d")
    widget._profile_name.setText("MyBank")
    widget._map_next_button.click()

    assert widget._error.text() == ""
    assert widget._stack.currentIndex() == 2
    assert widget._preview_table.rowCount() == 1
    assert ImportService(service.vault).match_profile(HEADER).name == "MyBank", (
        "profile persisted"
    )


def test_INV10c_preview_shows_rows_summary_and_period(qtbot, service, tmp_path):
    from finbreak.ui.import_wizard import ImportWizardWidget

    acct = _acct(service)
    ImportService(service.vault).save_profile("MyBank", HEADER, SINGLE)
    rows = [
        ["2026-01-05", "Coffee", "-10.00"],
        ["bad", "BadDate", "-1.00"],
        ["2026-01-20", "Salary", "1000.00"],
    ]
    path = _write_csv(tmp_path, "stmt.csv", HEADER, rows)

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    widget._select_file(str(path))

    assert widget._stack.currentIndex() == 2
    assert widget._preview_table.rowCount() == 3, (
        "every data row in file order (incl. the error row)"
    )
    assert widget._preview.new_count == 2 and widget._preview.duplicate_count == 0
    assert len(widget._preview.errors) == 1
    assert widget._summary_label.text() != ""
    # The Amount column shows the decimal amount, not raw minor units: rows
    # interleave by row_number, so row 0 is Coffee (-10.00) and row 2 is Salary.
    assert widget._preview_table.item(0, 2).text() == "-10.00"
    assert widget._preview_table.item(2, 2).text() == "1000.00"
    assert widget._period_start.date().toString(Qt.DateFormat.ISODate) == "2026-01-05"
    assert widget._period_end.date().toString(Qt.DateFormat.ISODate) == "2026-01-20"


def test_INV10d_import_inserts_rows_and_records_period(qtbot, service, tmp_path):
    from finbreak.ui.import_wizard import ImportWizardWidget

    acct, conn = _acct(service), service.vault.connection
    ImportService(service.vault).save_profile("MyBank", HEADER, SINGLE)
    rows = [["2026-01-05", "Coffee", "-10.00"], ["2026-01-20", "Salary", "1000.00"]]
    path = _write_csv(tmp_path, "stmt.csv", HEADER, rows)

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    returned: list[bool] = []
    widget.done.connect(lambda: returned.append(True))
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    widget._select_file(str(path))

    assert widget._import_button.isEnabled()
    widget._import_button.click()
    assert TransactionRepository(conn).count_for_account(acct) == 2
    assert len(StatementPeriodRepository(conn).list_for_account(acct)) == 1
    assert returned == [True], "returns to the main window on import"


def test_INV10e_second_import_is_all_duplicate(qtbot, service, tmp_path):
    from finbreak.ui.import_wizard import ImportWizardWidget

    acct, conn = _acct(service), service.vault.connection
    ImportService(service.vault).save_profile("MyBank", HEADER, SINGLE)
    rows = [["2026-01-05", "Coffee", "-10.00"], ["2026-01-20", "Salary", "1000.00"]]
    path = _write_csv(tmp_path, "stmt.csv", HEADER, rows)
    _do_import(ImportService(service.vault), _csv(HEADER, rows), SINGLE, acct)
    assert TransactionRepository(conn).count_for_account(acct) == 2

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    widget._select_file(str(path))
    assert widget._preview.new_count == 0
    assert widget._import_button.isEnabled(), (
        "all-duplicate stays enabled (to record the period)"
    )
    widget._import_button.click()
    assert TransactionRepository(conn).count_for_account(acct) == 2, "no new rows"


def test_INV10_import_disabled_when_no_drafts(qtbot, service, tmp_path):
    from finbreak.ui.import_wizard import ImportWizardWidget

    acct = _acct(service)
    ImportService(service.vault).save_profile("MyBank", HEADER, SINGLE)
    path = _write_csv(
        tmp_path, "stmt.csv", HEADER, [["bad", "BadDate", "-1.00"]]
    )  # all error

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    widget._select_file(str(path))
    assert widget._preview_table.rowCount() == 1, "the error row is still shown"
    assert not widget._import_button.isEnabled(), "zero drafts disables Import"


# --------------------------------------------------------------------------- #
# INV-11 — no secret logged across a match -> preview -> import cycle
# --------------------------------------------------------------------------- #
def test_INV11_import_cycle_logs_no_secret(service, caplog):
    password = _PW.decode()
    acct = _acct(service)
    imp = ImportService(service.vault)
    text = _csv(HEADER, [["2026-01-05", "Coffee", "-10.00"]])
    with caplog.at_level(logging.INFO, logger="finbreak"):
        imp.save_profile("MyBank", HEADER, SINGLE)
        imp.match_profile(HEADER)
        preview = imp.preview(text, SINGLE, acct)
        imp.commit_import(preview, preview.period_start, preview.period_end, "s.csv")

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert password not in joined, "the master password must never be logged"
    params = service.load_params()
    key = derive_key(bytearray(_PW), params.salt, params)
    assert bytes(key).hex() not in joined, "the derived key (hex) must never be logged"
