"""Shared fixtures for the Swing Lab suite.

`setup_inputs` mirrors `tests.test_swing_setup_policy.base_inputs` deliberately
rather than importing it: importing one test module from another makes pytest
collect the first module's classes twice, and this repository's convention puts
shared fixtures in a `*_helpers.py` module. The two builders describe the same
LONG-leaning fixture, and `test_swing_lab_policy` asserts the production
assessment they produce is unchanged, so a drift between them fails loudly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fmis.decision_context import ContextState
from fmis.decision_support import Alignment, OverallState
from fmis.level_crossing import LevelOrigin, LevelSide, PriceLevel
from fmis.market_regime import ParticipationState, StructureState, VolatilityState
from fmis.market_structure import StructuralSwingLabel
from fmis.paper.models import PriceBar
from fmis.structural_trend import StructuralTrendType
from fmis.swing_setup.models import ExecutionBreakEvent, SetupInputs

__all__ = ["AS_OF", "T0", "bar", "level", "breaks", "setup_inputs"]

AS_OF = datetime(2026, 8, 1, tzinfo=timezone.utc)
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
_ORIGIN_TS = datetime(2026, 7, 1, tzinfo=timezone.utc)


def level(side: LevelSide, price: float, index: int = 1) -> PriceLevel:
    label = (
        StructuralSwingLabel.HIGHER_HIGH
        if side is LevelSide.UPPER
        else StructuralSwingLabel.LOWER_LOW
    )
    return PriceLevel(
        side=side,
        price=price,
        origin=LevelOrigin(
            index=index, timestamp=_ORIGIN_TS, label=label, confirmation_bars=2
        ),
    )


def breaks(*events: tuple[LevelSide, float, int]) -> tuple[ExecutionBreakEvent, ...]:
    return tuple(
        ExecutionBreakEvent(level=level(side, price, index=1), index=bar_index)
        for side, price, bar_index in events
    )


def bar(index: int, open_: str, high: str, low: str, close: str, *, interval: str = "4h") -> PriceBar:
    return PriceBar(
        symbol="BTCUSDT",
        interval=interval,
        open_time=T0 + timedelta(hours=4 * index),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
    )


def setup_inputs(**overrides) -> SetupInputs:
    """A LONG-leaning, TRENDING-context fixture that confirms under production."""
    kwargs = dict(
        symbol="BTCUSDT",
        as_of=AS_OF,
        source="fixture",
        context_interval="1w",
        setup_interval="1d",
        execution_interval="4h",
        context_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        setup_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        execution_structural_trend=StructuralTrendType.NEUTRAL,
        context_regime_structure=StructureState.TRENDING,
        context_regime_volatility=VolatilityState.STEADY,
        context_regime_participation=ParticipationState.TYPICAL,
        evidence_state=OverallState.WATCH,
        evidence_dominant_alignment=Alignment.UPWARD,
        decision_context_state=ContextState.SUFFICIENT,
        decision_context_statements=(),
        execution_close=100.0,
        execution_closed_count=10,
        execution_levels=(level(LevelSide.UPPER, 110.0), level(LevelSide.LOWER, 90.0)),
        execution_breaks=breaks((LevelSide.UPPER, 105.0, 5)),
        setup_levels=(level(LevelSide.UPPER, 130.0), level(LevelSide.LOWER, 70.0)),
        inherited_limitations=("X-1: test",),
    )
    kwargs.update(overrides)
    return SetupInputs(**kwargs)
