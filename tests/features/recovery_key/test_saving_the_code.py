"""INV-28 — "Save to a file" never leaves the user a saved code that opens nothing.

Why this exists: Save runs BEFORE Keep or Decline, and it suggested the same
file name every time. On Settings' Replace and on the post-recovery offer, a
user could save over the file holding their LIVE code, then press "Keep my
existing recovery code" — the old code stayed live and its only saved copy now
held a code no slot opens. First run had the same shape: Save, then Decline,
left a file holding a dead code. And the write truncated the file before
writing it, so a failure part-way left neither code (full audit 2026-09-27,
code lane 15; FIBR-0367 row 35).

So: a Decline after a Save asks first, and "Keep the new code" makes the saved
file the working one; the suggested name carries the day; the file is replaced
whole or not at all.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from _recovery_helpers import (
    MASTER_PASSWORD,
    code_secret,
    create_vault,
    opens_with,
    read_v2_sidecar,
    unwrap_slot,
)
from PySide6.QtWidgets import QMessageBox

from finbreak.datetime_format import today as app_today
from finbreak.services.auth import AuthService
from finbreak.services.recovery_code import generate_code
from finbreak.ui import recovery_key as recovery_module
from finbreak.ui.recovery_key import RecoveryCodeDialog, build_recovery_offer

pytestmark = pytest.mark.features


@pytest.fixture
def service(paths: tuple[Path, Path]) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    create_vault(svc, MASTER_PASSWORD)  # first run: no recovery slot yet
    yield svc
    svc.lock()


def _save_to(monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    monkeypatch.setattr(
        recovery_module.QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (str(target), "")),
    )


def _offer_saved_to(
    qtbot: Any, service: AuthService, monkeypatch: Any, target: Path
) -> tuple[RecoveryCodeDialog, str]:
    code = generate_code()
    dialog = build_recovery_offer(service, code)
    qtbot.addWidget(dialog)
    dialog.show()
    _save_to(monkeypatch, target)
    dialog._save()
    assert target.read_text(encoding="utf-8") == code + "\n", (
        "precondition: Save must have written the code"
    )
    return dialog, code


def _capture_warnings(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """A real warning box blocks a headless run until the test times out."""
    titles: list[str] = []
    monkeypatch.setattr(
        recovery_module.QMessageBox,
        "warning",
        staticmethod(lambda _parent, title, _text: titles.append(title)),
    )
    return titles


def _decline_check(dialog: RecoveryCodeDialog) -> QMessageBox | None:
    return dialog.findChild(QMessageBox, "recovery_code_decline_check")


def _press(box: QMessageBox, label_part: str) -> None:
    for button in box.buttons():
        if label_part.lower() in button.text().lower():
            button.click()
            return
    raise AssertionError(
        f"no button containing {label_part!r}: {[b.text() for b in box.buttons()]}"
    )


def test_declining_after_a_save_asks_first(
    qtbot: Any, service: AuthService, monkeypatch: Any, tmp_path: Path
) -> None:
    target = tmp_path / "code.txt"
    dialog, _code = _offer_saved_to(qtbot, service, monkeypatch, target)
    finished: list[int] = []
    dialog.finished.connect(finished.append)

    dialog.reject()  # the Decline button, Escape and the window [X] all land here

    box = _decline_check(dialog)
    assert box is not None and box.isVisible(), (
        "declining after a Save went straight through, leaving a saved file "
        "that holds a code which will open nothing"
    )
    assert str(target) in box.text(), "the question must name the saved file"
    assert finished == [], "the offer must still be open while the user decides"


def test_keeping_the_new_code_makes_the_saved_file_the_working_one(
    qtbot: Any,
    service: AuthService,
    monkeypatch: Any,
    tmp_path: Path,
    paths: tuple[Path, Path],
) -> None:
    target = tmp_path / "code.txt"
    dialog, _code = _offer_saved_to(qtbot, service, monkeypatch, target)
    dialog.reject()
    box = _decline_check(dialog)
    assert box is not None, "precondition: the question must be asked"

    _press(box, "keep the new code")

    saved = target.read_text(encoding="utf-8").strip()
    vault_path, sidecar_path = paths
    key = unwrap_slot(code_secret(saved), read_v2_sidecar(sidecar_path), "recovery")
    assert opens_with(vault_path, sidecar_path, key), (
        "after 'Keep the new code', the code in the saved file must open the vault"
    )


def test_declining_anyway_writes_no_slot(
    qtbot: Any, service: AuthService, monkeypatch: Any, tmp_path: Path
) -> None:
    dialog, _code = _offer_saved_to(qtbot, service, monkeypatch, tmp_path / "c.txt")
    finished: list[int] = []
    dialog.finished.connect(finished.append)
    dialog.reject()
    box = _decline_check(dialog)
    assert box is not None, "precondition: the question must be asked"

    _press(box, "decline anyway")

    assert finished == [0], "Decline anyway must close the offer as declined"
    assert not service.has_recovery_key(), "Decline must write no recovery slot"


def test_go_back_leaves_the_offer_open(
    qtbot: Any, service: AuthService, monkeypatch: Any, tmp_path: Path
) -> None:
    dialog, _code = _offer_saved_to(qtbot, service, monkeypatch, tmp_path / "c.txt")
    finished: list[int] = []
    dialog.finished.connect(finished.append)
    dialog.reject()
    box = _decline_check(dialog)
    assert box is not None, "precondition: the question must be asked"

    _press(box, "go back")

    assert finished == [], "Go back must return to the code, deciding nothing"
    assert dialog.isVisible()
    assert not service.has_recovery_key()


def test_declining_without_a_save_asks_nothing(
    qtbot: Any, service: AuthService
) -> None:
    dialog = build_recovery_offer(service, "ABCD-EFGH-JKMN-PQRS-TVWX-YZ01-2345")
    qtbot.addWidget(dialog)
    finished: list[int] = []
    dialog.finished.connect(finished.append)
    dialog.show()

    dialog.reject()

    assert _decline_check(dialog) is None
    assert finished == [0]


def test_the_suggested_file_name_carries_the_day(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same fixed name every time made the live code's file the default
    target of every later save."""
    suggested: list[str] = []

    def capture(*args: Any, **_kwargs: Any) -> tuple[str, str]:
        suggested.append(args[2])
        return "", ""  # the user cancels

    monkeypatch.setattr(
        recovery_module.QFileDialog, "getSaveFileName", staticmethod(capture)
    )
    dialog = RecoveryCodeDialog("ABCD-EFGH-JKMN-PQRS-TVWX-YZ01-2345")
    qtbot.addWidget(dialog)
    dialog._save()

    assert suggested == [f"finbreak-recovery-code-{app_today().isoformat()}.txt"]


def test_a_failed_write_leaves_the_existing_file_whole(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Truncate-then-write: a failure part-way lost the file's old contents,
    which may be the user's only copy of the code that works."""
    target = tmp_path / "code.txt"
    target.write_text("THE-CODE-THAT-WORKS\n", encoding="utf-8")
    _save_to(monkeypatch, target)

    real_fdopen = os.fdopen

    class _FailingHandle:
        def __init__(self, handle: Any) -> None:
            self._handle = handle

        def __enter__(self) -> _FailingHandle:
            return self

        def __exit__(self, *exc: Any) -> None:
            self._handle.close()

        def write(self, _text: str) -> int:
            raise OSError(28, "No space left on device")

    monkeypatch.setattr(
        recovery_module.os,
        "fdopen",
        lambda fd, *a, **k: _FailingHandle(real_fdopen(fd, *a, **k)),
    )
    warnings = _capture_warnings(monkeypatch)
    dialog = RecoveryCodeDialog("ABCD-EFGH-JKMN-PQRS-TVWX-YZ01-2345")
    qtbot.addWidget(dialog)
    dialog._save()

    assert warnings, "precondition: the write must actually have failed"
    assert target.read_text(encoding="utf-8") == "THE-CODE-THAT-WORKS\n", (
        "a failed save destroyed the file it was saving over"
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["code.txt"], (
        "a failed save left a partial file behind"
    )


@pytest.mark.skipif(os.name != "posix", reason="symlinks are a POSIX question here")
def test_a_planted_part_file_is_never_written_through(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The temp name is derived from the name the user chose, so it is
    predictable, and in a shared directory someone can plant a link there
    first. Writing through it would put the code in their file."""
    target = tmp_path / "code.txt"
    decoy = tmp_path / "someone-elses-file.txt"
    decoy.write_text("not the user's\n", encoding="utf-8")
    (tmp_path / "code.txt.part").symlink_to(decoy)
    _save_to(monkeypatch, target)
    warnings = _capture_warnings(monkeypatch)

    code = "ABCD-EFGH-JKMN-PQRS-TVWX-YZ01-2345"
    dialog = RecoveryCodeDialog(code)
    qtbot.addWidget(dialog)
    dialog._save()

    assert warnings == [], f"a stale .part must be cleared, not refused: {warnings}"
    assert decoy.read_text(encoding="utf-8") == "not the user's\n"
    assert target.read_text(encoding="utf-8") == code + "\n"
    assert not target.is_symlink()
    assert target.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name != "posix", reason="symlinks are a POSIX question here")
def test_a_link_planted_after_the_stale_part_is_cleared_is_refused(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Clearing a stale .part leaves a window before the create. A link planted
    in it must make the save fail, never redirect the code into another file.
    The re-plant is the attacker's move, made deterministic."""
    target = tmp_path / "code.txt"
    part = tmp_path / "code.txt.part"
    decoy = tmp_path / "someone-elses-file.txt"
    decoy.write_text("not the user's\n", encoding="utf-8")
    _save_to(monkeypatch, target)
    warnings = _capture_warnings(monkeypatch)

    real_unlink = Path.unlink

    def unlink_then_plant(self: Path, missing_ok: bool = False) -> None:
        real_unlink(self, missing_ok=missing_ok)
        if self == part and not part.is_symlink():
            part.symlink_to(decoy)

    monkeypatch.setattr(Path, "unlink", unlink_then_plant)
    dialog = RecoveryCodeDialog("ABCD-EFGH-JKMN-PQRS-TVWX-YZ01-2345")
    qtbot.addWidget(dialog)
    dialog._save()

    assert decoy.read_text(encoding="utf-8") == "not the user's\n", (
        "the code was written through a link planted at the temp name"
    )
    assert warnings, "the save must be refused and the user told"
    assert not target.exists()
