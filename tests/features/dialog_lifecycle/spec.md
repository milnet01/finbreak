# Feature test — dialog lifecycle (FIBR-0065)

Contract for the non-blocking-pop-up conversion. Full design:
[`docs/specs/FIBR-0065.md`](../../../docs/specs/FIBR-0065.md).

- **INV-1 (no blocking pop-up)** — a source grep: no `.exec(` token in the code or
  comments of `ui/{home,rules,statements,import_wizard}.py`, **except** the single
  `menu.exec(` in `home.py` (the Home context `QMenu`, out of scope). This is the
  crash-class regression guard — a future `dialog.exec()` re-introduction fails it.
- **INV-2 (lock never crashes)** — a real `MainWindow._lock()`-during-open-popup
  integration test covering the guard-less D5 PDF-password prompt specifically
  (lives in the pdf_import suite where the wizard fixtures are), plus per-pattern
  positive wiring legs in each widget's own suite.
- **INV-4 (no leak)** — each pop-up is freed on close via `finished → deleteLater`.

The behavioural-parity (INV-5) and PDF-semantics (INV-6) checks live in the
existing per-widget suites (categorisation / statements / pdf_import), re-pointed
from the old `exec()` fakes to real signal-emitting `QDialog` subclasses.
