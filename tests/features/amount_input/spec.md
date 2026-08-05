# tests/features/amount_input — FIBR-0219 locale-aware amount input

Conformance tests for [`docs/specs/FIBR-0219.md`](../../../docs/specs/FIBR-0219.md):
the manual-entry Amount field accepts the **numeric part** of the amount the app
itself just displayed, under the user's own locale, and **refuses** — visibly,
naming both readings — any input two conventions read as two different numbers.
A refusal costs a retype; a wrong guess costs a factor of 100 or 1000 on
somebody's money.

Every leg pins the **default** `QLocale` (`QLocale.setDefault`, restored in a
`finally`) because `ui/_amount.py` reads `QLocale()` and not `QLocale.system()` —
so the suite is hermetic on any runner. Vaults live under `tmp_path`; the CSV and
OFX fixtures are tiny in-repo strings and the PDF fixture is the synthetic one
the `standard_bank_pdf` suite ships. No network, no real financial data
(testing.md § 6).

## Coverage

| INV | What it pins |
|-----|--------------|
| INV-1 | `parse_transaction` stays **C-locale only** and no importer's result depends on the desktop locale: CSV, OFX and a Standard Bank PDF import identically under `C` and `de_DE`. The CSV fixture carries a **discriminating** row (`1.234,56` — rejected by C, read as 1234.56 by `de_DE`) so the leg can tell a moved locale layer from an unmoved one. |
| INV-2 | Every string `_format_amount`'s **magnitude** can produce round-trips: 5 locales × 5 values, fed back through `parse_amount_input`, returns `abs(value)` exactly. Anchored on the shipping `_format_amount`, never a re-render of its `toString` line. |
| INV-3 | The C form (`-12.34`, `1234.56`) is accepted under every locale — the invariant that keeps FIBR-0216's `-12.34` placeholder honest. |
| INV-4 | When both conventions parse and **disagree**, the input is refused and the message names both readings, labelled `(grouped)` / `(decimal)`. Two `qtbot` legs: an ambiguous input shows an error and stores nothing; `-12,34` under `de_DE` **stores `amount_minor == -1234`** — the only leg that fails if `parse_amount_input` is never wired into `_on_add`. |
| INV-5 | Group separators are removed **before** the decimal point is swapped. Three `de_DE` values; the wrong order makes each 100× too large, silently. |
| INV-6 | The result is an exact `Decimal` rebuilt from the input string, never Qt's `toDouble` float. |
| INV-7 | The measured `QLocale` matrix (spec § 2.1 / § 2.2) is asserted, not merely recorded — so a PySide6 upgrade that changes group-placement **strictness** lands as a red suite rather than a silent money-parsing change. |
| INV-8 | The shape guard: an input matching `^[+-]?\d+(?:[.,]\d+)*[.,]\d{3}$` is refused when only one convention yields a candidate. Four groups — locale-candidate branch, C-candidate branch, grouped-head, and the bounds from the other side (no `_format_amount` magnitude matches; `en_US` `1.500` is still accepted; the `en_ZA` message names both readings). |
| INV-9 | `parse_amount_input` raises **only** `ValueError`. Two tables — must-raise (`""`, `"-"`, `"nan"`, `"inf"`, `"."`, `","`) and must-return (`1_000`, a 400-digit string) — plus the two typed-U+2212 sign legs, which cover different locales and different mechanisms. |

## Out of scope

A pasted currency symbol (`R 1 234,56`) and the bracketed negative `(R 12,34)`
are refused before and after FIBR-0219 (spec § 9 decisions 2 and 6) — no leg
types either. Non-ASCII digit entry (`ar_EG`, `fa_IR`) round-trips incidentally
and is deliberately unpinned: pinning it would promise it (spec § 9 decision 5).
