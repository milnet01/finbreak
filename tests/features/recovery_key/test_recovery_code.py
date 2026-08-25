"""FIBR-0019 INV-5/INV-6/INV-11 — the recovery code itself. Enforces spec.md.

INV-5 and INV-6 are headless (``recovery_code`` is pure). INV-11 is NOT: its
trial-unwrap seam lives in ``ui/_password_hint.py``, the I/O half of the hint
pair, because ``services/password_hint.py``'s own contract is to be pure and the
only sidecar locator sits in a module that imports PySide6 (§ 7).

Why this exists: a "show it again" affordance, or a code written into
``window.ini`` beside the password hint, would turn a full-strength credential
into a plaintext file next to the vault it opens.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from _recovery_helpers import (
    MASTER_PASSWORD,
    code_secret,
    code_with_check_symbol,
    create_vault,
    forge_wrong_code_with_a_valid_check_symbol,
    keep_recovery_key,
    kek_for,
    opens_with,
    read_v2_sidecar,
    require_seam,
    unwrap_slot,
)

from finbreak import crypto
from finbreak.errors import KeyUnwrapError
from finbreak.keywrap import SLOT_RECOVERY
from finbreak.services.auth import AuthService
from finbreak.services.password_hint import HintPolicyError, validate_hint
from finbreak.services.recovery_code import (
    PAYLOAD_SYMBOLS,
    check_symbol,
    decode,
    format_code,
    generate_code,
    normalise,
    verify_check_symbol,
)

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths: tuple[Path, Path]) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    yield svc
    svc.lock()


# --------------------------------------------------------------------------- #
# INV-5 — the code is never persisted by the app of its own accord
# --------------------------------------------------------------------------- #
def test_code_never_reaches_a_plaintext_surface(
    tmp_path: Path, paths: tuple[Path, Path], service: AuthService
) -> None:
    _vault_path, _sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)

    # The § 4.5 step 8 carve-out, and the ONLY write this invariant permits: the
    # user chose a path and asked for the code to be saved there. That is the
    # user storing their own credential, not the app retaining it -- and the
    # difference between the two is what INV-5 is about. The test supplies the
    # path, so nothing about it is the app's doing.
    user_chosen_file = tmp_path / "my-recovery-code.txt"
    user_chosen_file.write_text(code)

    service.lock()

    needles = {
        "the display form": code.encode(),
        "the display form, lower case": code.lower().encode(),
        "the normalised base32": normalise(code).encode(),
        "the normalised base32, lower case": normalise(code).lower().encode(),
        "the decoded 17-byte payload": code_secret(code),
        "the decoded payload as hex": code_secret(code).hex().encode(),
    }

    offenders: dict[Path, list[str]] = {}
    for path in sorted(tmp_path.rglob("*")):
        if not path.is_file():
            continue
        # vault.db (and its WAL siblings) are EXCLUDED deliberately. The vault is
        # encrypted, so a plaintext search of it cannot fail -- and a leg that
        # cannot fail is not evidence. Keeping the code out of the vault's
        # CONTENTS is a different invariant needing a fixture that opens the
        # vault and searches its tables; this spec does not claim it.
        if path.name.startswith("vault.db"):
            continue
        blob = path.read_bytes()
        hits = [label for label, needle in needles.items() if needle in blob]
        if hits:
            offenders[path] = hits

    assert set(offenders) == {user_chosen_file}, (
        "INV-5: the recovery code must reach no plaintext surface the app wrote "
        "of its own accord -- not vault.kdf.json, not window.ini (plaintext by "
        "design, FIBR-0052 INV-5, and where the password hint already lives), "
        "not a log file, nothing under the data directory.\n"
        f"  expected: exactly one file holds it -- {user_chosen_file}, the path "
        "this test supplied as the user's choice\n"
        f"  actual:   {({str(p): hits for p, hits in offenders.items()}) or '{}'}"
    )


# --------------------------------------------------------------------------- #
# INV-6 — the check symbol is a typo detector, not authentication
# --------------------------------------------------------------------------- #
def test_valid_check_symbol_does_not_authenticate(
    paths: tuple[Path, Path], service: AuthService
) -> None:
    vault_path, sidecar_path = paths
    code = create_vault(service)
    keep_recovery_key(service, code)
    service.lock()

    data = read_v2_sidecar(sidecar_path)
    forged = forge_wrong_code_with_a_valid_check_symbol(code)

    assert verify_check_symbol(normalise(forged)), (
        "INV-6 precondition: the forged code must PASS the local check, or the "
        "legs below prove nothing -- a code rejected as a typo never reaches the "
        "unwrap and the test would be vacuous.\n"
        "  expected: verify_check_symbol(forged) is True\n"
        f"  actual:   False, for {forged!r}"
    )
    assert decode(normalise(forged)) != decode(normalise(code)), (
        "INV-6 precondition: the forgery must carry a DIFFERENT payload.\n"
        f"  expected: decode(forged) != decode(real)\n"
        f"  actual:   both decode to {decode(normalise(code)).hex()}"
    )

    with pytest.raises(KeyUnwrapError):
        unwrap_slot(code_secret(forged), data, SLOT_RECOVERY)

    forged_kek = kek_for(code_secret(forged), data, SLOT_RECOVERY)
    assert not opens_with(vault_path, sidecar_path, forged_kek), (
        "INV-6: a locally well-formed but wrong code must not open the vault by "
        "any route. The check symbol is a usability device and carries no "
        "security weight; using it to short-circuit the unwrap would make a "
        "typo-free guess look accepted.\n"
        "  expected: the vault stays closed\n"
        "  actual:   it opened"
    )


# --------------------------------------------------------------------------- #
# § 4.3 fold — the check symbol is folded too (FIBR-0307 finding 1)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("typed", "printed"), [("I", "1"), ("L", "1"), ("O", "0")])
def test_a_confusably_transcribed_check_symbol_is_not_a_typo(
    typed: str, printed: str
) -> None:
    """Crockford's fold reads ``I``/``L`` as ``1`` and ``O`` as ``0``, and the
    28th symbol is no exception. A user who writes the printed digit in the
    confusable form has transcribed the code CORRECTLY.
    """
    code = normalise(code_with_check_symbol(printed))
    substituted = code[:PAYLOAD_SYMBOLS] + typed

    assert verify_check_symbol(code), (
        "precondition: the printed form must verify, or the leg below proves "
        "nothing about the fold.\n"
        f"  expected: verify_check_symbol({code!r}) is True\n"
        "  actual:   False"
    )
    assert decode(substituted) == decode(code), (
        "precondition: substituting the CHECK symbol must not change the "
        "credential -- decode() reads the 27-symbol payload only, so both "
        "forms must feed Argon2id the same 17 bytes.\n"
        f"  expected: both decode to {decode(code).hex()}\n"
        f"  actual:   {decode(substituted).hex()}"
    )
    assert verify_check_symbol(substituted), (
        f"§ 4.3: the printed {printed!r} written as {typed!r} is the SAME code "
        "-- decode() proves it on the line above -- so refusing it reports a "
        "typo the user did not make, and locks them out of the recovery route "
        "before any derivation is attempted.\n"
        f"  expected: verify_check_symbol({substituted!r}) is True\n"
        "  actual:   False -- the 28th symbol is compared as a raw character "
        "while the payload it is checked against is folded"
    )


def test_the_fold_does_not_widen_to_a_wrong_check_symbol() -> None:
    """Folding must not turn the typo detector into a rubber stamp: ``I``/``L``/
    ``O`` stand in for ``1``/``1``/``0`` and for nothing else."""
    code = normalise(code_with_check_symbol("2"))
    for typed in "ILO":
        substituted = code[:PAYLOAD_SYMBOLS] + typed
        assert not verify_check_symbol(substituted), (
            "§ 4.3: the fold maps I/L to 1 and O to 0. A code whose check "
            f"symbol is '2' must still be refused when its 28th symbol reads "
            f"{typed!r}, or the check has stopped detecting transcription "
            "slips altogether.\n"
            f"  expected: verify_check_symbol({substituted!r}) is False\n"
            "  actual:   True"
        )


@pytest.mark.parametrize("printed", ["U", "*", "~", "$", "="])
def test_the_five_non_data_check_symbols_still_verify(printed: str) -> None:
    """The check alphabet is 37 symbols, five of which are outside the data
    alphabet entirely. A fold implemented over the DATA decode table alone would
    drop these, refusing one issued code in every seven."""
    code = normalise(code_with_check_symbol(printed))
    assert verify_check_symbol(code), (
        "§ 4.3: `*`, `~`, `$`, `=` and `U` are legal check symbols -- a code's "
        f"last group may read `RST{printed}`. Refusing one is refusing a "
        "correctly printed code.\n"
        f"  expected: verify_check_symbol({code!r}) is True\n"
        "  actual:   False"
    )


def test_hint_rejects_the_code_whose_check_symbol_was_transcribed_confusably(
    paths: tuple[Path, Path], service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-11's scan gates on ``verify_check_symbol``, so finding 1 is also a
    one-character bypass of it: the live code, with its ``1`` written as ``I``,
    yields no candidate, costs no derivation, and is written to plaintext
    ``window.ini`` beside the vault it opens.
    """
    _vault_path, sidecar_path = paths
    from finbreak.ui import _password_hint as hint_io

    check = require_seam(
        hint_io,
        "validate_hint_with_recovery",
        "INV-11's trial-unwrap lives in ui/_password_hint.py (§ 11).",
    )
    monkeypatch.setattr("finbreak.paths.sidecar_path", lambda: sidecar_path)

    # Force the check symbol: the defect is reachable only for '0' and '1', and
    # first_run would otherwise mint one of 37 at random.
    printed = code_with_check_symbol("1")
    monkeypatch.setattr("finbreak.services.auth.generate_code", lambda: printed)

    code = create_vault(service)
    assert code == printed, (
        "precondition: the vault must have been created with the forced code, "
        "or this leg is testing an unrelated one.\n"
        f"  expected: {printed!r}\n"
        f"  actual:   {code!r}"
    )
    keep_recovery_key(service, code)

    substituted = format_code(normalise(code)[:PAYLOAD_SYMBOLS] + "I")
    with pytest.raises(HintPolicyError):
        check(f"same as the one on the card: {substituted}", MASTER_PASSWORD.decode())


# --------------------------------------------------------------------------- #
# INV-11 — a stored hint may contain neither the password nor the code
# --------------------------------------------------------------------------- #
def test_hint_rejects_the_recovery_code(
    paths: tuple[Path, Path], service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _vault_path, sidecar_path = paths

    # The pure policy module keeps its two-argument signature: the recovery-slot
    # leg is the CALLER's, per the seam above (verified against the tree
    # 2026-08-20). A three-argument validate_hint would mean the trial-unwrap had
    # been pushed into the module whose contract is to be pure.
    assert list(inspect.signature(validate_hint).parameters) == ["hint", "password"], (
        "INV-11: services/password_hint.validate_hint stays pure and keeps its "
        "two-argument signature -- the trial-unwrap belongs in the I/O half.\n"
        "  expected: ['hint', 'password']\n"
        f"  actual:   {list(inspect.signature(validate_hint).parameters)}"
    )

    from finbreak.ui import _password_hint as hint_io

    check = require_seam(
        hint_io,
        "validate_hint_with_recovery",
        "INV-11's trial-unwrap lives in ui/_password_hint.py (§ 11): it needs "
        "paths.sidecar_path(), which sits in a module importing PySide6, so it "
        "cannot live in the pure services/password_hint.py.",
    )
    monkeypatch.setattr("finbreak.paths.sidecar_path", lambda: sidecar_path)

    code = create_vault(service)
    keep_recovery_key(service, code)

    # Leg 1 -- the real code, in the DISPLAY form the user holds. Normalising
    # first is load-bearing: `A1B2-C3D4-...`'s longest unbroken symbol run is
    # four, so a scan of the raw hint text finds no 28-symbol candidate and
    # cheerfully accepts a hint that IS the recovery code.
    with pytest.raises(HintPolicyError):
        check(f"same as the one on the card: {code}", MASTER_PASSWORD.decode())

    # Leg 2 -- a well-formed but WRONG code is accepted. The check symbol proves
    # only that it is not a typo; it is the trial-unwrap that decides, so a
    # candidate that does not unwrap is not the live code and the hint stands.
    forged = forge_wrong_code_with_a_valid_check_symbol(code)
    check(f"same as the one on the card: {forged}", MASTER_PASSWORD.decode())

    # Leg 3 -- no candidate, no key derivation at all. The common case must not
    # cost a ~46 MiB Argon2id run every time the user edits their hint.
    derivations: list[int] = []
    real_hash = crypto.hash_secret_raw

    def counting_hash(**kwargs: Any) -> bytes:
        derivations.append(1)
        return real_hash(**kwargs)

    monkeypatch.setattr("finbreak.crypto.hash_secret_raw", counting_hash)
    check("the one I always use", MASTER_PASSWORD.decode())
    assert derivations == [], (
        "INV-11: a hint holding no 28-symbol Crockford candidate must perform NO "
        "key derivation -- the trial-unwrap runs only where a candidate passes "
        "its check symbol locally.\n"
        "  expected: 0 Argon2id derivations\n"
        f"  actual:   {len(derivations)}"
    )


# --------------------------------------------------------------------------- #
# INV-11's trial-unwrap is bounded, de-duplicated, and never silently fails open
# (FIBR-0310 P12)
# --------------------------------------------------------------------------- #
def test_the_trial_unwrap_is_deduplicated(
    paths: tuple[Path, Path], service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repeated candidate bought a second ~46 MiB Argon2id derivation of the
    first one's answer (FIBR-0310 P12).

    No cap sits on top of the dedup, deliberately: measured, the crafted worst
    case a 100-character hint can reach is 24 distinct candidates (~0.6 s), and
    a random one peaks at 10 -- so no cap value both bounds the work and never
    refuses an honest hint. ``_code_candidates``' docstring carries the numbers.
    """
    _vault_path, sidecar_path = paths
    from finbreak.ui import _password_hint as hint_io

    check = require_seam(
        hint_io,
        "validate_hint_with_recovery",
        "INV-11's trial-unwrap lives in ui/_password_hint.py (§ 11).",
    )
    monkeypatch.setattr("finbreak.paths.sidecar_path", lambda: sidecar_path)
    code = create_vault(service)
    keep_recovery_key(service, code)

    derivations: list[int] = []
    real_hash = crypto.hash_secret_raw

    def counting_hash(**kwargs: Any) -> bytes:
        derivations.append(1)
        return real_hash(**kwargs)

    monkeypatch.setattr("finbreak.crypto.hash_secret_raw", counting_hash)

    # Leg 1 -- the same wrong-but-well-formed candidate twice is ONE derivation.
    # Two identical windows unwrap identically, so the second can only reach the
    # answer the first already gave.
    # Separated by "." rather than by prose: `normalise` strips SPACES, so
    # "or maybe" between the two copies would merge into one run and produce
    # straddling windows -- three candidates, not the repeat this leg is about.
    forged = forge_wrong_code_with_a_valid_check_symbol(code)
    assert len(_distinct(hint_io, f"{forged}.{forged}")) == 1, (
        "precondition: the two copies must be ONE distinct candidate"
    )
    check(f"{forged}.{forged}", MASTER_PASSWORD.decode())
    assert derivations == [1], (
        "a repeated candidate must not be derived twice\n"
        "  expected: 1 Argon2id derivation\n"
        f"  actual:   {len(derivations)}"
    )


def _distinct(hint_io: Any, text: str) -> list[str]:
    return hint_io._code_candidates(normalise(text))


def test_an_unreadable_sidecar_fails_open_but_says_so(
    paths: tuple[Path, Path],
    service: AuthService,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The hint is accepted when the slot cannot be read -- a v1 vault has no
    recovery code to protect. But it left no trace, so a genuinely unreadable
    sidecar looked exactly like a hint that had passed the check (FIBR-0310 P12).
    """
    _vault_path, sidecar_path = paths
    from finbreak.ui import _password_hint as hint_io

    check = require_seam(
        hint_io,
        "validate_hint_with_recovery",
        "INV-11's trial-unwrap lives in ui/_password_hint.py (§ 11).",
    )
    monkeypatch.setattr("finbreak.paths.sidecar_path", lambda: sidecar_path)
    code = create_vault(service)
    keep_recovery_key(service, code)

    monkeypatch.setattr(
        "finbreak.ui._password_hint.read_sidecar_v2",
        lambda _path: (_ for _ in ()).throw(OSError("no such file")),
    )
    hint = f"same as the one on the card: {code}"
    with caplog.at_level("WARNING", logger="finbreak.ui._password_hint"):
        check(hint, MASTER_PASSWORD.decode())  # accepted: nothing to test against
    assert caplog.records, (
        "a fail-OPEN on a hint that already looked like it carried a code must "
        "leave a log line"
    )
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert normalise(code) not in normalise(logged), "the hint must never be logged"


def test_check_symbol_refuses_a_payload_of_the_wrong_length() -> None:
    """The docstring said "27-symbol" and the body checked nothing, so passing a
    whole 28-symbol code -- the easiest mistake against this signature -- got a
    plausible symbol computed over the wrong number, silently (FIBR-0310 P12).
    """
    payload = normalise(generate_code())[:PAYLOAD_SYMBOLS]
    assert len(check_symbol(payload)) == 1  # the contract still holds
    with pytest.raises(ValueError):
        check_symbol(payload + check_symbol(payload))  # a whole code
    with pytest.raises(ValueError):
        check_symbol(payload[:-1])
