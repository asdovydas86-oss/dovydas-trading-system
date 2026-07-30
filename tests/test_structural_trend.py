"""Tests for the deterministic structural trend (fmis.structural_trend).

Hand-built state runs pin every policy rule and rejection. Generated matrices then
assert the properties against an **independent oracle** that derives the trend by a
different method — filter the directional states, then scan from the right for the
last opposition — rather than by the production left fold, so a wrong step or a
wrong classification order cannot pass unnoticed.

The chosen policy is a *policy*, not a measurement, so the tests that matter most
are the ones pinning what it refuses to do: it never reports a direction on an
alternating history, never lets a non-directional state end a trend, never folds
`NEUTRAL` into `INDETERMINATE`, and never survives a single opposing shift.

Prefix stability is tested in all three modes, including the one the guarantee
deliberately **excludes** — an arbitrary cut inside a same-candle HIGH/LOW group.
A test that pins a documented limitation is worth as much as one pinning a
guarantee, and it is what stops the limitation being "fixed" into a false claim.
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

import fmis.structural_trend as st
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
    derive_structural_sequence_state_history,
    detect_swings,
    label_swing,
    label_swing_sequence,
)
from fmis.structural_trend import (
    MINIMUM_DIRECTIONAL_SHIFTS,
    StructuralTrendSnapshot,
    StructuralTrendType,
    derive_structural_trend,
    derive_structural_trend_history,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
PACKAGE_DIR = Path(st.__file__).parent

S = StructuralSequenceStateType
TT = StructuralTrendType

#: One-letter shorthand for a state, used to write history specs compactly.
BY_LETTER = {
    "H": S.SHIFTED_HIGHER,
    "L": S.SHIFTED_LOWER,
    "E": S.EXPANDED,
    "C": S.CONTRACTED,
    "U": S.UNCHANGED,
    "I": S.INSUFFICIENT_STRUCTURE,
}
NON_DIRECTIONAL = (S.EXPANDED, S.CONTRACTED, S.UNCHANGED, S.INSUFFICIENT_STRUCTURE)
DIRECTIONAL = (S.SHIFTED_HIGHER, S.SHIFTED_LOWER)

_PRICES: dict[StructuralSwingLabel, tuple[float, float]] = {
    StructuralSwingLabel.HIGHER_HIGH: (100.0, 110.0),
    StructuralSwingLabel.LOWER_HIGH: (110.0, 100.0),
    StructuralSwingLabel.EQUAL_HIGH: (100.0, 100.0),
    StructuralSwingLabel.HIGHER_LOW: (50.0, 60.0),
    StructuralSwingLabel.LOWER_LOW: (60.0, 50.0),
    StructuralSwingLabel.EQUAL_LOW: (50.0, 50.0),
}
#: The label pair producing each complete state, read off ADR-0015 §2's matrix.
_LABELS_FOR_STATE: dict[
    StructuralSequenceStateType, tuple[StructuralSwingLabel, StructuralSwingLabel]
] = {
    S.SHIFTED_HIGHER: (
        StructuralSwingLabel.HIGHER_HIGH,
        StructuralSwingLabel.HIGHER_LOW,
    ),
    S.SHIFTED_LOWER: (
        StructuralSwingLabel.LOWER_HIGH,
        StructuralSwingLabel.LOWER_LOW,
    ),
    S.EXPANDED: (StructuralSwingLabel.HIGHER_HIGH, StructuralSwingLabel.LOWER_LOW),
    S.CONTRACTED: (StructuralSwingLabel.LOWER_HIGH, StructuralSwingLabel.HIGHER_LOW),
    S.UNCHANGED: (StructuralSwingLabel.EQUAL_HIGH, StructuralSwingLabel.EQUAL_LOW),
}


# ============================== builders =====================================


def swing(label: StructuralSwingLabel, index: int) -> StructuralSwing:
    """One `StructuralSwing` carrying ``label``, confirmed at ``index``."""
    # endswith, not "in": "higher_low" contains "high" but is a LOW-side label.
    kind = SwingType.HIGH if label.value.endswith("high") else SwingType.LOW
    earlier, later = _PRICES[label]
    previous = SwingPoint(index=0, timestamp=_BASE, price=earlier, type=kind)
    current = SwingPoint(
        index=index,
        timestamp=_BASE + timedelta(hours=4 * index),
        price=later,
        type=kind,
    )
    return label_swing(compare_swings(previous, current))


def snapshot(state: StructuralSequenceStateType, index: int) -> (
    StructuralSequenceStateSnapshot
):
    """A valid state snapshot at ``index`` whose state is ``state``.

    A complete state is built as an outside bar — both sides confirmed at the one
    index — so the snapshot's triggers are its own latest sides with no reliance on
    carry-forward. `INSUFFICIENT_STRUCTURE` is built from a HIGH side alone, which
    is the only way that state can arise.
    """
    if state is S.INSUFFICIENT_STRUCTURE:
        high = swing(StructuralSwingLabel.HIGHER_HIGH, index)
        return StructuralSequenceStateSnapshot(
            state=StructuralSequenceState(
                latest_high=high, latest_low=None, state=state
            ),
            triggers=(high,),
        )
    high_label, low_label = _LABELS_FOR_STATE[state]
    high, low = swing(high_label, index), swing(low_label, index)
    return StructuralSequenceStateSnapshot(
        state=StructuralSequenceState(
            latest_high=high, latest_low=low, state=state
        ),
        triggers=(high, low),
    )


def history(spec: str) -> tuple[StructuralSequenceStateSnapshot, ...]:
    """A snapshot history whose states follow ``spec``, one letter per snapshot."""
    return tuple(
        snapshot(BY_LETTER[letter], position + 1)
        for position, letter in enumerate(spec)
    )


def states_of(spec: str) -> list[StructuralSequenceStateType]:
    return [BY_LETTER[letter] for letter in spec]


def trends(spec: str) -> list[StructuralTrendType]:
    return [s.trend for s in derive_structural_trend_history(history(spec))]


# ============================== the oracle ===================================


def oracle(states: list[StructuralSequenceStateType]) -> StructuralTrendType:
    """The trend, derived by a deliberately different method than production.

    Production folds left, carrying an accumulator. This filters to the directional
    states first, then scans **from the right** for the trailing same-direction run
    and separately checks whether any adjacent pair ever disagreed. Two independent
    derivations of one policy: a wrong step rule or a wrong classification order in
    production shows up as a disagreement here.
    """
    shifts = [s for s in states if s in DIRECTIONAL]
    if not shifts:
        return TT.INDETERMINATE

    contested = any(a is not b for a, b in zip(shifts, shifts[1:]))

    latest = shifts[-1]
    length = 0
    for s in reversed(shifts):
        if s is not latest:
            break
        length += 1

    if length >= MINIMUM_DIRECTIONAL_SHIFTS:
        return (
            TT.SUSTAINED_HIGHER
            if latest is S.SHIFTED_HIGHER
            else TT.SUSTAINED_LOWER
        )
    return TT.NEUTRAL if contested else TT.INDETERMINATE


def oracle_history(states: list[StructuralSequenceStateType]) -> list[
    StructuralTrendType
]:
    return [oracle(states[: n + 1]) for n in range(len(states))]


# ========================= candle-derived pipeline ===========================


def series(rows: list[tuple[float, float, float, float]]) -> CandleSeries:
    candles = tuple(
        Candle(
            timestamp=_BASE + timedelta(hours=4 * position),
            symbol="BTCUSDT",
            timeframe="4h",
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=10.0,
            is_closed=True,
        )
        for position, (o, h, lo, c) in enumerate(rows)
    )
    return CandleSeries(symbol="BTCUSDT", timeframe="4h", candles=candles)


def structural_run(candles: tuple[Candle, ...]) -> tuple[StructuralSwing, ...]:
    whole = CandleSeries(symbol="BTCUSDT", timeframe="4h", candles=candles)
    return label_swing_sequence(
        compare_swing_sequence(detect_swings(whole, left_bars=1, right_bars=1))
    )


def state_history(candles: tuple[Candle, ...]) -> tuple[
    StructuralSequenceStateSnapshot, ...
]:
    return derive_structural_sequence_state_history(structural_run(candles))


def random_rows(
    rng: random.Random, count: int, drift: float, outside_every: int = 0
) -> list[tuple[float, float, float, float]]:
    """A deterministic pseudo-random OHLC run, optionally with engulfing bars."""
    rows: list[tuple[float, float, float, float]] = []
    level = 100.0
    for position in range(count):
        level += rng.uniform(-3, 3) + drift
        span = (
            rng.uniform(6, 10)
            if outside_every and position % outside_every == 0
            else rng.uniform(0.5, 3)
        )
        o = level
        c = level + rng.uniform(-1, 1)
        rows.append((o, max(o, c) + span, min(o, c) - span, c))
    return rows


def random_state_history(
    seed: int, count: int = 50, outside: bool = False
) -> tuple[StructuralSequenceStateSnapshot, ...]:
    rng = random.Random(seed)
    rows = random_rows(rng, count, (seed % 3 - 1) * 1.2, 3 if outside else 0)
    return state_history(series(rows).candles)


# ===================== 1. the model: shape and immutability ==================


def test_snapshot_holds_exactly_two_fields() -> None:
    assert [f.name for f in fields(StructuralTrendSnapshot)] == [
        "trend",
        "state_snapshot",
    ]


def test_snapshot_is_frozen() -> None:
    one = StructuralTrendSnapshot(trend=TT.NEUTRAL, state_snapshot=snapshot(S.EXPANDED, 1))
    with pytest.raises(FrozenInstanceError):
        one.trend = TT.SUSTAINED_HIGHER  # type: ignore[misc]


def test_snapshot_is_slotted_and_grows_no_attribute() -> None:
    one = StructuralTrendSnapshot(trend=TT.NEUTRAL, state_snapshot=snapshot(S.EXPANDED, 1))
    assert not hasattr(one, "__dict__")
    # A frozen+slots dataclass raises TypeError from the generated __setattr__
    # for a name that is not a field, rather than AttributeError.
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        one.length = 3  # type: ignore[attr-defined]


def test_snapshot_is_hashable_and_compares_by_value() -> None:
    source = snapshot(S.EXPANDED, 1)
    a = StructuralTrendSnapshot(trend=TT.NEUTRAL, state_snapshot=source)
    b = StructuralTrendSnapshot(trend=TT.NEUTRAL, state_snapshot=source)
    assert a == b and hash(a) == hash(b)
    assert len({a, b}) == 1


def test_snapshot_index_and_timestamp_are_projections_not_fields() -> None:
    stored = {f.name for f in fields(StructuralTrendSnapshot)}
    assert "index" not in stored and "timestamp" not in stored
    source = snapshot(S.UNCHANGED, 7)
    one = StructuralTrendSnapshot(trend=TT.NEUTRAL, state_snapshot=source)
    assert one.index == source.index == 7
    assert one.timestamp == source.timestamp


def test_snapshot_rejects_a_non_trend_value() -> None:
    with pytest.raises(TypeError, match="trend must be a StructuralTrendType"):
        StructuralTrendSnapshot(
            trend="sustained_higher",  # type: ignore[arg-type]
            state_snapshot=snapshot(S.EXPANDED, 1),
        )


def test_snapshot_rejects_a_non_state_snapshot() -> None:
    with pytest.raises(
        TypeError, match="state_snapshot must be a StructuralSequenceStateSnapshot"
    ):
        StructuralTrendSnapshot(
            trend=TT.NEUTRAL,
            state_snapshot=snapshot(S.EXPANDED, 1).state,  # type: ignore[arg-type]
        )


def test_the_trend_enum_has_exactly_four_members() -> None:
    assert [m.name for m in StructuralTrendType] == [
        "SUSTAINED_HIGHER",
        "SUSTAINED_LOWER",
        "NEUTRAL",
        "INDETERMINATE",
    ]


@pytest.mark.parametrize(
    "absent",
    ["UPTREND", "DOWNTREND", "BULLISH", "BEARISH", "LONG", "SHORT", "BUY", "SELL",
     "STRONG", "WEAK", "MIXED", "OTHER", "UNKNOWN", "AMBIGUOUS", "BALANCED",
     "ADVANCING_UP", "ADVANCING_DOWN", "RANGING", "CONTINUATION", "REVERSAL"],
)
def test_the_trend_enum_has_no_interpretive_member(absent: str) -> None:
    assert absent not in StructuralTrendType.__members__


def test_the_minimum_is_two_and_is_an_int() -> None:
    assert MINIMUM_DIRECTIONAL_SHIFTS == 2
    assert isinstance(MINIMUM_DIRECTIONAL_SHIFTS, int)
    assert not isinstance(MINIMUM_DIRECTIONAL_SHIFTS, bool)


def test_the_derivation_takes_no_threshold_parameter() -> None:
    """The policy is one stated constant, not a per-call dial."""
    import inspect

    for fn in (derive_structural_trend, derive_structural_trend_history):
        assert list(inspect.signature(fn).parameters) == ["snapshots"]


# ===================== 2. empty and insufficient history =====================


def test_empty_history_yields_an_empty_tuple() -> None:
    result = derive_structural_trend_history([])
    assert result == ()
    assert isinstance(result, tuple)


def test_empty_history_yields_indeterminate_not_neutral() -> None:
    """No evidence is not conflicting evidence."""
    assert derive_structural_trend([]) is TT.INDETERMINATE


def test_a_single_shift_is_not_a_trend() -> None:
    assert derive_structural_trend(history("H")) is TT.INDETERMINATE
    assert derive_structural_trend(history("L")) is TT.INDETERMINATE


@pytest.mark.parametrize("state", NON_DIRECTIONAL)
def test_a_history_of_one_non_directional_state_is_indeterminate(
    state: StructuralSequenceStateType,
) -> None:
    assert derive_structural_trend((snapshot(state, 1),)) is TT.INDETERMINATE


def test_a_long_non_directional_history_is_still_indeterminate() -> None:
    """There is no minimum on snapshot *count* — only on directional shifts."""
    assert derive_structural_trend(history("ECUECUECUECU" * 5)) is TT.INDETERMINATE


def test_an_insufficient_structure_only_history_is_indeterminate() -> None:
    assert derive_structural_trend(history("IIIIII")) is TT.INDETERMINATE
    assert trends("IIII") == [TT.INDETERMINATE] * 4


# ===================== 3. the minimum valid history ==========================


def test_two_same_direction_shifts_are_the_minimum_valid_trend() -> None:
    assert derive_structural_trend(history("HH")) is TT.SUSTAINED_HIGHER
    assert derive_structural_trend(history("LL")) is TT.SUSTAINED_LOWER


def test_one_fewer_than_the_minimum_is_not_a_trend() -> None:
    assert trends("H") == [TT.INDETERMINATE]
    assert trends("HH") == [TT.INDETERMINATE, TT.SUSTAINED_HIGHER]


def test_the_minimum_is_honoured_rather_than_hard_coded() -> None:
    """A run one short of the constant is never sustained; one at it always is."""
    short = "H" * (MINIMUM_DIRECTIONAL_SHIFTS - 1)
    exact = "H" * MINIMUM_DIRECTIONAL_SHIFTS
    assert derive_structural_trend(history(short)) is not TT.SUSTAINED_HIGHER
    assert derive_structural_trend(history(exact)) is TT.SUSTAINED_HIGHER


# ===================== 4. upward and downward histories =====================


@pytest.mark.parametrize("count", range(1, 9))
def test_monotonic_upward_history(count: int) -> None:
    result = trends("H" * count)
    expected = [TT.INDETERMINATE] * min(count, MINIMUM_DIRECTIONAL_SHIFTS - 1)
    expected += [TT.SUSTAINED_HIGHER] * (count - len(expected))
    assert result == expected


@pytest.mark.parametrize("count", range(1, 9))
def test_monotonic_downward_history(count: int) -> None:
    result = trends("L" * count)
    expected = [TT.INDETERMINATE] * min(count, MINIMUM_DIRECTIONAL_SHIFTS - 1)
    expected += [TT.SUSTAINED_LOWER] * (count - len(expected))
    assert result == expected


def test_upward_and_downward_are_exactly_symmetric() -> None:
    swap = {TT.SUSTAINED_HIGHER: TT.SUSTAINED_LOWER,
            TT.SUSTAINED_LOWER: TT.SUSTAINED_HIGHER}
    for spec in ("HHLHH", "HLLH", "HHEUCLL", "IIHHL", "HLHLHH"):
        mirrored = spec.translate(str.maketrans("HL", "LH"))
        assert trends(mirrored) == [swap.get(t, t) for t in trends(spec)]


# ===================== 5. mixed and alternating histories ===================


def test_a_mixed_history_matches_its_directional_subsequence() -> None:
    """Non-directional states are transparent, so removing them changes nothing."""
    for spec in ("IHEHCLUL", "EEHUUHCC", "IIIHECHUL", "UUU", "ECUHHECULL"):
        directional = "".join(c for c in spec if c in "HL")
        assert derive_structural_trend(history(spec)) == derive_structural_trend(
            history(directional)
        )


def test_an_alternating_history_never_reports_a_direction() -> None:
    for count in range(1, 13):
        spec = ("HL" * count)[:count]
        result = derive_structural_trend(history(spec))
        assert result in (TT.INDETERMINATE, TT.NEUTRAL), (spec, result)


def test_an_alternating_history_is_indeterminate_then_neutral_forever() -> None:
    assert trends("HLHLHLHL") == [TT.INDETERMINATE] + [TT.NEUTRAL] * 7


def test_an_alternating_history_starting_lower_behaves_identically() -> None:
    assert trends("LHLHLHLH") == [TT.INDETERMINATE] + [TT.NEUTRAL] * 7


def test_a_mixed_history_with_interleaved_neutrals_still_alternates_to_neutral() -> None:
    assert derive_structural_trend(history("HEELCCHUUL")) is TT.NEUTRAL


# ===================== 6. continuation through neutral states ===============


@pytest.mark.parametrize("state", NON_DIRECTIONAL)
def test_a_sustained_trend_survives_one_non_directional_state(
    state: StructuralSequenceStateType,
) -> None:
    run = (*history("HH"), snapshot(state, 3))
    assert derive_structural_trend(run) is TT.SUSTAINED_HIGHER


@pytest.mark.parametrize("letter", "ECU")
def test_a_sustained_trend_survives_a_long_run_of_one_neutral_state(
    letter: str,
) -> None:
    assert derive_structural_trend(history("HH" + letter * 50)) is TT.SUSTAINED_HIGHER


def test_a_sustained_trend_survives_every_neutral_state_combined() -> None:
    assert derive_structural_trend(history("HH" + "ECUECU" * 8)) is TT.SUSTAINED_HIGHER
    assert derive_structural_trend(history("LL" + "UCEUCE" * 8)) is TT.SUSTAINED_LOWER


def test_a_neutral_state_does_not_advance_a_partial_run() -> None:
    """Transparent means transparent in both directions: it cannot help either."""
    assert derive_structural_trend(history("HEEEEE")) is TT.INDETERMINATE
    assert derive_structural_trend(history("HEEEH")) is TT.SUSTAINED_HIGHER


def test_persistence_across_five_hundred_neutral_snapshots() -> None:
    """The documented limitation, pinned so it cannot change unnoticed."""
    run = history("HH" + "C" * 500)
    assert derive_structural_trend(run) is TT.SUSTAINED_HIGHER
    result = derive_structural_trend_history(run)
    assert len(result) == 502
    assert {s.trend for s in result[1:]} == {TT.SUSTAINED_HIGHER}


# ===================== 7. invalidation ======================================


def test_one_opposing_shift_invalidates_a_sustained_trend() -> None:
    assert trends("HHL") == [TT.INDETERMINATE, TT.SUSTAINED_HIGHER, TT.NEUTRAL]


def test_two_opposing_shifts_establish_the_opposite_trend() -> None:
    assert trends("HHLL") == [
        TT.INDETERMINATE,
        TT.SUSTAINED_HIGHER,
        TT.NEUTRAL,
        TT.SUSTAINED_LOWER,
    ]


def test_an_invalidated_trend_does_not_return_without_new_evidence() -> None:
    assert derive_structural_trend(history("HHL" + "ECU" * 10)) is TT.NEUTRAL


def test_an_invalidated_trend_returns_only_after_a_fresh_full_run() -> None:
    assert derive_structural_trend(history("HHLH")) is TT.NEUTRAL
    assert derive_structural_trend(history("HHLHH")) is TT.SUSTAINED_HIGHER


def test_invalidation_is_not_delayed_by_intervening_neutral_states() -> None:
    assert derive_structural_trend(history("HHEEECCCL")) is TT.NEUTRAL


def test_a_long_sustained_run_is_invalidated_by_exactly_one_opposing_shift() -> None:
    assert derive_structural_trend(history("H" * 40)) is TT.SUSTAINED_HIGHER
    assert derive_structural_trend(history("H" * 40 + "L")) is TT.NEUTRAL


def test_contested_never_resets_so_indeterminate_never_returns() -> None:
    result = trends("HL" + "ECU" * 6)
    assert result[0] is TT.INDETERMINATE
    assert TT.INDETERMINATE not in result[1:]
    assert set(result[1:]) == {TT.NEUTRAL}


def test_neutral_and_indeterminate_are_distinguished_on_minimal_inputs() -> None:
    """The one-snapshot difference that separates absent from conflicting evidence."""
    assert derive_structural_trend(history("H")) is TT.INDETERMINATE
    assert derive_structural_trend(history("HL")) is TT.NEUTRAL


# ===================== 8. totality and carry-forward ========================


@pytest.mark.parametrize(
    "spec", ["", "H", "HH", "IHEHCLUL", "HLHLHL", "ECU", "H" * 30, "HHLLHHLL"]
)
def test_one_trend_snapshot_per_input_snapshot(spec: str) -> None:
    run = history(spec)
    result = derive_structural_trend_history(run)
    assert len(result) == len(run)
    assert [s.index for s in result] == [s.index for s in run]
    assert [s.timestamp for s in result] == [s.timestamp for s in run]


def test_the_source_snapshot_is_carried_by_identity_never_copied() -> None:
    run = history("IHEHCLUL")
    result = derive_structural_trend_history(run)
    assert all(a.state_snapshot is b for a, b in zip(result, run))


def test_a_single_side_snapshot_history_from_carry_forward_is_accepted() -> None:
    """A real history mostly holds one trigger per snapshot, the other carried."""
    high = swing(StructuralSwingLabel.HIGHER_HIGH, 1)
    low = swing(StructuralSwingLabel.HIGHER_LOW, 2)
    later_high = swing(StructuralSwingLabel.HIGHER_HIGH, 3)
    first = StructuralSequenceStateSnapshot(
        state=StructuralSequenceState(
            latest_high=high, latest_low=None, state=S.INSUFFICIENT_STRUCTURE
        ),
        triggers=(high,),
    )
    second = StructuralSequenceStateSnapshot(
        state=StructuralSequenceState(
            latest_high=high, latest_low=low, state=S.SHIFTED_HIGHER
        ),
        triggers=(low,),
    )
    third = StructuralSequenceStateSnapshot(
        state=StructuralSequenceState(
            latest_high=later_high, latest_low=low, state=S.SHIFTED_HIGHER
        ),
        triggers=(later_high,),
    )
    assert [s.trend for s in derive_structural_trend_history((first, second, third))] == [
        TT.INDETERMINATE,
        TT.INDETERMINATE,
        TT.SUSTAINED_HIGHER,
    ]


# ===================== 9. rejections: types and ordering ====================


@pytest.mark.parametrize("fn", [derive_structural_trend, derive_structural_trend_history])
@pytest.mark.parametrize("bad", [None, 7, 3.5, object()])
def test_a_non_iterable_is_rejected(fn, bad) -> None:
    with pytest.raises(TypeError, match="snapshots must be an iterable"):
        fn(bad)


@pytest.mark.parametrize("fn", [derive_structural_trend, derive_structural_trend_history])
@pytest.mark.parametrize("bad", ["HH", b"HH"])
def test_a_string_is_rejected_rather_than_iterated(fn, bad) -> None:
    with pytest.raises(TypeError, match="snapshots must be an iterable"):
        fn(bad)


@pytest.mark.parametrize("fn", [derive_structural_trend, derive_structural_trend_history])
def test_a_non_snapshot_element_is_rejected_with_its_position(fn) -> None:
    run = (*history("HH"), snapshot(S.EXPANDED, 3).state)
    with pytest.raises(
        TypeError,
        match=r"snapshots\[2\] must be a StructuralSequenceStateSnapshot",
    ):
        fn(run)


@pytest.mark.parametrize("fn", [derive_structural_trend, derive_structural_trend_history])
def test_a_trend_snapshot_is_not_accepted_as_input(fn) -> None:
    """The output type is not the input type; feeding one back is a caller bug."""
    with pytest.raises(TypeError, match="must be a StructuralSequenceStateSnapshot"):
        fn(derive_structural_trend_history(history("HH")))


@pytest.mark.parametrize("fn", [derive_structural_trend, derive_structural_trend_history])
def test_a_decreasing_index_is_rejected(fn) -> None:
    run = (snapshot(S.SHIFTED_HIGHER, 5), snapshot(S.SHIFTED_HIGHER, 2))
    with pytest.raises(
        ValueError,
        match=r"snapshots must be ordered by strictly increasing index; "
        r"snapshots\[1\] has index 2 after 5",
    ):
        fn(run)


@pytest.mark.parametrize("fn", [derive_structural_trend, derive_structural_trend_history])
def test_a_repeated_index_is_rejected(fn) -> None:
    """A valid history has one snapshot per candle; two at one index cannot occur."""
    run = (snapshot(S.SHIFTED_HIGHER, 4), snapshot(S.SHIFTED_LOWER, 4))
    with pytest.raises(
        ValueError, match=r"snapshots\[1\] has index 4 after 4"
    ):
        fn(run)


@pytest.mark.parametrize("fn", [derive_structural_trend, derive_structural_trend_history])
def test_a_decreasing_timestamp_is_rejected(fn) -> None:
    high = swing(StructuralSwingLabel.HIGHER_HIGH, 9)
    displaced = StructuralSequenceStateSnapshot(
        state=StructuralSequenceState(
            latest_high=high, latest_low=None, state=S.INSUFFICIENT_STRUCTURE
        ),
        triggers=(high,),
    )
    # index rises 3 -> 9 while the timestamp is engineered to fall
    earlier = swing(StructuralSwingLabel.HIGHER_HIGH, 3)
    ahead = SwingPoint(
        index=3, timestamp=_BASE + timedelta(hours=4 * 40), price=110.0,
        type=SwingType.HIGH,
    )
    moved = label_swing(
        compare_swings(
            SwingPoint(index=0, timestamp=_BASE, price=100.0, type=SwingType.HIGH),
            ahead,
        )
    )
    first = StructuralSequenceStateSnapshot(
        state=StructuralSequenceState(
            latest_high=moved, latest_low=None, state=S.INSUFFICIENT_STRUCTURE
        ),
        triggers=(moved,),
    )
    assert earlier is not moved
    with pytest.raises(
        ValueError,
        match="snapshots must be ordered by strictly increasing timestamp",
    ):
        fn((first, displaced))


@pytest.mark.parametrize("fn", [derive_structural_trend, derive_structural_trend_history])
def test_ordering_is_validated_before_anything_is_built(fn) -> None:
    """An unordered run yields no partial result, only the error."""
    run = (*history("HHHH"), snapshot(S.SHIFTED_HIGHER, 2))
    with pytest.raises(ValueError):
        fn(run)


def test_an_unordered_run_is_rejected_rather_than_sorted() -> None:
    run = tuple(reversed(history("HHHH")))
    with pytest.raises(ValueError):
        derive_structural_trend_history(run)


# ===================== 10. purity, replay, immutability =====================


@pytest.mark.parametrize("spec", ["", "H", "HHLL", "IHEHCLUL", "HLHLHL", "H" * 25])
def test_repeated_calls_are_equal(spec: str) -> None:
    run = history(spec)
    assert derive_structural_trend_history(run) == derive_structural_trend_history(run)
    assert derive_structural_trend(run) == derive_structural_trend(run)


def test_results_compare_equal_across_calls_but_are_not_identical() -> None:
    run = history("HHLL")
    a, b = derive_structural_trend_history(run), derive_structural_trend_history(run)
    assert a == b
    assert a is not b
    assert all(x is not y for x, y in zip(a, b))


def test_the_input_list_is_neither_mutated_nor_reordered() -> None:
    run = list(history("IHEHCLUL"))
    original = list(run)
    derive_structural_trend_history(run)
    derive_structural_trend(run)
    assert run == original
    assert all(a is b for a, b in zip(run, original))


def test_a_generator_input_is_accepted_and_fully_consumed() -> None:
    run = history("HHLL")
    assert derive_structural_trend(s for s in run) is TT.SUSTAINED_LOWER
    assert len(derive_structural_trend_history(s for s in run)) == 4


def test_the_returned_history_is_an_immutable_tuple() -> None:
    result = derive_structural_trend_history(history("HH"))
    assert isinstance(result, tuple)
    with pytest.raises(TypeError):
        result[0] = result[1]  # type: ignore[index]


# ===================== 11. the two forms agree ==============================


@pytest.mark.parametrize(
    "spec",
    ["H", "L", "HH", "LL", "HL", "LH", "HHL", "HHLL", "IHEHCLUL", "HLHLHL",
     "ECU", "IIIHH", "HH" + "C" * 20, "H" * 12, "HHLHH", "UUUHHUUU"],
)
def test_the_scalar_form_equals_the_last_of_the_history_form(spec: str) -> None:
    run = history(spec)
    assert derive_structural_trend(run) is (
        derive_structural_trend_history(run)[-1].trend
    )


def test_the_two_forms_differ_in_shape_only_on_empty_input() -> None:
    assert derive_structural_trend_history([]) == ()
    assert derive_structural_trend([]) is TT.INDETERMINATE


# ===================== 12. generated matrices vs the oracle =================


@pytest.mark.parametrize("length", range(0, 5))
def test_exhaustive_state_sequences_match_the_oracle(length: int) -> None:
    """Every sequence of the given length over all six state members."""
    checked = 0
    for combination in itertools.product("HLECUI", repeat=length):
        spec = "".join(combination)
        # 'I' can only precede a complete state, so skip specs that revive it
        if "I" in spec and any(c != "I" for c in spec[: spec.rindex("I")]):
            continue
        expected = oracle_history(states_of(spec))
        assert trends(spec) == expected, spec
        assert derive_structural_trend(history(spec)) is (
            expected[-1] if expected else TT.INDETERMINATE
        )
        checked += 1
    assert checked > 0


@pytest.mark.parametrize("seed", range(40))
def test_random_state_sequences_match_the_oracle(seed: int) -> None:
    rng = random.Random(seed)
    spec = "".join(rng.choice("HHLLECU") for _ in range(rng.randint(0, 60)))
    assert trends(spec) == oracle_history(states_of(spec))


@pytest.mark.parametrize("seed", range(30))
def test_candle_derived_histories_match_the_oracle(seed: int) -> None:
    run = random_state_history(seed, outside=bool(seed % 2))
    expected = oracle_history([s.state.state for s in run])
    assert [s.trend for s in derive_structural_trend_history(run)] == expected
    assert derive_structural_trend(run) is (
        expected[-1] if expected else TT.INDETERMINATE
    )


@pytest.mark.parametrize("seed", range(30))
def test_candle_derived_histories_are_total_and_identity_preserving(
    seed: int,
) -> None:
    run = random_state_history(seed, outside=bool(seed % 2))
    result = derive_structural_trend_history(run)
    assert len(result) == len(run)
    assert all(a.state_snapshot is b for a, b in zip(result, run))


def test_a_direction_is_only_ever_reported_on_a_real_run() -> None:
    """No generated case reports a direction without the minimum consecutive shifts."""
    for seed in range(60):
        rng = random.Random(1000 + seed)
        spec = "".join(rng.choice("HHLLECU") for _ in range(rng.randint(0, 40)))
        result = trends(spec)
        shifts = [c for c in spec if c in "HL"]
        for position, value in enumerate(result):
            if value in (TT.SUSTAINED_HIGHER, TT.SUSTAINED_LOWER):
                seen = [c for c in spec[: position + 1] if c in "HL"]
                letter = "H" if value is TT.SUSTAINED_HIGHER else "L"
                trailing = 0
                for c in reversed(seen):
                    if c != letter:
                        break
                    trailing += 1
                assert trailing >= MINIMUM_DIRECTIONAL_SHIFTS, (spec, position)
        assert shifts or set(result) <= {TT.INDETERMINATE}


# ===================== 13. prefix stability =================================


@pytest.mark.parametrize("spec", ["", "H", "HHLL", "IHEHCLUL", "HLHLHLHL",
                                  "HH" + "ECU" * 6, "H" * 15, "HHLHHLLH"])
def test_prefix_stability_over_the_snapshot_history(spec: str) -> None:
    run = history(spec)
    full = derive_structural_trend_history(run)
    for k in range(len(run) + 1):
        assert derive_structural_trend_history(run[:k]) == full[:k], k


@pytest.mark.parametrize("spec", ["H", "HHLL", "IHEHCLUL", "HLHLHLHL", "H" * 9])
def test_the_scalar_form_agrees_with_every_prefix(spec: str) -> None:
    run = history(spec)
    full = derive_structural_trend_history(run)
    for k in range(1, len(run) + 1):
        assert derive_structural_trend(run[:k]) is full[k - 1].trend


@pytest.mark.parametrize("seed", range(20))
def test_prefix_stability_under_candle_series_extension(seed: int) -> None:
    """Mode 1 of the guarantee: grow the series one closed bar at a time."""
    rng = random.Random(2000 + seed)
    rows = random_rows(rng, 40, (seed % 3 - 1) * 1.2, 3 if seed % 2 else 0)
    candles = series(rows).candles
    full = derive_structural_trend_history(state_history(candles))
    for count in range(1, len(candles) + 1):
        partial = derive_structural_trend_history(state_history(candles[:count]))
        assert partial == full[: len(partial)], count


@pytest.mark.parametrize("seed", range(20))
def test_prefix_stability_under_complete_structural_group_extension(
    seed: int,
) -> None:
    """Mode 2 of the guarantee: take whole same-candle groups, never a part."""
    rng = random.Random(3000 + seed)
    rows = random_rows(rng, 40, (seed % 3 - 1) * 1.2, 3 if seed % 2 else 0)
    run = structural_run(series(rows).candles)
    indices = sorted({s.comparison.current.index for s in run})
    full = derive_structural_trend_history(
        derive_structural_sequence_state_history(run)
    )
    for k in range(len(indices) + 1):
        keep = set(indices[:k])
        cut = tuple(s for s in run if s.comparison.current.index in keep)
        partial = derive_structural_trend_history(
            derive_structural_sequence_state_history(cut)
        )
        assert partial == full[: len(partial)], k


def test_prefix_stability_does_not_claim_a_stable_value() -> None:
    """An emitted reading never changes; the trend itself may still be invalidated."""
    run = history("HHL")
    assert derive_structural_trend_history(run[:2])[-1].trend is TT.SUSTAINED_HIGHER
    assert derive_structural_trend_history(run)[-1].trend is TT.NEUTRAL
    assert derive_structural_trend_history(run)[:2] == derive_structural_trend_history(
        run[:2]
    )


# ===================== 14. outside bars and the excluded cut ================


def test_an_outside_bar_yields_one_reading_not_two() -> None:
    """The state history already resolved the group atomically; trend adds no split."""
    run = history("HHLL")
    assert all(len(s.triggers) == 2 for s in run)
    assert len(derive_structural_trend_history(run)) == 4


def test_either_outside_bar_trigger_order_gives_the_same_trend_history() -> None:
    forward = history("HHLL")
    swapped = tuple(
        StructuralSequenceStateSnapshot(
            state=s.state, triggers=tuple(reversed(s.triggers))
        )
        for s in forward
    )
    assert [t.triggers for t in swapped] != [t.triggers for t in forward]
    assert [s.trend for s in derive_structural_trend_history(swapped)] == [
        s.trend for s in derive_structural_trend_history(forward)
    ]


@pytest.mark.parametrize("seed", range(12))
def test_outside_bar_series_preserve_one_reading_per_state_snapshot(
    seed: int,
) -> None:
    run = random_state_history(4000 + seed, outside=True)
    assert any(len(s.triggers) == 2 for s in run), "fixture produced no outside bar"
    result = derive_structural_trend_history(run)
    assert len(result) == len(run)
    assert [s.index for s in result] == [s.index for s in run]


def test_the_arbitrary_inside_group_cut_is_outside_the_guarantee() -> None:
    """ADR-0016 §7's limitation, inherited. Pinned so it cannot be "fixed" falsely.

    Splitting an outside bar's HIGH from its LOW yields a different — and correct —
    state for that candle, so the reading at and after it differs. This is measured,
    not assumed.

    **Two figures, deliberately kept apart** (ADR-0017 §9.1). Compared as whole
    `StructuralTrendSnapshot` tuples — the guarantee's own equality — *every* split
    diverges, because the embedded state snapshot for that candle is genuinely
    different. Compared on the trend *value* alone, only a minority diverge. The
    review found the first draft of the design quoting the second figure as though
    it measured the first, so both are pinned here and neither can be silently
    substituted for the other.
    """
    split = divergent_snapshots = divergent_values = 0
    for seed in range(40):
        rng = random.Random(5000 + seed)
        run = structural_run(series(random_rows(rng, 40, (seed % 3 - 1) * 1.2, 3)).candles)
        grouped: dict[int, list[StructuralSwing]] = {}
        for structure in run:
            grouped.setdefault(structure.comparison.current.index, []).append(structure)
        full = derive_structural_trend_history(
            derive_structural_sequence_state_history(run)
        )
        full_values = [s.trend for s in full]
        for index, group in sorted(grouped.items()):
            if len(group) < 2:
                continue
            split += 1
            cut = tuple(
                s for s in run if s.comparison.current.index < index
            ) + (group[0],)
            partial = derive_structural_trend_history(
                derive_structural_sequence_state_history(cut)
            )
            if partial != full[: len(partial)]:
                divergent_snapshots += 1
            if [s.trend for s in partial] != full_values[: len(partial)]:
                divergent_values += 1

    assert split > 0, "the fixture stopped producing outside bars"
    # Under the guarantee's own equality the cut diverges every single time.
    assert divergent_snapshots == split, (
        "an inside-group cut no longer changes every reading; either the state "
        "history stopped resolving groups atomically or a stronger guarantee was "
        "introduced without updating ADR-0016 §7 and ADR-0017 §9"
    )
    # The trend *value* changes less often — a different and weaker statement.
    assert 0 < divergent_values < split, (
        "the trend-value divergence rate collapsed to 0 or 100%, so the two "
        "figures ADR-0017 §9.1 distinguishes are no longer distinguishable"
    )


# ===================== 15. export and visibility contracts =================


def test_the_public_api_is_exactly_five_names() -> None:
    assert set(st.__all__) == {
        "MINIMUM_DIRECTIONAL_SHIFTS",
        "StructuralTrendType",
        "StructuralTrendSnapshot",
        "derive_structural_trend",
        "derive_structural_trend_history",
    }
    assert len(st.__all__) == 5


def test_every_exported_name_resolves() -> None:
    for name in st.__all__:
        assert hasattr(st, name), name


def test_no_submodule_collides_with_a_public_name() -> None:
    import pkgutil

    submodules = {m.name for m in pkgutil.iter_modules(st.__path__)}
    assert submodules == {"models", "trend"}
    assert submodules & set(st.__all__) == set()


def test_no_private_helper_is_exported() -> None:
    for private in (
        "_advance",
        "_classify",
        "_Run",
        "_INITIAL_RUN",
        "_validated",
        "_TREND_BY_DIRECTIONAL_STATE",
        "_is_directional_state",
        "_trend_for_directional_state",
        "_validate_snapshot_history_order",
    ):
        assert private not in st.__all__, private
        assert not hasattr(st, private), private


def test_no_mutable_public_object_is_exported() -> None:
    for name in st.__all__:
        assert not isinstance(getattr(st, name), (list, dict, set)), name


def test_the_directional_state_mapping_is_immutable_and_has_two_entries() -> None:
    from fmis.structural_trend.models import _TREND_BY_DIRECTIONAL_STATE

    assert len(_TREND_BY_DIRECTIONAL_STATE) == 2
    assert set(_TREND_BY_DIRECTIONAL_STATE) == set(DIRECTIONAL)
    with pytest.raises(TypeError):
        _TREND_BY_DIRECTIONAL_STATE[S.EXPANDED] = TT.SUSTAINED_HIGHER  # type: ignore[index]


def test_no_non_directional_state_is_treated_as_directional() -> None:
    from fmis.structural_trend.models import _is_directional_state

    for state in NON_DIRECTIONAL:
        assert not _is_directional_state(state)
    for state in DIRECTIONAL:
        assert _is_directional_state(state)


def test_the_directional_mapping_covers_exactly_the_shifted_states() -> None:
    """A new state member added upstream must not silently become directional."""
    from fmis.structural_trend.models import _is_directional_state

    directional = {s for s in StructuralSequenceStateType if _is_directional_state(s)}
    assert directional == {S.SHIFTED_HIGHER, S.SHIFTED_LOWER}
    assert len(list(StructuralSequenceStateType)) == 6


# ===================== 16. architecture guards ==============================


def _code_tokens(path: Path) -> set[str]:
    """Identifiers, attributes and non-docstring literals — docstrings excluded."""
    tree = ast.parse(path.read_text())
    docstrings = {
        d
        for node in ast.walk(tree)
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
        "bos", "choch", "bullish", "bearish", "support", "resistance",
        "liquidity", "sweep", "strength", "confidence", "score", "rank",
        "buy", "sell", "signal", "evidence", "probability", "predict",
        "forecast", "uptrend", "downtrend", "regime", "bias", "momentum",
        "breakout", "reversal", "continuation", "protected", "level",
        "candle", "consolidation", "squeeze", "magnitude", "duration",
        "decay", "timeout", "weight", "vote", "majority",
    )
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        tokens = _code_tokens(py)
        for word in forbidden:
            assert word not in tokens, f"{py.name}: {word}"


def test_the_package_reads_no_candle_field_and_no_price() -> None:
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.Attribute):
                assert node.attr not in (
                    "high", "low", "close", "open", "volume", "candles",
                    "price", "sort", "comparison", "label", "triggers",
                    "latest_high", "latest_low",
                ), f"{py.name}: {node.attr}"


def test_the_package_re_derives_nothing_from_a_lower_layer() -> None:
    called: set[str] = set()
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called.add(node.func.id)
    for banned in (
        "detect_swings", "compare_swings", "compare_swing_sequence",
        "label_swing", "label_swing_sequence",
        "derive_structural_sequence_state",
        "derive_structural_sequence_state_history",
        "_sequence_state_for", "_validate_key_order",
        "_validate_current_point_order", "_label_for", "_relation_for",
        "sorted", "reversed",
    ):
        assert banned not in called, banned


def test_the_shared_step_and_classification_are_used_by_both_public_functions() -> None:
    """One rule, not one per API shape — the anti-drift guarantee."""
    tree = ast.parse((PACKAGE_DIR / "trend.py").read_text())
    for name in ("derive_structural_trend", "derive_structural_trend_history"):
        node = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == name
        )
        called = {
            c.func.id
            for c in ast.walk(node)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        }
        assert "_advance" in called, name
        assert "_classify" in called, name
        assert "_validated" in called, name


def test_the_directionality_authority_lives_only_in_models() -> None:
    """`trend.py` names no state member; it asks `models` instead."""
    source = (PACKAGE_DIR / "trend.py").read_text()
    for member in StructuralSequenceStateType:
        assert f"StructuralSequenceStateType.{member.name}" not in source


def test_the_trend_vocabulary_is_named_only_where_it_is_decided() -> None:
    """`SUSTAINED_*` is produced by the mapping in models, never spelled in trend.py."""
    source = (PACKAGE_DIR / "trend.py").read_text()
    assert "StructuralTrendType.SUSTAINED_HIGHER" not in source
    assert "StructuralTrendType.SUSTAINED_LOWER" not in source
    # NEUTRAL and INDETERMINATE are the classification's own output, so they belong
    assert "StructuralTrendType.NEUTRAL" in source
    assert "StructuralTrendType.INDETERMINATE" in source


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


def test_imports_only_market_structure_and_own_modules() -> None:
    assert _internal_imports() <= {
        "fmis.market_structure",
        "fmis.structural_trend.models",
        "fmis.structural_trend.trend",
    }


@pytest.mark.parametrize(
    "forbidden",
    ["fmis.data", "fmis.decision_support", "fmis.evidence", "fmis.providers",
     "fmis.pipeline", "fmis.ingest", "fmis.trading_context",
     "fmis.relative_value", "fmis.features", "fmis.alignment"],
)
def test_does_not_depend_on_other_layers(forbidden: str) -> None:
    assert not any(i.startswith(forbidden) for i in _internal_imports()), forbidden


def test_does_not_reach_into_market_structure_submodules() -> None:
    """Only the package's public surface, never its private internals."""
    for internal in _internal_imports():
        assert not internal.startswith("fmis.market_structure."), internal


def test_uses_only_stdlib() -> None:
    roots: set[str] = set()
    for py in PACKAGE_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
    assert roots <= set(sys.stdlib_module_names) | {"fmis"}


def test_nothing_below_imports_this_package() -> None:
    """Only a layer strictly *above* trend may depend on it.

    `fmis.series_context` is that layer and the only permitted consumer: it sits
    above trend, wraps its output with a series identity, and re-derives none of
    its logic (ADR-0018). Every other package must stay independent of trend, and
    in particular `fmis.market_structure` must never import upward.

    The exemption is named rather than pattern-matched, so a second consumer
    appearing anywhere fails this test and has to justify itself in an ADR.
    """
    root = Path(st.__file__).parent.parent
    permitted = {root / "series_context"}
    for py in root.rglob("*.py"):
        if py.parent == PACKAGE_DIR or py.parent in permitted:
            continue
        assert "fmis.structural_trend" not in py.read_text(), py


def test_the_only_permitted_consumer_does_not_reach_into_private_internals() -> None:
    """`fmis.series_context` may use the public surface and nothing else."""
    root = Path(st.__file__).parent.parent
    for py in (root / "series_context").glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("fmis.structural_trend."), py


# ===================== 17. nothing upstream changed ========================


def test_market_structure_evidence_family_remains_empty() -> None:
    from fmis.evidence import EvidenceFamily, descriptors, descriptors_for

    assert descriptors_for(EvidenceFamily.MARKET_STRUCTURE) == ()
    assert len(descriptors()) == 6


def test_the_evidence_family_enum_is_unchanged() -> None:
    from fmis.evidence import EvidenceFamily

    assert [m.name for m in EvidenceFamily] == [
        "TREND", "MOMENTUM", "VOLUME", "VOLATILITY", "MARKET_STRUCTURE",
        "RELATIVE_STRENGTH", "LIQUIDITY", "MACRO", "NEWS", "SENTIMENT",
    ]


def test_no_evidence_descriptor_was_added_for_the_trend() -> None:
    """Nothing here classifies in ADR-0011 §1's sense."""
    from fmis.evidence import descriptors

    for descriptor in descriptors():
        assert "structural" not in descriptor.name.lower()
        assert descriptor.name.lower() != "trend"


def test_the_market_structure_public_api_is_unchanged() -> None:
    import fmis.market_structure as ms

    assert len(ms.__all__) == 19
    assert "derive_structural_trend" not in ms.__all__
    assert "StructuralTrendType" not in ms.__all__


def test_market_structure_still_contains_no_trend_vocabulary() -> None:
    """The guard that forced this package to be a sibling still holds."""
    import fmis.market_structure as ms

    for py in sorted(Path(ms.__file__).parent.glob("*.py")):
        assert "trend" not in _code_tokens(py), py.name
