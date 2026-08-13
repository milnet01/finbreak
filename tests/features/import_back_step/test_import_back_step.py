"""Feature-conformance tests — the import preview step can go Back (FIBR-0270).

Enforces `spec.md` beside this file. FIBR-0146 D7's all-rows-failed banner tells
the user to "Go back and check the column mapping"; the wizard had no back
control, so the remedy named a screen with no route to it. These tests pin the
control, the two sources that must NOT offer it, and the matched-profile case
that re-picking the file cannot fix.

Every vault uses `tmp_path`; fixtures are tiny in-repo strings plus the existing
`standard_bank_pdf` PDF — no real statements, no network (testing.md § 6).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from conftest import _PW, _acct
from finbreak.models import ColumnMapping
from finbreak.services.auth import AuthService
from finbreak.ui.import_wizard import _STEP_MAP, _STEP_PREVIEW, ImportWizardWidget

# The date column is deliberately NOT header[0]: an empty combo sits at index 0,
# so a form left at its defaults would answer "Ref" and fail INV-4 loudly rather
# than pass by coincidence.
HEADER = ["Ref", "Posted", "Details", "Amount"]
ROWS = [
    ["R1", "20/07/2026", "Coffee", "-10.00"],
    ["R2", "21/07/2026", "Tea", "-5.00"],
]


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _wizard(qtbot, service, acct) -> ImportWizardWidget:
    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget._account_combo.setCurrentIndex(widget._account_combo.findData(acct))
    return widget


def _write(tmp_path: Path, header: list[str], rows: list[list[str]]) -> str:
    text = ",".join(header) + "\n" + "".join(",".join(r) + "\n" for r in rows)
    path = tmp_path / "stmt.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _fill_map_form(widget: ImportWizardWidget) -> None:
    """Point the map step's role combos at HEADER's columns."""
    for role, column in (
        ("date", "Posted"),
        ("description", "Details"),
        ("amount", "Amount"),
    ):
        combo = widget._column_combos[role]
        combo.setCurrentIndex(combo.findData(column))


def test_INV1_back_returns_an_unmatched_csv_to_the_map_step(qtbot, service, tmp_path):
    """INV-1 — the control exists, it navigates, and it does not reset the form.

    Landing back on a *blank* map step would be a re-entry dressed up as a
    correction, so the mapping the preview was built from is asserted after the
    trip, not just the step index.
    """
    acct = _acct(service)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(_write(tmp_path, HEADER, ROWS))
    assert widget._stack.currentIndex() == _STEP_MAP, (
        "precondition: an unmatched CSV shows the map step (FIBR-0146 D5a)"
    )

    _fill_map_form(widget)
    widget._on_map_next()
    assert widget._stack.currentIndex() == _STEP_PREVIEW, (
        "precondition: a valid mapping reaches the preview step"
    )

    assert not widget._back_button.isHidden(), (
        "a mapped source must offer the way back its banner names"
    )
    widget._back_button.click()
    assert widget._stack.currentIndex() == _STEP_MAP, "Back returns to the map step"
    assert widget._column_combos["date"].currentData() == "Posted", (
        "Back is a correction, not a re-entry — the form keeps what it had"
    )
    assert widget._column_combos["amount"].currentData() == "Amount"

    # And the round trip completes: Next from the returned-to form re-previews.
    widget._on_map_next()
    assert widget._stack.currentIndex() == _STEP_PREVIEW, "Next still works after Back"


def test_INV2_the_go_back_remedy_is_followable(qtbot, service, tmp_path):
    """INV-2 — FIBR-0270's actual defect: the banner named an unreachable screen.

    Asserted against the shipped sentence rather than assumed, so rewording the
    banner without providing the control (or removing the control and leaving the
    sentence) fails here.
    """
    from finbreak.importers.base import RowError
    from finbreak.services.import_ import ImportPreview

    acct = _acct(service)
    widget = _wizard(qtbot, service, acct)
    widget._select_file(_write(tmp_path, HEADER, ROWS))
    _fill_map_form(widget)
    widget._on_map_next()

    all_error = ImportPreview(acct, [], [RowError(1, "x")], 0, 0, None, None)
    widget._apply_preview_counts(all_error)
    assert not widget._preview_banner.isHidden(), (
        "precondition: 0 new · 0 dup · N error fires the D7 banner"
    )
    assert "Go back" in widget._preview_banner.text(), (
        "precondition: the mapped-source remedy is the one that names a control"
    )
    assert not widget._back_button.isHidden(), (
        "the banner tells the user to go back; the control must be on that screen"
    )


def test_INV3_a_self_describing_source_offers_no_back(qtbot, service):
    """INV-3 — a recognised Standard Bank statement skips mapping, so Back would
    land on a form the user was never shown and that decides nothing."""
    acct = _acct(service)
    widget = _wizard(qtbot, service, acct)
    fixture = (
        Path(__file__).parent.parent
        / "standard_bank_pdf"
        / "fixtures"
        / "family_a_zero_fee.pdf"
    )
    widget._select_file(str(fixture))
    assert widget._has_mapping_step is False, (
        "precondition: a RECOGNISED SB statement skips the map step"
    )
    assert widget._stack.currentIndex() == _STEP_PREVIEW, (
        "precondition: it goes straight to the preview"
    )
    assert widget._back_button.isHidden(), "no map step -> Back would land nowhere"


def test_INV4_back_after_a_matched_profile_shows_the_stored_mapping(
    qtbot, service, tmp_path
):
    """INV-4 — the case re-picking the file cannot fix.

    A matched profile jumps straight to the preview, so the mapping combos were
    never filled from it. Back must show the mapping actually in force, and an
    edit there must re-preview under the correction — otherwise a wrong saved
    profile is a dead end.
    """
    acct = _acct(service)
    widget = _wizard(qtbot, service, acct)
    stored = ColumnMapping("Posted", "Details", "Amount", None, None, "%d/%m/%Y", False)
    widget._imports.save_profile("test-bank", HEADER, stored)

    widget._select_file(_write(tmp_path, HEADER, ROWS))
    assert widget._stack.currentIndex() == _STEP_PREVIEW, (
        "precondition: an exact-signature match skips the map step (INV-10a)"
    )
    assert widget._has_mapping_step is True, (
        "precondition: a matched CSV is still a mapped source"
    )
    assert not widget._back_button.isHidden(), (
        "the profile is what is wrong, so this is the case that most needs Back"
    )

    widget._back_button.click()
    assert widget._stack.currentIndex() == _STEP_MAP
    assert widget._column_combos["date"].currentData() == "Posted", (
        "a form the user never saw must show the profile actually in force, "
        "not combo defaults (HEADER[0] is 'Ref', so defaults answer 'Ref')"
    )
    assert widget._column_combos["description"].currentData() == "Details"
    assert widget._column_combos["amount"].currentData() == "Amount"
    assert widget._selected_date_format() == "%d/%m/%Y", (
        "the stored format is authoritative and must survive the trip back"
    )

    # The correction round-trips: re-previewing from the returned-to form works.
    widget._on_map_next()
    assert widget._stack.currentIndex() == _STEP_PREVIEW
