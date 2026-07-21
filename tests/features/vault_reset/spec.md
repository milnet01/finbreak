# tests/features/vault_reset — FIBR-0030 destructive "start over" vault reset

Conformance tests for [`docs/specs/FIBR-0030.md`](../../../docs/specs/FIBR-0030.md).
From the unlock screen, a user who has lost the master password (no hint, no
backup) can irreversibly delete the vault and return to first-run setup. The
whole risk is an *accidental* trigger, so the flow is dominated by friction: a
Step-1 irreversible-warning message box, then a Step-2 modal whose OK is gated on
typing the literal word `DELETE`. Only after both pass does the shell call the new
`AuthService.reset_vault()` primitive.

## Coverage

| INV | What it pins | Test |
|-----|--------------|------|
| INV-1 | `reset_vault` deletes the complete on-disk footprint — `vault.db`, `vault.kdf.json`, and both orphaned SQLite WAL sidecars `vault.db-wal` / `vault.db-shm` (hardcoded literal names, pinning the suffix independently of the code). None survives. | `test_INV1_complete_footprint_deletion` |
| INV-2 | Clean slate: after a reset, first-run creates+opens a brand-new vault under a new password and it is empty; the old password no longer opens anything. | `test_INV2_clean_slate_for_next_vault` |
| INV-3 | Safe while locked: a never-unlocked service (`self._key is None`, connection never opened) resets without error and deletes the files. | `test_INV3_safe_while_locked` |
| INV-4 | Double confirmation gates the delete. Cancelling either Step-1 or Step-2 leaves the vault present and does not call `reset_vault`; a real `StartOverDialog` Cancel click fires `rejected` (dialog hidden). | `test_INV4_cancel_step1_no_delete`, `test_INV4_cancel_step2_no_delete`, `test_INV4_dialog_cancel_fires_rejected` |
| INV-5 | Step-2 OK is gated on exact `CONFIRM_WORD` (`"DELETE"`): `"delete"`, `"DELETE "`, `"DEL"`, `""` keep it disabled; `"DELETE"` enables it. | `test_INV5_ok_gated_on_exact_confirm_word` |
| INV-6 | Vault-coupled `window.ini` keys (`unlock/fail_count`, `unlock/last_fail`, `hint/text`) are cleared on reset; a benign key (window geometry) is retained. | `test_INV6_coupled_keys_cleared_benign_kept` |
| INV-7 | After reset the shell routes to first-run: `state() == "first_run"`, `window._dialog` is a `FirstRunDialog`, both vault files gone. | `test_INV7_returns_to_first_run` |
| INV-8 | `reset_vault` wipes the in-memory key via `lock()`: unlock so `self._key` holds real bytes, capture the `bytearray`, reset, then the captured buffer is zeroed and `self._key is None`. | `test_INV8_key_wiped` |
| INV-9 | The affordance is unlock-screen-only and derivation-aware: `UnlockDialog` exposes the button, clicking it fires `start_over_requested`, and `setEnabled(not busy)` toggles it. | `test_INV9_affordance_unlock_only_and_busy_aware` |
| INV-10 | A failed reset is contained: an `OSError` from `reset_vault` is caught, `QMessageBox.critical` fires, the coupled `window.ini` keys survive, and the app stays on `UnlockDialog` (no route to first-run). | `test_INV10_failed_reset_is_contained` |

## Notes on the shell-flow tests

`_on_start_over` pops two blocking modals, so the shell tests monkeypatch the
Step-1 `QMessageBox.warning` staticmethod and `StartOverDialog.exec` to run
headless (the INV-10 test additionally spies `QMessageBox.critical`). This is an
added step over the backup restore flow they mirror, which pops no modal.
