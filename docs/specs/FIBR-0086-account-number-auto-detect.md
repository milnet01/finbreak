# FIBR-0086 — Detect a statement's account number and file it automatically

**Status:** spec draft (2026-08-06).
**Kind:** feature.
**Source:** ROADMAP FIBR-0086 (user-request-2026-07-11, dogfooding v0.1.0);
promoted ahead of FIBR-0085 by user directive 2026-08-06.

**Blocked by:** none — the storage half shipped as FIBR-0193.
**Blocker for:** FIBR-0085 (batch statement import).
**Pairs with:** FIBR-0059 (change-account fix), FIBR-0057 (destination picker).

**Layman:** When you import a bank statement, finbreak reads the account
number printed on it and files the statement under the right account by
itself — and if it is an account finbreak has never seen, it offers to
create it, pre-filled from the statement.

## 1. Goal

After this ships, importing a statement whose account number matches exactly
one configured account pre-selects that account in the wizard, with a visible
statement of *why* it was selected. A statement matching no configured account
offers to create one, pre-filled with the number, a name and a type read off
the statement. A statement matching more than one account, or carrying no
readable number, falls back to today's manual pick — the destination combo
keeps the value the pick step gave it, and the wizard says why it could not
choose.
The user can always override. `ParseResult` gains one optional field — a
`SourceAccountHint` carrying the number, and where the layout prints them a
name and a family — and no schema change is required.

## 2. Problem

### 2.1 Every import is hand-filed today

`ui/import_wizard.py` asks for the destination account twice — once on the
pick step (`_account_combo`, built in `_build_pick_step`) and again on the
preview step (`_confirm_account_combo`, built in `_build_preview_step`, added
by FIBR-0057 so the target can be changed after the preview). Both are
populated by `_fill_account_combo()`, which lists accounts in the repository's
`ORDER BY name COLLATE NOCASE, id` — i.e. **alphabetically by name**, nothing
to do with the statement. Neither combo is ever pre-selected from the
statement's own contents: the first entry alphabetically wins by default. The
statement is *full* of the answer and the application does not read it.

Two consequences:

1. **Every single-file import is a manual pick that can be got wrong.** The
   default selection is whichever account sorts first, so an inattentive
   import files the statement under an unrelated account. FIBR-0059 exists to
   repair that after the fact; this item removes most of its occasions.
2. **Batch import (FIBR-0085) is not buildable without it.** Selecting a
   folder of statements and hand-mapping each to an account is the tedium
   batch import exists to remove. FIBR-0085 is blocked on this bullet by user
   directive 2026-08-06.

### 2.2 What the statements actually print — measured, not assumed

The design below is grounded in the user's real Standard Bank corpus
(`/mnt/Emulators/storage_backup_2026-05-08/Statements/`, supplied 2026-08-06;
**never committed** — `testing.md` §6). Forty-eight PDFs across six folders,
47 of them readable, read with `pdfplumber` at the supplied password. The probe extracted, from
page 1 of each file, the text preceding an `account number` label and the
digit-run following it.

> **Every account number in this document is a synthetic stand-in, not the
> user's.** The real values are held only in the scratchpad measurement and
> are never written to this repository (INV-8, which binds this document as
> well as the test fixtures). The stand-ins are chosen to **preserve every
> structural relationship the design turns on** — notably §2.3's collision,
> where the Credit Card row's number normalises to exactly the Current row's.
> Digit *lengths* and grouping are preserved; the digits are invented.

| Folder | On disk | Read | Family | Text before the label | Number after it |
|---|---:|---:|---|---|---|
| Current | 10 | 9 | A | `PRESTIGE CURRENT ACCOUNT` | `11 222 333 4` |
| Savings | 16 | 16 | A | `PURESAVE` | `22 333 444 5` |
| RCP Loan | 4 | 4 | A | `STAFF REVOLVING CREDIT (RCC) PLAN LOAN` | `33 444 555 6` |
| Home Loan | 2 | 2 | B | *(none)* | `447556667` |
| Investment | 3 | 3 | D | *(none)* | `5566 777 888 9` |
| Credit Card | 13 | 13 | C | *(none)* | `000112223334` ⚠ |
| **Total** | **48** | **47** | | | |

*On disk* is `find . -name '*.pdf' | wc -l` per folder; *Read* is how many
`pdfplumber` opened at the supplied password. The one-file gap is the
`PdfminerException` paragraph that closes this section.

`Family` is the existing `importers/standard_bank.py::Family` StrEnum, as
returned by `detect_standard_bank()`.

Every folder yielded **at most one distinct number, and never two** — every
file that produced a number produced its folder's only one. (The same corpus
does vary elsewhere: §2.3's card PAN changes mid-sequence, and 2 of the 13
Credit Card files print no page-1 label at all.) Five of the six folders yield
a number that is *their own* account's, on all 34 of their files; the Credit
Card folder's is stable too, on the 11 that print one, and belongs to a
different account — which is §2.3.

**The label falls above the transaction table — measured against the boundary
§4.2 actually specifies, not merely "near the top".** A first-N-lines probe
would prove the wrong thing: §4.2 slices the header at
`_table_region(page_lines, family).start`, so what has to hold is
`label_index < _table_region(...).start` on page 1. Re-run over the corpus
with the real `_table_region` and `detect_standard_bank`, every readable
family-A/B/D file satisfies it:

| Family | Files | Label index | `_table_region(...).start` |
|---|---:|---|---|
| A | 16 | 18 | 21 |
| A | 8 | 17 | 20 |
| A | 4 | 20 | 21 |
| A | 1 | 16 | 19 |
| B | 2 | 11 | 21 |
| D | 3 | 17 | 20 |

34 of 34, with a margin of one to ten lines. Extraction from families A, B
and D is therefore reliable on this corpus **under the specified boundary**.
The narrowest margin is one line (family A, label 20 / start 21), so this is
a measured fact about the current layouts, not a structural guarantee —
§6 carries what happens when a layout change closes that gap.

Family C behaves differently and harmlessly: on 11 of its 13 files
`_table_region` returns `slice(0, 0)` for page 1 (the card's transaction
table starts on a later page), so the header slice is empty and extraction
would yield nothing even if C were not excluded. On the other 2 there is no
label on page 1 at all.

One file, `Current/SBSA_Statement_2026-05-28_3-months.pdf`, raised
`PdfminerException` on open and yielded nothing. It is already handled: the
existing boundary catch in `importers/pdf_importer.py` maps it to a friendly
error. It is counted in the 48 and excluded from the 34.

### 2.3 The credit-card trap — why the obvious implementation is wrong

The Credit Card row above is marked ⚠ because **the number after its
`account number` label belongs to a different account.** Page 1 of
`SBSA Credit Card Statement 2025-07-21.pdf` wraps one sentence across five
layout lines:

```
Payment due                    Payment Information
R205.48 will be processed
through your debit order       Total amount outstanding on this statement 6,849.68
account number 000112223334    Minimum payment due 205.48
on 20 August 2025.             Payment due date 15 Aug 25
```

Read as prose: *"R205.48 will be processed through your debit order **account
number 000112223334** on 20 August 2025."* That is the **debit-order account**
— the current account that pays the card. And it is not a hypothetical
collision: `000112223334` normalises to `112223334`, which is the Current
account's number exactly (row 1 of the table).

So the natural implementation — *find the words "account number", take the
digits* — would file the **11 credit-card statements that carry a page-1
label under the current account** (the other 2 print none there, and a
whole-document scan would take all 13). Under this design that lands as a wrong *pre-selection* rather
than a silent write (INV-7 keeps the preview step), but it is still the
failure the roadmap bullet forbids ("never silently import to the wrong
account"): a confidently-labelled wrong default that a user clicking through
would accept. No amount of careful reading of the design would have caught
it; only the corpus did.

The card's own identifier is printed elsewhere on page 1, masked:

```
Account Summary                Account 1234 **** **** 5678
```

That is a card PAN, not an account number, and **it is not stable**: the
corpus shows one PAN on the four statements up to 2025-10-20 and a
**different** one on the nine from 2025-11-20 onward — a card reissue, with
both the middle digits and the last four changing. An identifier that changes
when the bank posts a new card cannot be the key a stored account is matched
on without the user re-entering it after every reissue.

**Family C is therefore excluded from auto-detect** (§3, decision 2).

### 2.4 Why extraction must be confined to the header

A whole-document digit scan is not merely imprecise, it is actively
poisoned — other accounts' numbers appear inside transaction rows:

- A Current statement's rows carry `SBSA HOMEL 447556667 250920` — the
  **home loan's** number, in a current-account transaction.
- An RCP statement's rows carry `SBSARCP STD 00112223334 20/09` — the
  **current account's** number, in an RCP transaction, zero-padded differently
  again.
- Investment and Savings rows carry masked counterparties: `*****2223334`
  (the Current row's tail) and `*****7778889` (the Investment row's tail) —
  the stand-ins preserve the tail relationship the real strings had.

Counting distinct 9-or-more-digit runs per document, the Current statements
carry **12 to 27** each. Extraction must read only the header block above the
transaction table, which `_table_region(page_lines, family)` already
delimits.

## 3. Scope decisions

Preference calls, not deductions.

1. **This item ships before FIBR-0085** (user, 2026-08-06). The alternative —
   batch import first, with one user-picked account for the whole batch — was
   recommended and declined; the user chose the enabler first so batch import
   can auto-file from its first release.

2. **Family C (credit card) is excluded from auto-detect in v1** (Claude,
   from the §2.3 evidence; a deviation from the roadmap bullet's "PDF printed
   number ... the Standard Bank / generic parsers can surface it"). Its
   labelled number
   provably belongs to another account, and its only self-identifier is a PAN
   that changes on reissue. Credit-card imports keep today's manual pick.
   Tracked as a follow-up in §9.

3. **Masked / trailing-digit matching is deferred for PDF**, a deviation from
   the bullet ("match on TRAILING digits when the statement masks it"). No PDF
   in the 48-file corpus presents a *masked* number as its own identifier —
   the only masked self-identifier is the Family C PAN, which decision 2
   excludes, and the other masked strings are counterparties in transaction
   rows (§2.4) that must never be matched on at all. Building a matching path
   that nothing exercises adds a way to match *more* loosely with no evidence
   it is ever needed.

   **The scope of that evidence is PDF only, and this is stated rather than
   glossed:** the corpus contains **zero OFX files**, and OFX is the format
   the roadmap calls "reliable" and the one most likely to mask. So for OFX
   this is not a measured deferral but an unmeasured risk; §6 carries the
   failure mode and the blank-prefill mitigation, and §9 the revisit trigger.

4. **A detected match is pre-selected, never auto-committed.** The wizard
   still shows the preview step and the user still presses the button.
   Auto-detect changes the default, not the flow.

5. **Ambiguity always degrades to manual, never to a guess.** Zero matches
   and two-or-more matches both leave the destination combo **exactly as it is
   today** — seeded from the pick step — and show an explanatory label instead
   of a match. Auto-detect only ever *changes* the selection on `matched`.
   This is the rule the whole design is built to protect.

   **It is deliberately not "clear the combo".** `_target_account_id()` is
   typed `-> int` and returns `self._confirm_account_combo.currentData()`,
   which is `None` for an unselected combo; `preview_result(result,
   account_id: int)` cannot take that. So "nothing pre-selected" is not
   implementable without widening two existing signatures, and it would buy
   nothing: today's seeded default is already the manual behaviour this
   degrades to.

## 4. Design

### 4.1 The seam: one optional field on `ParseResult`

The seam must carry **three** things, not one — §4.6 prefills an account's
number, name and type, and a bare `str` can only carry the number. So the new
field is a small value object, and `ParseResult` still gains exactly one field,
appended **last**, exactly as FIBR-0171 appended `closing_balance_minor`:

```python
# --- importers/base.py -----------------------------------------------------

@dataclass(frozen=True)
class SourceAccountHint:
    """What a statement says about the account it belongs to (FIBR-0086).

    Everything here is as-PRINTED, never normalised — normalisation is a
    matching concern and lives in services/account_match.py. Every field
    except ``number`` is best-effort: the formats differ in what they print."""

    number: str          # as printed, grouping and padding intact
    name: str | None = None    # the product name, where the layout prints one
    family: str | None = None  # the Family value, as a str; None for non-SB


@dataclass
class ParseResult:
    drafts: list[TransactionDraft]
    errors: list[RowError]
    period_start: str | None
    period_end: str | None
    closing_balance_minor: int | None = None
    # FIBR-0086, appended last so every existing positional construction is
    # unchanged. None when the format carries no account number, or the
    # family is excluded (§4.2).
    source_account: SourceAccountHint | None = None
```

Named `source_account`, not `account`, so no reader confuses it with
`models.Account` (the stored row it is matched *against*). `family` is typed
`str | None` rather than `Family` so `base.py` keeps depending on nothing —
it is imported by every importer, and a `Family` import there would make the
shared value object depend on the Standard Bank one.

Every importer keeps working untouched; three start populating it:

| Importer | `number` from | `name` | `family` | Populated when |
|---|---|---|---|---|
| `StandardBankImporter.parse` | §4.2 header extraction | family A only (B and D print none) | always | family ∈ {A, B, D} |
| `OfxImporter.parse` | `account.account_id`, already read into `OfxAccountInfo` | `None` | `None` | `account_id` is non-empty |
| `CsvImporter.parse` | — | — | — | never; CSV carries no account number |

Those three are the complete set: `ParseResult` is constructed in exactly
`csv_importer.py`, `ofx_importer.py` and `standard_bank.py` — verified with
`grep -rn "ParseResult(" src/finbreak/`, which returns eight construction
sites across those three files and no others. `pdf_importer.py` produces
*candidate tables*, not a `ParseResult`, so it has no row. `base.py`'s own
docstring also mentions a "manual" source; manual entry creates transactions
directly and never builds a `ParseResult`, so it is not a fourth producer.

**OFX carries an `account_type` this design deliberately does not use.**
`OfxAccountInfo` already holds it, and the roadmap bullet asks for
"type/currency where available", so dropping it is a third deviation and is
recorded as one rather than left silent: OFX's `<ACCTTYPE>` vocabulary
(`CHECKING`, `SAVINGS`, `CREDITLINE`, …) does not map onto this app's account
types without a translation table nobody has validated, and a *wrong*
prefilled type is worse than an empty one the user fills in. §9 tracks it.

OFX needs no new extraction: `OfxImporter.parse` already builds
`OfxAccountInfo(account.account_id or "", ...)`. The value is threaded into
the `ParseResult` beside it.

### 4.2 Header-confined, family-dispatched extraction

New in `importers/standard_bank.py`:

```python
# The label as printed. The corpus shows three spellings: "Account Number"
# (families A and B), "account number" (C, excluded), "Account number:" (D) —
# hence the case-insensitive match and the optional colon.
#
# The captured run allows a SINGLE space or dash between digits (grouping, as
# in "11 222 333 4") and therefore stops at a column gap of two or more
# spaces. It deliberately does NOT use `[\d\s-]*`, which is greedy across any
# whitespace and merges a following numeric column into the key: verified
# 2026-08-06, `Account Number 44 555 666 7   2024 03 27` captured
# "44 555 666 7   2024 03 27" under the greedy form and "44 555 666 7" under
# this one, with zero difference across all 34 readable A/B/D files.
_ACCOUNT_LABEL = re.compile(
    r"account\s+number\s*:?\s*((?:\d[ -]?)*\d)", re.IGNORECASE
)

# Families whose header label names THEIR OWN account. C is absent by
# design, not by omission: its label names the debit-order account (§2.3).
_ACCOUNT_NUMBER_FAMILIES = frozenset({Family.A, Family.B, Family.D})


def extract_account_number(
    page_lines: list[str], family: Family
) -> SourceAccountHint | None:
    """What this statement prints about ITS OWN account, or None.

    Returns None for any family not in _ACCOUNT_NUMBER_FAMILIES — the guard
    lives HERE, in the extractor, not only at the call site, so that calling
    it directly with Family.C (which INV-1's test does) cannot yield the
    debit-order account. A call-site-only guard would let INV-1 pass while
    the function it names stays wrong.

    Reads only the header block ABOVE the transaction table, because other
    accounts' numbers appear inside transaction rows (§2.4). Scans the header
    block TOP-DOWN and takes the FIRST line matching _ACCOUNT_LABEL; later
    matches are ignored. (Every file measured in §2.2 has exactly one, so the
    rule is only reached by a layout that changes; first-wins keeps it
    deterministic rather than order-dependent.) Values are returned as
    printed; the caller normalises."""
```

The header block is `page_lines[: _table_region(page_lines, family).start]`,
measured in §2.2 to contain the label on 34 of 34 readable A/B/D files.
Reusing `_table_region` — rather than a new "first N lines" rule — means the
boundary moves with the table detection it already governs, and a
header-layout change cannot silently widen the scan into transaction rows.

`name` is the text on the label line *before* the label, stripped, when
non-empty — the §2.2 measurement (family A prints its product name there;
B and D print nothing). `family` is `str(family)`.

Family E is not in the set. It is a Current-account layout (FIBR-0190) and
would be expected to print a Family-A-style label, but **no Family E
statement exists in the corpus**, so including it would be an untested claim.
§9 records the trigger.

`StandardBankImporter.parse` calls it once, on page 1's lines. The call site
keeps its own `family in _ACCOUNT_NUMBER_FAMILIES` check as belt-and-braces,
so a future caller cannot reintroduce the §2.3 trap by dropping the guard.

### 4.3 Normalisation

New module `services/account_match.py`:

```python
def normalise_account_number(raw: str) -> str:
    """Digits only, leading zeros removed — the comparison key.

    Grouping varies by layout ("11 222 333 4" vs "447556667"), so it must not
    decide identity. Returns "" for a value with no digits, which never
    matches (INV-4)."""
    return re.sub(r"\D", "", raw).lstrip("0")
```

**Grouping-insensitivity is measured; padding-insensitivity is defensive, and
the distinction matters.** The corpus shows grouping varying between layouts
(spaces in A and D, none in B), so stripping non-digits is required by the
evidence. It shows **no** leading-zero variation in any *extractable header* —
the zero-padded spellings that appear (`000112223334`, `00112223334`) are both
from positions §4.2 refuses to read: the Family-C debit-order label and an RCP
transaction row. So `lstrip("0")` is justified defensively, against a bank that
pads its own header inconsistently between statements, not by an observed case.
It is retained rather than dropped because the two directions are not
symmetric:

- Stripping can only make two numbers **more** likely to be equal. Two stored
  accounts colliding is an *ambiguous* match, which §4.4 resolves to manual.
- Not stripping can make a statement fail to match its own account, which
  sends a correct detection to `no_match` and offers to create a duplicate.

The one assumption it rests on, stated because it is an assumption and not a
fact about banking generally: **within this application, two accounts whose
numbers differ only in leading zeros are never distinct accounts.** If that is
ever false, the pair is ambiguous and lands in manual — degraded, not wrong.

### 4.4 The matching ladder

```python
@dataclass(frozen=True)
class AccountMatch:
    """Why the wizard selected (or did not select) an account."""
    account_id: int | None      # None unless exactly one candidate matched
    outcome: Literal["matched", "no_number", "no_match", "ambiguous"]
    normalised: str             # the MATCH KEY only ("" when no_number).
                                # No prefill reads this — §4.6 prefills from
                                # hint.number, as printed.
    candidates: tuple[int, ...] # every id that matched; len != 1 => no select


def match_account(
    hint: SourceAccountHint | None, accounts: Sequence[Account]
) -> AccountMatch:
```

The rules, in order:

1. `hint` is `None`, or `hint.number` normalises to `""` →
   `no_number`. Nothing is pre-selected.
2. `hint.number` contains a **masking character** (`*`, `x` or `X`) →
   `no_number`. This is what actually *enforces* §3 decision 3's deferral, and
   without it the deferral is a comment rather than a rule: normalisation
   strips non-digits, so `"xxxx1234"` becomes `"1234"` (verified 2026-08-06)
   and would match a stored account numbered `1234` — matching on a masked
   tail by accident, which is precisely what decision 3 declined to build
   deliberately. The check is on the **raw** `hint.number`, before
   normalisation, because normalisation destroys the evidence.
3. Otherwise collect every account whose stored `account_number` is non-`None`
   and normalises to the **same** string. Accounts with a `NULL`
   `account_number` never match anything — a fresh vault matches nothing.
4. Exactly one candidate → `matched`, `account_id` set.
5. Zero candidates → `no_match`. Offers creation (§4.5).
6. Two or more → `ambiguous`. The combo is left as the pick step set it and
   the wizard says why it could not choose (§3 decision 5).

Comparison is on the normalised form of *both* sides, so a user who typed
`11 222 333 4`, `112223334` or `0112223334` when creating the account gets
the same result.

### 4.5 The three outcomes in the wizard

The hook is the existing preview-step picker `_confirm_account_combo`
(FIBR-0057) and its `_target_account_id()`. No new step and no new dialog for
the matched path.

**Order matters here more than anything else in this spec, so it is stated as
a sequence rather than left to the implementer.** Matching runs *before* the
preview is built, and the preview is built against the matched account:

```
1. parse            -> ParseResult (carries source_account)
2. match_account(result.source_account, accounts)   -> AccountMatch
3. seed _confirm_account_combo from the match, under QSignalBlocker
4. preview = preview_result(result, _target_account_id())   <-- now the match
   (_target_account_id() returns _confirm_account_combo.currentData(), which
    step 3 has just set — verified against source 2026-08-06)
5. show the preview step
```

**Why the order is load-bearing, and what goes wrong reversed.** The combo's
`currentIndexChanged` is wired to `_on_confirm_account_changed`, which is the
*only* thing that re-points an already-built preview — it calls
`self._imports.retarget(self._preview, account_id)`. A `QSignalBlocker`
suppresses that signal. So setting the combo to a matched account *after* the
preview exists, under a blocker, would leave `self._preview` targeted at the
previous account while the combo displayed the matched one — and
`commit_import` persists `self._preview`. The user would approve a screen
reading "Matched account number …" and the transactions would land somewhere
else. **That is the wrong-account commit this whole spec exists to prevent**,
so the blocker is only ever safe when the preview has not been built yet,
which is what step 3-before-4 guarantees. (This is why the existing seeding at
step 0 → preview step is safe under its blocker: it also runs before
`preview_result`.)

Auto-detect also **overrides the step-0 pick** when it fires, because the
statement is better evidence than a default the user may never have touched.
`no_number`, `no_match` and `ambiguous` leave the existing pick-step seeding
untouched (§3 decision 5) — they change the *label*, never the selection.

- **`matched`** — the combo is set to the matched account per the sequence
  above, and a label beneath it reads *"Matched account number 11 222 333 4
  printed on this statement."* The user can still change it afterwards, which
  goes through `_on_confirm_account_changed` and re-runs the
  duplicate-detection pass exactly as it does today.
- **`ambiguous`** — the combo keeps the pick step's value; the label reads
  *"This statement's account number matches more than one account — pick
  one."*
- **`no_match`** — the combo keeps the pick step's value; the label offers
  creation with a button, *"No account has number 22 333 444 5. Create it?"*

**Every label renders `hint.number` as printed, never the normalised key.**
The number on screen is the one the user can see on the paper statement in
front of them; showing `112223334` where the page says `11 222 333 4` invites
them to conclude the app read it wrong.

`no_number` shows no label at all: the wizard looks exactly as it does today,
which is the correct behaviour for CSV, for Family C and for Family E.

### 4.6 Create-from-statement prefill

The create button opens the existing account-create path pre-filled from
three statement-derived values:

| Field | Source | Available for |
|---|---|---|
| `account_number` | `hint.number`, **as printed** | every detecting family |
| `name` | `hint.name` | family A only |
| `type` | derived from `hint.family` | families B, D |

All three arrive through the single `SourceAccountHint` field of §4.1; there
is no second seam.

**A masked number never reaches this form at all**, so there is no masking
case to handle here. §4.4 rule 2 classifies it `no_number`, and `no_number` is
the one outcome that offers no creation button (§4.5) — creation is reachable
only from `no_match`. An earlier draft of this spec carried a "blank the
number when masked" rule here; it guarded a branch nothing could enter, and
removing it is the shorter correct design rather than a loss of safety.

`account_number` is stored **as printed**, not as the normalised key —
storage keeps what the statement said, and every comparison normalises both
sides at match time (§4.4), so a stored `11 222 333 4` matches a later
statement printing `112223334` regardless. Storing the stripped form would
silently rewrite what the user could verify against the paper.

The name prefill is the §2.2 measurement: family A prints the product name
immediately before the label on the same line, and it was stable across all
29 family-A files — `PRESTIGE CURRENT ACCOUNT`, `PURESAVE`, `STAFF REVOLVING
CREDIT (RCC) PLAN LOAN` (product names, not account data). Families B and D
print nothing there, so `hint.name` is `None` and the box is left empty.

Type is inferred only where the family determines it — `B` → loan,
`D` → investment. `A` spans current, savings **and** revolving credit (per
the `Family` enum's own comment), so it yields no type and the user picks.
Every prefilled field stays editable; nothing is created without the user
confirming.

## 5. Invariants

- **INV-1** — `extract_account_number(lines, Family.C)` returns `None`, for
  every `lines`. The guard is in the extractor itself, so the invariant holds
  under a direct call and not merely at `StandardBankImporter.parse`'s call
  site.
  *Test:* `tests/features/account_detect/test_extract.py::test_family_c_yields_none`
  — calls the extractor **directly** with a synthetic Family-C page whose
  header carries a `account number 000112223334` label, and asserts `None`.
  *Breaks when:* `Family.C` is added to `_ACCOUNT_NUMBER_FAMILIES`, or the
  guard is moved to the call site only — either of which files every
  credit-card statement under the debit-order account.

- **INV-2** — Extraction reads only lines above `_table_region(...).start`.
  *Test:* `tests/features/account_detect/test_extract.py::test_ignores_number_in_transaction_rows`
  — a synthetic family-A header carrying `Account Number 11 222 333 4`, whose
  transaction rows below the column header contain `SBSA HOMEL 447556667`,
  extracts `11 222 333 4`. Both numbers are invented (INV-8).
  *Breaks when:* the scan is widened to the whole page, at which point a
  current-account statement can extract the home loan's number from a row.

- **INV-2a** — The captured run stops at a column gap: a label line with a
  further numeric column to its right yields only the account number.
  *Test:* `tests/features/account_detect/test_extract.py::test_capture_stops_at_column_gap`
  — `"Account Number 44 555 666 7   2024 03 27"` extracts `"44 555 666 7"`,
  not `"44 555 666 7   2024 03 27"`.
  *Breaks when:* the capture class is widened back to `[\d\s-]*`, which
  crosses any whitespace and merges the next column into the key. Verified
  2026-08-06: the greedy form fails this case and the specified form passes
  it, with identical output on all 34 readable A/B/D files.

- **INV-3** — `match_account` returns an `account_id` only when exactly one
  account matched; `candidates` always carries every match.
  *Test:* `tests/features/account_detect/test_match.py::test_two_matches_select_nothing`.
  *Breaks when:* the ladder returns the first candidate instead of requiring
  uniqueness — which silently picks one of two equally valid accounts.

- **INV-4** — An account whose stored `account_number` is `NULL` never
  matches, and a statement number that normalises to `""` never matches.
  *Test:* `tests/features/account_detect/test_match.py::test_null_and_empty_never_match`.
  *Breaks when:* normalisation returns `""` on both sides and `"" == ""`
  matches — which files every statement under every unnumbered account.

- **INV-5** — Normalisation is padding- and grouping-insensitive:
  `normalise_account_number` maps `"11 222 333 4"`, `"112223334"`,
  `"000112223334"` and `"00-112-223-334"` to the same string.
  *Test:* `tests/features/account_detect/test_match.py`, parametrised over the
  four spellings above plus one negative (`"no digits"` → `""`).
  *Breaks when:* the digit filter drops the `lstrip("0")` — after which a
  bank that pads differently between statements stops matching its own
  account.

- **INV-6** — Adding `source_account` leaves every existing
  `ParseResult` construction valid.
  *Test:* `./scripts/ci-local.sh` — the full gate, with no `ParseResult`
  construction edited outside the three importers named in §4.1. The
  baseline to hold is the pre-change suite total (1791 passed / 2 skipped at
  `e32fe73`, the FIBR-0231 close), plus this spec's new tests and nothing else.
  *Breaks when:* the field is inserted before `closing_balance_minor` rather
  than appended, which shifts every positional construction by one.

- **INV-7** — Auto-detect never commits an import. The preview step is still
  shown and the destination is still user-changeable.
  *Test:* `tests/features/account_detect/test_wizard.py::test_match_preselects_but_does_not_commit`.
  *Breaks when:* a future change wires `matched` straight to the commit path
  — turning a wrong match from a visible default into a silent misfiling.

- **INV-7a** — The account the preview was computed against is always the
  account the combo displays. There is no state in which the wizard shows
  "Matched account number X" over a preview built for a different account.
  *Test:* `tests/features/account_detect/test_wizard.py::test_preview_account_matches_displayed_account`
  — drives a `matched` import and asserts
  `wizard._preview.account_id == wizard._confirm_account_combo.currentData()`.
  *Breaks when:* the combo is seeded from the match **after** `preview_result`
  under a `QSignalBlocker` (§4.5). The blocker suppresses
  `currentIndexChanged`, so `_on_confirm_account_changed` — the only thing
  that calls `retarget` — never runs, and `commit_import` persists the
  stale-account preview. This is the wrong-account commit, and the ordering in
  §4.5 is the only thing preventing it.

- **INV-8** — No real statement, password, or account number from the user's
  corpus enters the repository. **This binds prose as well as fixtures** —
  this document, the ROADMAP bullets, the CHANGELOG and every commit message
  are as public as the code, and `docs/specs/` is tracked in a repo whose
  visibility is `PUBLIC` (`gh repo view --json visibility`, checked
  2026-08-06).
  *Test:* `tests/features/account_detect/test_no_real_data.py::test_no_corpus_numbers_in_tree`
  — walks the tracked tree (`git ls-files`), **normalises each file's digit
  runs the same way `normalise_account_number` does**, and fails on a match
  against the five distinct corpus keys, which the test reads from the
  **environment** (`FINBREAK_CORPUS_NUMBERS`, comma-separated) and **skips**
  when it is unset, so the numbers it guards against are never themselves
  committed. Run it with the variable set before any push touching this
  feature.

  **Normalising the haystack, not just the needles, is the whole point.**
  Everything this spec stores and displays is *as printed* (§4.5, §4.6), so
  the likeliest leak spelling is `11 222 333 4` — which does not contain the
  substring `112223334`. A needle-only grep would miss exactly the shape the
  rest of the design encourages. Five keys, not six: §2.3's credit-card
  number normalises to the current account's, so the six sources yield five
  distinct values.
  *Breaks when:* a number is pasted from a real statement into a fixture, a
  spec paragraph, or a commit message — which publishes the user's banking
  data irrevocably, since rewriting public history does not un-publish it.

  **`gitleaks` does not cover this and is not cited as if it did.** It matches
  credential and key patterns; a bare nine-digit run is not one, so the gate
  would pass a leak of exactly this shape. That gap is why this invariant
  needs a test of its own rather than a pointer at the existing gate.

- **INV-9** — A `hint.number` containing a masking character (`*`, `x`, `X`)
  yields `no_number`, so it never matches an account and never reaches the
  create form (which only `no_match` offers).
  *Test:* `tests/features/account_detect/test_match.py::test_masked_number_never_matches`
  — `match_account(SourceAccountHint("xxxx1234"), [account numbered "1234"])`
  returns `no_number`, not `matched`.
  *Breaks when:* the masking check is done after normalisation instead of
  before it. Normalisation strips non-digits, so `"xxxx1234"` becomes
  `"1234"` (verified 2026-08-06) and matches a real account numbered `1234` —
  accidentally implementing the trailing-digit matching §3 decision 3
  explicitly declined to build.

## 6. Failure modes

- **The label moves or is reworded.** Extraction returns `None`, the wizard
  shows no label, and the user picks manually — today's behaviour. A layout
  change degrades the feature; it does not misfile.
- **`_table_region` finds no column header on page 1.** It does **not** raise
  — it returns `slice(0, 0)`, so `.start` is `0` and the header block is
  `page_lines[:0]`, i.e. empty. Extraction yields `None` → `no_number`. (Zero
  *length* is not the operative property: a `slice(5, 5)` is also zero-length
  and would still give a five-line header. `.start` is what matters.) This is
  the observed Family-C shape on 11 of 13 files (§2.2) and it fails safe.
- **A layout change moves the label below the column header.** §2.2 measured a
  margin as narrow as one line, so this is reachable without a redesign. The
  label then falls outside the header slice, extraction returns `None`, and
  the wizard degrades to manual. Safe, but silent — nothing alerts anyone that
  auto-detect stopped working, which §11 records as an accepted gap.
- **A label line carries a further number one space away** (e.g.
  `Account Number 44 555 666 7 44`). The capture merges them, producing a key
  no account matches → `no_match`, offering to create an account with a
  visibly wrong number the user can correct or decline. Not observed in the
  corpus — every A/B/D label line either ends at the number or continues with
  words — and the harm is bounded at a bad prefill, never a wrong match,
  because a merged key is not expected to collide with a correctly-stored
  number — though nothing makes that impossible, and a user who stored the
  merged spelling would collide. §11 records it as unchecked.
- **Two accounts genuinely share a normalised number.** `ambiguous`; nothing
  selected. This is the correct outcome, and it is also what protects the
  §4.3 leading-zero decision.
- **The user stores a wrong number against an account.** Statements match the
  wrong account, visibly, with the number shown in the label. The user sees
  the mismatch and changes the combo. This is a data-entry error the design
  surfaces rather than hides.
- **A bank pads differently between two statements of the same account.**
  Covered by INV-5; both normalise identically.
- **OFX `account_id` is masked by some institution.** §4.4 rule 2 classifies
  it `no_number`, so the wizard shows no label, offers no creation, and looks
  exactly as it does today — the safe outcome. **Without that rule it would be
  actively harmful**, because normalisation strips the mask: `"xxxx1234"`
  becomes `"1234"` (verified 2026-08-06), which can *match* a real account
  numbered 1234, or reach `no_match` and offer to create an account
  permanently numbered `1234`. Rule 2 is therefore the mitigation, INV-9 locks
  it, and this is **unmeasured territory**: the corpus is 48 PDFs with zero
  OFX files, so §3 decision 3's evidence does not reach the format the roadmap
  calls "reliable". §9 records the rest.

## 7. Tests

New suite `tests/features/account_detect/` with its own `spec.md`, per
`docs/standards/testing.md`. **All fixtures are synthetic strings** — the
real corpus is read only in the scratchpad, never committed (INV-8).

| File | Locks | Notes |
|---|---|---|
| `test_extract.py` | INV-1, INV-2, INV-2a | Synthetic per-family header blocks built to the shapes measured in §2.2, including a family-A header whose rows carry a foreign account number, and a label line with a trailing numeric column. |
| `test_match.py` | INV-3, INV-4, INV-5, INV-9 | Pure-function tests over `match_account` / `normalise_account_number`; no vault. |
| `test_wizard.py` | INV-7, INV-7a | `qtbot`; asserts the combo selection, that the preview's account equals the displayed one, and that no commit occurred. Probe widget reveal with `isHidden()`, not `isVisible()`: a widget on a non-current `QStackedLayout` page reports `isVisible() == False` even after `setVisible(True)`, because visibility needs the whole ancestor chain shown. |
| `test_no_real_data.py` | INV-8 | Walks `git ls-files`, normalises each file's digit runs, and fails on any of the corpus keys supplied via `FINBREAK_CORPUS_NUMBERS`; skips when unset. |

**Every `test_extract.py` fixture must contain a line `_table_region`
recognises as that family's column header** — for family A, one carrying
`balance` plus one of `debit`/`debits`/`withdrawals`/`date` and *no* money
token. Without it `_table_region` returns `slice(0, 0)`, the header slice is
empty, and the test passes or fails for a reason unrelated to what it claims
to lock (§6's first failure mode). Fixture shape: header lines → column-header
line → transaction rows.

Every test must be seen to fail against pre-change code before the change
lands (`testing.md`; `superpowers:test-driven-development`).

**Two of them need the red state constructed rather than found**, because
pre-change the extractor does not exist at all and a test against absent code
fails for the wrong reason:

- *INV-1's red state* — write the *generic* extractor first (label match, no
  family guard), watch `test_family_c_yields_none` fail against it, then add
  the guard. That failing run is the assertion that would have caught the §2.3
  trap; skipping it leaves INV-1 proven only against code that was never
  wrong.
- *INV-2a's red state* — same shape: build it with the greedy `[\d\s-]*`
  class, watch `test_capture_stops_at_column_gap` fail, then narrow the class.

For the rest, the red state is the ordinary one: the symbol does not exist,
the import fails, write it.

Ripple: `ParseResult`'s new field is additive with a default, so no existing
test changes (INV-6). If any does, INV-6 has been violated and the field was
not appended last.

## 8. Alternatives considered (and rejected)

1. **Scan the whole document for an account-number label.** Rejected on
   §2.4's evidence: Current statements carry 12–27 distinct long digit runs,
   including the home loan's number inside a transaction row. It would misfile.

2. **Match Family C on its masked PAN (`1234 **** **** 5678`).** Rejected:
   the corpus shows the PAN changing mid-sequence on a card reissue (four
   statements carry one, the following nine carry another), so every reissue
   would silently stop matching, and a 4-digit tail is a weak key besides.

3. **Take the number after the `account number` label on every family,
   including C.** This is the obvious implementation and it is wrong — §2.3.
   Recorded here because it is what the next reader will propose.

4. **Auto-commit an import when exactly one account matches.** Rejected
   (§3, decision 4): it converts a wrong match from a visible default into a
   silent misfiling, and the roadmap bullet forbids exactly that.

5. **Store the detected number on the account automatically on first
   import.** Rejected for v1: it writes user data as a side effect of an
   import, and a single wrong detection then becomes permanent. Creation
   stays explicit (§4.6).

6. **Put normalisation in `models.Account`.** Rejected: matching is a
   service concern and `models.py` is data shapes only, per `design.md`'s
   layering.

## 9. Out of scope

- **Family C auto-detect** — needs a stable card identifier; revisit if
  Standard Bank prints a non-PAN account number, or if the user accepts
  re-entering the last four digits after each reissue. Tracked as FIBR-0240.
- **Masked / trailing-digit matching** — deferred per §3 decision 3.
  Revisit trigger: the first real statement or OFX file whose *own*
  identifier is masked, **other than the Family C PAN** — that one already
  exists in the corpus (§2.3) and FIBR-0240 owns it, so a trigger that
  included it would fire on day one and mean nothing. Tracked as FIBR-0241.
- **Family E extraction** — no Family E statement exists in the corpus.
  Revisit when one does. Tracked as FIBR-0242.
- **OFX `<ACCTTYPE>` → account-type prefill** — the value is available on
  `OfxAccountInfo` and deliberately unused (§4.1); mapping its vocabulary onto
  this app's account types needs a translation table nobody has validated.
  Tracked as FIBR-0243.
- **Non-Standard-Bank PDF families** (ABSA/Nedbank/FNB) — already tracked by
  FIBR-0074, itself blocked on sample statements.
- **Batch import** — FIBR-0085, which this unblocks.

## 10. Resource cost

No new state, no new build target, no new dependency. No schema change:
FIBR-0193 already shipped `accounts.account_number` at v12→v13.

Bounded, rather than "negligible": extraction runs **one regex over at most
`_table_region(...).start` lines of page 1 only** — 21 lines or fewer on
every file measured in §2.2 — and never over the transaction body or later
pages, so it is O(header) and independent of statement length. Matching is
one linear pass over the configured accounts (`normalise_account_number` is a
character filter), so O(accounts), with no vault read beyond the account list
the wizard already loads to populate its combo. Per `ParseResult`, one extra
reference to a frozen 3-field value object, or `None`.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `test_extract.py::test_family_c_yields_none` |
| INV-2 | `test_extract.py::test_ignores_number_in_transaction_rows` |
| INV-2a | `test_extract.py::test_capture_stops_at_column_gap` |
| INV-3 | `test_match.py::test_two_matches_select_nothing` |
| INV-4 | `test_match.py::test_null_and_empty_never_match` |
| INV-5 | `test_match.py` normalise cases |
| INV-6 | `./scripts/ci-local.sh` — the full gate (a positional break fails many tests) |
| INV-7 | `test_wizard.py::test_match_preselects_but_does_not_commit` |
| INV-7a | `test_wizard.py::test_preview_account_matches_displayed_account` |
| INV-8 | `test_no_real_data.py::test_no_corpus_numbers_in_tree` — covers full account numbers only. A pasted **masked tail** (§2.4's `*****NNNNNNN` counterparties) is a 7-digit fragment that will not match any of the five 9-to-11-digit keys, so that shape is **unchecked**; the author is the guard. **Only when `FINBREAK_CORPUS_NUMBERS` is set**; it skips in CI, which cannot hold the numbers. So CI does not catch this: a developer running it before a push does. Explicitly **not** `gitleaks`, which matches credential patterns and would pass a bare digit run. |
| INV-9 | `test_match.py::test_masked_number_never_matches` |
| §4.6 name prefill is correct for family A | **nothing** — the prefill is read from a synthetic fixture matching the measured shape, so a *real* layout change is caught only by a user noticing a wrong name. Low consequence: the field is editable before creation. |
| §2.2's corpus measurements (one number per folder; label above `_table_region(...).start` on 34/34) | **nothing** — one-off scratchpad measurements over a corpus that is not in the repository and cannot be re-run in CI. Re-measure if the extraction rules or the `_table_region` header detection change. |
| Auto-detect silently stopping (a layout change moves the label below the column header, §6) | **nothing** — every degraded path is indistinguishable from "this format carries no number". No metric, no warning. Accepted: the failure is safe, and the alternative is alerting on a condition that is also the normal CSV case. |
| The `hint.name` / `hint.family` prefills matching the account the user then creates | **nothing** — the user is the check; both fields are editable and neither participates in matching. |
| A merged capture (§6, a number one space right of the label) colliding with a correctly-stored account number | **nothing** — the design makes it unlikely, not impossible, and no test can enumerate the collision space. Bounded: a collision produces a wrong pre-selection, which INV-7 keeps visible and user-changeable. |

## 12. Cross-doc impact

- `CHANGELOG.md` — an `Added` entry at release.
- `README.md` — the import section gains a line about automatic filing.
- `docs/specs/FIBR-0085-*.md` — will cite this spec as its enabler when written.
- ROADMAP — FIBR-0086 → 🚧 at implementation; FIBR-0240/0241/0242/0243 filed from §9.
- No standard changes. No ADR: this adds no dependency and no new layer.

**INV-8 binds every one of those.** The invariant is not a testing rule — it
covers prose, and the CHANGELOG entry, the README line, the ROADMAP
annotations and each commit message on this feature are all published. Write
them about *shapes* ("the account number printed on the statement"), never
about values. The `test_no_real_data.py` grep covers the tracked tree, which
catches the files but **not** commit messages; those are on the author.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 3 | 2026-08-06 | 3 | 2 | 4 | 3 | 8 | 17 verified, all fixed; 0 dismissed. Dimensions: dim 4×6, dim 7×3, dim 12×3, dim 5×3, dim 6×2. Origin split: **2 draft, 15 collateral — the second consecutive loop dominated by collateral**, which is loop-economics' stop-dispatching signal; answered by a harder 4b/4c sweep rather than a fourth cold loop. Both CRITICALs were contradictions loop 2 introduced. (a) Loop 2 wrote "leave the existing step-0 seeding exactly as it is today" against §3 decision 5's "leave the combo unselected" — and settling it surfaced that **"nothing pre-selected" was never implementable**: `_target_account_id()` is typed `-> int` and returns `_confirm_account_combo.currentData()` (verified against source), which is `None` on an unselected combo, and `preview_result` takes `account_id: int`. Settled as: no outcome ever clears the combo; only `matched` changes it. (b) Loop 2's masked-number rule routed to `no_number`, which made loop 2's own §4.6 blank-prefill rule and INV-9's second clause **unreachable** — creation is offered only from `no_match`. Removed the unreachable branch rather than routing around it. Also verified this loop and previously only assumed: `_target_account_id()`'s source combo, `ImportPreview.account_id`'s existence, and `ImportService.retarget`'s signature — all three underpin INV-7a. Mechanical: §7's table had been split in two by an interposed paragraph (3 of 4 rows rendering as literal pipes); the ladder's `1a.` was not a valid ordered-list marker; §7's Locks column omitted INV-7a and INV-9. |
| 2 | 2026-08-06 | 3 | 3 | 6 | 5 | 10 | 24 verified, all fixed; 1 dismissed (TOC — 0 of 3 siblings at 946–1594 lines carry one, so it is project convention). Dimensions: dim 4×6, dim 5×5, dim 2×4, dim 7×3, dim 6×3, dim 15×2, dim 11×1, dim 1×1, dim 10×1. Origin split: **2 draft defects, 9 collateral** — most of this loop answered loop 1's own fixes. **The decisive finding was a draft defect all 3 lanes found independently: §4.5 seeded the matched account into `_confirm_account_combo` under a `QSignalBlocker` AFTER the preview was built.** Verified against source — the blocker suppresses `currentIndexChanged`, which is wired to `_on_confirm_account_changed`, the only caller of `ImportService.retarget`; so the combo would display the matched account while `self._preview` stayed pointed at the old one, and `commit_import` persists `self._preview`. That is a wrong-account **commit**, introduced by this spec's own UI design. Fixed by specifying the order as a numbered sequence (match → seed → preview) with the reasoning inline, plus INV-7a. Second CRITICAL, verified by running it: `normalise_account_number("xxxx1234")` returns `"1234"`, so a masked id could match a real account numbered 1234 — §3 decision 3's deferral was enforced nowhere. Fixed with a new ladder rule (numbered 1a at the time; renumbered to rule 2 in loop 3) + INV-9. Third: §4.4's `normalised` comment and §4.6's as-printed rule gave opposite instructions for a persisted value (loop-1 collateral). |
| 1 | 2026-08-06 | 3 | 3 | 5 | 6 | 7 | 21 verified, all fixed; 2 dismissed unverified. Dimensions: dim 2×6, dim 6×4, dim 7×3, dim 4×3, dim 5×2, dim 10×1, dim 15×1, dim 9×1. **The three CRITICALs were the doc leaking the user's real account numbers into a PUBLIC repo against its own INV-8 (all 3 lanes, independently), INV-2 prescribing a real number as a committed fixture, and §4.6's name/type prefill having no transport through §4.1's one-field seam.** Fixes: every number replaced with a synthetic stand-in preserving the §2.3 collision; the seam widened to a `SourceAccountHint` value object; INV-8 rewritten to bind prose and given a real test (`gitleaks` cannot see a bare digit run). Two lane CRITICALs were **refuted by running them** — the claim that `_table_region(...).start` yields an empty header block and the feature never fires is false: measured 34/34 A/B/D files with the label above the boundary (margin 1–10 lines). Its residue was real and fixed (the reliability claim had been measured with a first-N-lines probe, not the specified boundary). One prescribed regex was executed before landing (4b-x): the greedy `[\d\s-]*` merges a following numeric column, the specified `[ -]?` form does not, with zero difference across all 34 files → new INV-2a. |
