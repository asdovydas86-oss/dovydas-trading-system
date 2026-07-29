"""Market structure primitives — deterministic swing detection.

Value types and pure functions in four stages:

    CandleSeries    -> detect_swings          -> tuple[SwingPoint, ...]
    SwingPoints     -> compare_swing_sequence -> tuple[SwingComparison, ...]
    SwingComparisons-> label_swing_sequence   -> tuple[StructuralSwing, ...]
    StructuralSwings-> derive_structural_sequence_state
                                              -> StructuralSequenceState

`detect_swings` reports *where* a candle's high was a local maximum or its low a
local minimum. `compare_swings` / `compare_swing_sequence` then report *how* each
swing's price stands against the previous swing **of the same type**, as a
`SwingRelation` of HIGHER, LOWER or EQUAL. `label_swing` /
`label_swing_sequence` finally *name* that pairing — `HIGHER_HIGH`,
`LOWER_LOW`, `EQUAL_HIGH` and so on — which is naming an established fact, not
interpreting it.

**Facts, not structure.** A swing point says *where* an extreme was; a
comparison says which of two prices is the larger number. Neither says what that
means. Break of structure, change of character, trend, consolidation, support
and resistance, and liquidity each require further decisions, and none of them
belongs here. See ADR-0012 and ADR-0013.

**Naming happens here; interpretation still does not.** A `SwingType.HIGH`
whose relation is `SwingRelation.HIGHER` is a `StructuralSwingLabel.HIGHER_HIGH`
— and that is all it is. It does not mean uptrend, breakout, break of structure,
continuation, or a reason to trade, and `LOWER_LOW` is not a short signal. The
underlying `type` and `relation` remain available separately on the comparison,
so nothing is lost by naming the pair. Full names are canonical; `HH`/`LH`/`HL`
are prose shorthand only, because `LH` and `HL` differ by one transposition and
mean opposite things. `EQUAL_HIGH` and `EQUAL_LOW` stay first-class and are
never folded away or renamed "double top", "support", or "liquidity".

**The two sides are then read side by side, and still not interpreted.**
`derive_structural_sequence_state` puts the latest HIGH-side label next to the
latest LOW-side label and says how they stand together: both at higher prices,
both lower, outward with nothing inward, inward with nothing outward, or neither
moved. Five states partition the nine complete combinations exactly, so there is
no catch-all member — and a sixth, `INSUFFICIENT_STRUCTURE`, covers a side that
does not exist yet, because a two-sided statement is never invented from one
side. `SHIFTED_HIGHER` is not an uptrend, `CONTRACTED` is not consolidation,
`EXPANDED` is not a breakout, and `UNCHANGED` is not a double top. Both source
`StructuralSwing` objects stay attached so the exact pair is never lost to the
grouping. See ADR-0015.

**Aggregate state evolves; confirmed facts do not.** A `SwingPoint`,
`SwingComparison` and `StructuralSwing` are settled once emitted, and appending
later data never revises one. A `StructuralSequenceState` is by design a
statement about the *latest* pair, so a newer confirmed swing on either side
supersedes it — a new fact about newer data, not a revision of an old one. Only
the first guarantee is non-repainting in the strict sense, and this package does
not claim the second.

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
    appeared in the input — never enum or dictionary order. Labelling preserves
    that order exactly.
  * **One authoritative label mapping, kept private** (`models._label_for`),
    for the same reason the price rule is: a public `label_for(type, relation)`
    would name a pairing no validated comparison produced.
  * **One authoritative state mapping, kept private** (`models._sequence_state_for`
    over `models._STATE_BY_LABEL_PAIR`), for the same reason, and one shared
    ordering rule (`models._validate_current_point_order`) so no consumer of an
    ordered run grows a second, conflicting contract.
  * **Validate order, never repair it.** Unsorted input is a caller bug; sorting
    it silently would hide the bug and compare the wrong pairs.
  * **Imports only `fmis.data`.** Never `fmis.decision_support`,
    `fmis.evidence`, `fmis.providers`, `fmis.pipeline`, or anything to do with
    AI, execution, or portfolios — and nothing below imports this package.
"""

from __future__ import annotations

from fmis.market_structure.labels import label_swing, label_swing_sequence
from fmis.market_structure.models import (
    StructuralSequenceState,
    StructuralSequenceStateType,
    StructuralSwing,
    StructuralSwingLabel,
    SwingComparison,
    SwingPoint,
    SwingRelation,
    SwingType,
)
from fmis.market_structure.relationships import (
    compare_swing_sequence,
    compare_swings,
)
from fmis.market_structure.sequence_state import derive_structural_sequence_state
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
    "StructuralSwingLabel",
    "StructuralSwing",
    "StructuralSequenceStateType",
    "StructuralSequenceState",
    "detect_swings",
    "compare_swings",
    "compare_swing_sequence",
    "label_swing",
    "label_swing_sequence",
    "derive_structural_sequence_state",
    "required_candles",
    "DEFAULT_LEFT_BARS",
    "DEFAULT_RIGHT_BARS",
]
