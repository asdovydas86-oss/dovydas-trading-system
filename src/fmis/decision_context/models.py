"""Value types for the Decision Context Engine.

The engine answers **one** question: *does the current analysis contain enough
trustworthy information to continue toward a trading setup?*

It answers nothing else. There is no direction, no entry, no exit, no target, no
stop, no position size and no risk anywhere in this package — those belong to
milestones that do not exist, and a test asserts none of those words appears in
any public name or any produced statement.

**Why this exists.** Measured on the repository before this milestone: a
40-candle page rendered its regime section as *available* while two of the three
regime dimensions underneath read `insufficient` and three features were still
warming up. A section's status says whether it produced output, not whether the
output can be trusted, and nothing aggregated the difference. `SPEC` §7 names
"excessive confidence from incomplete data" as a bias the system must guard
against; this package is that guard.

**Sufficiency is about availability, never about agreement.** Conflicts are
deliberately excluded from the judgement — a market whose timeframes disagree is
still analysable, and penalising disagreement would push the system toward pages
that look tidy by being one-sided. That is the failure `docs/analysis-notes.md`
records, expressed as a completeness rule instead of a checklist.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

__all__ = [
    "ContextState",
    "Severity",
    "Requirement",
    "REQUIREMENT_ORDER",
    "RequirementCheck",
    "ViewAdequacy",
    "ContextInput",
    "DecisionContext",
    "DecisionContextError",
    "ContextInputError",
]


class DecisionContextError(Exception):
    """Base class for every decision-context failure.

    Follows the package-error convention `IngestError`, `LevelCrossingError`,
    `MarketRegimeError` and `WorkspaceError` established elsewhere, so a caller
    can catch this layer's failures as a group.
    """


class ContextInputError(DecisionContextError, ValueError):
    """The supplied facts cannot describe one analysis at one instant.

    Also a `ValueError`, matching `StructureBreakInputError` and
    `RegimeInputError`, so a caller catching `ValueError` at a boundary keeps
    working.
    """


class ContextState(str, Enum):
    """Whether the analysis can be continued, and how far.

    * `SUFFICIENT` — every requirement is met. The analysis rests on the data
      each layer said it needed.
    * `LIMITED` — nothing blocking is missing, but something is degraded. The
      analysis continues *with the named limitation attached to it*, which is a
      different thing from continuing silently.
    * `INSUFFICIENT` — a blocking requirement is unmet. Continuing toward a setup
      from here would be reasoning from data the system knows is not there.

    Deliberately absent: any member naming a direction, a recommendation, a
    confidence, a score or a rank. `SUFFICIENT` says the *information* is
    adequate; it says nothing whatever about the market.
    """

    SUFFICIENT = "sufficient"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"


class Severity(str, Enum):
    """What an unmet requirement costs.

    Fixed per requirement in code rather than configured, because "which gaps
    are fatal" is a semantic property of the gap, not a knob. A configurable
    severity set would let a caller quietly demote the one check that was about
    to stop them.
    """

    BLOCKING = "blocking"
    LIMITING = "limiting"


class Requirement(str, Enum):
    """The named conditions an analysis must satisfy to be continued.

    Five, and **every one of them delegates its rule to a layer that already
    declared it**. That is the design's central discipline: this engine invents
    no threshold of its own, so there is no number here for a future reader to
    wonder about, and no second definition that could drift from the first.
    """

    #: Enough closed candles for detection to be possible at all —
    #: `fmis.market_structure.required_candles` decides, from the caller's own
    #: detection settings.
    PRIMARY_DATA_DEPTH = "primary_data_depth"
    #: No feature on the primary view is still warming up — the feature engine's
    #: own warm-up metadata decides.
    WARM_UP_COMPLETE = "warm_up_complete"
    #: No regime dimension reported `INSUFFICIENT` — `fmis.market_regime`
    #: decides, using the distinction ADR-0025 drew between evidence that was
    #: absent and evidence that disagreed.
    REGIME_DETERMINATE = "regime_determinate"
    #: The structural chain produced at least one price level —
    #: `fmis.level_crossing` decides.
    STRUCTURE_PRESENT = "structure_present"
    #: The evidence layer did not report `INSUFFICIENT_DATA` —
    #: `fmis.decision_support` decides, by ADR-0008 §7's own rule.
    EVIDENCE_PRESENT = "evidence_present"


#: Reporting order. **Never** enum definition order — the rule every ordering
#: contract in this repository follows. It runs from the data outward: is there
#: enough data, are the indicators ready, did the derived layers manage to say
#: anything.
REQUIREMENT_ORDER: tuple[Requirement, ...] = (
    Requirement.PRIMARY_DATA_DEPTH,
    Requirement.WARM_UP_COMPLETE,
    Requirement.REGIME_DETERMINATE,
    Requirement.STRUCTURE_PRESENT,
    Requirement.EVIDENCE_PRESENT,
)

_ORDER_RANK: Mapping[Requirement, int] = MappingProxyType(
    {requirement: rank for rank, requirement in enumerate(REQUIREMENT_ORDER)}
)

#: Which gaps stop the analysis and which merely qualify it.
#:
#: Depth, structure and evidence are **blocking**: without candles there is
#: nothing to read, without a level there is nothing to read *against*, and
#: without directional evidence the evidence layer has already said it cannot
#: speak. Warm-up and regime determinacy are **limiting**: the analysis is
#: thinner than it should be, and a reader who is told exactly how may still
#: proceed.
SEVERITY: Mapping[Requirement, Severity] = MappingProxyType(
    {
        Requirement.PRIMARY_DATA_DEPTH: Severity.BLOCKING,
        Requirement.WARM_UP_COMPLETE: Severity.LIMITING,
        Requirement.REGIME_DETERMINATE: Severity.LIMITING,
        Requirement.STRUCTURE_PRESENT: Severity.BLOCKING,
        Requirement.EVIDENCE_PRESENT: Severity.BLOCKING,
    }
)


@dataclass(frozen=True, slots=True)
class RequirementCheck:
    """One requirement, whether it was met, and which layer decided.

    ``source`` names the layer whose rule was applied. It is the field that makes
    this engine auditable: a reader who disagrees with a verdict can go to the
    layer that produced it rather than to a threshold invented here.

    ``statement`` restates the fact plainly. It contains no recommendation and no
    comparative judgement.
    """

    requirement: Requirement
    met: bool
    severity: Severity
    statement: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, Requirement):
            raise TypeError(
                f"requirement must be a Requirement, got "
                f"{type(self.requirement).__name__}"
            )
        if not isinstance(self.met, bool):
            raise TypeError(f"met must be a bool, got {type(self.met).__name__}")
        if not isinstance(self.severity, Severity):
            raise TypeError(
                f"severity must be a Severity, got {type(self.severity).__name__}"
            )
        for name in ("statement", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ContextInputError(f"{name} must be a non-empty str")


@dataclass(frozen=True, slots=True)
class ViewAdequacy:
    """What one timeframe view contributed, as counts rather than as prose.

    Deliberately **not** a fact sheet. The engine reads five integers and two
    booleans per view; handing it a sheet would let it reach a candle, and
    handing it the rendered workspace would make it parse formatted strings back
    into numbers.
    """

    role: str
    interval: str
    closed_candles: int
    required_candles: int
    warming_up: int
    level_count: int
    dimensions_insufficient: int

    def __post_init__(self) -> None:
        for name in ("role", "interval"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ContextInputError(f"{name} must be a non-empty str")
        for name in (
            "closed_candles",
            "required_candles",
            "warming_up",
            "level_count",
            "dimensions_insufficient",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an int, got {type(value).__name__}")
            if value < 0:
                raise ContextInputError(f"{name} cannot be negative, got {value}")
        if self.required_candles < 1:
            raise ContextInputError(
                "required_candles must be at least 1; a view that requires no "
                "candles cannot have its depth judged"
            )

    @property
    def has_enough_candles(self) -> bool:
        """Depth against the caller's **own** declared requirement, not a literal."""
        return self.closed_candles >= self.required_candles

    @property
    def label(self) -> str:
        return f"{self.role} · {self.interval}"


@dataclass(frozen=True, slots=True)
class ContextInput:
    """Exactly the facts the engine reads. The layer boundary, and nothing more.

    Built by the application layer from what the engines already produced. The
    engine never sees a candle, a fact sheet, an evidence report or a rendered
    page — which is what lets it be tested from seven integers and keeps it from
    parsing presentation back into data.

    ``evidence_is_insufficient`` is supplied as a **boolean the evidence layer
    already decided**, not as a count this engine would threshold. ADR-0008 §7
    owns the rule; restating it here would create a second definition.
    """

    symbol: str
    as_of: datetime
    views: tuple[ViewAdequacy, ...]
    primary_role: str
    evidence_is_insufficient: bool
    conflict_count: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("symbol", "primary_role"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ContextInputError(f"{name} must be a non-empty str")
        if not isinstance(self.as_of, datetime):
            raise TypeError(
                f"as_of must be a datetime, got {type(self.as_of).__name__}"
            )
        if not isinstance(self.views, tuple):
            raise TypeError("views must be a tuple of ViewAdequacy")
        for position, view in enumerate(self.views):
            if not isinstance(view, ViewAdequacy):
                raise TypeError(
                    f"views[{position}] must be a ViewAdequacy, got "
                    f"{type(view).__name__}"
                )
        if not self.views:
            raise ContextInputError("at least one view is required")
        roles = [view.role for view in self.views]
        if len(set(roles)) != len(roles):
            raise ContextInputError(
                "views must not repeat a role; two answers for one timeframe "
                "would let a reader pick the one they preferred"
            )
        if self.primary_role not in roles:
            raise ContextInputError(
                f"primary_role {self.primary_role!r} is not among the views "
                f"({', '.join(roles)})"
            )
        if not isinstance(self.evidence_is_insufficient, bool):
            raise TypeError("evidence_is_insufficient must be a bool")
        if isinstance(self.conflict_count, bool) or not isinstance(
            self.conflict_count, int
        ):
            raise TypeError("conflict_count must be an int")
        if self.conflict_count < 0:
            raise ContextInputError("conflict_count cannot be negative")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def primary(self) -> ViewAdequacy:
        """The view the judgement is made about."""
        return next(view for view in self.views if view.role == self.primary_role)


@dataclass(frozen=True, slots=True)
class DecisionContext:
    """The one answer, every check behind it, and the policy that produced it.

    Carries **no score and no confidence number**. A reader who wants to disagree
    reads the checks; a number would compress exactly the information they need
    and imply a calibration this engine has never performed.

    Frozen and slotted, with metadata copied into a read-only mapping.
    """

    symbol: str
    as_of: datetime
    state: ContextState
    checks: tuple[RequirementCheck, ...]
    policy: Any
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ContextInputError("symbol must be a non-empty str")
        if not isinstance(self.as_of, datetime):
            raise TypeError(
                f"as_of must be a datetime, got {type(self.as_of).__name__}"
            )
        if not isinstance(self.state, ContextState):
            raise TypeError(
                f"state must be a ContextState, got {type(self.state).__name__}"
            )
        if not isinstance(self.checks, tuple):
            raise TypeError("checks must be a tuple of RequirementCheck")
        for position, check in enumerate(self.checks):
            if not isinstance(check, RequirementCheck):
                raise TypeError(
                    f"checks[{position}] must be a RequirementCheck, got "
                    f"{type(check).__name__}"
                )
        names = [check.requirement for check in self.checks]
        if len(set(names)) != len(names):
            raise ContextInputError("a requirement must not be checked twice")
        if set(names) != set(REQUIREMENT_ORDER):
            missing = [r.value for r in REQUIREMENT_ORDER if r not in set(names)]
            raise ContextInputError(
                f"every requirement must be reported, including the met ones; "
                f"missing: {missing}"
            )
        if names != sorted(names, key=_ORDER_RANK.__getitem__):
            raise ContextInputError(
                "checks must follow REQUIREMENT_ORDER; a stable order is what "
                "makes two contexts diffable"
            )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def unmet(self) -> tuple[RequirementCheck, ...]:
        """Every requirement that was not met — a projection, never stored."""
        return tuple(check for check in self.checks if not check.met)

    @property
    def blocking(self) -> tuple[RequirementCheck, ...]:
        """Unmet requirements that stop the analysis."""
        return tuple(
            check for check in self.unmet if check.severity is Severity.BLOCKING
        )

    @property
    def limiting(self) -> tuple[RequirementCheck, ...]:
        """Unmet requirements that qualify the analysis without stopping it."""
        return tuple(
            check for check in self.unmet if check.severity is Severity.LIMITING
        )

    @property
    def may_continue(self) -> bool:
        """Whether the analysis may be continued at all.

        Derived from ``state``, **not** re-derived from the checks. An earlier
        version tested "no blocking check", which disagreed with itself under a
        strict policy: strictness promotes a limiting gap to blocking at the
        *state*, while the check keeps its own fixed severity, so the result
        reported `INSUFFICIENT` and `may_continue` at the same time. One source
        of truth removes the contradiction rather than validating against it —
        ADR-0016 §4 applied to a property.

        Named for what it *is* — a statement about information — rather than for
        what a caller might do with it. `should_trade` would be a different and
        forbidden claim.
        """
        return self.state is not ContextState.INSUFFICIENT
