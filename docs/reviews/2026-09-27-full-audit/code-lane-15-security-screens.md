**Lane 15 — the security-sensitive screens (unlock, recovery code, first run, password dialogs, hint, settings).** I read all 8 subject files in full from disk. Line counts as read:

| File | Lines |
|---|---|
| `ui/unlock.py` | 600 |
| `ui/recovery_key.py` | 560 |
| `ui/first_run.py` | 260 |
| `ui/password_dialog.py` | 75 |
| `ui/_password_hint.py` | 191 |
| `ui/set_hint.py` | 116 |
| `ui/_unlock_throttle.py` | 79 |
| `ui/settings.py` | 324 |

**What I held on arrival, before reading anything:** the global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, finbreak's `CLAUDE.md` (including the module-map note on the key envelope), the finbreak `MEMORY.md` index, and a git snapshot (HEAD 52e5162, clean). The shared context was read once, as instructed.

**How the lane ran:**
- `workspace_search` hit a rate limit mid-run. I used `Grep` from then on, and every search that touched the tree kept the `tests/**` exclusion. No test file was opened.
- One disagreement with the brief, resolved in the brief's favour: I read contract docs by line range rather than whole, because they are 20–100 KB each.

**Contract reads:**
- FIBR-0019: §3, §4.3, §4.5–§6.
- security-model: §5 in full, plus the T13 row.
- FIBR-0029: §3.2–§4.
- FIBR-0095: schedule, persistence, D1–D7, invariants.
- FIBR-0054, FIBR-0105, FIBR-0083: the invariant tables.
- FIBR-0030 and FIBR-0051: **not read** (the batched read spilled). See Info.
- Cross-references: `services/recovery_code.py`, `ui/_clipboard.py`, `ui/_worker.py`, parts of `services/auth.py`, `services/unlock_throttle.py:52-68`, and `main_window.py` lines 700-790 and 1240-1385.

## Critical (0)

## High (0)

## Medium (7)

- **[dim 9] `recovery_key.py:167-203`** — `"finbreak-recovery-code.txt"` with `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)`
  - The Save affordance runs *before* Keep or Decline, and it always suggests the same file name.
  - On Settings **Replace** and on the D5 post-recovery offer, the user can save over the file that holds their live code, then press "Keep my existing recovery code". The old code stays live, but its only saved copy has been overwritten with a code no slot opens.
  - First run has the same problem: Save then Decline leaves a file holding a code that opens nothing.
  - The write is also not atomic (truncate, then write), which breaches qt.md's `QSaveFile` idiom.
  - Fix: suggest a date-stamped file name. On a Decline after a Save, warn that the saved file holds a code that will not work. Write through temp-plus-rename.

- **[dim 3] `recovery_key.py:115-117`** — `self._display = QLineEdit(code)` / `setReadOnly(True)`
  - A read-only `QLineEdit` in Normal echo still allows mouse-select + Ctrl+C and context-menu Copy. Both go to the system clipboard through Qt's own copy, never through `ClipboardAutoClear`.
  - On X11, a mouse selection also fills the PRIMARY selection, which nothing clears.
  - security-model T13 says of the recovery code that it "IS auto-cleared". It lists the Normal-echo Ctrl+C bypass only for account numbers, as a deliberate gap.
  - The code is wrong, not the doc. This is the most sensitive value the app copies (A8).
  - Fix: set `Qt.ContextMenuPolicy.NoContextMenu` and `setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)` on the display, or route its copy through the guard. Otherwise T13 must list this bypass as a residual.

- **[dim 4] `unlock.py:433-470`** — `unlocked = self._service.complete_unlock(raw)` with arms for `RollbackAvailableError`, `VaultStateError`, `SchemaVersionError` and `OSError` only.
  - The recovery-route copy of this ladder (`:400-407`) guards `KdfPolicyError` with the comment "letting it out of a Qt slot is the crash class FIBR-0065 exists to stop". The password route has no such arm.
  - `complete_unlock` does raise it. At `auth.py:583-589`, after a failed `migrate_to_v2`, the `sidecar_version` probe re-raises on a sidecar left unreadable. `_unlock_through_slot` → `validate_slot` also raises it if the file changes between calls.
  - The exception escapes the slot with the dialog still showing, and no message.
  - Fix: add a `KdfPolicyError` arm with the same "security-settings file" message `_on_unlock` uses.

- **[dim 7] `unlock.py:523-540`** — `def _on_failure(self, _exc: object) -> None: ... self._show_failure()`
  - Any `DeriveWorker` exception is discarded unlogged, charged to the throttle, and shown as "Check your password" (or "your recovery code"). `_worker.py:29` catches every `Exception`.
  - A `MemoryError` on the 46 MiB allocation would land here. So would argon2's `HashingError` for params it cannot run: `validate_params` has no ceiling on parallelism, which `_password_hint.py:153-158` handles explicitly.
  - That is the "correct password told to re-check it forever" outcome the `KdfPolicyError` comment at `:285-290` exists to prevent. It also contradicts security-model INV-3d: a damaged record must not be charged to the throttle.
  - Fix: log the exception. Treat a non-credential derivation error as a distinct message, without calling `record_failure`.

- **[dim 16] `_unlock_throttle.py:59-63`, via `services/unlock_throttle.py:67-68`** — `elapsed = (now - last_fail).total_seconds()` / `return max(0.0, delay - elapsed)`
  - A `last_fail` stamped while the clock ran ahead makes the wait `30 s + skew`, with no cap. A common cause is a dual-boot machine whose hardware clock is in local time, corrected by NTP after boot. A 2-hour skew means a 2-hour lockout of the owner.
  - FIBR-0095 INV-3 mandates this (`now < last_fail → result > delay(n)`). security-model INV-10 promises "The delay is capped … never permanently locked out".
  - The two documents disagree, and I cannot tell which side is wrong; see Open questions.
  - Fix: clamp the result to `delay(n)` (treat a future `last_fail` as `now`). An attacker who can write the file can reset it anyway (FIBR-0095 D5).

- **[dim 16] `first_run.py:225-244`** — `except Exception as exc: ... "Could not create the vault: {error}"`
  - The `try` covers `complete_first_run` *and* the two prefs writes after it.
  - If `set_datetime_prefs` or `set_amount_prefs` fails (disk full), the vault already exists, is unlocked and has its idle timer armed. Yet:
    - the user is told creation failed;
    - the recovery code (`code`) is dropped without ever being shown;
    - `completed` never fires.
  - A retry then fails with "cannot first-run over an existing vault" (`auth.py:282-283`), so the dialog cannot be completed.
  - FIBR-0083 INV-8 says "A cancelled/failed first-run creates no vault".
  - Fix: split the `try`. On a prefs failure after creation, warn and still emit `recovery_code_ready` and `completed`.

- **[dim 4] `first_run.py:179-180`** — `@Slot()` on `def _update_strength(self, text: str)`, connected to `textChanged(str)`.
  - The identical method at `recovery_key.py:321` carries no decorator.
  - As I understand PySide6, a `@Slot()` with no arguments is invoked with zero arguments. That would raise `TypeError` on every keystroke, and the advisory strength label (T2) would never update on first run.
  - **Not run — needs a check:** type into `FirstRunDialog._password` and read `_strength.text()`.
  - Fix: `@Slot(str)`, or drop the decorator as in `recovery_key.py`.

## Low / Info

- **[dim 3] `unlock.py:217`** — `self._hint_label = QLabel(hint)` uses the default `AutoText`, so a hint containing tags renders as rich text on the pre-unlock screen. `window.ini` is plaintext and conceded attacker-writable (FIBR-0095 "The schedule"). The sibling strength labels set `PlainText`. Fix: `setTextFormat(Qt.TextFormat.PlainText)`.
- **[dim 13] English-only text shown to the user:**
  - `first_run.py:196` — `self._error.setText(str(exc))` shows `validate_first_run`'s English `ValueError` text ("passwords do not match").
  - `first_run.py:242`, `recovery_key.py:350` and `recovery_key.py:389` interpolate raw exception text into `tr()` strings.
  - All of it bypasses the i18n commitment in design.md. Fix: map known errors to `tr()` literals.
- **[dim 7] `settings.py:318`** — `except VaultLockedError:` is the only arm, so a SQLite write error from `set_*` escapes the Save slot. Fix: catch the storage error and show it.
- **[dim 7] `recovery_key.py:197-201`** — a failed `fchmod` is passed over silently. It is commented, but the user is not told the file may be readable by other accounts. Fix: warn on failure.
- **INFO:** FIBR-0030 and FIBR-0051 were not read beyond their outlines. The start-over affordance and the dialog-posture invariants were checked only against what the code comments cite.
- **INFO:** FIBR-0054 INV-7 names Windows as "un-wired", while `settings.py:170` names "the Windows build" as supported. This is doc drift, not a code finding.
- **Dim 2b:** nothing found. `recovery_unlocked`, `NewMasterPasswordDialog`, `build_add_or_replace_offer`, `remove_recovery_key`, `validate_hint_with_recovery` and `recovery_code_ready` all have live callers in `main_window.py`. `unlock_failed` has no consumer, and its comment says that is deliberate.
- **Dimensions with nothing found:** dim 5 (no findings), dim 8, dim 10, dim 11, dim 15 and dim 17. Dim 12 is N/A.

## Covered by spec and looks correct

- **Recovery route (`unlock.py:330-392`):**
  - It uses `normalise` → `verify_check_symbol` → `decode(normalised)`, so Argon2id gets the decoded 17 bytes and never the text. The Crockford trap is handled.
  - A typo is not counted as an attempt (§4.6 step 1).
  - A damaged slot is not charged to the throttle (§6 row 2).
  - It shares the throttle gate (INV-10).
- **Recovery offer (`build_recovery_offer`):** the guard is owned by the window, retired on destroy, and a "Never" setting is overridden to the default (T13).
- **`NewMasterPasswordDialog`:** cannot be dismissed (D6), confirms before writing (INV-9), and wipes its buffer.
- **`_code_candidates` / `validate_hint_with_recovery`:** match security-model INV-11 — reassembly, no check-symbol filter, fail-open with a log that never includes the hint, `validate_slot` called before derivation.
- **`_unlock_throttle.load`:** meets FIBR-0095 D5 (naive datetimes rejected, exponent clamped).
- **Hint display:** read once, display-only (FIBR-0029 INV-1/3/9).
- **`password_dialog.py`:** Password echo, remember-checkbox unchecked by default.

## Open questions

- **Clock skew:** should FIBR-0095 INV-3 (an uncapped longer wait when the clock moves back) or security-model INV-10 ("capped") govern? Whichever is wrong needs `review-contract`.
- **Recovery-code entry field (`unlock.py:193`):** it echoes Normal, while the password field is masked. No contract I read addresses whether the recovery code should be masked.
- **Hint scan on the GUI thread:** `validate_hint_with_recovery` runs up to about 74 Argon2id derivations for an all-caps 100-character hint, synchronously (`main_window.py:1365`). INV-11 says "uncapped", but `_worker.py` cites design.md "Concurrency" as keeping derivation off the GUI thread. I did not read design.md, so I cannot tell whether this is a breach.
- **The `@Slot()` finding** above needs running before it is acted on.

## 3 items to fix first

1. **Save-then-decline overwrites the live code's file** (`recovery_key.py:167`). This silently loses the user's only working copy of a vault-opening credential, on exactly the Replace and D5 paths meant for someone who already fears an exposure.
2. **The missing `KdfPolicyError` arm on the password route** (`unlock.py:433`). An unhandled exception on the only route into the vault, reachable after an interrupted migration — the state users are most likely to be in after an update.
3. **Derivation failures reported as a wrong password and throttled** (`unlock.py:523`). A user with the correct password is told to re-check it forever, with an escalating lockout and nothing in the log to diagnose it.