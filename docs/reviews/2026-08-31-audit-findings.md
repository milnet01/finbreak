# Whole-tree audit, 2026-08-31 — finding record

`check-code --tree` plus a 15-lane `review-code` sweep. This file exists so
FIBR-0327 and FIBR-0328 point at the findings themselves rather than at a
session transcript.

**Status:** what was fixed is in `CHANGELOG.md` under FIBR-0318 and in the git
history. What is open is below. Severities are the lanes' raw grades; where the
threat-model calibration moved one, both are shown.

**Method note.** Lanes ran without shell access, so every claim is from reading.
Each finding fixed under FIBR-0318 was re-verified against source first, and
several claims were executed. The unfixed ones below are **verified as written
by the lane, not re-confirmed against source** unless noted — check before
acting, as `close-findings` requires.

`.ants_review_falsepos.jsonl` holds the classes already dismissed. Do not
re-litigate those.

---

## Open HIGH — each has its own roadmap item

| Finding | Item |
|---|---|
| Batch mapping ladder never fires for files 2..N | FIBR-0319 |
| Linux relaunch waits on the PyInstaller child, not the bootloader | FIBR-0320 |
| Remembered PDF password written to the provisional account | FIBR-0321 |
| Parallel row lists keep cleartext account numbers past lock | FIBR-0322 |

---

## MEDIUM (FIBR-0327)

### crypto, vault and migration

- **`crypto.py` `validate_params` bounds only the low side.** `time_cost` and
  `parallelism` are unchecked and `memory_kib` has no ceiling. The restore path
  derives from an attacker-supplied `params.json`, so a hostile `.fbk` forces an
  unbounded Argon2 allocation pre-login, and `time_cost: 0` raises
  `argon2.HashingError` — in neither `restore_backup`'s nor `verify_backup`'s
  nor the UI's except tuple.
- **`migrations.py` bounds the embedded `schema_version` above but not below.**
  A crafted `.fbk` with `0`, a negative, or a TEXT value raises `KeyError` /
  `TypeError` out of a Qt slot on the pre-login surface.
- **`vault.py` `ATTACH DATABASE '{dest_db}'` interpolates the path unescaped.**
  An apostrophe in the user's home permanently breaks backup export *and* the v2
  migration at S1. Found independently by two lanes. `bandit` B608 does not
  match `ATTACH`.
- **`vault.py` `cipher_compatibility` is unvalidated on the FIBR-0019 callers.**
  The comment claims the caller allowlist-validates it; true of `backup.py`,
  false of `auth.py`'s two sites, which pass it straight from the plaintext
  sidecar. A one-byte edit turns an intact vault into "your vault is broken".
- **Migration commit points have no `_fsync_dir`.** The module defines the
  helper and uses it only on the rollback path. If S5's directory entry reaches
  stable storage and S4's does not, the user gets a v1 sidecar over a DEK-keyed
  database — reported as *wrong password* over an intact vault.
- **`crypto.py` `write_sidecar_json` fsyncs the file but not its parent** before
  `os.replace`, where four sibling sites do. A crash can silently revert a new
  master password or recovery key.
- **`backup.py` `SQLCIPHER_COMPAT` is both what is written and what is
  accepted.** Bumping it makes every `.fbk` already in the field unrestorable,
  at the moment the user needs it. Split into a written constant and an accepted
  set.
- **`auth.py` `complete_first_run` does not close the vault on failure**, though
  `Vault.create`'s own comment promises that coverage. A disk-full at the
  sidecar write leaves the service reporting locked while `Vault.connection`
  returns a live unlocked handle.

### money and reporting

- **Which clock defines "today" is undecided.** The reporting, alert and
  forecast services use `date.today()` (OS-local) while a user-pinnable timezone
  exists and is scoped to display only. At a month boundary this moves a whole
  month of totals. No document owns the question.
- **`transfer_detection` loads the entire transactions table on every
  `drill_down()`** — i.e. every Home refresh — to resolve a handful of ids.
- **`repositories/transfers.py` candidate self-join has no usable index.**
  Equality on `amount_minor` alone cannot use the composite index, and
  `julianday()` around `occurred_on` disables the date index. Quadratic in vault
  size, on a tab the user opens routinely.

### UI

- **`forecast.py`'s two labels do not set `PlainText`** and interpolate
  user-supplied account names. `month_summary.py` fixes exactly this, with the
  reasoning written down.
- **`transactions.py` date pickers are uninitialised**, so ticking "Date range"
  empties the table with no message.
- **`_amount.py` formats money through `float`.** `_MAX_AMOUNT_MINOR` exceeds
  float64's exact-integer range, so a large amount can render differently from
  what is stored.
- **`rules.py` is the only table that refills without `fill_guard`.** Deleting
  row 1 of 3 leaves row 1 selected, now showing a different rule, with Edit and
  Delete enabled against it.
- **`categories.py` `_refresh` does not re-run its gating slot**, relying on
  `QTreeWidget.clear()` emitting `currentItemChanged` — which the same file's
  own comment records as unreliable.
- **`_datetime_prefs.py` `_read_timezone`'s recovery branch is unreachable**, so
  a free-typed zone this host does not enumerate silently persists the
  *previously selected* zone while the field displays the typed one. A wrong
  zone is a wrong-day render.
- **`pdf_export.py` uses `calendar.month_name`**, bypassing both `_tr()` and
  `QLocale` in a module where every other string is translated.
- **Batch review's Account cell is mouse-only.** `cellClicked` is the only
  route and `NoEditTriggers` removes the keyboard one, so a keyboard-only user
  cannot complete a batch at all.
- **Batch picker's "nothing selected" sentinel is inert.** A row reading
  *— pick one —* opens a picker with the first account already chosen.
- **`file_label` is O(N) per row inside an O(N) refresh**, so a batch is cubic.
- **Import preview's Amount column bypasses the shared money formatter** — no
  locale grouping, no currency symbol, no negative-style preference — on the
  last screen before an irreversible commit.
- **Two unguarded vault reads remain in `import_wizard.py`**, where five sibling
  slots catch `VaultLockedError`.

### update and delivery

- **`update_installer.py` embeds `shlex.quote` output inside a double-quoted
  shell string.** Its single-quoted form terminates the `echo` early and
  swallows the `exec`: the app closes, the key is wiped, and it never reopens.
  Any `$APPIMAGE` path containing an apostrophe. Undetectable by testing the
  current build.
- **`single_instance.py`'s re-probe narrows but does not close the stale-socket
  race.** Two launches can both `removeServer`, the second unlinking the first
  winner's live socket — two writers on one SQLCipher file.
- **A truncated download is reported as a signature failure.** `download()`
  never compares received bytes against `Content-Length`, so a dropped
  connection raises the integrity alarm — misdiagnosing, and desensitising the
  user to the one alarm that matters.
- **`release-*.sh` upload is unguarded under `set -e`**, so on the exact 503 the
  read-back gate was written for, the gate never runs.
- **`release-linux.sh` demands a *pushed* bump and tests only that it is
  committed.** With no `--target`, the tag is created off the remote's pre-bump
  HEAD.
- **`.githooks/pre-push` runs the gate against the working tree**, not the
  commits being pushed, while its header claims a red commit cannot reach
  origin.
- **`FIBR-0096`'s claim that the per-artifact `.sig` is the primary integrity
  gate is false for a rename-replay** — the signature binds bytes only, not
  version, basename or platform.

### app shell

- **Detached workers may be garbage-collected while running.**
  `setParent(None)` returns ownership to Python and the next statement drops the
  only tracked reference; the C++ reasoning in the comment does not hold in
  PySide6.
- **The drain never `disconnect()`s**, so a download completing during shutdown
  can still reach `installer.apply()`.
- **An update-check exception is discarded with no record**, on a signal that
  fires only on a genuine bug, in a file that imports no logger.
- **The interrupted-restore `os.replace` is unguarded**, so a read-only
  directory makes the app unlaunchable with a traceback, on a path where the
  vault is mid-surgery.
- **`_selftest.py` has no `cryptography` check** — see FIBR-0326.
- **`app.py` has no top-level exception handler and no `sys.excepthook`**, so on
  a windowed Windows build any startup failure that is not `VaultStateError`
  produces an app that does nothing when double-clicked.
- **`app.py`'s only user-facing string is neither translated nor
  placeholder-substituted.**

---

## LOW / INFO (FIBR-0328)

Recorded as classes; the individual instances are recoverable by re-running the
sweep, and none loses data.

- **Stale comments and docstrings that assert something no longer true** — the
  largest class. Examples: `transfers.py` claiming no multi-statement unit
  exists after batch ops were added; `_replacement_is_sound`'s premise about S4
  having completed; `backup.py` citing INV-14 and INV-15, neither of which
  exists in FIBR-0014; `FIBR-0113`'s counter-example naming code that has since
  been fixed.
- **Raw ISO dates on surfaces the date preference does not reach** —
  `forecast.py`, `transfers.py`, `recurring.py`, `alerts_dialog.py`. FIBR-0083's
  deliverables name only two files, so no contract is breached.
- **Display strings assembled with `+` or f-strings**, against `coding.md`
  § 5.2 — a translator cannot reorder them. Several sites.
- **Missing accessible names** on the password, confirm and recovery-code
  fields, and on the custom date-format field.
- **Unreachable defensive branches** whose absence would be caught by a
  foreign-key constraint or an enum bound.
- **Error paths collapsing two distinguishable causes into one message** — e.g.
  `has_recovery_key` returning False for both "no key" and "damaged sidecar".
- **Unicode input surfaces**: `Decimal` accepts any Unicode `Nd` digit and PEP
  515 underscores; `\d` in the account-number matcher is Unicode-wide;
  `casefold()` without NFC lets two visually identical category names coexist.
- **Two `check-code` observations.** Tracked Python under `docs/reviews/` is
  outside the gate's `ruff check src tests` scope by design, and nothing records
  that decision. There is no `.yamllint` config, so the tool runs on defaults
  the project never adopted (80 columns against its own 88).
