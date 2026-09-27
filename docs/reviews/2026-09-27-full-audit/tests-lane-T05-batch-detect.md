## Chunk T05: 9 files read

**Line counts as read:**

| File | Lines |
|---|---|
| batch_import/test_batch_import.py | 1054 |
| batch_import/test_batch_import_ui.py | 1037 |
| account_detect/test_no_real_data.py | 234 |
| account_detect/test_match.py | 169 |
| account_detect/test_extract.py | 234 |
| account_detect/test_wizard.py | 432 |
| import_date_detect/test_import_date_detect.py | 870 |
| import_back_step/test_import_back_step.py | 193 |
| import_column_detect/test_import_column_detect.py | 292 |

None of these directories has a conftest.py.

**Already in my context before I read anything:**
- `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md` and the finbreak `CLAUDE.md`.
- The finbreak memory index, which includes the qtbot isHidden and waitUntil-proxy entries.
- A git snapshot: clean `main` at 52e5162.

I read every test file from disk. Beyond the tests, I read only these one-hop pieces of `src/finbreak`:
- `ui/import_batch.py`: `file_labels`, lines 160–175 and lines 225–245.
- A search for how `ui/import_wizard.py` imports `datetime`, where it calls `_autodetect_date_format` and where it enables its buttons.
- The same `datetime` import search on `importers/date_detect.py`.

No account number and nothing from `.corpus-numbers` appears below.

### Findings

**[HIGH] [dim 1] tests/features/account_detect/test_no_real_data.py:168**
> for run in _DIGIT_RUN.findall(text):
(runs to :171: `if normalise_account_number(run) in keys:`)

Consequence: the separator class allows up to 4 separator characters between digits (`[\s .\-‐-―]{0,4}`, line 81). So a real number followed or preceded by any other digits within 4 spaces becomes one longer run. The check is exact set membership, so that longer run never equals a key and the leak passes. The obvious case is a statement header line pasted into prose: the number, then a date column 2–4 spaces away. That shape is written in this chunk's own fixture at `test_extract.py:153`. The guard-the-guard test (line 111) covers six spellings of an isolated number and none next to other digits, so nothing catches this.
Fix: match a key as a substring of the normalised run (`any(k in norm for k in keys)`), and add an "adjacent to a date column" spelling to the parametrised guard-the-guard test.

**[HIGH] [dim 5] tests/features/batch_import/test_batch_import_ui.py:546**
> qtbot.wait(300)

Consequence: the lines after it make positive completion claims: `indices == [0, 1, 2]`, every file `committed`, and 6 rows in the vault. Those need three chained `singleShot(0)` run turns, each doing a SQLCipher commit, to finish inside a fixed 300 ms. On a loaded CI runner the chain can still be mid-run, and the test goes red with no defect. This is the same failure class the project already met in INV-14(a) (CI run 31622538238).
Fix: `waitUntil` on the finished state (`_batch_phase == "report"`, or all records committed) and then assert `indices`. A short fixed wait is still fine for the "no second chain" check.

**[MEDIUM] [dim 5] tests/features/batch_import/test_batch_import_ui.py:717**
> qtbot.wait(200)

(also line 756: `qtbot.wait(100)`)

Consequence: after these fixed waits the test asserts positive states. In leg (b) those are `_close_button.isVisible()` and `any(... == "not_attempted")`, lines 722 and 725. In leg (c) it is `any(... == "skipped")`, line 760. Whenever those states are reached through a queued turn rather than inside the click, a slow runner fails the leg with no defect present.
Fix: `waitUntil` on the asserted state itself, and keep fixed waits only for the negative "done never fired" checks.

**[MEDIUM] [dim 1] tests/features/batch_import/test_batch_import_ui.py:254**
> assert not widget2._batch_review._import_button.isEnabled(), (

Consequence: leg (b) of INV-3 has only this negative assertion. The button starts disabled (`import_batch.py:169`: `self._import_button.setEnabled(False)`). The wait before it (line 246) is on a record's outcome, which is a proxy, not on the review having been redrawn. If the redraw that recomputes `can_import` (`import_batch.py:237`) runs after that poll, the assertion reads the initial disabled state. It would then pass even against the break the docstring names ("gated on at least one ready"). Leg (a) avoids this by also asserting `BatchImportService.can_import(files)` directly; leg (b) does not.
Fix: add `assert not BatchImportService.can_import(files2)` as leg (a) does, or wait on the review phase rather than on an outcome.

**[MEDIUM] [dim 1] tests/features/account_detect/test_no_real_data.py:166**
> except (UnicodeDecodeError, OSError):

Consequence: any tracked text file that is not valid UTF-8 is skipped whole, with no report. A bank CSV or OFX saved as cp1252 is an example; this chunk's own OFX headers declare `CHARSET:1252`. A real number in such a file passes the leak guard. Digits are ASCII in every encoding involved, so the skip gains nothing.
Fix: decode with `errors="replace"` (or scan the raw bytes with a bytes pattern), and skip only on `OSError`.

**[MEDIUM] [dim 1] tests/features/import_date_detect/test_import_date_detect.py:194**
> monkeypatch.setattr(date_detect, "date", _NoClock, raising=False)

Consequence: `importers/date_detect.py` imports only `from datetime import datetime` (line 22). It has no `date` attribute, so `raising=False` quietly creates one that nothing reads. A detector that started reading the clock through `datetime.now()` or `datetime.today()` would not trip this "poison". Only the 1998 and 2099 legs guard INV-2, and only against a year window narrow enough to exclude those years. The docstring's "any call to date.today() inside the detector explodes" is not what the test does.
Fix: patch the name the module actually binds (`date_detect.datetime`, with a subclass whose `now` and `today` raise), and drop `raising=False` so a missing target fails loudly.

**[MEDIUM] [dim 1] tests/features/import_column_detect/test_import_column_detect.py:290**
> first = guess_columns(header)

(runs to :292: `assert first == second`)

Consequence: both calls use the same header order in the same process. String-hash randomisation is fixed for a whole process, so even a guesser that depends on set or hash order returns the same answer twice. The test cannot fail. The docstring also claims order-independence, which is never exercised because the order is never changed.
Fix: call it with a permuted header and assert each role still maps to the same original string. Or drop the order claim and the test.

**[MEDIUM] [dim 6] tests/features/import_date_detect/test_import_date_detect.py:799**
> src = Path("src/finbreak/ui/import_wizard.py").read_text(encoding="utf-8")

Consequence: the path is relative to the working directory, while every other file in this chunk resolves paths from `__file__`. Running the suite from anywhere but the repo root raises `FileNotFoundError`, for example `cd tests && pytest features/import_date_detect` or an IDE runner rooted at `tests/`.
Fix: resolve from `Path(__file__).resolve().parents[3]`.

**[LOW] [dim 1] tests/features/batch_import/test_batch_import_ui.py:937**
> def __iter__(self):

Consequence: the pass counter only sees Python-level iteration over `files`. A quadratic that walks a derived list escapes it. For example, one pass to build a list of names, then `names.count(n)` per row: that is one counted pass at 2 files and at 60. So the O(N²) the FIBR-0327 docstring guards against can come back in that form and stay green. The current code (`file_labels`, three `Counter`s) is linear, and the per-row re-tally shape it replaced *is* caught.
Fix: also assert a scaling bound (for example, count `BatchFile.path` attribute reads), or state in the docstring that only re-iteration of `files` is pinned.

**[LOW] [dim 1] tests/features/import_date_detect/test_import_date_detect.py:367**
> warnings.simplefilter("ignore", DeprecationWarning)

Consequence: this test (and the one at :333) asserts CPython's `strptime` behaviour, not finbreak's. The suppressed warning says that behaviour changes in 3.15. On that interpreter the test goes red, or passes for a different reason, while telling you nothing about the product.
Fix: keep it as a comment beside the rejection test, or mark it as a known Python-version-bound precondition.

### Pre-pass verdicts
- account_detect/test_no_real_data.py:208 (setenv_call, dim 6): **false positive.** `monkeypatch.setenv` is undone automatically at teardown. The value is synthetic, and the next test (:216) also runs `delenv` itself. Nothing leaks into `test_no_corpus_numbers_in_tree`.

### Dimensions scanned
- 1: 7 findings (2 HIGH-or-MEDIUM on the leak guard, INV-3(b) negative, clock poison, column-detect tautology, file_labels proxy, stdlib precondition).
- 4: settled by orchestrator. None of this chunk's files contradicts it.
- 5: 2 findings (fixed waits before positive asserts in `test_batch_import_ui.py`).
  - The negative-assertion waits at :412 and :799 are the right shape.
  - `test_INV14` (a) waits on the real state.
- 6: 1 finding (cwd-relative path). The pre-pass was a false positive.
  - Class-level monkeypatches (`ImportService.commit_import`, `BatchImportService.run_step` and `scan_step`) are all undone by `monkeypatch`.
  - See the open question on `test_wizard.py:402`.
- 7: clean. No RNG, no clock reads, and every comparison is ordered or sorted.
- 8: clean. The only skip (`test_no_real_data.py:152`) carries a reason and a live condition, and it ran in the baseline.
- 9: clean. No network, and only `tmp_path` vaults.
- 11: clean. No empty bodies.
- 12: N/A. No per-test timing supplied, and none of this chunk is in the slowest 20.
- 14: clean on its triggers. The two neutralised-check findings are filed under dim 1 because they are guard-scope defects, not suppressed assertions. The mocked layers (`commit_import`, `decrypt`, `StandardBankImporter`) are never the layer each test claims to exercise.
- 15: N/A. Nothing failing in this chunk.

### Noted, not mine
- None.

### Possibly wider
- Fixed `qtbot.wait(N)` followed by positive assertions probably appears in other widget suites that drive `singleShot(0)` chains.
- Tests reading source files by cwd-relative `Path("src/...")` may exist elsewhere (for example other tr()-wrapping checks).

### Open questions
- `account_detect/test_wizard.py:402`, `test_create_dialog_prefills_from_the_statement`: it builds a `CreateAccountDialog` with no `qtbot` or `qapp` fixture, and does not register the dialogs for cleanup. Whether it passes when run alone depends on a QApplication already existing, which could come from an earlier test or from an autouse fixture in `tests/conftest.py` (outside my bound). Unexecuted. Needs `pytest "tests/features/account_detect/test_wizard.py::test_create_dialog_prefills_from_the_statement"` run in isolation.
- The adjacency finding (the first HIGH) follows from the regex and the exact-equality check, not from a run. Confirming it needs the guard-the-guard test run with an invented number followed by 2–4 spaces and a date: `pytest tests/features/account_detect/test_no_real_data.py -k spelling`, with that added spelling.
- The INV-3(b) finding turns on whether the wizard redraws the review table in the same slot call as the last scan step. That is past my one-hop bound in `ui/import_wizard.py`. Whoever reads the scan-chain slot can settle it.