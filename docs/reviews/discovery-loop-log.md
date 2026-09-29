# docs/discovery.md — review-contract loop log

Kept outside the document: discovery.md has never carried a loop log and no
standard requires one (review-contract 4d).

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Verified / fixed | Dismissed | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-09-29 | 2 (every lane held every question; neutral-lane) | 3 | 1 | 0 | 0 | 4 / 4 | 4 open questions, none a finding (macOS target, retired phase names, currency storage, code signing) | Gate armed by 2fd2f03, b4bf2a9, f2d87c1 (criteria 4, 7, 8; the forecasting scope change). Findings inside that span: 0 of 4. All four were outside it and fixed in-run as exempt records of code that exists: `publish-release.sh` named as the release script (now release-linux/-windows, FIBR-0016 still planned); native RPM/deb listed out of scope though OBS ships them (FIBR-0155); charts still "design-phase" (ADR-0008 chose QtCharts); the build smoke-test described as an every-push gate stage (opt-in, weekly CI). No further loop owed. |
