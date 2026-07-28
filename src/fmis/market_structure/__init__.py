"""Market structure primitives — deterministic swing detection.

Value types and pure functions in two layers:

    CandleSeries -> detect_swings          -> tuple[SwingPoint, ...]
    SwingPoints  -> compare_swing_sequence -> tuple[SwingComparison, ...]

`detect_swings` reports *where* a candle's high was a local maximum or its low a
local minimum. `compare_swings` / `compare_swing_sequence` then report *how* each
swing's price stands against the previous swing **of the same type**, as a
`SwingRelation` of HIGHER, LOWER or EQUAL.

**Facts, not structure.** A swing point says *where* an extreme was; a
comparison says which of two prices is the larger number. Neither says what that
means. Break of structure, change of character, trend, consolidation, support
and resistance, and liquidity each require further decisions, and none of them
belongs here. See ADR-0012 and ADR-0013.

**The HH/HL/LH/LL naming is deliberately withheld.** A `SwingType.HIGH` whose
relation is `SwingRelation.HIGHER` is what people call a "higher high", but that
label fuses two facts into one word and invites reading a trend into it. The two
are kept separate — ``type`` and ``relation`` — so the layer that eventually
names them does so as an explicit decision.

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
  * **No interpretation.** No direction, trend, strength, confidence, or
    ranking. No BOS, CHoCH, HH/HL/LH/LL naming, support, resistance, or
    liquidity. Comparing two prices is arithmetic; calling the result bullish is
    not, and only the first belongs here.
  * **Compare like with like.** A swing high is only ever compared to another
    swing high, a low only to another low.
  * **One authoritative price rule, kept private.** Comparison is exact and
    lives in `models._relation_for`; `compare_swings` is the only public pair
    operation, because it is the one that validates.
  * **Ties break on input order.** Two comparisons sharing a `current.index`
    (one candle yielding both a HIGH and a LOW) appear in the order those points
    appeared in the input — never enum or dictionary order.
  * **Validate order, never repair it.** Unsorted input is a caller bug; sorting
    it silently would hide the bug and compare the wrong pairs.
  * **Imports only `fmis.data`.** Never `fmis.decision_support`,
    `fmis.evidence`, `fmis.providers`, `fmis.pipeline`, or anything to do with
    AI, execution, or portfolios — and nothing below imports this package.
"""

from __future__ import annotations

from fmis.market_structure.models import (
    SwingComparison,
    SwingPoint,
    SwingRelation,
    SwingType,
)
from fmis.market_structure.relationships import (
    compare_swing_sequence,
    compare_swings,
)
from fmis.market_structure.swings import (
    DEFAULT_LEFT_BARS,
    DEFAULT_RIGHT_BARS,
    detect_swings,
    required_candles,
)

__all__ = [
    "SwingType",
    "SwingPoint",
    "SwingRelation",
    "SwingComparison",
    "detect_swings",
    "compare_swings",
    "compare_swing_sequence",
    "required_candles",
    "DEFAULT_LEFT_BARS",
    "DEFAULT_RIGHT_BARS",
]
