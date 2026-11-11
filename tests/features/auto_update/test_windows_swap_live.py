"""FIBR-0131 INV-3/INV-6 run for real: the PowerShell helper against stand-in files.

Windows only. The Linux gate checks the helper's text; this checks what it leaves
on disk. ``update_installer`` needs only the standard library, so a Windows box
with pytest alone can run it: ``pytest --noconftest <this file>``.
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys

import pytest

from finbreak.services.update_installer import _windows_relaunch_command

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="runs PowerShell")


def _run_helper(tmp_path, *, hold_new_open: bool):
    exe = tmp_path / "finbreak.exe"
    new = tmp_path / "finbreak-update-abcdefgh.exe"
    exe.write_bytes(b"OLD")
    new.write_bytes(b"NEW")
    # Python opens without FILE_SHARE_DELETE, so neither a rename nor a delete of
    # the staged file can succeed while this is held: an antivirus scan's lock.
    held = new.open("rb") if hold_new_open else None
    try:
        subprocess.run(  # nosec B603
            _windows_relaunch_command(str(exe), str(new)), timeout=120, check=False
        )
    finally:
        if held:
            held.close()
    return exe


def test_FIBR0469_a_locked_staged_file_leaves_the_old_program_in_place(tmp_path):
    exe = _run_helper(tmp_path, hold_new_open=True)

    assert exe.read_bytes() == b"OLD"
    assert not (tmp_path / "finbreak.exe.old").exists()


def test_FIBR0469_a_free_staged_file_is_installed_and_nothing_is_left(tmp_path):
    exe = _run_helper(tmp_path, hold_new_open=False)

    assert exe.read_bytes() == b"NEW"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["finbreak.exe"]
