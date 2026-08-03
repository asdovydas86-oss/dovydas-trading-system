"""Tests for deterministic structural swing labels (fmis.market_structure).

Hand-built comparisons pin the six-way mapping and every rejection. Randomized
runs then assert the properties, using an oracle that builds the label name from
the naming convention (`"{relation}_{type}"`) rather than re-listing the
production lookup table, so a wrong table entry cannot pass unnoticed.
"""

from __future__ import annotations

import ast
import random
import sys
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import fmis.market_structure as ms
from fmis.data import Candle, CandleSeries
from fmis.market_structure import (
    StructuralSwing,
    StructuralSwingLabel,
    SwingComparison,
    SwingPoint,
    SwingRelation,
    SwingType,
    compare_swing_sequence,
    compare_swings,
    detect_swings,
    label_swing,
    label_swing_sequence,
)

#: The confirmation window every hand-built fixture point is confirmed under.
#: Required since Milestone AH: a swing that does not state its window cannot
#: say when it became knowable, and nothing downstream may assume one.
CB = 2

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
PACKAGE_DIR = Path(ms.__file__).parent
SRC = PACKAGE_DIR.parent


def sp(index: int, price: float, type: SwingType = SwingType.HIGH) -> SwingPoint:
    return SwingPoint(index, _BASE + timedelta(hours=4 * index), price, type, confirmation_bars=CB)


def pair(
    previous_price: float, current_price: float, type: SwingType = SwingType.HIGH
) -> SwingComparison:
    return compare_swings(sp(0, previous_price, type), sp(1, current_price, type))


def series(
    bars: list[tuple[float, float]], *, closed: list[bool] | None = None
) -> CandleSeries:
    flags = closed or [True] * len(bars)
    return CandleSeries(
        symbol="BTCUSDT",
        timeframe="4h",
        candles=tuple(
            Candle(
                timestamp=_BASE + timedelta(hours=4 * i),
                symbol="BTCUSDT", timeframe="4h",
                open=(h + l) / 2, high=h, low=l, close=(h + l) / 2,
                volume=1.0, is_closed=flag,
            )
            for i, ((h, l), flag) in enumerate(zip(bars, flags))
        ),
    )


def chain(bars: list[tuple[float, float]], **kwargs) -> tuple[StructuralSwing, ...]:
    """The full deterministic chain: candles -> detect -> compare -> label."""
    points = detect_swings(series(bars, **kwargs), left_bars=1, right_bars=1)
    return label_swing_sequence(compare_swing_sequence(points))


def labels(swings: tuple[StructuralSwing, ...]) -> list[str]:
    return [s.label.value for s in swings]


# ============================ enum ===========================================


def test_label_members_are_exactly_six() -> None:
    assert {m.name for m in StructuralSwingLabel} == {
        "HIGHER_HIGH", "LOWER_HIGH", "EQUAL_HIGH",
        "HIGHER_LOW", "LOWER_LOW", "EQUAL_LOW",
    }
    assert len(StructuralSwingLabel) == 6


def test_label_values_are_full_snake_case_names() -> None:
    for member in StructuralSwingLabel:
        assert member.value == member.name.lower()
        assert "_" in member.value


def test_no_abbreviated_canonical_members() -> None:
    names = {m.name for m in StructuralSwingLabel}
    values = {m.value for m in StructuralSwingLabel}
    for abbreviation in ("HH", "LH", "EH", "HL", "LL", "EL"):
        assert abbreviation not in names
        assert abbreviation.lower() not in values


def test_no_directional_or_signal_vocabulary() -> None:
    names = {m.name for m in StructuralSwingLabel}
    values = {m.value for m in StructuralSwingLabel}
    for forbidden in ("BULLISH", "BEARISH", "CONTINUATION", "REVERSAL", "BREAK",
                      "BOS", "CHOCH", "LONG", "SHORT", "BUY", "SELL", "STRONG",
                      "WEAK", "CONFIRMED", "INVALID", "TREND", "SUPPORT",
                      "RESISTANCE", "LIQUIDITY"):
        assert forbidden not in names
        assert forbidden.lower() not in values


def test_label_is_a_str_enum_matching_repository_convention() -> None:
    assert isinstance(StructuralSwingLabel.HIGHER_HIGH, str)


def test_label_members_cannot_be_reassigned() -> None:
    with pytest.raises(AttributeError):
        StructuralSwingLabel.HIGHER_HIGH = "other"  # type: ignore[misc]


def test_exactly_six_states_exist_no_seventh() -> None:
    """The enum is exactly the cartesian product of the two source enums."""
    assert len(StructuralSwingLabel) == len(SwingType) * len(SwingRelation) == 6


# ============================ model ==========================================


def test_structural_swing_fields_are_exactly_two() -> None:
    assert [f.name for f in fields(StructuralSwing)] == ["comparison", "label"]


def test_structural_swing_does_not_duplicate_underlying_facts() -> None:
    names = {f.name for f in fields(StructuralSwing)}
    for duplicated in ("previous", "current", "relation", "price", "index",
                       "timestamp", "type"):
        assert duplicated not in names, duplicated


def test_structural_swing_is_frozen_slotted_and_hashable() -> None:
    assert StructuralSwing.__slots__ == ("comparison", "label")
    swing = label_swing(pair(1.0, 2.0))
    assert not hasattr(swing, "__dict__")
    with pytest.raises(FrozenInstanceError):
        swing.label = StructuralSwingLabel.LOWER_HIGH  # type: ignore[misc]
    assert isinstance(hash(swing), int)
    assert len({label_swing(pair(1.0, 2.0)), label_swing(pair(1.0, 2.0))}) == 1


def test_structural_swing_equality_is_by_value() -> None:
    assert label_swing(pair(1.0, 2.0)) == label_swing(pair(1.0, 2.0))
    assert label_swing(pair(1.0, 2.0)) != label_swing(pair(2.0, 1.0))


def test_structural_swing_holds_the_comparison_object() -> None:
    comparison = pair(1.0, 2.0)
    assert label_swing(comparison).comparison is comparison


def test_non_comparison_rejected() -> None:
    with pytest.raises(TypeError, match="comparison must be a SwingComparison"):
        # type: ignore[arg-type]
        StructuralSwing("not a comparison", StructuralSwingLabel.HIGHER_HIGH)
    with pytest.raises(TypeError, match="comparison must be a SwingComparison"):
        label_swing("not a comparison")  # type: ignore[arg-type]


def test_non_label_rejected() -> None:
    with pytest.raises(TypeError, match="label must be a StructuralSwingLabel"):
        StructuralSwing(pair(1.0, 2.0), "higher_high")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "previous,current,swing_type,wrong",
    [
        (1.0, 2.0, SwingType.HIGH, StructuralSwingLabel.LOWER_HIGH),
        (1.0, 2.0, SwingType.HIGH, StructuralSwingLabel.EQUAL_HIGH),
        (1.0, 2.0, SwingType.HIGH, StructuralSwingLabel.HIGHER_LOW),
        (2.0, 1.0, SwingType.LOW, StructuralSwingLabel.HIGHER_LOW),
        (1.0, 1.0, SwingType.LOW, StructuralSwingLabel.LOWER_LOW),
        (1.0, 1.0, SwingType.HIGH, StructuralSwingLabel.HIGHER_HIGH),
    ],
)
def test_inconsistent_label_rejected(
    previous: float, current: float, swing_type: SwingType,
    wrong: StructuralSwingLabel,
) -> None:
    """A manually built object cannot claim a label the comparison contradicts."""
    with pytest.raises(ValueError, match="does not match the comparison"):
        StructuralSwing(pair(previous, current, swing_type), wrong)


def test_consistent_manual_construction_is_accepted() -> None:
    swing = StructuralSwing(pair(1.0, 2.0), StructuralSwingLabel.HIGHER_HIGH)
    assert swing.label is StructuralSwingLabel.HIGHER_HIGH


# ============================ the six mappings ===============================


def test_high_and_higher_is_higher_high() -> None:
    assert label_swing(pair(1.0, 2.0, SwingType.HIGH)).label is (
        StructuralSwingLabel.HIGHER_HIGH
    )


def test_high_and_lower_is_lower_high() -> None:
    assert label_swing(pair(2.0, 1.0, SwingType.HIGH)).label is (
        StructuralSwingLabel.LOWER_HIGH
    )


def test_high_and_equal_is_equal_high() -> None:
    assert label_swing(pair(1.0, 1.0, SwingType.HIGH)).label is (
        StructuralSwingLabel.EQUAL_HIGH
    )


def test_low_and_higher_is_higher_low() -> None:
    assert label_swing(pair(1.0, 2.0, SwingType.LOW)).label is (
        StructuralSwingLabel.HIGHER_LOW
    )


def test_low_and_lower_is_lower_low() -> None:
    assert label_swing(pair(2.0, 1.0, SwingType.LOW)).label is (
        StructuralSwingLabel.LOWER_LOW
    )


def test_low_and_equal_is_equal_low() -> None:
    assert label_swing(pair(1.0, 1.0, SwingType.LOW)).label is (
        StructuralSwingLabel.EQUAL_LOW
    )


def test_mapping_is_exhaustive_over_both_source_enums() -> None:
    produced = set()
    for swing_type in SwingType:
        for previous, current in ((1.0, 2.0), (2.0, 1.0), (1.0, 1.0)):
            produced.add(label_swing(pair(previous, current, swing_type)).label)
    assert produced == set(StructuralSwingLabel)


def test_labelling_is_deterministic() -> None:
    comparison = pair(1.0, 2.0)
    assert label_swing(comparison) == label_swing(comparison)


# ============================ sequence =======================================


def test_empty_sequence_returns_empty_tuple() -> None:
    assert label_swing_sequence([]) == ()
    assert label_swing_sequence(()) == ()


def test_single_comparison_returns_one_structural_swing() -> None:
    result = label_swing_sequence([pair(1.0, 2.0)])
    assert len(result) == 1
    assert result[0].label is StructuralSwingLabel.HIGHER_HIGH


def test_high_only_comparisons() -> None:
    points = [sp(0, 10.0), sp(1, 12.0), sp(2, 11.0), sp(3, 11.0)]
    result = label_swing_sequence(compare_swing_sequence(points))
    assert labels(result) == ["higher_high", "lower_high", "equal_high"]


def test_low_only_comparisons() -> None:
    points = [sp(i, p, SwingType.LOW) for i, p in enumerate([5.0, 4.0, 6.0, 6.0])]
    result = label_swing_sequence(compare_swing_sequence(points))
    assert labels(result) == ["lower_low", "higher_low", "equal_low"]


def test_alternating_high_and_low_comparisons() -> None:
    points = [
        sp(0, 10.0, SwingType.HIGH), sp(1, 1.0, SwingType.LOW),
        sp(2, 12.0, SwingType.HIGH), sp(3, 2.0, SwingType.LOW),
        sp(4, 11.0, SwingType.HIGH), sp(5, 2.0, SwingType.LOW),
    ]
    result = label_swing_sequence(compare_swing_sequence(points))
    assert labels(result) == [
        "higher_high", "higher_low", "lower_high", "equal_low",
    ]


def test_output_count_equals_input_count() -> None:
    comparisons = compare_swing_sequence(
        [sp(0, 1.0), sp(1, 2.0), sp(2, 3.0), sp(3, 4.0)]
    )
    assert len(label_swing_sequence(comparisons)) == len(comparisons)


def test_input_order_is_preserved_exactly() -> None:
    comparisons = compare_swing_sequence([
        sp(0, 10.0, SwingType.HIGH), sp(1, 1.0, SwingType.LOW),
        sp(2, 12.0, SwingType.HIGH), sp(3, 2.0, SwingType.LOW),
    ])
    result = label_swing_sequence(comparisons)
    assert [s.comparison for s in result] == list(comparisons)


def test_output_is_an_immutable_tuple() -> None:
    result = label_swing_sequence([pair(1.0, 2.0)])
    assert isinstance(result, tuple)
    with pytest.raises(TypeError):
        result[0] = None  # type: ignore[index]


def test_input_collection_is_not_mutated() -> None:
    comparisons = [pair(1.0, 2.0), compare_swings(sp(1, 2.0), sp(2, 3.0))]
    snapshot = list(comparisons)
    label_swing_sequence(comparisons)
    assert comparisons == snapshot and len(comparisons) == 2


def test_accepts_any_iterable() -> None:
    comparisons = [pair(1.0, 2.0)]
    assert label_swing_sequence(iter(comparisons)) == label_swing_sequence(comparisons)


# ============================ sequence rejection =============================


def test_decreasing_current_index_rejected() -> None:
    first = compare_swings(sp(0, 1.0), sp(5, 2.0))
    second = compare_swings(sp(0, 1.0), sp(2, 3.0))
    with pytest.raises(ValueError, match="ordered by current index"):
        label_swing_sequence([first, second])


def test_duplicate_comparison_object_rejected() -> None:
    comparison = pair(1.0, 2.0)
    with pytest.raises(ValueError, match="repeats or precedes current index"):
        label_swing_sequence([comparison, comparison])


def test_duplicate_same_type_current_point_rejected() -> None:
    first = compare_swings(sp(0, 1.0), sp(3, 2.0))
    second = compare_swings(sp(1, 5.0), sp(3, 9.0))  # same current index, same type
    with pytest.raises(ValueError, match="repeats or precedes current index"):
        label_swing_sequence([first, second])


def test_shared_current_index_with_different_timestamp_rejected() -> None:
    high = compare_swings(sp(0, 1.0, SwingType.HIGH), sp(3, 2.0, SwingType.HIGH))
    odd_low = compare_swings(
        SwingPoint(0, _BASE, 9.0, SwingType.LOW, confirmation_bars=CB),
        SwingPoint(3, _BASE + timedelta(hours=99), 8.0, SwingType.LOW, confirmation_bars=CB),
    )
    with pytest.raises(ValueError, match="different timestamp"):
        label_swing_sequence([high, odd_low])


def test_decreasing_current_timestamp_rejected() -> None:
    first = compare_swings(
        SwingPoint(0, _BASE, 1.0, SwingType.HIGH, confirmation_bars=CB),
        SwingPoint(1, _BASE + timedelta(hours=80), 2.0, SwingType.HIGH, confirmation_bars=CB),
    )
    second = compare_swings(
        SwingPoint(0, _BASE, 5.0, SwingType.LOW, confirmation_bars=CB),
        SwingPoint(2, _BASE + timedelta(hours=8), 4.0, SwingType.LOW, confirmation_bars=CB),
    )
    with pytest.raises(ValueError, match="ordered by current timestamp"):
        label_swing_sequence([first, second])


def test_non_comparison_element_rejected() -> None:
    with pytest.raises(TypeError, match=r"comparisons\[1\] must be a SwingComparison"):
        label_swing_sequence([pair(1.0, 2.0), "nope"])  # type: ignore[list-item]


def test_non_iterable_input_rejected() -> None:
    with pytest.raises(TypeError, match="must be an iterable"):
        label_swing_sequence(42)  # type: ignore[arg-type]


def test_a_bare_string_is_not_accepted_as_a_sequence() -> None:
    with pytest.raises(TypeError, match="must be an iterable"):
        label_swing_sequence("comparisons")  # type: ignore[arg-type]


# ============================ outside-bar composition ========================


def test_outside_bar_equal_index_comparisons_are_accepted() -> None:
    """The composition this layer must not break.

    One candle yields a HIGH and a LOW, so two comparisons share a
    `current.index`. Both must be labelled, in input order.
    """
    bars = [(5.0, 4.0), (9.0, 1.0), (5.0, 4.0), (11.0, 0.5), (5.0, 4.0)]
    points = detect_swings(series(bars), left_bars=1, right_bars=1)
    comparisons = compare_swing_sequence(points)
    shared = [c.current.index for c in comparisons]
    assert len(shared) != len(set(shared))  # equal indices really are present

    result = label_swing_sequence(comparisons)
    assert len(result) == len(comparisons)
    assert labels(result) == ["higher_high", "lower_low"]


def test_equal_index_order_is_inherited_from_input_not_imposed() -> None:
    """Labelling preserves the upstream tie order; it never imposes HIGH-first.

    HIGH-before-LOW is a property of `detect_swings`, not a rule of this layer.
    `compare_swing_sequence` accepts a valid run in either order, so both must
    come back labelled in the order they arrived (ADR-0014 §8).
    """
    def run(first: SwingType, second: SwingType) -> list[str]:
        price = {SwingType.HIGH: (50.0, 60.0), SwingType.LOW: (10.0, 20.0)}
        points: list[SwingPoint] = []
        for index in (10, 20):
            stamp = _BASE + timedelta(hours=4 * index)
            for kind in (first, second):
                points.append(
                    SwingPoint(index, stamp, price[kind][0 if index == 10 else 1], kind, confirmation_bars=CB)
                )
        comparisons = compare_swing_sequence(points)
        result = label_swing_sequence(comparisons)
        assert [s.comparison for s in result] == list(comparisons)
        return [s.comparison.current.type.value for s in result]

    assert run(SwingType.HIGH, SwingType.LOW) == ["high", "low"]
    assert run(SwingType.LOW, SwingType.HIGH) == ["low", "high"]


def test_low_before_high_at_an_equal_index_is_valid_upstream() -> None:
    """The reversed tie order is legitimate input, not something to reject."""
    stamp = _BASE + timedelta(hours=40)
    points = [
        SwingPoint(0, _BASE, 10.0, SwingType.LOW, confirmation_bars=CB),
        SwingPoint(0, _BASE, 50.0, SwingType.HIGH, confirmation_bars=CB),
        SwingPoint(10, stamp, 20.0, SwingType.LOW, confirmation_bars=CB),
        SwingPoint(10, stamp, 60.0, SwingType.HIGH, confirmation_bars=CB),
    ]
    comparisons = compare_swing_sequence(points)          # accepted upstream
    result = label_swing_sequence(comparisons)            # accepted here
    assert labels(result) == ["higher_low", "higher_high"]


def test_outside_bar_order_is_high_then_low() -> None:
    bars = [(5.0, 4.0), (9.0, 1.0), (5.0, 4.0), (11.0, 0.5), (5.0, 4.0)]
    result = chain(bars)
    assert [s.comparison.current.type.value for s in result] == ["high", "low"]


# ============================ full deterministic chain =======================


def test_full_chain_labels_normal_alternating_swings() -> None:
    bars = [(5.0, 4.0), (9.0, 1.0), (5.0, 4.0), (11.0, 0.5), (5.0, 4.0),
            (7.0, 2.0), (5.0, 4.0)]
    assert labels(chain(bars)) == [
        "higher_high", "lower_low", "lower_high", "higher_low",
    ]


def test_full_chain_reaches_equal_high_and_equal_low() -> None:
    bars = [(5.0, 4.0), (9.0, 1.0), (5.0, 4.0), (9.0, 1.0), (5.0, 4.0)]
    assert labels(chain(bars)) == ["equal_high", "equal_low"]


def test_full_chain_reaches_every_label() -> None:
    reached: set[str] = set()
    for bars in (
        [(5.0, 4.0), (9.0, 1.0), (5.0, 4.0), (11.0, 0.5), (5.0, 4.0)],
        [(5.0, 4.0), (11.0, 0.5), (5.0, 4.0), (9.0, 1.0), (5.0, 4.0)],
        [(5.0, 4.0), (9.0, 1.0), (5.0, 4.0), (9.0, 1.0), (5.0, 4.0)],
    ):
        reached |= set(labels(chain(bars)))
    assert reached == {m.value for m in StructuralSwingLabel}


def test_full_chain_ignores_a_forming_trailing_candle() -> None:
    bars = [(5.0, 4.0), (9.0, 1.0), (5.0, 4.0), (11.0, 0.5), (5.0, 4.0)]
    closed_only = chain(bars)
    with_forming = chain(bars + [(99.0, 0.01)],
                         closed=[True] * len(bars) + [False])
    assert closed_only == with_forming


def test_full_chain_frontier_advance_adds_without_altering() -> None:
    """Labels already produced stay identical as the frontier advances."""
    bars = [(5.0, 4.0), (9.0, 1.0), (5.0, 4.0), (11.0, 0.5), (5.0, 4.0),
            (7.0, 2.0), (5.0, 4.0), (8.0, 1.5), (5.0, 4.0)]
    seen: dict[tuple[int, int, str], StructuralSwing] = {}
    for length in range(len(bars) + 1):
        for swing in chain(bars[:length]):
            comparison = swing.comparison
            key = (comparison.previous.index, comparison.current.index,
                   comparison.current.type.value)
            if key in seen:
                assert seen[key] == swing, f"changed at length {length}"
            seen[key] = swing
    assert len(seen) == len(chain(bars))


# ============================ property-style tests ===========================


def oracle_label(comparison: SwingComparison) -> str:
    """Expected label built from the naming convention, not the lookup table.

    `"{relation}_{type}"` — a different derivation from the production dict, so a
    wrong table entry disagrees with it.
    """
    return f"{comparison.relation.value}_{comparison.current.type.value}"


def random_points(rng: random.Random, count: int) -> list[SwingPoint]:
    points: list[SwingPoint] = []
    index = 0
    for _ in range(count):
        index += rng.choice([1, 1, 2, 3])
        stamp = _BASE + timedelta(hours=4 * index)
        if rng.random() < 0.15:  # outside bar
            points.append(SwingPoint(index, stamp, float(rng.randint(50, 55)),
                                     SwingType.HIGH, confirmation_bars=CB))
            points.append(SwingPoint(index, stamp, float(rng.randint(10, 15)),
                                     SwingType.LOW, confirmation_bars=CB))
        else:
            kind = rng.choice([SwingType.HIGH, SwingType.LOW])
            price = float(rng.randint(50, 55) if kind is SwingType.HIGH
                          else rng.randint(10, 15))
            points.append(SwingPoint(index, stamp, price, kind, confirmation_bars=CB))
    return points


@pytest.mark.parametrize("seed", range(25))
def test_property_label_matches_type_and_relation(seed: int) -> None:
    comparisons = compare_swing_sequence(random_points(random.Random(seed), 40))
    for swing in label_swing_sequence(comparisons):
        assert swing.label.value == oracle_label(swing.comparison)


@pytest.mark.parametrize("seed", range(25))
def test_property_count_and_order_match_the_input(seed: int) -> None:
    comparisons = compare_swing_sequence(random_points(random.Random(100 + seed), 40))
    result = label_swing_sequence(comparisons)
    assert len(result) == len(comparisons)
    assert [s.comparison for s in result] == list(comparisons)


@pytest.mark.parametrize("seed", range(25))
def test_property_each_swing_holds_its_original_comparison(seed: int) -> None:
    comparisons = compare_swing_sequence(random_points(random.Random(200 + seed), 40))
    for swing, comparison in zip(label_swing_sequence(comparisons), comparisons):
        assert swing.comparison is comparison


@pytest.mark.parametrize("seed", range(25))
def test_property_prefix_stability(seed: int) -> None:
    """A label already produced never changes as later comparisons arrive."""
    comparisons = compare_swing_sequence(random_points(random.Random(300 + seed), 40))
    emitted: dict[int, StructuralSwing] = {}
    for length in range(len(comparisons) + 1):
        for position, swing in enumerate(label_swing_sequence(comparisons[:length])):
            if position in emitted:
                assert emitted[position] == swing, f"changed at length {length}"
            emitted[position] = swing
    assert len(emitted) == len(comparisons)


@pytest.mark.parametrize("seed", range(15))
def test_property_no_impossible_state_is_produced(seed: int) -> None:
    comparisons = compare_swing_sequence(random_points(random.Random(400 + seed), 40))
    for swing in label_swing_sequence(comparisons):
        assert swing.label in set(StructuralSwingLabel)
        assert swing.comparison.current.type in set(SwingType)
        assert swing.comparison.relation in set(SwingRelation)


# ============================ scope boundaries ===============================


def _code_tokens(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    docstrings = {
        d for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and (d := ast.get_docstring(node, clean=False)) is not None
    }
    tokens: set[str] = set()

    def add(text: str) -> None:
        lowered = text.lower()
        tokens.add(lowered)
        tokens.update(lowered.replace("_", " ").split())

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                add(node.value)
        elif isinstance(node, ast.Name):
            add(node.id)
        elif isinstance(node, ast.Attribute):
            add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            add(node.name)
    return tokens


def test_no_interpretation_vocabulary_in_code() -> None:
    forbidden = (
        "bos", "choch", "trend", "regime", "bullish", "bearish", "support",
        "resistance", "liquidity", "sweep", "strength", "confidence", "score",
        "buy", "sell", "signal", "evidence", "observation", "continuation",
        "reversal", "breakout", "doubletop", "doublebottom", "confirmed",
    )
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        tokens = _code_tokens(py)
        for word in forbidden:
            assert word not in tokens, f"{py.name}: {word}"


def test_label_is_derived_from_the_current_point_not_the_previous_one() -> None:
    """Static check: `_label_for` reads `current`, never `previous`.

    Both give the same answer for any valid comparison — `SwingComparison`
    guarantees the types match — so no runtime test can tell them apart. The
    source is therefore where the rule has to be pinned.
    """
    source = (PACKAGE_DIR / "models.py").read_text()
    tree = ast.parse(source)
    body = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_label_for"
    )
    read = {
        node.attr for node in ast.walk(body) if isinstance(node, ast.Attribute)
    }
    assert "current" in read
    assert "previous" not in read


def test_no_approximate_equality_introduced() -> None:
    for py in (PACKAGE_DIR / "labels.py", PACKAGE_DIR / "models.py"):
        tokens = _code_tokens(py)
        for marker in ("isclose", "epsilon", "tolerance", "atol", "rtol",
                       "approx", "round", "decimal", "tick"):
            assert marker not in tokens, f"{py.name}: {marker}"


def test_labels_module_does_not_detect_or_compare() -> None:
    tree = ast.parse((PACKAGE_DIR / "labels.py").read_text())
    called = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "detect_swings" not in called
    assert "compare_swing_sequence" not in called
    assert "compare_swings" not in called
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("high", "low", "close", "open", "volume",
                                     "candles", "price")


def test_market_structure_evidence_family_remains_empty() -> None:
    from fmis.evidence import EvidenceFamily, descriptors, descriptors_for

    assert descriptors_for(EvidenceFamily.MARKET_STRUCTURE) == ()
    assert len(descriptors()) == 6


# ============================ public API / boundaries ========================


def test_public_api_is_exactly_the_declared_surface() -> None:
    assert set(ms.__all__) == {
        "SwingType", "SwingPoint", "SwingRelation", "SwingComparison",
        "StructuralSwingLabel", "StructuralSwing",
        "detect_swings", "compare_swings", "compare_swing_sequence",
        "label_swing", "label_swing_sequence",
        "StructuralSequenceStateType", "StructuralSequenceState",
        "StructuralSequenceStateSnapshot",
        "derive_structural_sequence_state", "derive_structural_sequence_state_history",
        "required_candles", "DEFAULT_LEFT_BARS", "DEFAULT_RIGHT_BARS",
    }
    for name in ms.__all__:
        assert hasattr(ms, name)


def test_no_mutable_public_object_is_exported() -> None:
    for name in ms.__all__:
        assert not isinstance(getattr(ms, name), (list, dict, set)), name


def test_the_label_mapping_is_internal_and_immutable() -> None:
    from types import MappingProxyType

    from fmis.market_structure import models

    assert "_LABEL_BY_TYPE_AND_RELATION" not in ms.__all__
    assert not hasattr(ms, "label_for")
    assert not hasattr(StructuralSwing, "label_for")
    assert isinstance(models._LABEL_BY_TYPE_AND_RELATION, MappingProxyType)
    with pytest.raises(TypeError):
        models._LABEL_BY_TYPE_AND_RELATION[("x", "y")] = None  # type: ignore[index]


@pytest.mark.parametrize(
    "run_kind, expected",
    [
        ("decreasing index",
         "comparisons must be ordered by current index; comparisons[1] has "
         "index 4 after 8"),
        ("shared index, different timestamp",
         "comparisons[1] shares current index 6 with the previous comparison "
         "but carries a different timestamp"),
        ("repeat within a type",
         "comparisons[1] repeats or precedes current index 4 for swing type "
         "'high'"),
    ],
)
def test_ordering_error_messages_are_exact(run_kind: str, expected: str) -> None:
    """The wording is a shipped contract, not an implementation detail.

    The ordering rule now lives in the shared `models._validate_current_point_order`
    so a second consumer cannot grow a divergent contract. Only the caller's
    parameter name is substituted into these messages; extracting or re-homing the
    rule again must not reword them, and a substring match would not notice if it
    did.
    """
    if run_kind == "decreasing index":
        run = [
            compare_swings(sp(4, 1.0), sp(8, 2.0)),
            compare_swings(sp(0, 1.0, SwingType.LOW), sp(4, 2.0, SwingType.LOW)),
        ]
    elif run_kind == "shared index, different timestamp":
        run = [
            compare_swings(sp(0, 1.0), sp(6, 2.0)),
            compare_swings(
                SwingPoint(0, _BASE, 9.0, SwingType.LOW, confirmation_bars=CB),
                SwingPoint(6, _BASE + timedelta(hours=999), 8.0, SwingType.LOW, confirmation_bars=CB),
            ),
        ]
    else:
        run = [compare_swings(sp(0, 1.0), sp(4, 2.0))] * 2

    with pytest.raises(ValueError) as caught:
        label_swing_sequence(run)
    assert str(caught.value) == expected


def test_no_submodule_shares_a_name_with_a_public_object() -> None:
    import pkgutil

    submodules = {m.name for m in pkgutil.iter_modules(ms.__path__)}
    assert submodules == {"labels", "models", "relationships", "sequence_state",
                          "state_history", "swings"}
    assert submodules & set(ms.__all__) == set()


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


def test_imports_only_canonical_data_and_own_modules() -> None:
    assert _internal_imports() <= {
        "fmis.data",
        "fmis.market_structure.labels",
        "fmis.market_structure.models",
        "fmis.market_structure.relationships",
        "fmis.market_structure.sequence_state",
        "fmis.market_structure.state_history",
        "fmis.market_structure.swings",
    }


@pytest.mark.parametrize(
    "forbidden",
    ["fmis.decision_support", "fmis.evidence", "fmis.providers", "fmis.pipeline",
     "fmis.ingest", "fmis.trading_context", "fmis.relative_value", "fmis.features"],
)
def test_does_not_depend_on_higher_or_sibling_layers(forbidden: str) -> None:
    assert not any(i.startswith(forbidden) for i in _internal_imports()), forbidden


def test_uses_only_stdlib() -> None:
    roots: set[str] = set()
    for py in PACKAGE_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
    assert roots <= set(sys.stdlib_module_names) | {"fmis"}
