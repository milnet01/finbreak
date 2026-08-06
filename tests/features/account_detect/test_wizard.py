"""FIBR-0086 — the wizard half (INV-7, INV-7a).

Driven through OFX, which carries its account id natively and so reaches the
match path with no PDF fixture. Every account number here is invented (INV-8).

The row that matters is INV-7a. Seeding the destination combo *after* the preview
is built, under a ``QSignalBlocker``, suppresses ``currentIndexChanged`` — so
``_on_confirm_account_changed`` never runs, ``retarget`` is never called, and
``commit_import`` persists a preview aimed at the previous account while the
screen reads "Matched account number …". That is the wrong-account commit this
whole feature exists to prevent, and only the match → seed → preview ordering
stops it.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from conftest import _PW
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService

pytestmark = pytest.mark.features

_OFX_HEADER = (
    "OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\n"
    "ENCODING:USASCII\r\nCHARSET:1252\r\nCOMPRESSION:NONE\r\nOLDFILEUID:NONE\r\n"
    "NEWFILEUID:NONE\r\n\r\n"
)


def _ofx(acctid: str) -> bytes:
    """A one-transaction bank statement carrying ``acctid`` as its account id."""
    body = (
        "<STMTTRN>\n<TRNTYPE>DEBIT\n<DTPOSTED>20260105\n<TRNAMT>-10.00\n"
        "<NAME>Coffee\n<FITID>a1\n</STMTTRN>\n"
    )
    return (
        _OFX_HEADER + "<OFX>\n<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0"
        "<SEVERITY>INFO</STATUS>\n"
        f"<STMTRS><CURDEF>ZAR<BANKACCTFROM><BANKID>250655<ACCTID>{acctid}"
        "<ACCTTYPE>CHECKING</BANKACCTFROM>\n"
        "<BANKTRANLIST><DTSTART>20260101\n<DTEND>20260131\n"
        f"{body}</BANKTRANLIST>\n"
        "<LEDGERBAL><BALAMT>0.00<DTASOF>20260131</LEDGERBAL>\n"
        "</STMTRS></STMTTRNRS></BANKMSGSRSV1>\n</OFX>\n"
    ).encode()


@pytest.fixture()
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _accounts(service: AuthService) -> AccountService:
    return AccountService(service.vault)


def _wizard(qtbot, service, pick_account_id: int):
    """A wizard whose PICK-step choice is ``pick_account_id``.

    The pick is deliberately the *wrong* account in the matched tests, so a green
    assertion proves auto-detect moved the selection rather than the seeding from
    step 0 happening to be right.
    """
    from finbreak.ui.import_wizard import ImportWizardWidget

    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(
        widget._account_combo.findData(pick_account_id)
    )
    return widget


def _write(tmp_path: Path, data: bytes) -> str:
    path = tmp_path / "stmt.ofx"
    path.write_bytes(data)
    return str(path)


# --- INV-7 -------------------------------------------------------------------


def test_match_preselects_but_does_not_commit(qtbot, service, tmp_path):
    """A match changes the default, not the flow: the preview step is shown and
    nothing is written until the user presses Import."""
    svc = _accounts(service)
    seeded = svc.list_accounts()[0].id
    target = svc.add_account("Savings", "savings", account_number="22 333 444 5").id

    widget = _wizard(qtbot, service, seeded)
    widget._select_file(_write(tmp_path, _ofx("223334445")))

    # Pre-selected: the combo moved off the pick-step account onto the match.
    assert widget._confirm_account_combo.currentData() == target
    # ...and still on the preview step, with nothing persisted.
    assert widget._stack.currentIndex() == 2
    txns = TransactionRepository(service.vault.connection)
    assert txns.count_for_account(target) == 0
    assert txns.count_for_account(seeded) == 0


# --- INV-7a ------------------------------------------------------------------


def test_preview_account_matches_displayed_account(qtbot, service, tmp_path):
    """The money row: the preview was computed for the account on screen.

    Goes red if the combo is seeded from the match after ``preview_result`` under
    a blocker — the combo would show the matched account while ``_preview`` stayed
    pointed at the pick-step one, and ``commit_import`` persists ``_preview``.
    """
    svc = _accounts(service)
    seeded = svc.list_accounts()[0].id
    target = svc.add_account("Savings", "savings", account_number="22 333 444 5").id
    assert seeded != target, "the fixture must start on the WRONG account"

    widget = _wizard(qtbot, service, seeded)
    widget._select_file(_write(tmp_path, _ofx("223334445")))

    assert widget._preview is not None
    assert widget._preview.account_id == widget._confirm_account_combo.currentData()
    assert widget._preview.account_id == target


# --- the degraded outcomes leave the selection alone -------------------------


def test_no_match_leaves_the_pick_step_selection(qtbot, service, tmp_path):
    """Zero matches must not guess — the combo keeps what the pick step gave it."""
    svc = _accounts(service)
    seeded = svc.list_accounts()[0].id
    svc.add_account("Savings", "savings", account_number="22 333 444 5")

    widget = _wizard(qtbot, service, seeded)
    widget._select_file(_write(tmp_path, _ofx("99 888 777 6")))

    assert widget._confirm_account_combo.currentData() == seeded
    assert widget._preview is not None
    assert widget._preview.account_id == seeded
    # ...and creation is offered, prefilled from the statement (§4.6).
    assert not widget._create_account_button.isHidden()


def test_creation_is_offered_only_on_no_match(qtbot, service, tmp_path):
    """`no_number` must never reach the create form.

    A masked or unreadable number would otherwise become an account's permanently
    stored number. CSV carries no number at all, which is the same outcome.
    """
    svc = _accounts(service)
    seeded = svc.list_accounts()[0].id
    svc.add_account("Savings", "savings", account_number="22 333 444 5")

    widget = _wizard(qtbot, service, seeded)
    # An OFX whose account id is masked -> no_number, not no_match.
    widget._select_file(_write(tmp_path, _ofx("xxxx4445")))

    assert widget._create_account_button.isHidden()
    assert widget._account_match_label.isHidden(), "no_number shows no label at all"
    assert widget._confirm_account_combo.currentData() == seeded


def test_a_fresh_pick_drops_the_previous_files_create_offer(qtbot, service, tmp_path):
    """The CSV path never runs the match, so a stale offer would survive into it."""
    svc = _accounts(service)
    seeded = svc.list_accounts()[0].id

    widget = _wizard(qtbot, service, seeded)
    widget._select_file(_write(tmp_path, _ofx("99 888 777 6")))
    assert not widget._create_account_button.isHidden(), "fixture: expected no_match"

    csv = tmp_path / "next.csv"
    csv.write_text("date,amount,description\n2026-01-05,-10.00,Coffee\n")
    widget._select_file(str(csv))

    assert widget._create_account_button.isHidden()
    assert widget._pending_hint is None


def _open_create_dialog(widget):
    """Click Create and return the live dialog.

    ``show_modal`` is deliberately non-blocking (FIBR-0065 D1) — it shows the
    dialog and wires ``accepted``, rather than returning a code — so the real
    dialog is reachable as a child and the test can drive it. Stubbing the helper
    instead would hide its actual signature, which is how the first draft of this
    suite passed against a call that could not work.
    """
    from finbreak.ui.account_create import CreateAccountDialog

    widget._create_account_button.click()
    dialog = widget.findChild(CreateAccountDialog)
    assert dialog is not None, "Create did not open the dialog"
    return dialog


def test_created_account_receives_the_preview(qtbot, service, tmp_path):
    """Creating from `no_match` retargets the preview onto the new account.

    The mirror image of INV-7a: the preview already exists when this button is
    pressed, so the combo update must NOT be blocked — the signal is what reaches
    `retarget`. Blocking here would leave the preview on the old account while the
    combo showed the new one.
    """
    svc = _accounts(service)
    seeded = svc.list_accounts()[0].id

    widget = _wizard(qtbot, service, seeded)
    widget._select_file(_write(tmp_path, _ofx("99 888 777 6")))
    assert widget._preview is not None
    assert widget._preview.account_id == seeded

    # Stand in for the user: type the name OFX cannot supply, then accept. The
    # prefilled number is left exactly as the dialog received it.
    dialog = _open_create_dialog(widget)
    assert dialog.entered_number() == "99 888 777 6", "prefilled as printed"
    dialog._name.setText("New Savings")
    dialog.accept()

    created = [a for a in svc.list_accounts() if a.id != seeded]
    assert len(created) == 1
    new_id = created[0].id
    # Stored AS PRINTED, not as the normalised key.
    assert created[0].account_number == "99 888 777 6"
    assert widget._confirm_account_combo.currentData() == new_id
    assert widget._preview.account_id == new_id, "the preview followed the new account"


def test_create_with_no_name_surfaces_the_error(qtbot, service, tmp_path):
    """OFX and families B/D print no name, so the box arrives empty and the user
    must fill it. Accepting anyway must say so, not fail silently."""
    svc = _accounts(service)
    seeded = svc.list_accounts()[0].id
    widget = _wizard(qtbot, service, seeded)
    widget._select_file(_write(tmp_path, _ofx("99 888 777 6")))

    dialog = _open_create_dialog(widget)
    assert dialog.entered_name() == "", "OFX carries no name to prefill"
    dialog.accept()

    assert len(svc.list_accounts()) == 1, "nothing created"
    assert "name" in widget._error.text().lower()
    # Still offered, so the user can correct it rather than losing the path.
    assert not widget._create_account_button.isHidden()


def test_create_dialog_prefills_from_the_statement() -> None:
    """Family B determines the type; family A does not (it spans three types)."""
    from finbreak.ui.account_create import CreateAccountDialog

    loan = CreateAccountDialog(number="447556667", name=None, family="B")
    assert loan.entered_number() == "447556667"
    assert loan.entered_name() == ""
    assert loan.entered_type() == "home_loan"

    current = CreateAccountDialog(
        number="11 222 333 4", name="PRESTIGE CURRENT ACCOUNT", family="A"
    )
    assert current.entered_name() == "PRESTIGE CURRENT ACCOUNT"
    assert current.entered_type() == "current", "family A infers nothing; first entry"


def test_ambiguous_leaves_the_pick_step_selection(qtbot, service, tmp_path):
    """Two accounts on one number is the case a first-candidate-wins implementation
    would resolve silently and wrongly. Stored in two spellings so the collision
    has to survive normalisation."""
    svc = _accounts(service)
    seeded = svc.list_accounts()[0].id
    svc.add_account("Savings", "savings", account_number="22 333 444 5")
    svc.add_account("Savings 2", "savings", account_number="0223334445")

    widget = _wizard(qtbot, service, seeded)
    widget._select_file(_write(tmp_path, _ofx("223334445")))

    assert widget._confirm_account_combo.currentData() == seeded
    assert widget._preview is not None
    assert widget._preview.account_id == seeded
