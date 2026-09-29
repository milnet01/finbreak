# demo_scripts — test contract (FIBR-0399)

The marketing helpers `scripts/capture_screenshots.py` and
`scripts/seed_demo_vault.py` run from a checkout. Three properties are locked:

- **INV-1:** `seed_demo_vault.py` imports `finbreak` from the checkout's `src/`,
  never from an older installed copy.
- **INV-2:** `capture_screenshots.py` renders offscreen even when the caller's
  environment names another Qt platform.
- **INV-3:** a curated site shot that this run did not capture is reported on
  stderr, never skipped silently.
