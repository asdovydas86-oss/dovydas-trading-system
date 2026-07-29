"""Tests for deterministic swing comparison (fmis.market_structure).

Hand-built points pin the model contract and every documented rejection.
Randomized runs then assert the properties that must hold for any input, using
an oracle written by partitioning on type — a different formulation from the
implementation's running-latest walk, so it can disagree with it.
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
    SwingComparison,
    SwingPoint,
    SwingRelation,
    SwingType,
    compare_swing_sequence,
    compare_swings,
    detect_swings,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
PACKAGE_DIR = Path(ms.__file__).parent
SRC = PACKAGE_DIR.parent


def sp(index: int, price: float, type: SwingType = SwingType.HIGH) -> SwingPoint:
    """A swing point whose timestamp follows its index."""
    return SwingPoint(
        index=index,
        timestamp=_BASE + timedelta(hours=4 * index),
        price=price,
        type=type,
    )


def rel(previous: SwingPoint, current: SwingPoint) -> str:
    return compare_swings(previous, current).relation.value


# ============================ SwingRelation ==================================


def test_relation_members_are_exactly_three() -> None:
    assert {r.name for r in SwingRelation} == {"HIGHER", "LOWER", "EQUAL"}
    assert [r.value for r in SwingRelation] == ["higher", "lower", "equal"]


def test_relation_has_no_directional_or_interpretive_members() -> None:
    names = {r.name for r in SwingRelation}
    values = {r.value for r in SwingRelation}
    for forbidden in ("BULLISH", "BEARISH", "LONG", "SHORT", "BUY", "SELL",
                      "BREAK", "REVERSAL", "CONTINUATION", "CONFIDENCE",
                      "STRENGTH", "UNAVAILABLE"):
        assert forbidden not in names
        assert forbidden.lower() not in values


def test_relation_is_a_str_enum_matching_repository_convention() -> None:
    assert isinstance(SwingRelation.HIGHER, str)


def test_relation_members_cannot_be_reassigned() -> None:
    with pytest.raises(AttributeError):
        SwingRelation.HIGHER = "other"  # type: ignore[misc]


def test_relation_is_not_a_reuse_of_the_decision_support_comparison() -> None:
    """Similar shape, different layer and different meaning.

    `decision_support.Comparison` is ABOVE/BELOW/EQUAL/UNAVAILABLE, describing a
    possibly-missing value in a higher layer this package may not import.
    """
    from fmis.decision_support import Comparison

    assert {c.name for c in Comparison} != {r.name for r in SwingRelation}
    assert "UNAVAILABLE" in {c.name for c in Comparison}
    assert "UNAVAILABLE" not in {r.name for r in SwingRelation}


# ============================ SwingComparison model ==========================


def test_comparison_fields_are_exactly_three() -> None:
    assert [f.name for f in fields(SwingComparison)] == [
        "previous", "current", "relation",
    ]


def test_comparison_has_no_interpretation_fields() -> None:
    names = {f.name for f in fields(SwingComparison)}
    tokens: set[str] = set()
    for name in names:
        tokens |= set(name.split("_")) | {name}
    for forbidden in ("confidence", "strength", "trend", "direction", "score",
                      "bos", "choch", "label", "bullish", "bearish"):
        assert forbidden not in tokens, forbidden


def test_comparison_is_frozen_slotted_and_hashable() -> None:
    assert SwingComparison.__slots__ == ("previous", "current", "relation")
    c = compare_swings(sp(0, 1.0), sp(1, 2.0))
    assert not hasattr(c, "__dict__")
    with pytest.raises(FrozenInstanceError):
        c.relation = SwingRelation.LOWER  # type: ignore[misc]
    assert isinstance(hash(c), int)
    assert len({compare_swings(sp(0, 1.0), sp(1, 2.0)),
                compare_swings(sp(0, 1.0), sp(1, 2.0))}) == 1


def test_comparison_equality_is_by_value() -> None:
    assert compare_swings(sp(0, 1.0), sp(1, 2.0)) == compare_swings(
        sp(0, 1.0), sp(1, 2.0)
    )
    assert compare_swings(sp(0, 1.0), sp(1, 2.0)) != compare_swings(
        sp(0, 1.0), sp(1, 3.0)
    )


def test_comparison_holds_the_points_whole() -> None:
    previous, current = sp(2, 5.0), sp(7, 9.0)
    c = compare_swings(previous, current)
    assert c.previous is previous
    assert c.current is current


# ============================ model validation ===============================


@pytest.mark.parametrize("field", ["previous", "current"])
def test_non_swing_point_rejected(field: str) -> None:
    args = {"previous": sp(0, 1.0), "current": sp(1, 2.0),
            "relation": SwingRelation.HIGHER}
    args[field] = "not a point"
    with pytest.raises(TypeError, match=f"{field} must be a SwingPoint"):
        SwingComparison(**args)  # type: ignore[arg-type]


def test_non_relation_rejected() -> None:
    with pytest.raises(TypeError, match="relation must be a SwingRelation"):
        SwingComparison(sp(0, 1.0), sp(1, 2.0), "higher")  # type: ignore[arg-type]


def test_mixed_swing_types_rejected() -> None:
    with pytest.raises(ValueError, match="same SwingType"):
        compare_swings(sp(0, 1.0, SwingType.HIGH), sp(1, 2.0, SwingType.LOW))
    with pytest.raises(ValueError, match="same SwingType"):
        compare_swings(sp(0, 1.0, SwingType.LOW), sp(1, 2.0, SwingType.HIGH))


def test_reversed_index_rejected_not_reordered() -> None:
    with pytest.raises(ValueError, match="must be greater than"):
        compare_swings(sp(5, 1.0), sp(2, 2.0))


def test_equal_index_rejected() -> None:
    earlier = sp(3, 1.0)
    same_index = SwingPoint(3, _BASE + timedelta(hours=99), 2.0, SwingType.HIGH)
    with pytest.raises(ValueError, match="must be greater than"):
        compare_swings(earlier, same_index)


def test_reversed_timestamp_rejected() -> None:
    previous = SwingPoint(1, _BASE + timedelta(hours=40), 1.0, SwingType.HIGH)
    current = SwingPoint(2, _BASE + timedelta(hours=4), 2.0, SwingType.HIGH)
    with pytest.raises(ValueError, match="must be later than"):
        compare_swings(previous, current)


def test_equal_timestamp_rejected() -> None:
    previous = SwingPoint(1, _BASE, 1.0, SwingType.HIGH)
    current = SwingPoint(2, _BASE, 2.0, SwingType.HIGH)
    with pytest.raises(ValueError, match="must be later than"):
        compare_swings(previous, current)


@pytest.mark.parametrize(
    "previous_price,current_price,wrong",
    [
        (1.0, 2.0, SwingRelation.LOWER),
        (1.0, 2.0, SwingRelation.EQUAL),
        (2.0, 1.0, SwingRelation.HIGHER),
        (1.0, 1.0, SwingRelation.HIGHER),
        (1.0, 1.0, SwingRelation.LOWER),
    ],
)
def test_inconsistent_relation_rejected(
    previous_price: float, current_price: float, wrong: SwingRelation
) -> None:
    """A manually built object cannot claim a relation the prices contradict."""
    with pytest.raises(ValueError, match="does not match the prices"):
        SwingComparison(sp(0, previous_price), sp(1, current_price), wrong)


def test_consistent_manual_construction_is_accepted() -> None:
    c = SwingComparison(sp(0, 1.0), sp(1, 2.0), SwingRelation.HIGHER)
    assert c.relation is SwingRelation.HIGHER


# ============================ pair comparison ================================


@pytest.mark.parametrize("swing_type", [SwingType.HIGH, SwingType.LOW])
def test_higher_price_is_higher(swing_type: SwingType) -> None:
    assert rel(sp(0, 100.0, swing_type), sp(1, 101.0, swing_type)) == "higher"


@pytest.mark.parametrize("swing_type", [SwingType.HIGH, SwingType.LOW])
def test_lower_price_is_lower(swing_type: SwingType) -> None:
    assert rel(sp(0, 100.0, swing_type), sp(1, 99.0, swing_type)) == "lower"


@pytest.mark.parametrize("swing_type", [SwingType.HIGH, SwingType.LOW])
def test_equal_price_is_equal(swing_type: SwingType) -> None:
    assert rel(sp(0, 100.0, swing_type), sp(1, 100.0, swing_type)) == "equal"


def test_relation_describes_numeric_movement_not_market_meaning() -> None:
    """A rising swing LOW is HIGHER — the same word as a rising swing HIGH.

    The relation reports which number is larger. It deliberately does not encode
    that a rising low and a rising high mean different things to a reader.
    """
    rising_low = rel(sp(0, 10.0, SwingType.LOW), sp(1, 20.0, SwingType.LOW))
    rising_high = rel(sp(0, 10.0, SwingType.HIGH), sp(1, 20.0, SwingType.HIGH))
    assert rising_low == rising_high == "higher"

    falling_low = rel(sp(0, 20.0, SwingType.LOW), sp(1, 10.0, SwingType.LOW))
    falling_high = rel(sp(0, 20.0, SwingType.HIGH), sp(1, 10.0, SwingType.HIGH))
    assert falling_low == falling_high == "lower"


def test_comparison_uses_exact_equality_with_no_tolerance() -> None:
    # One ulp apart is HIGHER, not EQUAL: no epsilon is invented.
    assert rel(sp(0, 1.0), sp(1, 1.0 + 1e-12)) == "higher"
    assert rel(sp(0, 1.0 + 1e-12), sp(1, 1.0)) == "lower"


def test_comparison_is_pure_and_deterministic() -> None:
    a, b = sp(0, 1.0), sp(1, 2.0)
    assert compare_swings(a, b) == compare_swings(a, b)


# ============================ sequence: basics ===============================


def test_empty_input_returns_empty_tuple() -> None:
    assert compare_swing_sequence([]) == ()
    assert compare_swing_sequence(()) == ()


def test_single_point_returns_empty_tuple() -> None:
    assert compare_swing_sequence([sp(0, 1.0)]) == ()
    assert compare_swing_sequence([sp(0, 1.0, SwingType.LOW)]) == ()


def test_first_point_of_each_type_produces_no_comparison() -> None:
    points = [sp(0, 1.0, SwingType.HIGH), sp(1, 2.0, SwingType.LOW)]
    assert compare_swing_sequence(points) == ()


def test_only_high_points() -> None:
    points = [sp(0, 1.0), sp(1, 3.0), sp(2, 2.0)]
    result = compare_swing_sequence(points)
    assert [c.relation.value for c in result] == ["higher", "lower"]
    assert all(c.previous.type is SwingType.HIGH for c in result)


def test_only_low_points() -> None:
    points = [sp(i, p, SwingType.LOW) for i, p in enumerate([5.0, 4.0, 4.0])]
    result = compare_swing_sequence(points)
    assert [c.relation.value for c in result] == ["lower", "equal"]


def test_alternating_high_and_low_points() -> None:
    points = [
        sp(0, 10.0, SwingType.HIGH), sp(1, 1.0, SwingType.LOW),
        sp(2, 12.0, SwingType.HIGH), sp(3, 2.0, SwingType.LOW),
        sp(4, 11.0, SwingType.HIGH), sp(5, 3.0, SwingType.LOW),
    ]
    result = compare_swing_sequence(points)
    assert [(c.current.index, c.current.type.value, c.relation.value)
            for c in result] == [
        (2, "high", "higher"), (3, "low", "higher"),
        (4, "high", "lower"), (5, "low", "higher"),
    ]


def test_irregular_interleaving() -> None:
    # Two highs, then two lows, then a high: each links to its own type.
    points = [
        sp(0, 10.0, SwingType.HIGH), sp(1, 11.0, SwingType.HIGH),
        sp(2, 5.0, SwingType.LOW), sp(3, 4.0, SwingType.LOW),
        sp(4, 9.0, SwingType.HIGH),
    ]
    result = compare_swing_sequence(points)
    assert [(c.previous.index, c.current.index) for c in result] == [
        (0, 1), (2, 3), (1, 4),
    ]
    assert [c.relation.value for c in result] == ["higher", "lower", "lower"]


def test_comparisons_link_the_immediately_previous_point_of_the_same_type() -> None:
    points = [
        sp(0, 10.0, SwingType.HIGH), sp(1, 20.0, SwingType.HIGH),
        sp(2, 30.0, SwingType.HIGH),
    ]
    result = compare_swing_sequence(points)
    assert [(c.previous.index, c.current.index) for c in result] == [(0, 1), (1, 2)]


def test_results_are_ordered_by_current_index() -> None:
    points = [
        sp(0, 10.0, SwingType.HIGH), sp(1, 1.0, SwingType.LOW),
        sp(5, 12.0, SwingType.HIGH), sp(9, 2.0, SwingType.LOW),
    ]
    indices = [c.current.index for c in compare_swing_sequence(points)]
    assert indices == sorted(indices)


def test_output_is_an_immutable_tuple() -> None:
    result = compare_swing_sequence([sp(0, 1.0), sp(1, 2.0)])
    assert isinstance(result, tuple)
    with pytest.raises(TypeError):
        result[0] = None  # type: ignore[index]


def test_input_collection_is_not_mutated() -> None:
    points = [sp(0, 1.0), sp(1, 2.0), sp(2, 3.0)]
    snapshot = list(points)
    compare_swing_sequence(points)
    assert points == snapshot
    assert len(points) == 3


def test_accepts_any_iterable() -> None:
    points = [sp(0, 1.0), sp(1, 2.0)]
    assert compare_swing_sequence(iter(points)) == compare_swing_sequence(points)


# ============================ sequence: rejection ============================


def test_unsorted_index_rejected_not_sorted_silently() -> None:
    points = [sp(0, 1.0), sp(5, 2.0), sp(3, 3.0)]
    with pytest.raises(ValueError, match="ordered by index"):
        compare_swing_sequence(points)


def test_duplicate_index_for_the_same_type_rejected() -> None:
    # Same index *and* timestamp, so the global ordering checks pass and the
    # per-type strictness check is what must reject it: one candle cannot be
    # two swing highs.
    first = SwingPoint(1, _BASE, 1.0, SwingType.HIGH)
    duplicate = SwingPoint(1, _BASE, 2.0, SwingType.HIGH)
    with pytest.raises(ValueError, match="repeats or precedes index"):
        compare_swing_sequence([first, duplicate])


def test_duplicate_index_across_types_is_accepted() -> None:
    # An outside candle legitimately yields one HIGH and one LOW at one index.
    points = [
        SwingPoint(1, _BASE, 9.0, SwingType.HIGH),
        SwingPoint(1, _BASE, 1.0, SwingType.LOW),
    ]
    assert compare_swing_sequence(points) == ()


def test_unsorted_timestamp_rejected() -> None:
    points = [
        SwingPoint(0, _BASE + timedelta(hours=40), 1.0, SwingType.HIGH),
        SwingPoint(1, _BASE, 2.0, SwingType.HIGH),
    ]
    with pytest.raises(ValueError, match="ordered by timestamp"):
        compare_swing_sequence(points)


def test_shared_index_with_differing_timestamp_rejected() -> None:
    points = [
        SwingPoint(1, _BASE, 9.0, SwingType.HIGH),
        SwingPoint(1, _BASE + timedelta(hours=4), 1.0, SwingType.LOW),
    ]
    with pytest.raises(ValueError, match="different timestamp"):
        compare_swing_sequence(points)


def test_non_swing_point_element_rejected() -> None:
    with pytest.raises(TypeError, match=r"points\[1\] must be a SwingPoint"):
        compare_swing_sequence([sp(0, 1.0), "nope"])  # type: ignore[list-item]


def test_non_iterable_input_rejected() -> None:
    with pytest.raises(TypeError, match="must be an iterable"):
        compare_swing_sequence(42)  # type: ignore[arg-type]


def test_a_bare_string_is_not_accepted_as_a_sequence() -> None:
    with pytest.raises(TypeError, match="must be an iterable"):
        compare_swing_sequence("points")  # type: ignore[arg-type]


# ============================ composes with detect_swings ====================


def candles(bars: list[tuple[float, float]]) -> CandleSeries:
    return CandleSeries(
        symbol="BTCUSDT",
        timeframe="4h",
        candles=tuple(
            Candle(
                timestamp=_BASE + timedelta(hours=4 * i),
                symbol="BTCUSDT", timeframe="4h",
                open=(h + l) / 2, high=h, low=l, close=(h + l) / 2,
                volume=1.0, is_closed=True,
            )
            for i, (h, l) in enumerate(bars)
        ),
    )


def test_accepts_detect_swings_output_including_outside_bars() -> None:
    """The composition this milestone exists for.

    An outside candle yields a HIGH and a LOW at the *same* index, so a global
    strict-index rule would reject valid detector output. Per-type strictness is
    what is actually required.
    """
    bars = [(5.0, 4.0), (9.0, 1.0), (5.0, 4.0), (11.0, 3.0), (5.0, 4.0)]
    points = detect_swings(candles(bars), left_bars=1, right_bars=1)
    shared = [p.index for p in points]
    assert len(shared) != len(set(shared))  # duplicate indices really are present

    result = compare_swing_sequence(points)
    assert [(c.current.type.value, c.relation.value) for c in result] == [
        ("high", "higher"), ("low", "higher"),
    ]


def test_end_to_end_pairs_are_always_same_type() -> None:
    bars = [(float(10 + (i * 7) % 9), float((i * 5) % 6)) for i in range(40)]
    points = detect_swings(candles(bars), left_bars=2, right_bars=2)
    for c in compare_swing_sequence(points):
        assert c.previous.type is c.current.type


# ============================ property-style tests ===========================


def random_points(rng: random.Random, count: int) -> list[SwingPoint]:
    """Ordered points with interleaved types, ties, and shared indices."""
    points: list[SwingPoint] = []
    index = 0
    for _ in range(count):
        index += rng.choice([1, 1, 2, 3])
        stamp = _BASE + timedelta(hours=4 * index)
        if rng.random() < 0.15:  # outside bar: both types at one index
            points.append(SwingPoint(index, stamp, float(rng.randint(50, 60)),
                                     SwingType.HIGH))
            points.append(SwingPoint(index, stamp, float(rng.randint(10, 20)),
                                     SwingType.LOW))
        else:
            kind = rng.choice([SwingType.HIGH, SwingType.LOW])
            price = float(rng.randint(50, 60) if kind is SwingType.HIGH
                          else rng.randint(10, 20))
            points.append(SwingPoint(index, stamp, price, kind))
    return points


def oracle(points: list[SwingPoint]) -> list[tuple[int, int, str, str]]:
    """Expected comparisons, derived by partitioning on type.

    A different formulation from the implementation's running-latest walk: this
    splits the run into two independent streams and zips each with its own tail.
    """
    expected: list[tuple[int, int, str, str]] = []
    for kind in (SwingType.HIGH, SwingType.LOW):
        stream = [p for p in points if p.type is kind]
        for previous, current in zip(stream, stream[1:]):
            if current.price > previous.price:
                relation = "higher"
            elif current.price < previous.price:
                relation = "lower"
            else:
                relation = "equal"
            expected.append(
                (previous.index, current.index, kind.value, relation)
            )
    expected.sort(key=lambda row: (row[1], row[2]))
    return expected


def actual(points: list[SwingPoint]) -> list[tuple[int, int, str, str]]:
    return [
        (c.previous.index, c.current.index, c.current.type.value, c.relation.value)
        for c in compare_swing_sequence(points)
    ]


@pytest.mark.parametrize("seed", range(25))
def test_property_matches_an_independently_derived_oracle(seed: int) -> None:
    points = random_points(random.Random(seed), 40)
    assert sorted(actual(points)) == sorted(oracle(points))


@pytest.mark.parametrize("seed", range(25))
def test_property_every_comparison_links_same_type_points(seed: int) -> None:
    points = random_points(random.Random(100 + seed), 40)
    for c in compare_swing_sequence(points):
        assert c.previous.type is c.current.type


@pytest.mark.parametrize("seed", range(25))
def test_property_links_the_immediately_previous_same_type_point(seed: int) -> None:
    points = random_points(random.Random(200 + seed), 40)
    for c in compare_swing_sequence(points):
        between = [
            p for p in points
            if p.type is c.current.type
            and c.previous.index < p.index < c.current.index
        ]
        assert between == [], "a same-type point sits between the linked pair"


@pytest.mark.parametrize("seed", range(25))
def test_property_relation_matches_direct_price_comparison(seed: int) -> None:
    points = random_points(random.Random(300 + seed), 40)
    for c in compare_swing_sequence(points):
        if c.current.price > c.previous.price:
            assert c.relation is SwingRelation.HIGHER
        elif c.current.price < c.previous.price:
            assert c.relation is SwingRelation.LOWER
        else:
            assert c.relation is SwingRelation.EQUAL


@pytest.mark.parametrize("seed", range(25))
def test_property_output_count_and_ordering(seed: int) -> None:
    points = random_points(random.Random(400 + seed), 40)
    result = compare_swing_sequence(points)
    highs = sum(1 for p in points if p.type is SwingType.HIGH)
    lows = sum(1 for p in points if p.type is SwingType.LOW)
    assert len(result) == max(highs - 1, 0) + max(lows - 1, 0)
    order = [c.current.index for c in result]
    assert order == sorted(order)


@pytest.mark.parametrize("seed", range(25))
def test_property_prefix_stability(seed: int) -> None:
    """A comparison already emitted never changes when later points arrive."""
    points = random_points(random.Random(500 + seed), 40)
    emitted: dict[tuple[int, int, str], SwingComparison] = {}
    for length in range(len(points) + 1):
        for c in compare_swing_sequence(points[:length]):
            key = (c.previous.index, c.current.index, c.current.type.value)
            if key in emitted:
                assert emitted[key] == c, f"changed at length {length}"
            emitted[key] = c
    final = compare_swing_sequence(points)
    assert len(emitted) == len(final)


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
        "resistance", "liquidity", "strength", "confidence", "long", "short",
        "buy", "sell", "signal", "evidence", "observation",
    )
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        tokens = _code_tokens(py)
        for word in forbidden:
            assert word not in tokens, f"{py.name}: {word}"


def test_abbreviated_structural_naming_is_banned_everywhere() -> None:
    """`HH`/`HL`/`LH`/`LL` never become canonical, in any module (ADR-0014 §3)."""
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        tokens = _code_tokens(py)
        for word in ("hh", "hl", "lh", "ll", "higherhigh", "lowerlow"):
            assert word not in tokens, f"{py.name}: {word}"


def test_composite_names_appear_only_in_the_naming_layer() -> None:
    """This layer keeps type and relation separate; naming happens above it.

    Full composite names are legitimate in `models.py` (the enum) and
    `labels.py` (the mapping) since ADR-0014, but must not leak down into
    detection or comparison.
    """
    for py in (PACKAGE_DIR / "swings.py", PACKAGE_DIR / "relationships.py"):
        tokens = _code_tokens(py)
        for word in ("higher_high", "lower_high", "equal_high",
                     "higher_low", "lower_low", "equal_low"):
            assert word not in tokens, f"{py.name}: {word}"


def test_market_structure_evidence_family_remains_empty() -> None:
    from fmis.evidence import EvidenceFamily, descriptors_for

    assert descriptors_for(EvidenceFamily.MARKET_STRUCTURE) == ()


def test_no_approximate_equality_constant_in_code() -> None:
    """No tolerance in code — the docstrings may of course say there is none."""
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        tokens = _code_tokens(py)
        for marker in ("isclose", "epsilon", "tolerance", "atol", "rtol",
                       "approx"):
            assert marker not in tokens, f"{py.name}: {marker}"
        tree = ast.parse(py.read_text())
        docstrings = {
            d for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
            and (d := ast.get_docstring(node, clean=False)) is not None
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                assert node.value == 0.0 or node.value >= 1.0, (
                    f"{py.name}: suspicious float literal {node.value}"
                )
        assert docstrings  # the scan really did have prose to exclude


# ============================ public API / boundaries ========================


def test_no_public_shortcut_bypasses_swing_comparison_validation() -> None:
    """The price rule is private, so it cannot be used to skip the invariants.

    A public helper returning a relation for two arbitrary points would accept
    mixed swing types and reversed ordering — exactly what `SwingComparison`
    exists to reject — while looking like the obvious thing to call.
    """
    assert not hasattr(SwingComparison, "relation_for")
    public = {name for name in dir(SwingComparison) if not name.startswith("_")}
    assert public == {"previous", "current", "relation"}

    from fmis.market_structure import models

    assert hasattr(models, "_relation_for")          # single authority, private
    assert "_relation_for" not in ms.__all__
    assert not hasattr(ms, "relation_for")


def test_the_only_public_pair_operation_validates() -> None:
    high = sp(0, 10.0, SwingType.HIGH)
    low = SwingPoint(1, _BASE + timedelta(hours=4), 20.0, SwingType.LOW)
    with pytest.raises(ValueError, match="same SwingType"):
        compare_swings(high, low)
    with pytest.raises(ValueError, match="must be greater than"):
        compare_swings(sp(5, 1.0), sp(2, 2.0))


def test_equal_current_index_ordering_follows_input_order() -> None:
    """Documented tie-break: emission order, not enum or dict order.

    One candle can yield both a HIGH and a LOW, so two comparisons can share a
    `current.index`. Their relative order is the order the points appeared in
    the input.
    """
    def run(first: SwingType, second: SwingType) -> list[str]:
        price = {SwingType.HIGH: (50.0, 60.0), SwingType.LOW: (10.0, 20.0)}
        points = []
        for index in (10, 20):
            stamp = _BASE + timedelta(hours=4 * index)
            for kind in (first, second):
                value = price[kind][0 if index == 10 else 1]
                points.append(SwingPoint(index, stamp, value, kind))
        return [c.current.type.value for c in compare_swing_sequence(points)]

    assert run(SwingType.HIGH, SwingType.LOW) == ["high", "low"]
    assert run(SwingType.LOW, SwingType.HIGH) == ["low", "high"]


def test_detect_swings_output_gives_high_before_low_at_a_shared_index() -> None:
    bars = [(5.0, 4.0), (9.0, 1.0), (5.0, 4.0), (11.0, 0.5), (5.0, 4.0)]
    points = detect_swings(candles(bars), left_bars=1, right_bars=1)
    result = compare_swing_sequence(points)
    shared = [c for c in result if c.current.index == 3]
    assert [c.current.type.value for c in shared] == ["high", "low"]


def test_public_api_is_exactly_the_declared_surface() -> None:
    assert set(ms.__all__) == {
        "SwingType", "SwingPoint", "SwingRelation", "SwingComparison",
        "StructuralSwingLabel", "StructuralSwing",
        "detect_swings", "compare_swings", "compare_swing_sequence",
        "label_swing", "label_swing_sequence",
        "StructuralSequenceStateType", "StructuralSequenceState",
        "derive_structural_sequence_state",
        "required_candles", "DEFAULT_LEFT_BARS", "DEFAULT_RIGHT_BARS",
    }
    for name in ms.__all__:
        assert hasattr(ms, name)


def test_no_submodule_shares_a_name_with_a_public_object() -> None:
    import pkgutil

    submodules = {m.name for m in pkgutil.iter_modules(ms.__path__)}
    assert submodules == {"labels", "models", "relationships", "sequence_state",
                          "swings"}
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
        "fmis.market_structure.swings",
    }


@pytest.mark.parametrize(
    "forbidden",
    ["fmis.decision_support", "fmis.evidence", "fmis.providers", "fmis.pipeline",
     "fmis.ingest", "fmis.trading_context", "fmis.relative_value", "fmis.features"],
)
def test_does_not_depend_on_higher_or_sibling_layers(forbidden: str) -> None:
    assert not any(i.startswith(forbidden) for i in _internal_imports()), forbidden


def test_relationships_module_never_detects_or_reads_candles() -> None:
    source = (PACKAGE_DIR / "relationships.py").read_text()
    tree = ast.parse(source)
    called = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "detect_swings" not in called
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("high", "low", "close", "open", "volume",
                                     "candles")
    assert "CandleSeries" not in {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
    }


def test_no_existing_package_imports_market_structure() -> None:
    offenders: list[str] = []
    for package in ("data", "ingest", "providers", "features", "alignment",
                    "relative_value", "pipeline", "decision_support",
                    "trading_context", "evidence"):
        for py in (SRC / package).rglob("*.py"):
            for node in ast.walk(ast.parse(py.read_text())):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.startswith("fmis.market_structure"):
                        offenders.append(f"{py}:{node.lineno}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("fmis.market_structure"):
                            offenders.append(f"{py}:{node.lineno}")
    assert offenders == []


def test_uses_only_stdlib() -> None:
    roots: set[str] = set()
    for py in PACKAGE_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
    assert roots <= set(sys.stdlib_module_names) | {"fmis"}
