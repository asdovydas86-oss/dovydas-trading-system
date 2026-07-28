"""Deterministic volume measurements: average volume and relative volume.

Two features, both reading `Candle.volume` over closed candles and both taking
their arithmetic from `volume_math.trailing_mean`, so the baseline is computed in
exactly one place.

These are **measurements, not conclusions.** Neither feature emits a label, a
threshold, a direction, or a judgement — no "high volume", no "confirmed", no
"strong". A relative volume of 3.0 is a fact; what it means on a Shenzhen
open-auction bar versus a 24/7 crypto perpetual is a question for a later,
market-aware interpretation layer, and deliberately not answerable here.

Window convention (see `volume_math`): the baseline is the ``lookback`` candles
*preceding* the latest one, which is therefore excluded from its own comparison.
Warm-up is ``lookback + 1`` closed candles.

Volume validity is inherited, not re-checked: `Candle` already rejects negative
and non-finite volume, and permits zero. Re-validating here would create a second
source of truth for a rule the canonical model owns.
"""

from __future__ import annotations

from typing import Any

from fmis.features.types import (
    BaseFeature,
    FeatureCategory,
    FeatureContext,
    FeatureResult,
)
from fmis.features.volume.volume_math import required_values, trailing_mean

__all__ = ["AverageVolume", "RelativeVolume"]

#: Metadata key naming why a value is absent although warm-up was satisfied.
#: A plain string rather than an imported enum: `fmis.features` must not depend
#: on `fmis.relative_value`, where the existing `UndefinedReason` vocabulary lives.
UNDEFINED_REASON_KEY = "undefined_reason"

#: The only undefined case these features have: every candle in the baseline
#: window reported zero volume, so the ratio has no denominator.
ZERO_BASELINE = "zero_average_volume"


def _require_lookback(lookback: object) -> int:
    """Validate a lookback the way every other feature validates its period."""
    # Reject bool explicitly: bool is a subclass of int but not a valid lookback.
    if isinstance(lookback, bool) or not isinstance(lookback, int):
        raise TypeError(f"lookback must be an int, got {type(lookback).__name__}")
    if lookback < 1:
        raise ValueError(f"lookback must be at least 1, got {lookback}")
    return lookback


def _base_metadata(lookback: int, available: int, *, provenance: str) -> dict[str, Any]:
    return {
        "lookback": lookback,
        "source": "volume",
        "closed_candles_available": available,
        "warmup_candles": required_values(lookback),
        "required_candles": required_values(lookback),
        "baseline_window": "the `lookback` candles preceding the latest one",
        "current_candle_excluded_from_baseline": True,
        "provenance": provenance,
    }


class AverageVolume(BaseFeature):
    """Mean volume over the ``lookback`` candles preceding the latest closed one.

    Value is a ``float``, or ``None`` while warming up. The latest candle is
    excluded so this reads as a *baseline* the latest candle can be compared
    against — including by `RelativeVolume`, which shares this arithmetic rather
    than repeating it.
    """

    category = FeatureCategory.VOLUME
    dependencies: tuple[str, ...] = ()

    def __init__(self, lookback: int = 20) -> None:
        self._lookback = _require_lookback(lookback)
        self.name = f"average_volume_{self._lookback}"

    @property
    def lookback(self) -> int:
        return self._lookback

    def compute(self, context: FeatureContext) -> FeatureResult:
        # Closed candles only — idempotent even if the engine already closed them.
        candles = context.primary.closed().candles
        volumes = [candle.volume for candle in candles]

        metadata = _base_metadata(
            self._lookback,
            len(candles),
            provenance="fmis.features.volume.statistics.AverageVolume",
        )

        baseline = trailing_mean(volumes, self._lookback)
        if baseline is None:
            return FeatureResult(
                name=self.name,
                category=self.category,
                value=None,
                metadata={**metadata, "insufficient_data": True},
            )
        return FeatureResult(
            name=self.name,
            category=self.category,
            value=baseline,
            metadata={**metadata, "insufficient_data": False},
        )


class RelativeVolume(BaseFeature):
    """Latest candle volume divided by the preceding ``lookback``-candle average.

    ``relative_volume = current_volume / average_volume``

    A value of 1.0 means the latest candle traded exactly its recent baseline;
    2.0 means twice it. The value is a bare ratio and carries no threshold — this
    feature never says whether a ratio is notable.

    Three distinguishable outcomes, each readable from the result:

      * **calculated** — ``value`` is a float, ``insufficient_data`` is ``False``.
      * **insufficient warm-up** — ``value`` is ``None``, ``insufficient_data`` is
        ``True``; fewer than ``lookback + 1`` closed candles.
      * **undefined** — ``value`` is ``None``, ``insufficient_data`` is ``False``,
        and ``undefined_reason`` is ``"zero_average_volume"``: enough candles, but
        every one in the baseline window reported zero volume, so there is no
        denominator. Not a real edge case only in theory — a halted session or an
        illiquid listing genuinely produces it.

    A zero denominator is reported, never repaired: no infinity is fabricated and
    no epsilon is substituted, because both would turn "we cannot say" into a
    number a later layer would treat as a measurement.

    ``current_volume`` and ``average_volume`` are recorded in metadata so a
    consumer can see the inputs without the raw candle series and without a second
    feature restating what `Candle.volume` already owns.
    """

    category = FeatureCategory.VOLUME
    dependencies: tuple[str, ...] = ()

    def __init__(self, lookback: int = 20) -> None:
        self._lookback = _require_lookback(lookback)
        self.name = f"relative_volume_{self._lookback}"

    @property
    def lookback(self) -> int:
        return self._lookback

    def compute(self, context: FeatureContext) -> FeatureResult:
        # Closed candles only — idempotent even if the engine already closed them.
        candles = context.primary.closed().candles
        volumes = [candle.volume for candle in candles]

        metadata = _base_metadata(
            self._lookback,
            len(candles),
            provenance="fmis.features.volume.statistics.RelativeVolume",
        )
        metadata["formula"] = "relative_volume = current_volume / average_volume"

        baseline = trailing_mean(volumes, self._lookback)
        if baseline is None:
            return FeatureResult(
                name=self.name,
                category=self.category,
                value=None,
                metadata={**metadata, "insufficient_data": True},
            )

        current = volumes[-1]
        metadata.update(
            {
                "insufficient_data": False,
                "current_volume": current,
                "average_volume": baseline,
            }
        )

        if baseline == 0:
            return FeatureResult(
                name=self.name,
                category=self.category,
                value=None,
                metadata={**metadata, UNDEFINED_REASON_KEY: ZERO_BASELINE},
            )
        return FeatureResult(
            name=self.name,
            category=self.category,
            value=current / baseline,
            metadata=metadata,
        )
