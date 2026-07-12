# ADR-0006: Transfer detection is suggest-then-confirm, never auto-applied

- **Status:** Accepted
- **Date:** 2026-06-30
- **Deciders:** Project lead, Claude
- **Related:** [docs/discovery.md](../discovery.md) (success criterion 3)

## Context

A user holds several accounts (current, savings, credit card, loans,
investment). Money moved *between their own accounts* — a credit-card payment,
a transfer to savings — is not income or expenditure; counting it as such would
inflate both totals (e.g. a R5 000 card payment shows as R5 000 "spent"). So
internal movement must be recognised and excluded from the breakdown.

Detection works by matching a debit in one account against a credit in another
for the same amount within a short date window. But this match is a **heuristic**:
two unrelated transactions can coincidentally pair (same amount, near date), and
a real expense could be wrongly hidden if auto-classified.

Options:

- **Auto-classify matches as transfers** — convenient, but can silently hide a
  genuine expense, corrupting the very numbers the app exists to get right.
- **Suggest matches and let the user confirm/reject** — mirrors the
  auto-categorisation pattern the user already chose (auto-rules + manual
  override); the user stays in control of money that "disappears" from the
  breakdown.

## Decision

Transfer detection **proposes** candidate pairs; the user **confirms or rejects**
each. Only confirmed pairs are linked as transfers and excluded from
income/expenditure totals. Nothing is auto-hidden.

## Consequences

**Positive:**

- No real expense is ever silently removed from the breakdown.
- Consistent mental model with auto-categorisation: the app suggests, the user
  decides.

**Negative:**

- A confirmation step for each suggested pair (mitigated by batch-confirm and by
  remembering rejected pairs so they don't re-surface).

**Neutral:**

- The matching tolerance (date window, amount exactness) is tunable and recorded
  in the transfer-detection spec; tightening it trades recall for precision.
- **As implemented (FIBR-0011):** the date window is the tunable
  `TRANSFER_WINDOW_DAYS` (= 3 days); amount matching ships **exact-magnitude only**,
  with a fee/near-amount tolerance deferred as a clean future follow-up.
