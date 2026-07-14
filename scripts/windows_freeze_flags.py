"""The single canonical PyInstaller collection-flag list (FIBR-0015 D3).

Both the Windows freeze (`scripts/build-windows-exe.py`) and the parity guard
(`tests/features/windows_build/`) read this list. The guard scrapes the Linux
freeze (`scripts/_build-smoke-in-container.sh`) and asserts its collection flags
equal these — so a native dependency collected for one OS can never be silently
dropped from the other's bundle (the FIBR-0004 argon2 / FIBR-0008 ofxparse
bundle-drop class, INV-3).

**Keep in lockstep with `_build-smoke-in-container.sh`'s `pyinstaller` invocation.**
The Linux freeze remains the guard's read-source (it is the single freeze behind
both the smoke and the released AppImage); rewiring that bash to import this list
is a noted FIBR-0015 follow-up (Out of scope). If you add a `--collect-*` /
`--hidden-import` there, add it here too or the parity guard fails.
"""

from __future__ import annotations

# --self-test imports every native stack lazily, so each needs help travelling
# into the frozen bundle. sqlcipher3/pikepdf use the hidden-import + collect-
# binaries pair; the argon2 / ofxparse / pdfplumber trees use --collect-all to
# pull submodules + data + native binaries wholesale (see the Linux freeze's
# comment block for the per-package rationale).
HIDDEN_IMPORTS = [
    "sqlcipher3",
    "pikepdf",
    "PySide6.QtWidgets",
]

COLLECT_BINARIES = [
    "pikepdf",
    "sqlcipher3",
]

COLLECT_ALL = [
    "argon2",
    "_argon2_cffi_bindings",
    "ofxparse",
    "bs4",
    "lxml",
    "pdfplumber",
    "pdfminer",
    "pypdfium2",
    "pypdfium2_raw",
    "PIL",
    "cryptography",
    "certifi",
]

# The ui/icons package-data directory (FIBR-0037 app icon + FIBR-0051 SVG glyphs)
# is data, not an import, so PyInstaller does not follow it. The SOURCE path is
# OS-specific and is NOT parity-checked (its correctness is owned by the EC3
# `icons` --self-test leg); the TARGET is the package-relative path
# `ui/icons.py` resolves via `Path(__file__).parent / "icons"`, and IS
# parity-checked against the Linux freeze's --add-data target.
ADD_DATA_TARGET = "finbreak/ui/icons"

# The bundled category library (FIBR-0139) is a SECOND package-data directory that
# travels exactly like ui/icons: data, not an import, so PyInstaller does not follow
# it — it needs its own --add-data. Same parity treatment (the package-relative TARGET
# is checked against the Linux freeze; the OS-specific SOURCE is not). Both freeze
# sites emit BOTH --add-data pairs, and the parity guard set-checks all targets.
DATA_ADD_DATA_TARGET = "finbreak/data"


def pyinstaller_flags() -> list[str]:
    """The collection flags, expanded to a flat argv fragment (order is stable so
    the freeze command is reproducible). The `--add-data` pair and the onefile /
    name / paths flags are the driver's job — this is only the collection set."""
    flags: list[str] = []
    for name in HIDDEN_IMPORTS:
        flags += ["--hidden-import", name]
    for name in COLLECT_BINARIES:
        flags += ["--collect-binaries", name]
    for name in COLLECT_ALL:
        flags += ["--collect-all", name]
    return flags
