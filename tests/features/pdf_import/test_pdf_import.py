"""FIBR-0009 — P07 PDF statement import. Enforces tests/features/pdf_import/spec.md.

The pure-ish ``PdfImporter`` extractor (PDF bytes -> grouped candidate tables ->
CSV text feeding the *existing* CSV pipeline verbatim), the in-memory ``pikepdf``
decrypt of locked PDFs, the opt-in remembered password (v5 nullable column +
credential accessors), the ``password_dialog``, and the wizard's PDF branch.
Headless layers are tested directly; the wizard round-trips (INV-7) use the
pytest-qt ``qtbot`` fixture with an injected fake ``PasswordDialog`` (a live modal
would block). Every on-disk vault uses ``tmp_path``; the fixture PDFs are committed
gridded blobs (reportlab stays probe-only); encrypted variants are made in-test.
"""

import io
import logging
import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pikepdf
import pytest
from PySide6.QtWidgets import QDialog

from conftest import _PW, build_v4_vault, build_v5_vault, keyed_connection
from finbreak.crypto import SALT_LEN
from finbreak.importers.pdf_importer import (
    _MAX_PDF_PAGES,
    _MAX_PDF_ROWS,
    PdfImporter,
    group_tables_by_header,
    table_to_text,
)
from finbreak.migrations import LATEST_SCHEMA_VERSION, run_migrations
from finbreak.models import ColumnMapping
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.import_ import ImportService, signature_for

pytestmark = pytest.mark.features

_FIXTURES = Path(__file__).parent / "fixtures"

# Date=Date, Description=Description, Money Out=debit, Money In=credit; DD/MM/YYYY.
_PDF_MAPPING = ColumnMapping(
    "Date", "Description", None, "Money Out", "Money In", "%d/%m/%Y", False
)
_PDF_HEADER = ["Date", "Description", "Money Out", "Money In"]


def _fixture(name: str) -> bytes:
    return (_FIXTURES / name).read_bytes()


def _encrypt(raw: bytes, *, user: str = "", owner: str = "owner-pw") -> bytes:
    """A ``pikepdf``-encrypted copy of ``raw`` (in memory). ``user=""`` yields an
    owner-only PDF (opens without a prompt, D3); a non-empty user password yields
    a user-password PDF (drives the prompt / ``PasswordError`` path)."""
    out = io.BytesIO()
    with pikepdf.open(io.BytesIO(raw)) as pdf:
        pdf.save(out, encryption=pikepdf.Encryption(owner=owner, user=user, R=6))
    return out.getvalue()


def _blank_pdf() -> bytes:
    out = io.BytesIO()
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page()
    pdf.save(out)
    return out.getvalue()


def _zero_page_pdf() -> bytes:
    out = io.BytesIO()
    pdf = pikepdf.Pdf.new()  # no pages
    pdf.save(out)
    return out.getvalue()


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.fixture
def paths(tmp_path) -> tuple[Path, Path]:
    return tmp_path / "vault.db", tmp_path / "vault.kdf.json"


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates straight to the latest
    yield svc
    svc.lock()


def _acct(service: AuthService) -> int:
    return AccountService(service.vault).list_accounts()[0].id


# --------------------------------------------------------------------------- #
# INV-1 — extract -> CSV-adapter -> the existing pipeline verbatim
# --------------------------------------------------------------------------- #
def test_INV1_candidate_tables_extracts_single_table():
    candidates = PdfImporter().candidate_tables(_fixture("single_table.pdf"))
    assert len(candidates) == 1
    header, *rows = candidates[0]
    assert header == _PDF_HEADER
    assert len(rows) == 3


def test_INV1_table_to_text_serialises_none_as_empty():
    table = [_PDF_HEADER, ["01/03/2026", "Coffee", "12.50", None]]
    text = table_to_text(table)
    from finbreak.importers.csv_importer import read_header

    assert read_header(text) == _PDF_HEADER
    # the None cell round-trips as an empty field, not the literal "None"
    assert "None" not in text


def test_INV1_pdf_table_feeds_csv_pipeline_money_contract(service):
    imp = ImportService(service.vault)
    candidates = PdfImporter().candidate_tables(_fixture("single_table.pdf"))
    text = table_to_text(candidates[0])
    preview = imp.preview(text, _PDF_MAPPING, _acct(service))
    assert preview.new_count == 3
    assert [(d.description, d.amount_minor) for d in preview.drafts] == [
        ("Coffee Shop", -1250),
        ("Salary", 200000),
        ("Groceries", -3499),
    ]


def test_INV1_two_page_repeated_header_groups_into_one(service):
    candidates = PdfImporter().candidate_tables(
        _fixture("two_page_repeated_header.pdf")
    )
    assert len(candidates) == 1, "the repeated header stitches the pages (D8)"
    header, *rows = candidates[0]
    assert header == _PDF_HEADER
    assert len(rows) == 4
    text = table_to_text(candidates[0])
    preview = ImportService(service.vault).preview(text, _PDF_MAPPING, _acct(service))
    assert preview.new_count == 4


def test_INV1_group_tables_by_header_stitches_and_drops_repeated_header():
    t1 = [["Date", "Amt"], ["01/01", "1"]]
    t2 = [["Date", "Amt"], ["02/01", "2"]]  # same header -> grouped, its header dropped
    t3 = [["Other"], ["x"]]  # distinct header -> its own candidate
    assert group_tables_by_header([t1, t2, t3]) == [
        [["Date", "Amt"], ["01/01", "1"], ["02/01", "2"]],
        [["Other"], ["x"]],
    ]


# --------------------------------------------------------------------------- #
# INV-1a — blank / duplicate / literal-"Column N" header cells uniquified (D13)
# --------------------------------------------------------------------------- #
def test_INV1a_blank_dup_and_literal_column_header_uniquified():
    raw = [["", "Amount", "Amount", "Column 1"], ["a", "b", "c", "d"]]
    candidate = group_tables_by_header([raw])[0]
    header = candidate[0]
    # blank pos1 -> "Column 1", but that collides with the real "Column 1" at pos4,
    # so it re-suffixes to "Column 1_2"; the first "Amount" is kept, the dup -> pos.
    assert header == ["Column 1_2", "Amount", "Column 3", "Column 1"]
    assert len(set(header)) == len(header), "collision-free"
    signature_for(header)  # must not raise the duplicate-header ValueError
    assert candidate[1] == ["a", "b", "c", "d"], (
        "data row untouched (header-only rewrite)"
    )


# --------------------------------------------------------------------------- #
# INV-2 — in-memory decrypt (security spine), D4's three legs
# --------------------------------------------------------------------------- #
def test_INV2_encrypted_fixture_decrypts_and_extracts_from_bytes():
    enc = _encrypt(_fixture("single_table.pdf"), user="secret")
    candidates = PdfImporter().candidate_tables(enc, password="secret")
    assert candidates[0][0] == _PDF_HEADER and len(candidates[0]) == 4


def test_INV2_owner_only_extracts_without_a_password():
    enc = _encrypt(_fixture("single_table.pdf"), user="")  # owner-only
    candidates = PdfImporter().candidate_tables(enc)  # no password supplied (D3)
    assert candidates[0][0] == _PDF_HEADER and len(candidates[0]) == 4


def test_INV2_decrypt_extract_writes_no_file(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    # Redirect BOTH the env var (qpdf's C runtime) and tempfile.tempdir (cached
    # after any prior gettempdir()); snapshot the scratch dir AND the CWD (D4b).
    monkeypatch.setenv("TMPDIR", str(scratch))
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    enc = _encrypt(_fixture("single_table.pdf"), user="secret")
    cwd = Path.cwd()
    before_scratch, before_cwd = set(scratch.iterdir()), set(cwd.iterdir())
    PdfImporter().candidate_tables(enc, password="secret")
    assert set(scratch.iterdir()) == before_scratch, "decrypt+extract wrote a temp file"
    assert set(cwd.iterdir()) == before_cwd, "decrypt+extract wrote to the CWD"


def test_INV2_module_has_no_disk_write_token():
    src = Path("src/finbreak/importers/pdf_importer.py").read_text()
    for tok in (
        "tempfile",
        "NamedTemporaryFile",
        ".write_bytes(",
        "os.write",
        '"w"',
        '"wb"',
        "'w'",
        "'wb'",
    ):
        assert tok not in src, f"disk-write token in the importer: {tok!r}"


# --------------------------------------------------------------------------- #
# INV-3 — a wrong / absent user password raises the re-prompt signal
# --------------------------------------------------------------------------- #
def test_INV3_absent_password_raises_password_error():
    enc = _encrypt(_fixture("single_table.pdf"), user="secret")
    with pytest.raises(pikepdf.PasswordError):
        PdfImporter().candidate_tables(enc)


def test_INV3_wrong_password_raises_password_error():
    enc = _encrypt(_fixture("single_table.pdf"), user="secret")
    with pytest.raises(pikepdf.PasswordError):
        PdfImporter().candidate_tables(enc, password="wrong")


# --------------------------------------------------------------------------- #
# INV-4 — remembered password is opt-in (v5 accessor round-trip; default None)
# --------------------------------------------------------------------------- #
def test_INV4_get_set_pdf_password_round_trip(service):
    accounts = AccountService(service.vault)
    acct = accounts.list_accounts()[0].id
    assert accounts.get_pdf_password(acct) is None, "default: nothing stored"
    accounts.set_pdf_password(acct, "secret")
    assert accounts.get_pdf_password(acct) == "secret"
    accounts.set_pdf_password(acct, None)  # clear
    assert accounts.get_pdf_password(acct) is None


# --------------------------------------------------------------------------- #
# INV-5 — no usable table -> one friendly ValueError (no crash / IndexError)
# --------------------------------------------------------------------------- #
def test_INV5_no_ruled_table_raises_friendly_error():
    with pytest.raises(ValueError, match="couldn't read a table"):
        PdfImporter().candidate_tables(_blank_pdf())


def test_INV5_zero_page_pdf_maps_to_friendly_error_not_indexerror():
    with pytest.raises(ValueError):
        PdfImporter().candidate_tables(_zero_page_pdf())


# --------------------------------------------------------------------------- #
# INV-6 — a multi-table PDF surfaces all candidates; header-only dropped
# --------------------------------------------------------------------------- #
def test_INV6_two_table_returns_both_candidates():
    candidates = PdfImporter().candidate_tables(_fixture("two_table.pdf"))
    assert len(candidates) == 2
    headers = [c[0] for c in candidates]
    assert ["Opening balance", "Closing balance"] in headers
    assert _PDF_HEADER in headers


def test_INV6_header_only_candidate_dropped():
    # group_tables_by_header keeps a header-only group as a len-1 candidate;
    # candidate_tables drops it with the same len > 1 filter (composed here).
    grouped = group_tables_by_header([[["A", "B"]], [["C", "D"], ["x", "1"]]])
    assert [len(c) for c in grouped] == [1, 2]
    assert [c for c in grouped if len(c) > 1] == [[["C", "D"], ["x", "1"]]]


# --------------------------------------------------------------------------- #
# INV-7 — import-wizard PDF round-trip (qtbot, fake PasswordDialog)
# --------------------------------------------------------------------------- #
def _wizard(qtbot, service, acct):
    from finbreak.ui.import_wizard import ImportWizardWidget

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    return widget


def _patch_dialog(monkeypatch, responses):
    """Replace ``import_wizard.PasswordDialog`` with a scripted fake. Each dialog
    construction pops the next response dict (``password``/``remember``/``accept``);
    returns the list of account-name labels the wizard passed (one per prompt)."""
    from finbreak.ui import import_wizard

    seq = iter(responses)
    shown: list[str] = []

    class _Fake:
        def __init__(self, account_name, parent=None):
            self._r = next(seq)
            shown.append(account_name)

        def exec(self):
            accepted = self._r.get("accept", True)
            return (
                QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected
            )

        def password(self):
            return self._r.get("password", "")

        def remember(self):
            return self._r.get("remember", False)

        def deleteLater(self):  # the wizard disposes each attempt (indie-review M1)
            pass

    monkeypatch.setattr(import_wizard, "PasswordDialog", _Fake)
    return shown


def test_INV7a_pdf_pick_lands_on_map_step(qtbot, service, tmp_path):
    path = _write(tmp_path, "stmt.pdf", _fixture("single_table.pdf"))
    widget = _wizard(qtbot, service, _acct(service))
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == 1, (
        "PDF -> map step (unlike OFX, not skipped)"
    )


def test_INV7a_content_sniff_routes_misnamed_pdf(qtbot, service, tmp_path):
    path = _write(tmp_path, "statement.bin", _fixture("single_table.pdf"))
    widget = _wizard(qtbot, service, _acct(service))
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == 1, "sniffed %PDF- -> map step"


def test_INV7b_encrypted_prompts_and_wrong_password_reprompts(
    qtbot, service, tmp_path, monkeypatch
):
    enc = _encrypt(_fixture("single_table.pdf"), user="secret")
    path = _write(tmp_path, "locked.pdf", enc)
    shown = _patch_dialog(monkeypatch, [{"password": "wrong"}, {"password": "secret"}])
    widget = _wizard(qtbot, service, _acct(service))
    widget._select_file(str(path))
    assert len(shown) == 2, "a wrong password re-prompted (INV-3)"
    assert widget._stack.currentIndex() == 1, "the correct password then proceeded"


def test_INV7b_cancel_abandons_import(qtbot, service, tmp_path, monkeypatch):
    enc = _encrypt(_fixture("single_table.pdf"), user="secret")
    path = _write(tmp_path, "locked.pdf", enc)
    _patch_dialog(monkeypatch, [{"accept": False}])
    widget = _wizard(qtbot, service, _acct(service))
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == 0, "Cancel abandons cleanly (stays on pick)"
    assert widget._error.text() == ""


def test_INV7c_multi_table_chooser_default_largest_and_switch_repopulates(
    qtbot, service, tmp_path
):
    path = _write(tmp_path, "two.pdf", _fixture("two_table.pdf"))
    widget = _wizard(qtbot, service, _acct(service))
    widget._select_file(str(path))
    assert not widget._pdf_table_combo.isHidden(), "chooser shown for >1 table"
    assert widget._pdf_table_combo.count() == 2
    # candidates preserve first-occurrence order: 0=summary, 1=transactions.
    assert widget._pdf_candidates[0][0] == ["Opening balance", "Closing balance"]
    assert widget._pdf_candidates[1][0] == _PDF_HEADER
    assert widget._pdf_table_combo.currentData() == 1, (
        "default = largest (transactions)"
    )
    assert widget._column_combos["date"].findData("Date") >= 0
    widget._pdf_table_combo.setCurrentIndex(0)  # switch to the summary table
    assert widget._column_combos["date"].findData("Opening balance") >= 0
    assert widget._column_combos["date"].findData("Date") < 0


def test_INV7d_single_table_profile_match_jumps_to_preview(qtbot, service, tmp_path):
    ImportService(service.vault).save_profile("bank", _PDF_HEADER, _PDF_MAPPING)
    path = _write(tmp_path, "stmt.pdf", _fixture("single_table.pdf"))
    widget = _wizard(qtbot, service, _acct(service))
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == 2, "single candidate + profile -> preview"
    assert widget._preview_table.rowCount() == 3


def test_INV7d_multi_table_profile_match_stays_on_map(qtbot, service, tmp_path):
    ImportService(service.vault).save_profile("bank", _PDF_HEADER, _PDF_MAPPING)
    path = _write(tmp_path, "two.pdf", _fixture("two_table.pdf"))
    widget = _wizard(qtbot, service, _acct(service))
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == 1, ">1 candidate always shows the map step"
    assert not widget._pdf_table_combo.isHidden()
    # the profile pre-filled the combos for the default (transactions) table
    assert widget._column_combos["date"].currentData() == "Date"
    assert widget._column_combos["debit"].currentData() == "Money Out"


def test_INV7e_import_inserts_rows_and_reimport_adds_zero(qtbot, service, tmp_path):
    acct, conn = _acct(service), service.vault.connection
    ImportService(service.vault).save_profile("bank", _PDF_HEADER, _PDF_MAPPING)
    path = _write(tmp_path, "stmt.pdf", _fixture("single_table.pdf"))
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert widget._import_button.isEnabled()
    widget._import_button.click()
    assert TransactionRepository(conn).count_for_account(acct) == 3
    assert len(StatementPeriodRepository(conn).list_for_account(acct)) == 1

    widget2 = _wizard(qtbot, service, acct)
    widget2._select_file(str(path))
    assert widget2._preview.new_count == 0, "same statement -> all duplicate"
    widget2._import_button.click()
    assert TransactionRepository(conn).count_for_account(acct) == 3, "no new rows"


def test_INV7f_remembered_password_auto_applies_no_prompt(
    qtbot, service, tmp_path, monkeypatch
):
    acct = _acct(service)
    enc = _encrypt(_fixture("single_table.pdf"), user="secret")
    path = _write(tmp_path, "locked.pdf", enc)
    _patch_dialog(monkeypatch, [{"password": "secret", "remember": True}])
    _wizard(qtbot, service, acct)._select_file(str(path))
    assert AccountService(service.vault).get_pdf_password(acct) == "secret", "stored"

    # second import: the dialog must not be constructed at all (auto-applied).
    from finbreak.ui import import_wizard

    class _NoDialog:
        def __init__(self, *a, **k):
            raise AssertionError("dialog shown despite a remembered password")

    monkeypatch.setattr(import_wizard, "PasswordDialog", _NoDialog)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == 1, "reached the map step with no prompt"


def test_INV7f_stored_password_that_fails_falls_back_to_prompt(
    qtbot, service, tmp_path, monkeypatch
):
    acct = _acct(service)
    AccountService(service.vault).set_pdf_password(acct, "stale")
    enc = _encrypt(_fixture("single_table.pdf"), user="secret")
    path = _write(tmp_path, "locked.pdf", enc)
    shown = _patch_dialog(monkeypatch, [{"password": "secret"}])
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert len(shown) == 1, "a stale stored password falls back to the prompt (INV-3)"
    assert widget._stack.currentIndex() == 1


def test_INV4_unencrypted_pdf_never_consults_stored_password(
    qtbot, service, tmp_path, monkeypatch
):
    # INV-4: an unencrypted PDF (no PasswordError) must NOT consult a stored
    # password — the first candidate_tables(None) succeeds before any stored
    # lookup — and must not overwrite it. No dialog is shown.
    acct = _acct(service)
    AccountService(service.vault).set_pdf_password(acct, "unrelated-stored-pw")
    path = _write(tmp_path, "plain.pdf", _fixture("single_table.pdf"))  # unencrypted
    from finbreak.ui import import_wizard

    class _NoDialog:
        def __init__(self, *a, **k):
            raise AssertionError("dialog shown for an unencrypted PDF")

    monkeypatch.setattr(import_wizard, "PasswordDialog", _NoDialog)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == 1, "unencrypted -> map step, no prompt"
    assert (
        AccountService(service.vault).get_pdf_password(acct) == "unrelated-stored-pw"
    ), "the stored password is neither consulted nor overwritten"


def test_FIBR0057_remembered_pdf_password_follows_a_retarget(
    qtbot, service, tmp_path, monkeypatch
):
    # A locked PDF is decrypted under the provisional (file-select) account, so
    # "remember" persists there (INV-7f). If the user then corrects the
    # destination on the preview step, the remembered password must also serve
    # the account the rows land on — else the auto-apply is defeated in exactly
    # the mis-link case FIBR-0057 exists to fix.
    accounts = AccountService(service.vault)
    current = accounts.add_account("Current acct", "current").id
    credit = accounts.add_account("Credit Card acct", "credit_card").id
    ImportService(service.vault).save_profile("bank", _PDF_HEADER, _PDF_MAPPING)
    enc = _encrypt(_fixture("single_table.pdf"), user="secret")
    path = _write(tmp_path, "locked.pdf", enc)
    _patch_dialog(monkeypatch, [{"password": "secret", "remember": True}])

    widget = _wizard(qtbot, service, current)
    widget._select_file(str(path))
    assert widget._stack.currentIndex() == 2, "profile + single table -> preview"
    assert accounts.get_pdf_password(current) == "secret", "stored under provisional"

    # The user corrects the destination to Credit Card, then imports.
    widget._confirm_account_combo.setCurrentIndex(
        widget._confirm_account_combo.findData(credit)
    )
    widget._import_button.click()
    assert accounts.get_pdf_password(credit) == "secret", (
        "the remembered password follows the corrected destination account"
    )


# --------------------------------------------------------------------------- #
# INV-8 — v4->v5 migration + credential hygiene
# --------------------------------------------------------------------------- #
def test_INV8_v4_upgrades_through_v7_adds_nullable_column(paths):
    # A v4 vault now migrates through v5 (PDF password), v6 (statement provenance)
    # and v7 (category link), so run_migrations lands it at 7 — but the v4->v5
    # column-add coverage is intact: statement_pdf_password still exists after the walk.
    vault_path, sidecar_path = paths
    salt = os.urandom(SALT_LEN)
    build_v4_vault(vault_path, sidecar_path, salt, [("2026-03-01", -1250, "Coffee")])
    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)  # v4 -> v7
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 7
    cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
    assert "statement_pdf_password" in cols
    row = conn.execute("SELECT statement_pdf_password FROM accounts").fetchone()
    assert row[0] is None, "nullable, defaults to NULL"
    conn.close()


def test_INV8_idempotent_at_v7(paths):
    vault_path, sidecar_path = paths
    salt = os.urandom(SALT_LEN)
    build_v4_vault(vault_path, sidecar_path, salt, [])
    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)  # v4 -> v7
    run_migrations(conn)  # re-run: no-op at v7
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 7
    conn.close()


def test_INV8_first_run_vault_is_v7(service):
    version = service.vault.connection.execute(
        "SELECT version FROM schema_version"
    ).fetchone()[0]
    assert version == 7


def test_INV8_latest_schema_version_is_7():
    assert LATEST_SCHEMA_VERSION == 7


def test_INV8_v5_upgrades_through_v7_adds_provenance_column(paths):
    # The v5->v6 provenance-column coverage (FIBR-0052 INV-13a): a v5 vault walks to
    # v7 and, along the way at v5->v6, gains the nullable
    # transactions.statement_period_id provenance column.
    vault_path, sidecar_path = paths
    salt = os.urandom(SALT_LEN)
    build_v5_vault(vault_path, sidecar_path, salt, [("2026-03-01", -1250, "Coffee")])
    conn = keyed_connection(vault_path, salt)
    run_migrations(conn)  # v5 -> v7
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 7
    cols = [r[1] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    assert "statement_period_id" in cols
    row = conn.execute("SELECT statement_period_id FROM transactions").fetchone()
    assert row[0] is None, "nullable, defaults to NULL for a pre-v6 row with no period"
    conn.close()


def test_INV8_password_not_on_account_object(service):
    account = AccountService(service.vault).list_accounts()[0]
    assert not hasattr(account, "statement_pdf_password"), "credential hygiene (D6)"


# --------------------------------------------------------------------------- #
# INV-9 — PDF is resource-bounded; cell text is inert
# --------------------------------------------------------------------------- #
def test_INV9_too_many_pages_refused(monkeypatch):
    import finbreak.importers.pdf_importer as pdf_mod

    monkeypatch.setattr(pdf_mod, "_MAX_PDF_PAGES", 1)
    with pytest.raises(ValueError):
        PdfImporter().candidate_tables(_fixture("two_page_repeated_header.pdf"))


def test_INV9_too_many_rows_refused(monkeypatch):
    import finbreak.importers.pdf_importer as pdf_mod

    monkeypatch.setattr(pdf_mod, "_MAX_PDF_ROWS", 2)  # single_table has 3 data rows
    with pytest.raises(ValueError):
        PdfImporter().candidate_tables(_fixture("single_table.pdf"))


def test_INV9_caps_are_the_documented_constants():
    assert _MAX_PDF_PAGES == 500
    assert _MAX_PDF_ROWS == 100_000


def test_INV9_formula_cell_stored_inert(service):
    table = [_PDF_HEADER, ["01/03/2026", "=cmd|'/c calc'!A1", "12.50", ""]]
    text = table_to_text(table)
    preview = ImportService(service.vault).preview(text, _PDF_MAPPING, _acct(service))
    assert [d.description for d in preview.drafts] == ["=cmd|'/c calc'!A1"], "inert str"


# --------------------------------------------------------------------------- #
# INV-10 — PDF feeds the same write pipeline (dedup + atomic period)
# --------------------------------------------------------------------------- #
def test_INV10_pdf_import_then_reimport_adds_zero(service):
    acct, conn = _acct(service), service.vault.connection
    imp = ImportService(service.vault)
    text = table_to_text(
        PdfImporter().candidate_tables(_fixture("single_table.pdf"))[0]
    )
    p1 = imp.preview(text, _PDF_MAPPING, acct)
    imp.commit_import(p1, p1.period_start, p1.period_end, "stmt.pdf")
    assert TransactionRepository(conn).count_for_account(acct) == 3
    p2 = imp.preview(text, _PDF_MAPPING, acct)
    assert p2.new_count == 0
    imp.commit_import(p2, p2.period_start, p2.period_end, "stmt.pdf")
    assert TransactionRepository(conn).count_for_account(acct) == 3
    assert len(StatementPeriodRepository(conn).list_for_account(acct)) == 1


# --------------------------------------------------------------------------- #
# INV-11 — no secret logged / in an exception message / on the wizard
# --------------------------------------------------------------------------- #
def test_INV11_password_never_logged(service, caplog):
    # Scope capture to our own package: the leak INV-11 guards is *our* code
    # logging the secret. pikepdf consumes the password (C) before pdfminer ever
    # sees plaintext, so the third-party libs never receive it — and their DEBUG
    # stream would otherwise flood the assertion with megabytes of PDF operators.
    enc = _encrypt(_fixture("single_table.pdf"), user="sentinel-pw-42")
    with caplog.at_level(logging.DEBUG, logger="finbreak"):
        PdfImporter().candidate_tables(enc, password="sentinel-pw-42")
        AccountService(service.vault).set_pdf_password(_acct(service), "sentinel-pw-42")
    assert "sentinel-pw-42" not in caplog.text


def test_INV11_password_not_in_exception_message():
    enc = _encrypt(_fixture("single_table.pdf"), user="sentinel-pw-42")
    try:
        PdfImporter().candidate_tables(enc, password="wrong-guess")
    except pikepdf.PasswordError as exc:
        assert "sentinel-pw-42" not in str(exc)
        assert "wrong-guess" not in str(exc)
    else:
        raise AssertionError("expected a PasswordError")


def test_INV11_wizard_defines_no_password_attribute():
    src = Path("src/finbreak/ui/import_wizard.py").read_text()
    assert not re.search(r"self\._[A-Za-z0-9_]*password", src)


def test_candidate_tables_maps_pdf_parse_error_to_value_error(monkeypatch):
    """A PDF pikepdf can open but pdfplumber/pdfminer can't parse must fail as a
    friendly ValueError, not an unhandled non-ValueError crash. (indie-review H-D)"""
    import pdfplumber
    from pdfplumber.utils.exceptions import PdfminerException

    import finbreak.importers.pdf_importer as pdf_mod

    monkeypatch.setattr(pdf_mod, "_normalise_to_plaintext", lambda raw, pw: raw)

    def boom(*args, **kwargs):
        raise PdfminerException("bad content stream")

    monkeypatch.setattr(pdfplumber, "open", boom)
    with pytest.raises(ValueError):
        PdfImporter().candidate_tables(b"whatever")
