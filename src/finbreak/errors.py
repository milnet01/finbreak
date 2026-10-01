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


class KeyUnwrapError(FinbreakError):
    """A wrapped DEK slot failed to authenticate — a wrong credential OR a
    tampered slot (FIBR-0019 § 4.2 / INV-3). Deliberately ONE type for both: the
    caller cannot act differently on them, and an error that distinguishes them
    is an oracle."""


class PasswordEmptyError(FinbreakError, ValueError):
    """A new master password was empty. A ``ValueError`` too, so a caller that
    treats every form refusal alike still catches it; a named type so a dialog
    can say it in translated words (FIBR-0395)."""


class PasswordMismatchError(FinbreakError, ValueError):
    """A new master password and its confirmation differ (FIBR-0395)."""


class VaultStateError(FinbreakError):
    """The on-disk vault/sidecar pair is in a mixed presence state — one file
    present without the other (FIBR-0004 INV-5)."""


class InterruptedRestoreError(VaultStateError):
    """A restore was interrupted and its ``*.old`` copies of the previous vault
    could not be moved back (full audit 2026-09-27 row 37). The copies are intact
    in ``directory``; a retry once it is writable recovers them. A subclass so a
    handler that does not know it still fails closed on the mixed pair."""

    def __init__(self, directory: object) -> None:
        super().__init__(f"interrupted restore could not be undone in {directory}")
        self.directory = directory


class RollbackAvailableError(VaultStateError):
    """§ 13.3's terminal branch, with D8's pre-upgrade copy verified beside it.

    Every route was exhausted **and** the password was right — and a ``.pre-v2``
    pair is on disk that opens with the very key the user just typed. § 13.3
    calls making that offer "the whole return on D8": the branch stops being
    terminal.

    A SUBCLASS of :class:`VaultStateError` on purpose. Every existing handler
    already fails closed on it with § 6's broken-pairing message, which is the
    correct fallback; a caller that can actually make the offer catches this one
    FIRST (FIBR-0019 § 13.3, FIBR-0307 finding 7).
    """


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


class BackupDestinationError(BackupError):
    """An export was pointed at the live vault (or a file beside it that the
    open connection owns), which the final rename would replace. Its own type so
    the window can say so, rather than the size refusal's words (FIBR-0404)."""


class UpdateError(FinbreakError):
    """A recoverable auto-update failure surfaced to the user on an explicit
    **Update now** — an oversize/timed-out/dropped download or a disk error at
    swap (FIBR-0054 INV-10/INV-11). The session stays on the current version."""


class UpdateDownloadError(UpdateError):
    """The update's bytes never fully arrived — a dropped or stalled connection,
    a body shorter than advertised, or one over the size cap (FIBR-0054 INV-10/
    INV-11). Told apart from a bad signature so the user hears "try again", not
    a tamper alarm (full audit 2026-09-27 row 38)."""


class UpdateVerificationError(UpdateError):
    """A downloaded AppImage failed its Ed25519 signature check — the *core*
    integrity gate (FIBR-0054 INV-4). Nothing is installed; the temp is deleted."""
