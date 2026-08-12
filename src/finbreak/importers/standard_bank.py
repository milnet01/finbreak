"""Standard Bank (SA) statement text-parser (FIBR-0050).

One reader for all six of the user's Standard Bank statement types — read the
**printed text lines** (stable across every layout) rather than the fragile ruled
table geometry the generic FIBR-0009 path relies on. A recognised statement feeds
the existing ``preview_result`` -> dedup -> ``commit_import`` pipeline exactly like
OFX (self-describing, so it skips column-mapping).

Five layout families dispatch inside this single module (D1):

* **A** — transactional (Current / Savings / Revolving-Credit): right-anchored
  ``…desc… [amount][-] MM DD balance[-]``; year inferred from the period line.
* **B** — Home Loan: ``PostingDate[ EffectiveDate] desc amount balance`` (ISO
  dates, no printed amount sign).
* **D** — Money Market / investment: ``YYYY MM DD desc [±R amount] R balance``.
* **C** — credit card: two-columns-per-line, section-signed, no running balance.
* **E** — the Current-account "Payments / Deposits" layout (FIBR-0190):
  ``D[D] Mon YY desc [-]amount balance``; a **leading** minus on both, and no
  printed period or closing balance.

Signs are budget-view (money out negative): the balance families (A/B/D/E) take
the printed magnitude carrying the **running-balance delta** sign (INV-7); the
credit card flips its printed sign (INV-6). Integrity is all-or-nothing (INV-11):
a per-row ``|delta| == printed`` gate (A/B/D/E) plus a completeness gate — against
the statement's independently-printed closing figure where one prints, or (E,
which prints none) against its printed ``Payments`` / ``Deposits`` column totals
(FIBR-0190 §4.5).

The decrypt + caps are reused from FIBR-0009; this module adds no dependency and no
schema change.
"""

from __future__ import annotations

import io
import re
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from finbreak.importers.base import ParseResult, RowError, SourceAccountHint
from finbreak.importers.pdf_importer import (
    _MAX_PDF_PAGES,
    _MAX_PDF_ROWS,
    _normalise_to_plaintext,
)
from finbreak.models import TransactionDraft
from finbreak.services.transactions import (
    parse_transaction,
    to_minor,
    to_minor_storable,
)

Fmt = str  # Literal["us", "eu"] — kept loose to avoid a typing import churn.


class Family(StrEnum):
    """The recognised Standard Bank layout family (D1/D4)."""

    A = "A"  # transactional: Current / Savings / Revolving-Credit
    B = "B"  # Home Loan
    C = "C"  # credit card
    D = "D"  # Money Market / investment
    E = "E"  # Current account, "Payments / Deposits" layout (FIBR-0190)


_LEGAL_MARKER = "standard bank of south africa"

# Month names for the "Statement from <D Month YYYY>" period line and Family-C /
# Money-Market "Date" lines.
_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}
_MON3 = {m[:3]: i for m, i in _MONTHS.items()}

# A money figure printed to exactly two decimals (SB always does), EITHER
# thousands-grouped (``1,234.56``) OR an ungrouped run (``1234.56`` — FIBR-0067;
# validated against all six real statement families, which always group, so the
# ungrouped alternative adds zero matches there — no regression — but a bank that
# prints ungrouped no longer fails the strict grammar). Used to detect the decimal
# separator (D9) and to pull the balance/amount off a line. Excludes 3-decimal
# rates (7.050%) and refs by the 2-digit tail, and — via the ``(?![.,]?\d)`` guard
# — a dotted-date fragment like ``2025.07.21`` (no digit, grouped or not, may
# follow the two-decimal tail).
_MONEY = re.compile(r"(?<![\d.,])(?:\d{1,3}(?:[.,]\d{3})*|\d{4,})[.,]\d{2}(?![.,]?\d)")

# A transaction "Statement from D Month YYYY to D Month YYYY" period line (A/C).
_PERIOD = re.compile(
    r"statement from\s+(\d{1,2})\s+([a-z]+)\s+(\d{4})\s+to\s+"
    r"(\d{1,2})\s+([a-z]+)\s+(\d{4})",
    re.I,
)

# Bounded post-table markers (D11). A region ends at the first line whose stripped
# text starts with / contains one of these; case-insensitive.
_TERMINATORS = (
    "please verify",
    "the standard bank of south africa",
    "die standard bank",
    "vat summary",
    "interest calculation",
    "interest payment details",
    "balance as at",
    "closing balance",
    "balance at date of statement",
    "balance outstanding at date of statement",
    "limit structure",
    "fee structure",
    "account summary",
    "details of agreement",
    "end of statement",
    "***end of statement***",
    "## these fees",
    "*## these fees",
    "* * * * *",
)

_BROUGHT_FORWARD = "brought forward"  # anchor marker, matched case-insensitively

# Family E's opening anchor — it prints this instead of "Balance Brought Forward"
# (FIBR-0190 §4.4). Widening the two marker scans globally is safe where widening
# the *shape* predicate ``_looks_like_row`` is not (D5 vs D6): this is an exact
# phrase, and no pre-E fixture contains it (asserted as a test, FIBR-0190 §7.10).
_E_OPENING = "statement opening balance"

# Family-C brought-forward anchor: the phrase IMMEDIATELY followed by the balance
# (e.g. "21 Jul 25 Balance Brought Forward 6,849.68"). Requiring the amount to abut
# the phrase rejects a prose decoy — "...has a credit balance. Balance brought
# forward on this statement -251.85" — whose figure is separated from the phrase by
# narrative text (FIBR-0106). The optional -/R lets a card that opens in credit
# still match its signed brought-forward.
_CC_BROUGHT_FORWARD = re.compile(
    rf"{_BROUGHT_FORWARD}\s+-?R?{_MONEY.pattern}", re.IGNORECASE
)

# A line the region-fold classified as a transaction row (a date + balance tail) but
# the strict family grammar rejects is a **mis-parse**, not a droppable line — raising
# (all-or-nothing) rather than silently skipping is what keeps a mis-extracted row on
# a closing-less statement (Savings) from becoming a silent under-import (INV-11).
_MISPARSE = "this statement didn't parse cleanly — try your bank's CSV or OFX export"


# --------------------------------------------------------------------------- #
# Number handling (D9)
# --------------------------------------------------------------------------- #
def _detect_number_format(region_text: str) -> Fmt:
    """Detect the statement's decimal convention from its money tokens (D9).

    US ``1,234.56`` (``.`` decimal) vs European ``1.234,56`` (``,`` decimal). The
    separator immediately before the final two digits is the decimal. All money
    tokens must agree; a statement mixing both is refused (a real SB statement is
    internally consistent — a mix signals a mis-read)."""
    votes = set()
    for tok in _MONEY.findall(region_text):
        votes.add("eu" if tok[-3] == "," else "us")
    if not votes:
        return "us"  # no money tokens (degenerate) — harmless default
    if len(votes) > 1:
        raise ValueError(
            "this statement mixes number formats — try your bank's CSV or OFX export"
        )
    return votes.pop()


def _parse_amount(token: str, fmt: Fmt) -> Decimal:
    """Parse one money token to its unsigned **magnitude** ``Decimal`` (D9).

    Strips an ``R`` prefix, a ``-`` wherever it prints (leading for B/C/D, trailing
    for A/RCP), the thousands separator, and normalises the decimal to ``.``. The
    printed sign is read separately (``_is_negative``) for the INV-7b cross-check."""
    t = token.strip().replace("R", "").replace(" ", "").replace("-", "")
    if fmt == "eu":
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        return Decimal(t)
    except InvalidOperation as exc:
        raise ValueError(f"couldn't read the amount {token!r}") from exc


def _is_negative(token: str) -> bool:
    """Whether a printed money token carries a ``-`` (leading or trailing)."""
    return "-" in token


def _signed_balance(token: str, fmt: Fmt) -> Decimal:
    """A balance token as a signed ``Decimal``: negative when the token carries the
    trailing ``-`` Standard Bank prints for a negative balance, positive otherwise.
    The single home of the ``-parse if negative else parse`` idiom (FIBR-0069) —
    every family's opening/row balance goes through it."""
    magnitude = _parse_amount(token, fmt)
    return -magnitude if _is_negative(token) else magnitude


def _money_tokens(text: str) -> list[str]:
    """The money figures on a line, in print order (with any trailing/leading
    ``-`` re-attached so ``_is_negative`` can see it)."""
    out: list[str] = []
    for m in _MONEY.finditer(text):
        start, end = m.start(), m.end()
        tok = m.group()
        # Re-attach an adjacent sign / R prefix so the caller can read the sign:
        # a leading "-", an "R", or the "-R" combination (Family D negatives).
        if start > 0 and text[start - 1] == "R":
            tok = "R" + tok
            if start > 1 and text[start - 2] == "-":
                tok = "-" + tok
        elif start > 0 and text[start - 1] == "-":
            tok = "-" + tok
        if end < len(text) and text[end] == "-":
            tok = tok + "-"
        out.append(tok)
    return out


# --------------------------------------------------------------------------- #
# Region bounding (D11) + credit-card de-interleave (INV-6)
# --------------------------------------------------------------------------- #
def _is_terminator(line: str) -> bool:
    low = line.strip().lower()
    return any(t in low for t in _TERMINATORS)


def _table_region(page_lines: list[str], family: Family) -> slice:
    """The transaction region of one page: ``[column-header+1, first terminator)``
    (D11). The header line is family-specific; an empty slice means the page has no
    transactions (e.g. a summary-only page)."""
    header = -1
    for i in range(len(page_lines)):
        # A 2-line window so a header that wraps across lines (the Current-account
        # "Details Service Date Balance" / "Debits Credits" split) is still found —
        # the same wrap tolerance detection uses (D4). Region starts after the first
        # header line; the extra wrap lines carry no transaction and are dropped.
        window = (
            page_lines[i] + " " + (page_lines[i + 1] if i + 1 < len(page_lines) else "")
        )
        low = window.lower()
        if family is Family.C:
            if "date" in low and "description" in low and "amount" in low:
                header = i
                break
        elif (
            "balance" in low
            and (
                "debit" in low
                or "debits" in low
                or "withdrawals" in low
                or "date" in low
            )
            # not the "Month-end Balance R…" summary line (it carries a money token);
            # tested on the header line itself, not the window (whose next line is the
            # first transaction and does carry money).
            and not _MONEY.search(page_lines[i])
        ):
            header = i
            break
    start = header + 1 if header != -1 else -1
    if start == -1 and family is Family.C:
        # A continuation page can carry the credit-card table onward WITHOUT
        # reprinting the "Date Description Amount" column header — the final page of a
        # multi-page statement opens straight into a "Debit"/"Credits" section. Fall
        # back to the first real transaction row so those rows aren't dropped (a drop
        # fails the mandatory Family-C completeness checksum, refusing the whole
        # statement — FIBR-0112). "Real row" = a CC segment ending in a 2-decimal
        # amount, which excludes summary-page date spans ("Statement Period 20 Sep 25
        # to 20 Oct 25") whose trailing token carries no cents.
        for i, line in enumerate(page_lines):
            if any(_AMOUNT_TAIL.search(seg) for seg in _split_credit_card_line(line)):
                start = i
                break
    if start == -1:
        return slice(0, 0)
    end = len(page_lines)
    for j in range(start, len(page_lines)):
        if _is_terminator(page_lines[j]):
            end = j
            break
    return slice(start, end)


# The label as printed. The corpus shows three spellings: "Account Number"
# (families A and B), "account number" (C, excluded) and "Account number:" (D) —
# hence the case-insensitive match and the optional colon.
#
# The captured run allows a SINGLE space or dash between digits (grouping, as in
# "11 222 333 4") and therefore stops at a column gap of two or more spaces. It
# deliberately does NOT use `[\d\s-]*`, which is greedy across any whitespace and
# merges a following numeric column into the key: `Account Number 44 555 666 7
# 2024 03 27` captures the date column too under the greedy form (FIBR-0086
# INV-2a).
_ACCOUNT_LABEL = re.compile(r"account\s+number\s*:?\s*((?:\d[ -]?)*\d)", re.IGNORECASE)

# Families whose header label names THEIR OWN account. C is absent by design, not
# by omission: its label names the debit-order account that pays the card, which
# normalises to the current account's number exactly (FIBR-0086 §2.3).
_ACCOUNT_NUMBER_FAMILIES = frozenset({Family.A, Family.B, Family.D})


def extract_account_number(
    page_lines: list[str], family: Family
) -> SourceAccountHint | None:
    """What this statement prints about ITS OWN account, or None.

    Returns None for any family not in ``_ACCOUNT_NUMBER_FAMILIES`` — the guard
    lives HERE, in the extractor, not only at the call site, so that calling it
    directly with ``Family.C`` cannot yield the debit-order account. A
    call-site-only guard would let the invariant's test pass while the function it
    names stays wrong.

    Reads only the header block ABOVE the transaction table, because other
    accounts' numbers appear inside transaction rows (§2.4) — a current-account
    statement prints the home loan's number in one. Scans the header block
    top-down and takes the FIRST line matching ``_ACCOUNT_LABEL``; later matches
    are ignored. (Every measured file has exactly one, so first-wins is only
    reached by a layout that changes, and keeps that case deterministic rather
    than order-dependent.) Values are returned as printed; the caller normalises.
    """
    if family not in _ACCOUNT_NUMBER_FAMILIES:
        return None
    header = page_lines[: _table_region(page_lines, family).start]
    for line in header:
        found = _ACCOUNT_LABEL.search(line)
        if found is None:
            continue
        number = found.group(1).strip()
        if not number:
            continue
        return SourceAccountHint(
            number=number,
            name=line[: found.start()].strip() or None,
            family=str(family),
        )
    return None


# A validated ``D[D] Mon YY`` date — the 3-letter month must be a real month (so a
# random 3-letter token in a description is neither a split point nor reaches the
# ``_dmy_iso`` lookup, INV-6). Title-case with no ``re.I``: Family C and Family E
# both print it that way (FIBR-0190 §2.2 measured 182/182 E rows Title-case).
_MON_RE = "(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
_CC_DATE = re.compile(rf"\d{{1,2}} {_MON_RE} \d{{2}}")
_E_DATE_LEAD = re.compile(rf"^\s*\d{{1,2}} {_MON_RE} \d{{2}}\b")
_AMOUNT_TAIL = re.compile(
    r"-?[\d.,]+[.,]\d{2}$"
)  # a segment ending in a 2-decimal amount


def _split_credit_card_line(line: str) -> list[str]:
    """Split a credit-card line into its 1–2 transaction segments at each **column
    boundary** date (INV-6). A date is a boundary only if it is line-leading or
    immediately follows a previous segment's **amount** — so a ``D[D] Mon YY``
    substring embedded inside a merchant description does **not** create a spurious
    split (it stays in the description; the amount is still the segment's last)."""
    matches = list(_CC_DATE.finditer(line))
    if not matches:
        return []
    boundaries: list[int] = []
    for i, m in enumerate(matches):
        if i == 0 or _AMOUNT_TAIL.search(line[: m.start()].rstrip()):
            boundaries.append(m.start())
    segs = []
    for k, s in enumerate(boundaries):
        e = boundaries[k + 1] if k + 1 < len(boundaries) else len(line)
        segs.append(line[s:e].strip())
    return segs


# --------------------------------------------------------------------------- #
# Year inference (D8) + period
# --------------------------------------------------------------------------- #
def _parse_period(full_text: str) -> tuple[str, str] | None:
    """The authoritative A/C statement span from the "Statement from … to …" line.

    The ``_PERIOD`` regex accepts any word as the month name, so a non-English
    (e.g. Afrikaans "Januarie") or garbled month must not index ``_MONTHS``
    directly — that raised a bare ``KeyError`` that crashed the wizard. An
    unresolvable month yields ``None`` (a malformed period, handled by the
    caller). (indie-review H1)"""
    m = _PERIOD.search(full_text)
    if not m:
        return None
    d1, mon1, y1, d2, mon2, y2 = m.groups()
    month1, month2 = _MONTHS.get(mon1.lower()), _MONTHS.get(mon2.lower())
    if month1 is None or month2 is None:
        return None
    start = _iso(int(y1), month1, int(d1))
    end = _iso(int(y2), month2, int(d2))
    return start, end


def _iso(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"


def _infer_years(md_pairs: list[tuple[int, int]], period: tuple[str, str]) -> list[int]:
    """Resolve the year of each ``(month, day)`` pair (Family A, D8).

    Seed the year and the initial "previous month" from the period start; increment
    the year whenever a transaction's month drops below the previous transaction's
    (a chronological statement only decreases at a year wrap; handles a Nov->Feb
    gap)."""
    start_year = int(period[0][:4])
    start_month = int(period[0][5:7])
    years: list[int] = []
    year = start_year
    prev_month = start_month
    for month, _day in md_pairs:
        if month < prev_month:
            year += 1
        years.append(year)
        prev_month = month
    return years


# --------------------------------------------------------------------------- #
# Detection (D4)
# --------------------------------------------------------------------------- #
def _signature_present(full_text: str, *tokens: str, window: int = 3) -> bool:
    """Whether every token (word-boundary, so plural ``Debits`` never matches
    singular ``Debit``) appears within some window of ``window`` consecutive lines —
    the "header block" scoping (D4), applied as a sliding window so it finds the
    transaction header wherever it prints (incl. page 2 of a multi-page statement)
    yet stays narrow enough that footer prose can't hold 4–5 column labels at once."""
    lines = full_text.splitlines()
    pats = [re.compile(rf"\b{re.escape(t.lower())}\b") for t in tokens]
    for i in range(len(lines)):
        blob = " ".join(lines[i : i + window]).lower()
        if all(p.search(blob) for p in pats):
            return True
    return False


def detect_standard_bank(full_text: str) -> Family | None:
    """The recognised SB family, or ``None`` (-> generic fallback, INV-2/INV-13a).

    Requires the legal marker document-wide AND a family header signature (over a
    sliding header-block window), most-specific-first C->D->E->B->A (D4;
    FIBR-0190 D2 adds E)."""
    if _LEGAL_MARKER not in full_text.lower():
        return None
    low = full_text.lower()
    if _signature_present(full_text, "date", "description", "amount", window=1) and (
        "credit card" in low or "titanium" in low
    ):
        return Family.C
    if _signature_present(full_text, "withdrawals", "deposits", "balance"):
        return Family.D
    if _signature_present(
        full_text, "date", "description", "payments", "deposits", "balance"
    ):
        return Family.E
    if _signature_present(
        full_text, "posting", "effective", "debit", "credit", "balance"
    ):
        return Family.B
    if _signature_present(full_text, "debits", "credits", "date", "balance"):
        return Family.A
    return None


# --------------------------------------------------------------------------- #
# Closing / opening capture (INV-10) + checksum (INV-11)
# --------------------------------------------------------------------------- #
_CLOSING_MARKERS = {
    Family.A: (
        "balance at date of statement",
        "balance outstanding at date of statement",
    ),
    Family.B: ("closing balance",),
    Family.C: ("closing balance",),
    Family.D: ("balance as at",),
    # E prints NO closing figure anywhere in the document (FIBR-0190 §2.2) — an
    # explicit empty tuple so `_capture_closing` returns None rather than KeyError,
    # and so the fact is stated where a reader looks for it. Its completeness gate
    # is `_verify_e_totals` instead (§4.5).
    Family.E: (),
}


def _capture_opening(region_lines: list[str], fmt: Fmt) -> Decimal:
    """The first opening anchor's balance (``opening_balance``; the anchor repeats
    per page on a multi-page statement, D12 — the first is the opening). The marker
    is "brought forward" (A/B/D) or E's "statement opening balance" (FIBR-0190 D6).

    For E this is reachable only on a **zero-row** statement: `parse` runs the family
    parser first, and `_parse_family_e` raises its own suffixed message from inside
    the per-row loop (FIBR-0190 §4.4)."""
    for line in region_lines:
        if _BROUGHT_FORWARD in line.lower() or _E_OPENING in line.lower():
            toks = _money_tokens(line)
            if toks:
                bal = toks[-1]
                return _signed_balance(bal, fmt)
    raise ValueError("couldn't find the opening balance on this statement")


def _capture_closing(full_text: str, family: Family, fmt: Fmt) -> Decimal | None:
    """The statement's independently-printed closing figure, or ``None`` when the
    family prints none (Savings, and every Family-E statement; INV-10). Scans the
    full document text (the A/RCP closings print on a summary page outside the
    transaction region)."""
    for line in full_text.splitlines():
        low = line.lower()
        for marker in _CLOSING_MARKERS[family]:
            if low.strip().startswith(marker) or marker in low:
                toks = _money_tokens(line)
                if toks:
                    bal = toks[-1]
                    return _signed_balance(bal, fmt)
    return None


def _storable(amount: Decimal, exponent: int) -> int:
    """``to_minor``, plus the magnitude bound storing the result forces (FIBR-0224).

    The opening and closing balances are the only amounts on a statement that never
    pass through ``parse_transaction``, so they inherited none of its money contract
    — the PDF twin of the OFX hole FIBR-0223 closed. A plain digit run past SQLite's
    signed 64-bit INTEGER parses, scales, and even **reconciles** (the completeness
    gate compares the two unbounded figures against each other, so a statement
    printing a huge opening AND a matching huge closing sails through it), then dies
    far away at the INSERT as ``OverflowError`` — neither of the two classes
    ``_on_import`` catches, so a dead slot at commit time rather than a message.

    Only one of FIBR-0222's two spellings can arrive here: ``_MONEY`` never matches a
    token containing ``e``, so ``decimal.Overflow`` is unreachable on this path and
    the magnitude bound is what does the work. Re-raised in this file's own voice, as
    every other refusal here is — what the user needs to know is that the statement
    is unusable, not which bound it broke.
    """
    try:
        return to_minor_storable(amount, exponent)
    except ValueError as exc:
        raise ValueError(
            "this statement's opening or closing balance is too large to store — "
            "try your bank's CSV or OFX export"
        ) from exc


def _verify_checksum(
    family: Family,
    opening: Decimal,
    drafts: list[TransactionDraft],
    closing: Decimal | None,
    exponent: int,
) -> None:
    """The completeness gate (INV-11), ``parse``-side. Raises the friendly
    all-or-nothing ``ValueError`` on non-reconciliation. A ``None`` closing is
    family-aware: skip for Family A (Savings legitimately prints none) and for
    Family E (which never prints one — its gate is `_verify_e_totals`), raise for
    B/D/C (they always print a closing; C has no per-row fallback gate)."""
    if closing is None:
        if family in (Family.A, Family.E):
            return  # per-row gate covered correctness (E adds its own totals gate)
        raise ValueError(
            "couldn't find the closing balance to check this statement against — "
            "try your bank's CSV or OFX export"
        )
    total = sum(d.amount_minor for d in drafts)
    # Bounded BEFORE the comparison below, so an unstorable figure is reported as
    # what it is rather than as a phantom "didn't add up" (FIBR-0224).
    opening_m = _storable(opening, exponent)
    closing_m = _storable(closing, exponent)
    if family is Family.C:
        # Drafts carry the flipped budget sign; the printed convention is +purchase.
        reconciled = opening_m - total
    else:
        reconciled = opening_m + total
    # Compare magnitudes: the per-row gate (A/B/D) / section flip (C) already
    # validates each transaction's sign, and the Home-Loan running-balance column
    # prints unsigned magnitudes while its "CLOSING BALANCE" row prints a sign — so
    # the completeness gate's job (truncation detection) is a magnitude endpoint match.
    if abs(reconciled) != abs(closing_m):
        raise ValueError(
            "this statement didn't add up — its running balance and transactions "
            "disagree; try your bank's CSV or OFX export"
        )


# Family E's summary page prints each column total alone on its own line, e.g.
# "Payments -R1,730.55" (FIBR-0190 §2.2). The R prefix is optional: the row tokens
# are bare, so a summary printing bare totals must not silently disable the gate.
_E_TOTAL = re.compile(rf"^\s*(Payments|Deposits)\s+-?R?({_MONEY.pattern})\s*$", re.I)

# Its own wording, deliberately NOT the `_verify_checksum` one: every existing
# message describes a *running balance* disagreement, which is factually wrong for
# the case this gate exists to catch — a truncated tail, where every surviving row
# still reconciles (FIBR-0190 D8/§4.5).
_E_TOTALS_MISMATCH = (
    "this statement didn't add up — its printed Payments/Deposits totals don't "
    "match its transactions; try your bank's CSV or OFX export"
)


def _verify_e_totals(
    full_text: str,
    drafts: list[TransactionDraft],
    opening: Decimal,
    exponent: int,
    fmt: Fmt,
) -> int | None:
    """Family E's completeness gate: |Σ money-out| vs the printed ``Payments`` total
    and |Σ money-in| vs ``Deposits`` (FIBR-0190 §4.5). Returns the final running
    balance in minor units when **both** printed and verified, else ``None``.

    This is the part of E that is *stronger* than Family A: the per-row chain
    catches an interior dropped row but is blind to a truncated **tail** (every
    surviving row still reconciles). The totals catch exactly that.

    Each label is verified **independently** (D9): a lone total still catches a
    dropped tail on its half, so skipping it would be strictly weaker than checking
    it. A label that prints more than once is treated as absent — per-page subtotals
    are plausible, and first/last-wins would silently compare against one."""
    seen: dict[str, list[str]] = {"payments": [], "deposits": []}
    for line in full_text.splitlines():
        m = _E_TOTAL.match(line)
        if m:
            seen[m.group(1).lower()].append(m.group(2))
    money_out = sum(d.amount_minor for d in drafts if d.amount_minor < 0)
    money_in = sum(d.amount_minor for d in drafts if d.amount_minor > 0)
    verified = 0
    for label, total in (("payments", money_out), ("deposits", money_in)):
        toks = seen[label]
        if len(toks) != 1:
            continue  # absent, or ambiguous (a repeated label) — degrade to A
        # Compare MAGNITUDES in minor units — both conversions written out, because
        # `amount_minor` is already an int in minor units while `_parse_amount`
        # returns a MAJOR-unit Decimal. The sign is owned by the per-row gate, and a
        # signed comparison would raise on a valid "Payments R<amount>" summary.
        if abs(total) != to_minor(_parse_amount(toks[0], fmt), exponent):
            raise ValueError(_E_TOTALS_MISMATCH)
        verified += 1
    if verified < 2:
        # A single verified total corroborates only one half of `opening + Σ`, so
        # FIBR-0171's forecast anchor gets None rather than an unchecked number (D10).
        return None
    # E is the one family that reaches a stored balance with an opening
    # `_verify_checksum` never converted — it prints no closing, so that gate takes
    # its `closing is None` early return before either bound (FIBR-0224).
    return _storable(opening, exponent) + sum(d.amount_minor for d in drafts)


# --------------------------------------------------------------------------- #
# Per-family row parsers (each returns drafts only; ``parse`` sets the span)
# --------------------------------------------------------------------------- #
# Registered-office / contact markers Standard Bank reprints in the page-break
# footer (every page). None appears in a transaction description, so a line
# carrying one is page boilerplate, not a continuation (FIBR-0119).
_SB_LETTERHEAD = re.compile(
    r"standard bank centre"
    r"|standardbank\.co\.za"
    r"|\bp\s?o\s+box\b"
    r"|switchboard"
    r"|\bfax\b"
    r"|registration\s+(?:no|number)"
    r"|authorised financial services",
    re.IGNORECASE,
)

# The words a repeated column header is made of (the Family-A/B/D header wraps as
# e.g. "Debit Credit Balance" / "Date Date Fee"). Deliberately EXCLUDES ambiguous
# words that also start real descriptions ("service", "details", "description",
# "amount", "reference") so a genuine wrapped description isn't mistaken for a
# header (FIBR-0119; generalises the Family-C ``_is_cc_skip_line`` rule).
_HEADER_TOKENS = frozenset(
    {
        "date",
        "fee",
        "credit",
        "credits",
        "debit",
        "debits",
        "balance",
        "withdrawal",
        "withdrawals",
        "deposit",
        "deposits",
        "cash",
        "posting",
        "effective",
    }
)


def _is_boilerplate(line: str) -> bool:
    """A page-break footer / letterhead / repeated column-header line that must NOT
    be folded into the preceding transaction's description (FIBR-0119). On a
    multi-page statement SB reprints the registered-office block + the column header
    at every break; those lines carry no date+amount, so ``_fold`` would otherwise
    glue them to the last transaction. Matches: a bare account/reference number; a
    registered-office / contact line; a line whose tokens are ALL table-header words
    (a repeated column header)."""
    s = line.strip()
    if not s:
        return False  # blank lines are handled by _fold's own skip
    if s.isdigit():  # a bare account / page / reference number in the footer
        return True
    if _SB_LETTERHEAD.search(s):
        return True
    toks = s.split()  # a repeated column header, e.g. "Debit Credit Balance"
    return len(toks) >= 2 and all(t.lower() in _HEADER_TOKENS for t in toks)


def _fold(lines: list[str], *, dmy_lead: bool = False) -> list[tuple[str, list[str]]]:
    """Group region lines into (transaction line, [continuation lines]) — a
    continuation is any in-region line with no date+amount tail, folded into the
    preceding transaction's description (INV-10). Lines before the first transaction,
    blank lines, and page-break boilerplate (``_is_boilerplate``, FIBR-0119) are
    dropped.

    ``dmy_lead`` is a pass-through to the predicate (FIBR-0190 D5) — the fold's own
    logic is unchanged."""
    groups: list[tuple[str, list[str]]] = []
    for line in lines:
        if not line.strip():
            continue
        if _is_boilerplate(line):
            continue  # page footer / letterhead / repeated header — never folded
        if _looks_like_row(line, dmy_lead=dmy_lead):
            groups.append((line, []))
        elif groups:
            groups[-1][1].append(line.strip())
    return groups


_TRAILING_TAIL = re.compile(r"\b\d{1,2}\s+\d{1,2}\s+[\d.,]+-?\s*$")  # … MM DD balance
_ISO_LEAD = re.compile(r"^\s*\d{4}-\d{2}-\d{2}\b")
_YMD_LEAD = re.compile(r"^\s*\d{4}\s+\d{1,2}\s+\d{1,2}\b")


def _looks_like_row(line: str, *, dmy_lead: bool = False) -> bool:
    """A transaction/anchor line for Families A/B/D (a brought-forward anchor, or a
    date + trailing balance). Family C rows are handled by the de-interleave.

    ``dmy_lead=True`` additionally accepts a line **leading** with a validated
    ``D[D] Mon YY`` date, or carrying E's opening marker — Family E only. The
    widening is opt-in because it is a *shape* predicate that can fire on incidental
    text: a Family-A continuation line that happens to start "12 Jan 25" would be
    promoted to a row and then rejected by A's strict grammar, turning a working
    import into an all-or-nothing refusal (FIBR-0190 D5). E accepts that hazard for
    itself — refusing beats silently folding a real transaction into the previous
    row's description — and the region bounds it."""
    if dmy_lead and (_E_DATE_LEAD.search(line) or _E_OPENING in line.lower()):
        return True
    return bool(
        _BROUGHT_FORWARD in line.lower()
        or _TRAILING_TAIL.search(line)
        or _ISO_LEAD.search(line)
        or _YMD_LEAD.search(line)
    )


def _anchor_balance(line: str, fmt: Fmt) -> Decimal | None:
    """If ``line`` is an opening anchor — "brought forward" (A/B/D) or E's "statement
    opening balance" (FIBR-0190 D6) — its (signed) balance; else ``None``. Handles the
    dated page-1 anchor and the undated continuation-page repeat (D12)."""
    low = line.lower()
    if _BROUGHT_FORWARD not in low and _E_OPENING not in low:
        return None
    toks = _money_tokens(line)
    if not toks:
        return None
    bal = toks[-1]
    return _signed_balance(bal, fmt)


# Its own wording, deliberately NOT one of the four "this statement didn't add up"
# messages (FIBR-0255 §4.2). This statement DOES add up — its running balance
# reconciles row by row, which is how the row below was verified before it was
# dropped. What failed is storing one row, and telling the user their arithmetic
# disagrees would misdiagnose the one failure they have the document for. Same
# reasoning as `_E_TOTALS_MISMATCH`'s own sentence (FIBR-0190 D8).
_UNREADABLE_MONEY_ROW = (
    "couldn't read one of this statement's transactions, and it moved money — "
    "importing it would give you the wrong totals; try your bank's CSV or OFX export"
)


def _draft(
    row: int, occurred_on: str, signed: Decimal, description: str, exponent: int
) -> TransactionDraft | RowError:
    """One parsed row as a draft, or a ``RowError`` when the row itself is
    unimportable — **degrading per row iff the row moved no money** (FIBR-0216,
    narrowed to that case by FIBR-0255).

    Every call site is a bare loop or comprehension with no per-row guard, so a
    ``parse_transaction`` ValueError used to propagate out of `parse` and abort the
    WHOLE import. The reachable case is a legitimate printed ``0.00`` line — a zero
    fee, "interest capitalised 0.00" — which fails "amount must be non-zero" and
    read to the user as an app bug on an otherwise perfect statement.

    Degrading is safe for that row, and **only** for that row: it verified fine and
    carries no money, so dropping it leaves every running balance and the
    credit-card completeness gate untouched, since it contributes 0 to both.
    ``csv_importer`` degrades per row exactly this way.

    FIBR-0216 applied that conclusion to every rejection, where its premise covers
    one. ``parse_transaction`` also rejects a bad date, a blank description, an
    over-precise amount and an unstorable magnitude, and all four can fire on a row
    that DID move money — whose delta ``_verify_row`` has already walked the running
    balance past, so the chain still reconciles and only the draft list comes up
    short. On a closing-less Savings page or a Family E page missing the relevant
    column total there is then no completeness gate left to notice, and the import
    is silently wrong by that row's amount (FIBR-0255 §2). So such a row raises: the
    all-or-nothing contract (INV-7b/INV-11), applied where its reasoning holds.

    **The discriminator is ``signed``, never the rejection reason.** They are not
    interchangeable — the description and date are checked before the amount, so a
    printed ``0.00`` line with a garbled date arrives here with ``signed == 0`` and
    an ISO-date reason, and must still degrade."""
    try:
        occurred_on, amount_minor, description = parse_transaction(
            occurred_on, signed, description, exponent
        )
    except ValueError as exc:
        if signed != 0:
            raise ValueError(_UNREADABLE_MONEY_ROW) from exc
        return RowError(row, str(exc))
    return TransactionDraft(row, occurred_on, amount_minor, description)


def _split(
    items: Sequence[TransactionDraft | RowError],
) -> tuple[list[TransactionDraft], list[RowError]]:
    """Partition ``_draft`` results into the two ``ParseResult`` channels, keeping
    file order within each (the preview interleaves them by ``row_number``)."""
    return (
        [i for i in items if isinstance(i, TransactionDraft)],
        [i for i in items if isinstance(i, RowError)],
    )


def _verify_row(delta: Decimal, amt_tok: str, fmt: Fmt, *, check_sign: bool) -> None:
    """The per-row INV-7b gate: the running-balance ``delta`` must equal the printed
    amount in **magnitude** and (where a sign prints — A/D/E, not the sign-less B) in
    **direction**. A mismatch is a mis-parse -> the all-or-nothing ``ValueError``."""
    if abs(delta) != _parse_amount(amt_tok, fmt):
        raise ValueError(
            "this statement didn't add up — a transaction's amount doesn't match "
            "its balance change; try your bank's CSV or OFX export"
        )
    if check_sign and _is_negative(amt_tok) != (delta < 0):
        raise ValueError(
            "this statement didn't add up — a transaction's sign doesn't match "
            "its balance change; try your bank's CSV or OFX export"
        )


def _parse_family_a(
    lines: list[str], exponent: int, fmt: Fmt, period: tuple[str, str]
) -> ParseResult:
    """Family A (transactional) — right-anchored ``…desc… [amount][-] MM DD
    balance[-]``; sign from the running-balance delta, cross-checked per row."""
    groups = _fold(lines)
    prev_balance: Decimal | None = None
    md_pairs: list[tuple[int, int]] = []
    staged: list[
        tuple[str, Decimal, str, Decimal]
    ] = []  # desc, |amt|, amt_tok, balance
    for line, cont in groups:
        bf = _anchor_balance(line, fmt)
        if bf is not None:
            prev_balance = bf  # brought-forward anchor (dated page-1 or undated repeat)
            continue
        m = re.search(
            r"(.*?)\s+((?:R?-?[\d.,]+-?)\s+)(\d{1,2})\s+(\d{1,2})\s+([\d.,]+-?)\s*$",
            line,
        )
        if not m:
            raise ValueError(_MISPARSE)
        desc, amt_tok, mm, dd, bal_tok = m.groups()
        balance = _signed_balance(bal_tok, fmt)
        if prev_balance is None:
            raise ValueError(
                "couldn't find the opening balance on this statement — "
                "try your bank's CSV or OFX export"
            )
        delta = balance - prev_balance
        _verify_row(delta, amt_tok, fmt, check_sign=True)
        full_desc = " ".join([_clean_desc(desc)] + cont).strip()
        staged.append((full_desc, delta, "", balance))
        md_pairs.append((int(mm), int(dd)))
        prev_balance = balance
    years = _infer_years(md_pairs, period)
    drafts, errors = _split(
        [
            _draft(
                i + 1,
                _iso(years[i], md_pairs[i][0], md_pairs[i][1]),
                delta,
                desc,
                exponent,
            )
            for i, (desc, delta, _t, _b) in enumerate(staged)
        ]
    )
    return ParseResult(drafts, errors, None, None)


def _clean_desc(desc: str) -> str:
    """Strip SB service-fee markers (``##`` / ``*##``) from a description tail."""
    return re.sub(r"\s*\*?##\s*$", "", desc).strip()


def _parse_family_b(lines: list[str], exponent: int, fmt: Fmt) -> ParseResult:
    """Family B (Home Loan) — ``PostingDate[ EffectiveDate] desc amount balance``,
    ISO dates, no printed sign (delta is the sole sign source)."""
    groups = _fold(lines)
    prev_balance: Decimal | None = None
    parsed: list[TransactionDraft | RowError] = []
    row = 0
    for line, cont in groups:
        bf = _anchor_balance(line, fmt)
        if bf is not None:
            prev_balance = bf
            continue
        m = re.match(
            r"\s*(\d{4}-\d{2}-\d{2})(?:\s+\d{4}-\d{2}-\d{2})?\s+(.*?)\s+"
            r"((?:[\d.,]+)\s+)([\d.,]+-?)\s*$",
            line,
        )
        if not m:
            raise ValueError(_MISPARSE)
        posting, desc, amt_tok, bal_tok = m.groups()
        balance = _signed_balance(bal_tok, fmt)
        if prev_balance is None:
            raise ValueError(
                "couldn't find the opening balance on this statement — "
                "try your bank's CSV or OFX export"
            )
        delta = balance - prev_balance
        _verify_row(delta, amt_tok, fmt, check_sign=False)  # B prints no amount sign
        row += 1
        full_desc = " ".join([_clean_desc(desc)] + cont).strip()
        parsed.append(_draft(row, posting, delta, full_desc, exponent))
        prev_balance = balance
    drafts, errors = _split(parsed)
    return ParseResult(drafts, errors, None, None)


def _parse_family_d(lines: list[str], exponent: int, fmt: Fmt) -> ParseResult:
    """Family D (Money Market) — ``YYYY MM DD desc [±R amount] R balance``."""
    groups = _fold(lines)
    prev_balance: Decimal | None = None
    parsed: list[TransactionDraft | RowError] = []
    row = 0
    for line, cont in groups:
        bf = _anchor_balance(line, fmt)
        if bf is not None:
            prev_balance = bf
            continue
        m = re.match(
            r"\s*(\d{4})\s+(\d{1,2})\s+(\d{1,2})\s+(.*?)\s+"
            r"((?:-?R[\d.,]+)\s+)(R[\d.,]+-?)\s*$",
            line,
        )
        if not m:
            raise ValueError(_MISPARSE)
        y, mo, d, desc, amt_tok, bal_tok = m.groups()
        balance = _signed_balance(bal_tok, fmt)
        if prev_balance is None:
            raise ValueError(
                "couldn't find the opening balance on this statement — "
                "try your bank's CSV or OFX export"
            )
        delta = balance - prev_balance
        _verify_row(delta, amt_tok, fmt, check_sign=True)
        row += 1
        full_desc = " ".join([desc.strip()] + cont).strip()
        parsed.append(
            _draft(row, _iso(int(y), int(mo), int(d)), delta, full_desc, exponent)
        )
        prev_balance = balance
    drafts, errors = _split(parsed)
    return ParseResult(drafts, errors, None, None)


# Family E's row: ``D[D] Mon YY  desc  [-]amount  [-]balance`` (FIBR-0190 §4.3).
# The `$` anchor plus the lazy description is what protects the description — the
# LAST two money tokens on the line win, so an embedded price can never be read as
# the amount; composing `_MONEY` (two decimals) additionally excludes reference and
# rate tokens. Both minuses are **leading** — the opposite of Family A's trailing
# convention, and a trailing minus is deliberately NOT admitted (D3): it does not
# occur, and refusing the statement beats guessing a sign.
_E_ROW = re.compile(
    rf"^\s*(\d{{1,2}}) ({_MON_RE}) (\d{{2}})\s+(.*?)\s+"
    rf"(-?{_MONEY.pattern})\s+(-?{_MONEY.pattern})\s*$"
)


def _parse_family_e(lines: list[str], exponent: int, fmt: Fmt) -> ParseResult:
    """Family E (Current account, "Payments / Deposits") — ``D[D] Mon YY desc
    [-]amount balance``, FIBR-0190.

    NOTE **"Payments" is the money-OUT column**, despite the word ordinarily
    suggesting money in. That inversion is the single most confusable thing here.
    Nothing below actually consults which column a figure came from: the stored
    amount is the running-balance **delta** and the printed sign is only the
    cross-check (INV-7), exactly as A/B/D do it.

    Takes no ``period``: E prints no "Statement from … to …" line, and needs none —
    every row carries a 2-digit year, so there is nothing to infer (D7)."""
    groups = _fold(lines, dmy_lead=True)
    prev_balance: Decimal | None = None
    parsed: list[TransactionDraft | RowError] = []
    row = 0
    for line, cont in groups:
        bf = _anchor_balance(line, fmt)
        if bf is not None:
            prev_balance = bf
            continue
        m = _E_ROW.match(line)
        if not m:
            raise ValueError(_MISPARSE)
        d, mon, yy, desc, amt_tok, bal_tok = m.groups()
        # _signed_balance, NOT _parse_amount: E's negative balances print a LEADING
        # minus and _parse_amount strips it, which would read every overdrawn row
        # as positive.
        balance = _signed_balance(bal_tok, fmt)
        if prev_balance is None:
            raise ValueError(
                "couldn't find the opening balance on this statement — "
                "try your bank's CSV or OFX export"
            )
        delta = balance - prev_balance
        _verify_row(delta, amt_tok, fmt, check_sign=True)
        row += 1
        full_desc = " ".join([desc.strip()] + cont).strip()
        parsed.append(
            _draft(row, _dmy_iso(f"{d} {mon} {yy}"), delta, full_desc, exponent)
        )
        prev_balance = balance
    drafts, errors = _split(parsed)
    return ParseResult(drafts, errors, None, None)


def _is_cc_skip_line(line: str) -> bool:
    """A zero-date Family-C line that is a **non-transaction**, not a continuation:
    a section header (every word one of credit(s)/debit(s)) or the masked
    "Account …" line (INV-10). These are skipped, not folded."""
    low = line.strip().lower()
    if low.startswith("account"):
        return True
    words = low.split()
    return bool(words) and all(
        w in {"credit", "credits", "debit", "debits"} for w in words
    )


def _parse_family_c(lines: list[str], exponent: int, fmt: Fmt) -> ParseResult:
    """Family C (credit card) — de-interleave two columns; sign = -(printed). A
    zero-date line inside the region folds into the prior segment's description
    (INV-10); a section header / "Account …" line is skipped, and a zero-date line
    before the first segment (no prior) is dropped."""
    staged: list[tuple[str, str, Decimal]] = []  # date_iso, description, signed
    for line in lines:
        segs = _split_credit_card_line(line)
        if not segs:
            # No date on this line: fold it into the prior transaction's
            # description, unless it is a section header / account line.
            if staged and not _is_cc_skip_line(line):
                date_iso, desc, signed = staged[-1]
                staged[-1] = (date_iso, f"{desc} {line.strip()}".strip(), signed)
            continue
        for seg in segs:
            m = re.match(r"(\d{1,2} [A-Za-z]{3} \d{2})\s+(.*?)\s+(-?[\d.,]+)\s*$", seg)
            if not m:
                # A dated segment with no amount is skipped (not raised, unlike the
                # A/B/D _MISPARSE) because Family C has no per-row gate — its
                # mandatory completeness gate (opening - Σ == closing) catches any
                # dropped amount loudly, so a silent under-import is impossible.
                continue
            date_s, desc, amt_tok = m.groups()
            low = desc.lower()
            if "balance brought forward" in low or "closing balance" in low:
                continue
            printed = _parse_amount(amt_tok, fmt)
            # printed purchase (no sign) -> budget negative; printed credit (-) -> +.
            signed = -printed if not _is_negative(amt_tok) else printed
            staged.append((_dmy_iso(date_s), desc.strip(), signed))
    drafts, errors = _split(
        [
            _draft(i + 1, date_iso, signed, desc, exponent)
            for i, (date_iso, desc, signed) in enumerate(staged)
        ]
    )
    return ParseResult(drafts, errors, None, None)


def _dmy_iso(date_s: str) -> str:
    d, mon, yy = date_s.split()
    month = _MON3.get(mon.lower())
    if month is None:  # defensive — the validated _CC_DATE regex should preclude it
        raise ValueError(f"couldn't read the date {date_s!r}")
    return _iso(2000 + int(yy), month, int(d))


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
class StandardBankImporter:
    def parse(
        self, pdf_bytes: bytes, exponent: int, password: str | None = None
    ) -> ParseResult | None:
        """Parse a Standard Bank statement, or return ``None`` when the PDF is not a
        recognised SB statement (-> the wizard's generic fallback, INV-2).

        Raises ``pikepdf.PasswordError`` on a bad/absent user password (reused
        signal), and the all-or-nothing friendly ``ValueError`` on a
        checksum/completeness failure, a mixed number format, or an over-large input
        (INV-11/INV-14)."""
        import pdfplumber

        plaintext = _normalise_to_plaintext(pdf_bytes, password)
        pages: list[list[str]] = []
        # pdfplumber/pdfminer raise a broad, non-ValueError exception tree on a
        # PDF it can't parse (past the pikepdf decrypt, which is upstream and
        # unaffected). Mirror the OFX D7 boundary catch so an untrusted PDF fails
        # as a friendly ValueError, never an unhandled Qt-slot crash. (H-D)
        try:
            with pdfplumber.open(io.BytesIO(plaintext)) as pdf:
                if len(pdf.pages) > _MAX_PDF_PAGES:
                    raise ValueError(
                        "this PDF has too many pages to import — "
                        "try your bank's CSV or OFX export"
                    )
                for page in pdf.pages:
                    pages.append((page.extract_text() or "").splitlines())
        except ValueError:
            raise  # our own friendly guards (e.g. the page cap) pass through
        except Exception as exc:  # untrusted-PDF boundary (mirrors OFX D7)
            raise ValueError(
                "couldn't read this PDF — try your bank's CSV or OFX export"
            ) from exc
        full_text = "\n".join("\n".join(p) for p in pages)

        family = detect_standard_bank(full_text)
        if family is None:
            return None

        period = _parse_period(full_text)

        region_lines: list[str] = []
        for page_lines in pages:
            region_lines.extend(page_lines[_table_region(page_lines, family)])

        # Bound the computation, not just the result (FIBR-0078): every region line
        # is at most a couple of drafts, so len(region_lines) > _MAX_PDF_ROWS means a
        # crafted PDF is trying to make the per-family regex + Decimal parse run over
        # a huge region. Reject here, before that work — the exact post-parse
        # len(result.drafts) cap below still holds (FIBR-0050 Deliverable 1).
        if len(region_lines) > _MAX_PDF_ROWS:
            raise ValueError(
                "this statement has too many transactions to import — "
                "try your bank's CSV or OFX export"
            )

        # Detect the decimal convention from the **transaction region** only (D9 /
        # Deliverable 1) — not the whole document — so a stray opposite-convention
        # money token in the footer / VAT summary / fee structure can't trip the
        # "mixes number formats" refusal on an otherwise-consistent statement.
        fmt = _detect_number_format("\n".join(region_lines))

        if family is Family.A:
            if period is None:
                # Family A prints a "Statement from … to …" line and needs it for
                # year inference; a missing / non-English / garbled one is a
                # malformed statement, surfaced as the friendly mis-parse message
                # rather than a raw int("") ValueError downstream. (H1/M1)
                raise ValueError(_MISPARSE)
            result = _parse_family_a(region_lines, exponent, fmt, period)
        elif family is Family.B:
            result = _parse_family_b(region_lines, exponent, fmt)
        elif family is Family.D:
            result = _parse_family_d(region_lines, exponent, fmt)
        elif family is Family.E:
            # Explicit, NOT left to the terminal `else` — Family C's parser does not
            # fail cleanly on an E statement. `_split_credit_card_line` finds the
            # "28 Feb 26" boundaries and the C segment grammar matches with the
            # **balance** captured as the amount, sign-flipped: wrong money, no
            # exception (FIBR-0190 §4.3).
            result = _parse_family_e(region_lines, exponent, fmt)
        else:
            result = _parse_family_c(region_lines, exponent, fmt)

        if len(result.drafts) > _MAX_PDF_ROWS:
            raise ValueError(
                "this statement has too many transactions to import — "
                "try your bank's CSV or OFX export"
            )

        closing = _capture_closing(full_text, family, fmt)
        if family is Family.C:
            opening = _cc_opening(full_text, fmt)
        else:
            opening = _capture_opening(region_lines, fmt)
        _verify_checksum(family, opening, result.drafts, closing, exponent)

        start, end = _span(period, result.drafts, full_text)
        # Persist the closing balance for the forecast anchor (FIBR-0171 D4): the
        # figure the checksum verified, in signed minor units, or None when the
        # statement prints none (Savings / Family A rides the per-row gate).
        # `_storable`, not `to_minor`: belt-and-braces today (a non-None closing has
        # already been bounded by the gate on the line above), but it keeps "every
        # balance conversion in this file is bounded" a local property rather than
        # one that depends on the gate above never gaining another early return.
        closing_minor = None if closing is None else _storable(closing, exponent)
        if family is Family.E:
            # E prints no closing figure, but its final running balance IS one — and
            # its printed column totals are what make that trustworthy. This must sit
            # AFTER the assignment above, which would otherwise overwrite it with
            # None on the next line (FIBR-0190 §4.5).
            closing_minor = _verify_e_totals(
                full_text, result.drafts, opening, exponent, fmt
            )
        # What this statement says about ITS OWN account (FIBR-0086), read from
        # page 1's header only. The family check here is belt-and-braces — the
        # extractor holds the same guard — so a future caller cannot reintroduce
        # the §2.3 trap by dropping it.
        hint = (
            extract_account_number(pages[0], family)
            if pages and family in _ACCOUNT_NUMBER_FAMILIES
            else None
        )
        # The per-row errors travel with the drafts (FIBR-0252). A literal `[]`
        # here discarded them, so a legitimately-unreadable row — the printed
        # `0.00` line FIBR-0216 degrades on — vanished from the preview, the
        # batch Errors column and `ImportResult.error_count`, and the statement
        # still reported "N added" with no hint that anything was skipped. Only
        # `drafts` feeds the balance gates; an error row carries no money.
        return ParseResult(
            result.drafts, result.errors, start, end, closing_minor, hint
        )


def _cc_opening(full_text: str, fmt: Fmt) -> Decimal:
    for line in full_text.splitlines():
        m = _CC_BROUGHT_FORWARD.search(line)
        if m:
            # The balance printed right after the anchor phrase — the first money
            # token in the tail from the phrase onward (the anchored regex guarantees
            # it abuts the phrase, so a prose decoy whose figure trails narrative
            # text never reaches here, FIBR-0106). Honour the printed sign (as
            # _capture_opening does) — a card that opens in credit prints a negative
            # brought-forward, and the sole Family-C gate (opening - Σ == closing)
            # needs the right sign.
            toks = _money_tokens(line[m.start() :])
            if toks:
                return _signed_balance(toks[0], fmt)
    raise ValueError("couldn't find the opening balance on this statement")


def _span(
    period: tuple[str, str] | None,
    drafts: list[TransactionDraft],
    full_text: str,
) -> tuple[str | None, str | None]:
    """The ``ParseResult`` coverage span (D8): a printed period wins (families A/C
    are the ones that supply one); otherwise min/max parsed date, else the
    statement "Date" line (quiet month)."""
    if period is not None:
        return period
    dates = sorted(d.occurred_on for d in drafts)
    if dates:
        return dates[0], dates[-1]
    stmt = _statement_date(full_text)
    return (stmt, stmt) if stmt else (None, None)


_DATE_YMD = re.compile(r"\bDate\s+(\d{4})\s+(\d{2})\s+(\d{2})\b")
_DATE_DMY = re.compile(r"\bDate\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b")


def _statement_date(full_text: str) -> str | None:
    m = _DATE_YMD.search(full_text)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _DATE_DMY.search(full_text)
    if m and m.group(2).lower() in _MONTHS:
        return _iso(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
    return None
