"""Standard Bank (SA) statement text-parser (FIBR-0050).

One reader for all six of the user's Standard Bank statement types — read the
**printed text lines** (stable across every layout) rather than the fragile ruled
table geometry the generic FIBR-0009 path relies on. A recognised statement feeds
the existing ``preview_result`` -> dedup -> ``commit_import`` pipeline exactly like
OFX (self-describing, so it skips column-mapping).

Four layout families dispatch inside this single module (D1):

* **A** — transactional (Current / Savings / Revolving-Credit): right-anchored
  ``…desc… [amount][-] MM DD balance[-]``; year inferred from the period line.
* **B** — Home Loan: ``PostingDate[ EffectiveDate] desc amount balance`` (ISO
  dates, no printed amount sign).
* **D** — Money Market / investment: ``YYYY MM DD desc [±R amount] R balance``.
* **C** — credit card: two-columns-per-line, section-signed, no running balance.

Signs are budget-view (money out negative): the balance families (A/B/D) take the
printed magnitude carrying the **running-balance delta** sign (INV-7); the credit
card flips its printed sign (INV-6). Integrity is all-or-nothing (INV-11): a
per-row ``|delta| == printed`` gate (A/B/D) plus a completeness gate against the
statement's independently-printed closing figure where one prints.

The decrypt + caps are reused from FIBR-0009; this module adds no dependency and no
schema change.
"""

from __future__ import annotations

import io
import re
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from finbreak.importers.base import ParseResult

# ``PasswordError`` is re-exported: pikepdf's re-prompt signal (FIBR-0009 INV-3), so
# the wizard can catch it from either importer module.
from finbreak.importers.pdf_importer import (
    _MAX_PDF_PAGES,
    _MAX_PDF_ROWS,
    PasswordError,  # noqa: F401  (re-export)
    _normalise_to_plaintext,
)
from finbreak.models import TransactionDraft
from finbreak.services.transactions import parse_transaction

Fmt = str  # Literal["us", "eu"] — kept loose to avoid a typing import churn.


class Family(StrEnum):
    """The recognised Standard Bank layout family (D1/D4)."""

    A = "A"  # transactional: Current / Savings / Revolving-Credit
    B = "B"  # Home Loan
    C = "C"  # credit card
    D = "D"  # Money Market / investment


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
    if header == -1:
        return slice(0, 0)
    end = len(page_lines)
    for j in range(header + 1, len(page_lines)):
        if _is_terminator(page_lines[j]):
            end = j
            break
    return slice(header + 1, end)


# A validated ``D[D] Mon YY`` date — the 3-letter month must be a real month (so a
# random 3-letter token in a description is neither a split point nor reaches the
# ``_cc_iso`` lookup, INV-6).
_MON_RE = "(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
_CC_DATE = re.compile(rf"\d{{1,2}} {_MON_RE} \d{{2}}")
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
    sliding header-block window), most-specific-first C->D->B->A (D4)."""
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
}


def _capture_opening(region_lines: list[str], fmt: Fmt) -> Decimal:
    """The first brought-forward anchor's balance (``opening_balance``; the anchor
    repeats per page on a multi-page statement, D12 — the first is the opening)."""
    for line in region_lines:
        if _BROUGHT_FORWARD in line.lower():
            toks = _money_tokens(line)
            if toks:
                bal = toks[-1]
                return _signed_balance(bal, fmt)
    raise ValueError("couldn't find the opening balance on this statement")


def _capture_closing(full_text: str, family: Family, fmt: Fmt) -> Decimal | None:
    """The statement's independently-printed closing figure, or ``None`` when the
    family prints none (Savings; INV-10). Scans the full document text (the A/RCP
    closings print on a summary page outside the transaction region)."""
    for line in full_text.splitlines():
        low = line.lower()
        for marker in _CLOSING_MARKERS[family]:
            if low.strip().startswith(marker) or marker in low:
                toks = _money_tokens(line)
                if toks:
                    bal = toks[-1]
                    return _signed_balance(bal, fmt)
    return None


def _minor(value: Decimal, exponent: int) -> int:
    return int((value * (10**exponent)).to_integral_value())


def _verify_checksum(
    family: Family,
    opening: Decimal,
    drafts: list[TransactionDraft],
    closing: Decimal | None,
    exponent: int,
) -> None:
    """The completeness gate (INV-11), ``parse``-side. Raises the friendly
    all-or-nothing ``ValueError`` on non-reconciliation. A ``None`` closing is
    family-aware: skip for Family A (Savings legitimately prints none), raise for
    B/D/C (they always print a closing; C has no per-row fallback gate)."""
    if closing is None:
        if family is Family.A:
            return  # Savings — the per-row gate already covered correctness
        raise ValueError(
            "couldn't find the closing balance to check this statement against — "
            "try your bank's CSV or OFX export"
        )
    total = sum(d.amount_minor for d in drafts)
    opening_m = _minor(opening, exponent)
    closing_m = _minor(closing, exponent)
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


# --------------------------------------------------------------------------- #
# Per-family row parsers (each returns drafts only; ``parse`` sets the span)
# --------------------------------------------------------------------------- #
def _fold(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Group region lines into (transaction line, [continuation lines]) — a
    continuation is any in-region line with no date+amount tail, folded into the
    preceding transaction's description (INV-10). Lines before the first transaction
    are dropped."""
    groups: list[tuple[str, list[str]]] = []
    for line in lines:
        if not line.strip():
            continue
        if _looks_like_row(line):
            groups.append((line, []))
        elif groups:
            groups[-1][1].append(line.strip())
    return groups


_TRAILING_TAIL = re.compile(r"\b\d{1,2}\s+\d{1,2}\s+[\d.,]+-?\s*$")  # … MM DD balance
_ISO_LEAD = re.compile(r"^\s*\d{4}-\d{2}-\d{2}\b")
_YMD_LEAD = re.compile(r"^\s*\d{4}\s+\d{1,2}\s+\d{1,2}\b")


def _looks_like_row(line: str) -> bool:
    """A transaction/anchor line for Families A/B/D (a brought-forward anchor, or a
    date + trailing balance). Family C rows are handled by the de-interleave."""
    return bool(
        _BROUGHT_FORWARD in line.lower()
        or _TRAILING_TAIL.search(line)
        or _ISO_LEAD.search(line)
        or _YMD_LEAD.search(line)
    )


def _anchor_balance(line: str, fmt: Fmt) -> Decimal | None:
    """If ``line`` is a brought-forward anchor, its (signed) balance; else ``None``.
    Handles the dated page-1 anchor and the undated continuation-page repeat (D12)."""
    if _BROUGHT_FORWARD not in line.lower():
        return None
    toks = _money_tokens(line)
    if not toks:
        return None
    bal = toks[-1]
    return _signed_balance(bal, fmt)


def _draft(
    row: int, occurred_on: str, signed: Decimal, description: str, exponent: int
) -> TransactionDraft:
    occurred_on, amount_minor, description = parse_transaction(
        occurred_on, signed, description, exponent
    )
    return TransactionDraft(row, occurred_on, amount_minor, description)


def _verify_row(delta: Decimal, amt_tok: str, fmt: Fmt, *, check_sign: bool) -> None:
    """The per-row INV-7b gate: the running-balance ``delta`` must equal the printed
    amount in **magnitude** and (where a sign prints — A/D, not the sign-less B) in
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
    drafts = [
        _draft(
            i + 1, _iso(years[i], md_pairs[i][0], md_pairs[i][1]), delta, desc, exponent
        )
        for i, (desc, delta, _t, _b) in enumerate(staged)
    ]
    return ParseResult(drafts, [], None, None)


def _clean_desc(desc: str) -> str:
    """Strip SB service-fee markers (``##`` / ``*##``) from a description tail."""
    return re.sub(r"\s*\*?##\s*$", "", desc).strip()


def _parse_family_b(lines: list[str], exponent: int, fmt: Fmt) -> ParseResult:
    """Family B (Home Loan) — ``PostingDate[ EffectiveDate] desc amount balance``,
    ISO dates, no printed sign (delta is the sole sign source)."""
    groups = _fold(lines)
    prev_balance: Decimal | None = None
    drafts: list[TransactionDraft] = []
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
        drafts.append(_draft(row, posting, delta, full_desc, exponent))
        prev_balance = balance
    return ParseResult(drafts, [], None, None)


def _parse_family_d(lines: list[str], exponent: int, fmt: Fmt) -> ParseResult:
    """Family D (Money Market) — ``YYYY MM DD desc [±R amount] R balance``."""
    groups = _fold(lines)
    prev_balance: Decimal | None = None
    drafts: list[TransactionDraft] = []
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
        drafts.append(
            _draft(row, _iso(int(y), int(mo), int(d)), delta, full_desc, exponent)
        )
        prev_balance = balance
    return ParseResult(drafts, [], None, None)


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
            staged.append((_cc_iso(date_s), desc.strip(), signed))
    drafts = [
        _draft(i + 1, date_iso, signed, desc, exponent)
        for i, (date_iso, desc, signed) in enumerate(staged)
    ]
    return ParseResult(drafts, [], None, None)


def _cc_iso(date_s: str) -> str:
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
        except Exception as exc:  # noqa: BLE001 — untrusted-PDF boundary (mirror OFX D7)
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

        start, end = _span(family, period, result.drafts, full_text)
        return ParseResult(result.drafts, [], start, end)


def _cc_opening(full_text: str, fmt: Fmt) -> Decimal:
    for line in full_text.splitlines():
        if "balance brought forward" in line.lower():
            toks = _money_tokens(line)
            if toks:
                bal = toks[-1]
                # Honour the printed sign (as _capture_opening does) — a card that
                # opens in credit prints a negative brought-forward, and the sole
                # Family-C gate (opening - Σ == closing) needs the right sign.
                return _signed_balance(bal, fmt)
    raise ValueError("couldn't find the opening balance on this statement")


def _span(
    family: Family,
    period: tuple[str, str] | None,
    drafts: list[TransactionDraft],
    full_text: str,
) -> tuple[str | None, str | None]:
    """The ``ParseResult`` coverage span (D8): A/C = the authoritative printed
    period; B/D = min/max parsed date, else the statement "Date" line (quiet
    month)."""
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
