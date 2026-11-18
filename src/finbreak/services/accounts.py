"""AccountService — validation + the delete guard around AccountRepository.

Owns name/type validation (FIBR-0005 INV-2/INV-3) and the delete guard (INV-6):
an in-use account is blocked, and the last remaining account cannot be deleted,
so a transaction always has an account to belong to.
"""

from __future__ import annotations

import logging
from typing import cast

from finbreak.errors import (
    QT_TRANSLATE_NOOP,
    AccountInUseError,
    LastAccountError,
    UserMessage,
)
from finbreak.models import Account, AccountType
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.text import fold_name
from finbreak.vault import Vault

log = logging.getLogger(__name__)

# The bank the Standard Bank reader names on every hint it returns (FIBR-0284).
# One spelling for the hint and the suggestion, so they cannot drift apart.
STANDARD_BANK = "Standard Bank"

# Banks whose statements finbreak can read (FIBR-0050), offered as bank
# suggestions before the vault records any (FIBR-0283 § 3).
KNOWN_BANKS: tuple[str, ...] = (STANDARD_BANK,)


def _normalise_optional(value: str | None) -> str | None:
    """Strip, and collapse an empty result to None — so a blank form field is
    stored as SQL NULL rather than "" (FIBR-0193 INV-5).

    Idempotent (``f(f(x)) == f(x)``), which the Accounts screen's
    read-and-pass-back depends on: it re-sends an already-stored value through
    ``update_account`` on every Update click, so the value is re-stripped each
    time and must not walk away character by character.
    """
    return (value or "").strip() or None


class AccountService:
    def __init__(self, vault: Vault):
        self._vault = vault

    def _accounts(self) -> AccountRepository:
        return AccountRepository(self._vault.connection)

    def list_accounts(self) -> list[Account]:
        return self._accounts().list_all()

    # The asymmetry below is deliberate (FIBR-0193 D2/D3, FIBR-0283).
    # ``add_account``'s optional fields default to None: an omitted column on an
    # ``INSERT`` is written NULL, which is the value the caller meant.
    # ``update_account``'s are REQUIRED, because the repository issues an
    # unconditional ``UPDATE … SET`` — a defaulted ``None`` would make a call
    # that forgot one silently erase a stored account number, note or bank.
    def add_account(
        self,
        name: str,
        type: str,
        *,
        account_number: str | None = None,
        note: str | None = None,
        bank: str | None = None,
    ) -> Account:
        name = self._validate(name, type)
        repo = self._accounts()
        account_id = repo.add(
            name,
            type,
            _normalise_optional(account_number),
            _normalise_optional(note),
            _normalise_optional(bank),
        )
        log.info("account created")
        # get() is Optional; the row was just inserted, so it is present.
        return cast(Account, repo.get(account_id))

    def update_account(
        self,
        account_id: int,
        name: str,
        type: str,
        *,
        account_number: str | None,
        note: str | None,
        bank: str | None,
    ) -> None:
        name = self._validate(name, type, exclude_id=account_id)
        self._accounts().update(
            account_id,
            name,
            type,
            _normalise_optional(account_number),
            _normalise_optional(note),
            _normalise_optional(bank),
        )
        log.info("account updated")

    def bank_suggestions(self) -> list[str]:
        """The banks the vault records, then ``KNOWN_BANKS``, each once by
        ``fold_name`` (the stored spelling wins), sorted by ``fold_name``."""
        by_key: dict[str, str] = {}
        for bank in [*self._accounts().banks(), *KNOWN_BANKS]:
            by_key.setdefault(fold_name(bank), bank)
        return [by_key[key] for key in sorted(by_key)]

    def delete_account(self, account_id: int) -> None:
        repo = self._accounts()
        conn = self._vault.connection
        in_account = TransactionRepository(conn).count_for_account(account_id)
        if in_account > 0:
            raise AccountInUseError(
                UserMessage(
                    QT_TRANSLATE_NOOP(
                        "Refusal",
                        "this account still has transactions — "
                        "move or remove them first",
                    )
                )
            )
        # A statement period referencing this account also blocks deletion — a
        # quiet-month / all-duplicate import records a period with ZERO
        # transactions, so the transaction-count guard above passes but the
        # statement_periods FK (no ON DELETE CASCADE, foreign_keys = ON) would
        # otherwise raise a raw IntegrityError that escapes the FinbreakError
        # taxonomy and crashes the delete slot. (indie-review data H-1; this also
        # gives StatementPeriodRepository.list_for_account its first src caller)
        if StatementPeriodRepository(conn).list_for_account(account_id):
            raise AccountInUseError(
                UserMessage(
                    QT_TRANSLATE_NOOP(
                        "Refusal",
                        "this account still has imported statements — "
                        "delete them first",
                    )
                )
            )
        # "Last account" = the target actually exists AND is the only row; the
        # "exists" clause is what lets a missing id fall through to a no-op.
        if repo.get(account_id) is not None and repo.count() == 1:
            raise LastAccountError(
                UserMessage(
                    QT_TRANSLATE_NOOP(
                        "Refusal", "at least one account must always exist"
                    )
                )
            )
        repo.delete(account_id)
        log.info("account deleted")

    # -- remembered PDF password (FIBR-0009 D6) -------------------------------
    def get_pdf_password(self, account_id: int) -> str | None:
        """The account's remembered PDF password, or ``None`` if none is stored
        (the default). Fetched only at the moment a PDF import needs it (INV-4);
        the UI talks to the service, never the repo directly."""
        return self._accounts().get_pdf_password(account_id)

    def set_pdf_password(self, account_id: int, value: str | None) -> None:
        """Store (opt-in) or clear (``None``) the account's remembered PDF
        password (INV-4). Persisted inside the SQLCipher vault — encrypted at rest
        by the master key, no redundant second layer (D5)."""
        self._accounts().set_pdf_password(account_id, value)
        log.info("account pdf password updated")

    def account_ids_with_pdf_password(self) -> set[int]:
        """The set of account ids that have a remembered PDF password — presence
        only, never the secret itself (FIBR-0128 INV-1). Backs the Accounts-screen
        marker and the Forget button's enabled state; the UI talks to the service,
        never the repo directly."""
        return self._accounts().ids_with_pdf_password()

    def _validate(self, name: str, type: str, exclude_id: int | None = None) -> str:
        """Return the trimmed name, or raise ``ValueError`` (INV-2/INV-3)."""
        try:
            AccountType(type)  # membership check — the closed-set gate
        except ValueError as exc:
            raise ValueError(f"unknown account type: {type!r}") from exc
        name = name.strip()
        if not name:
            raise ValueError(
                UserMessage(
                    QT_TRANSLATE_NOOP("Refusal", "account name must not be empty")
                )
            )
        lowered = fold_name(name)
        for existing in self._accounts().list_all():
            if existing.id == exclude_id:
                continue
            if fold_name(existing.name) == lowered:
                raise ValueError(
                    UserMessage(
                        QT_TRANSLATE_NOOP(
                            "Refusal", "an account named {name!r} already exists"
                        ),
                        name=name,
                    )
                )
        return name
