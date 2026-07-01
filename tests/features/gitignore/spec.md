# Feature: `.gitignore` blocks financial data and build output

Test contract for [FIBR-0002](../../../docs/specs/FIBR-0002.md). The
public repo must never be able to stage a user's financial data or
local build output (security-model T6 / A7). These tests enforce that
`.gitignore` covers the required paths — and, just as important, that
it does **not** hide real source.

The check is `git check-ignore --no-index <path>` (exit 0 = ignored,
non-zero = not ignored). `--no-index` is mandatory: a bare
`git check-ignore` reports every *tracked* file as "not ignored"
regardless of the rules, which would make INV-3 pass vacuously.
Directory patterns are queried via a path *inside* the directory
(e.g. `dist/app.exe`), because a bare directory name with no trailing
slash and no on-disk directory reports "not ignored".

- **INV-1** — financial data is ignored: `*.db` / `*.sqlite` /
  `*.sqlite3` vaults and their SQLite runtime sidecars (`-wal` /
  `-shm` / `-journal`, matched by `*.db-*` / `*.sqlite-*` /
  `*.sqlite3-*`).
- **INV-2** — build / packaging / tooling output is ignored:
  `build/`, `dist/`, `*.egg-info/`, `.flatpak-builder/`, `*.dmg`,
  `*.AppImage`, `*.flatpak`, and the `.pytest_cache/` / `.ruff_cache/`
  / `.mypy_cache/` tool caches.
- **INV-3** — real source is **not** ignored (guards against an
  over-broad pattern hiding tracked files).
