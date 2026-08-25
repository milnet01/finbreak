"""Every ``tr()`` / ``translate()`` argument lupdate reads is a string literal.

``docs/standards/coding.md`` § Translatable UI strings says so, and until
FIBR-0310 R3 nothing checked it. Four user-facing strings shipped as
module constants passed to ``self.tr(...)``, four more went through a
constant *context*, and eight more through a one-argument ``_tr`` wrapper --
every one of them extracting to nothing, so the strings were permanently
untranslatable while looking translated at the call site.

The three failing shapes are MEASURED rather than assumed. ``pyside6-lupdate``
over a probe file holding all four (2026-08-25) extracted the two literal ones
and neither of the others::

    self.tr("literal")                          -> extracted
    self.tr(MODULE_CONSTANT)                    -> DROPPED
    QCoreApplication.translate("Ctx", "text")   -> extracted
    QCoreApplication.translate(CTX, "text")     -> DROPPED
    helper("text")  # wrapper calling translate -> DROPPED

An AST walk rather than a ``pyside6-lupdate`` run: the rule is about the shape
of the call, the walk needs no tool on PATH, and it names the offending line
instead of reporting an absence from a catalog.

A wrapper FUNCTION is still allowed, and is how a long shared string keeps one
copy -- what matters is that the literal sits inside the ``translate()`` call in
its body, where lupdate reads it (``ui/unlock.py``'s ``_pairing_broken``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.features

_SRC = Path(__file__).resolve().parents[3] / "src" / "finbreak"

# Which positional arguments lupdate reads, per call shape: `tr(text)` and
# `translate(context, text)`.
_LITERAL_ARGS: dict[str, tuple[int, ...]] = {"tr": (0,), "translate": (0, 1)}


def _is_literal_str(node: ast.expr) -> bool:
    """A plain string literal, or the implicit concatenation of several -- which
    the parser has already folded into one ``Constant`` by this point. An
    f-string is a ``JoinedStr`` and is NOT one."""
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _offences(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        name = node.func.attr
        wanted = _LITERAL_ARGS.get(name)
        if wanted is None:
            continue
        for index in wanted:
            if index >= len(node.args):
                continue
            if not _is_literal_str(node.args[index]):
                found.append(
                    f"{path.name}:{node.lineno}: "
                    f"{name}() argument {index} is "
                    f"{type(node.args[index]).__name__}, not a string literal"
                )
    return found


# The one module still holding the wrapper shape. NOT an allowance: it has 30
# call sites, a third of them inside f-strings where the inlined call blows the
# line limit, so making it conform is a readability refactor of the PDF renderer
# rather than the plumbing fix FIBR-0310 R3 is. Filed as FIBR-0311 and excluded
# here BY NAME, with the leg below failing once it is clean so the exception
# cannot outlive the work.
_KNOWN_OFFENDER = "pdf_export.py"


def test_no_tr_call_takes_a_non_literal_argument() -> None:
    offences = [
        line
        for path in sorted(_SRC.rglob("*.py"))
        if path.name != _KNOWN_OFFENDER
        for line in _offences(path)
    ]
    assert not offences, (
        "a tr() / translate() argument lupdate reads is not a string literal, so "
        "these strings extract to an EMPTY catalog entry and ship "
        "untranslatable -- while reading at the call site as though they were "
        "handled (coding.md § Translatable UI strings; FIBR-0310 R3).\n"
        "  expected: no offending call\n"
        "  actual:\n    " + "\n    ".join(offences)
    )


def test_the_walk_actually_sees_a_planted_offence(tmp_path: Path) -> None:
    """The leg above asserts an ABSENCE, which is what a walk that quietly
    matches nothing also reports. Plant each dropped shape and require it back."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "MSG = 'x'\n"
        "CTX = 'C'\n"
        "class W:\n"
        "    def a(self):\n"
        "        self.tr(MSG)\n"
        "    def b(self):\n"
        "        QCoreApplication.translate(CTX, 'literal')\n"
        "    def c(self):\n"
        "        self.tr(f'{MSG} interpolated')\n"
        "    def ok(self):\n"
        "        self.tr('a literal')\n"
        "        QCoreApplication.translate('Ctx', 'a literal')\n",
        encoding="utf-8",
    )
    lines = _offences(planted)
    assert len(lines) == 3, (
        "the walk must catch all three dropped shapes and neither of the two "
        "good ones, or a green run above proves nothing.\n"
        f"  expected: 3 offences\n  actual:   {len(lines)} -- {lines}"
    )


def test_the_known_offender_is_still_one() -> None:
    """The exclusion above expires by failing, not by being remembered.

    A named exception that stays green after the work lands is how a stale
    allowance survives a codebase for years. When ``pdf_export.py`` conforms,
    this leg goes red and both it and ``_KNOWN_OFFENDER`` come out.
    """
    offences = _offences(_SRC / "services" / _KNOWN_OFFENDER)
    assert offences, (
        f"{_KNOWN_OFFENDER} no longer takes a non-literal tr()/translate() "
        "argument, so the exclusion in this module is spent: delete "
        "`_KNOWN_OFFENDER`, its use in the leg above, and this leg (FIBR-0311).\n"
        "  expected: at least one offence while the exclusion stands\n"
        "  actual:   none"
    )
