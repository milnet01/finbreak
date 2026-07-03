"""Importers — pure parsers that turn a statement source into a ``ParseResult``
of transaction drafts + per-row errors (FIBR-0007). No DB, no Qt; the money
rule stays in ``parse_transaction`` (reused per row)."""
