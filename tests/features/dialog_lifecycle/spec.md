# Feature test — dialog lifecycle (FIBR-0065)

Contract for the non-blocking-pop-up conversion. Full design:
[`docs/specs/FIBR-0065.md`](../../../docs/specs/FIBR-0065.md).

- **INV-1 (no blocking pop-up, and no event pumping)** — a source grep over the
  code *and comments* of `ui/{home,rules,statements,import_wizard,import_batch}.py`
  for **two** tokens: `.exec(` and `processEvents`. The sole exemption is the
  single `menu.exec(` in `home.py` (the Home context `QMenu`, out of scope). This
  is the crash-class regression guard — a future `dialog.exec()` re-introduction
  fails it.

  Both halves widened with FIBR-0085 (its INV-6). `import_batch.py` joins the set
  because a new UI module is outside this guard until it is named, and a guard
  that silently does not cover new code is worse than no guard. `processEvents`
  joins the pattern because a modal `QProgressDialog` driven by a bare
  `QApplication.processEvents()` loop carries no `.exec(` token, so it passed the
  original grep untouched while re-entering the event loop exactly as FIBR-0065
  forbids — the batch import is the first feature with a long-running loop and so
  the first with a reason to reach for it. The token binds the whole file set, not
  just the two files FIBR-0085 touched, which tightens it for the four older
  members for free.
- **INV-2 (lock never crashes)** — a real `MainWindow._lock()`-during-open-popup
  integration test covering the guard-less D5 PDF-password prompt specifically
  (lives in the pdf_import suite where the wizard fixtures are), plus per-pattern
  positive wiring legs in each widget's own suite.
- **INV-4 (no leak)** — each pop-up is freed on close via `finished → deleteLater`.

The behavioural-parity (INV-5) and PDF-semantics (INV-6) checks live in the
existing per-widget suites (categorisation / statements / pdf_import), re-pointed
from the old `exec()` fakes to real signal-emitting `QDialog` subclasses.
