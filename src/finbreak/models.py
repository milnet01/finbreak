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


class CategorySource(StrEnum):
    """How a transaction's category was set (FIBR-0010). ``MANUAL`` is frozen —
    the rule engine never touches it; ``RULE`` was set by a rule and is recomputed
    on every apply. A ``None`` source is a never-touched auto row. The ``.value``
    is the stored, non-translated token."""

    RULE = "rule"
    MANUAL = "manual"


@dataclass
class Transaction:
    """One row of the ``transactions`` table. ``category_id`` / ``category_source``
    (appended after ``created_at`` at v7, FIBR-0010) are the category link: the
    ``list_all`` SELECT names all eight columns in this order so ``Transaction(*row)``
    stays aligned. ``category_source`` is a ``CategorySource`` token or ``None``."""

    id: int
    account_id: int
    occurred_on: str
    amount_minor: int
    description: str
    created_at: str
    category_id: int | None
    category_source: str | None


@dataclass
class CategorizationRule:
    """One auto-categorisation rule (FIBR-0010): ``pattern`` (a text substring,
    normalised via ``normalise_text``) → ``category_id`` (a leaf), ordered by
    ascending ``priority`` (then ``id``) for first-match. The repository SELECT
    shares this field order so ``CategorizationRule(*row)`` stays aligned."""

    id: int
    pattern: str
    category_id: int
    priority: int
    created_at: str


class CategoryKind(StrEnum):
    """The two Type roots of the category tree (FIBR-0006 INV-2). The ``.value``
    is the stored, non-translated token carried on the root rows only; display
    labels ("Income" / "Expenditure") are a separate UI concern."""

    INCOME = "income"
    EXPENDITURE = "expenditure"


@dataclass
class ColumnMapping:
    """The mapping recipe that turns a bank's CSV columns into transaction fields
    (FIBR-0007). ``save_profile`` / ``CsvImporter.parse`` take one of these — the
    seven mapping fields only, so an unsaved wizard mapping parses identically to
    a persisted profile. Exactly one amount style is populated: ``amount_column``
    set (single signed column) **or** ``debit_column`` + ``credit_column`` set
    (the pair); the unused style's columns are ``None`` (checks test ``is not
    None``). ``invert_amount`` negates a single amount column (some banks print
    money-out as a positive figure); it is ignored for the debit/credit style."""

    date_column: str
    description_column: str
    amount_column: str | None
    debit_column: str | None
    credit_column: str | None
    date_format: str
    invert_amount: bool


@dataclass
class TransactionDraft:
    """One normalised, not-yet-saved import row (the glossary "Draft"). The
    date/debit/credit direction is carried **in** the signed ``amount_minor``,
    not a separate field; ``row_number`` (1-based over the data rows) lets the
    preview interleave drafts and errors back into file order, and is dropped
    when the draft is deduped and written as a ``Transaction``."""

    row_number: int
    occurred_on: str
    amount_minor: int
    description: str


@dataclass
class OfxAccountInfo:
    """The per-statement summary an OFX file surfaces (FIBR-0008 D8). Both fields
    come straight from the ofxparse ``Account``; ``account_type`` is ``""`` for a
    credit-card statement (``<CCSTMTRS>``), so the wizard's chooser falls back to
    the id alone. Not persisted — it only labels the statement chooser."""

    account_id: str
    account_type: str


@dataclass
class ImportProfile:
    """One saved bank layout (FIBR-0007). ``signature`` is the exact header
    fingerprint (the match key, ``UNIQUE`` at the DB). Exactly one amount style
    is populated (validated at the service layer). The repository ``SELECT`` and
    this field order share ``id, name, signature, date_column,
    description_column, amount_column, debit_column, credit_column, date_format,
    invert_amount, created_at`` so ``ImportProfile(*row)`` stays aligned."""

    id: int
    name: str
    signature: str
    date_column: str
    description_column: str
    amount_column: str | None
    debit_column: str | None
    credit_column: str | None
    date_format: str
    invert_amount: int
    created_at: str

    def column_mapping(self) -> ColumnMapping:
        """The ``ColumnMapping`` recipe carried by this profile (for parse/preview)."""
        return ColumnMapping(
            date_column=self.date_column,
            description_column=self.description_column,
            amount_column=self.amount_column,
            debit_column=self.debit_column,
            credit_column=self.credit_column,
            date_format=self.date_format,
            invert_amount=bool(self.invert_amount),
        )


@dataclass
class StatementPeriod:
    """One import's coverage-period record (FIBR-0007 D8). The repository
    ``SELECT`` and this field order share ``id, account_id, period_start,
    period_end, source_filename, imported_at`` so ``StatementPeriod(*row)`` stays
    aligned. ``period_*`` are ISO-8601 dates; ``imported_at`` a UTC timestamp."""

    id: int
    account_id: int
    period_start: str
    period_end: str
    source_filename: str | None
    imported_at: str


@dataclass
class StatementRow:
    """One row of the Statements tab (FIBR-0052 INV-7) — a **view** row, distinct
    from the persistence ``StatementPeriod``: it carries the joined account
    ``name`` and the derived count of transactions currently linked to the
    statement (``statement_period_id = id``), which ``StatementService`` assembles
    with a ``LEFT JOIN`` + ``COUNT`` so a zero-linked statement still appears with
    ``transaction_count`` 0. Not persisted; not a table row."""

    id: int
    account_name: str
    account_id: int
    period_start: str
    period_end: str
    source_filename: str | None
    imported_at: str
    transaction_count: int


@dataclass
class Category:
    """One node of the self-referential ``categories`` tree. ``parent_id`` is
    ``None`` for the two Type roots; ``kind`` is a ``CategoryKind`` token on the
    roots only, ``None`` on every descendant (FIBR-0006). The repository
    ``SELECT`` and this field order share ``id, parent_id, name, kind,
    created_at`` so ``Category(*row)`` stays aligned — ``id`` and ``parent_id``
    are adjacent ``int`` columns, so a swap would compile but corrupt."""

    id: int
    parent_id: int | None
    name: str
    kind: str | None
    created_at: str
