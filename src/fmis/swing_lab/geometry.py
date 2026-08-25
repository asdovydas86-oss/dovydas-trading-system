"""Trade geometry as an explicit, separately-specified policy. **Research only.**

Milestone BW measured the production swing strategy and found the binding defect
was not a filter but arithmetic: the policy places the stop at the *nearest*
execution-timeframe level and the target at the *nearest* setup-timeframe level,
and **nothing requires the target to be further away than the stop**. Half the
setups planned a reward smaller than their risk, and the strategy's average
winner paid less than its average loser cost.

This module makes that geometry a **named, swappable, pre-declared policy** so
alternatives can be measured against it rather than argued about.

    GeometryCandidate   the facts frozen at the decision instant
            │
            ▼
    GeometryPolicy      a stop rule, a target rule, and admission rules
            │
            ▼
    GeometryPlan | GeometrySkip

**Three rules this module exists to obey.**

1. **A level is never invented.** Every stop and every target returned here is a
   `PriceLevel` the structural engines already produced, selected from
   `fmis.swing_setup.policy.ordered_levels` — the same ordering production uses,
   called rather than restated. There is no rule that computes a price, and a
   test asserts this module never constructs a `PriceLevel`. "Place the target
   at 2R" is unrepresentable here, deliberately: it would manufacture a market
   fact to hit an arithmetic goal.
2. **An admission rule may only *refuse*.** `min_planned_rr` and `min_stop_atr`
   can turn a trade into a skip. Neither can move a level, widen a stop or
   extend a target. A geometry that cannot meet the requirement is not traded.
3. **Outcome statistics cannot reach this module.** Nothing here reads an MFE,
   an MAE, a realized R or any bar after the decision instant.
   `GeometryCandidate` carries no such field, so a lookahead is not merely
   forbidden — it is unrepresentable. `fmis.swing_lab.geometry_outcome` owns the
   after-the-fact measurements and is imported by no policy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Final

from fmis.level_crossing import LevelSide, PriceLevel
from fmis.swing_lab.models import SwingLabError
from fmis.swing_setup.models import STOP_SIDE, TARGET_SIDE, Direction
from fmis.swing_setup.policy import ordered_levels

__all__ = [
    "BASIS_POINT",
    "LevelRef",
    "GeometryCandidate",
    "StopRule",
    "TargetRule",
    "VolatilitySource",
    "GeometryPolicy",
    "SkipReason",
    "GeometrySkip",
    "GeometryPlan",
    "plan_geometry",
    "level_refs",
]

#: One basis point as a fraction. Named so a conversion is never a bare 10_000
#: sitting in an expression where a reader must infer which way it divides.
BASIS_POINT: Final[float] = 0.0001


@dataclass(frozen=True, slots=True)
class LevelRef:
    """One structural level, with enough provenance to say where it came from.

    A flattened, JSON-safe view of a `PriceLevel` plus the interval whose
    structure produced it. The interval is **not** on `PriceLevel` itself — a
    level does not know which timeframe derived it — and the whole point of this
    milestone is comparing a 4H stop against a 1D one, so it is carried here.
    """

    price: float
    side: LevelSide
    interval: str
    origin_index: int | None
    origin_label: str | None

    def __post_init__(self) -> None:
        if isinstance(self.price, bool) or not isinstance(self.price, (int, float)):
            raise TypeError("price must be a number")
        if not isinstance(self.side, LevelSide):
            raise TypeError("side must be a LevelSide")
        if not isinstance(self.interval, str) or not self.interval.strip():
            raise SwingLabError("interval must be a non-empty str")

    @property
    def provenance(self) -> str:
        """A short human-readable source, e.g. ``4h:swing_high@231``."""
        label = self.origin_label or "unattributed"
        index = "?" if self.origin_index is None else str(self.origin_index)
        return f"{self.interval}:{label}@{index}"


def level_refs(levels: Sequence[PriceLevel], *, interval: str) -> tuple[LevelRef, ...]:
    """Adapt production `PriceLevel`s into research refs. A copy, never a computation."""
    return tuple(
        LevelRef(
            price=level.price,
            side=level.side,
            interval=interval,
            origin_index=None if level.origin is None else level.origin.index,
            origin_label=(
                None
                if level.origin is None
                else getattr(level.origin.label, "value", str(level.origin.label))
            ),
        )
        for level in levels
    )


@dataclass(frozen=True, slots=True)
class GeometryCandidate:
    """Every geometry-relevant fact, frozen at the instant the setup confirmed.

    **This is the no-lookahead boundary.** A candidate is built inside the replay
    from the same `SetupInputs` the production policy read, at the same instant,
    and every geometry policy is then evaluated over the frozen record with no
    further access to history. A future bar cannot change a plan because no
    policy can see one: the only forward-looking object in this package is a
    simulated trade, which is produced *from* a plan and can never feed one.

    The level lists are already **nearest-first**, ordered by
    `fmis.swing_setup.policy.ordered_levels`, so a policy selecting the second or
    third level agrees with production about what "nearer" means.
    """

    symbol: str
    setup_id: str
    direction: Direction
    signal_at: datetime
    signal_index: int
    reference_price: float
    #: Protective-side levels on the EXECUTION timeframe (4H under production).
    execution_stop_levels: tuple[LevelRef, ...]
    #: Protective-side levels on the SETUP timeframe (1D under production).
    setup_stop_levels: tuple[LevelRef, ...]
    #: Objective-side levels on the SETUP timeframe (1D under production).
    setup_target_levels: tuple[LevelRef, ...]
    #: Objective-side levels on the CONTEXT timeframe (1W under production).
    context_target_levels: tuple[LevelRef, ...]
    #: Wilder ATR(14) on the execution timeframe, or ``None`` while warming up.
    execution_atr: float | None
    #: Wilder ATR(14) on the setup timeframe, or ``None`` while warming up.
    setup_atr: float | None
    context_interval: str
    setup_interval: str
    execution_interval: str
    segment: str | None
    context_regime_structure: str
    context_regime_volatility: str
    context_structural_trend: str
    setup_structural_trend: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.direction, Direction):
            raise TypeError("direction must be a Direction")
        if (
            isinstance(self.reference_price, bool)
            or not isinstance(self.reference_price, (int, float))
            or self.reference_price <= 0
        ):
            raise SwingLabError("reference_price must be a positive number")
        for name in ("execution_atr", "setup_atr"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number or None")
            if value <= 0:
                # A zero or negative ATR is not a quiet "no volatility" — it is a
                # broken measurement, and normalising by it would divide by zero
                # or flip a comparison. Refused at construction.
                raise SwingLabError(f"{name} must be positive when present, got {value}")

    @property
    def stop_side(self) -> LevelSide:
        return STOP_SIDE[self.direction]

    @property
    def target_side(self) -> LevelSide:
        return TARGET_SIDE[self.direction]


class StopRule(str, Enum):
    """Where the initial stop comes from. Every member selects a real level.

    * `NEAREST_EXECUTION` — **production**: the nearest execution-timeframe (4H)
      structural level on the protective side.
    * `NEAREST_SETUP` — the nearest *setup*-timeframe (1D) protective level. The
      question this asks is BW defect 2's: is the 4H level the setup's true
      invalidation, or merely the closest thing to the entry?
    * `EXECUTION_BEYOND_VOLATILITY` — the nearest execution-timeframe protective
      level that is at least ``min_stop_atr`` ATR away. Not a widened stop: a
      *different, real* level, skipped entirely if none qualifies.
    """

    NEAREST_EXECUTION = "nearest_execution"
    NEAREST_SETUP = "nearest_setup"
    EXECUTION_BEYOND_VOLATILITY = "execution_beyond_volatility"


class TargetRule(str, Enum):
    """Where the target comes from. Every member selects a real level.

    * `NEAREST_SETUP` — **production**: the nearest setup-timeframe (1D) level
      on the objective side.
    * `SECOND_SETUP` — the *second* nearest such level. Skipped when the engine
      identified only one, never substituted with the first.
    * `NEAREST_CONTEXT` — the nearest context-timeframe (1W) objective level: a
      structurally larger objective, already computed, never interpolated.
    * `FIRST_SETUP_SUPPORTING_RR` — the nearest setup-timeframe level whose
      reward reaches ``min_planned_rr`` times the risk. This **selects among
      levels the engine produced**; it never moves one. When no real level
      qualifies the trade is skipped, which is the distinction the brief draws
      between choosing a structural target and manufacturing an R multiple.
    """

    NEAREST_SETUP = "nearest_setup"
    SECOND_SETUP = "second_setup"
    NEAREST_CONTEXT = "nearest_context"
    FIRST_SETUP_SUPPORTING_RR = "first_setup_supporting_rr"


class VolatilitySource(str, Enum):
    """Which existing ATR normalises a stop distance. No new volatility engine.

    Both members name a Wilder ATR(14) that `fmis.pipeline.regime.regime_features`
    already computes on that timeframe's own candles. This milestone adds no
    volatility calculation of any kind.
    """

    EXECUTION_ATR = "execution_atr"
    SETUP_ATR = "setup_atr"


class SkipReason(str, Enum):
    """Why a candidate produced no trade. **Every refusal is named and counted.**

    A skipped candidate is never silently dropped: `GeometrySkip` is a result,
    not an absence, so a variant that trades rarely and a variant that trades
    often can be compared on *why* they differ rather than only on how many
    trades came out.
    """

    NO_STOP_LEVEL = "no_stop_level"
    NO_TARGET_LEVEL = "no_target_level"
    NO_SECOND_TARGET_LEVEL = "no_second_target_level"
    NO_VOLATILITY_MEASURE = "no_volatility_measure"
    STOP_INSIDE_VOLATILITY = "stop_inside_volatility"
    BELOW_MINIMUM_PLANNED_RR = "below_minimum_planned_rr"

    @property
    def statement(self) -> str:
        return _SKIP_STATEMENTS[self]


_SKIP_STATEMENTS: Final[dict[SkipReason, str]] = {
    SkipReason.NO_STOP_LEVEL: (
        "no structural level exists on the protective side of the entry on the "
        "timeframe this rule reads"
    ),
    SkipReason.NO_TARGET_LEVEL: (
        "no structural level exists on the objective side of the entry on the "
        "timeframe this rule reads"
    ),
    SkipReason.NO_SECOND_TARGET_LEVEL: (
        "the engine identified only one objective-side level, and this rule asks "
        "for the second; the first is deliberately not substituted"
    ),
    SkipReason.NO_VOLATILITY_MEASURE: (
        "the volatility measure this rule normalises by was still warming up"
    ),
    SkipReason.STOP_INSIDE_VOLATILITY: (
        "every available structural stop sits closer to the entry than the "
        "required multiple of ordinary bar range"
    ),
    SkipReason.BELOW_MINIMUM_PLANNED_RR: (
        "the real structural target does not pay the required multiple of the "
        "risk; the target is not moved to make it"
    ),
}


@dataclass(frozen=True, slots=True)
class GeometrySkip:
    """A candidate this policy declined, and the named reason it declined it."""

    candidate: GeometryCandidate
    policy_id: str
    reason: SkipReason
    #: The planned R:R that failed the test, when one could be computed at all.
    #: Present only for `BELOW_MINIMUM_PLANNED_RR`, so a reader can see *how
    #: far* short the geometry fell rather than only that it did.
    observed_planned_rr: float | None = None

    @property
    def statement(self) -> str:
        return self.reason.statement


@dataclass(frozen=True, slots=True)
class GeometryPlan:
    """A stop, a target, and every distance a diagnosis needs — all derived.

    Nothing here is stored that could be recomputed from ``entry``, ``stop`` and
    ``target``; the derived distances are computed once at construction because
    a dozen call sites re-deriving `planned_rr` is a dozen chances to divide the
    wrong way, not because the value is a fact worth persisting.
    """

    candidate: GeometryCandidate
    policy_id: str
    entry: float
    stop: LevelRef
    target: LevelRef
    risk: float
    reward: float
    planned_rr: float
    stop_bps: float
    target_bps: float
    stop_atr_multiple: float | None
    target_atr_multiple: float | None

    def __post_init__(self) -> None:
        # These are guaranteed by `ordered_levels`' strict inequality, and are
        # re-asserted because this is the type every downstream measurement
        # trusts. A zero risk would make every R multiple infinite and a
        # negative one would silently invert every win and loss.
        if self.risk <= 0:
            raise SwingLabError(f"risk must be positive, got {self.risk}")
        if self.reward <= 0:
            raise SwingLabError(f"reward must be positive, got {self.reward}")

    @property
    def stop_source(self) -> str:
        return self.stop.provenance

    @property
    def target_source(self) -> str:
        return self.target.provenance

    @property
    def reward_below_risk(self) -> bool:
        """The BW defect, as a predicate: this trade plans to win less than it risks."""
        return self.planned_rr < 1.0

    @property
    def entry_position_in_range(self) -> float:
        """Where the entry sits between its own stop and target, 0.0 → 1.0.

        0.0 means the entry is *at* the stop (all of the structural range is
        reward); 1.0 means it is at the target (all of it is risk). It is
        `risk / (risk + reward)` and therefore a restatement of the planned R:R
        — carried under its own name because the entry-quality question in §6 of
        the brief is asked in these terms and answering it by eye from an R:R
        invites the reader to do the algebra wrongly.
        """
        return self.risk / (self.risk + self.reward)


def _select_stop(
    candidate: GeometryCandidate, policy: GeometryPolicy
) -> tuple[LevelRef | None, SkipReason | None]:
    """Apply one stop rule. Returns the chosen level or the named refusal."""
    if policy.stop_rule is StopRule.NEAREST_EXECUTION:
        levels = candidate.execution_stop_levels
        return (levels[0], None) if levels else (None, SkipReason.NO_STOP_LEVEL)

    if policy.stop_rule is StopRule.NEAREST_SETUP:
        levels = candidate.setup_stop_levels
        return (levels[0], None) if levels else (None, SkipReason.NO_STOP_LEVEL)

    levels = candidate.execution_stop_levels
    if not levels:
        return None, SkipReason.NO_STOP_LEVEL
    atr = policy.volatility_of(candidate)
    if atr is None:
        return None, SkipReason.NO_VOLATILITY_MEASURE
    floor = policy.min_stop_atr
    if floor is None:  # pragma: no cover - forbidden by GeometryPolicy.__post_init__
        raise SwingLabError(
            "EXECUTION_BEYOND_VOLATILITY requires min_stop_atr; "
            "GeometryPolicy should have refused this policy at construction"
        )
    required = floor * atr
    for level in levels:
        if abs(candidate.reference_price - level.price) >= required:
            return level, None
    return None, SkipReason.STOP_INSIDE_VOLATILITY


def _reward(candidate: GeometryCandidate, price: float) -> float:
    if candidate.direction is Direction.LONG:
        return price - candidate.reference_price
    return candidate.reference_price - price


def _select_target(
    candidate: GeometryCandidate, policy: GeometryPolicy, risk: float
) -> tuple[LevelRef | None, SkipReason | None]:
    """Apply one target rule. Returns the chosen level or the named refusal."""
    if policy.target_rule is TargetRule.NEAREST_SETUP:
        levels = candidate.setup_target_levels
        return (levels[0], None) if levels else (None, SkipReason.NO_TARGET_LEVEL)

    if policy.target_rule is TargetRule.SECOND_SETUP:
        levels = candidate.setup_target_levels
        if not levels:
            return None, SkipReason.NO_TARGET_LEVEL
        if len(levels) < 2:
            return None, SkipReason.NO_SECOND_TARGET_LEVEL
        return levels[1], None

    if policy.target_rule is TargetRule.NEAREST_CONTEXT:
        levels = candidate.context_target_levels
        return (levels[0], None) if levels else (None, SkipReason.NO_TARGET_LEVEL)

    levels = candidate.setup_target_levels
    if not levels:
        return None, SkipReason.NO_TARGET_LEVEL
    required = policy.min_planned_rr
    if required is None:  # pragma: no cover - forbidden by GeometryPolicy.__post_init__
        raise SwingLabError(
            "FIRST_SETUP_SUPPORTING_RR requires min_planned_rr; "
            "GeometryPolicy should have refused this policy at construction"
        )
    for level in levels:
        if _reward(candidate, level.price) >= required * risk:
            return level, None
    return None, SkipReason.BELOW_MINIMUM_PLANNED_RR


@dataclass(frozen=True, slots=True)
class GeometryPolicy:
    """One pre-declared way of turning a confirmed setup into a stop and a target.

    ``family`` records which question of the brief the policy answers (A–F), so a
    result table can never present an isolated experiment and a combination as
    though they were the same kind of claim.

    ``is_production_geometry`` is the control: nearest 4H stop, nearest 1D
    target, no admission rule. It must reproduce the live product exactly, and
    the study measures that rather than asserting it.
    """

    policy_id: str
    title: str
    family: str
    hypothesis: str
    stop_rule: StopRule
    target_rule: TargetRule
    min_planned_rr: float | None = None
    min_stop_atr: float | None = None
    volatility_source: VolatilitySource = VolatilitySource.EXECUTION_ATR

    def __post_init__(self) -> None:
        for name in ("policy_id", "title", "family", "hypothesis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingLabError(f"{name} must be a non-empty str")
        if not isinstance(self.stop_rule, StopRule):
            raise TypeError("stop_rule must be a StopRule")
        if not isinstance(self.target_rule, TargetRule):
            raise TypeError("target_rule must be a TargetRule")
        if not isinstance(self.volatility_source, VolatilitySource):
            raise TypeError("volatility_source must be a VolatilitySource")
        for name in ("min_planned_rr", "min_stop_atr"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number or None")
            if value <= 0:
                raise SwingLabError(f"{name} must be positive when set, got {value}")
        # A rule that reads a parameter must be given one. Defaulting a missing
        # threshold to zero would turn "volatility-aware" into "no filter" and
        # the result table would show a variant that quietly ran as the baseline.
        if self.stop_rule is StopRule.EXECUTION_BEYOND_VOLATILITY and self.min_stop_atr is None:
            raise SwingLabError(
                "StopRule.EXECUTION_BEYOND_VOLATILITY needs min_stop_atr; without "
                "one it would silently be the production stop rule"
            )
        if (
            self.target_rule is TargetRule.FIRST_SETUP_SUPPORTING_RR
            and self.min_planned_rr is None
        ):
            raise SwingLabError(
                "TargetRule.FIRST_SETUP_SUPPORTING_RR needs min_planned_rr; without "
                "one it would silently be the production target rule"
            )

    @property
    def is_production_geometry(self) -> bool:
        """``True`` only for the exact live rule with no admission test at all."""
        return (
            self.stop_rule is StopRule.NEAREST_EXECUTION
            and self.target_rule is TargetRule.NEAREST_SETUP
            and self.min_planned_rr is None
            and self.min_stop_atr is None
        )

    def volatility_of(self, candidate: GeometryCandidate) -> float | None:
        """The ATR this policy normalises by, read from the candidate. Never computed."""
        if self.volatility_source is VolatilitySource.EXECUTION_ATR:
            return candidate.execution_atr
        return candidate.setup_atr


def plan_geometry(
    candidate: GeometryCandidate, policy: GeometryPolicy
) -> GeometryPlan | GeometrySkip:
    """Apply one geometry policy to one frozen candidate. **Pure and total.**

    Deterministic: no clock, no randomness, no network, no market access. The
    same candidate and the same policy always produce the same result, and the
    result is always one of the two named types — there is no path that returns
    ``None``, raises for an ordinary market condition, or falls back to the
    production rule when its own rule cannot be satisfied. A rule that cannot be
    satisfied produces a `GeometrySkip` naming why.

    The order of operations is load-bearing and is stated here because it
    decides what a skip *means*:

    1. the stop is selected, because risk is the denominator of everything after;
    2. the volatility floor is applied to that risk;
    3. the target is selected, which for one rule depends on the risk from (1);
    4. the planned R:R floor is applied last.

    Raises:
        TypeError: the arguments are not a candidate and a policy. A market
            condition is never an exception here.
    """
    if not isinstance(candidate, GeometryCandidate):
        raise TypeError(
            f"candidate must be a GeometryCandidate, got {type(candidate).__name__}"
        )
    if not isinstance(policy, GeometryPolicy):
        raise TypeError(f"policy must be a GeometryPolicy, got {type(policy).__name__}")

    entry = candidate.reference_price

    stop, refusal = _select_stop(candidate, policy)
    if stop is None:
        return GeometrySkip(candidate=candidate, policy_id=policy.policy_id, reason=refusal)
    risk = abs(entry - stop.price)
    if risk <= 0:  # pragma: no cover - ordered_levels' strict inequality forbids it
        raise SwingLabError(
            f"selected stop {stop.price} equals the entry {entry}; ordered_levels "
            "should have excluded it"
        )

    atr = policy.volatility_of(candidate)

    # (2) The volatility floor. Applied to whichever stop rule ran, so a policy
    # combining a deeper structural stop with a volatility floor still refuses a
    # stop that is structurally real but economically inside ordinary noise.
    if policy.min_stop_atr is not None:
        if atr is None:
            return GeometrySkip(
                candidate=candidate,
                policy_id=policy.policy_id,
                reason=SkipReason.NO_VOLATILITY_MEASURE,
            )
        if risk < policy.min_stop_atr * atr:
            return GeometrySkip(
                candidate=candidate,
                policy_id=policy.policy_id,
                reason=SkipReason.STOP_INSIDE_VOLATILITY,
            )

    target, refusal = _select_target(candidate, policy, risk)
    if target is None:
        return GeometrySkip(candidate=candidate, policy_id=policy.policy_id, reason=refusal)
    reward = _reward(candidate, target.price)
    if reward <= 0:  # pragma: no cover - ordered_levels' strict inequality forbids it
        raise SwingLabError(
            f"selected target {target.price} is not beyond the entry {entry} for "
            f"a {candidate.direction.value}; ordered_levels should have excluded it"
        )

    planned_rr = reward / risk

    # (4) The planned-R:R floor, last, because it is a judgement about the
    # completed geometry rather than about either level on its own.
    if policy.min_planned_rr is not None and planned_rr < policy.min_planned_rr:
        return GeometrySkip(
            candidate=candidate,
            policy_id=policy.policy_id,
            reason=SkipReason.BELOW_MINIMUM_PLANNED_RR,
            observed_planned_rr=planned_rr,
        )

    return GeometryPlan(
        candidate=candidate,
        policy_id=policy.policy_id,
        entry=entry,
        stop=stop,
        target=target,
        risk=risk,
        reward=reward,
        planned_rr=planned_rr,
        stop_bps=(risk / entry) / BASIS_POINT,
        target_bps=(reward / entry) / BASIS_POINT,
        stop_atr_multiple=None if atr is None else risk / atr,
        target_atr_multiple=None if atr is None else reward / atr,
    )
