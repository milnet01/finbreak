<!-- ants-roadmap-format: 1 -->
# finbreak — Roadmap

> **Current version:** 0.1.7 (released 2026-07-12). See
> [CHANGELOG.md](CHANGELOG.md) for what's shipped; this file
> covers what's **planned**.
>
> **Format:** v1 — see
> [docs/standards/roadmap-format.md](docs/standards/roadmap-format.md).
> Every actionable bullet carries a stable
> `FIBR-NNNN` ID alongside its phase ID
> (`P##`, `FP##`, `DS##`, `DOC##`, `R##`); the phase ID
> categorises blocks while the stable ID identifies individual
> bullets within them. ID is identity, position is priority,
> items are tackled top-to-bottom. `Dependencies:` lines list
> **direct** predecessors only; transitive prerequisites are
> implied by walking the chain.
>
> **Build order rationale:** the layers are built bottom-up so
> each phase rests on a tested one below it. The encrypted
> **security spine** (key derivation → vault → unlock) is the
> *vertical slice* (P02), built first and on purpose — it is the
> load-bearing concern (personal financial data), so it is
> proven end-to-end before any feature sits on top of it. Each
> phase is then a thin, demonstrable increment.

**Legend** (per `docs/standards/roadmap-format.md § 3.3`)

- ✅ Done (shipped)
- 🚧 In progress (being tackled now)
- 📋 Planned (next up for this phase)
- 💭 Considered (research phase; scope or feasibility uncertain)

**Themes** (per `docs/standards/roadmap-format.md § 3.4`)

- 🎨 Features · ⚡ Performance · 🔌 Plugins · 🖥 Platform
- 🔒 Security · 🧰 Dev experience · 📚 Documentation
- 📦 Packaging · 🐛 Bug fixes · 🔍 Findings fold-in
- 🧹 Cleanup / debt

> **Security is a standing concern, not a phase.** Every
> `implement`-Kind item below must satisfy
> [docs/security-model.md](docs/security-model.md); the security
> static-analysis gate wired up in P01 (bandit + pip-audit +
> gitleaks) runs on every phase's audit and every push.

---

## P01 — Bootstrap (target: next)

**Theme:** wire up the build, lint, format, test, **security
scan**, and CI plumbing chosen in Phase A. Zero user-facing
features. Forces the audit + security harness to be
known-working before any business code lands, and de-risks the
scariest unknown (native-library bundling) up front.

### 🧰 Dev experience

- ✅ [FIBR-0001] **P01: project skeleton + lint + format
  + test + security-scan harness.** `pyproject.toml` (Python
  3.12+), `pip`+`venv` dev env, `ruff check` and `ruff format
  --check` clean on placeholder source, `pytest` exits 0 on an
  empty suite, **`bandit`, `pip-audit`, and `gitleaks` exit 0**.
  `.github/workflows/ci.yml` runs the same gates, and
  `scripts/ci-local.sh` mirrors them one-for-one (single source
  of truth for the gate list) so issues are caught before
  pushing. Dependencies: none. Lanes: build, ci, tests,
  security. Kind: chore. Source: planned.
  Resolved (2026-07-01): closed by /close-phase. Local gate exits 0; CI green in 23s; INV-1..INV-6 all demonstrated (INV-5 secret-injection demo flipped gitleaks + bandit red, then green on removal). /audit + /indie-review both returned zero actionable findings on the same pass. Impl commit 6b6ac64; tag FIBR-0001-complete.

- ✅ [FIBR-0002] **P01: `.gitignore` + secret-leak
  guard.** Standard Python ignore set (build artefacts,
  `.venv`, `__pycache__`, dep caches, IDE/OS files) plus
  explicit ignores for any local vault/`*.db`/`*.dmg`/AppImage
  build output, so **no financial data or build secret can ever
  be staged**. `gitleaks` (from FIBR-0001) is the backstop.
  Dependencies: FIBR-0001. Lanes: build, security. Kind: chore.
  Source: planned.
  Resolved 2026-07-01: .gitignore extended to block financial data (*.db/*.sqlite/*.sqlite3 + SQLite -wal/-shm/-journal sidecars) and build/packaging/tooling output; regression-locked by tests/features/gitignore/ (INV-1..INV-3 via git check-ignore --no-index). Spec cold-eyes-clean (4 loops); /audit + /indie-review zero actionable on the close pass (one indie-review LOW — global-git-excludes coupling — fixed inline). Full ci-local.sh gate green. Tag FIBR-0002-complete.

- ✅ [FIBR-0053] **Pre-push git hook runs the CI gate locally before every push.**
  Prompted by a CI failure email (commit a0cc895: gitleaks flagged the
  `shiboken6.isValid` false-positive in the FIBR-0051 spec prose; fixed in the
  next commit via `.gitleaks.toml`, so main was already green). Root cause was
  process, not drift: `ci.yml` already calls `scripts/ci-setup.sh` +
  `scripts/ci-local.sh` (the identical gate a dev runs), so green-locally ==
  green-in-CI — but that docs-only cold-eyes commit was pushed without running
  the gate. `.githooks/pre-push` runs `scripts/ci-local.sh` on every push (venv
  auto-activated), enabled via `git config core.hooksPath .githooks` (documented
  in CLAUDE.md; a fresh clone enables it once). Faithful full-gate match; a rare
  pypi timeout can flake pip-audit (retry / `--no-verify` for that transient
  case).
  **Layman:** Automatically checks your work before it leaves your machine, so a broken commit can't reach GitHub and trigger a failure email.
  Kind: chore.
  Lanes: ci, build.
  Source: user-request-2026-07-09 (CI failure email on a0cc895).

- ✅ [FIBR-0055] **Settings screen — a Settings menu item whose first control is a user-configurable auto-lock timeout, plus core preferences.**
  User request 2026-07-09: add a Settings menu item; the first thing to
  include is a user-set timeout for the auto-lock (lockout) feature. Pulls the
  Settings-screen + auto-lock-timeout portion of FIBR-0014 (P12) FORWARD as its
  own near-term item (it only depends on what is already built — the FIBR-0004
  auth/idle-lock spine and the FIBR-0052 shell); FIBR-0014 keeps the heavier
  encrypted-backup export/import + dark-theme polish pass, and hosts the
  FIBR-0017 language switcher.
  Resolved 2026-07-09 (FIBR-0055-complete): Settings screen shipped — File → Settings… opens a modal SettingsDialog with a user-configurable auto-lock timeout (1/5/10/15/30 min, default 10, persisted in the vault settings table, applied live to the idle timer) + a read-only base-currency display. No schema change. Spec /cold-eyes-converged (4 loops); TDD (19-leg tests/features/settings/); /audit 0, /indie-review 3 cold lanes clean (2 test-fidelity LOWs folded). Gate green 343 passed/1 skipped, mypy 0. Theme toggle + stored-PDF-password management remain in FIBR-0014.

  Scope (settle exact list at spec time -> /cold-eyes before TDD):
  - A **Settings** entry in the menubar (and/or a toolbar/Window-menu action)
    opening a Settings screen — a tab or a modal dialog (decide at design;
    a modal keeps it out of the tab rotation, a tab matches the workspace).
  - **Auto-lock timeout (the priority):** the FIBR-0004 idle auto-lock currently
    uses a FIXED inactivity timeout; make it user-configurable (e.g. 1/5/10/15/30
    min, with a sensible floor; a "never" option only behind an explicit warning
    since it defeats the security spine). Applied live to the running idle timer;
    persisted so it survives a restart. Persistence home to settle: the vault
    settings table (it is only needed while unlocked) vs the plaintext settings
    sibling used for window geometry (non-sensitive) — likely the vault settings
    table, read on unlock.
  - **Other settings suggested (cheap, tie into what exists; trim at design):**
    - Base / display currency (already a vault setting from FIBR-0004 — surface it).
    - Theme: dark / light / follow-system toggle (deferred to FIBR-0014 at spec
      time — the toggle needs the theme system that phase's polish pass builds).
    - Manage stored PDF passwords (FIBR-0009 stores per-account PDF passwords) —
      view which accounts have one remembered + a "forget" button.
    - "Confirm before deleting a statement" toggle (for the FIBR-0052 delete).
    - Startup tab preference (which workspace tab opens on launch — ties to the
      FIBR-0052 last-tab persistence).
    - "Check for updates" on/off (the opt-in switch FIBR-0054 auto-update needs;
      off by default — the update check is the one deliberate, consented egress).
    - Number / date format override (deferred at spec time: locale *number*
      formatting → FIBR-0017 i18n; user-chosen *date* format → FIBR-0048).
  - Every new string tr()-wrapped, layouts (no fixed geometry) for RTL, amounts
    via QLocale (coding.md §5.2), consistent with the rest of the UI.

  Dependencies: FIBR-0004 (auth + idle auto-lock), FIBR-0052 (shell). Relates to
  FIBR-0014 (P12 settings — narrowed to backup + theme polish + i18n host),
  FIBR-0009 (stored PDF passwords), FIBR-0054 (update-check opt-in).
  **Layman:** Adds a Settings menu where you can change how the app behaves — first and foremost, how long it waits before locking itself when you step away (right now that time is fixed). Also a home for a few other handy toggles.
  Kind: feature.
  Source: user-request-2026-07-09.

### 📦 Packaging

- ✅ [FIBR-0003] **P01: bundling smoke-test (de-risk
  native libs early).** Freeze the trivial placeholder app into
  a one-file **AppImage** *and* a PyInstaller bundle, then launch
  each on a clean target with **no Python installed**, confirming
  the CPython runtime + a stub load of all three native stacks —
  SQLCipher, Qt, and qpdf/`pikepdf` (scope broadened to the third
  stack per the FIBR-0003 spec, 2026-07-01). This surfaces
  the native-lib collection risk named in ADR-0007 *now*, not
  after ten phases are built on top. Full multi-platform
  packaging + publish pipeline is deferred to P13. Dependencies:
  FIBR-0001. Lanes: build, ci. Kind: chore. Source: planned.
  Resolved 2026-07-01: closed by /close-phase. `--self-test` loads all three native stacks; `build-smoke.sh` freezes a PyInstaller onefile + AppImage in a `python:3.12-slim-bookworm` container (glibc floor ~2.36; wheels' own floor 2.34) and both print `FINBREAK_SELFTEST_OK` in the Python-free `debian:13-slim` clean-room — ADR-0007's clean-machine criterion proven at P01. The de-risk empirically caught 5 real portability traps (host-glibc mismatch, static manylinux Python, missing Qt system libs, missing harfbuzz, missing libGL). Toolchain pinned (INV-4); opt-in build stage + weekly CI job keep the everyday gate fast. Impl commit 49e87b6; /audit + /indie-review zero actionable on the close pass (3 doc/comment drifts fixed inline). Tag FIBR-0003-complete.

---

- ✅ [FIBR-0054] **Optional in-app auto-update (check → prompt Later/Skip/Update now → download, install, relaunch).**
  User request 2026-07-09: the app must offer (never force) updates. Flow:
  on a new version, prompt the user with three choices — **Later** (re-ask next
  launch), **Skip** (this version, don't re-prompt for it), **Update now**. On
  "Update now": download the latest build, close the app, install the update, and
  relaunch automatically.
  Progress (2026-07-10): brainstormed + design approved. Scope = full in-app auto-update, Linux/AppImage first (Windows seam only, not built). Two phases: (1) real release infra — version 0.1.0, signed release AppImage, published v0.1.0 GitHub Release; (2) the updater — opt-in launch check → Later/Skip/Update-now prompt → download + Ed25519-signature-verify → atomic AppImage swap → relaunch. Integrity gate = Ed25519 signature verified via the already-bundled `cryptography` lib (no new runtime dep/tool). Next: write docs/specs/FIBR-0054.md → /cold-eyes.
  Resolved (2026-07-14) by /close-phase. Code-complete since v0.1.0 and field-proven through v0.1.9; the live auto-relaunch confirmed v0.1.8->v0.1.9 (commit 8e4a298) was the last gate before close. Close ran a full audit (semgrep/ruff/bandit/gitleaks) + 2 cold indie-review lanes over the auto-update surface: 1 MEDIUM (_on_download_failed missing the auto-lock guard its ready-sibling has) + 3 LOW (temp-staging outside the try; 2 test-fidelity) all fixed inline (commit 67132c1); 2 semgrep dynamic-urllib FPs allowlisted (allowlist-001). Gate green 856/1. Tag FIBR-0054-complete. Windows in-app auto-update is FIBR-0131 (separate).

  Design notes (to settle when picked — needs its own brainstorm + spec →
  /cold-eyes):
  - **Per-platform mechanism** (no single cross-platform updater). *FIBR-0054
    has since settled the **Linux AppImage** slice: full-file download + atomic
    replace + Ed25519 verify (D2 rejected zsync/delta; D1 chose Ed25519 via the
    bundled `cryptography`, not AppImageUpdate). The other platforms below remain
    to-settle.* Linux AppImage → AppImageUpdate / zsync + delta; Flatpak/Flathub
    → the platform updates it
    (an in-app updater would be redundant/blocked there — likely just deep-link to
    the store or no-op); Windows .exe → a bundled updater (e.g. WinSparkle) or a
    small helper that swaps the install after exit; macOS .app → Sparkle. The
    "close → install → relaunch" hand-off is the platform-specific hard part.
  - **Update source + integrity:** check GitHub Releases (the repo already
    publishes there); verify a signature / checksum before installing (security —
    never run an unverified downloaded binary). Respect the no-network default
    elsewhere: the update check + signed download are the one deliberate outbound
    flow, opt-in via a setting, off by default until the user consents.
  - **UX:** a non-blocking prompt (not a modal that traps them); "Skip this
    version" persists the skipped version (in the plaintext settings sibling, like
    window geometry — not the vault); works while locked (no vault needed to
    update). Show current vs available version + changelog link.
  - **Depends on** the release pipeline (ADR-0007 / FIBR-0003 bundling) being able
    to publish signed artifacts. Sequence after the core app is feature-complete;
    not blocking FIBR-0052/P08/P09.
  **Layman:** The app checks for a newer version and, if you choose, downloads and installs it for you and reopens — you're always in control (Later, Skip this version, or Update now).
  Kind: feature.
  Lanes: packaging, ui, services.
  Source: user-request-2026-07-09.

- ✅ [FIBR-0132] **Windows `.exe` launches with a console window — build `--windowed` to suppress it.**
  FIBR-0015 froze the .exe with `--onefile` but not `--windowed`, so PyInstaller attaches a console (the black cmd window the user saw before the GUI). Fix: add `--windowed` in build-windows-exe.py. Wrinkle: `--windowed` sets sys.stdout/stderr to None on Windows (PyInstaller docs), so the windows-build.yml `--self-test` sentinel read (FINBREAK_SELFTEST_OK) goes blind — reroute the sentinel to a file via a FINBREAK_SELFTEST_OUT env var (run_self_test already takes an `out` stream) and have the workflow read the file + Start-Process -Wait for the now-GUI process. Regression-lock with a windows_build feature test asserting the driver builds --windowed.
  **Layman:** Stops the black command-prompt window from flashing up before the app opens on Windows.
  Kind: fix.
  Source: user-report-2026-07-14.
  Resolved 2026-07-14: `build-windows-exe.py` now freezes `--windowed`; self-test sentinel rerouted to FINBREAK_SELFTEST_OUT file so the clean-room read survives the None stdout; windows-build.yml reads the file via Start-Process -Wait. Regression-locked (test_driver_freezes_windowed_gui_exe + test_selftest_can_redirect_sentinel_to_a_file). Gate green 853/1. Ships in the next Windows release build.

- 🚧 [FIBR-0133] **Free Windows code signing via SignPath Foundation (OSS program).**
  User applying to SignPath Foundation's free code-signing program for OSS. Prep done this session: PRIVACY.md added (finbreak collects no data; local-only); README gained the required SignPath attribution ("Free code signing provided by SignPath.io, certificate by SignPath Foundation") which the hub site renders onto the download page (antsprojectshub.co.za/p/fin-break.html) — NOTE (2026-07-26 debt sweep): that attribution string is no longer in README.md, having been removed after the decline; it must be restored before any reapplication; Google Search Console verification + indexing done so the app is discoverable (a SignPath requirement — see [[finbreak-public-site-and-signing]]). Also fixed the stale milnet01/Fin_Break->finbreak repo slug in the hub data. REMAINING once approved: wire the SignPath signing step into .github/workflows/windows-build.yml so release .exe artifacts are signed; promote the .exe to a signed release asset. Requirements met: MIT license, public repo, GitHub 2FA (user to confirm), discoverable (in progress). Windows-only (macOS = Apple $99/yr; Linux AppImage GPG-signed already).
  **Layman:** Get finbreak's Windows app officially signed for free so Windows stops showing "unknown publisher" warnings.
  Kind: package.
  Source: user-request-2026-07-14.
  Scope boundary (2026-07-14): "promote the .exe to a signed release asset" above means the AUTHENTICODE/publisher signature only. The Ed25519-signed .exe release asset (the sidecar the in-app updater verifies) is FIBR-0131's D5, not this item. FIBR-0133 adds the Authenticode signature to that already-attached .exe once SignPath approves.
  Progress (2026-07-14): the SignPath "discoverable" requirement is now MET — the Fin Break page (antsprojectshub.co.za/p/fin-break.html) is live and INDEXED on Google (confirmed via a Google search result, ~3h after publish). Requirements now: MIT ✓, public repo ✓, PRIVACY.md + SignPath attribution ✓, discoverable ✓; REMAINING = SignPath's own approval ONLY (external, awaited); GitHub 2FA confirmed ON (2026-07-14, GitHub-mandated). All contributor-side SignPath requirements (MIT, public repo, PRIVACY + attribution, discoverable, 2FA) are now MET. No code work outstanding; FIBR-0131's Windows updater is already merged and waiting for the v0.1.10 release that will bundle both the Authenticode signature (this item) and the Ed25519 .exe.sig.
  Update (2026-07-16): SignPath Foundation DECLINED the application. Plan per the user: build more of a public presence first, then reapply and hope for approval next time. Stays 🚧 (blocked on the reapplication + their approval, not on any contributor-side prep — MIT/public/2FA/discoverable are all still met). Windows .exe remains un-Authenticode-signed meanwhile → SmartScreen "unknown publisher" persists; the Ed25519 updater sidecar sig is unaffected.

- ✅ [FIBR-0134] **Embed the finbreak icon in the Windows .exe (was PyInstaller's default console-stub icon).**
  The published v0.1.9 finbreak-0.1.9-x86_64.exe showed PyInstaller's default console-stub icon in Explorer/taskbar because scripts/build-windows-exe.py never passed --icon to the freeze. Fixed by adding `--icon assets/icon/finbreak.ico` (the committed multi-size 16..256 Windows icon from FIBR-0037) to the PyInstaller command, plus a fail-loud guard that the .ico exists and a windows_build regression test asserting the driver passes --icon and the .ico is a real MS icon. Driver flag only (like --windowed/FIBR-0132), so the Linux parity guard is untouched; the Linux AppImage icon travels separately via appimagetool. The icon-bearing .exe appears on the NEXT Windows build/release — the already-published v0.1.9 asset is not rewritten.
  **Layman:** Make the Windows app file show finbreak's donut icon in Explorer instead of a generic black terminal icon.
  Kind: fix.
  Source: user-request-2026-07-14.
  Resolved (2026-07-14): added --icon assets/icon/finbreak.ico to scripts/build-windows-exe.py + a fail-loud .ico-exists guard + a windows_build regression test (test_driver_embeds_the_app_icon). Gate-relevant tests green (windows_build 13 passed). Icon lands on the next Windows build.

- ✅ [FIBR-0152] **Update prompt shows only the latest release's notes — accumulate all changes since the user's version.**
  Gap (verified 2026-07-19): the UpdateDialog "What's new" panel is filled
  from GitHub's /releases/latest — a SINGLE release's body
  (services/update.py:224 `notes = release.get("body") or ""`;
  fetch_latest_release hits /repos/{owner}/{repo}/releases/latest,
  update_fetch.py:22). So a user N versions behind sees ONLY the newest
  release's notes; the intervening releases' notes are never shown. There is
  no in-app changelog viewer either (zero `changelog` refs under src/), and
  the notes panel deliberately has link-opening OFF (offline/no-egress
  posture, INV-12) so there is no "view full changelog online" fallback.
  Resolved (2026-07-28): SHIPPED by TDD, but NOT via Option A — a bundled
  CHANGELOG.md stops at the running version, so it cannot describe the
  releases the user has yet to install. Took the item's own alternative B,
  narrowed: the OFFER still rests solely on /releases/latest (D11 prerelease
  exclusion intact); a second, best-effort read of the same host's
  /releases list (new update_fetch.fetch_releases, sharing a new _get_json
  with fetch_latest_release, same cap + timeout) feeds only the notes;
  pure _accumulated_notes keeps every non-draft, non-prerelease body newer
  than the running version and no newer than the offered one, newest first,
  each headed by its version. Any failure of the second read degrades to the
  single body — it never costs the user the update. No new module and no new
  host, so INV-12 (one networked file) is unchanged; notes stay verbatim
  non-tr() release data. 6 new tests (list parse + URL, 3-behind accumulate,
  1-behind latest-only, draft/prerelease excluded, list-failure fallback,
  qtbot dialog renders the accumulated body). Gate: 1398 passed, 2 skipped.

  Recommended fix (Option A — best fit for the offline posture): ship
  CHANGELOG.md inside the bundle and have the update prompt show every entry
  BETWEEN the user's current __version__ and the latest available version. No
  new network surface; reuses the Keep-a-Changelog structure already
  maintained. A small version-range slicer over the local file feeds the same
  `notes` string the dialog already renders as markdown.

  Alternatives considered: (B) fetch /releases (all, not /latest) and
  concatenate each body newer than current — more network + a bigger response
  cap + prerelease filtering; (C) leave latest-only. Prefer A.

  Reproduce-first when built: a service-level test that, given current=0.3.0
  and a CHANGELOG containing 0.4.0/0.5.0/0.6.0 sections, returns the
  concatenated 0.4.0..0.6.0 notes (and latest-only when exactly one behind);
  plus a qtbot assertion that the dialog renders the accumulated body. Must
  preserve FIBR-0054 INV-12 (no new egress) and the lupdate/tr() posture
  (release notes stay non-tr() verbatim data).
  **Layman:** If you skip a couple of updates, the "What's new" box only tells you about the newest one — it should show everything that changed since your version.
  Kind: enhancement.
  Lanes: ui, services, packaging.
  Source: user-request-2026-07-19.

- 📋 [FIBR-0158] **Un-exclude the Debian 13 + Ubuntu 24.04 deb builds on OBS (home:milnet:finbreak).**
  Both RPM families (openSUSE Tumbleweed + Fedora 44) build, publish and install
  from OBS (FIBR-0155). The two deb targets (Debian 13, Ubuntu 24.04) are
  currently "excluded" — OBS finds no Debian source package to build. Two gaps to
  close, both verified-design work (rule 13 — confirm against OBS debtransform
  docs, don't recall):

    1. Author a `.dsc` at the OBS package root — OBS's debtransform only builds a
       deb when a `.dsc` is present. It needs the debtransform headers
       (Debtransform-Tar: the finbreak orig tarball; the debian/ dir). set_version
       must stamp its Version (add it to the lockstep, obs_packaging INV-6).

    2. Deliver vendor.tar.gz INTO the deb build tree. RPM gets it as Source1, but a
       deb build only unpacks the orig tarball — which does not contain vendor/.
       Cleanest: switch debian/source/format from "3.0 (native)" to "3.0 (quilt)"
       and ship the wheels as a component orig tarball
       (finbreak_<ver>.orig-vendor.tar.gz), which dpkg-source unpacks to vendor/ at
       the source root, where debian/rules already looks (--find-links vendor/).

  Then expect the same class of per-distro fixes the RPM bring-up surfaced, found
  empirically from the OBS build logs:
    - Debian/Ubuntu apt names for the freeze-time libs (libgthread-2.0.so.0 is in
      libglib2.0-0 on Debian; the krb5 lib is libgssapi-krb5-2; collect-set is
      libgl1/libegl1/libxcb*/...).
    - python3 default per target: Ubuntu 24.04 = 3.12, Debian 13 = 3.13 — both
      already vendored (cp312 + cp313), no extra ABI.
    - lintian is far more lenient than openSUSE rpmlint on a bundled tree; watch
      dpkg-shlibdeps on the private /usr/lib/finbreak (debian/rules already
      excludes it via -Xusr/lib/finbreak).

  Driver: iterate with packaging/obs/obs-submit.sh + obs-status.sh, reading each
  deb build log, exactly as the RPM targets were brought up. See
  packaging/obs/README.md "Still open".
  **Layman:** Get the .deb version of finbreak building on the build service too, so Debian and Ubuntu users get a native package (right now only the openSUSE/Fedora RPMs build; the .deb targets are skipped).
  Kind: package.
  Source: user-request-2026-07-23.

- 🚧 [FIBR-0159] **Publish finbreak to Flathub — the cross-distro app store (GNOME Software / KDE Discover).**
  Flathub is the de-facto cross-distro app store: one submission surfaces finbreak
  in GNOME Software + KDE Discover on openSUSE, Fedora, Ubuntu, Debian, Mint, etc.
  Unlike the official distro archives (which forbid bundling and need a maintainer
  sponsor — impractical for finbreak's deliberately-bundled runtime), Flathub is
  self-publish and embraces the self-contained/sandboxed model, so it fits.
  Design (chosen, docs/specs/FIBR-0159.md — /cold-eyes CONVERGED loop 8, signed off
  2026-07-23; a SEPARATE build pipeline from OBS — flatpak-builder + a manifest, not
  rpm/deb):
    - Build on the freedesktop 25.08 runtime + the pinned pip-wheel closure
      (PySide6==6.11.1 carries its own Qt6) — NOT the PySide6 BaseApp (tops out at
      6.10, forks the pinned stack) and NOT the KDE runtime (no 6.11 branch). The
      manifest io.github.milnet01.finbreak.yaml pip-installs the sha256-pinned
      closure (packaging/flatpak/python3-deps.yaml, generated by
      generate-pip-sources.sh — --prefer-wheels DERIVED from the closure, never
      hand-listed) into /app, then pip-installs finbreak from its git clone.
    - Reuse the existing AppStream metainfo + .desktop + icons shipped under
      packaging/obs/ (single source of truth — installed from the finbreak module's
      own git clone so a standalone-submitted manifest still finds them, ADR-0007).
    - Minimal, network-free, portal-only sandbox: NO --share=network (app networking
      unreachable at the OS level), NO --filesystem=* (import/export go through the
      xdg-desktop-portal chooser, granting only the file the user picks), NO
      --talk-name=*. The updater is inert under Flatpak by construction (no $APPIMAGE
      / not a frozen exe → detect_installer() is None) — no build-time gating needed.
      One small src change: gate _kde_wayland() off under Flatpak so the unreachable
      org.kde.KWin window-centering call is honestly disabled (INV-8).
    - Submit to github.com/flathub/flathub (PR on the new-pr base branch), pass the
      reviewer round, then Flathub builds + hosts it.
  Progress (2026-07-23): spec CONVERGED (cold-eyes loop 8) + signed off; implementation landed — packaging/flatpak/ (manifest, generate-pip-sources.sh, python3-deps.yaml, flatpak-build.sh, README), the _kde_wayland() Flatpak gate (main_window.py, INV-8), security-model.md INV-8 note, and tests/features/flatpak_packaging/ (INV-1..8). Local flatpak-builder build + portal smoke next, then the Flathub new-pr submission.
  Local build VALIDATED (2026-07-23): flatpak-builder builds green offline from the sha256-pinned closure (24 sources, ofxparse the one sdist); `flatpak run --command=finbreak … --self-test` → FINBREAK_SELFTEST_OK (Qt+SQLCipher+qpdf travelled); sandbox network-isolated (in-sandbox connect → OSError, proving no --share=network); full gate green (1258 passed). Two gate fixes folded in: types-PyYAML mypy stubs + a .gitleaks.toml allowlist for the flatpak-builder artifacts (.build/.repo/.flatpak-builder). REMAINING before Flathub submit: (1) manual live-host §5 smoke on KDE-Wayland — portal file open + PDF/.fbk export, Center-window disabled, real screenshot URLs; (2) re-pin the manifest to a release tag/commit (currently v0.1.16); (3) open the flathub/flathub new-pr PR — an outward-facing action, awaiting user go-ahead.
  Decision (2026-07-28, user): KEEP the app id io.github.milnet01.finbreak for
  the Flathub submission — do not switch to the user's own domain
  (antsprojectshub.co.za). Flathub accepts a reverse-DNS id based on a
  code-hosting account you control, 0.1.18 already shipped with this id, and a
  rename would churn the desktop file, icon filenames, metainfo id, the Flatpak
  manifest and the OBS spec while making existing RPM installs look like a
  different app. The domain is still the right HOMEPAGE value in the manifest and
  metainfo — that field is independent of the id. (User data is unaffected either
  way: paths.py keys AppDataLocation on applicationName "finbreak", not the id.)

  Follow-up (optional, lower priority): the Snap Store (Ubuntu-led, also
  self-publish, also appears in the software centres) — a snapcraft.yaml. Do after
  Flathub. Official distro archives are out of scope (bundling policy).
  **Layman:** Get finbreak into the main Linux app store (Flathub), so users on any distro can find and install it from their graphical Software centre with one click — the single biggest reach-the-most-people step.
  Kind: package.
  Lanes: packaging, release.
  Source: user-request-2026-07-23.

- 📋 [FIBR-0160] **Add openSUSE Leap 15.6 as an OBS target (deferred — Leap ships no python 3.12+).**
  Attempted 2026-07-23: added the Leap 15.6 target + a %if 0%{?sle_version}
  python313 build branch, but the build went "unresolvable" — osc buildinfo:
  "nothing provides python313, python313-devel, python313-pip". Leap 15.6 (SLE 15
  SP6) has no python313 (nor 3.12/3.14); we vendor only cp312/cp313/cp314. The Leap
  target was removed to keep the project clean; the spec keeps the %{py3}/%{py3pkg}
  abstraction (harmless — resolves to python3 on every active target).

  To enable later:
    1. Confirm Leap 15.6's newest python3XX module (`osc buildinfo` against
       openSUSE:Leap:15.6, or the Leap package index) — likely python311 (3.11).
    2. Vendor that ABI (add it to vendor-wheels.sh's PY loop) — all deps must
       publish that cpXX wheel (PySide6/cryptography are abi3 so fine; check
       sqlcipher3-wheels, lxml, pikepdf, Pillow, cffi, charset-normalizer).
    3. Set the sle_version branch's %{py3pkg} to that module (e.g. python311) and
       %{py3} to its interpreter (python3.11).
    4. Re-add the openSUSE_Leap_15.6 repo (obs-setup.sh) + rebuild.

  Lower priority than FIBR-0159 (Flathub), which serves Leap users through GNOME
  Software / KDE Discover regardless.
  **Layman:** Offer a native openSUSE Leap package too. Parked for now: Leap's software repos don't carry a new-enough Python to match our bundled parts, and Flathub will reach Leap users in the meantime.
  Kind: package.
  Source: user-request-2026-07-23.

- 📋 [FIBR-0161] **Fold the Flathub `flathub.json` arch-restriction into the FIBR-0159 spec §5 checklist.**
  During FIBR-0159 submission prep we found the pinned wheel closure is
  x86_64-only, but Flathub's buildbot builds every arch by default — so the
  submission needs a `flathub.json` with `only-arches: [x86_64]` or the aarch64
  build fails. Implemented in packaging (packaging/flatpak/flathub.json + INV-9
  test locking only-arches to the closure's wheel arches), but the signed-off
  FIBR-0159 spec §3.4/§5 pre-submit checklist never mentions it. Fold in an arch
  line — but the spec is a design doc, so the edit runs through /cold-eyes
  (--max-loops 7, CLAUDE.md rule 14) rather than an inline patch.
  **Layman:** The Flathub packaging now ships a small config that tells Flathub to build only for the PC (x86_64) chip we have the parts for; the design document should mention it.
  Kind: doc-fix.
  Source: in-session-2026-07-23.

- 📋 [FIBR-0184] **bump.json's Flatpak re-pin todo names a tagging step the release path doesn't use, so `git rev-parse v<NEW>` fails locally.**
  Hit during the v0.1.18 release. The `.claude/bump.json` todo for the
  Flatpak `commit:` pin says to set it "AFTER `git tag -a v{NEW}`" — but
  nothing in the release path runs `git tag -a`. `scripts/release-linux.sh`
  creates the tag through `gh release create`, which creates it on the
  REMOTE only. So the local clone has no such ref and the todo's own
  follow-up command fails:

      $ git rev-parse v0.1.18^{commit}
      fatal: ambiguous argument 'v0.1.18^{commit}': unknown revision ...

  The fix is a `git fetch --tags origin` before the rev-parse (that is what
  unblocked it here). Two candidate homes, either is fine:
  (a) reword the bump.json todo to name the real sequence — run
  release-linux.sh, `git fetch --tags`, then rev-parse; or
  (b) better, fold the whole step into release-linux.sh after the release is
  created, since the sha is known there and the manual step exists only
  because the tag does not exist at bump time. (b) removes the todo
  entirely rather than correcting it.

  Low severity — it costs one confusing failure per release, and the
  flatpak_packaging tests (INV-4 40-hex sha, INV-10 tag == __version__)
  still pass either way because they cannot tell whether the tag and the
  commit point at the same object. That blind spot is the reason this is a
  manual step at all, so a wrong instruction here is worth fixing.
  **Layman:** A release checklist step tells you to look up something that isn't on your computer yet, so it fails until you fetch it first.
  Kind: doc-fix.
  Source: in-session-2026-07-28 (v0.1.18 release).

- ✅ [FIBR-0188] **The AppImage's embedded .desktop name doesn't match the app id, so the panel shows a second icon.**
  Verified 2026-07-28 by source read (user screenshot shows the duplicate).
  Resolved (2026-07-28): SHIPPED. Two new build vars — APP_ID (the .desktop basename AND the bundled icon name, which appimagetool requires to match Icon=) and APP_WM_CLASS (the X11 half, from applicationName(), the bare "finbreak") — both defaulting to $ONEFILE so the self-test stub is byte-identical. Also corrected the app.py comment that ASSERTED the AppImage already shipped a reverse-DNS .desktop; it never did, and that unverified claim is why the mismatch survived. Tests derive expectations FROM app.py, so a future app_id change fails the test rather than silently desyncing the launcher. Source-scan only — the grouping is empirical and proves out on the NEXT release's AppImage, not the published 0.1.18 one. Gate: 1403 passed.

  The mismatch, exactly:
    - src/finbreak/app.py:48 calls
      QGuiApplication.setDesktopFileName("io.github.milnet01.finbreak"), so the
      window announces that app id (Wayland app_id / the desktop-entry association
      key).
    - scripts/_build-smoke-in-container.sh:169 writes the AppImage's embedded
      launcher as "$ONEFILE.desktop" = finbreak.desktop, with Icon=$ONEFILE and NO
      StartupWMClass line at all.

  So a compositor/panel resolving the window's app id looks for
  io.github.milnet01.finbreak.desktop and finds finbreak.desktop instead. No
  match, so the running window cannot be grouped with its launcher and appears as
  a second, separate panel entry. On X11 the same gap shows up differently: the
  xcb backend derives WM_CLASS from applicationName() ("finbreak"), and with no
  StartupWMClass key the association rests on the basename coincidence alone.

  NOT a bug in the RPM/deb path: packaging/obs/io.github.milnet01.finbreak.desktop
  is already named for the app id AND carries StartupWMClass=finbreak, which is
  the pairing this item brings to the AppImage.

  Fix: name the embedded file for the app id and add the X11 key — i.e. an APP_ID
  variable (defaulting to $ONEFILE so the self-test smoke stub is unchanged, with
  the release build exporting io.github.milnet01.finbreak), write
  "$APP_ID.desktop", add StartupWMClass=$ONEFILE, and rename the bundled icon to
  $APP_ID.png with Icon=$APP_ID so it keeps matching (appimagetool requires the
  icon to match the Icon= key). Mirrors the obs/ launcher exactly.

  Verify: this cannot be proven by a source-scan alone. Build the AppImage
  (scripts/build-release-appimage.sh), run it, and confirm with
  `xprop WM_CLASS` (X11) or the panel grouping (Wayland) that one icon appears.
  A test can pin the generated .desktop's basename + keys; the grouping itself is
  empirical, like the FIBR-0131 PowerShell legs.
  **Layman:** Running the AppImage puts a duplicate finbreak icon in the taskbar instead of lighting up the one you pinned.
  Kind: fix.
  Source: user-request-2026-07-28 (screenshot: duplicate panel icon).

- 📋 [FIBR-0206] **AppStream metainfo points at six screenshots that 404 — appstreamcli validate fails.**
  Found while validating the metainfo during the v0.1.19 bump.
  `appstreamcli validate packaging/obs/io.github.milnet01.finbreak.metainfo.xml`
  exits non-zero: `✘ Validation failed: warnings: 6`, all six
  `screenshot-image-not-found`.

  Verified live 2026-08-02, not inferred from the validator — every URL was
  fetched and all six return **HTTP 404**:
  `https://antsprojectshub.co.za/img/finbreak/{dashboard,transactions,categories,recurring,transfers,rules}.png`

  Pre-existing, and NOT caused by the v0.1.19 metainfo edit (that only
  prepended a `<release>` block; the warnings are all on `<screenshot>`
  elements). The file's own header comment at `:5` names `appstreamcli
  validate` as the check, so the intended gate exists and is red.

  Why it matters rather than being cosmetic: this is the file GNOME
  Software and KDE Discover read. A listing whose screenshot URLs 404
  renders with **no screenshots at all** — the single biggest thing a
  store page uses to sell an app. It also bears on **FIBR-0159** (Flathub,
  🚧): Flathub's submission CI runs `appstreamcli validate`, so this is
  plausibly a submission blocker, not just a wart. Worth confirming what
  severity Flathub gates on before assuming it passes.

  The assets themselves exist in-repo (`assets/` holds the README
  screenshots, refreshed for FIBR-0113 on 2026-07-30) — so this is a
  publish-and-point problem, not a capture problem. Two candidate fixes:
  upload the six PNGs to the antsprojectshub.co.za path already
  referenced (the download page repo is `milnet01/antsprojectshub`,
  `build.mjs` → `dist`), or re-point `<screenshot>` at raw
  `github.com/milnet01/finbreak` URLs, which need no second repo to stay
  in sync. Note the two surfaces have drifted before, so whichever is
  chosen wants a check that keeps them together.
  **Layman:** The Linux app-store listing links six screenshots that aren't actually online, so the listing would show none.
  Kind: fix.
  Lanes: release, docs.
  Source: in-session-2026-08-02 v0.1.19 release.
  Progress (2026-08-02): root cause narrowed, and it is NOT a missing
  upload — the images are published and live. The metainfo simply has the
  wrong path shape.

  The site repo (`milnet01/antsprojectshub`) holds all six at
  `src/assets/img/shots/finbreak-<name>.png`, and its build serves them at
  `/assets/img/shots/`, not `/img/finbreak/`. All six verified live
  2026-08-02 — `https://antsprojectshub.co.za/assets/img/shots/finbreak-{dashboard,transactions,categories,recurring,transfers,rules}.png`
  each return **HTTP 200**, while the two shapes the metainfo could have
  meant (`/img/finbreak/<name>.png` and `/img/shots/finbreak-<name>.png`)
  both 404.

  So the fix is a six-line URL correction in
  `packaging/obs/io.github.milnet01.finbreak.metainfo.xml`, mapping
  `/img/finbreak/<name>.png` → `/assets/img/shots/finbreak-<name>.png`.
  Note the basename gains the `finbreak-` prefix as well as the path
  change, so a path-only sed will still 404.

  Deliberately NOT fixed in this session: it is outside the v0.1.19 release
  scope this session was asked for, and the release does not depend on it.
  The remaining open question is unchanged — whether to point at the site
  (one more place to keep in sync when screenshots are refreshed) or at raw
  `github.com/milnet01/finbreak` URLs, which need no second repo. Whichever
  is chosen, verify with `appstreamcli validate` afterwards; that is the
  check that is currently red.

- 📋 [FIBR-0208] **The AppImage's bundled libxkbcommon segfaults on X11 keymap data it can't parse.**
  Found 2026-08-02 while probing FIBR-0200 in a throwaway environment; it
  is the app-side finding of that probe, not the probe's own fault.

  `dist/finbreak-0.1.19-x86_64.AppImage` SIGSEGVs against a plain X server
  (Xvfb), coredump frame #0 inside the BUNDLED `libxkbcommon.so.0`
  (`+0x1d9b8`). It dies at startup or on the first keystroke, and loading a
  keymap first (`setxkbmap us`) does not help. Forcing the system copy —
  `LD_PRELOAD=/usr/lib64/libxkbcommon.so.0` — makes the SAME AppImage run
  to completion: unlock, every tab, clean quit. So the bundled library is
  what fails, not the app.

  Not exotic-display-only. On the maintainer's own desktop the same bundled
  copy logs, on every launch,
  `xkbcommon: ERROR: /usr/share/X11/locale/en_US.UTF-8/Compose:1661:1:
  unrecognized keysym "dead_hamza"` (repeated down the Compose file)
  against the system's newer `xkeyboard-config` data — the same version
  skew, milder symptom, already visible in the journal today.

  Risk: this library ships to every Linux user of the AppImage, and a
  distro whose X11 locale data is newer than the bundled parser expects
  gets a noisy log at best and the reproduced segfault at worst.

  Provenance not yet pinned: the copy is either PySide6's wheel bundle or
  the `python:3.12-slim-bookworm` build container's system library (Debian
  12 is older than most target desktops). Establishing which comes first —
  the fix is then to exclude it from the freeze so the host copy is used,
  or to build against newer keyboard data.
  **Layman:** The app carries its own copy of a keyboard-layout library that is older than the system's keyboard data — it crashed in testing.
  Kind: fix.
  Source: in-session-2026-08-02 FIBR-0200 pre-check.

## P02 — Vertical slice: the security spine (target: after P01)

**Theme:** the smallest end-to-end feature that touches every
layer — and deliberately the **encrypted-storage spine**, since
security is the load-bearing concern. Proves UI → service →
repository → encrypted vault → output → test before any feature
lands on top.

### 🔒 Security

- ✅ [FIBR-0004] **P02: master password → encrypted vault
  → one manual transaction → table → lock.** First-run sets the
  master password + base currency; `CryptoService` derives the
  key with **Argon2id** (parameters pinned in security-model.md
  INV-2) and
  opens the **SQLCipher** (AES-256) vault; `AuthService`
  unlocks/locks and wipes the key from memory on lock; the user
  manually enters one transaction (through a repository, in a
  single DB transaction) and sees it in a table; locking returns
  to the unlock screen and the on-disk file is unreadable
  without the password. Verifies the whole security model
  (ADR-0003 + docs/security-model.md) concretely. Dependencies:
  FIBR-0001. (FIBR-0002 and FIBR-0003 also complete P01 first by
  phase-ordering, but are not direct code prerequisites of the
  vault.) Lanes: ui, services, repo, security, tests. Kind:
  implement. Source: planned.
  Shipped 2026-07-02. Security spine implemented TDD-first; audit (ruff/bandit/gitleaks/semgrep/mypy) clean and three cold 4-lane indie-review rounds converged (all findings fixed inline). Gate green 74 passed/1 skipped. Live language switching (retranslateUi) deferred to FIBR-0017 per user decision (spec deliverable shipped: tr() strings + RTL + QLocale amounts).

---

## P03 — Accounts

### 🎨 Features

- ✅ [FIBR-0005] **P03: multiple accounts per profile.**
  Account model + CRUD + accounts-manager UI; each account
  tagged with a type (current, savings, credit card, personal
  loan, home loan, investment, other). Transactions belong to an
  account — this must exist before any import. Dependencies:
  FIBR-0004. Lanes: ui, services, repo, tests. Kind: implement.
  Source: planned.
  Resolved (2026-07-02): shipped P03. Account model + CRUD, AccountService (validation + delete guard), AccountsWidget (add/edit/delete), the account picker + Account column + id→name join, and the first forward-only schema-migration runner (v1→v2: seed Default, backfill, atomic BEGIN…COMMIT/ROLLBACK). Migration transaction mechanism verified empirically vs sqlcipher3 0.6.0. Closed via 2 audit + indie-review rounds (all findings fixed inline — key-wipe on newer-vault open, wired the edit form, strengthened the INV-4 rollback test to a true atomicity test); gate green 100 passed/1 skipped, mypy 0, audit 0.

---

- 📋 [FIBR-0157] **Guided first-run wizard walks new users through the natural workflow: create accounts → import statements → categorise transactions → confirm/reject transfers.**
  A sequenced onboarding wizard (and, ideally, smaller task-level wizards) that
  guides a new user through finbreak's natural order of operations rather than
  leaving them to discover it:

    1. Create one or more accounts first (nothing else works without an account
       to attach transactions to).
    2. Import statements (CSV / OFX / PDF) into an account.
    3. Categorise the imported transactions (Type → Category).
    4. Confirm or reject the auto-detected transfers between accounts.

  Design intent / open questions to settle at spec time:
    - Trigger on first run (empty vault) automatically, and make it re-invokable
      later from a Help/menu entry — never a forced modal a returning user can't
      dismiss.
    - Each step should deep-link into the real UI (open the Accounts dialog, the
      Import flow, the Transactions tab filtered to Uncategorised, the Transfers
      review) rather than reimplementing those screens — reuse over rebuild.
    - Show progress ("step 2 of 4") and let the user skip ahead / come back; a
      step is "done" when its underlying data condition is met (≥1 account
      exists, ≥1 statement imported, no uncategorised rows, no pending transfers).
    - Correctness guard: the wizard only navigates and prompts — it must never
      itself write to the transactions table or bypass the transfer-confirmation
      step (transfers stay a user decision, per the transfers invariant).
    - Consider a lightweight "what next?" nudge on the dashboard once onboarding
      is complete but a natural next action exists (e.g. a new statement import
      left uncategorised).
  **Layman:** A step-by-step helper for newcomers that walks them through setting up the app in the right order, so a first-time user is never staring at an empty screen wondering what to do.
  Kind: feature.
  Source: user-request-2026-07-23.

## P04 — Category tree

### 🎨 Features

- ✅ [FIBR-0006] **P04: Type → Category tree (3rd level
  ready).** Self-referential `categories` table (`parent_id`),
  seeded Income/Expenditure types with sensible default
  categories (salary, sales / fast food, bills, medical,
  lottery…), and a category-management UI exposing two levels.
  Data model supports a future Sub-category level without
  migration. Dependencies: FIBR-0004, FIBR-0005. Lanes: services, repo, ui,
  tests. Kind: implement. Source: planned.
  Resolved (2026-07-02): shipped the categories aggregate (self-referential table + 2 seeded Type roots + 16 defaults), the QTreeWidget manager, and the v2→v3 migration. Spec cold-eyes-converged (7 loops); TDD; /audit + /indie-review 0 actionable on the closing pass. Gate green (122 passed/1 skipped, mypy 0). Transaction→category link deferred to P08 (FIBR-0010) by design. Journal: docs/journal/FIBR-0006.md. Tag FIBR-0006-complete.

---

## P05 — CSV import + mapping profiles

### 🎨 Features

- ✅ [FIBR-0007] **P05: CSV import with per-bank mapping
  profiles + dedup + import wizard.** `ImportService`
  orchestration + `CsvImporter` + saved per-bank column-mapping
  profiles (ADR-0005); de-duplication so re-importing an
  overlapping statement adds **zero** duplicates (success
  criterion 2); import wizard with a preview that shows per-row
  parse errors *before* anything is written. The first real
  import path; establishes the pipeline P06/P07 reuse.
  Dependencies: FIBR-0005, FIBR-0006. Lanes: services, importers, ui,
  repo, tests. Kind: implement. Source: planned.
  Design-ahead (user-request-2026-07-02): capture each imported
  statement's coverage period (start/end date) per account as
  first-class data AT IMPORT TIME — the reliable input for statement-gap
  detection (FIBR-0038). Bank PDFs print the period; for CSV (no period
  metadata) confirm it in the wizard. Cheap to add now, expensive to
  retrofit (would need re-import to learn periods). Establish the
  data-model hook here (the first importer) so OFX (FIBR-0008) and PDF
  (FIBR-0009) populate it too.
  Resolved (2026-07-03): shipped via /close-phase. CsvImporter + ImportService (exact-signature profiles, multiset-delta dedup, atomic write + coverage-period), v3->v4 migration (import_profiles + statement_periods), non-modal wizard. 43 tests (INV-1..11); gate green 165 passed/1 skipped, mypy 0; audit 0 + indie-review 0 CRIT/HIGH/MED (one LOW fixed inline: preview renders decimals not minor units). Tag FIBR-0007-complete.

---

## P06 — OFX import

### 🎨 Features

- ✅ [FIBR-0008] **P06: OFX import.** `OfxImporter` via
  `ofxparse`, feeding the same `ImportService` pipeline (dedup,
  categorisation, transfer detection) built in P05. OFX is a
  worldwide standard needing no mapping profile. Dependencies:
  FIBR-0007. Lanes: importers, services, tests. Kind: implement.
  Source: planned.
  Resolved (2026-07-04): P06 OFX import shipped. Pure OfxImporter -> the same ParseResult/ImportService pipeline as CSV (D2 _preview_from_result seam); embedded DTSTART/DTEND period (D4); payee-else-memo (D5); all-or-nothing-per-statement error model (D15); resource caps (D13); wizard OFX branch skips mapping + a multi-account chooser (D8/D10); no schema change (D9). Spec cold-eyes-converged (8 loops). Gate green 199 passed / 1 skipped, mypy 0; /audit 0, /indie-review fixed inline (deferred the tz-DTPOSTED day-shift -> FIBR-0042). FIBR-0003 build smoke re-run green (all five native stacks travel, incl. ofxparse/lxml; fixed a latent argon2 dep-drift in the build script en route). Tag FIBR-0008-complete.

---

## P07 — PDF statement import (incl. locked PDFs)

### 🎨 Features · 🔒 Security

- ✅ [FIBR-0009] **P07: PDF statement import with
  in-memory decrypt.** `PdfImporter` (`pdfplumber` table
  extraction) on the P05 pipeline; password-protected statements
  are decrypted **in memory only** (`pikepdf`, never written
  decrypted to disk); opt-in "remember this password" stores it
  **encrypted in the vault** against the account (default:
  prompt each time, store nothing). A wrong PDF password
  re-prompts rather than aborting the import. Dependencies: FIBR-0007.
  Lanes: importers, services, security, ui, tests. Kind:
  implement. Source: planned.
  Resolved (2026-07-04): PdfImporter (extract-then-CSV-adapter) + in-memory pikepdf decrypt + opt-in remembered password (v5 column) + wizard PDF branch. TDD; gate green 240 passed/1 skipped, mypy 0; FIBR-0003 build smoke PASS (native PDF tree travels). /close-phase: /audit 0, /indie-review 3 lanes (2 clean, 1 LOW coverage gap fixed inline). Free-text/OCR PDFs deferred (§ Out of scope). See docs/journal/FIBR-0009.md.

---

## P07.5 — App shell & first-run wizard (UX redesign)

### 🎨 Features · 🖥️ UX

---

- ✅ [FIBR-0051] **P07.5: app-shell UX redesign — real app window (QMainWindow) with menubar / icon toolbar / status bar; first-run & unlock as popups.**
  Replace the full-screen QStackedWidget swap model with a QMainWindow
  shell: menubar (File / View / Help / Donate), an icon toolbar
  (Manual entry / Import / Accounts / Categories / Lock, icon-above-
  label), a central swappable content stack, and a status bar that
  reports current activity (Ready / Importing… / Added transaction /
  Vault locked) plus a persistent transaction count. First-run and
  unlock become popup dialogs shown OVER the window (chrome greyed,
  content shows a Welcome / 🔒 Locked placeholder); idle auto-lock
  returns to the locked-shell state. Manual entry becomes a popup
  Add-Transaction dialog. Home = getting-started panel when empty,
  transaction table once populated (the P10 dashboard later replaces
  Home's body). Donate menu opens the .github/FUNDING.yml links
  (GitHub Sponsors / Patreon / PayBru) via QDesktopServices — a
  user-initiated hand-off to the OS browser; the app itself made no
  network calls at the time of this bullet (FIBR-0054 later added the
  one opt-in, off-by-default update check — your financial data still
  never leaves the machine). Reuses the existing
  accounts / categories / import screens as content views. Preserves
  FIBR-0004 security invariants: key wiped on quit, auto-lock fires,
  NO transaction data shown while locked, corrupt/incomplete-install
  guard at startup. Build order: this ships FIRST, then P08 rules +
  category link, P09 transfer detection, P10 dashboard drop into the
  ready-made content area. Out of scope (own phases): dashboard
  charts (FIBR-0012), rules screen (FIBR-0010), transfer prompts
  (FIBR-0011), branded app icon (FIBR-0037).
  Dependencies: FIBR-0004, FIBR-0005, FIBR-0006, FIBR-0007, FIBR-0008, FIBR-0009.
  **Layman:** Turn the bare password-box-then-form startup into a proper app window — menus, a toolbar of shortcuts, a status bar, and a first-run popup wizard — so it looks and feels like a real desktop app.
  Kind: implement.
  Lanes: ui, app, tests.
  Source: user-request-2026-07-05.
  Resolved (2026-07-09): shipped by /close-phase. QMainWindow shell + popup first-run/unlock/manual-entry dialogs + status bar + Donate menu; content destroyed-on-lock (no decrypted rows survive). TDD: 22 tests/features/app_shell/ + D10 ripple re-home; gate green 299 passed/1 skipped, mypy 0; FIBR-0003 build smoke PASS (icons travel into the frozen bundle, DoD #2). /audit clean; /indie-review 2 cold lanes — no CRIT/HIGH/MED, 2 LOW (status-bar Ready restore, locale-hermetic amount test) + 1 INFO (QIcon-absent rationale) folded inline. Tag FIBR-0051-complete.

- ✅ [FIBR-0052] **P07.6: tabbed main window + statement provenance & delete (shell v2).**
  Tabbed-workspace evolution the user approved 2026-07-09 (design brainstormed + approved this session), EXPANDED the same day by two follow-ups — exact per-statement transaction count + delete-a-statement-and-its-transactions — which pull the statement-provenance data model (planned as "Round 2") into this phase (user chose "all in one phase", 2026-07-09). Builds on the FIBR-0051 shell. Full contract: docs/specs/FIBR-0052.md.
  Resolved (2026-07-09): shipped by /close-phase. Tabbed QTabWidget workspace (Home · Statements · Accounts · Categories) + Home toolbar button + vault-independent Window menu (Center/Reset) + window geometry/last-tab persisted to a plain INI outside the vault; Statements tab (StatementService + StatementsWidget) with an exact linked-transaction count + atomic delete-statement-and-its-transactions; v5→v6 nullable transactions.statement_period_id FK + commit_import stamp (reordered period-first) + one-time ambiguity-guarded backfill; AccountsWidget/CategoriesWidget show_done flag; home.svg. TDD: 27 tests/features/statements/ + the FIBR-0051 app_shell ripple (nav/lock/manual-entry re-homed to the tab model) + the v5→v6 schema ripple across vault/accounts/categories/import_/ofx_import/pdf_import. Gate green 324 passed/1 skipped, mypy 0; home.svg travels via the existing ui/icons/*.svg glob (DoD #2). Real Standard Bank credit-card PDF validated end-to-end in a throwaway vault (53 txns, exact count, clean delete). /audit 0; /indie-review 3 cold lanes — no CRIT/HIGH/MED, security spine verified; 1 production LOW (locked-vault delete guard) + 1 test-fidelity + 4 coverage findings folded inline. Tag FIBR-0052-complete. P08/FIBR-0010 rules follows.

  Scope:
  - Central content area becomes a QTabWidget "workspace" with FIXED tabs: Home · Statements · Accounts · Categories. Mirrored under the View menu (both navigate); the tab widgets are PERSISTENT (a switch, not a rebuild). Reuses AccountsWidget/CategoriesWidget as tab pages via a `show_done` flag that retires their now-redundant "back to Home" button in tab mode.
  - Add a Home QAction to the toolbar (new house SVG glyph). Toolbar order: Home · Manual entry · Import · Accounts · Categories · Lock. Toolbar buttons switch tabs; Manual entry / Import still open their dialog / wizard (Import is a flow that replaces the workspace and returns to it, NOT a tab).
  - **Statement provenance (v5→v6 migration):** add a nullable `transactions.statement_period_id` FK; `commit_import` stamps every imported row with its source statement; manual entries stay NULL. A one-time ambiguity-guarded backfill links statements imported before the column existed (stamp account+in-span rows, skip dates covered by >1 period). Every importer already writes statement_periods via the single commit_import path, so no backfill of the record itself is needed.
  - **Statements tab (read + delete):** lists every imported statement (account · period · source file · imported-at · transaction count = rows linked via statement_period_id — exact for v6 imports, backfill-linked for pre-v6 imports; a statement with no linked rows shows 0, not an em-dash). A Delete action removes the statement record AND its imported transactions in one atomic service transaction (manual/other-statement rows untouched), after a confirmation naming the count; refreshes Home + the status count. New StatementService (services/statements.py) + StatementsWidget (ui/statements.py).
  - Home tab: unchanged from FIBR-0051 (getting-started ↔ table). Full categorised income/expenditure breakdown is still FIBR-0012.
  - Window geometry: remember size + position + toolbar state + last-active tab via QSettings in a plain INI (paths.window_settings_path()) OUTSIDE the encrypted vault (non-sensitive; restored before unlock). Add Center-window + Reset-layout actions in a vault-independent Window menu.
  - Security preserved: lock tears down the whole tabbed workspace (and any open import wizard) and shows the Locked placeholder (rebuilt on unlock) — FIBR-0051 INV-3 (nothing decrypted survives a lock). The delete is a service-owned atomic transaction leaving a re-openable vault on failure; the plain FK (no cascade) blocks an unsafe period-only delete.

  Staging (the rest, approved but separate items):
  - Follow-up (cheap now the stamp exists, not requested yet): a dedicated per-statement transaction VIEW (double-click a statement → its transactions read-only). Undo-of-delete also deferred.
  - Later (post-FIBR-0052): Home dashboard — income/expenditure summary + category breakdown; BLOCKED on P08 (FIBR-0010 category link) + P09 (FIBR-0011 transfer detection) for correct totals (self-transfers must not double-count). This is FIBR-0012's dashboard, pulled onto Home.

  Progress (2026-07-09): spec docs/specs/FIBR-0052.md written from the approved+expanded design; next /cold-eyes to convergence (rule §14) before TDD.

  Dependencies: FIBR-0051 (shell). Independent of P08/P09; runs before them.
  **Layman:** Turn the single content area into tabs (Home · Statements · Accounts · Categories), add a Home button to the toolbar, and make the window remember its size and position (plus a Center-window action). The Statements tab shows what you've imported with an exact transaction count and lets you delete a statement and all its transactions — which needs a small database change to tag each transaction with the statement it came from.
  Kind: implement.
  Lanes: ui, app, tests.
  Source: user-request-2026-07-09.

## P08 — Auto-categorisation rules

### 🎨 Features

- ✅ [FIBR-0010] **P08: rules engine + manual override.**
  `CategorizationService` applies a user-editable rule set to
  auto-assign categories; a manual override is the
  highest-priority signal and is never clobbered by re-import or
  a later rule. Rules-manager UI to view/add/edit. Dependencies:
  FIBR-0005, FIBR-0006, FIBR-0007, FIBR-0051, FIBR-0052. Lanes: services, ui, repo, tests. Kind: implement.
  Source: planned.
  Scope note (2026-07-09, spec drafted): the spec (docs/specs/FIBR-0010.md) grows this bullet's "rules-manager (view/add/edit)" summary to the full P08 slice — the transaction→category link (v6→v7), first-match-by-priority rules run on import + an explicit "Apply rules now", a manual per-transaction override that is frozen (never clobbered by re-import or a rule run), a Home Category column + "Set category…", the rules-manager tab (add/edit/delete/move/apply), an atomic delete-category cascade with a blast-radius confirm, and the learn-from-corrections offer pulled forward from FIBR-0035 (see that bullet). Deps widened to FIBR-0005/0006/0007/0051/0052.
  Resolved (2026-07-10): shipped. Rules engine + manual override + learning + delete-category cascade; schema v6->v7. TDD 45 tests; /audit 0, /indie-review 3 cold lanes + confirming pass (1 HIGH auto-lock + 3 MED test-coverage/naming + 1 LOW dedup-helper folded inline). Gate green 411/1, mypy 0. Tag FIBR-0010-complete; journal docs/journal/FIBR-0010.md.

---

## P09 — Transfer detection

### 🎨 Features

- ✅ [FIBR-0011] **P09: transfer detection
  (suggest-then-confirm).** `TransferDetectionService` matches a
  debit in one account against a credit in another (same amount,
  short date window) and **proposes** the pair; only
  user-confirmed pairs are linked as transfers and excluded from
  income/expenditure totals (success criterion 3, ADR-0006).
  Rejected pairs are remembered so they don't re-surface. Never
  auto-hides a real expense. Dependencies: FIBR-0005, FIBR-0007. Lanes:
  services, ui, repo, tests. Kind: implement. Source: planned.
  Progress (2026-07-12): design brainstormed + approved by user. Chose ±3-day match window, a dedicated Transfers tab (no post-import pop-up), and a single decision table (v7→v8) recording confirmed/rejected pairs (pending candidates recomputed live). Next: write docs/specs/FIBR-0011.md → /cold-eyes (7-loop cap) → TDD.
  Resolved (2026-07-12): shipped by TDD. Schema v7→v8 (transfer_pairs decision table, dual ON DELETE CASCADE, canonical UNIQUE); TransferRepository (candidate self-join — equal-magnitude/opposite-sign/different-account/±TRANSFER_WINDOW_DAYS=3, per-decision commits); TransferDetectionService (candidates/confirm/reject/unlink/confirmed_transfers/confirmed_transfer_txn_ids [the FIBR-0012 exclusion primitive]/confirm_all); the 6th Transfers tab (suggested+confirmed tables, Confirm/Reject/Confirm all/Unlink, VaultLockedError-guarded). tests/features/transfers/ one case per INV-1..12 + edges (window 0/3/4, off-by-one, two-debits, same-account, Cartesian, empty-vault); schema-version + tab-count ripple across 9 suites. Spec /cold-eyes-converged loop 4. Close: /audit 0 in the new code (3 pre-existing FIBR-0054 updater semgrep warnings out of scope); /indie-review 2 cold lanes — data/logic CLEAN, UI/shell 2 LOW (auto-lock test parametrized over all 4 slots; stale tab-count docstrings) folded inline. Gate green 645/1, mypy 0. Unblocks FIBR-0012 (dashboard).

---

## P10 — Reporting + dashboard

### 🎨 Features

- ✅ [FIBR-0012] **P10: dashboard — summary, pie/donut,
  trends, filterable table.** `ReportingService` aggregates by
  category / account / period; the dashboard shows the
  income-vs-expenditure summary, a category pie/donut, and
  month-to-month trends, per account or consolidated; the
  transaction table gains full search + filters (success
  criterion 1). **Charts library is chosen at spec time**
  (QtCharts vs matplotlib vs pyqtgraph — must be dark-themeable
  *and* render into the PDF) and recorded as an ADR. Dependencies:
  FIBR-0008, FIBR-0009, FIBR-0010, FIBR-0011 (OFX, PDF, rule-based
  categorisation, and **transfer detection** — so the consolidated
  income/expenditure totals correctly exclude transfers, SC3; CSV via
  FIBR-0007 is pulled in transitively, so all of CSV/OFX/PDF are
  consolidated — SC1 names all three). Lanes: services, ui, tests. Kind: implement.
  Source: planned.
  UX (user, 2026-07-11, dogfooding v0.1.2): the Home tab currently shows the raw transaction table (interim from FIBR-0051). The user confirms Home should be the income/expenditure SUMMARY (this dashboard), NOT the transaction list. So this item also owns relocating the transaction table off Home into its own view/tab (e.g. a "Transactions" tab) — carrying the full search + filters this item already promises — leaving Home for the summary + charts.
  **Layman:** The Home screen becomes a proper dashboard — a plain income-vs-spending summary, a pie chart of where your money goes, and month-by-month trends — while the transaction list moves to its own searchable, filterable tab.
  Design approved 2026-07-12 (brainstorming). Scope locked: QtCharts (ADR-0008, no new dep); ReportingService (period model default=previous month, persisted ReportPrefs; transfers never counted as income/expenditure anywhere); Home dashboard (period+account selectors, income/expenditure/net tiles, spending-by-category donut, monthly income-vs-expenditure grouped-bar trend); new Transactions tab absorbing FIBR-0109 (search + date-range + account + category filters, all combinable) with the transaction table relocated off Home. Tab order → Home·Transactions·Statements·Accounts·Categories·Rules·Transfers. Next: ADR-0008 + spec → /cold-eyes.
  Resolved 2026-07-13: shipped by TDD across 11 slices. ReportingService (pure period model + summary/spending_by_category/monthly_trend, transfers excluded, integer-exact) + ReportPrefs persistence; Home reworked into the QtCharts dashboard (donut + 12-month trend, ≤8-wedge collapse, empty-state placeholder); new Transactions tab with search+date+account+category filters (absorbs FIBR-0109); 7-tab shell, count live from Home's ReportingService, QtCharts self-test leg. Close: /audit 0 actionable; /indie-review 2 cold lanes → 3 findings all fixed inline (report_prefs year bound INV-2; per-table column-key objectNames; VaultLockedError-specific slot guards) + 2 regression tests. Gate green 712/1, mypy 0. Tag FIBR-0012-complete.

---

## P11 — Password-protected PDF export

### 🎨 Features · 🔒 Security

- ✅ [FIBR-0013] **P11: locked PDF export with section
  selection.** `PdfExportService` renders chosen sections
  (summary / charts / transactions) for a chosen period via the
  Qt PDF engine, then encrypts with a password set at export
  time (`pikepdf`, AES-256). Export dialog ticks sections + picks
  period + sets password (success criterion 5). Dependencies:
  FIBR-0012. Lanes: services, ui, security, tests. Kind: implement.
  Source: planned.
  **Layman:** Save a password-protected PDF report of your finances — pick which parts to include (summary, charts, transactions) and the date range, and set a password so only you can open it.
  UX (user, 2026-07-12): the export password must be OPTIONAL — the user can choose to add one, but an unprotected PDF export is a first-class supported outcome (not forced). So the "locked" in the headline is opt-in: the section-selection export flow offers an optional password field; empty → a normal unencrypted PDF, non-empty → the pikepdf AES-256 export-lock (ADR-0004). Design the dialog around that choice.
  In-progress 2026-07-13: spec docs/specs/FIBR-0013.md drafted (brainstorm-approved) and in /cold-eyes (project cap 7). Export password OPTIONAL per user; SC5 relaxed accordingly (discovery.md updated).
  Resolved 2026-07-13: P11 locked-PDF export SHIPPED by TDD (7 slices). PdfExportService (in-memory render → optional pikepdf AES-256, atomic export); ui/charts.py shared builders; ReportingService widened to an account set; ExportDialog (INV-14 gating + master-toggle state machine); File-menu + toolbar entry; --self-test encrypt leg. Close: /audit 0 in-scope; /indie-review 2 cold lanes → no CRIT/HIGH/MED, 3 LOW fixed inline (empty-donut placeholder, currency-symbol escaping, narrowed export except). Gate green 779/1. Tag FIBR-0013-complete.

---

## P12 — Settings, auto-lock, backup, theme polish

### 🔒 Security · 🎨 Features

- ✅ [FIBR-0014] **P12: settings, inactivity auto-lock,
  encrypted backup.** Settings screen (base currency display,
  auto-lock timeout, manage stored PDF passwords, theme);
  inactivity **auto-lock** drops the key and returns to unlock;
  **encrypted backup export/restore** (the only mitigation for a
  forgotten master password, per ADR-0003); dark-theme polish
  pass. Dependencies: FIBR-0004. Lanes: ui, services, security, tests.
  Kind: implement. Source: planned.
  **Layman:** A full Settings screen plus an encrypted backup you can export and restore — your one safety net if you ever forget your master password — and a light/dark theme choice.
  Note (2026-07-09): the Settings-screen scaffold + the user-configurable auto-lock timeout (+ base-currency read-only display) are pulled FORWARD into FIBR-0055 (near-term, user-requested); FIBR-0055's first cut delivers the scaffold + configurable auto-lock timeout + read-only currency only. This phase narrows to what remains: the encrypted-backup export/import (the only mitigation for a forgotten master password, ADR-0003), the dark-theme polish pass and its dark/light/follow-system theme toggle (a toggle needs the theme system this pass builds), stored-PDF-password management, and hosting the FIBR-0017 language switcher. If FIBR-0055 ships first, this becomes an extension of that Settings screen rather than a fresh one.
  Split (2026-07-13, in-session, user-approved): P12 bundled four independent pieces. Auto-lock is already shipped (mechanism FIBR-0114; user-configurable timeout + Settings scaffold + read-only currency via FIBR-0055). This item is now NARROWED to the encrypted backup export/restore only — the ADR-0003 forgotten-master-password mitigation, keyed by a SEPARATE backup password so it can actually recover a forgotten master password. The other three pieces are split into their own items: app-wide theme system -> FIBR-0127; stored-PDF-password management UI -> FIBR-0128; language-switcher hosting -> FIBR-0129 (note: overlaps FIBR-0017, which already owns the i18n picker — reconcile when either is specced). Build order: backup (this) first, then 0127, 0128, 0129. Spec: docs/specs/FIBR-0014.md (encrypted backup).
  Resolved 2026-07-13 (/close-phase). Shipped by TDD in 7 red→green slices + a fold-in of 6 cold-review findings. D2 SQLCipher mechanics (sqlcipher_export / PRAGMA rekey / cipher_compatibility / HMAC-on / no-plaintext-temp) validated by a throwaway spike on sqlcipher3-binary 0.6.0 (SQLCipher 4.12.0) before any code. BackupService(vault, auth) export/restore over a stdlib-zip .fbk (manifest.json + params.json + vault.db); separate backup password (fresh salt), INV-1..13. UI: Settings Export + pre-login Restore on unlock & first-run; synchronous main-thread export (INV-9); interrupted-restore reconciliation (INV-5). /audit 0 actionable (1 bandit B608 FP suppressed on a test); 2 cold review lanes → 6 findings (2 HIGH crypto/UI, 2 HIGH/MED, LOW) all fixed inline with regression tests. security-model.md T11 hedge dropped + .fbk untrusted surface added (cold-eyes clean). Gate green 841/1, mypy 0. Tag FIBR-0014-complete.

---

- 📋 [FIBR-0017] **P12: multi-language UI (i18n) — 6 bundled locales incl. RTL + language switcher.**
  Qt translation pipeline: every user-facing string is wrapped in `tr()` from the first UI onward (P02), `lupdate` extracts them to `.ts` catalogs, translations are compiled to `.qm` and loaded via `QTranslator` at startup and on live switch. Ships **6 locales**: English (base), Spanish, Simplified Chinese, Hindi, French, and **Arabic** (right-to-left). A language picker in the FIBR-0014 Settings screen switches locale. Numbers, currency, and dates render through `QLocale` (matters for a finance app — ties into the base-currency display), not hardcoded formats. The UI is built **RTL-ready** (layout mirroring) from P02 per design.md "Internationalization (i18n) & localisation", so Arabic is translate-and-ship; further RTL scripts (Hebrew, Urdu) are then a translation-only follow-up. NOTE: this stays cheap only if the string-externalization and RTL-safe-layout conventions are followed from P02 — retrofitting hardcoded English (and left-to-right-only layouts) across the whole feature stack is far more expensive. Dependencies: FIBR-0014 (settings screen hosts the switcher; transitively pulls the feature-complete UI so all strings exist to translate).
  **Layman:** Lets people use finbreak in their own language — ships in 6 languages to start (including Arabic, which reads right-to-left), with more addable later.
  Kind: implement.
  Lanes: ui, i18n, services, tests.
  Source: user-request-2026-07-01.
  Deferred from FIBR-0004 (P02) per user decision 2026-07-02: the three P02 screens (first_run, unlock, main_window) build their strings once in __init__ and do NOT implement live language switching (changeEvent → retranslateUi). coding.md §5.2 asks for this "from P02"; the FIBR-0004 spec deliverable required only tr() strings + RTL layouts + QLocale amounts (all shipped), and there are no translations to switch yet. When this phase lands, add changeEvent/retranslateUi to those three screens (and every screen built between P02 and here) so the language switcher takes effect without a relaunch.
  Scope note (2026-08-03, user request): loading the right catalog **at
  startup from the system language** is FIBR-0209, not this bullet. This
  item's "loaded via QTranslator at startup and on live switch" says the
  mechanism exists but never says which locale is chosen on a first run
  with no stored preference — FIBR-0209 pins that (system locale, full
  `pt_BR` then bare `pt`, else English) and the silent-fallback rule.
  Fold FIBR-0209 in if this is specced first; otherwise ship it after.

- ✅ [FIBR-0127] **App-wide six-theme (finance-flavoured) + follow-system theme system & modern polish.**
  Split from FIBR-0014 (P12). Nothing exists today: the app rides the system/Qt default palette (dark by convention) with NO stylesheet, no QPalette install, no theme setting key, no toggle (app.py sets no palette). This builds the theme system from scratch (Fusion + token-driven QPalette/QSS — ADR-0010): a non-vault `theme` pref with 7 values (`system` + six named themes Ledger/Parchment/Mint · Midnight/Graphite/Emerald), palette+stylesheet application at the app entry point, and live follow-system detection, plus the sleek modern polish (gradient/glow accents + grid row-highlighting). Widgets already READ the live palette (ui/icons.py _is_dark_theme, home.py ChartTheme from palette().text(), _amount.py fixed mid-tones) so they adapt once a palette is installed. Delivers FIBR-0116's live icon re-tint on theme switch (toolbar glyphs re-tint on the ThemeController themeChanged signal); the _amount.py palette-adaptive re-tinting stays deferred here. Hosted in the FIBR-0055 Settings dialog. (The old note that the code mis-cites ADR-0002 for the dark theme and "write a real theme ADR when specced" is done — ADR-0010 is that theme ADR; the icons.py citation is corrected in the spec.)
  **Layman:** A proper set of light and dark themes (six finance-flavoured looks) you can choose — or have the app follow your operating system's light/dark setting — instead of the app being dark-only.
  Kind: implement.
  Lanes: ui.
  Source: split-from-FIBR-0014-2026-07-13.
  Spec docs/specs/FIBR-0127.md + ADR-0010 written 2026-07-14 from the user-approved brainstorm (designed look, 6 finance themes Ledger/Parchment/Mint + Midnight/Graphite/Emerald, live follow-system, sleek modern polish: gradient/glow accents + grid row-highlighting, theme-aware toolbar icons). Cold-eyes next.
  Resolved (2026-07-14): SHIPPED by /close-phase (code). TDD 30-leg tests/features/theme/ (INV-1..13 + D3/D4) → ui/theme.py (six-theme token registry → build_palette/build_stylesheet, ThemeController with live colorSchemeChanged follow-system, non-vault pref) + app.py/main_window.py/settings.py wiring + D11 ADR-0002→ADR-0010 citation fixes. /audit 0 actionable (semgrep full + ruff/bandit/gitleaks via gate); /indie-review 2 cold lanes → no CRIT/HIGH/MED, 1 LOW (INV-10 pixmap-content re-tint falsifier) folded inline. Gate green 907/1, mypy 0. Tag FIBR-0127-complete; journal docs/journal/FIBR-0127.md.

- ✅ [FIBR-0128] **Forget remembered PDF statement passwords (per-account, Accounts screen).**
  Split from FIBR-0014 (P12). The store already EXISTS (FIBR-0009, schema v5): accounts.statement_pdf_password (nullable, vault-encrypted at rest, deliberately not selected into the Account dataclass for credential hygiene), with AccountsRepository.get_pdf_password / set_pdf_password. It is written implicitly during import and auto-tried; there is NO management UI. This item adds an Accounts-screen, per-account control to list accounts with a remembered statement password and forget (clear) it (placement + forget-only per spec FIBR-0128 D1/D5). (Distinct from the FIBR-0013 export password, which is ephemeral and never stored.)
  **Layman:** A per-account button to see which accounts have a remembered bank-statement password and forget (clear) it — the password itself is never shown.
  Kind: implement.
  Lanes: ui, security.
  Source: split-from-FIBR-0014-2026-07-13.
  Placement decided (spec FIBR-0128 D1, user directive 2026-07-14): the presence/forget controls live on the **Accounts screen** (per-account, selection-driven), NOT Settings — different accounts can have different statement passwords, so the per-account surface is the natural home. Forget-only (no reveal, no manual set); the secret never crosses into the UI. Spec written; /cold-eyes next.
  Resolved (2026-07-14): SHIPPED by /close-phase (code). TDD 8-leg tests/features/accounts/ (INV-1..5) → repo ids_with_pdf_password + service account_ids_with_pdf_password + ui/accounts.py Forget button/marker/handler. Presence is an id-set (never selects the secret column); the plaintext never crosses into the UI (INV-1). Forget-only, per-account, confirm-gated, VaultLockedError-silent; enable/disable recomputed before the None early-return so a post-Forget refresh disables the button. semgrep+bandit 0 on the changed surface; 1 cold review lane → production CLEAN, 2 LOW test-precision folded inline. Gate green 915/1, mypy 0. Tag FIBR-0128-complete; journal docs/journal/FIBR-0128.md.

- 📋 [FIBR-0129] **Host the language switcher in Settings (picker widget + language setting key).**
  Split from FIBR-0014 (P12). Strings are tr()-wrapped throughout and RTL-ready (app.setLayoutDirection), but there is NO QTranslator, no .ts/.qm, no language setting key, no picker. This provides the language-picker widget in the FIBR-0055 Settings dialog + a `language` settings key. The translation pipeline itself (lupdate -> .ts -> .qm -> QTranslator at startup + live retranslateUi) is FIBR-0017; gate the picker's usefulness on that, or ship the widget writing the key now and wire it when FIBR-0017 lands.
  **Layman:** A place in Settings to pick your language. The actual translations arrive with FIBR-0017; this just provides the chooser and remembers your pick.
  Kind: implement.
  Lanes: ui, i18n.
  Source: split-from-FIBR-0014-2026-07-13.
  Scope note (2026-08-03, user request): the `language` key this bullet
  adds must default to a `"system"` sentinel, not to `"en"` — FIBR-0209
  makes "follow the operating system's language" the out-of-the-box
  behaviour, so the picker's first entry is "System default" and an
  explicit pick is what overrides detection. Same shape as the timezone
  / date / time combos (`DATETIME_SYSTEM`, `ui/_datetime_prefs.py`),
  which this dialog already hosts.

- ✅ [FIBR-0135] **Auto-lock "Never" option — let the user disable the idle timer entirely.**
  User lives alone / rarely has visitors and doesn't want the idle auto-lock. Added 0="Never" to ALLOWED_AUTO_LOCK_MINUTES (listed LAST so a corrupt/absent value still falls back to the 1-minute floor, never to "Never" — the INV-1 safe-fail is preserved). _arm_timer stops the timer instead of starting it when Never; notify_activity gains an isActive() guard so user activity can't silently re-arm a disabled timer. Settings combo gains a "Never" label. Password-on-open and manual Lock button are unchanged; the key is still wiped on lock and exit. security-model.md T3 amended to record the accepted residual risk (an unattended unlocked session stays unlocked — a user choice, not a silent default). Reverses the FIBR-0055 D6 "no never option" decision by explicit user request. Kind: enhancement.
  **Layman:** Add a "Never" choice to the auto-lock setting so the app won't lock itself while you're away — you still type your password when you open it and can lock it any time with the Lock button.
  Kind: enhancement.
  Source: user-request-2026-07-14.
  Resolved (2026-07-14) — commit b915254. Auto-lock "Never" (0) added; _arm_timer stops on it, notify_activity isActive()-guarded, combo label + security-model T3 note. Gate green 862/1.

- 📋 [FIBR-0209] **Launch in the system language automatically, falling back to English.**
  User request 2026-08-03. On startup, detect the operating system's
  language and load that locale's translation automatically — the user
  should not have to find a setting to be understood.

  Resolution order (first hit wins):
  1. An explicit language the user picked, if one is stored (FIBR-0129's
     `language` key). An explicit choice always beats detection.
  2. The system language, via `QLocale.system()` — match on the full
     locale first (e.g. `pt_BR`), then fall back to the bare language
     (`pt`), so a regional variant still finds its base translation.
  3. English, if the system language is absent, unreadable, or has no
     bundled `.qm` catalog.

  Follow the project's existing sentinel shape: the stored `language`
  key should default to a `"system"` token exactly like
  `DATETIME_SYSTEM` in `ui/_datetime_prefs.py`, so "follow the system"
  is a real stored state and not merely the absence of a value. That
  also makes the Settings picker's first entry ("System default")
  consistent with the timezone / date / time combos already there.

  Two traps worth pinning in the spec:
  - The fallback must be **silent and total** — an unsupported language
    is the normal case for most of the world until more locales ship,
    so it must never surface an error or an empty UI, just English.
  - Detection runs BEFORE the first window is built, like the theme
    pref (`app.py` applies the theme before `MainWindow`), so the
    locked first window is already in the right language. The theme
    system's `load_theme_pref` allowlist-against-known-ids is the
    pattern to copy for validating a stored/detected language token.

  Depends on FIBR-0017 (the QTranslator pipeline + the bundled `.qm`
  catalogs must exist before there is anything to detect INTO) and
  FIBR-0129 (owns the `language` settings key this reads). Ship after
  both, or fold into FIBR-0017 if that is specced first.
  **Layman:** finbreak should open in whatever language your computer is set to, without you having to pick it. If it does not know your language, or does not have a translation for it yet, it opens in English.
  Kind: feature.
  Lanes: ui, i18n.
  Source: user-request-2026-08-03.

- ✅ [FIBR-0210] **Startup is bricked by a corrupt window.ini (int('') on last_tab).**
  From the FIBR-0204 sweep (MEDIUM, verified). `MainWindow._restore_geometry`
  reads `int(raw_tab) if raw_tab is not None else _TAB_HOME`. MEASURED: an INI
  containing `last_tab=` makes QSettings return `''` (NOT None), and `int('')`
  raises ValueError. It runs inside `MainWindow.__init__`, so it escapes past
  `app.py`'s `except VaultStateError` guard and the app never starts again until
  the user finds and deletes ~/.config/finbreak/window.ini.

  Reachable from a truncated sync after power loss, a hand-edit, or a downgrade
  from a future version that stores a tab NAME. Fix: `except (TypeError,
  ValueError): return _TAB_HOME` — the same defensive posture `auth.py`'s
  `auto_lock_minutes` already takes for a corrupt stored value, and the same
  allowlist-the-known-good shape as `theme.load_theme_pref`.

  While there, audit the other `window.ini` reads for the same shape.
  **Layman:** If the settings file that remembers your window size gets damaged, finbreak refuses to open at all until you find and delete it by hand. It should just fall back to the default.
  Kind: fix.
  Lanes: ui.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): `_restore_geometry` is fail-safe on every
  read. The audit the bullet asked for found three MORE brick shapes in the
  same function, not just `int('')` — `geometry` and `window_state` are handed
  to `restoreGeometry`/`restoreState`, and a plain string where a `@ByteArray`
  was written raises TypeError (measured, PySide6 6.9). New `_restore_blob`
  helper type-checks the blob and reports whether Qt actually applied it, so an
  undecodable geometry now falls back to `_DEFAULT_WINDOW_SIZE` instead of
  leaving the window unsized. `last_tab` is a try/except returning `_TAB_HOME`.
  Same shape found and fixed in `_table_state.remember_columns` (a corrupt
  `columns/*` key took down the tab being built). Tests: five parametrised legs
  in `test_INV5b_corrupt_window_ini_does_not_brick_startup` + one in
  table_state; four of five and the table_state leg verified red first.

- ✅ [FIBR-0211] **Two vault reads sit outside their VaultLockedError guards.**
  From the FIBR-0204 sweep (MEDIUM, verified by reading). Two sites call into the
  vault OUTSIDE the try/except that was written to protect them:

  1. `ui/forecast.py` — `_headline_text` -> `_coverage_suffix` and
     `_provenance_text` -> `_excluded_names` each construct an AccountService and
     call `list_accounts()`, but `refresh()`'s `except VaultLockedError` closes
     before those two setText calls. The module docstring claims "every slot
     catches VaultLockedError and returns". NOTE: FIBR-0204 WIDENED this exposure
     — `_excluded_names` is now called in both forecast modes, not just ANCHORED
     — so this is worth closing promptly.
  2. `ui/categories.py:198` — `delete_blast_radius(category_id)` is one line
     ABOVE a try/except that carefully documents the auto-lock-while-the-confirm-
     box-is-open case. Same shape at `ui/rules.py` `_refresh` and the
     `leaf_categories_grouped` call before the dialog.

  No sys.excepthook is installed anywhere in src/, so these escape a Qt slot.
  Fold the reads into the guarded block in each case.
  **Layman:** In two places the app reads your data a moment after the vault may have locked itself, which can make it close unexpectedly instead of just stopping.
  Kind: fix.
  Lanes: ui.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): five unguarded reads folded into their
  guards, not the two reported. forecast.py — `refresh` now BUILDS both strings
  inside the try and only renders after it, so `_coverage_suffix` and
  `_excluded_names` are covered (the module docstring's "every slot catches
  VaultLockedError" is now true). categories.py — `delete_blast_radius` moved
  into a try. rules.py — `_refresh`'s pair (`list_rules` + `list_all`) and the
  `leaf_categories_grouped`/`sub_category_parent_names` reads that build the
  dialog in BOTH `_on_add` and `_on_edit`; the bullet named `_on_add`'s, the
  `_on_edit` twin was found by reading the sibling. Tests: one forecast leg, one
  categories leg, three parametrised rules legs — all five verified red first.

- ✅ [FIBR-0212] **Backup restore accepts a DEFLATE bomb and skips the directory fsync.**
  From the FIBR-0204 sweep (MEDIUM x3, verified by reading). Three separate
  things in services/backup.py:

  1. **DEFLATE bomb on the READ path.** The comment says "vault.db is ZIP_STORED
     — AES ciphertext is incompressible, so DEFLATE can't bomb it", which is true
     of files finbreak WRITES and irrelevant to files it READS: `_read_capped`
     never inspects `compress_type`. A ~500 KB hostile .fbk whose vault.db is
     deflated zeros inflates to the 512 MiB cap in RAM, pre-login, on the restore
     path. FIBR-0014 INV-12 explicitly requires a file_size/compress_size ratio
     check; it is not implemented. Also add MemoryError to restore_backup's
     normalisation tuple — today it escapes as an unhandled exception.
  2. **No directory fsync after the rename.** `_write_fbk` fsyncs the FILE then
     os.replace's it, but POSIX does not guarantee the directory entry reaches
     stable storage. A power loss after "Backup saved" can leave no dest at all —
     on the one artifact whose entire purpose is surviving a disaster.
  3. **The .fbk temp is O_TRUNC, not O_EXCL.** O_NOFOLLOW stops the symlink case,
     but an attacker who pre-creates a regular dest.fbk.tmp (mode 0666) in a
     shared export dir has it filled and renamed into place — the user's backup
     is then attacker-owned and world-readable. `_write_owner_only` in the same
     file gets this right with O_EXCL; the two writers differ for no stated
     reason. (pdf_export was given the O_EXCL|O_NOFOLLOW|0600 treatment in
     FIBR-0204; this is its sibling.)
  **Layman:** A malicious backup file could be crafted to eat a lot of memory when you restore it, and a power cut right after a backup could leave no file at all.
  Kind: security.
  Lanes: services.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): all three closed. (1) INV-12's ratio clause
  is implemented — new `MAX_COMPRESSION_RATIO = 100`, and `_read_capped` now
  bounds BOTH the declared-size gate and the bounded read by
  `min(cap, compress_size * ratio)`, so a lying `file_size` cannot inflate past
  what its own compressed bytes could honestly produce. MEASURED: a bomb sized
  to land exactly ON the 512 MiB cap passed every existing gate, and the test
  had to match the message — without the ratio check the restore inflates all
  512 MiB and STILL raises BackupError from the downstream "this isn't a vault"
  failure, a green that proves nothing. MemoryError normalised at `_read_entries`
  (so verify_backup gets it too, as reason "invalid") AND in restore_backup's
  tuple. (2) New `_fsync_dir` after the export's `os.replace`, best-effort since
  a directory fsync is not portable. (3) `_write_fbk` is now
  unlink-then-O_EXCL|O_NOFOLLOW|0600, the pdf_export shape; verified the
  pre-planted 0666 temp used to survive into the final backup.
  Tests: three legs in tests/features/backup, all verified red first.

- ✅ [FIBR-0213] **recategorize_auto_rows rescans the whole vault inside the import transaction.**
  From the FIBR-0204 sweep (MEDIUM, verified by reading). `commit_import`'s
  comment says it will "categorise the just-inserted rows (auto/NULL)", but
  `recategorize_auto_rows` iterates `tx_repo.auto_rows()` — EVERY auto row in the
  vault, all accounts, all statements.

  Two consequences. Cost: importing a 20-row CSV into a 50k-row vault runs 50k
  `categorize_with_library` calls plus their UPDATEs inside the write transaction
  holding the DB lock, on the GUI thread. Surprise: if the built-in library
  changed between releases, importing one small statement silently re-files
  hundreds of unrelated historical rows, moving every chart and report.

  At minimum correct the comment. Better: scope the recompute to the rows this
  import inserted (or to the period), and make a full re-file an explicit user
  action. A separate measured finding: rule and library patterns are re-folded
  once PER TRANSACTION ROW inside the loop (`categorization.py` and
  `category_library.py`), measured 0.397s -> 0.120s for 20k rows x 113 patterns
  when folded once up front — fold them in `_match_inputs`.
  **Layman:** Importing a small statement quietly re-sorts every transaction you have ever imported, inside the same operation — slow on a big history, and it can move numbers you were not expecting to change.
  Kind: fix.
  Lanes: services.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): both halves done, and the comment did not
  need correcting — the CODE was changed to match what it always claimed.
  Scoping: `recategorize_auto_rows(conn, *, min_txn_id=0)` + `auto_rows(min_txn_id
  =)` + a new `TransactionRepository.max_id()`. `commit_import` reads max_id()
  INSIDE its transaction just before the inserts; SQLite gives a new INTEGER
  PRIMARY KEY row max(rowid)+1, so the boundary is exact with no per-row id
  round-trip. A whole-vault re-file is now only the Rules tab's "Apply now" — leg
  (b) of FIBR-0010 INV-4, which was already an explicit user action, so no new UI.
  INV-4 + D9 updated in docs/specs/FIBR-0010.md; the feature spec's "or the next
  import" clause no longer holds and says so. Folding: new `fold_rules` /
  `fold_entries`, and `_match_inputs` returns folded pairs. Both one-shot matchers
  now delegate to the same `*_folded` loop the recompute path uses, so folding
  once cannot diverge from folding per call. MEASURED here 0.429s -> 0.067s over
  20k rows x 113 patterns (load avg 0.35; both runs identical to 3dp). Tests:
  counted, not timed — 12 rows x 8 patterns went 120 folds -> 20. Both legs red
  first.

- ✅ [FIBR-0214] **Theme palettes miss WCAG on borders, stripes, muted text and one focus ring.**
  From the FIBR-0204 sweep (MEDIUM x3, ratios COMPUTED with the real WCAG
  formula, not estimated). The selected-row text was CRITICAL and is already
  fixed in FIBR-0204; these are the remainder, and each needs a palette decision
  rather than a code fix:

  - **1.4.11 non-text contrast (needs 3:1) — control borders fail on every
    theme.** `border` is the 1px edge on QLineEdit/QComboBox/QPushButton/
    QGroupBox, i.e. the only thing identifying an input's bounds: ledger 1.36,
    parchment 1.42, mint 1.27, midnight 1.41, graphite 1.43, emerald 1.61
    (against `window`). Ledger's FOCUS RING is also short at 2.87 — accent
    #b8892b on #f5f4ef — and the same value is the selected-tab underline. The
    other five focus rings pass (3.22-8.25).
  - **Alternating row stripes are invisible.** alt_base vs base: 1.16-1.27
    across the six. `polish_item_views`' docstring claims it makes stripes
    "visible"; at these ratios they are not. Decorative, so not a WCAG failure —
    but the stated purpose is not met.
  - **1.4.3 (needs 4.5:1) — muted_text where it is LIVE, not disabled.**
    `muted_text` is the QHeaderView::section and unselected QTabBar::tab colour:
    ledger 4.39, parchment 3.36, mint 4.30. Its Disabled-palette use IS exempt;
    these are not. Related: `Link` is `accent_soft` at 1.25-2.86 and links do
    render (update_dialog sets setOpenExternalLinks(False) on a notes widget).

  The theme suite now has INV-4a computing ratios per theme (FIBR-0204) — extend
  that harness to these pairs rather than writing a second one. Open question the
  reviewer raised and I could not answer from the docs: is there a contrast
  budget for the palettes at all? Neither FIBR-0127 nor ADR-0010 states one.
  **Layman:** Some of the colours in the themes are too faint to see easily — input outlines, the alternating row shading, and some grey text. Needs a design pass with the contrast numbers checked.
  Kind: accessibility.
  Lanes: ui.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): the open question the bullet raised — is there a contrast budget at all? — is answered and written down as FIBR-0127 INV-4b. User chose the low-visual-cost set over a full AA restyle (2026-08-03). Verified every ratio in the bullet against source first; all six border figures, ledger's 2.87 focus ring, the 1.16-1.27 stripes, muted 4.39/3.36/4.30 and the 1.36-2.86 links all reproduced exactly. FIXED (invisible side by side): muted_text ledger #6b7280->#69707d, parchment #8a7a63->#726552, mint #5f7a6f->#5c766b (all now >=4.5:1 on window); ledger accent #b8892b->#b2842a (focus ring 2.87->3.06); Link role accent_soft->accent (1.36-2.86 -> 3.16-8.83 on base — accent_soft stays live as the QSS button gradient, so INV-4's no-unused-token half still holds). DELIBERATELY UNMET, recorded rather than ignored: input borders at 1.27-1.61 (reaching 3:1 means #d8d3c4->#998c65 on ledger — a visible restyle of all six); Link under 4.5:1 on the light themes (4.5 would make a link indistinguishable from body text, and every link in the app is non-clickable by design); alt_base stripes at 1.16-1.27 (decorative, outside SC 1.4.11 — and polish_item_views' "visible" claim is corrected). Three legs added to the INV-4a harness as the bullet asked, not a second one. All three red first.

- ✅ [FIBR-0215] **Three toolbar glyphs are unmapped, so they never hover-brighten or re-tint.**
  From the FIBR-0204 sweep (MEDIUM, verified by reading). `icons._ICON_HUES`
  omits `transactions`, `statements` and `export` — all three ARE toolbar action
  icon names with SVGs on disk. `toolbar_icon` returns a plain `icon(name)` for
  them, which adds no Active/Selected pixmap, so the module docstring's "vibrant
  one on hover" and "tuned to the active light/dark theme" simply do not happen
  there, and `_retint_toolbar_icons` re-installs an identical icon.

  Theme INV-10 is phrased as "a MAPPED action's icon cacheKey() changes", so the
  test is shaped around the gap rather than catching it. Contrast is fine
  (#808080 scores 3.18-4.39 on all six windows) — this is consistency, not
  accessibility. Decide whether the omission was deliberate visual hierarchy; the
  docstring's "any glyph not listed stays neutral grey" reads as a fallback for
  UNUSED glyphs, not for three live toolbar buttons.
  **Layman:** Three of the toolbar buttons do not light up when you hover over them, and do not change shade when you switch theme, unlike the other ten.
  Kind: fix.
  Lanes: ui.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): user decided the omission was an oversight, not hierarchy — all three mapped. `transactions` 237 (blue-violet), `statements` 69 (olive-gold), `export` 357 (coral), placed in the three widest gaps in the existing wheel (38-100, 210-265, 330-25 wrapping) so no pair sits closer than the 13 degrees `lock` and `categories` already do. The bullet's read of the test was right: INV-10 asserted the re-tint for ONE action, which proves the mechanism and not the coverage, so it stayed green for as long as the gap existed. Now asserted over the whole `_icon_actions` set — nothing in it missing from `_ICON_HUES`, every glyph's pixmap changes light->dark, and every mapped glyph's Active pixmap differs from its Normal one — so a future toolbar action that forgets its hue is caught the day it lands. Red first, naming exactly the three.

- ✅ [FIBR-0216] **Assorted MEDIUM/LOW findings from the FIBR-0204 sweep, batched.**
  From the FIBR-0204 sweep. Each verified against source; none reached CRITICAL
  or HIGH, so they were deferred by user decision rather than fixed in that pass.

  **Correctness / robustness**
  - `parse_transaction` has no upper bound; a pasted `1E19` reaches SQLite and
    raises OverflowError (NOT ValueError), escaping ManualEntryDialog's slot.
    Exact bound: 9223372036854775807 minor units. Range-check and raise
    ValueError like every other rejection.
  - `standard_bank._draft` is called from bare loops with no per-row try, so a
    legitimate 0.00 statement line (a zero fee, "interest capitalised 0.00")
    aborts the WHOLE statement import with "amount must be non-zero" — which
    reads as an app bug. csv_importer degrades per row; this should too.
  - `services/transactions.py` validates the date but does not canonicalise it:
    `date.fromisoformat` accepts "20260715" and "2026-W29-3" and stores them
    verbatim, and everything downstream compares dates as STRINGS. No current
    caller reaches it (all paths go through strptime().isoformat() or a
    QDateEdit) — latent, one-line fix.
  - `_coverage_suffix` (ui/forecast.py) counts ALL accounts as its denominator,
    so a vault holding any debt/investment account always shows the partial-total
    suffix even when every CASH account contributed. Compare against the cash
    count instead.
  - Two same-day charges from one merchant collapse into a single recurring item
    (grouping is `(direction, merchant_key)` and the amount is a median), so the
    forecast projects R199/month against a true R398. Also inflates the "Seen"
    count, which can push occurrences past the new-recurring alert threshold and
    silently suppress that alert. Document at minimum.

  **Amount / locale**
  - Display is locale-aware (QLocale) but input is C-locale only, so a de_DE user
    cannot type back the number the app just showed them (`1.234,56` is
    rejected). The manual-entry placeholder is tr()-able while the parser is not,
    which makes the translation actively misleading.
  - `negative_style` is a magic string (`== "brackets"`) in a codebase that uses
    StrEnum for all nine other closed token sets.

  **UI polish**
  - Alerts dialog dismiss buttons are a bare tr("✕") with no accessibleName — a
    screen reader announces N identically-unnamed buttons (WCAG 4.1.2), and the
    bare glyph gives translators no context.
  - Every dismiss recomputes the whole alert set TWICE (the dialog re-renders,
    then the shell's `changed` signal re-runs it), each a full unfiltered
    transaction scan plus a recurring-detection pass.
  - File -> Quit is disabled while locked (the whole File menu is), so on the
    app's default startup surface there is no menu route to exit — and there are
    no keyboard shortcuts or menu mnemonics anywhere in the app
    (`grep setShortcut|QKeySequence` returns nothing), so no Ctrl+Q either.
  - A manual update check returning after a lock pops a QMessageBox over the
    lock screen; every sibling guards on `self._dialog is prompt`.
  - An auto-lock during a nested modal loop (Help->About, a QFileDialog) defers
    the workspace's deleteLater indefinitely, so decrypted rows survive in the
    hidden widget until the user dismisses the box — the unattended case
    auto-lock exists for.
  - StartOverDialog's confirm word is inside a tr() string, so a translated build
    tells the user to type a word the comparison will never accept, permanently
    disabling OK. The module docstring claims the opposite.
  - PDF export can leave a stuck wait cursor (no `finally`, unlike the two backup
    handlers).
  - Dark-theme PDF page numbers render black on the dark page background.

  **Docs / dead code**
  - FIBR-0172 still specifies an `AlertsCard` in HomeView; FIBR-0185 replaced it
    with a dialog and grep finds zero hits for `dashboard_alerts`/`AlertsCard`.
  - FIBR-0006 describes a Type combo on the category Add form that does not
    exist, claims two-level depth (the UI renders unbounded), and says the
    service does NOT guard re-parent cycles (it does).
  - `select_by_index` has almost no production caller — both wrappers
    (`StatementsWidget._select_period`, `TransactionsView._select_txn`) are
    documented as test/shell accessors with zero non-definition hits in src/.
  - `ExportDialog._export_button()` has zero callers in src/.
  - The `.old` restore stamp is second-resolution, so two restores inside one
    second silently discard the first recoverable copy.
  **Layman:** A collection of smaller issues found in the big code review — none of them break anything today, but each is worth tidying.
  Kind: fix.
  Lanes: ui, services.
  Source: code-quality-review-2026-08-03.
  Resolved (2026-08-03): worked the batch in four commits. Fixed:
  StartOverDialog's tr()'d confirm word (a translated build could never confirm);
  standard_bank's 0.00 row aborting a whole statement; parse_transaction's missing
  upper bound (OverflowError, not ValueError, escaping the slot); the PDF export
  wait cursor's missing finally; decrypted rows surviving an auto-lock through a
  nested modal loop; two update-check boxes over the lock screen;
  _coverage_suffix's all-accounts denominator; date canonicalisation; the .old
  stamp's second resolution; the alerts dismiss buttons' accessibleName; the
  double alert-set recompute per dismiss; Quit unreachable while locked (+ the
  app's first shortcut, Ctrl+Q); negative_style -> NegativeStyle StrEnum; the
  misleading tr()'d amount placeholder. Documented: the same-day recurring
  collapse (both plausible fixes break a real case, so it needs evidence);
  FIBR-0172's AlertsCard section and FIBR-0006's D9 + cycle-guard claims;
  _export_button as a test accessor.

  THREE corrections to the bullet, each verified against source:
  (1) `select_by_index` is NOT near-dead — it has three production call sites
  (transactions.py, statements.py, accounts.py). Dropped, not silently filtered.
  (2) `ExportDialog._export_button()` has zero src/ callers but IS a live test
  accessor, so it is labelled rather than removed.
  (3) The dark-theme PDF page numbers and the locale amount input each turned out
  too large for a batch and are split out as FIBR-0217 and FIBR-0219. FIBR-0219
  in particular: the obvious locale fix MEASURED as a silent 100x error (de_DE
  turns a typed -12.34 into -1234), strictly worse than today's rejection — a
  hazard the original finding did not name.

- 📋 [FIBR-0217] **Dark-theme PDF page numbers render black on the dark page.**
  Split out of FIBR-0216 after an implementation attempt showed it is not a
  batched-polish-sized fix. MEASURED with pdfplumber: the footer page number
  comes out `non_stroking_color == (0, 0, 0)` while the body text is `0.902`,
  and the dark theme's page background genuinely renders (a filled rect
  `(10,10)-(585,832)` in `#242830`, confirmed by rasterising — corner pixel
  RGB(36,40,48)). The number sits inside that rect, so it is black on
  near-black, about 1.3:1.

  `QTextDocument::print_` draws that number itself using the painter's default
  pen, and the painter is created inside `print_` — unreachable. Qt suppresses
  its own numbering only when the document is ALREADY paginated, so the fix
  shape is to paginate + paint the pages ourselves and draw the footer in the
  theme's ink.

  **Attempted and reverted 2026-08-03.** Reproducing what `print_` does
  internally is version-sensitive and it regressed pagination twice against a
  direct A/B harness: without Qt's DPI transform the whole report rendered at
  about 1/12 scale in the page corner (1 page instead of 8); with the transform
  applied it still came out 7 pages instead of 8 and the body glyphs landed at
  x=10 rather than x=66, because `print_` also reserves the page-layout margins.
  Getting this right needs its own pass with page-by-page visual verification —
  the wrong risk to take inside a batch of small fixes, on a money report.

  The A/B harness is the asset to keep: render the same HTML through
  `doc.print_` and through the replacement, then compare page count and every
  body glyph's (text, x0, top) via pdfplumber. Identical body glyphs + a
  theme-coloured footer is the acceptance gate, and it makes the regression risk
  measurable rather than hoped-at.
  **Layman:** On a dark-themed PDF report the little page number at the bottom is black on a nearly-black background, so you cannot read it.
  Kind: fix.
  Source: in-session-2026-08-03 (split out of FIBR-0216).

- 📋 [FIBR-0218] **The AppImage installs no launcher, so a hand-made one shows a second panel icon.**
  Reported by the user 2026-08-03 with screenshots: two finbreak icons in the
  KDE panel while running 0.1.19 (the latest). DIAGNOSED on their machine, not
  inferred.

  Root cause is an app-ID mismatch, and finbreak's own side is correct. On
  Wayland KDE associates a window with a pinned launcher by matching the window's
  `app_id` to the launcher's desktop-file BASENAME. `app.py` sets
  `QGuiApplication.setDesktopFileName("io.github.milnet01.finbreak")` and the
  AppImage bundles `io.github.milnet01.finbreak.desktop` — consistent. But the
  user's panel pinned `~/.local/share/applications/finbreak.desktop`, a
  hand-rolled launcher whose basename id is `finbreak`, so KDE saw a pinned
  launcher and an unrelated window. (`StartupWMClass=finbreak` in that file is
  the X11 key and is ignored on Wayland — a trap, since it LOOKS like the
  association key.)

  Resolved for the reporter by renaming their launcher to
  `io.github.milnet01.finbreak.desktop` and pointing `Icon=` at the installed
  `io.github.milnet01.finbreak` hicolor PNGs.

  The product gap: the AppImage installs no desktop entry of its own, so a user
  who wants a menu/panel entry hand-writes one and will usually name it
  `finbreak.desktop` — reproducing this. Options to weigh: (a) document the
  required basename in the README's AppImage install section (cheapest, and the
  README is refreshed every release anyway); (b) have the AppImage offer to
  install a correct launcher on first run, the way many AppImages do; (c) rely on
  AppImageLauncher, which does it correctly but is not installed by default on
  openSUSE. (a) is the minimum and should ship regardless of the rest.

  Also observed on the reporter's machine, and NOT part of this item: three
  concurrent installs — the AppImage 0.1.19, an RPM/deb providing
  `/usr/share/applications/io.github.milnet01.finbreak.desktop`, and a Flatpak
  `io.github.milnet01.finbreak` still on 0.1.16. Worth asking whether the docs
  should warn that the three can shadow each other's launchers.
  **Layman:** If you make your own shortcut for the AppImage, finbreak shows up twice in the taskbar — once for the shortcut and once for the running window.
  Kind: fix.
  Source: user-report-2026-08-03.

- ✅ [FIBR-0219] **Amount input is C-locale only, and the obvious fix silently multiplies by 100.**
  Split out of FIBR-0216 because implementing it turned up a hazard the original
  finding did not name, which changes what the fix has to be.

  The gap is real: display goes through `QLocale().toString()` (grouped,
  locale-correct separators — `_amount.py`), while input goes straight to
  `parse_transaction`, which does `Decimal(str(raw).strip())` — C locale only. So
  a de_DE user is shown `R 1.234,56` and cannot type it back.

  **The naive fix is worse than the bug, and this is the reason to be careful.**
  "Strip the locale group separator, swap its decimal point for a dot" is the
  obvious normalisation, and MEASURED under de_DE (group `.`, point `,`) it turns
  a typed `-12.34` into `-1234` — a silent 100x error, on a money field, with no
  rejection anywhere. Today that same input is simply refused, which is safe. A
  fix that trades a refusal for a silent 100x error is a regression however good
  the intent. The full measured matrix (en_US / de_DE / fr_FR, four input forms
  each) was taken 2026-08-03; fr_FR is a third shape again, grouping with U+202F.

  So the design question this needs answered first is what happens to an AMBIGUOUS
  input, not how to parse an unambiguous one. Sketch worth evaluating: normalise
  via the locale AND via the C rules, and accept only when the two agree on a
  value; when they disagree, refuse with a message naming the format the app
  displays. That keeps every unambiguous input working in both conventions and
  turns the dangerous case into a visible refusal rather than a wrong number.
  Whatever is chosen needs a per-locale test matrix, since the failure mode is
  silent and off by a factor of 100.

  Done already under FIBR-0216: the manual-entry placeholder was a tr()-able
  `"e.g. -12.34"` while the parser is C-locale only, so a translated build asked
  for `-12,34` and then rejected it — actively misleading. It is now a
  non-translatable `-12.34`, an example of a machine format (coding.md § 5.2),
  so the hint cannot disagree with the parser. That removed the harm ahead of
  the locale gap; the gap itself is now closed here, and the placeholder stays
  exactly as FIBR-0216 left it — INV-3 makes the C form valid under every
  locale, so hint and parser still cannot disagree.
  **Layman:** If your computer is set to a language that writes numbers as 1.234,56 you cannot type an amount back the way finbreak just showed it to you.
  Kind: fix.
  Source: code-quality-review-2026-08-03 (split out of FIBR-0216).
  Spec written and gated (2026-08-04): docs/specs/FIBR-0219.md, ACCEPTED
  after 5 cold-eyes loops (§13 is the ledger). The design call this bullet
  left open is made: validate with QLocale (which checks group PLACEMENT, so
  de_DE rejects "-12.34" instead of reading it as -1234), rebuild the Decimal
  exactly from the string, accept when both conventions agree, refuse when
  they disagree — and, the part the bullet did not anticipate, refuse by
  SHAPE when only one convention parses at all.

  That last rule exists because the review found the two-parser test is blind
  to the real hazard: en_ZA (the base-currency locale) reads "1,500" as 1.5
  while the C convention simply rejects it, so one candidate survives and is
  stored as 150 minor units where the user meant 150 000. Silent 1000x, and
  a regression against today's refusal. Two further variants of the same hole
  were found and closed in later loops (a bounded head let "1234,500"
  through; a hardcoded separator set let de_CH's "1'234.500" through).

  Also surfaced and filed separately: FIBR-0222, a pre-existing
  decimal.Overflow from to_minor's scaleb that escapes _on_add as a non-
  ValueError and crashes the dialog — reachable today, independent of this
  item.

  Next: TDD implementation against INV-1..INV-9.
  Resolved (2026-08-05): `parse_amount_input` + `_locale_decimal` in
  `src/finbreak/ui/_amount.py`, wired at the one typed-amount seam
  (`ManualEntryDialog._on_add`). QLocale validates group PLACEMENT, the Decimal is
  rebuilt exactly from the string (never Qt's float), the two conventions must
  agree, and a `^[+-]?\d+(?:[.,]\d+)*[.,]\d{3}$` shape guard refuses the
  one-surviving-candidate case AFTER the agreement test — so en_US keeps the
  `.`-tail forms it stores today. `parse_transaction` and the three importers are
  untouched and stay C-locale only (INV-1).

  75 legs in `tests/features/amount_input/` cover INV-1..INV-9 across
  en_US / en_ZA / de_DE / fr_FR / sv_SE. TDD: the suite went red on exactly one
  leg — the positive dialog leg the spec names as the only one that fails when the
  call site is omitted — and green on wiring it.

  Accepted trade recorded in the spec's § 6: under the comma-decimal locales
  `1.500`, `1.250`, `2.000`, `0.100`, `12.500` and `1234.500` are stored today and
  are refused after this, because the same shape is how `1,500` → 1.5 arrives.
  `1,50`, `1.50` and `1500` all work. The mirror hazard under a `.`-decimal locale
  (a European pasting `1.500`) is deliberately retained — the app does the same
  today and refusing it would cost every en_US user.

- 📋 [FIBR-0220] **Agreeing with a "~ guess" cannot teach the app — the no-nag gate has no escape hatch.**
  Reported by the user 2026-08-03. VERIFIED against source; the current
  behaviour is deliberate and documented, and the gap is a missing action rather
  than a defect.

  What happens today. Right-click a `~ guess` row -> Set category -> the picker
  opens with the guessed category ALREADY selected (`_on_set_category` passes
  `txn.category_id`). Accepting it calls `set_manual_category`, which writes
  `(same_id, 'manual')` — the source differs from `'library'`, so the row really
  is written and the `~` marker clears (`transactions.py:354` renders the marker
  only for `category_source == 'library'`). So the row IS confirmed and frozen.

  But `_maybe_offer_rule` returns early when `chosen == would_categorize(desc)`
  (`transactions.py:427`), and `would_categorize` includes the LIBRARY layer
  (`categorization.py:293-301`, FIBR-0139 D4 — which explicitly supersedes
  FIBR-0010 INV-5's rules-only phrasing: "confirming a library guess raises no
  learning nag; overriding one still offers the rule"). Agreeing with a guess is
  therefore, by construction, the one case that can never produce a rule.

  Consequence: confirming a guess fixes exactly one row. The next import of the
  same merchant is a `~ guess` again, and the user repeats the work per
  statement. The only two routes to a persistent rule are to pick a DIFFERENT
  category (tripping the "differs" check) or to hand-write one on the Rules tab —
  neither discoverable from the row being looked at.

  The no-nag rule itself is right and should stay: a modal offer on every
  agreement would be intolerable. What is missing is an explicit, opt-in action.
  Candidates, cheapest first: (a) a second context-menu item on a guessed row —
  "Always file <merchant> here" — that skips the differs-check and opens the
  existing `RuleEditDialog` pre-filled exactly as the learn offer does, reusing
  `_maybe_offer_rule`'s dialog and `_apply_learned_rule` wholesale; (b) a
  "remember this" checkbox in the CategoryPickerDialog; (c) a bulk "turn my
  confirmed guesses into rules" pass. (a) is the smallest and is the one route
  that starts where the user already is.

  Whichever ships, the merchant-key question needs deciding: the learn offer
  pre-fills the rule with the FULL description and tells the user to trim it to a
  keyword. For a guess-derived rule the library's own matched pattern is the
  better default, since it is already the generalised merchant token — but that
  means surfacing which library pattern matched, which `match_library` currently
  discards (it returns only the category id).
  **Layman:** When the app guesses a category correctly, saying "yes, that's right" only fixes that one row — the next statement guesses again. There is no way to say "always file this shop here".
  Kind: enhancement.
  Source: user-report-2026-08-03.

- ✅ [FIBR-0222] **A huge exponent crashes the Add-transaction slot before the 64-bit bound is reached.**
  Surfaced by the FIBR-0219 spec review; VERIFIED against source, and
  independent of that item (it reproduces on today's shipping code).

  MEASURED 2026-08-04:
  `parse_transaction("2026-07-01", "1e999999", "x", 2)` raises
  `decimal.Overflow`, not `ValueError`. The value is a finite Decimal, so
  the `is_finite()` check passes; the fractional-digit check passes; then
  `to_minor` does `amount.scaleb(exponent).to_integral_value()` and
  `scaleb` overflows the Decimal context BEFORE `_MAX_AMOUNT_MINOR` is
  ever compared.

  `decimal.Overflow` is an `ArithmeticError`, so `ManualEntryDialog._on_add`'s
  `except ValueError` does not catch it and the Qt slot dies. Reachable by
  typing `1e999999` into the Amount field today.

  This is exactly the class FIBR-0216 closed when it added the 64-bit
  `_MAX_AMOUNT_MINOR` guard ("a class no caller catches, unlike the
  ValueError every other rejection here raises") — the guard just sits one
  step too late to catch an exponent this large.

  Fix shape: bound the exponent before scaling (or wrap `to_minor`'s call
  and re-raise as `ValueError`), so every rejection out of
  `parse_transaction` remains a `ValueError` as its docstring promises.
  Needs a regression leg driving the dialog, not just the parser.
  **Layman:** Typing a a number like 1e999999 into the Add-transaction box closes the dialog instead of showing "that's too big".
  Kind: fix.
  Source: cold-eyes-FIBR-0219-loop2-2026-08-04.
  Resolved (2026-08-05): reproduced first — `parse_transaction("2026-07-01",
  "1e999999", "x", 2)` raised `decimal.Overflow` from `to_minor`'s `scaleb`,
  and the dialog leg died in `_on_add` rather than showing an error.
  `parse_transaction` now wraps the `to_minor` call and re-raises `Overflow`
  as `ValueError("amount is too large to store")` — deliberately the same
  message as the 64-bit bound below it, since it is the same rejection. Guard
  placement: after the scaling rather than a second magnitude bound before it,
  so `_MAX_AMOUNT_MINOR` stays the ONE stated bound and cannot drift from a
  duplicate expressed as an exponent. `Overflow` is caught narrowly, not
  `DecimalException`: with a finite operand and a currency exponent of 0-3 it
  is the only trapped signal reachable there (a huge NEGATIVE exponent is
  already rejected one check earlier, verified).
  Regression legs in tests/features/vault/: two rows on the INV-4b reject
  table (both signs) plus `test_INV4b_dialog_refuses_a_huge_exponent_instead_of_dying`,
  which drives ManualEntryDialog — the class distinction is invisible from the
  parser's side. All three verified RED before the fix. spec.md INV-4b now
  states that ValueError is the class for every rejection, magnitude included.

- 📋 [FIBR-0223] **The OFX closing-balance scaling is the one to_minor call site with no ValueError guard.**
  Surfaced while sweeping to_minor's call sites for FIBR-0222. PARTLY
  verified — read the code, did NOT reach it with an input.

  `src/finbreak/importers/ofx_importer.py:153` scales the `<LEDGERBAL>`
  straight through: `closing_balance_minor = None if balance is None else
  to_minor(balance, exponent)`. Every OTHER amount in that file goes
  through `parse_transaction`, whose ValueError the row loop catches into
  `RowError`; this one has no guard, and its own neighbouring comment
  records that this line runs OUTSIDE the wizard's boundary try/except
  (the reason `getattr(statement, "balance", None)` is there at all).

  So a `<BALAMT>` large enough to overflow `scaleb` raises
  `decimal.Overflow` — an ArithmeticError, uncaught — exactly the class
  FIBR-0222 just closed inside `parse_transaction`. FIBR-0222's fix does
  NOT cover this path.

  NOT YET VERIFIED: whether ofxparse admits exponent notation in
  `<BALAMT>` at all. Three attempts to build a driving fixture failed for
  unrelated reasons (the hand-rolled OFX would not parse, and reusing
  `tests/features/ofx_import`'s own `_stmt`/`_txn` helpers outside pytest
  did not either) — so the reachability is open, not disproven. Start
  there: if ofxparse rejects the token first, this is unreachable and the
  bullet closes as a note; if it does not, the fix is a try/except around
  the one call, mirroring FIBR-0222.

  Also worth a look in the same pass: `standard_bank.py:492/493/560/567`
  and `1102` scale PDF-derived amounts through the same helper.
  `_parse_amount` strips separators and never yields an `e`, so plain
  digit runs cannot overflow the context — believed safe, unverified.
  **Layman:** A corrupt bank file could crash the import wizard instead of reporting the bad line.
  Kind: fix.
  Source: in-session-2026-08-05 (FIBR-0222 call-site sweep).

## P13 — Packaging & release

### 📦 Packaging

- ✅ [FIBR-0015] **P13: Windows self-contained `.exe` build.**
  PyInstaller freezes `finbreak.exe` (bundled CPython + all native
  deps — SQLCipher, the needed Qt plugins, qpdf) on a
  `windows-latest` runner via `.github/workflows/windows-build.yml`
  (`workflow_dispatch`), clean-roomed with Python off `PATH`
  (`--self-test` → `FINBREAK_SELFTEST_OK`) and uploaded as a CI
  artifact for testers. Unsigned, manual-update, no installer.
  Builds on the P01 smoke-test.
  Dependencies: FIBR-0013, FIBR-0014, FIBR-0003 (direct
  predecessors). Walking the dependency edges, FIBR-0013 and
  FIBR-0014 transitively pull in the entire P02–P12 feature stack
  (FIBR-0004 through FIBR-0012), so P13 cannot start until the app
  is feature-complete. Lanes: build, ci, packaging.
  Kind: chore. Source: planned.
  Resolved 2026-07-13 (FIBR-0015-complete): the Windows `.exe` shipped by TDD (fixture-first cross-package regression + the INV-3 parity guard + the freeze driver). The one-time blocker — `sqlcipher3-binary` shipped Linux/macOS wheels only — was dissolved by swapping to `sqlcipher3-wheels` (the cross-platform fork, same SQLCipher 4.12.0 engine; ADR-0009), proven vault-portable both directions before the swap. `/audit` 0 actionable; `/indie-review` 2 cold lanes 0 defects; gate green 851/1. See docs/journal/FIBR-0015.md.
  Scope: this item delivered **only the Windows `.exe`**. The **Linux AppImage** already shipped under FIBR-0054 (`scripts/build-release-appimage.sh`); **macOS `.app`/`.dmg` + Flatpak/Flathub** are split to **FIBR-0130** (packaging-only — the `sqlcipher3-wheels` swap already cleared their SQLCipher blocker too). Superseded: the 2026-07-13 "compile SQLCipher on Windows" readiness-scan blocker and the "Wine + MSVC" local-build note — the Windows wheel makes both moot.

- 📋 [FIBR-0130] **P13: macOS `.dmg` packaging** (Flatpak/Flathub → FIBR-0159).
  The macOS `.app`-in-`.dmg` — the packaging remainder split out of FIBR-0015 when its Windows `.exe` slice closed (2026-07-13). The Flatpak/Flathub half moved to FIBR-0159 (see the scope update below). The SQLCipher crypto blocker is already cleared (the `sqlcipher3-wheels` fork ships macOS + Linux wheels of the same 4.12.0 engine, ADR-0009), so this is packaging-only: freeze the macOS app on a `macos-latest` runner (reusing the FIBR-0015 `windows_freeze_flags.py` collection list + `--self-test` clean-room); the artifact still meets ADR-0007's "no Python installed" launch bar. (The Flatpak manifest is FIBR-0159's, not this item's — see the scope update below.) Dependencies: FIBR-0015 (freeze tooling), FIBR-0037 (icon → `.icns`). Lanes: build, ci, packaging. Kind: chore. Source: split-from-FIBR-0015-2026-07-13.
  Scope update (2026-07-23): the Flatpak/Flathub half is now owned end-to-end by FIBR-0159 (docs/specs/FIBR-0159.md — freedesktop 25.08 runtime + pinned-wheel closure, portal-only sandbox). FIBR-0130 is left to deliver the macOS `.app`/`.dmg` only; do NOT re-author a Flatpak manifest here.

- ✅ [FIBR-0131] **Windows in-app auto-update.**
  Extend the FIBR-0054 self-update stack (check GitHub → Ed25519-verify the download → the Later/Skip/Update-now dialog — all already cross-platform) to actually *install* the update on Windows, which `detect_installer()` currently returns `None` for (inert, INV-7). A running Windows `.exe` locks itself, so the Linux "os.replace the file then relaunch" trick can't be copied. **Design (user-approved 2026-07-13): a separate helper process does the swap** — the app writes the verified new `.exe` beside the old one and spawns a detached waiter (cmd/PowerShell) that waits for finbreak to exit, moves the new file over the old one, and relaunches it (the Windows analogue of the FIBR-0122 `/bin/sh` waiter; watch the same PyInstaller-onefile `_MEI`-teardown race). Adds a `WindowsInstaller` + `detect_installer()` returning it on a frozen Windows build, and an asset-picker that selects the `.exe` release asset on Windows. Also promote the Windows `.exe` from a CI artifact to a signed release asset (attach + an Ed25519 `.sig` for the updater to verify; FIBR-0015 D6 deferred this) and evaluate Authenticode code-signing (an unsigned self-swapping-and-relaunching `.exe` is what Defender/SmartScreen distrusts most; free-ish for OSS via Azure Trusted Signing / SignPath). Same two-cycle caveat as Linux — the relaunch only proves out on the update *after* it ships. Dependencies: FIBR-0054 (update infra), FIBR-0015 (Windows build). Lanes: services, ui, ci, security. Kind: feature. Source: user-request-2026-07-13.
  Sequencing (2026-07-14): the "evaluate Authenticode code-signing" clause above is split out to FIBR-0133 (SignPath, blocked on approval). FIBR-0131 ships the Ed25519-signed .exe release asset + the in-app Windows updater ONLY; publisher (Authenticode/SmartScreen) trust is FIBR-0133 and does not block this. Spec: docs/specs/FIBR-0131.md.
  Spec refinements (docs/specs/FIBR-0131.md, cold-eyes-converged): (1) the waiter is PowerShell (the "cmd/" option was dropped); it waits by exe IMAGE PATH, not a PID (tree-agnostic + PID-recycling-proof). (2) The .exe is ALREADY a published release asset (v0.1.9 ships finbreak-0.1.9-x86_64.exe); the only missing piece for the updater is the Ed25519 .exe.sig sidecar, which D5 adds — so "promote from a CI artifact" is really "add the .sig".
  Closed 2026-07-14 by /close-phase (code-complete). Spec cold-eyes-converged (6 loops x 3 lanes); TDD (WindowsInstaller image-path swap+relaunch behind the existing Installer seam; installer-driven asset-picker; UpdateInfo.appimage_url->asset_url). /audit 0 actionable (3 bandit assert-in-tests FPs, out of gate scope). /indie-review 2 cold lanes -> crypto/PowerShell/ordering verified sound, 1 MEDIUM fixed inline (spawn-before-wipe so a Popen failure can't strand a wiped key; Linux twin guarded too). Gate green 877/1; tag FIBR-0131-complete. CAVEAT (like Linux FIBR-0054): the live Windows swap+relaunch is a two-cycle manual verification on the user's Windows box, and needs a release that first attaches the Ed25519 .exe.sig (v0.1.9 shipped the .exe but no .sig). Journal docs/journal/FIBR-0131.md.

- 📋 [FIBR-0016] **P13: `scripts/publish-release.sh` +
  release automation.** One committed script builds every
  artifact above, publishes the GitHub Release, and drives the
  Flathub submission/update — consuming the Flathub manifest
  produced by FIBR-0015. It is itself a specced item (its own
  `docs/specs/`, cold-eyes-reviewed) — a publish script can't
  predate the thing it publishes. Dependencies: FIBR-0015. Lanes:
  build, ci, packaging. Kind: chore. Source: planned.
  Note (2026-07-10): FIBR-0054 pulls a **Linux-only** slice of release automation forward — a thin `scripts/publish-release.sh` (or `gh release create`) that publishes the signed AppImage + `.sig` as GitHub Release `v0.1.0`, so the in-app updater has a real release to check/download. FIBR-0016 remains owner of the full multi-artifact publish + the Flathub submission/update flow; extend the Linux slice rather than replacing it.
  Note (2026-07-12, user request — "automate the release as much as possible"): the version-bump half is now automated — `.claude/bump.json` (added 2026-07-12) drives /bump and /release: source of truth src/finbreak/__init__.py, mechanical edits to pyproject.toml + tests/test_smoke.py + a dated CHANGELOG cut from [Unreleased], a post_check version-lockstep gate, and tag template v{NEW}. What remains MANUAL (the Linux-slice glue this item should close): after the bump, a human still runs scripts/build-release-appimage.sh (freeze + clean-room + sign), verifies the .sig against the committed RELEASE_PUBLIC_KEY_B64, extracts the CHANGELOG [X.Y.Z] section for notes, and runs `gh release create v<NEW> <appimage> <sig> --notes-file … --latest` (non-prerelease). Deliverable: a single `scripts/publish-release.sh` that chains bump (via the recipe) → full gate (ci-local.sh) → build+clean-room+sign → **verify .sig vs RELEASE_PUBLIC_KEY_B64 (hard gate — never publish an unverifiable release the in-app updater would reject)** → gh release create with the AppImage + .sig attached, notes from the changelog, non-prerelease so /releases/latest resolves. Idempotency + preconditions (clean tree, tag not already present, signing key available) checked up front. Keep it the Linux slice under FIBR-0016; the multi-artifact + Flathub publish stays the full-item scope. Spec-first per the item's own note (docs/specs/, cold-eyes) before coding.

- ✅ [FIBR-0037] **P13: a proper branded app icon (not a flat
  glyph).** Design a polished, richly-shaded application icon —
  the working concept is **money + an upward chart** (e.g. a
  banknote or coins fronting a rising line/bar graph), on a
  **transparent** background, reading clearly from a taskbar 16px
  up to a store 1024px. Ship the full asset set every artifact
  needs: master (≥1024px PNG/SVG source), multi-size `.ico`
  (Windows), `.icns` (macOS), the freedesktop hicolor PNG set +
  `.desktop` reference (Linux/AppImage), and the Flathub icon.
  **Licensing is a hard gate, not a nicety:** because the app
  ships on Flathub / GitHub Releases under MIT, every source
  element must be **original or CC0/public-domain** — no scraped
  copyrighted or attribution-encumbered art, even when combining
  pieces (record provenance + license of each source in
  `docs/` alongside the asset). Until this lands, the FIBR-0003
  smoke-test AppImage and dev builds use a throwaway placeholder
  icon. Dependencies: none (asset work); **blocks FIBR-0015**
  (packaging embeds it) and should harmonise with the FIBR-0023
  theme accent colour. Lanes: design, packaging. Kind: ux.
  Source: user-request-2026-07-01.
  Resolved 2026-07-09 (FIBR-0037-complete): branded app icon shipped — a "spending by category" donut (green/blue/teal/orange segments) with a gold coin centre on a dark navy tile, chosen with the user after shrink-testing candidates for small-size legibility (holds at 24px). Single 1024 master assets/icon/finbreak.png; scripts/make-icons.sh derives the platform set (Linux PNGs 16-512, 7-size Windows .ico, macOS .iconset) so they can't drift. Runtime window icon travels as ui/icons/app.png package data, set via QApplication.setWindowIcon (every window/dialog + taskbar); --self-test renders it (bundle-travel proof). macOS .icns is a mac-build-time step from the .iconset (FIBR-0015). /audit 0, indie-review clean (1 stale-comment LOW folded). Gate green 344 passed/1 skipped, mypy 0. Unblocks FIBR-0015 (the builds need the icon).

---

- 📋 [FIBR-0044] **Broaden Linux store reach: Snap Store + AUR + native distro packages.**
  Flathub (FIBR-0015) already surfaces the app in GNOME Software + KDE Discover across most distros, so this item adds the remaining self-publishable Linux channels: (a) Snap Store — a snapcraft.yaml (Ubuntu App Centre's default backend); (b) AUR — a PKGBUILD pointing at the GitHub release/AppImage (community-maintained, low overhead); (c) native RPM + DEB packages for Fedora/openSUSE/Debian/Ubuntu built via the openSUSE Build Service (OBS) and/or Fedora COPR, published to a project repo. (Getting INTO official distro repos is maintainer-driven and slow — tracked separately if pursued.) All free, all self-publish. Depends on FIBR-0015 (the built artifacts) and FIBR-0016 (release automation extends to push each channel).
  **Layman:** Beyond Flathub (which already puts us in most Linux app stores), also publish to Ubuntu's Snap Store and Arch's AUR, plus ready-to-install packages for Fedora/openSUSE/Debian — so almost any Linux user can install us in one click.
  Kind: package.
  Source: user-request-2026-07-04.
  Clarified (2026-07-04): this is the item that delivers the user's "each distro's built-in app store / software centre" request. Those centres (GNOME Software, KDE Discover, Ubuntu App Center, Pop!_Shop, Mint Software Manager, elementary AppCenter) are front-ends that read Flathub / Snap / distro repos — there is no per-store submission. So FIBR-0015 (Flathub → GNOME Software + KDE Discover, the majority of distros) + this item (Snap → Ubuntu App Center; native RPM/DEB → repo-based centres) together cover essentially every distro software centre. No separate work per store.

- 📋 [FIBR-0045] **Free Windows/macOS package managers: winget, Chocolatey, Homebrew Cask.**
  Free, self-publishable manager listings that just reference the GitHub Release artifact: (a) winget — a manifest PR to microsoft/winget-pkgs (`winget install finbreak`); (b) Chocolatey — a community nuspec package; (c) Homebrew Cask — a Ruby cask pointing at the macOS .dmg (`brew install --cask finbreak`). No paid account and no signing rework beyond what FIBR-0015 already does. Reaches the more technical slice of Windows/Mac users and gives them auto-update. Depends on FIBR-0015/FIBR-0016.
  **Layman:** Also list the app in the free 'app installers' many Windows and Mac users already use, so they can install and auto-update it with one command — no store account needed from us.
  Kind: package.
  Source: user-request-2026-07-04.

- ✅ [FIBR-0056] **Desktop-launcher integration — running window groups under its launcher (single taskbar icon) + branded icon.**
  Shipped 2026-07-09. A down-payment on FIBR-0015 desktop integration, done now at
  the user's request. app.py sets applicationName + QGuiApplication.setDesktopFileName
  = "finbreak", so the running window's Wayland app_id (X11 WM_CLASS) matches
  finbreak.desktop (StartupWMClass=finbreak) — KDE/GNOME then group the window under
  its launcher instead of showing a second, generic icon. On the user's machine: the
  branded PNGs were installed into ~/.local/share/icons/hicolor/*/apps/finbreak.png and
  the pinned finbreak.desktop's Icon= was pointed from wallet-open to finbreak (caches
  rebuilt). Repo change is app.py only; the .desktop + icon-theme install are
  per-machine (the canonical packaged .desktop + hicolor install belong to FIBR-0015).
  Verified: gate green 344 passed/1 skipped, mypy 0; desktop-file-validate clean; app
  launches with app_id/desktopFileName = finbreak.
  **Layman:** Fixes the app showing a second, generic icon in the taskbar when open, and puts the new icon on the panel launcher.
  Kind: implement.
  Source: user-request-2026-07-09.

- ✅ [FIBR-0082] **Generate app screenshots from synthetic dummy data for the GitHub README + antsprojectshub.co.za.**
  A reproducible way to populate a THROWAWAY vault with realistic-but-fake dummy data (a spread of accounts, a month or two of categorised transactions, a couple of imported statements, a few rules) and capture screenshots of the key screens for the GitHub README and https://antsprojectshub.co.za/.
  Resolved (2026-07-23): scripts/seed_demo_vault.py seeds a throwaway ZAR
  demo vault (3 accounts, ~13 months of categorised transactions, 3-level
  nested categories, auto-rules, confirmed transfers + recurring), and
  scripts/capture_screenshots.py renders every main tab offscreen in both
  the Midnight (dark) and Ledger (light) themes, plus a curated mixed-theme
  site/ set matching the metainfo <image> URLs. 20 PNGs under
  assets/screenshots/; metainfo now lists 6 captioned shots. Demo vault kept
  at .demo-vault/ (git-ignored) for reuse. Statements shot deferred (see
  FIBR-0162). Still user's: upload assets/screenshots/site/* to
  antsprojectshub.co.za/img/finbreak/ before the Flathub/OBS submit.

  Scope: a scripted seeder (e.g. scripts/seed-demo-vault.py) that first-runs a vault and inserts synthetic transactions/categories/accounts/rules, plus a documented capture flow for the main views — first-run, unlock, Home, Statements tab, Categories, Rules, the import wizard, and (once P10/FIBR-0012 lands) the spending-by-category dashboard, which is the most compelling shot.

  HARD constraint (security-model INV-6 / testing.md §6): screenshots use ONLY synthetic dummy data — never real financial data, never a real statement, never a committed vault. The seeded vault + captured PNGs are throwaway artifacts (or committed only as marketing PNGs under a docs/ or assets/ path, never the vault/data itself).

  Not blocked: the current shell (Home/Statements/Accounts/Categories/Rules tabs, import wizard) can already be captured now; re-run after the dashboard (FIBR-0012) ships to add the headline dashboard shot. Pairs naturally with a P13 release.
  **Layman:** Create polished screenshots of the app filled with realistic fake sample data — for the GitHub page and the portfolio site — so people can see what it looks like without installing it.
  Kind: marketing.
  Lanes: docs, ui, marketing.
  Source: user-request-2026-07-10.

- ✅ [FIBR-0155] **Publish finbreak via the openSUSE Build Service (OBS) — native RPM/deb + the openSUSE software portal.**
  User has an OBS account (build.opensuse.org) and wants finbreak on the openSUSE store + other Linux distro channels. OBS builds native packages for many distros from one recipe and publishes to software.opensuse.org + downloadable repos — complementary to the existing AppImage (FIBR-0054) and the deferred Flatpak/Flathub (FIBR-0130).
  Resolved (2026-07-21): OBS native-from-source packaging SHIPPED (code + recipes; gate green 1244/2). Spec docs/specs/FIBR-0155.md cold-eyes-CONVERGED loop 6. Decisions: (1) native-from-source, PyInstaller --onedir frozen runtime under /usr/lib/finbreak/ (security-critical stack — SQLCipher/qpdf/pdfium/Qt — stays BUNDLED, not distro-shared, § 3.2); (2) four confirmed targets (Tumbleweed, Fedora, Debian 13, Ubuntu 24.04) + Leap 15.6 pending one glibc check (§5, likely a 5th); (3) version flows tag → _service set_version → recipes; (4) metainfo <release> + debian/changelog mirror CHANGELOG via 2 new bump.json todos + post_check. Ships packaging/obs/ (finbreak.spec, debian/, io.github.milnet01.finbreak.desktop + .metainfo.xml [validates via appstreamcli], finbreak.sh launcher, _service, README runbook). Edits: pyproject [project.scripts], app.py Wayland app_id → reverse-DNS app-ID (X11 WM_CLASS stays 'finbreak'), security-model INV-8 distro note, naming.md app-ID resolved, bump.json sync. Reproduce-first TDD: tests/features/obs_packaging/ INV-1..8 (RED pre-recipes → green). CAVEAT: the "real OBS build green" exit criterion is a MANUAL maintainer step on the user's build.opensuse.org account (documented osc flow in packaging/obs/README.md + the §5 pre-submit checklist: Leap glibc go/no-go, per-distro package names, wheel vendoring, live xprop WM_CLASS, screenshots) — like FIBR-0131's live-swap caveat, not automatable in this repo's CI.
  Progress (2026-07-23): during OBS manual bring-up, the _service wheel-vendoring command was found broken — it used pip download --only-binary=:all:, but ofxparse ships as an sdist only (no PyPI wheel), so pip resolved nothing and aborted the whole closure (0 wheels), taking ofxparse's own deps lxml + six with it; the offline %build would have failed. Fixed: pre-build ofxparse into a universal wheel, then --find-links vendor/ so it satisfies the binary-only constraint and pip pulls lxml (dual-ABI) + six normally. Verified by an offline --no-index install into a clean cp313 venv importing the full stack (34 wheels, vendor.tar.gz ~300M). Build recipes (finbreak.spec/debian/rules) needed no change — they only pip install --no-index --find-links vendor/. Also corrected the runbook home:milnet01 -> home:milnet (OBS username).

  Scope to decide in the spec: (1) native-from-source packaging (an RPM `.spec` + a `debian/` recipe that pip-installs the PySide6 app + its native deps — SQLCipher, pikepdf/qpdf — into a distro package, .desktop + icon + AppStream metainfo) vs. wrapping the frozen AppImage; native is the "app store" experience OBS is built for. (2) Which targets to enable (openSUSE Tumbleweed/Leap, Fedora, Debian, Ubuntu). (3) How versioning/signing/release automation ties to the existing bump + release pipeline. (4) The AppStream metainfo `<release>` notes must mirror CHANGELOG (see changelog-writer). Needs: spec → /cold-eyes → implement (OBS project config + recipes + a submit/tag step) → verify a real OBS build. Dependencies: the app is feature-complete + already ships an AppImage, so no code blockers.
  **Layman:** Get finbreak into Linux "app stores": one OBS setup builds native openSUSE/Fedora (RPM) and Debian/Ubuntu (deb) packages and lists it on software.opensuse.org, so users install + auto-update it the normal way for their distro.
  Kind: package.
  Lanes: packaging, release.
  Source: user-request-2026-07-21.

- 📋 [FIBR-0163] **Add a populated Statements-tab screenshot via a synthetic statement import.**
  FIBR-0082's capture omits the Statements tab: the demo seeder inserts
  transactions straight through the repository, so no StatementPeriod rows
  exist and the Statements list renders empty. To capture it, drive a
  synthetic CSV/OFX through the real import path (ImportService / the import
  wizard) in scripts/seed_demo_vault.py, then re-add "statements" to
  scripts/capture_screenshots.py's _SCREENS. Low priority — the other 7 tabs
  already cover the headline features.
  **Layman:** One screenshot (the "Statements" list) is still blank because the demo data is added directly rather than by importing a bank file; this adds that missing shot.
  Kind: marketing.
  Source: in-session-2026-07-23.

- ✅ [FIBR-0164] **Keep README.md current every release; fix stale Windows signing + auto-update status.**
  User directive (2026-07-23): ensure README.md is up to date on every
  release. Fixed two stale claims: the "Code signing" section said Windows
  builds were SignPath-signed (SignPath DECLINED — FIBR-0133), and the
  Windows install section said "no auto-update on Windows" (FIBR-0131 shipped
  Windows in-app auto-update + the signed .exe release asset, confirmed on the
  v0.1.16 release assets). Also refreshed the feature list for 0.1.17's
  password-safety additions (hint, clipboard auto-clear, unlock throttle,
  verify-backup). Broadened .claude/bump.json's README todo to sweep the
  standing status sections (code signing, per-platform install/auto-update,
  distribution) against reality each release, not just the feature list; also
  recorded as a [[readme-update-every-release]] memory.
  **Layman:** Fixed the README so it no longer wrongly says the Windows app is officially signed or that it can't auto-update, and set things up so the README is checked on every release.
  Kind: doc-fix.
  Source: user-request-2026-07-23.

## Enhancements & performance backlog

Ideas captured 2026-07-01 from a product / performance review
(user-requested). Not yet slotted into the P0x phase order — each
carries a **Target phase** and `Dependencies:`; it is promoted into that
phase when its dependencies land. Two are **foundational** (marked
*Sequencing*) and must be designed at the noted phase, not deferred,
because retrofitting them is a data migration.

### 🔒 Security & account recovery

- ✅ [FIBR-0018] **Encrypted vault backup & restore.**
  Export the whole vault to a single encrypted backup file the user
  keeps off-device (external drive / cloud), and restore from it — the
  mitigation design.md names for the no-recovery-backdoor rule, so a disk
  failure or lost laptop doesn't mean lost data. Target phase: P12 (its
  heading already lists "backup"). Dependencies: FIBR-0004. Lanes:
  crypto, ux. Kind: feature. Source: user-request-2026-07-01.
  Merged into FIBR-0014 (2026-07-13): FIBR-0018 and the narrowed FIBR-0014 both describe the encrypted vault backup & restore. FIBR-0014 (docs/specs/FIBR-0014.md) is the IMPLEMENTATION spec; track the work there. The backup safety nudge is FIBR-0089; restore-verification is FIBR-0033. This item stays as the original provenance record — flip it ✅ alongside FIBR-0014 when the backup ships.
  Resolved (2026-07-28): closed as covered by its merge target. FIBR-0014
  (P12 settings / auto-lock / encrypted backup) is ✅ and the encrypted
  vault backup & restore it absorbed is live — services/backup.py plus the
  backup_export / backup_restore / backup_verify dialogs. This bullet was
  kept only as the original provenance record per the 2026-07-13 merge
  note, which said to flip it alongside FIBR-0014; doing that now.

- 📋 [FIBR-0019] **Master-password recovery via recovery key
  (key-wrapping).** At vault creation, generate a high-entropy recovery
  code the user stores safely; wrap the vault data-key under **both** the
  master password and the recovery code (envelope encryption) so a
  forgotten password is recoverable via the code with **no** backdoor.
  *Sequencing:* foundational — the key envelope must exist at FIBR-0004
  (vault creation); retrofitting needs a full re-encrypt migration.
  Requires an ADR + a security-model.md update at spec time. Target
  phase: P02. Dependencies: FIBR-0004. Lanes: crypto, security.
  Kind: security. Source: user-request-2026-07-01.

- 📋 [FIBR-0020] **Biometric unlock (fingerprint / face) with capability
  detection.** Store a key-wrapped copy of the vault key in the OS secure
  keystore, released by the platform biometric (Windows Hello, macOS
  Touch ID, Linux fprintd where present). **Detect** availability per-OS
  and offer it only when present; always keep the password as fallback. A
  convenience unlock, **not** a recovery method — Linux biometric support
  is uneven, so degrade gracefully. Target phase: P12. Dependencies:
  FIBR-0004, FIBR-0019 (shares the key-wrapping envelope). Lanes: crypto,
  platform, ux. Kind: feature. Source: user-request-2026-07-01.

- ✅ [FIBR-0029] **Password reminder / hint (shown before unlock).**
  An optional user-set hint on the unlock screen to jog memory —
  enforced to **not be the password** (and not to contain it). *Security
  note:* the hint must render **before** the vault is decrypted, so it
  lives **outside** the encrypted DB and is readable by anyone with
  device access — warn the user, keep it short, and record the new
  plaintext artefact in security-model.md at spec time. A memory aid, not
  a recovery method. Target phase: P02. Dependencies: FIBR-0004. Lanes:
  crypto, ux. Kind: feature. Source: user-request-2026-07-01.
  Design resolved by user 2026-07-20 (autonomous run): (1) SET the hint via a "Set password hint…" button in Settings that prompts for the CURRENT master password, verifies it, then enforces hint ≠ password AND hint does-not-contain password (needs plaintext in hand — hence the confirm), and saves to the plaintext window.ini (readable pre-unlock, outside the encrypted vault). (2) SHOW the hint on the unlock screen behind a "Show hint" button (hidden by default, reveal-on-click — reduces shoulder-surf exposure). Defaults decided: ~100-char cap; a plaintext-storage warning shown when setting; empty/unset hint means no "Show hint" affordance appears. security-model.md gains the new plaintext artefact (hint) as an asset + an enforcement invariant (hint never equals/contains the password) — that doc edit runs through /cold-eyes per §14. Ready to spec.
  Resolved (2026-07-20, autonomous run): shipped. Optional plaintext password hint shown on the unlock screen behind a reveal-on-click "Show hint" button; SET from Settings ("Set password hint…" → confirm current password via new AuthService.verify_password, constant-time hmac.compare_digest against the session key). Enforced never to equal/contain the master password (pure services/password_hint.validate_hint: NFC-normalize + casefold both sides, unconditional containment — a short password can't be embedded verbatim; obfuscation out of scope). Stored in plaintext window.ini (key hint/text, readable pre-unlock). security-model.md gains A1 plaintext-artefact note + INV-11; that doc edit cold-eyes converged loop 1. Spec docs/specs/FIBR-0029.md cold-eyes converged loop 2 (loop 1 caught a short-password leak: dropped a len>=4 carve-out). 24 hint tests (INV-1..9); full gate green (1197 passed, 2 skipped). commit 4ddf725; tag FIBR-0029-complete.

- ✅ [FIBR-0030] **"Forgotten password → start over" (destructive vault
  reset, double-confirmed).** Last resort on the unlock screen once the
  hint (FIBR-0029) and recovery key (FIBR-0019) are exhausted:
  irreversibly delete the vault and its sidecars and return to first-run
  setup so the user can begin fresh. **Double confirmation required** — a
  clear "this erases everything, permanently and unrecoverably" warning
  **and** a second explicit step (e.g. type DELETE) before anything is
  removed. By design nothing survives (the old data can't be decrypted
  without the key anyway). Target phase: P02. Dependencies: FIBR-0004.
  Lanes: crypto, ux. Kind: feature. Source: user-request-2026-07-01.
  Design confirmed by user 2026-07-20 + recon done (autonomous run). Affordance: new flat "Forgotten password? Start over…" button on UnlockDialog, modelled on _restore_button (ui/unlock.py:67-71 create, :103 layout, :108 click) + a new `start_over_requested` signal; the SHELL owns the flow (mirror restore_requested → main_window `_open_restore`). Double-confirm: Step 1 = QMessageBox.question with "cannot be undone" prose (model ui/statements.py:220-237); Step 2 = a small purpose-built QDialog whose OK is gated on a text field == "DELETE" (textChanged→_sync_ok→setEnabled, model ui/backup_export.py:79-106; the type-a-word gate is net-new). New primitive `AuthService.reset_vault()` (net-new; mirrors first_run/lock): call service.lock() first (idempotent, Windows-safe), then unlink BOTH paths.vault_path() AND paths.sidecar_path() (both must go or Vault.presence_state() raises VaultStateError on a mixed state) — reuse the unlink idiom at main_window.py:1020-1021. CRITICAL non-obvious: also unlink the SQLite WAL sidecars vault.db-wal / vault.db-shm (WAL mode is on, vault.py:104/174; NO path helper exists and nothing unlinks them today → they'd orphan). Clear the vault-coupled window.ini keys: UnlockThrottle().reset() (ui/_unlock_throttle.py:73-79) + clear_hint() (ui/_password_hint.py:42-45); LEAVE benign UI state (geometry/window_state/last_tab/theme/update-opt-in). Return to first-run: after delete call main_window `_route_pre_login()` (:1025-1031) → state() now "first_run" (both files gone) → _show_first_run(). Tests: new tests/features/vault_reset/; mirror test_backup_ui.py:67-75 (button fires signal) + :151-181 (shell flow builds MainWindow, invoke reset handler, assert both files gone + window._dialog is FirstRunDialog + throttle/hint keys absent in window_ini); conftest `paths`(:48-52) + autouse `window_ini`(:107-120) fixtures. NEXT: write docs/specs/FIBR-0030.md → /cold-eyes --max-loops 7 → reproduce-first TDD → close. (Note: FIBR-0019 recovery key referenced in the headline prose is context only — the hard dep is FIBR-0004, shipped; do not block on FIBR-0019.)
  Resolved (2026-07-21): shipped. AuthService.reset_vault() deletes the complete on-disk footprint (vault.db + KDF sidecar + both SQLite WAL sidecars vault.db-wal/-shm); UnlockDialog "Forgot password? Start over…" button + start_over_requested; StartOverDialog type-DELETE gate (exec()-driven, wires accepted->accept itself); shell _on_start_over does Step-1 warning -> Step-2 dialog -> try reset_vault (OSError->critical box) -> clear throttle+hint keys -> teardown -> first-run. security-model.md INV-12 (deletion-completeness hygiene) + T11 note. Spec docs/specs/FIBR-0030.md cold-eyes CONVERGED loop 6 (7-loop cap); reproduce-first TDD, 12 vault_reset tests, gate green 1209 passed. Tag FIBR-0030-complete.

- ✅ [FIBR-0031] **Failed-unlock throttling (exponential backoff).**
  Slow down brute-force guessing of the master password: after each wrong
  attempt on the unlock screen, impose a growing delay (e.g. 1s → 2s → 4s
  …, capped) before the next try is accepted. A one-off typo is barely
  noticeable; bulk guessing becomes infeasible. Pure client-side timing —
  no lockout that could deny the legitimate owner access, and no counter
  that weakens the crypto. Record the backoff schedule in security-model.md
  at spec time. Target phase: P04 (lands with the unlock flow).
  Dependencies: FIBR-0004. Lanes: security, ux. Kind: security.
  Source: user-request-2026-07-01.
  Duplicate of FIBR-0095 (2026-07-15): both describe failed-unlock exponential backoff on the master-password unlock screen. FIBR-0095 is the newer, verified record (confirmed 2026-07-11 that services/auth.py applies no backoff) and is the tracking item for the implementation. This bullet stays as the original provenance record — flip it ✅ alongside FIBR-0095 when the throttling ships.
  Resolved 2026-07-18 as the duplicate of FIBR-0095 (shipped) — failed-unlock exponential backoff is implemented and tested there (services/unlock_throttle.py + ui/_unlock_throttle.py, security-model INV-10).

- ✅ [FIBR-0032] **Clipboard auto-clear for copied sensitive values.**
  When the user copies a sensitive value (account number, amount, a stored
  PDF password), clear it from the system clipboard after a short timeout
  (~30s, configurable in the FIBR-0014 Settings screen) so it doesn't
  linger for other apps to read. Only clear if the clipboard still holds
  the value we put there (don't wipe something the user copied since).
  Target phase: P12. Dependencies: FIBR-0012, FIBR-0014. Lanes: ui,
  security. Kind: security. Source: user-request-2026-07-01.
  Scope check 2026-07-18 (autonomous run): DEFERRED pending a product/scope decision. Recon found the app has NO app-wired clipboard "Copy" affordances anywhere (no QClipboard/setText into clipboard in src/), so auto-clear is greenfield — it has nothing to clear until copy points are added first. Deciding what becomes copyable is a real fork: amount/description in the transactions context menu are natural + safe, but a "copy the stored statement PDF password" affordance would be a NEW exposure that regresses FIBR-0128 INV-1 (that secret currently never crosses into the UI). Needs a user call on (a) which values become copyable and (b) whether the PDF password is copyable at all, before writing the spec. Not silently guessing a UX+security scope. Kept 📋.
  Scope RESOLVED by user 2026-07-18: copyable values = transaction AMOUNT + DESCRIPTION only (add "Copy amount"/"Copy description" to the transactions list context menu), auto-clear after ~30s (configurable). The stored statement PDF password stays NON-copyable (no regression of FIBR-0128 INV-1); account number NOT copyable in this pass. Unblocked — ready to spec when its turn comes (currently queued behind FIBR-0033).
  Resolved (2026-07-20, autonomous run): shipped. "Copy amount"/"Copy description" added to the transactions context menu (rendered cell text + in-memory description — no vault read, lock-safe INV-8); PDF password + account numbers stay NON-copyable (FIBR-0128 INV-1 preserved). New ClipboardAutoClear(QObject) helper: single owned single-shot QTimer wired directly to clear_if_ours; live per-copy timeout; clears only if the clipboard still holds our value. AuthService clipboard_clear_seconds getter/setter, ALLOWED=(10,30,60,0), DEFAULT=30; Settings combo; 0="Never" honoured. security-model.md T13 threat row added + cold-eyes converged (loop 1, polish-only). Spec docs/specs/FIBR-0032.md cold-eyes converged loop 9. 23 clipboard tests (INV-1..8); full gate green (1164 passed, 2 skipped). commit 0b45573; tag FIBR-0032-complete.

- ✅ [FIBR-0033] **Backup restore-verification ("does my backup work?").**
  A one-click check that opens an encrypted backup (FIBR-0018) into a
  throwaway in-memory / temp copy, confirms it decrypts and its schema +
  row counts are intact, then discards it — proving the backup is
  genuinely restorable **without** touching the live vault. A backup never
  test-restored is a guess, not a safety net. Target phase: P12.
  Dependencies: FIBR-0018. Lanes: crypto, ux. Kind: feature.
  Source: user-request-2026-07-01.
  Dependency re-points: FIBR-0018 (the backup mechanism) is merged into and implemented by FIBR-0014, so this restore-verification builds on FIBR-0014's .fbk export/restore (docs/specs/FIBR-0014.md), not a separate FIBR-0018 deliverable.
  Started 2026-07-18 (autonomous run, after deferring FIBR-0032 on scope). One-click "does my backup work?" — open a .fbk (FIBR-0014) into a throwaway temp/in-memory copy, confirm it decrypts + schema/row-counts intact, discard it, WITHOUT touching the live vault. Spec -> /cold-eyes -> TDD -> close.
  Resolved (2026-07-19): shipped read-only backup verification. Service verify_backup(src, backup_password, *, on_key=None) -> VerifyResult + shared _open_backup_vault helper (caller owns work_dir; backup key+password wiped on every path incl. exceptions — INV-7); runs cipher_integrity_check (early-return corrupt), as-migrated schema == LATEST_SCHEMA_VERSION (INV-2), display-only counts; reason-code table (wrong_password/corrupt/bad_kdf_params/too_new/invalid/io_error). UI: BackupVerifyDialog + Settings "Verify backup…" button (settings_verify_backup) + main_window wiring (synchronous under wait cursor; no auto-lock, verify never touches the live vault — D7/INV-1). security-model.md T5 note (post-login read-only reuse of FIBR-0014 guards; no new pre-login surface). All 7 deliverables done. Reproduce-first TDD: 14 new tests. Full gate green (1142 passed, 1 skipped). One cold code-review lane: clean, no findings. Commit 42bca98, tag FIBR-0033-complete. (Retires duplicate scope none; distinct from FIBR-0014 restore.)

- ✅ [FIBR-0041] **Back-fill the CSV import path with the INV-5b resource-size cap.**
  security-model.md INV-5b binds an import resource budget (max file size / row count / parse time) to the import specs — naming FIBR-0007 (CSV) and FIBR-0008 (OFX) by id. FIBR-0008 pins the cap for the OFX path (D13: read_file_bytes stat-checks against _MAX_OFX_BYTES before read; a transaction-count cap). But FIBR-0007's CSV path (ImportService.read_file -> str) shipped WITHOUT a size cap, so security-model INV-5b's FIBR-0007 claim is currently unmet. Back-fill: apply the same size stat-check to read_file (or a shared bounded reader), pick a _MAX_CSV_BYTES constant, add a test (monkeypatch the cap down). Surfaced by the FIBR-0008 /cold-eyes (lane C, 2026-07-03).
  **Layman:** Add the same "reject a suspiciously huge file" safety limit to the CSV import that OFX import gets, so no oversized statement file can hog memory.
  Kind: security.
  Lanes: importers, services, tests.
  Source: cold-eyes-2026-07-03 FIBR-0008 lane-C.
  Resolved (2026-07-15): already shipped — verified stale bullet. ImportService.read_file (services/import_.py) routes through the shared _read_capped helper, refusing a file over _MAX_IMPORT_BYTES (16 MiB) BEFORE loading it, so security-model INV-5b's FIBR-0007 (CSV) claim is now met. Hardened beyond the original ask during a later indie-review (H-F/H-G): reads cap+1 bytes rather than trusting stat().st_size, so an endless-symlink (/dev/zero) or a file that grows post-stat can't slip an unbounded read past the cap. Tests: test_read_file_refuses_oversized_csv (monkeypatches the cap to 100) + test_read_capped_bounds_read_against_endless_symlink, both in tests/features/import_/test_import.py. No code change this session — flip only.

- ✅ [FIBR-0095] **Unlock throttling — backoff after repeated failed master-password attempts.**
  Verified 2026-07-11: services/auth.py applies NO delay/backoff on a failed unlock. Add an increasing backoff (spec finalized backoff-only — no lockout) after consecutive failed unlock attempts — defence-in-depth against bulk interactive guessing through the app's own unlock screen (the offline-crack path on a stolen vault is defended by Argon2id's slow KDF, security-model INV-2, not by this UI backoff). Track the attempt count / last-fail time in the plaintext window.ini (pre-unlock, non-sensitive; spec finalized persisted-not-in-memory so a relaunch can't reset the backoff); UX = a friendly 'try again in N seconds'. Deps: FIBR-0004 (unlock path).
  **Layman:** After several wrong master-password tries, finbreak briefly slows further attempts — extra protection if someone gets hold of your vault file.
  Kind: security.
  Source: claude-suggestion-2026-07-11.
  Started 2026-07-18 (self-directed, "build it all" autonomous run). Adding exponential backoff after repeated failed master-password unlock attempts; attempt count/last-fail persisted in plaintext window.ini so a relaunch doesn't reset the backoff. Spec -> /cold-eyes -> TDD -> /close-phase.
  Shipped 2026-07-18 (self-directed autonomous 'build it all' run). Capped exponential backoff (1s,2s,4s,…,30s) after a wrong master password in the unlock dialog; attempt count + last-fail persisted in plaintext window.ini so a relaunch can't reset it. Pure core services/unlock_throttle.py (exponent clamped BEFORE the power — tampered fail_count can't build a giant int) + QSettings adapter ui/_unlock_throttle.py (defensive int()/fromisoformat() coercion + tz-naive rejection) + UnlockDialog wiring (authoritative entry gate re-read every submit, 1-Hz countdown, reset-on-success, submit-only disable preserving FIBR-0004 INV-2f). security-model INV-10 (defence-in-depth, not a boundary). Spec /cold-eyes 4 loops → polish-converged; reproduce-first TDD 19 tests INV-1..7; /audit semgrep+bandit 0 on the changed surface; cold code-review caught 1 CRITICAL (tz-naive last_fail → aware/naive subtraction crash = owner lockout) folded reproduce-first + 1 LOW test tidy. Gate green 1126/1, mypy 0. Commits 7564234→7c8778d; tag FIBR-0095-complete.

- ✅ [FIBR-0096] **Per-release SHA256SUMS + generated SBOM alongside the signed AppImage.**
  The release AppImage is already Ed25519-signed (FIBR-0054 INV-14). Add, per release: a SHA256SUMS file (artifact checksums) and a generated SBOM (CycloneDX via cyclonedx-py, or pip-audit output) listing the bundled dependency versions — supply-chain transparency + a second integrity signal for users who verify manually rather than via the in-app updater. Wire into build-release-appimage.sh / the publish step. Deps: FIBR-0054 (release pipeline).
  **Layman:** Each download comes with a checksum file and a parts-list, so anyone can verify what's inside and that it wasn't tampered with.
  Kind: security.
  Source: claude-suggestion-2026-07-11.
  Resolved (2026-07-21): spec cold-eyes-converged over 8 loops (security/cross-ref lane clean 6–8; release-shell hardened), then reproduce-first TDD (10 tests, INV-1..7). Ships gen-checksums.sh (merge-aware manifest helper), two-phase signed SHA256SUMS with an anti-laundering fetch-verify gate + release-view fail-closed fetch, per-platform CycloneDX SBOM (freeze-before-PyInstaller, pip-audit -r --no-deps), and security-model INV-13. Gate green (1219 passed).

### 🎨 Features & accessibility

- ✅ [FIBR-0021] **Multi-currency decision (ADR).** Decide single- vs
  multi-currency for v1 **before** accounts are built. If multi: a
  currency column on accounts/transactions, QLocale-formatted display,
  and a rule that the dashboard never sums across currencies without
  conversion. *Sequencing:* decide before FIBR-0005 (accounts) — adding a
  currency column afterwards is a schema migration. Target phase: P03
  (the decision precedes it). Dependencies: none. Lanes: data.
  Kind: investigate. Source: user-request-2026-07-01.
  Resolved 2026-07-02 (user decision): SINGLE-currency for v1 — every
  account shares the vault's one base_currency, set at first-run. Rationale:
  matches the shipped FIBR-0004 model, and because FIBR-0005 introduces the
  forward-migration runner, adding per-account/per-transaction currency
  later is a routine forward migration, not a painful retrofit — so the
  "decide before accounts" gate is satisfied by choosing single-currency now
  and revisiting only when a real multi-currency need arises. If revisited:
  currency column on accounts/transactions, QLocale-formatted display, and a
  rule that the dashboard never sums across currencies without conversion.

- 📋 [FIBR-0022] **Budgets + recurring / subscription detection.**
  Per-category monthly spending limits with progress + over-budget
  signalling on the dashboard, plus automatic detection of repeating
  charges (same payee / amount cadence) so subscriptions surface. Target
  phase: P10. Dependencies: FIBR-0006 (category tree), FIBR-0010 (rules).
  Lanes: reporting, ux. Kind: feature. Source: user-request-2026-07-01.
  Split 2026-07-15: the recurring/subscription-detection half is now FIBR-0142 (active, being built first per user pick). This bullet stays as the budgets tracking item (per-category monthly limits + over-budget dashboard signalling) — the follow-up after FIBR-0142 ships.

- 📋 [FIBR-0023] **Theming: separate theme sets for normal and
  colourblind vision + picker.** Ship **two families** of themes — a set
  for normal colour vision **and** a set designed for colourblind users
  (protanopia / deuteranopia / tritanopia-friendly palettes) — selectable
  from the FIBR-0014 Settings screen (beside the FIBR-0017 language
  picker). The normal-vision family goes beyond plain light/dark: ship a
  small curated set of named themes — at minimum **Light**, **Dark**,
  **Midnight** (near-black OLED-friendly), **Solarized Light**,
  **Solarized Dark**, **Sepia** (warm, low-eyestrain), and a
  **High-contrast** pairing — plus a **"follow the OS"** option that
  tracks the system light/dark setting. Each theme is a named palette
  (window / surface / text / accent / chart-series roles), defined in one
  place so adding a theme is data, not code — no per-widget hardcoded
  colours (coding.md § 8 bars magic constants without a named source; a
  QSS stylesheet + palette tokens keeps colours in one table). Dashboard
  charts (FIBR-0012) draw series colours from the
  active theme's chart-series role, so whichever theme is chosen keeps the
  chart series distinguishable. Target phase: P12. Dependencies:
  FIBR-0012, FIBR-0014. Lanes: ui, accessibility. Kind: ux.
  Source: user-request-2026-07-01.

- 📋 [FIBR-0024] **Accessibility: keyboard navigation + screen-reader
  support.** Full keyboard control (focus order, shortcuts, no mouse-only
  actions) and screen-reader labels/roles via Qt accessibility
  (`QAccessible`) on widgets and charts. Pairs with the i18n/RTL
  (FIBR-0017) and theming (FIBR-0023) work. Target phase: P12.
  Dependencies: FIBR-0014. Lanes: ui, accessibility. Kind: accessibility.
  Source: user-request-2026-07-01.

- 📋 [FIBR-0034] **Import preview + undo (rollback a whole import batch).**
  Before an import lands, show a preview — "about to add 214 transactions
  from 3 May–2 Jun across 1 account" — so a wrong file can be cancelled
  before it touches the ledger. Each committed import is tagged as a batch
  so it can be undone in one action if it was the wrong statement.
  Preserves manual category overrides on re-import per FIBR-0010's rule.
  Target phase: P06 (lands with the first import UI). Dependencies:
  FIBR-0007. Lanes: services, ui, repo, tests. Kind: feature.
  Source: user-request-2026-07-01.

- ✅ [FIBR-0035] **Auto-categorisation that learns from corrections.**
  Extends the FIBR-0010 rules engine: when the user manually re-files a
  transaction (e.g. "TESCO" → Groceries), offer to create or update a rule
  so similar future transactions self-categorise — the tedious part gets
  quieter the more the app is used. Always a **suggestion** the user
  confirms (never a silent auto-rule), and a manual override still wins
  over any learned rule (FIBR-0010's invariant). Target phase: P08
  (extends the rules engine). Dependencies: FIBR-0010. Lanes: services,
  ui, tests. Kind: feature. Source: user-request-2026-07-01.
  Note (2026-07-09): the core learn-from-corrections behaviour (offer to *create* a rule from a manual correction; suggestion-only; manual override still wins) is pulled forward into FIBR-0010 (spec INV-5 / D11), per the 2026-07-09 user request. FIBR-0035's "*update* an existing rule" variant is subsumed by FIBR-0010 D6 (a learned rule inserts at top priority, beating the rule it corrects — no in-place update needed). Re-evaluate / close this bullet when FIBR-0010 ships.
  Resolved (2026-07-10): fully delivered by FIBR-0010. The create-a-rule-from-a-correction learning is FIBR-0010 INV-5/D11; the update-an-existing-rule variant is subsumed by D6 (a learned correction inserts at top priority, beating the rule it corrects — no in-place update needed). Suggestion-only + manual-override-wins guarantees both hold. No separate work remains.

- 📋 [FIBR-0036] **Net-worth-over-time trend.** A dashboard line showing
  the running total across all accounts month to month — is the overall
  picture trending up or down — distinct from FIBR-0012's
  income-vs-expenditure bars (this is the cumulative balance, not per-month
  flow). Draws its series colour from the active theme (FIBR-0023) like the
  other charts. Target phase: P10. Dependencies: FIBR-0012. Lanes:
  reporting, ui, tests. Kind: feature. Source: user-request-2026-07-01.

- 📋 [FIBR-0038] **Statement coverage tracking + gap detection.**
  Record each imported statement's coverage period (start/end date) per
  account as first-class data, then a gap-detection pass reports
  uncovered date ranges between covered ranges, per account (e.g.
  Jan–Mar + May-onwards -> flags April missing). Range-based, so it is
  reliable where a transaction-date heuristic is not: a quiet month with
  zero transactions is still "covered" if its statement was imported, and
  it handles non-monthly cycles (quarterly) and overlapping imports
  (merge coverage). "Up to date" (latest statement -> today) is not a
  gap; only holes between covered ranges are. Surfaces as a per-account
  completeness report + a dashboard warning badge. Depends on the
  coverage-period capture hook added at first import (FIBR-0007) — without
  recorded periods, gaps can only be guessed from transaction dates
  (false alarms on quiet months). Dependencies: FIBR-0005 (accounts —
  gaps are per-account), FIBR-0007 (import captures the periods).
  **Layman:** Warns you when you've skipped a statement — e.g. you loaded January–March and then May onwards, and it spots that April is missing for that account.
  Kind: feature.
  Lanes: services, repo, ui, tests.
  Source: user-request-2026-07-02.

- 📋 [FIBR-0039] **In-app liability disclaimer + issue reporting.**
  A plain-language liability disclaimer — the app is provided as-is and is not responsible for incorrect information it may display (mis-parsed amounts, wrong totals); it is local-only and not financial advice. Shown at first run (acknowledged once, persisted) and always available from an About/Help dialog. Alongside it, a "Report an issue" link opening the GitHub Issues page (https://github.com/milnet01/finbreak/issues) so users can log problems for resolution. Complements the MIT LICENSE's warranty disclaimer with a user-facing, plain-English one. Shares the About/Help screen with the donate-links item — whichever ships first builds the screen.
  **Layman:** A clear notice that the app isn't responsible for any incorrect figures it shows, with an easy button to report problems so they get fixed.
  Note (FIBR-0054): when this disclaimer copy is written, phrase "local-only" as **data-locality** ("your financial data stays on your machine"), not "never connects" — the opt-in updater is a consented outbound exception, so a bare "local-only" shown on-screen would mislead.
  Kind: feature.
  Source: user-request-2026-07-03.
  Coordination note update: FIBR-0051 (P07.5) ships only a minimal About (QMessageBox.about) and puts donate links in their own Donate menu — it does NOT build the shared About/Help screen. So this bullet still owns building that screen (disclaimer + "Report an issue" link); the old "whichever of FIBR-0039/0040 ships first builds the screen" pact no longer applies.

- ✅ [FIBR-0040] **In-app donate / support links.**
  Clickable support links that open each FUNDING.yml sponsor page in the user's browser — GitHub Sponsors (milnet01), Patreon (AntsProjectsHub), and the Paybru tip URL (https://paybru.co.za/tip/ants-projects-hub). Surfaced in the About/Help dialog and a Help-menu entry. Keep the URLs in one place in sync with .github/FUNDING.yml (a small constants module or read at build time) so they never drift. Shares the About/Help screen with the disclaimer item.
  **Layman:** Buttons in the app that open the pages where people can support the project financially.
  Kind: feature.
  Source: user-request-2026-07-03.
  Being delivered by FIBR-0051 (P07.5 app-shell, spec in cold-eyes): its Donate menu ships all three FUNDING.yml links + the sync check (FIBR-0051 INV-8a). Flips ✅ when FIBR-0051 ships (FIBR-0051 DoD #6). Note the placement differs from this bullet's "About/Help dialog + Help menu" — FIBR-0051 uses a dedicated Donate menu.
  Resolved (2026-07-09): delivered by FIBR-0051's Donate menu — the three .github/FUNDING.yml links (GitHub Sponsors/Patreon/PayBru) via QDesktopServices.openUrl + the INV-8a sync check that fails on drift. Placement is a dedicated Donate menu rather than the About/Help dialog; same substance.

- ✅ [FIBR-0042] **Preserve the as-posted local date for a timezone-bearing OFX <DTPOSTED>.**
  Surfaced by the FIBR-0008 /indie-review (lane 1, 2026-07-04). `OfxImporter` uses `tx.date.date().isoformat()`; ofxparse normalises a timestamped `<DTPOSTED>` to UTC (`local - offset`), so a transaction posted in the evening of a negative-offset zone rolls to the next calendar day (verified: `20260105230000[-5:EST]` -> "2026-01-06"). Two consequences: (a) mis-assignment to the wrong day and, at a month boundary, the wrong statement period; (b) it can defeat INV-6 cross-source dedup (an OFX row keyed on occurred_on won't match a manually-entered copy if the OFX date shifted). Out of the FIBR-0008 contract (D4/INV-1b specify date-only DTPOSTED, and the fixtures use date-only, so nothing shipped is wrong). Blocked-ish: ofxparse discards the original tz offset, so the fix needs either raw-DTPOSTED reparsing or a product decision on whether local or UTC date is authoritative. Fix: decide the authoritative date, recover the local calendar date (or document UTC), add a tz-bearing DTPOSTED test.
  **Layman:** Some bank OFX files stamp each transaction with a time and timezone; today an evening transaction can be filed under the wrong day, which can also stop it matching a manually-typed copy.
  Kind: fix.
  Source: indie-review-2026-07-04 FIBR-0008 lane-1.
  Progress (2026-07-18): self-directed pick. Root cause confirmed — ofxparse 0.21 `parseOfxDateTime` returns `local_date - timeZoneOffset` (UTC), so a tz-bearing `<DTPOSTED>`/`<DTEND>` shifts the calendar day. Fix: a small `_LocalDateOfxParser(OfxParser)` subclass neutralises the printed `[offset:tz]` bracket to `[0:GMT]` and delegates to super, preserving the as-posted local date (the roadmap's decided semantic) for BOTH transaction dates and the DTSTART/DTEND span. Reuses ofxparse's own parsing (msec/null-date/custom-format). Reproduce-first TDD.
  Resolved (2026-07-18): SHIPPED. `_LocalDateOfxParser(OfxParser)` in `ofx_importer.py` overrides `parseOfxDateTime` to rewrite the printed `[offset:tz]` suffix to `[0:GMT]` before delegating to super, so ofxparse's UTC normalisation is a no-op and the as-posted local date is preserved for transaction dates AND the DTSTART/DTEND span (reuses the base parser's msec/null-date/custom-format handling; date-only values untouched). Reproduce-first TDD in `tests/features/ofx_import/` INV-11/11a/11b (negative-offset evening stays same day, month-boundary DTEND not extended into next month, positive-offset morning does not roll backward) — all fail pre-fix, green after. Self-review + full gate green 1107/1, mypy 0 (small fix; FIBR-0141/FIBR-0149 precedent — no full /indie-review). This also restores INV-6 cross-source dedup for shifted evening rows.

- ✅ [FIBR-0047] **Date pickers show unambiguous ISO YYYY/MM/DD, not the locale's M/D/YY.**
  Shipped 2026-07-04: setDisplayFormat("yyyy/MM/dd") on the main-window date field + the import wizard's period pickers; regression test in the vault suite. A user-CHOSEN format is the separate item below.
  **Layman:** Dates now always read year/month/day (e.g. 2026/07/04) so there's no US-vs-rest-of-world confusion.
  Kind: ux.
  Source: user-request-2026-07-04.

- ✅ [FIBR-0048] **User-configurable date-display format (Settings).**
  Belongs with FIBR-0014 (P12 Settings). The ISO yyyy/MM/dd default already shipped; this promotes it to a user choice persisted in the vault settings.
  **Layman:** Let the user pick how dates are shown (e.g. DD/MM/YYYY, YYYY-MM-DD) instead of the fixed ISO default.
  Kind: feature.
  Source: user-request-2026-07-04.
  Resolved (2026-07-11): subsumed by FIBR-0083, which shipped the user-configurable date-display format (plus timezone + time format) as its date half. No separate work remains.

- 📋 [FIBR-0049] **First-run onboarding / empty-state guidance on the home screen.**
  The home screen opens on the manual add-transaction form with cryptic fields (Amount, Description) and no guidance, which confused a real non-technical tester. Add empty-state help + inline field hints (Amount = money in/out, negative = out; Description = what it was for).
  **Layman:** A friendly welcome for a brand-new user — 'import a statement, or add a transaction by hand' — instead of a bare form.
  Kind: ux.
  Source: user-request-2026-07-04.
  Empty-state half delivered by FIBR-0051 (P07.5): the HomeView getting-started page is this bullet's "friendly welcome — import a statement or add a transaction". Remaining scope: the inline Amount/Description field hints on the manual-entry form (not in FIBR-0051). Stays open for those hints.

- ✅ [FIBR-0050] **Standard Bank (SA) statement text-parser — one reader for all account types.**
  Extends P07 (FIBR-0009). The generic ruled-table extractor
  mangles or misses several real Standard Bank layouts (the
  Current account collapses into one cell; the credit card's
  two-columns-per-line + gridline-less layout is unreadable). Add
  ONE Standard Bank text-layer reader (not per-account-type
  files) that parses the printed transaction lines and feeds the
  existing preview -> dedup -> commit pipeline; a recognised
  statement skips column-mapping (like OFX). Covers current,
  savings, home-loan, revolving-credit-loan, credit-card, and money-market/investment
  statements. Signed amount = the printed figure signed by the running-balance delta
  (unifies the families incl. the home loan, which prints no
  per-amount sign); credit card uses the Debit/Credits section
  rule (flip to purchases-negative budget view). Handles both
  number formats (US 1,427.41 and European 239.206,04 — the RCP
  loan), MM-DD dates with year inferred from the statement
  period, full-ISO dates (home loan), multi-line descriptions,
  per-page brought-forward continuation, and non-transaction row
  skipping. Correctness check: per-row balance-delta == printed amount (primary); additive opening balance + sum of parsed
  amounts == printed closing balance where the statement prints one (Savings has none). Loan-sign note: on a loan a
  fee shows positive (debt up) under the balance-delta rule — a
  user-facing loan-sign toggle is a possible follow-up. Fixtures
  100% SYNTHETIC (no real PII/ID/statements committed).
  Dependencies: FIBR-0009.
  Lanes: importers, ui, tests.
  **Layman:** Makes all your real Standard Bank statements — cheque, savings, home loan, personal loan, credit card and money-market — import cleanly, by teaching the app to read the printed statement lines the way you do.
  Kind: feature.
  Source: user-request-2026-07-05.
  Resolved (2026-07-05): shipped one Standard Bank text-layer reader (StandardBankImporter) for all six account types — current, savings, home loan, revolving-credit, credit card, money-market — family-dispatched inside one module. Validated end-to-end on all six real statements (checksums pass) + 13 synthetic fixtures. Spec cold-eyes-converged (9 loops); TDD (36 tests). Close: /audit clean; /indie-review (2 rounds, cold) — code findings (credit-card de-interleave HIGH, decrypt-crash net, INV-7b sign gate) + a confirming re-review round (1 HIGH corrupt-PDF Qt-slot crash, region-scoped number detection, Family-C continuation fold, _cc_opening sign, INV-12 test correction) all fixed inline; final cold pair clean. Gate green (277 passed/1 skipped, mypy 0). Fixtures 100% synthetic. Journal: docs/journal/FIBR-0050.md. Tag FIBR-0050-complete.</note>

  <invoke name="mcp__ants__changelog_log">
  /mnt/Games/Scripts/Linux/finbreak

- ✅ [FIBR-0059] **Edit a logged statement — re-assign its account (and its transactions) to fix an import mistake.**
  User request 2026-07-09: after importing an SBSA credit-card statement that got
  linked to "Current", the user wants to correct an already-logged statement's account
  in place. Scope: a "Change account" action on the Statements tab (FIBR-0052) that
  opens an account picker and atomically re-points BOTH statement_periods.account_id
  AND every linked transactions.account_id (WHERE statement_period_id = id) to the
  chosen account — one service-owned BEGIN…COMMIT (mirrors delete_statement's atomic
  pattern), leaving manual + other statements' rows untouched, ROLLBACK on failure.
  Refreshes the Statements list + Home + the status count (changed signal). The target
  account must exist (the user creates "Credit Card" in the Accounts tab first if
  needed). Also the tool that lets the user fix any statement mis-linked by FIBR-0057
  (the import account-snapshot bug). Deps: FIBR-0052 (Statements tab + provenance
  column). Next: spec -> /cold-eyes -> TDD -> /close-phase.
  **Layman:** Lets you correct a statement you already imported — e.g. change it from Current to Credit Card — without deleting and re-importing. It moves the statement and all of its transactions to the account you pick.
  Kind: feature.
  Source: user-request-2026-07-09.
  Resolved (2026-07-09): a "Change account" action on the Statements tab. StatementService.reassign_account(period_id, new_account_id) atomically re-points statement_periods.account_id AND every transaction stamped with it (one owned BEGIN…COMMIT mirroring delete_statement; ROLLBACK to a re-openable vault). A span-collision guard runs BEFORE BEGIN (pure read + refuse) with a period_id self-exclusion, so a same-account pick is the INV-5 no-op, not a false refusal; a real collision (target already has that span) raises ValueError → a tr() warning. A DISTINCT reassigned signal (the changed handler hard-codes "Statement deleted") drives a "Statement account changed" status via a shared refresh helper. New AccountPickerDialog (preselects the current account, deleteLater'd). StatementRow += account_id; repos get()/set_account()/reassign_account() (commit-free); no schema change (reuses the v6 provenance stamp). Spec /cold-eyes-converged in 6 cold loops (2 lanes = 12 reviews; design stable since loop 2). TDD 14 tests. Close: /audit 0; /indie-review 2 cold lanes — data/service CLEAN, UI/shell 1 LOW (undisposed picker dialog) folded inline. Gate green 366 passed/1 skipped; FIBR-0059 src mypy-clean. Also filed FIBR-0061 (mypy not enforced in the gate + 4 pre-existing test-file type errors, found during this close). Commits 2fc5a42 + review fold.

- 📋 [FIBR-0072] **Warn (or disable chrome) when navigating away from an in-progress import.**
  main_window._open_import() never disables the toolbar/menu, so clicking Home/Statements/Accounts/Categories/Rules mid-import silently rebuilds the workspace and destroys the in-progress wizard (chosen file, column mapping, unsaved preview) with no confirmation. Either confirm before discarding, or disable navigation chrome during an import (as locked states do).
  Kind: ux.
  Source: indie-review-2026-07-10 (M-shell1).

- 📋 [FIBR-0073] **Add keyboard mnemonics to menus + dialog labels (a11y sweep).**
  Menu titles (File/View/Window/Help/Donate) have no '&' Alt-accelerators; no dialog uses label mnemonics. Weakens keyboard-only navigation vs a typical desktop app (WCAG-adjacent). One focused sweep across main_window + the dialogs.
  Kind: accessibility.
  Source: indie-review-2026-07-10 (shell L1 + dialog INFO).

- 📋 [FIBR-0074] **Dedicated per-bank PDF readers for ABSA / Nedbank / FNB (needs real anonymised sample statements).**
  Today ABSA/Nedbank/FNB statements CAN already be imported two ways: (1) their CSV/OFX exports (most reliable), and (2) the generic PDF table-extractor (pdf_importer.py) for any PDF with ruled transaction tables, via the column-mapping step. A DEDICATED zero-config text-layer reader like standard_bank.py (auto-detect + no mapping) needs REAL anonymised sample statements per bank to build and validate — the SB reader (FIBR-0050) required 6 real statements to catch layout edge cases; synthetic dummy PDFs exercise code paths but don't validate real-world layouts. Blocked on the user providing (or the project sourcing) a few real anonymised statements per bank. Until then, the generic extractor + CSV/OFX cover these banks.
  **Layman:** Zero-config PDF import for the other big SA banks, the way Standard Bank statements already import without mapping columns.
  Kind: feature.
  Source: user-request-2026-07-10.

- ✅ [FIBR-0083] **User-configurable timezone + date/time display format (Settings).**
  Motivated by dogfooding v0.1.0: the Statements tab 'Imported' column shows a raw ISO UTC timestamp (e.g. 2026-07-11T06:49:15.506928+00:00). Extends FIBR-0048 (user-chosen DATE-display format) to also cover the user's TIME ZONE and TIME-of-day format, so any timestamp renders in the user's zone + preferred format. Belongs with FIBR-0014 / FIBR-0055 Settings; the prefs persist in the vault settings (like the auto-lock timeout). Render via QDateTime + QTimeZone + QLocale (coding.md 5.2), consistent with FIBR-0017 QLocale formatting. Ships together with / absorbs FIBR-0048 (date half).
  **Layman:** Let a person pick their time zone and how dates and times are shown, so timestamps (like a statement's 'Imported' time) read in their local time and chosen format instead of a raw UTC value.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).
  Resolved (2026-07-11): shipped via TDD in 4 slices — pure datetime_format formatter (format_date/format_timestamp, presets, "system" sentinel + INV-6 fallbacks); DateTimePrefs + AuthService persistence (vault settings, no schema change); Settings + first-run combos (shared ui/_datetime_prefs.py); display wiring (Statements Period/Imported, Home Date) + live push on Settings Save. 8 cold-eyes loops on the spec; full gate green.

- ✅ [FIBR-0084] **User-customisable table columns — resize, reorder, and remember per tab.**
  Motivated by dogfooding v0.1.0. Extends FIBR-0052 (which already remembers window geometry + last-active tab in the plaintext window.ini sibling) to per-table column state. Make each QTableView/QTreeView header user-resizable AND movable (QHeaderView.setSectionsMovable(True)); persist each table's full header state (column widths + order) via QHeaderView.saveState()/restoreState(), keyed per tab, in the plaintext window.ini (non-sensitive UI state, like geometry — FIBR-0052 INV-5; NOT the vault). Covers every relevant table: Statements, Home transactions, Accounts, Categories, Rules. A Reset-layout action (FIBR-0052) should also clear saved column state.
  **Layman:** Let a person drag columns wider or narrower and drag them into a different order on any table (Statements, Home, Accounts, Categories, Rules), and have finbreak remember that layout next time.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).
  Scope re-checked 2026-07-28 — mostly already shipped, folded into
  FIBR-0113. Everything this bullet asks for exists: ui/_table_state.py's
  remember_columns() sets setSectionsMovable(True), restores
  QHeaderView.saveState()/restoreState() from the plaintext window INI
  (paths.window_settings_path, NOT the vault — the FIBR-0052 INV-5 rule
  this bullet names), keyed per table by objectName, and re-saves on
  resize / reorder / re-sort. The Reset-layout action this bullet also
  asks for is main_window._reset_layout (menu action
  "action_reset_layout"), but it does NOT clear saved column state — see the 2026-07-28 correction below. Shipped as
  FIBR-0117 with the reorder half added by FIBR-0012, and most recently
  extended to the import-wizard preview table.
  Correction + re-scope (2026-07-28, /cold-eyes on docs/specs/FIBR-0113.md).
  The 2026-07-28 note above was written from recall and was WRONG twice; both
  claims are now corrected against source:

  - "The Reset-layout action this bullet also asks for is
    main_window._reset_layout": the action exists, but _reset_layout removes
    exactly _KEY_GEOMETRY, _KEY_STATE and _KEY_SIZE. It never touches the
    "columns/<objectName>" entries remember_columns writes, so saved column
    state survives a Reset layout. What this bullet asks for is NOT done.
  - "this bullet's residue is exactly FIBR-0113's table conversion": false.
    Two further surfaces have no column persistence at all —
    ui/forecast.py's 4-column events table (objectName already
    "forecast_events"; forecast.py imports nothing from _table_state) and
    ui/home.py's dashboard breakdown trees (QTreeWidget, setColumnCount(2),
    a VISIBLE Name/Amount header, objectName "dashboard_breakdown_<key>";
    home.py likewise imports nothing from _table_state). This bullet's own
    text names both classes — "each QTableView/QTreeView header" and "Home
    transactions" — so they are in scope by its own wording (user confirmed
    2026-07-28).

  Re-scoped accordingly: FIBR-0113 delivers ONLY the Accounts table (it was
  carrying the rest, and a cold-eyes loop showed that fold-in was the largest
  single source of defects in that spec). The remaining three gaps are now
  FIBR-0192, which is the blocker for this bullet's ✅.

  So: do NOT flip this bullet when FIBR-0113 ships. Flip it when FIBR-0192
  ships. Categories stays deliberately out of scope (single column under
  setHeaderHidden(True) — nothing to resize or reorder).

  Call sites today: statements, transactions, rules, recurring, transfers,
  import_wizard. Accounts is genuinely missing (still a QListWidget with no
  header at all) and making it a table is FIBR-0113; Categories is
  deliberately out of scope, not an omission. But those two are NOT the
  whole residue — see the correction above: Forecast, the Home dashboard
  trees and Reset layout remain, and they are FIBR-0192's.
  Resolved (2026-08-02): unblocked by FIBR-0192, which was this bullet's stated blocker. Every table and tree the app shows now resizes, drag-reorders and remembers its layout per tab — the Forecast events table and the three Home breakdown trees were the last two unwired surfaces, and Window → Reset layout now returns them all to their build-time defaults in the same click.

- 📋 [FIBR-0085] **Batch statement import — import several statement files in one go.**
  Motivated by dogfooding v0.1.0. Today the import wizard handles ONE file per run (FIBR-0007 CSV / FIBR-0008 OFX / FIBR-0009 PDF). Add multi-file selection that runs each file through the existing preview -> dedup -> commit pipeline, with per-file semantics (a bad/duplicate file is reported and skipped, never aborting the batch) and a summary dialog listing each file's outcome (imported N / skipped-duplicate / failed-why) + transaction counts. Mixed formats (CSV/OFX/PDF) allowed in one batch; per-file mapping where the format needs it (CSV mapping profile selection, PDF password prompt). Reuses the existing importers + FIBR-0052 statement provenance; the new work is the multi-file wizard flow + aggregate reporting. Deps: FIBR-0007/0008/0009 (importers), FIBR-0052 (per-statement provenance so each imported file is a distinct statement row).
  **Layman:** Let a person select and import many statement files at once (e.g. a whole folder of monthly PDFs) instead of importing them one at a time.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).

- 📋 [FIBR-0086] **Account numbers + import auto-detect — match a statement to its account (prompt to create if new).**
  Motivated by dogfooding v0.1.0. The account-number STORAGE half shipped separately as FIBR-0193 (2026-07-30): `accounts.account_number` is a nullable column in the ENCRYPTED vault, added by schema migration **v12 -> v13** — so this bullet is now DETECTION + MATCHING only, and no new column is needed. On import, extract the statement's account number and match it to a configured account (normalised: strip spaces/dashes; match on TRAILING digits when the statement masks it, e.g. "xxxx1234"), auto-selecting the account instead of today's manual pick. Availability varies by format: OFX <ACCTID> (reliable), PDF printed number (the Standard Bank / generic parsers can surface it), CSV often carries none — so auto-detect is a SMART DEFAULT with a manual fallback whenever the number is absent or matches zero/multiple accounts (never silently import to the wrong account — cf. FIBR-0059). When the detected number matches no account, prompt to create one, pre-filled from statement metadata (number, bank name if printed, type/currency where available) and asking the user for the rest. ENABLER for FIBR-0085 (batch import) — auto-detect is what makes multi-file import usable (you cannot hand-map a folder of files); reduces reliance on FIBR-0059 (change-account fix). Deps: FIBR-0005 (accounts), FIBR-0007/0008/0009 (importers must surface the statement's number), FIBR-0052 (statement provenance).
  **Layman:** Give each account its account number so importing a statement automatically files it under the right account — and if it's an account finbreak hasn't seen, it offers to create it, pre-filled from the statement.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).

- 📋 [FIBR-0087] **Per-account currency — support offshore/foreign-currency accounts in the portfolio (revisits FIBR-0021).**
  The user wants to include an offshore account in their portfolio — the "real multi-currency need" FIBR-0021 deferred to (it chose single base_currency for v1, set at first-run, and said revisit when this arises). Per FIBR-0021's own "if revisited" note: add a currency column on accounts (default = the vault base currency), CHOOSE the currency when ADDING an account (the user's ask), QLocale-format each amount in its account's currency, and enforce that the dashboard NEVER sums across currencies without explicit conversion. Needs its OWN design/spec — the hard decisions: (a) consolidated totals across currencies — NO live FX rates (that would widen the network surface beyond the one FIBR-0054 update egress), so either per-currency subtotals or a user-entered/stored conversion rate; (b) how the dashboard presents mixed currencies (per-currency subtotals vs one converted total). Schema migration (currently v7 -> v8). Deps: FIBR-0005 (accounts), FIBR-0012 (dashboard totals). Kept SEPARATE from FIBR-0083 (date/time formatting).
  **Layman:** Let each account have its own currency (e.g. a USD offshore account alongside your ZAR accounts), chosen when you create the account, so foreign accounts show and total correctly.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).
  Consolidation design (proposed direction, user Q 2026-07-11 "how do mixed-currency statements consolidate into graphs/summaries?"): NO live FX rates (offline posture — only the FIBR-0054 updater egress). Default = per-currency subtotals: the dashboard shows each currency separately (ZAR panel, USD panel), NEVER summing across currencies (upholds FIBR-0021's rule). PLUS an optional USER-ENTERED exchange rate (stored in the vault) that converts everything to the base currency for a single consolidated total + unified graphs, always LABELLED "converted at your rate, entered <date>" so it's never mistaken for a live figure; user updates it at will. Warrants a small ADR ("how finbreak handles FX") when built. Rejected: live-rate fetch (breaks offline).

- 📋 [FIBR-0088] **Detect an already-imported statement up front (content hash) — warn before re-importing.**
  User wants an early 'already imported?' check that short-circuits BEFORE the per-transaction dedup (saving redundant work). Partly plumbed already: statements store source_filename and statement_periods has id_for_span (account+period existence check). Robust key = a CONTENT HASH (SHA-256 of the file bytes): detects a re-import of the IDENTICAL file regardless of filename — filename alone is unreliable (same file renamed; or two different files both named 'statement.pdf'). Add a file_hash column (schema migration, currently v7), compute it at import start, and if it matches a prior import WARN the user with an import-anyway option (a corrected re-issue is a legit re-import) rather than silently skipping. The existing account+period match (id_for_span) is a softer secondary signal. COMPLEMENTS, not replaces, transaction dedup (INV-6), which still catches overlapping-but-different files. Primarily a UX safeguard against accidental re-import; the CPU saving is a bonus. Also gives FIBR-0085 (batch import) its per-file 'already imported -> skipped' outcome. Deps: FIBR-0007/0008/0009 (importers), FIBR-0052 (statement provenance).
  **Layman:** When you import a statement finbreak has already seen, it tells you up front ('looks like you already imported this') instead of silently re-processing it.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.0).

- 📋 [FIBR-0089] **Backup safety nudge — first-run emphasis + a 'last backup was N days ago' reminder.**
  The encrypted-backup MECHANISM is planned in FIBR-0014; this is the SAFETY UX around it. ADR-0003: no password recovery = permanent data loss, so a backup is the only mitigation. Add (a) first-run copy stressing 'back this up somewhere safe', and (b) a gentle, non-blocking reminder when the last backup (tracked via a vault-settings timestamp) is older than a threshold. Depends on / complements FIBR-0014 (the export itself). Highest-value safety improvement per the 2026-07-11 review.
  **Layman:** Because a forgotten master password means your data is gone for good, finbreak reminds you to keep a backup — stressed at first run and gently nudged if it's been a while.
  Kind: ux.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0090] **Split a transaction across multiple categories.**
  A personal-finance staple. One transaction carries N category allocations summing to its amount. Affects the categorization model (per-transaction allocations, not a single category_id) and the dashboard totals (aggregate by allocation, not whole-transaction). Schema change (an allocations/splits table). Deps: FIBR-0006 (categories), FIBR-0010 (categorization), FIBR-0012 (dashboard totals must respect splits). Own spec.
  **Layman:** Split one purchase across categories — e.g. a R1,200 shop = R900 groceries + R300 household — so your breakdowns are accurate.
  Kind: feature.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0091] **Free-text notes + tags on transactions.**
  A free-text note and/or tags (labels) per transaction, orthogonal to the category tree. Enables richer filtering/reporting in the dashboard's filterable table (FIBR-0012). Schema: a note column + a tags table (many-to-many). Deps: FIBR-0012 (filters), FIBR-0052 (transactions). Own spec.
  **Layman:** Attach a note or tag ('reimbursable', 'holiday 2026') to a transaction for context the category tree can't hold, and to filter/report on.
  Kind: feature.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0092] **Rule preview (what will it match?) + bulk re-categorize selected transactions.**
  Enhances FIBR-0010's rules engine + the categorization UX. (a) Rule preview: on rule create/edit, show the matching transactions (the would_categorize primitive already exists, FIBR-0010) before commit. (b) Bulk action: multi-select rows in the Home/transactions table -> set category (and optionally offer to make a rule). Pairs with FIBR-0084 (column/row UX) and FIBR-0012 (filterable table). Deps: FIBR-0010. Mostly UI + reuse of existing services.
  **Layman:** When you write a categorisation rule, see which transactions it'll catch before saving; and select many rows to set their category at once.
  Kind: enhancement.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0093] **Plain data export — CSV / spreadsheet of your categorised transactions.**
  A 'File -> Export data' that writes the (filtered) transactions — date, amount, description, account, category, notes/tags — to CSV (and optionally XLSX). Complements the report-style PDF export (FIBR-0013): this is RAW DATA for spreadsheets, not a formatted report. Local file write, no network (offline posture holds). Deps: FIBR-0007/0008/0009 (the data), FIBR-0012 (filters define the export scope). Own small spec.
  **Layman:** Export your categorised transactions to a CSV/spreadsheet for your own analysis or your accountant.
  Kind: feature.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0094] **Account balances + net-worth over time (opening balance + running balance).**
  Today finbreak tracks TRANSACTIONS, not balances. Add a per-account opening balance (+ as-of date); derive a running balance per transaction; surface an account-balance and consolidated net-worth trend on the dashboard. Interacts with FIBR-0011 (transfers — moving money between your own accounts must not change net worth) and FIBR-0087 (multi-currency net worth needs the FX decision). Schema: opening_balance on accounts. Deps: FIBR-0011, FIBR-0012, FIBR-0087. Bigger; own spec + likely an ADR on balance derivation.
  **Layman:** Track each account's balance over time — set an opening balance and finbreak shows running balances and your overall net-worth trend, beyond just spending-by-category.
  Kind: feature.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0100] **Undo for destructive actions (delete statement / delete category).**
  Today destructive actions are confirm-only (Statements delete with its transactions, FIBR-0052; category delete-cascade, FIBR-0010). Add a short-lived undo — a status-bar 'Deleted — Undo' for a few seconds, or Edit -> Undo — that restores the deleted rows within the same session. Friendlier than confirm-only; reduces fear of the delete buttons. Design: soft-delete or an in-memory undo stack + a re-insert. Deps: FIBR-0052, FIBR-0010.
  **Layman:** An 'undo' right after deleting a statement or category, so a misclick isn't permanent.
  Kind: ux.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0101] **Keyboard-first categorising — shortcuts for fast triage of a big import.**
  Add keyboard shortcuts to the transaction table: set-category (opens the picker), jump-to-next-uncategorised, and quick-assign recent categories. Speeds triaging a large import. Pairs with FIBR-0092 (bulk re-categorize) and FIBR-0010 (rules); cleaner once FIBR-0097 (model/view) lands. Mostly UI. Deps: FIBR-0010.
  **Layman:** Categorise a large import quickly with the keyboard — set a category and jump to the next one without reaching for the mouse.
  Kind: ux.
  Source: claude-suggestion-2026-07-11.

- ✅ [FIBR-0105] **User-configurable amount display: negative sign style + colour (Settings).**
  Two independent prefs persisted in the vault settings (mirrors FIBR-0083
  DateTimePrefs / FIBR-0055 auto-lock): (1) negative-amount style — "minus"
  (−ZAR25,000.00) vs "brackets" ((ZAR25,000.00), today's QLocale default); (2)
  colour amounts on/off — money-out red, money-in green. Settings + first-run
  controls; applied at the Home transactions table's Amount column (the only
  amount display today). Default: minus + colour ON. Display-only (never mutates
  stored data). Ships in v0.1.5 alongside the inline update notes.
  **Layman:** Let a person choose how money amounts look — negatives as a minus sign (−R25) or in brackets (R25), and turn on/off colouring money-out red and money-in green — so the transaction list reads the way they prefer.
  Kind: feature.
  Source: user-request-2026-07-11 (dogfooding v0.1.4: "why are some values in brackets?" → make it a Settings choice).
  Resolved (2026-07-11): TDD-built in 4 slices — AmountPrefs + AuthService.amount_prefs/set_amount_prefs (INV-2/5); _format_amount explicit sign (- / ()) locale-independent + _NEGATIVE_TEXT/_POSITIVE_TEXT colour in HomeView (INV-1/3/4); Settings combo + colour checkbox and first-run mirror (INV-6/7); shell reads/passes/re-pushes on Save. 19 new tests; full gate green (598 passed). Lands on main; publishes in v0.1.5 (bundled with the inline update notes).

- ✅ [FIBR-0106] **Credit-card (Family C) import: opening balance mis-read from a prose "brought forward" decoy line.**
  Root-caused (verified against a real SBSA CC statement, synthetic fixture to
  follow — real file/password never committed). `_cc_opening` (standard_bank.py
  :812) returns the LAST money token on the FIRST line containing "balance
  brought forward". A credit-in-hand statement prints a prose summary line
  "...has a credit balance. Balance brought forward on this statement -251.85"
  BEFORE the real opening line "21 Jul 25 Balance Brought Forward 6,849.68", so
  it grabs -251.85 (which is actually the CLOSING balance carried to the next
  statement). Checksum then fails: reconciled = opening - Σ = -251.85 - 7101.53
  vs closing -251.85. With the correct opening 6,849.68 it reconciles exactly
  (6849.68 - 7101.53 = -251.85 = closing). Fix: anchor the match so the phrase
  is at line start (optionally after a `DD Mon YY` date) with the amount
  immediately after — the prose sentence won't match. TDD with a synthetic
  fixture carrying the decoy line + a real opening + a reconciling body.
  **Layman:** A real Standard Bank credit-card statement refused to import ("didn't add up") because the importer read the wrong opening balance.
  Kind: fix.
  Source: dogfooding-2026-07-11.
  Resolved (2026-07-11): anchored _cc_opening on a new _CC_BROUGHT_FORWARD regex requiring a money amount to IMMEDIATELY follow the "balance brought forward" phrase (optional -/R sign), and take the first money token in the tail from the phrase onward. The prose decoy ("...credit balance. Balance brought forward on this statement -251.85") has narrative text between phrase and figure, so it no longer matches; the real anchor "21 Jul 25 Balance Brought Forward 6,849.68" does. TDD: 2 pure unit tests (decoy-rejection + printed-negative-sign preservation) in tests/features/standard_bank_pdf; full SB suite (50) green, no regression on the 6 validated real statements. Gate green (600 passed/1 skipped). Synthetic figures only — real file/password never touched disk.

- ✅ [FIBR-0107] **Self-update relaunch: wait for the old AppImage to exit before launching the new one.**
  The 0.1.4→0.1.5 relaunch (detached Popen + PYINSTALLER_RESET_ENVIRONMENT, then immediate os._exit) still raced the old AppImage's teardown: the fresh onefile bootloader started while the old image's FUSE mount + _MEI extraction dir were still live and died ("closed but didn't reopen"). Fix (update_installer.py): spawn a detached /bin/sh WAITER (new session) that polls `kill -0 <old-pid>` until this process has fully exited — FUSE unmounted, _MEI cleaned — and only THEN execs the swapped image with the reset env. Hard ~60s cap (600 × 0.1s) so a wedged old process can never hang the relaunch. Same pattern robust self-relaunching Qt AppImages (RPCS3, PCSX2) use. Added a diagnostic relaunch log (data-dir sibling of the vault) capturing the waiter's + relaunched image's output so a future silent failure leaves evidence. TDD: pure _relaunch_command builder test (waits on pid, quoted exec after the loop), detached-session/env test updated to the waiter contract, log-write test; plus a real-process smoke proving the waiter blocks until the old pid dies then execs. Gate green (602 passed/1 skipped). NOTE (two-cycle trap): this code ships in 0.1.6 but only RUNS on the 0.1.6→next update — 0.1.5→0.1.6 still relaunches via the old 0.1.5 logic, so one manual reopen is still expected for that hop.
  **Layman:** After an update the app closed but didn't reopen; now it reliably restarts itself.
  Kind: fix.
  Source: dogfooding-2026-07-11.

- ✅ [FIBR-0108] **Update download: show real progress instead of a permanently-full indeterminate bar.**
  The "Downloading…" bar in the update dialog is hardcoded to indeterminate (busy) mode — ui/update_dialog.py:79 `self._busy.setRange(0, 0)` — so it shows a moving/striped full bar the entire download rather than actual percent-complete. The fix is feasible without new deps: services/update_fetch.py `download()` already streams the body in 64 KiB chunks (`_DOWNLOAD_CHUNK_BYTES`, line 89), so it can (a) read the total from the response `Content-Length` header and (b) accept an optional progress callback invoked per chunk with (received, total). Then the DownloadWorker (ui/_update_worker.py) emits a progress signal and the dialog switches the bar to determinate (`setRange(0, total)` + `setValue(received)`), falling back to indeterminate only when Content-Length is absent/zero. Keep the byte-cap (max_bytes) guard intact. TDD: unit-test the callback fires with monotonic received ≤ total and a missing-Content-Length fallback; a qtbot test that the bar goes determinate on a known-size download. Kind: enhancement.
  **Layman:** While an update downloads, the progress bar looks full/striped the whole time instead of filling up as it downloads.
  Kind: enhancement.
  Source: dogfooding-2026-07-12.
  Resolved (2026-07-28): update_fetch.download takes an optional per-chunk on_progress callback reporting (received, total) with total from Content-Length (0 when absent/malformed); UpdateService passes it to the asset download only, DownloadWorker relays it as a Qt signal, and UpdateDialog.set_progress switches the bar to determinate — an unsized download keeps the indeterminate look. INV-10 byte cap untouched. Tests: test_FIBR0108_download_reports_progress_against_content_length, _absent_or_malformed_content_length_reports_unknown_total, _download_worker_relays_progress, _prompt_bar_goes_determinate_on_a_known_size, _prompt_bar_stays_indeterminate_when_size_unknown.

- ✅ [FIBR-0109] **Move the Home transaction list to a dedicated Transactions tab with account / date-range / amount-range filters.**
  User request 2026-07-12. Today Home is the transaction table (HomeView). Move that table to its own Transactions tab and add filters: by account, by date range (from/to), and/or by amount range (min/max), combinable. This dovetails with FIBR-0012 (the dashboard's "filterable table" + Home-as-summary vision) and complements FIBR-0011 (a confirmed-transfer marker could later show here). Reuses the existing list_transactions read; the filter is a query/where layer. Dates in the filter follow the typed-or-picker rule below.
  **Layman:** Give the transaction list its own tab with filters for account, date range and amount, so the Home tab is freed to become a summary/dashboard.
  Kind: feature.
  Lanes: ui.
  Source: user-request-2026-07-12.
  Absorbed into FIBR-0012 (P10 dashboard) 2026-07-12: the Transactions tab is built there with search + date-range + account + category filters (all combinable). The amount-range (min/max) filter this bullet originally named was NOT chosen in the FIBR-0012 brainstorm and is DEFERRED (recorded in docs/specs/FIBR-0012.md Out-of-scope) — a clean future follow-up. Close this bullet when FIBR-0012 ships; re-open a fresh item only if the amount-range filter is still wanted.
  Resolved (2026-07-28): closed as covered by its absorb target. FIBR-0012
  (P10 dashboard) is ✅ and shipped the dedicated Transactions tab
  (src/finbreak/ui/transactions.py) with search + date-range + account +
  category filters, all combinable — which is what this bullet asked for
  minus one piece. The amount-range (min/max) filter the 2026-07-12 absorb
  note explicitly DEFERRED is still wanted, and is re-filed as its own
  item rather than kept alive here.

- 📋 [FIBR-0110] **Every date input accepts typed entry (validated) or a date picker.**
  User request 2026-07-12. Cross-cutting UX: wherever a date is entered — the manual-entry dialog, the future Transactions filters (above), any settings/import date field — offer both a typed field (ISO-validated, the existing parse_transaction date check) and a QDateEdit-style calendar picker, so neither typists nor mouse users are forced. A shared date-input widget/helper so the two modes stay consistent (Rule-of-Three: extract on the third site).
  **Layman:** Anywhere you enter a date in the app, you can either type it (with a check that it's a real date) or pick it from a small calendar.
  Kind: ux.
  Lanes: ui.
  Source: user-request-2026-07-12.

- 📋 [FIBR-0111] **Show the currency in its own column, separate from the amount value.**
  User request 2026-07-12 (screenshot): the Home Amount column renders "ZAR69.00" / "-ZAR25,000.00" with the currency crammed against the number, hard to read. Give the currency its own column (or right-align the bare number and show the currency code separately), so the value column holds just the formatted number + sign. Touches HomeView._format_amount / the Amount column layout (FIBR-0105 amount-display work) and should carry through to the future dedicated Transactions tab (FIBR-0109). Keep the negative-style (minus/brackets) + red/green colour prefs (FIBR-0105) working on the value column.
  **Layman:** Put the currency code (e.g. ZAR) in its own column so the number is easy to read, instead of "ZAR69.00" crammed together.
  Kind: ux.
  Lanes: ui.
  Source: user-request-2026-07-12.

- ✅ [FIBR-0112] **Credit-card (Family C) import: continuation page without a column header drops its transactions.**
  Root-caused against a real SBSA CC statement (2025-10-20; real file/password never committed, synthetic fixture/tests to follow). A 3-page statement: page 1 = summary, page 2 = transaction table WITH the "Date Description Amount" column header, page 3 = continuation transactions with NO column header (opens straight into a "Debit Debit" section). _table_region (standard_bank.py:229) locates the Family-C region only by that column header, so page 3's region is empty and its 3 transactions (Checkers 514.21 + Cash Finance Charge 23.05 + Tips 10.00 = 547.26) are silently dropped. The completeness checksum then fails (opening 1348.95 - Σ = 1421.51 vs closing 1968.77; the 547.26 gap is exactly the dropped rows) and the whole statement is refused. Fix: when a Family-C page has no column header, fall back to starting the region at the first real transaction row (a CC segment ending in a 2-decimal amount) — which excludes summary-page date spans like "Statement Period 20 Sep 25 to 20 Oct 25" that carry no 2-decimal tail. TDD: pure _table_region unit tests (header-less continuation page captured; header-less summary page stays empty) + reconciliation; validated end-to-end against the real statement in a throwaway scratchpad.
  **Layman:** Another real Standard Bank credit-card statement refused to import ("didn't add up") because the last page's transactions were being skipped.
  Kind: fix.
  Source: dogfooding-2026-07-12.
  Resolved (2026-07-12): _table_region now falls back, on a Family-C page with no "Date Description Amount" column header, to starting the region at the first real transaction row (a CC segment ending in a 2-decimal amount — which excludes summary-page date spans like "Statement Period 20 Sep 25 to 20 Oct 25"). TDD: 2 pure _table_region unit tests (header-less continuation page captured; header-less summary page stays empty). Validated end-to-end on the real SBSA 2025-10-20 statement in a throwaway scratchpad: now 72 drafts, reconciles exactly (1348.95 - (-619.82) = 1968.77 = closing); the 3 previously-dropped page-3 rows (Checkers 514.21, Cash Finance Charge 23.05, Tips 10.00 = 547.26) are captured. Full SB suite + gate green (604 passed/1 skipped). Real file/password never committed; tests are synthetic. Note: a pre-existing cosmetic issue remains (a "Continued on next page......" line folds into the last page-N transaction's description) — filed separately, not this fix.

- ✅ [FIBR-0113] **Accounts tab: show accounts in a sortable 5-column table (Name / Type / Account number / Note / Status) instead of one line.**
  User request 2026-07-12 (screenshot): the Accounts tab lists each account as one line "Credit Card — Credit card" (name — type). Move to a columnar QTableWidget with columns: Name, Type of account, Account number, Note (optional), Status. Requires two NEW nullable account fields — account_number and note (schema bump) — plus the add/edit form growing those inputs and the AccountsWidget becoming a table (mirrors the Rules/Statements tab table shape). Account number is display/reference only (not used for matching). Dovetails with the columnar direction of FIBR-0109 (Transactions tab) and the account credential accessors already on the accounts repo (FIBR-0009).
  **Layman:** Show accounts in a proper table (Name, Type, Account number, an optional Note, and a Status column you can sort by) instead of a single cramped "Name — Type" line each.
  Kind: feature.
  Lanes: ui, repo.
  Source: user-request-2026-07-12.
  Started 2026-07-28, with FIBR-0084 folded in. Scope check first: the
  column machinery FIBR-0084 asks for ALREADY SHIPPED under FIBR-0117 /
  FIBR-0012 — _table_state.remember_columns does widths + drag-reorder +
  per-table persistence in the window INI keyed by objectName, and
  main_window._reset_layout does NOT clear it (corrected 2026-07-28, see below). It is already called by Statements,
  Transactions, Rules, Recurring, Transfers and the import-wizard preview.
  The only two screens without it are Categories (a single-column
  QTreeWidget with setHeaderHidden(True) — column customisation is
  meaningless there) and Accounts (still a QListWidget). So FIBR-0084's
  residue IS this item, and it closes alongside.
  Re-scoped 2026-07-28 (/cold-eyes loop 2 on docs/specs/FIBR-0113.md).
  The "FIBR-0084 folded in" plan above is WITHDRAWN, and one claim in it was
  wrong: main_window._reset_layout does not clear saved column state (it
  removes geometry / window_state / window_size only), so FIBR-0084 was never
  as close to done as that note said. Two more surfaces also lack column
  persistence entirely — ui/forecast.py's events table and ui/home.py's
  2-column dashboard breakdown trees.
  Progress (2026-07-28): /cold-eyes loop 5 ran and did NOT converge —
  CRITICAL 3 · HIGH 6 · MEDIUM 13 · LOW 13 · INFO 8, all verified, none
  fixed. Full write-up with cites and proposed fixes:
  docs/reviews/FIBR-0113-cold-eyes-loop5.md (do NOT re-dispatch review
  lanes to rediscover them — fold them in from that file).
  The three CRITICALs: (1) §4.5's premise that redrawing the table drops
  the selection is FALSE — with a sort active the selection survives and
  resolves to a DIFFERENT account, so the form loads account B while the
  selection points at account A and the next Update writes B onto A
  (reproduced against real Qt: docs/reviews/FIBR-0113-selection-drift-repro.py);
  (2) §4.4's trailing _on_selection_changed() copies a StatementsWidget
  line whose handler there only toggles buttons — on Accounts it also
  rewrites the form, so every _refresh() clobbers in-progress input and
  defeats _on_add's field-clearing; (3) INV-12 requires the test to
  assert the table cells "carry the typed values", which contradicts
  §4.3's masked cell — satisfying it literally ships the account number
  UNMASKED with every other invariant green.
  Three HIGHs are the same shape — the spec promises something no
  invariant locks: the account-number column's masking, the table's
  click-sortability, and the update write path for the two new columns.
  SPLIT EXECUTED (2026-07-28): loop 5's recommendation was to SPLIT rather than run
  loop 6 — draft defects are not falling (three NEW structural gaps
  appeared at loop 5 after four cold reads missed them), and the spec is
  985 lines vs a ~567 median. Proposed seam and per-finding assignment
  are in the review file. FIBR-0113 keeps the UI half; the schema +
  model/repo/service half became FIBR-0193.
  Also note: the /cold-eyes cheap breadth pass returned ZERO suspects on
  all three lanes this loop; the strong pass then found 3 CRITICAL. The
  skill has been amended so a breadth pass can no longer certify a lane
  clean after a loop that produced CRITICAL/HIGH.
  Split executed (2026-07-28), and split again on 2026-07-30. This item
  now delivers the TABLE half ONLY: the 5-column sortable Accounts table,
  the account-number cell and form field with the number ALWAYS masked, and
  the two-row edit form. The reveal toggle and its auto-hide timer moved to
  FIBR-0198, which ships AFTER this. The storage half — migration v13, models.Account, the accounts
  repository and service — moved to FIBR-0193, which SHIPS FIRST: this
  table reads and writes columns FIBR-0193 creates.

  Loop 5's 35 verified findings were routed to whichever half owns them per
  the assignment in docs/reviews/FIBR-0113-cold-eyes-loop5.md, and folded in
  directly rather than re-reviewed. The two open decisions that gated the
  three CRITICALs were resolved against current source, not by preference:
  (1) _refresh() uses CLEAR-then-fill, because AccountsWidget._refresh
  already opens with self._list.clear() — clear-then-fill preserves today's
  behaviour, where the StatementsWidget reuse-rows shape would newly
  introduce the cross-account write CR-1 reproduced; (2) the Forget-button
  rule moves into a gating-only helper _apply_forget_gating(), called from
  _on_selection_changed and _refresh()'s tail here, plus FIBR-0198's reveal
  handler once that ships, so a refresh can no longer repopulate the form
  (CR-2 + HI-6 in one fix).

  Headline + Layman card reconciled to five columns in this same edit (both
  still said four; the Status column was the user's 2026-07-28 decision).

  Spec rewritten as the UI half; cold-eyes gate re-run from loop 6 against
  the reduced document — §13's loop log for loops 1-5 is a frozen record and
  travels with this id.

  Folding that work in here made this spec the largest source of its own
  review defects (4 of 5 criticals in cold-eyes loop 2 traced to the
  fold-in). Split on the user's call: the FIBR-0084 completion work moved
  to FIBR-0192, which is what unblocks FIBR-0084's ✅. Two further splits
  followed — the storage half to FIBR-0193 (2026-07-28) and the reveal to
  FIBR-0198 (2026-07-30) — so this item's scope is the paragraph above,
  not this one.

  Consequence for the close: flip ONLY this bullet when the work ships.
  FIBR-0084 stays 📋 until FIBR-0192 lands.

  User decisions (2026-07-28):
  - FIVE columns: Name | Type | Account number | Note | Status. The Status
    column absorbs the suffixes _refresh currently concatenates onto the
    row text (the 🔑 saved-statement-password marker and the FIBR-0177
    reconciliation ✓ / ⚠ off by {money} / ⚠ {n} periods marker), so the
    user can click-sort to bring non-reconciling accounts to the top.
  - Account number is MASKED wherever it is displayed (last 4 shown) — it
    is shoulder-surf / screenshot exposure, not storage exposure (the vault
    is already encrypted). The mask is display-only; the stored value is
    verbatim. The way to SEE the full number is FIBR-0198's, not this
    item's.
  - The add/edit form stays INLINE on the tab, relaid as a two-row grid
    rather than moving to a dialog.

  Work (this item only, after the two splits): AccountsWidget moves
  QListWidget -> QTableWidget using the existing _table_state seam
  (SortableItem for the sortable columns, fill_guard, tag_row/selected_index
  so an action still targets the right account after a re-sort,
  enable_sorting, remember_columns with a distinct objectName), plus the
  two-row edit form and the always-masked account-number cell. The
  migration, the Account model and the repo/service changes are FIBR-0193's
  and ship first; the reveal toggle and its timer are FIBR-0198's and ship
  after. Spec cold-eyes-gated; TDD next.
  Cold-eyes gate 2026-07-30: 5 loops run jointly with FIBR-0198 (3
  strong cold lanes each, no breadth pass). 132 findings verified, 1
  unverified, all fixed — 3 CRITICAL / 30 HIGH / 50 MEDIUM / 54 LOW.
  Draft defects fell 30 -> 17 -> 11 -> 10 -> 8; fix collateral ran
  0 -> 9 -> 7 -> 5 -> 9. Stopped at loop 5 on the
  collateral-outnumbers-draft trigger, with implementation next.

  Highest-value catches: the reveal's clipboard copy escapes the
  auto-hide entirely (ClipboardAutoClear is wired only to the
  transactions list), so FIBR-0198's T13 amendment had to say the copy is
  NOT auto-cleared; three invariant legs were unbuildable or vacuous
  against a correct implementation; and this bullet's own body
  contradicted the split in seven places, including FIBR-0084's closing
  paragraph, which would have flipped that item green with three
  surfaces unbuilt.

  Nothing is owed on either spec. Both are gated and ready to build.
  Order: FIBR-0193 (storage) -> FIBR-0113 (table) -> FIBR-0198 (reveal).
  Resolved (2026-07-30): shipped by TDD, on top of FIBR-0193's storage.
  `AccountsWidget._list` (QListWidget) became `_table` (QTableWidget) with five
  sortable columns — Name, Type, Account number, Note, Status — built like
  `StatementsWidget`'s (NoEditTriggers / SelectRows / SingleSelection /
  `enable_sorting` / `remember_columns` on a new `accounts_table` objectName), so
  Accounts joins the shared remembered-column scheme (FIBR-0084's Accounts
  surface; the other three stay FIBR-0192's). The add/edit form relaid into a
  two-row grid with Account-number and Note fields. The number is masked on BOTH
  surfaces by two different mechanisms — the cell via the new
  `_mask_account_number` (a QTableWidgetItem has no echo mode), the form field via
  `Password` echo mode; the form always holds the RAW value, or an Update would
  write "•••• 7890" back as the account number. Row identity moved to the
  `_table_state` contract (tag on fill, `selected_index` in every handler), and
  the six `_ACCOUNT_*_ROLE` constants were deleted as a correctness requirement:
  `_ACCOUNT_ID_ROLE` and `_ROW_INDEX_ROLE` are both `Qt.ItemDataRole.UserRole`, so
  a survivor would make `selected_index` return a database id used as an index.
  The fill is clear-then-fill (a leading `setRowCount(0)` inside `fill_guard`) —
  the sibling's reuse-rows shape lets a selection ride its item through a re-sort
  onto a different account (reproduced against real Qt; the Statements twin is
  FIBR-0194, not fixed here). Status is a `SortableItem` keyed on a severity rank,
  composing the reconciliation marker first and the 🔑 second — the reverse of the
  old list line, since the column sorts by severity — and the four `tr()` literals
  dropped their leading "  ·  ". Reproduce-first TDD: 19 red before the rewrite
  (INV-5/7/9/12/15/18/20/21/22 in `test_accounts.py`, INV-8/17 in
  `test_table_state.py`), with four existing legs RE-DERIVED rather than
  re-pointed because a mechanical `_list`→`_table` swap would have left them
  passing while checking less — the FIBR-0128 sentinel sweep above all. Cross-doc
  per spec §12: FIBR-0005, FIBR-0128 and FIBR-0177 annotated, README + both
  Accounts screenshots refreshed (the demo seeder now carries numbers and notes so
  the masking is visible), CHANGELOG. FIBR-0198 (the reveal toggle) is next;
  FIBR-0084 stays 📋 until FIBR-0192.

- ✅ [FIBR-0114] **Auto-lock should be an inactivity timer (reset on user activity), not an absolute timer from unlock.**
  User report 2026-07-12. AuthService._arm_timer (auth.py:241) starts a single-shot QTimer at unlock (and only re-arms on a settings change), so the auto-lock fires a fixed duration after UNLOCK regardless of activity — locking mid-use. Fix: make it an inactivity timer. Add AuthService.notify_activity() that restarts the running timer with its existing interval (no settings re-read, since it fires on every input event; no-op when locked/headless), and have MainWindow install an application-level event filter that calls notify_activity() on user-input events (MouseButtonPress/MouseMove/KeyPress/Wheel). TDD: service-level (notify_activity restarts the running timer when unlocked, no-op when locked) + shell-level (eventFilter calls notify_activity on an input event).
  **Layman:** The screen-lock countdown ignored whether you were actively using the app — it locked a fixed time after unlocking even mid-use. It should count from your last interaction.
  Kind: fix.
  Source: dogfooding-2026-07-12.
  Resolved (2026-07-12): added AuthService.notify_activity() — restarts the running idle timer with its armed interval (no settings re-read; no-op when locked/headless) — and MainWindow now installs an application-wide event filter that calls it on MouseButtonPress/MouseMove/KeyPress/Wheel. The auto-lock now counts from the last interaction, not from unlock. TDD: 2 service-level tests (restart-when-unlocked via a spy timer; no-op-when-locked) + 1 shell-level test (a KeyPress through the app filter calls notify_activity). Gate green (607 passed/1 skipped), mypy/ruff/bandit/gitleaks clean.

- 📋 [FIBR-0115] **Credit-card import: strip the "Continued on next page" footer from the last transaction's description.**
  Surfaced while fixing FIBR-0112 (not that bug — amounts/checksum are unaffected). On a multi-page Family-C statement, the in-region "NNNN Continued on next page......" line has no transaction date, so _fold/_parse_family_c folds it into the PRECEDING transaction's description (e.g. "# International Txn Fee 0453155796 Continued on next page......"). Cosmetic data-quality issue affecting one row per page break. Fix: treat a line matching a "Continued on next page" / bare account-number footer as a skip line (like the "Debit"/"Credits" section headers in _is_cc_skip_line), not a description continuation. TDD with a synthetic fixture line.
  **Layman:** On multi-page credit-card statements, one transaction's description gets a stray "Continued on next page..." tacked onto it. Cosmetic only — the amounts are correct.
  Kind: fix.
  Source: dogfooding-2026-07-12.

- ✅ [FIBR-0116] **Toolbar icons: muted theme-aware colour that brightens to vibrant on hover.**
  User request 2026-07-12: the toolbar glyphs are currently a single flat mid-grey (#808080, hand-authored monochrome SVGs loaded by ui/icons.py `icon()`; the toolbar is ToolButtonTextUnderIcon). Wanted: (1) each icon a MUTED colour by default, (2) the icon brightening to a VIBRANT version of that same hue while the mouse hovers, reverting on leave, and (3) colours chosen per the active theme (light/dark). Approach sketch: give each glyph a semantic accent colour, then re-tint at load time — either recolour the SVG per state (parse `stroke="#808080"` → muted/vibrant/theme variants and build a QIcon with Normal/Active pixmaps so Qt swaps to the Active pixmap on hover automatically), or drive it via a QProxyStyle / event-filter on the toolbar buttons. Theme-awareness ties into the theme system FIBR-0014 builds (dark/light/follow-system) — coordinate so the muted/vibrant palettes have a light AND dark variant. Related: FIBR-0014 (palette-adaptive re-tinting / dark-theme polish) — this is the specific hover-brighten behaviour, keep them cross-referenced. Icons live in src/finbreak/ui/icons/*.svg; loader is src/finbreak/ui/icons.py.
  **Layman:** Give the toolbar buttons gentle colour that lights up brightly when you point at one, and dims back when you move away — and pick colours that suit the current light or dark theme.
  Kind: enhancement.
  Lanes: ui.
  Source: user-request-2026-07-12.
  Resolved (2026-07-12): toolbar_icon() recolours each hand-authored SVG at load — a per-icon muted semantic hue at rest (QIcon Normal) + a vibrant one on hover/focus (QIcon Active/Selected, Qt's built-in hover swap, no event filter), tuned to the active light/dark theme via the app palette. 8 glyphs each get a calm distinct hue; _make_action uses it for toolbar + menus. Tests: Normal≠Active, theme-aware + hover more saturated, unmapped-glyph fallback. Ships in v0.1.7. Live theme-switch re-tint stays with FIBR-0014 (icons read the palette at build time).
  Live theme-switch re-tint is delivered by FIBR-0127 (the theme system): MainWindow re-runs toolbar_icon() for each icon'd action on the ThemeController's themeChanged signal, so the muted/vibrant glyphs re-tint to the new light/dark palette without a relaunch. The FIBR-0116 muted/vibrant seam (v0.1.7) is the mechanism; FIBR-0127 wires the live-on-switch trigger. (2026-07-14)

- ✅ [FIBR-0117] **Data tables: remember column widths + click-header-to-sort (toggle order on re-click).**
  User request 2026-07-12 (screenshot, Statements tab): the QTableWidget-based data tables should (1) REMEMBER column widths across sessions, and (2) allow clicking a column header to sort by that column, with a second click on the same header toggling ascending/descending. Applies to the Statements table and the other list tables (Rules, the FIBR-0011 Transfers tables, the FIBR-0113 Accounts table, Home). Approach: QTableWidget.setSortingEnabled(True) gives click-to-sort with the asc/desc toggle for free (note: with sorting on, populate rows then enable, and key numeric/date columns with a sortable value — e.g. QTableWidgetItem data role or zero-padded/ISO text — so "112" doesn't sort before "69" and dates sort chronologically). Persist column widths via QHeaderView.saveState()/restoreState() into the window INI (paths.window_settings_path, same store as geometry, NOT the vault — it is non-secret view state), keyed per-table by objectName. Requested for inclusion in the v0.1.7 release alongside FIBR-0011. Related: the columnar tables in FIBR-0111/FIBR-0113.
  **Layman:** Let the tables (Statements, and the other lists) remember how wide you've dragged each column, and let you click a column heading to sort by it — click again to flip between ascending and descending.
  Kind: enhancement.
  Lanes: ui.
  Source: user-request-2026-07-12.
  Resolved (2026-07-12): new ui/_table_state.py — SortableItem (numeric/date sort keys), enable_sorting, remember_columns (header saveState/restoreState → window INI keyed by objectName, not the vault), and a row-tag scheme (tag_row/selected_index/select_by_index) so an action maps to the correct row after a re-sort (the money-critical guard). Applied to Statements, Transfers, Home (click-sort + widths + persisted sort/direction; Home moved off all-Stretch to interactive+stretch-last). Rules keeps priority order (not sortable) but persists widths, per user choice. tests/features/table_state/ covers numeric sort, tag-survives-reorder, action-targets-sorted-row, and width+sort persistence across rebuild. Ships in v0.1.7.

- ✅ [FIBR-0118] **App icon: transparent (rounded) corners instead of a hard square tile.**
  User request 2026-07-12 (About-box screenshot): the app/window icon (the donut-on-dark-navy tile) has hard square corners that read as a solid block against the dialog background. Make the corners transparent — a rounded-rectangle alpha mask so the four corners are see-through. Regenerate the whole icon set from the 1024 master: apply the rounded-corner alpha to assets/icon/finbreak.png (or add the mask step in scripts/make-icons.sh), then re-run make-icons.sh to rebuild the Linux PNGs (16-512), the Windows .ico, the macOS .iconset, and the runtime src/finbreak/ui/icons/app.png. Keep the corner radius modest (~15-20% of the tile) so it matches platform icon conventions. Verify the About box + taskbar show transparent corners (QIcon/PNG alpha travels). Requested alongside the v0.1.7 polish batch. Related: FIBR-0037 (the branded app icon) + FIBR-0116 (toolbar-glyph colour).
  **Layman:** Round off the corners of the app icon so it doesn't show as a solid square block — the corners become see-through and blend into whatever's behind it.
  Kind: ux.
  Lanes: ui, packaging.
  Source: user-request-2026-07-12.
  Resolved (2026-07-12): make-icons.sh applies an 18%-radius rounded-rectangle alpha mask to the master once, deriving every size (Linux hicolor PNGs, Windows .ico, macOS .iconset, runtime app.png) from the rounded temp; master stays square. Regenerated the set; regression test asserts transparent corners + opaque centre. Refreshed the dogfood install's hicolor icons so the launcher shows it now; the About-box (embedded app.png) rounds on the v0.1.7 install. Ships in v0.1.7.

- ✅ [FIBR-0119] **Home Loan (Family B) import: page-break footer/letterhead folds into the previous transaction's description.**
  Root-caused against a real SBSA Home Loan statement (2026-02-28; real file/password never committed, synthetic fixture/tests to follow). On a multi-page Family-B statement, a page break prints the registered-office letterhead (bare account number, "Standard Bank Centre …", "P O Box …", "Tel. Switchboard: … Fax: …") plus a repeated column header ("Debit Credit Balance" / "Date Date Fee") BETWEEN two transactions. None of those lines carries a date+amount, so _fold (standard_bank.py:489) — which appends every non-row in-region line to the preceding transaction as a description continuation — glued the whole block onto the last transaction before it (e.g. "Insurance Premium 0453155796 Standard Bank Centre … Debit Credit Balance Date Date Fee"). Amounts/dates/counts are unaffected (54 drafts still reconcile), so it imported "successfully" with a corrupt description; it also makes dedup fragile across statements where the same transaction appears with different page-break pollution. Fix: a shared _is_boilerplate() predicate (bare account/reference number; SB registered-office/contact markers; a repeated column-header line whose tokens are all table-header words) that _fold drops instead of folding — generalising the existing _is_cc_skip_line Family-C rule. TDD: pure synthetic _parse_family_b test (footer+header block between two rows → clean descriptions) + re-validated the two real Home Loan statements (27 / 54 drafts, clean descriptions) and the full synthetic A/B/C/D suite. NOTE: the "27 new · 27 duplicate" the user saw importing the 2026-02 statement after the 2025-08 one is CORRECT — the 2026-02 statement restarts at 2025-03-01 (54 drafts = the 27 overlapping the first statement, deduped, + 27 new); no dedup bug.
  **Layman:** On a multi-page home-loan statement, one transaction's description got the whole page footer (bank address, phone/fax, column headers) glued onto the end — making it a paragraph long instead of a few words.
  Kind: fix.
  Source: dogfooding-2026-07-12.
  Resolved (2026-07-12): added a shared `_is_boilerplate()` predicate (bare account/reference number; SB registered-office/contact markers — "standard bank centre"/"standardbank.co.za"/"P O Box"/"switchboard"/"fax"/registration/FSP; a repeated column-header line whose tokens are ALL table-header words) that `_fold` drops instead of folding into the preceding transaction — generalising the Family-C `_is_cc_skip_line` rule; the header-token set deliberately excludes ambiguous words (service/details/description/amount/reference) so a genuine wrapped description isn't mistaken for a header. TDD: pure synthetic `_parse_family_b` test (footer+letterhead+repeated-header block between two rows → clean descriptions). Re-validated the two real Home Loan statements (27 / 54 drafts, all descriptions clean incl. the formerly-polluted 2025-11-03 "Insurance Premium") + the full synthetic A/B/C/D suite. Gate green 656/1. The "27 new · 27 duplicate" the user saw was CORRECT (the 2026-02 statement restarts at 2025-03-01: 54 drafts = 27 overlapping the first import (deduped) + 27 new) — no dedup change.

- ✅ [FIBR-0120] **Data tables: drag-to-reorder columns, with the order persisted across sessions.**
  Extends the shared _table_state.remember_columns seam (FIBR-0117, which already
  saved/restored full header state incl. section order): enables setSectionsMovable
  on every table that calls it, so drag-reorder + persistence light up across all
  four data tables at once. Reordering is visual-only — the parallel-list row tag
  lives on logical column 0, so selection + sorting stay correct whatever the order.
  **Layman:** You can now drag a table's column headings to rearrange them (e.g. put Amount before Date), and the app remembers your arrangement next time — on the Transactions, Statements, Rules and Transfers tables.
  Kind: enhancement.
  Source: user-request-2026-07-12.

- 📋 [FIBR-0121] **Loan-account sign display: show debt-reducing amounts as positive on loan-type accounts.**
  Approach APPROVED by user (2026-07-13): DISPLAY-ONLY, display-time inversion for
  loan-type accounts (AccountType.HOME_LOAN / PERSONAL_LOAN). Keep amount_minor
  stored canonical (FIBR-0007: debit negative / credit positive) so the exact-money
  math, transfer detection, and the FIBR-0012 dashboard totals are all undisturbed;
  only the on-screen sign + direction colour flip for loan accounts. Scope is
  display-only for now (NOT changing how loan flows count in dashboard totals) — a
  deeper "interest-as-expense / repayment-as-transfer" semantic is a possible later
  follow-up.
    Needs its own spec + the project's 7-loop cold-eyes (correctness-critical money
  display). OPEN QUESTION to verify during that spec (do NOT assume): how the
  importer currently signs loan-statement debit/credit columns, and whether transfers
  INTO a loan are being detected at all (the loan-payment leg and its current-account
  leg may currently share a sign, which opposite-sign transfer matching would miss).
  If a real detection gap exists, split it out as a bug-fix. Touches ui/_amount.py +
  the Transactions table render; the account type is on models.Account.type.
  **Layman:** On home-loan / personal-loan accounts, your payments (which reduce what you owe) will read as positive/green and interest &amp; fees (which increase what you owe) as negative/red — the natural way round, instead of the current back-to-front look.
  Kind: feature.
  Source: user-request-2026-07-12 (approved 2026-07-13).

- ✅ [FIBR-0122] **Auto-update relaunch: stop the /bin/sh waiter inheriting the frozen app's bundled-library path.**
  Root cause (from update-relaunch.log): the relaunch /bin/sh waiter inherited the
  PyInstaller onefile app's LD_LIBRARY_PATH pointing at its private _MEI extraction
  dir, so the SYSTEM /bin/sh loaded the app's bundled libreadline.so.8 and died on a
  symbol lookup (rl_completion_rewrite_hook) BEFORE it could relaunch — the real cause
  of "closed but didn't reopen". Fix: _relaunch_env restores LD_LIBRARY_PATH / LD_PRELOAD
  to the pre-launch value PyInstaller preserves in <VAR>_ORIG (or drops them when there
  was none), so the waiter runs against system libraries; the exec'd AppImage sets up
  its own loader path. TDD: 2 unit tests (restore-from-ORIG + drop-when-absent). Ships
  in the next release. TWO-CYCLE CAVEAT: the *running* (old) version performs each
  relaunch, so 0.1.7→(this release) still needs one manual reopen; the update AFTER it
  is the true auto-relaunch test — same caveat as the earlier relaunch fixes (FIBR-0054).
  **Layman:** After an update the app should reopen itself; it was silently failing to. Fixed so the little helper that reopens it runs with the system's own libraries instead of the app's bundled ones.
  Kind: fix.
  Source: user-report-2026-07-13 (0.1.6→0.1.7 did not auto-relaunch).

- ✅ [FIBR-0123] **Group category pickers by Income/Expenditure type (disambiguate same-named categories).**
  The category pickers (Set-category dialog `ui/category_picker.py`, the Rules editor `ui/rules.py`, and the Transactions category filter) flatten the two-root Income/Expenditure category tree (FIBR-0006) into one flat combo, so: (1) you can't tell an income category from an expenditure one at pick time, and (2) two categories that share a name under different Type roots are indistinguishable — real dogfooding case 2026-07-13: the seeded income "Lottery" plus a user-added expenditure "Lottery" render as two identical rows. Fix: group each combo under non-selectable "Income" / "Expenditure" section headers (or an equivalent grouped/indented presentation) so the Type is obvious and same-named siblings are unambiguous. The category *manager* already shows the tree grouped; this is only the flat picker combos. Known-deferred shortcut, recorded at the FIBR-0010 close ("category selectors are flat combos, grouping deferred").
  **Layman:** When you pick a category, show which options are income and which are expenditure — and make two categories that share a name (e.g. an income "Lottery" for winnings and an expenditure "Lottery" for tickets) tell-apart-able instead of two identical rows.
  Kind: ux.
  Source: dogfooding-2026-07-13.
  Resolved (2026-07-13): shipped by TDD (6 slices) + 1 indie-review LOW fixed inline (parent-cycle guard). Grouped pickers/filter under Income/Expenditure headers, Name (Type) tag; audit 0, gate green. Tag FIBR-0123-complete.

- ✅ [FIBR-0136] **Add the missing Statements toolbar icon + button.**
  Statements shipped (FIBR-0052) text-only and absent from the toolbar — reachable only via the View menu, where it also lacked a glyph unlike its neighbours. Added ui/icons/statements.svg (Feather file-text style matching the icon set), wired it into _action_statements (was icon=None), and added the action to the toolbar after Transactions to mirror the workspace tab order. Reverses the FIBR-0052 "Statements not on the toolbar" test assertion by explicit user request; the statements/app_shell tests were updated (toolbar order now includes action_statements; a rendering-icon + toolbar-membership test added). Kind: fix.
  **Layman:** Give the Statements screen its own button with an icon in the toolbar (it was only reachable from the View menu before, and even there it had no icon).
  Kind: fix.
  Source: user-request-2026-07-14.
  Resolved (2026-07-14) — commit eb52443. statements.svg added, wired into _action_statements + the toolbar after Transactions; tests updated. Gate green 862/1.

- 💭 [FIBR-0137] **Business / Personal account grouping — separate views within one profile.**
  Today the model is one profile per logged-in user with a single, flat account list; every view (Home dashboard, Transactions, Accounts) spans all accounts at once. An external tester runs both business and personal accounts and wants to view each set separately WITHOUT a second profile/login.

  Investigate: (a) an account "group" attribute — fixed Business/Personal, or user-defined groups — as a nullable column on accounts (no migration pain, defaults ungrouped); (b) a group filter/toggle shared across Home, Transactions and Accounts (reuse the existing account-selector pattern in HomeView); (c) whether dashboard totals should roll up per-group; (d) how this interacts with the (planned) expandable dashboard and with transfer-detection across groups. Keep the single-profile design — this is a view/grouping concern, not multi-user.

  Source: user-request-2026-07-14 (friend / external tester).
  **Layman:** Let someone tag each account as Business or Personal (or custom groups) and view the two separately, so a person with both kinds of accounts keeps them apart while still staying under one login.
  Kind: investigate.
  Source: user-request-2026-07-14.

- ✅ [FIBR-0138] **Expandable dashboard drill-down (Income / Spending / Transfers → categories → merchant → transactions).**
  Designed in-session 2026-07-14 (three user-approved brainstorm decisions). Enhances the FIBR-0012 dashboard: keep the donut + 12-month trend charts as the snapshot, add an expanding tree below them that drills the numbers.
  Spec written (docs/specs/FIBR-0138.md) 2026-07-14; /cold-eyes next.
  Spec CLEARED FOR CODE 2026-07-14 — /cold-eyes converged loop 5 (5 loops × 3 cold lanes = 15 reviews; accuracy lane clean from loop 4). Next: TDD tests/features/dashboard_drilldown/ (INV-1..9) → /close-phase.
  Resolved (2026-07-14): SHIPPED (code) via /close-phase. TDD 41-leg tests/features/dashboard_drilldown/ (INV-1..9) → DrillNode/DrillLabels (models), merchant_name (text.py, pure+total), drill_rows_in_range (5-tuple sibling read), ReportingService.drill_down (one "group by top-of-chain" category algorithm + account-pair transfers, INV-7 uniform-string sort; branch totals sum from integer amount_minor so they equal the tiles, INV-1), HomeView QScrollArea+QTreeWidget wiring. Close: /audit semgrep 0 + gate 0; /indie-review 2 cold lanes → production money-correct, folded inline a top_of_chain/category_node corrupt-data cycle guard + 5 test-strength adds (real INV-7 mixed-type sort-key falsifier, INV-9 sentinel-label proof, cycle regression, count==1 bare label, punctuation merchant_name). Gate green 975/1, mypy 0. Commits 810283f (impl) + ebbcced (fold) + close; tag FIBR-0138-complete; journal docs/journal/FIBR-0138.md. README "what works today" refresh deferred to next bump per Deliverable 7.

  D1 Presentation: an expanding tree (QTreeWidget-style), NOT a click-to-drill donut. The three totals (Income / Spending / Transfers) are the top rows.
  D2 Spending/Income drill follows the existing category tree (parent->child, any depth) to a leaf category; at a leaf, group its transactions by merchant with a x count, then expand a merchant to the individual transactions (date + amount).
  D3 Merchant = "smart cleanup" of the free-text description (strip card numbers, branch/ref codes, trailing digits) to a best-guess shop name, grouped + counted. There is NO merchant field today (only transactions.description) - this is a new derivation. Fuzzy by nature; refine rules over time. Candidate reuse: the FIBR-0010 rule-engine description matching.
  D4 Transfers drill by account pair (from->to, x count), then the individual moves. Transfers have no categories (money between own accounts, excluded from income/spend totals).

  INV (correctness-critical): the merchant cleanup only affects DISPLAY GROUPING - every total/subtotal is summed from real amount_minor; cleanup can never change a number, only which line it sits under.

  Details: biggest-amount-first sort at every level (matches the donut); the period + account selectors drive the tree; magnitudes shown like the tiles. Needs a new ReportingService drill API + a merchant-normalisation helper. Spec -> /cold-eyes (--max-loops 7) -> TDD when scheduled; after the v0.1.10 release per the current plan.
  **Layman:** Click a total on the Home dashboard to open it up — Spending breaks into categories, each category into shops (with a count like "McDonald's ×3"), and each shop into the actual purchases; Transfers break down by which accounts the money moved between.
  Kind: enhancement.
  Lanes: reporting, ui.
  Source: user-request-2026-07-14.

- ✅ [FIBR-0139] **Built-in category library — smarter auto-categorise out of the box.**
  Fixes the cold-start: today auto-categorise only matches USER-written rules (FIBR-0010), so a fresh vault imports everything Uncategorised. Design (brainstorm-approved 2026-07-14):
  D1 Ship a bundled, per-release-updateable data file src/finbreak/data/category_library.json — list of {pattern, category} entries, SA-first (Pick n Pay/Checkers/Woolworths/Shoprite/Shell/Engen/Dis-Chem/Vodacom/MTN/Eskom...) + universal (Netflix/Spotify/Uber/Steam/Apple...), mapping to the v3-seeded default categories (Groceries/Transport/Bills & utilities/Entertainment/Medical/Salary/...). Travels like ui/icons (pyproject glob + PyInstaller --add-data). Missing/malformed file => empty library, app runs (fail-safe).
  D2 Matching order: user rules FIRST, then library. categorize() already substring-matches (contains, normalise_text-folded) — no wildcards. Manual pick always wins (golden rule INV-1 untouched).
  D3 New CategorySource.LIBRARY = 'library' — NO schema migration (category_source is free-text TEXT; auto_rows predicate 'IS NULL OR <> manual' already recomputes library rows). categorize/recategorize_auto_rows extended to return WHICH source matched so set_category stamps 'rule' vs 'library'.
  D4 Runs on the EXISTING paths — import auto-categorise + Rules-tab Apply — both now include the library. NO new button.
  D5 Settings toggle (default ON), reuse SettingsRepository (non-schema). Off => library not consulted; next apply/import reverts library rows to uncategorised.
  D6 Small '~ guess' tag beside library-guessed category in the Transactions table (Home is now the FIBR-0012/0138 dashboard with no per-row cell — superseded by spec D7); overridable.
  D7 Library binds category by NAME; a renamed default category => entries fall through to Uncategorised (never mis-filed). Structural binding is a future enhancement (out of scope).
  INV money-safety: only sets category, never reads/alters an amount; grand-book total + amount_minor multiset identical before+after (per-category sums change by design — see spec INV-1). Deps: FIBR-0010. Lanes: services, ui, repo, tests. Next: spec docs/specs/<id>.md -> /cold-eyes (max-loops 7) -> TDD.
  **Layman:** finbreak ships with a built-in list of common shops so imported transactions get sensible categories automatically, without you writing a rule for every merchant.
  Kind: feature.
  Source: user-request-2026-07-14.
  Active 2026-07-14 — brainstorm complete + user-approved (all decisions D1-D7 locked: bundled JSON library, user-rules-first, CategorySource.LIBRARY no-migration, existing import+Apply paths, Settings toggle default-ON, '~ guess' tag, rename falls through safely). NEXT: write spec docs/specs/FIBR-0139.md -> /cold-eyes (max-loops 7) -> TDD.
  Resolved (2026-07-14): SHIPPED by TDD. category_library.py (LibraryEntry, pure+total parse_library, fail-safe cached load_library, match_library) + data/category_library.json seed (every entry bound by name to a v3 DEFAULT_CATEGORIES leaf). CategorySource.LIBRARY (free-text column, no migration); categorize_with_library (rule beats library), _match_inputs (toggle-gated), _leaf_name_to_id (first-wins), library_enabled; recategorize_auto_rows + would_categorize rerouted. Settings toggle (default ON) wired through the shell; Transactions "~ guess" marker with every Category cell a bare-name SortableItem. data/*.json package-data + second --add-data pair in all three freeze sites; parity guard set-checks both targets. tests/features/category_library/ (INV-1..11) + autouse neutralise fixture + real_library marker. /audit (semgrep full) 0 actionable; /indie-review 2 cold lanes 0 CRIT/HIGH/MED, only LOW substring-precision (accepted D2 substring-only tradeoff, marked overridable guesses, money never touched). Gate green 934/1, mypy 0. Commit 24e7a91; tag FIBR-0139-complete; journal docs/journal/FIBR-0139.md. FIBR-0140 (learn-from-history) remains the deferred "later" half.

- 📋 [FIBR-0140] **Auto-categorise learns from your own history (statistical, no hand-written rule).**
  The 'later' half of the 2026-07-14 'both' decision (library now, learning later). Distinct from FIBR-0035 (offer-to-MAKE-a-rule, shipped) and FIBR-0092 (bulk re-categorize + rule preview): this auto-applies a category learned from the user's OWN past manual picks (merchant-keyed), ranked with/near the library, still overridable, manual always wins. Deps: the built-in category library item + FIBR-0010. Design TBD in its own brainstorm.
  **Layman:** Once you've categorised a shop by hand a few times, finbreak remembers and auto-applies that to future transactions from the same shop — without you writing a rule.
  Kind: enhancement.
  Source: user-request-2026-07-14.

- ✅ [FIBR-0142] **Recurring money detection (subscriptions + standing income).**
  Split from FIBR-0022 (the recurring half; budgets stay on FIBR-0022 as the follow-up). Auto-detect repeating money movements — recurring OUT (subscriptions, debit orders, insurance) and recurring IN (salary, standing deposits) — surface for confirm/dismiss. User-chosen scope (2026-07-15 brainstorm): both directions; "Balanced" sensitivity (seen 3+ times, amount within ~10% of the group median, gaps consistently in one cadence bucket — weekly/fortnightly/monthly/yearly with slack). Pure deterministic detect_recurring(rows, today) grouping on normalise_text(merchant_name(description)) x direction (reuses FIBR-0138 cleanup); excludes confirmed transfers; integer amount_minor throughout (INV-13). Persistence: new schema v9 recurring_decisions table keyed on (direction, merchant_key) — not txn ids — mirroring transfer_pairs. RecurringService shaped like TransferDetectionService (candidates/confirmed/confirm/dismiss/reset/summary). SURFACES: dedicated Recurring tab (Suggested/Confirmed tables mirroring Transfers) built now; the read-only Home dashboard card is DEFERRED until the dashboard-focus rework so it isn't added to a layout being decluttered. Deps: FIBR-0138 (merchant_name), FIBR-0011 (transfer exclusion), FIBR-0012 (dashboard).
  **Layman:** finbreak spots your regular payments and deposits — subscriptions, debit orders, salary — so you can see what's on autopilot and what it costs you each month.
  Kind: feature.
  Source: user-request-2026-07-01 (FIBR-0022 split) + brainstorm-2026-07-15.
  Resolved (2026-07-15): shipped by TDD (4 slices) — pure detect_recurring + schema v9 recurring_decisions + RecurringRepository/RecurringService + the Recurring tab (after Transfers). Closed by /close-phase: semgrep+bandit 0; 2 cold code-review lanes → 1 HIGH (fortnightly monthly-equivalent pre-divided factor defeated ROUND_HALF_EVEN) + 1 LOW (created_at reset on flip) + 3 test-strength adds, all folded inline. Gate green. Tag FIBR-0142-complete. Home dashboard card deferred to FIBR-0143.

- ✅ [FIBR-0143] **Rework the Home dashboard so the income/expenditure/transfers breakdown is the hero, charts secondary.**
  User feedback 2026-07-15 (with a screenshot): the current Home leads visually with the donut and the income-vs-spending BAR graph, while the FIBR-0138 drill-down breakdown (Income / Spending / Transfers -> category -> merchant -> txn) sits at the very bottom. The user's intended hero of the dashboard is that BREAKDOWN, not the graphs -- valuable information but the BIG feature is the breakdown. Especially de-emphasise the bar graph. Invert the layout: promote the expandable breakdown to the primary surface; keep the charts as smaller/secondary supporting detail. BLOCKED pending the user's own HTML mockup of the envisioned layout (they said they'll make one) -- do NOT redesign the layout before that lands. When it does: brainstorm-confirm against the mockup -> spec -> cold-eyes -> TDD. The deferred FIBR-0142 recurring Home-card slots into this reworked layout. Deps: FIBR-0012 (dashboard), FIBR-0138 (drill-down breakdown).
  **Layman:** Redesign the main screen so the plain-language breakdown of where your money went (and came from) is the star, with the pie and bar charts moved to a supporting role.
  Kind: ux.
  Evidence: /home/ants/Pictures/ClaudePaste/paste_20260715_085635_284_5e11f9ac.png
  Source: user-feedback-2026-07-15 (dashboard focus).
  UNBLOCKED 2026-07-15: user delivered the HTML mockup `/home/ants/Documents/dashboard_2.html` (+ annotated screenshot). Envisioned layout: three side-by-side columns — Expenditure / Income / Transfers — each with the existing pie chart on top, a bold coloured header + big total, then the expandable breakdown list (categories → merchant sub-rows, e.g. Groceries → Checkers/Sixty60, Spar); the monthly bar chart demoted to a full-width strip at the bottom ("2026 Monthly Trend Breakdown"). User notes: NO borders (those were alignment guides only), CONSISTENT row heights, reuse the existing pie chart (not the mockup's CSS one), add polish/flair. Next: brainstorm-confirm against the mockup → spec → cold-eyes → TDD. Also lands the deferred FIBR-0142 Home recurring card (consumes RecurringService.summary()). User gated this behind "if my weekly limit hasn't finished yet" (2026-07-15).
  Started 2026-07-16: design brainstormed + user-approved against the mockup (dashboard_2.html). Decisions: pies in all 3 columns (fed from the existing drill_down branch children — pie mirrors each column's breakdown list); keep Net as a slim full-width strip; include the deferred FIBR-0142 recurring Home card now. Layout: 3 side-by-side columns (Expenditure/Income/Transfers) each = pie → coloured header+total → expandable breakdown tree; Net strip; full-width Recurring card; monthly-trend bar demoted to a bottom strip. No schema/service-data change — all reuse (drill_down + summary + monthly_trend + RecurringService.summary). Spec docs/specs/FIBR-0143.md next → /cold-eyes (cap 7) → TDD.
  Spec CLEARED FOR CODE 2026-07-16 — /cold-eyes converged loop 7 (7 loops × 3 cold lanes = 21 reviews; loop 7 all-polish, 0 CRIT/HIGH/MED). Spec docs/specs/FIBR-0143.md written + 7-loop log. Key contract details settled across the loops: build_breakdown_donut does its own cap loop (no _donut_wedges extraction — donut stays byte-for-byte unchanged for the PDF export); each column's header+pie+list all source from the one drill_down branch node (summary feeds only the Net strip); explicit node→column map (Expenditure←nodes[1]/Spending, Income←nodes[0], Transfers←nodes[2]) so a naive zip can't mis-colour; recurring card is UNSCOPED by the Home selectors (summary(today) takes only today — shows all confirmed recurring money vault-wide); branch colour on header+tree only (pie is palette-coloured), gated on amount_prefs.colour; monthly_out is a positive magnitude so In/Out colours are forced-by-role. Commits d132c18→7238685, all pushed, gate green. NEXT: TDD tests/features/dashboard_focus/.
  Resolved (2026-07-16): shipped by TDD. build_breakdown_donut (own cap loop, palette, empty-safe; PDF donut byte-for-byte unchanged) + HomeView reworked into three columns (Expenditure/Income/Transfers, each pie+coloured header+drill tree) + slim Net strip + unscoped Recurring card + demoted trend strip; explicit node→column map; RecurringService wired into main_window (amount_prefs by keyword). New tests/features/dashboard_focus/ (INV-1..9, 20 legs) + rippled FIBR-0138/FIBR-0012 tests onto the new surfaces. Closed by /close-phase: semgrep 0; 2 cold review lanes → production clean (0 CRIT/HIGH/MED), 3 LOW test-strength adds folded inline. Gate green (1040 pytest, mypy 0). Commits 070cd76→6719de5. Tag FIBR-0143-complete.

- 📋 [FIBR-0144] **Centralise the schema-version drift guard to remove per-bump test churn.**
  Surfaced during the FIBR-0142 close. Every feature that ever added a migration hard-asserts `LATEST_SCHEMA_VERSION == N` (and encodes the version in test function names + spec.md INV lines), so each schema bump forces ~24 assertion edits + ~15 renames across ~9 feature suites (v8→v9 did exactly this). Replace the scattered per-feature guards with ONE canonical "latest schema version" test (assert the constant + that a fresh vault reaches it) and have each feature's migration test assert only its OWN delta (the intermediate step it introduced), never the moving global latest. Removes the churn and the drift risk. Low priority, no user-facing effect.
  **Layman:** A cleanup: right now every time the database format is upgraded, a bunch of unrelated tests have to be hand-edited. This would make that a one-line change instead.
  Kind: refactor.
  Source: in-session-2026-07-15 (FIBR-0142 review observation).

- 📋 [FIBR-0145] **Transfer detection learns from confirmed/rejected transfer pairs.**
  User feedback 2026-07-16 (general use of the shipped Transfers tab): confirming/rejecting a transfer should TEACH the detector, not just decide the one pair. Today FIBR-0011's `transfer_pairs` records a decision keyed on the two specific transaction ids, so an equivalent pair next month (same two accounts, same kind of description, same equal-magnitude/opposite-sign shape) is presented cold again. Enhancement: derive a reusable signal from each confirm/reject — keyed on something like (account_pair, direction, normalised description/merchant pattern) — so future candidate pairs that match a CONFIRMED pattern are auto-suggested or pre-confirmed, and pairs that match a REJECTED pattern are suppressed. Mirror the FIBR-0010 categorization-rules learning-from-manual-overrides design (a learned-rule table + a manual decision always winning + an overridable marker), applied to the transfer surface. Correctness guard: a learned auto-confirm must never merge money that isn't genuinely a transfer, so the learned pattern should stay conservative (exact account pair + tight amount/description match) and remain user-overridable. Deps: FIBR-0011 (transfer detection), pattern-reuse from FIBR-0010 (rules engine).
  **Layman:** When you confirm or reject that two transactions are the same money moving between your own accounts, the app should remember the pattern and get better at spotting (or ignoring) similar transfers next time — instead of re-asking about the same kind of pair every import.
  Kind: enhancement.
  Source: user-feedback-2026-07-16 (general use).

- ✅ [FIBR-0146] **PDF statement import fails every row with a raw "time data ... does not match format" date error.**
  Reported 2026-07-16 (external Windows tester, screenshot). Import preview: all 165 rows red, Status "Error", the Description column filled with the raw Python message "time data '20 ...' does not match format ...", Date/Amount blank, footer "0 new · 0 duplicate · 165 error". Root cause: the generic PDF importer (importers/pdf_importer.py) extracts the table then parses each date via the shared CSV path importers/csv_importer.py:74 datetime.strptime(row[date_column], mapping.date_format); on failure it appends RowError(row_number, str(exc)) (csv_importer.py:88-89), so the raw strptime message becomes the shown text. The applied mapping.date_format does not match this bank's date format — the failing values step through days 20,21,22,26,27,28,31,02,03 (a DD-first statement rolling over a month boundary), so a wrong/guessed format was applied (wrong profile matched, or the wizard's date-format guess/selection was wrong for an unrecognised bank). TWO fixes: (1) correctness — parse this bank's actual date format (needs the sample to know the exact string; may need a new mapping profile or a smarter date-format auto-detect / a clearer wizard affordance to pick it); (2) UX — a row-level failure should show a friendly "couldn't read the date in this row" not the raw str(ValueError), and a 100%-failure import should surface a "the date format didn't match — pick the right one / this bank isn't recognised yet" banner instead of 165 identical raw errors. Needs from the user: which bank, and the exact date format as printed (e.g. "20/07/2026" vs "20 Jul 2026" vs "2026-07-20"), ideally a redacted sample PDF, to reproduce-first then fix.
  **Layman:** A friend's Windows PDF statement imported with every single row marked "Error" (165 errors, 0 imported) — the app couldn't read the dates and showed a raw programmer error message instead of a helpful one.
  Kind: fix.
  Source: external-tester-2026-07-16.
  Progress (2026-07-16): started. Approach confirmed with user — auto-detect the statement's date format from the extracted date column, pre-select a plain-English format in a friendly picker (replacing the raw %-code box) with a live sample-date preview so a wrong guess is caught before import (never a silent wrong-day); fall back to the picker when genuinely ambiguous. Plus a friendly per-row date error and a whole-import \"date format didn't match\" banner. Spec → /cold-eyes (7-loop) → TDD next; reproducible via a synthetic day-first (DD/MM/YYYY, month-rollover) fixture without the tester's sample.
  Progress (2026-07-16, EOD): spec docs/specs/FIBR-0146.md written + run through /cold-eyes to the full project cap (7 loops × 3 cold lanes = 21 reviews). Core converged — accuracy lane clean loops 5–7, no remaining silent-wrong-day path loops 5–7; every CRITICAL/HIGH/MEDIUM/LOW fixed in-loop (notably: removed a plausible-year guard built on a false strptime claim, added dotted %m.%d.%Y to close a silent day-first read, and rejected the empty-format strptime(\"\",\"\")→1900-01-01 phantom-date trap at _validate_mapping). Spec Status = CLEARED FOR CODE. Paused for the night; NEXT = TDD (tests/features/import_date_detect/) per the spec's Deliverables + Test plan. 8 commits on main, all pushed.
  Resolved (2026-07-17): shipped by TDD. New pure importers/date_detect.py (detect_date_format + 15 ordered KNOWN_DATE_FORMATS, clock-free, no year guard — strptime separates 2/4-digit widths); friendly per-row RowError in csv_importer (D3); wizard date-format QComboBox + Custom… reveal + auto-detect + live preview + whole-import banner (D4-D8); _validate_mapping rejects the empty-format strptime("","")→1900-01-01 trap (D4). New tests/features/import_date_detect/ (spec.md + 39 tests, 4 layers). Close: /audit semgrep 0; 2 cold review lanes — Lane A (date/money) no reachable defects, Lane B 2 MEDIUM (unblocked matched-profile date-combo re-detect; missing PDF-path tests) + 2 LOW, all folded inline + re-verified. Gate green 1080/1, mypy 0. Tag FIBR-0146-complete.

- ✅ [FIBR-0148] **Deleting a statement silently loses transactions a still-present overlapping statement also covered.**
  Import dedup (services/import_.py `_dedup`, D6/INV-5) is a multiset delta:
  duplicates are DROPPED at import, never stored — the single stored copy is
  stamped to whichever statement imported it FIRST (`statement_period_id`, a
  single-valued column). `StatementService.delete_statement`
  (services/statements.py) deletes exactly that statement's stamped rows and does
  NO re-evaluation of other statements.
  Started 2026-07-17. Chose fix direction (a) ownership hand-off on delete: reassign transactions covered by a remaining overlapping statement to that statement, delete only truly-orphaned rows. Spec docs/specs/FIBR-0148.md.
  Resolved 2026-07-17. Fix direction (a) ownership hand-off shipped: delete_statement now hand_off_covered → delete-orphans → delete-period in one owned transaction; covered rows re-stamped to a remaining same-account statement (ORDER BY period_start,id), never NULL. Spec docs/specs/FIBR-0148.md cold-eyes-converged loop 3 (polish). TDD tests/features/statements/ INV-1..9 (reproduce-first). /audit semgrep 0; cold code-review no correctness defects, 1 LOW test-strength folded inline. Filed FIBR-0149 (confirm-dialog count overstatement, spec D5 follow-up). Gate green 1103/1. Commit d3f113b.

  Concrete data loss: statement A (Jan) imported, then overlapping statement B
  (Jan-Feb) imported — B's January rows are deduped away, only February inserted.
  Delete A -> the January transactions vanish, even though B is still present and
  legitimately covered January. B is not re-imported, so its rows are not
  restored; B now shows a coverage span with a silent hole. For a money app this
  is the unforgivable class (surfaced by a user question 2026-07-17).

  Fix directions (needs a decision — likely a spec + cold-eyes, correctness-
  critical):
    (a) Ownership hand-off on delete: before deleting a row, check whether another
        remaining statement of the same account covers its date (the span+NOT EXISTS
        logic the v6 backfill already uses); if so, REASSIGN its statement_period_id
        to that statement instead of deleting. Cheapest; delete only removes rows no
        remaining statement covers. Caveat: span-overlap is a proxy for "the other
        statement listed it" (true in practice — a statement lists all its period's
        rows).
    (b) Model change: store every imported row linked to its statement (many-to-many
        transaction<->statement), dedup at display/aggregation time. Most correct,
        biggest change.
    (c) Minimum viable: warn on delete when rows would be lost that another
        statement's span also covers, prompting a re-import.
  Kind: fix (data integrity).
  **Layman:** If two statements overlap and you delete one, the shared transactions vanish instead of staying under the statement you kept.
  Kind: fix.
  Source: user-question-2026-07-17.

- ✅ [FIBR-0149] **Delete-statement confirm dialog overstates the count when a statement overlaps another.**
  Surfaced by the FIBR-0148 cold code-review. After FIBR-0148, delete_statement
  hands off transactions a remaining overlapping statement also covers (they
  survive), but ui/statements.py's confirm dialog still says "Delete this
  statement and its %n transaction(s)? This cannot be undone." with %n =
  statement.transaction_count (the FULL linked count). In an overlap delete the
  true deleted count is lower (often 0), so "cannot be undone" + an inflated
  count could scare a user into cancelling a delete they wanted. FIBR-0148 D5
  deliberately deferred this as a follow-up (revisit if users find the count
  confusing). Fix direction: compute the would-orphan count up front (a dry-run
  of the hand-off's NOT-covered set) and word the dialog as "delete this
  statement (N of M transactions will be removed; the rest stay under an
  overlapping statement)"; add the overlap-path confirmation test the review
  noted is currently missing (test_INV10a only covers the non-overlap case).
  **Layman:** When you delete a statement that shares transactions with another one you keep, the "delete its N transactions? This cannot be undone" prompt still counts all N — even though the shared ones now survive under the other statement. The warning should reflect how many actually go.
  Kind: ux.
  Source: indie-review-2026-07-17 (FIBR-0148 close, lane finding LOW).
  Progress (2026-07-18): starting — reproduce-first TDD. Fix: add TransactionRepository.delete_split_counts + StatementService.delete_preview (mirrors CategoryService.delete_blast_radius; UI calls service not repo), branch the confirm dialog so the overlap case names the ACTUAL removed count + reassures the shared rows stay. New overlap-path confirm test (INV-10a only covers non-overlap).
  Resolved (2026-07-18): the confirm dialog now names the ACTUAL removed count on an overlap delete. New TransactionRepository.delete_split_counts -> (removed, kept) reuses hand_off_covered's EXISTS coverage guard byte-for-byte (preview can never disagree with the delete); surfaced via StatementService.delete_preview (UI→service, never repo, mirroring CategoryService.delete_blast_radius). ui/statements.py _on_delete branches: overlap (kept>0) → "%n of its transaction(s) will be permanently removed — the rest are shared with an overlapping statement and will stay"; non-overlap keeps the original wording (now from the fresh count). VaultLockedError-guarded. Reproduce-first TDD: INV-10c (full-overlap A/B, removed==0) fails pre-fix ("its 2 transactions… cannot be undone"), green after. Self-review (too small for /indie-review, per the FIBR-0141 precedent) + gate green 1104/1, mypy 0. Commit 10ee1db.
  Extended, not replaced, by FIBR-0201 (2026-08-03): the preview-wording
  contract now covers the BATCH form. `delete_preview` is the batch-of-one
  case of a new `delete_preview_many`, with its signature and result
  unchanged. The invariant that the preview and the delete share their
  coverage predicate byte-for-byte survives, and is now MECHANICAL rather
  than eye-checked: four inline literals could be compared by reading, but
  once each carries an N-placeholder run they cannot, so all four sites
  interpolate one `_coverage_where_sql` and a test asserts the fragment
  appears twice in each emitted statement. The batch's own trap is that
  SUMMING per-statement previews reports 0 removed for a delete that
  destroys transactions (measured) — one batch-aware call answers it.

- ✅ [FIBR-0151] **Confirmed transfers are not reflected on the Transactions tab.**
  Reported 2026-07-18 with screenshots. In the Transfers tab, the "Confirmed
  transfers" list shows approved transfers (status bar: "Confirmed 1 transfer(s).").
  But on the Transactions tab those same legs (e.g. "Ib transfer to *****9000740
  16H26 *****5235" on Market Link, and the paired Credit Card leg) still appear as
  normal transactions with no transfer marker and (in the shots) a blank Category —
  i.e. confirming a transfer in FIBR-0011's suggest-then-confirm flow does not
  propagate to how the Transactions view renders/labels those rows.
  Root-cause (2026-07-18, subagent-verified): MISSING-WIRING gap, not a
  regression. Confirm correctly records ONE `transfer_pairs` row
  (status='confirmed') via TransferRepository.add_decision
  (repositories/transfers.py:76-80); the `transfer_pairs` table is separate
  (migrations.py:270-277, v7->v8) with NO is_transfer/transfer_id column on
  `transactions`. FIBR-0011 INV-12 ("Transactions untouched",
  docs/specs/FIBR-0011.md:66) DELIBERATELY leaves the transaction rows
  byte-identical on confirm. The Transactions tab
  (TransactionService.list_transactions services/transactions.py:111-125;
  ui/transactions.py refresh:166 + render 223-311) reads only
  transactions/categories/accounts and has ZERO lookup against transfer_pairs or
  the existing `confirmed_transfer_txn_ids()` primitive (FIBR-0011 INV-5) -> the
  two legs keep their blank category and no marker.
  Resolved (2026-07-19): read-time fix. TransactionsView now composes a TransferDetectionService over the same vault and, in refresh(), builds a {txn_id: label} map from confirmed_transfers(); _category_cell shows the directional counterparty label ("Transfer to <credit account>" for the debit leg, "Transfer from <debit account>" for the credit leg). list_transactions() untouched (no tuple-shape change); INV-12 preserved (no transactions row read/mutated). Design chosen by user: directional counterparty naming (not a flat "Transfer" label). Reproduce-first: 2 qtbot tests in tests/features/transfers/test_transfers.py; new contract = transfers spec INV-13. Gate green 1128 passed. Commit 5af8ee6.

  DESIGN DECISION NEEDED before coding (no spec defines how a confirmed transfer
  should render on the tab): options = (a) a "Transfer" pseudo-category / label
  surfaced at READ time by threading confirmed_transfer_txn_ids() into
  list_transactions (must NOT mutate transaction rows -> preserves FIBR-0011
  INV-12); (b) a separate badge/indicator column; (c) exclude transfer legs from
  the tab. Recommend (a) read-time label. Fix stays read/render-side only.

  Reproduce-first: service-level test in tests/features/transfers/test_transfers.py
  -> confirm a transfer, call TransactionService.list_transactions(), assert each
  leg is marked/labelled as a transfer (fails today). Prefer over a GUI test.

  Note: the "Transactions tab" is specced as FIBR-0012 / FIBR-0139, not FIBR-0109.

  Depends-on / relates to FIBR-0011 (transfer detection, shipped) and FIBR-0109
  (dedicated Transactions tab). Reproduce-first: confirm a suggested transfer, then
  assert the two legs are shown as a linked/marked transfer (or excluded/annotated)
  on the Transactions tab. Investigate whether confirm writes the transfer link in
  the DB but the Transactions query/view ignores it, or whether the view needs a
  refresh/signal after confirm.
  **Layman:** When you approve a transfer in the Transfers screen, the two matching transactions still show up as ordinary, uncategorised entries on the Transactions list instead of being marked as a transfer.
  Kind: fix.
  Source: user-report-2026-07-18 (screenshots).

- ✅ [FIBR-0153] **Amount column: show the currency symbol ("R 1,234.49"), not the ISO code, plus a separate Currency column.**
  Current display renders "ZAR1,234.49" — the ISO code is passed as the currency *symbol* to QLocale().toCurrencyString in _format_amount (ui/_amount.py:24; symbol = base_currency() returns the ISO code "ZAR", ui/transactions.py:253), and there is no space. User request (2026-07-19): (a) show the amount with the proper symbol + a space — "R 1,234.49" for ZAR; (b) move the ISO code into its own dedicated "Currency" column on the transactions table. Work: map ISO code -> symbol (ZAR->R) with a space in _format_amount (decide symbol source — a small ISO->symbol table or a QLocale currency-symbol lookup for the base currency); add a Currency column (shifts the _COL_* constants). Also audit the Home tab / charts / PDF export for the same ISO-as-symbol rendering so the fix is consistent app-wide. Interaction: FIBR-0032's "Copy amount" reads the rendered Amount cell text, so it auto-follows the new format (no rework). Needs its own spec -> /cold-eyes -> reproduce-first TDD. Relates to FIBR-0105 (amount display prefs).
  **Layman:** Money currently shows as "ZAR1,234.49", which is hard to read — this makes it show as "R 1,234.49" and puts the "ZAR" code in its own tidy Currency column.
  Kind: fix.
  Lanes: ui.
  Source: user-request-2026-07-19.
  Resolved (2026-07-20, autonomous run): shipped. _format_amount now maps the base-currency ISO code to a symbol via a single-homed CURRENCY_SYMBOLS map (beside CURRENCY_EXPONENTS in services/auth.py) and composes "<symbol> <magnitude>" with one space — "R 1,234.49" not "ZAR1,234.49" — fixing every money site app-wide (Transactions, Home tiles, PDF export) through the one formatter. Magnitude uses QLocale().toString(x,"f",decimals) (symbol-free/grouped/locale-correct), NOT toCurrencyString(v,"") which leaks the ISO code in non-C locales (caught empirically in cold-eyes loop 2). Transactions table gains a dedicated Currency column (_COL_CURRENCY=2, shifting Description/Account/Category to 3/4/5); Copy amount auto-follows. Spec docs/specs/FIBR-0153.md cold-eyes converged loop 5 (CRITICAL mechanism bug caught + fixed). INV-1..9 tested (en_US + en_ZA locale legs; stale 5-col saved-layout safe). Full gate green (1173 passed, 2 skipped). commit 4132649; tag FIBR-0153-complete.

- ✅ [FIBR-0154] **Category UI: expose a 3rd tier (sub-categories) — Type → Category → Sub-category.**
  User asked for 3-tier categories (e.g. Expenditure > Groceries > Spar). Today the app is capped at TWO levels (Type > Category).
  Resolved (2026-07-21): 3rd category tier UI shipped. Spec cold-eyes CONVERGED loop 8 (verify, both cold lanes clean). Reproduce-first TDD: 17 RED INV-1..7 tests → implemented 6 source files (recursive 3-deep render; Add anchored to tree selection with UI depth cap; subject-aware "Move under…" re-parent; breadcrumb pickers via new sub_category_parent_names() map). Service & schema unchanged (cap is UI-only). Gate green 1235 passed; tag FIBR-0154-complete, commit 35131cd.

  Already supported (no work): the data model is a self-referencing tree with no depth cap — `parent_id INTEGER REFERENCES categories(id)` (migrations.py:117-120), `Category.parent_id: int | None` (models.py:230-242); FIBR-0006 shipped it "3rd level ready, no migration needed". `CategoryService.add_category` -> `_require_parent` only checks the parent EXISTS (not that it is a root), with `_reject_cycle` guarding acyclicity (services/categories.py:41-48, 106-116, 118-139) — so the service layer already permits a grandchild. Renaming a leaf (Spar -> Pick 'n Pay) also works today via `update_category` (services/categories.py:50-65) + the Update button (ui/categories.py:125-140).

  The gap is UI-only, deliberately deferred as "D9": the module docstring says "The UI exposes two levels (Type -> Category); a third (sub-category) level is a later enhancement (D9)" (ui/categories.py:9-10). `CategoriesWidget._refresh` renders only root -> one level of children and Add always parents onto the root Type combo (ui/categories.py:212-229, :116) — no control to pick a leaf as parent.

  Scope for this item: (1) CategoriesWidget — allow picking an existing Category as parent and render a 3-deep tree; (2) the category pickers that flatten the tree (Set-category dialog ui/category_picker.py, Rules editor ui/rules.py, Transactions category filter) must render/resolve the deeper level — note the existing flat-combo ambiguity already roadmapped separately; (3) spec -> cold-eyes -> TDD. Decide a max depth (2 vs 3 vs arbitrary) — the model allows arbitrary, but a UI/UX cap keeps the tree legible.
  **Layman:** Let you add a third level under a category (e.g. Expenditure › Groceries › Spar) and pick it when tagging transactions. Note: renaming a category (e.g. correcting "Spar" to "Pick 'n Pay") already works today — this item is only about adding the deeper third level.
  Kind: feature.
  Lanes: ui, services.
  Source: user-request-2026-07-19.

- ✅ [FIBR-0156] **Menu bar: add a "Report an Issue" item to the right of Donate that lets users log an app issue.**
  User wants a menu-bar entry to the RIGHT of Donate for logging an issue with the app. Anchor: the menu bar is File · View · Window · Help · Donate (main_window.py:4); Donate's actions open URLs via self._open_url(...) + QDesktopServices (main_window.py:32, :360-376), mirroring the .github/FUNDING.yml donate-URL pattern.
  Resolved (2026-07-21): shipped a single top-level "Report an Issue" menu-bar action to the right of Donate, opening REPORT_ISSUE_URL (https://github.com/milnet01/finbreak/issues/new) in the OS browser via _open_url — a user-initiated egress, not an app fetch (security-model INV-8), mirroring the Donate pattern. Chose the single-action form (no submenu, no version/OS pre-fill) per shortest-correct; pre-fill remains an easy follow-up. Covered by INV-8b (test_INV8b_report_issue_opens_url); action_report_issue added to the INV-1 canonical set. Gate green (1236 passed). Tagged FIBR-0156-complete.

  Design (for the spec): a new top-level "Report an Issue" menu-bar item positioned after Donate, opening the public repo's issue page (https://github.com/milnet01/finbreak/issues/new) in the user's browser via self._open_url — privacy-preserving and consistent with the local-only model + security-model INV-8 (opening a URL in the browser is NOT app network access, exactly like Donate). Decide: single top-level action vs a small menu ("Report a bug" / "Request a feature" → issues/new?template=...); optionally pre-fill the issue body with __version__ + OS via URL query (?title=&body=&labels=) — no sensitive data. Keep the URL as a module constant near the DONATE_* constants. Needs: spec (tiny) → cold-eyes (self-read; a one-menu-item feature test, not a multi-file design doc) → reproduce-first TDD (mirror the Donate action tests) → close.
  **Layman:** Add a "Report an Issue" button next to "Donate" in the top menu so users can quickly report a bug or request a feature — it opens the project's issue page in their browser (no data leaves the app).
  Kind: feature.
  Lanes: ui.
  Source: user-request-2026-07-21.

- ✅ [FIBR-0171] **Cash-flow forecast — project account balances forward from detected recurring income and expenses.**
  Turns finbreak from backward-looking (what did I spend?) into forward-looking (can I afford this?). Reuses the shipped recurring-money detection (FIBR-0142): take the confirmed recurring income + expenses, roll them forward from today's balance, and draw a projected-balance line to a chosen horizon (month-end / N days). Highest value-per-line-of-code of this batch because the detection engine already exists.
  **Layman:** Shows where your balance is heading — e.g. "you'll have about R X left by month-end" — based on your regular income and bills.
  Kind: feature.
  Source: in-session-2026-07-23.
  Started 2026-07-24 (self-directed, user delegated the pick). Design: vault-wide cash-flow forecast reusing RecurringService.confirmed() — net-flow projection by default, upgrades to an absolute projected-balance line when the user enters an optional 'current balance as of today' anchor (stored as a vault setting, shown with its as-of date so a stale anchor is never mistaken for fact). New Forecast tab: projected line chart + upcoming-events list + horizon picker. Pure integer-minor projection core. Spec next → /cold-eyes (max-loops 7) → TDD.
  Shipped 2026-07-24 (TDD). Schema v11 persists each statement's closing balance (statement_periods.closing_balance_minor); the forecast anchors to the sum of per-account balances brought current to today with real post-statement transactions (sum_after, half-open (period_end, today]), then projects the confirmed recurring set forward to a chosen horizon (End-of-month/30/60/90) via the pure Decimal-free project_forecast (reuses _add_cadence). NET_FLOW fallback (line from 0) when no account has a recorded balance. New Forecast tab after Recurring. INV-1..13 green; gate green.

- ✅ [FIBR-0172] **Spending alerts — flag unusual spend, a newly-appeared recurring charge, or a missed expected debit.**
  A notice layer on top of recurring detection (FIBR-0142) + category history: (a) new recurring charge detected this period, (b) a category's spend is N× its rolling average, (c) an expected recurring debit did not post. Non-intrusive surfacing (dashboard banner / list), user-dismissable. Pairs naturally with the cash-flow forecast.
  **Layman:** Quiet nudges when something changes: a new subscription starts, one category spikes well above normal, or an expected payment didn't arrive.
  Kind: feature.
  Source: in-session-2026-07-23.
  Resolved 2026-07-24 (self-directed autonomous run). Three dismissable Home-dashboard alerts: (a) new recurring OUT charge (suggested stream, occurrences<=4 — cadence-agnostic "just detected"); (b) category spike (last COMPLETE month >= 2x prior-3-month integer average, confirmed-transfer + None-bucket excluded so totals match the donut); (c) missed expected debit (confirmed OUT overdue past next_expected+3d). Pure integer-only detectors + AlertService (sole Decimal->minor in input prep); new v12 alert_dismissals table (recurring_decisions idiom), persisted per-scope dismissal keys; non-intrusive AlertsCard (hidden when empty, VaultLockedError-silent dismiss, card-local rebuild). Spec docs/specs/FIBR-0172.md cold-eyes CONVERGED loop 3 (caught + fixed a monthly-detector-dead boundary hole, a snapshot.confirmed AttributeError, an INV-15 Decimal leak, and a cross-feature v12 drift-guard conflict). Reproduce-first TDD tests/features/spending_alerts/ (32 tests +1 folded, INV-1..19); /audit semgrep 0 + cold code-review 0 defects; gate green 1360 passed. Schema 11->12 rippled 12 feature guard files + reworked the FIBR-0177 reconciliation guard. Journal docs/journal/FIBR-0172.md.

- 📋 [FIBR-0173] **Savings goals — track progress toward a target amount, distinct from spending budgets.**
  Budgets cap spending; goals build toward a target — a separate concept from the planned Budgets item (FIBR-0022). Per-goal: name, target amount, optional target date, current progress (linked account balance or manual contributions), and an on-track / behind indicator.
  **Layman:** Set a target like "R10,000 holiday fund" and watch a progress bar fill as you save toward it.
  Kind: feature.
  Source: in-session-2026-07-23.

- 📋 [FIBR-0174] **Tax-year summary — per-category totals for a chosen tax year with a tax-deductible flag, exportable to PDF/CSV.**
  Adds a "tax-deductible" flag to categories and a tax-year report view (configurable year boundary for the SA Mar–Feb tax year). Reuses the existing PDF (services/pdf_export.py) and the planned plain-data CSV export (FIBR-0093). Locally useful given the SA bank focus.
  **Layman:** A one-click annual report of what you earned and spent per category for a tax year, with deductible categories flagged — ready for filing.
  Kind: feature.
  Source: in-session-2026-07-23.

- 📋 [FIBR-0175] **Compare periods on the dashboard — this month vs last, this year vs last year, side by side.**
  The dashboard shows one period at a time (FIBR-0143). Add a compare toggle that renders a second period alongside the current one with per-category deltas (up/down arrows + amount/percent). Small addition to the existing reporting aggregation for a big 'aha'.
  **Layman:** See two periods next to each other so you can spot what went up or down.
  Kind: feature.
  Source: in-session-2026-07-23.

- 📋 [FIBR-0176] **Receipt attachments — attach a photo/PDF of a receipt to a transaction, stored inside the encrypted vault.**
  Store attachment blobs inside the SQLCipher vault (not on disk) so they inherit the same at-rest encryption as transactions. Needs a size cap (reuse the INV-5b resource-size cap pattern) and a schema/migration for an attachments table. Fits the privacy-first, everything-encrypted design.
  **Layman:** Keep a picture of a receipt with its transaction, encrypted like everything else.
  Kind: feature.
  Source: in-session-2026-07-23.

- ✅ [FIBR-0177] **Account-level balance reconciliation — verify imported transactions sum to the bank's stated balance for every account.**
  Generalises the Standard Bank import-time reconciliation (importers/standard_bank.py: opening ± total vs closing) into a visible, ongoing account-level check: opening balance + running sum of transactions vs the latest known statement balance, surfaced as ✓ / off-by-R-X. Catches import gaps for every account and every bank, complementing the planned statement coverage/gap detection (FIBR-0038) and running-balance work (FIBR-0094).
  **Layman:** A tick that confirms your imported transactions add up to the balance your bank states — or flags the gap — for any account, not just at import time.
  Kind: feature.
  Source: in-session-2026-07-23.
  Started 2026-07-24 (self-directed autonomous run). Spec docs/specs/FIBR-0177.md drafted: v1 reconciles current+savings cash accounts only (debt/investment/other deferred — persisted closing sign convention is canonical only for asset accounts); cross-statement telescoping over persisted closing balances (C_prev + sum_after(P_prev,P_curr] == C_curr, exact), reusing FIBR-0171 primitives; Accounts-tab per-account marker; no schema change. Next: /cold-eyes.
  Resolved 2026-07-24 (self-directed autonomous run). v1 reconciles current+savings cash accounts via cross-statement telescoping over persisted closing balances (C_prev + sum_after(P_prev,P_curr] == C_curr, exact integer minor units); debt/investment/other quietly NOT_SUPPORTED (deferred v2 — their persisted closing sign convention differs). Accounts-tab per-account marker. No schema change. Spec docs/specs/FIBR-0177.md cold-eyes CONVERGED loop 3; reproduce-first TDD tests/features/reconciliation/ (20 tests, INV-1..12); /audit semgrep 0 + cold code-review 0 defects; gate green 1327 passed. Surfaced + filed FIBR-0179 (forecast anchor debt-account sign bug). Journal docs/journal/FIBR-0177.md.

- 📋 [FIBR-0178] **Cash-flow forecast v2 follow-ups (FIBR-0171 D12, logged not dropped).**
  Deferred out of the FIBR-0171 v1 cash-flow forecast (spec D12),
  logged so they are not lost: (a) a user-typed manual balance
  override for balance-less accounts (CSV-only), so those accounts can
  contribute to the anchor without waiting for a balance-bearing
  statement; (b) per-account (rather than vault-wide) forecasts;
  (c) scenario / what-if one-off inputs (a known future cost the
  recurring engine won't model); (d) a CSV balance-column mapping so a
  CSV import can persist a closing balance too. Multi-currency forecasts
  stay out of scope and are tracked by FIBR-0087.
  **Layman:** Optional extras for the new Forecast tab, deferred from v1.
  Kind: feature.
  Source: FIBR-0171 spec D12 (in-session 2026-07-24).

- ✅ [FIBR-0179] **Forecast anchor mishandles debt-account (credit-card / loan) closing balances — wrong-sign roll-forward + an owed figure folded into the vault-wide cash total.**
  ForecastService._anchor (services/forecast.py) sums
  latest_closing_balances() across ALL account types with
  `current = balance_minor + roll_minor` (a plain `+`, no type dispatch).
  But a debt product's persisted closing_balance_minor is stored in the
  "owed" convention (positive = debt, as the statement prints it), the
  OPPOSITE sign to the canonical amount_minor (debit −/credit +). So for a
  credit-card / home-loan / personal-loan account the `+ roll_minor`
  brings the balance current in the WRONG direction, AND the owed figure
  is folded into a vault-wide "cash" total as if it were an asset (doubly
  wrong). Reachable: Family C credit-card statements always persist a
  closing (the SB checksum raises on a missing closing for non-savings
  families), so a credit-card account contributes to the anchor. Verify
  first (write a failing forecast test with a credit_card account + a
  post-statement transaction) then fix — likely by canonicalising the
  closing per AccountType, or by excluding debt/investment accounts from
  the anchor. Related: FIBR-0177 sidesteps this by scoping reconciliation
  to current+savings; the loan display-inversion roadmap note keeps
  amount_minor canonical while inverting only at display.
  **Layman:** The new Forecast's starting balance can be wrong for credit-card and loan accounts — it needs a per-account-type sign fix (or to leave debt accounts out of the total).
  Kind: fix.
  Source: in-session-2026-07-24 (surfaced by FIBR-0177 cold-eyes, spec D9).
  Resolved (2026-07-25): verified first — a RED test proved a
  credit-card account with a persisted closing balance (R1200 owed)
  was anchored as +R1200 of *cash*, and a post-statement purchase
  rolled it the wrong way. Fixed by narrowing the anchor to CASH_TYPES
  (current + savings) in ForecastService._anchor — the same gate
  FIBR-0177 D1 applies, for the same sign-convention reason. Debt /
  investment / other accounts now contribute nothing; a vault whose
  only balance-bearing account is a debt account falls back to
  NET_FLOW. The Forecast tab's provenance line gained a second
  exclusion clause so a type-excluded account is no longer mislabelled
  "no recorded balance yet". Contract: tests/features/forecast/spec.md
  INV-14 (3 new tests); FIBR-0171 §D1 carries an amendment note. Gate
  green 1363 passed, 2 skipped.

- ✅ [FIBR-0185] **Move the Home alerts card behind an Alerts button + dialog, so alerts never reflow the dashboard.**
  Verified 2026-07-28 from a user screenshot: the alerts card renders inline at
  the TOP of the Home dashboard, above the period picker. With 4 alerts it
  occupies ~120px and pushes the whole dashboard (period picker, Net line, the
  three donut columns, Spending/Income/Transfers panes, the recurring card, the
  trend chart) down the page. Dismissing one alert pulls everything back up. So
  the dashboard's vertical layout is a function of how many alerts happen to be
  open — the thing the user is reading moves under them as they read it.
  Resolved 2026-07-28. The inline alerts card is gone from the Home
  dashboard; alerts now sit behind an "Alerts (N)" button on the selector
  row, which opens a new AlertsDialog (src/finbreak/ui/alerts_dialog.py)
  listing every open alert with its per-alert dismiss control. The FIBR-0172
  alert model, detectors and dismissal store are untouched — the rows and the
  VaultLockedError-silent dismiss handler moved out of HomeView verbatim.
  Button states are theme-driven, not hard-coded: ThemeTokens grew a ninth
  `attention` token (dark on the three light themes, light on the three dark
  ones, so it reads against each window), and build_stylesheet fills
  QPushButton#alerts_button with it — with a separate :disabled rule so "no
  alerts" sits quietly. The dialog opens through the shell's tracked
  _open_dialog(defer=False) path (auto-lock tears it down) and emits `changed`
  after each dismiss, which the shell routes to HomeView.refresh_alerts() so
  the count stays live. Net effect: the dashboard's top row is fixed-height
  whatever the alert count. Tests: tests/features/spending_alerts/
  test_alerts_ui.py (9 legs, replacing test_alerts_card.py) + a theme leg
  pinning the attention token's light/dark posture and the button's QSS.

  User's chosen design (they weighed the alternative and rejected it): NOT a
  separate Alerts tab — a tab is easy to never open, and would need its own
  attention-drawing mechanism anyway. Instead an **Alerts button** on the Home
  header row that opens an **Alerts dialog** listing every open alert with its
  per-alert dismiss control (the same dismissals that already persist, FIBR-0172).

  Button states:
    - alerts outstanding → an attention colour DRAWN FROM THE ACTIVE THEME (six
      themes ship; no hard-coded red — each theme needs a legible attention/danger
      role, and the light themes need a different value from the dark ones).
    - none outstanding → disabled, styled to sit quietly in the theme.
  A count on the face ("Alerts (4)") is the cheap way to make the state readable
  without opening it.

  Net effect: the dashboard's top row becomes fixed-height whatever the alert
  count, which is the actual complaint. Pairs with the fixed-size work below,
  and largely subsumes it — alerts are the only element on Home whose height
  varies with data.

  Reuse: the alert model, detectors and dismissal persistence all shipped with
  FIBR-0172; this is a presentation change, not new alert logic. The dialog
  should go through the shell's tracked _open_dialog path (auto-lock tears
  dialogs down — INV-9), not exec().
  **Layman:** Alerts move into a button that opens a list. The button lights up when something needs attention, so the dashboard below it stops jumping around every time an alert appears or is dismissed.
  Kind: ux.
  Source: user-request-2026-07-28 (screenshot).

- ✅ [FIBR-0186] **Give the Home dashboard a fixed layout that scrolls when the window is too small, instead of reflowing.**
  User request 2026-07-28, alongside the Alerts-button item above: "Set a fixed
  size for everything on the dashboard so that if someone makes the window too
  small, it means they will have to scroll to see everything."
  Decision (2026-07-28, user): take the MINIMUM-size + QScrollArea route, not
  literal per-widget fixed pixel sizes. Same user-visible behaviour (the layout
  stops squashing; a too-small window scrolls) without clipping text for anyone
  running larger system fonts or display scaling. This closes the design note
  above — build it that way.
  Resolved 2026-07-28. As decided, the minimum-size + QScrollArea route, not
  literal per-widget fixed sizes. The scroll area already existed (FIBR-0012
  D1) with no floor under it, so the only change was a floor:
  `dashboard_content` (the scrolled content widget) now carries
  setMinimumSize(880, 620). Below that the viewport scrolls instead of
  squashing the three donut columns into slivers; above it the layout is still
  free to grow, so larger system fonts / display scaling widen rather than
  clip. The floor is on the content only — HomeView's own minimumSizeHint
  stays small, so the window is never pinned open. Tests:
  tests/features/dashboard/test_min_size.py (3 legs; verified
  discriminating — two fail with the setMinimumSize line removed).

  DESIGN NOTE — recommend implementing this as a MINIMUM size plus a scroll area,
  not as hard-coded pixel sizes on each widget. Same user-visible behaviour (the
  layout stops squashing; a too-small window scrolls), but:
    - setFixedSize on text-bearing widgets CLIPS rather than scrolls when the user
      runs a larger system font or a HiDPI scale factor — an accessibility
      regression, and finbreak already ships "Follow system" theming, so honouring
      system display settings is the established posture;
    - a minimum size is one property per pane instead of a width AND height per
      widget, and it cannot drift out of sync with the content it wraps.
  The concrete shape: wrap Home's content in a QScrollArea with
  setWidgetResizable(True), give the content widget a sensible minimum width and
  height, and let the existing layouts do the rest. Scrollbars appear only when
  the window is smaller than that minimum.

  Sequencing: land the Alerts button FIRST. Alerts are the only Home element whose
  height varies with data, so that change removes most of the observed movement
  on its own, and it will be clearer afterwards how much of this item is still
  needed — possibly only the scroll area.

  Test posture: qtbot legs asserting the content keeps its minimum size when the
  window is shrunk below it, and that the scroll area becomes scrollable rather
  than the panes shrinking. Per qtbot-visibility notes, probe with isHidden()
  rather than isVisible() for widgets on a non-current page.
  **Layman:** The dashboard keeps its shape no matter the window size — make the window small and you scroll to see the rest, rather than everything squashing and rearranging.
  Kind: ux.
  Source: user-request-2026-07-28 (screenshot).

- ✅ [FIBR-0187] **The Import-statement preview table forgets its column widths between imports.**
  Verified 2026-07-28 (user screenshot + source read). The import preview table is
  built at src/finbreak/ui/import_wizard.py:272 as a plain QTableWidget(0, 5) with
  setHorizontalHeaderLabels — and never calls remember_columns(), the helper in
  src/finbreak/ui/_table_state.py that every other table uses (transactions.py,
  recurring.py, statements.py, transfers.py, rules.py all import it). It also has
  no objectName, which remember_columns needs as its settings key
  ("columns/<objectName>").
  Resolved (2026-07-28): SHIPPED by TDD. The preview table was the one table built without remember_columns. Gave it objectName "import_preview_table" (the helper keys saved state on it; unnamed would share the empty "columns/" key and cross-corrupt the other tables) and called the existing helper — no new code. Columns are now drag-reorderable too, from the same call. 2 new tests, both failing before. Gate: 1401 passed.

  So this is a missed call-site, not missing capability: remember_columns already
  restores widths + column order + sort on construction and re-saves on every
  resize/reorder/sort, keyed by objectName in the window INI. The fix is to give
  the preview table an objectName and call remember_columns on it — rule-of-reuse
  case (a), call the existing helper directly, no new code.

  Side benefit, worth noting because it is the same one line: remember_columns
  also sets setSectionsMovable(True), so the preview's columns become
  drag-reorderable like the rest of the app's tables.

  Reproduce-first: a qtbot leg that widens a preview column, rebuilds the wizard,
  and asserts the width survived — mirroring whatever the existing table_state
  suite (tests/features/table_state/) already does for the shipped tables, which
  is the pattern to copy rather than invent.
  **Layman:** Widen a column while checking an import and it snaps back to the default next time you import — unlike every other table in the app, which remembers.
  Kind: fix.
  Source: user-request-2026-07-28 (screenshot).

- ✅ [FIBR-0189] **Allow only one running finbreak instance; a second launch raises the existing window.**
  User request 2026-07-28: "ensure that the app can only have one running
  instance (if we need to change this in future we can revisit this)" — so
  single-instance is the intended behaviour, not a configurable one for now.
  Resolved (2026-07-28): SHIPPED by TDD. src/finbreak/single_instance.py — QLocalSocket probe then QLocalServer listen, wired in app.py::run before any window is built. Handles all three traps: a kill -9 stale socket (removeServer before listen, safe only because the probe ran first) that would otherwise make the app permanently unlaunchable; the update relaunch (_release_for_relaunch frees the socket before the key wipe, since apply() ends in os._exit and runs no cleanup — else the replacement would probe a live owner and silently exit); and per-user scoping (the socket lives in a shared temp dir on Unix). Fails OPEN. 8 tests + spec.md. auto_update INV-6 re-pointed from callback IDENTITY to behaviour. Gate: 1411 passed.

  Two reasons this is worth more than tidiness:
    1. It is a likely contributor to the duplicate panel icon in FIBR-0188 —
       a second process is a second window, and no launcher association can
       merge those. Fix both; neither subsumes the other (0188 is a launcher
       NAMING mismatch that bites even with a single process).
    2. VAULT SAFETY. The vault is one SQLCipher file. Two instances with it
       open are two writers against the same database — at best the second
       one's writes race the first's, at worst a torn write during an import
       or migration. The app has no cross-process locking today. Worth
       verifying whether concurrent open is already possible before assuming
       it is: if SQLite's own locking already refuses the second opener, the
       symptom is a confusing error rather than corruption, but either way
       one instance is the answer.

  Implementation — Qt's canonical single-instance pattern, no new dependency:
  QLocalServer / QLocalSocket. On start, try to connect to a named socket keyed
  per USER (not a fixed global name — a multi-user machine must not have one
  user's launch bounce off another's, and the socket must live in the user's
  runtime dir). Connect succeeds => an instance is live: send a "raise" message,
  then exit(0) without building a window. Connect fails => become the owner,
  listen, and on each incoming connection raise + activate the existing window
  (show(), raise_(), activateWindow(), and un-minimise if needed).

  Care needed, and these are the parts that actually bite:
    - STALE SOCKET after a crash or SIGKILL: a leftover socket file makes every
      later launch think an instance is live and silently exit — the app becomes
      unlaunchable. QLocalServer.removeServer(name) before listen() is the
      standard guard; the connect-first ordering means a LIVE owner still wins.
    - The AppImage relaunch path (FIBR-0054/0131 self-update) spawns the new
      binary from the old one. The old process must have released the socket
      before the new one listens, or the update relaunch turns into a silent
      no-op — exactly the class of bug the 0.1.2->0.1.3 "closed but didn't
      reopen" relaunch fix was. Sequence this against os._exit in the installer.
    - The --self-test entry point (_selftest.py builds its own QApplication)
      must NOT take the lock, or a self-test while the app is open would exit 0
      having tested nothing.

  Test posture: the socket layer is testable headlessly — a first "instance"
  listens, a second attempt detects it and reports "already running" without
  building a MainWindow; a removed/stale socket still allows a fresh start. The
  window-raising itself is a qtbot leg on the handler, not on real cross-process
  focus (which is compositor policy and empirical, like the FIBR-0131 legs).
  **Layman:** Clicking finbreak when it's already open brings up the window you already have, instead of starting a second copy.
  Kind: feature.
  Source: user-request-2026-07-28.

- ✅ [FIBR-0190] **A current Standard Bank Current-account statement imports ZERO of its 183 rows — the "Payments / Deposits" column layout matches no Family signature, and the generic fallback can't split the columns.**
  Verified 2026-07-28 against a real 12-page, 3-month SBSA Current-account
  statement (2026-02-28 -> 2026-05-27, 183 transaction rows; NOT committed —
  personal data, see "needs a sample" below).
  Sample located (2026-07-28): the user supplied the path to the real
  statement this diagnosis was made against —
  /mnt/Emulators/storage_backup_2026-05-08/Statements/Current/SBSA_Statement_2026-05-28_3-months.pdf
  (LOCAL ONLY — real payees and balances; it must NEVER be committed, and
  nothing derived from it may enter tests/fixtures/ un-anonymised). So the
  blocker is no longer "no access to the layout" but "no committable
  fixture": the work is to hand-build an anonymised copy in the same layout
  (fictional payees, made-up amounts, recomputed running balance so the
  existing balance checksum still passes) the way the current
  standard_bank fixtures were produced, then fix detect_standard_bank
  against it and re-verify once against the real file locally.

  BOTH import paths fail, so the user sees no importable rows at all:

  1. The dedicated reader returns None (unrecognised -> generic fallback).
     `_LEGAL_MARKER` IS present, so it is definitely an SB statement, but every
     family signature misses. The statement's transaction header line is:
         `Date Description Payments Deposits Balance`
     Family A wants debits+credits+date+balance (window 3) — "credits" appears
     NOWHERE in the document. Family D wants withdrawals+deposits+balance —
     "deposits" is present but "withdrawals" is not. C and B miss outright.
     So this is a FIFTH transactional layout: the money-out column is headed
     **Payments** (not Debits) and money-in **Deposits** (not Credits).

  2. The generic PDF fallback finds a table but cannot use it. `candidate_tables`
     returns 2 candidates; candidate 1 has the correct 5-cell header
     ['Date','Description','Payments','Deposits','Balance'] and 183 data rows —
     but the DATA rows are not column-split: the whole row lands in cell 0
     (e.g. "28 Feb 26 &lt;desc&gt; -250.00 4,278.15\n&lt;continuation&gt;"), because the
     page has no ruling lines for pdfplumber to split on. Result: CsvImporter
     with a Payments/Deposits debit/credit ColumnMapping yields
     **drafts=0, errors=183** under every date format tried
     (%d %b, %b %d, %d %m, %m %d, %d/%m/%Y, %m/%d/%Y, %d %m %Y).

  Observed row shape (useful for the grammar): `DD Mon YY  &lt;description&gt;
  &lt;signed amount&gt;  &lt;running balance&gt;`, with a wrapped continuation line
  carrying the rest of the description — i.e. date-first with an already-SIGNED
  single amount plus a balance tail, which is closer to the existing Family-C /
  fold-based row parsing than to Family A's column pair. The region opens with
  `STATEMENT OPENING BALANCE &lt;amount&gt;` and terminates on the existing
  "please verify" terminator, both already handled.

  Suggested shape: add this as a new Family (or a Family-A variant) —
  `detect_standard_bank` needs a signature on `date`+`description`+`payments`+
  `deposits`+`balance`, and a row grammar for the date-first signed-amount +
  balance form, reusing `_fold` / `_anchor_balance` / `_verify_row` and the
  existing running-balance checksum (which this layout CAN satisfy — it prints a
  balance on every row plus an opening balance). Note "Payments" is a money-OUT
  column here, which inverts the usual reading of that word — worth a comment.

  Needs a sample: the verification file is a real statement with real balances
  and payees, so it cannot go in `tests/fixtures/`. Blocked on a hand-anonymised
  copy (same layout, fictional payees/amounts, recomputed running balance) the
  way the existing standard_bank fixtures were produced. Same blocker class as
  FIBR-0074, but this one is Standard Bank — a bank the app already claims to
  support — so it is a REGRESSION-grade gap, not a new-bank feature.
  **Layman:** A real Standard Bank statement won't import at all right now — the reader doesn't recognise this newer page layout, and the manual fallback can't tell the columns apart either.
  Kind: fix.
  Lanes: importers, tests.
  Source: user-request-2026-07-28 (real statement checked in-session).
  Spec ACCEPTED (2026-08-03): docs/specs/FIBR-0190.md, converged after 4
  cold-eyes loops (2 cold lanes each). Not yet implemented — next step is TDD,
  red first.

  Corrections to this bullet, all measured against the real statement:
  - 182 transaction rows, not 183. The generic fallback's "183 data rows"
    counted the STATEMENT OPENING BALANCE line as a row.
  - The statement prints NO closing balance anywhere in 12 pages, and no
    "Statement from ... to ..." period line (it prints From:/To:). So Family E
    must NOT join Family A's period-is-None refusal, or every E statement
    bricks.
  - The balance's minus is LEADING (-730.55), the opposite of Family A's
    trailing convention. 0 of 182 rows carry a trailing-minus balance.
  - Row dates are Title-case on all 182 rows, so _MON_RE needs no re.I.
  - The last page prints Payments / Deposits column totals and both are EXACT
    column sums, so Family E gets a real completeness gate where Savings has
    none — it catches a truncated tail, which the per-row running-balance chain
    is blind to.

  The spec's design point the reviews kept returning to: parse()'s family chain
  ends in a bare `else: _parse_family_c(...)`, so omitting an explicit
  `elif family is Family.E` routes every E statement into the credit-card
  parser, which does not fail cleanly — it matches with the balance captured as
  the amount, sign-flipped. Wrong money, no exception.
  Resolved (2026-08-04): Family E shipped per docs/specs/FIBR-0190.md.
  detect_standard_bank gains the five-token "Date Description Payments
  Deposits Balance" signature in the slot C->D->E->B->A; _E_ROW parses
  `D[D] Mon YY desc [-]amount [-]balance` (both minuses LEADING, the
  opposite of Family A); _looks_like_row/_fold gained an OPT-IN dmy_lead
  keyword so no other family's fold changed; _anchor_balance and
  _capture_opening learned "statement opening balance"; _cc_iso became the
  shared _dmy_iso. E prints no closing figure, so its completeness gate is
  _verify_e_totals against the printed Payments/Deposits column totals,
  each verified independently on magnitudes in minor units — and
  closing_balance_minor is supplied only when BOTH printed and verified.
  8 synthetic reportlab fixtures + 46 test legs; 8 mutations of the new
  code were each caught by at least one leg. Suite 1610 passed / 2 skipped.
  Cross-doc: FIBR-0050 (5 enumerations that said "A/B/D" or named Savings
  as the sole closing-less family), the test contract, CHANGELOG.

- 📋 [FIBR-0191] **Amount-range (min/max) filter on the Transactions tab.**
  Split out of FIBR-0109 (2026-07-28) as the one piece its absorb target
  did not build. FIBR-0012 shipped the Transactions tab
  (src/finbreak/ui/transactions.py) with search + date-range + account +
  category filters, all combinable; the amount-range (min/max) filter
  FIBR-0109 originally named was deliberately NOT chosen in the FIBR-0012
  brainstorm and is recorded under Out-of-scope in
  docs/specs/FIBR-0012.md. The user confirmed on 2026-07-28 that it is
  still wanted, so it is re-filed here rather than left implicit in a
  closed bullet.

  Scope: two optional amount inputs (min, max) in the existing Transactions
  filter bar, combinable with every filter already present, pushed into the
  same query/where layer the other filters use — not a post-filter in
  Python. Decisions the spec must settle, none of them obvious:

  - Whether the comparison is on the SIGNED amount or its magnitude. The
    app stores money-out as negative, so "over 1000" most likely means
    |amount| >= 1000 to a user, but a signed reading is defensible and the
    two disagree on every debit. Getting this wrong is a wrong-total class
    bug, so it needs an explicit invariant either way.
  - Whether a blank input means unbounded on that side (expected) and how
    min &gt; max is handled — refuse, swap, or return empty.
  - Currency: FIBR-0087 (per-account currency) and FIBR-0111 (currency in
    its own column) are both open, so a mixed-currency vault would compare
    unlike amounts. Either scope this to the single-currency case with a
    note, or gate it on those items.
  - Whether the range participates in the saved per-tab filter state the
    other Transactions filters use.

  Reuses the existing list_transactions read path and the tab's current
  filter plumbing; no new repository. Dependencies: FIBR-0012 (✅).
  **Layman:** Let people narrow the transaction list to amounts between two figures — e.g. "show me everything over R1 000" — alongside the search, date, account and category filters already there.
  Kind: feature.
  Lanes: ui.
  Source: user-request-2026-07-28.

- ✅ [FIBR-0192] **Finish FIBR-0084: the shared column scheme on the last unwired headers, and make Reset layout actually reset columns.**
  Split out of FIBR-0113 on 2026-07-28 after a /cold-eyes loop-2 pass found
  that FIBR-0113's fold-in of this work was the single largest source of
  defects in that spec (4 of 5 criticals). Splitting keeps each item inside
  the review's design point; nothing is dropped. FIBR-0084 stays OPEN until
  this ships — FIBR-0113 alone does not close it.

  Three gaps, each verified against source on 2026-07-28, not recalled:

  1. ui/forecast.py::ForecastWidget._make_table builds a 4-column
  QTableWidget, already named "forecast_events" and otherwise configured
  like its siblings, but forecast.py imports nothing from _table_state — so
  its columns are neither reorderable nor remembered. CAUTION: its filler
  _fill_events uses a bare setRowCount + setItem loop with NO fill_guard,
  unlike every other sorted table (statements / transactions / transfers /
  recurring). So add remember_columns ONLY — adding enable_sorting without
  first wrapping the fill in fill_guard lets Qt re-sort mid-fill and render
  a running balance against another event's date. Wrap the fill first if
  click-sorting is wanted.

  2. ui/home.py's dashboard breakdown trees: QTreeWidget with
  setColumnCount(2), a VISIBLE header (setHeaderLabels Name / Amount) and
  objectName "dashboard_breakdown_<key>". home.py imports nothing from
  _table_state. FIBR-0084's own text names this surface — "Make each
  QTableView/QTreeView header user-resizable AND movable ... Covers every
  relevant table: Statements, Home transactions, Accounts, Categories,
  Rules" — so it is in scope by that bullet's wording (user confirmed
  2026-07-28). Note _table_state.remember_columns is typed
  `(table: QTableWidget)`; a QTreeWidget is not one, so the helper needs its
  parameter widened to the common base (both expose horizontalHeader /
  header via QAbstractItemView + QHeaderView) or a sibling overload. That
  signature widening is the only non-trivial piece of this item.

  3. main_window.py::MainWindow._reset_layout removes exactly _KEY_GEOMETRY,
  _KEY_STATE and _KEY_SIZE. It never touches the "columns/<objectName>"
  entries remember_columns writes, so Reset layout silently leaves every
  table's saved column layout in place — which is what FIBR-0084's bullet
  asks for and does not have. QSettings.remove("columns") drops the whole
  group. Two cautions found in review: the action does NOT rebuild the
  workspace, so live headers keep their restored state until restart unless
  they are also reset in place; and the existing self.resize(...) runs AFTER
  settings.sync(), which can emit sectionResized on a live table and write
  "columns/<name>" straight back. Order the clear accordingly and assert the
  user-visible outcome, not just an empty INI.

  Deps: FIBR-0117 (the _table_state seam), FIBR-0113 (lands the Accounts
  table; independent of this). Blocker for: FIBR-0084's ✅ flip.
  **Layman:** Let people resize and reorder the columns on the Forecast tab and the Home dashboard's category breakdown lists — the last two places that still can't — and make the "Reset layout" menu item put columns back to their defaults, which it currently doesn't do.
  Kind: feature.
  Lanes: ui.
  Source: cold-eyes-2026-07-28 (FIBR-0113 loop 2).
  Spec ACCEPTED 2026-07-31 (docs/specs/FIBR-0192.md) — /cold-eyes
  converged after 4 loops plus a mid-run split. Totals: 1 CRIT, 10 HIGH,
  29 MED, 34 LOW verified and ALL fixed; 9 unverified/dismissed. No
  deferred tail — nothing was left open.

  The split (loop 3->4): the ratio stop-trigger fired twice (collateral
  outnumbering draft defects two loops running), so the ten measured Qt
  facts and their probe scripts moved to docs/specs/FIBR-0192-qt-facts.md
  with permanent ids QT-1..QT-10, and all citations were retargeted off
  the position-dependent "2.1 row N" form. That doc is a REFERENCE —
  /doc-lint checks it, not /cold-eyes.

  Three findings that would have shipped bugs: (1) saveState() serialises
  the sections-movable flag, so a capture one line early would have
  turned drag-reorder off app-wide; (2) it ALSO serialises the sort
  indicator, so a capture before enable_sorting would make the sort arrow
  vanish; (3) a sortable view's re-sort rides on sortIndicatorChanged, so
  the blockSignals guard an earlier draft specified would have
  desynchronised the arrow from the rows on five shipped tables. All
  three were found by RUNNING Qt, not by reading it.

  Next: TDD the implementation (8 invariants, 7 test functions in
  tests/features/table_state/ plus the mypy gate stage).
  Resolved (2026-08-02): implemented TDD off the accepted spec. `remember_columns` widened to `QTableWidget | QTreeWidget` via `_header_of`, capturing the build-time header state into a `finbreak_default_header_state` dynamic property after `setSectionsMovable(True)` and before the restore; new `reset_columns(root)` sweeps `findChildren` and restores it (NOT under `blockSignals`); `_reset_layout` reordered to resize -> centre -> reset_columns -> clear -> sync. Two new call sites: `forecast.py::_make_table`, `home.py::_build_column`. Seven legs in tests/features/table_state/ (INV-1,2,3,5,6,7,8) plus mypy for INV-4; suite 1455 passed / 2 skipped.

  Three spec claims measured NARROWER than written, and the spec was amended rather than the tests bent to fit: (1) INV-6 needed a fourth precondition — the Transactions tab must be the CURRENT tab, or a QTabWidget gives its page no layout pass and the reset's resize emits no `sectionResized` at all, leaving the leg vacuous; (2) INV-6 does NOT discriminate the clear-first/clear-last ordering — `reset_columns` and `settings.remove("columns")` are redundant in-process, so the INI holds the default state under either ordering; (3) consequently nothing covers the clear itself. §4.4's ordering is kept on correctness grounds (it does not depend on which Qt emission timing occurs), and §11 now carries six `nothing` rows instead of four plus a `partly`.

  Verified by mutation, not by reading: capture-before-movable, capture-after-restore, drop-reset_columns, drop-home-call, drop-forecast-call and the narrowed mypy type each turn the expected leg red.

- ✅ [FIBR-0193] **Account storage: migration v13 adds nullable accounts.account_number + accounts.note, carried through model / repo / service.**
  Split out of FIBR-0113 on 2026-07-28, executing the recommendation
  /cold-eyes loop 5 made when that spec did not converge (35 verified
  findings; docs/reviews/FIBR-0113-cold-eyes-loop5.md). FIBR-0113 was 985
  lines against a ~567-line median, and three NEW structural draft defects
  appeared at loop 5 after four cold reads missed them — the size trigger in
  /cold-eyes Phase 5. This half was the quietest lane in that loop: zero
  CRITICAL, one HIGH, all findings local.

  SHIPS FIRST. FIBR-0113 (the 5-column Accounts table and the masking)
  reads and writes these two columns, so it cannot start until they exist.
  FIBR-0198 (the reveal toggle) follows FIBR-0113.

  Scope — the storage half of FIBR-0113's original design:
  - migrations.py: LATEST_SCHEMA_VERSION 12 -> 13 and a _migrate_to_v13 step
    issuing two nullable ADD COLUMNs inside one owned_transaction.
  - models.Account gains account_number + note, appended after created_at.
  - repositories/accounts.AccountRepository: both listing SELECTs grow the
    two columns in dataclass field order (Account(*row) is positional), and
    add() / update() grow the two parameters, REQUIRED not defaulted.
  - services/accounts.AccountService: add_account's are optional keyword
    args, update_account's are REQUIRED — an unconditional UPDATE ... SET
    means a defaulted None silently erases a stored value at every one of
    the six existing three-argument call sites.
  - A module-level _normalise_optional in services/accounts.py, called by
    BOTH write paths, so a blank field stores SQL NULL rather than "".

  Also carries FIBR-0086's bullet amendment: FIBR-0086 currently claims the
  account-number STORAGE half ("a new column in the ENCRYPTED vault ...
  schema migration, currently v7 -> v8"), which this item delivers instead,
  at v13 not v8. Amend it to keep detection + matching only when this ships,
  or a later implementer re-adds an existing column at a stale version.

  FIBR-0084 stays 📋 when this ships, and stays 📋 when FIBR-0113 ships —
  FIBR-0192 is its blocker, not either half of this split.

  Spec next (docs/specs/FIBR-0193.md), then cold-eyes,
  then TDD.
  **Layman:** Give each account somewhere to keep an account number and a free-text note — the storage side only; the Accounts screen that shows and edits them is FIBR-0113.
  Kind: feature.
  Lanes: repo.
  Source: split-from-FIBR-0113-2026-07-28 (/cold-eyes loop 5).
  Resolved (2026-07-30): shipped by TDD. Schema **v13** — `_migrate_to_v13`
  issues two nullable `ADD COLUMN`s (`accounts.account_number`,
  `accounts.note`) inside one `owned_transaction`; `models.Account` gains both
  fields appended after `created_at` (defaulted, so the four-argument
  positional literals outside the repository keep working); both
  `AccountRepository` read paths SELECT all six columns in dataclass field
  order; `add`/`update` take the two parameters REQUIRED; `AccountService`
  routes both write paths through the new module-level `_normalise_optional`,
  so a blank field stores SQL `NULL` rather than `""`. `add_account`'s two are
  optional keyword args, `update_account`'s are required (D2/D3) — an
  unconditional `UPDATE ... SET` means a defaulted `None` would silently erase
  a stored value. `ui/accounts.py::_on_update` reads the account's current
  values off two new item-data roles (`UserRole + 4`/`+ 5`) and passes them
  back unchanged, so a name/type-only edit leaves both stored fields intact
  (D5, INV-7); FIBR-0113 replaces that passthrough with real form fields.
  Reproduce-first TDD: new `tests/features/accounts/test_migration_v13.py`
  (5 legs, INV-1/INV-2) run RED before the migration existed, plus INV-3..INV-7
  in `test_accounts.py`. Schema-churn sweep: 14 test files re-pinned, 6 test
  functions renamed, the `v12`-as-latest comment sweep across 5 files, and 6
  feature `spec.md` prose fixes. FIBR-0086's bullet amended above (its storage
  half landed here, at v13 not v8). FIBR-0113 stays 🚧 — it ships next.

- 📋 [FIBR-0194] **StatementsWidget.refresh leaves a stale selection that resolves to a different statement under an active sort.**
  Found while reviewing FIBR-0113's spec, which took StatementsWidget.refresh
  as its fill precedent. Verified against source and reproduced against real Qt
  (docs/reviews/FIBR-0113-selection-drift-repro.py).

  ui/statements.py::StatementsWidget.refresh fills with
  `setRowCount(len(self._rows))` + setItem inside fill_guard, with NO
  preceding clear. setRowCount(len) does not clear rows, so an existing
  selection SURVIVES the repopulate; fill_guard's exit then re-applies the
  active sort, and the selection rides its item through that re-sort. It
  lands on whichever row's INSERTION index equals the previously-selected
  VISUAL row — i.e. `_table_state.selected_index` can return a different
  object than the user selected.

  Measured with three rows under a descending sort: the first and last rows
  drift; the MIDDLE row is the sort's fixed point and does not, which is why
  a single-row test can pass in the broken state.

  HARMLESS TODAY, which is why this is 📋 and not urgent:
  StatementsWidget._on_selection_changed only sets two button enabled-states
  (_reassign_button, _delete_button) and touches no form, so the worst
  current outcome is a correctly-enabled button. But _on_reassign and
  _on_delete both resolve through _selected_row() — so a user who sorts,
  selects, and triggers a refresh (any add/import) before clicking could
  reassign or delete a DIFFERENT statement than the one highlighted. Worth
  confirming whether any refresh can interleave with a live selection that
  way before deciding the severity.

  Fix: add a leading `self._table.setRowCount(0)` inside the fill_guard, as
  FIBR-0113 §3 decision 6 does for the Accounts table, and add a regression
  test that drives EVERY row (not one) under a descending sort and asserts
  selected_index is None after refresh.

  Check the other tables built on the same _table_state seam for the same
  pattern before fixing — transactions, transfers, recurring, rules and the
  import-wizard preview all use fill_guard, and any of them that loads a
  form from the selection has the FIBR-0113 CR-1 hazard for real.
  **Layman:** On the Statements tab, redrawing the list while it is sorted can leave the highlighted row pointing at a different statement than the one shown. Harmless today because the two buttons it drives are only enabled/disabled — but the same pattern would corrupt data on any tab that loads a form from the selection.
  Kind: fix.
  Lanes: ui.
  Source: cold-eyes-2026-07-28 loop 5 on docs/specs/FIBR-0113.md (code-side observation, surfaced not fixed).

- 📋 [FIBR-0195] **Resolve the docs/plans/ gap once, project-wide, instead of re-arguing it in every spec.**
  spec-format §2 makes a plan mandatory "once the build order matters (a
  migration, a change that must land in a specific sequence, or anything a
  second person will execute)". Verified 2026-07-28: docs/plans/ does not
  exist anywhere in this tree, and none of the 49 files in docs/specs/ has
  one — including every spec that ships a schema migration.

  The cost is not the missing files, it is that each affected spec now spends
  a paragraph explaining why it has no plan, and a cold reviewer correctly
  re-raises it every time. Prior non-compliance is not a waiver, so the
  paragraph cannot just say "nobody else does it either".

  Decide one of:
  (a) adopt docs/plans/ for specs that carry a migration or an ordered build,
      starting with the next one, and backfill nothing; or
  (b) record the departure ONCE — in docs/standards/documentation.md or a
      project spec-format override — and have every spec point at that single
      statement instead of restating it.

  (b) is the cheaper answer if the build order genuinely lives fine inside
  the spec's design section, which is what the existing 49 specs suggest in
  practice. Either way the per-spec paragraph goes away.

  Surfaced by /cold-eyes rather than fixed inline: choosing between (a) and
  (b) is a project-convention decision, not a docs defect.
  **Layman:** Every spec that involves a database change is supposed to ship a short build-order file. None of them do, and each spec currently explains that omission again. Decide once: either start writing them, or record the exemption in one place.
  Kind: doc.
  Source: cold-eyes-2026-07-28 loop 1 on docs/specs/FIBR-0193.md.

- 📋 [FIBR-0196] **Reconcile the spec-filename rule: naming.md says `<ID>.md`, the shared spec-format says `<ID>-<topic>.md`.**
  Two standards claim authority over the same filename and give
  different answers:

  - docs/standards/naming.md: "**Spec doc** | `<ID>.md` (the stable
    roadmap ID)", repeated under *ID-named docs* ("using the **stable ID
    verbatim**"). Its §9 *Project overrides* says "(None yet.)"
  - ~/.claude/skills/_shared/spec-format.md §2 (the governing format
    standard, since this project has no docs/standards/spec-format.md):
    `docs/specs/<ID>-<topic>.md`.

  Measured 2026-07-28: 48 of the 49 files in docs/specs/ use the bare-ID
  form. The single exception was FIBR-0193, written topic-suffixed during
  the FIBR-0113 split; it has been renamed to docs/specs/FIBR-0193.md so
  the tree is uniform again, and every reference repointed.

  That fixes the instance, not the conflict. The next spec written from
  the shared format standard will depart again, and a cold reviewer will
  correctly flag it again.

  Decide one of:
  (a) keep the bare-ID form (matches all 49 specs and naming.md) and
  record it as a project override in naming.md §9, so the departure from
  the shared standard is stated once and deliberately; or
  (b) adopt `<ID>-<topic>.md`, update naming.md's table and its ID-named
  docs paragraph, and accept that the existing 49 are grandfathered.

  (a) is the cheaper answer — it is what the tree already does, and the
  topic suffix buys nothing that the spec's own title line does not.

  Surfaced by /cold-eyes rather than decided inline: which standard wins
  is a project-convention call, not a docs defect.
  **Layman:** Two rulebooks disagree about what to call a spec file. Pick one so the next spec doesn't get named wrong.
  Kind: doc.
  Source: cold-eyes-2026-07-28 loop 2 on docs/specs/FIBR-0193.md.

- 📋 [FIBR-0197] **Two feature spec.md files still pin LATEST_SCHEMA_VERSION == 5.**
  `tests/features/pdf_import/spec.md` INV-8 pins `LATEST_SCHEMA_VERSION == 5`
  and `tests/features/import_/spec.md` INV-8 says the version "is now 5".
  Both are prose-only staleness in test-contract files: the *tests* those
  specs describe are green, so nothing fails. Surfaced by a cold-eyes lane
  while reviewing FIBR-0193 and deliberately NOT folded into that item —
  these two files are outside its blast radius (they are not in the
  `== 12` pin set FIBR-0193 §6/§12 own), and widening a review run into
  unrelated documents is how a review silently becomes an edit run.
  Fix: advance both to whatever `LATEST_SCHEMA_VERSION` is when this is
  picked up, or reword them to cite the constant instead of a literal so
  they stop churning on every migration.
  **Layman:** Two old test-contract files still say the database format is at version 5, when it is really at 12 (and about to be 13) — harmless today, but confusing to read.
  Kind: doc-fix.
  Source: in-session-2026-07-30 (FIBR-0193 cold-eyes loop 4, deferred finding).

- ✅ [FIBR-0198] **Accounts tab: reveal the masked account number, with an auto re-mask after 30s.**
  Split out of FIBR-0113 on 2026-07-30. FIBR-0113 ships the sortable
  5-column Accounts table with the account number ALWAYS masked; this item
  adds the way to see it. Blocked by FIBR-0113 (it needs the table, the
  mask helper and the account-number form field that item creates).

  Scope: a "Show account numbers" QCheckBox between the table and the
  form; a single-shot QTimer (_REVEAL_SECONDS = 30, matching the existing
  clipboard_clear_seconds default) that re-masks unattended; reveal
  governs BOTH surfaces — the table cell text AND the form field's echo
  mode (Password -> Normal), because the form fills on every row selection;
  session-scoped, never persisted, and gone after a lock cycle. The
  toggle handler must re-select the previously-selected account with the
  table's signals blocked, or it clobbers a half-typed edit.

  Also amends docs/security-model.md T13, whose mitigation currently
  asserts account numbers are "not copyable" — true only while the form
  field stays in Password echo mode, i.e. only until this ships.

  The split reason: shipping the table alone renders the account number
  masked and nothing regresses; shipping the reveal alone is impossible.
  FIBR-0113 §8 records why "mask with no reveal" is not the end state —
  a user who needs the full number to pay someone would otherwise have to
  open the vault file to get it back.
  **Layman:** Add a "Show account numbers" tick-box to the Accounts tab so you can read a full account number when you need to pay someone — and have it hide itself again after half a minute so it can't be left on screen.
  Kind: feature.
  Lanes: ui.
  Source: in-session-2026-07-30 (FIBR-0113 split, UI half).
  Resolved (2026-07-30): shipped by TDD, closing the
  FIBR-0193 → FIBR-0113 → FIBR-0198 chain. A "Show account numbers" checkbox
  between the table and the form switches the account number from masked to raw
  on BOTH surfaces FIBR-0113 masks — the table cell (a conditional write in the
  fill) and the form field (echo mode `Normal`/`Password`, the
  `ExportDialog._on_show_toggled` idiom). Session-scoped and written to no store;
  a lock needs no extra code, since `MainWindow._lock()` destroys the workspace
  and the next unlock builds a fresh widget. A parented single-shot `QTimer`
  re-masks after `_REVEAL_SECONDS` (a COPIED literal 30, not an import of
  `DEFAULT_CLIPBOARD_CLEAR_SECONDS` — importing it would make this window track
  that user-settable default, the coupling D3 forbids); the interval restarts
  rather than extends on each fresh reveal, and no `_refresh()` from any other
  cause touches it. `_on_reveal_toggled` runs six ordered steps, re-selecting
  under `blockSignals` (with the unblock in a `finally`) so a re-mask cannot
  repopulate four form inputs from storage over a half-typed edit — the reveal is
  the one control a user reaches for mid-edit. `_refresh()` gained a
  `VaultLockedError` guard around all five pre-fill reads, because a queued
  timeout can land between the vault locking and the deferred `deleteLater()`.
  Reproduce-first TDD, 5 legs red first: INV-2 leads by EMITTING the timeout,
  because the configuration-observing legs all pass against an implementation
  that never connects it, and its no-restart leg leads with `isActive()` because
  `QTimer` returns -1 from `remainingTime()` when inactive. `security-model.md`
  T13 amended and **T14** added: the reveal makes an account number copyable from
  the form field, and that copy is NOT auto-cleared — `ClipboardAutoClear` is
  wired only to the transactions list, so a Ctrl+C during a 30-second reveal
  outlives it indefinitely. A deliberate gap (clearing it mid-payment would defeat
  the reason the reveal exists), now stated rather than implied. Screenshots +
  README refreshed. FIBR-0084 still stays 📋 until FIBR-0192.

- ✅ [FIBR-0199] **Cover Reset layout's settings clear — no leg discriminates it today.**
  Found by mutation-testing during the FIBR-0192 build (2026-08-02).
  `reset_columns(self)` and `settings.remove("columns")` in
  `MainWindow._reset_layout` are redundant while both run in the same
  call: each alone leaves a rebuilt view on the default columns, so
  dropping either one keeps INV-6 green and only dropping BOTH turns it
  red. The clear is defence-in-depth for a view `reset_columns` cannot
  reach (built without `remember_columns`, or destroyed before the
  reset), and that path has no live instance.
  The same redundancy is why no leg discriminates the clear-first vs
  clear-last ordering that FIBR-0192 §4.4 turns on — under either, the
  INI ends up holding the default state, immediately as well as after a
  deferred layout pass. Closing this needs a genuinely fresh process, or
  a fixture that builds a remembered view and destroys it before the
  reset. FIBR-0192 §11 records both as `nothing` rows.
  **Layman:** A safety net in the Reset-layout code has no test proving it works.
  Kind: test.
  Source: in-session-2026-08-02 FIBR-0192 build.
  Progress (2026-08-02): one fixture input verified while pre-checking
  FIBR-0200. A leg that needs a remembered view DESTROYED before the reset
  must use `deleteLater()` plus a real event-loop spin (or
  `shiboken6.delete`) — `QApplication.processEvents()` does NOT process
  DeferredDelete, so the widget is still alive and the leg silently proves
  nothing (measured: `shiboken6.isValid(holder)` is still True after
  `deleteLater()` + `processEvents()`; False after a `QTimer`-quit
  `app.exec()` spin). FIBR-0200 itself closed as not reproducible, so this
  bullet no longer shares a scenario with it.
  Resolved (2026-08-02): closed by the fixture this bullet called for — a
  remembered view DESTROYED before the reset, which is the one shape
  `reset_columns(self)` cannot reach. `tests/features/table_state/` row 13
  + `test_FIBR0199_reset_clear_discriminates_a_destroyed_remembered_view`
  widens and persists `transactions_table`'s column 0, destroys the table
  (`deleteLater()` + `_pump_deferred_delete()`, asserted with
  `shiboken6.isValid`), runs `_reset_layout()`, and requires a freshly
  built view to come up on the default width.
  Discrimination verified by mutating BOTH lines independently, not just
  the one: dropping `settings.remove("columns")` turns it RED
  (`assert 197 == 100` — the stale width survives), while dropping
  `reset_columns(self)` leaves it GREEN. That is the property INV-6 could
  not provide, which only went red when both were dropped.
  NOT closed: the clear-first vs clear-last ORDERING that FIBR-0192 §4.4
  turns on still has no discriminating leg — this fixture destroys the
  view, so both orderings end with the group erased. Still a `nothing` row.

- ✅ [FIBR-0200] **remember_columns' _save can outlive its header and raise at teardown.**
  Observed 2026-08-02 while probing FIBR-0192: a standalone script exits
  with `RuntimeError: libshiboken: Internal C++ object
  (PySide6.QtWidgets.QHeaderView) already deleted` raised from `_save` in
  `ui/_table_state.py`. The closure captures `header` and stays connected
  to the header's own signals, so a late emission during interpreter /
  widget teardown calls `header.saveState()` on a destroyed C++ object.
  Pre-existing (FIBR-0117), not introduced by FIBR-0192 — surfaced only
  because the probe ran outside pytest, where teardown ordering differs.
  Harmless today (stderr noise at exit, nothing is lost), but it is the
  same class as the shiboken lifetime issues the UI already guards. (This
  line originally cited "the QT-5 `TypeError` §4.3 documents"; FP01
  re-measured QT-5 on 2026-08-02 and no `TypeError` occurs — that citation
  is withdrawn, but this teardown `RuntimeError` is independently real and
  was reproduced again by the close-phase code lane.) Likely fix:
  guard `_save` with `shiboken6.isValid(header)`, matching the pattern
  `main_window.py::_ensure_workspace` already uses. Confirm it can fire
  in the packaged app before spending much on it.
  **Layman:** A harmless-looking error can print when the app shuts down.
  Kind: fix.
  Source: in-session-2026-08-02 FIBR-0192 build.
  Resolved (2026-08-02): NOT REPRODUCIBLE AS SHIPPED. The pre-check this
  bullet itself asked for came back negative on every path tried, so the
  `shiboken6.isValid` guard is not worth adding — it would be a defensive
  branch for a state the current stack forbids. Evidence, all against
  v0.1.19 / PySide6 6.11.1:
  (a) The packaged AppImage driven end to end against a seeded throwaway
  vault on an isolated X display: unlock, five tabs built, then File ▸
  Quit — exits 0 with EMPTY stderr. File ▸ Lock, which destroys all 13
  remembered views while the process keeps running, is equally silent.
  (b) The same flow from source: exit 0, silent.
  (c) Direct probe: after a GENUINE destruction (`shiboken6.isValid(header)`
  == False, verified), `_save` is never called again. Qt drops the
  connection with the header, and emitting on the dead header raises
  "Signal source has been deleted" at the EMIT site, so `_save` never runs
  to reach `header.saveState()`. NOTE a first attempt at this probe was
  invalid: `QApplication.processEvents()` does NOT process DeferredDelete,
  so the widget was still alive and the silence proved nothing.
  (d) 30 days of real maintainer runs — 30 distinct `app-finbreak@*.service`
  scopes, whose stderr does reach the journal (its fontconfig / xkbcommon
  lines prove the capture works) — contain zero "already deleted" /
  "Internal C++ object" lines.
  The one gap: the 2026-08-02 probe script that produced the original
  observation was never committed, so its exact shape could not be
  replayed verbatim. Re-open if it resurfaces on a newer PySide6.

- ✅ [FIBR-0201] **Bulk-confirm transfers — tick several suggested pairs and confirm them in one click.**
  The Transfers tab today offers exactly two speeds and nothing in
  between: `_on_confirm` (`ui/transfers.py:174`) confirms the ONE
  selected candidate, and `_on_confirm_all` (`:200`) confirms every
  candidate the detector produced. A user who trusts eight of twelve
  suggestions has to click through eight times or accept all twelve.

  Verified against source 2026-08-02, not recalled:

  1. `ui/transfers.py:119` sets the suggested table to
  `QAbstractItemView.SelectionMode.SingleSelection`, so multi-select is
  not merely unwired — the table refuses it. Widening it is the first
  change, and it is the one with blast radius: `_selected_row()` returns
  a single index and is used by `_on_confirm`, `_on_reject` and the
  enable/disable recompute, so each needs a decision about what "the
  selection" means once it can be plural.

  2. `remember_columns` + `enable_sorting` are both live on this table
  (`:120-121`), so a confirm that rebuilds via `_refresh()` re-sorts.
  The FIBR-0113 finding applies: a selection held across a re-sort can
  ride its item onto a DIFFERENT row. A bulk confirm must resolve every
  ticked row to its `(debit.id, credit.id)` BEFORE it starts confirming,
  not index into `self._candidates` as it goes.

  3. The status line uses `tr("Confirmed %n transfer(s).", "", n)`, which
  already pluralises — so the count is free once the loop exists.

  Open design question for the spec: whether the service grows a
  `confirm_many(pairs)` that owns one transaction, or the widget loops
  over `confirm()`. A partial failure mid-loop leaves some pairs
  confirmed and some not, with no record of where it stopped, so the
  transaction boundary is a correctness question, not a tidiness one.
  Kind: feature.
  **Layman:** Confirm a handful of suggested transfers at once instead of one at a time.
  Kind: feature.
  Lanes: ui.
  Source: user-request-2026-08-02.
  Progress (2026-08-02): specced jointly with FIBR-0202 in
  `docs/specs/FIBR-0201.md` (umbrella spec, ACCEPTED after 4 cold-eyes
  loops with 2 cold lanes each, 18 invariants).
  **This bullet's open design question is answered: neither a widget loop
  nor a new batch transaction.** `TransferDetectionService` grows
  `confirm_many(pairs)`, and `confirm_all()` becomes `confirm_many(
  candidate_pairs())` — the consumed-set logic MOVES rather than being
  copied, because the hazard it guards (two selected suggestions sharing a
  transaction) is not specific to "all". It keeps `confirm_all`'s shipped
  per-decision-commit boundary (FIBR-0011 D6) rather than inventing a new
  one, since changing that is a behaviour change this item did not ask
  for. It calls `add_decision` directly, not `_record`, so a consumed pair
  is skipped instead of raising `ValueError` at the user; verified that
  this is safe — `add_decision` canonicalises the pair internally
  (`min`/`max`), so bypassing `_record` changes what is rejected, never
  what is written.
  The selection mode is `MultiSelection`, not `ExtendedSelection` (plain
  click toggles; no Ctrl/Shift knowledge needed for this app's audience),
  and only the SUGGESTED table widens — `_make_table` builds both transfer
  tables from one line, so it takes a parameter.
  Resolved (2026-08-03): shipped by TDD off docs/specs/FIBR-0201.md.
  The open design question (service `confirm_many` vs a widget loop) is
  answered by D4/§4.3 in favour of the service: `confirm_many(pairs)`
  confirms in the GIVEN order and the consumed-set logic MOVED there rather
  than being copied, so `confirm_all()` is literally its caller (INV-5) and
  the two cannot drift. `reject_many` sits alongside it (D3) — rejection
  consumes nothing, so two selected suggestions sharing a transaction are
  both recorded. Both record via `add_decision`, not `_record`, whose two
  guards RAISE where a skip is wanted; `add_decision` canonicalises the pair
  internally, so nothing about what is written changes. A skipped pair is
  named on the status line, and `tr("Rejected.")` stays byte-for-byte at
  n == 1 (INV-14).

- ✅ [FIBR-0202] **Bulk-delete statements — tick several, plus a Delete all button.**
  The Statements tab deletes exactly one statement per click
  (`ui/statements.py:205`, single-select at `:94`), and there is no way
  to clear the list. Clearing out a bad import run means N confirm
  dialogs.

  Verified against source 2026-08-02, not recalled:

  1. `ui/statements.py:94` is `SelectionMode.SingleSelection` — same
  first change as the transfers item, and the same re-sort hazard
  (`enable_sorting` at `:95`): resolve ticked rows to statement ids
  before deleting, never index as you go.

  2. **The confirm text cannot simply be repeated N times.** `_on_delete`
  calls `StatementService.delete_preview` (`services/statements.py:82`)
  per statement and branches on whether any transactions are shared with
  an overlapping statement — the FIBR-0149 wording fix. A bulk delete
  needs ONE aggregate message, so `delete_preview` needs a batch form or
  the caller has to sum the pairs itself.

  3. **The batch is order-sensitive, and this is the real hazard.**
  `delete_statement` (`services/statements.py:57`) runs FIBR-0148's
  hand-off: each stamped row a REMAINING same-account statement also
  covers is re-stamped to that statement rather than deleted. "Remaining"
  is evaluated per call, so deleting A then B is not the same as deleting
  {A,B} as a set — rows handed to B in step one are then deleted in step
  two, and a preview computed up-front over-states what survives. The
  spec has to decide whether a bulk delete is one transaction that
  evaluates coverage against the post-batch survivor set, or a
  documented sequence of independent deletes.

  4. A **Delete all** button is the same operation with the selection
  implied, and inherits point 3 exactly: with every statement going, no
  statement remains to hand rows off to, so every stamped row is deleted.
  Worth stating in the confirm text, since that is the case where the
  loss is total.
  Kind: feature.
  **Layman:** Remove several imported statements at once, or clear the lot, instead of deleting them one by one.
  Kind: feature.
  Lanes: ui.
  Source: user-request-2026-08-02.
  Progress (2026-08-02): specced jointly with FIBR-0201 in
  `docs/specs/FIBR-0201.md` (umbrella, ACCEPTED after 4 cold-eyes loops).
  **This bullet's point 3 is CORRECTED by measurement.** It called the
  per-call FIBR-0148 hand-off "order-sensitive, and this is the real
  hazard". Measured against the real services: the SURVIVING DATA is not
  order-sensitive — deleting A-then-B and B-then-A end identically, and
  identically to batch semantics — because the hand-off re-evaluates on
  every call, so coverage by a statement that is itself being deleted
  never persists. What DOES break is the PREVIEW: summing per-statement
  `delete_preview` calls over a batch reports `removed=0, kept=3` where
  the batch-aware query reports `removed=2, kept=1`, so the confirm dialog
  would promise nothing is permanently removed and then destroy two
  transactions. That is the money-critical defect, and atomicity — not
  data correctness — is what one transaction buys (spec D5/§2.1).
  Also found while specing: the exclusion predicate `q.id <> :pid` lives
  at FOUR sites, not two — `hand_off_covered`'s `SET` correlated picker as
  well as its `EXISTS` guard, plus both of `delete_split_counts`' arms.
  Widening only the guard would let a row be handed to a statement inside
  the batch, which the same batch then deletes.
  Resolved (2026-08-03): shipped by TDD off the shared spec.
  Point 3's premise was already corrected by §2.1 and the build confirms it:
  loop ORDER does not change what survives — INV-13 measured batch against a
  per-call loop in BOTH orders over three seeds. The real hazard was the
  CONFIRM MESSAGE: summing per-statement previews reported removed=0 for a
  delete that destroys two transactions. One batch-aware preview now answers
  it. The exclusion predicate lives at FOUR sites, not two (the SET picker is
  not EXISTS-shaped and is the easy one to miss); all four interpolate one
  `_coverage_where_sql`, proven on the emitted SQL. The batch is one owned
  transaction — for atomicity, not data correctness.

- ✅ [FIBR-0203] **Back-fill the missing v0.1.17 GitHub release — its notes are invisible to the in-app updater.**
  `gh release list` jumps 0.1.18 → 0.1.16: there is no GitHub **release**
  for v0.1.17, though the tag exists locally AND on origin
  (`21bebf7`, 2026-07-23) and `CHANGELOG.md` carries the full section.

  Verified against source 2026-08-02, not recalled — this is not
  cosmetic. FIBR-0152 (✅, shipped) accumulates the notes shown in the
  update prompt from the **GitHub release objects**, not from tags or
  from CHANGELOG.md: `services/update.py:280` calls `fetch_releases`,
  which GETs `/releases?per_page=30`
  (`services/update_fetch.py:28`), and `:286` feeds that list to
  `_accumulated_notes(releases, current, offered)`. A release absent
  from the list contributes nothing.

  Consequence: a user still on **0.1.16** who is offered 0.1.18 sees
  0.1.18's body only. Everything 0.1.17 delivered — Flathub Flatpak
  packaging (FIBR-0159), native RPM/deb via OBS (FIBR-0155), 3-level
  categories (FIBR-0154), the "Forgot password? Start over" vault reset
  (FIBR-0030), signed SHA256SUMS + SBOM (FIBR-0096), Report an Issue
  (FIBR-0156) — is silently missing from the prompt. The offer itself is
  unaffected (`_notes_since` is best-effort and the decision is already
  made), so this degrades the notes only.

  Open decision for whoever picks this up: whether to publish notes-only
  (cheap, fixes the accumulation immediately) or to also build and sign
  the v0.1.17 artifacts to match every other release (the tag is 10 days
  old; v0.1.18 supersedes it for actual downloads, and every other
  release carries AppImage + exe + both `.sig`s + SHA256SUMS + SBOM).
  Notes-only leaves an asset-less release page, which is a visible
  inconsistency but harms nobody, since `/releases/latest` — the offer
  endpoint — is unaffected either way.
  Kind: fix.
  **Layman:** A whole version's release notes are missing from the update prompt inside the app.
  Kind: fix.
  Lanes: release.
  Source: in-session-2026-08-02 housekeeping.
  Resolved (2026-08-02): published the v0.1.17 GitHub release
  **notes-only**, per the open decision in this bullet — the notes body is
  CHANGELOG.md's `[0.1.17]` section verbatim, prefaced by a short italic
  line stating the notes were published retrospectively and that no
  artifacts are attached because v0.1.18+ supersede it.
  Created with `--latest=false`, which was the one real hazard: GitHub's
  default "latest" selection is date-based, so a release object created
  today for an older tag would have become `/releases/latest` — the exact
  endpoint `check_for_update` reads to decide what to OFFER. Verified after
  publishing: `/releases/latest` still returns **v0.1.18**, and v0.1.17
  carries 0 assets, `draft: false`, `prerelease: false`.
  Fix verified end-to-end against the LIVE API rather than by inspection:
  called the real `fetch_releases` + `_accumulated_notes` for a user on
  0.1.16 offered 0.1.18 — 19 releases fetched, the prompt now contains
  both `## 0.1.18` and `## 0.1.17` headings (11,032 chars) and the 0.1.17
  body's own content (FIBR-0154, Flathub). Before the back-fill that call
  returned 0.1.18's body alone. The non-empty-`body` and
  not-draft/not-prerelease conditions `_accumulated_notes` gates on are
  all satisfied.
  No CHANGELOG entry and no code change: the defect was a missing release
  object on GitHub, not app behaviour — nothing in the shipped software
  differs. Notes-only leaves an asset-less release page, the accepted
  cost recorded in this bullet's own decision.

- ✅ [FIBR-0204] **FP01 — fix-pass after FIBR-0192: two wrong Qt measurements, and the docs that still say it never shipped.**
  Raised by `/close-phase` on FIBR-0192 — one static-analysis sweep
  (semgrep/ruff/bandit, **0 findings**) plus two cold review lanes. Every
  finding below was re-verified in this session against PySide6 6.11.1 or
  against the file itself; nothing is taken on the reviewer's word.

  **The two measurement defects (latent, no user-visible bug today):**

  1. **QT-10's negative half is backwards.**
  `docs/specs/FIBR-0192-qt-facts.md:38` and `:176-179` conclude that
  `stretchLastSection` and the section resize mode are NOT carried in
  `QHeaderView.saveState()`. Re-measured: **stretch, resize mode,
  `sectionsClickable`, `defaultSectionSize` and per-section hidden flags
  all restore to their captured values.** Probe C's own recorded output
  refutes the conclusion drawn from it. Consequence: `_table_state.py`
  `remember_columns`' docstring (`:141-146`) enumerates only the movable
  flag and the sort indicator as ordering constraints, so a contributor
  who adds `setStretchLastSection(True)` or `hideColumn(n)` AFTER
  `remember_columns` gets it silently reverted by the first Reset layout
  — QT-3's exact failure shape on a flag the contract calls safe. No
  current call site violates it (`transactions.py:181-184` precedes
  `:189`), which is why nothing is broken today.
  Also of record: `docs/specs/FIBR-0192.md:776` shows cold-eyes loop 3
  citing this measurement to DISMISS a lane that had reported it
  correctly.

  2. **QT-5 is a probe artifact.** `_table_state.py:183-188` and
  `main_window.py:1558-1559` state that `_save` never runs on a restore
  because `Qt::SortOrder` fails to marshal and raises `TypeError`, and
  therefore that `reset_columns` "never writes to the INI". Re-measured:
  `restoreState` emits `sortIndicatorChanged` **whenever the restored
  indicator differs from the current one**, and the argument marshals
  cleanly — a proper `SortOrder` enum, no `TypeError`, nothing on
  stderr. So `reset_columns` DOES `setValue` + `sync()` per affected
  view. Harmless today only because `_reset_layout`'s trailing
  `settings.remove("columns")` erases the writes; the docstring's
  rationale rests on a false premise, and any future caller of
  `reset_columns` without a trailing clear persists the default.
  Measured additionally: on a **QTreeWidget**, `restoreState` also emits
  `sectionResized` once, which the same docstring (`:177`) denies.

  **The documentation-truth half** — the item shipped in 70f0e15, and
  these still describe it as pending:

  - `docs/specs/FIBR-0192.md:3-4` — **Status still "ready to
  implement"**; its three siblings (FIBR-0113/0193/0198 `:3`) read
  `✅ SHIPPED`. And `:11-12` still instructs "do NOT flip FIBR-0084 until
  this ships", which the same commit did.
  - `docs/specs/FIBR-0052.md:71` (INV-6) and `:325-326` (INV-6b) — never
  widened to name the `columns/*` group, though FIBR-0192 §12 called this
  out by name as the one existing contract this item widens.
  - `docs/specs/FIBR-0113.md:653-654` — **actively wrong advice**: "no
  escape hatch today ... must delete the `columns/accounts_table` key by
  hand." The escape hatch now exists.
  - `docs/specs/FIBR-0113.md:594-597` (§5 INV-13/INV-14) and `:773-780`
  (§9) — the two places FIBR-0192 §12 said would be "annotated as
  discharged here"; neither was.
  - `docs/specs/FIBR-0113.md:18, :39, :67, :110, :863`;
  `docs/specs/FIBR-0193.md:891-892, :978`;
  `tests/features/accounts/spec.md:227-229` — present-tense pending.
  - `FIBR-0192.md:597` and `:657` — the remembered-view count is **13**,
  not 11 (`recurring.py` and `transfers.py` each build two tables); §10's
  resource figures inherit it.

  **Test-suite verdict: clean.** 15 mutations against the shipped source;
  no vacuous leg, and all four of §11's "nothing checks this" admissions
  are literally accurate. Two LOWs to fold: INV-6's precondition (b) is
  asserted more weakly than §5 states
  (`tests/features/table_state/test_table_state.py:544` accepts a key
  holding the DEFAULT state), and §11 credits INV-6 with catching nothing
  when it does catch the both-mechanisms-dropped case.

  FIBR-0200 was independently confirmed real by the code lane (the `_save`
  teardown `RuntimeError`), and this change takes the connected-closure
  count from 8 to 12 — evidence for that bullet, not new work here.
  Kind: review-fix.
  **Layman:** Corrections found while closing the column-layout work: two measured facts were recorded backwards, and a pile of documents still say the feature is unbuilt.
  Kind: review-fix.
  Lanes: ui, docs.
  Source: in-session-2026-08-02 /close-phase FIBR-0192.
  Resolved (2026-08-02): applied via `/apply-fixes`, commit `5cd057f`.
  Every finding re-measured before fixing rather than taken on the
  reviewer's word — which paid twice. **QT-11 added** and QT-10's negative
  clause withdrawn: `saveState()` does serialise `stretchLastSection`, the
  resize mode, `sectionsClickable`, `defaultSectionSize` and hidden flags.
  **QT-5 rewritten**: `restoreState` emits `sortIndicatorChanged` once per
  view, the `SortOrder` marshals cleanly, and `reset_columns` therefore
  writes + `sync()`s per view — proved against the real functions by
  watching the INI's bytes change across the call. The review's own
  explanation for the original QT-5 reading (Probe A missing a
  `QtCore.Qt` import) was **tested and disproved**; the handler runs
  either way, and that is recorded in the doc so the next reader does not
  re-derive it. Both source comments corrected, plus §4.2/§4.3/§4.4/§8/§10.
  Doc-truth half closed: FIBR-0192's own Status line, its FIBR-0084
  blocker instruction, FIBR-0052 INV-6/INV-6b (widened to the `columns/*`
  group at last), FIBR-0113's wrong "delete the key by hand" advice and
  its two §5/§9 discharge annotations, FIBR-0193 and the accounts test
  spec. Cold-eyes loop-log rows left **frozen** — they record what each
  loop believed at the time, and rewriting them would destroy the audit
  trail that made the QT-10 dismissal findable. View count corrected
  11 → 13. **A test fix that needed fixing twice:** INV-6's precondition
  (b) asserted only that the settings key existed; the first replacement
  compared stored bytes against the build-time default, and mutation
  testing showed that ALSO passes with the widening removed, because the
  preceding `window.resize` already provokes a save. It now snapshots
  either side of the widening and goes red when the widening is dropped.
  Gate green **1455 passed, 2 skipped**; `/doc-lint` clean on all six
  edited docs.

- 📋 [FIBR-0205] **tests/features/bundling cannot be run on its own — it SIGABRTs with a coredump.**
  Found while running a subset of the suite during the v0.1.19 bump.
  `pytest tests/features/bundling` aborts the interpreter — SIGABRT,
  `Fatal Python error: Aborted`, a 12 MB coredump per run. The whole suite
  is green (1455 passed), so this is invisible to the gate and to CI.

  Verified against source 2026-08-02, and reproduced with the release bump
  stashed so it is not caused by the version edits:

  1. `test_INV1_selftest_fail_names_the_broken_stack`
  (`tests/features/bundling/test_bundling.py:86`) monkeypatches
  `_selftest._check_qt` to `lambda: None` and `_check_sqlcipher` to raise,
  then calls `run_self_test`.

  2. `run_self_test` (`src/finbreak/_selftest.py:266`) runs its checks in
  the order `qt → qtcharts → icons → sqlcipher → …`. So `_check_icons`
  runs for real, BEFORE the stubbed-out sqlcipher failure it is testing
  for — and `_check_icons` (`:63`) renders a pixmap
  (`icon("lock").pixmap(QSize(16, 16))`).

  3. `_check_qt` is what constructs the QApplication — its own docstring at
  `:72` says `_check_icons` "Runs after `_check_qt` (needs the
  QApplication)". Stubbing `_check_qt` removes it, so `QIcon::pixmap`
  reaches Qt's `qFatal` in `libqsvgicon.so` and calls `abort()`.
  `run_self_test`'s `except Exception` cannot catch it — `qFatal` is not a
  Python exception.

  4. It passes in the full suite only because an EARLIER test file leaks a
  process-wide QApplication. Proven both ways:
  `pytest tests/features/bundling` → SIGABRT;
  `pytest tests/features/theme tests/features/bundling` → 42 passed.
  So the test's docstring claim that it unit-tests the FAIL contract
  "independent of installed native deps" is false — it depends on a
  QApplication it does not create.

  Consequence beyond the noise: `docs/specs/FIBR-0001.md` INV-6 and
  CLAUDE.md both document running a single test / a single file as a
  supported workflow, and for this file it is not — it dumps core.

  Likely fix: stub `_check_qtcharts` and `_check_icons` alongside the other
  two (the test only asserts the ordered-token contract, so the real
  renderers are incidental), or take pytest-qt's `qapp` fixture so the
  QApplication is created explicitly rather than inherited. Prefer the
  stub — it makes the test's stated independence true.
  **Layman:** One test file crashes hard unless other tests run first, so you can't run it by itself.
  Kind: test.
  Lanes: tests.
  Source: in-session-2026-08-02 v0.1.19 release.

- ✅ [FIBR-0207] **The theme INV-1 test failed whenever a real finbreak was open on the same machine.**
  Caught by the pre-push gate while pushing the v0.1.19 release record:
  `test_INV1_theme_applied_before_window` failed `DID NOT RAISE
  _Sentinel`, breaking a push whose only content was `.claude/workflow.md`
  and `ROADMAP.md`. The same test had passed twice earlier in the session
  (1455 passed, twice), so the trigger was environmental, not a code change.

  Cause, verified against source and reproduced live rather than inferred:

  1. The test patches `app_mod.MainWindow` with a recorder that raises, then
  asserts `run()` raises it — i.e. that the theme is applied BEFORE the
  window is built (FIBR-0127 INV-1).

  2. `app.run()` (`src/finbreak/app.py:64-66`) probes the FIBR-0189
  single-instance guard and `return 0`s *before* constructing `MainWindow`.
  So with another instance live, the recorder is never reached and the
  `pytest.raises` fails.

  3. `single_instance.socket_name()` carries the **uid**, so it is the same
  OS user's running app that collides — and a real finbreak was open on the
  desktop (5 processes; `/home/ants/Applications/finbreak-x86_64.AppImage`,
  already on 0.1.19 — i.e. exactly what a maintainer does right after
  cutting a release: run it).

  4. The suite's `theme_isolation` fixture snapshots only palette / style /
  stylesheet, so it never covered this.

  The product was behaving CORRECTLY throughout — this was only ever a
  test-isolation gap, invisible in CI (no desktop instance) and invisible
  locally until someone had the app open during a gate run.

  Fixed by stubbing the probe alongside the `MainWindow` / `AuthService`
  patches the test already applies — the same class of external dependency
  it had already decided to isolate. No coverage lost: the guard has its own
  8-test suite at `tests/features/single_instance/`. `listen()` needs no
  stub, since the recorder raises before `run()` reaches it.
  Verified the fix under the failing condition rather than after closing the
  app: with 5 finbreak processes still live, `tests/features/theme/` goes
  **32 passed** (was 1 failed / 31 passed).

  Only ONE test drives `finbreak.app.run()`, so this is a local stub rather
  than an autouse fixture; a second such test should factor it out.
  **Layman:** A test broke just because the app happened to be running — fixed, so it no longer depends on that.
  Kind: test.
  Lanes: tests.
  Source: in-session-2026-08-02 v0.1.19 release.

### ⚡ Performance

- ✅ [FIBR-0025] **Enable SQLite WAL mode.** Set
  `PRAGMA journal_mode=WAL` on the SQLCipher DB for better write
  throughput and UI responsiveness during import. *Sequencing:* set at DB
  creation (FIBR-0004). WAL adds `-wal` / `-shm` sidecars (already
  ignored by FIBR-0002; SQLCipher encrypts them too). Target phase: P02.
  Dependencies: FIBR-0004. Lanes: persistence, perf. Kind: perf.
  Source: user-request-2026-07-01.
  Resolved 2026-07-17 (commit 6c74966): journal_mode=WAL on the LIVE vault connection (set at create, converted on open) — readers no longer block the import writer. synchronous stays at the default FULL so per-commit fsync preserves the create() DB-durable-before-sidecar ordering (FIBR-0005 INV-5). The transient restore/backup-assembly connection (in_memory_temp) keeps the rollback journal, since backup._install moves vault.db at the file level without its -wal sidecar (FIBR-0014 INV-1 preserved).

- ✅ [FIBR-0026] **Index the import de-duplication lookup.** Add a DB
  index on `(account_id, date, amount)` (and/or a normalised-description
  hash column) so import dedup (design.md data-flow step 5) is an indexed
  lookup, not an O(n·m) scan of existing rows for every imported row.
  Target phase: post-MVP perf (after P05 — FIBR-0007 ships the un-indexed
  MVP dedup by design; index it when a large account measures slow).
  Dependencies: FIBR-0007. Lanes: data, perf. Kind: perf.
  Source: user-request-2026-07-01.
  Resolved 2026-07-17 (commit 6c74966): the dedup lookup is now an indexed probe via the composite transactions(account_id, occurred_on, amount_minor) index (shipped under FIBR-0098). design.md's un-indexed MVP dedup is now index-backed.

- 📋 [FIBR-0027] **SQL-side dashboard aggregation + incremental refresh.**
  Compute dashboard summaries / charts with SQL `GROUP BY` rather than
  Python loops, and refresh incrementally on a single-row edit instead of
  a full recompute; add supporting indexes (`date`, `category_id`). Keeps
  the dashboard fast at tens of thousands of transactions. Target phase:
  P10. Dependencies: FIBR-0012. Lanes: reporting, perf. Kind: perf.
  Source: user-request-2026-07-01.

- 📋 [FIBR-0028] **Virtual table model for the transaction list.** Back
  the transaction table with a `QAbstractTableModel` (lazy / virtual
  rows) rather than per-row widgets, so a large history scrolls smoothly.
  Target phase: P10. Dependencies: FIBR-0012. Lanes: ui, perf.
  Kind: perf. Source: user-request-2026-07-01.

---

- ✅ [FIBR-0071] **Add DB indexes for the import-dedup + count lookups (full-table scans today).**
  No CREATE INDEX anywhere in migrations.py. TransactionRepository.existing_for() (WHERE account_id, occurred_on, amount_minor) runs once per distinct (date, amount) bucket inside every import — N full scans; same for count_for_account / count_for_category / rules count_for_category. Fine at today's personal scale (design.md accepts it) but a multi-year vault degrades. A composite index on transactions(account_id, occurred_on, amount_minor) plus single-column indexes on account_id/category_id/statement_period_id would flatten it. Overlaps FIBR-0026 (indexed dedup lookup).
  Kind: perf.
  Source: indie-review-2026-07-10 (M-data3).
  Resolved 2026-07-17 (commit 6c74966): shipped together with FIBR-0098. The composite transactions(account_id, occurred_on, amount_minor) flattens existing_for() import-dedup + count_for_account; categorization_rules(category_id) covers the rules count_for_category. EXPLAIN QUERY PLAN test proves the dedup probe is an indexed search, not a scan.

- 📋 [FIBR-0097] **Virtualize the transaction tables — QTableWidget → QTableView + QAbstractTableModel.**
  Verified 2026-07-11: Home, Statements, and Rules use QTableWidget (ui/home.py, ui/statements.py, ui/rules.py), which builds a widget for EVERY cell — fine at 50 rows, sluggish at thousands. Migrate to QTableView + a QAbstractTableModel so rendering is virtualized (only visible rows built). Also a cleaner data/view separation that FIBR-0012 (sort/filter) and FIBR-0084 (movable/resizable columns) build on naturally. Sizeable refactor; own spec. Deps: FIBR-0051/0052 (the current widgets).
  **Layman:** Keep the transaction lists fast even with thousands of rows by only drawing the rows you can actually see.
  Kind: perf.
  Source: claude-suggestion-2026-07-11.

- ✅ [FIBR-0098] **Add database indexes on the hot query columns.**
  Verified 2026-07-11: the schema (migrations.py) declares NO indexes. Add them on the frequently-queried columns — transactions(occurred_on), transactions(account_id), transactions(category_id), transactions(statement_period_id) (+ any dedup/lookup key). A forward migration (current v7 -> v8). Speeds listing, filtering (FIBR-0012), cross-source dedup, and delete-cascade. Cheap, high-value. Deps: FIBR-0005/0006/0010/0052 (the columns).
  **Layman:** Add quick-lookup indexes so finbreak finds and filters transactions fast as your history grows.
  Kind: perf.
  Source: claude-suggestion-2026-07-11.
  Resolved 2026-07-17 (commit 6c74966): v9->v10 forward migration adds five indexes on the hot columns — transactions(account_id, occurred_on, amount_minor) [composite; its account_id prefix also serves count_for_account, so no redundant standalone account_id index], transactions(occurred_on), transactions(category_id), transactions(statement_period_id), and categorization_rules(category_id) [the rules half of the category-delete blast radius]. Pure-DDL, atomic (one owned transaction; a wedged build rolls back to a re-openable v9). Subsumes FIBR-0071 + FIBR-0026. New tests/features/db_performance/ suite; full gate green.

- 📋 [FIBR-0099] **Faster cold start — PyInstaller --onedir inside the AppImage (skip per-launch extraction).**
  Verified 2026-07-11: the release build uses PyInstaller --onefile (scripts/_build-smoke-in-container.sh:85), which re-extracts the whole bundle to /tmp on EVERY launch (adds seconds of cold-start latency). Since the AppImage is ITSELF a self-contained mounted container, freeze with --onedir and place the dir inside the AppDir — the app then runs directly, no per-launch extraction. Transparent to the user; measure before/after start time and confirm the FIBR-0003 clean-room bundling proof still passes. Deps: FIBR-0003/FIBR-0054 (build pipeline).
  **Layman:** Make the app open faster by not unpacking itself every single time you launch it.
  Kind: perf.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0104] **Move slow statement import onto a worker thread (responsive UI + native overlap).**
  User idea (multi-threading for performance). Honest framing: Python's GIL means threading helps RESPONSIVENESS + native-code overlap, NOT pure-Python CPU parallelism. The app already threads its two slow blocking ops correctly (Argon2 key derivation via DeriveWorker; network via UpdateCheck/DownloadWorker — both native/GIL-releasing). Best next win: move IMPORT (pdfplumber text extraction, in-memory pikepdf decrypt, CSV/OFX parse, dedup + commit) onto a QThread worker (reuse the ui/_worker.py DeriveWorker pattern) with a progress indicator — today it runs ON THE UI THREAD (security-model / FIBR-0075 note: pdfplumber extract runs on the UI thread), so a large statement freezes the window. These ops are native-heavy (pdfplumber/pikepdf C++, SQLCipher C) so they RELEASE the GIL → genuine overlap with the GUI. CAVEAT: SQLite/SQLCipher connections are NOT shareable across threads — the worker needs its OWN connection to the vault (or marshal results back via signals). Pure-Python CPU hotspots (rule matching) won't benefit (GIL) — indexes (FIBR-0098) + virtualized tables (FIBR-0097) are the levers there. Deps: FIBR-0007/0008/0009 (import), reuses the QThread worker pattern; pairs with FIBR-0065 (non-blocking dialog discipline)."
  **Layman:** When importing a big statement, do the heavy reading on a background thread with a progress bar so the window stays responsive instead of freezing.
  Kind: perf.
  Source: user-suggestion-2026-07-11.

- 📋 [FIBR-0147] **Index the transfer_pairs cascade-delete FK columns.**
  Surfaced while shipping FIBR-0098. `transfer_pairs` (FIBR-0011) has two
  `ON DELETE CASCADE` FKs — `txn_a_id` / `txn_b_id` REFERENCES transactions(id) —
  but SQLite does NOT auto-index FK columns, so each transaction delete scans
  `transfer_pairs` for a match. `delete_for_statement` deletes many transactions
  at once (one statement), so a bulk statement delete is O(deleted × pairs). The
  table is small today (only confirmed/rejected pairs), so it was left OUT of the
  FIBR-0098 index set to stay in-lane. Add `CREATE INDEX` on
  `transfer_pairs(txn_a_id)` and `transfer_pairs(txn_b_id)` (a v10->v11 forward
  migration) if a large multi-year vault with many detected transfers measures a
  slow statement delete. Kind: perf.
  **Layman:** Make deleting a big statement fast even when transfers have been detected.
  Kind: perf.
  Source: claude-suggestion-2026-07-17 (deferred from FIBR-0098).

### 🧹 Warnings & tech debt

Every warning or error found during any work — tests, gate, build, tooling,
dependencies, review — is filed here (or the most fitting section) for later
investigation/resolution, even when third-party or non-blocking. A warning today
is a future error tomorrow.

- ✅ [FIBR-0043] **Silence/resolve ofxparse's bs4 findAll DeprecationWarning noise in the test run.**
  Surfaced by FIBR-0008 (2026-07-04). Running `tests/features/ofx_import/` emits ~100 `DeprecationWarning: Call to deprecated method findAll. (Replaced by find_all)` — raised INSIDE `ofxparse` 0.21 (`ofxparse.py` calling BeautifulSoup's deprecated `findAll`), not our code. Harmless today (tests pass), but: (a) it's log noise that masks real warnings, and (b) a future bs4 major could turn `findAll` into a hard error, breaking OFX import. ofxparse 0.21 is the current latest (lightly maintained), so there's no newer release to bump to. Options: a scoped pytest `filterwarnings` ignore for ofxparse's DeprecationWarning (documented, so it doesn't hide OUR deprecations); upstream a PR to ofxparse (findAll -> find_all); or, if bs4 ever breaks it, migrate to a maintained parser (ofxtools) — the escape hatch already noted in FIBR-0008 § Dependencies. Decide + apply.
  **Layman:** The OFX-import library prints ~100 harmless "this method is old" warnings whenever we run our tests; the app works fine, but the noisy warnings should be quietened or fixed at the source.
  Kind: investigate.
  Source: in-session-2026-07-04 FIBR-0008 build/test warnings.
  Resolved (2026-07-10): already delivered by FIBR-0058 — the scoped pytest `filterwarnings` ignore for "Call to deprecated method findAll.*" plus the `beautifulsoup4>=4.9,<5` pin are both live in pyproject.toml. This was the investigate twin of the FIBR-0058 chore; no additional code needed. Closing as superseded.

- ✅ [FIBR-0057] **Import wizard snapshots the target account at file-select — a later dropdown change is ignored.**
  ui/import_wizard.py `_select_file` (line ~255) does `self._account_id = self._account_combo.currentData()` and bakes it into the preview; the account combo lives on step 0 only and changing it after a file is chosen does not re-read or re-preview. Combined with the combo defaulting to the first account, a user who doesn't set the account BEFORE choosing the file (or wants to change it after) silently imports under the wrong account. Fix options: (a) read the account at commit time (decouple from the snapshot); (b) keep the account picker editable through the flow and re-run dedup/preview on change; (c) at minimum, disable the combo once a file is picked + surface the chosen account on the preview step so it's visible before commit. Prefer (a)+(c). Needs a reproduction test. Related to the FIBR-00xx edit-statement-account feature (which lets a user fix a mis-link post-import).
  **Layman:** When importing a statement, if you change which account it goes into AFTER picking the file, the app ignores the change and uses the first account (e.g. "Current"). This is how a credit-card statement can land on the wrong account.
  Kind: fix.
  Source: self-found-2026-07-09.
  Resolved (2026-07-09): the preview step now carries a destination-account picker that is the single source of truth for the committed account — seeded from the pick step at file-select, read live via _target_account_id() by every preview + the per-account PDF-password lookup, and user-correctable before the irreversible Import (changing it re-runs the dedup via ImportService.retarget). Cold-review fold: a remembered PDF password now follows a re-target onto the committed account. Tests: import_ FIBR0057 x3 (retarget re-dedups; preview exposes the destination; changing it re-targets the whole commit) + pdf_import FIBR0057 x1 (remembered password follows the corrected account). Gate green 348 passed/1 skipped, mypy 0, audit 0. Commits 4be777c + ba6d912.

- ✅ [FIBR-0058] **ofxparse emits BeautifulSoup findAll DeprecationWarnings (107 per test run).**
  The gate run shows 107 `DeprecationWarning: Call to deprecated method findAll. (Replaced by find_all) -- Deprecated since version 4.0.0` from ofxparse (ofxparse.py:445/449/454/949), which calls BeautifulSoup's long-deprecated `findAll`. It is inside the ofxparse dependency, not our code, so we can't fix the call directly. Options: (a) pin/track ofxparse for an upstream fix or a maintained fork; (b) filterwarnings in pytest config to quiet the known-3rd-party warning (documented, not a blanket ignore); (c) evaluate replacing ofxparse if it stays unmaintained. BeautifulSoup will eventually remove `findAll`, which would then break OFX import — so this is a latent breakage, not just noise. Investigate + decide.
  **Layman:** A dependency the app uses for one import format prints lots of "deprecated" warnings during tests. Harmless today, but noisy and a sign the dependency is aging.
  Kind: chore.
  Source: self-found-2026-07-09.
  Resolved (2026-07-09): investigated — ofxparse 0.21 is the latest PyPI release (unmaintained since 2023; no find_all fix to track), and bs4 4.15 still ships findAll as a deprecated alias (removal slated for bs4 5.0). Two-part root-cause fix, not a blanket silence: (a) scoped pytest filterwarnings ignoring ONLY "Call to deprecated method findAll..." (our own future deprecations still surface); (b) beautifulsoup4>=4.9,<5 pin in [project].dependencies — the latent-breakage guard, since an unpinned bs4 5.0 (findAll removed) would break OFX import; bs4 is only reached transitively via ofxparse. Gate 352 passed, 0 warnings (was 107); pip check clean. Option (c) — replacing ofxparse — deferred (large; FIBR-0008 built OFX import around it); revisit if ofxparse stays unmaintained when bs4 5.0 becomes necessary. Audit 0 (ruff/bandit skipped — pyproject-only). Config-only chore, no multi-agent review warranted. Commit below.

- ✅ [FIBR-0060] **Window geometry restore + Center Window don't work on Wayland (FIBR-0052 was X11-assumed).**
  Reported on KDE Wayland. Root cause: FIBR-0052 (INV-5 geometry persistence, INV-6
  Center window) assumed X11 semantics. On Wayland the compositor owns window
  placement — an app cannot set/restore its own POSITION, and move()/setGeometry-pos
  is a no-op — so Center Window can never work and position-restore is impossible;
  size-restore via restoreGeometry is also unreliable before first map. Verified:
  saving works (~/.local/share/finbreak/window.ini has a geometry key), and
  _restore_geometry calls restoreGeometry before show — but Wayland ignores the
  position, and the FIBR-0052 tests only asserted the QSettings round-trip (offscreen
  platform), never real WM behaviour, so they passed while the feature is broken for
  the user. Fix plan: (a) restore SIZE explicitly via resize() (Wayland allows size
  requests) and confirm it sticks; (b) on Wayland, disable/grey Center window +
  position-restore with a tooltip (or drop them there) since the compositor centres
  windows itself — keep them on X11 where they work; (c) detect the platform
  (QGuiApplication.platformName()); (d) add a test that exercises the real behaviour,
  not just the settings round-trip. My code (FIBR-0052) — own it. Related to the
  sole-author no-Wayland-coverage gap.
  **Layman:** The app doesn't remember its window size/position between runs, and Window → Center Window does nothing. On modern Linux (Wayland), apps aren't allowed to position their own windows, so parts of this can't work the way they were built.
  Kind: fix.
  Source: user-report-2026-07-09.
  Resolved (2026-07-09): platform-aware geometry. _is_wayland()/_kde_wayland()/_center_supported() gate behaviour. On Wayland the SIZE is restored via resize() from a bare window_size key (the compositor honours a size request; restoreGeometry's size is unreliable pre-map) — matching the SystemManager reference. Center window is IMPLEMENTED on KDE Wayland via KWin's scripting D-Bus API (QtDBus loadScript/start/unloadScript of a PID-matched centring script — the SystemManager technique, ported to QtDBus so no dbus-send subprocess); disabled with a tooltip on other Wayland compositors (no app-usable placement API); X11/Windows/macOS keep move(). Position-restore on launch stays compositor-owned on Wayland (as SystemManager also accepts). LIVE-VERIFIED on the user's KDE Wayland: window centres exactly (work-area offset dcx=0 dcy=0). Tests: FIBR0060 x4 (size restore; KWin dispatch on KDE; disabled+no-op on non-KDE; enabled off Wayland) via monkeypatched _is_wayland/XDG_CURRENT_DESKTOP. Cold-review fold: temp-file-leak-on-write-failure + Plasma-version doc accuracy. Gate green 352 passed/1 skipped, mypy 0, audit 0. Commits 36e0ea1 + review fold. Note: the FIBR-0052 INV-5/INV-6 tests only asserted the QSettings round-trip (offscreen), never real WM behaviour — now both platform branches are exercised.

- ✅ [FIBR-0061] **mypy is not enforced by the gate, and `mypy src tests` reports 4 pre-existing type errors in test files.**
  Found while closing FIBR-0059. `scripts/ci-local.sh` (the gate, run by the
  pre-push hook + ci.yml) runs ruff / format / bandit / pip-audit / gitleaks /
  pytest but NOT mypy — so the journal's repeated "mypy 0" claims came from ad-hoc
  manual runs (often `mypy src`, not the config's `files = ["src", "tests"]`), and
  type errors in the test tree were never gated. `mypy src tests` (mypy 2.1.0)
  currently reports 4: tests/features/settings/test_settings.py:70/75/80 (a
  findChild helper returning QComboBox|None / QDialogButtonBox|None dereferenced
  without a None-guard — FIBR-0055 code) and tests/features/app_shell/
  test_app_shell.py:83 (a fake QThread subclass whose start() override signature is
  incompatible). None are runtime bugs (test-only typing), but they hide real
  regressions. Fix: (a) add a mypy stage to ci-local.sh so it's actually enforced;
  (b) fix the 4 (cast/assert the findChild Optionals; align the fake start()
  signature). My code (sole author). NB FIBR-0059's own new src is mypy-clean.
  **Layman:** The type-checker (mypy) that catches whole classes of bugs isn't actually run by the automated quality gate, and running it by hand turns up 4 small type issues in the test code that have gone unnoticed.
  Kind: chore.
  Source: self-found-2026-07-09.
  Resolved (2026-07-09): added a `mypy` stage to `scripts/ci-local.sh` (after gitleaks, before pytest — bare `mypy` uses the config's `files = ["src","tests"]`), so CI (which invokes ci-local.sh) now enforces it too; the dev group already pins `mypy==2.1.0`. Fixed the 4 test-tree errors: `assert ... is not None` guards on `_combo`/`_click_save`/`_click_cancel` in `tests/features/settings/test_settings.py`, and aligned `_StubWorker.start` to the `QThread.start(self, priority=...)` signature in `tests/features/app_shell/test_app_shell.py`. Gate green: 366 passed / 1 skipped, mypy clean (59 files), shellcheck 0.

- ✅ [FIBR-0062] **Test-audit: hoist duplicated paths/service/_PW fixtures + connection-proxy helpers to shared conftest.**
  All 4 /test-audit chunks flagged this. The identical `paths` fixture, `_PW` literal, `_FailAt*`/`_StandInVault` connection-proxy classes, and `_acct`/`_wizard`/`_default_id`/`_pump_deferred_delete`/`_two_accounts` helpers are copy-pasted across ~9 tests/features/* files (Rule-of-Three well exceeded). Extract to tests/conftest.py (paths + _PW import + a raising_proxy(real, trigger, message) factory). The window_ini autouse fixture was already hoisted 2026-07-10 as part of the CRITICAL isolation fix.
  **Layman:** Lots of test files copy-paste the same setup code; move it to one shared place so a change only needs editing once.
  Kind: test.
  Source: test-audit-2026-07-10.
  Resolved (2026-07-10): hoisted the copy-pasted test infrastructure to tests/conftest.py — the `paths` fixture (was duplicated in 11 feature suites), the `_PW` literal (3 remaining local copies → imported from conftest, joining the 8 that already did), a generic `raising_conn(real, trigger, message, on=)` factory + a `StandInVault` class replacing 7 bespoke `_FailAt*`/`_StandInVault` wedge classes across 5 suites (the migration + service atomicity-rollback tests), and the `_acct` (5 copies) + `_pump_deferred_delete` (3 copies) helpers. Deliberately NOT hoisted (Rule-of-Three not met / not identical): the `service` fixture (varies — some suites first_run, some don't), `_default_id` (varying signature: service vs vault), `_two_accounts` (single-site). Gate green 440 passed/1 skipped, mypy 0 (fresh cache), ruff clean.

- ✅ [FIBR-0063] **Test-audit: parametrize repeated single-assert tests + split multi-claim tests.**
  Convert the four standard_bank INV11 checksum/completeness tests and the three INV2a per-family detection asserts to @pytest.mark.parametrize(ids=...) so one failure doesn't mask siblings; same for the import_ bad-mapping-config loop (test_import.py:263). Consider splitting statements INV5a's 7-claim test (esp. the plaintext-leak security checks).
  **Layman:** Some tests bundle several checks in one; splitting/parametrizing them makes a failure point at the exact broken case.
  Kind: test.
  Source: test-audit-2026-07-10.
  Resolved (2026-07-10): parametrized the genuine bundled-assert/loop tests so one failure can't mask siblings — standard_bank test_INV2a_each_family_detected_by_its_own_signature (3 bundled asserts → @pytest.mark.parametrize ids=family_b/d/c) and import_ test_service_rejects_bad_mapping_config (the `for bad in (...)` loop → parametrized test_service_preview_rejects_bad_mapping_config ids=no_amount_style/missing_column/both_styles; the distinct save_profile path split into its own test). Split the statements INV5a omnibus: the plaintext-leak SECURITY checks (no txn description/amount in the geometry INI) now live in a dedicated test_INV5a_no_transaction_data_leaks_to_plaintext_ini so a geometry-persistence regression can't mask a data leak. The four standard_bank INV11 checksum/completeness tests were left as-is — they are already SEPARATE test functions (independent failure points), so parametrizing would only DRY, not fix masking. Gate green, ruff clean.

- ✅ [FIBR-0064] **Test-audit: add tests for untested error branches surfaced by the audit.**
  Untested branches: UnlockDialog SchemaVersionError (HIGH); FirstRunDialog create-failure except; AuthService.unlock() password-wipe-on-failure; CategoryService._require_parent ValueError; categorization.move_rule unknown rule_id; import_wizard _decrypt_pdf/_extract_pdf_tables friendly-error paths (wizard-level); StatementService.list_statements ordering contract; standard_bank corrupt-PDF wizard message (assert substring, not != ''); and the 5 auto-lock 'must not raise' tests should gain a concrete post-click state assertion.
  **Layman:** A few error-handling paths in the app have no test; add regression tests so a future change can't silently break them.
  Kind: test.
  Source: test-audit-2026-07-10.
  Resolved (2026-07-10): added regression tests for the untested error branches + strengthened the weak ones. New tests: move_rule unknown-id no-op (categorisation); _require_parent bad-parent-id ValueError (categories — the None-parent branch was already covered); list_statements import-recency ordering (statements); AuthService.unlock password-wipe on load_params failure (vault/security-INV-3); UnlockDialog SchemaVersionError 'newer version' message (vault, driven via _on_derived to skip Argon2); FirstRunDialog 'Could not create the vault' create-failure (vault). Strengthened: the standard_bank corrupt-PDF test now asserts the friendly-message SUBSTRING (not != '') — which REVEALED + FIXED a real UX bug: the wizard caught PdfError but showed str(exc) (raw pikepdf 'unable to find trailer dictionary...') rather than the friendly message; added _show_pdf_read_error() mapping PdfError→friendly at the 3 PDF catch sites (import_wizard). The 5 auto-lock 'must not raise' tests (4 categorisation INV14 + statements reassign) each gained a concrete post-click state assertion (row unchanged / rule-created / error-empty / txn-stayed-on-account). Gate green 452 passed/1 skipped, mypy 0, ruff clean.

- ✅ [FIBR-0065] **Fix the auto-lock-during-modal-dialog crash (reproduced HIGH).**
  REPRODUCED (Qt DeferredDelete is processed inside a nested exec() loop): an idle auto-lock fires while a content-widget dialog is exec()-blocking; MainWindow._lock() -> _clear_live() -> workspace.deleteLater() destroys the dialog's parent chain during that nested loop, so the post-exec() call (home.py CategoryPickerDialog.selected_category_id(); import_wizard.py PasswordDialog.password()/remember(); also statements.py, rules.py) hits a deleted C++ object -> RuntimeError, which the VaultLockedError guards do NOT catch. The existing guards only cover 'dialog closes BEFORE lock', not 'lock DURING exec()'. Needs its own spec+cold-eyes+TDD cycle (lifecycle-critical security code). Proposed approach: either convert content-widget dialogs to the shell's non-blocking setModal(True)+show() pattern (FIBR-0051 D2 rejected exec() for exactly this), OR a MainWindow modal-registry that wipes the key immediately (security preserved) but defers the UI teardown until the nested loop unwinds. Recommend prioritising ABOVE FIBR-0054.
  **Layman:** If the app auto-locks itself while a small pop-up (pick a category, edit a rule, enter a PDF password) is open, it can crash instead of locking cleanly.
  Kind: fix.
  Source: indie-review-2026-07-10 (full-codebase sweep, H-B).
  Started 2026-07-10. Approach chosen with the user: convert the remaining blocking exec() content-dialogs to the shell's non-blocking setModal(True)+show()+signal pattern (matches FIBR-0051 D2). Spec → cold-eyes → TDD next.
  Resolved 2026-07-10. Converted the 6 blocking exec() content-widget pop-ups (home set-category + learning offer, rules add/edit, statements reassign, import-wizard PDF password) to the non-blocking show_modal (setModal+show()+signal) pattern; PDF password loop → the _try_decrypt state machine. Spec /cold-eyes-converged (5 loops); TDD: dialog_lifecycle INV-1 grep + a real _lock()-during-open-PDF-prompt regression (INV-2 guard-less path) + parity ripple. Gate green 437 passed/1 skipped, mypy 0; /audit 0; a cold code-review lane confirmed the D5 semantics faithful (doc-nits only, folded). Tag FIBR-0065-complete.

- ✅ [FIBR-0066] **Refactor the 6x duplicated BEGIN/COMMIT/ROLLBACK transaction boilerplate into one owned-transaction helper.**
  Identical BEGIN / try:...commit() / except: rollback(); raise appears 6x in services (categorization apply_rules/set_manual_category/move_rule, categories delete_category, import_ commit_import, statements delete/reassign) and 6x in migrations.py. A vault.owned_transaction() context manager would collapse both and remove the risk a 7th call site copies it with a subtly wrong exception class. Load-bearing atomicity code — do carefully with tests.
  Kind: refactor.
  Source: indie-review-2026-07-10 (M-C3, corroborated x2: crypto-vault migrations.py + core-services).
  Resolved (2026-07-10): extracted owned_transaction(conn) context manager into new src/finbreak/db.py — the single BEGIN…COMMIT / ROLLBACK-and-reraise boundary. Replaced all 13 hand-rolled sites: 7 services (categorization move_rule/apply_rules/set_manual_category, categories delete_category, import_ commit_import, statements delete_statement/reassign_account) + 6 migrations (v2→v7). Deliberately a free function on a bare Connection, not a Vault method, so migrations.py (which vault.py imports) can use it without an import cycle. No behavior change — all atomicity tests (import INV-7 rollback, migration atomicity, delete-cascade INV-7, move_rule two-row swap) stay green. mypy 0, 248 affected tests pass.

- ✅ [FIBR-0067] **Widen the Standard Bank _MONEY regex to accept ungrouped 4+-digit amounts, then re-validate against the real statements.**
  standard_bank.py _MONEY = r'(?<![\d.,])\d{1,3}(?:[.,]\d{3})*[.,]\d{2}(?!\d)' fails to match an amount >= 1000 printed WITHOUT a thousands separator (e.g. '1500.00' -> no match), so a statement with an ungrouped opening/closing balance fails with the generic mis-parse. Degrades SAFELY (friendly error, no corruption); none of the 6 validated real statements exhibit it. NOT folded in the audit sweep: the naive fix (\d{1,3}->\d+) risks a NEW false positive (a dotted date like 2026.07.15 -> spurious '2026.07' token), and this parser was validated end-to-end on a real-statement corpus not available in-session. Fix + re-validate against all 6 real statements as its own item.
  Kind: fix.
  Source: indie-review-2026-07-10 (M-imp1).
  Blocked (2026-07-10): deliberately NOT fixed in the audit-fix sweep — the SB _MONEY regex is a validated parser and there is no real-statement corpus in-session to re-validate against. A naive widening to accept ungrouped 4+-digit amounts risks a dotted-date false positive (e.g. matching a date fragment as money), which would silently mis-parse. Needs real anonymised sample statements (same blocker as FIBR-0074's dedicated ABSA/Nedbank/FNB readers) to widen + re-run the six-statement checksum corpus. Keep planned; revisit when sample statements are available.
  Resolved (2026-07-10): UNBLOCKED — the user provided the six real Standard Bank statements (one per family: Credit Card/Current/Home Loan/Money Market/RCP/Savings) + the password. Reproduced first: all six PASS with the current regex, and ZERO ungrouped 4+-digit tokens appear (SB always groups thousands). Widened _MONEY to also accept an ungrouped run: `(?:\d{1,3}(?:[.,]\d{3})*|\d{4,})[.,]\d{2}`, with a `(?![.,]?\d)` tail guard against the dotted-date false positive the earlier defer flagged (2025.07.21 rejected; 3-decimal rates still rejected). Re-validated against all six real statements in a throwaway harness — EXACT same txn counts (53/82/27/20/30/3), zero regression. Added a synthetic parametrized _MONEY unit test (grouped/small/ungrouped-4/7-digit/reject-3dp-rate/reject-dotted-date/iso-date). The real statements + password were NEVER committed (validated in scratchpad, since deleted; the committed test uses synthetic strings only — testing.md §6). Gate green 460 passed/1 skipped, mypy 0, ruff clean.

- ✅ [FIBR-0068] **Promote the _set_combo(combo, value) helper to a shared UI util and dedup the 7x findData+setCurrentIndex idiom.**
  Kind: refactor.
  Source: indie-review-2026-07-10 (M-dlg4).
  Resolved (2026-07-10): extracted the guarded combo-preselect idiom (index = combo.findData(v); if index >= 0: combo.setCurrentIndex(index)) into select_combo_data() in new src/finbreak/ui/_widgets.py, and converted the 6 sites (settings/accounts/categories type combos + rules/category_picker/account_picker id combos). IMPORTANT distinction surfaced, not forced: kept DISTINCT from ImportWizardWidget._set_combo, which is UNGUARDED by design — the wizard wants a saved-profile column absent from the current file to CLEAR the combo (force a re-pick), whereas the picker/dialog sites keep the current selection when a value isn't found. Merging them would have been a silent behavior change. mypy 0, 165 UI tests pass.

- ✅ [FIBR-0069] **Extract a _signed_balance_from_tokens helper for the 4x duplicated Standard Bank balance-token parse.**
  Kind: refactor.
  Source: indie-review-2026-07-10 (M-imp3).
  Resolved (2026-07-10): extracted _signed_balance(token, fmt) in standard_bank.py — the single home of the '-parse if _is_negative else parse' idiom. Replaced 7 occurrences (the reviewer's 'x4' undercounted): the brought-forward/opening captures (_capture_opening x2, credit-card opening, _anchor_balance) + the per-row balance in Families A/B/D. Named _signed_balance (a single token) rather than the tentative _signed_balance_from_tokens, since every site passes one token. No behavior change — all family checksums + per-row sign gates stay green (83 SB/PDF tests). ruff/mypy 0.

- ✅ [FIBR-0070] **Decide the fate of the unwired ImportProfileRepository.list_all() (build a manage-saved-profiles screen, or remove it).**
  list_all() has zero callers in src/ — the wizard only auto-matches by signature and saves. Either an intended 'manage saved import profiles' feature was never wired up, or it is dead weight. Decide feature-vs-delete.
  Kind: chore.
  Source: indie-review-2026-07-10 (M-data1).
  Loop-2 review (2026-07-10): ImportProfileRepository.get() is also unwired in src/ (only test callers) — the other half of the never-built manage-profiles screen. Fold get() into this decision (wire both up, or remove both).
  Resolved (2026-07-10): KEEP (user rule: 'if we'll use it later, leave it'). No roadmap item commits to a manage-profiles screen, but the saved-import-profiles feature is shipped (FIBR-0007) and a 'manage saved profiles' view (see/rename/delete accumulated bank layouts) is its natural completion — a plausible later use, not a far-fetched hypothetical. list_all/get (+ update) are the read/edit API that view needs; removing tested working methods only to re-add them is negative-value churn (and would force rewriting a legitimate upsert test's observation). Neutralised the audit's 'dead weight?' concern by DOCUMENTING intent in the ImportProfileRepository module docstring (kept-not-deleted, remove only if the view is dropped from the roadmap). No behavior change.

- ✅ [FIBR-0075] **Bound PDF per-page decompressed content size (decompression-bomb / zip-bomb vector).**
  Caps today are whole-file bytes (16 MiB), page count (500), and extracted row count (100k) — none bound the DECOMPRESSED size of a page's Flate-compressed content stream, so a small in-cap PDF can expand to GBs before extract_tables()/extract_text() returns (on the UI thread). security-model.md §5 explicitly names FIBR-0009 as responsible for THIS vector, but the code doesn't implement it — a real spec-vs-code gap. Non-trivial: pdfplumber/pdfminer don't easily expose a streaming size bound; likely needs a pdfminer-level limit or a subprocess with rlimits. Investigate + implement, or document the residual risk explicitly.
  **Layman:** A small, valid PDF whose page decompresses to gigabytes could hang or OOM the app when imported.
  Kind: security.
  Source: indie-review-2026-07-10 loop-2 (statement H2).
  Resolved (2026-07-10): assessed + documented as accepted residual risk (the roadmap-sanctioned option; user deferred the call to me). security-model.md INV-5b previously implied FIBR-0009 bounds the decompression/zip-bomb vector — the code does NOT (caps are file-size 16 MiB / 500 pages / 100k rows; none bound a page's DECOMPRESSED Flate stream). INV-5b now states this honestly: the decompressed-size residual is ACCEPTED for a local single-user app (threat = the user opening a file they chose, not a server ingesting untrusted uploads); the robust fix (extraction in a memory-capped subprocess — POSIX RLIMIT_AS / Windows Job Objects) is disproportionate + cross-platform-heavy, and pdfplumber/pdfminer expose no cheap in-process streaming bound. T5 row annotated with the residual + pointer. Revisit if PDFs ever arrive from an untrusted channel. No code change — a spec-vs-code gap closed by making the claim honest.

- ✅ [FIBR-0076] **Single-instance / busy_timeout handling so two app copies don't crash with a raw OperationalError.**
  _connect sets PRAGMA key + foreign_keys only; SQLite default busy_timeout is 0. Two instances (or a slow backup/AV holding a read lock) make the second write raise sqlite3.OperationalError uncaught -> unhandled traceback. Add PRAGMA busy_timeout and/or an explicit single-instance guard (QLocalServer / lockfile) at the app layer.
  Kind: fix.
  Source: indie-review-2026-07-10 loop-2 (crypto M2).
  Resolved (2026-07-10): _connect now issues `PRAGMA busy_timeout = 5000` (vault.py) — a second instance or a slow backup/AV holding a transient lock now serialises via SQLite's locking (waiting up to 5s) instead of the second write raising a raw sqlite3.OperationalError. This fixes the reported crash symptom; SQLite's file locking already guarantees no corruption under concurrent access, so the busy_timeout is sufficient. A QLocalServer/lockfile single-instance guard (preventing two windows at all) was considered but is a UX nicety, not required for crash-safety — deliberately NOT built (simplicity-first). Regression test asserts the PRAGMA value.

- ✅ [FIBR-0077] **Explicitly pin PRAGMA cipher_use_hmac = ON in _connect (defense-in-depth for INV-1 tamper-evidence).**
  security-model.md INV-1 states tamper-detection as a code guarantee, but _connect never sets cipher_use_hmac — it rests entirely on sqlcipher3-binary==0.6.0's SQLCipher-4 default. A future dep bump changing the default would silently weaken it (global rule §5). NOTE: FIBR-0004 D4 deliberately chose to ASSERT the default rather than re-configure it (test-covered), so this is a spec-level decision to reconsider, not a drive-by — needs a D4 revisit before changing.
  Kind: security.
  Source: indie-review-2026-07-10 loop-2 (crypto M4, flagged x2).
  Resolved (2026-07-10): D4 revisit conclusion — pin it. _connect now issues `PRAGMA cipher_use_hmac = ON` explicitly right after `PRAGMA key` (vault.py), so INV-1 tamper-evidence is correct-by-construction rather than resting on sqlcipher3-binary's SQLCipher-4 default (which a future dep bump could flip, global rule §5). Every vault is created with the default ON, so pinning ON can never mismatch an existing file. FIBR-0004 D4 spec text updated with the revisit note; the existing INV-1 assert stays as the regression check. New test_connection_pins_hmac_and_busy_timeout covers it. Gate green.

- ✅ [FIBR-0078] **Move the Standard Bank row cap before the per-family parse (bounds computation, not just the result).**
  standard_bank.parse checks len(result.drafts) > _MAX_PDF_ROWS only AFTER _parse_family_* has run full regex + Decimal parsing over every region line — a crafted PDF with millions of transaction-shaped lines does all that work before rejection. pdf_importer.py checks its cap earlier (cheaper). Add a cheap pre-parse region-line count guard. NOTE: the current ordering is spec-consistent (FIBR-0050 Deliverable 1), so changing it needs a FIBR-0050 spec update.
  Kind: perf.
  Source: indie-review-2026-07-10 loop-2 (statement H3).
  Resolved (2026-07-10): standard_bank.parse now rejects len(region_lines) > _MAX_PDF_ROWS immediately after building region_lines — before _detect_number_format and the per-family regex/Decimal pass — so a crafted PDF with millions of transaction-shaped region lines is refused before that expensive work (bounds the computation, not just the result). The exact post-parse len(result.drafts) > _MAX_PDF_ROWS cap (FIBR-0050 Deliverable 1 / INV-14) is retained for precision (Family C de-interleaves ~2 drafts/line). FIBR-0050 spec Deliverable updated. The existing over-cap monkeypatch test (INV-14) now exercises the early guard with the same friendly ValueError; 83 SB/PDF tests green, ruff clean.

- ✅ [FIBR-0079] **Gate RuleEditDialog OK on a selectable category (zero-leaf-categories edge) + honest selected_category_id return type.**
  If a user deletes every leaf category, RuleEditDialog's combo is empty, selected_category_id() returns None (despite its -> int hint), and OK stays enabled -> add_rule(pattern, None) surfaces the confusing 'a category must be a leaf, not a Type' instead of 'create a category first'. Gate OK on combo.count() > 0 (or block Add/Edit when leaf_categories() is empty) and type selected_category_id() as int | None. FIBR-0010 D13's 'no ValueError reaches a caller through the dialog' silently fails to cover zero-leaves.
  Kind: ux.
  Source: indie-review-2026-07-10 loop-2 (core-services + ui-dialogs M2).
  Resolved (2026-07-10): RuleEditDialog._sync_ok now also requires self._category.count() > 0, so OK stays disabled with zero leaf categories; selected_category_id() typed int | None (honest). RulesWidget._on_add blocks up front with a "Create a category first, then add a rule." message when leaf_categories() is empty — the reachable path (the _on_edit + learning paths can't hit zero-leaves, since an existing rule / a manual pick both imply a live category). _apply_add/_apply_edit/_apply_learned_rule add a defensive None guard (narrows for the int-typed add_rule/update_rule). FIBR-0010 D13 spec updated to cover the edge. TDD: 2 red→green tests (dialog OK disabled with empty leaves + selected_category_id None; Add blocked + message shown). mypy 0, 74 tests pass.

- ✅ [FIBR-0080] **Route the two hand-rolled settings reads through SettingsRepository.get.**
  services/transactions.py read_minor_unit_exponent + TransactionService.base_currency hand-roll SELECT value FROM settings WHERE key=... instead of SettingsRepository(conn).get(key) (already used by auth.py). Reuse-before-rewrite (CLAUDE.md §3); a typo'd key in one copy has no lint signal. read_minor_unit_exponent needs None/int-cast handling.
  Kind: refactor.
  Source: indie-review-2026-07-10 loop-2 (data M-1).
  Resolved (2026-07-10): read_minor_unit_exponent + TransactionService.base_currency now route through SettingsRepository(conn).get(key) (services/transactions.py) instead of hand-rolling the SELECT — one seam for the key strings (reuse, CLAUDE.md §3). cast(str, value) preserves the v1-invariant 'always present' assumption per the repo's assert-over-can't-happen convention. mypy 0, 171 affected tests pass.

- ✅ [FIBR-0081] **Small type/doc debt: _on_move Literal typing, _selected_row dedup, FIBR-0007 stale INV-7 insert-order narrative.**
  (1) ui/rules.py _on_move takes direction:str + a type:ignore against move_rule's Literal['up','down'] — type the param as Literal to drop the workaround (global rule §1). (2) _selected_row is byte-identical in rules.py + statements.py (2 sites — extract on the 3rd). (3) FIBR-0007 spec's INV-7 test narrative describes the OLD insert order (transactions-before-period); FIBR-0052's statement_period_id FK reversed it (period-first) — update the spec text (or a FIBR-0052 addendum) so a reader doesn't reason about a stale order.
  Kind: doc-fix.
  Source: indie-review-2026-07-10 loop-2 (misc LOW).
  Resolved (2026-07-10): (1) ui/rules.py _on_move now types direction as Literal['up','down'], dropping the # type: ignore[arg-type] against move_rule. (3) FIBR-0007 spec INV-7 narrative corrected with a FIBR-0052 addendum — commit_import inserts the period row first (statement_period_id FK) then the transactions batch, and the wedge test raises on the transactions INSERT. (2) _selected_row dedup deliberately NOT done — only 2 sites, Rule-of-Three defers extraction to the 3rd (CLAUDE.md §3).

- 📋 [FIBR-0102] **Tighten mypy toward strict.**
  Verified 2026-07-11: [tool.mypy] sets only python_version + per-module stub-ignores — NOT strict. Enable strict (or stage it: disallow_untyped_defs, warn_return_any, disallow_any_generics, no_implicit_optional) to catch a class of bugs at the type layer — valuable for a money app. Incremental: turn flags on one at a time, fix the fallout, keep the gate green each step. Deps: none (gate/CI config).
  **Layman:** Turn on stricter automatic type-checking to catch more bugs before they ship.
  Kind: refactor.
  Source: claude-suggestion-2026-07-11.

- 📋 [FIBR-0103] **Consolidate presentation formatting into one module.**
  FIBR-0083 introduces src/finbreak/datetime_format.py (date/time display). Fold the existing amount/currency QLocale formatting (ui/_amount.py::_format_amount -> QLocale.toCurrencyString; already lifted out of ui/home.py and now imported by 8 modules, so the remaining work is the fold into a shared formatting package) into a shared formatting package alongside it, so all presentation logic is centralised + unit-tested in one place (Rule of Three: date + currency + future). Deps: FIBR-0083 (lands the first formatter). Small refactor; do AFTER FIBR-0083 ships.
  **Layman:** Keep all the 'how numbers and dates look' code in one tidy, tested place.
  Kind: refactor.
  Source: claude-suggestion-2026-07-11.

- ✅ [FIBR-0141] **CategoryService.update_category has no descendant-cycle guard — re-parenting a category under its own child creates a cycle.**
  Found during the FIBR-0138 close (indie-review). `update_category`
  (`src/finbreak/services/categories.py`) blocks re-parenting a *root* and
  requires an existing parent, but does NOT reject moving a category under
  one of its own descendants — so X→Y→X cycles are reachable via the UI.
  `categorization.type_of` already fails loud (ValueError) on such a cycle,
  and FIBR-0138's `drill_down` was hardened to stay total against it, but
  the ROOT CAUSE is the missing guard here. Fix: in `update_category`,
  reject a `parent_id` that is the subject itself or any of its
  descendants (ascend the prospective parent's chain; if the subject is
  encountered, raise ValueError). Add a reproduce-first test. Small,
  self-contained.
  **Layman:** You can accidentally make the category tree loop back on itself (put a group inside one of its own sub-groups), which confuses the parts of the app that walk the tree; the app should refuse that move.
  Kind: fix.
  Source: indie-review-2026-07-14 (FIBR-0138 close).
  Resolved 2026-07-17: added a `_reject_cycle` guard to `CategoryService.update_category` (mirrors the depth-safe ascend-with-`seen` idiom in `categorization.leaf_categories_grouped`) — ascends from the prospective parent to the root and raises ValueError if the subject appears in that chain, so re-parenting a category under itself or one of its own descendants is refused; the `seen` set keeps the walk total against a pre-existing corrupt cycle. Reproduce-first TDD in `tests/features/categories/` (INV-5: self-parent, direct child, deep descendant all rejected; legitimate cross-branch move still succeeds). Adapted the pre-existing `categorisation` corrupt-cycle test to inject the cycle at the repository layer (below the guard) since the service now refuses to build one. Note: today's category-manager parent picker only offers the two Type roots, so the cycle was reachable via a direct service call, not that UI — the guard is the service-layer contract boundary. Gate green 1083/1, mypy 0.

- ✅ [FIBR-0150] **security-model.md header provenance line is stale (skips FIBR-0054/0131/0133).**
  The header (docs/security-model.md L3-5) reads "amended through FIBR-0014 (2026-07-13 — T11: separate-password backup recovery)" yet the body already carries FIBR-0054 (update-flow / INV-8 egress) and FIBR-0131/FIBR-0133 (Windows update / SignPath) content added since, without a header bump. Treat the line as a "most-recent material amendment" marker and either (a) document that semantics in the header itself, or (b) backfill the missed provenance. Surfaced by the FIBR-0095 /cold-eyes lane B (loop 4). Low-priority doc hygiene; FIBR-0095 bumps the line to itself as part of its own edit.
  **Layman:** The security document's "last updated by" note names an old change and skips several newer ones — a quick tidy so it reflects reality.
  Kind: doc-fix.
  Source: cold-eyes-2026-07-18 FIBR-0095 lane-B.
  Resolved (2026-07-26, debt sweep): both halves are now in place. The
  header (docs/security-model.md L3-8) reads "amended through FIBR-0096
  (2026-07-21 — INV-13: signed SHA256SUMS + CycloneDX SBOM)", so the
  FIBR-0014 staleness is gone; and remedy option (a) is documented
  verbatim in the header itself — "This line names the most-recent
  material amendment, not a full history." Landed incidentally via the
  FIBR-0095/FIBR-0096 edits rather than as its own change, which is why
  the bullet was never flipped. Verified against source, not recalled.

- ✅ [FIBR-0165] **CSV import no longer crashes on a structurally-broken file — csv.Error is translated to a friendly ValueError.**
  indie-review (importers lane), MEDIUM. csv.DictReader parses lazily during iteration, so a field over csv.field_size_limit (e.g. an unterminated quote) raised csv.Error from the `for` line — outside the per-row try — and csv.Error is not a ValueError, so the wizard's (ValueError, FinbreakError) net missed it and the import crashed (violates INV-4 'malformed file must never crash'). Fixed in csv_importer.py: parse() materialises rows under one csv.Error->ValueError guard; read_header() guards the .fieldnames access. Regression: test_INV4_malformed_csv_surfaces_valueerror_not_csv_error.
  **Layman:** A corrupt or truncated CSV now shows a friendly 'not valid CSV' message instead of crashing the import.
  Kind: review-fix.
  Source: indie-review-2026-07-23.

- ✅ [FIBR-0166] **Argon2id acceptance floor decoupled from the creation pin so a future KDF-strength bump can't lock out existing vaults.**
  indie-review (crypto lane), LOW (data-loss footgun). validate_params checked memory_kib against the SAME ARGON2_MEMORY_KIB used to create vaults, while the docstring claimed the pin could be raised without locking out existing vaults — false. Raising the constant (per global rule §5 / an OWASP bump) would push every existing vault below the floor -> KdfPolicyError on open = permanent lockout. Fixed by adding ARGON2_MEMORY_FLOOR_KIB (= the pin today, held at the minimum ever shipped); validate_params now checks the floor, so the pin can rise independently. Zero behaviour change today; all floor tests stay green.
  **Layman:** Made it safe to strengthen password protection later without locking anyone out of their existing data.
  Kind: review-fix.
  Source: indie-review-2026-07-23.

- ✅ [FIBR-0167] **Auto-update enforces https on redirects, not just the initial URL (FIBR-0054 INV-10).**
  indie-review (update/signature lane), LOW (defence-in-depth). _require_https guarded only the first URL; urllib's default opener follows 3xx redirects to http/ftp transparently, so an https URL redirecting to http:// was followed. Integrity was still guaranteed by the Ed25519 check on the asset, but the unsigned API JSON could be read over plaintext. Fixed with _HttpsOnlyRedirectHandler on a process-wide opener (install_opener), re-asserting _require_https on every hop; urlopen keeps its call shape so the test seam survives. Regression: test_INV10_redirect_to_non_https_is_refused.
  **Layman:** The update check can no longer be silently downgraded to an insecure connection via a redirect.
  Kind: review-fix.
  Source: indie-review-2026-07-23.

- ✅ [FIBR-0168] **Recurring & Transfers tabs render amounts with the currency symbol + locale grouping via _format_amount.**
  indie-review (UI lane), LOW. Both tabs rendered raw str(Decimal) instead of the shared _format_amount, so a large figure showed with no currency glyph and no thousands grouping — easy to misread by an order of magnitude in a finance app. Values/signs were correct. Both amounts are positive magnitudes, so no negative-style/colour prefs plumbing was needed: the base-currency symbol is read fresh (TransactionService.base_currency()) like the Transactions/Home tabs and passed to _format_amount; the SortableItem numeric sort key is unchanged.
  **Layman:** Money on the Recurring and Transfers tabs now shows as 'R 1,234.50' like the rest of the app, instead of a bare '1234.5'.
  Kind: review-fix.
  Source: indie-review-2026-07-23.

- 📋 [FIBR-0169] **Auto-update anti-rollback: bind the offered version into the signed artifact to prevent a signed-but-older downgrade.**
  indie-review (update/signature lane), LOW — deferred (design + release-pipeline change, needs a spec). The Ed25519 signature binds only the artifact BYTES, not the version; the offered version comes verbatim from the untrusted GitHub tag_name. A GitHub-release-WRITE attacker (no signing key — the residual security-model §2 already acknowledges) could re-publish an old, still-validly-signed AppImage under a higher tag; check_for_update sees it as newer, download_and_verify passes (authentic bytes), and the user is silently downgraded to a version with known bugs. Fix options: sign a manifest naming version+hash, or refuse to install a payload whose embedded __version__ <= current. At minimum document the downgrade case alongside the existing 'no rollback' accepted-risk in FIBR-0054 Out-of-scope.
  **Layman:** Stop a would-be attacker (who can write GitHub releases but holds no signing key) from tricking the app into installing an older, still-signed version.
  Kind: security.
  Source: indie-review-2026-07-23.

- ✅ [FIBR-0170] **Install the verified update from the in-memory buffer to close the verify-in-memory / install-from-disk TOCTOU.**
  indie-review (update/signature lane), INFO — out of the current threat model (needs a same-user/root attacker able to rewrite the 0600 mkstemp temp in the target dir, explicitly out of scope per security-model §4), so deferred. download_and_verify verifies data read into memory (asset_tmp.read_bytes()) but the installer later os.replace()s the on-disk temp — the file could differ from the verified bytes in the window. Hardening: write the verified `data` buffer to a fresh temp and install THAT, rather than trusting the re-read file. Low priority; noted for completeness.
  **Layman:** Extra hardening so the exact bytes we checked are the exact bytes installed.
  Kind: security.
  Source: indie-review-2026-07-23.
  Resolved (2026-07-28): download_and_verify now writes the verified in-memory buffer to a fresh mkstemp (0600, O_EXCL) and deletes the download temp it re-read those bytes from, so the file the installer swaps in is the file the signature check passed. Shrinks the swap window from the whole transfer to the moment before os.replace(). Test: test_FIBR0170_installs_the_verified_buffer_not_the_re_read_download.

- 📋 [FIBR-0180] **Decide deliberately whether to move the CI/build base image off Debian 12 (bookworm, now oldstable).**
  ci.yml, ci-docker.sh and build-smoke.sh all pin python:3.12-slim-bookworm. Debian 13 (trixie) has been stable since Aug 2025, so bookworm is oldstable and a python:3.12-slim-trixie image exists. This is NOT a routine bump: the build image's glibc (~2.36) is the EFFECTIVE floor of every frozen artifact (libpython links it - see the pyproject.toml dependencies comment), so moving to trixie raises the minimum glibc an AppImage/.exe user needs. The debt sweep added that rationale as a comment on ci.yml's container line rather than bumping. Decide: (a) hold on bookworm until the AppImage's target-distro floor justifies moving, or (b) bump all three call-sites together and re-run build-smoke to confirm the clean-room launch still passes on the oldest distro we claim to support. Either way, record the decision so the next sweep does not re-raise it.
  **Layman:** Our build machine runs an older Debian. Moving to the newer one is a trade-off: it may stop finbreak running on older Linux systems, so it needs a decision rather than a routine update.
  Kind: chore.
  Source: debt-sweep-2026-07-26.

- ✅ [FIBR-0181] **Consolidate the five hand-rolled Decimal to minor-units conversions behind one to_minor() helper.**
  Five independent implementations of the same Decimal->minor-units conversion: services/alerts.py:167 (_to_minor), services/forecast.py:215, importers/standard_bank.py:445 (_minor), importers/ofx_importer.py:157 (inline), services/transactions.py:73 (a scaleb variant). The duplication is already self-admitted in two places: alerts.py's docstring says it is 'the exact idiom ForecastService._to_input uses', and ofx_importer.py's comment points at a _minor that lives in a different module it does not import. The REVERSE direction already has a single home (transactions.to_display_decimal) - add the forward to_minor(amount, exponent) beside it and route all five through it. Well past Rule of Three. Deliberately NOT done in the debt sweep: this is money code in a correctness-critical app, so it wants its own reproduce-first cycle with a test pinning rounding behaviour (esp. the scaleb variant, which may not round identically) rather than a drive-by edit. Related watch item: services/forecast.py CASH_TYPES and services/reconciliation.py _RECONCILABLE_TYPES are the identical frozenset kept in manual sync by comment - only 2 sites, so below Rule of Three; extract on the third caller.
  **Layman:** The code that turns a money amount into whole cents is written out five separate times. One shared version would make a rounding mistake impossible to introduce in just one of them.
  Kind: refactor.
  Source: debt-sweep-2026-07-26.
  Resolved (2026-07-28): `to_minor(amount, exponent)` now lives beside
  `to_display_decimal` in services/transactions.py as its exact inverse
  (`int(amount.scaleb(exponent).to_integral_value())`), and all five sites
  route through it — alerts._to_minor and standard_bank._minor deleted,
  forecast._to_input and ofx_importer's inline scaling replaced,
  parse_transaction now calls it. TDD: 16 new cases in
  tests/features/vault/test_vault.py pin exact scaling at exponent 0/2/3,
  the to_display_decimal round-trip, half-even rounding below the minor
  unit, and — the risk the bullet flagged — that the two replaced
  spellings (`* 10**exp` and `.scaleb(exp)`) agree, so no stored value
  changed. Doc drift swept: FIBR-0171 §D7 + the OFX bullet, FIBR-0172 §D7
  + INV-15, and the alerts.py docstring now name the shared helper.
  NOT done (deliberate, unchanged): forecast.CASH_TYPES /
  reconciliation._RECONCILABLE_TYPES remain 2 duplicate frozensets —
  still below Rule of Three; extract on the third caller.
  Verified: ruff + mypy clean, 1385 passed, 2 skipped (was 1369).

- ✅ [FIBR-0182] **Four dead-code sites surfaced by the debt sweep (not removed - each needs an owner decision).**
  Surfaced rather than deleted (global rule 11 - do not remove pre-existing dead code unasked). Each verified with a repo-wide grep over src/tests/scripts/docs: (1) importers/standard_bank.py:42 re-exports PasswordError from pdf_importer behind a '# noqa: F401 (re-export)'; nothing imports it from standard_bank (the wizard takes it from pdf_importer), so the noqa keeps a dead name alive - drop it, or declare __all__ if the re-export is intended public API. (2) ui/transfers.py:221 candidate_count() sits under a 'test / shell accessors' banner with zero callers anywhere. (3) ui/statements.py:265 selected_period_id() has zero callers; its only mention is prose at docs/specs/FIBR-0059.md:356 - so either the test that spec implies is missing, or the accessor is. (4) importers/standard_bank.py:919 _span()'s `family` parameter is never read (the body branches only on `period is not None`); dropping it touches two call-sites (:893) and two tests. NOTE: main_window.py:237/239 _update_check_worker / _download_worker are assigned-never-read but are defensible QThread lifetime anchors - left alone.
  **Layman:** Four small pieces of code that nothing uses. Removing them is tidy-up, but each one needs a quick check that it was not left there on purpose.
  Kind: chore.
  Source: debt-sweep-2026-07-26.
  Resolved (2026-07-28): all four removed after re-verifying each has zero
  callers. (1) the PasswordError re-export + its noqa F401 dropped from
  standard_bank.py (the wizard imports it from pdf_importer). (2)
  ui/transfers.py candidate_count() removed. (3) ui/statements.py
  selected_period_id() removed, and the FIBR-0059 §"code reused" survey
  line updated so no doc points at it. (4) _span()'s unread `family`
  parameter dropped (call-site :893 + two asserts in
  test_standard_bank.py), docstring reworded to state the actual rule (a
  printed period wins; A/C are simply the families that supply one).
  Verified: ruff + mypy clean, 1369 passed, 2 skipped.

- ✅ [FIBR-0183] **bandit prints 31 'Test in comment' warnings because prose follows the # nosec test id.**
  bandit parses everything after '# nosec' as a comma/space-separated list of test IDs, so a marker written '# nosec B603 - fixed /bin/sh waiter, our own argv' makes it try to resolve 'fixed', 'waiter', 'our', 'own', 'argv' as test names and emit 'WARNING Test in comment: X is not a test name or id, ignoring' for each. 31 such warnings across the tree. Verified pre-existing and NOT caused by the debt sweep's noqa cleanup (identical count before and after, and bandit still exits 0 with the suppressions honoured). Low severity, but it is 31 lines of noise in every gate run, which is exactly the condition under which a real bandit warning gets skimmed past. Fix: put the rationale on its own line above, or after a separator bandit stops parsing at, keeping the marker itself bare ('# nosec B603').
  **Layman:** Our security scanner prints 31 confusing warnings every run, caused purely by how a comment is written. Harmless now, but the noise could hide a real warning.
  Kind: chore.
  Source: debt-sweep-2026-07-26.
  Resolved (2026-07-28): moved every rationale off the `# nosec` line (own
  comment line above, marker left bare) in update_installer.py x3,
  backup.py and tests/features/backup/test_backup.py. Verified: bandit
  "Test in comment" warnings 31 -> 0, `bandit -c pyproject.toml -r src -q`
  still exits 0 with the 7 suppressions honoured; ruff + 1369 passed,
  2 skipped.

- ✅ [FIBR-0221] **cryptography 49.0.0 carries CVE-2026-69247; the pinned version failed the pip-audit gate.**
  Surfaced by ./scripts/ci-local.sh's pip-audit stage while closing
  FIBR-0190 — unrelated to that work, but a red gate and a real advisory
  on a dep we pin ourselves. cryptography is an EXPLICIT runtime dep, not
  just transitive: services/update.py and services/update_key.py import it
  directly for Ed25519 verification of downloaded updates (FIBR-0054 D1),
  so this is our signature-checking library.

  Resolved (2026-08-04): pinned cryptography==50.0.0 (the advisory's fix
  version). No caller change needed — the Ed25519PublicKey /
  InvalidSignature API the two call sites use is unchanged across the
  major. Full gate re-run green: 1610 passed / 2 skipped, pip-audit clean.
  **Layman:** A security library finbreak uses had a published flaw; it is now on the fixed version.
  Kind: security.
  Lanes: dependencies, security.
  Source: in-session-2026-08-04.

## How to add an item

1. Allocate the next ID:
   ```bash
   echo $(($(cat .roadmap-counter) + 1)) > .roadmap-counter
   printf "FIBR-%04d\n" $(cat .roadmap-counter)
   ```
2. Insert at the **position** where it should be tackled (not
   blindly at the end).
3. Set the status emoji (📋 Planned, 💭 Considered).
4. Add `Lanes:` line declaring ownership.
5. Add `Kind:` (required on every bullet, per
   `roadmap-format.md § 3.5`) and `Source:` (omit only when it's
   `planned`).

See `docs/standards/roadmap-format.md § 3.5` for the full bullet
contract.

## How findings get folded

After every `/audit` + `/indie-review` (and `/debt-sweep`):

```
Phase closes
  → Run /audit + /indie-review
  → Triage findings
  → If clean: phase fully closed.
  → If actionable: batch into one new fix-pass FP## (next-up),
    add [Unreleased] entry, run that fix-pass through the
    9-step loop; its own closing audits may produce another.
```

See `docs/standards/roadmap-format.md § 3.8` and the
[app-workflow skill](~/.claude/skills/app-workflow/SKILL.md)
for the full pattern.
