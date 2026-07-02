"""Plain record types (coding.md § 5.1 — dataclasses for records).

``KdfParams`` mirrors the plaintext KDF sidecar field-for-field, except its
``salt`` (bytes) serialises as the hex string ``salt_hex`` (JSON has no bytes
type). ``Transaction`` is one row of the ``transactions`` table.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# Sidecar schema version. Bumped only when the on-disk KDF record layout changes.
FORMAT_VERSION = 1


class AccountType(StrEnum):
    """The closed set of account types (FIBR-0005 INV-2). The ``.value`` is the
    stored, non-translated token; display labels are a separate UI concern."""

    CURRENT = "current"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    PERSONAL_LOAN = "personal_loan"
    HOME_LOAN = "home_loan"
    INVESTMENT = "investment"
    OTHER = "other"


@dataclass
class KdfParams:
    format_version: int
    memory_kib: int
    time_cost: int
    parallelism: int
    key_len: int
    salt_len: int
    salt: bytes

    def to_sidecar_dict(self) -> dict[str, int | str]:
        """The flat JSON object written to the sidecar — ``salt`` → ``salt_hex``."""
        return {
            "format_version": self.format_version,
            "memory_kib": self.memory_kib,
            "time_cost": self.time_cost,
            "parallelism": self.parallelism,
            "key_len": self.key_len,
            "salt_len": self.salt_len,
            "salt_hex": self.salt.hex(),
        }


@dataclass
class Account:
    id: int
    name: str
    type: str
    created_at: str


@dataclass
class Transaction:
    id: int
    account_id: int
    occurred_on: str
    amount_minor: int
    description: str
    created_at: str
