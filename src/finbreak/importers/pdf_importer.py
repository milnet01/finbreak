"""PdfImporter — an **extractor** (not a second parser) for FIBR-0009.

A PDF statement is a printed page: many banks print transactions as a ruled
table, which ``pdfplumber`` lifts off the page as rows of cells. The design
(D1) is to **extract the transaction table and serialise it to CSV text**, then
feed the *existing, unchanged* CSV pipeline (``read_header`` -> ``match_profile``
-> ``CsvImporter.parse`` -> ``preview`` -> ``commit_import``) verbatim — a PDF is
imported as "a CSV we happened to lift off a page". So there is no PDF money
parser; a PDF amount obeys the identical contract as a manually-typed one.

Every PDF is normalised **in memory only** through ``pikepdf`` (qpdf): opening
the source bytes and re-saving them to a ``BytesIO`` strips any encryption —
owner-only *or* user-password — and yields plaintext bytes handed straight to
``pdfplumber`` (INV-2). The module reads/writes **no** file: the decrypted bytes
never touch disk (security-model INV-4). A **user-password** PDF opened without
the right password raises ``pikepdf.PasswordError`` (re-exported here as the
prompt signal, INV-3); an owner-only or plaintext PDF opens with no prompt (D3).

The extractor is resource-bounded (INV-9): more than ``_MAX_PDF_PAGES`` pages or
a candidate with more than ``_MAX_PDF_ROWS`` data rows is refused with a friendly
``ValueError`` — the byte cap is upstream (``ImportService.read_file_bytes``).
"""

from __future__ import annotations

import csv
import io

import pikepdf

# Re-exported so callers gate the password prompt on the module's own signal
# rather than importing pikepdf themselves (INV-3).
PasswordError = pikepdf.PasswordError

# Page + row caps (INV-9, security-model INV-5b). Strict (``>``), matching the
# byte cap. Orders of magnitude above any real personal statement; one-line
# tunable. The byte cap (_MAX_IMPORT_BYTES) lives on the service.
_MAX_PDF_PAGES = 500
_MAX_PDF_ROWS = 100_000

# A cell may be an empty ``str`` or ``None`` depending on table settings; both
# are treated as empty. The type is ``str | None`` end-to-end (mypy-0).
type _Table = list[list[str | None]]


def _fold(cell: str | None) -> str:
    """Whitespace-fold a header cell for grouping (D8) — ``None`` -> ``""``."""
    return " ".join((cell or "").split())


def _uniquify_header(header: list[str | None]) -> list[str]:
    """Rewrite a table's header row to a **collision-free unique** ``list[str]``
    (D13), so the reused ``signature_for`` / ``match_profile`` never raise their
    duplicate-header ``ValueError`` on a real bank PDF.

    A blank cell, or a later duplicate of an already-kept label, becomes a
    positional placeholder ``"Column {n}"`` (1-based); the **first** occurrence of
    a label keeps it. Each generated placeholder is then checked against **all
    other** final cells (not just earlier ones — so a placeholder colliding with
    an untouched real ``"Column 1"`` label is caught) and re-suffixed ``_2``,
    ``_3``, … until unique. Already-unique non-blank labels are left untouched.
    """
    kept: list[str] = []
    slots: list[tuple[str, bool]] = []  # (value, is_placeholder)
    for position, cell in enumerate(header, start=1):
        label = (cell or "").strip()
        if label and label not in kept:
            kept.append(label)
            slots.append((label, False))
        else:
            slots.append((f"Column {position}", True))

    final = [value for value, _ in slots]
    for index, (value, is_placeholder) in enumerate(slots):
        if not is_placeholder:
            continue
        candidate, suffix = value, 2
        while any(candidate == final[j] for j in range(len(final)) if j != index):
            candidate = f"{value}_{suffix}"
            suffix += 1
        final[index] = candidate
    return final


def group_tables_by_header(tables: list[_Table]) -> list[_Table]:
    """Group raw extracted tables into candidate tables (a **pure** helper —
    raw tables in, grouped + header-uniquified candidates out; unit-testable on
    synthetic ``list[list[list]]`` without a PDF fixture).

    Owns the D8 cross-page grouping **and** the D13 header-uniquify: tables whose
    header row (row 0, whitespace-folded) is identical are grouped into one
    candidate — the first member keeps the (uniquified) header, later members
    contribute their data rows (their repeated header row already excluded, since
    grouping is keyed on it). Distinct headers stay separate candidates, in
    first-occurrence order (page then table).
    """
    groups: dict[tuple[str, ...], _Table] = {}
    order: list[tuple[str, ...]] = []
    for table in tables:
        if not table:
            continue
        key = tuple(_fold(cell) for cell in table[0])
        if key not in groups:
            header: list[str | None] = list(_uniquify_header(table[0]))
            groups[key] = [header]
            order.append(key)
        groups[key].extend(table[1:])  # data rows; the repeated header is row 0
    return [groups[key] for key in order]


def table_to_text(table: _Table) -> str:
    """Serialise one candidate table to CSV text (D1): ``csv.writer``, an empty
    or ``None`` cell -> ``""``. Row 0 is the already-uniquified header (D13), so
    the reused ``read_header`` / ``signature_for`` consume it directly."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in table:
        writer.writerow(["" if cell is None else cell for cell in row])
    return buffer.getvalue()


class PdfImporter:
    def candidate_tables(
        self, pdf_bytes: bytes, password: str | None = None
    ) -> list[_Table]:
        """The candidate transaction tables in ``pdf_bytes`` (named to avoid
        colliding with ``pdfplumber``'s own ``page.extract_tables()`` it wraps).

        Normalise in memory through ``pikepdf`` (strips owner-only + user
        encryption, D2/D3), open the plaintext bytes with ``pdfplumber``, collect
        every page's ``extract_tables()``, group them (D8) + uniquify the headers
        (D13), drop header-only (0-data-row) tables, and apply the page + row caps
        (INV-9). Raises ``pikepdf.PasswordError`` on a bad/absent **user** password
        (INV-3), and a friendly ``ValueError`` on no usable table (INV-5) or an
        over-large page/row count (INV-9).
        """
        import pdfplumber

        plaintext = _normalise_to_plaintext(pdf_bytes, password)
        with pdfplumber.open(io.BytesIO(plaintext)) as pdf:
            if len(pdf.pages) > _MAX_PDF_PAGES:
                raise ValueError(
                    "this PDF has too many pages to import — "
                    "try your bank's CSV or OFX export"
                )
            raw_tables: list[_Table] = []
            for page in pdf.pages:  # iterate, never index .pages[0] (INV-5)
                raw_tables.extend(page.extract_tables())

        candidates = [c for c in group_tables_by_header(raw_tables) if len(c) > 1]
        for candidate in candidates:
            if len(candidate) - 1 > _MAX_PDF_ROWS:
                raise ValueError(
                    "a table in this PDF has too many rows to import — "
                    "try your bank's CSV or OFX export"
                )
        if not candidates:
            raise ValueError(
                "couldn't read a table from this PDF — "
                "try your bank's CSV or OFX export"
            )
        return candidates


def _normalise_to_plaintext(raw: bytes, password: str | None) -> bytes:
    """Open ``raw`` with ``pikepdf`` and re-save it to an in-memory ``BytesIO``,
    stripping any encryption (D3). Raises ``pikepdf.PasswordError`` on a
    user-password PDF opened without the right password (INV-3). The bytes never
    touch disk (INV-2)."""
    with pikepdf.open(io.BytesIO(raw), password=password or "") as pdf:
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
