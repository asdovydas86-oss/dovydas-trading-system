"""Tests for the deterministic structural sequence state (fmis.market_structure).

Hand-built runs pin all nine complete combinations, every insufficient case and
every rejection. Randomized runs then assert the properties, using an oracle that
derives the state from each side's *outward / inward / static* movement rather
than re-listing the production lookup table, so a wrong table cell cannot pass
unnoticed.
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
    StructuralSequenceStateType,
    StructuralSwing,
    StructuralSwingLabel,
    SwingPoint,
    SwingType,
    compare_swing_sequence,
    compare_swings,
    derive_structural_sequence_state,
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

# Prices producing each label, as (previous, current).
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
    """A `StructuralSwing` carrying exactly ``label``, at chosen indices."""
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


def chain(bars: list[tuple[float, float]], **kwargs) -> StructuralSequenceState:
    """The full deterministic chain: candles -> detect -> compare -> label -> state."""
    points = detect_swings(series(bars, **kwargs), left_bars=1, right_bars=1)
    return derive_structural_sequence_state(
        label_swing_sequence(compare_swing_sequence(points))
    )


# ---------------------------------------------------------------------------
# The oracle. Deliberately a *different derivation* from the production table:
# each side is reduced to whether it moved outward from its own previous swing,
# inward, or not at all, and the state follows from that pair.
# ---------------------------------------------------------------------------

_OUTWARD = {StructuralSwingLabel.HIGHER_HIGH, StructuralSwingLabel.LOWER_LOW}
_INWARD = {StructuralSwingLabel.LOWER_HIGH, StructuralSwingLabel.HIGHER_LOW}


def _movement(label: StructuralSwingLabel) -> str:
    if label in _OUTWARD:
        return "out"
    if label in _INWARD:
        return "in"
    return "static"


def oracle_state(
    high: StructuralSwingLabel | None, low: StructuralSwingLabel | None
) -> StructuralSequenceStateType:
    if high is None or low is None:
        return StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
    moves = (_movement(high), _movement(low))
    if moves == ("out", "in"):
        return StructuralSequenceStateType.SHIFTED_HIGHER
    if moves == ("in", "out"):
        return StructuralSequenceStateType.SHIFTED_LOWER
    if moves == ("static", "static"):
        return StructuralSequenceStateType.UNCHANGED
    if "in" in moves:
        return StructuralSequenceStateType.CONTRACTED
    return StructuralSequenceStateType.EXPANDED


# ============================ enum ===========================================


def test_state_enum_membership_is_exact() -> None:
    assert {member.name for member in StructuralSequenceStateType} == {
        "SHIFTED_HIGHER",
        "SHIFTED_LOWER",
        "EXPANDED",
        "CONTRACTED",
        "UNCHANGED",
        "INSUFFICIENT_STRUCTURE",
    }


def test_state_enum_values_are_lowercase_names() -> None:
    for member in StructuralSequenceStateType:
        assert member.value == member.name.lower()


def test_state_enum_is_a_str_enum() -> None:
    assert issubclass(StructuralSequenceStateType, str)
    assert StructuralSequenceStateType.EXPANDED == "expanded"


@pytest.mark.parametrize(
    "banned",
    ["BULLISH", "BEARISH", "UPTREND", "DOWNTREND", "TREND", "LONG", "SHORT", "BUY",
     "SELL", "CONTINUATION", "REVERSAL", "BREAKOUT", "BOS", "CHOCH", "STRONG",
     "WEAK", "CONFIRMED", "SUPPORT", "RESISTANCE", "LIQUIDITY", "CONSOLIDATION",
     "DOUBLE_TOP", "DOUBLE_BOTTOM", "SCORE", "CONFIDENCE", "SIGNAL"],
)
def test_state_enum_carries_no_interpretation_vocabulary(banned: str) -> None:
    names = {member.name for member in StructuralSequenceStateType}
    values = {member.value for member in StructuralSequenceStateType}
    assert banned not in names
    assert banned.lower() not in values


def test_there_is_no_catch_all_member() -> None:
    """The five complete states partition all nine cells, so MIXED is unneeded."""
    names = {member.name for member in StructuralSequenceStateType}
    for catch_all in ("MIXED", "OTHER", "UNKNOWN", "UNDEFINED", "NEUTRAL"):
        assert catch_all not in names


def test_every_complete_state_is_reachable_from_a_real_combination() -> None:
    reached = {
        derive_structural_sequence_state([swing(h), swing(l, 1, 5)]).state
        for h, l in itertools.product(HIGH_LABELS, LOW_LABELS)
    }
    assert reached == set(StructuralSequenceStateType) - {
        StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
    }


# ============================ the nine combinations ==========================


@pytest.mark.parametrize("high", HIGH_LABELS)
@pytest.mark.parametrize("low", LOW_LABELS)
def test_every_complete_combination_matches_the_oracle(
    high: StructuralSwingLabel, low: StructuralSwingLabel
) -> None:
    result = derive_structural_sequence_state([swing(high), swing(low, 1, 5)])
    assert result.state is oracle_state(high, low)
    assert result.latest_high.label is high
    assert result.latest_low.label is low


def test_higher_high_with_higher_low_is_shifted_higher() -> None:
    result = derive_structural_sequence_state(
        [swing(StructuralSwingLabel.HIGHER_HIGH), swing(StructuralSwingLabel.HIGHER_LOW, 1, 5)]
    )
    assert result.state is StructuralSequenceStateType.SHIFTED_HIGHER


def test_lower_high_with_lower_low_is_shifted_lower() -> None:
    result = derive_structural_sequence_state(
        [swing(StructuralSwingLabel.LOWER_HIGH), swing(StructuralSwingLabel.LOWER_LOW, 1, 5)]
    )
    assert result.state is StructuralSequenceStateType.SHIFTED_LOWER


def test_lower_high_with_higher_low_is_contracted() -> None:
    result = derive_structural_sequence_state(
        [swing(StructuralSwingLabel.LOWER_HIGH), swing(StructuralSwingLabel.HIGHER_LOW, 1, 5)]
    )
    assert result.state is StructuralSequenceStateType.CONTRACTED


def test_higher_high_with_lower_low_is_expanded() -> None:
    result = derive_structural_sequence_state(
        [swing(StructuralSwingLabel.HIGHER_HIGH), swing(StructuralSwingLabel.LOWER_LOW, 1, 5)]
    )
    assert result.state is StructuralSequenceStateType.EXPANDED


@pytest.mark.parametrize(
    "high, low, expected",
    [
        (StructuralSwingLabel.EQUAL_HIGH, StructuralSwingLabel.HIGHER_LOW,
         StructuralSequenceStateType.CONTRACTED),
        (StructuralSwingLabel.EQUAL_HIGH, StructuralSwingLabel.LOWER_LOW,
         StructuralSequenceStateType.EXPANDED),
        (StructuralSwingLabel.EQUAL_HIGH, StructuralSwingLabel.EQUAL_LOW,
         StructuralSequenceStateType.UNCHANGED),
        (StructuralSwingLabel.HIGHER_HIGH, StructuralSwingLabel.EQUAL_LOW,
         StructuralSequenceStateType.EXPANDED),
        (StructuralSwingLabel.LOWER_HIGH, StructuralSwingLabel.EQUAL_LOW,
         StructuralSequenceStateType.CONTRACTED),
    ],
)
def test_the_five_equality_combinations(
    high: StructuralSwingLabel,
    low: StructuralSwingLabel,
    expected: StructuralSequenceStateType,
) -> None:
    result = derive_structural_sequence_state([swing(high), swing(low, 1, 5)])
    assert result.state is expected


def test_equality_cases_are_not_all_collapsed_into_one_state() -> None:
    """Five equality combinations, three different states — not one bucket."""
    states = {
        derive_structural_sequence_state([swing(h), swing(l, 1, 5)]).state
        for h, l in itertools.product(HIGH_LABELS, LOW_LABELS)
        if StructuralSwingLabel.EQUAL_HIGH in (h, l)
        or StructuralSwingLabel.EQUAL_LOW in (h, l)
    }
    assert states == {
        StructuralSequenceStateType.CONTRACTED,
        StructuralSequenceStateType.EXPANDED,
        StructuralSequenceStateType.UNCHANGED,
    }


def test_the_exact_pair_survives_the_grouping() -> None:
    """Two combinations sharing a state are still distinguishable from the result."""
    a = derive_structural_sequence_state(
        [swing(StructuralSwingLabel.HIGHER_HIGH), swing(StructuralSwingLabel.LOWER_LOW, 1, 5)]
    )
    b = derive_structural_sequence_state(
        [swing(StructuralSwingLabel.HIGHER_HIGH), swing(StructuralSwingLabel.EQUAL_LOW, 1, 5)]
    )
    assert a.state is b.state is StructuralSequenceStateType.EXPANDED
    assert a.latest_low.label is not b.latest_low.label


def test_each_complete_pair_maps_to_exactly_one_state() -> None:
    seen: dict[tuple[StructuralSwingLabel, StructuralSwingLabel], set] = {}
    for h, l in itertools.product(HIGH_LABELS, LOW_LABELS):
        for indices in ((0, 4), (2, 6), (10, 14)):
            result = derive_structural_sequence_state(
                [swing(h, *indices), swing(l, indices[0] + 1, indices[1] + 1)]
            )
            seen.setdefault((h, l), set()).add(result.state)
    assert len(seen) == 9
    assert all(len(states) == 1 for states in seen.values())


# ============================ the model ======================================


def test_model_has_exactly_three_fields() -> None:
    assert [f.name for f in fields(StructuralSequenceState)] == [
        "latest_high",
        "latest_low",
        "state",
    ]


def test_model_duplicates_no_structural_field() -> None:
    names = {f.name for f in fields(StructuralSequenceState)}
    for duplicated in ("label", "comparison", "previous", "current", "relation",
                       "price", "index", "timestamp", "type", "high_label",
                       "low_label"):
        assert duplicated not in names


def test_model_is_frozen() -> None:
    result = derive_structural_sequence_state([swing(StructuralSwingLabel.HIGHER_HIGH)])
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        result.state = StructuralSequenceStateType.EXPANDED  # type: ignore[misc]


def test_model_is_slotted_and_has_no_dict() -> None:
    assert StructuralSequenceState.__slots__ == ("latest_high", "latest_low", "state")
    result = derive_structural_sequence_state([])
    assert not hasattr(result, "__dict__")


def test_model_rejects_an_undeclared_attribute() -> None:
    """CPython frozen+slots raises TypeError here, not AttributeError."""
    result = derive_structural_sequence_state([])
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        result.extra = 1  # type: ignore[attr-defined]


def test_model_is_hashable() -> None:
    a = derive_structural_sequence_state([swing(StructuralSwingLabel.EQUAL_HIGH)])
    b = derive_structural_sequence_state([swing(StructuralSwingLabel.EQUAL_HIGH)])
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_model_rejects_an_invalid_high_side_object() -> None:
    with pytest.raises(TypeError, match="latest_high"):
        StructuralSequenceState(
            latest_high="higher_high",  # type: ignore[arg-type]
            latest_low=None,
            state=StructuralSequenceStateType.INSUFFICIENT_STRUCTURE,
        )


def test_model_rejects_an_invalid_low_side_object() -> None:
    with pytest.raises(TypeError, match="latest_low"):
        StructuralSequenceState(
            latest_high=None,
            latest_low=StructuralSwingLabel.LOWER_LOW,  # type: ignore[arg-type]
            state=StructuralSequenceStateType.INSUFFICIENT_STRUCTURE,
        )


def test_model_rejects_a_low_side_swing_in_the_high_slot() -> None:
    with pytest.raises(ValueError, match="latest_high must hold a 'high' swing"):
        StructuralSequenceState(
            latest_high=swing(StructuralSwingLabel.LOWER_LOW),
            latest_low=None,
            state=StructuralSequenceStateType.INSUFFICIENT_STRUCTURE,
        )


def test_model_rejects_a_high_side_swing_in_the_low_slot() -> None:
    with pytest.raises(ValueError, match="latest_low must hold a 'low' swing"):
        StructuralSequenceState(
            latest_high=None,
            latest_low=swing(StructuralSwingLabel.HIGHER_HIGH),
            state=StructuralSequenceStateType.INSUFFICIENT_STRUCTURE,
        )


def test_model_rejects_an_invalid_state_object() -> None:
    with pytest.raises(TypeError, match="state must be a StructuralSequenceStateType"):
        StructuralSequenceState(latest_high=None, latest_low=None, state="unchanged")  # type: ignore[arg-type]


def test_model_rejects_an_inconsistent_manual_construction() -> None:
    with pytest.raises(ValueError, match="does not match the latest sides"):
        StructuralSequenceState(
            latest_high=swing(StructuralSwingLabel.HIGHER_HIGH),
            latest_low=swing(StructuralSwingLabel.HIGHER_LOW, 1, 5),
            state=StructuralSequenceStateType.CONTRACTED,
        )


def test_model_rejects_a_complete_state_claimed_with_a_missing_side() -> None:
    with pytest.raises(ValueError, match="does not match the latest sides"):
        StructuralSequenceState(
            latest_high=swing(StructuralSwingLabel.HIGHER_HIGH),
            latest_low=None,
            state=StructuralSequenceStateType.EXPANDED,
        )


def test_model_rejects_insufficient_claimed_for_a_complete_pair() -> None:
    with pytest.raises(ValueError, match="does not match the latest sides"):
        StructuralSequenceState(
            latest_high=swing(StructuralSwingLabel.EQUAL_HIGH),
            latest_low=swing(StructuralSwingLabel.EQUAL_LOW, 1, 5),
            state=StructuralSequenceStateType.INSUFFICIENT_STRUCTURE,
        )


@pytest.mark.parametrize("high, low", list(itertools.product(HIGH_LABELS, LOW_LABELS)))
def test_every_wrong_state_is_rejected_for_every_pair(
    high: StructuralSwingLabel, low: StructuralSwingLabel
) -> None:
    correct = oracle_state(high, low)
    for candidate in StructuralSequenceStateType:
        if candidate is correct:
            continue
        with pytest.raises(ValueError):
            StructuralSequenceState(
                latest_high=swing(high),
                latest_low=swing(low, 1, 5),
                state=candidate,
            )


# ============================ insufficient data ==============================


def test_empty_input_is_insufficient_with_both_sides_absent() -> None:
    result = derive_structural_sequence_state([])
    assert result.state is StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
    assert result.latest_high is None
    assert result.latest_low is None


@pytest.mark.parametrize("high", HIGH_LABELS)
def test_high_side_only_is_insufficient_but_keeps_the_side_it_has(
    high: StructuralSwingLabel,
) -> None:
    result = derive_structural_sequence_state([swing(high)])
    assert result.state is StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
    assert result.latest_high.label is high
    assert result.latest_low is None


@pytest.mark.parametrize("low", LOW_LABELS)
def test_low_side_only_is_insufficient_but_keeps_the_side_it_has(
    low: StructuralSwingLabel,
) -> None:
    result = derive_structural_sequence_state([swing(low)])
    assert result.state is StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
    assert result.latest_low.label is low
    assert result.latest_high is None


def test_one_side_never_fabricates_a_complete_state() -> None:
    for label in HIGH_LABELS + LOW_LABELS:
        result = derive_structural_sequence_state([swing(label)])
        assert result.state is StructuralSequenceStateType.INSUFFICIENT_STRUCTURE


def test_a_single_swing_of_each_type_is_needed_before_a_state_exists() -> None:
    """A first HIGH label alone stays insufficient; the first LOW completes it."""
    high = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    low = swing(StructuralSwingLabel.HIGHER_LOW, 1, 5)
    assert (
        derive_structural_sequence_state([high]).state
        is StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
    )
    assert (
        derive_structural_sequence_state([high, low]).state
        is StructuralSequenceStateType.SHIFTED_HIGHER
    )


def test_a_run_with_no_low_side_at_all_never_becomes_complete() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4),
        swing(StructuralSwingLabel.LOWER_HIGH, 4, 8),
        swing(StructuralSwingLabel.EQUAL_HIGH, 8, 12),
    ]
    for length in range(1, len(run) + 1):
        result = derive_structural_sequence_state(run[:length])
        assert result.state is StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
        assert result.latest_low is None


# ============================ latest-side selection ==========================


def test_a_newer_high_replaces_an_older_high() -> None:
    first = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    second = swing(StructuralSwingLabel.LOWER_HIGH, 4, 8)
    result = derive_structural_sequence_state([first, second])
    assert result.latest_high is second


def test_a_newer_low_replaces_an_older_low() -> None:
    first = swing(StructuralSwingLabel.HIGHER_LOW, 0, 4)
    second = swing(StructuralSwingLabel.LOWER_LOW, 4, 8)
    result = derive_structural_sequence_state([first, second])
    assert result.latest_low is second


def test_a_new_high_leaves_the_latest_low_unchanged() -> None:
    low = swing(StructuralSwingLabel.HIGHER_LOW, 1, 5)
    high_a = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    high_b = swing(StructuralSwingLabel.LOWER_HIGH, 4, 8)
    before = derive_structural_sequence_state([high_a, low])
    after = derive_structural_sequence_state([high_a, low, high_b])
    assert before.latest_low is after.latest_low is low
    assert after.latest_high is high_b


def test_a_new_low_leaves_the_latest_high_unchanged() -> None:
    high = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    low_a = swing(StructuralSwingLabel.HIGHER_LOW, 1, 5)
    low_b = swing(StructuralSwingLabel.LOWER_LOW, 5, 9)
    before = derive_structural_sequence_state([high, low_a])
    after = derive_structural_sequence_state([high, low_a, low_b])
    assert before.latest_high is after.latest_high is high
    assert after.latest_low is low_b


def test_irregular_interleaving_selects_the_last_of_each_side() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4),
        swing(StructuralSwingLabel.HIGHER_LOW, 1, 5),
        swing(StructuralSwingLabel.LOWER_HIGH, 4, 8),
        swing(StructuralSwingLabel.EQUAL_LOW, 5, 9),
        swing(StructuralSwingLabel.LOWER_HIGH, 8, 12),
        swing(StructuralSwingLabel.EQUAL_HIGH, 12, 16),
        swing(StructuralSwingLabel.LOWER_LOW, 9, 17),
    ]
    result = derive_structural_sequence_state(run)
    assert result.latest_high is run[5]
    assert result.latest_low is run[6]
    assert result.state is StructuralSequenceStateType.EXPANDED


def test_the_latest_high_is_not_the_first_high() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4),
        swing(StructuralSwingLabel.EQUAL_LOW, 1, 5),
        swing(StructuralSwingLabel.EQUAL_HIGH, 4, 8),
    ]
    result = derive_structural_sequence_state(run)
    assert result.latest_high is run[2]
    assert result.state is StructuralSequenceStateType.UNCHANGED


def test_the_latest_low_is_not_the_first_low() -> None:
    run = [
        swing(StructuralSwingLabel.EQUAL_HIGH, 0, 4),
        swing(StructuralSwingLabel.LOWER_LOW, 1, 5),
        swing(StructuralSwingLabel.EQUAL_LOW, 5, 9),
    ]
    result = derive_structural_sequence_state(run)
    assert result.latest_low is run[2]
    assert result.state is StructuralSequenceStateType.UNCHANGED


# ============================ outside bars ===================================


def outside_pair(index: int) -> tuple[StructuralSwing, StructuralSwing]:
    """A HIGH-side and a LOW-side swing sharing one current index and timestamp."""
    high = label_swing(
        compare_swings(sp(index - 4, 100.0, SwingType.HIGH), sp(index, 110.0, SwingType.HIGH))
    )
    low = label_swing(
        compare_swings(sp(index - 4, 20.0, SwingType.LOW), sp(index, 10.0, SwingType.LOW))
    )
    return high, low


def test_an_equal_index_outside_bar_pair_is_accepted() -> None:
    high, low = outside_pair(6)
    result = derive_structural_sequence_state([high, low])
    assert result.latest_high is high
    assert result.latest_low is low
    assert result.state is StructuralSequenceStateType.EXPANDED


def test_an_equal_index_pair_is_accepted_in_either_order() -> None:
    high, low = outside_pair(6)
    assert (
        derive_structural_sequence_state([low, high]).state
        is derive_structural_sequence_state([high, low]).state
    )


def test_an_equal_index_pair_updates_both_sides_at_once() -> None:
    older_high = swing(StructuralSwingLabel.EQUAL_HIGH, 0, 2)
    older_low = swing(StructuralSwingLabel.EQUAL_LOW, 0, 2)
    high, low = outside_pair(6)
    before = derive_structural_sequence_state([older_high, older_low])
    after = derive_structural_sequence_state([older_high, older_low, high, low])
    assert before.state is StructuralSequenceStateType.UNCHANGED
    assert after.latest_high is high
    assert after.latest_low is low
    assert after.state is StructuralSequenceStateType.EXPANDED


def falling_outside_pair(index: int) -> tuple[StructuralSwing, StructuralSwing]:
    """An outside-bar pair labelling LOWER_HIGH and LOWER_LOW at one index."""
    high = label_swing(
        compare_swings(
            sp(index - 4, 120.0, SwingType.HIGH), sp(index, 110.0, SwingType.HIGH)
        )
    )
    low = label_swing(
        compare_swings(
            sp(index - 4, 20.0, SwingType.LOW), sp(index, 10.0, SwingType.LOW)
        )
    )
    assert (high.label, low.label) == (
        StructuralSwingLabel.LOWER_HIGH,
        StructuralSwingLabel.LOWER_LOW,
    )
    return high, low


def test_an_outside_bar_exposes_no_intermediate_state() -> None:
    """The whole run resolves atomically: only the final pair produces a state.

    Both halves of one candle are applied before anything is reported. Feeding
    the HIGH half alone — which no caller would do, but which a per-entry
    implementation would effectively do internally — gives a materially
    different answer, so this is not a vacuous check.
    """
    older_high = swing(StructuralSwingLabel.EQUAL_HIGH, 0, 2)
    older_low = swing(StructuralSwingLabel.EQUAL_LOW, 0, 2)
    high, low = falling_outside_pair(6)
    full = derive_structural_sequence_state([older_high, older_low, high, low])
    partial = derive_structural_sequence_state([older_high, older_low, high])
    assert partial.state is StructuralSequenceStateType.CONTRACTED
    assert full.state is StructuralSequenceStateType.SHIFTED_LOWER
    assert full.latest_low is low
    assert partial.latest_low is older_low


def test_the_two_selected_sides_need_not_share_an_index() -> None:
    high = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    low = swing(StructuralSwingLabel.HIGHER_LOW, 20, 40)
    result = derive_structural_sequence_state([high, low])
    assert result.latest_high.comparison.current.index != (
        result.latest_low.comparison.current.index
    )
    assert result.state is StructuralSequenceStateType.SHIFTED_HIGHER


# ============================ ordering =======================================


def test_a_normally_ordered_run_is_accepted() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4),
        swing(StructuralSwingLabel.HIGHER_LOW, 1, 5),
        swing(StructuralSwingLabel.LOWER_HIGH, 4, 8),
    ]
    assert derive_structural_sequence_state(run).state is (
        StructuralSequenceStateType.CONTRACTED
    )


def test_a_decreasing_current_index_is_rejected() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 4, 8),
        swing(StructuralSwingLabel.HIGHER_LOW, 0, 4),
    ]
    with pytest.raises(ValueError, match="must be ordered by current index"):
        derive_structural_sequence_state(run)


def test_a_decreasing_current_timestamp_is_rejected() -> None:
    earlier = SwingPoint(8, _BASE + timedelta(hours=99), 100.0, SwingType.HIGH)
    later = SwingPoint(9, _BASE + timedelta(hours=1), 10.0, SwingType.LOW)
    first = label_swing(compare_swings(sp(0, 90.0, SwingType.HIGH), earlier))
    second = label_swing(
        compare_swings(
            SwingPoint(2, _BASE, 20.0, SwingType.LOW), later
        )
    )
    with pytest.raises(ValueError, match="must be ordered by current timestamp"):
        derive_structural_sequence_state([first, second])


def test_a_duplicate_same_type_current_point_is_rejected() -> None:
    one = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    with pytest.raises(ValueError, match="repeats or precedes current index"):
        derive_structural_sequence_state([one, one])


def test_two_high_side_comparisons_ending_on_one_index_are_rejected() -> None:
    a = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    b = swing(StructuralSwingLabel.LOWER_HIGH, 1, 4)
    with pytest.raises(ValueError, match="repeats or precedes current index"):
        derive_structural_sequence_state([a, b])


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
    with pytest.raises(ValueError, match="shares current index"):
        derive_structural_sequence_state([high, low])


def test_the_error_message_names_the_callers_parameter() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 4, 8),
        swing(StructuralSwingLabel.HIGHER_LOW, 0, 4),
    ]
    with pytest.raises(ValueError, match=r"structures\[1\]"):
        derive_structural_sequence_state(run)


def test_only_the_parameter_name_differs_from_the_labelling_layer() -> None:
    """The shared rule substitutes the caller's parameter and nothing else.

    Extracting the ordering check must not reword what `label_swing_sequence`
    already ships, so the two messages are compared directly rather than by
    substring.
    """
    comparisons = [
        compare_swings(sp(4, 1.0), sp(8, 2.0)),
        compare_swings(sp(0, 1.0, SwingType.LOW), sp(4, 2.0, SwingType.LOW)),
    ]
    with pytest.raises(ValueError) as from_labels:
        label_swing_sequence(comparisons)
    with pytest.raises(ValueError) as from_state:
        derive_structural_sequence_state([label_swing(c) for c in comparisons])
    assert str(from_labels.value).replace("comparisons", "structures") == str(
        from_state.value
    )


def test_input_is_not_mutated_or_sorted() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4),
        swing(StructuralSwingLabel.HIGHER_LOW, 1, 5),
        swing(StructuralSwingLabel.LOWER_HIGH, 4, 8),
    ]
    snapshot = list(run)
    derive_structural_sequence_state(run)
    assert run == snapshot
    assert all(a is b for a, b in zip(run, snapshot))


def test_an_unsorted_run_is_rejected_rather_than_sorted() -> None:
    ordered = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4),
        swing(StructuralSwingLabel.HIGHER_LOW, 1, 5),
        swing(StructuralSwingLabel.LOWER_HIGH, 4, 8),
    ]
    with pytest.raises(ValueError):
        derive_structural_sequence_state(list(reversed(ordered)))


def test_a_generator_is_accepted_and_fully_consumed() -> None:
    run = [
        swing(StructuralSwingLabel.EQUAL_HIGH, 0, 4),
        swing(StructuralSwingLabel.EQUAL_LOW, 1, 5),
    ]
    result = derive_structural_sequence_state(item for item in run)
    assert result.state is StructuralSequenceStateType.UNCHANGED


def test_a_non_iterable_is_rejected() -> None:
    with pytest.raises(TypeError, match="must be an iterable"):
        derive_structural_sequence_state(42)  # type: ignore[arg-type]


def test_a_string_is_rejected_rather_than_iterated_character_by_character() -> None:
    with pytest.raises(TypeError, match="must be an iterable"):
        derive_structural_sequence_state("higher_high")  # type: ignore[arg-type]


def test_a_non_structural_element_is_rejected() -> None:
    with pytest.raises(TypeError, match=r"structures\[1\] must be a StructuralSwing"):
        derive_structural_sequence_state(
            [swing(StructuralSwingLabel.HIGHER_HIGH), "higher_low"]  # type: ignore[list-item]
        )


def test_a_bare_comparison_is_rejected() -> None:
    comparison = compare_swings(sp(0, 100.0), sp(4, 110.0))
    with pytest.raises(TypeError, match="must be a StructuralSwing"):
        derive_structural_sequence_state([comparison])  # type: ignore[list-item]


# ============================ aggregate evolution ============================


def test_the_aggregate_state_may_change_when_a_new_fact_arrives() -> None:
    high = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    low = swing(StructuralSwingLabel.HIGHER_LOW, 1, 5)
    later_low = swing(StructuralSwingLabel.LOWER_LOW, 5, 9)
    before = derive_structural_sequence_state([high, low])
    after = derive_structural_sequence_state([high, low, later_low])
    assert before.state is StructuralSequenceStateType.SHIFTED_HIGHER
    assert after.state is StructuralSequenceStateType.EXPANDED


def test_the_underlying_structural_facts_are_unchanged_by_extension() -> None:
    high = swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4)
    low = swing(StructuralSwingLabel.HIGHER_LOW, 1, 5)
    later_low = swing(StructuralSwingLabel.LOWER_LOW, 5, 9)
    before = derive_structural_sequence_state([high, low])
    snapshot = (high.label, low.label, low.comparison)
    after = derive_structural_sequence_state([high, low, later_low])
    assert (high.label, low.label, low.comparison) == snapshot
    assert before.latest_high is after.latest_high is high


def test_evolution_is_deterministic() -> None:
    run = [
        swing(StructuralSwingLabel.HIGHER_HIGH, 0, 4),
        swing(StructuralSwingLabel.HIGHER_LOW, 1, 5),
        swing(StructuralSwingLabel.LOWER_LOW, 5, 9),
    ]
    states = [
        tuple(
            derive_structural_sequence_state(run[:length]).state
            for length in range(len(run) + 1)
        )
        for _ in range(5)
    ]
    assert len(set(states)) == 1
    assert states[0] == (
        StructuralSequenceStateType.INSUFFICIENT_STRUCTURE,
        StructuralSequenceStateType.INSUFFICIENT_STRUCTURE,
        StructuralSequenceStateType.SHIFTED_HIGHER,
        StructuralSequenceStateType.EXPANDED,
    )


def test_repeated_calls_return_equal_results() -> None:
    run = [swing(StructuralSwingLabel.EQUAL_HIGH), swing(StructuralSwingLabel.EQUAL_LOW, 1, 5)]
    assert derive_structural_sequence_state(run) == derive_structural_sequence_state(run)


def test_a_forming_candle_cannot_reach_this_layer() -> None:
    """No candle is consumed here, so a forming bar is irrelevant by construction.

    The chain below differs only in whether the last bar has closed; detection
    already excludes it, so the state is identical.
    """
    bars = [(10.0, 5.0), (12.0, 4.0), (11.0, 6.0), (14.0, 3.0), (13.0, 7.0),
            (16.0, 2.0), (15.0, 8.0)]
    closed = [True] * 6 + [False]
    assert chain(bars[:-1]).state is chain(bars, closed=closed).state


def test_the_full_chain_produces_a_state() -> None:
    bars = [(10.0, 5.0), (12.0, 4.0), (11.0, 6.0), (14.0, 3.0), (13.0, 7.0),
            (16.0, 2.0), (15.0, 8.0)]
    result = chain(bars)
    assert isinstance(result, StructuralSequenceState)
    assert result.state in set(StructuralSequenceStateType)


# ============================ property-style =================================


def random_run(rng: random.Random, length: int) -> list[StructuralSwing]:
    """A valid interleaved run: per-type strictly increasing, globally sorted."""
    points: list[SwingPoint] = []
    index = 0
    for _ in range(length):
        index += rng.randint(1, 3)
        type = rng.choice((SwingType.HIGH, SwingType.LOW))
        price = rng.choice((10.0, 20.0, 30.0))
        points.append(sp(index, price, type))
    return list(label_swing_sequence(compare_swing_sequence(tuple(points))))


@pytest.mark.parametrize("seed", range(25))
def test_property_latest_sides_are_the_last_of_each_kind(seed: int) -> None:
    rng = random.Random(seed)
    run = random_run(rng, rng.randint(0, 14))
    result = derive_structural_sequence_state(run)
    highs = [s for s in run if s.comparison.current.type is SwingType.HIGH]
    lows = [s for s in run if s.comparison.current.type is SwingType.LOW]
    assert result.latest_high is (highs[-1] if highs else None)
    assert result.latest_low is (lows[-1] if lows else None)


@pytest.mark.parametrize("seed", range(25))
def test_property_state_matches_the_independent_oracle(seed: int) -> None:
    rng = random.Random(seed)
    run = random_run(rng, rng.randint(0, 14))
    result = derive_structural_sequence_state(run)
    expected = oracle_state(
        result.latest_high.label if result.latest_high else None,
        result.latest_low.label if result.latest_low else None,
    )
    assert result.state is expected


@pytest.mark.parametrize("seed", range(25))
def test_property_no_input_object_is_mutated(seed: int) -> None:
    rng = random.Random(seed)
    run = random_run(rng, rng.randint(0, 14))
    snapshot = [(s.label, s.comparison) for s in run]
    order = list(run)
    derive_structural_sequence_state(run)
    assert [(s.label, s.comparison) for s in run] == snapshot
    assert all(a is b for a, b in zip(run, order))


@pytest.mark.parametrize("seed", range(25))
def test_property_output_is_deterministic(seed: int) -> None:
    rng = random.Random(seed)
    run = random_run(rng, rng.randint(0, 14))
    assert derive_structural_sequence_state(run) == derive_structural_sequence_state(run)


@pytest.mark.parametrize("seed", range(25))
def test_property_insufficient_never_hides_a_complete_pair(seed: int) -> None:
    rng = random.Random(seed)
    run = random_run(rng, rng.randint(0, 14))
    result = derive_structural_sequence_state(run)
    both_sides = result.latest_high is not None and result.latest_low is not None
    complete = result.state is not StructuralSequenceStateType.INSUFFICIENT_STRUCTURE
    assert both_sides == complete


@pytest.mark.parametrize("seed", range(25))
def test_property_the_chain_from_random_candles_holds(seed: int) -> None:
    rng = random.Random(seed)
    bars: list[tuple[float, float]] = []
    for _ in range(rng.randint(3, 40)):
        low = rng.choice((1.0, 2.0, 3.0, 4.0, 5.0))
        bars.append((low + rng.choice((1.0, 2.0, 3.0)), low))
    result = chain(bars)
    assert isinstance(result, StructuralSequenceState)
    expected = oracle_state(
        result.latest_high.label if result.latest_high else None,
        result.latest_low.label if result.latest_low else None,
    )
    assert result.state is expected


@pytest.mark.parametrize("seed", range(20))
def test_property_prefixes_never_alter_an_already_emitted_structural_swing(
    seed: int,
) -> None:
    rng = random.Random(seed)
    run = random_run(rng, rng.randint(2, 14))
    for length in range(len(run) + 1):
        result = derive_structural_sequence_state(run[:length])
        if result.latest_high is not None:
            assert result.latest_high in run[:length]
        if result.latest_low is not None:
            assert result.latest_low in run[:length]


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
        "consolidation", "squeeze", "bias", "direction", "uptrend", "downtrend",
    )
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        tokens = _code_tokens(py)
        for word in forbidden:
            assert word not in tokens, f"{py.name}: {word}"


def test_no_approximate_equality_introduced() -> None:
    tokens = _code_tokens(PACKAGE_DIR / "sequence_state.py")
    for marker in ("isclose", "epsilon", "tolerance", "atol", "rtol", "approx",
                   "round", "decimal", "tick", "atr", "percent"):
        assert marker not in tokens, marker


def test_the_state_module_consumes_no_candle_and_reruns_nothing() -> None:
    tree = ast.parse((PACKAGE_DIR / "sequence_state.py").read_text())
    called = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for banned in ("detect_swings", "compare_swings", "compare_swing_sequence",
                   "label_swing", "label_swing_sequence", "sorted"):
        assert banned not in called, banned
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("high", "low", "close", "open", "volume",
                                     "candles", "price", "sort")


def test_the_state_module_never_compares_prices() -> None:
    """No arithmetic or numeric comparison: the state is a lookup on two labels."""
    tree = ast.parse((PACKAGE_DIR / "sequence_state.py").read_text())
    for node in ast.walk(tree):
        assert not isinstance(node, ast.BinOp)
        if isinstance(node, ast.Compare):
            for op in node.ops:
                assert isinstance(op, (ast.Is, ast.IsNot, ast.In, ast.NotIn)), op


def test_market_structure_evidence_family_remains_empty() -> None:
    from fmis.evidence import EvidenceFamily, descriptors, descriptors_for

    assert descriptors_for(EvidenceFamily.MARKET_STRUCTURE) == ()
    assert len(descriptors()) == 6


def test_no_transition_or_interpretation_api_was_introduced() -> None:
    """State history landed in Z1; transition *interpretation* did not.

    This guard originally also forbade a history API. That milestone has since
    been delivered deliberately (ADR-0016), so the history names are no longer
    listed — but everything that would read a sequence rather than record it is
    still forbidden, and the list has grown rather than shrunk.
    """
    for name in ("structural_sequence_state_sequence",
                 "derive_structural_sequence_states", "transitions",
                 "StructuralSequenceTransition", "derive_transitions",
                 "state_changed", "trend", "regime", "bias"):
        assert not hasattr(ms, name), name


# ============================ public API / boundaries ========================


def test_public_api_is_exactly_the_declared_surface() -> None:
    assert set(ms.__all__) == {
        "SwingType", "SwingPoint", "SwingRelation", "SwingComparison",
        "StructuralSwingLabel", "StructuralSwing",
        "StructuralSequenceStateType", "StructuralSequenceState",
        "detect_swings", "compare_swings", "compare_swing_sequence",
        "label_swing", "label_swing_sequence",
        "StructuralSequenceStateType", "StructuralSequenceState",
        "StructuralSequenceStateSnapshot",
        "derive_structural_sequence_state", "derive_structural_sequence_state_history",
        "required_candles", "DEFAULT_LEFT_BARS", "DEFAULT_RIGHT_BARS",
    }
    for name in ms.__all__:
        assert hasattr(ms, name)


def test_the_previous_public_api_remains_intact() -> None:
    """Every name the labelling milestone exported is still exported."""
    previous = {
        "SwingType", "SwingPoint", "SwingRelation", "SwingComparison",
        "StructuralSwingLabel", "StructuralSwing", "detect_swings",
        "compare_swings", "compare_swing_sequence", "label_swing",
        "label_swing_sequence", "required_candles", "DEFAULT_LEFT_BARS",
        "DEFAULT_RIGHT_BARS",
    }
    assert previous <= set(ms.__all__)


def test_no_mutable_public_object_is_exported() -> None:
    for name in ms.__all__:
        assert not isinstance(getattr(ms, name), (list, dict, set)), name


def test_no_helper_leaked_into_the_public_surface() -> None:
    for private in ("_STATE_BY_LABEL_PAIR", "_sequence_state_for",
                    "_validate_current_point_order", "state_for", "_movement"):
        assert private not in ms.__all__
        assert not hasattr(ms, private), private


def test_the_state_mapping_is_internal_and_immutable() -> None:
    from types import MappingProxyType

    from fmis.market_structure import models

    assert isinstance(models._STATE_BY_LABEL_PAIR, MappingProxyType)
    assert len(models._STATE_BY_LABEL_PAIR) == 9
    with pytest.raises(TypeError):
        models._STATE_BY_LABEL_PAIR[("x", "y")] = None  # type: ignore[index]


def test_the_state_mapping_covers_every_complete_combination_exactly_once() -> None:
    from fmis.market_structure import models

    assert set(models._STATE_BY_LABEL_PAIR) == set(
        itertools.product(HIGH_LABELS, LOW_LABELS)
    )


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


def test_the_ordering_rule_has_exactly_one_implementation() -> None:
    """Both consuming layers call the shared validator rather than re-deriving it."""
    for module in ("labels.py", "sequence_state.py"):
        tree = ast.parse((PACKAGE_DIR / module).read_text())
        called = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "_validate_current_point_order" in called, module
