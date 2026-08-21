"""Crockford base32 recovery codes — generate, format, normalise, check, decode
(FIBR-0019 § 4.3).

**STUB — FIBR-0019 is not implemented.** Every function raises
``NotImplementedError`` so ``tests/features/recovery_key/`` executes against a
real call (``testing.md`` § 1). The alphabets and sizes below are the spec's own
fixed values.

Pure and Qt-free, so it is testable headless. Three properties the
implementation must honour, each of which the suite locks:

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


def generate_code() -> str:
    """A fresh 135-bit code in display form — seven hyphen-separated groups of
    four, the 28th symbol being the mod-37 check symbol."""
    raise NotImplementedError("FIBR-0019")


def format_code(symbols: str) -> str:
    """Group ``symbols`` four at a time, hyphen-separated (the display form)."""
    raise NotImplementedError("FIBR-0019")


def normalise(text: str) -> str:
    """Strip hyphens, spaces and case — and nothing else (§ 4.3 Input)."""
    raise NotImplementedError("FIBR-0019")


def check_symbol(payload: str) -> str:
    """The mod-37 check symbol for a 27-symbol normalised payload."""
    raise NotImplementedError("FIBR-0019")


def verify_check_symbol(code: str) -> bool:
    """``True`` iff ``code``'s 28th symbol matches its payload. A *typo
    detector*: it carries no security weight (INV-6)."""
    raise NotImplementedError("FIBR-0019")


def decode(code: str) -> bytes:
    """The 135-bit payload as ``PAYLOAD_BYTES`` big-endian bytes, check symbol
    excluded — the one value Argon2id is ever fed (§ 4.3)."""
    raise NotImplementedError("FIBR-0019")
