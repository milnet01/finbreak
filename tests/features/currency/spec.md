# currency — feature test contract

The test side of
[`docs/specs/FIBR-0087-per-account-currency.md`](../../../docs/specs/FIBR-0087-per-account-currency.md).
That spec owns the invariants; this suite enforces two of them.

- **INV-6** — `scope_currency` returns the single currency of its scope, or
  raises `MixedCurrencyError`. `test_scope.py`.
- **INV-7** — each service in the spec's § 4.5 first table refuses a mixed
  scope and answers a single-currency one. `test_scope.py`.

Every vault uses `tmp_path`; every row is synthetic (testing.md § 6).
