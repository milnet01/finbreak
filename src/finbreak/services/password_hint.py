"""Password-hint enforcement — the pure, Qt-free policy (FIBR-0029 § 3.4).

The hint lives in plaintext ``window.ini`` (``ui/_password_hint.py`` does the I/O),
so it must never be, nor contain, the master password — otherwise the "hint" is a
plaintext copy of the secret. This module is the single authoritative gate for
that, kept pure (no Qt, no I/O) so it is testable without a display — the same
math-vs-I/O split as ``services/unlock_throttle.py`` vs ``ui/_unlock_throttle.py``.

Comparison is Unicode-correct: both sides are NFC-normalized then **casefolded**
(not ``.lower()``), so a hint that is the password in a different case OR a
different Unicode normal form is still caught. Containment runs **unconditionally**
— no password-length carve-out — so a short password embedded verbatim is always
rejected (this is what makes ``security-model.md`` INV-11 true as written). The
guarantee is against *verbatim* inclusion; a user who deliberately obfuscates their
own hint (internal spaces, zero-width chars, homoglyphs) is out of scope (§ 3.4).
"""

from __future__ import annotations

import unicodedata

MAX_HINT_LEN = 100


class HintPolicyError(Exception):
    """The proposed hint violates policy (too long, or is/contains the password).

    Its message names the specific reason so the caller can surface it inline.
    """


def _norm(value: str) -> str:
    """NFC-normalize then casefold — the Unicode-correct case/normal-form fold."""
    return unicodedata.normalize("NFC", value).casefold()


def validate_hint(hint: str, password: str) -> None:
    """Raise ``HintPolicyError`` if the hint is unusable.

    A blank hint (empty / whitespace-only) is caller-handled as "clear", not
    passed here. ``password`` is a plaintext ``str`` (the check is Unicode string
    logic, and ``QLineEdit.text()`` already produced one); the wipeable KDF
    ``bytearray`` is used only by ``AuthService.verify_password`` (§ 3.5).
    """
    if len(hint) > MAX_HINT_LEN:
        raise HintPolicyError(f"The hint must be {MAX_HINT_LEN} characters or fewer.")
    normalized_hint = _norm(hint)
    normalized_password = _norm(password)
    # Equality is subsumed by containment (if H.strip() == P then P in H); it is
    # kept ONLY for the friendlier "may not BE your password" message (§ 3.4).
    if normalized_hint.strip() == normalized_password:
        raise HintPolicyError("The hint may not be your password.")
    if normalized_password in normalized_hint:
        raise HintPolicyError("The hint may not contain your password.")
