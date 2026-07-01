# Changelog

All notable changes to finbreak are documented in this
file.

The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Sections use the standard categories — **Added** for new
features, **Changed** for changes in existing behavior,
**Deprecated** for soon-to-be-removed features, **Removed**
for now-removed features, **Fixed** for bug fixes, and
**Security** for security-relevant changes.

The `[Unreleased]` block is required at the top, always —
even if empty. The Roadmap dialog reads it for current-work
signaling per
[`docs/standards/roadmap-format.md § 3.6.2`](docs/standards/roadmap-format.md).

## [Unreleased]

### Added

- Development quality + security gate: a single command,
  `scripts/ci-local.sh`, runs ruff (lint + format-check), bandit,
  pip-audit, gitleaks, and pytest, cheapest-first, failing on the first
  bad stage. `.github/workflows/ci.yml` runs the identical stages by
  invoking that same script (one source of truth), so local and CI runs
  cannot drift. Ships the `pyproject.toml` toolchain (exact-pinned dev
  group), the `.gitleaks.toml` scan config, and a placeholder `finbreak`
  package with a smoke test. (FIBR-0001)
