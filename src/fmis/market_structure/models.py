"""Value types for deterministic swing detection and comparison.

A `SwingPoint` is a **located fact**: at this candle, this extreme price was a
local high or low relative to its neighbours. It is not a judgement. It carries
no direction, no trend, no strength, and no confidence.

A `SwingComparison` adds exactly one more fact — how one swing's price stands
against the previous swing *of the same kind* — expressed as a `SwingRelation`
of HIGHER, LOWER or EQUAL. That is arithmetic about two numbers, not a reading
of the market.

A `StructuralSwing` adds a **name** for that pairing and nothing else: a
`SwingType` and a `SwingRelation` together are what a chartist calls a higher
high or a lower low. Naming a fact is not interpreting it — break of structure,
trend, and support levels all require further decisions this layer deliberately
does not make.

A `StructuralSequenceState` puts the latest HIGH-side label beside the latest
LOW-side label and says how the two stand together — both sides at higher
prices, both lower, outward, inward, or neither. That is still arithmetic about
two already-established facts. It is not a trend, a bias, or a reason to trade,
and either side may simply be absent.

``index`` is a position into the **closed** candles of the series it was derived
from (`CandleSeries.closed().candles`), not into the raw series. Detection
operates on closed candles only, so any forming candle is absent before indices
are assigned; a raw index would silently mean something different depending on
whether the last bar had closed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType

__all__ = [
    "SwingType",
    "SwingPoint",
    "SwingRelation",
    "SwingComparison",
    "StructuralSwingLabel",
    "StructuralSwing",
    "StructuralSequenceStateType",
    "StructuralSequenceState",
    "StructuralSequenceStateSnapshot",
]


class SwingType(str, Enum):
    """Which extreme a swing point marks.

    Two members and no third: a swing is a high or a low. Anything that would
    need a `NEUTRAL`, `BOTH`, or `UNCONFIRMED` member is a different concept —
    an unconfirmed swing is simply not emitted, and a candle that is both a
    swing high and a swing low produces two separate points.
    """

    HIGH = "high"
    LOW = "low"


def _require_bars(value: object, field: str) -> int:
    """A positive int. ``bool`` is rejected explicitly, being an int subclass.

    **The one bar-count rule in this package.** It lives here rather than in
    `swings`, where it began, because `SwingPoint.confirmation_bars` must apply
    exactly the same rule and `swings` imports *this* module — importing back the
    other way would close an import cycle. `required_candles` and `detect_swings`
    read it from here, so a window this validator rejects cannot be used for
    detection *or* recorded on a point, in one wording rather than two.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an int, got {type(value).__name__}")
    if value < 1:
        raise ValueError(f"{field} must be at least 1, got {value}")
    return value


@dataclass(frozen=True, slots=True)
class SwingPoint:
    """One confirmed local extreme: where it is, when, at what price, which kind.

    Frozen, slotted and hashable, so a detected swing cannot drift, cannot grow
    an attribute it was never given, and can be put in a set or used as a dict
    key when a later layer compares runs.

    Fields, and nothing else:
      * ``index`` — position in the closed-candle sequence it was detected from.
      * ``timestamp`` — that candle's timestamp, carried so a point stays
        meaningful once separated from the series.
      * ``price`` — the candle's ``high`` for a `SwingType.HIGH`, its ``low``
        for a `SwingType.LOW`. The extreme itself, never a midpoint or average.
      * ``type`` — `SwingType.HIGH` or `SwingType.LOW`.
      * ``confirmation_bars`` — the ``right_bars`` this point was **confirmed
        under**. See below; it is the reason ADR-0020 D1 is closed.

    **Why the confirmation window is carried (ADR-0024).** A pivot at bar ``o``
    is not knowable at bar ``o``: it becomes knowable only once
    ``confirmation_bars`` further candles have closed and none of them exceeded
    it. Every consumer that places a swing *in time* needs that number, and until
    this field existed the number travelled **beside** the data as a hand-passed
    argument — `derive_structure_breaks(..., confirmation_bars=R)`. A caller who
    passed a different ``R`` than the one used for detection silently changed
    which level was the reference at every bar, and therefore which breaks and
    which changes of character existed, **while raising no error**: measured at
    36.1 % of 300 seeded series producing materially different breaks, zero of
    them detected. Carrying the number on the point that earned it makes that
    mismatch unrepresentable rather than merely discouraged.

    ``left_bars`` is deliberately **not** carried. It decides *whether* a pivot
    is a pivot, which is already settled by the time this object exists; only
    ``right_bars`` decides *when the pivot became knowable*, and that is the one
    question a later layer asks. Carrying a field no consumer reads would be
    provenance theatre. Adding it later is purely additive if a consumer appears.

    ``confirmation_bars`` is **required and has no default.** A default would
    silently bind every hand-built point to `DEFAULT_RIGHT_BARS` and be wrong for
    anyone who detected with another window — the exact failure this field exists
    to prevent, reintroduced at the constructor.

    Deliberately absent: direction, trend, strength, confidence, rank, and any
    reference to a neighbouring swing. Each of those is an interpretation, and
    a field for one would invite filling it before anything can compute it.
    """

    index: int
    timestamp: datetime
    price: float
    type: SwingType
    confirmation_bars: int

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
        if isinstance(self.price, bool) or not isinstance(self.price, (int, float)):
            raise TypeError(f"price must be a number, got {type(self.price).__name__}")
        if not math.isfinite(self.price):
            raise ValueError("price must be a finite number")
        if not isinstance(self.type, SwingType):
            raise TypeError(f"type must be a SwingType, got {type(self.type).__name__}")
        # Validated with `_require_bars`' own rule rather than a second wording:
        # at least 1, because `detect_swings` — the only producer — rejects a
        # smaller window outright. A point claiming to have been confirmed under
        # zero bars would claim a confirmation that never happened.
        _require_bars(self.confirmation_bars, "confirmation_bars")

    @property
    def knowable_from(self) -> int:
        """The earliest closed-candle index at which this pivot was knowable.

        ``index + confirmation_bars`` — a **projection, not a stored field**,
        following ADR-0016 §4: a stored copy of a value one attribute away is
        somewhere for it to drift.

        This is a fact about **detection**, not a policy about what may be done
        at that bar. `fmis.structure_break` decides that a level becomes eligible
        to break structure here; that decision stays in that layer, and this
        property states only when the point became knowable at all.
        """
        return self.index + self.confirmation_bars


class SwingRelation(str, Enum):
    """How one swing's price stands against the previous swing of its own kind.

    Three members describing **numeric movement only**. `HIGHER` means the later
    price is the larger number — nothing more. It is not "bullish", and on a
    swing low it says only that the low sits at a higher price than the low
    before it.

    Deliberately absent: BULLISH, BEARISH, BREAK, REVERSAL, CONTINUATION, and
    anything carrying confidence or strength. Each of those is a reading of the
    fact rather than the fact, and each needs its own decision record.

    There is also no UNAVAILABLE member. Both swings always exist and always
    carry a finite price, so every comparison resolves — unlike
    `fmis.decision_support.Comparison`, which describes possibly-missing values
    in a different layer and must not be reused here.
    """

    HIGHER = "higher"
    LOWER = "lower"
    EQUAL = "equal"


def _relation_for(previous: SwingPoint, current: SwingPoint) -> SwingRelation:
    """The relation implied by two swings' prices — the one authoritative rule.

    Comparison is **exact** on the stored float values:

        current.price > previous.price  -> HIGHER
        current.price < previous.price  -> LOWER
        otherwise                       -> EQUAL

    No epsilon, tolerance, percentage band, ATR scaling, rounding, or `Decimal`
    conversion, matching `fmis.decision_support.classify_comparison`. The
    repository stores prices as plain validated floats with no tick-size or
    instrument-precision metadata anywhere, so any tolerance would be a locally
    invented judgement about what counts as "the same price". ADR-0013 §4 records
    the limitation that leaves.

    Deliberately **private**. It compares prices and nothing else — it does not
    check that the two swings share a type, or that ``current`` actually follows
    ``previous``. Exposing it publicly would offer a plausible-looking shortcut
    that silently bypasses every invariant `SwingComparison` exists to enforce.
    Callers use `compare_swings`, which validates. Defined once here and used by
    both `SwingComparison.__post_init__` and `compare_swings`, so the rule has
    exactly one implementation.
    """
    if current.price > previous.price:
        return SwingRelation.HIGHER
    if current.price < previous.price:
        return SwingRelation.LOWER
    return SwingRelation.EQUAL


@dataclass(frozen=True, slots=True)
class SwingComparison:
    """Two same-kind swings and how their prices compare. Nothing more.

    ``previous`` and ``current`` are the two `SwingPoint` objects, kept whole so
    a consumer can see index, timestamp and price without a lookup. ``relation``
    is the arithmetic result, and is **validated against the prices** rather than
    trusted: an object claiming HIGHER when the price fell cannot be constructed.

    Invariants, all enforced on construction:
      * both points are `SwingPoint` objects;
      * both have the **same** `SwingType` — a high is never compared to a low;
      * ``current.index > previous.index``;
      * ``current.timestamp > previous.timestamp``;
      * ``relation`` equals the exact price comparison (see `compare_swings`).

    The ordering checks reject reversed arguments rather than silently swapping
    them. "Previous" and "current" are the caller's claim about direction of
    time, and quietly reordering would turn a caller's mistake into a plausible
    but wrong answer.

    Frozen, slotted and hashable: a comparison is a fact about two fixed points
    and cannot drift, and it can be put in a set when a later layer diffs runs.

    Deliberately absent: any label combining type and relation. A swing high that
    is HIGHER than the previous swing high is commonly called a "higher high",
    but that name is an interpretation; this type keeps ``type`` and ``relation``
    as two separate facts so a later layer can name them deliberately.
    """

    previous: SwingPoint
    current: SwingPoint
    relation: SwingRelation

    def __post_init__(self) -> None:
        for name, value in (("previous", self.previous), ("current", self.current)):
            if not isinstance(value, SwingPoint):
                raise TypeError(
                    f"{name} must be a SwingPoint, got {type(value).__name__}"
                )
        if not isinstance(self.relation, SwingRelation):
            raise TypeError(
                f"relation must be a SwingRelation, got {type(self.relation).__name__}"
            )
        if self.previous.type is not self.current.type:
            raise ValueError(
                "previous and current must have the same SwingType, got "
                f"{self.previous.type.value!r} and {self.current.type.value!r}"
            )
        if self.current.index <= self.previous.index:
            raise ValueError(
                f"current.index ({self.current.index}) must be greater than "
                f"previous.index ({self.previous.index})"
            )
        if self.current.timestamp <= self.previous.timestamp:
            raise ValueError(
                f"current.timestamp ({self.current.timestamp.isoformat()}) must be "
                f"later than previous.timestamp ({self.previous.timestamp.isoformat()})"
            )
        if self.previous.confirmation_bars != self.current.confirmation_bars:
            raise ValueError(
                "previous and current must share a confirmation window, got "
                f"{self.previous.confirmation_bars} and "
                f"{self.current.confirmation_bars}; two points detected under "
                "different windows are not a comparable pair"
            )
        expected = _relation_for(self.previous, self.current)
        if self.relation is not expected:
            raise ValueError(
                f"relation {self.relation.value!r} does not match the prices "
                f"({self.previous.price} -> {self.current.price}); "
                f"expected {expected.value!r}"
            )


class StructuralSwingLabel(str, Enum):
    """The conventional name for one `SwingType` + `SwingRelation` pairing.

    Six members, exhausting the two swing types against the three relations.
    Each is a **name for an established fact**, not a reading of it:
    `HIGHER_HIGH` says the current swing is a high whose price is numerically
    above the previous high. It does not say the market is trending up, that a
    breakout occurred, that structure broke, or that anything should be traded —
    and `LOWER_LOW` is correspondingly not a short signal.

    Names are written in full. `HH`, `LH`, `EH`, `HL`, `LL`, `EL` are common
    shorthand and may appear in prose, but abbreviations make the wrong thing
    easy: `LH` and `HL` differ by one transposition and mean opposite things,
    which is a poor property for an identifier that will appear in conditionals.

    `EQUAL_HIGH` and `EQUAL_LOW` are first-class members, never folded into the
    others. A retest at exactly the previous level is its own structural fact,
    and calling it "double top", "resistance", or "liquidity" would be an
    interpretation belonging to a later layer.

    Deliberately absent: BULLISH, BEARISH, CONTINUATION, REVERSAL, BREAK, BOS,
    CHOCH, LONG, SHORT, BUY, SELL, STRONG, WEAK, CONFIRMED, INVALID.
    """

    HIGHER_HIGH = "higher_high"
    LOWER_HIGH = "lower_high"
    EQUAL_HIGH = "equal_high"
    HIGHER_LOW = "higher_low"
    LOWER_LOW = "lower_low"
    EQUAL_LOW = "equal_low"


#: The one authoritative mapping from (swing type, relation) to its name.
#: Exhaustive over both enums by construction; an immutable mapping so the
#: vocabulary cannot be re-pointed at runtime.
_LABEL_BY_TYPE_AND_RELATION: Mapping[
    tuple[SwingType, SwingRelation], StructuralSwingLabel
] = MappingProxyType(
    {
        (SwingType.HIGH, SwingRelation.HIGHER): StructuralSwingLabel.HIGHER_HIGH,
        (SwingType.HIGH, SwingRelation.LOWER): StructuralSwingLabel.LOWER_HIGH,
        (SwingType.HIGH, SwingRelation.EQUAL): StructuralSwingLabel.EQUAL_HIGH,
        (SwingType.LOW, SwingRelation.HIGHER): StructuralSwingLabel.HIGHER_LOW,
        (SwingType.LOW, SwingRelation.LOWER): StructuralSwingLabel.LOWER_LOW,
        (SwingType.LOW, SwingRelation.EQUAL): StructuralSwingLabel.EQUAL_LOW,
    }
)


def _label_for(comparison: SwingComparison) -> StructuralSwingLabel:
    """The label implied by a comparison — the one authoritative derivation.

    Reads ``comparison.current.type`` and ``comparison.relation``. The previous
    point's type is deliberately not consulted: `SwingComparison` already
    guarantees both points share a type, so checking it again would invite the
    two sources disagreeing.

    Deliberately **private**, following `_relation_for`. A public
    ``label_for(type, relation)`` would let a caller name a pairing that no
    validated `SwingComparison` produced, which is the same shortcut-around-the-
    invariants hazard ADR-0013 §6 removed. Callers use `label_swing`.
    """
    return _LABEL_BY_TYPE_AND_RELATION[(comparison.current.type, comparison.relation)]


@dataclass(frozen=True, slots=True)
class StructuralSwing:
    """A `SwingComparison` and its conventional name. Exactly two fields.

    ``comparison`` carries every underlying fact — both points, their indices,
    timestamps and prices, and the relation — so none of it is repeated here.
    Duplicating ``current``, ``price`` or ``index`` as extra fields would create
    a second place for them to disagree.

    ``label`` is **validated against the comparison**, not trusted: an object
    claiming `HIGHER_HIGH` for a low that fell cannot be constructed.

    Frozen, slotted and hashable, so a label cannot drift and can go in a set
    when a later layer diffs runs.
    """

    comparison: SwingComparison
    label: StructuralSwingLabel

    def __post_init__(self) -> None:
        if not isinstance(self.comparison, SwingComparison):
            raise TypeError(
                "comparison must be a SwingComparison, got "
                f"{type(self.comparison).__name__}"
            )
        if not isinstance(self.label, StructuralSwingLabel):
            raise TypeError(
                "label must be a StructuralSwingLabel, got "
                f"{type(self.label).__name__}"
            )
        expected = _label_for(self.comparison)
        if self.label is not expected:
            raise ValueError(
                f"label {self.label.value!r} does not match the comparison "
                f"({self.comparison.current.type.value} + "
                f"{self.comparison.relation.value}); expected {expected.value!r}"
            )


def _validate_key_order(
    keys: Sequence[tuple[int, datetime, SwingType]],
    *,
    subject: str,
    index_noun: str,
    timestamp_noun: str,
    element_noun: str,
) -> None:
    """The one authoritative sequence-ordering rule, over normalised keys.

    A key is ``(index, timestamp, type)``. Every layer that consumes an ordered
    structural run projects its own elements onto keys and calls this, so the rule
    has exactly one implementation and cannot drift between layers. The rule:

      * ``index`` is **non-decreasing** across the whole run;
      * ``timestamp`` is non-decreasing with it;
      * keys sharing an ``index`` share its timestamp;
      * within each `SwingType`, index and timestamp are **strictly** increasing.

    Global strictness is deliberately not required: one outside candle produces a
    HIGH and a LOW at the same index, so a run legitimately contains two keys
    sharing an index. Per-type strictness is what matters, and it is also what
    rejects a duplicated element.

    Order is validated, never repaired, and the relative order of two keys at an
    equal index is whatever the input had — this rule imposes no HIGH-before-LOW
    convention of its own.

    Deliberately **private**. The four noun arguments exist because the two
    original implementations shipped with different wording, and the messages are
    a contract: `compare_swing_sequence` says "points … index … point" while
    `label_swing_sequence` says "comparisons … current index … comparison". Both
    are reproduced **byte-for-byte** by substituting nouns and nothing else.

    ``index_noun`` and ``timestamp_noun`` are passed separately rather than
    derived from one another. Deriving "current timestamp" from "current index" by
    string manipulation would put the message contract at the mercy of a
    transformation, and a reworded message is exactly the regression that slipped
    past substring assertions in the structural-label milestone.

    Args:
        keys: the run to check, already materialised in input order.
        subject: the caller's parameter name, used in error text.
        index_noun: how the caller names an index ("index" / "current index").
        timestamp_noun: how the caller names a timestamp.
        element_noun: how the caller names one element ("point" / "comparison").

    Raises:
        ValueError: the run is not ordered.
    """
    latest: dict[SwingType, tuple[int, datetime]] = {}

    for position, (index, timestamp, type) in enumerate(keys):
        if position > 0:
            earlier_index, earlier_timestamp, _ = keys[position - 1]
            if index < earlier_index:
                raise ValueError(
                    f"{subject} must be ordered by {index_noun}; "
                    f"{subject}[{position}] has index {index} after "
                    f"{earlier_index}"
                )
            if timestamp < earlier_timestamp:
                raise ValueError(
                    f"{subject} must be ordered by {timestamp_noun}; "
                    f"{subject}[{position}] has "
                    f"{timestamp.isoformat()} after "
                    f"{earlier_timestamp.isoformat()}"
                )
            # Two keys may share an index only when both came from one candle, in
            # which case they share its timestamp too.
            shared_index = index == earlier_index
            if shared_index and timestamp != earlier_timestamp:
                raise ValueError(
                    f"{subject}[{position}] shares {index_noun} "
                    f"{index} with the previous {element_noun} but carries "
                    "a different timestamp"
                )

        previous = latest.get(type)
        if previous is not None:
            # Strict within a type: one candle cannot yield two elements of the
            # same type, so a repeat here — including an identical object — is a
            # real inconsistency.
            previous_index, previous_timestamp = previous
            if index <= previous_index:
                raise ValueError(
                    f"{subject}[{position}] repeats or precedes {index_noun} "
                    f"{previous_index} for swing type "
                    f"{type.value!r}"
                )
            if timestamp <= previous_timestamp:
                raise ValueError(
                    f"{subject}[{position}] repeats or precedes {timestamp_noun} "
                    f"{previous_timestamp.isoformat()} for "
                    f"swing type {type.value!r}"
                )
        latest[type] = (index, timestamp)


def _validate_current_point_order(
    comparisons: Sequence[SwingComparison], subject: str
) -> None:
    """Ordering rule for a run of comparisons — a thin adapter over `_validate_key_order`.

    Projects each comparison onto its ``current`` point's key and delegates. The
    rule itself lives in one place; this function exists to name the "current
    point" projection and to fix this layer's message vocabulary.

    Checked on each comparison's ``current`` point:

      * ``current.index`` is **non-decreasing** across the whole run;
      * ``current.timestamp`` is non-decreasing with it;
      * comparisons sharing a ``current.index`` share its timestamp;
      * within each `SwingType`, index and timestamp are **strictly** increasing.

    Global strictness is deliberately not required: one outside candle produces a
    HIGH and a LOW at the same index, so `compare_swing_sequence` legitimately
    emits two comparisons sharing a ``current.index``. Per-type strictness is what
    matters, and it is also what rejects a duplicated comparison.

    Order is validated, never repaired, and the relative order of two comparisons
    at an equal index is whatever the input had — this rule imposes no
    HIGH-before-LOW convention of its own.

    Deliberately **private**. ``subject`` names the caller's parameter in error
    messages so the message points at the argument the caller actually passed;
    every other word of those messages is fixed, because `label_swing_sequence`
    shipped with this exact wording and extracting the rule must not reword its
    output. The noun "comparison" stays correct for every caller: whatever a
    caller holds, it is a run of `SwingComparison` objects that arrives here.

    Args:
        comparisons: the run to check, already materialised in input order.
        subject: the caller's parameter name, used in error text.

    Raises:
        ValueError: the run is not ordered.
    """
    _validate_key_order(
        [
            (
                comparison.current.index,
                comparison.current.timestamp,
                comparison.current.type,
            )
            for comparison in comparisons
        ],
        subject=subject,
        index_noun="current index",
        timestamp_noun="current timestamp",
        element_noun="comparison",
    )


class StructuralSequenceStateType(str, Enum):
    """How the latest HIGH-side and latest LOW-side labels stand together.

    Six members partitioning the nine complete label combinations, plus one
    member for an incomplete pair. Each describes **numeric movement of two
    already-established facts** and nothing else.

    The partition is built from one idea: each side has moved *outward* from its
    own previous swing, *inward*, or not at all. `HIGHER_HIGH` and `LOWER_LOW`
    are outward, `LOWER_HIGH` and `HIGHER_LOW` are inward, `EQUAL_HIGH` and
    `EQUAL_LOW` are static. That covers all nine cells with no overlap and no
    leftovers, which is why there is no `MIXED` member — a dumping ground would
    mean the partition was incomplete.

      * `SHIFTED_HIGHER` — both sides moved to higher prices (one outward, one
        inward). It does **not** mean uptrend, bullish, strong, or continuation.
      * `SHIFTED_LOWER` — both sides moved to lower prices. Not bearish, not a
        reversal, not weakness.
      * `EXPANDED` — one or both sides moved outward and neither moved inward.
        Not a breakout, not volatility, not a range break.
      * `CONTRACTED` — one or both sides moved inward and neither moved outward.
        Not consolidation, not compression, not a squeeze.
      * `UNCHANGED` — neither side moved: `EQUAL_HIGH` with `EQUAL_LOW`. Not a
        double top, not a double bottom, not support, resistance or liquidity.
      * `INSUFFICIENT_STRUCTURE` — no labelled swing on one side or on either.
        See `StructuralSequenceState`.

    "Expanded" and "contracted" describe the two sides' movement, not a measured
    width. The HIGH side is compared to the previous HIGH and the LOW side to the
    previous LOW, and those two baselines are independent and generally from
    different candles, so this layer never computes or claims a range size — it
    reads no price at all.

    Deliberately absent: BULLISH, BEARISH, UPTREND, DOWNTREND, LONG, SHORT, BUY,
    SELL, CONTINUATION, REVERSAL, BREAKOUT, BOS, CHOCH, STRONG, WEAK, CONFIRMED,
    and anything carrying confidence, score or ranking.
    """

    SHIFTED_HIGHER = "shifted_higher"
    SHIFTED_LOWER = "shifted_lower"
    EXPANDED = "expanded"
    CONTRACTED = "contracted"
    UNCHANGED = "unchanged"
    INSUFFICIENT_STRUCTURE = "insufficient_structure"


#: The one authoritative mapping from (latest HIGH label, latest LOW label) to
#: its state. Exhaustive over the nine complete combinations by construction; an
#: immutable mapping so the classification cannot be re-pointed at runtime.
#: Written out cell by cell rather than derived, so that reading it is the same
#: as reading the ADR's matrix.
_STATE_BY_LABEL_PAIR: Mapping[
    tuple[StructuralSwingLabel, StructuralSwingLabel], StructuralSequenceStateType
] = MappingProxyType(
    {
        # both sides moved to higher prices
        (
            StructuralSwingLabel.HIGHER_HIGH,
            StructuralSwingLabel.HIGHER_LOW,
        ): StructuralSequenceStateType.SHIFTED_HIGHER,
        # both sides moved to lower prices
        (
            StructuralSwingLabel.LOWER_HIGH,
            StructuralSwingLabel.LOWER_LOW,
        ): StructuralSequenceStateType.SHIFTED_LOWER,
        # outward on one or both sides, inward on neither
        (
            StructuralSwingLabel.HIGHER_HIGH,
            StructuralSwingLabel.LOWER_LOW,
        ): StructuralSequenceStateType.EXPANDED,
        (
            StructuralSwingLabel.HIGHER_HIGH,
            StructuralSwingLabel.EQUAL_LOW,
        ): StructuralSequenceStateType.EXPANDED,
        (
            StructuralSwingLabel.EQUAL_HIGH,
            StructuralSwingLabel.LOWER_LOW,
        ): StructuralSequenceStateType.EXPANDED,
        # inward on one or both sides, outward on neither
        (
            StructuralSwingLabel.LOWER_HIGH,
            StructuralSwingLabel.HIGHER_LOW,
        ): StructuralSequenceStateType.CONTRACTED,
        (
            StructuralSwingLabel.LOWER_HIGH,
            StructuralSwingLabel.EQUAL_LOW,
        ): StructuralSequenceStateType.CONTRACTED,
        (
            StructuralSwingLabel.EQUAL_HIGH,
            StructuralSwingLabel.HIGHER_LOW,
        ): StructuralSequenceStateType.CONTRACTED,
        # neither side moved
        (
            StructuralSwingLabel.EQUAL_HIGH,
            StructuralSwingLabel.EQUAL_LOW,
        ): StructuralSequenceStateType.UNCHANGED,
    }
)


def _sequence_state_for(
    latest_high: "StructuralSwing | None", latest_low: "StructuralSwing | None"
) -> StructuralSequenceStateType:
    """The state implied by the two latest sides — the one authoritative rule.

    Either side missing gives `INSUFFICIENT_STRUCTURE`: a state is a statement
    about *both* sides, and inventing one from a single side would be fabricating
    the half that is not there. Which half is missing stays visible on the
    `StructuralSequenceState` itself, so no extra enum member is needed to say it.

    Deliberately **private**, following `_relation_for` and `_label_for`. A public
    ``state_for(high_label, low_label)`` would let a caller classify a pairing
    that no validated pair of `StructuralSwing` objects produced.
    """
    if latest_high is None or latest_low is None:
        return StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
    return _STATE_BY_LABEL_PAIR[(latest_high.label, latest_low.label)]


@dataclass(frozen=True, slots=True)
class StructuralSequenceState:
    """The latest HIGH-side and LOW-side structural facts, and their state.

    Exactly three fields. ``latest_high`` and ``latest_low`` are the two source
    `StructuralSwing` objects — kept whole, so every underlying fact (both
    points, their indices, timestamps and prices, the relation, the label) stays
    reachable and none of it is copied here. Either may be ``None`` when no swing
    of that side has been labelled yet.

    ``state`` is **validated against those two sides**, not trusted: an object
    claiming `EXPANDED` for a pair that contracted cannot be constructed, and
    neither can one claiming a complete state with a side missing.

    The state groups the nine complete combinations into five, so it is
    deliberately lossy — which is exactly why both sides are retained. A consumer
    that needs to tell `HIGHER_HIGH` + `EQUAL_LOW` from `HIGHER_HIGH` +
    `LOWER_LOW` reads ``latest_high.label`` and ``latest_low.label`` and gets the
    exact pair back.

    Unlike a `StructuralSwing`, which is settled forever once emitted, an
    instance of this type describes *the latest known pair* and is expected to be
    superseded when a newer swing on either side is confirmed. The object itself
    is still immutable; a later call simply returns a different one. See ADR-0015.

    Frozen, slotted and hashable, matching every other value type here.
    """

    latest_high: "StructuralSwing | None"
    latest_low: "StructuralSwing | None"
    state: StructuralSequenceStateType

    def __post_init__(self) -> None:
        for name, value, side in (
            ("latest_high", self.latest_high, SwingType.HIGH),
            ("latest_low", self.latest_low, SwingType.LOW),
        ):
            if value is None:
                continue
            if not isinstance(value, StructuralSwing):
                raise TypeError(
                    f"{name} must be a StructuralSwing or None, got "
                    f"{type(value).__name__}"
                )
            if value.comparison.current.type is not side:
                raise ValueError(
                    f"{name} must hold a {side.value!r} swing, got "
                    f"{value.comparison.current.type.value!r}"
                )
        if not isinstance(self.state, StructuralSequenceStateType):
            raise TypeError(
                "state must be a StructuralSequenceStateType, got "
                f"{type(self.state).__name__}"
            )
        expected = _sequence_state_for(self.latest_high, self.latest_low)
        if self.state is not expected:
            raise ValueError(
                f"state {self.state.value!r} does not match the latest sides; "
                f"expected {expected.value!r}"
            )


@dataclass(frozen=True, slots=True)
class StructuralSequenceStateSnapshot:
    """The structural sequence state at one candle, and the swings that set it.

    A `StructuralSequenceState` describes the *latest* pair and is superseded as
    newer swings confirm (ADR-0015 §8). A snapshot fixes one such state to the
    candle that produced it, so a run of snapshots is a sequence of **historical
    facts** rather than a value that keeps changing. See ADR-0016.

    Exactly two fields.

    ``state`` is the complete aggregate, reused whole rather than flattened.
    `StructuralSequenceState` already validates that its own three fields agree,
    so copying ``latest_high`` / ``latest_low`` / ``state`` up here would create a
    second place for them to disagree — the hazard ADR-0014 §5 removed.

    ``triggers`` are the `StructuralSwing` objects **confirmed at this candle**:
    one normally, two when an outside bar produced both a HIGH and a LOW. They
    are what changed, as opposed to ``state.latest_high`` / ``latest_low``, which
    may have been carried forward from an earlier snapshot. Both orders of an
    outside-bar pair are accepted and preserved; this type imposes no
    HIGH-before-LOW convention, matching ADR-0014 §8.

    ``index`` and ``timestamp`` are **computed projections, not fields**. Every
    trigger in a group shares them by construction, so storing them would
    duplicate a derived fact.

    Deliberately absent: any transition classification, any "changed" flag, any
    direction, magnitude, duration, strength, confidence or score. Whether one
    snapshot following another is meaningful is a reading, and it belongs to a
    later layer that can state its conditions. A consumer comparing
    ``history[i - 1].state.state`` with ``history[i].state.state`` already has
    every fact such a layer would need.

    Frozen, slotted and hashable, matching every other value type here.
    """

    state: StructuralSequenceState
    triggers: tuple[StructuralSwing, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.state, StructuralSequenceState):
            raise TypeError(
                "state must be a StructuralSequenceState, got "
                f"{type(self.state).__name__}"
            )
        if not isinstance(self.triggers, tuple):
            raise TypeError(
                f"triggers must be a tuple, got {type(self.triggers).__name__}"
            )
        for position, trigger in enumerate(self.triggers):
            if not isinstance(trigger, StructuralSwing):
                raise TypeError(
                    f"triggers[{position}] must be a StructuralSwing, got "
                    f"{type(trigger).__name__}"
                )
        if not 1 <= len(self.triggers) <= 2:
            raise ValueError(
                "triggers must hold one swing, or two when one candle produced "
                f"both a high and a low; got {len(self.triggers)}"
            )

        first = self.triggers[0].comparison.current
        types = [trigger.comparison.current.type for trigger in self.triggers]
        if len(set(types)) != len(types):
            raise ValueError(
                "triggers must have distinct swing types; got "
                f"{[type.value for type in types]}"
            )
        for position, trigger in enumerate(self.triggers[1:], start=1):
            current = trigger.comparison.current
            if current.index != first.index:
                raise ValueError(
                    f"triggers[{position}] has index {current.index}, but a "
                    f"snapshot covers one candle; expected {first.index}"
                )
            if current.timestamp != first.timestamp:
                raise ValueError(
                    f"triggers[{position}] has timestamp "
                    f"{current.timestamp.isoformat()}, but a snapshot covers one "
                    f"candle; expected {first.timestamp.isoformat()}"
                )

        # Each trigger must be the state's own latest side. This is what makes a
        # snapshot a coherent fact rather than a state and an unrelated cause
        # stapled together, and it is checked by identity: the state must hold
        # the very object that triggered it, not an equal one.
        for trigger in self.triggers:
            side = trigger.comparison.current.type
            held = (
                self.state.latest_high
                if side is SwingType.HIGH
                else self.state.latest_low
            )
            if held is not trigger:
                raise ValueError(
                    f"the {side.value!r} trigger is not the state's latest "
                    f"{side.value} swing; a snapshot's triggers must be the "
                    "sides the state itself holds"
                )

    @property
    def index(self) -> int:
        """The closed-candle index this snapshot describes.

        A projection of ``triggers[0].comparison.current.index``, not stored.
        Every trigger shares it, enforced on construction.
        """
        return self.triggers[0].comparison.current.index

    @property
    def timestamp(self) -> datetime:
        """The timestamp of the candle this snapshot describes.

        A projection of ``triggers[0].comparison.current.timestamp``, not stored.
        """
        return self.triggers[0].comparison.current.timestamp
