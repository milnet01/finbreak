# loan_sign — test contract (FIBR-0467)

The contract is [`docs/specs/FIBR-0467-home-loan-sign.md`](../../../docs/specs/FIBR-0467-home-loan-sign.md).
This suite locks its schema-v16 upgrade step:

- **INV-4:** the step negates exactly the rows its selector picks: a `home_loan`
  account's rows on a `.pdf` period with a stored closing.
- **INV-5:** the step is all-or-nothing, and runs once.
- **INV-6:** afterwards, every confirmed transfer pair's two amounts are exact
  opposites.
- **INV-7:** re-importing a Family B statement after the upgrade adds nothing.

INV-1, INV-2 and INV-3 live in `tests/features/standard_bank_pdf/`; INV-8 in
`tests/features/transfers/`.
