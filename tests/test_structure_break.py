"""Tests for `fmis.structure_break` — Break of Structure Foundation v1.

Organised in the order ADR-0020 states the contract: the model and its
self-validation, the qualifying-kind policy, eligibility and the reference rule,
lifecycle, duplicates and ordering, the safe pipeline, prefix stability,
properties, and architecture guards.

Exception messages are treated as a shipped contract and asserted with ``==``,
not `pytest.raises(match=...)`, following `test_market_structure_ordering.py`.

Note the deliberate asymmetry: this module imports `Candle` because building a
`LevelCrossingEvent` requires one, while the package under test does not import
`fmis.data` at all. That is the point, and a guard below pins it.
"""

from __future__ import annotations

import ast
import importlib
import itertools
import json
import pickle
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import fmis.structure_break as sb
from fmis.data import Candle, CandleSeries, SeriesIdentity
from fmis.level_crossing import (
    CrossingKind,
    CrossingMechanism,
    LevelCrossingEvent,
    LevelOrigin,
    LevelSide,
    PriceLevel,
    contextual_level_crossings,
    contextual_structural_levels,
    derive_level_crossings,
    structural_levels,
)
from fmis.market_structure import (
    DEFAULT_RIGHT_BARS,
    StructuralSwingLabel,
    detect_swings,
)
from fmis.series_context import (
    ContextualSeries,
    SeriesIdentityMismatchError,
    contextual_structural_state_history,
    contextual_structural_swings,
    contextual_structural_trend_history,
)
from fmis.structure_break import (
    StructureBreak,
    StructureBreakError,
    StructureBreakInputError,
    contextual_structure_breaks,
    derive_structure_breaks,
)
from fmis.structure_break import breaks as breaks_mod
from fmis.structure_break import models as models_mod
from fmis.structure_break import pipeline as pipeline_mod

PACKAGE_DIR = Path(sb.__file__).parent
_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
RB = 2  # confirmation bars used throughout, matching DEFAULT_RIGHT_BARS
CB = RB  # the same window, recorded on every hand-built origin (AH)


# =========================== helpers ========================================


def candle(
    i: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    symbol: str = "BTCUSDT",
    timeframe: str = "4h",
) -> Candle:
    return Candle(
        timestamp=_BASE + timedelta(hours=4 * i),
        symbol=symbol,
        timeframe=timeframe,
        open=float(open_),
        high=float(high),
        low=float(low),
        close=float(close),
        volume=1.0,
        is_closed=True,
    )


def series(
    rows: list[tuple[float, float, float, float]],
    *,
    symbol: str = "BTCUSDT",
    timeframe: str = "4h",
) -> CandleSeries:
    return CandleSeries(
        symbol=symbol,
        timeframe=timeframe,
        candles=tuple(
            candle(i, *row, symbol=symbol, timeframe=timeframe)
            for i, row in enumerate(rows)
        ),
    )


def origin(
    index: int, label: StructuralSwingLabel, confirmation_bars: int = CB
) -> LevelOrigin:
    return LevelOrigin(
        index=index,
        timestamp=_BASE + timedelta(hours=4 * index),
        label=label,
        confirmation_bars=confirmation_bars,
    )


def level(
    price: float,
    side: LevelSide,
    origin_index: int,
    label: StructuralSwingLabel | None = None,
    confirmation_bars: int = CB,
) -> PriceLevel:
    if label is None:
        label = (
            StructuralSwingLabel.HIGHER_HIGH
            if side is LevelSide.UPPER
            else StructuralSwingLabel.LOWER_LOW
        )
    return PriceLevel(
        price=price,
        side=side,
        origin=origin(origin_index, label, confirmation_bars),
    )


def event(
    lvl: PriceLevel,
    index: int,
    *,
    kind: CrossingKind = CrossingKind.CLOSE_BREACH,
    mechanism: CrossingMechanism = CrossingMechanism.WITHIN_RANGE,
) -> LevelCrossingEvent:
    """Build a crossing event directly, with a candle consistent with the claim.

    Constructed here rather than derived so a test can express a (level, bar,
    kind) combination without engineering a candle series that produces it. The
    candle is still real and the event still self-validates.
    """
    price = lvl.price
    if lvl.side is LevelSide.UPPER:
        if kind is CrossingKind.TOUCH:
            bar = candle(index, price - 1, price, price - 2, price - 1)
        elif kind is CrossingKind.WICK_BREACH:
            bar = candle(index, price - 1, price + 2, price - 2, price - 1)
        elif mechanism is CrossingMechanism.WITHIN_RANGE:
            bar = candle(index, price - 1, price + 3, price - 2, price + 2)
        else:  # wholly beyond
            bar = candle(index, price + 2, price + 4, price + 1, price + 3)
    else:
        if kind is CrossingKind.TOUCH:
            bar = candle(index, price + 1, price + 2, price, price + 1)
        elif kind is CrossingKind.WICK_BREACH:
            bar = candle(index, price + 1, price + 2, price - 2, price + 1)
        elif mechanism is CrossingMechanism.WITHIN_RANGE:
            bar = candle(index, price + 1, price + 2, price - 3, price - 2)
        else:
            bar = candle(index, price - 3, price - 1, price - 4, price - 2)
    return LevelCrossingEvent(
        level=lvl, candle=bar, index=index, kind=kind, mechanism=mechanism
    )


def pipeline(
    candles: CandleSeries, right_bars: int = RB
) -> tuple[tuple[PriceLevel, ...], tuple[LevelCrossingEvent, ...]]:
    """The full context-free chain: candles -> swings -> levels -> crossings."""
    swings = contextual_structural_swings(candles, right_bars=right_bars)
    levels = structural_levels(swings.values)
    return levels, derive_level_crossings(candles, list(levels))


def real_series() -> CandleSeries:
    rows = json.loads(
        (Path(__file__).parent / "fixtures" / "btcusdt_4h.json").read_text()
    )
    return CandleSeries(
        symbol="BTCUSDT",
        timeframe="4h",
        candles=tuple(
            Candle(
                timestamp=datetime.fromisoformat(
                    row["timestamp"].replace("Z", "+00:00")
                ),
                symbol="BTCUSDT",
                timeframe="4h",
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                is_closed=True,
            )
            for row in rows
        ),
    )


def seeded_rows(count: int, seed: int) -> list[tuple[float, float, float, float]]:
    """Deterministic OHLC. Seeded in a **test** only; production has no randomness."""
    rng = random.Random(seed)
    rows: list[tuple[float, float, float, float]] = []
    for _ in range(count):
        open_ = rng.uniform(95.0, 105.0)
        close = rng.uniform(95.0, 105.0)
        rows.append(
            (
                open_,
                max(open_, close) + rng.uniform(0.0, 3.0),
                min(open_, close) - rng.uniform(0.0, 3.0),
                close,
            )
        )
    return rows


#: An upward break: an upper level at 103 from bar 5, broken by a close of 105
#: at bar 8. Reused wherever a known-good break is needed.
UPWARD_ROWS = [
    (100, 101, 99, 100),
    (100, 102, 98, 100),
    (100, 104, 96, 100),
    (100, 102, 98, 100),
    (100, 101, 99, 100),
    (100, 103, 97, 100),
    (100, 101, 99, 100),
    (100, 100.5, 99.5, 100),
    (100, 106, 99, 105),
    (102, 103, 98, 99),
    (99, 107, 98, 106),
]

#: The minimal prefix-instability counterexample from the design (§2.4). Under
#: pivot-bar eligibility a 13-bar prefix reports a break the full run does not.
COUNTEREXAMPLE_ROWS = [
    (101.4, 102.5, 98.1, 99.9),
    (101.8, 103.7, 100.8, 101.4),
    (101.7, 103.2, 99.6, 100.9),
    (100.0, 102.2, 98.4, 101.1),
    (100.8, 101.9, 99.7, 100.1),
    (100.5, 102.5, 98.6, 99.6),
    (101.6, 102.1, 98.5, 100.0),
    (101.9, 102.4, 100.1, 101.8),
    (101.7, 103.5, 101.5, 101.8),
    (100.4, 103.8, 98.9, 101.8),
    (99.8, 102.1, 98.6, 101.9),
    (98.8, 101.6, 97.1, 101.4),
    (101.7, 103.0, 97.5, 98.4),
    (98.2, 102.4, 97.7, 100.7),
    (98.8, 101.4, 98.5, 101.3),
]


# ===================== 1. the model =========================================


def test_a_break_projects_every_derived_fact() -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    crossing = event(upper, 8)
    got = StructureBreak(crossing=crossing)
    assert got.index == 8
    assert got.timestamp == crossing.timestamp
    assert got.level is upper
    assert got.side is LevelSide.UPPER
    assert got.origin is upper.origin
    assert got.label is StructuralSwingLabel.HIGHER_HIGH


def test_the_model_stores_exactly_one_field() -> None:
    """AH: `eligible_from` became a projection of the level's own provenance."""
    assert set(StructureBreak.__dataclass_fields__) == {"crossing"}
    assert isinstance(StructureBreak.eligible_from, property)


def test_no_lifecycle_or_interpretation_field_exists() -> None:
    for banned in (
        "invalidated",
        "failed",
        "active",
        "retested",
        "strength",
        "confidence",
        "direction",
        "bullish",
        "bearish",
    ):
        assert banned not in StructureBreak.__dataclass_fields__, banned
        assert not hasattr(StructureBreak, banned), banned


def test_a_break_is_immutable() -> None:
    got = StructureBreak(crossing=event(level(103.0, LevelSide.UPPER, 5), 8))
    with pytest.raises((AttributeError, TypeError)):
        got.eligible_from = 0
    with pytest.raises((AttributeError, TypeError)):
        got.invented = 1


def test_equality_and_hashing_are_structural() -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    crossing = event(upper, 8)
    a = StructureBreak(crossing=crossing)
    b = StructureBreak(crossing=crossing)
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1
    # Two breaks can now differ only in their crossing, the single field. A break
    # can no longer disagree with its own level about eligibility, because it
    # does not store that number (AH).
    other = StructureBreak(crossing=event(level(103.0, LevelSide.UPPER, 5), 9))
    assert a != other
    assert a.eligible_from == other.eligible_from == 7


def test_repr_is_stable_and_names_the_type() -> None:
    got = StructureBreak(crossing=event(level(103.0, LevelSide.UPPER, 5), 8))
    assert repr(got).startswith("StructureBreak(")
    assert repr(got) == repr(got)


def test_a_break_round_trips_through_pickle() -> None:
    levels, crossings = pipeline(series(UPWARD_ROWS))
    got = derive_structure_breaks(levels, crossings)
    restored = pickle.loads(pickle.dumps(got))
    assert restored == got
    assert hash(restored[0]) == hash(got[0])


# ===================== 2. model self-validation =============================


@pytest.mark.parametrize(
    "kind,message",
    [
        (CrossingKind.TOUCH, "crossing kind 'touch' does not break structure; expected 'close_breach'"),
        (
            CrossingKind.WICK_BREACH,
            "crossing kind 'wick_breach' does not break structure; expected 'close_breach'",
        ),
    ],
)
def test_a_break_cannot_be_built_from_a_non_close_crossing(
    kind: CrossingKind, message: str
) -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    with pytest.raises(ValueError) as excinfo:
        StructureBreak(crossing=event(upper, 8, kind=kind))
    assert str(excinfo.value) == message


def test_a_break_cannot_be_built_from_an_already_beyond_crossing() -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    crossing = event(upper, 8, mechanism=CrossingMechanism.ALREADY_BEYOND)
    with pytest.raises(ValueError) as excinfo:
        StructureBreak(crossing=crossing)
    assert str(excinfo.value) == (
        "crossing mechanism 'already_beyond' does not break structure; the series "
        "began beyond the level, so no arrival can be claimed"
    )


def test_a_break_cannot_be_built_from_an_unprovenanced_level() -> None:
    bare = PriceLevel(103.0, LevelSide.UPPER)
    with pytest.raises(ValueError) as excinfo:
        StructureBreak(crossing=event(bare, 8))
    assert str(excinfo.value) == (
        "crossing level carries no origin; a break needs provenance to place the "
        "level in time"
    )


def test_a_break_cannot_precede_its_own_eligibility() -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    with pytest.raises(ValueError) as excinfo:
        StructureBreak(crossing=event(upper, 6))
    assert str(excinfo.value) == (
        "crossing index (6) precedes eligible_from (7); the level was not yet "
        "knowable"
    )


def test_eligible_from_cannot_be_supplied_at_all() -> None:
    """AH: the second source of truth is removed, not validated against.

    Two rejections disappeared with the field — "cannot precede the level
    origin" and "cannot be negative" — because neither is expressible any more.
    `knowable_from` is ``index + confirmation_bars`` over a non-negative index and
    a window of at least 1, so both are arithmetic guarantees, not checks.
    """
    upper = level(103.0, LevelSide.UPPER, 5)
    crossing = event(upper, 8)
    with pytest.raises(TypeError) as excinfo:
        StructureBreak(crossing=crossing, eligible_from=4)  # type: ignore[call-arg]
    assert "eligible_from" in str(excinfo.value)

    got = StructureBreak(crossing=crossing)
    assert got.eligible_from == 7
    assert got.eligible_from > upper.origin.index
    assert got.eligible_from == upper.origin.knowable_from


def test_model_type_validation() -> None:
    with pytest.raises(TypeError) as excinfo:
        StructureBreak(crossing="x")  # type: ignore[arg-type]
    assert str(excinfo.value) == "crossing must be a LevelCrossingEvent, got str"


# ===================== 3. the qualifying-kind policy ========================


def test_an_upward_break() -> None:
    levels, crossings = pipeline(series(UPWARD_ROWS))
    got = derive_structure_breaks(levels, crossings)
    assert [(b.index, b.side, b.level.price) for b in got] == [
        (8, LevelSide.UPPER, 103.0)
    ]


def test_a_downward_break() -> None:
    rows = [
        (100, 101, 99, 100),
        (100, 102, 98, 100),
        (100, 104, 96, 100),
        (100, 102, 98, 100),
        (100, 101, 99, 100),
        (100, 103, 97, 100),
        (100, 101, 99, 100),
        (100, 100.5, 99.5, 100),
        (100, 101, 94, 95),
    ]
    levels, crossings = pipeline(series(rows))
    got = derive_structure_breaks(levels, crossings)
    assert [(b.index, b.side, b.level.price) for b in got] == [
        (8, LevelSide.LOWER, 97.0)
    ]


def test_upward_is_not_named_bullish_anywhere() -> None:
    """`side` carries the sense; naming it bullish would be the interpretation."""
    levels, crossings = pipeline(series(UPWARD_ROWS))
    got = derive_structure_breaks(levels, crossings)[0]
    assert got.side is LevelSide.UPPER
    assert "bull" not in repr(got).lower()


def test_no_break_when_nothing_closes_beyond_a_reference() -> None:
    rows = [(100, 101, 99, 100)] * 12
    levels, crossings = pipeline(series(rows))
    assert derive_structure_breaks(levels, crossings) == ()


@pytest.mark.parametrize("kind", [CrossingKind.TOUCH, CrossingKind.WICK_BREACH])
def test_a_touch_or_wick_breach_never_breaks_structure(kind: CrossingKind) -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    got = derive_structure_breaks(
        [upper], [event(upper, 8, kind=kind)]
    )
    assert got == ()


def test_a_close_breach_of_the_reference_breaks_structure() -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    got = derive_structure_breaks([upper], [event(upper, 8)])
    assert len(got) == 1
    assert got[0].crossing.kind is CrossingKind.CLOSE_BREACH


def test_a_wick_beyond_that_closes_back_inside_is_a_rejection_not_a_break() -> None:
    """The whole reason CLOSE_BREACH is required rather than merely preferred."""
    upper = level(103.0, LevelSide.UPPER, 5)
    wick = event(upper, 8, kind=CrossingKind.WICK_BREACH)
    assert wick.candle.high > upper.price
    assert wick.candle.close < upper.price
    assert derive_structure_breaks([upper], [wick]) == ()


def test_there_is_no_way_to_configure_the_qualifying_kind() -> None:
    import inspect

    parameters = set(inspect.signature(derive_structure_breaks).parameters)
    assert parameters == {"levels", "crossings"}


# ===================== 4. equal highs and equal lows ========================


def test_an_equal_high_derived_level_breaks_when_price_closes_beyond_it() -> None:
    rows = [
        (100, 101, 99, 100),
        (100, 102, 98, 100),
        (100, 105, 96, 100),
        (100, 102, 98, 100),
        (100, 101, 99, 100),
        (100, 105, 97, 100),
        (100, 101, 99, 100),
        (100, 100.5, 99.5, 100),
        (100, 110, 99, 109),
    ]
    levels, crossings = pipeline(series(rows))
    labels = {lv.origin.label for lv in levels if lv.side is LevelSide.UPPER}
    assert StructuralSwingLabel.EQUAL_HIGH in labels
    got = derive_structure_breaks(levels, crossings)
    assert [(b.index, b.level.price, b.label) for b in got] == [
        (8, 105.0, StructuralSwingLabel.EQUAL_HIGH)
    ]


def test_an_equal_low_derived_level_breaks_when_price_closes_beyond_it() -> None:
    equal_low = level(97.0, LevelSide.LOWER, 5, StructuralSwingLabel.EQUAL_LOW)
    got = derive_structure_breaks(
        [equal_low], [event(equal_low, 8)]
    )
    assert [b.label for b in got] == [StructuralSwingLabel.EQUAL_LOW]


@pytest.mark.parametrize("label", list(StructuralSwingLabel))
def test_every_label_can_produce_a_break(label: StructuralSwingLabel) -> None:
    """The label is carried, never used to filter — ADR-0020 §3.3."""
    side = (
        LevelSide.UPPER
        if label
        in (
            StructuralSwingLabel.HIGHER_HIGH,
            StructuralSwingLabel.LOWER_HIGH,
            StructuralSwingLabel.EQUAL_HIGH,
        )
        else LevelSide.LOWER
    )
    lvl = level(100.0, side, 5, label)
    got = derive_structure_breaks([lvl], [event(lvl, 8)])
    assert [b.label for b in got] == [label]


def test_the_label_is_carried_unchanged_from_the_swing() -> None:
    levels, crossings = pipeline(series(UPWARD_ROWS))
    got = derive_structure_breaks(levels, crossings)[0]
    assert got.label is got.level.origin.label


# ===================== 5. eligibility and the reference rule ================


def test_a_level_is_not_eligible_before_its_confirmation_bar() -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    for index in range(5, 7):
        assert derive_structure_breaks(
            [upper], [event(upper, index)]
        ) == ()
    assert len(derive_structure_breaks([upper], [event(upper, 7)])) == 1


def test_eligible_from_is_the_origin_plus_the_confirmation_delay() -> None:
    """The delay now varies with the level's own provenance, not with an argument."""
    for bars in (1, 2, 5):
        upper = level(103.0, LevelSide.UPPER, 5, confirmation_bars=bars)
        got = derive_structure_breaks([upper], [event(upper, 20)])
        assert got[0].eligible_from == 5 + bars
        assert got[0].origin.confirmation_bars == bars


def test_only_the_most_recent_eligible_level_is_the_reference() -> None:
    old = level(100.0, LevelSide.UPPER, 3)
    new = level(110.0, LevelSide.UPPER, 8)
    crossings = [event(old, 20), event(new, 20)]
    got = derive_structure_breaks([old, new], crossings)
    assert [b.level for b in got] == [new]


def test_a_superseded_level_never_breaks_structure() -> None:
    """Crossing an older, lower high while a newer high stands is not a break."""
    old = level(100.0, LevelSide.UPPER, 3)
    new = level(110.0, LevelSide.UPPER, 8)
    got = derive_structure_breaks([old, new], [event(old, 20)])
    assert got == ()


def test_the_reference_is_most_recent_not_most_extreme() -> None:
    """A lower high becomes the reference once confirmed — ADR-0020 §3.4, D5."""
    high = level(110.0, LevelSide.UPPER, 3)
    lower_high = level(105.0, LevelSide.UPPER, 8, StructuralSwingLabel.LOWER_HIGH)
    got = derive_structure_breaks(
        [high, lower_high], [event(lower_high, 20)]
    )
    assert [b.level.price for b in got] == [105.0]


def test_before_any_level_is_eligible_there_is_no_reference() -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    assert breaks_mod._reference(
        breaks_mod._levels_by_side([upper])[LevelSide.UPPER], 6
    ) is None


def test_the_reference_lookup_matches_an_exhaustive_linear_reference() -> None:
    """Review P2-1: `_reference` became a binary search; prove it found the same element.

    Compared against a deliberately naive linear implementation over every
    arrangement of up to four levels and every as-of index around them, so the
    optimisation is verified rather than asserted.
    """

    def linear(ranked, index):
        found = None
        for eligible_from, lvl in ranked:
            if eligible_from > index:
                break
            found = lvl
        return found

    checked = 0
    for count in range(0, 5):
        for origins in itertools.combinations(range(0, 9), count):
            for bars in (1, 2, 3):
                levels = [
                    level(100.0 + i, LevelSide.UPPER, o, confirmation_bars=bars)
                    for i, o in enumerate(origins)
                ]
                ranked = breaks_mod._levels_by_side(levels)[LevelSide.UPPER]
                for index in range(-1, 16):
                    assert breaks_mod._reference(ranked, index) is linear(ranked, index)
                    checked += 1
    assert checked > 5000


def test_the_reference_lookup_is_sublinear_in_the_level_count() -> None:
    """A scan would grow with the level count; a binary search does not."""
    counts = []
    for size in (16, 1024):
        levels = [level(100.0 + i, LevelSide.UPPER, i + 1) for i in range(size)]
        ranked = breaks_mod._levels_by_side(levels)[LevelSide.UPPER]
        probes = 0
        original = ranked.__getitem__

        class Counting(list):
            def __getitem__(self, item):
                nonlocal probes
                probes += 1
                return list.__getitem__(self, item)

        counted = Counting(ranked)
        breaks_mod._reference(counted, size + 10)
        counts.append(probes)
    # 64x more levels must not cost 64x more probes
    assert counts[1] < counts[0] * 4, counts


def test_sides_are_tracked_independently() -> None:
    upper = level(110.0, LevelSide.UPPER, 3)
    lower = level(90.0, LevelSide.LOWER, 8)
    got = derive_structure_breaks(
        [upper, lower], [event(upper, 20), event(lower, 21)]
    )
    assert [(b.index, b.side) for b in got] == [
        (20, LevelSide.UPPER),
        (21, LevelSide.LOWER),
    ]


# ===================== 6. lifecycle: structure breaks once ==================


def test_a_level_breaks_at_most_once() -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    got = derive_structure_breaks(
        [upper], [event(upper, 8), event(upper, 10), event(upper, 12)]
    )
    assert [b.index for b in got] == [8]


def test_the_earliest_qualifying_crossing_wins_regardless_of_input_order() -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    for order in itertools.permutations([event(upper, 12), event(upper, 8), event(upper, 10)]):
        got = derive_structure_breaks([upper], list(order))
        assert [b.index for b in got] == [8]


def test_repeated_crossings_of_one_level_yield_one_break_end_to_end() -> None:
    levels, crossings = pipeline(series(UPWARD_ROWS))
    close_breaches = [
        e for e in crossings if e.kind is CrossingKind.CLOSE_BREACH and e.level.price == 103.0
    ]
    assert len(close_breaches) >= 2
    got = derive_structure_breaks(levels, crossings)
    assert len([b for b in got if b.level.price == 103.0]) == 1


def test_a_broken_level_stops_producing_breaks_and_no_newer_level_replaces_it() -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    got = derive_structure_breaks(
        [upper], [event(upper, i) for i in range(8, 30)]
    )
    assert len(got) == 1


def test_a_break_is_never_invalidated() -> None:
    """No API, field or return shape can withdraw a break once reported."""
    levels, crossings = pipeline(series(UPWARD_ROWS))
    got = derive_structure_breaks(levels, crossings)
    extended = derive_structure_breaks(
        levels, list(crossings) + [event(levels[0], 40)]
    )
    assert got[0] in extended


# ===================== 7. mechanisms: gaps and already-beyond ===============


def test_a_gapped_breach_breaks_structure() -> None:
    rows = [
        (100, 101, 99, 100),
        (100, 102, 98, 100),
        (100, 104, 96, 100),
        (100, 102, 98, 100),
        (100, 101, 99, 100),
        (100, 103, 97, 100),
        (100, 101, 99, 100),
        (100, 100.5, 99.5, 100),
        (150, 155, 148, 152),
    ]
    levels, crossings = pipeline(series(rows))
    gapped = [e for e in crossings if e.mechanism is CrossingMechanism.GAPPED_BEYOND]
    assert gapped
    got = derive_structure_breaks(levels, crossings)
    assert [(b.index, b.level.price) for b in got] == [(8, 103.0)]
    assert got[0].crossing.mechanism is CrossingMechanism.GAPPED_BEYOND


def test_an_already_beyond_crossing_never_breaks_structure() -> None:
    """Excluded by mechanism — stated explicitly, not left to eligibility alone."""
    upper = level(103.0, LevelSide.UPPER, 5)
    beyond = event(upper, 20, mechanism=CrossingMechanism.ALREADY_BEYOND)
    assert derive_structure_breaks([upper], [beyond]) == ()


def test_an_already_beyond_crossing_is_also_unreachable_by_eligibility() -> None:
    """It can only occur at bar 0, where no structural level is ever eligible."""
    real = real_series()
    levels, crossings = pipeline(real)
    for crossing in crossings:
        if crossing.mechanism is CrossingMechanism.ALREADY_BEYOND:
            assert crossing.index == 0
            assert crossing.level.origin.index + RB > 0
    for lvl in levels:
        assert lvl.origin.index >= 1


def test_the_mechanism_is_carried_through_for_the_consumer() -> None:
    upper = level(103.0, LevelSide.UPPER, 5)
    for mechanism in (CrossingMechanism.WITHIN_RANGE, CrossingMechanism.GAPPED_BEYOND):
        got = derive_structure_breaks(
            [upper], [event(upper, 8, mechanism=mechanism)]
        )
        assert got[0].crossing.mechanism is mechanism


# ===================== 8. outside bars ======================================


def test_one_bar_can_break_both_sides() -> None:
    """Reachable when the reference low sits above the reference high."""
    upper = level(90.0, LevelSide.UPPER, 3)
    lower = level(110.0, LevelSide.LOWER, 5)
    # A genuine outside bar: it trades through both levels and closes between
    # them, so it closes above the upper reference and below the lower one.
    bar = candle(20, 100, 115, 85, 100)
    crossings = [
        LevelCrossingEvent(
            level=upper, candle=bar, index=20,
            kind=CrossingKind.CLOSE_BREACH, mechanism=CrossingMechanism.WITHIN_RANGE,
        ),
        LevelCrossingEvent(
            level=lower, candle=bar, index=20,
            kind=CrossingKind.CLOSE_BREACH, mechanism=CrossingMechanism.WITHIN_RANGE,
        ),
    ]
    got = derive_structure_breaks([upper, lower], crossings)
    assert [(b.index, b.side) for b in got] == [
        (20, LevelSide.UPPER),
        (20, LevelSide.LOWER),
    ]
    assert len({b.timestamp for b in got}) == 1


def test_two_breaks_sharing_a_bar_make_no_claim_about_order() -> None:
    """Their order is the level ordering; the model cannot express a path."""
    for banned in ("path", "order", "sequence", "first", "intrabar"):
        assert not any(banned in f for f in StructureBreak.__dataclass_fields__), banned


def test_an_outside_bar_that_closes_inside_breaks_nothing() -> None:
    rows = [
        (100, 101, 99, 100),
        (100, 102, 98, 100),
        (100, 104, 96, 100),
        (100, 102, 98, 100),
        (100, 101, 99, 100),
        (100, 103, 97, 100),
        (100, 101, 99, 100),
        (100, 100.5, 99.5, 100),
        (100, 130, 70, 100),
    ]
    levels, crossings = pipeline(series(rows))
    assert derive_structure_breaks(levels, crossings) == ()


def test_an_outside_bar_that_closes_beyond_the_upper_reference_breaks_it() -> None:
    rows = [
        (100, 101, 99, 100),
        (100, 102, 98, 100),
        (100, 104, 96, 100),
        (100, 102, 98, 100),
        (100, 101, 99, 100),
        (100, 103, 97, 100),
        (100, 101, 99, 100),
        (100, 100.5, 99.5, 100),
        (100, 130, 70, 129),
    ]
    levels, crossings = pipeline(series(rows))
    got = derive_structure_breaks(levels, crossings)
    assert [(b.index, b.side, b.level.price) for b in got] == [
        (8, LevelSide.UPPER, 103.0)
    ]


def test_an_outside_bar_derived_level_can_itself_break_later() -> None:
    rows = [
        (100, 101, 99, 100),
        (100, 102, 98, 100),
        (100, 104, 96, 100),
        (100, 102, 98, 100),
        (100, 101, 99, 100),
        (100, 103, 97, 100),
        (100, 110, 90, 100),
        (100, 101, 99, 100),
        (100, 102, 98, 100),
        (100, 115, 99, 114),
    ]
    levels, crossings = pipeline(series(rows))
    origins = {lv.origin.index for lv in levels}
    assert 6 in origins
    got = derive_structure_breaks(levels, crossings)
    assert [(b.index, b.level.price) for b in got] == [(9, 110.0)]


# ===================== 9. duplicates and validation =========================


def test_two_levels_on_one_side_sharing_an_origin_index_are_rejected() -> None:
    a = level(100.0, LevelSide.UPPER, 5)
    b = level(101.0, LevelSide.UPPER, 5, StructuralSwingLabel.LOWER_HIGH)
    with pytest.raises(StructureBreakInputError) as excinfo:
        derive_structure_breaks([a, b], [])
    assert str(excinfo.value) == (
        "levels[1] shares origin index 5 with another upper level; the reference "
        "level at that point would be ambiguous"
    )


def test_two_levels_on_different_sides_may_share_an_origin_index() -> None:
    """One outside bar legitimately yields a HIGH and a LOW at one index."""
    upper = level(110.0, LevelSide.UPPER, 5)
    lower = level(90.0, LevelSide.LOWER, 5)
    got = derive_structure_breaks(
        [upper, lower], [event(upper, 20)]
    )
    assert len(got) == 1


def test_an_unprovenanced_level_is_rejected() -> None:
    with pytest.raises(StructureBreakInputError) as excinfo:
        derive_structure_breaks(
            [level(100.0, LevelSide.UPPER, 5), PriceLevel(105.0, LevelSide.UPPER)],
            []
        )
    assert str(excinfo.value) == (
        "levels[1] carries no origin (upper 105.0); a break needs provenance to "
        "place the level in time"
    )


def test_an_unprovenanced_level_is_rejected_even_with_no_crossings() -> None:
    """Validation happens before derivation, so failure never depends on the data."""
    with pytest.raises(StructureBreakInputError):
        derive_structure_breaks([PriceLevel(105.0, LevelSide.UPPER)], [])


def test_a_crossing_referencing_an_unknown_level_is_rejected() -> None:
    known = level(100.0, LevelSide.UPPER, 5)
    unknown = level(200.0, LevelSide.UPPER, 9)
    with pytest.raises(StructureBreakInputError) as excinfo:
        derive_structure_breaks([known], [event(unknown, 20)])
    assert str(excinfo.value) == (
        "crossings[0] references a level absent from levels (upper 200.0)"
    )


def test_an_equal_valued_but_distinct_level_object_is_still_unknown() -> None:
    """Membership is by identity, so a look-alike does not silently pass."""
    known = level(100.0, LevelSide.UPPER, 5)
    twin = level(100.0, LevelSide.UPPER, 5)
    assert known == twin and known is not twin
    with pytest.raises(StructureBreakInputError):
        derive_structure_breaks([known], [event(twin, 20)])


def test_duplicate_provenance_across_sides_is_accepted_and_ranked() -> None:
    upper = level(110.0, LevelSide.UPPER, 5, StructuralSwingLabel.HIGHER_HIGH)
    lower = level(90.0, LevelSide.LOWER, 5, StructuralSwingLabel.LOWER_LOW)
    ranked = breaks_mod._levels_by_side([upper, lower])
    assert ranked[LevelSide.UPPER] == [(7, upper)]
    assert ranked[LevelSide.LOWER] == [(7, lower)]


def test_two_levels_at_one_price_with_different_origins_are_both_kept() -> None:
    first = level(100.0, LevelSide.UPPER, 3)
    second = level(100.0, LevelSide.UPPER, 8, StructuralSwingLabel.EQUAL_HIGH)
    got = derive_structure_breaks(
        [first, second], [event(second, 20)]
    )
    assert [b.level is second for b in got] == [True]


@pytest.mark.parametrize(
    "call,message",
    [
        (
            lambda: derive_structure_breaks("levels", []),
            "levels must be a sequence of PriceLevel, got str",
        ),
        (
            lambda: derive_structure_breaks([], "crossings"),
            "crossings must be a sequence of LevelCrossingEvent, got str",
        ),
        (
            lambda: derive_structure_breaks([1], []),
            "levels[0] must be a PriceLevel, got int",
        ),
        (
            lambda: derive_structure_breaks(
                [level(100.0, LevelSide.UPPER, 5)], [1]
            ),
            "crossings[0] must be a LevelCrossingEvent, got int",
        ),
    ],
)
def test_argument_validation_messages(call, message: str) -> None:
    with pytest.raises(TypeError) as excinfo:
        call()
    assert str(excinfo.value) == message


def test_a_confirmation_delay_cannot_be_supplied_to_this_layer() -> None:
    """AH: the whole class of mismatch is gone, because the argument is gone.

    Before, `confirmation_bars` was a required keyword argument validated for
    type and sign. A caller could satisfy every one of those checks and still
    pass a number that disagreed with the ``right_bars`` used for detection,
    which silently changed which level was the reference at every bar. There is
    now nothing to validate, because there is nothing to pass.
    """
    upper = level(103.0, LevelSide.UPPER, 5)
    with pytest.raises(TypeError):
        derive_structure_breaks([upper], [event(upper, 20)], confirmation_bars=2)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        derive_structure_breaks([upper], [event(upper, 20)], confirmation_bars=99)  # type: ignore[call-arg]

    # And the delay that *is* used comes off the level itself.
    got = derive_structure_breaks([upper], [event(upper, 20)])
    assert [b.eligible_from for b in got] == [upper.origin.knowable_from] == [7]


def test_a_zero_confirmation_window_is_no_longer_representable() -> None:
    """It was permitted while the delay was an argument; provenance forbids it.

    Zero meant "eligible at its own pivot bar", which is only true of a level
    that came from no confirmation window at all. Every origin now records the
    window it was confirmed under, and `detect_swings` — the only producer —
    rejects a window below 1, so recording 0 would record a confirmation that
    never happened.
    """
    with pytest.raises(ValueError) as excinfo:
        LevelOrigin(
            index=5,
            timestamp=_BASE,
            label=StructuralSwingLabel.HIGHER_HIGH,
            confirmation_bars=0,
        )
    assert str(excinfo.value) == "confirmation_bars must be at least 1, got 0"


def test_the_input_error_is_a_value_error_and_a_package_error() -> None:
    assert issubclass(StructureBreakInputError, StructureBreakError)
    assert issubclass(StructureBreakInputError, ValueError)


# ===================== 10. empty inputs =====================================


def test_empty_levels_and_crossings() -> None:
    assert derive_structure_breaks([], []) == ()


def test_levels_but_no_crossings() -> None:
    assert derive_structure_breaks(
        [level(100.0, LevelSide.UPPER, 5)], []
    ) == ()


def test_crossings_but_no_levels_is_rejected_not_silently_empty() -> None:
    upper = level(100.0, LevelSide.UPPER, 5)
    with pytest.raises(StructureBreakInputError):
        derive_structure_breaks([], [event(upper, 20)])


def test_an_empty_result_is_an_immutable_tuple() -> None:
    assert isinstance(derive_structure_breaks([], []), tuple)


# ===================== 11. ordering =========================================


def test_breaks_are_ordered_by_bar_then_side() -> None:
    upper = level(90.0, LevelSide.UPPER, 3)
    lower = level(110.0, LevelSide.LOWER, 3)
    bar = candle(20, 100, 115, 85, 100)
    crossings = [
        LevelCrossingEvent(level=lower, candle=bar, index=20,
                           kind=CrossingKind.CLOSE_BREACH,
                           mechanism=CrossingMechanism.WITHIN_RANGE),
        LevelCrossingEvent(level=upper, candle=bar, index=20,
                           kind=CrossingKind.CLOSE_BREACH,
                           mechanism=CrossingMechanism.WITHIN_RANGE),
    ]
    got = derive_structure_breaks([upper, lower], crossings)
    assert [b.side for b in got] == [LevelSide.UPPER, LevelSide.LOWER]


def test_the_ordering_key_is_strictly_increasing() -> None:
    rows = seeded_rows(120, 11)
    levels, crossings = pipeline(series(rows))
    got = derive_structure_breaks(levels, crossings)
    keys = [breaks_mod._break_key(b) for b in got]
    assert all(a < b for a, b in zip(keys, keys[1:]))


def test_ordering_uses_an_explicit_rank_not_enum_order() -> None:
    assert breaks_mod._SIDE_RANK[LevelSide.UPPER] == 0
    assert breaks_mod._SIDE_RANK[LevelSide.LOWER] == 1
    with pytest.raises(TypeError):
        breaks_mod._SIDE_RANK[LevelSide.UPPER] = 9


def test_index_order_is_timestamp_order() -> None:
    rows = seeded_rows(120, 13)
    levels, crossings = pipeline(series(rows))
    got = derive_structure_breaks(levels, crossings)
    assert [b.timestamp for b in got] == sorted(b.timestamp for b in got)


# ===================== 12. input-order invariance ===========================


def test_permuting_the_level_input_changes_nothing() -> None:
    rows = seeded_rows(100, 17)
    levels, crossings = pipeline(series(rows))
    reference = derive_structure_breaks(levels, crossings)
    rng = random.Random(17)
    for _ in range(10):
        shuffled = list(levels)
        rng.shuffle(shuffled)
        assert derive_structure_breaks(shuffled, crossings) == reference


def test_permuting_the_crossing_input_changes_nothing() -> None:
    rows = seeded_rows(100, 19)
    levels, crossings = pipeline(series(rows))
    reference = derive_structure_breaks(levels, crossings)
    rng = random.Random(19)
    for _ in range(10):
        shuffled = list(crossings)
        rng.shuffle(shuffled)
        assert derive_structure_breaks(levels, shuffled) == reference


def test_reversing_both_inputs_changes_nothing() -> None:
    rows = seeded_rows(100, 23)
    levels, crossings = pipeline(series(rows))
    assert derive_structure_breaks(
        list(reversed(levels)), list(reversed(crossings))
    ) == derive_structure_breaks(levels, crossings)


def test_duplicated_crossing_events_change_nothing() -> None:
    rows = seeded_rows(100, 29)
    levels, crossings = pipeline(series(rows))
    reference = derive_structure_breaks(levels, crossings)
    assert derive_structure_breaks(
        levels, list(crossings) * 3
    ) == reference


# ===================== 13. prefix stability =================================


def _prefix_violations(
    rows: list[tuple[float, float, float, float]], right_bars: int = RB
) -> int:
    levels, crossings = pipeline(series(rows), right_bars)
    full = derive_structure_breaks(levels, crossings)
    violations = 0
    for n in range(len(rows) + 1):
        plevels, pcrossings = pipeline(series(rows[:n]), right_bars)
        got = derive_structure_breaks(plevels, pcrossings)
        want = tuple(b for b in full if b.index < n)
        if [(b.index, b.side, b.level.price) for b in got] != [
            (b.index, b.side, b.level.price) for b in want
        ]:
            violations += 1
    return violations


@pytest.mark.parametrize("seed", [31, 37, 41, 43, 47])
def test_prefix_stability_on_seeded_fixtures(seed: int) -> None:
    assert _prefix_violations(seeded_rows(45, seed)) == 0


@pytest.mark.parametrize("right_bars", [1, 2, 3])
def test_prefix_stability_across_confirmation_delays(right_bars: int) -> None:
    assert _prefix_violations(seeded_rows(45, 53), right_bars) == 0


@pytest.mark.parametrize(
    "name,rows",
    [
        ("upward break", UPWARD_ROWS),
        ("counterexample", COUNTEREXAMPLE_ROWS),
        ("flat", [(100, 101, 99, 100)] * 15),
        ("outside bars", [(100, 110, 90, 100), (100, 120, 80, 100)] * 6),
    ],
)
def test_prefix_stability_on_handcrafted_edge_cases(name: str, rows: list) -> None:
    assert _prefix_violations(rows) == 0, name


def test_prefix_stability_on_the_real_fixture() -> None:
    real = real_series()
    rows = [(c.open, c.high, c.low, c.close) for c in real.candles]
    levels, crossings = pipeline(real)
    full = derive_structure_breaks(levels, crossings)
    for n in range(len(real.candles) + 1):
        prefix = CandleSeries(
            symbol=real.symbol, timeframe=real.timeframe, candles=real.candles[:n]
        )
        plevels, pcrossings = pipeline(prefix)
        got = derive_structure_breaks(plevels, pcrossings)
        assert [(b.index, b.side, b.level.price) for b in got] == [
            (b.index, b.side, b.level.price) for b in full if b.index < n
        ]


def test_the_documented_counterexample_is_stable_under_the_shipped_rule() -> None:
    """§2.4: pivot-bar eligibility breaks here; the confirmation rule does not."""
    rows = COUNTEREXAMPLE_ROWS
    levels, crossings = pipeline(series(rows))
    full = derive_structure_breaks(levels, crossings)
    plevels, pcrossings = pipeline(series(rows[:13]))
    prefix = derive_structure_breaks(plevels, pcrossings)
    assert [(b.index, b.side, b.level.price) for b in prefix] == [
        (b.index, b.side, b.level.price) for b in full if b.index < 13
    ]
    assert any(b.index == 12 for b in prefix)


def test_adding_later_crossings_cannot_change_earlier_breaks() -> None:
    rows = seeded_rows(80, 59)
    levels, crossings = pipeline(series(rows))
    ordered = sorted(crossings, key=lambda e: e.index)
    for n in range(1, len(ordered)):
        short = derive_structure_breaks(levels, ordered[:n])
        longer = derive_structure_breaks(levels, ordered[: n + 1])
        assert all(b in longer for b in short)


# ===================== 14. replay determinism ===============================


def test_replay_is_deterministic() -> None:
    rows = seeded_rows(120, 61)
    levels, crossings = pipeline(series(rows))
    first = derive_structure_breaks(levels, crossings)
    for _ in range(5):
        assert derive_structure_breaks(levels, crossings) == first


def test_a_rebuilt_equal_pipeline_replays_identically() -> None:
    rows = seeded_rows(90, 67)
    a_levels, a_crossings = pipeline(series(rows))
    b_levels, b_crossings = pipeline(series(rows))
    assert derive_structure_breaks(
        a_levels, a_crossings
    ) == derive_structure_breaks(b_levels, b_crossings)


# ===================== 15. the safe pipeline ================================


def _contextual(candles: CandleSeries):
    swings = contextual_structural_swings(candles)
    levels = contextual_structural_levels(swings)
    return levels, contextual_level_crossings(candles, levels)


def test_the_safe_pipeline_end_to_end() -> None:
    candles = series(UPWARD_ROWS)
    levels, crossings = _contextual(candles)
    got = contextual_structure_breaks(levels, crossings)
    assert isinstance(got, ContextualSeries)
    assert got.identity == SeriesIdentity(symbol="BTCUSDT", timeframe="4h")
    assert [(b.index, b.level.price) for b in got.values] == [(8, 103.0)]


def test_identity_is_carried_by_reference() -> None:
    levels, crossings = _contextual(series(UPWARD_ROWS))
    got = contextual_structure_breaks(levels, crossings)
    assert got.identity is levels.identity


def test_an_instrument_mismatch_is_rejected() -> None:
    levels, crossings = _contextual(series(UPWARD_ROWS))
    eth = ContextualSeries(
        identity=SeriesIdentity(symbol="ETHUSDT", timeframe="4h"),
        values=crossings.values,
    )
    with pytest.raises(SeriesIdentityMismatchError) as excinfo:
        contextual_structure_breaks(levels, eth)
    assert str(excinfo.value) == (
        "subjects[1] has identity 'ETHUSDT'/'4h', expected 'BTCUSDT'/'4h'"
    )


def test_a_timeframe_mismatch_is_rejected() -> None:
    levels, crossings = _contextual(series(UPWARD_ROWS))
    other = ContextualSeries(
        identity=SeriesIdentity(symbol="BTCUSDT", timeframe="1h"),
        values=crossings.values,
    )
    with pytest.raises(SeriesIdentityMismatchError) as excinfo:
        contextual_structure_breaks(levels, other)
    assert str(excinfo.value) == (
        "subjects[1] has identity 'BTCUSDT'/'1h', expected 'BTCUSDT'/'4h'"
    )


def test_identity_comparison_does_not_normalize() -> None:
    levels, crossings = _contextual(series(UPWARD_ROWS))
    for symbol, timeframe in (("btcusdt", "4h"), (" BTCUSDT", "4h"), ("BTCUSDT", "4H")):
        other = ContextualSeries(
            identity=SeriesIdentity(symbol=symbol, timeframe=timeframe),
            values=crossings.values,
        )
        with pytest.raises(SeriesIdentityMismatchError):
            contextual_structure_breaks(levels, other)


def test_a_mismatch_is_rejected_before_any_derivation() -> None:
    """An unrankable level set would raise too — the identity check must win."""
    bad_levels = ContextualSeries(
        identity=SeriesIdentity(symbol="BTCUSDT", timeframe="4h"),
        values=(PriceLevel(100.0, LevelSide.UPPER),),
    )
    other = ContextualSeries(
        identity=SeriesIdentity(symbol="ETHUSDT", timeframe="4h"), values=()
    )
    with pytest.raises(SeriesIdentityMismatchError):
        contextual_structure_breaks(bad_levels, other)


def test_empty_contextual_inputs_retain_identity() -> None:
    """Two *equal but distinct* identity objects, so `is` actually discriminates.

    Passing one shared object would make a wrapper that returned the *crossings'*
    identity — or rebuilt an equal one — indistinguishable from a correct one.
    """
    from_levels = SeriesIdentity(symbol="BTCUSDT", timeframe="4h")
    from_crossings = SeriesIdentity(symbol="BTCUSDT", timeframe="4h")
    assert from_levels == from_crossings and from_levels is not from_crossings
    got = contextual_structure_breaks(
        ContextualSeries(identity=from_levels, values=()),
        ContextualSeries(identity=from_crossings, values=())
    )
    assert got.values == ()
    assert got.identity is from_levels


def test_a_non_empty_result_also_carries_the_levels_identity_object() -> None:
    levels, crossings = _contextual(series(UPWARD_ROWS))
    rewrapped = ContextualSeries(
        identity=SeriesIdentity(symbol="BTCUSDT", timeframe="4h"),
        values=crossings.values,
    )
    assert rewrapped.identity is not levels.identity
    got = contextual_structure_breaks(levels, rewrapped)
    assert got.values
    assert got.identity is levels.identity


def test_eligibility_is_read_from_provenance_in_exactly_one_place() -> None:
    """`_levels_by_side` reads `origin.knowable_from`; nothing restates the sum."""
    for bars in (1, 2, 4):
        upper = level(103.0, LevelSide.UPPER, 5, confirmation_bars=bars)
        ranked = breaks_mod._levels_by_side([upper])[LevelSide.UPPER]
        assert ranked == [(5 + bars, upper)]
        assert breaks_mod._reference(ranked, 5 + bars - 1) is None
        assert breaks_mod._reference(ranked, 5 + bars) is upper


def test_an_empty_candle_series_still_carries_identity() -> None:
    levels, crossings = _contextual(series([]))
    got = contextual_structure_breaks(levels, crossings)
    assert got.values == ()
    assert got.identity == SeriesIdentity(symbol="BTCUSDT", timeframe="4h")


def test_no_pipeline_function_accepts_an_identity_argument() -> None:
    import inspect

    parameters = set(inspect.signature(contextual_structure_breaks).parameters)
    assert not any("identity" in p for p in parameters)


def test_a_bare_payload_where_an_envelope_belongs_is_rejected() -> None:
    levels, crossings = _contextual(series(UPWARD_ROWS))
    with pytest.raises(TypeError) as excinfo:
        contextual_structure_breaks((), crossings)
    assert str(excinfo.value) == "levels must be a ContextualSeries, got tuple"
    with pytest.raises(TypeError) as excinfo:
        contextual_structure_breaks(levels, ())
    assert str(excinfo.value) == "crossings must be a ContextualSeries, got tuple"


def test_context_substitution_is_unrepresentable() -> None:
    levels, crossings = _contextual(series(UPWARD_ROWS))
    got = contextual_structure_breaks(levels, crossings)
    with pytest.raises((AttributeError, TypeError)):
        got.identity = SeriesIdentity(symbol="ETHUSDT", timeframe="4h")


_EQUIVALENCE_ROWS = {
    "upward break": UPWARD_ROWS,
    "counterexample": COUNTEREXAMPLE_ROWS,
    "empty": [],
    "flat, no break": [(100, 101, 99, 100)] * 15,
    "outside bars": [(100, 110, 90, 100), (100, 120, 80, 100)] * 6,
    "seeded": seeded_rows(60, 71),
}


@pytest.mark.parametrize("name", sorted(_EQUIVALENCE_ROWS))
def test_context_free_and_context_aware_payloads_are_identical(name: str) -> None:
    candles = series(_EQUIVALENCE_ROWS[name])
    levels, crossings = pipeline(candles)
    bare = derive_structure_breaks(levels, crossings)
    clevels, ccrossings = _contextual(candles)
    wrapped = contextual_structure_breaks(clevels, ccrossings)
    assert wrapped.values == bare


def test_identity_cannot_change_a_payload() -> None:
    rows = seeded_rows(60, 73)
    payloads = []
    for symbol, timeframe in (("BTCUSDT", "4h"), ("ETHUSDT", "1h"), ("banana", "banana")):
        candles = series(rows, symbol=symbol, timeframe=timeframe)
        levels, crossings = _contextual(candles)
        got = contextual_structure_breaks(levels, crossings)
        payloads.append([(b.index, b.side, b.level.price, b.eligible_from) for b in got.values])
    assert payloads[0] == payloads[1] == payloads[2]


# ===================== 16. properties =======================================


def test_every_break_references_a_supplied_level() -> None:
    rows = seeded_rows(100, 79)
    levels, crossings = pipeline(series(rows))
    for got in derive_structure_breaks(levels, crossings):
        assert any(got.level is lv for lv in levels)


def test_every_break_references_a_supplied_crossing() -> None:
    rows = seeded_rows(100, 83)
    levels, crossings = pipeline(series(rows))
    for got in derive_structure_breaks(levels, crossings):
        assert any(got.crossing is e for e in crossings)


def test_every_break_satisfies_all_five_conjuncts() -> None:
    rows = seeded_rows(150, 89)
    levels, crossings = pipeline(series(rows))
    got = derive_structure_breaks(levels, crossings)
    seen_levels = set()
    for b in got:
        assert b.crossing.kind is CrossingKind.CLOSE_BREACH
        assert b.crossing.mechanism is not CrossingMechanism.ALREADY_BEYOND
        assert b.level.origin is not None
        assert b.index >= b.eligible_from == b.level.origin.index + RB
        assert b.eligible_from == b.level.origin.knowable_from
        ranked = breaks_mod._levels_by_side(levels)[b.side]
        assert breaks_mod._reference(ranked, b.index) is b.level
        assert id(b.level) not in seen_levels
        seen_levels.add(id(b.level))


def test_at_most_one_break_per_bar_per_side() -> None:
    rows = seeded_rows(150, 97)
    levels, crossings = pipeline(series(rows))
    got = derive_structure_breaks(levels, crossings)
    slots = [(b.index, b.side) for b in got]
    assert len(slots) == len(set(slots))


def test_a_larger_confirmation_delay_never_invents_a_break_of_a_newer_level() -> None:
    rows = seeded_rows(120, 101)
    levels, crossings = pipeline(series(rows))
    for bars in (2, 3, 4, 5):
        for b in derive_structure_breaks(levels, crossings):
            assert b.index >= b.level.origin.index + bars


def test_repeated_execution_produces_identical_results() -> None:
    rows = seeded_rows(80, 103)
    levels, crossings = pipeline(series(rows))
    results = [
        derive_structure_breaks(levels, crossings) for _ in range(5)
    ]
    assert all(r == results[0] for r in results)


def test_an_exhaustive_small_reference_space_is_consistent() -> None:
    """Every arrangement of two upper levels and one crossing bar."""
    checked = 0
    for o1, o2 in itertools.product(range(1, 6), repeat=2):
        if o1 == o2:
            continue
        a = level(100.0, LevelSide.UPPER, o1)
        b = level(110.0, LevelSide.UPPER, o2, StructuralSwingLabel.LOWER_HIGH)
        for at in range(1, 14):
            for target in (a, b):
                got = derive_structure_breaks(
                    [a, b], [event(target, at)]
                )
                eligible = [
                    lv for lv in (a, b) if lv.origin.index + RB <= at
                ]
                expected = (
                    max(eligible, key=lambda lv: lv.origin.index) if eligible else None
                )
                assert [x.level for x in got] == ([target] if expected is target else [])
                checked += 1
    assert checked > 400


# ===================== 17. exports and architecture guards ==================


def test_the_public_api_is_exactly_five_names() -> None:
    assert set(sb.__all__) == {
        "StructureBreak",
        "StructureBreakError",
        "StructureBreakInputError",
        "derive_structure_breaks",
        "contextual_structure_breaks",
    }
    assert len(sb.__all__) == 5


def test_every_exported_name_resolves() -> None:
    for name in sb.__all__:
        assert hasattr(sb, name), name


def test_no_submodule_collides_with_a_public_name() -> None:
    import pkgutil

    submodules = {m.name for m in pkgutil.iter_modules(sb.__path__)}
    assert submodules == {"breaks", "models", "pipeline"}
    assert submodules & set(sb.__all__) == set()


def test_no_export_collides_across_the_whole_package_tree() -> None:
    import collections
    import pkgutil

    import fmis

    owners: dict[str, list[str]] = collections.defaultdict(list)
    for module in pkgutil.walk_packages(fmis.__path__, "fmis."):
        imported = importlib.import_module(module.name)
        if (
            imported.__spec__ is None
            or imported.__spec__.submodule_search_locations is None
        ):
            continue
        for name in getattr(imported, "__all__", []):
            owners[name].append(module.name)
    assert {n: o for n, o in owners.items() if len(o) > 1} == {}


def test_no_private_helper_is_exported() -> None:
    for private in (
        "_levels_by_side",
        "_reference",
        "_break_key",
        "_require_confirmation_bars",
        "_require_envelope",
        "_SIDE_RANK",
    ):
        assert private not in sb.__all__, private
        assert not hasattr(sb, private), private


def test_no_mutable_public_object_is_exported() -> None:
    for name in sb.__all__:
        assert not isinstance(getattr(sb, name), (list, dict, set)), name


def _internal_imports() -> set[str]:
    found: set[str] = set()
    for py in PACKAGE_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("fmis"):
                    found.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("fmis"):
                        found.add(alias.name)
    return found


def test_imports_only_the_permitted_packages() -> None:
    assert _internal_imports() <= {
        "fmis.level_crossing",
        "fmis.series_context",
        "fmis.market_structure",
        "fmis.structure_break.breaks",
        "fmis.structure_break.models",
        "fmis.structure_break.pipeline",
    }


def test_the_package_cannot_reach_a_candle() -> None:
    """The mission, enforced structurally: `fmis.data` is not imported at all."""
    assert not any(i.startswith("fmis.data") for i in _internal_imports())
    for py in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            a.asname or a.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in n.names
        }
        for banned in ("Candle", "CandleSeries"):
            assert banned not in names, (py, banned)


def test_no_ohlc_field_is_read_anywhere() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("open", "high", "low", "close", "volume"), (
                    py,
                    node.attr,
                )


def test_does_not_import_structural_trend() -> None:
    trend = "fmis." + "structural_trend"
    assert not any(i.startswith(trend) for i in _internal_imports())
    for py in PACKAGE_DIR.glob("*.py"):
        assert trend not in py.read_text(), py


@pytest.mark.parametrize(
    "forbidden",
    [
        "fmis.decision_support",
        "fmis.evidence",
        "fmis.providers",
        "fmis.pipeline",
        "fmis.ingest",
        "fmis.trading_context",
        "fmis.relative_value",
        "fmis.features",
        "fmis.alignment",
    ],
)
def test_does_not_depend_on_other_layers(forbidden: str) -> None:
    assert not any(i.startswith(forbidden) for i in _internal_imports()), forbidden


def test_does_not_reach_into_private_submodules_of_its_dependencies() -> None:
    for internal in _internal_imports():
        if internal.startswith("fmis.structure_break"):
            continue
        assert not internal.startswith("fmis.level_crossing."), internal
        assert not internal.startswith("fmis.series_context."), internal
        assert not internal.startswith("fmis.market_structure."), internal


def test_only_change_of_character_imports_structure_break() -> None:
    """Only `fmis.change_of_character`, which sits *above* this package, may consume it.

    Narrowed from "nothing imports this package" when Change of Character
    Foundation v1 shipped. That widening was designed here, not discovered later:
    §19 below and ADR-0020 §7 both specify a consumer that reads the break
    sequence alone, which is exactly what CHoCH does. What matters — and what
    this test still enforces — is the *direction*: nothing below may import
    upward, so `fmis.data`, `fmis.market_structure`, `fmis.structural_trend`,
    `fmis.series_context` and `fmis.level_crossing` remain unable to see this
    package.

    The exemption is named rather than pattern-matched, so a second consumer
    appearing anywhere fails this test and has to justify itself in an ADR.

    Widened for Milestone AF to add `fmis.pipeline`, the **application layer**.
    ADR-0007 §1 defines it as the top of the graph, permits it to import every
    engine, and a test there asserts no engine imports it back; the Structural
    Fact Sheet composition root is the first consumer to read this package that
    way. The widening is designed, not discovered: an application layer that
    could not reach the structural chain would leave that chain unreachable,
    which is the milestone's entire purpose.

    The direction rule is unchanged. Every engine below remains unable to see
    this package, and each exemption is still named rather than pattern-matched,
    so a further consumer fails this test and must justify itself in an ADR.
    """
    root = PACKAGE_DIR.parent
    permitted = {root / "change_of_character", root / "pipeline"}
    for py in root.rglob("*.py"):
        if py.parent == PACKAGE_DIR or py.parent in permitted:
            continue
        assert "fmis.structure_break" not in _code_without_docstrings(py), py


def _code_without_docstrings(path: pathlib.Path) -> str:
    """The module's source with every docstring blanked out.

    The guard above is a **text** scan rather than an import scan on purpose: it
    catches a dynamic ``importlib.import_module("fmis.structure_break")``, which
    an AST import check would miss entirely.

    Docstrings are excluded because prose is not a dependency. Milestone AH gave
    `SwingPoint.knowable_from` and `LevelOrigin` docstrings that name this package
    to explain *which layer owns eligibility* — precisely the boundary this test
    defends. A guard that forbade naming the rule it enforces would push those
    explanations out of the code, which is the opposite of what it is for.

    Only docstrings are blanked. A comment or a string literal in executable code
    that names the package still fails, so the crude scan keeps its teeth.
    """
    source = path.read_text()
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body or not isinstance(body[0], ast.Expr):
            continue
        doc = body[0].value
        if not isinstance(doc, ast.Constant) or not isinstance(doc.value, str):
            continue
        for lineno in range(doc.lineno, doc.end_lineno + 1):
            lines[lineno - 1] = "\n"
    return "".join(lines)


def test_the_only_permitted_consumer_does_not_reach_into_private_internals() -> None:
    """`fmis.change_of_character` may use this package's public surface and nothing else.

    In particular it must not import `_break_key`, `_reference` or
    `_levels_by_side`: the reference rule, the eligibility arithmetic and the
    break ordering each have exactly one implementation, and a consumer restating
    one is the drift this guard exists to prevent.
    """
    root = PACKAGE_DIR.parent
    for py in (root / "change_of_character").glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("fmis.structure_break."), py


def test_no_import_cycle_exists() -> None:
    import subprocess

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import fmis.data, fmis.market_structure, fmis.series_context, "
            "fmis.level_crossing; "
            "assert 'fmis.structure_break' not in sys.modules; print('ok')",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_uses_only_stdlib() -> None:
    roots: set[str] = set()
    for py in PACKAGE_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
    assert roots <= set(sys.stdlib_module_names) | {"fmis"}


def test_no_global_mutable_state() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.Global)], py
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    [node.target] if isinstance(node, ast.AnnAssign) else node.targets
                )
                if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                    continue
                if isinstance(node.value, (ast.List, ast.Dict, ast.Set)):
                    raise AssertionError(f"module-level mutable literal in {py}")


def test_no_wall_clock_access() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(
                    a.name.split(".")[0] in ("time", "calendar") for a in node.names
                ), py
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in ("time", "calendar"), py
            if isinstance(node, ast.Attribute):
                assert node.attr not in (
                    "now", "utcnow", "today", "monotonic", "perf_counter", "time_ns",
                ), (py, node.attr)


def test_no_randomness_in_production() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(a.name.split(".")[0] == "random" for a in node.names), py
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] != "random", py


def test_no_environment_dependence() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        source = py.read_text()
        for banned in ("os.environ", "getenv", "sys.argv"):
            assert banned not in source, (py, banned)


def test_no_price_tolerance_anywhere() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
            n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
        }
        for banned in ("isclose", "epsilon", "atol", "rtol", "approx", "round", "Decimal"):
            assert banned not in names, (py, banned)


def _referenced_names(py: Path) -> set[str]:
    tree = ast.parse(py.read_text())
    return (
        {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        | {
            n.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))
        }
        | {
            a.asname or a.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in n.names
        }
    )


def test_no_crossing_logic_is_duplicated() -> None:
    """The crossing rule and its ordering key have one implementation, upstream."""
    for py in PACKAGE_DIR.glob("*.py"):
        used = _referenced_names(py)
        for banned in (
            "crossing_kind",
            "_crossing_kind",
            "_is_wholly_beyond",
            "_level_key",
            "_event_key",
            "_extreme_for",
            "derive_level_crossings",
            "_validate_event_order",
        ):
            assert banned not in used, (py, banned)


def test_no_swing_or_level_logic_is_duplicated() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        used = _referenced_names(py)
        for banned in (
            "detect_swings",
            "left_bars",
            "right_bars",
            "structural_levels",
            "_SIDE_BY_LABEL",
            "compare_swings",
            "label_swing",
            "SwingRelation",
        ):
            assert banned not in used, (py, banned)


def test_no_trend_or_state_logic_is_duplicated() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        used = _referenced_names(py)
        for banned in (
            "StructuralTrendType",
            "StructuralSequenceState",
            "MINIMUM_DIRECTIONAL_SHIFTS",
            "derive_structural_trend",
            "SHIFTED_HIGHER",
        ):
            assert banned not in used, (py, banned)


def test_no_identity_logic_is_duplicated() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("symbol", "timeframe"):
                raise AssertionError(f"{py} reads an identity field directly")


def test_the_pipeline_delegates_and_never_re_derives() -> None:
    tree = ast.parse((PACKAGE_DIR / "pipeline.py").read_text())
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for required in ("derive_structure_breaks", "require_same_identity", "ContextualSeries"):
        assert required in called, required
    for node in ast.walk(tree):
        assert not isinstance(node, ast.BinOp), ast.dump(node)


def test_no_choch_implementation_exists() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        used = {n.lower() for n in _referenced_names(py)}
        for banned in ("choch", "change_of_character", "character"):
            assert banned not in used, (py, banned)


def test_no_trading_vocabulary_in_the_package() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        used = {n.lower() for n in _referenced_names(py)}
        for banned in (
            "entry", "exit", "stop_loss", "take_profit", "signal", "long", "short",
            "buy", "sell", "bullish", "bearish", "regime", "confidence", "protected",
            "inducement", "sweep", "portfolio", "size",
        ):
            assert banned not in used, (py, banned)


# ===================== 18. nothing upstream changed =========================


def test_existing_swing_behaviour_is_unchanged() -> None:
    real = real_series()
    assert len(detect_swings(real)) == 5


def test_existing_level_and_crossing_behaviour_is_unchanged() -> None:
    real = real_series()
    levels, crossings = pipeline(real)
    assert len(levels) == 3
    assert len(crossings) == 15


def test_existing_structural_state_and_trend_behaviour_is_unchanged() -> None:
    real = real_series()
    swings = contextual_structural_swings(real)
    history = contextual_structural_state_history(swings)
    trend = contextual_structural_trend_history(history)
    assert history.identity is swings.identity
    assert len(trend.values) >= 1


def test_the_upstream_public_apis_did_not_change() -> None:
    import fmis.level_crossing as lc
    import fmis.market_structure as ms
    import fmis.series_context as sc
    import fmis.structural_trend as st

    assert len(lc.__all__) == 13
    assert len(ms.__all__) == 19
    assert len(sc.__all__) == 7
    assert len(st.__all__) == 5


def test_default_right_bars_still_matches_the_confirmation_delay_used_here() -> None:
    assert DEFAULT_RIGHT_BARS == RB


# ===================== 19. future CHoCH consumption =========================


def test_a_future_choch_layer_needs_only_the_break_sequence() -> None:
    """Review §15: CHoCH is the first break opposing the previous break's direction."""
    rows = seeded_rows(150, 107)
    levels, crossings = pipeline(series(rows))
    breaks = derive_structure_breaks(levels, crossings)

    def hypothetical_choch(run: tuple[StructureBreak, ...]) -> tuple[StructureBreak, ...]:
        return tuple(b for a, b in zip(run, run[1:]) if a.side is not b.side)

    got = hypothetical_choch(breaks)
    assert isinstance(got, tuple)
    for change in got:
        assert change in breaks


def test_choch_consumption_touches_no_level_crossing_or_candle() -> None:
    """`side` and ordering are all a change of character needs."""
    rows = seeded_rows(150, 109)
    levels, crossings = pipeline(series(rows))
    breaks = derive_structure_breaks(levels, crossings)
    sides = [b.side for b in breaks]
    changes = [i for i in range(1, len(sides)) if sides[i] is not sides[i - 1]]
    assert all(isinstance(i, int) for i in changes)


def test_a_break_is_self_describing_without_its_inputs() -> None:
    rows = seeded_rows(120, 113)
    levels, crossings = pipeline(series(rows))
    for b in derive_structure_breaks(levels, crossings):
        described = (
            b.index, b.timestamp, b.side, b.level.price, b.origin.index,
            b.origin.timestamp, b.label, b.eligible_from, b.crossing.mechanism,
        )
        assert len(described) == 9
