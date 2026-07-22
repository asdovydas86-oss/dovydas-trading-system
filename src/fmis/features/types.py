"""Core type definitions for the deterministic Feature Engine.

This module defines the *vocabulary* of the Feature Engine — the interface every
calculation implements and the standardized objects that flow between layers. It
contains **no indicator math**. EMA, RSI, MACD, ATR, etc. are deliberately not
implemented here (or anywhere yet); this file only describes the shapes that
will hold their results.

Design in one paragraph:
    A ``Feature`` is a small, single-responsibility unit that reads a
    ``FeatureContext`` (the price series plus any already-computed features and
    auxiliary technical inputs) and returns exactly one ``FeatureResult``. A
    ``FeatureEngine`` runs a set of features and assembles their results into a
    ``FeatureSet`` — the single, standardized output object that higher layers
    consume. Features are discovered through a ``FeatureRegistry`` rather than
    hard-wired, so new *technical* calculations can be added without editing
    existing modules.

Scope boundary (important):
    This engine is strictly for **deterministic technical-market features** —
    price/volume-derived indicators, momentum, trend, volatility, market
    structure, support/resistance, and deterministic pattern detection. It does
    **not** own macro, news, on-chain, derivatives, sentiment, or AI-generated
    interpretation. Those are separate future engines; a Context / Evidence
    Aggregation layer will combine their outputs with this engine's FeatureSet.
    Every ``FeatureResult`` produced here is deterministic and reproducible;
    non-deterministic AI observations/interpretations belong to another layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, Union, runtime_checkable

from fmis.data import CandleSeries

__all__ = [
    "FeatureValue",
    "FeatureCategory",
    "TrendDirection",
    "VolatilityRegime",
    "MomentumRegime",
    "FeatureResult",
    "FeatureContext",
    "FeatureSet",
    "Feature",
    "BaseFeature",
]


# A feature may produce a scalar (RSI = 55.3), a boolean (is_golden_cross),
# a label (trend = "up"), a multi-component mapping (MACD -> line/signal/hist),
# or a sequence (an EMA series). This recursive union covers all of them without
# forcing every calculation into the same rigid shape.
FeatureValue = Union[
    float,
    int,
    bool,
    str,
    None,
    Mapping[str, "FeatureValue"],
    Sequence["FeatureValue"],
]


class FeatureCategory(str, Enum):
    """Technical evidence category a feature belongs to.

    Grouping features by category lets the future Decision / Aggregation layer
    weigh *diversity* of technical evidence instead of counting correlated
    indicators twice (see PROJECT_SPECIFICATION_V1.md section 4.6).

    Scope: these are stable **technical-analysis** categories only. Non-technical
    domains — macro, news, on-chain, derivatives, sentiment, AI-generated — are
    intentionally NOT represented here. Each of those is a separate future engine
    whose outputs a Context / Evidence Aggregation layer combines with this
    engine's FeatureSet. Do not add such members to this enum.
    """

    INDICATOR = "indicator"          # raw TA primitives: EMA, RSI, MACD, ATR, ...
    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    MARKET_STRUCTURE = "market_structure"
    SUPPORT_RESISTANCE = "support_resistance"
    PATTERN = "pattern"


class TrendDirection(str, Enum):
    """Output vocabulary for trend-direction features (not computed yet)."""

    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"
    UNDEFINED = "undefined"


class VolatilityRegime(str, Enum):
    """Output vocabulary for volatility-regime features (not computed yet)."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"
    UNDEFINED = "undefined"


class MomentumRegime(str, Enum):
    """Output vocabulary for momentum-regime features (not computed yet)."""

    ACCELERATING = "accelerating"
    STEADY = "steady"
    DECELERATING = "decelerating"
    UNDEFINED = "undefined"


@dataclass(frozen=True, slots=True)
class FeatureResult:
    """One feature's output: what it is, which category, its value, and how it
    was produced.

    A FeatureResult is always a **deterministic, reproducible technical
    calculation** — same input series and parameters always yield the same value.
    This is deliberately distinct from future AI observations/interpretations,
    which are non-deterministic and belong to a separate layer, never here.

    Immutable so a computed result cannot be mutated downstream. ``metadata``
    carries the parameters used (e.g. ``{"period": 50}``), warm-up/insufficient
    bars flags, and provenance — everything needed to make a value reproducible
    and auditable later.
    """

    name: str
    category: FeatureCategory
    value: FeatureValue
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FeatureContext:
    """Everything a feature is allowed to read while computing.

    - ``primary``  : the price series the FeatureSet is being built for.
    - ``computed`` : results of features that already ran this pass, so a feature
                     can depend on another (e.g. "distance to EMA" reads "EMA")
                     without recomputing it.
    - ``sources``  : an extension slot for named **auxiliary technical inputs**
                     that a feature may need beyond the primary series — e.g. a
                     higher-timeframe candle series or a reference instrument.
                     It is NOT a universal container for unrelated domains
                     (macro, news, on-chain, derivatives, sentiment, AI); those
                     live in separate engines, not in this context.
    """

    primary: CandleSeries
    computed: Mapping[str, FeatureResult] = field(default_factory=dict)
    sources: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FeatureSet:
    """The standardized output of the Feature Engine for one symbol+timeframe.

    A FeatureSet is deliberately **single-timeframe**. Multi-timeframe alignment
    (1W/1D/4H) is composed one layer up by combining several FeatureSets, keeping
    this object simple and each feature's meaning unambiguous.

    Accessors below are plain container lookups, not calculations.
    """

    symbol: str
    timeframe: str
    as_of: datetime  # timestamp of the last (closed) candle the set describes
    features: Mapping[str, FeatureResult] = field(default_factory=dict)

    def get(self, name: str) -> FeatureResult | None:
        """Return the named result, or None if absent."""
        return self.features.get(name)

    def has(self, name: str) -> bool:
        """Return True if the named feature is present."""
        return name in self.features

    def by_category(self, category: FeatureCategory) -> tuple[FeatureResult, ...]:
        """Return all results in one evidence category (order not guaranteed)."""
        return tuple(r for r in self.features.values() if r.category == category)

    # TODO(milestone-C-impl): typed convenience accessors once concrete features
    # exist, e.g. ema(period) -> float, trend_direction() -> TrendDirection.


@runtime_checkable
class Feature(Protocol):
    """Structural interface every calculation implements.

    Kept intentionally tiny — one responsibility, one result. ``dependencies``
    names other features that must run first; the engine uses it to order work.
    Being a ``runtime_checkable`` Protocol means any object with these members
    qualifies, so features need not inherit from a shared base if they prefer not
    to (though ``BaseFeature`` is provided for convenience).
    """

    @property
    def name(self) -> str: ...

    @property
    def category(self) -> FeatureCategory: ...

    @property
    def dependencies(self) -> tuple[str, ...]: ...

    def compute(self, context: FeatureContext) -> FeatureResult: ...


class BaseFeature(ABC):
    """Optional convenience base for features.

    Subclasses set ``name`` and ``category`` (and ``dependencies`` if any) as
    class attributes and implement ``compute``. This base contains **no math** —
    concrete indicator/structure/volatility/etc. subclasses are added in later
    milestones, each in its own category package.
    """

    name: str
    category: FeatureCategory
    dependencies: tuple[str, ...] = ()

    @abstractmethod
    def compute(self, context: FeatureContext) -> FeatureResult:
        """Read ``context`` and return this feature's single result."""
        raise NotImplementedError
