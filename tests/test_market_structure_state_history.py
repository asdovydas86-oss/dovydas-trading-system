"""Tests for deterministic structural sequence state history (fmis.market_structure).

Hand-built runs pin every snapshot rule and rejection. Randomized runs then assert
the properties, using an oracle that recomputes each snapshot from the raw swing
prices — a different derivation from the production lookup table, so a wrong cell
cannot pass unnoticed.

The prefix-stability contract is the reason this milestone exists, so it is tested
in all three extension modes, including the one the guarantee deliberately
**excludes**: an arbitrary cut inside a same-candle HIGH/LOW group. A test that
pins a documented limitation is worth as much as one pinning a guarantee.
"""

from __future__ import annotations

import ast
import itertools
import random
import sys
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import fmis.market_structure as ms
from fmis.data import Candle, CandleSeries
from fmis.market_structure import (
    StructuralSequenceState,
    StructuralSequenceStateSnapshot,
    StructuralSequenceStateType,
    StructuralSwing,
    StructuralSwingLabel,
    SwingPoint,
    SwingType,
    compare_swing_sequence,
    compare_swings,
    derive_structural_sequence_state,
    derive_structural_sequence_state_history,
    detect_swings,
    label_swing,
    label_swing_sequence,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
PACKAGE_DIR = Path(ms.__file__).parent

HIGH_LABELS = (
    StructuralSwingLabel.HIGHER_HIGH,
    StructuralSwingLabel.LOWER_HIGH,
    StructuralSwingLabel.EQUAL_HIGH,
)
LOW_LABELS = (
    StructuralSwingLabel.HIGHER_LOW,
    StructuralSwingLabel.LOWER_LOW,
    StructuralSwingLabel.EQUAL_LOW,
)
_PRICES: dict[StructuralSwingLabel, tuple[float, float]] = {
    StructuralSwingLabel.HIGHER_HIGH: (100.0, 110.0),
    StructuralSwingLabel.LOWER_HIGH: (110.0, 100.0),
    StructuralSwingLabel.EQUAL_HIGH: (105.0, 105.0),
    StructuralSwingLabel.HIGHER_LOW: (10.0, 20.0),
    StructuralSwingLabel.LOWER_LOW: (20.0, 10.0),
    StructuralSwingLabel.EQUAL_LOW: (15.0, 15.0),
}


def sp(index: int, price: float, type: SwingType = SwingType.HIGH) -> SwingPoint:
    return SwingPoint(index, _BASE + timedelta(hours=4 * index), price, type)


def swing(
    label: StructuralSwingLabel, previous_index: int = 0, current_index: int = 4
) -> StructuralSwing:
    type = SwingType.HIGH if label in HIGH_LABELS else SwingType.LOW
    previous_price, current_price = _PRICES[label]
    built = label_swing(
        compare_swings(
            sp(previous_index, previous_price, type),
            sp(current_index, current_price, type),
        )
    )
    assert built.label is label
    return built


def series(bars: list[tuple[float, float]]) -> CandleSeries:
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


def structures(bars: list[tuple[float, float]]) -> tuple[StructuralSwing, ...]:
    """The full deterministic chain up to labels."""
    return label_swing_sequence(
        compare_swing_sequence(detect_swings(series(bars), left_bars=1, right_bars=1))
    )


def history(bars: list[tuple[float, float]]):
    return derive_structural_sequence_state_history(structures(bars))


def shape(snapshots) -> list[tuple[int, StructuralSequenceStateType]]:
    return [(s.index, s.state.state) for s in snapshots]


def random_bars(rng: random.Random, low: int = 6, high: int = 50):
    bars = []
    for _ in range(rng.randint(low, high)):
        bottom = rng.choice([1.0, 2.0, 3.0, 4.0, 5.0])
        bars.append((bottom + rng.choice([1.0, 2.0, 3.0]), bottom))
    return bars


# ---------------------------------------------------------------------------
# Oracle: recomputed from raw prices, never from the production mapping.
# ---------------------------------------------------------------------------


def oracle_state(high, low) -> StructuralSequenceStateType:
    S = StructuralSequenceStateType
    if high is None or low is None:
        return S.INSUFFICIENT_STRUCTURE

    def direction(structure: StructuralSwing) -> int:
        comparison = structure.comparison
        return (comparison.current.price > comparison.previous.price) - (
            comparison.current.price < comparison.previous.price
        )

    h, l = direction(high), direction(low)
    if h > 0 and l > 0:
        return S.SHIFTED_HIGHER
    if h < 0 and l < 0:
        return S.SHIFTED_LOWER
    if h == 0 and l == 0:
        return S.UNCHANGED
    return S.EXPANDED if (h >= 0 and l <= 0) else S.CONTRACTED


def oracle_history(run):
    """An independent fold, written without reference to the production loop."""
    out = []
    latest: dict[SwingType, StructuralSwing] = {}
    for index in sorted({s.comparison.current.index for s in run}):
        group = [s for s in run if s.comparison.current.index == index]
        for s in group:
            latest[s.comparison.current.type] = s
        out.append(
            (
                index,
                oracle_state(latest.get(SwingType.HIGH), latest.get(SwingType.LOW)),
                tuple(group),
            )
        )
    return out


# ============================ 1-4 basic inputs ===============================


def test_empty_input_yields_an_empty_history() -> None:
    assert derive_structural_sequence_state_history([]) == ()


def test_empty_input_returns_a_tuple_not_none() -> None:
    assert isinstance(derive_structural_sequence_state_history([]), tuple)


def test_one_swing_yields_one_insufficient_snapshot() -> None:
    high = swing(StructuralSwingLabel.HIGHER_HIGH)
    result = derive_structural_sequence_state_history([high])
    assert len(result) == 1
    assert result[0].state.state is StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
    assert result[0].triggers == (high,)
    assert result[0].state.latest_high is high
    assert result[0].state.latest_low is None


@pytest.mark.parametrize("label", HIGH_LABELS + LOW_LABELS)
def test_a_single_side_is_always_insufficient(label: StructuralSwingLabel) -> None:
    result = derive_structural_sequence_state_history([swing(label)])
    assert result[0].state.state is StructuralSequenceStateType.INSUFFICIENT_STRUCTURE


def test_insufficient_snapshots_are_emitted_not_suppressed() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4),
        swing(StructuralSwingLabel.LOWER_HIGH, 4, 8),
        swing(StructuralSwingLabel.HIGHER_LOW, 1, 9),
    ]
    result = derive_structural_sequence_state_history(run)
    assert [s.state.state for s in result] == [
        StructuralSequenceStateType.INSUFFICIENT_STRUCTURE,
        StructuralSequenceStateType.INSUFFICIENT_STRUCTURE,
        StructuralSequenceStateType.CONTRACTED,
    ]


def test_the_first_complete_snapshot_is_the_first_with_both_sides() -> None:
    run = [
        swing(StructuralSwingLabel.EQUAL_HIGH, 0, 4),
        swing(StructuralSwingLabel.EQUAL_LOW, 1, 5),
    ]
    result = derive_structural_sequence_state_history(run)
    assert result[0].state.state is StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
    assert result[1].state.state is StructuralSequenceStateType.UNCHANGED


def test_a_run_with_one_side_only_never_becomes_complete() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4),
        swing(StructuralSwingLabel.LOWER_HIGH, 4, 8),
        swing(StructuralSwingLabel.EQUAL_HIGH, 8, 12),
    ]
    result = derive_structural_sequence_state_history(run)
    assert len(result) == 3
    assert all(
        s.state.state is StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
        for s in result
    )
    assert all(s.state.latest_low is None for s in result)


# ============================ 5-11 every classification ======================


@pytest.mark.parametrize("high", HIGH_LABELS)
@pytest.mark.parametrize("low", LOW_LABELS)
def test_every_complete_combination_appears_in_a_snapshot(
    high: StructuralSwingLabel, low: StructuralSwingLabel
) -> None:
    run = [swing(high, 0, 4), swing(low, 1, 5)]
    result = derive_structural_sequence_state_history(run)
    assert result[-1].state.state is oracle_state(run[0], run[1])
    assert result[-1].state.latest_high.label is high
    assert result[-1].state.latest_low.label is low


def test_every_state_type_is_reachable_in_a_history() -> None:
    reached = {
        derive_structural_sequence_state_history(
            [swing(h, 0, 4), swing(l, 1, 5)]
        )[-1].state.state
        for h, l in itertools.product(HIGH_LABELS, LOW_LABELS)
    }
    reached.add(
        derive_structural_sequence_state_history([swing(HIGH_LABELS[0])])[0].state.state
    )
    assert reached == set(StructuralSequenceStateType)


@pytest.mark.parametrize(
    "high, low, expected",
    [
        (StructuralSwingLabel.HIGHER_HIGH, StructuralSwingLabel.HIGHER_LOW,
         StructuralSequenceStateType.SHIFTED_HIGHER),
        (StructuralSwingLabel.LOWER_HIGH, StructuralSwingLabel.LOWER_LOW,
         StructuralSequenceStateType.SHIFTED_LOWER),
        (StructuralSwingLabel.HIGHER_HIGH, StructuralSwingLabel.LOWER_LOW,
         StructuralSequenceStateType.EXPANDED),
        (StructuralSwingLabel.LOWER_HIGH, StructuralSwingLabel.HIGHER_LOW,
         StructuralSequenceStateType.CONTRACTED),
        (StructuralSwingLabel.EQUAL_HIGH, StructuralSwingLabel.EQUAL_LOW,
         StructuralSequenceStateType.UNCHANGED),
    ],
)
def test_named_classifications(
    high: StructuralSwingLabel,
    low: StructuralSwingLabel,
    expected: StructuralSequenceStateType,
) -> None:
    result = derive_structural_sequence_state_history([swing(high, 0, 4), swing(low, 1, 5)])
    assert result[-1].state.state is expected


# ============================ 6 repeated states ==============================


def test_a_repeated_state_is_still_its_own_snapshot() -> None:
    """Never deduplicate: the triggers differ even when the state does not."""
    run = [
        swing(StructuralSwingLabel.EQUAL_HIGH, 0, 4),
        swing(StructuralSwingLabel.EQUAL_LOW, 1, 5),
        swing(StructuralSwingLabel.EQUAL_HIGH, 4, 8),
        swing(StructuralSwingLabel.EQUAL_LOW, 5, 9),
    ]
    result = derive_structural_sequence_state_history(run)
    assert len(result) == 4
    assert [s.state.state for s in result[1:]] == [
        StructuralSequenceStateType.UNCHANGED
    ] * 3
    assert [s.triggers for s in result] == [(run[0],), (run[1],), (run[2],), (run[3],)]


# ============================ 12-15 outside bars, equality ===================


def outside_pair(index: int, falling: bool = False):
    high = label_swing(
        compare_swings(
            sp(index - 4, 120.0 if falling else 100.0, SwingType.HIGH),
            sp(index, 110.0, SwingType.HIGH),
        )
    )
    low = label_swing(
        compare_swings(
            sp(index - 4, 20.0, SwingType.LOW), sp(index, 10.0, SwingType.LOW)
        )
    )
    return high, low


def test_outside_bar_high_then_low_yields_one_snapshot() -> None:
    high, low = outside_pair(6)
    result = derive_structural_sequence_state_history([high, low])
    assert len(result) == 1
    assert set(result[0].triggers) == {high, low}
    assert result[0].state.latest_high is high
    assert result[0].state.latest_low is low


def test_outside_bar_low_then_high_yields_one_snapshot() -> None:
    high, low = outside_pair(6)
    result = derive_structural_sequence_state_history([low, high])
    assert len(result) == 1
    assert set(result[0].triggers) == {high, low}


def test_outside_bar_state_index_and_timestamp_are_order_insensitive() -> None:
    high, low = outside_pair(6)
    a = derive_structural_sequence_state_history([high, low])
    b = derive_structural_sequence_state_history([low, high])
    assert [s.state for s in a] == [s.state for s in b]
    assert [s.index for s in a] == [s.index for s in b]
    assert [s.timestamp for s in a] == [s.timestamp for s in b]


def test_outside_bar_trigger_order_is_inherited_not_imposed() -> None:
    """ADR-0014 §8, one layer up: sorting triggers would impose HIGH-before-LOW."""
    high, low = outside_pair(6)
    assert derive_structural_sequence_state_history([high, low])[0].triggers == (high, low)
    assert derive_structural_sequence_state_history([low, high])[0].triggers == (low, high)


def test_outside_bar_is_applied_atomically() -> None:
    """No half-applied state is ever exposed.

    With a falling outside bar, applying the HIGH alone would read CONTRACTED;
    the complete candle reads SHIFTED_LOWER. Only the second is ever emitted.
    """
    older_high = swing(StructuralSwingLabel.EQUAL_HIGH, 0, 2)
    older_low = swing(StructuralSwingLabel.EQUAL_LOW, 0, 2)
    high, low = outside_pair(6, falling=True)
    result = derive_structural_sequence_state_history([older_high, older_low, high, low])
    assert [s.state.state for s in result] == [
        StructuralSequenceStateType.UNCHANGED,
        StructuralSequenceStateType.SHIFTED_LOWER,
    ]
    assert StructuralSequenceStateType.CONTRACTED not in [s.state.state for s in result]


def test_equal_highs_and_lows_flow_through_unchanged() -> None:
    run = [
        swing(StructuralSwingLabel.EQUAL_HIGH, 0, 4),
        swing(StructuralSwingLabel.EQUAL_LOW, 1, 5),
    ]
    result = derive_structural_sequence_state_history(run)
    assert result[-1].state.latest_high.label is StructuralSwingLabel.EQUAL_HIGH
    assert result[-1].state.latest_low.label is StructuralSwingLabel.EQUAL_LOW
    assert result[-1].state.state is StructuralSequenceStateType.UNCHANGED


def test_equal_timestamps_at_one_index_are_accepted() -> None:
    high, low = outside_pair(6)
    assert high.comparison.current.timestamp == low.comparison.current.timestamp
    result = derive_structural_sequence_state_history([high, low])
    assert result[0].timestamp == high.comparison.current.timestamp


# ============================ 17 invalid order ===============================


def test_a_decreasing_index_is_rejected() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 4, 8),
        swing(StructuralSwingLabel.HIGHER_LOW, 0, 4),
    ]
    with pytest.raises(ValueError) as caught:
        derive_structural_sequence_state_history(run)
    assert str(caught.value) == (
        "structures must be ordered by current index; structures[1] has "
        "index 4 after 8"
    )


def test_a_duplicate_same_type_point_is_rejected() -> None:
    one = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    with pytest.raises(ValueError) as caught:
        derive_structural_sequence_state_history([one, one])
    assert str(caught.value) == (
        "structures[1] repeats or precedes current index 4 for swing type 'high'"
    )


def test_a_mismatched_timestamp_at_an_equal_index_is_rejected() -> None:
    high = label_swing(
        compare_swings(sp(0, 100.0, SwingType.HIGH), sp(6, 110.0, SwingType.HIGH))
    )
    low = label_swing(
        compare_swings(
            SwingPoint(0, _BASE, 20.0, SwingType.LOW),
            SwingPoint(6, _BASE + timedelta(hours=999), 10.0, SwingType.LOW),
        )
    )
    with pytest.raises(ValueError) as caught:
        derive_structural_sequence_state_history([high, low])
    assert str(caught.value) == (
        "structures[1] shares current index 6 with the previous comparison but "
        "carries a different timestamp"
    )


def test_an_unordered_run_yields_no_partial_history() -> None:
    ordered = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4),
        swing(StructuralSwingLabel.HIGHER_LOW, 1, 5),
        swing(StructuralSwingLabel.LOWER_HIGH, 4, 8),
    ]
    with pytest.raises(ValueError):
        derive_structural_sequence_state_history(list(reversed(ordered)))


def test_a_non_iterable_is_rejected() -> None:
    with pytest.raises(TypeError, match="must be an iterable"):
        derive_structural_sequence_state_history(42)  # type: ignore[arg-type]


def test_a_string_is_rejected() -> None:
    with pytest.raises(TypeError, match="must be an iterable"):
        derive_structural_sequence_state_history("hh")  # type: ignore[arg-type]


def test_a_non_structural_element_is_rejected() -> None:
    with pytest.raises(TypeError) as caught:
        derive_structural_sequence_state_history(
            [swing(StructuralSwingLabel.HIGHER_HIGH), "x"]  # type: ignore[list-item]
        )
    assert str(caught.value) == "structures[1] must be a StructuralSwing, got str"


def test_a_generator_is_accepted() -> None:
    run = [
        swing(StructuralSwingLabel.EQUAL_HIGH, 0, 4),
        swing(StructuralSwingLabel.EQUAL_LOW, 1, 5),
    ]
    assert len(derive_structural_sequence_state_history(item for item in run)) == 2


# ============================ 18-20 replay and immutability ==================


def test_deterministic_replay_matches_whole_series_derivation() -> None:
    rng = random.Random(9)
    for _ in range(30):
        bars = random_bars(rng, 10, 40)
        whole = history(bars)
        replayed = None
        for k in range(1, len(bars) + 1):
            replayed = history(bars[:k])
        assert shape(replayed) == shape(whole)


def test_repeated_calls_are_equal() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4),
        swing(StructuralSwingLabel.HIGHER_LOW, 1, 5),
    ]
    assert derive_structural_sequence_state_history(
        run
    ) == derive_structural_sequence_state_history(run)


def test_input_is_not_mutated_or_reordered() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4),
        swing(StructuralSwingLabel.HIGHER_LOW, 1, 5),
        swing(StructuralSwingLabel.LOWER_HIGH, 4, 8),
    ]
    snapshot = list(run)
    derive_structural_sequence_state_history(run)
    assert run == snapshot
    assert all(a is b for a, b in zip(run, snapshot))


def test_the_history_is_an_immutable_tuple() -> None:
    result = history(
        [(10.0, 5.0), (12.0, 4.0), (11.0, 6.0), (14.0, 3.0), (13.0, 7.0)]
    )
    assert isinstance(result, tuple)


def test_snapshot_is_frozen() -> None:
    result = derive_structural_sequence_state_history([swing(HIGH_LABELS[0])])[0]
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        result.triggers = ()  # type: ignore[misc]


def test_snapshot_is_slotted_with_no_dict() -> None:
    assert StructuralSequenceStateSnapshot.__slots__ == ("state", "triggers")
    result = derive_structural_sequence_state_history([swing(HIGH_LABELS[0])])[0]
    assert not hasattr(result, "__dict__")


def test_snapshot_rejects_an_undeclared_attribute() -> None:
    result = derive_structural_sequence_state_history([swing(HIGH_LABELS[0])])[0]
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        result.extra = 1  # type: ignore[attr-defined]


def test_snapshot_is_hashable() -> None:
    a = derive_structural_sequence_state_history([swing(HIGH_LABELS[0])])[0]
    b = derive_structural_sequence_state_history([swing(HIGH_LABELS[0])])[0]
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_carry_forward_is_by_identity() -> None:
    high = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    low = swing(StructuralSwingLabel.HIGHER_LOW, 1, 5)
    later_high = swing(StructuralSwingLabel.LOWER_HIGH, 4, 8)
    result = derive_structural_sequence_state_history([high, low, later_high])
    assert result[-1].state.latest_low is low
    assert result[-1].state.latest_high is later_high
    assert result[-1].triggers == (later_high,)


# ============================ 21-22 projections ==============================


def test_snapshot_has_exactly_two_fields() -> None:
    assert [f.name for f in fields(StructuralSequenceStateSnapshot)] == [
        "state",
        "triggers",
    ]


def test_index_and_timestamp_are_not_stored_fields() -> None:
    names = {f.name for f in fields(StructuralSequenceStateSnapshot)}
    assert "index" not in names
    assert "timestamp" not in names


def test_index_and_timestamp_are_properties() -> None:
    assert isinstance(StructuralSequenceStateSnapshot.index, property)
    assert isinstance(StructuralSequenceStateSnapshot.timestamp, property)


def test_index_and_timestamp_are_read_only() -> None:
    """No setter, and the frozen dataclass refuses assignment.

    On a frozen+slots dataclass CPython raises `TypeError` here
    ("super(type, obj): obj must be an instance or subtype of type") rather than
    `AttributeError`, which is why the expectation is a tuple. The same quirk is
    already documented for undeclared attributes elsewhere in this suite.
    """
    result = derive_structural_sequence_state_history([swing(HIGH_LABELS[0])])[0]
    assert StructuralSequenceStateSnapshot.index.fset is None
    assert StructuralSequenceStateSnapshot.timestamp.fset is None
    with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
        result.index = 99  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
        result.timestamp = _BASE  # type: ignore[misc]


def test_projections_match_the_triggering_point() -> None:
    rng = random.Random(12)
    for _ in range(40):
        for snapshot in history(random_bars(rng, 10, 40)):
            current = snapshot.triggers[0].comparison.current
            assert snapshot.index == current.index
            assert snapshot.timestamp == current.timestamp
            for trigger in snapshot.triggers:
                assert trigger.comparison.current.index == snapshot.index
                assert trigger.comparison.current.timestamp == snapshot.timestamp


def test_no_structural_fact_is_duplicated_on_the_snapshot() -> None:
    names = {f.name for f in fields(StructuralSequenceStateSnapshot)}
    for duplicated in ("latest_high", "latest_low", "label", "comparison",
                       "price", "index", "timestamp", "type", "relation"):
        assert duplicated not in names


# ============================ snapshot validation ============================


def _state_of(*swings) -> StructuralSequenceState:
    high = next((s for s in swings if s.comparison.current.type is SwingType.HIGH), None)
    low = next((s for s in swings if s.comparison.current.type is SwingType.LOW), None)
    from fmis.market_structure.models import _sequence_state_for

    return StructuralSequenceState(high, low, _sequence_state_for(high, low))


def test_snapshot_rejects_a_non_state() -> None:
    with pytest.raises(TypeError, match="state must be a StructuralSequenceState"):
        StructuralSequenceStateSnapshot("x", (swing(HIGH_LABELS[0]),))  # type: ignore[arg-type]


def test_snapshot_rejects_non_tuple_triggers() -> None:
    high = swing(HIGH_LABELS[0])
    with pytest.raises(TypeError, match="triggers must be a tuple"):
        StructuralSequenceStateSnapshot(_state_of(high), [high])  # type: ignore[arg-type]


def test_snapshot_rejects_a_non_structural_trigger() -> None:
    high = swing(HIGH_LABELS[0])
    with pytest.raises(TypeError, match=r"triggers\[0\] must be a StructuralSwing"):
        StructuralSequenceStateSnapshot(_state_of(high), ("x",))  # type: ignore[arg-type]


def test_snapshot_rejects_zero_triggers() -> None:
    with pytest.raises(ValueError, match="triggers must hold one swing"):
        StructuralSequenceStateSnapshot(_state_of(), ())


def test_snapshot_rejects_three_triggers() -> None:
    high = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    low = swing(StructuralSwingLabel.HIGHER_LOW, 0, 4)
    with pytest.raises(ValueError, match="triggers must hold one swing"):
        StructuralSequenceStateSnapshot(_state_of(high, low), (high, low, high))


def test_snapshot_rejects_two_triggers_of_one_type() -> None:
    a = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    with pytest.raises(ValueError, match="distinct swing types"):
        StructuralSequenceStateSnapshot(_state_of(a), (a, a))


def test_snapshot_rejects_triggers_from_different_candles() -> None:
    high = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    low = swing(StructuralSwingLabel.HIGHER_LOW, 1, 5)
    with pytest.raises(ValueError, match="a snapshot covers one candle"):
        StructuralSequenceStateSnapshot(_state_of(high, low), (high, low))


def test_snapshot_rejects_a_trigger_the_state_does_not_hold() -> None:
    """The coherence invariant: a trigger must BE the state's latest side."""
    older = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    newer = swing(StructuralSwingLabel.LOWER_HIGH, 4, 8)
    with pytest.raises(ValueError, match="is not the state's latest"):
        StructuralSequenceStateSnapshot(_state_of(newer), (older,))


def test_snapshot_accepts_a_coherent_pair() -> None:
    high, low = outside_pair(6)
    snapshot = StructuralSequenceStateSnapshot(_state_of(high, low), (high, low))
    assert snapshot.index == 6


# ============================ 23-25 prefix stability =========================


def test_prefix_stability_under_candle_extension() -> None:
    """The guarantee this milestone exists to provide."""
    rng = random.Random(23)
    for _ in range(60):
        bars = random_bars(rng)
        full = history(bars)
        for k in range(1, len(bars) + 1):
            prefix = history(bars[:k])
            assert shape(prefix) == shape(full)[: len(prefix)]


def test_prefix_stability_under_complete_group_extension() -> None:
    rng = random.Random(24)
    for _ in range(60):
        run = structures(random_bars(rng))
        if not run:
            continue
        full = derive_structural_sequence_state_history(run)
        boundary = 0
        for snapshot in full:
            boundary += len(snapshot.triggers)
            cut = derive_structural_sequence_state_history(run[:boundary])
            assert shape(cut) == shape(full)[: len(cut)]


def test_snapshots_compare_equal_across_calls_but_are_not_identical() -> None:
    """Snapshots are rebuilt per derivation; assert `==`, never `is`."""
    bars = [(10.0, 5.0), (12.0, 4.0), (11.0, 6.0), (14.0, 3.0), (13.0, 7.0)]
    a, b = history(bars), history(bars)
    assert a == b
    if a:
        assert a[0] is not b[0]


def test_an_arbitrary_cut_inside_an_outside_bar_group_is_outside_the_guarantee() -> None:
    """The documented limitation, pinned so it cannot be discovered by accident.

    Splitting a same-candle HIGH/LOW pair gives a different — and correct — state
    for that candle, because it is a different input. It cannot arise from candle
    growth (a candle yields both swings or neither) and it is not detectable (a
    HIGH with no matching LOW is a legal run). The guarantee is therefore stated
    for candle and complete-group extension only.
    """
    older_high = swing(StructuralSwingLabel.EQUAL_HIGH, 0, 2)
    older_low = swing(StructuralSwingLabel.EQUAL_LOW, 0, 2)
    high, low = outside_pair(6, falling=True)
    run = [older_high, older_low, high, low]

    whole = derive_structural_sequence_state_history(run)
    split = derive_structural_sequence_state_history(run[:3])

    assert whole[-1].state.state is StructuralSequenceStateType.SHIFTED_LOWER
    assert split[-1].state.state is StructuralSequenceStateType.CONTRACTED
    assert shape(split) != shape(whole)[: len(split)]

    # ...and the same cut on a *complete* group boundary is stable.
    stable = derive_structural_sequence_state_history(run[:2])
    assert shape(stable) == shape(whole)[: len(stable)]


def test_a_candle_prefix_never_splits_an_outside_bar_group() -> None:
    """Why the limitation cannot arise from real data."""
    rng = random.Random(25)
    groups_seen = 0
    for _ in range(60):
        bars = random_bars(rng)
        for k in range(1, len(bars) + 1):
            for snapshot in history(bars[:k]):
                groups_seen += 1
                types = {t.comparison.current.type for t in snapshot.triggers}
                assert len(types) == len(snapshot.triggers)
    assert groups_seen > 0


# ============================ 26 equivalence contract ========================


def test_final_history_state_equals_the_single_state_function() -> None:
    rng = random.Random(31)
    checked = 0
    for _ in range(120):
        run = structures(random_bars(rng, 0, 45))
        if not run:
            continue
        checked += 1
        assert (
            derive_structural_sequence_state_history(run)[-1].state
            == derive_structural_sequence_state(run)
        )
    assert checked > 50


def test_equivalence_holds_for_hand_built_combinations() -> None:
    for high, low in itertools.product(HIGH_LABELS, LOW_LABELS):
        run = [swing(high, 0, 4), swing(low, 1, 5)]
        assert (
            derive_structural_sequence_state_history(run)[-1].state
            == derive_structural_sequence_state(run)
        )


def test_equivalence_for_empty_input() -> None:
    assert derive_structural_sequence_state_history([]) == ()
    single = derive_structural_sequence_state([])
    assert single.state is StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
    assert single.latest_high is None and single.latest_low is None


def test_equivalence_for_insufficient_input() -> None:
    run = [swing(StructuralSwingLabel.HIGHER_HIGH)]
    assert (
        derive_structural_sequence_state_history(run)[-1].state
        == derive_structural_sequence_state(run)
    )


def test_the_single_state_function_does_not_build_a_history() -> None:
    """Q4: the cheap call must stay cheap — no history allocation."""
    tree = ast.parse((PACKAGE_DIR / "sequence_state.py").read_text())
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "derive_structural_sequence_state_history" not in called
    assert "StructuralSequenceStateSnapshot" not in called


# ============================ property tests =================================


@pytest.mark.parametrize("seed", range(25))
def test_property_one_snapshot_per_distinct_index(seed: int) -> None:
    run = structures(random_bars(random.Random(seed), 0, 45))
    result = derive_structural_sequence_state_history(run)
    assert len(result) == len({s.comparison.current.index for s in run})


@pytest.mark.parametrize("seed", range(25))
def test_property_indices_strictly_increase(seed: int) -> None:
    result = derive_structural_sequence_state_history(
        structures(random_bars(random.Random(seed), 0, 45))
    )
    indices = [s.index for s in result]
    assert indices == sorted(set(indices))


@pytest.mark.parametrize("seed", range(25))
def test_property_matches_the_independent_oracle(seed: int) -> None:
    run = structures(random_bars(random.Random(seed), 0, 45))
    result = derive_structural_sequence_state_history(run)
    expected = oracle_history(run)
    assert [(s.index, s.state.state) for s in result] == [
        (index, state) for index, state, _ in expected
    ]
    assert [s.triggers for s in result] == [triggers for _, _, triggers in expected]


@pytest.mark.parametrize("seed", range(25))
def test_property_triggers_reconstruct_the_input(seed: int) -> None:
    run = structures(random_bars(random.Random(seed), 0, 45))
    result = derive_structural_sequence_state_history(run)
    rebuilt = [t for snapshot in result for t in snapshot.triggers]
    assert rebuilt == list(run)


@pytest.mark.parametrize("seed", range(25))
def test_property_sides_are_the_latest_at_or_before_each_snapshot(seed: int) -> None:
    run = structures(random_bars(random.Random(seed), 0, 45))
    result = derive_structural_sequence_state_history(run)
    for snapshot in result:
        upto = [s for s in run if s.comparison.current.index <= snapshot.index]
        highs = [s for s in upto if s.comparison.current.type is SwingType.HIGH]
        lows = [s for s in upto if s.comparison.current.type is SwingType.LOW]
        assert snapshot.state.latest_high is (highs[-1] if highs else None)
        assert snapshot.state.latest_low is (lows[-1] if lows else None)


@pytest.mark.parametrize("seed", range(25))
def test_property_insufficient_prefix_is_contiguous_and_ends_once(seed: int) -> None:
    """Once both sides exist they never become unavailable again."""
    result = derive_structural_sequence_state_history(
        structures(random_bars(random.Random(seed), 0, 45))
    )
    states = [s.state.state for s in result]
    insufficient = [
        i for i, s in enumerate(states)
        if s is StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
    ]
    assert insufficient == list(range(len(insufficient)))


@pytest.mark.parametrize("seed", range(20))
def test_property_no_input_object_is_mutated(seed: int) -> None:
    run = list(structures(random_bars(random.Random(seed), 0, 45)))
    before = [(s.label, s.comparison) for s in run]
    order = list(run)
    derive_structural_sequence_state_history(run)
    assert [(s.label, s.comparison) for s in run] == before
    assert all(a is b for a, b in zip(run, order))


# ============================ 27-30 boundaries and guards ====================


def test_public_api_includes_exactly_the_new_names() -> None:
    assert set(ms.__all__) == {
        "SwingType", "SwingPoint", "SwingRelation", "SwingComparison",
        "StructuralSwingLabel", "StructuralSwing",
        "StructuralSequenceStateType", "StructuralSequenceState",
        "StructuralSequenceStateSnapshot",
        "detect_swings", "compare_swings", "compare_swing_sequence",
        "label_swing", "label_swing_sequence",
        "derive_structural_sequence_state",
        "derive_structural_sequence_state_history",
        "required_candles", "DEFAULT_LEFT_BARS", "DEFAULT_RIGHT_BARS",
    }


def test_the_previous_public_api_remains_intact() -> None:
    previous = {
        "SwingType", "SwingPoint", "SwingRelation", "SwingComparison",
        "StructuralSwingLabel", "StructuralSwing", "StructuralSequenceStateType",
        "StructuralSequenceState", "detect_swings", "compare_swings",
        "compare_swing_sequence", "label_swing", "label_swing_sequence",
        "derive_structural_sequence_state", "required_candles",
        "DEFAULT_LEFT_BARS", "DEFAULT_RIGHT_BARS",
    }
    assert previous <= set(ms.__all__)


def test_no_submodule_collides_with_a_public_name() -> None:
    import pkgutil

    submodules = {m.name for m in pkgutil.iter_modules(ms.__path__)}
    assert submodules == {
        "labels", "models", "relationships", "sequence_state", "state_history",
        "swings",
    }
    assert submodules & set(ms.__all__) == set()


def test_no_private_helper_is_exported() -> None:
    for private in ("_sequence_state_for", "_validate_current_point_order",
                    "_validate_key_order", "_STATE_BY_LABEL_PAIR"):
        assert private not in ms.__all__
        assert not hasattr(ms, private), private


def test_no_mutable_public_object_is_exported() -> None:
    for name in ms.__all__:
        assert not isinstance(getattr(ms, name), (list, dict, set)), name


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
        "reversal", "breakout", "confirmed", "consolidation", "squeeze", "bias",
        "direction", "uptrend", "downtrend", "changed", "improving", "weakening",
        "magnitude", "duration",
    )
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        tokens = _code_tokens(py)
        for word in forbidden:
            assert word not in tokens, f"{py.name}: {word}"


def test_the_history_module_delegates_and_recomputes_nothing() -> None:
    tree = ast.parse((PACKAGE_DIR / "state_history.py").read_text())
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_sequence_state_for" in called
    assert "_validate_current_point_order" in called
    for banned in ("detect_swings", "compare_swings", "compare_swing_sequence",
                   "label_swing", "label_swing_sequence",
                   "derive_structural_sequence_state", "sorted"):
        assert banned not in called, banned


def test_the_history_module_performs_no_arithmetic_and_reads_no_candle() -> None:
    tree = ast.parse((PACKAGE_DIR / "state_history.py").read_text())
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.BinOp)]
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("high", "low", "close", "open", "volume",
                                     "candles", "price", "sort")


def test_no_state_mapping_is_reimplemented_in_the_history_module() -> None:
    """Every state member must come from the shared rule, never named here."""
    source = (PACKAGE_DIR / "state_history.py").read_text()
    for member in StructuralSequenceStateType:
        assert f"StructuralSequenceStateType.{member.name}" not in source


def test_market_structure_evidence_family_remains_empty() -> None:
    from fmis.evidence import EvidenceFamily, descriptors, descriptors_for

    assert descriptors_for(EvidenceFamily.MARKET_STRUCTURE) == ()
    assert len(descriptors()) == 6


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
