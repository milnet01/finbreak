"""FIBR-0425 / FIBR-0434 — every refusal reaches the screen through Qt's
translation system.

Enforces ``docs/specs/FIBR-0425-translatable-refusals.md`` INV-1 to INV-3 and
INV-5 to INV-8 (INV-4 is the existing message assertions, unmodified). A
refusal is raised with a ``UserMessage`` whose English template is marked with
``QT_TRANSLATE_NOOP("Refusal", …)``; the screen shows it through
``ui/user_text.user_text``, which translates first and substitutes after.

The AST walks each carry a planted-offence leg, as
``test_translatable_strings.py`` does, so a walk that matches nothing cannot
pass.
"""

from __future__ import annotations

import ast
import logging
import string
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QLocale

from conftest import _PW
from finbreak.errors import QT_TRANSLATE_NOOP, UserMessage
from finbreak.models import ColumnMapping
from finbreak.services.auth import AuthService
from finbreak.services.import_ import ImportService
from finbreak.ui.user_text import user_text

pytestmark = pytest.mark.features

_SRC = Path(__file__).resolve().parents[3] / "src" / "finbreak"
_LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    return {
        id(child): node
        for node in ast.walk(tree)
        for child in ast.iter_child_nodes(node)
    }


# --------------------------------------------------------------------------- #
# INV-1 — no screen shows an exception's own text
# --------------------------------------------------------------------------- #
def _in_logging_call(node: ast.AST, parents: dict[int, ast.AST]) -> bool:
    current = parents.get(id(node))
    while current is not None:
        if (
            isinstance(current, ast.Call)
            and isinstance(current.func, ast.Attribute)
            and current.func.attr in _LOG_METHODS
        ):
            return True
        current = parents.get(id(current))
    return False


def _shown_exception_text(path: Path) -> list[str]:
    tree = _tree(path)
    parents = _parents(tree)
    found: list[str] = []
    for handler in ast.walk(tree):
        if not isinstance(handler, ast.ExceptHandler) or handler.name is None:
            continue
        for stmt in handler.body:
            for node in ast.walk(stmt):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "str"
                    and len(node.args) == 1
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == handler.name
                    and not _in_logging_call(node, parents)
                ):
                    found.append(f"{path.name}:{node.lineno}: str({handler.name})")
    return found


def test_INV1_no_screen_shows_exception_text(tmp_path: Path) -> None:
    offences = [
        line
        for path in sorted((_SRC / "ui").rglob("*.py"))
        for line in _shown_exception_text(path)
    ]
    assert not offences, (
        "a UI handler renders an exception's own text, which no catalog can "
        "translate; show it through user_text(exc) instead (FIBR-0425 INV-1).\n"
        "  actual:\n    " + "\n    ".join(offences)
    )

    planted = tmp_path / "planted.py"
    planted.write_text(
        "class W:\n"
        "    def a(self):\n"
        "        try:\n"
        "            pass\n"
        "        except ValueError as exc:\n"
        "            self._error.setText(str(exc))\n"
        "    def b(self):\n"
        "        try:\n"
        "            pass\n"
        "        except ValueError as exc:\n"
        "            log.warning('failed: %s', str(exc))\n",
        encoding="utf-8",
    )
    assert _shown_exception_text(planted) == ["planted.py:6: str(exc)"], (
        "the walk must see the planted setText(str(exc)) and pass the logging call"
    )


# --------------------------------------------------------------------------- #
# INV-2 / INV-3 — every UserMessage is marked, and its placeholders match
# --------------------------------------------------------------------------- #
def _user_message_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "UserMessage")
            or (
                isinstance(node.func, ast.Attribute) and node.func.attr == "UserMessage"
            )
        )
    ]


def _marked_template(call: ast.Call) -> str | None:
    """The literal template when the call's first argument is
    ``QT_TRANSLATE_NOOP("Refusal", <literal>)``, else ``None``."""
    if not call.args:
        return None
    marker = call.args[0]
    if not (
        isinstance(marker, ast.Call)
        and isinstance(marker.func, ast.Name)
        and marker.func.id == "QT_TRANSLATE_NOOP"
        and len(marker.args) == 2
        and not marker.keywords
    ):
        return None
    context, text = marker.args
    if not (
        isinstance(context, ast.Constant)
        and context.value == "Refusal"
        and isinstance(text, ast.Constant)
        and isinstance(text.value, str)
    ):
        return None
    return text.value


def _unmarked(path: Path) -> list[str]:
    return [
        f"{path.name}:{call.lineno}"
        for call in _user_message_calls(_tree(path))
        if _marked_template(call) is None
    ]


def _placeholder_mismatches(path: Path) -> list[str]:
    found: list[str] = []
    for call in _user_message_calls(_tree(path)):
        template = _marked_template(call)
        if template is None:
            continue  # INV-2's to report
        keywords = {kw.arg for kw in call.keywords}
        try:
            fields = {
                name for _, name, _, _ in string.Formatter().parse(template) if name
            }
        except ValueError as exc:
            found.append(f"{path.name}:{call.lineno}: {exc}")
            continue
        if fields != keywords:
            found.append(
                f"{path.name}:{call.lineno}: template names {sorted(fields)}, "
                f"call passes {sorted(k for k in keywords if k)}"
            )
    return found


_PLANTED_MESSAGES = (
    "CONSTANT = 'x'\n"
    "a = UserMessage(f'built {CONSTANT}')\n"
    "b = UserMessage(CONSTANT)\n"
    "c = UserMessage(QT_TRANSLATE_NOOP('Other', 'wrong context'))\n"
    "d = UserMessage(QT_TRANSLATE_NOOP('Refusal', 'could not read {value}'), raw='1')\n"
    "e = UserMessage(QT_TRANSLATE_NOOP('Refusal', 'a lone { brace'))\n"
    "ok = UserMessage(QT_TRANSLATE_NOOP('Refusal', 'read {raw!r}'), raw='1')\n"
)


def test_INV2_every_message_is_marked(tmp_path: Path) -> None:
    offences = [line for path in sorted(_SRC.rglob("*.py")) for line in _unmarked(path)]
    assert not offences, (
        "a UserMessage's template is not a QT_TRANSLATE_NOOP('Refusal', <literal>) "
        "call, so lupdate cannot extract it (FIBR-0425 INV-2).\n"
        "  actual:\n    " + "\n    ".join(offences)
    )
    planted = tmp_path / "planted.py"
    planted.write_text(_PLANTED_MESSAGES, encoding="utf-8")
    assert _unmarked(planted) == ["planted.py:2", "planted.py:3", "planted.py:4"]


def test_INV2_lupdate_extracts_refusals(pseudo) -> None:
    """An imported marker is extracted, not only one defined in the same file."""
    assert ("Refusal", "an account named {name!r} already exists") in pseudo.messages


def test_INV3_placeholders_match_values(tmp_path: Path) -> None:
    offences = [
        line
        for path in sorted(_SRC.rglob("*.py"))
        for line in _placeholder_mismatches(path)
    ]
    assert not offences, (
        "a refusal's placeholders differ from the values its call passes, which "
        "would raise KeyError inside the handler showing it (FIBR-0425 INV-3).\n"
        "  actual:\n    " + "\n    ".join(offences)
    )
    planted = tmp_path / "planted.py"
    planted.write_text(_PLANTED_MESSAGES, encoding="utf-8")
    found = _placeholder_mismatches(planted)
    assert [line.split(":")[1] for line in found] == ["5", "6"], found


# --------------------------------------------------------------------------- #
# INV-5 — under a catalog, each kind of sink shows the refusal translated
# --------------------------------------------------------------------------- #
_HEADER = ["Date", "Details", "Amount"]
_MAPPING = ColumnMapping("Date", "Details", "Amount", None, None, "%Y-%m-%d", False)


@pytest.fixture
def service(paths) -> Iterator[AuthService]:
    svc = AuthService(*paths)
    svc.first_run(bytearray(_PW), "ZAR")
    yield svc
    svc.lock()


def test_INV5_accounts_error_label_is_translated(qtbot, service, catalogs, controller):
    from finbreak.ui.accounts import AccountsWidget

    controller.apply("fr")
    widget = AccountsWidget(service)
    qtbot.addWidget(widget)
    widget._name.setText("Default")  # seeded by the migration: a duplicate
    widget._on_add()
    assert widget._error.text() == "⟦an account named 'Default' already exists⟧", (
        "the refusal must be looked up in the catalog first and its name filled "
        "in after"
    )


def test_INV5_batch_status_cell_is_translated(
    qtbot, service, catalogs, controller, tmp_path
):
    from conftest import cell_text
    from finbreak.ui import import_batch
    from finbreak.ui.import_wizard import ImportWizardWidget

    ImportService(service.vault).save_profile("layout", _HEADER, _MAPPING)
    (tmp_path / "empty.csv").write_text("", encoding="utf-8")
    (tmp_path / "good.csv").write_text(
        "Date,Details,Amount\n2026-01-02,shop,-10.00\n", encoding="utf-8"
    )
    controller.apply("fr")
    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget.show()
    widget._select_files([str(tmp_path / "empty.csv"), str(tmp_path / "good.csv")])
    qtbot.waitUntil(
        lambda: any(f.outcome == "failed" for f in widget._batch_files), timeout=3000
    )
    row = next(i for i, f in enumerate(widget._batch_files) if f.outcome == "failed")
    status = cell_text(widget._batch_review._table, row, import_batch.COL_STATUS)
    assert "⟦the file has no header row⟧" in status, (
        f"the failed file's reason must reach its cell translated; got {status!r}"
    )


def test_INV5_preview_reason_cell_is_translated(
    qtbot, service, catalogs, controller, tmp_path
):
    from conftest import cell_text
    from finbreak.ui.import_wizard import ImportWizardWidget

    ImportService(service.vault).save_profile("layout", _HEADER, _MAPPING)
    path = tmp_path / "rows.csv"
    path.write_text(
        "Date,Details,Amount\n2026-01-02,shop,-10.00\n,blank date,-5.00\n",
        encoding="utf-8",
    )
    controller.apply("fr")
    widget = ImportWizardWidget(service)
    qtbot.addWidget(widget)
    widget.show()
    widget._select_file(str(path))
    table = widget._preview_table
    reasons = [cell_text(table, r, 3) for r in range(table.rowCount())]
    assert "⟦the date cell is empty⟧" in reasons, (
        f"the row error must reach the preview translated; reason cells: {reasons!r}"
    )


# --------------------------------------------------------------------------- #
# INV-6 — an int value appears in the locale's digits
# --------------------------------------------------------------------------- #
def test_INV6_int_values_use_locale_digits(qapp) -> None:
    previous = QLocale()
    QLocale.setDefault(QLocale("ar_EG"))
    try:
        shown = user_text(
            UserMessage(
                QT_TRANSLATE_NOOP(
                    "Refusal", "this OFX file has more than {limit} transactions"
                ),
                limit=100000,
            )
        )
    finally:
        QLocale.setDefault(previous)
    assert "١" in shown and not any(c in "0123456789" for c in shown), (
        f"the limit must read in Arabic-Indic digits; got {shown!r}"
    )


# --------------------------------------------------------------------------- #
# INV-7 — a translation whose placeholders do not fit falls back to English
# --------------------------------------------------------------------------- #
def test_INV7_bad_translation_falls_back(translate_one, caplog) -> None:
    template = 'could not read the amount "{raw}"'
    translate_one("Refusal", template, "{nope}")
    message = UserMessage(QT_TRANSLATE_NOOP("Refusal", template), raw="SENTINEL-7")
    with caplog.at_level(logging.WARNING, logger="finbreak"):
        shown = user_text(message)
    assert shown == 'could not read the amount "SENTINEL-7"'
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and template in warnings[0].getMessage()
    assert "SENTINEL-7" not in caplog.text, "a refusal's values never reach the log"


# --------------------------------------------------------------------------- #
# INV-8 — an exception with no UserMessage shows a fixed sentence
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (OSError(2, "SENTINEL-8", "/home/SENTINEL-8"), "couldn't read this file"),
        (ValueError("SENTINEL-8"), "something unexpected went wrong"),
    ],
    ids=["oserror", "valueerror"],
)
def test_INV8_bare_exception_shows_a_fixed_sentence(qapp, caplog, exc, expected):
    with caplog.at_level(logging.DEBUG, logger="finbreak"):
        shown = user_text(exc)
    assert shown == expected
    assert caplog.records, "precondition: the fallback logs, so the log leg can fail"
    assert "SENTINEL-8" not in caplog.text, "only the exception's type is logged"
