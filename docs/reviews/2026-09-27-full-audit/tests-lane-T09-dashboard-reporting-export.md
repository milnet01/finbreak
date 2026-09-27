## Chunk T09: 15 files read

**Line counts as read (last numbered line):** dashboard/test_dashboard.py 248 · dashboard/test_charts.py 158 · dashboard/test_min_size.py 104 · dashboard_focus/test_dashboard_focus.py 525 · dashboard_drilldown/test_dashboard_drilldown.py 700 · reporting/test_reporting_service.py 333 · reporting/test_period_model.py 126 · reconciliation/test_reconcile.py 77 · reconciliation/test_reconciliation_service.py 202 · reconciliation/test_reconciliation_marker.py 108 · reconciliation/test_closing_balances_for_account.py 75 · reconciliation/test_no_schema_change.py 25 · transfers/test_transfers.py 940 · pdf_export/test_export_dialog.py 186 · pdf_export/test_pdf_export.py 614. None of these directories has its own conftest.py.

**Already in my context before I read anything:** the global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, finbreak's `CLAUDE.md`, the project `MEMORY.md` index, and a git snapshot (HEAD 52e5162, clean). I read the subject from disk. The brief and my standing lane rules did not conflict anywhere. One `workspace_search` call was rate-limited, so that single lookup (`ui/accounts.py` "off by") ran through `Grep` instead.

### Findings

**[MEDIUM] [dim 1] tests/features/dashboard_focus/test_dashboard_focus.py:336** (runs to 339)
> labels = {s.label() for s in pie.chart().series()[0].slices()}
> assert not any("Savings" in ll or "Default" in ll for ll in labels)
Consequence: the pie slices are the branch's direct children, which are category nodes. The transfer legs ("to savings" / "from current") are uncategorised, so if one leaked into Spending or Income it would land in the "Uncategorised" slice. It would never appear as a label containing "Savings" or "Default". So the second half of `test_INV2_confirmed_transfer_only_in_transfers_column` passes whether or not transfers are excluded from the pies.
Fix: assert the pie amounts. For example, the Expenditure pie total equals 550 exactly, or the Uncategorised slice equals 150.

**[MEDIUM] [dim 1] tests/features/dashboard_drilldown/test_dashboard_drilldown.py:513** (runs to 515)
> first = [c.label for c in _drill(service)[1].children]
> second = [c.label for c in _drill(service)[1].children]
> assert first == second
Consequence: the test is named `test_INV7_equal_magnitude_leaves_order_by_category_id`, but Spending's children are the two top-of-chain parents "Ztest P1" and "Ztest P2". Their labels differ, so the sort is settled by label and never reaches the category-id key. And two builds over unchanged data in one process return the same order whatever the sort does. A missing or wrong id tiebreak passes.
Fix: make the tied nodes siblings with identical labels (compare `Same` under one parent's children), and assert the expected id order, not self-equality.

**[MEDIUM] [dim 1] tests/features/dashboard_drilldown/test_dashboard_drilldown.py:529** (runs to 534)
> return [(c.label, c.amount, c.count) for c in merchant.children]
> ...
> assert snapshot() == snapshot()  # deterministic across independent builds
Consequence: both leaves have the same date, amount and description. So as far as I can tell each leaf's `(label, amount, count)` tuple is identical, and any ordering of the two gives equal lists. The determinism leg cannot fail. Only the "no TypeError" and `len == 2` parts verify anything. I did not open the leaf-label code; if the label embeds the txn id, this finding falls.
Fix: include something that tells the leaves apart (a txn id, if the node carries one) in the snapshot and assert its expected order.

**[MEDIUM] [dim 1] tests/features/transfers/test_transfers.py:536** (runs to 540)
> def _boom(*a, **k):
>     raise VaultLockedError("locked mid-click")
> monkeypatch.setattr(widget._detection, method, _boom)
> getattr(widget, button).click()  # must not raise
Consequence: nothing asserts that `_boom` was reached. If a button is disabled when clicked, or a slot stops calling the patched method, the click does nothing and the leg passes while checking nothing. The comment at line 508 records that exactly this happened once (confirm/reject → confirm_many/reject_many).
Fix: record calls in `_boom` and assert it fired once after the click.

**[MEDIUM] [dim 1] tests/features/reconciliation/test_reconciliation_marker.py:99**
> assert "500" in one_text, "the discrepancy magnitude (R 500.00) is rendered"
Consequence: the marker renders `_format_amount(to_display_decimal(abs(discrepancy_minor), exponent), symbol)` (ui/accounts.py:595). If the minor-to-major conversion were dropped and the row read "off by 50000", it would still contain "500" and pass. That is the 100x unit bug test_charts.py:118 documents as having shipped once.
Fix: assert against `_format_amount(Decimal("500.00"), symbol)` exactly, as test_dashboard_focus.py:296 does.

**[MEDIUM] [dim 1] tests/features/dashboard/test_dashboard.py:161** (runs to 163)
> assert "3" in income.text() and "000" in income.text()
> assert "500" in expenditure.text()
> assert "2" in net.text() and "500" in net.text()  # net 2500
Consequence: loose substring matches pass on wrong totals. Income 30 000 or 13 000 passes. Expenditure 1 500, 2 500 or 5 000 passes. Net 25 000 passes. The same shape appears at test_dashboard_focus.py:394 (`"2" in ... "450" in`). These are the dashboard's headline money figures.
Fix: compare to `_format_amount(Decimal(...), symbol)` exactly.

**[MEDIUM] [dim 1] tests/features/pdf_export/test_pdf_export.py:132** (runs to 133)
> html, _ = _svc(service)._build_html(_options(account_ids=frozenset({a, b})), _TODAY)
> assert "Savings" in html
Consequence: `test_named_accounts_header_lists_names` checks the whole HTML. With two accounts in scope, `_summary_html` also writes a "By account" table that names every account. So "Savings" is present even if the header collapsed to a count or dropped the name. The sibling test at :141 already splits on `<h2>` to isolate the header; this one does not.
Fix: assert on `html.split("<h2>", 1)[0]`.

**[MEDIUM] [dim 1] tests/features/pdf_export/test_pdf_export.py:468** (also :491)
> mode = out.stat().st_mode & 0o777
> assert mode == 0o600, f"exported report is mode {mode:o}, expected 600"
Consequence: the test never sets the process umask. On a runner with umask 077, the pre-fix `Path.write_bytes` (0o666 & ~umask) also yields 0600, so the test passes against the defect it guards. It is only a real test under a loose umask, which it leaves to the environment.
Fix: set `os.umask(0o022)` for the test and restore it afterwards.

**[LOW] [dim 1] tests/features/pdf_export/test_pdf_export.py:399** (runs to 404)
> monkeypatch.setattr(
>     Path, "write_bytes", lambda self, data: writes.append(str(self))
> )
Consequence: the claim is that render+encrypt "writes nothing to disk", but only `Path.write_bytes` is watched. The module's own write path is now `os.open` (pdf_export.py:173). A regression that writes plaintext through `os.open`, `open()` or a file-backed `QPdfWriter` passes.
Fix: also patch `os.open` and `builtins.open` (or run under a read-only cwd/tmp) and assert none was called.

**[LOW] [dim 1] tests/features/dashboard/test_dashboard.py:221** (runs to 234)
> def test_INV7_period_selector_change_persists_and_rerenders(qtbot, service):
> ...
> assert stored.mode == MODE_SPECIFIC_YEAR
Consequence: only persistence is asserted. A selector change that saves the pref but never re-renders passes, so the "rerenders" half of the claim is unverified.
Fix: also assert a period-dependent figure or the trend axis changed after the switch.

**[LOW] [dim 1] tests/features/transfers/test_transfers.py:98**
> assert LATEST_SCHEMA_VERSION >= 8
Consequence: this can fail only if the schema version goes down. It verifies nothing about the v7→v8 step its name claims. That step is actually covered by `test_INV9_v7_upgrades_to_v9` at :101.
Fix: delete it, or fold it into the v7 upgrade test.

**[LOW] [dim 7] tests/features/dashboard_focus/test_dashboard_focus.py:201** (also :410, :453, :490)
> today = date.today()
Consequence: the recurring-card tests seed occurrences and compute the expected summary from the machine clock, while HomeView reads `app_today()` (ui/home.py:305, :402), which follows the pinned zone. The two agree only while the zone setting is "system" and the run does not cross midnight between seeding and render. This is the clock trap your brief lists (shared context § D).
Fix: pin `app_today` (monkeypatch the home module's symbol) to a fixed date and seed from that.

### Pre-pass verdicts
- none supplied

### Dimensions scanned
- 1: 11 findings (8 MEDIUM, 3 LOW)
- 4: clean against the orchestrator's count; nothing in this chunk contradicts it
- 5: clean. No sleeps and no network. Visibility asserts use `show()` + `waitExposed` on the current stack page. No `waitUntil` on a proxy condition.
- 7: 1 finding. Every other date is pinned: `_TODAY` / `_JAN`, the injected `today`, and the two-clock monkeypatch in the filename test.
- 11: clean. No empty or TODO bodies. The `LATEST >= 8` pin is filed under dim 1.
- 14: clean. The monkeypatched `pikepdf.Encryption`, `QFileDialog` and `Path.write_bytes` are failure injection or out-of-scope layers. No `except: pass`, no warning filters.
- 6: clean. `QLocale.setDefault` and `qapp.setPalette` are restored in `finally`; all other patching goes through `monkeypatch`; every vault is per-test `paths`.
- 8: N/A, no skip or xfail markers in this chunk.
- 9: N/A, no external endpoints.
- 12: N/A, none of these tests is in the slowest 20 and there is no per-test timing.
- 15: N/A, nothing in this chunk failed.

### Noted, not mine
- services/pdf_export.py:131 `render_pdf_bytes` falls back to `date.today()` when no `today` is passed. The filename-agreement test covers the shell path only; whether other callers pass `today` belongs to review-code.

### Possibly wider
- Loose substring money checks (`"500" in text`, `"2" in ... and "450" in ...`) probably appear in UI tests outside this chunk as well.
- Negative/robustness tests that monkeypatch a collaborator to raise, without asserting it was reached, likely recur elsewhere, for example other tabs' VaultLockedError slot tests.

### Open questions
- test_dashboard_drilldown.py:534: whether a txn leaf's `label` embeds anything unique (such as the id) decides whether the determinism leg is vacuous. I did not open the leaf-construction code.
- test_pdf_export.py:468: needs the test re-run under `umask 077` against the pre-fix `write_bytes` implementation to show the vacuous pass directly. Unexecuted; needs `(umask 077; pytest tests/features/pdf_export/test_pdf_export.py -k owner_only)` against a reverted `export()`.
- Dim 6 run-alone vs in-suite: not checkable without two runs. I found no shared mutable state structurally.