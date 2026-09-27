## Chunk T04: 4 files read

**Subject file line counts, as read from disk:**
- `/mnt/Games/Scripts/Linux/finbreak/tests/features/import_/test_import.py`: 1340 lines
- `/mnt/Games/Scripts/Linux/finbreak/tests/features/standard_bank_pdf/test_standard_bank.py`: 1307 lines
- `/mnt/Games/Scripts/Linux/finbreak/tests/features/pdf_import/test_pdf_import.py`: 936 lines
- `/mnt/Games/Scripts/Linux/finbreak/tests/features/ofx_import/test_ofx_import.py`: 699 lines

The last numbered line of each file with content. `Read` also showed one empty line after each, from the final newline.

**Already in my context on arrival:** the global `~/.claude/CLAUDE.md`, `/mnt/Games/CLAUDE.md`, the finbreak project `CLAUDE.md`, the finbreak memory index, and a git snapshot at HEAD 52e5162 naming the FIBR-0331 commits. I read the subject files from disk.

**Which lane ran:** I am a `review-lane` agent with read-only tools. `workspace_search` was rate-limited once, so I used `Grep` for that one lookup.

**Code I opened (one hop, for Q1 only):**
- `ImportService._validate_mapping`, `_read_capped` and `preview` in `services/import_.py`
- `read_header` and `read_rows` in `importers/csv_importer.py`
- `OfxImporter.parse` lines 60–109 in `importers/ofx_importer.py`
- `_on_pdf_table_changed`, `_on_pdf_password` and `_after_decrypt` in `ui/import_wizard.py`

### Findings

**[MEDIUM] [dim 1] tests/features/import_/test_import.py:291** (the `both_styles` case of the parametrised test at :297)
> ColumnMapping(
>     "Date", "Details", "Amount", "Debit", "Credit", "%Y-%m-%d", False
> ),
- **What the test uses:** `HEADER` is `["Date", "Details", "Amount"]`. Line 302 checks only `with pytest.raises(ValueError):`.
- **Why that is too loose:** in `_validate_mapping` (`services/import_.py:410`), if the "exactly one amount style" check were deleted, this mapping would fall through to the pair branch. `style_cols` would then be `["Debit", "Credit"]`, and neither is in the header, so the "mapped column(s) not in the file header" `ValueError` fires anyway.
- **Consequence:** the `both_styles` leg stays green even when the both-styles refusal it exists to pin is removed. This is shared context § D's trap. The `no_amount_style` leg does discriminate: its header check passes, so nothing else raises.
- **Fix:** put `Debit`/`Credit` in that case's header text, or add `match="exactly one amount style"`. Adding `match=` to all three cases also stops `missing_column` passing on some other `ValueError`.

**[MEDIUM] [dim 1] tests/features/ofx_import/test_ofx_import.py:671** (in `test_investment_statement_refused_not_crashed`, :657)
> with pytest.raises(ValueError):
- **The routes to `ValueError`:** `OfxImporter.parse` (`ofx_importer.py:79-84`) wraps the ofxparse call in `except Exception` and maps everything to `ValueError("this file could not be read as OFX")`. `:90-91` also raises `ValueError` when there are no accounts. So there are three routes to `ValueError` besides the investment filter at `:99-108`.
- **Consequence:** the OFX string is hand-built SGML. If ofxparse rejects it, or yields no accounts, the test passes without ever reaching the `AccountType.Investment` filter its docstring claims to cover (the AttributeError crash). A deleted filter would then go unnoticed.
- **Fix:** add `match="investment/brokerage"`.

**[MEDIUM] [dim 1] tests/features/ofx_import/test_ofx_import.py:282** (in `test_INV4_statement_less_envelope_raises_value_error`)
> with pytest.raises(ValueError):
- **What the source says:** the code comment at `ofx_importer.py:87-88` says the no-statements guard sits "AFTER the boundary catch so its distinct message isn't collapsed (INV-4)".
- **Consequence:** the test can't tell that distinct message from the boundary catch's generic one. If ofxparse rejected the sign-on-only envelope, or the explicit guard were removed so the access failed elsewhere, the test would still pass.
- **Fix:** add `match="no statements were found"`.

**[MEDIUM] [dim 1] tests/features/pdf_import/test_pdf_import.py:282**
> assert [c for c in grouped if len(c) > 1] == [[["C", "D"], ["x", "1"]]]
- **What is being asserted:** the test's claim (`:278-279`) is that `candidate_tables` drops a header-only candidate. But the `len(c) > 1` filter here is written inside the test and applied by the test. `candidate_tables` is never called.
- **Consequence:** delete the filter from `PdfImporter.candidate_tables` and this test stays green. The assertion checks the test's own list comprehension.
- **Fix:** call `candidate_tables` on a fixture containing a header-only table and assert on what it returns, or monkeypatch the extractor to return such a group.

**[MEDIUM] [dim 1] tests/features/ofx_import/test_ofx_import.py:547**
> for banned in ("import socket", "import http", "urllib", "requests", "ftplib"):
- **Consequence:** the test claims "no network surface in the importer". But the matching is exact substrings and case-sensitive, so `from http.client import HTTPSConnection`, `from http import client`, `import ssl` and `asyncio.open_connection` all pass. It would read green over a real network import.
- **Fix:** parse the module with `ast` and check every `Import`/`ImportFrom` root against a denylist (`socket`, `http`, `urllib`, `ssl`, `ftplib`, `requests`, `asyncio`).

**[LOW] [dim 1] tests/features/pdf_import/test_pdf_import.py:212**
> for tok in (
>     "tempfile",
>     "NamedTemporaryFile",
>     ".write_bytes(",
- **Consequence:** the list has no `.write_text(`, `"ab"`, `"xb"`, `shutil.copy` or `os.open`, so `Path(...).write_text(...)` in `pdf_importer.py` passes this "no disk-write token" check. The behavioural sibling at `:195` only observes `TMPDIR` and the current working directory, so a write elsewhere is caught by neither.
- **Fix:** widen the token set, or do an `ast` walk for `open()` calls with a write mode plus `write_text`/`write_bytes` attribute calls.

**[LOW] [dim 1] tests/features/standard_bank_pdf/test_standard_bank.py:686**
> assert len(_PRE_E_FIXTURES) == 15
- **Consequence:** this is meant to guard the hand-written list at `:654-676` against fixture drift. It checks only the count. Rename a fixture, or add one and delete another, and the count stays 15. The new fixture's detection then goes untested while this guard stays green.
- **Fix:** assert that the glob's name set equals the name set of the parametrised list.

**[LOW] [dim 1] tests/features/ofx_import/test_ofx_import.py:571**
> assert _PW.decode() not in caplog.text
- **Consequence:** the master password is used only in the `service` fixture's `first_run`, which runs before the `caplog` block. Nothing inside the block receives it, so this assertion cannot fail. It reads as a "no secret logged" check (the INV-8 header) while checking nothing.
- **Fix:** drop it, or assert on a secret that actually flows through the OFX path.

**[LOW] [dim 1] tests/features/pdf_import/test_pdf_import.py:679**
> assert LATEST_SCHEMA_VERSION >= 9
- **Consequence:** the name and docstring claim "the walk reaches v9". The test only compares a constant, so it cannot fail unless the constant drops below 9, and it exercises no migration.
- **Note:** the reachability claim is carried by `:633`, `:653` and `:682`, which do walk v4/v5 to latest.
- **Fix:** delete it, or fold its claim into one of those walks.

**[LOW] [dim 5] tests/features/import_/test_import.py:928**
> os.symlink("/dev/zero", link)
- **Consequence:** this test's claimed defect is a stat-only or unbounded read. If that defect came back, the test would not fail red. `open(...).read()` on `/dev/zero` would allocate until memory ran out or the run hung. On this machine `/tmp` is RAM-backed, so that is memory pressure on the whole desktop, and on CI it is a killed runner rather than a failure message.
- **Fix:** replace `/dev/zero` with a small in-test endless source (a generator-backed handle patched into `open`), or give this test a hard per-test timeout or memory limit.

**[LOW] [dim 6] tests/features/pdf_import/test_pdf_import.py:211** (also `:790` and `tests/features/ofx_import/test_ofx_import.py:546`)
> src = Path("src/finbreak/importers/pdf_importer.py").read_text()
- **Consequence:** these three paths are relative to the working directory, so the result depends on where pytest is invoked from. Run `pytest` from `tests/` or any other directory and all three raise `FileNotFoundError`. That is red, not false green. The sibling at `test_standard_bank.py:325` resolves through `standard_bank.__file__` and does not have this problem.
- **Fix:** resolve through the imported module's `__file__`, or through `Path(__file__).parents[N]`.

### Pre-pass verdicts
- `test_pdf_import.py:200` `setenv_call`: **false positive.** It is `monkeypatch.setenv("TMPDIR", ...)`, which is undone at teardown. The `tempfile.tempdir` change on `:201` is also a `monkeypatch.setattr`, so it is restored too. Nothing leaks to other tests.

### Dimensions scanned
- **1:** 9 findings (above).
- **4:** clean. The orchestrator settled it and I did not re-derive it. No same-name redefinition within any file of this chunk; each file defines its own `service` fixture at module scope, which is not a test.
- **5:** 1 finding (`import:928`). No `sleep`, no network. The Qt legs call slots synchronously with no `waitUntil` proxy conditions. `_pump_deferred_delete` at `pdf:401` is a drain, not a race.
- **11:** clean. Every test body exercises the code under test. None is `pass` or a TODO, and none targets a removed symbol.
- **14:** clean.
  - No `verify=False`, bare `except: pass` or warning filters.
  - The monkeypatches of `_normalise_to_plaintext`/`pdfplumber.open` (`sb:1249`, `pdf:802`), `_try_decrypt` and `commit_import` (`import:1156`, `:1186`) replace layers those tests do not claim to exercise.
  - The `except VaultLockedError` at `import:1239` converts the escape into `pytest.fail`, so it does not suppress the failure.
  - I checked the `on_pdf_password` and `on_pdf_table_changed` legs of `test_FIBR0327_an_auto_lock_never_escapes_a_wizard_slot` against `_after_decrypt` and `_on_pdf_table_changed`. Both reach a vault call after the lock, so neither leg is vacuous.
- **15:** N/A. Nothing is failing in this chunk.
- **6:** 1 finding (the working-directory-relative source reads). The pre-pass `setenv` is a false positive.
- **7:** clean. The `os.urandom` salts at `pdf:638`, `:655` and `:687` never reach an assertion, and no clock is read.
- **8:** clean. The one skip (`import:926`) carries a reason and a live POSIX condition.
- **9:** N/A. No production endpoints.
- **12:** does not fire. None of these tests is in the suite's slowest 20, and there is no per-test timing.

### Noted, not mine
- None. I read the code only to settle Q1, and did not see a code defect while doing so.

### Possibly wider
- **Refusal tests that check only for `ValueError`:** at every importer entry point with a broad `except Exception -> ValueError` boundary, a `pytest.raises(ValueError)` with no `match=` probably has the same weakness as the two OFX findings. Candidates include the PDF-importer and batch-import suites outside this chunk.
- **Static source checks:** `ast`-free token checks of source text are likely repeated in other feature suites.

### Open questions
1. **Does the investment OFX string at `ofx:661-670` actually get past `_LocalDateOfxParser.parse` and reach the investment filter?** This settles whether the investment finding above is live or latent. It needs execution: run `pytest tests/features/ofx_import/test_ofx_import.py::test_investment_statement_refused_not_crashed` with `match="investment/brokerage"` added, or print `exc.value` from the current test.
2. **Where do the hard-coded schema versions belong?** `import:546`, `:596`, `:602` and `:608` (`test_INV8_latest_schema_version_is_10` asserts `== 14`), and `ofx:538`/`:542`, pin the latest schema version literally. Every new migration turns them red for reasons unrelated to INV-8. The pdf suite's own docstring at `:675-678` records this exact pattern as "never maintained" and replaced it there. I have not filed it because it fits no briefed dimension's trigger. Whether it belongs in this review is the orchestrator's call.
3. **The `TMPDIR` redirect at `pdf:195-207`:** does the qpdf C runtime read `TMPDIR` per call or once at library load? If it caches at first use, a `TMPDIR` redirect made after an earlier test has already used pikepdf would not redirect qpdf's temp files. The scratch-directory leg would then be vacuous for qpdf. Settling it needs an experiment: run the test alone and in the full suite with a spy on qpdf's temp creation, for example under `strace -e openat`.