"""Historical feature series — the additive companion to `FeatureResult`.

`Feature.compute()` answers *what is this feature's value now*. This module
answers *what has it been*, for every closed candle at which it was defined, and
it does so **without changing the first question's answer** (ADR-0031).

The distinction that makes the type worth having:

    FeatureResult   one value, the latest, with the parameters that produced it
    FeatureSeries   one value per closed candle at which the feature is defined,
                    each bound to the candle that produced it

`FeatureValue` already permits a `Sequence`, so a list *could* have been stuffed
into `FeatureResult.value`. That was rejected. A bare list answers none of the
questions a history raises — which candle is element 0, where warm-up ends,
whether a `None` means *not yet* or *not defined here*, which symbol and
timeframe this is — and every one of those reconstructions is a place for a
caller to be off by one. ADR-0031 records the alternatives and why each was
refused.

**Three states, never two.** A closed-candle position is in exactly one of them
and they are always distinguishable:

    no point at that index      the feature had not warmed up there
    a point with a value        the feature is defined and this is its value
    a point with a reason       the feature warmed up and is still undefined here
                                (`RelativeVolume` over an all-zero baseline)

**Nothing here computes anything.** This module holds the vocabulary; the
indicator packages hold the math, each in one shared helper so that
`compute()` and `compute_series()` cannot disagree.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from fmis.data import SeriesIdentity
from fmis.features.types import (
    FeatureCategory,
    FeatureContext,
    FeatureResult,
    FeatureValue,
)

__all__ = [
    "FeatureSeriesPoint",
    "FeatureSeries",
    "SeriesFeature",
    "supports_series",
]


@dataclass(frozen=True, slots=True)
class FeatureSeriesPoint:
    """One closed candle's feature value, bound to the candle that produced it.

    ``index`` is the candle's position in the **closed-candle sequence** the
    computation ran over — the same index space `SwingPoint.index`,
    `LevelOrigin.index` and `LevelCrossingEvent.index` already use, so a feature
    value and a structural event at one bar carry one number.

    ``timestamp`` is that candle's own timestamp, carried so a consumer can place
    a value in time without holding the candles.

    ``value`` is whatever the feature produces — a float for EMA, ATR and RSI, an
    immutable mapping for MACD. The protocol assumes no scalar anywhere.

    ``undefined_reason`` names why a warmed-up position still has no value. The
    invariant is enforced in both directions: a point has a value **or** a
    reason, never both and never neither. A point that carried neither would make
    *undefined* and *computed as nothing* look alike, which is the confusion
    `StructuralFactSheet.warming_up` exists one layer up to prevent.
    """

    index: int
    timestamp: datetime
    value: FeatureValue = None
    undefined_reason: str | None = None

    def __post_init__(self) -> None:
        # bool is an int subclass; an index of True is a programming error.
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise TypeError(f"index must be an int, got {type(self.index).__name__}")
        if self.index < 0:
            raise ValueError(f"index cannot be negative, got {self.index}")
        if not isinstance(self.timestamp, datetime):
            raise TypeError(
                f"timestamp must be a datetime, got {type(self.timestamp).__name__}"
            )
        if self.undefined_reason is not None and (
            not isinstance(self.undefined_reason, str)
            or not self.undefined_reason.strip()
        ):
            raise TypeError("undefined_reason must be a non-empty str or None")
        if (self.value is None) != (self.undefined_reason is not None):
            raise ValueError(
                "a point carries a value or an undefined_reason, never both and "
                "never neither; a valueless point with no reason cannot be told "
                "apart from a value that happens to be nothing"
            )


@dataclass(frozen=True, slots=True)
class FeatureSeries:
    """One feature's whole history over one closed candle series.

    ``identity`` is stored **once for the whole series**, following
    `ContextualSeries` (ADR-0018): a history of two thousand points holds one
    identity object, and no per-point copy exists to fall out of step with it.

    ``as_of`` is the **last closed candle's** timestamp — the same instant
    `FeatureSet.as_of` carries, and deliberately not the last point's timestamp.
    The two differ exactly while a feature is warming up, and collapsing them
    would make a warming-up series indistinguishable from a stale one. It is
    `None` only for a series computed over no closed candles at all.

    ``closed_candles`` is how many closed candles the computation saw, and
    ``warmup_candles`` how many it needs before its first point. Both are stored
    because neither is recoverable from ``points`` — an empty ``points`` tuple
    beside a positive ``closed_candles`` is the series form of
    ``FeatureResult(value=None, insufficient_data=True)``, and it still has to
    say how much history the feature wanted.

    ``first_index`` and ``latest`` are **projections over ``points``**, not
    stored fields (ADR-0016 §4): a stored copy of a value one attribute away is
    somewhere for it to drift.

    **Warm-up is never backfilled.** Positions before the first defined one carry
    no point at all — not `None`, not zero, not the seed. A consumer that wants
    to know where the series begins reads ``first_index``; one that wants to know
    where it *could* begin reads ``warmup_candles``.

    ``metadata`` carries the feature's own parameters and provenance, defensively
    copied into a read-only mapping on the `FeatureResult.metadata` convention.

    Frozen and slotted, so a computed history cannot drift downstream.
    """

    name: str
    category: FeatureCategory
    identity: SeriesIdentity
    as_of: datetime | None
    closed_candles: int
    warmup_candles: int
    points: tuple[FeatureSeriesPoint, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise TypeError("name must be a non-empty str")
        if not isinstance(self.category, FeatureCategory):
            raise TypeError(
                f"category must be a FeatureCategory, got {type(self.category).__name__}"
            )
        if not isinstance(self.identity, SeriesIdentity):
            raise TypeError(
                f"identity must be a SeriesIdentity, got {type(self.identity).__name__}"
            )
        if self.as_of is not None and not isinstance(self.as_of, datetime):
            raise TypeError(
                f"as_of must be a datetime or None, got {type(self.as_of).__name__}"
            )
        for name in ("closed_candles", "warmup_candles"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an int, got {type(value).__name__}")
            if value < 0:
                raise ValueError(f"{name} cannot be negative, got {value}")

        if isinstance(self.points, (str, bytes)) or not isinstance(
            self.points, Sequence
        ):
            raise TypeError("points must be a sequence of FeatureSeriesPoint")
        # Accept any non-string sequence at construction; store an immutable
        # tuple, matching `CandleSeries`' own normalisation of `candles`.
        object.__setattr__(self, "points", tuple(self.points))

        previous: FeatureSeriesPoint | None = None
        for position, point in enumerate(self.points):
            if not isinstance(point, FeatureSeriesPoint):
                raise TypeError(
                    f"points[{position}] must be a FeatureSeriesPoint, got "
                    f"{type(point).__name__}"
                )
            if point.index >= self.closed_candles:
                raise ValueError(
                    f"points[{position}] is at closed-candle index {point.index}, "
                    f"but only {self.closed_candles} closed candles were read; a "
                    "point cannot describe a bar that was not there"
                )
            if previous is not None:
                if point.index <= previous.index:
                    raise ValueError(
                        "points must be in strictly increasing candle order; "
                        f"points[{position}] is at index {point.index} after "
                        f"{previous.index}"
                    )
                if point.timestamp <= previous.timestamp:
                    raise ValueError(
                        "point timestamps must be strictly increasing, matching "
                        "the candle series they index into"
                    )
            previous = point

        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def first_index(self) -> int | None:
        """The closed-candle index of the first defined point, or `None`.

        A **projection**, never a stored field. `None` means the feature has not
        warmed up over this input — which is a different statement from "its
        first value is zero" and is why an absent series returns an absence.
        """
        return self.points[0].index if self.points else None

    @property
    def latest(self) -> FeatureSeriesPoint | None:
        """The most recent point, or `None` while warming up."""
        return self.points[-1] if self.points else None

    def point_at(self, index: int) -> FeatureSeriesPoint | None:
        """The point at one closed-candle index, or `None` if undefined there.

        A container lookup, not a calculation: the answer for a warming-up
        position is an absence, never an interpolation.
        """
        for point in self.points:
            if point.index == index:
                return point
        return None


@runtime_checkable
class SeriesFeature(Protocol):
    """A `Feature` that can additionally produce its whole aligned history.

    **Additive, and deliberately a second Protocol.** `Feature` is unchanged and
    `BaseFeature` declares no abstract `compute_series`, so a feature whose
    output is not a series — a pattern detector, say — stays a perfectly valid
    `Feature`. `supports_series` is the one published way to ask, and it has two
    honest answers.

    `compute_series` reads the same `FeatureContext` `compute` reads and honours
    the same closed-candles-only rule, so the two cannot describe different bars.
    """

    @property
    def name(self) -> str: ...

    @property
    def category(self) -> FeatureCategory: ...

    @property
    def dependencies(self) -> tuple[str, ...]: ...

    def compute(self, context: FeatureContext) -> FeatureResult: ...

    def compute_series(self, context: FeatureContext) -> FeatureSeries: ...


def supports_series(feature: object) -> bool:
    """Can this feature produce an aligned history?

    A named function rather than an inline `isinstance`, so the question is asked
    in one place and a caller cannot decide it by reading for a method name.
    """
    return isinstance(feature, SeriesFeature)
