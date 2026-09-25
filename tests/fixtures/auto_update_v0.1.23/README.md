# FIBR-0301 — a real, previously-shipped signed artifact

Two files, downloaded unmodified from the **public** GitHub release
`v0.1.23` of `milnet01/finbreak`:

```
gh release download v0.1.23 -R milnet01/finbreak -p SHA256SUMS -p SHA256SUMS.sig \
    -D tests/fixtures/auto_update_v0.1.23
```

| File | What it is |
|------|------------|
| `SHA256SUMS` | The release's checksum manifest — file hashes and asset names only. No secrets, no bank data (`docs/standards/testing.md § 6`). |
| `SHA256SUMS.sig` | The raw 64-byte Ed25519 signature over `SHA256SUMS`'s exact bytes, produced by `scripts/sign-release.py` against the maintainer's private signing key at release time. |

## Why this exists (FIBR-0301)

`docs/standards/versioning.md` § 2 names the update path as a compatibility
surface whose break includes **"a signing-key rotation"**. Before this
fixture, nothing in the gate could catch that class of break:

- `scripts/release-linux.sh`'s hard gate verifies a freshly-built manifest
  against the `RELEASE_PUBLIC_KEY_B64` committed in the **same tree** — so
  rotating the private key and the committed constant together, in one
  commit, passes the gate green.
- Every other signature test in `tests/features/auto_update/` (INV-4,
  INV-14) signs and verifies with a **throwaway keypair generated inside the
  test** (`Ed25519PrivateKey.generate()`), monkeypatched in as
  `update_key.public_key`. That proves the Ed25519 primitives round-trip; it
  proves nothing about whether the app's **actual, shipped** trusted key still
  matches what a real past release was signed with.

A same-build round-trip cannot detect a rotation, by construction: whatever
key the test generates, it both signs *and* verifies with. This fixture is
signed with the **maintainer's real private key**, once, outside any test run,
and its signature is checked against the **real, committed**
`RELEASE_PUBLIC_KEY_B64` — the exact constant `update_key.public_key()` loads
in production. If that constant is ever rotated without a coordinated
migration, `test_INV15_historical_release_verifies_against_committed_key`
(`tests/features/auto_update/test_auto_update.py`) turns red, because this
signature no longer verifies against the new key — the same failure every
already-installed copy's updater would hit.

## Scope

This locks **one direction only**: that the currently-trusted key can still
verify a signature it (or its predecessor, if never rotated) produced in the
past. It says nothing about whether a *future* release will verify under
today's key — that is what every real release's own build-time signing +
verification already covers, and is out of scope here.

## If this test goes red

**The fix is almost never to re-pin this fixture with a freshly-signed one.**
Re-signing `SHA256SUMS` with the new key and re-generating `.sig` would make
the test pass again while proving nothing — it would be exactly the
same-build blind spot INV-4/INV-14 already have, defeating the reason INV-15
exists. A red run here means: `RELEASE_PUBLIC_KEY_B64` no longer matches the
key that signed v0.1.23, so **every copy of finbreak already installed from a
release signed under the old key can no longer verify an update** and its
in-app updater is permanently stuck. That is a product incident, not a test
to silence — see `docs/standards/versioning.md` § 2 (the update-path
compatibility-surface row) for what a coordinated rotation requires before a
constant like this may change.

## Regression history

Filed **2026-08-20** during a `review-contract` loop on
`docs/standards/versioning.md` (loop 3, Q1 — see that document's cold-eyes
loop log) as **FIBR-0301**: the "What checks this" cell for the update-path
row read as covered by `tests/features/auto_update/` and
`scripts/release-linux.sh`'s hard gate, and neither actually covers a
signing-key rotation. This fixture + INV-15 close that gap. No rotation has
ever occurred on this project; `RELEASE_PUBLIC_KEY_B64` has been unchanged
since it was generated 2026-07-11.
