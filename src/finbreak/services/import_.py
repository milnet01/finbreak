"""ImportService — orchestrates CSV import over the vault (FIBR-0007).

Owns the DB side the pure ``CsvImporter`` deliberately avoids: matching /
upserting mapping profiles, the multiset-delta dedup (D6/INV-5), the atomic
write of the deduped rows **and** the coverage-period record (D7/INV-7), and the
span-dedup (INV-6). Constructed like the other services — takes a ``Vault`` and
builds a fresh repository per operation from ``self._vault.connection``.

``signature_for`` is a module-level function (no vault needed, so the signature
is headless-testable): the **exact** header fingerprint (D4) — the tuple of
fieldnames joined in file order by ``\\x1f`` (a control char that cannot occur in
a header). A header with two equal names is refused (a name-based mapping is
ambiguous — ``csv.DictReader`` would silently collapse the columns).
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from finbreak.importers.base import ParseResult, RowError
from finbreak.importers.csv_importer import CsvImporter, read_header
from finbreak.models import ColumnMapping, ImportProfile, TransactionDraft
from finbreak.repositories.import_profiles import ImportProfileRepository
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.repositories.transactions import TransactionRepository
from finbreak.services.categorization import recategorize_auto_rows
from finbreak.services.transactions import read_minor_unit_exponent
from finbreak.text import normalise_text
from finbreak.vault import Vault

log = logging.getLogger(__name__)

_SIGNATURE_DELIMITER = "\x1f"  # unit separator — cannot occur in a CSV header

# Import file-size cap (FIBR-0008 D13/INV-10; format-neutral since FIBR-0009 D10)
# — refused BEFORE the bytes are read into memory (read_file_bytes). Shared by
# OFX and PDF, both byte-read imports. Orders of magnitude above any real
# personal statement (KB–low-MB); one-line-tunable. The per-format count caps
# (_MAX_OFX_TRANSACTIONS, _MAX_PDF_ROWS) live on their importers.
_MAX_IMPORT_BYTES = 16 * 1024 * 1024  # 16 MiB


def signature_for(header: list[str]) -> str:
    """The exact header fingerprint (D4). Case, spacing, and order are all
    significant. Raises ``ValueError`` on a duplicate column name (ambiguous)."""
    if len(set(header)) != len(header):
        raise ValueError(
            "the header has duplicate column names — a mapping is ambiguous"
        )
    return _SIGNATURE_DELIMITER.join(header)


@dataclass
class ImportPreview:
    """The no-write analysis of a file under a mapping: the parsed drafts, the
    per-row errors, the derived dedup counts, and the default coverage span."""

    account_id: int
    drafts: list[TransactionDraft]
    errors: list[RowError]
    new_count: int
    duplicate_count: int
    period_start: str | None
    period_end: str | None


@dataclass
class ImportResult:
    """The outcome of a committed import."""

    inserted_count: int
    duplicate_count: int
    error_count: int
    period_recorded: bool


class ImportService:
    def __init__(self, vault: Vault):
        self._vault = vault

    @property
    def _conn(self):
        return self._vault.connection

    @staticmethod
    def _normalise(text: str) -> str:
        """The dedup transform (D6, description-only): the shared ``normalise_text``
        (FIBR-0010 D2) — fold whitespace, then casefold, byte-identical to before.
        Distinct from ``signature_for``'s exact fingerprint."""
        return normalise_text(text)

    # -- profiles -------------------------------------------------------------
    def match_profile(self, header: list[str]) -> ImportProfile | None:
        """The saved profile whose signature exactly matches ``header``, or
        ``None`` for an unknown (but valid) header. Propagates ``ValueError`` for
        a duplicate-named header (INV-1/INV-9)."""
        signature = signature_for(header)  # raises on a duplicate-named header
        return ImportProfileRepository(self._conn).get_by_signature(signature)

    def save_profile(
        self, name: str, header: list[str], mapping: ColumnMapping
    ) -> ImportProfile:
        """Upsert a mapping profile by signature (D4): a first save inserts, a
        second under the same signature updates in place (name + mapping
        overwritten). Validates the mapping config first (``ValueError``)."""
        self._validate_mapping(mapping, header)
        signature = signature_for(header)
        repo = ImportProfileRepository(self._conn)
        existing = repo.get_by_signature(signature)
        if existing is not None:
            repo.update(existing.id, name, mapping)
        else:
            repo.add(name, signature, mapping)
        log.info("import profile saved")
        # get_by_signature is Optional; the row was just written, so it is present.
        return cast(ImportProfile, repo.get_by_signature(signature))

    # -- preview + commit -----------------------------------------------------
    def read_file(self, path: str) -> str:
        """Decode a picked CSV file as ``utf-8-sig`` so a BOM is tolerated (D11)."""
        return Path(path).read_text(encoding="utf-8-sig")

    def read_file_bytes(self, path: str) -> bytes:
        """Read a picked file as raw bytes, refusing an oversized file **before**
        loading it into memory (FIBR-0008 D13/INV-10) — the bytes counterpart to
        ``read_file``. Format-neutral (FIBR-0009 D10): the OFX **and** PDF paths
        both use it. The stat-then-read window is a benign TOCTOU for a local,
        user-picked, single-user file."""
        if Path(path).stat().st_size > _MAX_IMPORT_BYTES:
            raise ValueError("this file is too large to import")
        return Path(path).read_bytes()

    def preview(
        self, text: str, mapping: ColumnMapping, account_id: int
    ) -> ImportPreview:
        """Parse a CSV + dedup-analyse + default the period — **no write**."""
        header = read_header(text)  # raises ValueError on an empty (headerless) file
        self._validate_mapping(mapping, header)
        exponent = read_minor_unit_exponent(self._conn)
        result = CsvImporter().parse(text, mapping, exponent)
        return self._preview_from_result(result, account_id)

    def preview_result(self, result: ParseResult, account_id: int) -> ImportPreview:
        """Dedup-analyse an OFX statement's pre-built ``ParseResult`` (FIBR-0008
        D2). The OFX parse runs in the wizard (it needs no vault); the DB-side
        dedup + period-carry is the shared ``_preview_from_result`` the CSV path
        also uses, so both importers reach the identical ``commit_import``."""
        return self._preview_from_result(result, account_id)

    def retarget(self, preview: ImportPreview, account_id: int) -> ImportPreview:
        """Re-run the dedup analysis of an already-built preview under a different
        target account (FIBR-0057): the user correcting the destination on the
        wizard's preview step. The drafts, per-row errors and coverage span are
        account-independent (already parsed) — only the dedup delta and the baked
        ``account_id`` change. No write; the returned preview feeds the unchanged
        ``commit_import``, so the committed rows land on the chosen account."""
        return self._build_preview(
            account_id,
            preview.drafts,
            preview.errors,
            preview.period_start,
            preview.period_end,
        )

    def _preview_from_result(
        self, result: ParseResult, account_id: int
    ) -> ImportPreview:
        """The dedup-analysis + period-carry tail shared by ``preview`` (CSV) and
        ``preview_result`` (FIBR-0008 D2): the multiset-delta dedup delta and the
        ``ParseResult``'s coverage span carried into an ``ImportPreview``. No
        write; ``commit_import`` is unchanged and consumes either path's preview."""
        return self._build_preview(
            account_id,
            result.drafts,
            result.errors,
            result.period_start,
            result.period_end,
        )

    def _build_preview(
        self,
        account_id: int,
        drafts: list[TransactionDraft],
        errors: list[RowError],
        period_start: str | None,
        period_end: str | None,
    ) -> ImportPreview:
        """Run the multiset-delta dedup for ``account_id`` over ``drafts`` and pack
        the counts + (account-independent) errors/span into an ``ImportPreview``.
        The single construction point shared by a fresh parse
        (``_preview_from_result``) and a re-target (``retarget``, FIBR-0057)."""
        to_insert = self._dedup(account_id, drafts, TransactionRepository(self._conn))
        new_count = len(to_insert)
        return ImportPreview(
            account_id=account_id,
            drafts=drafts,
            errors=errors,
            new_count=new_count,
            duplicate_count=len(drafts) - new_count,
            period_start=period_start,
            period_end=period_end,
        )

    def commit_import(
        self,
        preview: ImportPreview,
        period_start: str,
        period_end: str,
        source_filename: str,
    ) -> ImportResult:
        """Atomically insert the deduped rows and (unless the span already exists)
        the coverage-period record — one ``BEGIN … COMMIT``/``ROLLBACK`` the
        service owns (D7/INV-7). The dedup delta and the span check are read
        **inside** the transaction, before the inserts, so nothing is counted
        then races an insert (single-connection, single-thread)."""
        self._validate_span(period_start, period_end)
        conn = self._conn
        tx_repo = TransactionRepository(conn)
        period_repo = StatementPeriodRepository(conn)
        conn.execute("BEGIN")  # first statement — own the transaction (D7)
        try:
            to_insert = self._dedup(preview.account_id, preview.drafts, tx_repo)
            # Resolve the period id FIRST so every inserted row can be stamped with
            # it (FIBR-0052 INV-8/D8): reuse the existing span's id, else create the
            # period row now and take its new id. ``period_recorded`` is true only
            # for a new span (FIBR-0007 INV-6 semantics unchanged).
            existing_id = period_repo.id_for_span(
                preview.account_id, period_start, period_end
            )
            period_recorded = existing_id is None
            if existing_id is None:
                period_id = period_repo.add(
                    preview.account_id,
                    period_start,
                    period_end,
                    Path(source_filename).name,  # store the basename, not the path
                )
            else:
                period_id = existing_id
            if to_insert:
                tx_repo.add_batch(
                    [
                        (
                            preview.account_id,
                            d.occurred_on,
                            d.amount_minor,
                            d.description,
                        )
                        for d in to_insert
                    ],
                    period_id,
                )
            # Last step before commit (FIBR-0010 D9): categorise the just-inserted
            # rows (auto/NULL) from the current rules, inside this same transaction —
            # so a fresh import arrives categorised with no uncategorised flash and no
            # second transaction. Manual rows are excluded, so INV-3 holds.
            recategorize_auto_rows(conn)
            conn.commit()
        except Exception:
            conn.rollback()  # undoes the batch inserts — leaves the vault re-openable
            raise
        log.info("import committed")
        return ImportResult(
            inserted_count=len(to_insert),
            duplicate_count=len(preview.drafts) - len(to_insert),
            error_count=len(preview.errors),
            period_recorded=period_recorded,
        )

    # -- helpers --------------------------------------------------------------
    def _dedup(
        self,
        account_id: int,
        drafts: list[TransactionDraft],
        tx_repo: TransactionRepository,
    ) -> list[TransactionDraft]:
        """The multiset-delta dedup (D6/INV-5): for each ``(occurred_on,
        amount_minor, _normalise(description))`` key, keep the **first** ``max(0,
        incoming − existing)`` drafts in file order (their raw descriptions
        preserved). Existing counts are taken against **all** rows in the bucket,
        so a duplicate of a manually-entered row is deduped too."""
        incoming = Counter(self._key(d) for d in drafts)
        existing_by_bucket: dict[tuple[str, int], Counter] = {}
        delta: dict[tuple[str, int, str], int] = {}
        for key in incoming:
            occurred_on, amount_minor, norm = key
            bucket = (occurred_on, amount_minor)
            if bucket not in existing_by_bucket:
                existing_by_bucket[bucket] = Counter(
                    self._normalise(desc)
                    for desc in tx_repo.existing_for(
                        account_id, occurred_on, amount_minor
                    )
                )
            delta[key] = max(0, incoming[key] - existing_by_bucket[bucket][norm])

        kept: Counter = Counter()
        to_insert: list[TransactionDraft] = []
        for draft in drafts:
            key = self._key(draft)
            if kept[key] < delta[key]:
                kept[key] += 1
                to_insert.append(draft)
        return to_insert

    def _key(self, draft: TransactionDraft) -> tuple[str, int, str]:
        return (
            draft.occurred_on,
            draft.amount_minor,
            self._normalise(draft.description),
        )

    @staticmethod
    def _validate_mapping(mapping: ColumnMapping, header: list[str]) -> None:
        """Exactly one amount style, every mapped column present in the header
        (D3/D5) — the form-boundary ``ValueError`` (D10)."""
        has_amount = mapping.amount_column is not None
        has_debit = mapping.debit_column is not None
        has_credit = mapping.credit_column is not None
        single = has_amount and not has_debit and not has_credit
        pair = has_debit and has_credit and not has_amount
        if not (single or pair):
            raise ValueError(
                "a mapping needs exactly one amount style: a single amount column, "
                "or a debit + credit pair"
            )
        style_cols = (
            [mapping.amount_column]
            if single
            else [mapping.debit_column, mapping.credit_column]
        )
        mapped = [mapping.date_column, mapping.description_column]
        mapped += [col for col in style_cols if col is not None]
        missing = [col for col in mapped if col not in header]
        if missing:
            raise ValueError(f"mapped column(s) not in the file header: {missing}")

    @staticmethod
    def _validate_span(period_start: str, period_end: str) -> None:
        """Hold a (possibly hand-edited) coverage span to the same ISO-date rigor
        as a transaction's date: both endpoints parse, and start <= end (INV-6)."""
        try:
            start = date.fromisoformat(period_start)
            end = date.fromisoformat(period_end)
        except (TypeError, ValueError) as exc:
            raise ValueError("period endpoints must be valid ISO-8601 dates") from exc
        if start > end:
            raise ValueError("period_start must not be after period_end")
