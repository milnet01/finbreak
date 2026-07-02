"""Shared pytest setup.

Force Qt's offscreen platform before any QApplication is created, so the
GUI-touching tests (FIBR-0004 INV-5/INV-6) run on a headless CI runner with no
display. Set at import time — pytest imports conftest before collecting tests
or creating the pytest-qt `qapp`.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
