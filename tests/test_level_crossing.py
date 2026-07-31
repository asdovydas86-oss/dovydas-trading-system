"""Tests for `fmis.level_crossing` — Level-Crossing Foundation v1.

Organised in the order ADR-0019 states the contract: models and their
self-validation, the crossing policy, mechanisms, ordering, lifecycle, the
safe pipeline, prefix stability, properties, and architecture guards.

Exception messages are treated as a shipped contract and asserted with ``==``,
not `pytest.raises(match=...)`, following `test_market_structure_ordering.py`:
a substring match is what let a reworded message through in the structural-label
milestone.
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

import fmis.level_crossing as lc
from fmis.data import Candle, CandleSeries, SeriesIdentity
from fmis.level_crossing import (
    CrossingKind,
    CrossingMechanism,
    DuplicateLevelError,
    LevelCrossingError,
    LevelCrossingEvent,
    LevelOrigin,
    LevelSide,
    PriceLevel,
    contextual_level_crossings,
    contextual_structural_levels,
    crossing_kind,
    derive_level_crossings,
    structural_levels,
)
from fmis.level_crossing import crossing as crossing_mod
from fmis.level_crossing import levels as levels_mod
from fmis.level_crossing import models as models_mod
from fmis.level_crossing import pipeline as pipeline_mod
from fmis.market_structure import (
    StructuralSwing,
    StructuralSwingLabel,
    SwingPoint,
    SwingType,
    compare_swing_sequence,
    detect_swings,
    label_swing_sequence,
)
from fmis.series_context import (
    ContextualSeries,
    SeriesIdentityMismatchError,
    contextual_structural_state_history,
    contextual_structural_swings,
    contextual_structural_trend_history,
)

PACKAGE_DIR = Path(lc.__file__).parent
_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


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


UPPER_100 = PriceLevel(100.0, LevelSide.UPPER)
LOWER_100 = PriceLevel(100.0, LevelSide.LOWER)


def origin(index: int, label: StructuralSwingLabel) -> LevelOrigin:
    return LevelOrigin(
        index=index, timestamp=_BASE + timedelta(hours=4 * index), label=label
    )


def swing_point(index: int, price: float, type_: SwingType) -> SwingPoint:
    return SwingPoint(
        index=index,
        timestamp=_BASE + timedelta(hours=4 * index),
        price=price,
        type=type_,
    )


def structural_swing(
    previous: SwingPoint, current: SwingPoint
) -> StructuralSwing:
    return label_swing_sequence(compare_swing_sequence((previous, current)))[0]


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
    """Deterministic OHLC with forced exact equalities, gaps and outside bars.

    Seeded in a **test** only; production is free of randomness, which an
    architecture guard enforces.
    """
    rng = random.Random(seed)
    rows: list[tuple[float, float, float, float]] = []
    for i in range(count):
        open_ = rng.uniform(80.0, 120.0)
        close = rng.uniform(80.0, 120.0)
        high = max(open_, close) + rng.uniform(0.0, 6.0)
        low = min(open_, close) - rng.uniform(0.0, 6.0)
        if i % 17 == 0:  # force an exact touch of the 100.0 grid line
            open_ = min(open_, 100.0)
            close = min(close, 100.0)
            rows.append((open_, 100.0, min(low, open_, close), close))
        elif i % 23 == 0:  # force a candle wholly above the grid
            rows.append((130.0, 136.0, 129.0, 134.0))
        elif i % 29 == 0:  # force a candle wholly below the grid
            rows.append((60.0, 64.0, 58.0, 62.0))
        else:
            rows.append((open_, high, low, close))
    return rows


GRID = tuple(
    [PriceLevel(float(p), LevelSide.UPPER) for p in range(95, 106)]
    + [PriceLevel(float(p), LevelSide.LOWER) for p in range(95, 106)]
)


# ===================== 1-5. public types: construction, immutability ========


def test_every_public_type_constructs() -> None:
    assert LevelSide.UPPER.value == "upper"
    assert CrossingKind.TOUCH.value == "touch"
    assert CrossingMechanism.WITHIN_RANGE.value == "within_range"
    assert PriceLevel(1.0, LevelSide.LOWER).origin is None
    o = origin(3, StructuralSwingLabel.HIGHER_HIGH)
    assert PriceLevel(1.0, LevelSide.UPPER, o).origin is o


def test_the_enums_have_exactly_the_documented_members() -> None:
    assert [m.value for m in LevelSide] == ["upper", "lower"]
    assert [m.value for m in CrossingKind] == ["touch", "wick_breach", "close_breach"]
    assert [m.value for m in CrossingMechanism] == [
        "within_range",
        "gapped_beyond",
        "already_beyond",
    ]


@pytest.mark.parametrize("member", list(LevelSide) + list(CrossingKind))
def test_the_enums_are_str_enums_like_every_sibling(member: object) -> None:
    assert isinstance(member, str)


@pytest.mark.parametrize(
    "subject,field,value",
    [
        (PriceLevel(1.0, LevelSide.UPPER), "price", 2.0),
        (PriceLevel(1.0, LevelSide.UPPER), "side", LevelSide.LOWER),
        (origin(1, StructuralSwingLabel.EQUAL_LOW), "index", 5),
    ],
)
def test_public_models_are_immutable(subject: object, field: str, value: object) -> None:
    with pytest.raises((AttributeError, TypeError)):
        setattr(subject, field, value)


def test_the_crossing_event_is_immutable() -> None:
    event = derive_level_crossings(series([(95, 105, 94, 104)]), [UPPER_100])[0]
    with pytest.raises((AttributeError, TypeError)):
        event.index = 9


def test_no_public_model_grows_an_attribute_it_was_never_given() -> None:
    for subject in (
        PriceLevel(1.0, LevelSide.UPPER),
        origin(1, StructuralSwingLabel.EQUAL_LOW),
        derive_level_crossings(series([(95, 105, 94, 104)]), [UPPER_100])[0],
    ):
        with pytest.raises((AttributeError, TypeError)):
            subject.invented = 1


def test_equality_is_structural() -> None:
    assert PriceLevel(1.0, LevelSide.UPPER) == PriceLevel(1.0, LevelSide.UPPER)
    assert PriceLevel(1.0, LevelSide.UPPER) != PriceLevel(1.0, LevelSide.LOWER)
    assert PriceLevel(1.0, LevelSide.UPPER) != PriceLevel(2.0, LevelSide.UPPER)
    assert PriceLevel(
        1.0, LevelSide.UPPER, origin(1, StructuralSwingLabel.HIGHER_HIGH)
    ) != PriceLevel(1.0, LevelSide.UPPER)


def test_public_models_are_hashable_and_collapse_in_a_set() -> None:
    a = PriceLevel(1.0, LevelSide.UPPER)
    b = PriceLevel(1.0, LevelSide.UPPER)
    assert hash(a) == hash(b)
    assert len({a, b}) == 1
    events = derive_level_crossings(series([(95, 105, 94, 104)]), [UPPER_100])
    assert len(set(events)) == 1
    assert len({events[0], events[0]}) == 1


def test_repr_is_stable_and_names_the_type() -> None:
    text = repr(PriceLevel(1.0, LevelSide.UPPER))
    assert text.startswith("PriceLevel(")
    assert repr(PriceLevel(1.0, LevelSide.UPPER)) == text


def test_public_models_round_trip_through_pickle() -> None:
    events = derive_level_crossings(series([(95, 105, 94, 104)]), [UPPER_100])
    restored = pickle.loads(pickle.dumps(events))
    assert restored == events
    assert hash(restored[0]) == hash(events[0])


# ===================== 6-11. the crossing policy ============================


@pytest.mark.parametrize(
    "row,expected",
    [
        ((95, 99, 94, 96), None),                       # never reached
        ((95, 100, 94, 96), CrossingKind.TOUCH),        # exact equality
        ((95, 105, 94, 96), CrossingKind.WICK_BREACH),  # wick beyond, close inside
        ((95, 105, 94, 100), CrossingKind.WICK_BREACH), # close exactly at level
        ((95, 105, 94, 104), CrossingKind.CLOSE_BREACH),
    ],
)
def test_the_upper_crossing_policy(row: tuple, expected: object) -> None:
    assert crossing_kind(candle(0, *row), UPPER_100) is expected


@pytest.mark.parametrize(
    "row,expected",
    [
        ((105, 108, 101, 106), None),
        ((105, 108, 100, 106), CrossingKind.TOUCH),
        ((105, 108, 95, 106), CrossingKind.WICK_BREACH),
        ((105, 108, 95, 100), CrossingKind.WICK_BREACH),
        ((99, 108, 95, 96), CrossingKind.CLOSE_BREACH),
    ],
)
def test_the_lower_crossing_policy(row: tuple, expected: object) -> None:
    assert crossing_kind(candle(0, *row), LOWER_100) is expected


def test_exact_equality_is_a_touch_and_never_a_breach() -> None:
    assert crossing_kind(candle(0, 95, 100, 94, 96), UPPER_100) is CrossingKind.TOUCH
    assert crossing_kind(candle(0, 105, 108, 100, 106), LOWER_100) is CrossingKind.TOUCH


def test_a_close_exactly_at_the_level_is_not_a_close_breach() -> None:
    assert (
        crossing_kind(candle(0, 95, 105, 94, 100), UPPER_100)
        is CrossingKind.WICK_BREACH
    )
    assert (
        crossing_kind(candle(0, 105, 108, 95, 100), LOWER_100)
        is CrossingKind.WICK_BREACH
    )


def test_a_close_breach_always_implies_the_extreme_was_beyond_too() -> None:
    """`high >= close` makes the kinds nest; no candle closes beyond a level it never reached."""
    for row in seeded_rows(200, 7):
        for level in GRID:
            if crossing_kind(candle(0, *row), level) is CrossingKind.CLOSE_BREACH:
                extreme = (
                    candle(0, *row).high
                    if level.side is LevelSide.UPPER
                    else candle(0, *row).low
                )
                if level.side is LevelSide.UPPER:
                    assert extreme > level.price
                else:
                    assert extreme < level.price


def test_the_three_kinds_are_mutually_exclusive_and_exhaustive() -> None:
    seen: set[CrossingKind | None] = set()
    for row in seeded_rows(300, 11):
        for level in GRID:
            seen.add(crossing_kind(candle(0, *row), level))
    assert seen == {None, *CrossingKind}


def test_comparison_is_exact_at_a_binary_float_boundary() -> None:
    """`0.1 + 0.2` is `0.30000000000000004`: a strict breach, not a touch. ADR-0013 4."""
    level = PriceLevel(0.3, LevelSide.UPPER)
    assert crossing_kind(candle(0, 0.1, 0.1 + 0.2, 0.1, 0.1), level) is (
        CrossingKind.WICK_BREACH
    )
    assert crossing_kind(candle(0, 0.1, 0.3, 0.1, 0.1), level) is CrossingKind.TOUCH


def test_negative_zero_and_zero_compare_equal() -> None:
    assert crossing_kind(candle(0, 0.0, 0.0, 0.0, 0.0), PriceLevel(-0.0, LevelSide.UPPER)) is (
        CrossingKind.TOUCH
    )


def test_open_is_never_consulted() -> None:
    """Two candles differing only in `open` classify identically."""
    a = candle(0, 96.0, 105.0, 94.0, 104.0)
    b = candle(0, 103.0, 105.0, 94.0, 104.0)
    assert crossing_kind(a, UPPER_100) is crossing_kind(b, UPPER_100)


def test_a_candle_body_crossing_the_level_is_a_close_breach() -> None:
    assert (
        crossing_kind(candle(0, 98, 103, 97, 102), UPPER_100)
        is CrossingKind.CLOSE_BREACH
    )


# ===================== 12-17. mechanisms, gaps, first candle ================


def test_a_gap_above_an_upper_level() -> None:
    events = derive_level_crossings(
        series([(95, 99, 94, 98), (110, 115, 108, 112)]), [UPPER_100]
    )
    assert len(events) == 1
    assert events[0].index == 1
    assert events[0].mechanism is CrossingMechanism.GAPPED_BEYOND
    assert events[0].kind is CrossingKind.CLOSE_BREACH


def test_a_gap_below_a_lower_level() -> None:
    events = derive_level_crossings(
        series([(105, 108, 101, 106), (95, 98, 90, 92)]), [LOWER_100]
    )
    assert len(events) == 1
    assert events[0].mechanism is CrossingMechanism.GAPPED_BEYOND
    assert events[0].kind is CrossingKind.CLOSE_BREACH


def test_a_first_candle_already_above_an_upper_level() -> None:
    events = derive_level_crossings(
        series([(110, 115, 108, 112), (111, 116, 109, 113)]), [UPPER_100]
    )
    assert [(e.index, e.mechanism) for e in events] == [
        (0, CrossingMechanism.ALREADY_BEYOND)
    ]


def test_a_first_candle_already_below_a_lower_level() -> None:
    events = derive_level_crossings(
        series([(90, 95, 88, 92), (91, 96, 89, 93)]), [LOWER_100]
    )
    assert [(e.index, e.mechanism) for e in events] == [
        (0, CrossingMechanism.ALREADY_BEYOND)
    ]


def test_a_first_candle_touching_exactly_is_within_range() -> None:
    events = derive_level_crossings(series([(95, 100, 94, 96)]), [UPPER_100])
    assert [(e.kind, e.mechanism) for e in events] == [
        (CrossingKind.TOUCH, CrossingMechanism.WITHIN_RANGE)
    ]


def test_a_candle_wholly_beyond_after_another_wholly_beyond_emits_nothing() -> None:
    """Without this rule a level breached once re-emits on every later candle."""
    events = derive_level_crossings(
        series([(110, 115, 108, 112), (111, 116, 109, 113), (112, 117, 110, 114)]),
        [UPPER_100],
    )
    assert len(events) == 1


def test_returning_to_the_level_then_gapping_again_emits_again() -> None:
    events = derive_level_crossings(
        series(
            [
                (95, 99, 94, 98),        # below
                (110, 115, 108, 112),    # gapped above
                (105, 108, 95, 97),      # traded back through
                (110, 115, 108, 112),    # gapped above again
            ]
        ),
        [UPPER_100],
    )
    assert [(e.index, e.mechanism) for e in events] == [
        (1, CrossingMechanism.GAPPED_BEYOND),
        (2, CrossingMechanism.WITHIN_RANGE),
        (3, CrossingMechanism.GAPPED_BEYOND),
    ]


def test_a_beyond_mechanism_always_carries_a_close_breach() -> None:
    for rows, level in (
        ([(95, 99, 94, 98), (110, 115, 108, 112)], UPPER_100),
        ([(105, 108, 101, 106), (95, 98, 90, 92)], LOWER_100),
        ([(110, 115, 108, 112)], UPPER_100),
    ):
        for event in derive_level_crossings(series(rows), [level]):
            if event.mechanism is not CrossingMechanism.WITHIN_RANGE:
                assert event.kind is CrossingKind.CLOSE_BREACH


def test_a_candle_entirely_above_a_lower_level_never_interacts() -> None:
    assert derive_level_crossings(series([(110, 115, 108, 112)]), [LOWER_100]) == ()


def test_a_candle_entirely_below_an_upper_level_never_interacts() -> None:
    assert derive_level_crossings(series([(90, 95, 88, 92)]), [UPPER_100]) == ()


# ===================== 18-25. many candles, many levels ====================


def test_empty_candles_with_levels() -> None:
    assert derive_level_crossings(series([]), list(GRID)) == ()


def test_empty_levels_with_candles() -> None:
    assert derive_level_crossings(series([(95, 105, 94, 104)]), []) == ()


def test_both_empty() -> None:
    assert derive_level_crossings(series([]), []) == ()


def test_an_empty_result_is_an_immutable_tuple() -> None:
    assert isinstance(derive_level_crossings(series([]), []), tuple)


def test_one_candle_crossing_three_upper_levels() -> None:
    ups = [PriceLevel(p, LevelSide.UPPER) for p in (102.0, 100.0, 101.0)]
    events = derive_level_crossings(series([(95, 105, 94, 104)]), ups)
    assert [e.level.price for e in events] == [100.0, 101.0, 102.0]


def test_one_candle_crossing_three_lower_levels() -> None:
    downs = [PriceLevel(p, LevelSide.LOWER) for p in (92.0, 90.0, 91.0)]
    events = derive_level_crossings(series([(95, 96, 85, 86)]), downs)
    assert [e.level.price for e in events] == [90.0, 91.0, 92.0]


def test_one_candle_crossing_mixed_upper_and_lower_levels() -> None:
    mixed = [
        PriceLevel(102.0, LevelSide.UPPER),
        PriceLevel(98.0, LevelSide.LOWER),
        PriceLevel(100.0, LevelSide.UPPER),
        PriceLevel(99.0, LevelSide.LOWER),
    ]
    events = derive_level_crossings(series([(95, 110, 80, 96)]), mixed)
    assert [(e.level.side.value, e.level.price) for e in events] == [
        ("upper", 100.0),
        ("upper", 102.0),
        ("lower", 98.0),
        ("lower", 99.0),
    ]


def test_many_candles_one_level() -> None:
    rows = seeded_rows(60, 3)
    events = derive_level_crossings(series(rows), [UPPER_100])
    assert len({e.index for e in events}) == len(events)


def test_many_candles_many_levels() -> None:
    events = derive_level_crossings(series(seeded_rows(60, 5)), list(GRID))
    assert len(events) > 100
    assert all(0 <= e.index < 60 for e in events)


# ===================== 26-27. outside bars =================================


def test_an_outside_bar_crosses_both_an_upper_and_a_lower_level() -> None:
    events = derive_level_crossings(
        series([(95, 110, 80, 96)]), [UPPER_100, PriceLevel(90.0, LevelSide.LOWER)]
    )
    assert len(events) == 2
    assert {e.index for e in events} == {0}
    assert {e.timestamp for e in events} == {_BASE}
    assert [e.level.side for e in events] == [LevelSide.UPPER, LevelSide.LOWER]


def test_an_outside_bar_can_cross_several_levels_on_both_sides() -> None:
    lv = [
        PriceLevel(101.0, LevelSide.UPPER),
        PriceLevel(105.0, LevelSide.UPPER),
        PriceLevel(90.0, LevelSide.LOWER),
        PriceLevel(85.0, LevelSide.LOWER),
    ]
    events = derive_level_crossings(series([(95, 110, 80, 96)]), lv)
    assert len(events) == 4
    assert [e.level.price for e in events] == [101.0, 105.0, 85.0, 90.0]


def test_the_model_cannot_express_an_intrabar_path() -> None:
    """No path field and no 'order unknown' flag: intrabar order is never known."""
    fields = set(LevelCrossingEvent.__dataclass_fields__)
    assert fields == {"level", "candle", "index", "kind", "mechanism"}
    for banned in ("path", "order", "sequence", "first", "intrabar", "unknown"):
        assert not any(banned in f for f in fields), banned
    assert not any(
        "unknown" in m.value or "order" in m.value for m in CrossingMechanism
    )


def test_outside_bar_event_order_is_the_level_order_not_a_time_claim() -> None:
    """Swapping which side sits nearer the extreme does not reorder the events."""
    lv = [UPPER_100, PriceLevel(90.0, LevelSide.LOWER)]
    near_high = derive_level_crossings(series([(95, 130, 89, 96)]), lv)
    near_low = derive_level_crossings(series([(95, 101, 10, 96)]), lv)
    assert [e.level.side for e in near_high] == [e.level.side for e in near_low]


def test_the_swing_outside_bar_convention_is_not_reused_here() -> None:
    """`market_structure` orders HIGH before LOW at one index; here the rule is the level key."""
    events = derive_level_crossings(
        series([(95, 110, 80, 96)]),
        [PriceLevel(85.0, LevelSide.LOWER), PriceLevel(105.0, LevelSide.UPPER)],
    )
    # Upper first because UPPER outranks LOWER — but by the level key, and the
    # prices are ordered inside each side, which the swing rule says nothing about.
    assert [(e.level.side.value, e.level.price) for e in events] == [
        ("upper", 105.0),
        ("lower", 85.0),
    ]


# ===================== 23-25, 31-32. duplicates and ordering ===============


def test_equal_price_levels_with_different_provenance_stay_distinct() -> None:
    a = PriceLevel(100.0, LevelSide.UPPER, origin(3, StructuralSwingLabel.HIGHER_HIGH))
    b = PriceLevel(100.0, LevelSide.UPPER, origin(7, StructuralSwingLabel.EQUAL_HIGH))
    events = derive_level_crossings(series([(95, 105, 94, 104)]), [a, b])
    assert [e.level for e in events] == [a, b]
    assert events[0].level is a and events[1].level is b


def test_equal_price_and_index_but_different_label_stay_distinct() -> None:
    a = PriceLevel(100.0, LevelSide.UPPER, origin(3, StructuralSwingLabel.HIGHER_HIGH))
    b = PriceLevel(100.0, LevelSide.UPPER, origin(3, StructuralSwingLabel.EQUAL_HIGH))
    assert len(derive_level_crossings(series([(95, 105, 94, 104)]), [a, b])) == 2


def test_a_level_without_an_origin_sorts_before_one_with_an_origin() -> None:
    bare = PriceLevel(100.0, LevelSide.UPPER)
    provenanced = PriceLevel(
        100.0, LevelSide.UPPER, origin(3, StructuralSwingLabel.HIGHER_HIGH)
    )
    events = derive_level_crossings(
        series([(95, 105, 94, 104)]), [provenanced, bare]
    )
    assert [e.level for e in events] == [bare, provenanced]


def test_two_exactly_identical_levels_are_rejected() -> None:
    level = PriceLevel(100.0, LevelSide.UPPER)
    with pytest.raises(DuplicateLevelError) as excinfo:
        derive_level_crossings(series([(95, 105, 94, 104)]), [level, level])
    assert str(excinfo.value) == (
        "levels contains a duplicate level (upper 100.0); levels must be distinct"
    )


def test_two_separately_built_equal_levels_are_also_rejected() -> None:
    with pytest.raises(DuplicateLevelError):
        derive_level_crossings(
            series([(95, 105, 94, 104)]),
            [PriceLevel(100.0, LevelSide.LOWER), PriceLevel(100.0, LevelSide.LOWER)],
        )


def test_duplicate_levels_are_rejected_even_when_no_candle_reaches_them() -> None:
    """Validation happens before derivation, so the failure never depends on the data."""
    with pytest.raises(DuplicateLevelError):
        derive_level_crossings(series([(95, 96, 94, 95)]), [UPPER_100, UPPER_100])


def test_duplicate_levels_are_rejected_with_no_candles_at_all() -> None:
    with pytest.raises(DuplicateLevelError):
        derive_level_crossings(series([]), [UPPER_100, UPPER_100])


def test_the_duplicate_error_is_a_value_error_and_a_package_error() -> None:
    assert issubclass(DuplicateLevelError, LevelCrossingError)
    assert issubclass(DuplicateLevelError, ValueError)


def test_event_order_is_deterministic_under_every_level_permutation() -> None:
    mixed = [
        PriceLevel(102.0, LevelSide.UPPER),
        PriceLevel(98.0, LevelSide.LOWER),
        PriceLevel(100.0, LevelSide.UPPER),
        PriceLevel(99.0, LevelSide.LOWER),
    ]
    reference = derive_level_crossings(series([(95, 110, 80, 96)]), mixed)
    for permutation in itertools.permutations(mixed):
        assert derive_level_crossings(series([(95, 110, 80, 96)]), list(permutation)) == (
            reference
        )


def test_reversed_level_order_changes_nothing() -> None:
    rows = seeded_rows(40, 13)
    forward = derive_level_crossings(series(rows), list(GRID))
    assert derive_level_crossings(series(rows), list(reversed(GRID))) == forward


def test_events_are_ordered_by_candle_index_first() -> None:
    events = derive_level_crossings(series(seeded_rows(40, 17)), list(GRID))
    assert [e.index for e in events] == sorted(e.index for e in events)


def test_the_ordering_key_is_strictly_increasing() -> None:
    events = derive_level_crossings(series(seeded_rows(40, 19)), list(GRID))
    keys = [crossing_mod._event_key(e) for e in events]
    assert all(a < b for a, b in zip(keys, keys[1:]))


def test_ordering_does_not_depend_on_enum_definition_order() -> None:
    """The rank mappings are explicit, so `.value` order and member order are irrelevant."""
    assert models_mod._SIDE_RANK[LevelSide.UPPER] == 0
    assert models_mod._SIDE_RANK[LevelSide.LOWER] == 1
    assert set(models_mod._LABEL_RANK) == set(StructuralSwingLabel)
    assert sorted(models_mod._LABEL_RANK.values()) == list(range(6))


def test_index_order_is_timestamp_order() -> None:
    events = derive_level_crossings(series(seeded_rows(40, 23)), list(GRID))
    stamps = [e.timestamp for e in events]
    assert stamps == sorted(stamps)


# ===================== 28-30. repeated crossings and lifecycle =============


def test_repeated_crossing_after_moving_back_across_the_level() -> None:
    events = derive_level_crossings(
        series([(95, 105, 94, 104), (104, 106, 96, 97), (97, 108, 96, 107)]),
        [UPPER_100],
    )
    assert [(e.index, e.kind) for e in events] == [
        (0, CrossingKind.CLOSE_BREACH),
        (1, CrossingKind.WICK_BREACH),
        (2, CrossingKind.CLOSE_BREACH),
    ]


def test_repeated_touches_are_each_emitted() -> None:
    events = derive_level_crossings(
        series([(95, 100, 94, 96), (95, 100, 94, 96), (95, 100, 94, 96)]),
        [UPPER_100],
    )
    assert [e.kind for e in events] == [CrossingKind.TOUCH] * 3


def test_all_crossings_are_reported_not_only_the_first() -> None:
    """v1 selected all-crossings; first-cross-only is the consumer's one-pass filter."""
    events = derive_level_crossings(
        series([(95, 105, 94, 96), (95, 105, 94, 96)]), [UPPER_100]
    )
    assert len(events) == 2
    first_only = {}
    for event in events:
        first_only.setdefault(event.level, event)
    assert len(first_only) == 1


def test_a_touch_consumes_nothing_and_a_later_breach_still_reports() -> None:
    events = derive_level_crossings(
        series([(95, 100, 94, 96), (96, 105, 95, 104)]), [UPPER_100]
    )
    assert [e.kind for e in events] == [
        CrossingKind.TOUCH,
        CrossingKind.CLOSE_BREACH,
    ]


def test_a_level_whose_origin_postdates_the_crossing_still_reports() -> None:
    """v1 has no activation policy; BOS filters on fields it already holds (D1)."""
    late = PriceLevel(100.0, LevelSide.UPPER, origin(9, StructuralSwingLabel.HIGHER_HIGH))
    events = derive_level_crossings(
        series([(95, 105, 94, 104), (95, 96, 94, 95)]), [late]
    )
    assert [e.index for e in events] == [0]
    assert events[0].index < events[0].level.origin.index
    # and a consumer can apply activation without re-reading a candle
    assert [e for e in events if e.index >= e.level.origin.index] == []


def test_no_public_model_carries_lifecycle_state() -> None:
    for banned in ("active", "spent", "protected", "invalidated", "count", "touched"):
        assert banned not in PriceLevel.__dataclass_fields__, banned
        assert banned not in LevelCrossingEvent.__dataclass_fields__, banned


# ===================== 33-34. prefix stability and replay ==================


def _prefix_violations(
    rows: list[tuple[float, float, float, float]], levels: list[PriceLevel]
) -> int:
    full = derive_level_crossings(series(rows), levels)
    violations = 0
    for n in range(len(rows) + 1):
        got = derive_level_crossings(series(rows[:n]), levels)
        if got != tuple(e for e in full if e.index < n):
            violations += 1
    return violations


@pytest.mark.parametrize(
    "name,rows",
    [
        ("equal prices", [(95, 100, 94, 96)] * 4),
        ("outside bars", [(95, 110, 80, 96), (96, 120, 70, 97)]),
        ("gaps", [(95, 99, 94, 98), (110, 115, 108, 112), (95, 99, 94, 98)]),
        ("repeated", [(95, 105, 94, 104), (104, 106, 96, 97), (97, 108, 96, 107)]),
        ("already beyond", [(110, 115, 108, 112), (111, 116, 109, 113)]),
        ("no interaction", [(10, 12, 9, 11)] * 5),
    ],
)
def test_prefix_stability_on_handcrafted_edge_cases(name: str, rows: list) -> None:
    assert _prefix_violations(rows, list(GRID)) == 0, name


def test_prefix_stability_on_a_large_seeded_fixture() -> None:
    rows = seeded_rows(120, 20260731)
    assert len(derive_level_crossings(series(rows), list(GRID))) > 500
    assert _prefix_violations(rows, list(GRID)) == 0


@pytest.mark.parametrize("levels", [[UPPER_100], [LOWER_100], [UPPER_100, LOWER_100], list(GRID)])
def test_prefix_stability_across_level_set_sizes(levels: list) -> None:
    assert _prefix_violations(seeded_rows(40, 29), levels) == 0


def test_prefix_stability_on_the_real_fixture_with_swing_derived_levels() -> None:
    real = real_series()
    levels = list(structural_levels(contextual_structural_swings(real).values))
    full = derive_level_crossings(real, levels)
    assert len(full) > 0
    for n in range(len(real.candles) + 1):
        prefix = CandleSeries(
            symbol=real.symbol, timeframe=real.timeframe, candles=real.candles[:n]
        )
        assert derive_level_crossings(prefix, levels) == tuple(
            e for e in full if e.index < n
        )


def test_replay_is_deterministic() -> None:
    rows = seeded_rows(80, 31)
    first = derive_level_crossings(series(rows), list(GRID))
    for _ in range(3):
        assert derive_level_crossings(series(rows), list(GRID)) == first


def test_a_rebuilt_equal_series_replays_identically() -> None:
    rows = seeded_rows(50, 37)
    assert derive_level_crossings(series(rows), list(GRID)) == derive_level_crossings(
        series(rows), list(GRID)
    )


# ===================== 35-39. the safe pipeline =============================


def _contextual_levels(s: CandleSeries) -> ContextualSeries[PriceLevel]:
    return contextual_structural_levels(contextual_structural_swings(s))


def test_the_safe_pipeline_end_to_end() -> None:
    real = real_series()
    levels = _contextual_levels(real)
    events = contextual_level_crossings(real, levels)
    assert isinstance(events, ContextualSeries)
    assert events.identity == SeriesIdentity(symbol="BTCUSDT", timeframe="4h")
    assert len(events.values) > 0


def test_identity_is_carried_by_reference_not_rebuilt() -> None:
    swings = contextual_structural_swings(real_series())
    levels = contextual_structural_levels(swings)
    assert levels.identity is swings.identity


def test_the_crossing_wrapper_carries_the_identity_the_check_returned() -> None:
    """`CandleSeries.identity` is a projection rebuilt per access, so `is` names the
    object `require_same_identity` returned — the candle side's — not the levels'."""
    real = real_series()
    levels = ContextualSeries(identity=real.identity, values=(UPPER_100,))
    events = contextual_level_crossings(real, levels)
    assert events.identity == real.identity
    assert events.identity is not levels.identity


def test_a_different_instrument_is_rejected() -> None:
    btc = series([(95, 105, 94, 104)])
    eth = series([(95, 105, 94, 104)], symbol="ETHUSDT")
    with pytest.raises(SeriesIdentityMismatchError) as excinfo:
        contextual_level_crossings(
            eth, ContextualSeries(identity=btc.identity, values=(UPPER_100,))
        )
    assert str(excinfo.value) == (
        "subjects[1] has identity 'BTCUSDT'/'4h', expected 'ETHUSDT'/'4h'"
    )


def test_a_different_timeframe_is_rejected() -> None:
    btc4h = series([(95, 105, 94, 104)])
    btc1h = series([(95, 105, 94, 104)], timeframe="1h")
    with pytest.raises(SeriesIdentityMismatchError) as excinfo:
        contextual_level_crossings(
            btc1h, ContextualSeries(identity=btc4h.identity, values=(UPPER_100,))
        )
    assert str(excinfo.value) == (
        "subjects[1] has identity 'BTCUSDT'/'4h', expected 'BTCUSDT'/'1h'"
    )


def test_identity_comparison_does_not_normalize() -> None:
    btc = series([(95, 105, 94, 104)])
    for symbol, timeframe in (("btcusdt", "4h"), (" BTCUSDT", "4h"), ("BTCUSDT", "4H")):
        other = ContextualSeries(
            identity=SeriesIdentity(symbol=symbol, timeframe=timeframe),
            values=(UPPER_100,),
        )
        with pytest.raises(SeriesIdentityMismatchError):
            contextual_level_crossings(btc, other)


def test_a_separately_reconstructed_equal_identity_is_accepted() -> None:
    btc = series([(95, 105, 94, 104)])
    rebuilt = SeriesIdentity(symbol="BTCUSDT", timeframe="4h")
    assert rebuilt is not btc.identity
    events = contextual_level_crossings(
        btc, ContextualSeries(identity=rebuilt, values=(UPPER_100,))
    )
    assert events.identity == rebuilt


def test_an_empty_result_still_carries_a_full_identity() -> None:
    btc = series([])
    events = contextual_level_crossings(
        btc, ContextualSeries(identity=btc.identity, values=(UPPER_100,))
    )
    assert events.values == ()
    assert events.identity == SeriesIdentity(symbol="BTCUSDT", timeframe="4h")


def test_empty_levels_still_carry_a_full_identity() -> None:
    btc = series([(95, 105, 94, 104)])
    events = contextual_level_crossings(
        btc, ContextualSeries(identity=btc.identity, values=())
    )
    assert events.values == ()
    assert events.identity == btc.identity


def test_empty_contextual_swings_yield_empty_levels_with_identity() -> None:
    empty = series([])
    levels = _contextual_levels(empty)
    assert levels.values == ()
    assert levels.identity == SeriesIdentity(symbol="BTCUSDT", timeframe="4h")


def test_no_pipeline_function_accepts_an_identity_argument() -> None:
    import inspect

    for function in (contextual_structural_levels, contextual_level_crossings):
        parameters = set(inspect.signature(function).parameters)
        assert not any("identity" in p for p in parameters), function.__name__


def test_a_bare_payload_where_an_envelope_belongs_is_rejected() -> None:
    with pytest.raises(TypeError) as excinfo:
        contextual_structural_levels(())
    assert str(excinfo.value) == "swings must be a ContextualSeries, got tuple"
    with pytest.raises(TypeError) as excinfo:
        contextual_level_crossings(series([]), ())
    assert str(excinfo.value) == "levels must be a ContextualSeries, got tuple"


def test_context_substitution_is_unrepresentable() -> None:
    """The only identity an output can carry is the one both inputs already shared."""
    btc = series([(95, 105, 94, 104)])
    events = contextual_level_crossings(
        btc, ContextualSeries(identity=btc.identity, values=(UPPER_100,))
    )
    with pytest.raises((AttributeError, TypeError)):
        events.identity = SeriesIdentity(symbol="ETHUSDT", timeframe="4h")


# ---- context-free / context-aware equivalence ----

_EQUIVALENCE_CASES = {
    "empty candles": ([], [UPPER_100]),
    "empty levels": ([(95, 105, 94, 104)], []),
    "both empty": ([], []),
    "one upper level": ([(95, 105, 94, 104)], [UPPER_100]),
    "one lower level": ([(105, 108, 95, 96)], [LOWER_100]),
    "equal touch": ([(95, 100, 94, 96)], [UPPER_100]),
    "wick breach": ([(95, 105, 94, 96)], [UPPER_100]),
    "close breach": ([(95, 105, 94, 104)], [UPPER_100]),
    "gap breach": ([(95, 99, 94, 98), (110, 115, 108, 112)], [UPPER_100]),
    "outside bar": ([(95, 110, 80, 96)], [UPPER_100, PriceLevel(90.0, LevelSide.LOWER)]),
    "multiple levels": ([(95, 110, 80, 96)], list(GRID)),
    "duplicate prices": (
        [(95, 105, 94, 104)],
        [
            PriceLevel(100.0, LevelSide.UPPER, origin(3, StructuralSwingLabel.HIGHER_HIGH)),
            PriceLevel(100.0, LevelSide.UPPER, origin(7, StructuralSwingLabel.EQUAL_HIGH)),
        ],
    ),
    "repeated interactions": (
        [(95, 105, 94, 104), (104, 106, 96, 97), (97, 108, 96, 107)],
        [UPPER_100],
    ),
}


@pytest.mark.parametrize("name", sorted(_EQUIVALENCE_CASES))
def test_context_free_and_context_aware_payloads_are_identical(name: str) -> None:
    rows, levels = _EQUIVALENCE_CASES[name]
    candles = series(rows)
    bare = derive_level_crossings(candles, levels)
    wrapped = contextual_level_crossings(
        candles, ContextualSeries(identity=candles.identity, values=tuple(levels))
    )
    assert wrapped.values == bare


def test_the_level_wrapper_payload_equals_the_bare_projection() -> None:
    swings = contextual_structural_swings(real_series())
    assert contextual_structural_levels(swings).values == structural_levels(
        swings.values
    )


def test_identity_cannot_change_a_payload() -> None:
    rows = seeded_rows(40, 41)
    payloads = []
    for symbol, timeframe in (("BTCUSDT", "4h"), ("ETHUSDT", "1h"), ("banana", "banana")):
        candles = series(rows, symbol=symbol, timeframe=timeframe)
        events = contextual_level_crossings(
            candles, ContextualSeries(identity=candles.identity, values=GRID)
        )
        payloads.append(
            [(e.index, e.kind, e.mechanism, e.level) for e in events.values]
        )
    assert payloads[0] == payloads[1] == payloads[2]


# ===================== 40-43. swing-derived levels ==========================


def test_a_swing_high_yields_an_upper_level_and_a_swing_low_a_lower_one() -> None:
    high = structural_swing(
        swing_point(1, 100.0, SwingType.HIGH), swing_point(5, 110.0, SwingType.HIGH)
    )
    low = structural_swing(
        swing_point(2, 90.0, SwingType.LOW), swing_point(6, 80.0, SwingType.LOW)
    )
    assert structural_levels([high])[0].side is LevelSide.UPPER
    assert structural_levels([low])[0].side is LevelSide.LOWER


def test_swing_derived_level_provenance_is_preserved_exactly() -> None:
    swing = structural_swing(
        swing_point(1, 100.0, SwingType.HIGH), swing_point(5, 110.0, SwingType.HIGH)
    )
    level = structural_levels([swing])[0]
    assert level.price == swing.comparison.current.price
    assert level.origin.index == swing.comparison.current.index
    assert level.origin.timestamp == swing.comparison.current.timestamp
    assert level.origin.label is swing.label is StructuralSwingLabel.HIGHER_HIGH


@pytest.mark.parametrize(
    "prices,type_,label,side",
    [
        ((100.0, 100.0), SwingType.HIGH, StructuralSwingLabel.EQUAL_HIGH, LevelSide.UPPER),
        ((100.0, 100.0), SwingType.LOW, StructuralSwingLabel.EQUAL_LOW, LevelSide.LOWER),
        ((100.0, 90.0), SwingType.HIGH, StructuralSwingLabel.LOWER_HIGH, LevelSide.UPPER),
        ((90.0, 100.0), SwingType.LOW, StructuralSwingLabel.HIGHER_LOW, LevelSide.LOWER),
        ((90.0, 100.0), SwingType.HIGH, StructuralSwingLabel.HIGHER_HIGH, LevelSide.UPPER),
        ((100.0, 90.0), SwingType.LOW, StructuralSwingLabel.LOWER_LOW, LevelSide.LOWER),
    ],
)
def test_every_structural_label_maps_to_the_right_side(
    prices: tuple, type_: SwingType, label: StructuralSwingLabel, side: LevelSide
) -> None:
    swing = structural_swing(
        swing_point(1, prices[0], type_), swing_point(5, prices[1], type_)
    )
    assert swing.label is label
    level = structural_levels([swing])[0]
    assert level.side is side
    assert level.origin.label is label


def test_an_equal_high_is_not_renamed_or_folded_away() -> None:
    swing = structural_swing(
        swing_point(1, 100.0, SwingType.HIGH), swing_point(5, 100.0, SwingType.HIGH)
    )
    assert structural_levels([swing])[0].origin.label is StructuralSwingLabel.EQUAL_HIGH


def test_two_swings_at_the_same_price_yield_two_distinct_levels() -> None:
    a = structural_swing(
        swing_point(1, 90.0, SwingType.HIGH), swing_point(5, 100.0, SwingType.HIGH)
    )
    b = structural_swing(
        swing_point(5, 100.0, SwingType.HIGH), swing_point(9, 100.0, SwingType.HIGH)
    )
    got = structural_levels([a, b])
    assert len(got) == 2
    assert got[0] != got[1]
    assert got[0].price == got[1].price == 100.0


def test_outside_bar_derived_swing_provenance_survives() -> None:
    """One candle yielding both a HIGH and a LOW gives two levels sharing an origin index."""
    rows = [
        (100, 101, 99, 100),
        (100, 102, 98, 100),
        (100, 106, 94, 100),   # first HIGH and first LOW, at index 2 (no level, D2)
        (100, 102, 98, 100),
        (100, 101, 99, 100),
        (100, 103, 97, 100),
        (100, 110, 80, 100),   # outside bar at index 6: second HIGH and second LOW
        (100, 103, 97, 100),
        (100, 102, 98, 100),
    ]
    points = detect_swings(series(rows), left_bars=2, right_bars=2)
    assert {p.type for p in points if p.index == 6} == {SwingType.HIGH, SwingType.LOW}
    swings = label_swing_sequence(compare_swing_sequence(points))
    got = structural_levels(swings)
    sides = {lv.side for lv in got if lv.origin.index == 6}
    assert sides == {LevelSide.UPPER, LevelSide.LOWER}
    assert {lv.price for lv in got if lv.origin.index == 6} == {110.0, 80.0}


def test_the_first_swing_of_each_type_yields_no_level() -> None:
    """Documented limitation D2, pinned so a future widening is a deliberate change."""
    real = real_series()
    points = detect_swings(real)
    got = structural_levels(contextual_structural_swings(real).values)
    assert len(points) - len(got) == 2
    firsts = {}
    for point in points:
        firsts.setdefault(point.type, point)
    origins = {(lv.origin.index, lv.side) for lv in got}
    for type_, point in firsts.items():
        side = LevelSide.UPPER if type_ is SwingType.HIGH else LevelSide.LOWER
        assert (point.index, side) not in origins


def test_structural_levels_preserves_input_order() -> None:
    real = real_series()
    swings = contextual_structural_swings(real).values
    got = structural_levels(swings)
    assert [lv.origin.index for lv in got] == [
        s.comparison.current.index for s in swings
    ]


def test_structural_levels_on_an_empty_run() -> None:
    assert structural_levels([]) == ()


def test_the_full_documented_pipeline_composes() -> None:
    real = real_series()
    swings = contextual_structural_swings(real)
    levels = contextual_structural_levels(swings)
    events = contextual_level_crossings(real, levels)
    assert swings.identity is levels.identity
    assert events.identity == levels.identity
    assert all(isinstance(e, LevelCrossingEvent) for e in events.values)


# ===================== validation ==========================================


@pytest.mark.parametrize(
    "kwargs,message",
    [
        (dict(price="x", side=LevelSide.UPPER), "price must be a number, got str"),
        (dict(price=True, side=LevelSide.UPPER), "price must be a number, got bool"),
        (dict(price=1.0, side="upper"), "side must be a LevelSide, got str"),
        (dict(price=1.0, side=LevelSide.UPPER, origin=3), "origin must be a LevelOrigin or None, got int"),
    ],
)
def test_price_level_type_validation(kwargs: dict, message: str) -> None:
    with pytest.raises(TypeError) as excinfo:
        PriceLevel(**kwargs)
    assert str(excinfo.value) == message


def test_a_non_finite_level_price_is_rejected() -> None:
    with pytest.raises(ValueError) as excinfo:
        PriceLevel(float("inf"), LevelSide.UPPER)
    assert str(excinfo.value) == "price must be a finite number"
    with pytest.raises(ValueError):
        PriceLevel(float("nan"), LevelSide.UPPER)


def test_a_level_may_not_contradict_its_own_provenance() -> None:
    with pytest.raises(ValueError) as excinfo:
        PriceLevel(
            100.0, LevelSide.UPPER, origin(3, StructuralSwingLabel.EQUAL_LOW)
        )
    assert str(excinfo.value) == (
        "side 'upper' does not match the origin label (equal_low); expected 'lower'"
    )


@pytest.mark.parametrize("label", list(StructuralSwingLabel))
def test_every_label_has_exactly_one_permitted_side(label: StructuralSwingLabel) -> None:
    good = models_mod._SIDE_BY_LABEL[label]
    bad = LevelSide.LOWER if good is LevelSide.UPPER else LevelSide.UPPER
    PriceLevel(100.0, good, origin(1, label))
    with pytest.raises(ValueError):
        PriceLevel(100.0, bad, origin(1, label))


@pytest.mark.parametrize(
    "kwargs,message",
    [
        (dict(index="1"), "index must be an int, got str"),
        (dict(index=True), "index must be an int, got bool"),
        (dict(timestamp="now"), "timestamp must be a datetime, got str"),
        (dict(label="higher_high"), "label must be a StructuralSwingLabel, got str"),
    ],
)
def test_level_origin_type_validation(kwargs: dict, message: str) -> None:
    base = dict(index=1, timestamp=_BASE, label=StructuralSwingLabel.HIGHER_HIGH)
    with pytest.raises(TypeError) as excinfo:
        LevelOrigin(**{**base, **kwargs})
    assert str(excinfo.value) == message


def test_a_negative_origin_index_is_rejected() -> None:
    with pytest.raises(ValueError) as excinfo:
        LevelOrigin(index=-1, timestamp=_BASE, label=StructuralSwingLabel.HIGHER_HIGH)
    assert str(excinfo.value) == "index cannot be negative, got -1"


def test_a_negative_event_index_is_rejected() -> None:
    c = candle(0, 95, 105, 94, 104)
    with pytest.raises(ValueError) as excinfo:
        LevelCrossingEvent(
            level=UPPER_100,
            candle=c,
            index=-1,
            kind=CrossingKind.CLOSE_BREACH,
            mechanism=CrossingMechanism.WITHIN_RANGE,
        )
    assert str(excinfo.value) == "index cannot be negative, got -1"


def test_an_event_cannot_claim_a_kind_its_own_candle_contradicts() -> None:
    c = candle(0, 95, 105, 94, 104)  # close breach
    with pytest.raises(ValueError) as excinfo:
        LevelCrossingEvent(
            level=UPPER_100,
            candle=c,
            index=0,
            kind=CrossingKind.TOUCH,
            mechanism=CrossingMechanism.WITHIN_RANGE,
        )
    assert str(excinfo.value) == (
        "kind 'touch' does not match the candle against the level (upper 100.0); "
        "expected 'close_breach'"
    )


def test_an_event_cannot_record_a_candle_that_never_reached_the_level() -> None:
    with pytest.raises(ValueError) as excinfo:
        LevelCrossingEvent(
            level=UPPER_100,
            candle=candle(0, 95, 96, 94, 95),
            index=0,
            kind=CrossingKind.TOUCH,
            mechanism=CrossingMechanism.WITHIN_RANGE,
        )
    assert str(excinfo.value) == (
        "candle does not reach the level (upper 100.0); no crossing to record"
    )


def test_an_event_cannot_claim_within_range_for_a_candle_wholly_beyond() -> None:
    with pytest.raises(ValueError) as excinfo:
        LevelCrossingEvent(
            level=UPPER_100,
            candle=candle(0, 110, 115, 108, 112),
            index=0,
            kind=CrossingKind.CLOSE_BREACH,
            mechanism=CrossingMechanism.WITHIN_RANGE,
        )
    assert str(excinfo.value) == (
        "mechanism 'within_range' does not match the candle, which lies wholly "
        "beyond the level (upper 100.0)"
    )


def test_an_event_cannot_claim_a_gap_for_a_candle_that_traded_at_the_level() -> None:
    with pytest.raises(ValueError) as excinfo:
        LevelCrossingEvent(
            level=UPPER_100,
            candle=candle(0, 95, 105, 94, 104),
            index=0,
            kind=CrossingKind.CLOSE_BREACH,
            mechanism=CrossingMechanism.GAPPED_BEYOND,
        )
    assert str(excinfo.value) == (
        "mechanism 'gapped_beyond' does not match the candle, which reaches the "
        "level (upper 100.0) within its range; expected 'within_range'"
    )


@pytest.mark.parametrize(
    "kwargs,message",
    [
        (dict(level=100.0), "level must be a PriceLevel, got float"),
        (dict(candle="c"), "candle must be a Candle, got str"),
        (dict(index="0"), "index must be an int, got str"),
        (dict(index=True), "index must be an int, got bool"),
        (dict(kind="touch"), "kind must be a CrossingKind, got str"),
        (dict(mechanism="within_range"), "mechanism must be a CrossingMechanism, got str"),
    ],
)
def test_event_type_validation(kwargs: dict, message: str) -> None:
    base = dict(
        level=UPPER_100,
        candle=candle(0, 95, 105, 94, 104),
        index=0,
        kind=CrossingKind.CLOSE_BREACH,
        mechanism=CrossingMechanism.WITHIN_RANGE,
    )
    with pytest.raises(TypeError) as excinfo:
        LevelCrossingEvent(**{**base, **kwargs})
    assert str(excinfo.value) == message


@pytest.mark.parametrize(
    "call,message",
    [
        (lambda: crossing_kind("c", UPPER_100), "candle must be a Candle, got str"),
        (
            lambda: crossing_kind(candle(0, 1, 1, 1, 1), 100.0),
            "level must be a PriceLevel, got float",
        ),
        (
            lambda: derive_level_crossings("s", []),
            "series must be a CandleSeries, got str",
        ),
        (
            lambda: derive_level_crossings(series([]), "levels"),
            "levels must be a sequence of PriceLevel, got str",
        ),
        (
            lambda: derive_level_crossings(series([]), [UPPER_100, 100.0]),
            "levels[1] must be a PriceLevel, got float",
        ),
        (
            lambda: structural_levels("swings"),
            "swings must be a sequence of StructuralSwing, got str",
        ),
        (
            lambda: structural_levels([1]),
            "swings[0] must be a StructuralSwing, got int",
        ),
        (
            lambda: contextual_level_crossings("s", ContextualSeries(
                identity=SeriesIdentity(symbol="B", timeframe="4h"), values=())),
            "series must be a CandleSeries, got str",
        ),
    ],
)
def test_argument_validation_messages(call, message: str) -> None:
    with pytest.raises(TypeError) as excinfo:
        call()
    assert str(excinfo.value) == message


def test_a_generator_of_levels_is_rejected_rather_than_silently_consumed() -> None:
    with pytest.raises(TypeError):
        derive_level_crossings(series([]), (lv for lv in GRID))


def test_unsorted_candles_are_impossible_by_construction() -> None:
    """`CandleSeries` already refuses them; this package inherits rather than re-checks."""
    with pytest.raises(ValueError) as excinfo:
        CandleSeries(
            symbol="BTCUSDT",
            timeframe="4h",
            candles=(candle(1, 1, 1, 1, 1), candle(0, 1, 1, 1, 1)),
        )
    assert str(excinfo.value) == "candle timestamps must be strictly increasing"


def test_duplicate_candle_timestamps_are_impossible_by_construction() -> None:
    with pytest.raises(ValueError):
        CandleSeries(
            symbol="BTCUSDT",
            timeframe="4h",
            candles=(candle(0, 1, 1, 1, 1), candle(0, 1, 1, 1, 1)),
        )


def test_forming_candles_are_excluded() -> None:
    forming = Candle(
        timestamp=_BASE + timedelta(hours=4),
        symbol="BTCUSDT",
        timeframe="4h",
        open=95.0, high=105.0, low=94.0, close=104.0, volume=1.0, is_closed=False,
    )
    s = CandleSeries(
        symbol="BTCUSDT", timeframe="4h", candles=(candle(0, 95, 96, 94, 95), forming)
    )
    assert derive_level_crossings(s, [UPPER_100]) == ()


def test_indices_are_positions_in_the_closed_sequence() -> None:
    forming = Candle(
        timestamp=_BASE + timedelta(hours=8),
        symbol="BTCUSDT",
        timeframe="4h",
        open=95.0, high=96.0, low=94.0, close=95.0, volume=1.0, is_closed=False,
    )
    s = CandleSeries(
        symbol="BTCUSDT",
        timeframe="4h",
        candles=(candle(0, 95, 96, 94, 95), candle(1, 95, 105, 94, 104), forming),
    )
    assert [e.index for e in derive_level_crossings(s, [UPPER_100])] == [1]


def test_the_event_index_matches_the_swing_index_convention() -> None:
    """Both are positions in `series.closed().candles`, so BOS can join on index."""
    real = real_series()
    points = detect_swings(real)
    events = derive_level_crossings(
        real, list(structural_levels(contextual_structural_swings(real).values))
    )
    closed = real.closed().candles
    for point in points:
        assert closed[point.index].timestamp == point.timestamp
    for event in events:
        assert closed[event.index] is event.candle


# ===================== property and combinatorial tests ====================


def test_raising_a_high_cannot_remove_a_strict_upper_wick_breach() -> None:
    for row in seeded_rows(120, 43):
        base = candle(0, *row)
        if crossing_kind(base, UPPER_100) not in (
            CrossingKind.WICK_BREACH,
            CrossingKind.CLOSE_BREACH,
        ):
            continue
        raised = candle(0, row[0], row[1] + 5.0, row[2], row[3])
        assert crossing_kind(raised, UPPER_100) in (
            CrossingKind.WICK_BREACH,
            CrossingKind.CLOSE_BREACH,
        )


def test_lowering_a_low_cannot_remove_a_strict_lower_breach() -> None:
    for row in seeded_rows(120, 47):
        base = candle(0, *row)
        if crossing_kind(base, LOWER_100) not in (
            CrossingKind.WICK_BREACH,
            CrossingKind.CLOSE_BREACH,
        ):
            continue
        lowered = candle(0, row[0], row[1], max(row[2] - 5.0, 0.0), row[3])
        assert crossing_kind(lowered, LOWER_100) in (
            CrossingKind.WICK_BREACH,
            CrossingKind.CLOSE_BREACH,
        )


def test_adding_future_candles_cannot_modify_earlier_events() -> None:
    rows = seeded_rows(60, 53)
    for n in range(1, len(rows)):
        short = derive_level_crossings(series(rows[:n]), list(GRID))
        long = derive_level_crossings(series(rows[: n + 1]), list(GRID))
        assert long[: len(short)] == short


def test_no_event_references_a_candle_outside_the_input() -> None:
    rows = seeded_rows(50, 59)
    s = series(rows)
    for event in derive_level_crossings(s, list(GRID)):
        assert event.candle in s.candles
        assert s.closed().candles[event.index] is event.candle


def test_no_event_references_a_level_outside_the_input() -> None:
    for event in derive_level_crossings(series(seeded_rows(50, 61)), list(GRID)):
        assert any(event.level is lv for lv in GRID)


def test_every_event_satisfies_the_crossing_predicate() -> None:
    for event in derive_level_crossings(series(seeded_rows(80, 67)), list(GRID)):
        assert crossing_kind(event.candle, event.level) is event.kind


def test_every_event_timestamp_is_its_candles_timestamp() -> None:
    for event in derive_level_crossings(series(seeded_rows(50, 71)), list(GRID)):
        assert event.timestamp is event.candle.timestamp


def test_the_event_timestamp_is_the_crossing_bars_not_the_levels_origin() -> None:
    """Review 15 fact 5: a swing carries its *pivot's* time, a crossing a different bar's.

    Exercised with a **provenanced** level whose origin timestamp differs from
    every crossing candle's, so a projection that fell back to the origin would
    be caught. An origin-less level cannot catch it.
    """
    provenanced = PriceLevel(
        100.0, LevelSide.UPPER, origin(0, StructuralSwingLabel.HIGHER_HIGH)
    )
    events = derive_level_crossings(
        series([(95, 96, 94, 95), (95, 105, 94, 104), (104, 106, 96, 97)]),
        [provenanced],
    )
    assert [e.index for e in events] == [1, 2]
    for event in events:
        assert event.timestamp is event.candle.timestamp
        assert event.timestamp != provenanced.origin.timestamp
        assert event.timestamp == _BASE + timedelta(hours=4 * event.index)


def test_swing_derived_events_carry_the_crossing_bars_timestamp() -> None:
    real = real_series()
    closed = real.closed().candles
    for event in contextual_level_crossings(real, _contextual_levels(real)).values:
        assert event.timestamp == closed[event.index].timestamp
        assert event.timestamp is event.candle.timestamp


def test_permuting_levels_cannot_change_the_normalized_event_set() -> None:
    rows = seeded_rows(30, 73)
    reference = derive_level_crossings(series(rows), list(GRID))
    rng = random.Random(73)
    for _ in range(10):
        shuffled = list(GRID)
        rng.shuffle(shuffled)
        assert derive_level_crossings(series(rows), shuffled) == reference


def test_repeated_execution_produces_identical_results() -> None:
    rows = seeded_rows(40, 79)
    results = [derive_level_crossings(series(rows), list(GRID)) for _ in range(5)]
    assert all(r == results[0] for r in results)


def test_event_provenance_survives_envelope_wrapping() -> None:
    real = real_series()
    levels = _contextual_levels(real)
    events = contextual_level_crossings(real, levels)
    for event in events.values:
        assert event.level.origin is not None
        assert any(event.level is lv for lv in levels.values)


def test_an_exhaustive_small_state_space_is_consistent() -> None:
    """Every OHLC arrangement over a tiny price grid, against both level sides."""
    grid = [98.0, 99.0, 100.0, 101.0, 102.0]
    checked = 0
    for o, h, l, c in itertools.product(grid, repeat=4):
        if h < max(o, c) or l > min(o, c) or h < l:
            continue
        bar = candle(0, o, h, l, c)
        for level in (UPPER_100, LOWER_100):
            kind = crossing_kind(bar, level)
            extreme = bar.high if level.side is LevelSide.UPPER else bar.low
            if level.side is LevelSide.UPPER:
                beyond, closed_beyond = extreme > 100.0, bar.close > 100.0
            else:
                beyond, closed_beyond = extreme < 100.0, bar.close < 100.0
            if extreme == 100.0:
                assert kind is CrossingKind.TOUCH
            elif not beyond:
                assert kind is None
            elif closed_beyond:
                assert kind is CrossingKind.CLOSE_BREACH
            else:
                assert kind is CrossingKind.WICK_BREACH
            checked += 1
    assert checked > 200


def test_an_exhaustive_two_candle_space_is_prefix_stable() -> None:
    grid = [(95, 99, 94, 98), (95, 100, 94, 96), (95, 105, 94, 104), (110, 115, 108, 112),
            (95, 110, 80, 96)]
    for first, second in itertools.product(grid, repeat=2):
        assert _prefix_violations([first, second], [UPPER_100, LOWER_100]) == 0


# ===================== exports and architecture guards =====================


def test_the_public_api_is_exactly_thirteen_names() -> None:
    assert set(lc.__all__) == {
        "LevelSide",
        "CrossingKind",
        "CrossingMechanism",
        "LevelOrigin",
        "PriceLevel",
        "LevelCrossingEvent",
        "LevelCrossingError",
        "DuplicateLevelError",
        "crossing_kind",
        "derive_level_crossings",
        "structural_levels",
        "contextual_structural_levels",
        "contextual_level_crossings",
    }
    assert len(lc.__all__) == 13


def test_every_exported_name_resolves() -> None:
    for name in lc.__all__:
        assert hasattr(lc, name), name


def test_no_submodule_collides_with_a_public_name() -> None:
    import pkgutil

    submodules = {m.name for m in pkgutil.iter_modules(lc.__path__)}
    assert submodules == {"crossing", "levels", "models", "pipeline"}
    assert submodules & set(lc.__all__) == set()


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
        "_crossing_kind",
        "_is_wholly_beyond",
        "_level_key",
        "_event_key",
        "_mechanism_for",
        "_require_distinct",
        "_require_envelope",
        "_validate_event_order",
        "_SIDE_BY_LABEL",
        "_SIDE_RANK",
        "_LABEL_RANK",
        "_extreme_for",
    ):
        assert private not in lc.__all__, private
        assert not hasattr(lc, private), private


def test_no_mutable_public_object_is_exported() -> None:
    for name in lc.__all__:
        assert not isinstance(getattr(lc, name), (list, dict, set)), name


def test_the_authoritative_mappings_are_immutable() -> None:
    for mapping in (
        models_mod._SIDE_BY_LABEL,
        models_mod._SIDE_RANK,
        models_mod._LABEL_RANK,
    ):
        with pytest.raises(TypeError):
            mapping[LevelSide.UPPER] = 99


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


def test_imports_only_the_three_permitted_packages() -> None:
    assert _internal_imports() <= {
        "fmis.data",
        "fmis.market_structure",
        "fmis.series_context",
        "fmis.level_crossing.crossing",
        "fmis.level_crossing.levels",
        "fmis.level_crossing.models",
        "fmis.level_crossing.pipeline",
    }


def test_does_not_import_structural_trend() -> None:
    """Trend must never be an input to a level fact. Review 15, ADR-0019 1.1."""
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
        if internal.startswith("fmis.level_crossing"):
            continue
        assert not internal.startswith("fmis.market_structure."), internal
        assert not internal.startswith("fmis.series_context."), internal
        assert not internal.startswith("fmis.data."), internal


def test_nothing_imports_level_crossing() -> None:
    root = PACKAGE_DIR.parent
    for py in root.rglob("*.py"):
        if py.parent == PACKAGE_DIR:
            continue
        assert "fmis.level_crossing" not in py.read_text(), py


def test_no_import_cycle_exists() -> None:
    import subprocess

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import fmis.data, fmis.market_structure, fmis.series_context; "
            "assert 'fmis.level_crossing' not in sys.modules; print('ok')",
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
                if any(
                    isinstance(t, ast.Name) and t.id == "__all__" for t in targets
                ):
                    continue  # the export list is read-only by convention, like every sibling
                if isinstance(node.value, (ast.List, ast.Dict, ast.Set)):
                    raise AssertionError(f"module-level mutable literal in {py}")


def test_no_wall_clock_access() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        source = py.read_text()
        for banned in ("datetime.now", "utcnow", "time.time", "time.monotonic"):
            assert banned not in source, (py, banned)


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
    """ADR-0013 4 and review 9: comparison is exact, and nothing here softens it."""
    for py in PACKAGE_DIR.glob("*.py"):
        source = py.read_text()
        tree = ast.parse(source)
        names = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        } | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        for banned in (
            "isclose",
            "epsilon",
            "atol",
            "rtol",
            "approx",
            "round",
            "Decimal",
            "quantize",
        ):
            assert banned not in names, (py, banned)


def test_the_crossing_rule_has_exactly_one_implementation() -> None:
    """Both the public predicate and the batch call `_crossing_kind`; neither re-derives."""
    source = (PACKAGE_DIR / "crossing.py").read_text()
    tree = ast.parse(source)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_crossing_kind" in called
    # the comparison operators live in models, not here
    comparisons = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Compare)
        and any(isinstance(op, (ast.Gt, ast.Lt)) for op in n.ops)
    ]
    for node in comparisons:
        segment = ast.get_source_segment(source, node) or ""
        assert "price" not in segment and "high" not in segment and "low" not in segment, (
            segment
        )


def test_the_pipeline_delegates_and_never_re_derives() -> None:
    tree = ast.parse((PACKAGE_DIR / "pipeline.py").read_text())
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for required in (
        "derive_level_crossings",
        "structural_levels",
        "require_same_identity",
        "ContextualSeries",
    ):
        assert required in called, required


def test_the_pipeline_performs_no_arithmetic_and_reads_no_price() -> None:
    tree = ast.parse((PACKAGE_DIR / "pipeline.py").read_text())
    for node in ast.walk(tree):
        assert not isinstance(node, ast.BinOp), ast.dump(node)
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("high", "low", "open", "close", "price"), node.attr


def _referenced_names(py: Path) -> set[str]:
    """Every identifier the module actually *uses* — prose in docstrings excluded.

    A text scan would flag a docstring that merely names an upstream helper while
    explaining why this package delegates to it, which is the opposite of the
    duplication being guarded against.
    """
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


def test_no_swing_logic_is_duplicated() -> None:
    """Detection, comparison and labelling keep their single implementation upstream."""
    for py in PACKAGE_DIR.glob("*.py"):
        used = _referenced_names(py)
        for banned in (
            "left_bars",
            "right_bars",
            "detect_swings",
            "_is_swing_high",
            "_is_swing_low",
            "_relation_for",
            "_label_for",
            "compare_swings",
            "label_swing",
            "SwingRelation",
        ):
            assert banned not in used, (py, banned)


def test_no_structural_state_or_trend_logic_is_duplicated() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        used = _referenced_names(py)
        for banned in (
            "StructuralSequenceState",
            "StructuralSequenceStateSnapshot",
            "StructuralTrendSnapshot",
            "MINIMUM_DIRECTIONAL_SHIFTS",
            "_advance",
            "SHIFTED_HIGHER",
            "derive_structural_trend_history",
        ):
            assert banned not in used, (py, banned)


def test_no_identity_logic_is_duplicated() -> None:
    """Identity comparison belongs to `require_same_identity` and nowhere else."""
    for py in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("symbol", "timeframe"):
                raise AssertionError(f"{py} reads an identity field directly")


def test_no_trading_vocabulary_in_the_package() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
        } | {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for banned in (
            "bos",
            "choch",
            "entry",
            "exit",
            "stop_loss",
            "take_profit",
            "signal",
            "long",
            "short",
            "buy",
            "sell",
            "bullish",
            "bearish",
            "regime",
            "confidence",
            "protected",
            "inducement",
            "sweep",
        ):
            assert banned not in {n.lower() for n in names}, (py, banned)


def test_no_enum_member_names_a_trading_concept() -> None:
    for enum in (LevelSide, CrossingKind, CrossingMechanism):
        for member in enum:
            lowered = member.name.lower()
            for banned in ("bos", "choch", "break_of", "bullish", "bearish", "signal"):
                assert banned not in lowered, (enum.__name__, member.name)


# ===================== nothing upstream changed ============================


def test_existing_swing_behaviour_is_unchanged() -> None:
    real = real_series()
    points = detect_swings(real)
    assert len(points) == 5
    assert all(isinstance(p, SwingPoint) for p in points)
    assert [p.index for p in points] == sorted(p.index for p in points)
    for point in points:
        closed = real.closed().candles[point.index]
        assert point.price == (
            closed.high if point.type is SwingType.HIGH else closed.low
        )


def test_existing_structural_state_behaviour_is_unchanged() -> None:
    real = real_series()
    swings = contextual_structural_swings(real)
    history = contextual_structural_state_history(swings)
    assert history.identity is swings.identity
    assert len(history.values) >= 1


def test_existing_trend_behaviour_is_unchanged() -> None:
    real = real_series()
    history = contextual_structural_trend_history(
        contextual_structural_state_history(contextual_structural_swings(real))
    )
    assert len(history.values) >= 1


def test_existing_series_identity_behaviour_is_unchanged() -> None:
    real = real_series()
    assert real.identity == SeriesIdentity(symbol="BTCUSDT", timeframe="4h")
    assert real.identity is not real.identity  # a projection, rebuilt each access


def test_the_series_context_public_api_did_not_change() -> None:
    import fmis.series_context as sc

    assert len(sc.__all__) == 7


def test_the_market_structure_public_api_did_not_change() -> None:
    import fmis.market_structure as ms

    assert len(ms.__all__) == 19


# ===================== future consumer shapes ==============================


def test_a_future_bos_layer_can_consume_events_without_re_reading_ohlc() -> None:
    """Everything a level-based break needs is already on the event."""
    real = real_series()
    events = contextual_level_crossings(real, _contextual_levels(real))

    def hypothetical_bos(history: ContextualSeries[LevelCrossingEvent]) -> tuple:
        return tuple(
            (event.index, event.timestamp, event.level.side, event.level.price,
             event.level.origin.index, event.level.origin.label)
            for event in history.values
            if event.kind is CrossingKind.CLOSE_BREACH
            and event.index >= event.level.origin.index
        )

    got = hypothetical_bos(events)
    assert isinstance(got, tuple)
    # and it needed no candle field
    assert all(len(row) == 6 for row in got)


def test_a_future_choch_layer_consumes_the_bos_sequence_not_candles() -> None:
    """Review 15: CHoCH is defined over the BOS sequence and never sees a crossing."""
    breaks = ((1, LevelSide.UPPER), (5, LevelSide.LOWER), (9, LevelSide.LOWER))
    changes = tuple(
        b for a, b in zip(breaks, breaks[1:]) if a[1] is not b[1]
    )
    assert changes == ((5, LevelSide.LOWER),)


def test_the_event_is_sufficient_to_reconstruct_the_crossing_decision() -> None:
    for event in derive_level_crossings(series(seeded_rows(40, 83)), list(GRID)):
        assert crossing_kind(event.candle, event.level) is event.kind
        assert (event.mechanism is CrossingMechanism.WITHIN_RANGE) is not (
            models_mod._is_wholly_beyond(event.candle, event.level)
        )


# ===================== adversarial numerics ================================


def test_very_large_prices() -> None:
    big = 1e300
    s = CandleSeries(
        symbol="BTCUSDT",
        timeframe="4h",
        candles=(
            Candle(
                timestamp=_BASE, symbol="BTCUSDT", timeframe="4h",
                open=big, high=big * 1.1, low=big * 0.9, close=big * 1.05,
                volume=1.0, is_closed=True,
            ),
        ),
    )
    events = derive_level_crossings(s, [PriceLevel(big, LevelSide.UPPER)])
    assert events[0].kind is CrossingKind.CLOSE_BREACH


def test_a_zero_price_level() -> None:
    s = CandleSeries(
        symbol="BTCUSDT",
        timeframe="4h",
        candles=(
            Candle(
                timestamp=_BASE, symbol="BTCUSDT", timeframe="4h",
                open=0.0, high=1.0, low=0.0, close=0.5, volume=0.0, is_closed=True,
            ),
        ),
    )
    assert derive_level_crossings(s, [PriceLevel(0.0, LevelSide.LOWER)])[0].kind is (
        CrossingKind.TOUCH
    )


def test_a_negative_level_price_is_representable_though_candles_are_not() -> None:
    """`PriceLevel` does not inherit `Candle`'s non-negativity, and says so by behaving."""
    level = PriceLevel(-5.0, LevelSide.LOWER)
    assert level.price == -5.0
    assert derive_level_crossings(series([(1, 2, 0, 1)]), [level]) == ()


def test_unicode_and_whitespace_identities_are_distinct() -> None:
    for symbol in ("BTC⁄USDT", " BTCUSDT", "btcusdt"):
        left = SeriesIdentity(symbol=symbol, timeframe="4h")
        right = SeriesIdentity(symbol="BTCUSDT", timeframe="4h")
        assert left != right
