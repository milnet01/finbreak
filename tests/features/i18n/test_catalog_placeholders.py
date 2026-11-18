"""Every shipped translation keeps its source's ``{placeholders}`` (FIBR-0017).

A screen fills a translated template with ``.format(name=…)``. A translation
that renames, drops or adds a placeholder, or leaves a stray brace, raises
``KeyError`` or ``ValueError`` at that moment, in that language only. The
catalogs are machine-drafted, so this is checked for every entry rather than
trusted.
"""

from __future__ import annotations

import string
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from finbreak.ui.language import CATALOG_DIR

pytestmark = pytest.mark.features


def _fields(text: str) -> set[str] | None:
    """The placeholder names ``str.format`` would look up; None if it would raise."""
    try:
        return {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}
    except ValueError:
        return None


def mismatches(ts: Path) -> list[str]:
    """One line per finished translation whose placeholders differ from its source."""
    found = []
    for context in ET.parse(ts).getroot().iter("context"):
        name = context.findtext("name")
        for message in context.iter("message"):
            source = message.findtext("source") or ""
            translation = message.find("translation")
            if translation is None or translation.get("type") in {
                "unfinished",
                "vanished",
                "obsolete",
            }:
                continue
            forms = [f.text or "" for f in translation.iter("numerusform")] or [
                translation.text or ""
            ]
            for form in forms:
                if _fields(form) != _fields(source):
                    found.append(f"{ts.name} {name}: {source!r} -> {form!r}")
    return found


def test_every_translation_keeps_its_placeholders() -> None:
    catalogs = sorted(CATALOG_DIR.glob("finbreak_*.ts"))
    assert catalogs, "no catalog shipped, so nothing was checked"
    assert [m for ts in catalogs for m in mismatches(ts)] == []


@pytest.mark.parametrize(
    "translation",
    ["{montant} de plus", "{amount} de plus {extra}", "de plus", "{amount de plus"],
)
def test_the_check_sees_a_bad_translation(tmp_path: Path, translation: str) -> None:
    """The leg above asserts an absence, which a parse that matched nothing also
    reports. A renamed, added, dropped and unclosed placeholder must each show."""
    ts = tmp_path / "finbreak_fr.ts"
    ts.write_text(
        '<?xml version="1.0" encoding="utf-8"?><TS version="2.1" language="fr">'
        "<context><name>X</name>"
        "<message><source>{amount} more</source>"
        "<translation>{amount} de plus</translation></message>"
        "<message><source>{amount} more</source>"
        f"<translation>{translation}</translation></message>"
        "</context></TS>",
        encoding="utf-8",
    )
    assert len(mismatches(ts)) == 1
