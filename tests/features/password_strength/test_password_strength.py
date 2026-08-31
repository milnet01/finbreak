"""FIBR-0318 — the advisory master-password strength nudge.

`docs/security-model.md` T2 says strength is surfaced at first-run, advisory and
not an enforced INV. Nothing implemented it: `validate_first_run`'s only
password rule was non-empty, so a one-character master password was accepted on
the vault's primary credential while the threat model credited the app with a
control it did not have.

These legs pin the two properties that matter: it never blocks, and length is
what it rewards.
"""

import pytest

from finbreak.services.password_strength import Strength, assess

pytestmark = pytest.mark.features


def test_length_drives_the_band():
    assert assess("short").strength is Strength.WEAK
    assert assess("mediumlength1").strength is Strength.FAIR
    assert assess("correct horse battery staple").strength is Strength.STRONG


def test_a_single_repeated_character_is_never_promoted_by_length():
    """ "aaaa...aaa" is long and worthless -- a handful of guesses whatever its
    length -- so the length bands must not carry it."""
    long_but_trivial = "a" * 40
    assert len(long_but_trivial) > len("correct horse battery staple")
    assert assess(long_but_trivial).strength is Strength.WEAK
    assert "repeated" in assess(long_but_trivial).advice.lower()


def test_a_strong_password_gets_no_nagging_advice():
    """A permanent nag reads as an unmet requirement, on a control that is
    explicitly advisory."""
    assert assess("correct horse battery staple").advice == ""


def test_empty_is_weak_with_no_advice():
    """The dialog's own "enter a password" handling owns that case; two
    complaints for one mistake is worse than one."""
    result = assess("")
    assert result.strength is Strength.WEAK
    assert result.advice == ""


def test_it_is_advisory_only_and_never_blocks(paths):
    """The whole point of T2's "advisory, not an enforced INV": validate_first_run
    is unchanged, so a weak password is still accepted. An enforced minimum
    would also lock out anyone whose vault predates the rule."""
    from finbreak.services.auth import AuthService

    service = AuthService(*paths)
    # A password assess() calls WEAK. Raises nothing -- non-empty and matching
    # is still the whole rule, which is what "advisory" means.
    assert assess("x").strength is Strength.WEAK
    service.validate_first_run(bytearray(b"x"), bytearray(b"x"), "ZAR")
