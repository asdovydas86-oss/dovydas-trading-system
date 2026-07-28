"""Tests for deterministic swing detection (fmis.market_structure).

Hand-built series pin the documented semantics — plateaus, equal extremes,
edges, confirmation delay. Randomized series then assert the properties that
must hold for *every* input, most importantly that detection never repaints:
extending a series can add swings but can never change one already reported.
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
    DEFAULT_LEFT_BARS,
    DEFAULT_RIGHT_BARS,
    SwingPoint,
    SwingType,
    detect_swings,
    required_candles,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
PACKAGE_DIR = Path(ms.__file__).parent
SRC = PACKAGE_DIR.parent  # src/fmis


def series(
    bars: list[tuple[float, float]], *, closed: bool | list[bool] = True
) -> CandleSeries:
    """A series from (high, low) pairs; open/close sit inside the range."""
    flags = closed if isinstance(closed, list) else [closed] * len(bars)
    return CandleSeries(
        symbol="BTCUSDT",
        timeframe="4h",
        candles=tuple(
            Candle(
                timestamp=_BASE + timedelta(hours=4 * i),
                symbol="BTCUSDT",
                timeframe="4h",
                open=(high + low) / 2,
                high=high,
                low=low,
                close=(high + low) / 2,
                volume=1.0,
                is_closed=flag,
            )
            for i, ((high, low), flag) in enumerate(zip(bars, flags))
        ),
    )


def highs(values: list[float], *, floor: float = 0.0) -> CandleSeries:
    """Vary only the high; every low is the same, so only highs can swing."""
    return series([(v, floor) for v in values])


def lows(values: list[float], *, ceiling: float = 1000.0) -> CandleSeries:
    """Vary only the low; every high is the same, so only lows can swing."""
    return series([(ceiling, v) for v in values])


def keys(points: tuple[SwingPoint, ...]) -> list[tuple[int, str]]:
    return [(p.index, p.type.value) for p in points]


# ============================ SwingType ======================================


def test_swing_type_members_are_exactly_high_and_low() -> None:
    assert {t.name for t in SwingType} == {"HIGH", "LOW"}
    assert SwingType.HIGH.value == "high"
    assert SwingType.LOW.value == "low"


def test_swing_type_carries_no_direction_vocabulary() -> None:
    names = {t.name for t in SwingType}
    for forbidden in ("UP", "DOWN", "BULLISH", "BEARISH", "TREND", "BOS", "CHOCH"):
        assert forbidden not in names


# ============================ SwingPoint =====================================


def point(**overrides: object) -> SwingPoint:
    kwargs: dict[str, object] = {
        "index": 3,
        "timestamp": _BASE,
        "price": 100.0,
        "type": SwingType.HIGH,
    }
    kwargs.update(overrides)
    return SwingPoint(**kwargs)  # type: ignore[arg-type]


def test_swing_point_fields_are_exactly_four() -> None:
    assert [f.name for f in fields(SwingPoint)] == [
        "index", "timestamp", "price", "type",
    ]


def test_swing_point_has_no_interpretation_fields() -> None:
    names = {f.name for f in fields(SwingPoint)}
    tokens: set[str] = set()
    for name in names:
        tokens |= set(name.split("_")) | {name}
    for forbidden in ("direction", "trend", "confidence", "strength", "bos",
                      "choch", "label", "score", "rank", "support", "resistance"):
        assert forbidden not in tokens, forbidden


def test_swing_point_is_frozen_and_slotted() -> None:
    assert SwingPoint.__slots__ == ("index", "timestamp", "price", "type")
    p = point()
    assert not hasattr(p, "__dict__")
    with pytest.raises(FrozenInstanceError):
        p.price = 1.0  # type: ignore[misc]


def test_swing_point_is_hashable_and_value_equal() -> None:
    assert point() == point()
    assert hash(point()) == hash(point())
    assert len({point(), point()}) == 1
    assert point() != point(index=4)
    assert point() != point(type=SwingType.LOW)


@pytest.mark.parametrize("bad", [True, 2.5, "3", None])
def test_swing_point_rejects_non_int_index(bad: object) -> None:
    with pytest.raises(TypeError, match="index must be an int"):
        point(index=bad)


def test_swing_point_rejects_negative_index() -> None:
    with pytest.raises(ValueError, match="index cannot be negative"):
        point(index=-1)


def test_swing_point_rejects_bad_timestamp_price_and_type() -> None:
    with pytest.raises(TypeError, match="timestamp must be a datetime"):
        point(timestamp="2024-01-01")
    with pytest.raises(TypeError, match="price must be a number"):
        point(price="100")
    with pytest.raises(ValueError, match="price must be a finite number"):
        point(price=float("nan"))
    with pytest.raises(TypeError, match="type must be a SwingType"):
        point(type="high")


# ============================ parameters =====================================


def test_required_candles_is_left_plus_right_plus_one() -> None:
    assert required_candles(1, 1) == 3
    assert required_candles(2, 2) == 5
    assert required_candles(5, 3) == 9


def test_default_bars_are_two_each() -> None:
    assert (DEFAULT_LEFT_BARS, DEFAULT_RIGHT_BARS) == (2, 2)


@pytest.mark.parametrize("field", ["left_bars", "right_bars"])
@pytest.mark.parametrize("bad", [0, -1, -5])
def test_non_positive_bars_rejected(field: str, bad: int) -> None:
    with pytest.raises(ValueError, match=f"{field} must be at least 1"):
        detect_swings(highs([1.0] * 10), **{field: bad})


@pytest.mark.parametrize("field", ["left_bars", "right_bars"])
@pytest.mark.parametrize("bad", [True, 1.5, "2", None])
def test_non_int_bars_rejected(field: str, bad: object) -> None:
    with pytest.raises(TypeError, match=f"{field} must be an int"):
        detect_swings(highs([1.0] * 10), **{field: bad})


def test_non_candle_series_rejected() -> None:
    with pytest.raises(TypeError, match="series must be a CandleSeries"):
        detect_swings([1, 2, 3])  # type: ignore[arg-type]


# ============================ basic detection ================================


def test_single_peak_is_a_swing_high() -> None:
    found = detect_swings(highs([1.0, 5.0, 1.0]), left_bars=1, right_bars=1)
    assert keys(found) == [(1, "high")]
    assert found[0].price == 5.0
    assert found[0].timestamp == _BASE + timedelta(hours=4)


def test_single_trough_is_a_swing_low() -> None:
    found = detect_swings(lows([9.0, 1.0, 9.0]), left_bars=1, right_bars=1)
    assert keys(found) == [(1, "low")]
    assert found[0].price == 1.0


def test_monotonic_series_has_no_swings() -> None:
    rising = highs([1.0, 2.0, 3.0, 4.0, 5.0])
    falling = lows([5.0, 4.0, 3.0, 2.0, 1.0])
    assert detect_swings(rising, left_bars=1, right_bars=1) == ()
    assert detect_swings(falling, left_bars=1, right_bars=1) == ()


def test_outside_bar_is_both_a_high_and_a_low() -> None:
    found = detect_swings(
        series([(5.0, 5.0), (9.0, 1.0), (5.0, 5.0)]), left_bars=1, right_bars=1
    )
    assert keys(found) == [(1, "high"), (1, "low")]
    assert found[0].price == 9.0 and found[1].price == 1.0


def test_price_is_the_extreme_not_the_close() -> None:
    found = detect_swings(highs([1.0, 7.0, 1.0]), left_bars=1, right_bars=1)
    assert found[0].price == 7.0  # the high, not (high+low)/2 used as close


def test_multiple_swings_in_one_series() -> None:
    found = detect_swings(
        highs([1.0, 5.0, 1.0, 8.0, 2.0, 6.0, 1.0]), left_bars=1, right_bars=1
    )
    assert keys(found) == [(1, "high"), (3, "high"), (5, "high")]


# ============================ left / right behaviour =========================


def test_wider_left_requires_more_left_neighbours() -> None:
    # index 2 (5.0) exceeds its immediate left neighbour (1.0) but not the
    # one before it (9.0).
    bars = [9.0, 1.0, 5.0, 1.0, 1.0]
    one = keys(detect_swings(highs(bars), left_bars=1, right_bars=1))
    two = keys(detect_swings(highs(bars), left_bars=2, right_bars=1))
    assert (2, "high") in one and (2, "high") not in two


def test_wider_right_requires_more_right_neighbours() -> None:
    # index 1 tops its immediate right neighbour but not the one after.
    bars = [1.0, 5.0, 3.0, 9.0, 1.0]
    one = keys(detect_swings(highs(bars), left_bars=1, right_bars=1))
    two = keys(detect_swings(highs(bars), left_bars=1, right_bars=2))
    assert (1, "high") in one and (1, "high") not in two


def test_asymmetric_bars_are_supported() -> None:
    found = detect_swings(
        highs([1.0, 2.0, 3.0, 9.0, 3.0, 1.0]), left_bars=3, right_bars=2
    )
    assert keys(found) == [(3, "high")]


# ============================ equal highs / lows / plateaus ==================


def test_plateau_of_equal_highs_yields_exactly_one_swing_at_the_first_bar() -> None:
    found = detect_swings(highs([1.0, 5.0, 5.0, 1.0]), left_bars=1, right_bars=1)
    assert keys(found) == [(1, "high")]


def test_longer_plateau_still_yields_exactly_one_swing() -> None:
    found = detect_swings(
        highs([1.0, 5.0, 5.0, 5.0, 5.0, 1.0]), left_bars=1, right_bars=1
    )
    assert keys(found) == [(1, "high")]


def test_plateau_of_equal_lows_yields_exactly_one_swing_at_the_first_bar() -> None:
    found = detect_swings(lows([9.0, 2.0, 2.0, 9.0]), left_bars=1, right_bars=1)
    assert keys(found) == [(1, "low")]


def test_separated_equal_highs_are_two_distinct_swings() -> None:
    # A double top: same price, two local maxima, both reported.
    found = detect_swings(highs([1.0, 5.0, 1.0, 5.0, 1.0]), left_bars=1, right_bars=1)
    assert keys(found) == [(1, "high"), (3, "high")]
    assert {p.price for p in found} == {5.0}


def test_separated_equal_lows_are_two_distinct_swings() -> None:
    found = detect_swings(lows([9.0, 2.0, 9.0, 2.0, 9.0]), left_bars=1, right_bars=1)
    assert keys(found) == [(1, "low"), (3, "low")]


def test_completely_flat_series_has_no_swings() -> None:
    # Every candle ties every neighbour, so the strict left test always fails.
    assert detect_swings(series([(5.0, 1.0)] * 10), left_bars=1, right_bars=1) == ()


def test_equal_left_neighbour_blocks_a_swing() -> None:
    # Strict on the left: a tie to the left is not a swing.
    assert detect_swings(highs([5.0, 5.0, 1.0]), left_bars=1, right_bars=1) == ()


def test_equal_right_neighbour_permits_a_swing() -> None:
    # Non-strict on the right: a tie to the right still confirms.
    assert keys(detect_swings(highs([1.0, 5.0, 5.0]), left_bars=1, right_bars=1)) == [
        (1, "high")
    ]


# ============================ edges / insufficient history ===================


def test_empty_series_yields_no_swings() -> None:
    assert detect_swings(series([]), left_bars=1, right_bars=1) == ()


def test_fewer_than_required_candles_yields_no_swings() -> None:
    for count in range(required_candles(2, 2)):
        bars = highs([float(i) for i in range(count)])
        assert detect_swings(bars, left_bars=2, right_bars=2) == ()


def test_exactly_required_candles_can_yield_a_swing() -> None:
    found = detect_swings(
        highs([1.0, 2.0, 9.0, 2.0, 1.0]), left_bars=2, right_bars=2
    )
    assert keys(found) == [(2, "high")]
    assert len(highs([1.0, 2.0, 9.0, 2.0, 1.0]).candles) == required_candles(2, 2)


def test_first_left_bars_and_last_right_bars_are_never_swings() -> None:
    values = [9.0, 1.0, 9.0, 1.0, 9.0, 1.0, 9.0]
    found = detect_swings(series([(v, v) for v in values]), left_bars=2, right_bars=2)
    for p in found:
        assert 2 <= p.index <= len(values) - 1 - 2


def test_a_peak_at_the_very_end_is_not_yet_confirmed() -> None:
    # In this snapshot the newest right_bars candles cannot yet be classified;
    # see test_confirmation_frontier_advances_as_candles_arrive for what
    # happens once more candles close.
    assert detect_swings(highs([1.0, 2.0, 9.0]), left_bars=1, right_bars=1) == ()


def test_confirmation_frontier_advances_as_candles_arrive() -> None:
    """Unconfirmed is a property of the snapshot, not of the candle.

    A candidate too near the end to classify becomes eligible once the required
    right-side candles close. "Non-repainting" means confirmed output is stable,
    not that the frontier is frozen.
    """
    values = [1.0, 9.0, 2.0, 2.0, 2.0]
    # Too near the end at first...
    assert detect_swings(highs(values[:3]), left_bars=1, right_bars=2) == ()
    # ...then eligible, and stable from then on.
    for length in range(4, len(values) + 1):
        found = detect_swings(highs(values[:length]), left_bars=1, right_bars=2)
        assert keys(found) == [(1, "high")]


def test_frontier_advance_never_alters_an_already_emitted_point() -> None:
    values = [1.0, 9.0, 2.0, 5.0, 1.0, 7.0, 1.0, 3.0, 3.0]
    emitted: dict[tuple[int, str], SwingPoint] = {}
    for length in range(len(values) + 1):
        for p in detect_swings(highs(values[:length]), left_bars=1, right_bars=1):
            key = (p.index, p.type.value)
            if key in emitted:
                assert emitted[key] == p, f"{key} changed at length {length}"
            emitted[key] = p
    assert emitted  # the walk actually produced points


# ============================ confirmation delay =============================


def test_swing_appears_only_once_the_right_bars_have_closed() -> None:
    values = [1.0, 9.0, 2.0, 3.0]
    # With right_bars=2 the peak at index 1 needs indices 2 and 3 to exist.
    assert detect_swings(highs(values[:3]), left_bars=1, right_bars=2) == ()
    assert keys(detect_swings(highs(values), left_bars=1, right_bars=2)) == [
        (1, "high")
    ]


def test_confirmation_delay_equals_right_bars() -> None:
    values = [1.0, 9.0] + [2.0] * 5
    for right in (1, 2, 3):
        needed = 2 + right  # peak at index 1 plus its right neighbours
        short = highs(values[:needed - 1])
        assert detect_swings(short, left_bars=1, right_bars=right) == ()
        assert keys(
            detect_swings(highs(values[:needed]), left_bars=1, right_bars=right)
        ) == [(1, "high")]


# ============================ closed candles only ============================


def test_forming_candles_are_excluded() -> None:
    # The forming final bar would otherwise confirm the peak at index 1.
    bars = [(1.0, 1.0), (9.0, 9.0), (2.0, 2.0)]
    assert detect_swings(
        series(bars, closed=[True, True, False]), left_bars=1, right_bars=1
    ) == ()
    assert keys(
        detect_swings(series(bars, closed=True), left_bars=1, right_bars=1)
    ) == [(1, "high")]


def test_indices_are_positions_in_the_closed_subsequence() -> None:
    bars = [(1.0, 1.0), (9.0, 9.0), (1.0, 1.0), (5.0, 5.0)]
    found = detect_swings(
        series(bars, closed=[True, True, True, False]), left_bars=1, right_bars=1
    )
    assert keys(found) == [(1, "high")]
    assert found[0].timestamp == _BASE + timedelta(hours=4)


def test_a_forming_candle_cannot_change_an_existing_swing() -> None:
    closed_only = detect_swings(
        highs([1.0, 9.0, 1.0, 2.0]), left_bars=1, right_bars=1
    )
    with_forming = detect_swings(
        series([(1.0, 0.0), (9.0, 0.0), (1.0, 0.0), (2.0, 0.0), (99.0, 0.0)],
               closed=[True, True, True, True, False]),
        left_bars=1, right_bars=1,
    )
    assert closed_only == with_forming


# ============================ ordering / immutability ========================


def test_result_is_an_immutable_tuple() -> None:
    found = detect_swings(highs([1.0, 5.0, 1.0]), left_bars=1, right_bars=1)
    assert isinstance(found, tuple)
    with pytest.raises(TypeError):
        found[0] = None  # type: ignore[index]


def test_results_are_sorted_by_index_then_type() -> None:
    values = [9.0, 1.0, 9.0, 1.0, 9.0, 1.0, 9.0, 1.0, 9.0]
    found = detect_swings(series([(v, v) for v in values]), left_bars=1, right_bars=1)
    assert keys(found) == sorted(keys(found))
    assert len(found) > 2


def test_high_precedes_low_at_the_same_index() -> None:
    found = detect_swings(
        series([(5.0, 5.0), (9.0, 1.0), (5.0, 5.0)]), left_bars=1, right_bars=1
    )
    assert [p.type for p in found] == [SwingType.HIGH, SwingType.LOW]


def test_input_series_is_not_mutated() -> None:
    candles = highs([1.0, 5.0, 1.0, 8.0, 1.0])
    before = tuple((c.high, c.low, c.timestamp) for c in candles.candles)
    detect_swings(candles, left_bars=1, right_bars=1)
    assert tuple((c.high, c.low, c.timestamp) for c in candles.candles) == before


# ============================ determinism ====================================


def test_repeated_detection_is_identical() -> None:
    candles = highs([1.0, 5.0, 2.0, 9.0, 3.0, 7.0, 1.0])
    assert detect_swings(candles) == detect_swings(candles)


def test_detection_is_a_pure_function_of_values_and_parameters() -> None:
    a = detect_swings(highs([1.0, 5.0, 1.0, 8.0, 1.0]), left_bars=1, right_bars=1)
    b = detect_swings(highs([1.0, 5.0, 1.0, 8.0, 1.0]), left_bars=1, right_bars=1)
    assert a == b
    assert keys(a) == keys(b)


# ============================ property-style randomized ======================


def random_bars(rng: random.Random, count: int) -> list[tuple[float, float]]:
    """Random but valid OHLC ranges, with deliberate ties to hit plateaus."""
    out: list[tuple[float, float]] = []
    for _ in range(count):
        low = float(rng.randint(0, 12))
        high = low + float(rng.randint(0, 8))
        out.append((high, low))
    return out


@pytest.mark.parametrize("seed", range(25))
def test_property_detection_is_deterministic(seed: int) -> None:
    rng = random.Random(seed)
    candles = series(random_bars(rng, 60))
    assert detect_swings(candles, left_bars=2, right_bars=2) == detect_swings(
        candles, left_bars=2, right_bars=2
    )


@pytest.mark.parametrize("seed", range(25))
def test_property_never_repaints_when_the_series_grows(seed: int) -> None:
    """The central guarantee: later candles never revise an earlier swing.

    Detecting on the first ``k`` candles must give exactly the swings the full
    run reports at indices that were already confirmable at ``k``.
    """
    rng = random.Random(seed)
    left, right = 2, 3
    bars = random_bars(rng, 50)
    full = detect_swings(series(bars), left_bars=left, right_bars=right)

    for k in range(len(bars) + 1):
        prefix = detect_swings(series(bars[:k]), left_bars=left, right_bars=right)
        expected = tuple(p for p in full if p.index <= k - 1 - right)
        assert prefix == expected, f"seed={seed} k={k}"


@pytest.mark.parametrize("seed", range(25))
def test_property_invariants_hold_for_every_result(seed: int) -> None:
    rng = random.Random(seed)
    left, right = rng.randint(1, 4), rng.randint(1, 4)
    bars = random_bars(rng, 70)
    candles = series(bars)
    found = detect_swings(candles, left_bars=left, right_bars=right)

    assert keys(found) == sorted(keys(found))                 # ordered
    assert len(set(keys(found))) == len(found)                # no duplicates
    for p in found:
        assert left <= p.index <= len(bars) - 1 - right       # inside the window
        candle = candles.candles[p.index]
        assert p.timestamp == candle.timestamp
        expected = candle.high if p.type is SwingType.HIGH else candle.low
        assert p.price == expected                            # the true extreme


@pytest.mark.parametrize("seed", range(25))
def test_property_detected_swings_really_are_local_extremes(seed: int) -> None:
    """Re-derive the rule independently and compare, rather than trusting it."""
    rng = random.Random(seed)
    left, right = 2, 2
    bars = random_bars(rng, 60)
    found = detect_swings(series(bars), left_bars=left, right_bars=right)

    highs_ = [b[0] for b in bars]
    lows_ = [b[1] for b in bars]
    expected: list[tuple[int, str]] = []
    for i in range(left, len(bars) - right):
        if all(highs_[i] > highs_[j] for j in range(i - left, i)) and all(
            highs_[i] >= highs_[j] for j in range(i + 1, i + right + 1)
        ):
            expected.append((i, "high"))
        if all(lows_[i] < lows_[j] for j in range(i - left, i)) and all(
            lows_[i] <= lows_[j] for j in range(i + 1, i + right + 1)
        ):
            expected.append((i, "low"))
    assert keys(found) == sorted(expected)


@pytest.mark.parametrize("seed", range(15))
def test_property_flat_regions_never_produce_adjacent_duplicate_swings(
    seed: int,
) -> None:
    """Plateaus must collapse: no two swings of one type at consecutive indices."""
    rng = random.Random(seed)
    bars = [(float(rng.choice([3, 3, 3, 5, 7])), 0.0) for _ in range(60)]
    found = detect_swings(series(bars), left_bars=1, right_bars=1)
    high_indices = [p.index for p in found if p.type is SwingType.HIGH]
    assert all(b - a > 1 for a, b in zip(high_indices, high_indices[1:]))


# ============================ scope: nothing interpreted =====================


def test_no_structure_interpretation_vocabulary_in_code() -> None:
    forbidden = (
        # Note: bare "higher"/"lower" are the legitimate SwingRelation member
        # names since ADR-0013. What stays forbidden is fusing them with the
        # swing type into a composite label, which is interpretation.
        "bos", "choch", "trend", "support", "resistance",
        "liquidity", "breakout", "bullish", "bearish", "buy", "sell", "signal",
        "strength", "confidence", "score",
        "hh", "hl", "lh", "ll", "higherhigh", "lowerlow",
        "higher_high", "higher_low", "lower_high", "lower_low",
    )
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        tree = ast.parse(py.read_text())
        docstrings = {
            d for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
            and (d := ast.get_docstring(node, clean=False)) is not None
        }
        tokens: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value not in docstrings:
                    tokens |= set(node.value.lower().replace("_", " ").split())
            elif isinstance(node, ast.Name):
                tokens |= set(node.id.lower().split("_")) | {node.id.lower()}
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                tokens |= set(node.name.lower().split("_")) | {node.name.lower()}
        for word in forbidden:
            assert word not in tokens, f"{py.name}: {word}"


def test_public_api_is_exactly_the_declared_surface() -> None:
    assert set(ms.__all__) == {
        "SwingType", "SwingPoint", "SwingRelation", "SwingComparison",
        "detect_swings", "compare_swings", "compare_swing_sequence",
        "required_candles", "DEFAULT_LEFT_BARS", "DEFAULT_RIGHT_BARS",
    }
    for name in ms.__all__:
        assert hasattr(ms, name)


# ============================ import boundaries ==============================


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


def test_imports_only_the_canonical_data_models() -> None:
    assert _internal_imports() <= {
        "fmis.data",
        "fmis.market_structure.models",
        "fmis.market_structure.relationships",
        "fmis.market_structure.swings",
    }


@pytest.mark.parametrize(
    "forbidden",
    ["fmis.decision_support", "fmis.evidence", "fmis.providers", "fmis.pipeline",
     "fmis.ingest", "fmis.trading_context", "fmis.relative_value", "fmis.features"],
)
def test_does_not_depend_on_higher_or_sibling_layers(forbidden: str) -> None:
    assert not any(i.startswith(forbidden) for i in _internal_imports()), forbidden


def test_no_existing_package_imports_market_structure() -> None:
    """No lower or sibling package *imports* this one.

    Checked against real import statements rather than raw text: the
    `fmis.features.market_structure` placeholder docstring deliberately points
    readers here, and a text scan would misread that pointer as a dependency.
    """
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


def test_scanned_packages_actually_exist() -> None:
    for package in ("data", "ingest", "providers", "features", "alignment",
                    "relative_value", "pipeline", "decision_support",
                    "trading_context", "evidence"):
        assert (SRC / package / "__init__.py").is_file(), package


def test_uses_only_stdlib() -> None:
    roots: set[str] = set()
    for py in PACKAGE_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
    assert roots <= set(sys.stdlib_module_names) | {"fmis"}


def test_importing_market_structure_loads_nothing_beyond_data(
    fresh_fmis_imports: None,
) -> None:
    import fmis.market_structure  # noqa: F401

    loaded = {m for m in sys.modules if m.startswith("fmis.")}
    for forbidden in ("fmis.decision_support", "fmis.evidence", "fmis.pipeline",
                      "fmis.providers", "fmis.features"):
        assert not any(m.startswith(forbidden) for m in loaded), forbidden
