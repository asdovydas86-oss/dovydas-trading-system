"""Value types for deterministic market-regime classification.

A **regime** is a statement about the *environment*, never about direction. It
says whether structure is trending or ranging, whether volatility is expanding or
contracting, and whether participation is elevated or subdued. It does not say
whether price is going up, whether anything should be bought, or whether a trade
exists. `ARCH` §9 defines the role precisely: an explicit, testable
classification that higher layers can condition on.

**Direction is deliberately absent, and its absence is the design.**
`docs/analysis-notes.md` records what happened when a regime gate carried
direction: the v2 checklists *looked* symmetric but their "bullish" branch was
satisfied by conditions that hold most of the time while the "bearish" branch
required a deep bear market, so a LONG began with two free confirmations. The v3
prompt classifies regime as BULLISH / BEARISH / RANGE; this engine deliberately
**does not**, and that divergence is recorded in ADR-0025. A consumer that wants
direction reads `StructuralTrendType`, which is a fact this layer does not
restate.

**Three dimensions, never collapsed.** A single opaque label would discard the
information a consumer needs to disagree with it, which is the objection `ARCH`
§9 raises against a bare word. Each dimension carries its own state, its own
evidence, and its own reason when it declines to classify.

**Uncertainty is a state, not a low score.** `INSUFFICIENT` means the evidence
was not available; `INDETERMINATE` means it was available and disagreed. Those
are different facts about the market and are never merged. There is no
confidence number anywhere in this package: a probability that has never been
calibrated is a decoration, and `SPEC` §4.1 rejects exactly that kind of
false precision.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from fmis.market_regime.policy import RegimePolicy
from fmis.structural_trend import StructuralTrendType

__all__ = [
    "RegimeDimensionName",
    "StructureState",
    "VolatilityState",
    "ParticipationState",
    "EvidenceStatus",
    "RegimeEvidence",
    "RegimeDimension",
    "MarketRegime",
    "RegimeInput",
    "MarketRegimeError",
    "RegimeInputError",
]


class MarketRegimeError(Exception):
    """Base class for every market-regime failure.

    Follows the established package-error convention — `IngestError`,
    `LevelCrossingError`, `StructureBreakError` — so a caller can catch this
    layer's failures as a group.
    """


class RegimeInputError(MarketRegimeError, ValueError):
    """The supplied facts cannot describe one series at one instant.

    Also a `ValueError`, matching `DuplicateLevelError` and
    `StructureBreakInputError`, so a caller catching `ValueError` at a boundary
    keeps working.
    """


class RegimeDimensionName(str, Enum):
    """The three environments this engine classifies, kept separate on purpose.

    Deliberately absent: any member naming a *combination*. `ARCH` §9 asks for
    evidence and uncertainty rather than a bare word, and a fourth "overall"
    member would be exactly the bare word — it would let a consumer read one
    value and skip the three that carry the information.
    """

    STRUCTURE = "structure"
    VOLATILITY = "volatility"
    PARTICIPATION = "participation"


class StructureState(str, Enum):
    """Whether structure is trending, ranging, or changing character.

    **Not a direction.** `TRENDING` says a sustained directional structure
    exists; it does not say which way, and reading it as bullish would be the v2
    mistake reintroduced. Which way is `StructuralTrendType`, one layer down.

    * `TRENDING` — both evidence families agree that structure is directional.
    * `RANGING` — both agree that it is not.
    * `TRANSITIONING` — a change of character occurred within the policy's
      lookback. The repository's own name for that event is *change of
      character*, so this state restates a fact rather than inventing one.
    * `INDETERMINATE` — the families disagree. Reported, never resolved.
    * `INSUFFICIENT` — at least one family had nothing to say.
    """

    TRENDING = "trending"
    RANGING = "ranging"
    TRANSITIONING = "transitioning"
    INDETERMINATE = "indeterminate"
    INSUFFICIENT = "insufficient"


class VolatilityState(str, Enum):
    """Whether recent true range stands above or below its own longer baseline.

    **Not** `fmis.features.VolatilityRegime`, which is a *level* vocabulary —
    LOW / NORMAL / HIGH / EXTREME — reserved for a volatility feature that has
    not been built. That answers "how volatile is this market"; this answers
    "is volatility changing relative to its own recent baseline". Reusing one
    enum for both would force one of the two meanings to bend, and the level
    vocabulary belongs to the feature layer that will compute it.

    Measured as a **ratio of two already-computed ATRs**, so the answer is
    self-normalising and carries no currency, no tick size and no asset class —
    the requirement that keeps this engine asset-agnostic.
    """

    EXPANDING = "expanding"
    CONTRACTING = "contracting"
    STEADY = "steady"
    INSUFFICIENT = "insufficient"


class ParticipationState(str, Enum):
    """Whether volume stands above or below its own recent average.

    `TYPICAL` rather than "normal": nothing here claims a distribution, and
    "normal" invites reading one.
    """

    ELEVATED = "elevated"
    SUBDUED = "subdued"
    TYPICAL = "typical"
    INSUFFICIENT = "insufficient"


class EvidenceStatus(str, Enum):
    """How one piece of evidence stands against its dimension's classification.

    `CONSISTENT` rather than "supporting" for two reasons. Evidence is consistent
    with a description of the environment; it does not *support a decision*, and
    this layer makes none. And the fact-only vocabulary guard that runs over
    rendered output forbids the substring ``support``, because a `PriceLevel` may
    never be called support (ADR-0019 §I) — a rule this package has no reason to
    bend.

    `CONTEXT` marks a fact that is **reported but counted neither for nor
    against** the state. `fmis.decision_support` set the precedent with
    `Alignment.NOT_DIRECTIONAL`: an observation worth showing that must never
    become evidence of something by itself. A change of character that happened
    long ago is the case here — a reader wants to know when structure last
    changed, but a stale event neither agrees nor disagrees with "trending".
    Without this status the choice is to hide the fact or to overstate it, and
    both are worse.

    `UNAVAILABLE` is **not** negative evidence. A warming-up indicator says
    nothing, and counting silence as disagreement is how an engine invents
    confidence it has not earned.
    """

    CONSISTENT = "consistent"
    CONFLICTING = "conflicting"
    CONTEXT = "context"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RegimeEvidence:
    """One fact the engine read, and how it stood.

    ``source`` names the evidence **family**, not the individual number, because
    families are the unit that may vote. Two members of one family are one piece
    of evidence; that is what stops a trend gate being counted twice, which
    `docs/analysis-notes.md` §1 records as the single largest cause of the v2
    LONG bias.

    ``observed`` is a short factual token — an enum value, or a qualitative
    reading such as ``"beyond both"``. ``value`` carries the number behind it
    when there is one, so a reader can check the classification rather than trust
    it.

    Frozen and hashable: evidence is a fact about one classification and cannot
    drift.
    """

    source: str
    status: EvidenceStatus
    observed: str
    value: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source:
            raise TypeError("source must be a non-empty str")
        if not isinstance(self.status, EvidenceStatus):
            raise TypeError(
                f"status must be an EvidenceStatus, got {type(self.status).__name__}"
            )
        if not isinstance(self.observed, str) or not self.observed:
            raise TypeError("observed must be a non-empty str")
        if self.value is not None and (
            isinstance(self.value, bool) or not isinstance(self.value, (int, float))
        ):
            raise TypeError(
                f"value must be a number or None, got {type(self.value).__name__}"
            )


@dataclass(frozen=True, slots=True)
class RegimeDimension:
    """One environment, its classification, and every fact behind it.

    ``reason`` is present exactly when the dimension declined to classify, and
    says which of the two different silences occurred — evidence absent, or
    evidence disagreeing. A dimension that classified carries ``None``: a reason
    on a decided state would be a rationalisation, and this layer does not write
    those.

    The three groupings below are **projections**, filtered from ``evidence`` on
    access rather than stored beside it, following ADR-0016 §4: three stored
    copies of one tuple are three places for it to drift.
    """

    name: RegimeDimensionName
    state: StructureState | VolatilityState | ParticipationState
    evidence: tuple[RegimeEvidence, ...]
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, RegimeDimensionName):
            raise TypeError(
                f"name must be a RegimeDimensionName, got {type(self.name).__name__}"
            )
        if not isinstance(
            self.state, (StructureState, VolatilityState, ParticipationState)
        ):
            raise TypeError(
                f"state must be a regime enum, got {type(self.state).__name__}"
            )
        if not isinstance(self.evidence, tuple):
            raise TypeError("evidence must be a tuple of RegimeEvidence")
        for position, item in enumerate(self.evidence):
            if not isinstance(item, RegimeEvidence):
                raise TypeError(
                    f"evidence[{position}] must be a RegimeEvidence, got "
                    f"{type(item).__name__}"
                )
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError(
                f"reason must be a str or None, got {type(self.reason).__name__}"
            )

    def _with_status(self, status: EvidenceStatus) -> tuple[RegimeEvidence, ...]:
        return tuple(item for item in self.evidence if item.status is status)

    @property
    def consistent(self) -> tuple[RegimeEvidence, ...]:
        """Evidence agreeing with the state — a projection, never stored."""
        return self._with_status(EvidenceStatus.CONSISTENT)

    @property
    def conflicting(self) -> tuple[RegimeEvidence, ...]:
        """Evidence disagreeing with the state — reported, never discarded."""
        return self._with_status(EvidenceStatus.CONFLICTING)

    @property
    def context(self) -> tuple[RegimeEvidence, ...]:
        """Facts reported but counted neither for nor against the state."""
        return self._with_status(EvidenceStatus.CONTEXT)

    @property
    def unavailable(self) -> tuple[RegimeEvidence, ...]:
        """Evidence that could not be read. **Not** evidence against anything."""
        return self._with_status(EvidenceStatus.UNAVAILABLE)


@dataclass(frozen=True, slots=True)
class MarketRegime:
    """Three classified environments for one series at one instant.

    Carries the identity and ``as_of`` of the series it describes, so a regime
    separated from its sheet still says what it is about and when — the same
    discipline ADR-0018 applied to derived facts.

    ``policy`` is the exact parameter set that produced this result, carried by
    reference and **type-checked**. A classification without its thresholds is not
    reproducible, and `ARCH` §9 requires regime to be checkable on historical
    data — a field that accepted anything would let a result cite a policy that
    could not have produced it.

    **There is no overall state and no score.** The dimensions are the result.
    Collapsing them would throw away the disagreement a reader most needs to see,
    and a number would imply a calibration this engine has never performed.

    Frozen and slotted, with ``metadata`` copied into a read-only mapping, so a
    regime cannot drift after construction.
    """

    symbol: str
    timeframe: str
    as_of: datetime
    dimensions: tuple[RegimeDimension, ...]
    policy: RegimePolicy
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol:
            raise RegimeInputError("symbol must be a non-empty str")
        if not isinstance(self.timeframe, str) or not self.timeframe:
            raise RegimeInputError("timeframe must be a non-empty str")
        if not isinstance(self.as_of, datetime):
            raise TypeError(
                f"as_of must be a datetime, got {type(self.as_of).__name__}"
            )
        if not isinstance(self.policy, RegimePolicy):
            raise TypeError(
                f"policy must be a RegimePolicy, got {type(self.policy).__name__}"
            )
        if not isinstance(self.dimensions, tuple):
            raise TypeError("dimensions must be a tuple of RegimeDimension")
        # Types first, then names. Reading `.name` off an unvalidated element
        # raises `AttributeError` from inside a comprehension, which tells a
        # caller nothing about which argument was wrong.
        for position, dimension in enumerate(self.dimensions):
            if not isinstance(dimension, RegimeDimension):
                raise TypeError(
                    f"dimensions[{position}] must be a RegimeDimension, got "
                    f"{type(dimension).__name__}"
                )
        names = [dimension.name for dimension in self.dimensions]
        if len(set(names)) != len(names):
            raise RegimeInputError(
                "dimensions must not repeat a name; a regime reporting one "
                "environment twice would let a reader pick the answer they liked"
            )
        if names != [name for name in RegimeDimensionName if name in set(names)]:
            raise RegimeInputError(
                "dimensions must be ordered structure, volatility, participation; "
                "a stable order is what makes two regimes diffable"
            )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def by_dimension(
        self,
    ) -> Mapping[RegimeDimensionName, RegimeDimension]:
        """Lookup by name — a projection over ``dimensions``, never a second store."""
        return MappingProxyType({d.name: d for d in self.dimensions})


@dataclass(frozen=True, slots=True)
class RegimeInput:
    """Exactly the facts the engine reads, and nothing else.

    **This is the layer boundary.** The engine classifies from this model alone:
    it never sees a `CandleSeries`, a `FeatureSet`, a fact sheet, or anything
    from `fmis.pipeline`. ADR-0007 puts the application layer at the top of the
    graph, so an engine that imported a fact sheet to read six numbers off it
    would invert the dependency for no gain. The composition root adapts; the
    engine stays reachable from a test with seven floats and an enum.

    Every optional field is optional because the repository can genuinely fail to
    produce it — an indicator still warming up, or a series with no confirmed
    swing. `None` means **not available**, never zero and never neutral.

    ``last_index`` and ``latest_change_index`` are positions in the closed-candle
    sequence, matching `SwingPoint.index`. They are supplied as indices rather
    than as a pre-computed distance because the subtraction is the engine's
    arithmetic to do: `fmis.pipeline` asserts it contains no arithmetic operator
    at all, and moving one subtraction up there to save a field would break that
    guarantee for a worse boundary.
    """

    symbol: str
    timeframe: str
    as_of: datetime
    structural_trend: StructuralTrendType
    last_index: int | None = None
    latest_change_index: int | None = None
    close: float | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None
    atr_fast: float | None = None
    atr_slow: float | None = None
    #: How much volume there is relative to its own recent baseline — a ratio
    #: around 1. Named for what the dimension reads rather than for the feature
    #: that produced it: the application root supplies `relative_volume_20`
    #: today, and an engine field named after one feature would bind this
    #: boundary to that feature's name the same way a hard-coded key would.
    participation_ratio: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol:
            raise RegimeInputError("symbol must be a non-empty str")
        if not isinstance(self.timeframe, str) or not self.timeframe:
            raise RegimeInputError("timeframe must be a non-empty str")
        if not isinstance(self.as_of, datetime):
            raise TypeError(
                f"as_of must be a datetime, got {type(self.as_of).__name__}"
            )
        if not isinstance(self.structural_trend, StructuralTrendType):
            raise TypeError(
                "structural_trend must be a StructuralTrendType, got "
                f"{type(self.structural_trend).__name__}"
            )
        for name in ("last_index", "latest_change_index"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an int or None")
            if value < 0:
                raise RegimeInputError(f"{name} cannot be negative, got {value}")
        for name in (
            "close",
            "ema_fast",
            "ema_slow",
            "atr_fast",
            "atr_slow",
            "participation_ratio",
        ):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number or None")
            if value != value or value in (float("inf"), float("-inf")):
                raise RegimeInputError(f"{name} must be finite, got {value}")
        if (
            self.latest_change_index is not None
            and self.last_index is not None
            and self.latest_change_index > self.last_index
        ):
            raise RegimeInputError(
                f"latest_change_index ({self.latest_change_index}) cannot exceed "
                f"last_index ({self.last_index}); a change of character cannot "
                "occur after the last closed candle"
            )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

