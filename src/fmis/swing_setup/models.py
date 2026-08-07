"""Value types for the Swing Setup Engine.

This is the one package in the repository permitted to represent trading
direction — see [ADR-0028](../../../docs/adr/ADR-0028-directional-interpretation-boundary.md).
Every model here is frozen, and every field states plainly when a value is not
justified by the facts: there is no sentinel number anywhere, only ``None`` or an
explicit status enum.

**`state` and `direction` are two different dimensions, on purpose.** A weak
`LONG` hypothesis (`state=CANDIDATE, direction=LONG`) is not a confirmed trade
(`state=CONFIRMED`). There is no `BUY`/`SELL` state, because collapsing the two
would let a caller read readiness off a name that only ever meant direction.

**Nothing here is computed.** `stop` and every entry of `targets` are
`fmis.level_crossing.PriceLevel` objects **by reference** — already produced by
`fmis.level_crossing`, never rebuilt. Wrapping them in a new type would be the
duplicated-value pattern ADR-0016 §4 already rejected.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from fmis.decision_context import ContextState
from fmis.decision_support import Alignment, OverallState
from fmis.level_crossing import LevelSide, PriceLevel
from fmis.market_regime import ParticipationState, StructureState, VolatilityState
from fmis.structural_trend import StructuralTrendType

__all__ = [
    "SETUP_SCHEMA_VERSION",
    "SwingSetupError",
    "SetupState",
    "Direction",
    "Lean",
    "DirectionalFactor",
    "TriggerKind",
    "Trigger",
    "RiskReward",
    "ProbabilityStatus",
    "Probability",
    "NOT_CALIBRATED",
    "SetupAssessment",
    "SetupInputs",
    "ExecutionBreakEvent",
    "CONFIRMATION_SIDE",
]

#: Bumped when the serialized shape changes in a way a consumer must notice.
SETUP_SCHEMA_VERSION = 1


class SwingSetupError(Exception):
    """Base class for every swing-setup failure.

    Follows the package-error convention `IngestError`, `WorkspaceError`,
    `MarketRegimeError` and `DecisionContextError` established elsewhere, so a
    caller can catch this layer's failures as a group.
    """


class SetupState(str, Enum):
    """How far a swing idea has gone. Never a trade direction.

    * `WAIT` — no directional candidate exists. A successful, first-class
      result — not an error, and not a degraded case of the other two.
    * `CANDIDATE` — a directional thesis exists (`direction` is set), but the
      execution-timeframe confirmation this policy requires has not occurred.
    * `CONFIRMED` — the thesis has confirmed under this policy's stated rule.

    Deliberately absent: `BUY`, `SELL`, or any member combining readiness with
    direction. See the module docstring.
    """

    WAIT = "wait"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"


class Direction(str, Enum):
    """Which side a directional candidate leans. Two members, symmetric.

    `None` on `SetupAssessment.direction` — never a third member here — is what
    a `WAIT` result carries, so "no direction" cannot be confused with a real,
    named third state.
    """

    LONG = "long"
    SHORT = "short"


class Lean(str, Enum):
    """Which way one independent evidence family leans, or why it does not count.

    * `LONG` / `SHORT` — this family's own directional reading.
    * `CONFLICTING` — the family's own evidence disagrees with itself (e.g. a
      structural trend reported `NEUTRAL`, or evidence reported `WAIT`). Not the
      same as being unavailable: something was read, and it did not agree.
    * `UNAVAILABLE` — nothing could be read from this family at all.

    Never counted as a vote for either side: `CONFLICTING` and `UNAVAILABLE`
    both fail to add a vote, for different, stated reasons.
    """

    LONG = "long"
    SHORT = "short"
    CONFLICTING = "conflicting"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class DirectionalFactor:
    """One independent evidence family, its lean, and what produced it.

    ``family`` names the family so a reader can check the tally by hand rather
    than trust it — the same discipline `RegimeEvidence.source` and
    `RequirementCheck.source` already apply. ``observed`` restates the raw fact
    read (an enum value); ``source`` names the engine that produced it.
    """

    family: str
    lean: Lean
    observed: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.family, str) or not self.family.strip():
            raise SwingSetupError("family must be a non-empty str")
        if not isinstance(self.lean, Lean):
            raise TypeError(f"lean must be a Lean, got {type(self.lean).__name__}")
        for name in ("observed", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingSetupError(f"{name} must be a non-empty str")


class TriggerKind(str, Enum):
    """What kind of execution-timeframe event the trigger names.

    * `AWAITING_STRUCTURE_BREAK` — a `CANDIDATE`'s open condition: the level
      that a confirmed close beyond would satisfy §6's confirmation rule.
    * `CONFIRMED_STRUCTURE_BREAK` — a `CONFIRMED` result's already-occurred
      break, named by reference rather than restated.

    Both are `fmis.structure_break`'s own concept — a `CLOSE_BREACH` at or after
    a level's confirmation bar — never a candle inspected here.
    """

    AWAITING_STRUCTURE_BREAK = "awaiting_structure_break"
    CONFIRMED_STRUCTURE_BREAK = "confirmed_structure_break"


@dataclass(frozen=True, slots=True)
class Trigger:
    """What is being watched for, or what already happened.

    ``level`` is ``None`` exactly when no candidate execution-timeframe level
    exists in the current window — reported honestly rather than omitted.
    A `CONFIRMED_STRUCTURE_BREAK` must carry both ``level`` and ``bar_index``:
    an already-occurred break with no level or bar to point at would be a claim
    this package cannot support.
    """

    kind: TriggerKind
    statement: str
    level: PriceLevel | None = None
    bar_index: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TriggerKind):
            raise TypeError(f"kind must be a TriggerKind, got {type(self.kind).__name__}")
        if not isinstance(self.statement, str) or not self.statement.strip():
            raise SwingSetupError("statement must be a non-empty str")
        if self.level is not None and not isinstance(self.level, PriceLevel):
            raise TypeError(f"level must be a PriceLevel or None, got {type(self.level).__name__}")
        if self.bar_index is not None:
            if isinstance(self.bar_index, bool) or not isinstance(self.bar_index, int):
                raise TypeError("bar_index must be an int or None")
            if self.bar_index < 0:
                raise SwingSetupError(f"bar_index cannot be negative, got {self.bar_index}")
        if self.kind is TriggerKind.CONFIRMED_STRUCTURE_BREAK and (
            self.level is None or self.bar_index is None
        ):
            raise SwingSetupError(
                "a confirmed trigger must carry the level and the bar that "
                "confirmed it; an occurred break with nothing to point at is "
                "not a claim this package can support"
            )


@dataclass(frozen=True, slots=True)
class RiskReward:
    """Risk and reward, computed once by the builder and never by AI.

    All six fields are computed and validated together so a `RiskReward` that
    disagrees with its own inputs cannot be constructed. ``ratio`` is
    ``reward / risk``, carried rather than left for a renderer to divide —
    division belongs beside the values it divides, following `RegimePolicy`'s
    own convention for its edges.
    """

    entry: float
    stop: float
    target: float
    risk: float
    reward: float
    ratio: float

    def __post_init__(self) -> None:
        for name in ("entry", "stop", "target", "risk", "reward", "ratio"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number, got {type(value).__name__}")
            if value != value or value in (float("inf"), float("-inf")):
                raise SwingSetupError(f"{name} must be finite, got {value}")
        if self.risk <= 0.0:
            raise SwingSetupError(f"risk must be positive, got {self.risk}")
        if self.reward <= 0.0:
            raise SwingSetupError(f"reward must be positive, got {self.reward}")


class ProbabilityStatus(str, Enum):
    """Whether a probability is a real, calibrated number.

    One member today: `NOT_CALIBRATED`. This repository has no backtester and
    no calibrated statistical model, so no probability is ever produced —
    stating that explicitly is the product-integrity rule the task brief
    requires, and the enum is the seam a future calibrated model extends rather
    than a field this package quietly starts populating.
    """

    NOT_CALIBRATED = "not_calibrated"


@dataclass(frozen=True, slots=True)
class Probability:
    """A probability, or the explicit statement that none exists.

    ``value`` must be ``None`` while ``status`` is `NOT_CALIBRATED` — enforced
    here, not left to callers, so a future bug cannot smuggle a number past the
    status that says none exists.
    """

    status: ProbabilityStatus
    value: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ProbabilityStatus):
            raise TypeError(
                f"status must be a ProbabilityStatus, got {type(self.status).__name__}"
            )
        if self.status is ProbabilityStatus.NOT_CALIBRATED and self.value is not None:
            raise SwingSetupError(
                "value must be None while status is NOT_CALIBRATED; a number "
                "beside that status would contradict it"
            )


#: The only probability v1 ever produces. Module-level and frozen so every
#: uncalibrated result cites the identical object.
NOT_CALIBRATED = Probability(ProbabilityStatus.NOT_CALIBRATED)

#: Which side a stop protects, and which side a target extends toward, per
#: direction. One authoritative mapping rather than a branch repeated at every
#: call site — a policy bug that inverted one branch would be caught by the
#: model's own validation rather than only by a test that happened to cover it.
_STOP_SIDE: Mapping[Direction, LevelSide] = MappingProxyType(
    {Direction.LONG: LevelSide.LOWER, Direction.SHORT: LevelSide.UPPER}
)
_TARGET_SIDE: Mapping[Direction, LevelSide] = MappingProxyType(
    {Direction.LONG: LevelSide.UPPER, Direction.SHORT: LevelSide.LOWER}
)
#: The side a confirming (or awaited) structure break must fall on.
CONFIRMATION_SIDE: Mapping[Direction, LevelSide] = MappingProxyType(
    {Direction.LONG: LevelSide.UPPER, Direction.SHORT: LevelSide.LOWER}
)


@dataclass(frozen=True, slots=True)
class SetupAssessment:
    """One deterministic swing-trade assessment for one symbol at one instant.

    ``reference_price`` is the execution-timeframe close that ``stop`` and
    ``targets`` are measured against — a recorded fact, never an executable
    order price (see the design record §7 for why an exact entry is not
    fabricated).

    ``limitations`` is inherited from every layer below plus this package's
    own, exactly as `Workspace.limitations` and `DailyRun.limitations` already
    do — a limitation kept off the result would be a claim of completeness this
    package cannot support.

    Frozen and slotted, with ``metadata`` copied into a read-only mapping.
    """

    symbol: str
    as_of: datetime
    objective: str
    state: SetupState
    direction: Direction | None
    thesis: tuple[str, ...]
    directional_factors: tuple[DirectionalFactor, ...]
    confirmation: tuple[str, ...]
    invalidation: tuple[str, ...]
    trigger: Trigger | None
    reference_price: float | None
    stop: PriceLevel | None
    targets: tuple[PriceLevel, ...]
    risk_reward: RiskReward | None
    probability: Probability
    regime_context: tuple[str, ...]
    sufficiency: ContextState
    limitations: tuple[str, ...]
    policy_id: str
    source: str
    schema_version: int = SETUP_SCHEMA_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("symbol", "objective", "policy_id", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingSetupError(f"{name} must be a non-empty str")
        if not isinstance(self.as_of, datetime):
            raise TypeError(f"as_of must be a datetime, got {type(self.as_of).__name__}")
        if not isinstance(self.state, SetupState):
            raise TypeError(f"state must be a SetupState, got {type(self.state).__name__}")
        if self.direction is not None and not isinstance(self.direction, Direction):
            raise TypeError("direction must be a Direction or None")
        if (self.direction is None) != (self.state is SetupState.WAIT):
            raise SwingSetupError(
                "direction is None if and only if state is WAIT; a candidate or "
                "confirmed result without a direction, or a WAIT result with "
                "one, is not representable"
            )
        for name in ("thesis", "confirmation", "invalidation", "regime_context", "limitations"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple of str")
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    raise SwingSetupError(f"every {name} line must be a non-empty str")
        if not isinstance(self.directional_factors, tuple):
            raise TypeError("directional_factors must be a tuple of DirectionalFactor")
        for position, item in enumerate(self.directional_factors):
            if not isinstance(item, DirectionalFactor):
                raise TypeError(
                    f"directional_factors[{position}] must be a DirectionalFactor, "
                    f"got {type(item).__name__}"
                )
        if self.trigger is not None and not isinstance(self.trigger, Trigger):
            raise TypeError("trigger must be a Trigger or None")
        if self.reference_price is not None:
            if isinstance(self.reference_price, bool) or not isinstance(
                self.reference_price, (int, float)
            ):
                raise TypeError("reference_price must be a number or None")
            if self.reference_price != self.reference_price or self.reference_price in (
                float("inf"), float("-inf"),
            ):
                raise SwingSetupError("reference_price must be finite")
            if self.reference_price <= 0.0:
                raise SwingSetupError(
                    f"reference_price must be positive, got {self.reference_price}"
                )
        if self.stop is not None and not isinstance(self.stop, PriceLevel):
            raise TypeError(f"stop must be a PriceLevel or None, got {type(self.stop).__name__}")
        if not isinstance(self.targets, tuple):
            raise TypeError("targets must be a tuple of PriceLevel")
        for position, target in enumerate(self.targets):
            if not isinstance(target, PriceLevel):
                raise TypeError(
                    f"targets[{position}] must be a PriceLevel, got {type(target).__name__}"
                )
        if self.risk_reward is not None and not isinstance(self.risk_reward, RiskReward):
            raise TypeError("risk_reward must be a RiskReward or None")
        if not isinstance(self.probability, Probability):
            raise TypeError(
                f"probability must be a Probability, got {type(self.probability).__name__}"
            )
        if not isinstance(self.sufficiency, ContextState):
            raise TypeError(
                f"sufficiency must be a ContextState, got {type(self.sufficiency).__name__}"
            )
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool):
            raise TypeError("schema_version must be an int")

        # A directionless result carries no direction-scoped fields at all —
        # checked before the direction-specific geometry below, so a WAIT
        # result cannot smuggle a stop or a target past the state it claims.
        if self.direction is None:
            for name, value in (
                ("trigger", self.trigger),
                ("stop", self.stop),
                ("risk_reward", self.risk_reward),
            ):
                if value is not None:
                    raise SwingSetupError(f"a WAIT result must not carry {name}")
            if self.targets:
                raise SwingSetupError("a WAIT result must not carry targets")
        else:
            required_stop_side = _STOP_SIDE[self.direction]
            if self.stop is not None and self.stop.side is not required_stop_side:
                raise SwingSetupError(
                    f"a {self.direction.value} stop must be a "
                    f"{required_stop_side.value} level, got {self.stop.side.value}"
                )
            required_target_side = _TARGET_SIDE[self.direction]
            for position, target in enumerate(self.targets):
                if target.side is not required_target_side:
                    raise SwingSetupError(
                        f"targets[{position}] for a {self.direction.value} must be "
                        f"a {required_target_side.value} level, got {target.side.value}"
                    )
            if self.trigger is not None and self.trigger.level is not None:
                required_trigger_side = CONFIRMATION_SIDE[self.direction]
                if self.trigger.level.side is not required_trigger_side:
                    raise SwingSetupError(
                        f"a {self.direction.value} trigger level must be a "
                        f"{required_trigger_side.value} level, got "
                        f"{self.trigger.level.side.value}"
                    )

        risk_reward_justified = self.stop is not None and bool(self.targets)
        if self.risk_reward is not None and not risk_reward_justified:
            raise SwingSetupError(
                "risk_reward requires both a stop and at least one target"
            )
        if risk_reward_justified and self.risk_reward is None:
            # A stop and a target together make R/R always computable — the
            # geometry validated above guarantees positive risk and reward —
            # so withholding it here would hide a number this model can prove.
            raise SwingSetupError(
                "a stop and a target are both present; risk_reward must be "
                "computed rather than withheld"
            )

        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ExecutionBreakEvent:
    """One break-of-structure event on the execution view, copied by reference.

    Carries only what confirmation search needs: the level that broke and the
    bar it broke on. `fmis.structure_break.StructureBreak` itself is never
    imported here — ADR-0028 §1 keeps this package's surface to the narrow set
    of types it actually interprets.

    A single ``latest`` break is not enough: `fmis.structure_break` can emit an
    upper and a lower break on the **same** bar (its own docs say so), ordered
    upper-before-lower, so "the most recent break" always resolves toward the
    lower side on a tie. Carrying the full ordered history, and searching it by
    the side the candidate actually needs, is what removes that asymmetry —
    see the independent review that found it.
    """

    level: PriceLevel
    index: int

    def __post_init__(self) -> None:
        if not isinstance(self.level, PriceLevel):
            raise TypeError(f"level must be a PriceLevel, got {type(self.level).__name__}")
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise TypeError(f"index must be an int, got {type(self.index).__name__}")
        if self.index < 0:
            raise SwingSetupError(f"index cannot be negative, got {self.index}")


@dataclass(frozen=True, slots=True)
class SetupInputs:
    """Exactly the facts the policy reads. The layer boundary, and nothing more.

    Built by `fmis.swing_setup.compose` from what the engines already produced.
    The policy never sees a fact sheet, a regime, an evidence report or a
    decision context object directly — narrow indices, prices and enums only,
    matching `RegimeInput` and `ContextInput`'s own discipline. That boundary is
    what lets the policy be tested from hand-built primitives, and what stops it
    reaching past the facts it was handed.

    ``execution_breaks`` is the **full, ordered** break history on the
    execution view — not only the latest one — so the policy can search for
    the most recent break matching a specific side rather than trusting
    whichever break happened to sort last (see `ExecutionBreakEvent`).
    ``execution_closed_count`` is the number of closed candles the execution
    view actually analysed, which is what lets the policy measure how many
    bars old a candidate confirming break is.
    """

    symbol: str
    as_of: datetime
    source: str
    context_interval: str
    setup_interval: str
    execution_interval: str
    context_structural_trend: StructuralTrendType
    setup_structural_trend: StructuralTrendType
    execution_structural_trend: StructuralTrendType
    context_regime_structure: StructureState
    context_regime_volatility: VolatilityState
    context_regime_participation: ParticipationState
    evidence_state: OverallState | None
    evidence_dominant_alignment: Alignment | None
    decision_context_state: ContextState
    decision_context_statements: tuple[str, ...]
    execution_close: float | None
    execution_closed_count: int
    execution_levels: tuple[PriceLevel, ...]
    execution_breaks: tuple[ExecutionBreakEvent, ...]
    setup_levels: tuple[PriceLevel, ...]
    inherited_limitations: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("symbol", "source", "context_interval", "setup_interval", "execution_interval"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingSetupError(f"{name} must be a non-empty str")
        if not isinstance(self.as_of, datetime):
            raise TypeError(f"as_of must be a datetime, got {type(self.as_of).__name__}")
        for name in (
            "context_structural_trend", "setup_structural_trend", "execution_structural_trend",
        ):
            value = getattr(self, name)
            if not isinstance(value, StructuralTrendType):
                raise TypeError(f"{name} must be a StructuralTrendType, got {type(value).__name__}")
        if not isinstance(self.context_regime_structure, StructureState):
            raise TypeError("context_regime_structure must be a StructureState")
        if not isinstance(self.context_regime_volatility, VolatilityState):
            raise TypeError("context_regime_volatility must be a VolatilityState")
        if not isinstance(self.context_regime_participation, ParticipationState):
            raise TypeError("context_regime_participation must be a ParticipationState")
        if self.evidence_state is not None and not isinstance(self.evidence_state, OverallState):
            raise TypeError("evidence_state must be an OverallState or None")
        if self.evidence_dominant_alignment is not None and not isinstance(
            self.evidence_dominant_alignment, Alignment
        ):
            raise TypeError("evidence_dominant_alignment must be an Alignment or None")
        if not isinstance(self.decision_context_state, ContextState):
            raise TypeError("decision_context_state must be a ContextState")
        if not isinstance(self.decision_context_statements, tuple):
            raise TypeError("decision_context_statements must be a tuple of str")
        if self.execution_close is not None:
            if isinstance(self.execution_close, bool) or not isinstance(
                self.execution_close, (int, float)
            ):
                raise TypeError("execution_close must be a number or None")
            if self.execution_close <= 0.0 or self.execution_close != self.execution_close:
                raise SwingSetupError(
                    f"execution_close must be finite and positive, got {self.execution_close}"
                )
        if isinstance(self.execution_closed_count, bool) or not isinstance(
            self.execution_closed_count, int
        ):
            raise TypeError("execution_closed_count must be an int")
        if self.execution_closed_count < 0:
            raise SwingSetupError("execution_closed_count cannot be negative")
        for name in ("execution_levels", "setup_levels"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple of PriceLevel")
            for position, level in enumerate(value):
                if not isinstance(level, PriceLevel):
                    raise TypeError(
                        f"{name}[{position}] must be a PriceLevel, got {type(level).__name__}"
                    )
        if not isinstance(self.execution_breaks, tuple):
            raise TypeError("execution_breaks must be a tuple of ExecutionBreakEvent")
        for position, event in enumerate(self.execution_breaks):
            if not isinstance(event, ExecutionBreakEvent):
                raise TypeError(
                    f"execution_breaks[{position}] must be an ExecutionBreakEvent, "
                    f"got {type(event).__name__}"
                )
            if event.index >= self.execution_closed_count:
                raise SwingSetupError(
                    f"execution_breaks[{position}].index ({event.index}) cannot be "
                    f"at or beyond execution_closed_count ({self.execution_closed_count})"
                )
        if not isinstance(self.inherited_limitations, tuple):
            raise TypeError("inherited_limitations must be a tuple of str")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
