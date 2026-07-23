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

from conftest import (
    _PW,
    StandInVault,
    _acct,
    build_v3_vault,
    keyed_connection,
    raising_conn,
)
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
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates straight to latest
    yield svc
    svc.lock()


def _csv(header: list[str], rows: list[list[str]]) -> str:
    return "\n".join([",".join(header)] + [",".join(r) for r in rows]) + "\n"


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


# INV-4 (indie-review) — a structurally-broken CSV (an unterminated quote over
# the field-size limit) is parsed LAZILY during iteration, so the csv.Error is
# raised outside the per-row guard. csv.Error is not a ValueError, so without a
# translation the wizard's (ValueError, FinbreakError) net misses it and the
# import CRASHES. Both entry points must surface a friendly ValueError instead.
def test_INV4_malformed_csv_surfaces_valueerror_not_csv_error() -> None:
    import csv

    oversize_field = '"' + "a" * (csv.field_size_limit() + 1000)
    # Malformed HEADER line: read_header's .fieldnames access raises csv.Error.
    with pytest.raises(ValueError):
        read_header(oversize_field)
    # Header ok, malformed DATA row: parse's row iteration raises csv.Error.
    text = ",".join(HEADER) + "\n" + oversize_field
    with pytest.raises(ValueError):
        CsvImporter().parse(text, SINGLE, 2)


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
_NO_STYLE = ColumnMapping("Date", "Details", None, None, None, "%Y-%m-%d", False)


@pytest.mark.parametrize(
    "bad",
    [
        _NO_STYLE,
        ColumnMapping("Date", "Details", "Missing", None, None, "%Y-%m-%d", False),
        ColumnMapping(
            "Date", "Details", "Amount", "Debit", "Credit", "%Y-%m-%d", False
        ),
    ],
    ids=["no_amount_style", "missing_column", "both_styles"],
)
def test_service_preview_rejects_bad_mapping_config(service, bad):
    # Parametrized (FIBR-0063) so one bad-config's failure can't mask the others.
    imp = ImportService(service.vault)
    acct = _acct(service)
    text = _csv(HEADER, [["2026-01-05", "a", "-1.00"]])
    with pytest.raises(ValueError):
        imp.preview(text, bad, acct)


def test_service_save_profile_rejects_no_amount_style(service):
    # A distinct code path from preview() validation (FIBR-0063 split).
    with pytest.raises(ValueError):
        ImportService(service.vault).save_profile("bad", HEADER, _NO_STYLE)


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

    wedge = ImportService(
        StandInVault(
            raising_conn(
                conn,
                "INSERT INTO transactions",
                "injected failure at the transactions batch INSERT",
                on="executemany",
            )
        )
    )
    with pytest.raises(RuntimeError):
        wedge.commit_import(preview, preview.period_start, preview.period_end, "s.csv")

    # SAME connection, before any reopen: neither transactions nor a period row —
    # the period row inserted before the failing batch was rolled back too.
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

    run_migrations(conn)  # v3 -> v9 (full run_migrations now walks to LATEST)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 10
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

    with pytest.raises(RuntimeError):
        run_migrations(
            raising_conn(
                conn,
                "CREATE TABLE statement_periods",
                "injected failure at statement_periods CREATE",
            )
        )

    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 3
    for table in ("import_profiles", "statement_periods"):
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            is None
        ), f"the {table} CREATE was rolled back"
    conn.close()


def test_INV8_idempotent_at_v9(paths):
    vault_path, sidecar_path = paths
    salt = bytes(range(SALT_LEN))
    build_v3_vault(vault_path, sidecar_path, salt, [])
    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)  # v3 -> v9
    run_migrations(conn)  # re-run: no-op at v9
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 10
    conn.close()


def test_INV8_first_run_vault_is_v9_with_empty_import_tables(service):
    conn = service.vault.connection
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 10
    assert conn.execute("SELECT count(*) FROM import_profiles").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM statement_periods").fetchone()[0] == 0


def test_INV8_latest_schema_version_is_10():
    assert LATEST_SCHEMA_VERSION == 10


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
    widget._date_format.setCurrentIndex(widget._date_format.findData("%Y-%m-%d"))
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
# FIBR-0057 — the destination account is confirmable + editable on the preview
# step, so a wrong default can be corrected before the irreversible Import
# (previously the account was snapshotted at file-select and never re-read).
# --------------------------------------------------------------------------- #
def _two_accounts(service) -> tuple[int, int]:
    """A deterministic (Current, Credit Card) id pair, regardless of any seed."""
    svc = AccountService(service.vault)
    current = svc.add_account("Current acct", "current").id
    credit = svc.add_account("Credit Card acct", "credit_card").id
    return current, credit


def test_FIBR0057_retarget_recomputes_dedup_for_new_account(service):
    imp = ImportService(service.vault)
    current, credit = _two_accounts(service)
    rows = [["2026-01-05", "Coffee", "-10.00"]]
    # Seed the row under Current so the dedup delta differs by account.
    _do_import(imp, _csv(HEADER, rows), SINGLE, current)

    under_current = imp.preview(_csv(HEADER, rows), SINGLE, current)
    assert under_current.new_count == 0 and under_current.duplicate_count == 1

    # Re-target the SAME preview to a fresh account: dedup is re-run, so the row
    # is new there; the drafts/period (account-independent) are untouched.
    under_credit = imp.retarget(under_current, credit)
    assert under_credit.account_id == credit
    assert under_credit.new_count == 1 and under_credit.duplicate_count == 0
    assert under_credit.drafts == under_current.drafts
    assert under_credit.period_start == under_current.period_start
    assert under_credit.period_end == under_current.period_end


def test_FIBR0057_preview_step_exposes_destination_account(qtbot, service, tmp_path):
    from finbreak.ui.import_wizard import ImportWizardWidget

    current, _credit = _two_accounts(service)
    ImportService(service.vault).save_profile("MyBank", HEADER, SINGLE)
    path = _write_csv(
        tmp_path, "stmt.csv", HEADER, [["2026-01-05", "Coffee", "-10.00"]]
    )

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(current))
    widget._select_file(str(path))

    assert widget._stack.currentIndex() == 2
    # The preview step carries the destination account, seeded from step 0, so it
    # is visible before the user presses Import.
    assert widget._confirm_account_combo.currentData() == current
    assert widget._preview.account_id == current


def test_FIBR0057_changing_account_on_preview_retargets_the_commit(
    qtbot, service, tmp_path
):
    from finbreak.ui.import_wizard import ImportWizardWidget

    current, credit = _two_accounts(service)
    conn = service.vault.connection
    ImportService(service.vault).save_profile("MyBank", HEADER, SINGLE)
    rows = [["2026-01-05", "Coffee", "-10.00"], ["2026-01-20", "Salary", "1000.00"]]
    path = _write_csv(tmp_path, "stmt.csv", HEADER, rows)

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    # The user leaves step 0 at the default "Current" (the mis-link trap) ...
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(current))
    widget._select_file(str(path))
    assert widget._preview.account_id == current

    # ... then corrects the destination on the preview step to "Credit Card".
    widget._confirm_account_combo.setCurrentIndex(
        widget._confirm_account_combo.findData(credit)
    )
    assert widget._preview.account_id == credit, (
        "changing the account on the preview step re-targets the import"
    )

    widget._import_button.click()
    # The statement + ALL its transactions land on Credit Card, not Current.
    assert TransactionRepository(conn).count_for_account(credit) == 2
    assert TransactionRepository(conn).count_for_account(current) == 0
    assert len(StatementPeriodRepository(conn).list_for_account(credit)) == 1
    assert len(StatementPeriodRepository(conn).list_for_account(current)) == 0


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


def test_read_file_maps_os_error_to_value_error(service, tmp_path):
    """A missing/unreadable file surfaces as the friendly ValueError the wizard
    catches, not a raw OSError. (indie-review H-F)"""
    missing = str(tmp_path / "nope.csv")
    with pytest.raises(ValueError):
        ImportService(service.vault).read_file(missing)
    with pytest.raises(ValueError):
        ImportService(service.vault).read_file_bytes(missing)


def test_read_file_refuses_oversized_csv(service, tmp_path, monkeypatch):
    """The CSV read path enforces the same size cap as the bytes path, so a
    multi-GB mis-pick can't be loaded whole into memory (FIBR-0041). (H-G)"""
    import finbreak.services.import_ as import_mod

    big = tmp_path / "big.csv"
    big.write_text("Date,Details,Amount\n" + "x,y,1.00\n" * 500)
    monkeypatch.setattr(import_mod, "_MAX_IMPORT_BYTES", 100)
    with pytest.raises(ValueError):
        ImportService(service.vault).read_file(str(big))


def test_validate_mapping_rejects_duplicate_column_roles():
    """Two roles mapped to one column is refused, not silently misrouted.
    (indie-review M-csv-cols)"""
    dup = ColumnMapping("Date", "Date", "Amount", None, None, "%Y-%m-%d", False)
    with pytest.raises(ValueError, match="different column"):
        ImportService._validate_mapping(dup, ["Date", "Amount"])


def test_read_capped_bounds_read_against_endless_symlink(service, tmp_path):
    """The size cap is enforced by a bounded read, so a symlink to an endless
    source (/dev/zero) is refused as 'too large' rather than read unbounded into
    memory — a stat-only cap sees st_size 0 and would slip through. (indie-review
    hardening of the FIBR-0041 cap)"""
    import os

    if not (hasattr(os, "symlink") and os.path.exists("/dev/zero")):
        pytest.skip("POSIX symlink + /dev/zero required")
    link = tmp_path / "statement.csv"
    os.symlink("/dev/zero", link)
    with pytest.raises(ValueError):
        ImportService(service.vault).read_file_bytes(str(link))
