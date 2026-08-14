"""Builders for the Daily Trading Workspace tests.

Two families, kept apart exactly as the package keeps them apart: scan results
(the market half) and store readings (the owner half). Nothing here fetches, and
nothing here reads a clock.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fmis.swing_setup.compose import SetupRunResult
from fmis.today import (
    OpportunityLine,
    PortfolioOverview,
    StoreReading,
    NotAvailable,
    build_today,
)

__all__ = [
    "REFERENCE",
    "result",
    "failed_result",
    "line",
    "reading",
    "portfolio",
    "workspace",
]

REFERENCE = datetime(2026, 8, 12, 21, 0, tzinfo=timezone.utc)


def result(assessment: Any) -> SetupRunResult:
    return SetupRunResult(requested_symbol=assessment.symbol, assessment=assessment)


def failed_result(symbol: str, detail: str = "provider timed out") -> SetupRunResult:
    return SetupRunResult(requested_symbol=symbol, failure=detail)


def line(**overrides: Any) -> OpportunityLine:
    """An `OpportunityLine` with every field overridable.

    Built directly rather than adapted from an assessment, so a warning rule can
    be exercised on a shape the engine has not yet produced — which is what a
    rule test needs and what an end-to-end test must not do.
    """
    values: dict[str, Any] = {
        "symbol": "BTCUSDT",
        "state": "confirmed",
        "sufficiency": "sufficient",
        "direction": "up",
        "risk_reward": 2.0,
        "stop": 100.0,
        "target": 120.0,
        "thesis": ("a stated reason",),
    }
    values.update(overrides)
    return OpportunityLine(**values)


def reading(**overrides: Any) -> StoreReading:
    """An empty-but-present store reading, with every field overridable."""
    values: dict[str, Any] = {
        "root": "/tmp/does-not-matter",
        "present": True,
        "positions": (),
        "closed_positions": (),
        "budget": None,
        "snapshot": None,
        "journal_entries": (),
        "decisions": (),
        "citations": (),
        "market_snapshots": (),
        "archived": (),
    }
    values.update(overrides)
    return StoreReading(**values)


def portfolio(**overrides: Any) -> PortfolioOverview:
    """A `PortfolioOverview` for rule tests that do not need a real store."""
    absent = NotAvailable(
        reason="nothing was measured",
        owned_by="a later slice",
        forbidden_inference="Do not read this as within budget.",
    )
    values: dict[str, Any] = {
        "store_root": "/tmp/store",
        "store_present": True,
        "open_positions": (),
        "limits": (),
        "budget_note": absent,
        "committed_risk": absent,
        "available_risk": absent,
        "cash": absent,
        "exposure": absent,
    }
    values.update(overrides)
    return PortfolioOverview(**values)


def workspace(results: Any, store: StoreReading | None = None, **overrides: Any):
    """A complete `TodayWorkspace` over the supplied results."""
    values: dict[str, Any] = {
        "reference_time": REFERENCE,
        "source": "fixture",
    }
    values.update(overrides)
    return build_today(results, store or reading(), **values)
