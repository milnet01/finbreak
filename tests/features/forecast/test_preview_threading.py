"""FIBR-0171 — the closing balance is threaded importer → preview → persist
(spec D4, Deliverable 8).

`ImportPreview` carries `closing_balance_minor`, `retarget` preserves it,
`commit_import` writes it via `StatementPeriodRepository.add`, and a span-reuse
re-import fills a NULL balance but never overwrites a non-NULL one (INV-12).

Enforces tests/features/forecast/spec.md INV-8/INV-12/INV-13. tmp_path; no network.
"""

from collections.abc import Iterator

import pytest

from conftest import _PW
from finbreak.importers.base import ParseResult
from finbreak.models import TransactionDraft
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.services.accounts import AccountService
from finbreak.services.auth import AuthService
from finbreak.services.import_ import ImportService

pytestmark = pytest.mark.features

_START, _END = "2026-06-01", "2026-06-30"


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def _result(closing: int | None, day: str = "2026-06-15", minor: int = -1234):
    draft = TransactionDraft(1, day, minor, f"row-{day}-{minor}")
    return ParseResult([draft], [], _START, _END, closing)


def _stored_balance(svc: AuthService, account_id: int) -> int | None:
    repo = StatementPeriodRepository(svc.vault.connection)
    pid = repo.id_for_span(account_id, _START, _END)
    assert pid is not None
    period = repo.get(pid)
    assert period is not None
    return period.closing_balance_minor


def test_INV13_preview_carries_the_balance_and_retarget_preserves_it(service) -> None:
    svc = service
    accounts = AccountService(svc.vault)
    a = accounts.list_accounts()[0].id
    b = accounts.add_account("Second", "current").id
    imp = ImportService(svc.vault)

    preview = imp.preview_result(_result(860_000), a)
    assert preview.closing_balance_minor == 860_000

    retargeted = imp.retarget(preview, b)
    assert retargeted.closing_balance_minor == 860_000, "retarget must not drop it"
    assert retargeted.account_id == b


def test_INV13_commit_persists_the_balance_on_a_new_span(service) -> None:
    svc = service
    a = AccountService(svc.vault).list_accounts()[0].id
    imp = ImportService(svc.vault)
    preview = imp.preview_result(_result(860_000), a)
    imp.commit_import(preview, _START, _END, "june.pdf")
    assert _stored_balance(svc, a) == 860_000


def test_INV12_span_reuse_fills_a_null_balance(service) -> None:
    svc = service
    a = AccountService(svc.vault).list_accounts()[0].id
    imp = ImportService(svc.vault)
    # First import: a CSV with no balance -> span stored with NULL.
    imp.commit_import(imp.preview_result(_result(None), a), _START, _END, "june.csv")
    assert _stored_balance(svc, a) is None
    # Re-import the SAME span from a PDF that carries a balance -> fills the gap.
    imp.commit_import(
        imp.preview_result(_result(860_000, day="2026-06-16"), a),
        _START,
        _END,
        "june.pdf",
    )
    assert _stored_balance(svc, a) == 860_000


def test_INV12_span_reuse_never_overwrites_a_nonnull_balance(service) -> None:
    svc = service
    a = AccountService(svc.vault).list_accounts()[0].id
    imp = ImportService(svc.vault)
    imp.commit_import(imp.preview_result(_result(860_000), a), _START, _END, "june.pdf")
    # A re-import with a DIFFERENT balance for the fixed span must be ignored.
    imp.commit_import(
        imp.preview_result(_result(999_999, day="2026-06-16"), a),
        _START,
        _END,
        "june-again.pdf",
    )
    assert _stored_balance(svc, a) == 860_000
