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


class AccountInUseError(FinbreakError):
    """Deleting an account that still holds >= 1 transaction (FIBR-0005 INV-6)."""


class LastAccountError(FinbreakError):
    """Deleting the only remaining account (FIBR-0005 INV-6/D7); at least one
    account must always exist."""


class SchemaVersionError(FinbreakError):
    """The on-disk vault's schema version is newer than this build supports —
    a distinct condition from ``VaultStateError``'s presence mismatch
    (FIBR-0005 INV-4)."""


class ProtectedCategoryError(FinbreakError):
    """Editing or deleting a Type root (Income / Expenditure) is refused — the
    two roots are structural and permanent (FIBR-0006 INV-5/INV-6)."""


class CategoryHasChildrenError(FinbreakError):
    """Deleting a category that still has sub-categories (FIBR-0006 INV-6);
    remove the children first."""


class BackupError(FinbreakError):
    """A backup restore failed — a wrong backup password, a corrupt / truncated /
    entry-missing / traversal / oversized `.fbk`, an unknown container
    ``format_version``, a below-floor KDF params record, or a newer embedded
    schema. Restore normalises the underlying ``KdfPolicyError`` /
    ``SchemaVersionError`` / ``DatabaseError`` / ``zipfile.BadZipFile`` to this one
    type, and changes nothing on disk (FIBR-0014 INV-4/11/12)."""


class UpdateError(FinbreakError):
    """A recoverable auto-update failure surfaced to the user on an explicit
    **Update now** — an oversize/timed-out/dropped download or a disk error at
    swap (FIBR-0054 INV-10/INV-11). The session stays on the current version."""


class UpdateVerificationError(UpdateError):
    """A downloaded AppImage failed its Ed25519 signature check — the *core*
    integrity gate (FIBR-0054 INV-4). Nothing is installed; the temp is deleted."""
