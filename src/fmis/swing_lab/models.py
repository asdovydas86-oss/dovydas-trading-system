"""The Swing Strategy Laboratory's own vocabulary — variants, trades, verdicts.

**Research types, and nothing else.** Nothing in this module is imported by a
production surface, nothing here can be written to the owner's store, and no
value here reaches a live decision. A guard asserts each absence.

**A variant is a specification, not a result.** `LabVariant` holds what a policy
*is* — which treatment the context role receives, which staleness bound applies,
which interval plays which role — and is written down before any history is
replayed. `docs/design/` records the same specification in prose. That ordering
is the entire anti-overfitting discipline: a variant whose definition is chosen
after its result has been seen is not a hypothesis, and there is no way to tell
the two apart afterwards from the numbers alone.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Final

from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.swing_setup.models import Direction
from fmis.swing_setup.policy import (
    CONFIRMATION_LOOKBACK_BARS,
    PRODUCTION_CONTEXT_ROLE_TREATMENT,
    SETUP_POLICY_ID,
    ContextRoleTreatment,
    research_policy_id,
)

__all__ = [
    "LAB_SCHEMA_VERSION",
    "SwingLabError",
    "LabVariant",
    "LabExitReason",
    "TradeVerdict",
    "LabTrade",
    "GateVerdict",
    "GateObservation",
    "LabVerdict",
]

#: Bumped whenever a persisted lab artifact changes shape. A forward milestone
#: reading an artifact written today must be able to tell that it can.
LAB_SCHEMA_VERSION: Final[int] = 1


class SwingLabError(Exception):
    """A laboratory input or invariant was violated. Never a market condition."""


@dataclass(frozen=True, slots=True)
class LabVariant:
    """One pre-specified policy under which history will be replayed.

    ``context_role`` and ``max_confirmation_age`` are both ``None`` for the
    production baseline, and that is load-bearing rather than a convenience:
    ``None`` means *the override is not supplied at all*, so the baseline runs
    the production call path with the production constants, and its assessments
    carry `SETUP_POLICY_ID` rather than a research id. Any other combination is
    a counterfactual and says so in its own ``policy_id``.

    ``timeframes`` is part of the specification because the owner's hypothesis
    is partly about *which interval plays which role*, not only about what the
    context role is allowed to do. Two variants differing only in this mapping
    are genuinely different policies and must not share a variant id.
    """

    variant_id: str
    title: str
    hypothesis: str
    context_role: ContextRoleTreatment | None
    max_confirmation_age: int | None
    timeframes: Mapping[TimeframeRole, str]

    def __post_init__(self) -> None:
        if not isinstance(self.variant_id, str) or not self.variant_id.strip():
            raise SwingLabError("variant_id must be a non-empty str")
        for name in ("title", "hypothesis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingLabError(f"{name} must be a non-empty str")
        if self.context_role is not None and not isinstance(
            self.context_role, ContextRoleTreatment
        ):
            raise TypeError("context_role must be a ContextRoleTreatment or None")
        if self.max_confirmation_age is not None:
            if isinstance(self.max_confirmation_age, bool) or not isinstance(
                self.max_confirmation_age, int
            ):
                raise TypeError("max_confirmation_age must be an int or None")
            if self.max_confirmation_age < 0:
                raise SwingLabError("max_confirmation_age cannot be negative")
        missing = [role.value for role in TimeframeRole if role not in self.timeframes]
        if missing:
            raise SwingLabError(f"timeframes must map every role; missing {missing}")
        if len({self.timeframes[role] for role in TimeframeRole}) != 3:
            raise SwingLabError(
                "context, setup and execution must each be a distinct interval"
            )
        object.__setattr__(
            self,
            "timeframes",
            MappingProxyType({role: self.timeframes[role] for role in TimeframeRole}),
        )

    @property
    def is_production_baseline(self) -> bool:
        """``True`` only when neither override is supplied at all."""
        return self.context_role is None and self.max_confirmation_age is None

    @property
    def effective_context_role(self) -> ContextRoleTreatment:
        """The treatment actually applied, production's own included."""
        return (
            PRODUCTION_CONTEXT_ROLE_TREATMENT
            if self.context_role is None
            else self.context_role
        )

    @property
    def effective_max_age(self) -> int:
        """The staleness bound actually applied, production's own included."""
        return (
            CONFIRMATION_LOOKBACK_BARS
            if self.max_confirmation_age is None
            else self.max_confirmation_age
        )

    @property
    def policy_id(self) -> str:
        """The ``policy_id`` every assessment under this variant will carry.

        Note that this is **not** unique per variant, and deliberately so: a
        variant that changes only the timeframe mapping runs the unmodified
        production policy, and stamping a research id on it would claim a
        policy change that did not happen. ``variant_id`` distinguishes runs;
        ``policy_id`` distinguishes *policies*.
        """
        return (
            SETUP_POLICY_ID
            if self.is_production_baseline
            else research_policy_id(
                self.effective_max_age, self.effective_context_role
            )
        )

    @property
    def interval_signature(self) -> tuple[str, str, str]:
        """The role→interval mapping as a hashable key.

        Variants sharing this signature read the *same facts*, so they can share
        one replay pass. Variants that do not, cannot — which is why this is a
        property of the specification rather than a runtime discovery.
        """
        return (
            self.timeframes[TimeframeRole.CONTEXT],
            self.timeframes[TimeframeRole.SETUP],
            self.timeframes[TimeframeRole.EXECUTION],
        )


class LabExitReason(str, Enum):
    """Why a simulated trade ended. Every terminal state is named.

    `AMBIGUOUS_SAME_BAR` is a **refusal**, not an outcome, and follows the rule
    `fmis.paper.engine` and `fmis.swing_setup.backtest_outcomes` already reached
    independently: a bar that touched the stop and the target cannot be ordered
    from four prices, and guessing would flatter or damn the variant by coin
    flip. Such trades are counted and excluded from expectancy, and the count is
    always reported beside it.

    `TIME_STOP` is what happens when neither level was reached inside the
    evaluation window. It is an exit at that bar's close — a stated measurement
    policy, not a discovery — and the alternative (dropping the trade) would
    silently delete every slow loser and most slow winners.

    `ENTRY_GAPPED_THROUGH_STOP` is the case where the bar that filled the entry
    had already opened beyond the stop. The trade is recorded as a loss at the
    fill, never skipped: skipping it would remove exactly the worst fills.
    """

    TARGET = "target"
    STOP = "stop"
    TIME_STOP = "time_stop"
    AMBIGUOUS_SAME_BAR = "ambiguous_same_bar"
    ENTRY_GAPPED_THROUGH_STOP = "entry_gapped_through_stop"
    NO_ENTRY_BAR = "no_entry_bar"

    @property
    def is_measurable(self) -> bool:
        """Whether this exit yields an R multiple expectancy may consume."""
        return self in _MEASURABLE_EXITS


_MEASURABLE_EXITS: Final[frozenset[LabExitReason]] = frozenset(
    {
        LabExitReason.TARGET,
        LabExitReason.STOP,
        LabExitReason.TIME_STOP,
        LabExitReason.ENTRY_GAPPED_THROUGH_STOP,
    }
)


class TradeVerdict(str, Enum):
    """Win, loss, or neither — decided by net R alone, never by exit reason.

    A target that netted less than zero after costs is a **loss**, and a time
    stop above the entry is a **win**. Classifying by exit reason instead would
    let a cost model change the expectancy without changing the win rate, and
    the two figures would quietly stop describing the same trades.
    """

    WIN = "win"
    LOSS = "loss"
    SCRATCH = "scratch"
    UNMEASURED = "unmeasured"


@dataclass(frozen=True, slots=True)
class LabTrade:
    """One simulated trade, from a confirmed setup to a terminal exit.

    Every price is exact (`Decimal`), every R multiple is a quotient computed at
    construction from the initial risk, and the cost basis that produced the net
    figure travels on the record — so two trades measured under different cost
    scenarios can never be added together by accident.
    """

    variant_id: str
    symbol: str
    setup_id: str
    direction: Direction
    signal_at: datetime
    entry_at: datetime | None
    entry_price: Decimal | None
    initial_stop: Decimal
    target: Decimal
    planned_reference_price: Decimal
    exit_at: datetime | None
    exit_price: Decimal | None
    exit_reason: LabExitReason
    bars_held: int
    gross_r: Decimal | None
    net_r: Decimal | None
    mfe_r: Decimal | None
    mae_r: Decimal | None
    cost_policy_id: str
    planned_risk_reward: float
    segment: str | None
    context_regime_structure: str
    context_structural_trend: str
    setup_structural_trend: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def verdict(self) -> TradeVerdict:
        if self.net_r is None:
            return TradeVerdict.UNMEASURED
        if self.net_r > 0:
            return TradeVerdict.WIN
        if self.net_r < 0:
            return TradeVerdict.LOSS
        return TradeVerdict.SCRATCH

    @property
    def is_measurable(self) -> bool:
        return self.net_r is not None


class GateVerdict(str, Enum):
    """What the production context-role gate did at one instant.

    Measured from `SetupInputs` rather than parsed out of a rendered thesis
    string. A text parse would break silently the first time a sentence was
    reworded, and would read as "the gate stopped blocking" — the most
    flattering possible failure.
    """

    #: The gate was not reached: something upstream had already refused.
    NOT_REACHED = "not_reached"
    #: The context regime was TRENDING; the gate allowed the decision through.
    ALLOWED = "allowed"
    #: The gate blocked, and without it no direction would have formed anyway.
    BLOCKED_WITHOUT_EFFECT = "blocked_without_effect"
    #: The gate blocked a decision that would otherwise have become a candidate.
    BLOCKED_CANDIDATE = "blocked_candidate"
    #: The gate blocked a decision that would otherwise have **confirmed**.
    BLOCKED_CONFIRMED = "blocked_confirmed"

    @property
    def is_blocking(self) -> bool:
        return self in _BLOCKING_VERDICTS

    @property
    def is_material(self) -> bool:
        """Whether removing the gate would have changed this instant's state."""
        return self in {
            GateVerdict.BLOCKED_CANDIDATE,
            GateVerdict.BLOCKED_CONFIRMED,
        }


_BLOCKING_VERDICTS: Final[frozenset[GateVerdict]] = frozenset(
    {
        GateVerdict.BLOCKED_WITHOUT_EFFECT,
        GateVerdict.BLOCKED_CANDIDATE,
        GateVerdict.BLOCKED_CONFIRMED,
    }
)


@dataclass(frozen=True, slots=True)
class GateObservation:
    """One instant, judged for what the context-role gate did to it."""

    symbol: str
    as_of: datetime
    verdict: GateVerdict
    context_regime_structure: str
    counterfactual_direction: Direction | None
    segment: str | None


class LabVerdict(str, Enum):
    """What a study concluded about one variant. **Derived, never asserted.**

    `classify` computes this from the measured result alone, so a reader can
    reconstruct it from the artifact rather than take a report's word for it.
    Three states, and the vocabulary is deliberately narrow:

    * `INCONCLUSIVE` — no expectancy could be stated at all, because the
      variant produced too few measurable trades to clear the sample floor (or
      none). **Not a negative result**: nothing was learned about it. A variant
      that was specified but never run also lands here.
    * `REJECTED` — an expectancy was stated and it is not positive. The variant
      lost money over the measured window.
    * `CANDIDATE_FOR_FORWARD_TEST` — an expectancy was stated and it is
      positive. This is the strongest verdict this repository can produce and
      it means exactly one thing: *worth testing forward*. It is **not**
      approval to trade, and there is no state above it.
    """

    INCONCLUSIVE = "inconclusive"
    REJECTED = "rejected"
    CANDIDATE_FOR_FORWARD_TEST = "candidate_for_forward_test"

    @property
    def is_approved_for_trading(self) -> bool:
        """Always ``False``. No verdict this repository produces approves trading.

        Exists so a caller asking the question gets a straight answer instead of
        inferring one from a label, and so a future state that *did* mean
        approval could not be added without editing this method deliberately.
        """
        return False

    @property
    def statement(self) -> str:
        """One sentence a surface can print without paraphrasing the verdict."""
        return _VERDICT_STATEMENTS[self]


_VERDICT_STATEMENTS: Final[dict[LabVerdict, str]] = {
    LabVerdict.INCONCLUSIVE: (
        "Inconclusive — too few measurable trades to state an expectancy. "
        "Nothing was established either way."
    ),
    LabVerdict.REJECTED: (
        "Rejected — an expectancy was measured and it is not positive over this "
        "window. Not a candidate for forward testing."
    ),
    LabVerdict.CANDIDATE_FOR_FORWARD_TEST: (
        "Candidate for forward testing only — a positive expectancy was measured "
        "over this window. This is NOT approval to trade."
    ),
}
