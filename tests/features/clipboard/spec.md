# Feature test contract — clipboard copy + auto-clear (FIBR-0032)

Enforces `docs/specs/FIBR-0032.md`. The transactions list gains a **copy
affordance** — right-click a row → "Copy amount" / "Copy description" — and the
copied value is **self-cleaning**: wiped from the system clipboard after a short,
configurable timeout, **but only if the clipboard still holds the value we put
there** (never clobber something the user copied since). The timeout is an
`AuthService` setting (`clipboard_clear_seconds`, default 30, allowed
`(10, 30, 60, 0)`; `0` == "Never" = copy without auto-clear).

The reusable helper `ClipboardAutoClear` (`ui/_clipboard.py`) is a testable seam:
it takes its `QClipboard` and `seconds_provider` by injection, so unit legs drive
the guard deterministically (no 30-second waits, no global-clipboard pollution).
UI legs inject a **recording fake** clipboard into `TransactionsView`. Every
on-disk vault uses `tmp_path`; no test touches the network or real financial data
(testing.md § 6).

| INV | Assertion |
|-----|-----------|
| INV-1 | **Copy affordances exist.** For a selected transaction row, `_show_context_menu` builds a menu whose non-separator action texts are exactly "Copy amount", "Copy description", "Set category…" — with **no** password/account action. With no row selected, the menu early-returns (nothing built). |
| INV-2 | **What gets copied.** With a row selected, `_on_copy_amount()` pushes the exact rendered Amount cell text (`item(row, _COL_AMOUNT).text()`) to the injected clipboard; `_on_copy_description()` pushes the in-memory `Transaction.description`. Neither transforms the value. Calling either slot with **nothing selected** writes nothing and does not raise. |
| INV-3 | **Auto-clear, guarded.** After a copy with a positive timeout the timer is active with `interval == seconds*1000`; invoking `clear_if_ours()` clears an **unchanged** clipboard and leaves a **changed** one untouched. A real-elapse leg proves the `timeout → clear_if_ours` wiring actually fires and clears. |
| INV-4 | **Configurable + "Never".** The timeout is read **live per copy** from `seconds_provider` — flipping the provider 10→30 between copies moves the armed interval (10_000 → 30_000). With the provider at `0` ("Never"), a copy still sets the value and **no** timer is armed (the value persists). |
| INV-5 | **Settings control.** `SettingsDialog` exposes a `QComboBox` (`objectName "settings_clipboard_clear"`) preselected to the stored value; Save calls `set_clipboard_clear_seconds(currentData())`. The setter **raises `ValueError`** on a value outside the allowed set (writing nothing); the getter falls back to the default (30) on an absent / non-int / out-of-set stored value. |
| INV-6 | **No new secret exposure.** No "Copy password" / "Copy account number" action is offered anywhere (covered by INV-1's exact action-text assertion). |
| INV-7 | **Clipboard mode + no network.** Copy / clear target `QClipboard`'s default `Clipboard` mode only — a sentinel pre-seeded into the X11 *Selection* buffer survives a copy + clear (guarded by a `supportsSelection()` skip, since the offscreen CI platform drops Selection writes). A **CI-gated source backstop** asserts `_clipboard.py` never references `QClipboard.Selection`, so the guarantee holds even when the runtime leg skips. No-network is carried by the vault-suite static scan over the new modules. `tr()` coverage is a convention, not asserted here. |
| INV-8 | **Copy is lock-safe.** Neither copy handler performs a `Vault.connection` read, so triggering either **after the vault has locked** copies the value without raising `VaultLockedError`. A **positive control** asserts a genuine vault read (`TransactionService.base_currency()`) *does* raise in the same locked fixture, so "copy did not raise" proves lock-safety, not an unlocked fixture. |

## Out of scope

- Lifecycle-clear (wipe a still-pending clipboard value on lock or app-exit) —
  a deferred roadmap follow-up; the accepted residual is documented as
  security-model T13.
- Copying account numbers or the statement PDF password (a deliberate non-goal —
  FIBR-0128 INV-1 preserved).
- Copying arbitrary cells / whole rows, or writing the X11 *Selection* buffer.
