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
    derive_key,
    load_and_validate_params,
)
from finbreak.errors import VaultLockedError, VaultStateError
from finbreak.models import FORMAT_VERSION, KdfParams
from finbreak.repositories.settings import SettingsRepository
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
ALLOWED_NEGATIVE_STYLES = ("minus", "brackets")
DEFAULT_NEGATIVE_STYLE = "minus"
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

    def first_run(self, password: bytearray, base_currency: str) -> None:
        """Headless convenience: derive then create, in one call (assumes validated)."""
        params = self.new_params()
        raw = derive_raw(password, params)
        self.complete_first_run(raw, params, base_currency)

    def complete_first_run(
        self, raw: bytes, params: KdfParams, base_currency: str
    ) -> None:
        """Main-thread step: create the vault and take ownership of the key."""
        # Copy the derived key into a wipeable buffer BEFORE the presence-state
        # guard, so *every* failure path — including "vault already exists"
        # (two instances racing first-run) — wipes it, not just the create()
        # failure. Previously the guard raised with the key copy un-wiped
        # (INV-3 leak). (indie-review M-auth2)
        key = bytearray(raw)
        try:
            if self._vault.presence_state() != "first_run":
                raise VaultStateError("cannot first-run over an existing vault")
            self._vault.create(
                key, params, base_currency, CURRENCY_EXPONENTS[base_currency]
            )
        except Exception:
            _wipe(key)  # don't leave the key in memory on any failure
            raise
        self._key = key
        self._arm_timer()
        log.info("first-run: vault created")

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
        """Main-thread step: open the vault; ``False`` (no key) on a wrong key."""
        key = bytearray(raw)
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
        raw = bytearray(derive_raw(password, self.load_params()))
        try:
            return hmac.compare_digest(raw, self._key)
        finally:
            _wipe(raw)

    # --- lock / idle / exit ------------------------------------------------ #
    def lock(self) -> None:
        self._stop_timer()
        self._vault.close()
        _wipe(self._key)
        self._key = None
        log.info("locked")

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
