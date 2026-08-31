"""Advisory master-password strength (Qt-free, pure).

`docs/security-model.md` T2 says password strength is *surfaced at first-run
(advisory, not an enforced INV)*. Nothing implemented it: `validate_first_run`'s
only password rule was non-empty, so a one-character master password was
accepted on the vault's primary credential while the threat model credited the
app with a control it did not have.

**Advisory, deliberately.** Nothing here blocks a password. An enforced minimum
would be a contract change (T2 says advisory), and it would lock out anyone
whose existing vault was created under the old rule — this function is also used
on the password-CHANGE path. It reports; the dialogs show what it says.

**Length is the message.** Argon2id at 47 MiB makes each guess expensive, so
what remains is how many guesses there are, and that is dominated by length
rather than by character classes. Composition rules push users toward
"Password1!" — predictable to a cracker and hard for a human — which is why
NIST SP 800-63B dropped them. So the bands are length-first, and the one
composition check that survives is a penalty for a single repeated character,
because "aaaaaaaaaaaa" is long and worthless.

Not a cracker's estimate and not calibrated against one: no wordlist ships with
finbreak, so this cannot detect that "correcthorse" is a known phrase. It is a
nudge, and the wording says so rather than implying a guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Strength(Enum):
    """How much the advice pushes back. The UI maps these to a colour."""

    WEAK = "weak"
    FAIR = "fair"
    STRONG = "strong"


@dataclass(frozen=True)
class Assessment:
    """A band plus the sentence to show. ``advice`` is empty for STRONG — there
    is nothing useful to add, and a permanent nag reads as an unmet requirement
    on a control that is explicitly advisory."""

    strength: Strength
    advice: str


# Chosen as round numbers a person can act on, not fitted to a corpus. A
# passphrase of a few words clears the upper band comfortably.
_FAIR_LENGTH = 12
_STRONG_LENGTH = 16


def assess(password: str) -> Assessment:
    """Band ``password`` and say, in plain English, what would improve it.

    An empty password is WEAK with no advice: the dialog's own "enter a
    password" handling owns that case, and duplicating it here would show two
    complaints for one mistake.
    """
    if not password:
        return Assessment(Strength.WEAK, "")

    distinct = len(set(password))
    if distinct == 1:
        # Long but worthless: one character repeated is a handful of guesses
        # whatever its length, so length alone must not promote it.
        return Assessment(
            Strength.WEAK, "One repeated character is easy to guess, however long."
        )

    length = len(password)
    if length >= _STRONG_LENGTH:
        return Assessment(Strength.STRONG, "")
    if length >= _FAIR_LENGTH:
        return Assessment(
            Strength.FAIR,
            "A few more characters would make this much harder to guess.",
        )
    return Assessment(
        Strength.WEAK,
        "Short passwords are quick to guess. A few unrelated words is stronger "
        "than a short complicated one, and easier to remember.",
    )
