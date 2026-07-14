"""Smoke test: the placeholder package imports and exposes its version.

Keeps the suite collectable and green on the empty project (FIBR-0001 INV-3)
before any feature code exists.
"""

import finbreak


def test_package_imports():
    assert finbreak.__version__ == "0.1.10"
