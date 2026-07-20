"""FIBR-0029 — Password hint shown before unlock. See spec.md.

Covers the 9 local invariants: the pure enforcement (`validate_hint`), the new
`AuthService.verify_password` primitive, the plaintext `window.ini` I/O adapter,
the reveal-on-click unlock affordance, and the Settings → confirm → save shell
flow. Vaults live under ``tmp_path``; ``window.ini`` is redirected to tmp by the
autouse ``window_ini`` fixture; no network, no real data.
"""

import unicodedata
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel, QPushButton

import finbreak.services.auth as auth_mod
from conftest import _PW
from finbreak.errors import VaultLockedError
from finbreak.services.auth import AuthService
from finbreak.services.password_hint import (
    MAX_HINT_LEN,
    HintPolicyError,
    validate_hint,
)
from finbreak.ui._password_hint import clear_hint, read_hint, write_hint
from finbreak.ui.main_window import MainWindow
from finbreak.ui.set_hint import SetHintDialog
from finbreak.ui.settings import SettingsDialog
from finbreak.ui.unlock import UnlockDialog

pytestmark = pytest.mark.features


# --------------------------------------------------------------------------- #
# Fixtures + helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def service(paths):
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")  # first-run migrates straight to latest
    yield svc
    svc.lock()


def _shell(qtbot, service) -> MainWindow:
    window = MainWindow(service)
    qtbot.addWidget(window)
    window._enter_unlocked()
    return window


def _open_set_hint(qtbot, service) -> tuple[MainWindow, SetHintDialog]:
    """Open Settings → click "Set password hint…" → return the SetHintDialog the
    shell placed in ``_dialog`` (the real button-driven path)."""
    window = _shell(qtbot, service)
    window._action_settings.trigger()
    settings = window._dialog
    assert isinstance(settings, SettingsDialog)
    button = settings.findChild(QPushButton, "settings_set_hint")
    assert button is not None
    button.click()
    dialog = window._dialog
    assert isinstance(dialog, SetHintDialog)
    return window, dialog


# --------------------------------------------------------------------------- #
# INV-1 — hint is optional and off by default
# --------------------------------------------------------------------------- #
def test_INV1_fresh_window_ini_has_no_hint(window_ini):
    assert read_hint() == ""


def test_INV1_unlock_dialog_no_affordance_when_unset(qtbot, service):
    dialog = UnlockDialog(service)
    qtbot.addWidget(dialog)
    assert dialog.findChild(QPushButton, "unlock_show_hint") is None


# --------------------------------------------------------------------------- #
# INV-2 — hint never equals or contains the password (NFC + casefold)
# --------------------------------------------------------------------------- #
def test_INV2_case_insensitive_equality_rejected():
    with pytest.raises(HintPolicyError):
        validate_hint("groceries2026", "Groceries2026")


def test_INV2_containment_rejected():
    with pytest.raises(HintPolicyError):
        validate_hint("see Groceries2026 note", "Groceries2026")


def test_INV2_nfd_normal_form_copy_rejected():
    # A hint that is the password in a different Unicode normal form (NFD) must
    # still be caught — NFC+casefold reconciles them where .lower() would not.
    password = unicodedata.normalize("NFC", "Groceriesé2026")
    hint_nfd = unicodedata.normalize("NFD", password)
    assert hint_nfd != password, "the NFD copy must differ as a raw string"
    with pytest.raises(HintPolicyError):
        validate_hint(hint_nfd, password)


def test_INV2_short_password_embedded_verbatim_rejected():
    # Unconditional containment: no password-length carve-out. A 3-char password
    # embedded verbatim in a hint leaks it and must be rejected.
    with pytest.raises(HintPolicyError):
        validate_hint("my pw is abc", "abc")


def test_INV2_safe_hint_passes():
    validate_hint("Spar loyalty year", "Groceries2026")  # must not raise


def test_INV2_equals_and_contains_have_distinct_messages():
    # The equality rule is retained for its friendlier "may not BE" message even
    # though it is subsumed by containment (spec § 3.4).
    with pytest.raises(HintPolicyError) as be:
        validate_hint("Groceries2026", "Groceries2026")
    with pytest.raises(HintPolicyError) as contains:
        validate_hint("see Groceries2026 here", "Groceries2026")
    assert str(be.value) != str(contains.value)


# --------------------------------------------------------------------------- #
# INV-3 — hint is readable pre-unlock, with no key
# --------------------------------------------------------------------------- #
def test_INV3_read_hint_pre_unlock(window_ini):
    write_hint("look under the mat")
    assert read_hint() == "look under the mat"  # no vault opened at all


# --------------------------------------------------------------------------- #
# INV-4 — setting a hint requires the correct current password
# --------------------------------------------------------------------------- #
def test_INV4_wrong_password_writes_nothing(qtbot, service):
    write_hint("old hint")
    window, dialog = _open_set_hint(qtbot, service)
    dialog._hint.setText("Spar loyalty year")
    dialog._password.setText("the wrong password")
    dialog.save_requested.emit()
    assert read_hint() == "old hint", "a wrong password must not overwrite the hint"
    assert isinstance(window._dialog, SetHintDialog), "dialog stays open on reject"


def test_INV4_correct_password_saves(qtbot, service):
    window, dialog = _open_set_hint(qtbot, service)
    dialog._hint.setText("Spar loyalty year")
    dialog._password.setText(_PW.decode())
    dialog.save_requested.emit()
    assert read_hint() == "Spar loyalty year"
    assert window._dialog is None, "the shell tears the dialog down on save"


def test_INV4_policy_violating_hint_blocked_even_with_correct_password(qtbot, service):
    window, dialog = _open_set_hint(qtbot, service)
    dialog._hint.setText(_PW.decode())  # the hint IS the password
    dialog._password.setText(_PW.decode())
    dialog.save_requested.emit()
    assert read_hint() == "", "a policy-violating hint must not be written"
    assert isinstance(window._dialog, SetHintDialog)


# --------------------------------------------------------------------------- #
# INV-5 — verify_password is correct and constant-time
# --------------------------------------------------------------------------- #
def test_INV5_correct_password_true(service):
    assert service.verify_password(bytearray(_PW)) is True


def test_INV5_wrong_password_false(service):
    assert service.verify_password(bytearray(b"the wrong password")) is False


def test_INV5_uses_constant_time_compare():
    # Constant-time can't be proven by a timing test here — assert the source uses
    # hmac.compare_digest, not ==, as a grep-style backstop (spec INV-5).
    source = Path(auth_mod.__file__).read_text(encoding="utf-8")
    assert "hmac.compare_digest" in source
    assert "import hmac" in source


def test_INV5_raises_when_locked(service):
    service.lock()
    with pytest.raises(VaultLockedError):
        service.verify_password(bytearray(_PW))


# --------------------------------------------------------------------------- #
# INV-6 — length cap
# --------------------------------------------------------------------------- #
def test_INV6_over_length_rejected():
    with pytest.raises(HintPolicyError):
        validate_hint("a" * (MAX_HINT_LEN + 1), "Groceries2026")


def test_INV6_at_length_passes():
    validate_hint("a" * MAX_HINT_LEN, "Groceries2026")  # must not raise


# --------------------------------------------------------------------------- #
# INV-7 — clearing works
# --------------------------------------------------------------------------- #
def test_INV7_clear_removes_hint(window_ini):
    write_hint("something")
    assert read_hint() == "something"
    clear_hint()
    assert read_hint() == ""


def test_INV7_blank_field_clears_via_shell(qtbot, service):
    write_hint("old hint")
    window, dialog = _open_set_hint(qtbot, service)
    dialog._hint.setText("   ")  # whitespace-only ⇒ clear
    dialog._password.setText(_PW.decode())
    dialog.save_requested.emit()
    assert read_hint() == ""


def test_INV7_affordance_disappears_after_clear(qtbot, service):
    write_hint("x")
    clear_hint()
    dialog = UnlockDialog(service)
    qtbot.addWidget(dialog)
    assert dialog.findChild(QPushButton, "unlock_show_hint") is None


# --------------------------------------------------------------------------- #
# INV-8 — the KDF password buffer is wiped
# --------------------------------------------------------------------------- #
def test_INV8_verify_password_wipes_kdf_buffer(service):
    pw = bytearray(_PW)
    service.verify_password(pw)
    assert bytes(pw) == bytes(len(pw)), "verify_password must zero the KDF buffer"


# --------------------------------------------------------------------------- #
# INV-9 — hint is display-only
# --------------------------------------------------------------------------- #
def test_INV9_reveal_does_not_mutate_password_or_throttle(qtbot, service):
    write_hint("Spar loyalty year")
    dialog = UnlockDialog(service)
    qtbot.addWidget(dialog)
    dialog._password.setText("typed so far")
    before = dialog._throttle.load().fail_count
    button = dialog.findChild(QPushButton, "unlock_show_hint")
    assert button is not None
    button.click()
    assert dialog._password.text() == "typed so far", "password field untouched"
    assert dialog._throttle.load().fail_count == before, "throttle counter untouched"


# --------------------------------------------------------------------------- #
# Exit criterion 1 — set → show round-trip (reveal reveals exactly the hint)
# --------------------------------------------------------------------------- #
def test_show_hint_reveals_the_stored_hint(qtbot, service):
    write_hint("Spar loyalty year")
    dialog = UnlockDialog(service)
    qtbot.addWidget(dialog)
    button = dialog.findChild(QPushButton, "unlock_show_hint")
    assert button is not None
    label = dialog.findChild(QLabel, "unlock_hint_text")
    assert label is not None
    assert label.isHidden(), "hint is hidden until Show hint is clicked"
    button.click()
    assert not label.isHidden(), "clicking Show hint reveals the hint label"
    assert label.text() == "Spar loyalty year"
