# FIBR-0087 — review-contract loop log

The review record for `docs/specs/FIBR-0087-per-account-currency.md`.
`review-contract` writes one row per loop as it closes.

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-11-21 | 2 × `review-lane` via `neutral-lane`, cold, identical brief, every lane held every question | 0 | 2 | 5 | 0 | **Seven verified, seven fixed, none dismissed.** Both lanes found four of them: INV-6 contradicted § 4.3 on a vault whose one currency is not the base; `RecurringService` gave a currency to `summary` only, so `snapshot`'s summary and `confirmed` would mix currencies; the Alerts dialog's dismiss count would overwrite the scoped button; and neither transfer type had a pinned currency field (`ConfirmedTransfer` was not named). One lane found that pairing lives in `TransferRepository.candidate_pairs`, which `confirm_all` calls without `candidates`, and that § 4.4's refusal lacked `QT_TRANSLATE_NOOP`. The orchestrator settled one lane question into a finding: the Forecast tab's `_coverage_suffix` and `_excluded_names` count every account. One false sentence in § 7 (tests asserting `_version == 18`; none exist) was deleted under the carve-out and is not tallied. Three open questions resolved clean. Packet built with every citation windowed and no defect found while building it; the packet was about 46k tokens. |
