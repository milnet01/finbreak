"""The dynamic-loader variables a PyInstaller bundle leaks to its children.

The onefile bootloader repoints ``LD_LIBRARY_PATH`` at its private ``_MEI``
extraction dir so the app finds its *bundled* libraries, and saves any pre-launch
value in ``LD_LIBRARY_PATH_ORIG``. It never touches ``LD_PRELOAD``: neither name
appears in a 6.21.0 bootloader or the AppImage runtime (measured 2026-09-29), so
an ``LD_PRELOAD`` in the environment is the user's own and is left alone
(FIBR-0401). A child that is a SYSTEM
program — ``/bin/sh``, ``xdg-open``, a browser — then loads those bundled
libraries instead of its own. The bundle's Debian ``libreadline.so.8`` makes a
bash ``/bin/sh`` die on a symbol lookup before it runs a line (FIBR-0122,
FIBR-0364). AppImage is Linux-only, so only the Linux pair is handled.
"""

from __future__ import annotations

from collections.abc import MutableMapping

LOADER_ENV = ("LD_LIBRARY_PATH",)


def restore_system_loader_env(env: MutableMapping[str, str]) -> None:
    """Set each loader var back to its pre-launch value, or drop it if it had none.

    The ``_ORIG`` copies are left in place, so a second call is a no-op rather
    than dropping a value the first call restored.
    """
    for var in LOADER_ENV:
        original = env.get(f"{var}_ORIG")
        if original:
            env[var] = original
        else:
            env.pop(var, None)
