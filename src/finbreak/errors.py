"""finbreak exception taxonomy (coding.md § 2 — specific exceptions over generic).

Named types so every FIBR-0004 invariant failure-leg asserts the *right*
exception, not a bare ``Exception``.
"""

from __future__ import annotations


class FinbreakError(Exception):
    """Base for finbreak's own errors."""


class KdfPolicyError(FinbreakError):
    """A recorded KDF record is unacceptable — below the strength floor, wrong
    field lengths, or a malformed / missing-field sidecar (FIBR-0004 INV-2b/2c)."""


class VaultStateError(FinbreakError):
    """The on-disk vault/sidecar pair is in a mixed presence state — one file
    present without the other (FIBR-0004 INV-5)."""


class VaultLockedError(FinbreakError):
    """An operation needing the vault was attempted while it is locked
    (FIBR-0004 INV-3)."""
