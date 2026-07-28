"""Market structure primitives — deterministic swing detection.

Two value types and one function: `SwingType`, `SwingPoint`, and
`detect_swings`, which reports where a candle's high was a local maximum or its
low a local minimum relative to a fixed number of neighbours.

    CandleSeries -> detect_swings -> tuple[SwingPoint, ...]

**Located facts, not structure.** A swing point says *where* an extreme was. It
says nothing about what the sequence of extremes means. Higher-high / lower-low
classification, break of structure, change of character, trend, consolidation,
support and resistance, and liquidity all come from *comparing* swings to each
other — each is a later milestone, and none of them belongs here. See ADR-0012.

**Why this is a package and not a Feature.** `FeatureValue` covers floats,
bools, strings, mappings and sequences of those; a tuple of `SwingPoint`
dataclasses is none of them, so swing points cannot be a `FeatureResult.value`
without being flattened into dictionaries and losing their type. They are domain
objects. A future Tier-2 feature in `fmis.features.market_structure` may consume
these points and summarise them into something `FeatureValue` can hold — that is
the intended split, and it is why the placeholder there no longer claims swing
detection.

Guarantees this package is built on, all inherited rather than re-implemented:
`CandleSeries` already enforces strictly increasing UTC timestamps, a single
symbol and timeframe, finite non-negative OHLCV, and `high >= low`. Detection
adds no validation of its own beyond its two parameters.

The plateau rule is a **deterministic representation policy, not a market
claim**: it deliberately makes detection asymmetric in time (strict left,
`>=` right), it is not the only defensible reading of a run of equal extremes,
and a downstream layer wanting a different convention must say so explicitly
rather than silently re-deriving swings under different rules. See ADR-0012 §6.

Rules for anything added here:
  * **Closed candles only**, always. A forming bar's high and low can still
    move, and a swing that can change is not a fact.
  * **Never inspect a candle outside the confirmation window.** A point is
    emitted only once every candle it depends on has closed, which is what makes
    detection non-repainting: later data never revises an earlier point.
  * **No interpretation.** No direction, trend, strength, confidence, ranking,
    or comparison between swings. No BOS, CHoCH, HH/HL/LH/LL, support,
    resistance, or liquidity.
  * **Imports only `fmis.data`.** Never `fmis.decision_support`,
    `fmis.evidence`, `fmis.providers`, `fmis.pipeline`, or anything to do with
    AI, execution, or portfolios — and nothing below imports this package.
"""

from __future__ import annotations

from fmis.market_structure.models import SwingPoint, SwingType
from fmis.market_structure.swings import (
    DEFAULT_LEFT_BARS,
    DEFAULT_RIGHT_BARS,
    detect_swings,
    required_candles,
)

__all__ = [
    "SwingType",
    "SwingPoint",
    "detect_swings",
    "required_candles",
    "DEFAULT_LEFT_BARS",
    "DEFAULT_RIGHT_BARS",
]
