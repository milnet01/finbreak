"""AuthService — master password ↔ vault key, and the key's whole lifetime.

The derived key lives in a zeroable ``bytearray`` held only while unlocked and
wiped in place on lock, the auto-lock timeout, and application exit (FIBR-0004
INV-3).
The expensive Argon2id derivation is a pure function (``derive_raw``) so the UI
can run it on a worker thread and hand the raw 32 bytes back for the main thread
to own — every wipe then runs on the one owning thread, no cross-thread race.
"""

from __future__ import annotations

import hmac
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer
from sqlcipher3.dbapi2 import DatabaseError

from finbreak.crypto import (
    ARGON2_MEMORY_KIB,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    KEY_LEN,
    SALT_LEN,
    SlotRecord,
    VaultSidecar,
    derive_key,
    load_and_validate_params,
    new_sidecar,
    read_sidecar_v2,
    sidecar_version,
    validate_slot,
    write_sidecar_v2,
)
from finbreak.errors import (
    KdfPolicyError,
    KeyUnwrapError,
    VaultLockedError,
    VaultStateError,
)
from finbreak.keywrap import SLOT_MASTER, SLOT_RECOVERY, unwrap_dek, wrap_dek
from finbreak.models import FORMAT_VERSION, SIDECAR_VERSION, KdfParams, NegativeStyle
from finbreak.repositories.settings import SettingsRepository
from finbreak.services import vault_migration
from finbreak.services.recovery_code import decode, generate_code, normalise
from finbreak.services.reporting import (
    MODE_CURRENT_MONTH,
    MODE_PREVIOUS_MONTH,
    MODE_SPECIFIC_MONTH,
    MODE_SPECIFIC_YEAR,
    MODE_YEAR_TO_DATE,
    ReportPrefs,
)
from finbreak.vault import Vault

log = logging.getLogger(__name__)

# The offered first-run base currencies, each 2-decimal (D1). ZAR leads so it is
# the default. Extended (incl. 0-/3-decimal currencies) in a later phase.
CURRENCY_EXPONENTS = {"ZAR": 2, "USD": 2, "EUR": 2, "GBP": 2, "AUD": 2, "CAD": 2}

# Display symbol per ISO code — the same 6 currencies as CURRENCY_EXPONENTS (INV-8),
# so "which currencies we support and their properties" stays single-homed here.
# The dollar variants take A$/C$ so they read unambiguously without the Currency
# column (FIBR-0153). ui/_amount.py imports this (a clean one-way ui → services edge).
CURRENCY_SYMBOLS: dict[str, str] = {
    "ZAR": "R",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "AUD": "A$",
    "CAD": "C$",
}

# Idle lock-out timeout measured from unlock — NOT reset on user activity. Now
# user-configurable (FIBR-0055): the value is read from the vault ``settings`` table
# on each arm; DEFAULT applies when the key is absent (a fresh / pre-FIBR-0055 vault)
# or holds a value outside the offered set. True activity-reset idle detection stays
# in FIBR-0014.
DEFAULT_AUTO_LOCK_MINUTES = 10
# 0 == "Never": idle auto-lock off (FIBR-0135, user request — the vault still needs
# the password on open and still locks via the manual Lock button and on exit; only
# the idle timer is disabled). It is listed LAST so a select_combo_data miss / the
# INV-1 fallback resolves to index 0 (the 1-minute floor, the MOST-aggressive lock),
# never to "Never" — a corrupt/absent value must never silently disable the lock.
AUTO_LOCK_NEVER = 0
# The offered choices (minutes); DEFAULT is a member so it always resolves.
ALLOWED_AUTO_LOCK_MINUTES = (1, 5, 10, 15, 30, AUTO_LOCK_NEVER)

# Clipboard auto-clear timeout in seconds (FIBR-0032): how long a copied amount /
# description lingers before ClipboardAutoClear wipes it (if the clipboard still
# holds our value). Read fresh per copy; DEFAULT applies on an absent / non-int /
# out-of-set stored value. 0 == "Never" (copy without auto-clear). The single home
# for both constants — the UI imports them, never redefining.
ALLOWED_CLIPBOARD_CLEAR_SECONDS = (10, 30, 60, 0)
DEFAULT_CLIPBOARD_CLEAR_SECONDS = 30

# The datetime display prefs (FIBR-0083) share one sentinel: "system" means
# resolve dynamically at display time (follow the OS); a concrete value pins it.
DATETIME_SYSTEM = "system"

# Amount display prefs (FIBR-0105) — how the Home Amount column renders negatives.
# Two independent, defaulted keys in the vault ``settings`` table (no schema
# change). Defaults (absent key) are the friendly non-accountant choice.
# Derived from the NegativeStyle StrEnum rather than restated, so the allowed set
# and the enum cannot drift (FIBR-0216).
ALLOWED_NEGATIVE_STYLES = tuple(s.value for s in NegativeStyle)
DEFAULT_NEGATIVE_STYLE = NegativeStyle.MINUS.value
DEFAULT_AMOUNT_COLOUR = True

# The five valid dashboard period modes (FIBR-0012 D2). A stored mode outside this
# set falls back to previous-month in ``report_prefs`` — a corrupt / hand-edited
# value must not crash the dashboard (INV-2).
_REPORT_MODES = frozenset(
    {
        MODE_PREVIOUS_MONTH,
        MODE_CURRENT_MONTH,
        MODE_SPECIFIC_MONTH,
        MODE_YEAR_TO_DATE,
        MODE_SPECIFIC_YEAR,
    }
)


def _parse_optional_int(raw: str | None) -> int | None:
    """An ``int`` from a stored settings string, or ``None`` for an empty / absent
    / non-integer value (the year/month keys are empty strings for relative modes)."""
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@dataclass(frozen=True)
class DateTimePrefs:
    """The user's display prefs — each a stored string (an IANA zone id / a Qt
    format token, or the ``"system"`` sentinel). Frozen: display formatting reads
    but never mutates them (FIBR-0083 INV-1). Persisted by ``AuthService`` in the
    vault ``settings`` table, mirroring ``auto_lock_minutes``."""

    timezone: str
    date_format: str
    time_format: str


@dataclass(frozen=True)
class AmountPrefs:
    """How the Home Amount column renders negatives (FIBR-0105). ``negative_style``
    is ``"minus"`` or ``"brackets"``; ``colour`` toggles red/green direction tint.
    Frozen: the display layer reads but never mutates these (INV-1). Persisted by
    ``AuthService`` in the vault ``settings`` table, mirroring ``DateTimePrefs``."""

    negative_style: str
    colour: bool


def _wipe(buffer: bytearray | None) -> None:
    """Overwrite a secret buffer in place (best-effort; str/bytes can't be wiped)."""
    if buffer:
        buffer[:] = bytes(len(buffer))


def derive_raw(password: bytearray, params: KdfParams) -> bytes:
    """Derive the raw key, wiping both the password and the intermediate buffer.

    Returns immutable ``bytes`` (the transient key crossing back from a worker
    thread); the caller copies it into its own zeroable buffer, per the thread
    model above.
    """
    try:
        derived = derive_key(password, params.salt, params)
        try:
            return bytes(derived)
        finally:
            _wipe(derived)
    finally:
        _wipe(password)


class AuthService:
    def __init__(self, vault_path: Path, sidecar_path: Path):
        self._vault = Vault(vault_path, sidecar_path)
        self._sidecar_path = sidecar_path
        self._key: bytearray | None = None
        self._timer: QTimer | None = None
        # Set when THIS unlock converted a v1 vault (D2), and read exactly once
        # by the shell so it can make D7's offer. Session state, deliberately
        # not persisted: a declined or closed offer costs nothing already done,
        # and re-offering it on every launch would be nagging.
        self._just_migrated = False
        # Invoked after an idle auto-lock so the UI can route away from the now
        # -locked vault (else the next action hits a closed connection). Set by
        # the UI shell; None in headless use.
        self.on_auto_lock: Callable[[], None] | None = None

    @property
    def vault(self) -> Vault:
        return self._vault

    def state(self) -> str:
        return self._vault.presence_state()

    # --- first run --------------------------------------------------------- #
    def validate_first_run(
        self, password: bytearray, confirm: bytearray, base_currency: str
    ) -> None:
        """Form-boundary validation; wipes both password buffers before returning."""
        try:
            if base_currency not in CURRENCY_EXPONENTS:
                raise ValueError(f"unsupported base currency: {base_currency!r}")
            if len(password) == 0:
                raise ValueError("password must not be empty")
            if password != confirm:
                raise ValueError("passwords do not match")
        finally:
            _wipe(password)
            _wipe(confirm)

    def new_params(self) -> KdfParams:
        return KdfParams(
            format_version=FORMAT_VERSION,
            memory_kib=ARGON2_MEMORY_KIB,
            time_cost=ARGON2_TIME_COST,
            parallelism=ARGON2_PARALLELISM,
            key_len=KEY_LEN,
            salt_len=SALT_LEN,
            salt=secrets.token_bytes(SALT_LEN),
        )

    def first_run(self, password: bytearray, base_currency: str) -> str:
        """Headless convenience: derive then create, in one call (assumes validated).

        Returns the display-form recovery code for the one-time § 4.5 step 8
        display. Nothing else can learn it — INV-5 forbids retaining it — so the
        caller either hands it to the user now or it is gone.
        """
        params = self.new_params()
        raw = derive_raw(password, params)
        return self.complete_first_run(raw, params, base_currency)

    def complete_first_run(
        self, raw: bytes, params: KdfParams, base_currency: str
    ) -> str:
        """Main-thread step: build the key envelope, create the vault, take the DEK.

        ``raw`` is KEK-**master** — the Argon2id output over the user's password
        and ``params.salt``. It is no longer the database key: SQLCipher gets a
        random DEK, and the KEK only wraps it (FIBR-0019 § 4.5, INV-1).

        Returns the display-form recovery code (step 8). The code is generated
        here and retained nowhere, so this return is the only route by which
        anything can learn it (INV-5). Its slot is NOT written: that is step 9,
        on Keep, and is :meth:`add_recovery_key` — declining is simply never
        calling it, which is what keeps a declined code's slot off disk (INV-12).
        """
        # Copy the derived key into a wipeable buffer BEFORE the presence-state
        # guard, so *every* failure path — including "vault already exists"
        # (two instances racing first-run) — wipes it, not just the create()
        # failure. Previously the guard raised with the key copy un-wiped
        # (INV-3 leak). (indie-review M-auth2)
        kek_master = bytearray(raw)
        # A bytearray, not bytes: security-model.md INV-3 requires a wipeable
        # buffer, and this one is SQLCipher's raw key for the vault's whole life.
        dek = bytearray(secrets.token_bytes(KEY_LEN))
        code = generate_code()
        try:
            if self._vault.presence_state() != "first_run":
                raise VaultStateError("cannot first-run over an existing vault")
            # write_sidecar=False: create() would serialise the flat v1 record,
            # which does not describe this vault at all. The sidecar is step 7's
            # alone, and writing it last preserves the vault-before-sidecar
            # create order (FIBR-0004 INV-5).
            self._vault.create(
                dek,
                params,
                base_currency,
                CURRENCY_EXPONENTS[base_currency],
                write_sidecar=False,
            )
            wrapped = wrap_dek(kek_master, bytes(dek), SLOT_MASTER, params)
            write_sidecar_v2(
                self._sidecar_path,
                new_sidecar(
                    params, {SLOT_MASTER: SlotRecord.from_wrap(params.salt, wrapped)}
                ),
            )
        except Exception:
            _wipe(dek)  # don't leave the key in memory on any failure
            raise
        finally:
            _wipe(kek_master)
        self._key = dek
        self._arm_timer()
        log.info("first-run: vault created with a key envelope")
        return code

    # --- recovery key (FIBR-0019) ------------------------------------------ #
    def read_sidecar(self) -> VaultSidecar:
        """The v2 sidecar, or ``VaultStateError`` if this vault is still v1.

        Every slot operation below goes through this rather than caching it: the
        file is the single source of truth for what slots exist, and a cached
        copy would let an Add race a Remove.
        """
        if sidecar_version(self._sidecar_path) != SIDECAR_VERSION:
            raise VaultStateError("this vault has not been migrated to the envelope")
        return read_sidecar_v2(self._sidecar_path)

    def has_recovery_key(self) -> bool:
        """Whether ``slots.recovery`` is on disk — what gates the § 4.6 route and
        the § 4.7 Add / Replace / Remove affordances."""
        try:
            return SLOT_RECOVERY in self.read_sidecar().slots
        except (VaultStateError, KdfPolicyError):
            return False

    def recovery_params(self) -> KdfParams:
        """The KDF record the recovery route derives under — the shared costs
        against ``slots.recovery``'s own salt."""
        sidecar = self.read_sidecar()
        if SLOT_RECOVERY not in sidecar.slots:
            raise VaultStateError("this vault has no recovery key")
        # `read_sidecar_v2` hard-fails on `master` alone, so a damaged recovery
        # slot loads (FIBR-0310 R5) and this is the recovery route's first look
        # at it. Refusing HERE rather than after the derive is what keeps the
        # two answers apart for the caller: "no recovery key" is a
        # VaultStateError and "the record is damaged" a KdfPolicyError, and the
        # UI has a different sentence for each.
        validate_slot(sidecar, SLOT_RECOVERY)
        return sidecar.params_for(SLOT_RECOVERY)

    def add_recovery_key(self, code: str) -> None:
        """Wrap the session's DEK into ``slots.recovery`` and rewrite the sidecar.

        § 4.5 step 9 (Keep), and § 4.7's Add and Replace — Replace is this call
        over an existing slot, which invalidates the previous code by overwriting
        the only copy of the DEK it wrapped. A re-wrap of 32 bytes: the database
        is untouched and the DEK does not change, which is what makes adding a
        recovery key to an existing vault cheap rather than a re-encrypt (D3).

        What Argon2id is fed is the DECODED 17-byte payload, never the text
        (§ 4.3) — the same input § 4.6's unlock and INV-11's trial-unwrap use, or
        a slot written by one would be unopenable by another.
        """
        self._write_slot(SLOT_RECOVERY, bytearray(decode(normalise(code))))

    def remove_recovery_key(self) -> None:
        """§ 4.7 Remove — delete ``slots.recovery`` and rewrite the sidecar.

        The vault keeps opening on the master password; what is given up is the
        second route, and the UI says so plainly before calling this.
        """
        if self._key is None:
            raise VaultLockedError("the vault is locked")
        write_sidecar_v2(
            self._sidecar_path, self.read_sidecar().without_slot(SLOT_RECOVERY)
        )
        log.info("recovery key removed")

    def set_master_password(self, password: bytearray) -> None:
        """Re-derive KEK-master against a FRESH salt and re-wrap the same DEK into
        ``slots.master`` (§ 4.6 step 4). The DEK does not change, so nothing is
        re-encrypted; afterwards the old password no longer opens the vault."""
        self._write_slot(SLOT_MASTER, password)

    def _write_slot(self, slot: str, secret: bytearray) -> None:
        """Derive a KEK from ``secret`` against a FRESH salt, wrap the session's
        DEK into ``slot``, and rewrite the sidecar atomically.

        The one implementation behind every credential change (§ 4.7: "all three
        are re-wraps"). ``secret`` is wiped here — ``derive_raw`` owns it.
        """
        if self._key is None:
            raise VaultLockedError("the vault is locked")
        sidecar = self.read_sidecar()
        # The new slot inherits this vault's recorded costs, not today's pin: a
        # migrated vault's slots must stay derivable under one schedule (§ 13.1).
        params = sidecar.params_with_salt(secrets.token_bytes(SALT_LEN))
        kek = bytearray(derive_raw(secret, params))
        try:
            wrapped = wrap_dek(kek, bytes(self._key), slot, params)
        finally:
            _wipe(kek)
        write_sidecar_v2(
            self._sidecar_path,
            sidecar.with_slot(slot, SlotRecord.from_wrap(params.salt, wrapped)),
        )
        log.info("re-wrapped the %s slot", slot)

    # --- unlock ------------------------------------------------------------ #
    def load_params(self) -> KdfParams:
        return load_and_validate_params(self._sidecar_path)

    def unlock(self, password: bytearray) -> bool:
        """Headless convenience: validate sidecar → derive → open, in one call."""
        try:
            params = self.load_params()
        except Exception:
            _wipe(password)
            raise
        raw = derive_raw(password, params)
        return self.complete_unlock(raw)

    def complete_unlock(self, raw: bytes) -> bool:
        """Main-thread step: open the vault; ``False`` (no key) on a wrong key.

        ``raw`` is what the sidecar's shape says it is (FIBR-0019 § 4.4): for a
        **v2** vault it is KEK-master, which unwraps ``slots.master`` to the DEK
        SQLCipher actually takes; for a **v1** vault it is still the database key
        itself, and a successful open is followed by § 13's conversion (D2).
        """
        if sidecar_version(self._sidecar_path) == SIDECAR_VERSION:
            return self._unlock_through_slot(bytearray(raw), SLOT_MASTER)
        return self._unlock_v1(bytearray(raw))

    def complete_recovery_unlock(self, raw: bytes) -> bool:
        """The § 4.6 recovery route's main-thread step — ``raw`` is KEK-recovery.

        Identical to the password route but for which slot it reads. The forced
        new master password (D6) is the caller's next step, not this one's: this
        opens the vault, and :meth:`set_master_password` is what leaves the user
        with a working credential.
        """
        return self._unlock_through_slot(bytearray(raw), SLOT_RECOVERY)

    def _unlock_through_slot(self, kek: bytearray, slot: str) -> bool:
        """Unwrap ``slot`` with ``kek`` and open the vault with the resulting DEK.

        A ``KeyUnwrapError`` is reported as an ordinary failed attempt with no
        distinction between a wrong credential and a tampered slot — the caller
        cannot act differently on the two, and an error that told them apart
        would be an oracle (§ 4.2, § 6).

        ``validate_slot`` runs here rather than only at load because
        ``read_sidecar_v2`` hard-fails on `master` alone: an optional slot's
        damage must not bar the routes that still work (FIBR-0310 R5). So the
        route that USES a slot is what refuses a malformed one, with FIBR-0307
        finding 9's distinct ``KdfPolicyError`` — "this record is damaged"
        rather than the throttled "wrong credential" the unwrap below would
        give. `master` reaches this having already been checked; the second run
        is two length comparisons on plaintext and buys one code path.
        """
        try:
            sidecar = read_sidecar_v2(self._sidecar_path)
            if slot not in sidecar.slots:
                return False
            validate_slot(sidecar, slot)
            try:
                dek = unwrap_dek(
                    kek,
                    sidecar.slots[slot].wrapped,
                    slot,
                    sidecar.params_for(slot),
                )
            except KeyUnwrapError:
                log.info("unlock failed")
                return False
            try:
                # § 13.3 step 0 is the branch above: the ladder is entered only
                # once the slot has unwrapped, so a mistyped password is a
                # failed attempt rather than a user told their vault is corrupt.
                if sidecar.migration_pending:
                    vault_migration.resume(
                        self._vault.vault_path, self._sidecar_path, kek, dek
                    )
                    sidecar = read_sidecar_v2(self._sidecar_path)
            except Exception:
                # The DEK is live key material from the unwrap above, and every
                # route out of here that is not _open_with owns wiping it —
                # § 13.3's terminal branch is a ROUTINE outcome, not a crash, so
                # this is the ordinary path (security-model INV-3, FP02 f.5).
                _wipe(dek)
                raise
        finally:
            _wipe(kek)
        return self._open_with(dek, sidecar.cipher_compatibility)

    def restore_pre_upgrade_copy(self) -> None:
        """Put D8's pre-upgrade pair back, after the user accepted the offer.

        The answer to a :class:`RollbackAvailableError` — § 13.3's terminal
        branch with a verified ``.pre-v2`` pair beside the vault. Afterwards the
        pair on disk is v1 again, so the next unlock takes the ordinary v1 route
        and converts it afresh (D2).

        Deliberately does NOT unlock: the vault is opened by the user typing
        their password at the dialog, which is the same step as every other
        unlock and keeps the key material out of this recovery path
        (FIBR-0019 § 13.3, FIBR-0307 finding 7).
        """
        vault_migration.restore_rollback_copy(
            self._vault.vault_path, self._sidecar_path
        )

    def _unlock_v1(self, key: bytearray) -> bool:
        """Open a pre-envelope vault, then convert it (D2).

        Every vault in the field migrates at its next successful unlock, because
        two key schedules in the field is the thing FIBR-0019 exists to avoid.
        A failed conversion never costs the user their session: nothing is
        swapped until § 13.2's S4, so the branch below re-opens exactly what was
        there and the attempt simply repeats at the next unlock.
        """
        try:
            self._vault.open(key)
        except DatabaseError:
            _wipe(key)
            log.info("unlock failed")
            return False
        except Exception:
            # Any other open failure (e.g. a newer-than-supported vault raising
            # SchemaVersionError from the migration runner) must still wipe the
            # derived key before propagating — never leave it in memory (INV-3).
            _wipe(key)
            raise
        try:
            self._vault.close()
            vault_migration.migrate_to_v2(
                self._vault.vault_path, self._sidecar_path, key
            )
        except Exception:
            log.exception("key-envelope migration failed")
            if sidecar_version(self._sidecar_path) != SIDECAR_VERSION:
                # Nothing was swapped, so the vault is exactly as it was.
                return self._open_with(key, None)
            # The sidecar was already replaced when the failure landed, which is
            # § 13.3's window — the resume ladder owns it from here.
            return self._unlock_through_slot(key, SLOT_MASTER)
        sidecar = read_sidecar_v2(self._sidecar_path)
        try:
            dek = unwrap_dek(
                key,
                sidecar.slots[SLOT_MASTER].wrapped,
                SLOT_MASTER,
                sidecar.params_for(SLOT_MASTER),
            )
        finally:
            _wipe(key)
        log.info("vault migrated to the key envelope")
        self._just_migrated = True
        return self._open_with(dek, sidecar.cipher_compatibility)

    def consume_migration_notice(self) -> bool:
        """``True`` once if this unlock converted a v1 vault (D2/D7).

        Every vault in the field is exactly the population this feature exists
        for, so leaving them to discover Settings' *Add* would ship the recovery
        key to nobody who already has data. The offer comes AFTER the migration
        rather than before, so a declined offer or a closed window costs nothing
        already done.
        """
        notice, self._just_migrated = self._just_migrated, False
        return notice

    def _open_with(self, key: bytearray, cipher_compat: int | None) -> bool:
        """Open the vault with ``key`` and take ownership of it.

        Every caller arrives here with the credential already PROVEN: the slot
        unwrapped (:meth:`_unlock_through_slot`), or the key has already opened
        this same database once (:meth:`_unlock_v1`). A wrong password is
        rejected before this point and never reaches it.

        So a ``DatabaseError`` here is not a failed attempt — it is § 6's broken
        pairing: the sidecar and the database do not belong together, or the
        database is damaged. Returning ``False`` reported it as a wrong password,
        which charged the throttle for a correct one and put the destructive
        reset in front of a user whose data was intact and merely mispaired.
        § 6 forbids that by name, and ``ui/unlock.py``'s ``_PAIRING_BROKEN`` is
        written for this state and keys on ``VaultStateError`` (FIBR-0307
        finding 2).
        """
        try:
            self._vault.open(key, cipher_compat=cipher_compat)
        except DatabaseError as exc:
            _wipe(key)
            log.warning("the unwrapped key did not open the vault")
            raise VaultStateError(
                "the key record unwrapped but the vault file did not open"
            ) from exc
        except Exception:
            _wipe(key)
            raise
        self._key = key
        self._arm_timer()
        log.info("unlocked")
        return True

    def verify_password(self, password: bytearray) -> bool:
        """True iff ``password`` derives the key this vault was unlocked with.

        Re-runs the pinned KDF and compares in constant time (FIBR-0029 § 3.5) —
        used to authorize a within-session change (setting the password hint). It
        verifies the key **the session was unlocked with** (``self._key``), not the
        vault's current on-disk password: a mid-session re-key (a backup restore)
        makes even the new correct password mismatch, returning ``False`` — a
        fail-closed outcome (nothing bad is written).

        Buffer discipline mirrors ``derive_raw`` / ``validate_first_run``: the KDF
        consumes ``password`` (``derive_raw`` wipes it) and the caller wipes it
        again in a ``finally``; the derived key copied here is wiped in place.
        """
        if self._key is None:
            raise VaultLockedError("the vault is locked")
        params = self.load_params()
        raw = bytearray(derive_raw(password, params))
        try:
            if sidecar_version(self._sidecar_path) != SIDECAR_VERSION:
                return hmac.compare_digest(raw, self._key)
            # Under the envelope the derived value is KEK-master, not the key the
            # session holds — comparing the two directly would refuse the correct
            # password on every v2 vault. Unwrap first, then compare the DEKs.
            sidecar = read_sidecar_v2(self._sidecar_path)
            try:
                dek = unwrap_dek(
                    raw,
                    sidecar.slots[SLOT_MASTER].wrapped,
                    SLOT_MASTER,
                    sidecar.params_for(SLOT_MASTER),
                )
            except KeyUnwrapError:
                return False
            try:
                return hmac.compare_digest(dek, self._key)
            finally:
                _wipe(dek)
        finally:
            _wipe(raw)

    # --- lock / idle / exit ------------------------------------------------ #
    def lock(self) -> None:
        self._stop_timer()
        self._vault.close()
        _wipe(self._key)
        self._key = None
        log.info("locked")

    def reset_vault(self) -> None:
        """Irreversibly delete the vault and its on-disk data footprint (DB, KDF
        sidecar, and both SQLite WAL sidecars), then leave the service in a locked,
        first-run state (FIBR-0030). Safe to call while locked — the unlock screen
        is the only caller, so the vault is typically never-unlocked when this runs."""
        self.lock()  # idempotent when already locked; releases any DB handle so the
        # unlink is Windows-safe, and wipes self._key if one is held.
        vault_path = self._vault.vault_path
        sidecar_path = self._vault.sidecar_path
        for path in (
            vault_path,
            sidecar_path,
            # SQLite runs in WAL mode (vault.py create/open), so it writes
            # `<db>-wal` and `<db>-shm` sidecars beside the DB. They hold the
            # vault's most recent (encrypted) transactions — part of the user's
            # data — and no path helper names them, so nothing else unlinks them.
            # "Start over" removes them too: so no fragment of the old vault
            # survives, and so an orphaned -wal can't interact with the next,
            # differently keyed vault created at first-run.
            vault_path.with_name(vault_path.name + "-wal"),
            vault_path.with_name(vault_path.name + "-shm"),
        ):
            path.unlink(missing_ok=True)
        log.info("vault reset")

    def _on_idle_timeout(self) -> None:
        if self._key is None:
            return  # already locked — a stale queued fire must not disturb the UI
        self.lock()
        if self.on_auto_lock is not None:
            self.on_auto_lock()

    def on_about_to_quit(self) -> None:
        """Wipe on shutdown; a no-op when already locked (no key held)."""
        self._stop_timer()
        self._vault.close()
        _wipe(self._key)
        self._key = None

    def _arm_timer(self) -> None:
        # Only meaningful with a running event loop; headless tests invoke the
        # timeout handler directly instead of waiting on the clock.
        if QCoreApplication.instance() is None:
            return
        if self._timer is None:
            self._timer = QTimer()
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._on_idle_timeout)
        minutes = self.auto_lock_minutes()
        if minutes == AUTO_LOCK_NEVER:
            self._timer.stop()  # "Never" — no idle lock (FIBR-0135); manual lock holds
            return
        self._timer.start(minutes * 60 * 1000)

    def notify_activity(self) -> None:
        """Reset the idle-lock countdown on user interaction, so the timeout is
        measured from the LAST activity rather than from unlock — an inactivity
        timer (FIBR-0114). Restarts the running timer with the interval set at arm
        time; deliberately does **not** re-read the setting, since this fires on
        every input event. A no-op when locked (no key) or headless (no timer).
        The ``isActive()`` guard means "Never" (a stopped timer, FIBR-0135) stays
        off — activity must not silently re-arm an idle-lock the user disabled."""
        if self._key is not None and self._timer is not None and self._timer.isActive():
            self._timer.start()  # restart from now, reusing the armed interval

    # --- auto-lock timeout config (FIBR-0055) ------------------------------ #
    def auto_lock_minutes(self) -> int:
        """The configured idle-lock timeout in minutes, read from the vault
        settings. Falls back to ``DEFAULT_AUTO_LOCK_MINUTES`` for an absent key, a
        non-integer stored value, or a value outside ``ALLOWED_AUTO_LOCK_MINUTES`` —
        a corrupt / hand-edited value must not weaken or crash the lock (INV-1)."""
        raw = SettingsRepository(self._vault.connection).get("auto_lock_minutes")
        if raw is None:
            return DEFAULT_AUTO_LOCK_MINUTES
        try:
            minutes = int(raw)
        except ValueError:
            return DEFAULT_AUTO_LOCK_MINUTES
        return (
            minutes
            if minutes in ALLOWED_AUTO_LOCK_MINUTES
            else DEFAULT_AUTO_LOCK_MINUTES
        )

    def set_auto_lock_minutes(self, minutes: int) -> None:
        """Validate, persist, then re-arm the running timer (INV-2). Rejects a value
        outside ``ALLOWED_AUTO_LOCK_MINUTES`` before any write; a locked vault raises
        ``VaultLockedError`` from ``Vault.connection`` (INV-7 defence in depth)."""
        if minutes not in ALLOWED_AUTO_LOCK_MINUTES:
            raise ValueError(
                f"auto-lock timeout must be one of {ALLOWED_AUTO_LOCK_MINUTES}"
            )
        SettingsRepository(self._vault.connection).set(
            "auto_lock_minutes", str(minutes)
        )
        self._arm_timer()

    # --- clipboard auto-clear config (FIBR-0032) --------------------------- #
    def clipboard_clear_seconds(self) -> int:
        """The configured clipboard auto-clear timeout in seconds, read from the
        vault settings. Falls back to ``DEFAULT_CLIPBOARD_CLEAR_SECONDS`` for an
        absent key, a non-integer stored value, or a value outside
        ``ALLOWED_CLIPBOARD_CLEAR_SECONDS`` (INV-5)."""
        raw = SettingsRepository(self._vault.connection).get("clipboard_clear_seconds")
        if raw is None:
            return DEFAULT_CLIPBOARD_CLEAR_SECONDS
        try:
            seconds = int(raw)
        except ValueError:
            return DEFAULT_CLIPBOARD_CLEAR_SECONDS
        return (
            seconds
            if seconds in ALLOWED_CLIPBOARD_CLEAR_SECONDS
            else DEFAULT_CLIPBOARD_CLEAR_SECONDS
        )

    def set_clipboard_clear_seconds(self, seconds: int) -> None:
        """Validate then persist the clipboard auto-clear timeout. Rejects a value
        outside ``ALLOWED_CLIPBOARD_CLEAR_SECONDS`` before any write (INV-5); a locked
        vault raises ``VaultLockedError`` from ``Vault.connection``, guarded
        dialog-side like auto-lock. Unlike ``set_auto_lock_minutes`` there is no live
        timer to re-arm — the timeout is read fresh per copy (D3)."""
        if seconds not in ALLOWED_CLIPBOARD_CLEAR_SECONDS:
            raise ValueError(
                f"clipboard clear timeout must be one of "
                f"{ALLOWED_CLIPBOARD_CLEAR_SECONDS}"
            )
        SettingsRepository(self._vault.connection).set(
            "clipboard_clear_seconds", str(seconds)
        )

    # --- datetime display prefs config (FIBR-0083) ------------------------- #
    def datetime_prefs(self) -> DateTimePrefs:
        """Read the three display prefs from the vault settings, each defaulting
        to ``"system"`` when absent (a fresh / pre-FIBR-0083 vault). The
        ``"system"`` sentinel is kept verbatim — expanded to a concrete
        zone/locale only at display time (D4)."""
        repo = SettingsRepository(self._vault.connection)
        return DateTimePrefs(
            timezone=repo.get("timezone") or DATETIME_SYSTEM,
            date_format=repo.get("date_format") or DATETIME_SYSTEM,
            time_format=repo.get("time_format") or DATETIME_SYSTEM,
        )

    def set_datetime_prefs(self, prefs: DateTimePrefs) -> None:
        """Persist the three display prefs (mirrors ``set_auto_lock_minutes``). A
        locked vault raises ``VaultLockedError`` from ``Vault.connection`` — the
        write is guarded dialog-side, like auto-lock (INV-5 defence in depth)."""
        repo = SettingsRepository(self._vault.connection)
        repo.set("timezone", prefs.timezone)
        repo.set("date_format", prefs.date_format)
        repo.set("time_format", prefs.time_format)

    # --- amount display prefs config (FIBR-0105) --------------------------- #
    def amount_prefs(self) -> AmountPrefs:
        """Read the two amount-display prefs from the vault settings. Each falls
        back to its default independently (INV-5): an ``amount_negative_style``
        outside ``ALLOWED_NEGATIVE_STYLES`` resolves to ``"minus"``; an
        ``amount_colour`` that isn't exactly ``"true"`` / ``"false"`` resolves to
        ON — a bad/absent stored value never crashes the display."""
        repo = SettingsRepository(self._vault.connection)
        style = repo.get("amount_negative_style")
        if style not in ALLOWED_NEGATIVE_STYLES:
            style = DEFAULT_NEGATIVE_STYLE
        stored_colour = repo.get("amount_colour")
        if stored_colour in ("true", "false"):
            colour = stored_colour == "true"
        else:
            colour = DEFAULT_AMOUNT_COLOUR
        return AmountPrefs(negative_style=style, colour=colour)

    def set_amount_prefs(self, prefs: AmountPrefs) -> None:
        """Persist both amount-display prefs (mirrors ``set_datetime_prefs``); the
        bool ``colour`` is stored as the ``"true"`` / ``"false"`` token. A locked
        vault raises ``VaultLockedError`` from ``Vault.connection`` — guarded
        dialog-side, like auto-lock (INV-2 defence in depth)."""
        repo = SettingsRepository(self._vault.connection)
        repo.set("amount_negative_style", prefs.negative_style)
        repo.set("amount_colour", "true" if prefs.colour else "false")

    # --- dashboard period prefs config (FIBR-0012) ------------------------- #
    def report_prefs(self) -> ReportPrefs:
        """Read the persisted dashboard period from the vault settings, mirroring
        ``amount_prefs`` / ``datetime_prefs`` — each of the three keys parsed
        defensively (INV-2). An unknown ``report_period_mode`` → previous-month;
        an empty / absent / non-int ``year`` / ``month`` → ``None``; a year outside
        1–9999 or a month outside 1–12 → ``None`` (either would make
        ``resolve_period``'s ``date(...)`` raise). A **specific** mode read back with
        its required field missing / unparseable / out-of-range downgrades to
        previous-month, so ``resolve_period`` never sees a specific mode with a
        ``None`` field (D2)."""
        repo = SettingsRepository(self._vault.connection)
        mode = repo.get("report_period_mode")
        if mode not in _REPORT_MODES:
            return ReportPrefs(MODE_PREVIOUS_MONTH)
        # Bound BOTH fields to date-constructible ranges (year 1–9999, month 1–12):
        # an out-of-range year (0 / negative / >9999) parses as an int but would make
        # resolve_period's date(...) raise, so it must downgrade like a missing field
        # (INV-2 "never an error"), not just a bad month.
        raw_year = _parse_optional_int(repo.get("report_period_year"))
        year = raw_year if raw_year is not None and 1 <= raw_year <= 9999 else None
        raw_month = _parse_optional_int(repo.get("report_period_month"))
        month = raw_month if raw_month is not None and 1 <= raw_month <= 12 else None
        if mode == MODE_SPECIFIC_MONTH and (year is None or month is None):
            return ReportPrefs(MODE_PREVIOUS_MONTH)
        if mode == MODE_SPECIFIC_YEAR and year is None:
            return ReportPrefs(MODE_PREVIOUS_MONTH)
        return ReportPrefs(mode=mode, year=year, month=month)

    def set_report_prefs(self, prefs: ReportPrefs) -> None:
        """Persist the dashboard period across the three ``settings`` keys (mirrors
        ``set_amount_prefs``). ``year`` / ``month`` are written as **empty strings**
        for a mode that carries neither (the three relative modes), so the
        round-trip is total (INV-2). A locked vault raises ``VaultLockedError`` from
        ``Vault.connection`` — guarded dialog-side, like auto-lock."""
        repo = SettingsRepository(self._vault.connection)
        repo.set("report_period_mode", prefs.mode)
        repo.set("report_period_year", "" if prefs.year is None else str(prefs.year))
        repo.set("report_period_month", "" if prefs.month is None else str(prefs.month))

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()
