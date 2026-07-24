# spending_alerts — feature test contract (FIBR-0172)

The binding design contract is [`docs/specs/FIBR-0172.md`](../../../docs/specs/FIBR-0172.md)
(cold-eyes converged). This file is the test-scope stub the app-workflow
requires per feature; the authoritative invariants (INV-1 … INV-19 + INV-14a)
live in the spec's § 5. Tests here cite those INV numbers.

Coverage in this directory:

- `test_detectors.py` — the three **pure** detectors (`detect_new_recurring`,
  `detect_category_spikes`, `detect_missed_debits`): boundaries + keys +
  integer-money mean (INV-1, INV-3, INV-6, INV-7, INV-8, INV-10, INV-15).
- `test_alert_dismissals.py` — `AlertDismissalRepository` idempotent dismiss +
  round-trip + clear on an in-memory vault (INV-12).
- `test_alert_service.py` — `AlertService.alerts(today)` over a real in-memory
  SQLCipher vault: new-recurring / spike / missed-debit assembly, transfer +
  None-bucket exclusion, dismissal scope, ordering, money-safety (INV-1, INV-2,
  INV-4, INV-5, INV-9, INV-11, INV-13, INV-15, INV-16, INV-19).
- `test_migration_v12.py` — the v12 `alert_dismissals` migration + drift guards
  (INV-14, INV-14a).
- `test_alerts_card.py` — the `AlertsCard` on the Home dashboard: hidden when
  empty, one row per alert, Dismiss round-trip, `VaultLockedError`-silent
  (INV-17, INV-18).
</content>
