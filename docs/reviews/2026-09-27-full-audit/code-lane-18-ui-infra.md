**Subject line counts as read (lane 18):** `ui/_amount.py` 255 · `ui/theme.py` 495 · `ui/_table_state.py` 257 · `ui/_datetime_prefs.py` 140 · `ui/icons.py` 129 · `ui/_widgets.py` 118 · `ui/modal.py` 35. All under `/mnt/Games/Scripts/Linux/finbreak/src/finbreak/`.

**Already in my context when I arrived:**
- `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md` and the finbreak project `CLAUDE.md`.
- The finbreak memory index (MEMORY.md).
- A git snapshot at HEAD 52e5162, clean tree, with recent FIBR-0331 commits.
- Then the shared-context packet.

I opened no test files. Every search either ran with `lane:"src"` or targeted `docs/`.

**Contract actually read:**
- FIBR-0127: invariants and design decisions (L55–250).
- FIBR-0153: §3–§4 (L56–220).
- FIBR-0083: invariants and D1–D7 (L63–213).
- FIBR-0139: D7 (L240–264).
- ADR-0010: Decision and Consequences.
- design.md: Error handling through i18n (L232–329).

**Two departures from the brief's list:**
- I also read FIBR-0219 §4 (L204–512). It is not in my lane-contract list, but `_amount.py` cites it as the contract for `parse_amount_input`, and dimension 2 needs it.
- I read nothing of FIBR-0095 or FIBR-0032 beyond search headlines. Both cite these modules only as patterns (the QSettings adapter, `select_combo_data`, `selected_index`) and add no obligations I could find.

## Critical (0)

## High (0)

## Medium (2)

- **[dim 13] Arabic-locale amounts would mix two digit systems** — `_amount.py:81-82`
  - Offending lines: `grouped = locale.toString(int(whole)) if int(whole) <= _TOSTRING_MAX else whole` / `body = grouped + locale.decimalPoint() + frac if decimals else grouped`
  - The integer part goes through `QLocale.toString`. That uses the locale's own digits: FIBR-0219 §4.4 measured `ar_EG` `zeroDigit()` as U+0660 and `fa_IR` as U+06F0.
  - The fraction comes straight from `f"{value:.{decimals}f}"`, which is always ASCII.
  - So under `ar_EG` or `fa_IR` every `_format_amount` value would render with Arabic-Indic whole digits and ASCII cents, e.g. `R ١٬٢٣٤٫56`. That covers the Transactions table, Home tiles, PDF export and the refusal messages.
  - The old `toString(float, "f", d)` route rendered every digit through the locale. The FIBR-0327 exactness rewrite introduced the mix.
  - design.md § i18n says numbers are formatted through `QLocale`, and it lists Arabic in the initial catalog set.
  - Unexecuted. Needs: `QLocale.setDefault(QLocale("ar_EG")); _format_amount(Decimal("1234.56"), "ZAR")`.
  - Fix: when `locale.zeroDigit() != "0"`, map `frac`'s ASCII digits onto the locale's zero digit. A `str.maketrans` from `"0123456789"` would do it.

- **[dim 7] A mistyped timezone is silently saved as "system"** — `_datetime_prefs.py:125-127`
  - Offending lines: `if QTimeZone(typed.encode()).isValid(): return typed` / `return DATETIME_SYSTEM`
  - Scenario: a user with a pinned zone edits the editable timezone field into text that names no zone. Examples are a stray character, or wrong case such as `africa/johannesburg` (IANA ids are case-sensitive to `QTimeZone`).
  - Any later Save quietly persists `"system"`, because `_on_save` writes all prefs.
  - That repoints every timestamp at the machine's zone. This is the same wrong-day class the comment at L71-76 exists to prevent, and nothing tells the user.
  - design.md § Error handling says: "errors surface to the user; nothing is silently swallowed."
  - Unexecuted. The completer may or may not auto-correct case on focus-out.
  - Fix: return a sentinel or raise on invalid text, and have the dialog show an error and refuse to Save. At minimum, keep the previously selected item's data rather than switching to system.

## Low / Info

- **[dim 2] Doc-side: FIBR-0153 and FIBR-0219 still describe the float route.** Code at `_amount.py:112` (`magnitude = _grouped(abs(display), decimals)`) and `:254` renders exactly, with no float. The docs still say otherwise:
  - FIBR-0153 §3.2 step 2 (L83), "The `float()` stays a display-only bounded conversion" (L107), and INV-3 citing `_amount.py:37`.
  - FIBR-0219 §4.2 L276-277 (`_format_amount` "renders `QLocale().toString(float(abs(display)), …)`") and §4.5 L467-478 (the refusal readings use `toString(float(value), "f", n)`).
  - The document is wrong and the code is right. This is for `review-contract`.
- **[dim 2] Doc-side: FIBR-0127 disagrees with itself and with the code on theme tokens.**
  - INV-4's mapping still reads `Link`←`accent_soft`. INV-4b and `theme.py:266` (`palette.setColor(role.Link, tokens.accent)`) say `accent`.
  - INV-3 lists eight colour tokens, but `theme.py:47` adds a ninth, `attention`.
  - Code-side comment drift too: `theme.py:3` says "eight semantic colour **tokens**" while `ThemeTokens`' docstring (L32) says "nine".
  - The document is wrong. The comment at L3 is a one-word code fix.
- **[dim 13] The ambiguity refusal is untranslated English built with an f-string** — `_amount.py:239-243` (`f'amount is ambiguous: "{text}" reads as {_render(grouped)} (grouped) or '`).
  - This contradicts design.md § i18n: "every user-facing string goes through tr()… never assembled by f-string".
  - FIBR-0219 §4.5 L484-487 explicitly defers translation of parser messages.
  - The two documents conflict. See Open questions.
- **[dim 11] Very long typed amounts produce a Python-internal error message** — `_amount.py:81`, `int(whole)`, on unbounded typed input.
  - Python 3.12 caps int-from-string conversion at 4300 digits. A typed amount longer than that, reaching `_render` through the step-3 shape guard, raises `ValueError("Exceeds the limit (4300 digits)…")`.
  - Example: a 5000-digit `…​.500` under `de_DE`, where only the C reading survives.
  - `_on_add` catches `ValueError`, so there is no crash, but it shows an interpreter message to the user.
  - Unexecuted. It depends on whether `toDouble` rejects on overflow.
  - Fix: cap the input length in `parse_amount_input` before either parse.
- **Dimensions with nothing found:**
  - **dim 2b:** every promised entry point has at least one non-definition caller in `src/`. Examples: `parse_amount_input` 1, `polish_item_views` 1, `reset_columns` 1, `show_modal` 10 call sites.
  - **dim 3:** both INI reads are type-guarded (`theme.py:182`, `_table_state.py:207`).
  - **dim 4:** `_settings()` in `theme.py:172` and `_table_state.py:169` are identical and have not diverged.
  - **dim 5:** N/A. `_save`'s per-resize `sync()` is merely slow.
  - **dim 8:** nothing found.
  - **dim 9:** nothing found.
  - **dim 10:** N/A, nothing logged here.
  - **dim 12:** N/A, no standard named.
  - **dim 15:** nothing found.
  - **dim 16:** an unwritable INI is sanctioned best-effort (FIBR-0127 D4).
  - **dim 17:** unknown theme id, stale header blob and renamed tz ids are all handled.

## Covered by spec and looks correct

- **`theme.py`** matches FIBR-0127:
  - INV-2: the guarded load.
  - INV-4: role mapping, with `HighlightedText` chosen by WCAG contrast ratio.
  - INV-5 and INV-11: token hex appears verbatim in the stylesheet, plus `polish_item_views`.
  - INV-6: Fusion, then palette, then stylesheet, then emit.
  - INV-7 and D3/D5: unknown id normalises the mode to "system", `Unknown` resolves to dark, and the slot keeps the mode.
- **`parse_amount_input`, `_locale_decimal` and `_guard_operand`** match FIBR-0219 §4.2–4.5:
  - Non-finite values dropped, then the agree/refuse table, then the shape guard only when one reading survives.
  - R2 runs before R3.
  - Signs replaced string-wise.
  - `InvalidOperation` is caught.
  - The operand strips the locale's group separator only when it is neither `.` nor `,`.
  - `_SPACES` really does hold U+0020, U+00A0 and U+202F (confirmed by regex).
- **`_format_amount`** matches FIBR-0153 INV-1/2/4/5.
- **`_datetime_prefs.py`** populate and `_read_token` match FIBR-0083 D4/D5, apart from the Medium above.
- **`SortableItem.__lt__`** matches FIBR-0139 D7's "only when both carry a key" semantics.
- **`modal.py`** matches its FIBR-0065 docstring.

## Open questions

1. design.md § i18n and FIBR-0219 §9 decision 3 disagree on whether parser refusals must go through `tr()`. I cannot tell which document governs.
2. Numbers use `QLocale()` (`_amount.py:77`), while the "system" date/time samples use `QLocale.system()` (`_datetime_prefs.py:33,38`, as FIBR-0083 D4 specifies). If the FIBR-0017 language picker calls `QLocale.setDefault`, numbers and dates will follow different locales. Is that intended?
3. `remember_columns` keys on `f"columns/{view.objectName()}"` (`_table_state.py:200`) with no guard against an empty objectName. Two unnamed views would share one layout. I did not check that every one of the 10 callers sets a name.
4. `toolbar_icon` pre-renders fixed pixel sizes 16/24/32/48 (`icons.py:60,93`) with no `devicePixelRatio`. At 200% scaling a 32-px icon upscales from 48 px. That may be blurry on Windows or macOS HiDPI, where portability is in scope. Unverified.

## 3 items to fix first

1. **The mixed digits in `_grouped`.** Every money string on screen and in PDFs is affected under a planned shipped locale (Arabic).
2. **`_read_timezone` degrading silently to "system".** It is a wrong-day render from a silent pref change, which is the class this project ranks worst.
3. **Amending FIBR-0153 and FIBR-0219 to describe the float-free `_grouped` route** (via `review-contract`). Both specs currently tell an implementer to use the float path that FIBR-0327 removed as lossy.