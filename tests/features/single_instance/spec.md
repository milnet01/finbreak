# tests/features/single_instance — FIBR-0189 one finbreak per OS user

Conformance tests for the single-instance guard. A second launch does **not**
open a second window: it knocks on the running instance's socket, that instance
raises itself, and the new process exits `0` before building any UI.

Two reasons this exists. The visible one is the duplicate taskbar entry (the
other half of which is the launcher naming in FIBR-0188 — neither fix subsumes
the other). The quieter one is **vault safety**: the vault is a single SQLCipher
file and the app has no cross-process locking, so two instances are two writers
racing the same database.

The implementation is `src/finbreak/single_instance.py` — Qt's canonical
`QLocalSocket` probe → `QLocalServer` listen, in that order — wired in
`app.py::run`. Tests drive the **real** sockets (mocking them would test
nothing); each uses a `tmp_path`-derived name so a developer's own running
finbreak can never collide with the suite.

## Coverage

| INV | What it pins |
|-----|--------------|
| INV-1 | Detection both ways: nothing listening → `another_instance_is_running` is `False` and the launch proceeds; once an owner is listening it is `True`; after the owner closes, a launch proceeds again. |
| INV-2 | The probe **wakes** the owner — `newConnection` fires and a pending connection is queued — which is what lets the running instance raise its window rather than silently absorbing the launch. |
| INV-3 | A stale socket **file** (kill -9 leftover: bound, then nothing listening) does not look like a live instance, and `listen()` clears it and succeeds. Without the `removeServer` guard this is the failure that makes the app permanently unlaunchable. The orphan is created with a raw `AF_UNIX` bind, because Qt's own destructor tidies up and so cannot fake one. Unix-only (skipped elsewhere). |
| INV-3a | **A LIVE owner is never evicted** (FIBR-0204). INV-3's twin. `listen()` used to call `removeServer` unconditionally, which unlinks whatever is at the path — including a running instance's socket. `app.py` probes before building the window but does not claim until after `show()`, so two launches inside that window both ended up "listening" on one name, with the first owner bound to an unlinked inode and unreachable forever: two writers on one SQLCipher file, the exact hazard this feature exists to prevent. `listen()` now tries first and clears the path only after a re-probe proves nobody is behind it. A launch that loses the race stands down (exit 0) rather than running unguarded — that path is the guard WORKING, not the fail-open case below. |
| INV-4 | The socket name is scoped to the uid. `QLocalServer` puts its socket in a **shared** temp dir on Unix, so an unqualified name would let one user's launch bounce off another's session — and that second user could never open the app at all. **Since FIBR-0204 the name is an absolute path under `$XDG_RUNTIME_DIR`** when that is set — `/tmp` is world-writable, so any local account could pre-bind the predictable name and finbreak's probe would read it as "already running" and exit 0 with no window, no message and status 0. `$XDG_RUNTIME_DIR` is specified user-owned and 0700. Falls back to the uid-suffixed bare name when the variable is unset. |
| INV-5 | The update relaunch releases the socket **before** the key wipe (`_release_for_relaunch`), so the replacement process's probe finds nobody and starts. Holding it would make the update appear to do nothing — the 0.1.2→0.1.3 "closed but didn't reopen" shape. Running unguarded (a failed `listen()`) still wipes the key. |
| INV-6 | A knock **un-minimises** the existing window, not merely `show()`s it — `show()` on a minimised window restores it to the taskbar, not to the foreground. |

**Fails open by design.** If the probe finds nobody but `listen()` still fails
(read-only runtime dir, an exotic sandbox), `app.py` runs the app *unguarded*
rather than refusing to start. Briefly allowing two windows is a far smaller
failure than an app that will not open, and INV-5's second leg pins that the
update path survives it.

**Coverage honesty.** The socket handshake is fully exercised here in-process.
What is **not** covered is real cross-process focus stealing — whether the
compositor actually brings the raised window forward is Wayland/X11 policy, not
something the app decides, so INV-6 asserts the window *state* we set rather
than where the window visually lands. Same posture as the FIBR-0131 PowerShell
legs and the AppImage relaunch legs: pin what we control, be explicit about what
only a real desktop can show.
