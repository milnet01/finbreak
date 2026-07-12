"""TransferDetectionService — the suggest-then-confirm transfer engine (FIBR-0011).

Mirrors ``CategorizationService`` (the name design.md + ROADMAP already use for
this component): a ``_conn`` property + a ``TransferRepository`` accessor. It turns
the repository's ``(debit_id, credit_id)`` candidate tuples into display-ready
``TransferCandidate`` / ``ConfirmedTransfer`` records (resolving each pair's two
``Transaction`` rows, the shared display magnitude, and both account names once per
call), and records the user's confirm/reject/unlink decisions — never touching a
``transactions`` row (INV-12). Only confirmed pairs enter
``confirmed_transfer_txn_ids()``, the exclusion primitive FIBR-0012 consumes (INV-5).
"""

from __future__ import annotations

import logging

from sqlcipher3 import dbapi2

from finbreak.models import (
    ConfirmedTransfer,
    Transaction,
    TransferCandidate,
    TransferStatus,
)
from finbreak.repositories.accounts import AccountRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.repositories.transfers import TransferRepository
from finbreak.services.transactions import read_minor_unit_exponent, to_display_decimal
from finbreak.vault import Vault

log = logging.getLogger(__name__)


class TransferDetectionService:
    def __init__(self, vault: Vault):
        self._vault = vault

    @property
    def _conn(self) -> dbapi2.Connection:
        return self._vault.connection

    def _transfers(self) -> TransferRepository:
        return TransferRepository(self._conn)

    # -- reads ----------------------------------------------------------------
    def candidates(self) -> list[TransferCandidate]:
        """The live list of suggested (undecided) pairs (INV-1/INV-7). Resolves each
        ``(debit_id, credit_id)`` against a ``{txn.id: Transaction}`` map + an
        id->account-name map, both built once per call (there is no get-by-id)."""
        pairs = self._transfers().candidate_pairs()
        if not pairs:
            return []
        txns, names, exponent = self._resolve_context()
        return [
            self._make_candidate(txns[debit_id], txns[credit_id], names, exponent)
            for debit_id, credit_id in pairs
        ]

    def confirmed_transfers(self) -> list[ConfirmedTransfer]:
        """The confirmed transfers for the tab's Confirmed table + Unlink — the
        pair id + both resolved rows + display + from/to names (INV-6/INV-10)."""
        confirmed = self._transfers().list_confirmed()
        if not confirmed:
            return []
        txns, names, exponent = self._resolve_context()
        result: list[ConfirmedTransfer] = []
        for pair in confirmed:
            a, b = txns[pair.txn_a_id], txns[pair.txn_b_id]
            debit, credit = (a, b) if a.amount_minor < 0 else (b, a)
            cand = self._make_candidate(debit, credit, names, exponent)
            result.append(
                ConfirmedTransfer(
                    pair.id,
                    cand.debit,
                    cand.credit,
                    cand.display_amount,
                    cand.from_account,
                    cand.to_account,
                )
            )
        return result

    def confirmed_transfer_txn_ids(self) -> set[int]:
        """The INV-5 exclusion primitive: the ids in every confirmed pair (the set
        FIBR-0012's dashboard totals will drop as internal movement)."""
        return self._transfers().confirmed_txn_ids()

    # -- decisions (each write is one per-decision commit, D6) ----------------
    def confirm(self, debit_id: int, credit_id: int) -> None:
        """Confirm a candidate as a transfer (INV-1). Raises ``ValueError`` (never a
        raw ``IntegrityError``) if either txn is already in a confirmed pair (INV-4)
        or the canonical pair is already decided (confirmed or rejected)."""
        self._record(debit_id, credit_id, TransferStatus.CONFIRMED)
        log.info("transfer confirmed")

    def reject(self, debit_id: int, credit_id: int) -> None:
        """Remember a rejection so the pair is never re-offered (INV-3). Same
        undecided-pair guard as ``confirm``."""
        self._record(debit_id, credit_id, TransferStatus.REJECTED)
        log.info("transfer rejected")

    def unlink(self, pair_id: int) -> None:
        """Delete a confirmed transfer, returning the pair to candidates (INV-6). A
        silent no-op on an absent or non-confirmed id (``delete_confirmed`` filters
        ``status = 'confirmed'``) — the UI only ever passes a confirmed pair's id."""
        self._transfers().delete_confirmed(pair_id)
        log.info("transfer unlinked")

    def confirm_all(self) -> int:
        """Confirm every current candidate, greedily + consumption-safe (INV-4/D7):
        iterate the deterministic candidate order, skipping any pair whose debit or
        credit an earlier confirm in this pass already consumed, and return the count
        committed. So a debit matching two credits is confirmed against the first and
        its second candidate is dropped — never a double-link."""
        consumed: set[int] = set()
        count = 0
        for debit_id, credit_id in self._transfers().candidate_pairs():
            if debit_id in consumed or credit_id in consumed:
                continue
            self._transfers().add_decision(
                debit_id, credit_id, TransferStatus.CONFIRMED.value
            )
            consumed.update((debit_id, credit_id))
            count += 1
        log.info("confirmed %d transfer(s)", count)
        return count

    # -- helpers --------------------------------------------------------------
    def _record(self, debit_id: int, credit_id: int, status: TransferStatus) -> None:
        repo = self._transfers()
        if repo.is_confirmed(debit_id) or repo.is_confirmed(credit_id):
            raise ValueError(
                "a transaction can belong to at most one confirmed transfer"
            )
        if repo.pair_decided(debit_id, credit_id):
            raise ValueError("this transfer pair has already been decided")
        repo.add_decision(debit_id, credit_id, status.value)

    def _resolve_context(
        self,
    ) -> tuple[dict[int, Transaction], dict[int, str], int]:
        """The three per-call lookups shared by ``candidates`` +
        ``confirmed_transfers``: id->Transaction, account id->name, and the single
        base-currency minor-unit exponent."""
        conn = self._conn
        txns = {t.id: t for t in TransactionRepository(conn).list_all()}
        names = {a.id: a.name for a in AccountRepository(conn).list_all()}
        return txns, names, read_minor_unit_exponent(conn)

    def _make_candidate(
        self,
        debit: Transaction,
        credit: Transaction,
        names: dict[int, str],
        exponent: int,
    ) -> TransferCandidate:
        """One ``TransferCandidate`` from its resolved debit/credit rows — the shared
        display magnitude is the credit side (positive), From/To are the debit's /
        credit's account names."""
        return TransferCandidate(
            debit=debit,
            credit=credit,
            display_amount=to_display_decimal(credit.amount_minor, exponent),
            from_account=names.get(debit.account_id, ""),
            to_account=names.get(credit.account_id, ""),
        )
