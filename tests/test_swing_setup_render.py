"""Milestone AR — Swing Setup Engine v1: rendering.

Presentation only: every value asserted here already exists on the
`SetupAssessment` the fixtures build. The renderer must never fabricate a
price for a `WAIT` result, must show an absent field honestly, and must be
deterministic.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.decision_context import ContextState
from fmis.decision_support import Alignment, OverallState
from fmis.level_crossing import LevelOrigin, LevelSide, PriceLevel
from fmis.market_regime import ParticipationState, StructureState, VolatilityState
from fmis.market_structure import StructuralSwingLabel
from fmis.structural_trend import StructuralTrendType
from fmis.swing_setup import ExecutionBreakEvent, SetupInputs, evaluate_setup, render_setup

_AS_OF = datetime(2026, 1, 2, tzinfo=timezone.utc)


def _level(side: LevelSide, price: float, index: int = 1) -> PriceLevel:
    label = StructuralSwingLabel.HIGHER_HIGH if side is LevelSide.UPPER else StructuralSwingLabel.LOWER_LOW
    origin = LevelOrigin(
        index=index, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        label=label, confirmation_bars=2,
    )
    return PriceLevel(side=side, price=price, origin=origin)


def confirmed_long():
    inputs = SetupInputs(
        symbol="BTCUSDT", as_of=_AS_OF, source="fixture",
        context_interval="1w", setup_interval="1d", execution_interval="4h",
        context_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        setup_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        execution_structural_trend=StructuralTrendType.NEUTRAL,
        context_regime_structure=StructureState.TRENDING,
        context_regime_volatility=VolatilityState.STEADY,
        context_regime_participation=ParticipationState.TYPICAL,
        evidence_state=OverallState.WATCH, evidence_dominant_alignment=Alignment.UPWARD,
        decision_context_state=ContextState.SUFFICIENT, decision_context_statements=(),
        execution_close=100.0,
        execution_closed_count=10,
        execution_levels=(_level(LevelSide.UPPER, 110.0), _level(LevelSide.LOWER, 90.0)),
        execution_breaks=(
            ExecutionBreakEvent(level=_level(LevelSide.UPPER, 105.0, index=3), index=5),
        ),
        setup_levels=(_level(LevelSide.UPPER, 130.0), _level(LevelSide.LOWER, 70.0)),
        inherited_limitations=("X-1: test limitation",),
    )
    return evaluate_setup(inputs)


def waiting():
    inputs = SetupInputs(
        symbol="BTCUSDT", as_of=_AS_OF, source="fixture",
        context_interval="1w", setup_interval="1d", execution_interval="4h",
        context_structural_trend=StructuralTrendType.INDETERMINATE,
        setup_structural_trend=StructuralTrendType.INDETERMINATE,
        execution_structural_trend=StructuralTrendType.INDETERMINATE,
        context_regime_structure=StructureState.RANGING,
        context_regime_volatility=VolatilityState.STEADY,
        context_regime_participation=ParticipationState.TYPICAL,
        evidence_state=OverallState.INSUFFICIENT_DATA, evidence_dominant_alignment=None,
        decision_context_state=ContextState.SUFFICIENT, decision_context_statements=(),
        execution_close=100.0, execution_closed_count=10, execution_levels=(),
        execution_breaks=(), setup_levels=(),
        inherited_limitations=(),
    )
    return evaluate_setup(inputs)


def candidate_short_with_watched_level():
    """A real shape observed live on DOTUSDT: CANDIDATE, execution unconfirmed
    and opposing, with a watched level still named."""
    inputs = SetupInputs(
        symbol="DOTUSDT", as_of=_AS_OF, source="fixture",
        context_interval="1w", setup_interval="1d", execution_interval="4h",
        context_structural_trend=StructuralTrendType.SUSTAINED_LOWER,
        setup_structural_trend=StructuralTrendType.SUSTAINED_LOWER,
        execution_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        context_regime_structure=StructureState.TRENDING,
        context_regime_volatility=VolatilityState.CONTRACTING,
        context_regime_participation=ParticipationState.SUBDUED,
        evidence_state=OverallState.WAIT, evidence_dominant_alignment=Alignment.UPWARD,
        decision_context_state=ContextState.SUFFICIENT, decision_context_statements=(),
        execution_close=0.818, execution_closed_count=500,
        execution_levels=(_level(LevelSide.LOWER, 0.815), _level(LevelSide.UPPER, 0.825)),
        execution_breaks=(),
        setup_levels=(_level(LevelSide.LOWER, 0.815),),
        inherited_limitations=(),
    )
    return evaluate_setup(inputs)


def candidate_with_no_watched_level():
    """CANDIDATE with no qualifying execution-timeframe level at all."""
    inputs = SetupInputs(
        symbol="DOTUSDT", as_of=_AS_OF, source="fixture",
        context_interval="1w", setup_interval="1d", execution_interval="4h",
        context_structural_trend=StructuralTrendType.SUSTAINED_LOWER,
        setup_structural_trend=StructuralTrendType.SUSTAINED_LOWER,
        execution_structural_trend=StructuralTrendType.NEUTRAL,
        context_regime_structure=StructureState.TRENDING,
        context_regime_volatility=VolatilityState.CONTRACTING,
        context_regime_participation=ParticipationState.SUBDUED,
        evidence_state=OverallState.WAIT, evidence_dominant_alignment=Alignment.UPWARD,
        decision_context_state=ContextState.SUFFICIENT, decision_context_statements=(),
        execution_close=0.818, execution_closed_count=500,
        execution_levels=(),
        execution_breaks=(),
        setup_levels=(),
        inherited_limitations=(),
    )
    return evaluate_setup(inputs)


def test_render_setup_rejects_the_wrong_type() -> None:
    with pytest.raises(TypeError):
        render_setup(object())  # type: ignore[arg-type]


def test_confirmed_long_page_shows_symbol_state_and_direction() -> None:
    text = render_setup(confirmed_long())
    assert "BTCUSDT" in text
    assert "CONFIRMED" in text
    assert "LONG" in text


def test_confirmed_long_page_shows_stop_target_and_risk_reward() -> None:
    text = render_setup(confirmed_long())
    assert "90" in text  # stop
    assert "130" in text  # target
    assert "R:R" in text
    assert "3.00" in text  # 30 reward / 10 risk


def test_wait_page_shows_no_fabricated_price() -> None:
    text = render_setup(waiting())
    assert "WAIT" in text
    assert "DIRECTION: —" in text or "direction: —" in text.lower()
    assert "NOT_CALIBRATED" in text


def test_wait_page_does_not_crash_on_empty_confirmation_and_trigger() -> None:
    text = render_setup(waiting())
    assert "not applicable" in text.lower() or "—" in text


def test_probability_is_never_a_number() -> None:
    for result in (confirmed_long(), waiting()):
        text = render_setup(result)
        assert "NOT_CALIBRATED" in text


def test_render_is_deterministic() -> None:
    result = confirmed_long()
    assert render_setup(result) == render_setup(result)


def test_the_page_carries_the_policy_disclaimer() -> None:
    text = render_setup(confirmed_long())
    assert "not a claim of profitability" in text
    assert "position sizing" in text.lower()


def test_the_reference_price_is_not_labelled_as_an_order_price() -> None:
    """The R/R reference close is labelled to avoid reading as an actionable entry."""
    text = render_setup(confirmed_long())
    assert "reference" in text
    assert "not an order price" in text


def test_candidate_page_shows_the_watched_level_and_no_fabricated_confirmation() -> None:
    result = candidate_short_with_watched_level()
    assert result.state.value == "candidate"
    text = render_setup(result)
    assert "CANDIDATE" in text
    assert "SHORT" in text
    assert "0.815" in text  # the watched level
    assert "level:" in text
    assert "confirmed at bar" not in text  # never fabricated for an unconfirmed trigger


def test_candidate_page_with_no_level_shows_absence_honestly() -> None:
    result = candidate_with_no_watched_level()
    assert result.state.value == "candidate"
    text = render_setup(result)
    assert "CANDIDATE" in text
    assert "none is available in the current window" in text
