"""Crockford base32 recovery codes — generate, format, normalise, check, decode
(FIBR-0019 § 4.3).

Pure and Qt-free, so it is testable headless. Three properties the
implementation honours, each of which ``tests/features/recovery_key/`` locks:

* **The check symbol's alphabet is 37 symbols, not 32** — the 32 data symbols
  plus ``*``, ``~``, ``$``, ``=`` and ``U``. 37 is the least prime above 32 and
  is what gives the check its detection properties; a mod-32 check is a
  different, weaker construction.
* **Normalisation removes hyphens, spaces and case ONLY.** Stripping ``*~$=``
  would destroy the very symbol the check is there to read.
* **What is fed to Argon2id is the DECODED value, never the text** — the
  135-bit payload as 17 fixed-width big-endian bytes, check symbol excluded.
  Crockford decodes ``I``/``L`` to ``1`` and ``O`` to ``0``, so deriving from
  the normalised string would refuse a code the user transcribed correctly.
"""

from __future__ import annotations

import secrets

# Crockford's DATA alphabet: 32 symbols, excluding I, L, O and U (§ 4.3).
DATA_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
# The CHECK alphabet: the 32 data symbols plus five more, U among them. A
# code's last group may legitimately read `RST$` or `RSTU`.
CHECK_ALPHABET = DATA_ALPHABET + "*~$=U"

PAYLOAD_BITS = 135
PAYLOAD_SYMBOLS = 27
PAYLOAD_BYTES = 17
CODE_SYMBOLS = PAYLOAD_SYMBOLS + 1
GROUP_SIZE = 4

# Crockford decoding is case-insensitive and folds the three characters left out
# of the DATA alphabet for being confusable: ``I``/``L`` read as ``1``, ``O`` as
# ``0``. That fold is the whole reason § 4.3 chose this alphabet, and it is why
# the KDF is fed ``decode()``'s output and never the text — a correctly
# transcribed ``AIB2…`` and the printed ``A1B2…`` must derive the SAME key.
_DECODE = {symbol: value for value, symbol in enumerate(DATA_ALPHABET)}
_DECODE.update({"I": 1, "L": 1, "O": 0})

# Every character a user may legitimately type as part of a code, once
# normalised — the data alphabet, the three folded stand-ins, and the four
# punctuation check symbols. Used to find candidate runs inside free text
# (INV-11); never to validate one, which is `verify_check_symbol`'s job.
INPUT_SYMBOLS = frozenset(DATA_ALPHABET + "ILOU*~$=")

# The check symbol is taken modulo the size of the CHECK alphabet — 37, the
# least prime above 32, which is what gives it its detection properties.
_CHECK_MODULUS = len(CHECK_ALPHABET)

# Crockford's fold applies to the 28th symbol exactly as it does to the payload:
# a printed ``1`` may be transcribed ``I`` or ``L``, a printed ``0`` as ``O``.
# So the check is read as a VALUE, never compared as a character — comparing
# characters refuses a code the user transcribed correctly, and (because INV-11's
# hint scan gates on the same call) lets that same form past the guard and into
# plaintext ``window.ini`` (FIBR-0307 finding 1). I/L/O are not themselves legal
# check symbols, so folding them only ever accepts strings that were previously
# rejected outright; it cannot accept a wrong check value.
_CHECK_DECODE = {symbol: value for value, symbol in enumerate(CHECK_ALPHABET)}
_CHECK_DECODE.update({"I": 1, "L": 1, "O": 0})


def _payload_int(payload: str) -> int:
    """The integer ``payload``'s data symbols encode, folding I/L/O and case."""
    value = 0
    for symbol in payload.upper():
        try:
            value = value * len(DATA_ALPHABET) + _DECODE[symbol]
        except KeyError:
            raise ValueError(f"not a Crockford data symbol: {symbol!r}") from None
    return value


def generate_code() -> str:
    """A fresh 135-bit code in display form — seven hyphen-separated groups of
    four, the 28th symbol being the mod-37 check symbol."""
    value = secrets.randbits(PAYLOAD_BITS)
    symbols = []
    for _ in range(PAYLOAD_SYMBOLS):
        symbols.append(DATA_ALPHABET[value & 0x1F])
        value >>= 5
    payload = "".join(reversed(symbols))
    return format_code(payload + check_symbol(payload))


def format_code(symbols: str) -> str:
    """Group ``symbols`` four at a time, hyphen-separated (the display form)."""
    return "-".join(
        symbols[i : i + GROUP_SIZE] for i in range(0, len(symbols), GROUP_SIZE)
    )


def normalise(text: str) -> str:
    """Strip hyphens, spaces and case — and nothing else (§ 4.3 Input).

    Deliberately does NOT fold ``I``/``L``/``O`` and does NOT strip ``*~$=``:
    the fold belongs to :func:`decode` (so a normalised payload still reads as
    the user typed it), and stripping the punctuation would destroy the very
    check symbol it is there to read.
    """
    return "".join(ch for ch in text.upper() if not ch.isspace() and ch != "-")


def check_symbol(payload: str) -> str:
    """The mod-37 check symbol for a 27-symbol normalised payload.

    ``ValueError`` on any other length. The docstring said "27-symbol" and the
    body checked nothing, so a caller passing a whole 28-symbol code -- the
    easiest mistake to make against this signature -- got a plausible symbol
    computed over the wrong number, silently (FIBR-0310 P12).
    """
    if len(payload) != PAYLOAD_SYMBOLS:
        raise ValueError(
            f"a check symbol covers {PAYLOAD_SYMBOLS} data symbols, got {len(payload)}"
        )
    return CHECK_ALPHABET[_payload_int(payload) % _CHECK_MODULUS]


def verify_check_symbol(code: str) -> bool:
    """``True`` iff ``code``'s 28th symbol matches its payload.

    A *typo detector*: it carries no security weight (INV-6). A locally
    well-formed code is one that is not a transcription slip, never one that
    has been shown to open anything.

    Compares the check *value* rather than the character, because Crockford's
    fold reads ``I``/``L`` as ``1`` and ``O`` as ``0`` — so a printed ``…RST1``
    written ``…RSTI`` is the same code, and :func:`decode` returns the same 17
    bytes for both.
    """
    text = code.upper()
    if len(text) != CODE_SYMBOLS:
        return False
    typed = _CHECK_DECODE.get(text[-1])
    if typed is None:
        return False
    try:
        return _payload_int(text[:PAYLOAD_SYMBOLS]) % _CHECK_MODULUS == typed
    except ValueError:
        return False


def decode(code: str) -> bytes:
    """The 135-bit payload as ``PAYLOAD_BYTES`` big-endian bytes, check symbol
    excluded — the one value Argon2id is ever fed (§ 4.3).

    Does not verify the check symbol: that is :func:`verify_check_symbol`'s
    separate step, so the trailing symbol here need only be present.
    """
    text = code.upper()
    if len(text) != CODE_SYMBOLS:
        raise ValueError(
            f"a recovery code is {CODE_SYMBOLS} symbols once normalised, "
            f"got {len(text)}"
        )
    return _payload_int(text[:PAYLOAD_SYMBOLS]).to_bytes(PAYLOAD_BYTES, "big")
