"""Builders for the Swing Decision Workspace tests.

Network-free and clock-free. Every assessment, store reading and paper view is
hand-built, so a full page is assembled with no provider, no filesystem and no
`datetime.now` anywhere in the call graph.

The families are kept apart exactly as the package keeps them apart: scan
results (the market half) and store readings (the owner half) are built by
separate functions that share no argument.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fmis.decision_context import ContextState
from fmis.level_crossing import LevelOrigin, LevelSide, PriceLevel
from fmis.market_structure import StructuralSwingLabel
from fmis.swing_setup import (
    Direction,
    DirectionalFactor,
    Lean,
    Probability,
    ProbabilityStatus,
    RiskReward,
    SetupAssessment,
    SetupState,
    Trigger,
    TriggerKind,
)
from fmis.swing_setup.compose import SetupRunResult
from fmis.today import StoreReading, TodayRun, build_today

__all__ = [
    "REFERENCE",
    "PIVOT",
    "assessment",
    "result",
    "failed_result",
    "reading",
    "run_of",
    "workspace_of",
]

REFERENCE = datetime(2026, 8, 20, 21, 0, tzinfo=timezone.utc)
PIVOT = datetime(2026, 6, 1, tzinfo=timezone.utc)
_START = datetime(2026, 8, 20, tzinfo=timezone.utc)
_NOT_CALIBRATED = Probability(status=ProbabilityStatus.NOT_CALIBRATED, value=None)


def assessment(
    symbol: str = "BTCUSDT",
    *,
    state: SetupState = SetupState.CONFIRMED,
    direction: Direction | None = Direction.LONG,
    sufficiency: ContextState = ContextState.SUFFICIENT,
    bar: int = 0,
    ratio: float = 3.0,
    thesis: tuple[str, ...] = ("trend continuation retest",),
    swing_index: int = 5,
) -> SetupAssessment:
    """One assessment, in any of the engine's three states.

    ``direction=None`` forces a `WAIT` result whatever ``state`` says, because
    that is the only shape `SetupAssessment` permits: a directional state with no
    direction is rejected by the engine's own validation.
    """
    common: dict[str, Any] = dict(
        symbol=symbol,
        as_of=_START + timedelta(hours=bar),
        objective="swing",
        probability=_NOT_CALIBRATED,
        regime_context=("context: trending",),
        sufficiency=sufficiency,
        limitations=("X-1: nothing was measured against a limit",),
        policy_id="swing-setup-v1",
        source="fixture",
    )
    if direction is None:
        return SetupAssessment(
            state=SetupState.WAIT,
            direction=None,
            thesis=thesis,
            directional_factors=(),
            confirmation=(),
            invalidation=(),
            trigger=None,
            reference_price=None,
            stop=None,
            targets=(),
            risk_reward=None,
            **common,
        )
    stop = PriceLevel(
        side=LevelSide.LOWER,
        price=90.0,
        origin=LevelOrigin(
            index=swing_index,
            timestamp=PIVOT,
            label=StructuralSwingLabel.LOWER_LOW,
            confirmation_bars=2,
        ),
    )
    target = PriceLevel(
        side=LevelSide.UPPER,
        price=130.0,
        origin=LevelOrigin(
            index=3,
            timestamp=PIVOT,
            label=StructuralSwingLabel.HIGHER_HIGH,
            confirmation_bars=2,
        ),
    )
    # The three factors the live policy emits, so the evidence projection runs
    # against the shape it was written for — including the correlation between
    # the two trend readings, which is what makes independence report honestly.
    lean = Lean.LONG if direction is Direction.LONG else Lean.SHORT
    factors = tuple(
        DirectionalFactor(
            family=family,
            lean=lean,
            observed=f"{family} agrees",
            source="fixture",
        )
        for family in (
            "context_structural_trend",
            "setup_structural_trend",
            "setup_evidence_alignment",
        )
    )
    return SetupAssessment(
        state=state,
        direction=direction,
        thesis=thesis,
        directional_factors=factors,
        confirmation=("awaiting an execution-timeframe break",),
        invalidation=("a close beyond the structural invalidation",),
        trigger=Trigger(
            kind=TriggerKind.AWAITING_STRUCTURE_BREAK, statement="awaiting"
        ),
        reference_price=100.0,
        stop=stop,
        targets=(target,),
        risk_reward=RiskReward(
            entry=100.0, stop=90.0, target=130.0, risk=10.0, reward=30.0, ratio=ratio
        ),
        **common,
    )


def result(subject: Any) -> SetupRunResult:
    return SetupRunResult(requested_symbol=subject.symbol, assessment=subject)


def failed_result(symbol: str, detail: str = "provider timed out") -> SetupRunResult:
    return SetupRunResult(requested_symbol=symbol, failure=detail)


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


def run_of(
    *results: SetupRunResult,
    store: StoreReading | None = None,
    approvals: Any | None = None,
    approval_note: Any = None,
    reference_time: datetime = REFERENCE,
) -> TodayRun:
    """A complete `TodayRun` over the supplied results, assembled offline."""
    held = store if store is not None else reading()
    return TodayRun(
        results=tuple(results),
        reading=held,
        workspace=build_today(
            results,
            held,
            reference_time=reference_time,
            source="fixture",
            approvals=approvals,
            approval_note=approval_note,
        ),
    )


def workspace_of(*results: SetupRunResult, **options: Any):
    """The workspace itself, for tests that never need the run behind it."""
    from fmis.swing_workspace import build_swing_workspace

    return build_swing_workspace(run_of(*results, **options))
