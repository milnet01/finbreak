#!/bin/sh
# /usr/bin/finbreak — the launcher the OBS RPM/deb installs (FIBR-0155 § 3.4).
#
# The payload is a PyInstaller --onedir frozen runtime under /usr/lib/finbreak/
# (its own Python + every pinned native: SQLCipher, qpdf, pdfium, Qt), NOT a
# site-packages install — so this is a thin exec wrapper around the onedir
# bootloader, not a `#!/usr/bin/python3` script. "$@" passes arguments through,
# so `finbreak --self-test` (the FIBR-0003 native-stack sentinel) works from the
# installed package.
exec /usr/lib/finbreak/finbreak "$@"
