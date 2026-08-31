"""``python -m finbreak`` entry point.

No arguments launches the GUI (FIBR-0004, superseding the FIBR-0003
``FINBREAK_NOT_BUILT`` placeholder). ``--self-test`` runs the permanent
native-stack diagnostic (FIBR-0003) — a way to check a broken install and the
clean-room bundle sentinel. See docs/specs/FIBR-0004.md.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from finbreak import _selftest


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--self-test"]:
        # The self-test is a PERMANENT diagnostic for a broken install
        # (FIBR-0003 INV-1), so it has to survive the machine it is most likely
        # to be run on: a headless one. Without a display Qt cannot initialise
        # xcb or wayland and ABORTS the process before the first check runs.
        # Default to the offscreen plugin when there is no display server; an
        # explicit QT_QPA_PLATFORM still wins, so the callers that already set
        # it (tests/conftest.py, build-smoke.sh, the OBS recipes) are unaffected.
        # Windows and macOS always have a window server and their frozen bundles
        # need not carry the offscreen plugin, so they keep the native default
        # (FIBR-0261).
        if sys.platform not in ("win32", "darwin") and not (
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        ):
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        # A `--windowed` (GUI) build has no console: PyInstaller sets
        # sys.stdout/stderr to None on Windows, so the sentinel can't be read
        # from stdout. When FINBREAK_SELFTEST_OUT names a file, write the
        # sentinel there instead — the clean-room reads that file (FIBR-0132).
        out_path = os.environ.get("FINBREAK_SELFTEST_OUT")
        if not out_path and sys.stdout is None:
            # A --windowed build has no console, so sys.stdout is None and
            # `print(..., file=None)` is a SILENT NO-OP -- the mode emitted
            # neither sentinel, including the failing-stack token that is the
            # whole reason FAIL carries a prefix. The clean-room was given
            # FINBREAK_SELFTEST_OUT (FIBR-0132); a user running the documented
            # diagnostic on the shipped .exe was not, and got an exit code and
            # nothing else. Fall back to a known file so the mode always has an
            # observable result. Named on stderr too, which costs nothing when
            # stderr is also None.
            out_path = str(Path(tempfile.gettempdir()) / "finbreak-selftest.txt")
            print(f"finbreak: self-test output -> {out_path}", file=sys.stderr)
        if out_path:
            with open(out_path, "w", encoding="utf-8") as out:
                return _selftest.run_self_test(out=out)
        return _selftest.run_self_test()
    if not args:
        from finbreak.app import run

        return run(None)
    print(f"finbreak: unrecognised arguments {args!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
