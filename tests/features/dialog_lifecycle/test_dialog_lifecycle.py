"""FIBR-0065 INV-1 — the crash-class regression guard.

No content-widget pop-up may block the event loop via ``dialog.exec()``: the H-B
crash (auto-lock during a nested ``exec()`` loop → deleted-C++-object
``RuntimeError``) can only exist where a blocking ``exec()`` does. A source grep
over the four converted files asserts the only surviving ``.exec(`` is the Home
context ``QMenu`` (a pop-up menu, not a modal dialog — out of scope).
"""

from __future__ import annotations

import re
from pathlib import Path

import finbreak.ui as ui_pkg

_UI_DIR = Path(ui_pkg.__file__).parent
_FILES = ("home.py", "rules.py", "statements.py", "import_wizard.py")
_EXEC = re.compile(r"\.exec\(")


def test_INV1_no_blocking_dialog_exec_in_content_widgets() -> None:
    offenders: list[str] = []
    for name in _FILES:
        for lineno, line in enumerate((_UI_DIR / name).read_text().splitlines(), 1):
            if not _EXEC.search(line):
                continue
            # Sole exemption: the Home right-click context menu (a QMenu, not a
            # modal dialog; reads no dialog object after, out of scope).
            if name == "home.py" and "menu.exec(" in line:
                continue
            offenders.append(f"{name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "blocking .exec( found — convert to the non-blocking show_modal pattern "
        "(FIBR-0065 INV-1):\n" + "\n".join(offenders)
    )
