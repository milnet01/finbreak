"""AccountService — validation + the delete guard around AccountRepository.

Owns name/type validation (FIBR-0005 INV-2/INV-3) and the delete guard (INV-6):
an in-use account is blocked, and the last remaining account cannot be deleted,
so a transaction always has an account to belong to.
"""

from __future__ import annotations

import logging
from typing import cast

from finbreak.errors import AccountInUseError, LastAccountError
from finbreak.models import Account, AccountType
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.vault import Vault

log = logging.getLogger(__name__)


class AccountService:
    def __init__(self, vault: Vault):
        self._vault = vault

    def _accounts(self) -> AccountRepository:
        return AccountRepository(self._vault.connection)

    def list_accounts(self) -> list[Account]:
        return self._accounts().list_all()

    def add_account(self, name: str, type: str) -> Account:
        name = self._validate(name, type)
        repo = self._accounts()
        account_id = repo.add(name, type)
        log.info("account created")
        # get() is Optional; the row was just inserted, so it is present.
        return cast(Account, repo.get(account_id))

    def update_account(self, account_id: int, name: str, type: str) -> None:
        name = self._validate(name, type, exclude_id=account_id)
        self._accounts().update(account_id, name, type)
        log.info("account updated")

    def delete_account(self, account_id: int) -> None:
        repo = self._accounts()
        in_account = TransactionRepository(self._vault.connection).count_for_account(
            account_id
        )
        if in_account > 0:
            raise AccountInUseError(
                "this account still has transactions — move or remove them first"
            )
        # "Last account" = the target actually exists AND is the only row; the
        # "exists" clause is what lets a missing id fall through to a no-op.
        if repo.get(account_id) is not None and repo.count() == 1:
            raise LastAccountError("at least one account must always exist")
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

    def _validate(self, name: str, type: str, exclude_id: int | None = None) -> str:
        """Return the trimmed name, or raise ``ValueError`` (INV-2/INV-3)."""
        try:
            AccountType(type)  # membership check — the closed-set gate
        except ValueError as exc:
            raise ValueError(f"unknown account type: {type!r}") from exc
        name = name.strip()
        if not name:
            raise ValueError("account name must not be empty")
        lowered = name.casefold()
        for existing in self._accounts().list_all():
            if existing.id == exclude_id:
                continue
            if existing.name.casefold() == lowered:
                raise ValueError(f"an account named {name!r} already exists")
        return name
