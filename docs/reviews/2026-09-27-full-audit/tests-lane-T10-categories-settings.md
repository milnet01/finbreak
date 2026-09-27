## Chunk T10 — 7 files read

**Subject line counts as read:** test_categories.py 881 · test_picker_labels.py 241 · test_category_library.py 466 · test_categorisation.py 1248 · test_clipboard.py 448 · test_settings.py 652 · test_table_state.py 916. I checked for other `*.py` files under categories/, categorisation/ and category_library/ and found none.

**What I already had in context before reading:** global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, finbreak `CLAUDE.md`, the finbreak MEMORY.md index, and a git snapshot (clean main at 52e5162). This ran as a review-lane with no shell. One `mcp__ants__workspace_search` call was refused with `rate_limited`, and I used `Grep` for that one search. Nothing in the brief conflicted with the lane file.

**One-hop reads:**
- `tests/conftest.py`: QT_QPA_PLATFORM setdefault at line 17, `_pump_deferred_delete`, `window_ini`, `_neutralise_category_library`, `_CallLog`, `PickerStub`, `RuleStub`, `stub_picker`, `spy_learning`
- `src/finbreak/ui/_clipboard.py` (whole file)
- Grep hits in `ui/rules.py` (`_on_add`, the status setText), `ui/categories.py` (the delete confirm) and `services/auth.py` (`first_run` / `_arm_timer` / `set_auto_lock_minutes`)

### Findings

**[MEDIUM] [dim 8] tests/features/clipboard/test_clipboard.py:266**
> if not clip.supportsSelection():
>     pytest.skip("no X11 Selection buffer on this platform (offscreen CI)")

Consequence:
- `tests/conftest.py:17` sets `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")` for the whole suite.
- The offscreen platform has no Selection buffer, so this leg skips on every default run: locally, in CI and in `ci-docker.sh`.
- It only runs if someone exports QT_QPA_PLATFORM=xcb themselves beforehand. That means the runtime check of INV-7 ("the Selection buffer is never written or cleared") runs nowhere, yet shows up every run as a skip.
- The only real cover is the static backstop at :277 (`assert "Selection" not in source`). That is a text search over `_clipboard.py` only. It would pass a mode passed in as a variable, or a Selection write in the TransactionsView caller.

Fix: either delete the runtime leg and treat :277 as the check, or run it in a job that forces xcb with a display.

**[MEDIUM] [dim 1] tests/features/categorisation/test_categorisation.py:146 (runs to :182)**
> monkeypatch.setattr(library_mod, "normalise_text", counting)

Consequence:
- The docstring says patterns were re-folded per row "in both ``categorize`` and ``match_library``".
- This test has no `real_library` marker and never injects a library. So the autouse `_neutralise_category_library` makes `load_library` return `[]`, and `match_library` has zero entries to fold.
- If `match_library` went back to per-row folding, this test would still pass. Only the `categorize` half of the claim is checked.

Fix: inject a library of several entries (the `_inject` pattern from test_category_library.py) and add those entries to the call bound.

**[MEDIUM] [dim 1] tests/features/category_library/test_category_library.py:460**
> cat.set_library_enabled(dlg.library_enabled())  # shell persists on Save

Consequence:
- The section claims a "Settings toggle round-trip (INV-7)", but the test does the shell's persist step itself.
- A MainWindow that never calls `set_library_enabled` when Settings is saved passes this test unchanged.
- What it actually checks is that the dialog reflects its constructor argument, plus the service setter. These are the "driving the collaborator" and "assert the user-visible outcome" traps from the known-traps list.

Fix: drive it through the shell (open Settings via `MainWindow`, untick, click Save), then assert `library_enabled()` and what a reopened dialog shows.

**[MEDIUM] [dim 1] tests/features/table_state/test_table_state.py:547 (the section header), docstring at :550**
> # INV-6 — a reset survives a rebuild (the clear-LAST discriminator)
> """All four preconditions, or this passes against the broken ordering:

Consequence:
- The test's own NOTE at :604–611 says mutation showed it "does not discriminate clear-first from clear-last". It goes red only when both `reset_columns(self)` and `settings.remove("columns")` are dropped.
- So the header and docstring claim an ordering check that the body does not deliver. FIBR-0199 (:695) covers the settings clear on its own, but no test in the chunk covers the ordering INV-6 names.
- A reader counting coverage from the name will think the ordering is locked when it is not.

Fix: either remove the "clear-LAST discriminator / broken ordering" claim from the header and docstring so they match the NOTE, or add a leg whose outcome depends on the order.

**[LOW] [dim 1] tests/features/categorisation/test_categorisation.py:845**
> assert "1" in widget._status.text(), "Apply reports the re-filed count"

(the same shape at :847: `assert "0" in widget._status.text()`)

Consequence:
- The status is `tr("Re-filed %n transaction(s).", "", count)` (rules.py:305).
- A wrong count of 10, 11 or 21 passes the first assertion, and 10 or 20 passes the second. The test is meant to prove the reported count.

Fix: compare the whole string against `widget.tr("Re-filed %n transaction(s).", "", 1)` (and 0 for the second).

**[LOW] [dim 6] tests/features/category_library/test_category_library.py:361**
> cl.load_library.cache_clear()  # trailing clear — don't poison the cache for later

Consequence:
- The trailing clear only runs if every assertion before it passes.
- If :354, :357 or :360 fails, the process-wide `lru_cache` keeps `[]` from a tmp path. monkeypatch restores `_LIBRARY_PATH` but not the cache.
- Any later `real_library` test that goes through `load_library` would then see an empty library and fail too, e.g. test_categorisation.py:1218 via `_match_inputs`. One real failure turns into two, and the second one points at the wrong place.

Fix: do the clear in a `try/finally` or in a fixture teardown.

**[LOW] [dim 12] tests/features/clipboard/test_clipboard.py:394**
> monkeypatch.setattr(service, "clipboard_clear_seconds", lambda: 1)

Consequence:
- Measured at 1.10 s. Almost all of it is the 1 s real timer, because `ClipboardAutoClear.copy` does `self._timer.start(seconds * 1000)` with whole seconds (`_clipboard.py:44`), so 1 s is the shortest possible wait.
- `test_INV3_real_elapse_auto_clears` (:232) pays the same 1 s.

Fix: a sub-second wait needs `_clipboard.py` to accept milliseconds. That means changing the code under test, so this stays LOW and is out of this review's scope.

### Pre-pass verdicts
- None were supplied.

### Dimensions scanned
- **1:** 4 findings (FIBR-0213 library half, the library toggle wiring, the INV-6 ordering claim, the loose Apply count).
- **4:** Clean. The orchestrator's count covers this chunk. The parametrised test at categorisation:850 is collected normally.
- **5:** No issues found.
  - No sleeps or network calls.
  - The real-clipboard waits use `waitSignal`/`waitUntil` on the state being asserted.
  - The header click at table_state:461 checks that the section is visible and has a non-zero width first.
  - The `except TimeoutError: pass` at clipboard:438 is followed by an assertion on the actual state, so it does not hide anything.
- **6:** 1 finding (the lru_cache clear only on success). The window INI is per-test `tmp_path` (autouse `window_ini`). The `clip` fixture clears the clipboard before and after.
- **7:** No issues found. table_state:425 uses unfrozen `date.today()`, but both the seeded dates and the assertions are relative (`dates_after == dates_before`), and the default "system" zone lines up with the app clock.
- **8:** 1 finding (the clipboard Selection skip).
- **9:** N/A. No external endpoints.
- **11:** No issues found.
- **12:** 1 finding (the 1 s clipboard floor). The four table_state tests over 1 s (FIBR0199 1.89 s, INV8 1.15 s, INV6 1.10 s, INV5 1.00 s) all build the full unlocked `MainWindow`, which is where `_reset_layout` lives. The window is what those tests are about, so I did not file them.
- **14:** No issues found.
- **15:** N/A. Nothing in this chunk failed.

### Noted, not mine
- None.

### Possibly wider
- A test in the app_shell/main_window suites may cover `MainWindow` persisting `library_enabled` on Settings save. If one does, the category_library:460 finding drops to "this test adds nothing". I did not look.
- The loose `"N" in text` count check probably also appears in other suites' status-label assertions.

### Open questions
- dim 8: to confirm the Selection leg passes when it does run, I would need `QT_QPA_PLATFORM=xcb pytest tests/features/clipboard/test_clipboard.py::test_INV7_selection_buffer_untouched` on a real X11 display. Unexecuted.
- dim 12: FIBR0199 (1.89 s) costs about 0.8 s more than its shell-building siblings. Finding out why needs a per-phase profile (`pytest --durations` plus a profiler on that one test). Unexecuted.
- dim 1, categories:536–537: the delete confirm assertions (`"3" in text`, `"1" in text`) have the same loose-substring shape as the Apply-count finding. A transaction count of 13 would pass both. I did not file it because the full confirm text past categories.py:213 was outside what I read.