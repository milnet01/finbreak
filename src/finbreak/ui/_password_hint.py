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
    PAYLOAD_INPUT_SYMBOLS,
    PAYLOAD_SYMBOLS,
    decode_payload,
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


def _code_candidates(hint: str) -> list[str]:
    """Every payload-length window in ``hint`` — security-model INV-11's scan.

    The 27-symbol payload is the whole credential (the check symbol is computed
    from it), so every window of ``PAYLOAD_SYMBOLS`` consecutive data-value
    symbols is a candidate, filtered on nothing (FIBR-0308).

    The hint is REASSEMBLED rather than stripped of all whitespace: the user may
    write ``A1B2-C3D4-…`` hyphenated, spaced or across a line break, but
    stripping every space also fused ordinary prose into one long run, which an
    unfiltered scan would pay one derivation per window for. So each
    whitespace-separated piece loses its hyphens; a piece holding a lowercase
    letter is scanned alone, and consecutive pieces holding none — the display
    form is upper case — are joined and scanned together. Only that join test
    reads case; matching is case-insensitive. Sentence-case prose yields
    nothing; a lower-case code written spaced is outside the leg, per INV-11.

    De-duplicated, keeping first-seen order: two identical windows unwrap
    identically, so a repeated one is a second ~46 MiB derivation that can only
    reach the answer the first already gave (FIBR-0310 P12). Uncapped, per
    INV-11: only code-like text (all-caps prose, say) reaches many windows.
    """
    candidates: dict[str, None] = {}

    def scan(text: str) -> None:
        run: list[str] = []
        for char in [*text.upper(), " "]:
            if char in PAYLOAD_INPUT_SYMBOLS:
                run.append(char)
                continue
            symbols = "".join(run)
            run.clear()
            for start in range(len(symbols) - PAYLOAD_SYMBOLS + 1):
                candidates[symbols[start : start + PAYLOAD_SYMBOLS]] = None

    joined: list[str] = []
    for piece in hint.split():
        piece = piece.replace("-", "")
        if any(char.islower() for char in piece):
            scan("".join(joined))
            joined.clear()
            scan(piece)
        else:
            joined.append(piece)
    scan("".join(joined))
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
    scanned for payload windows (``_code_candidates``) and each is
    trial-unwrapped against ``slots.recovery``. A successful unwrap proves the
    hint carries the LIVE code. No candidate — the common case — costs no key
    derivation at all.

    A well-formed but *wrong* code is accepted: it is the unwrap that decides
    (INV-6).
    """
    validate_hint(hint, password)

    candidates = _code_candidates(hint)
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
        # that refusal — ``validate_params`` floors ``time_cost`` and
        # ``parallelism`` at 1 but sets no ceiling (FIBR-0341), so a combination
        # argon2 cannot run (more lanes than the memory holds) is still argon2's
        # to reject. It turns on the params rather than the candidate, so it
        # cannot single one out and the guard covers the whole loop.
        validate_slot(sidecar, SLOT_RECOVERY)
        for candidate in candidates:
            # ``derive_key`` copies its argument in and never touches it, so the
            # decoded code needs a name of its own to be wiped by.
            secret = bytearray(decode_payload(candidate))
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
