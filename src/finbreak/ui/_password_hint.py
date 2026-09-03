"""``QSettings`` adapter for the optional password hint (FIBR-0029 § 3.1).

Persists the user-authored hint in the plaintext ``window.ini`` — the same
pre-unlock store ``ui/_unlock_throttle.py`` uses — under ``hint/text``. It lives
in plaintext (not the vault) because it must be readable **before** the vault is
decrypted (that is exactly when the password is forgotten); ``services/
password_hint.validate_hint`` is what keeps it from being/containing the password.

The I/O is split into this ui adapter (Qt ``QSettings``) so ``AuthService``
(services layer) never imports Qt-ui, mirroring the throttle adapter: the unlock
dialog reads the hint pre-unlock and Settings writes it, so QSettings I/O belongs
in ui. ``.sync()`` after every write so a same-process read-back sees it (matching
``ui/_unlock_throttle.py``). ``read_hint`` needs no key and returns ``""`` when
unset.
"""

from __future__ import annotations

import logging

from argon2.exceptions import HashingError
from PySide6.QtCore import QCoreApplication, QSettings

from finbreak import paths
from finbreak.crypto import derive_key, read_sidecar_v2, validate_slot
from finbreak.errors import KdfPolicyError, KeyUnwrapError
from finbreak.keywrap import SLOT_RECOVERY, unwrap_dek
from finbreak.services.password_hint import HintPolicyError, validate_hint
from finbreak.services.recovery_code import (
    CODE_SYMBOLS,
    INPUT_SYMBOLS,
    decode,
    normalise,
    verify_check_symbol,
)

log = logging.getLogger(__name__)

_HINT_KEY = "hint/text"


def _settings() -> QSettings:
    return QSettings(str(paths.window_settings_path()), QSettings.Format.IniFormat)


def read_hint() -> str:
    """The stored hint, or ``""`` when unset (callable pre-unlock, no key)."""
    value = _settings().value(_HINT_KEY)
    return value if isinstance(value, str) else ""


def write_hint(text: str) -> None:
    settings = _settings()
    settings.setValue(_HINT_KEY, text)
    settings.sync()


def clear_hint() -> None:
    settings = _settings()
    settings.remove(_HINT_KEY)
    settings.sync()


def _code_candidates(normalised_hint: str) -> list[str]:
    """Every ``CODE_SYMBOLS``-long window in ``normalised_hint`` whose check
    symbol verifies locally — the free half of INV-11's test.

    Scans the NORMALISED hint, which is load-bearing: the user holds the code as
    ``A1B2-C3D4-…``, whose longest unbroken symbol run is four, so a scan of the
    raw text finds no 28-symbol candidate and cheerfully accepts a hint that IS
    the recovery code. Runs are split on anything outside the input alphabet, so
    ordinary prose around the code cannot merge with it.

    De-duplicated, keeping first-seen order: two identical windows unwrap
    identically, so a repeated one is a second ~46 MiB derivation that can only
    reach the answer the first already gave (FIBR-0310 P12).

    **There is no cap on top of that, and the absence is measured rather than an
    oversight.** ``MAX_HINT_LEN`` (100) leaves 73 windows, each verifying by
    chance with probability 1/37. Measured 2026-08-25 on this machine: a
    derivation is 26 ms; 20 000 random 100-symbol hints averaged 2.0 candidates
    and peaked at 10, and hill-climbing to maximise the count reached 24 — so
    the crafted worst case is ~0.6 s on the UI thread, against ~50 ms for an
    ordinary hint. A cap would have to sit below 24 to bound anything and above
    10 to never refuse an honest hint, and no value does both.
    """
    candidates: dict[str, None] = {}
    run: list[str] = []
    for char in [*normalised_hint, " "]:
        if char in INPUT_SYMBOLS:
            run.append(char)
            continue
        text = "".join(run)
        run.clear()
        for start in range(len(text) - CODE_SYMBOLS + 1):
            window = text[start : start + CODE_SYMBOLS]
            if verify_check_symbol(window):
                candidates[window] = None
    return list(candidates)


def validate_hint_with_recovery(hint: str, password: str) -> None:
    """``validate_hint``, plus INV-11's recovery-code leg — ``HintPolicyError``.

    Lives here rather than in ``services/password_hint.py`` because that module's
    contract is to be pure (no Qt, no I/O) and the only sidecar locator,
    ``paths.sidecar_path()``, sits in a module importing PySide6. Reaching it
    from the policy module would buy a Qt import, file I/O and a ~46 MiB
    derivation inside the one piece of this feature meant to be testable
    headless (FIBR-0019 § 11).

    The check works **without holding the code**, and that constraint decides its
    shape: INV-5 forbids retaining it, and the hint is set from Settings long
    after the one-time display, so nothing in memory has it. Instead the hint is
    normalised, scanned for a check-symbol-valid candidate, and any candidate is
    trial-unwrapped against ``slots.recovery``. A successful unwrap proves the
    hint carries the LIVE code. No candidate — the common case — costs no key
    derivation at all.

    A well-formed but *wrong* code is accepted: the check symbol proves only that
    it is not a typo, and it is the unwrap that decides (INV-6).
    """
    validate_hint(hint, password)

    candidates = _code_candidates(normalise(hint))
    if not candidates:
        return
    try:
        sidecar = read_sidecar_v2(paths.sidecar_path())
    except (KdfPolicyError, OSError) as exc:
        # A v1 vault, or no readable sidecar: there is no slot to test, so the
        # hint is accepted. Logged because this is a fail-OPEN on a hint that
        # already looked like it carried a code, and it left no trace at all
        # (FIBR-0310 P12). The hint itself is never logged.
        log.warning("hint holds a code-like sequence but no slot to test it: %s", exc)
        return
    if SLOT_RECOVERY not in sidecar.slots:
        return
    params = sidecar.params_for(SLOT_RECOVERY)
    record = sidecar.slots[SLOT_RECOVERY]
    try:
        # ``validate_slot`` is public precisely so the route that USES an
        # optional slot is the one that refuses a damaged one: ``read_sidecar_v2``
        # hard-fails on ``master`` alone, so a damaged ``recovery`` slot loads
        # without complaint (FIBR-0310 R5). ``HashingError`` is the remainder of
        # that refusal — ``validate_params`` bounds only the low side, leaving
        # ``time_cost`` and ``parallelism`` for argon2 itself to reject
        # (FIBR-0327). It turns on the params rather than the candidate, so it
        # cannot single one out and the guard covers the whole loop.
        validate_slot(sidecar, SLOT_RECOVERY)
        for candidate in candidates:
            # ``derive_key`` copies its argument in and never touches it, so the
            # decoded code needs a name of its own to be wiped by.
            secret = bytearray(decode(candidate))
            try:
                kek = derive_key(secret, params.salt, params)
            finally:
                secret[:] = bytes(len(secret))
            try:
                dek = unwrap_dek(kek, record.wrapped, SLOT_RECOVERY, params)
            except KeyUnwrapError:
                continue
            finally:
                kek[:] = bytes(len(kek))
            dek[:] = bytes(len(dek))
            # The message the user reads, so coding.md § 5.2 applies: this
            # module is in ui/ and has no QObject to carry `self.tr`, hence the
            # explicit context. The three sibling messages come from
            # `services/password_hint.py`, which is Qt-free by contract and so
            # cannot translate its own; that is FIBR-0017's to settle.
            raise HintPolicyError(
                QCoreApplication.translate(
                    "PasswordHint", "The hint may not contain your recovery code."
                )
            )
    except (KdfPolicyError, HashingError) as exc:
        # Fails OPEN, like the unreadable-sidecar arm above: a slot that cannot
        # be tested is no evidence the hint carries the code, and barring the
        # user from setting one over a slot they may never use is the worse
        # failure. Logged for the same reason that arm is. ``HintPolicyError``
        # is not a ``FinbreakError`` and so is never caught here.
        log.warning("hint holds a code-like sequence but its slot is damaged: %s", exc)
