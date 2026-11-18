"""Every shipped translation keeps its source's ``{placeholders}`` (FIBR-0017).

A screen fills a translated template with ``.format(name=…)``. A translation
that renames, drops or adds a placeholder, or leaves a stray brace, raises
``KeyError`` or ``ValueError`` at that moment, in that language only; one that
changes a format spec or drops ``%n`` shows the wrong value. The catalogs are
machine-drafted, so this is checked for every entry rather than trusted.
"""

from __future__ import annotations

import re
import string
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from finbreak.ui.language import CATALOG_DIR

pytestmark = pytest.mark.features


def _fields(text: str) -> tuple[list[tuple[str, str, str]], list[str]] | None:
    """What ``str.format`` would substitute — each field with its format spec and
    conversion — and Qt's ``%n`` / ``%1`` markers; None if ``format`` would raise."""
    try:
        fields = sorted(
            (f, spec or "", conv or "")
            for _, f, spec, conv in string.Formatter().parse(text)
            if f is not None
        )
    except ValueError:
        return None
    return fields, sorted(re.findall(r"%(?:n|L?\d+)", text))


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
    ("source", "good", "bad"),
    [
        ("{amount} more", "{amount} de plus", "{montant} de plus"),
        ("{amount} more", "{amount} de plus", "{amount} de plus {extra}"),
        ("{amount} more", "{amount} de plus", "de plus"),
        ("{amount} more", "{amount} de plus", "{amount de plus"),
        ("{amount:,} more", "{amount:,} de plus", "{amount} de plus"),
        ("{amount} more", "{amount} de plus", "{amount!r} de plus"),
        ("%n rows", "%n lignes", "des lignes"),
        ("%1 rows", "%1 lignes", "%2 lignes"),
    ],
)
def test_the_check_sees_a_bad_translation(
    tmp_path: Path, source: str, good: str, bad: str
) -> None:
    """The leg above asserts an absence, which a parse that matched nothing also
    reports. A renamed, added, dropped or unclosed placeholder, a changed format
    spec or conversion, and a dropped or renumbered Qt marker must each show."""
    ts = tmp_path / "finbreak_fr.ts"
    ts.write_text(
        '<?xml version="1.0" encoding="utf-8"?><TS version="2.1" language="fr">'
        "<context><name>X</name>"
        f"<message><source>{source}</source><translation>{good}</translation>"
        f"</message><message><source>{source}</source>"
        f"<translation>{bad}</translation></message>"
        "</context></TS>",
        encoding="utf-8",
    )
    assert len(mismatches(ts)) == 1
