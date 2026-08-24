"""Fixtures for the operator dashboard suite.

**Real engine outputs wherever they are cheap to build.** The workspace comes
from `swing_workspace_helpers.workspace_of`, which runs the actual composition
root over synthetic assessments; the pulse and macro reports are real
`MarketPulse` and `MacroContextReport` values assembled from real
`MarketReading` objects. A dashboard test asserting against a hand-written stub
would pass while the mapping read a field the engine renamed, which is the
whole class of bug this seam exists to catch.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from fmis.macro import MacroContextReport, MacroLevel
from fmis.market_pulse import (
    Benchmark,
    FreshnessPolicy,
    Horizon,
    HorizonMove,
    MarketCategory,
    MarketPulse,
    MarketReading,
    MarketUnavailable,
    MarketUniverse,
    ProviderInstrument,
    QuantityKind,
    TradingSchedule,
    VolatilityReading,
)

__all__ = [
    "AT",
    "HOURLY",
    "DAILY",
    "benchmark",
    "dark",
    "reading_for",
    "pulse_of",
    "macro_of",
    "Boom",
]

#: The instant every fixture describes. Fixed, so a snapshot is comparable.
AT = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)

HOURLY = Horizon(horizon_id="latest_bar", bars=1, description="the last completed bar")
DAILY = Horizon(
    horizon_id="latest_observation",
    bars=1,
    description="the last completed observation",
)

_HOURLY_POLICY = FreshnessPolicy(
    publication_period=timedelta(hours=1),
    tolerance=timedelta(minutes=30),
    basis="the venue publishes hourly bars; tolerance covers clock skew",
)


class Boom(Exception):
    """A stand-in for whatever a provider raises. Never caught broadly."""


def benchmark(
    benchmark_id: str = "BTC",
    *,
    display_name: str | None = None,
    category: MarketCategory = MarketCategory.CRYPTO,
    quote_unit: str = "USDT",
    quantity_kind: QuantityKind = QuantityKind.PRICE_LIKE,
    interval: str = "1h",
) -> Benchmark:
    return Benchmark(
        benchmark_id=benchmark_id,
        display_name=display_name or f"{benchmark_id} (test)",
        category=category,
        schedule=TradingSchedule.CONTINUOUS,
        quote_unit=quote_unit,
        instrument=ProviderInstrument(
            provider="test-venue", symbol=f"{benchmark_id}USDT", interval=interval
        ),
        quantity_kind=quantity_kind,
        freshness_policy=_HOURLY_POLICY,
    )


def dark(benchmark_id: str = "DXY", reason: str = "no provider is configured") -> Benchmark:
    """A market this build has no provider for. DXY and XAU are the live cases."""
    return Benchmark(
        benchmark_id=benchmark_id,
        display_name=f"{benchmark_id} (unsupported)",
        category=MarketCategory.CURRENCY,
        schedule=TradingSchedule.SESSION_BOUND,
        quote_unit="index points",
        unsupported_reason=reason,
    )


def reading_for(
    subject: Benchmark,
    *,
    move: float | None = 0.0125,
    move_reason: str | None = None,
    volatility: float | None = 0.0071,
    volatility_reason: str | None = None,
    bar_open: datetime | None = None,
    horizon: Horizon = HOURLY,
) -> MarketReading:
    """One market's reading. ``move=None`` requires a reason, as the engine does."""
    opened = bar_open or (AT - timedelta(hours=1))
    # The engine refuses a measured value over an unnamed window — "a number
    # nobody can reconstruct" — so a fixture that produces one must name it too.
    window = (
        {}
        if move is None
        else {"window_start": opened - timedelta(hours=horizon.bars), "window_end": opened}
    )
    volatility_window = (
        {}
        if volatility is None
        else {"window_start": opened - timedelta(hours=200), "window_end": opened}
    )
    return MarketReading(
        benchmark=subject,
        source="test-venue",
        interval="1h",
        last_bar_open=opened,
        closed_bar_count=200,
        moves=(
            HorizonMove(
                horizon_id=horizon.horizon_id,
                bars=horizon.bars,
                value=move,
                unavailable_reason=move_reason,
                metric="simple return over the window",
                observation_count=horizon.bars + 1,
                **window,
            ),
        ),
        volatility=VolatilityReading(
            value=volatility,
            unavailable_reason=volatility_reason,
            metric="standard deviation of bar returns",
            observation_count=200,
            **volatility_window,
        ),
    )


def pulse_of(
    readings: Sequence[MarketReading] = (),
    *,
    unavailable: Sequence[tuple[Benchmark, str]] = (),
    unsupported: Sequence[Benchmark] = (),
    as_of: datetime = AT,
    horizons: Sequence[Horizon] = (HOURLY,),
    name: str = "test",
) -> MarketPulse:
    members = [reading.benchmark for reading in readings]
    members.extend(entry for entry, _ in unavailable)
    members.extend(unsupported)
    return MarketPulse(
        as_of=as_of,
        universe=MarketUniverse(name=name, benchmarks=tuple(members)),
        readings=tuple(readings),
        unavailable=tuple(
            MarketUnavailable(benchmark=entry, reason=reason)
            for entry, reason in unavailable
        ),
        rankings=(),
        horizons=tuple(horizons),
    )


def macro_of(
    readings: Sequence[MarketReading] = (),
    *,
    levels: Sequence[MacroLevel] = (),
    unavailable: Sequence[tuple[Benchmark, str]] = (),
    unsupported: Sequence[Benchmark] = (),
    as_of: datetime = AT,
    horizons: Sequence[Horizon] = (DAILY,),
) -> MacroContextReport:
    members = [reading.benchmark for reading in readings]
    members.extend(entry for entry, _ in unavailable)
    members.extend(unsupported)
    return MacroContextReport(
        as_of=as_of,
        universe=MarketUniverse(name="macro", benchmarks=tuple(members)),
        levels=tuple(levels),
        readings=tuple(readings),
        unavailable=tuple(
            MarketUnavailable(benchmark=entry, reason=reason)
            for entry, reason in unavailable
        ),
        rate_facts=(),
        relationships=(),
        horizons=tuple(horizons),
    )


def level_for(
    subject: Benchmark,
    *,
    value: float = 4.19,
    unit: str = "percent per annum",
    observed_at: datetime | None = None,
) -> MacroLevel:
    return MacroLevel(
        benchmark_id=subject.benchmark_id,
        display_name=subject.display_name,
        value=value,
        unit=unit,
        quantity_kind=subject.quantity_kind,
        observed_at=observed_at or (AT - timedelta(days=1)),
        source="test-source",
    )
