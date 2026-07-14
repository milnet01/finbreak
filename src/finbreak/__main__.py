"""``python -m finbreak`` entry point.

No arguments launches the GUI (FIBR-0004, superseding the FIBR-0003
``FINBREAK_NOT_BUILT`` placeholder). ``--self-test`` runs the permanent
native-stack diagnostic (FIBR-0003) — a way to check a broken install and the
clean-room bundle sentinel. See docs/specs/FIBR-0004.md.
"""

from __future__ import annotations

import os
import sys

from finbreak import _selftest


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--self-test"]:
        # A `--windowed` (GUI) build has no console: PyInstaller sets
        # sys.stdout/stderr to None on Windows, so the sentinel can't be read
        # from stdout. When FINBREAK_SELFTEST_OUT names a file, write the
        # sentinel there instead — the clean-room reads that file (FIBR-0132).
        out_path = os.environ.get("FINBREAK_SELFTEST_OUT")
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
