# tests/features/settings — FIBR-0055 Settings screen (auto-lock timeout)

Conformance tests for [`docs/specs/FIBR-0055.md`](../../../docs/specs/FIBR-0055.md).
The Settings screen's priority control is a **user-configurable auto-lock
timeout**, persisted in the encrypted vault `settings` table (no schema change),
applied live to the idle timer, surfaced through a modal `SettingsDialog` opened
from the **File → Settings…** action. A read-only base-currency display rides
along.

## Coverage

| INV | What it pins |
|-----|--------------|
| INV-1 | `AuthService.auto_lock_minutes()` — absent key / non-integer / out-of-set all fall back to `DEFAULT_AUTO_LOCK_MINUTES` (10); a stored valid value round-trips. Malformed values seeded via `SettingsRepository.set` (bypasses validation). |
| INV-2 | `set_auto_lock_minutes(n)` — invalid `n` raises `ValueError` (no write, no re-arm); valid `n` persists + calls `_arm_timer` (spy). |
| INV-3 | `_arm_timer` uses the persisted value — a live `QApplication` timer is armed to `n * 60_000` ms. |
| INV-4 | The value survives lock → unlock (same `AuthService`) and a fresh `AuthService` over the same files (real restart). |
| INV-5 | A fresh `first_run` vault (no `auto_lock_minutes` row, no migration) reports the 10-minute default. |
| INV-6 | The `Settings…` action is vault-dependent chrome: in `_menu_file.actions()`; the File menu is enabled unlocked, disabled on lock. |
| INV-7 | An idle auto-lock while Settings is open tears the tracked dialog down (`_dialog is None`); `set_auto_lock_minutes` on a locked vault raises `VaultLockedError`. |
| INV-8 | The dialog preselects the current timeout (`currentData()`), offers only `ALLOWED_AUTO_LOCK_MINUTES`, and shows the base currency in a read-only `QLabel` (no editable field). An out-of-set stored value still preselects the default. |
| INV-9 | Save applies via the service + the shell tears down + reports "Settings saved"; Cancel changes nothing. The shell path reads + passes the real vault currency. |
| D6 | `DEFAULT_AUTO_LOCK_MINUTES ∈ ALLOWED_AUTO_LOCK_MINUTES`. |

INV-10 (i18n) is covered by the existing `test_INV10_no_fixed_geometry_in_new_ui`
source-scan (globs all `ui/*.py`, so `ui/settings.py` is included); `tr()`-wrapping
is a review-checklist item per `coding.md § 5.2`.

## FIBR-0083 — datetime display prefs (added coverage)

The Settings screen also hosts the [FIBR-0083](../../../docs/specs/FIBR-0083.md)
timezone / date-format / time-format controls, and `AuthService` gains the
`DateTimePrefs` round-trip these persist through (same vault `settings` pattern
as auto-lock, no schema change). Service-level legs live here (the dialog combos
land alongside them when that slice ships):

| INV | What it pins |
|-----|--------------|
| FIBR-0083 INV-5 | `AuthService.datetime_prefs()` defaults each of the three keys to `"system"` when absent, reads each independently, and round-trips a `set_datetime_prefs(DateTimePrefs(...))` write to the named `timezone` / `date_format` / `time_format` keys. `DateTimePrefs` is a frozen dataclass (display never mutates stored prefs, INV-1). |
