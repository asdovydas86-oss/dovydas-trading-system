"""Shared, offline fixture builders for the `fmis.archive` test suite.

Not a test module itself (no `test_` prefix, so pytest does not collect it).
Builds real `Workspace`/`DailyRun` instances from seeded candle series — no
network, no mocked transport — following the same pattern
`tests/test_workspace_build.py` already establishes for workspace fixtures.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from fmis.daily.models import DailyRun, FailureKind, SymbolFailure, SymbolResult, ResultCategory
from fmis.data import Candle, CandleSeries
from fmis.pipeline.multi_timeframe import TimeframeRole, build_multi_timeframe_facts
from fmis.pipeline.regime import regime_features
from fmis.pipeline.structural_facts import build_structural_facts
from fmis.workspace import build_workspace
from fmis.workspace.models import SectionId

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def seeded_series(
    count: int = 260, seed: int = 5, symbol: str = "BTCUSDT", timeframe: str = "4h"
) -> CandleSeries:
    rng = random.Random(seed)
    candles = []
    for i in range(count):
        open_ = rng.uniform(95.0, 105.0)
        close = rng.uniform(95.0, 105.0)
        candles.append(
            Candle(
                timestamp=_BASE + timedelta(hours=4 * i),
                symbol=symbol,
                timeframe=timeframe,
                open=open_,
                high=max(open_, close) + rng.uniform(0.0, 3.0),
                low=min(open_, close) - rng.uniform(0.0, 3.0),
                close=close,
                volume=rng.uniform(0.5, 5.0),
                is_closed=True,
            )
        )
    return CandleSeries(symbol=symbol, timeframe=timeframe, candles=tuple(candles))


def facts(seed: int = 5, count: int = 260, symbol: str = "BTCUSDT", **kwargs):
    return build_structural_facts(
        seeded_series(count=count, seed=seed, symbol=symbol),
        features=regime_features(),
        source="fixture",
        **kwargs,
    )


def multi(seeds: tuple[int, int, int] = (1, 5, 9), symbol: str = "BTCUSDT"):
    """A three-view sheet whose views come from different seeds, so they differ."""
    return build_multi_timeframe_facts(
        {
            TimeframeRole.CONTEXT: facts(seed=seeds[0], symbol=symbol),
            TimeframeRole.SETUP: facts(seed=seeds[1], symbol=symbol),
            TimeframeRole.EXECUTION: facts(seed=seeds[2], symbol=symbol),
        },
        intervals={
            TimeframeRole.CONTEXT: "1w",
            TimeframeRole.SETUP: "1d",
            TimeframeRole.EXECUTION: "4h",
        },
        source="fixture",
    )


def fixture_workspace(symbol: str = "BTCUSDT", seeds: tuple[int, int, int] = (1, 5, 9), **kwargs):
    """A real, fully-built `Workspace` — every section populated deterministically."""
    return build_workspace(multi(seeds=seeds, symbol=symbol), **kwargs)


def fixture_symbol_result(workspace) -> SymbolResult:
    return SymbolResult(
        requested_symbol=workspace.symbol,
        category=ResultCategory(workspace.metadata["context_state"]),
        resolved_symbol=workspace.symbol,
        workspace=workspace,
        context=workspace.by_id[SectionId.CONTEXT],
        regime_summary="context · 1w: trending",
        duration_seconds=0.042,
    )


def fixture_failed_result(symbol: str = "SOLUSDT") -> SymbolResult:
    return SymbolResult(
        requested_symbol=symbol,
        category=ResultCategory.FAILED,
        failure=SymbolFailure(
            kind=FailureKind.PROVIDER_FAILURE, detail="timeout", exception_type="BinanceTransportError"
        ),
    )


def fixture_daily_run(
    *,
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
    include_failure: bool = False,
    reference_time: datetime | None = None,
) -> DailyRun:
    results = []
    for index, symbol in enumerate(symbols):
        workspace = fixture_workspace(symbol=symbol, seeds=(index + 1, index + 5, index + 9))
        results.append(fixture_symbol_result(workspace))
    if include_failure:
        results.append(fixture_failed_result())
    return DailyRun(
        reference_time=reference_time or datetime.now(timezone.utc),
        results=tuple(results),
        objective="swing_trade",
        source="binance-spot",
        limitations=(("AN-1", "This is a readiness index, not a ranking."),),
        metadata={"requested": symbols, "intervals": ("1w", "1d", "4h")},
    )
