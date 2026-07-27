"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest


@pytest.fixture
def fresh_fmis_imports() -> Iterator[None]:
    """Clear `fmis.*` from `sys.modules` for a cold-import test, then restore it.

    Import-boundary tests assert what a cold ``import fmis.<pkg>`` pulls in, which
    requires clearing `sys.modules` first. The restore afterwards is the important
    half: without it, every later test comparing class identity against a
    module-level import (e.g. ``fmis.data.ObservationSeries is ObservationSeries``)
    would compare against a *re-imported* class object and fail — a failure that
    depends purely on alphabetical test-file ordering, and so appears and vanishes
    as unrelated test files are added or renamed.

    The original module objects are put back, not merely re-imported, so identity
    holds for modules imported before the wipe.
    """
    saved = {name: mod for name, mod in sys.modules.items() if name.startswith("fmis")}
    for name in saved:
        del sys.modules[name]
    try:
        yield
    finally:
        for name in [n for n in sys.modules if n.startswith("fmis")]:
            del sys.modules[name]
        sys.modules.update(saved)
