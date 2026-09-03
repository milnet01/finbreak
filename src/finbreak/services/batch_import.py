"""BatchImportService — import several statement files in one unattended run.

The design contract is ``docs/specs/FIBR-0085-batch-statement-import.md``; the
section references below point at it.

**Headless on purpose** (§ 4.1). Every decision the batch makes lives here —
the SCAN classify/parse/match ladder, the stored-password ladder, the
cumulative dedup counts, the REVIEW re-derivation, the two caps, and the
per-file RUN step — so all of it is testable without Qt. What is *not* here is
ASK: a ``PasswordDialog`` and the wizard's mapping page are widgets, so the
widget pulls a question through ``next_question`` and pushes the reply back
through ``answer``. That seam is **inverted rather than asynchronous** because
the non-blocking dialog contract (FIBR-0065) means a dialog returns immediately
and the answer arrives on a signal — there is nothing to await inside a Qt slot.

``ImportService`` is deliberately unchanged: this module holds the per-file loop
and calls the existing one-file methods, which is what keeps ``commit_import``'s
single-file transaction boundary exactly as INV-2 requires.

The scan and the run are driven one file per event-loop turn by the widget
(§ 4.7), so both are exposed as ``scan_step`` / ``run_step`` over an index
rather than as loops — a headless caller walks the identical steps in a plain
``while``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from finbreak.errors import FinbreakError
from finbreak.importers.base import ParseResult, SourceAccountHint
from finbreak.importers.csv_importer import CsvImporter, read_header
from finbreak.importers.ofx_importer import OfxImporter
from finbreak.importers.pdf_importer import (
    PasswordError,
    PdfError,
    PdfImporter,
    default_table_index,
    table_to_text,
)
from finbreak.importers.sniff import looks_like_ofx, looks_like_pdf
from finbreak.importers.standard_bank import StandardBankImporter
from finbreak.models import Account, ColumnMapping
from finbreak.repositories.statement_periods import StatementPeriodRepository
from finbreak.services.account_match import match_account
from finbreak.services.accounts import AccountService
from finbreak.services.import_ import ImportPreview, ImportResult, ImportService
from finbreak.services.transactions import read_minor_unit_exponent
from finbreak.vault import Vault

# Both caps refuse rather than raise (INV-11). The file cap counts SELECTED
# FILES — not the statements a multi-statement OFX fans out into — because that
# is the number the user chose. The draft cap bounds what is held in memory at
# once: every scanned file keeps its drafts until the run ends (§ 10).
_MAX_BATCH_FILES = 200
_MAX_BATCH_DRAFTS = 200_000

# The two `not_attempted` wordings (§ 4.8). One outcome reached from two passes
# means two different things to the user, and "the batch was cancelled" is
# simply false for someone who selected 201 files and cancelled nothing. They
# are carried in `reason` — widening its "user-facing text for failed/skipped"
# role, since § 4.2 gives `not_attempted` no other field to distinguish them.
CANCELLED = "Not imported — the batch was cancelled"
CAP_REACHED = "Not imported — the batch reached its size limit"

# SCAN failure text reuses the wizard's existing friendly strings (§ 4.8) rather
# than inventing a second vocabulary for the same errors. This one is the
# service-side copy of `ImportWizardWidget._show_pdf_read_error`'s sentence: a
# `PdfError`'s own `str` is raw pikepdf internals ("unable to find trailer
# dictionary while recovering damaged file"). It is duplicated rather than
# shared because the wizard's copy is `tr()`-wrapped and this module is Qt-free.
PDF_UNREADABLE = "Couldn't read this PDF — try your bank's CSV or OFX export."
UNDATED = "No dated transactions found in this file"
SKIPPED_LOCKED = "Skipped — we couldn't unlock this file"
SKIPPED_UNMAPPED = "Skipped — no column mapping was set"

Outcome = Literal[
    "waiting",  # selected, not yet reached by SCAN  (initial value)
    "ready",  # parsed, account known, will commit
    "already_imported",  # span exists and zero new rows; set in REVIEW
    "needs_password",  # a locked PDF, no working password yet
    "needs_mapping",  # a CSV whose header matches no saved profile
    "needs_account",  # parsed, but match_account did not resolve one
    "failed",  # unreadable / unparseable / no dated rows; see `reason`
    "skipped",  # the user declined, or three prompts were exhausted
    "committed",  # RUN completed it; `result` carries the counts
    "not_attempted",  # a cap stopped SCAN, or cancel stopped RUN, before it
]

# The outcomes a record can no longer move out of. `already_imported` is
# pointedly NOT among them: it is re-derived in both directions on every REVIEW
# pass, and freezing it is exactly the silent data loss INV-10 exists to stop.
_TERMINAL: frozenset[str] = frozenset(
    {"committed", "failed", "skipped", "not_attempted"}
)
# Public alias — the review widget needs the same set to decide which rows may
# still be given an account, and a second hand-written copy of it there is a
# second definition that will drift.
TERMINAL_OUTCOMES = _TERMINAL

# What ASK is for. An account does NOT block a parse, which is why it is settled
# on the review screen instead (§ 3 decision 5).
_BLOCKING: frozenset[str] = frozenset({"needs_password", "needs_mapping"})

# Every outcome that is not yet settled one way or the other. The three INV-3
# names, PLUS `waiting`: a record nobody has reached yet owes no answer, but it
# is just as unfinished, and leaving it out let `Import all` go live the moment
# the FIRST file matched an account — while twenty-nine others were still
# unread and the scan chain was still armed.
_UNSETTLED: frozenset[str] = _BLOCKING | {"needs_account", "waiting"}

# The reply a widget pushes back for one question: a password, a column mapping,
# or `None` for "the user declined this file".
type Answer = str | ColumnMapping | None


@dataclass
class BatchFile:
    """One selected file — or one STATEMENT within a multi-statement OFX — from
    selection through to its committed result.

    Mutable by design: every field but ``path`` is written as the passes advance
    (§ 4.2). ``ImportPreview`` carries no filename, format or hint, so the batch
    has to keep its own association.
    """

    path: str  # full path; basename for display
    outcome: Outcome = "waiting"
    statement_index: int | None = None  # OFX fan-out; None for every other format
    parsed: ParseResult | None = None  # kept: the account may be set later
    preview: ImportPreview | None = None  # None until an account is known
    hint: SourceAccountHint | None = None  # ParseResult.source_account
    account_id: int | None = None  # the destination, once settled
    reason: str = ""  # user-facing text for failed/skipped/not_attempted
    pending_password: str | None = None  # § 4.4 — held, not yet written
    remember_password: bool = False  # § 4.4 — the dialog's tick
    result: ImportResult | None = None  # None until committed
    new_count: int = 0  # § 4.5 cumulative
    duplicate_count: int = 0  # § 4.5 cumulative
    error_count: int = 0  # unparseable ROWS, which the table would else hide

    # -- SCAN resume state ---------------------------------------------------
    # § 4.3 requires an answered file to "re-enter SCAN at the step that stopped
    # it": a password resumes at decrypt, a mapping at `CsvImporter().parse`.
    # `pending_password` carries the first; these two carry the second, and the
    # already-read text besides — so answering a mapping does not re-read the
    # file (nor re-extract a PDF's table).
    source_text: str | None = None  # CSV text, or a PDF table serialised to CSV
    mapping: ColumnMapping | None = None  # the mapping ASK supplied

    @property
    def sort_key(self) -> tuple[str, int]:
        """Commit order (§ 4.2). Sorted rather than taken as ``QFileDialog``
        returned it, because that selection order is not a defined sort and
        INV-4's reproducibility needs two runs over the same files to claim rows
        in the same order. ``statement_index`` breaks the tie within one OFX
        file, whose statements share a path; it is coalesced to 0 because
        sorting a mixed ``None``/``int`` column raises ``TypeError``."""
        return (self.path, self.statement_index or 0)


def stored_passwords(
    accounts: Sequence[Account], get: Callable[[int], str | None]
) -> list[str]:
    """Each account's remembered PDF password, de-duplicated, order stable.

    A batch has no pick-step account to key a lookup on (§ 2.3), so it tries
    every account's remembered password before prompting. All of them are the
    same person's own vault, so trying account A's password against account B's
    statement discloses nothing the user does not already hold.

    The de-duplication is INV-9: without it a password shared by three accounts
    is tried once per account holding it — invisible on success, and a
    quadratic-looking stall on a large account list.
    """
    seen: list[str] = []
    for account in accounts:
        password = get(account.id)
        if password and password not in seen:
            seen.append(password)
    return seen


def next_question(files: Sequence[BatchFile]) -> BatchFile | None:
    """The next record needing a password or a mapping, or ``None`` when ASK is
    exhausted. Pure — it reads outcomes, it does not show anything."""
    for record in files:
        if record.outcome in _BLOCKING:
            return record
    return None


def cumulative_counts(files: Sequence[BatchFile], imports: ImportService) -> None:
    """Set ``new_count`` AND ``duplicate_count`` on every record WITH A PREVIEW.

    ``ImportService._dedup`` runs its multiset delta against **committed** rows
    only, so two files in one batch that overlap each other each preview their
    shared rows as new — nothing is committed yet, so nothing dedups them
    against each other. ``commit_import`` re-runs the delta inside its own
    transaction, so the *result* is always right; the defect is confined to the
    screen the user is asked to approve, which would promise more than lands.

    The domain is ``preview is not None`` — **not** ``outcome == "ready"``. Two
    reasons, and the second is the one that bites: this runs BEFORE REVIEW sets
    the ready/already_imported outcomes on the same pass, so "the ready records"
    names a set that does not exist yet; and an ``already_imported`` record must
    keep having its counts recomputed, or a later retarget can never see its
    ``new_count`` rise above zero and it can never return to ``ready`` (INV-10).

    The baseline for each record is the existing vault rows for its account
    **plus** the drafts claimed by earlier records in this batch. The vault half
    arrives already applied: ``preview.duplicate_row_numbers`` is exactly the
    set the vault-only delta dropped, so the drafts *not* in it are what this
    record would insert against the vault alone. The batch half is ``claimed``
    below, which only ever grows — an earlier record's inserted rows are in the
    vault by the time a later one commits, so they absorb a duplicate from every
    subsequent record, not just the next one.

    Walks in commit order, scoped per destination account, because dedup is
    per-account: two files landing in different accounts never dedup against
    each other however identical their rows. The key is the one
    ``ImportService._key`` builds — ``(occurred_on, amount_minor,
    _normalise(description))`` — so this is the same equality the commit will
    apply, not a second opinion about it.

    **Both counts move together, and that is not a detail** (INV-4). Making only
    ``new_count`` cumulative while the Duplicate column kept reading
    ``preview.duplicate_count`` would put two numbers computed under different
    rules side by side on the approval screen: the second file's shared rows
    would be subtracted from New and never appear under Duplicate, so New +
    Duplicate would not account for the file's rows.
    """
    claimed: dict[int, Counter[tuple[str, int, str]]] = {}
    for record in files:
        preview = record.preview
        if preview is None or record.outcome in _TERMINAL:
            continue
        against_vault = Counter(
            imports._key(draft)
            for draft in preview.drafts
            if draft.row_number not in preview.duplicate_row_numbers
        )
        account_claims = claimed.setdefault(preview.account_id, Counter())
        new_count = 0
        for key, count in against_vault.items():  # each key visited once per record
            take = max(0, count - account_claims[key])
            new_count += take
            account_claims[key] += take
        record.new_count = new_count
        record.duplicate_count = len(preview.drafts) - new_count


class BatchImportService:
    def __init__(self, vault: Vault):
        self._vault = vault
        self._imports = ImportService(vault)
        self._accounts = AccountService(vault)
        # A vault-level setting, not per-account (§ 4.3), so it is settled once
        # before SCAN starts and is unaffected by the account question moving to
        # the review screen.
        self._exponent = read_minor_unit_exponent(vault.connection)
        # Passwords typed during THIS run. Without them a first batch of thirty
        # same-bank PDFs is thirty prompts — an "unattended" feature that asks
        # thirty questions — because the stored list is empty until something is
        # remembered, and *Remember* may never be ticked (§ 4.4). Held in memory
        # for the run only; only a *Remember*-ticked one is ever written.
        self._run_passwords: list[str] = []

    # -- selection ------------------------------------------------------------
    def build(self, paths: Sequence[str]) -> list[BatchFile]:
        """One record per selected file, in commit order — or, over the file cap,
        the same records already refused (INV-11).

        The cap is applied here, **before anything is read**, so an over-large
        selection costs no disk at all.
        """
        files = sorted(
            (BatchFile(path=path) for path in paths), key=lambda r: r.sort_key
        )
        if len(files) > _MAX_BATCH_FILES:
            for record in files:
                record.outcome = "not_attempted"
                record.reason = CAP_REACHED
        return files

    @staticmethod
    def draft_total(files: Sequence[BatchFile]) -> int:
        """Drafts held by the batch so far — the draft cap's meter. Counts a
        fanned-out OFX statement's drafts individually (§ 4.2)."""
        return sum(len(r.parsed.drafts) for r in files if r.parsed is not None)

    # -- SCAN -----------------------------------------------------------------
    def scan_step(self, files: list[BatchFile], index: int) -> int:
        """Scan ``files[index]`` and return the index to resume at — one
        event-loop turn's work (§ 4.7).

        A multi-statement OFX is spliced in immediately after its own record, so
        the list stays in commit order and the returned index skips the
        statements this call already settled.
        """
        record = files[index]
        # A record that is already settled is never re-read. Without this the
        # FILE CAP is decorative: `build` marks an over-cap selection
        # `not_attempted`, and the widget arms the chain regardless, so every
        # one of the 201 refused files was opened, parsed and held in memory —
        # its outcome overwritten, its "reached its size limit" reason left
        # stranded under a `needs_account` status — and the refused batch then
        # imported in full. It also makes a re-entered chain idempotent rather
        # than re-parsing a file and re-fanning-out an OFX.
        if record.outcome in _TERMINAL:
            return index + 1
        if self.draft_total(files) >= _MAX_BATCH_DRAFTS:
            self.stop_from(files, index, CAP_REACHED)
            return len(files)
        extras = self.scan(record)
        files[index + 1 : index + 1] = extras
        return index + 1 + len(extras)

    def scan(self, record: BatchFile) -> list[BatchFile]:
        """Advance one record through the SCAN ladder, settling its outcome.

        Returns the ADDITIONAL records created by an OFX fan-out (empty for
        every other format, and for OFX after the first statement).
        """
        try:
            if looks_like_ofx(record.path):
                return self._scan_ofx(record)
            if looks_like_pdf(record.path):
                self._scan_pdf(record)
            else:
                self._scan_csv(record)
        except PdfError as exc:
            self._fail(record, PDF_UNREADABLE, exc)
        except (ValueError, OSError, FinbreakError) as exc:
            # The same net the wizard's single-file path uses, not a bare
            # `except Exception` (coding.md § 2): an unexpected type still
            # escapes and is a bug, where "continue past anything" would hide
            # one behind a per-file report line.
            self._fail(record, str(exc), exc)
        return []

    @staticmethod
    def _fail(record: BatchFile, reason: str, _exc: Exception) -> None:
        record.outcome = "failed"
        record.reason = reason

    def _scan_ofx(self, record: BatchFile) -> list[BatchFile]:
        """Fan a multi-statement OFX out into one record per statement (INV-15).

        ``OfxImporter.parse`` returns a list because a single OFX file can carry
        several statements, each potentially for a *different* account. Taking
        only the first would silently discard the rest — and the wizard's
        single-file path already models this correctly with its chooser, so a
        batch that collapsed it would regress behaviour that ships today.

        ``OfxAccountInfo`` is destructured and discarded: the hint comes from
        ``parsed.source_account``, which ``OfxImporter`` already sets per
        statement, so every format reaches the identical ``match_account`` call.
        """
        data = self._imports.read_file_bytes(record.path)
        statements = OfxImporter().parse(data, self._exponent)
        extras: list[BatchFile] = []
        for index, (_info, parsed) in enumerate(statements):
            target = record if index == 0 else BatchFile(path=record.path)
            target.statement_index = index
            self._settle_parse(target, parsed)
            if index:
                extras.append(target)
        return extras

    def _scan_pdf(self, record: BatchFile) -> None:
        """Decrypt (§ 4.4), then the Standard Bank reader, then the generic table
        extractor feeding the CSV ladder — the same order the wizard uses."""
        if record.source_text is None:  # not already extracted by an earlier pass
            data = self._imports.read_file_bytes(record.path)
            plaintext = self._decrypt(record, data)
            if plaintext is None:
                return  # needs_password — ASK will come back to this record
            sb_result = StandardBankImporter().parse(plaintext, self._exponent)
            if sb_result is not None:
                self._settle_parse(record, sb_result)
                return
            candidates = PdfImporter().candidate_tables(plaintext)
            record.source_text = table_to_text(
                candidates[default_table_index(candidates)]
            )
        self._scan_csv(record)

    def _decrypt(self, record: BatchFile, data: bytes) -> bytes | None:
        """No password, then each distinct known password once, then the user.

        Returns the plaintext, or ``None`` having marked the record
        ``needs_password``. Any non-password failure propagates to ``scan``'s
        net, so the friendly-message mapping has one home.
        """
        for password in [None, *self._password_ladder()]:
            try:
                return PdfImporter.decrypt_to_plaintext(data, password)
            except PasswordError:
                continue
        record.outcome = "needs_password"
        return None

    def _password_ladder(self) -> list[str]:
        """Every account's remembered password, then every password typed so far
        in this run — each distinct string once (INV-9)."""
        ladder = stored_passwords(
            self._accounts.list_accounts(), self._accounts.get_pdf_password
        )
        for password in self._run_passwords:
            if password not in ladder:
                ladder.append(password)
        return ladder

    def _scan_csv(self, record: BatchFile) -> None:
        """Read (size-capped), match a saved profile, parse. Reached directly for
        a CSV and, via a serialised table, for a non-Standard-Bank PDF."""
        if record.source_text is None:
            record.source_text = self._imports.read_file(record.path)
        header = read_header(record.source_text)  # raises on an empty file
        mapping = record.mapping
        if mapping is None:
            # A CSV that matches a saved profile but parses ambiguous dates is
            # NOT promoted to needs_mapping: the profile carries the format the
            # user already confirmed for that exact header signature, and
            # re-asking an answered question is the babysitting § 3 decision 1
            # rejects.
            profile = self._imports.match_profile(header)
            if profile is None:
                record.outcome = "needs_mapping"
                return
            mapping = profile.column_mapping()
        else:
            # A hand-set mapping has not been through the form-boundary checks a
            # saved profile passed on its way in, and `CsvImporter.parse`
            # documents that it assumes a validated one. The single-file path
            # gets this from `ImportService.preview`, which the batch cannot
            # call yet — it has no account. A mapping that does not fit fails
            # THIS FILE with the validator's own friendly message, rather than
            # parsing garbage or taking the batch down.
            ImportService._validate_mapping(mapping, header)
        self._settle_parse(
            record, CsvImporter().parse(record.source_text, mapping, self._exponent)
        )

    def _settle_parse(self, record: BatchFile, parsed: ParseResult) -> None:
        """The tail every format shares: keep the parse, refuse an undated file,
        then try to resolve its destination account."""
        record.parsed = parsed
        record.hint = parsed.source_account
        # `ImportPreview.errors` holds the rows that could not be parsed. A file
        # where 40 of 50 rows failed commits 10 and would report "10 added" with
        # no hint that 40 vanished — in a money app a silently dropped row is
        # the defect, so the count reaches the screen and the report.
        record.error_count = len(parsed.errors)
        if parsed.period_start is None or parsed.period_end is None:
            # INV-13. Without this the record reaches `_validate_span`, whose
            # `date.fromisoformat(None)` surfaces "period endpoints must be
            # valid ISO-8601 dates" — a message about malformed dates for a file
            # that had none at all. Both endpoints are independently `str |
            # None`, so guarding only `period_start` leaves the other open.
            record.outcome = "failed"
            record.reason = UNDATED
            return
        match = match_account(parsed.source_account, self._accounts.list_accounts())
        if match.account_id is None:
            record.outcome = "needs_account"  # settled on the review screen
            return
        self.set_account(record, match.account_id)

    # -- ASK ------------------------------------------------------------------
    def answer(
        self, files: Sequence[BatchFile], record: BatchFile, value: Answer
    ) -> None:
        """Apply the user's reply to the question ``next_question`` handed out.

        ``None`` declines (the record becomes ``skipped``); otherwise the record
        re-enters SCAN at the step that stopped it — a password resumes at
        decrypt, a mapping at ``CsvImporter().parse`` — and runs the rest of the
        ladder, **including the draft-cap check** (§ 4.3). ASK is a second door
        into the ladder, and a cap enforced only on the scan step is one an
        unmapped batch walks past by one file per question answered.

        ``files`` is taken for that cap alone; the reply itself concerns one
        record. A record that has already settled is ignored rather than
        overwritten — a stale reply would otherwise turn a fully parsed file
        into "Skipped — no column mapping was set".
        """
        if record.outcome in _TERMINAL:
            return
        if value is not None and self.draft_total(files) >= _MAX_BATCH_DRAFTS:
            record.outcome = "not_attempted"
            record.reason = CAP_REACHED
            return
        if value is None:
            # Never "you didn't supply a password": INV-8 also reaches `skipped`
            # after three WRONG ones, where the user supplied three and none
            # worked. "We couldn't unlock this file" is true of both routes.
            record.reason = (
                SKIPPED_LOCKED
                if record.outcome == "needs_password"
                else SKIPPED_UNMAPPED
            )
            record.outcome = "skipped"
            return
        if isinstance(value, ColumnMapping):
            record.mapping = value
            record.outcome = "waiting"
            self.scan(record)
            self._retry_blocked_on_mapping(files, answered=record)
            return
        record.pending_password = value
        if value not in self._run_passwords:
            self._run_passwords.append(value)
        record.outcome = "waiting"
        self.scan(record)
        self._retry_blocked_on_password(files, answered=record)

    def _retry_blocked_on_password(
        self, files: Sequence[BatchFile], *, answered: BatchFile
    ) -> None:
        """Re-run the ladder for every OTHER record still blocked on a password.

        Section 4.4 promises a password typed during this run joins the list for
        every later file "before any further prompting", and gives the reason: a
        first batch of thirty same-bank PDFs is otherwise thirty prompts, which
        is an unattended feature asking thirty questions.

        The ordering defeated it. The UI runs SCAN over the WHOLE list before
        showing the first prompt, so every locked file is already
        ``needs_password`` by the time anything joins ``_run_passwords`` -- the
        list is empty for the entire scan pass. ``answer`` then re-scanned only
        the ONE record it was given, and ``next_question`` hands out the next
        record still sitting blocked without re-running its ladder. So the only
        ladder entry the list ever contributed was the password just typed for
        the record being re-scanned, which ``pending_password`` already held.

        Re-scanning here is what makes the list do its job: those records'
        ladders now include the new password, so a same-password file resolves
        without a question. A record that still cannot be unlocked simply
        returns to ``needs_password`` and is asked about as before.

        ``scan`` re-checks the draft cap per record, so this cannot walk past it.
        """
        for other in files:
            if other is answered or other.outcome != "needs_password":
                continue
            other.outcome = "waiting"
            self.scan(other)

    def _retry_blocked_on_mapping(
        self, files: Sequence[BatchFile], *, answered: BatchFile
    ) -> None:
        """Re-run the ladder for every OTHER record still blocked on a mapping.

        The twin of :meth:`_retry_blocked_on_password`, defeated by the same
        ordering: SCAN runs over the WHOLE list before the first question, so
        every CSV whose header matched no profile is already ``needs_mapping``
        by the time the user answers one. The wizard saves the profile BEFORE
        calling ``answer`` (``_on_map_next`` saves, then answers), so
        ``match_profile`` would resolve for every file sharing that header —
        but ``answer`` re-scanned only the record it was handed, and
        ``next_question`` hands out the next blocked record without re-running
        its ladder. § 4.3 decision 1: re-asking an answered question is
        babysitting.

        The answered mapping is NOT applied to the others. Each re-scanned
        record consults ``match_profile`` with its OWN header, so a different
        layout returns to ``needs_mapping`` and is asked about as before — and
        a mapping answered with no profile NAME saved nothing, so nothing
        resolves and the batch behaves exactly as it did.

        ``scan`` re-checks the draft cap per record, so this cannot walk past it.
        """
        for other in files:
            if other is answered or other.outcome != "needs_mapping":
                continue
            other.outcome = "waiting"
            self.scan(other)

    # -- REVIEW ---------------------------------------------------------------
    def set_account(self, record: BatchFile, account_id: int) -> None:
        """Point a record at a destination account — from ``match_account`` at
        SCAN, or from the review screen's picker (§ 4.6).

        Which call builds the preview is not interchangeable. A record that
        arrives with no preview (it was ``needs_account``) needs
        ``preview_result``; ``retarget`` takes an ``ImportPreview`` and has none
        to take. A record that already has one is *changing* its destination, so
        ``retarget`` replaces it. Either way the preview and the displayed
        account move together — a cell updated without re-pointing the preview
        is the wrong-account commit reached through a new door (INV-5).
        """
        if record.parsed is None or record.outcome in _TERMINAL:
            return
        record.account_id = account_id
        if record.preview is None:
            record.preview = self._imports.preview_result(record.parsed, account_id)
        else:
            record.preview = self._imports.retarget(record.preview, account_id)
        record.outcome = "ready"  # REVIEW re-derives already_imported from here
        self._settle_password(record)

    def _settle_password(self, record: BatchFile) -> None:
        """Write a *Remember*-ticked password once the destination settles.

        At prompt time the file is still unparsed, so there is nothing to key a
        password to — § 4.4 holds it on the record instead. It is dropped
        unwritten if the file never settles an account (``failed``, ``skipped``,
        or left ``needs_account``), which is the honest consequence of keying
        stored passwords to accounts rather than to files.
        """
        if (
            record.remember_password
            and record.pending_password
            and record.account_id is not None
        ):
            self._accounts.set_pdf_password(record.account_id, record.pending_password)

    def review(self, files: Sequence[BatchFile]) -> None:
        """Re-evaluate the whole batch — on entry to the review step and after
        EVERY account change. No commit has happened yet.

        The re-derivation is **two-directional**, and that is load-bearing. A
        one-way ``ready -> already_imported`` flip looks equivalent and silently
        loses data: the user retargets a row that was ``already_imported`` under
        the wrong account, its rows are genuinely new under the right one, but
        nothing moves it back — and RUN commits only ``ready`` records, so the
        file is dropped without a word. Re-deriving both outcomes from scratch on
        every pass is the shortest rule that cannot do that, which is why this is
        expressed as *set the outcome* rather than *demote when* (INV-10).
        """
        cumulative_counts(files, self._imports)
        periods = StatementPeriodRepository(self._vault.connection)
        for record in files:
            preview = record.preview
            if preview is None or record.outcome in _TERMINAL:
                continue
            # INV-13 refuses an undated record at SCAN, so anything holding a
            # preview here has both endpoints.
            span = periods.id_for_span(
                preview.account_id,
                str(preview.period_start),
                str(preview.period_end),
            )
            record.outcome = (
                "already_imported"
                if span is not None and record.new_count == 0
                else "ready"
            )

    @staticmethod
    def can_import(files: Sequence[BatchFile]) -> bool:
        """Whether `Import all` may be pressed: at least one file ``ready`` and
        NO file still unsettled — not ``needs_account``, not ``needs_password``,
        not ``needs_mapping``, and not merely ``waiting`` to be scanned (INV-3).

        § 4.6 states this button's rule in terms of ``needs_account`` alone, on
        the grounds that ASK exhausts the questions before REVIEW is reached.
        That was a property of the *flow*, not of the button, and the flow does
        not hold: the batch table is on screen from the first scan turn (§ 6),
        and § 4.7 deliberately returns to the event loop between turns, so a
        button enabled the moment file 1 matches is a button the user can press
        with twenty-nine files still unread. Pressing it started RUN while the
        SCAN chain was still armed — two chains stepping the same index, files
        silently skipped by both, and a run committing against a review table
        whose counts had never been computed (an INV-4 breach).

        So the gate is "every record has been settled", which is the property
        INV-3 actually needs and which the button can enforce on its own.

        Files that are ``failed``, ``skipped``, ``not_attempted`` or
        ``already_imported`` do not block it — they stay listed with their
        reason and are simply not committed. They are the report, not an
        obstacle.
        """
        outcomes = {record.outcome for record in files}
        return "ready" in outcomes and not (outcomes & _UNSETTLED)

    # -- RUN ------------------------------------------------------------------
    def run_step(self, files: Sequence[BatchFile], index: int) -> int:
        """Commit ``files[index]`` if it is ``ready``; return the next index —
        one event-loop turn's work, so Cancel stays live between files."""
        record = files[index]
        if record.outcome == "ready":
            self._commit(record)
        return index + 1

    def _commit(self, record: BatchFile) -> None:
        preview = record.preview
        if preview is None:  # defensive: `ready` implies a preview
            return
        try:
            record.result = self._imports.commit_import(
                preview,
                str(preview.period_start),
                str(preview.period_end),
                record.path,  # commit_import stores Path(...).name itself
            )
        except (ValueError, FinbreakError) as exc:
            # INV-1: a file that fails does not stop the batch. The caught set is
            # the same pair the wizard's single-file `_on_import` catches.
            record.outcome = "failed"
            record.reason = str(exc)
            return
        record.outcome = "committed"

    @staticmethod
    def stop_from(files: Sequence[BatchFile], index: int, reason: str) -> None:
        """Mark every record from ``index`` on as ``not_attempted`` — a cap
        stopping SCAN, or Cancel stopping either pass.

        Outcomes that already say something truer are left alone: a record that
        is ``already_imported``, ``failed`` or ``skipped`` has a report line of
        its own, and overwriting it with "the batch was cancelled" would lose
        the more useful sentence. Without this rule a cancelled scan would also
        strand rows reading *Waiting…* forever.
        """
        for record in files[index:]:
            if record.outcome in ("waiting", "ready"):
                record.outcome = "not_attempted"
                record.reason = reason
