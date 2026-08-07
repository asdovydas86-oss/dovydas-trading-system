"""The deterministic Swing Setup policy — interpretation over facts, never arithmetic.

`evaluate_setup` is the one function in the repository allowed to say `LONG` or
`SHORT` (ADR-0028). It is pure: no network, no clock, no randomness, and no
recomputation of anything an engine below it already produced. Every number it
reads is copied from `SetupInputs`; every conclusion it reaches is reasoned from
at least two independent evidence families, never one.

**The three roles, stated once.** `CONTEXT` and `SETUP` form the thesis; `EXECUTION`
only confirms or withholds it and never votes on direction — kept structurally
separate so a supportive context and a supportive setup can never, by
themselves, manufacture a confirmed trade. See the design record §5–§6 for the
full reasoning.

**Never from one family.** A directional candidate needs at least
`MINIMUM_AGREEING_FAMILIES` independent families agreeing, and **zero** voting
the opposite way. One indicator alone — `RSI < 30 => LONG`, `EMA fast > EMA slow
=> LONG` — cannot reach that bar by construction, because there is only one
family to ask.

**`WAIT` is a first-class, successful result.** Nothing here treats it as a
failure, an exception, or a case requiring an apology.
"""

from __future__ import annotations

from datetime import datetime

from fmis.decision_context import ContextState
from fmis.decision_support import Alignment, OverallState
from fmis.level_crossing import LevelSide, PriceLevel
from fmis.market_regime import StructureState
from fmis.structural_trend import StructuralTrendType
from fmis.swing_setup.models import (
    CONFIRMATION_SIDE,
    NOT_CALIBRATED,
    Direction,
    DirectionalFactor,
    ExecutionBreakEvent,
    Lean,
    RiskReward,
    SetupAssessment,
    SetupInputs,
    SetupState,
    Trigger,
    TriggerKind,
    _STOP_SIDE,
    _TARGET_SIDE,
)

__all__ = [
    "SETUP_POLICY_ID",
    "MINIMUM_AGREEING_FAMILIES",
    "CONFIRMATION_LOOKBACK_BARS",
    "evaluate_setup",
]

#: Carried on every result produced by this module. A version string, matching
#: `RegimePolicy`/`ContextPolicy`'s own convention, so a reader comparing two
#: assessments sees *which* policy differed rather than an opaque digest.
SETUP_POLICY_ID = "swing-setup-v1"

#: How many independent families must agree, with none opposing, before a
#: directional candidate exists. A module constant and deliberately not a
#: parameter — the same discipline `MINIMUM_DIRECTIONAL_SHIFTS` (ADR-0017)
#: applies: a number chosen deliberately and labelled as a choice is honest,
#: while offering it as a per-call knob would let a caller threshold-shop past
#: the single-indicator rule this constant exists to enforce.
MINIMUM_AGREEING_FAMILIES = 2

#: How many of the most recent execution-timeframe bars a confirming break may
#: fall within and still count as confirmation. Stated policy, not a
#: measurement — the same discipline `RegimePolicy.transition_lookback_bars`
#: applies. Without it a break from months earlier, with no bearing on a
#: candidate that only just formed, would silently confirm it; the independent
#: review that found this gap is why the constant exists rather than an
#: assumption that "latest" already meant "recent".
CONFIRMATION_LOOKBACK_BARS = 10


def _trend_lean(trend: StructuralTrendType) -> Lean:
    """`SUSTAINED_HIGHER`/`SUSTAINED_LOWER` vote; `NEUTRAL` conflicts; else abstains.

    `NEUTRAL` means the structural-trend package's own evidence exists on both
    sides and disagrees (its docs say so directly) — that is a real conflict,
    not silence, and is reported as `CONFLICTING` rather than folded into
    `UNAVAILABLE`. `INDETERMINATE` means evidence is absent, which is a genuine
    abstention.
    """
    if trend is StructuralTrendType.SUSTAINED_HIGHER:
        return Lean.LONG
    if trend is StructuralTrendType.SUSTAINED_LOWER:
        return Lean.SHORT
    if trend is StructuralTrendType.NEUTRAL:
        return Lean.CONFLICTING
    return Lean.UNAVAILABLE


def _evidence_lean(
    state: OverallState | None, alignment: Alignment | None
) -> Lean:
    """The setup-role evidence layer's own alignment, read as one family.

    `fmis.decision_support` has already reduced up to five observations to one
    `dominant_alignment` under its own grouping rule (ADR-0008). Reading that
    single value, rather than the individual observations behind it, is what
    keeps this one family instead of several correlated ones.
    """
    if state is None or state is OverallState.INSUFFICIENT_DATA:
        return Lean.UNAVAILABLE
    if state is OverallState.WAIT:
        return Lean.CONFLICTING
    if alignment is Alignment.UPWARD:
        return Lean.LONG
    if alignment is Alignment.DOWNWARD:
        return Lean.SHORT
    return Lean.UNAVAILABLE


def _tally(factors: tuple[DirectionalFactor, ...]) -> Direction | None:
    """A side wins only with at least `MINIMUM_AGREEING_FAMILIES` votes and none opposing.

    A tie, an all-conflicting read, an all-unavailable read, or a single lone
    vote on either side all resolve to ``None`` — no side wins by default, and
    none is broken arbitrarily.
    """
    long_votes = sum(1 for factor in factors if factor.lean is Lean.LONG)
    short_votes = sum(1 for factor in factors if factor.lean is Lean.SHORT)
    if long_votes >= MINIMUM_AGREEING_FAMILIES and short_votes == 0:
        return Direction.LONG
    if short_votes >= MINIMUM_AGREEING_FAMILIES and long_votes == 0:
        return Direction.SHORT
    return None


def _nearest(
    levels: tuple[PriceLevel, ...], *, side: LevelSide, close: float, above: bool
) -> PriceLevel | None:
    """The closest level of ``side`` strictly ``above``/below ``close``, by comparison alone.

    Strict inequality against ``close`` is load-bearing: it is what guarantees a
    selected stop or target can never equal the reference price, so a computed
    risk or reward can never be exactly zero. Ties on price break on the
    origin's bar index, the same total order `structural_facts._level_sort_key`
    uses, so two runs over identical levels choose identically.
    """
    candidates = tuple(
        level
        for level in levels
        if level.side is side and (level.price > close if above else level.price < close)
    )
    if not candidates:
        return None

    def key(level: PriceLevel) -> tuple[float, int]:
        origin_index = level.origin.index if level.origin is not None else -1
        return (level.price, origin_index)

    return min(candidates, key=key) if above else max(candidates, key=key)


def _latest_matching_break(
    breaks: tuple[ExecutionBreakEvent, ...], *, side: LevelSide
) -> ExecutionBreakEvent | None:
    """The most recent break on ``side``, searched by side rather than trusting a single "latest".

    `fmis.structure_break` can emit an upper and a lower break on the same bar,
    ordered upper-before-lower — so the array's last element is not
    necessarily the last element *on the side a candidate needs*, and always
    resolves ties toward the lower side. Searching backward for the first
    match on the requested side removes that asymmetry rather than trusting
    positional order to mean what it does not.
    """
    for event in reversed(breaks):
        if event.level.side is side:
            return event
    return None


def _risk_reward(direction: Direction, close: float, stop: PriceLevel, target: PriceLevel) -> RiskReward:
    """Risk and reward, computed from levels `_nearest` already proved are on the correct side.

    Both differences are strictly positive by construction: `_nearest` only ever
    returns a stop strictly on the protective side of ``close`` and a target
    strictly on the far side, so this function never needs to reject a bad
    geometry — it was made unrepresentable one call earlier.
    """
    if direction is Direction.LONG:
        reward = target.price - close
        risk = close - stop.price
    else:
        reward = close - target.price
        risk = stop.price - close
    return RiskReward(
        entry=close, stop=stop.price, target=target.price,
        risk=risk, reward=reward, ratio=reward / risk,
    )


def _regime_context_lines(inputs: SetupInputs) -> tuple[str, ...]:
    return (
        f"context ({inputs.context_interval}) regime: "
        f"structure={inputs.context_regime_structure.value}, "
        f"volatility={inputs.context_regime_volatility.value}, "
        f"participation={inputs.context_regime_participation.value}",
    )


def _factor_observed(family: str, inputs: SetupInputs) -> str:
    if family == "context_structural_trend":
        return inputs.context_structural_trend.value
    if family == "setup_structural_trend":
        return inputs.setup_structural_trend.value
    state = inputs.evidence_state
    alignment = inputs.evidence_dominant_alignment
    if state is None:
        return "no evidence report"
    return f"{state.value} (dominant={alignment.value if alignment is not None else 'none'})"


def _directional_factors(inputs: SetupInputs) -> tuple[DirectionalFactor, ...]:
    return (
        DirectionalFactor(
            family="context_structural_trend",
            lean=_trend_lean(inputs.context_structural_trend),
            observed=_factor_observed("context_structural_trend", inputs),
            source=f"fmis.structural_trend ({inputs.context_interval})",
        ),
        DirectionalFactor(
            family="setup_structural_trend",
            lean=_trend_lean(inputs.setup_structural_trend),
            observed=_factor_observed("setup_structural_trend", inputs),
            source=f"fmis.structural_trend ({inputs.setup_interval})",
        ),
        DirectionalFactor(
            family="setup_evidence_alignment",
            lean=_evidence_lean(inputs.evidence_state, inputs.evidence_dominant_alignment),
            observed=_factor_observed("setup_evidence_alignment", inputs),
            source="fmis.decision_support",
        ),
    )


def _wait(
    inputs: SetupInputs,
    factors: tuple[DirectionalFactor, ...],
    thesis: tuple[str, ...],
) -> SetupAssessment:
    limitations = inputs.inherited_limitations + _extra_limitations(factors)
    return SetupAssessment(
        symbol=inputs.symbol,
        as_of=inputs.as_of,
        objective="swing",
        state=SetupState.WAIT,
        direction=None,
        thesis=thesis,
        directional_factors=factors,
        confirmation=(),
        invalidation=(),
        trigger=None,
        reference_price=None,
        stop=None,
        targets=(),
        risk_reward=None,
        probability=NOT_CALIBRATED,
        regime_context=_regime_context_lines(inputs),
        sufficiency=inputs.decision_context_state,
        limitations=limitations,
        policy_id=SETUP_POLICY_ID,
        source=inputs.source,
    )


def _extra_limitations(factors: tuple[DirectionalFactor, ...]) -> tuple[str, ...]:
    """One line per family that did not vote, naming why. Transparency, not noise."""
    lines = []
    for factor in factors:
        if factor.lean is Lean.CONFLICTING:
            lines.append(
                f"{factor.family} conflicts with itself ({factor.observed}) and "
                "cast no vote."
            )
        elif factor.lean is Lean.UNAVAILABLE:
            lines.append(f"{factor.family} was unavailable and cast no vote.")
    return tuple(lines)


def evaluate_setup(inputs: SetupInputs) -> SetupAssessment:
    """Interpret already-computed facts into one deterministic setup assessment.

    Pure: no network, no clock, no randomness. Equal inputs give an equal
    assessment, always.
    """
    if not isinstance(inputs, SetupInputs):
        raise TypeError(f"inputs must be a SetupInputs, got {type(inputs).__name__}")

    factors = _directional_factors(inputs)

    if inputs.decision_context_state is ContextState.INSUFFICIENT:
        reasons = inputs.decision_context_statements or (
            "a blocking decision-context requirement is unmet",
        )
        thesis = (
            "Decision context is INSUFFICIENT: " + "; ".join(reasons) + ". "
            "No directional candidate may be formed from data the system has "
            "already flagged as inadequate.",
        )
        return _wait(inputs, factors, thesis)

    if inputs.context_regime_structure is not StructureState.TRENDING:
        thesis = (
            f"Context-role ({inputs.context_interval}) regime structure is "
            f"{inputs.context_regime_structure.value}, not trending. A "
            "directional swing thesis requires a trending higher-timeframe "
            "environment; this package does not infer a direction from a "
            "regime, which classifies environment only.",
        )
        return _wait(inputs, factors, thesis)

    direction = _tally(factors)
    if direction is None:
        long_votes = sum(1 for f in factors if f.lean is Lean.LONG)
        short_votes = sum(1 for f in factors if f.lean is Lean.SHORT)
        conflicting = sum(1 for f in factors if f.lean is Lean.CONFLICTING)
        unavailable = sum(1 for f in factors if f.lean is Lean.UNAVAILABLE)
        thesis = (
            f"Directional factors do not agree: {long_votes} long, "
            f"{short_votes} short, {conflicting} conflicting, {unavailable} "
            f"unavailable. At least {MINIMUM_AGREEING_FAMILIES} independent "
            "families must agree with none opposing before a candidate exists.",
        )
        return _wait(inputs, factors, thesis)

    # A candidate exists. Confirmation is EXECUTION-role only, and never votes
    # on direction — see the module docstring.
    confirmation_side = CONFIRMATION_SIDE[direction]
    opposite_trend = (
        StructuralTrendType.SUSTAINED_LOWER
        if direction is Direction.LONG
        else StructuralTrendType.SUSTAINED_HIGHER
    )
    execution_opposes = inputs.execution_structural_trend is opposite_trend
    matching_break = _latest_matching_break(inputs.execution_breaks, side=confirmation_side)
    break_age = (
        None
        if matching_break is None
        else inputs.execution_closed_count - 1 - matching_break.index
    )
    break_is_stale = break_age is not None and break_age > CONFIRMATION_LOOKBACK_BARS
    break_confirms = matching_break is not None and not break_is_stale

    agreeing = tuple(f for f in factors if f.lean.value == direction.value)
    thesis = tuple(
        f"{factor.family} leans {factor.lean.value} ({factor.observed}, {factor.source})."
        for factor in agreeing
    )

    reference_price = inputs.execution_close
    stop = target = None
    if reference_price is not None:
        stop = _nearest(
            inputs.execution_levels,
            side=_STOP_SIDE[direction],
            close=reference_price,
            above=(_STOP_SIDE[direction] is LevelSide.UPPER),
        )
        target = _nearest(
            inputs.setup_levels,
            side=_TARGET_SIDE[direction],
            close=reference_price,
            above=(_TARGET_SIDE[direction] is LevelSide.UPPER),
        )
    targets = (target,) if target is not None else ()
    risk_reward = (
        _risk_reward(direction, reference_price, stop, target)
        if stop is not None and target is not None
        else None
    )

    if stop is not None:
        invalidation = (
            f"Structural invalidation: a confirmed close beyond the "
            f"{stop.side.value} level at {stop.price} on the execution "
            f"timeframe ({inputs.execution_interval}) — the same level "
            "reported as the stop.",
        )
    else:
        invalidation = (
            "No structural invalidation level is available in the current "
            "execution-timeframe window; treat the thesis as invalidated if "
            "the directional factors above reverse.",
        )

    if break_confirms and not execution_opposes and reference_price is not None:
        state = SetupState.CONFIRMED
        broken = matching_break.level
        confirmation = (
            f"Confirmed: execution timeframe ({inputs.execution_interval}) "
            f"closed beyond the {broken.side.value} level at {broken.price}, "
            f"bar {matching_break.index} ({break_age} bar(s) ago) — the "
            "confirmation this policy requires.",
        )
        trigger = Trigger(
            kind=TriggerKind.CONFIRMED_STRUCTURE_BREAK,
            statement=confirmation[0],
            level=broken,
            bar_index=matching_break.index,
        )
    else:
        state = SetupState.CANDIDATE
        watched = None
        if reference_price is not None:
            watched = _nearest(
                inputs.execution_levels,
                side=confirmation_side,
                close=reference_price,
                above=(confirmation_side is LevelSide.UPPER),
            )
        notes = []
        if reference_price is None:
            notes.append("no execution-timeframe data is available in this window")
        if matching_break is not None and break_is_stale:
            notes.append(
                f"the most recent matching execution-timeframe break is "
                f"{break_age} bar(s) old, beyond the "
                f"{CONFIRMATION_LOOKBACK_BARS}-bar confirmation window"
            )
        elif matching_break is None and inputs.execution_breaks:
            notes.append(
                f"no execution-timeframe break on the {confirmation_side.value} "
                "side has occurred in this window"
            )
        if execution_opposes:
            notes.append(
                "execution-timeframe structural trend is sustained in the "
                "opposite direction"
            )
        if watched is not None:
            base = (
                f"Awaiting a confirmed close beyond the {confirmation_side.value} "
                f"level at {watched.price} on the execution timeframe "
                f"({inputs.execution_interval})"
            )
        else:
            base = (
                f"Awaiting a confirmed close beyond a {confirmation_side.value} "
                f"level on the execution timeframe ({inputs.execution_interval}); "
                "none is available in the current window"
            )
        statement = base + (f"; {'; '.join(notes)}." if notes else ".")
        confirmation = (statement,)
        trigger = Trigger(
            kind=TriggerKind.AWAITING_STRUCTURE_BREAK,
            statement=statement,
            level=watched,
            bar_index=None,
        )

    limitations = inputs.inherited_limitations + _extra_limitations(factors)
    if inputs.decision_context_state is ContextState.LIMITED:
        limitations = limitations + (
            "Decision context is LIMITED: " + "; ".join(inputs.decision_context_statements)
            + ".",
        ) if inputs.decision_context_statements else limitations + (
            "Decision context is LIMITED.",
        )

    return SetupAssessment(
        symbol=inputs.symbol,
        as_of=inputs.as_of,
        objective="swing",
        state=state,
        direction=direction,
        thesis=thesis,
        directional_factors=factors,
        confirmation=confirmation,
        invalidation=invalidation,
        trigger=trigger,
        reference_price=reference_price,
        stop=stop,
        targets=targets,
        risk_reward=risk_reward,
        probability=NOT_CALIBRATED,
        regime_context=_regime_context_lines(inputs),
        sufficiency=inputs.decision_context_state,
        limitations=limitations,
        policy_id=SETUP_POLICY_ID,
        source=inputs.source,
    )
