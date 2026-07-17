"""Smoke test: prove the package imports and exposes a version string."""

from __future__ import annotations

import fmis


def test_package_imports() -> None:
    assert fmis is not None


def test_version_is_nonempty_string() -> None:
    assert isinstance(fmis.__version__, str)
    assert fmis.__version__
