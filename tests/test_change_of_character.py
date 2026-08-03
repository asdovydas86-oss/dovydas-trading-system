"""Tests for `fmis.change_of_character` — Change of Character Foundation v1.

Organised in the order ADR-0021 states the contract: the model and its
self-validation, the predecessor rule, the transition table, lifecycle,
duplicates and validation, empty input, ordering, input-order invariance, prefix
stability, replay determinism, the safe pipeline, properties, adversarial
fixtures, and architecture guards.

Exception messages are treated as a shipped contract and asserted with ``==``,
not `pytest.raises(match=...)`, following `test_market_structure_ordering.py` and
`test_structure_break.py`.

Note the deliberate asymmetry: this module imports `Candle`, `PriceLevel` and
`LevelCrossingEvent` because building a `StructureBreak` requires them, while the
package under test imports `fmis.data` not at all and takes exactly one name —
`LevelSide` — from `fmis.level_crossing`. That is the point, and guards below pin
both.
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

import fmis.change_of_character as coc
from fmis.change_of_character import (
    ChangeOfCharacter,
    ChangeOfCharacterError,
    ChangeOfCharacterInputError,
    contextual_changes_of_character,
    derive_changes_of_character,
)
from fmis.change_of_character import changes as changes_mod
from fmis.change_of_character import models as models_mod
from fmis.change_of_character import pipeline as pipeline_mod
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
from fmis.market_structure import DEFAULT_RIGHT_BARS, StructuralSwingLabel, detect_swings
from fmis.series_context import (
    ContextualSeries,
    SeriesIdentityMismatchError,
    contextual_structural_state_history,
    contextual_structural_swings,
    contextual_structural_trend_history,
)
from fmis.structure_break import (
    StructureBreak,
    contextual_structure_breaks,
    derive_structure_breaks,
)

PACKAGE_DIR = Path(coc.__file__).parent
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
        origin=LevelOrigin(
            index=origin_index,
            timestamp=_BASE + timedelta(hours=4 * origin_index),
            label=label,
            confirmation_bars=confirmation_bars,
        ),
    )


def break_at(
    index: int,
    side: LevelSide,
    *,
    origin_index: int | None = None,
    price: float = 100.0,
    label: StructuralSwingLabel | None = None,
    bars: int | None = None,
) -> StructureBreak:
    """A `StructureBreak` built directly, with a crossing consistent with it.

    Constructed rather than derived so a test can express a (bar, side)
    combination without engineering a candle series that produces it. The
    crossing is still real and both objects still self-validate.

    ``bars`` defaults to ``min(RB, index)`` so that a break at an early bar is
    representable at all: a break requires ``origin.confirmed_at <= index``,
    which `RB` alone cannot satisfy for ``index < RB``.

    Since Milestone AH the window is carried on the level's own origin and must
    be **at least 1**, so ``index`` must be at least 1 too: a level cannot have
    become knowable at bar 0. `test_a_break_at_bar_zero_is_unrepresentable`
    pins that.
    """
    if bars is None:
        bars = min(RB, index)
    if bars < 1:
        raise ValueError(
            f"a break at bar {index} needs a confirmation window of at least 1, "
            "which no level at or before that bar can have"
        )
    if origin_index is None:
        origin_index = index - bars
    lvl = level(price, side, origin_index, label, confirmation_bars=bars)
    if side is LevelSide.UPPER:
        bar = candle(index, price - 1, price + 3, price - 2, price + 2)
    else:
        bar = candle(index, price + 1, price + 2, price - 3, price - 2)
    crossing = LevelCrossingEvent(
        level=lvl,
        candle=bar,
        index=index,
        kind=CrossingKind.CLOSE_BREACH,
        mechanism=CrossingMechanism.WITHIN_RANGE,
    )
    return StructureBreak(crossing=crossing)


def run(*spec: tuple[int, LevelSide]) -> tuple[StructureBreak, ...]:
    """A break run from ``(bar, side)`` pairs, with distinct level prices."""
    return tuple(
        break_at(index, side, price=100.0 + position)
        for position, (index, side) in enumerate(spec)
    )


U = LevelSide.UPPER
L = LevelSide.LOWER


def sides_and_bars(
    changes: tuple[ChangeOfCharacter, ...],
) -> list[tuple[int, str, int, str]]:
    return [
        (c.previous.index, c.previous.side.value, c.index, c.side.value)
        for c in changes
    ]


def chain(
    candles: CandleSeries, right_bars: int = RB
) -> tuple[StructureBreak, ...]:
    """The full context-free chain: candles -> swings -> levels -> crossings -> breaks."""
    swings = contextual_structural_swings(candles, right_bars=right_bars)
    levels = structural_levels(swings.values)
    crossings = derive_level_crossings(candles, list(levels))
    return derive_structure_breaks(levels, crossings)


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


def outside_bar_breaks() -> tuple[StructureBreak, ...]:
    """The design §2.3 counterexample: ``upper@4 · upper@12 · lower@12``.

    Derived through `derive_structure_breaks`, not hand-assembled, so the shape is
    demonstrably one the shipped break layer produces. It needs the reference low
    to sit **above** the reference high, exactly as ADR-0020 §3.9 described.
    """
    early_up = level(101.0, U, 1)
    up = level(103.0, U, 5)
    low = level(110.0, L, 6)
    outside = candle(12, 105, 130, 90, 106)  # closes above 103 and below 110
    events = [
        LevelCrossingEvent(
            level=early_up,
            candle=candle(4, 100, 102, 99, 101.5),
            index=4,
            kind=CrossingKind.CLOSE_BREACH,
            mechanism=CrossingMechanism.WITHIN_RANGE,
        ),
        LevelCrossingEvent(
            level=up,
            candle=outside,
            index=12,
            kind=CrossingKind.CLOSE_BREACH,
            mechanism=CrossingMechanism.WITHIN_RANGE,
        ),
        LevelCrossingEvent(
            level=low,
            candle=outside,
            index=12,
            kind=CrossingKind.CLOSE_BREACH,
            mechanism=CrossingMechanism.WITHIN_RANGE,
        ),
    ]
    return derive_structure_breaks(
        [early_up, up, low], events
    )


def adr_0020_sketch(
    breaks: tuple[StructureBreak, ...],
) -> tuple[tuple[StructureBreak, StructureBreak], ...]:
    """ADR-0020 §7's superseded sketch, kept **only** to pin the disagreement."""
    return tuple((a, b) for a, b in zip(breaks, breaks[1:]) if a.side is not b.side)


# ===================== 1. the model =========================================


def test_a_change_projects_every_derived_fact() -> None:
    previous, subject = run((5, U), (9, L))
    change = ChangeOfCharacter(subject=subject, previous=previous)
    assert change.index == subject.index == 9
    assert change.timestamp == subject.timestamp
    assert change.side is L
    assert change.subject is subject
    assert change.previous is previous


def test_the_model_stores_exactly_two_fields() -> None:
    import dataclasses

    assert [f.name for f in dataclasses.fields(ChangeOfCharacter)] == [
        "subject",
        "previous",
    ]


def test_only_three_projections_exist() -> None:
    projections = {
        name
        for name in dir(ChangeOfCharacter)
        if isinstance(getattr(ChangeOfCharacter, name, None), property)
    }
    assert projections == {"index", "timestamp", "side"}


def test_no_lifecycle_or_interpretation_field_exists() -> None:
    previous, subject = run((5, U), (9, L))
    change = ChangeOfCharacter(subject=subject, previous=previous)
    for absent in (
        "previous_side",
        "bars_since",
        "duration",
        "direction",
        "bullish",
        "bearish",
        "confirmed",
        "strength",
        "confidence",
        "valid",
        "invalidated",
        "failed",
        "active",
        "trend",
        "regime",
        "bias",
        "state",
    ):
        assert not hasattr(change, absent), absent


def test_a_change_is_immutable() -> None:
    previous, subject = run((5, U), (9, L))
    change = ChangeOfCharacter(subject=subject, previous=previous)
    with pytest.raises(AttributeError):
        change.subject = previous  # type: ignore[misc]


def test_equality_and_hashing_are_structural() -> None:
    previous, subject = run((5, U), (9, L))
    one = ChangeOfCharacter(subject=subject, previous=previous)
    two = ChangeOfCharacter(subject=subject, previous=previous)
    assert one == two
    assert hash(one) == hash(two)
    assert len({one, two}) == 1


def test_repr_is_stable_and_names_the_type() -> None:
    previous, subject = run((5, U), (9, L))
    change = ChangeOfCharacter(subject=subject, previous=previous)
    assert repr(change).startswith("ChangeOfCharacter(")


def test_a_change_round_trips_through_pickle() -> None:
    previous, subject = run((5, U), (9, L))
    change = ChangeOfCharacter(subject=subject, previous=previous)
    assert pickle.loads(pickle.dumps(change)) == change


# ===================== 2. model self-validation =============================


def test_a_change_cannot_be_built_from_two_breaks_on_one_side() -> None:
    previous, subject = run((5, U), (9, U))
    with pytest.raises(ValueError) as excinfo:
        ChangeOfCharacter(subject=subject, previous=previous)
    assert str(excinfo.value) == (
        "previous break is on the same side (upper); character did not change"
    )


def test_a_change_cannot_be_built_from_a_same_bar_predecessor() -> None:
    """The intrabar refusal, enforced by the model itself."""
    upper, lower = run((12, U), (12, L))
    with pytest.raises(ValueError) as excinfo:
        ChangeOfCharacter(subject=lower, previous=upper)
    assert str(excinfo.value) == (
        "previous break index (12) does not precede the subject's (12); "
        "two breaks at one bar carry no order in time"
    )


def test_a_change_cannot_be_built_from_a_later_predecessor() -> None:
    earlier, later = run((5, U), (9, L))
    with pytest.raises(ValueError) as excinfo:
        ChangeOfCharacter(subject=earlier, previous=later)
    assert str(excinfo.value) == (
        "previous break index (9) does not precede the subject's (5); "
        "two breaks at one bar carry no order in time"
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"subject": "no", "previous": break_at(5, U)},
            "subject must be a StructureBreak, got str",
        ),
        (
            {"subject": break_at(9, L), "previous": 3},
            "previous must be a StructureBreak, got int",
        ),
    ],
)
def test_model_type_validation(kwargs: dict, message: str) -> None:
    with pytest.raises(TypeError) as excinfo:
        ChangeOfCharacter(**kwargs)
    assert str(excinfo.value) == message


def test_the_input_error_is_a_value_error_and_a_package_error() -> None:
    assert issubclass(ChangeOfCharacterInputError, ChangeOfCharacterError)
    assert issubclass(ChangeOfCharacterInputError, ValueError)
    assert not issubclass(ChangeOfCharacterError, ValueError)


# ===================== 3. bullish and bearish changes =======================


def test_a_bullish_shaped_change_is_an_upper_break_after_a_lower_one() -> None:
    breaks = run((4, L), (11, U))
    got = derive_changes_of_character(breaks)
    assert len(got) == 1
    assert got[0].side is U
    assert got[0].previous.side is L
    assert got[0].index == 11


def test_a_bearish_shaped_change_is_a_lower_break_after_an_upper_one() -> None:
    breaks = run((4, U), (11, L))
    got = derive_changes_of_character(breaks)
    assert len(got) == 1
    assert got[0].side is L
    assert got[0].previous.side is U
    assert got[0].index == 11


def test_neither_direction_is_named_bullish_or_bearish() -> None:
    """`side` carries the sense; naming it bullish would be the interpretation."""
    upward = derive_changes_of_character(run((4, L), (11, U)))[0]
    downward = derive_changes_of_character(run((4, U), (11, L)))[0]
    assert upward.side is LevelSide.UPPER
    assert downward.side is LevelSide.LOWER
    for change in (upward, downward):
        assert "bull" not in repr(change).lower()
        assert "bear" not in repr(change).lower()
        assert "revers" not in repr(change).lower()


# ===================== 4. the predecessor rule ==============================


def test_the_predecessor_is_the_latest_strictly_earlier_break_bar() -> None:
    breaks = run((3, U), (6, U), (10, L))
    got = derive_changes_of_character(breaks)
    assert len(got) == 1
    assert got[0].previous.index == 6  # not 3


def test_no_change_at_the_first_break_bearing_bar() -> None:
    assert derive_changes_of_character(run((7, U))) == ()
    got = derive_changes_of_character(run((7, U), (9, L)))
    assert [c.index for c in got] == [9]


def test_a_single_break_never_changes_character() -> None:
    for side in (U, L):
        assert derive_changes_of_character(run((5, side))) == ()


def test_no_bar_carrying_a_break_lies_between_a_change_and_its_predecessor() -> None:
    breaks = run((2, U), (5, U), (8, L), (13, U), (14, L))
    got = derive_changes_of_character(breaks)
    bars = sorted({b.index for b in breaks})
    for change in got:
        between = [
            bar for bar in bars if change.previous.index < bar < change.index
        ]
        assert between == []


# ===================== 5. the transition table ==============================

#: ADR-0021 §3.3, exhaustive over 4 prior characters x 3 side sets. Each row is
#: (prior bar spec, current bar spec, expected change side or None).
_TRANSITIONS = [
    ((), ((20, U),), None),
    ((), ((20, L),), None),
    ((), ((20, U), (20, L)), None),
    (((10, U),), ((20, U),), None),
    (((10, U),), ((20, L),), L),
    (((10, U),), ((20, U), (20, L)), L),
    (((10, L),), ((20, L),), None),
    (((10, L),), ((20, U),), U),
    (((10, L),), ((20, U), (20, L)), U),
    (((10, U), (10, L)), ((20, U),), None),
    (((10, U), (10, L)), ((20, L),), None),
    (((10, U), (10, L)), ((20, U), (20, L)), None),
]


@pytest.mark.parametrize(("prior", "current", "expected"), _TRANSITIONS)
def test_the_transition_table_is_exhaustive_and_exact(
    prior: tuple, current: tuple, expected: LevelSide | None
) -> None:
    got = derive_changes_of_character(run(*prior, *current))
    at_bar = [c for c in got if c.index == 20]
    if expected is None:
        assert at_bar == []
    else:
        assert len(at_bar) == 1
        assert at_bar[0].side is expected
        assert at_bar[0].previous.index == 10


def test_the_transition_table_covers_every_combination() -> None:
    assert len(_TRANSITIONS) == 12
    priors = {tuple(sorted(side.value for _, side in p)) for p, _, _ in _TRANSITIONS}
    currents = {tuple(sorted(side.value for _, side in c)) for _, c, _ in _TRANSITIONS}
    assert priors == {(), ("upper",), ("lower",), ("lower", "upper")}
    assert currents == {("upper",), ("lower",), ("lower", "upper")}


def test_the_next_character_never_depends_on_whether_a_change_was_emitted() -> None:
    """After a lower break at 20, a later upper break changes character either way."""
    after_change = derive_changes_of_character(run((10, U), (20, L), (30, U)))
    after_continuation = derive_changes_of_character(run((10, L), (20, L), (30, U)))
    assert [c.index for c in after_change] == [20, 30]
    assert [c.index for c in after_continuation] == [30]
    assert after_change[-1].previous.index == 20
    assert after_continuation[-1].previous.index == 20


def test_indeterminate_suppresses_but_does_not_persist() -> None:
    breaks = run((10, U), (10, L), (20, U), (30, L))
    got = derive_changes_of_character(breaks)
    assert [c.index for c in got] == [30]
    assert got[0].previous.index == 20


# ===================== 6. alternating and repeated breaks ===================


def test_alternating_breaks_change_character_every_time() -> None:
    breaks = run((2, U), (4, L), (6, U), (8, L), (10, U))
    got = derive_changes_of_character(breaks)
    assert [c.index for c in got] == [4, 6, 8, 10]
    assert [c.side.value for c in got] == ["lower", "upper", "lower", "upper"]


def test_repeated_same_side_breaks_never_change_character() -> None:
    for side in (U, L):
        breaks = run((2, side), (5, side), (9, side), (14, side))
        assert derive_changes_of_character(breaks) == ()


def test_a_run_of_continuations_after_a_change_yields_one_change() -> None:
    breaks = run((2, U), (5, U), (9, L), (12, L), (15, L))
    got = derive_changes_of_character(breaks)
    assert [c.index for c in got] == [9]
    assert got[0].previous.index == 5


def test_character_is_the_last_break_bar_not_an_accumulated_run() -> None:
    """Three upper breaks give the same character as one — E4."""
    one = derive_changes_of_character(run((5, U), (20, L)))
    three = derive_changes_of_character(run((5, U), (8, U), (11, U), (20, L)))
    assert [c.side for c in one] == [c.side for c in three] == [L]
    assert one[0].index == three[0].index == 20
    assert three[0].previous.index == 11


# ===================== 7. outside bars ======================================


def test_the_outside_bar_fixture_is_produced_by_the_break_layer() -> None:
    breaks = outside_bar_breaks()
    assert [(b.index, b.side.value) for b in breaks] == [
        (4, "upper"),
        (12, "upper"),
        (12, "lower"),
    ]


def test_an_outside_bar_change_names_a_strictly_earlier_predecessor() -> None:
    got = derive_changes_of_character(outside_bar_breaks())
    assert sides_and_bars(got) == [(4, "upper", 12, "lower")]


def test_the_adr_0020_sketch_claims_an_intrabar_order_and_is_superseded() -> None:
    """The audit's principal finding (design §2.3), pinned so it cannot be lost."""
    breaks = outside_bar_breaks()
    sketch = adr_0020_sketch(breaks)
    shipped = derive_changes_of_character(breaks)

    # The sketch pairs two breaks that share a bar.
    assert [(a.index, b.index) for a, b in sketch] == [(12, 12)]
    # The shipped rule never does, and cannot: the model rejects it.
    assert all(c.previous.index < c.index for c in shipped)
    assert [(c.previous.index, c.index) for c in shipped] == [(4, 12)]
    # Both agree bar 12 is where character changed.
    assert {b.index for _, b in sketch} == {c.index for c in shipped} == {12}


def test_the_two_rules_agree_whenever_no_two_breaks_share_a_bar() -> None:
    for seed in range(60, 90):
        breaks = chain(series(seeded_rows(200, seed)))
        if len({b.index for b in breaks}) != len(breaks):
            continue
        sketch = [(a, b) for a, b in adr_0020_sketch(breaks)]
        shipped = derive_changes_of_character(breaks)
        assert [(a.index, b.index) for a, b in sketch] == [
            (c.previous.index, c.index) for c in shipped
        ]


def test_both_breaks_of_an_outside_bar_are_tested_against_one_prior_side() -> None:
    breaks = run((5, L), (12, U), (12, L))
    got = derive_changes_of_character(breaks)
    assert len(got) == 1
    assert got[0].side is U
    assert got[0].previous.index == 5


def test_an_outside_bar_can_never_produce_two_changes() -> None:
    for prior in ((3, U), (3, L)):
        got = derive_changes_of_character(run(prior, (9, U), (9, L)))
        assert len(got) <= 1


# ===================== 8. equal highs, equal lows, gaps =====================


@pytest.mark.parametrize("label", list(StructuralSwingLabel))
def test_every_swing_label_can_take_part_in_a_change(
    label: StructuralSwingLabel,
) -> None:
    side = U if label.value.endswith("high") else L
    other = L if side is U else U
    previous = break_at(4, other, price=100.0)
    subject = break_at(11, side, price=120.0, label=label)
    got = derive_changes_of_character([previous, subject])
    assert len(got) == 1
    assert got[0].subject.label is label


def test_an_equal_high_derived_level_can_change_character() -> None:
    previous = break_at(4, L, price=95.0, label=StructuralSwingLabel.LOWER_LOW)
    subject = break_at(11, U, price=105.0, label=StructuralSwingLabel.EQUAL_HIGH)
    got = derive_changes_of_character([previous, subject])
    assert got[0].subject.label is StructuralSwingLabel.EQUAL_HIGH


def test_an_equal_low_derived_level_can_change_character() -> None:
    previous = break_at(4, U, price=105.0, label=StructuralSwingLabel.HIGHER_HIGH)
    subject = break_at(11, L, price=95.0, label=StructuralSwingLabel.EQUAL_LOW)
    got = derive_changes_of_character([previous, subject])
    assert got[0].subject.label is StructuralSwingLabel.EQUAL_LOW


def test_the_label_is_not_read_by_this_layer_at_all() -> None:
    """Two runs differing only in label give structurally identical changes."""
    a = derive_changes_of_character(
        [
            break_at(4, U, price=105.0, label=StructuralSwingLabel.HIGHER_HIGH),
            break_at(11, L, price=95.0, label=StructuralSwingLabel.LOWER_LOW),
        ]
    )
    b = derive_changes_of_character(
        [
            break_at(4, U, price=105.0, label=StructuralSwingLabel.EQUAL_HIGH),
            break_at(11, L, price=95.0, label=StructuralSwingLabel.EQUAL_LOW),
        ]
    )
    assert [(c.index, c.side) for c in a] == [(c.index, c.side) for c in b]


def test_a_gapped_break_changes_character_like_any_other() -> None:
    lvl = level(103.0, U, 5)
    gapped = LevelCrossingEvent(
        level=lvl,
        candle=candle(11, 150, 155, 148, 152),
        index=11,
        kind=CrossingKind.CLOSE_BREACH,
        mechanism=CrossingMechanism.GAPPED_BEYOND,
    )
    subject = StructureBreak(crossing=gapped)
    got = derive_changes_of_character([break_at(4, L, price=95.0), subject])
    assert len(got) == 1
    assert got[0].subject.crossing.mechanism is CrossingMechanism.GAPPED_BEYOND


def test_the_mechanism_is_carried_through_for_the_consumer() -> None:
    breaks = run((4, U), (11, L))
    got = derive_changes_of_character(breaks)
    assert got[0].subject.crossing.mechanism is CrossingMechanism.WITHIN_RANGE
    assert got[0].previous.crossing.mechanism is CrossingMechanism.WITHIN_RANGE


# ===================== 9. duplicates and validation =========================


def test_duplicated_breaks_change_nothing() -> None:
    breaks = list(run((4, U), (11, L), (15, U)))
    once = derive_changes_of_character(breaks)
    twice = derive_changes_of_character(breaks + breaks)
    assert once == twice


def test_a_rebuilt_equal_break_is_a_duplicate_not_a_conflict() -> None:
    first = break_at(4, U)
    same = break_at(4, U)
    assert first is not same and first == same
    got = derive_changes_of_character([first, same, break_at(11, L)])
    assert len(got) == 1
    # The **first** equal break is kept, by reference — not an equal substitute
    # chosen by input order.
    assert got[0].previous is first
    assert derive_changes_of_character([same, first, break_at(11, L)])[0].previous is (
        same
    )


def test_two_distinct_breaks_at_one_bar_and_side_are_rejected() -> None:
    with pytest.raises(ChangeOfCharacterInputError) as excinfo:
        derive_changes_of_character(
            [break_at(4, U, price=100.0), break_at(4, U, price=101.0)]
        )
    assert str(excinfo.value) == (
        "breaks[1] shares bar index 4 and side upper with a different break; "
        "the previous break at that bar would be ambiguous"
    )


def test_a_conflict_is_rejected_before_any_change_is_built() -> None:
    with pytest.raises(ChangeOfCharacterInputError):
        derive_changes_of_character(
            [
                break_at(4, U, price=100.0),
                break_at(11, L, price=90.0),
                break_at(4, U, price=101.0),
            ]
        )


def test_two_distinct_breaks_at_one_bar_on_different_sides_are_accepted() -> None:
    got = derive_changes_of_character(run((4, L), (9, U), (9, L)))
    assert [c.index for c in got] == [9]


@pytest.mark.parametrize(
    ("argument", "message"),
    [
        ("nope", "breaks must be a sequence of StructureBreak, got str"),
        (b"nope", "breaks must be a sequence of StructureBreak, got bytes"),
        (None, "breaks must be a sequence of StructureBreak, got NoneType"),
        (42, "breaks must be a sequence of StructureBreak, got int"),
        (
            iter([]),
            "breaks must be a sequence of StructureBreak, got list_iterator",
        ),
    ],
)
def test_argument_validation_messages(argument: object, message: str) -> None:
    with pytest.raises(TypeError) as excinfo:
        derive_changes_of_character(argument)  # type: ignore[arg-type]
    assert str(excinfo.value) == message


def test_a_non_break_element_is_rejected_by_position() -> None:
    with pytest.raises(TypeError) as excinfo:
        derive_changes_of_character([break_at(4, U), "no"])
    assert str(excinfo.value) == "breaks[1] must be a StructureBreak, got str"


def test_the_function_takes_no_configuration() -> None:
    import inspect

    signature = inspect.signature(derive_changes_of_character)
    assert list(signature.parameters) == ["breaks"]
    for banned in ("confirmation_bars", "threshold", "minimum", "policy", "tolerance"):
        assert banned not in signature.parameters, banned


def test_the_input_is_not_mutated() -> None:
    breaks = list(run((4, U), (11, L)))
    snapshot = list(breaks)
    derive_changes_of_character(breaks)
    assert breaks == snapshot


# ===================== 10. empty inputs =====================================


def test_empty_input() -> None:
    assert derive_changes_of_character(()) == ()
    assert derive_changes_of_character([]) == ()


def test_an_empty_result_is_an_immutable_tuple() -> None:
    got = derive_changes_of_character(())
    assert isinstance(got, tuple)
    with pytest.raises(TypeError):
        got[0] = 1  # type: ignore[index]


def test_an_empty_candle_series_yields_no_change() -> None:
    empty = CandleSeries(symbol="BTCUSDT", timeframe="4h", candles=())
    assert derive_changes_of_character(chain(empty)) == ()


# ===================== 11. ordering =========================================


def test_changes_are_ordered_by_bar() -> None:
    got = derive_changes_of_character(run((2, U), (5, L), (9, U), (14, L)))
    assert [c.index for c in got] == [5, 9, 14]


def test_the_ordering_key_is_strictly_increasing() -> None:
    for seed in range(200, 230):
        got = derive_changes_of_character(chain(series(seeded_rows(180, seed))))
        indices = [c.index for c in got]
        assert indices == sorted(indices)
        assert len(set(indices)) == len(indices)


def test_index_order_is_timestamp_order() -> None:
    got = derive_changes_of_character(run((2, U), (5, L), (9, U)))
    assert [c.timestamp for c in got] == sorted(c.timestamp for c in got)


def test_at_most_one_change_per_bar() -> None:
    for seed in range(300, 330):
        got = derive_changes_of_character(chain(series(seeded_rows(180, seed))))
        assert len({c.index for c in got}) == len(got)


def test_the_output_is_never_sorted_after_construction() -> None:
    """Ordering is a property of the walk, not a step that could be removed."""
    tree = ast.parse((PACKAGE_DIR / "changes.py").read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "sorted"
    ]
    assert len(calls) == 1  # the bar indices, and nothing else
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "sort" not in attributes


# ===================== 12. input-order invariance ===========================


def test_permuting_the_input_changes_nothing() -> None:
    breaks = list(chain(series(seeded_rows(250, 31))))
    expected = derive_changes_of_character(breaks)
    rng = random.Random(7)
    for _ in range(10):
        shuffled = list(breaks)
        rng.shuffle(shuffled)
        assert derive_changes_of_character(shuffled) == expected


def test_reversing_the_input_changes_nothing() -> None:
    breaks = list(run((2, U), (5, L), (9, U), (14, L)))
    assert derive_changes_of_character(breaks[::-1]) == derive_changes_of_character(
        breaks
    )


def test_every_permutation_of_a_small_run_agrees() -> None:
    breaks = list(run((2, U), (5, L), (9, U)))
    expected = derive_changes_of_character(breaks)
    for permutation in itertools.permutations(breaks):
        assert derive_changes_of_character(list(permutation)) == expected


def test_outside_bar_side_order_does_not_change_the_result() -> None:
    breaks = list(outside_bar_breaks())
    forward = derive_changes_of_character(breaks)
    swapped = derive_changes_of_character([breaks[0], breaks[2], breaks[1]])
    assert forward == swapped


# ===================== 13. prefix stability =================================


def _prefix_violations(rows: list, right_bars: int = RB) -> int:
    full = derive_changes_of_character(chain(series(rows), right_bars))
    violations = 0
    for length in range(1, len(rows) + 1):
        prefix = derive_changes_of_character(chain(series(rows[:length]), right_bars))
        expected = tuple(c for c in full if c.index < length)
        if prefix != expected:
            violations += 1
    return violations


@pytest.mark.parametrize("seed", [401, 402, 403, 404, 405])
def test_prefix_stability_on_seeded_fixtures(seed: int) -> None:
    assert _prefix_violations(seeded_rows(120, seed)) == 0


@pytest.mark.parametrize("right_bars", [1, 2, 3])
def test_prefix_stability_across_confirmation_delays(right_bars: int) -> None:
    assert _prefix_violations(seeded_rows(120, 411), right_bars) == 0


def test_prefix_stability_on_the_real_fixture() -> None:
    real = real_series()
    rows = [(c.open, c.high, c.low, c.close) for c in real.candles]
    assert _prefix_violations(rows) == 0


def test_adding_later_breaks_cannot_change_earlier_changes() -> None:
    breaks = list(run((2, U), (5, L), (9, U)))
    before = derive_changes_of_character(breaks)
    after = derive_changes_of_character(breaks + list(run((20, L), (25, U))))
    assert after[: len(before)] == before


def test_a_later_two_sided_bar_cannot_retract_an_earlier_change() -> None:
    breaks = list(run((2, U), (5, L)))
    before = derive_changes_of_character(breaks)
    after = derive_changes_of_character(breaks + list(run((9, U), (9, L))))
    assert after[: len(before)] == before


def test_truncating_the_break_run_is_also_stable() -> None:
    breaks = list(chain(series(seeded_rows(200, 421))))
    full = derive_changes_of_character(breaks)
    for cut in range(len(breaks) + 1):
        prefix = derive_changes_of_character(breaks[:cut])
        bars = {b.index for b in breaks[:cut]}
        expected = tuple(
            c for c in full if c.index in bars and c.previous.index in bars
        )
        assert prefix == expected


# ===================== 14. replay determinism ===============================


def test_replay_is_deterministic() -> None:
    breaks = chain(series(seeded_rows(200, 51)))
    first = derive_changes_of_character(breaks)
    for _ in range(5):
        assert derive_changes_of_character(breaks) == first


def test_a_rebuilt_equal_pipeline_replays_identically() -> None:
    rows = seeded_rows(200, 53)
    first = derive_changes_of_character(chain(series(rows)))
    second = derive_changes_of_character(chain(series(list(rows))))
    assert first == second


def test_identity_of_the_supplied_breaks_is_preserved() -> None:
    breaks = list(run((2, U), (5, L)))
    got = derive_changes_of_character(breaks)
    assert got[0].subject is breaks[1]
    assert got[0].previous is breaks[0]


# ===================== 15. the safe pipeline ================================


def _contextual_breaks(candles: CandleSeries) -> ContextualSeries[StructureBreak]:
    swings = contextual_structural_swings(candles, right_bars=RB)
    levels = contextual_structural_levels(swings)
    crossings = contextual_level_crossings(candles, levels)
    return contextual_structure_breaks(levels, crossings)


def test_the_safe_pipeline_end_to_end() -> None:
    breaks = _contextual_breaks(series(seeded_rows(200, 61)))
    got = contextual_changes_of_character(breaks)
    assert isinstance(got, ContextualSeries)
    assert got.values == derive_changes_of_character(breaks.values)


def test_identity_is_carried_by_reference() -> None:
    breaks = _contextual_breaks(series(seeded_rows(200, 63)))
    assert contextual_changes_of_character(breaks).identity is breaks.identity


def test_empty_contextual_input_retains_identity() -> None:
    identity = SeriesIdentity(symbol="BTCUSDT", timeframe="4h")
    envelope: ContextualSeries[StructureBreak] = ContextualSeries(
        identity=identity, values=()
    )
    got = contextual_changes_of_character(envelope)
    assert got.values == ()
    assert got.identity is identity


def test_a_non_empty_result_also_carries_the_input_identity_object() -> None:
    identity = SeriesIdentity(symbol="BTCUSDT", timeframe="4h")
    envelope = ContextualSeries(identity=identity, values=run((2, U), (5, L)))
    got = contextual_changes_of_character(envelope)
    assert len(got.values) == 1
    assert got.identity is identity


def test_a_bare_payload_where_an_envelope_belongs_is_rejected() -> None:
    with pytest.raises(TypeError) as excinfo:
        contextual_changes_of_character(run((2, U), (5, L)))  # type: ignore[arg-type]
    assert str(excinfo.value) == "breaks must be a ContextualSeries, got tuple"


def test_the_envelope_message_matches_every_other_pipeline() -> None:
    from fmis.level_crossing import pipeline as lc_pipeline
    from fmis.series_context import pipeline as sc_pipeline
    from fmis.structure_break import pipeline as sb_pipeline

    for module in (lc_pipeline, sc_pipeline, sb_pipeline, pipeline_mod):
        with pytest.raises(TypeError) as excinfo:
            module._require_envelope((), name="x")
        assert str(excinfo.value) == "x must be a ContextualSeries, got tuple"


def test_no_pipeline_function_accepts_an_identity_argument() -> None:
    import inspect

    signature = inspect.signature(contextual_changes_of_character)
    assert list(signature.parameters) == ["breaks"]
    assert "identity" not in signature.parameters


def test_context_substitution_is_unrepresentable() -> None:
    other = SeriesIdentity(symbol="ETHUSDT", timeframe="1h")
    breaks = _contextual_breaks(series(seeded_rows(120, 67)))
    with pytest.raises(TypeError):
        contextual_changes_of_character(breaks, identity=other)  # type: ignore[call-arg]


def test_the_wrapper_does_not_call_require_same_identity() -> None:
    """One subject: a one-subject check would imply a guarantee that is not made."""
    source = (PACKAGE_DIR / "pipeline.py").read_text()
    tree = ast.parse(source)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "require_same_identity" not in called
    assert "derive_changes_of_character" in called
    assert "ContextualSeries" in called


def test_an_identity_mismatch_upstream_is_still_rejected_upstream() -> None:
    """This layer has one input, so the mismatch contract stays where it belongs."""
    btc = series(seeded_rows(120, 71))
    eth = series(seeded_rows(120, 73), symbol="ETHUSDT")
    swings = contextual_structural_swings(btc, right_bars=RB)
    levels = contextual_structural_levels(swings)
    crossings = contextual_level_crossings(eth, contextual_structural_levels(
        contextual_structural_swings(eth, right_bars=RB)
    ))
    with pytest.raises(SeriesIdentityMismatchError):
        contextual_structure_breaks(levels, crossings)


@pytest.mark.parametrize(
    "name",
    ["empty", "single_break", "alternating", "repeated", "outside_bar", "real"],
)
def test_context_free_and_context_aware_payloads_are_identical(name: str) -> None:
    identity = SeriesIdentity(symbol="BTCUSDT", timeframe="4h")
    payloads = {
        "empty": (),
        "single_break": run((5, U)),
        "alternating": run((2, U), (5, L), (9, U)),
        "repeated": run((2, U), (5, U), (9, U)),
        "outside_bar": outside_bar_breaks(),
        "real": chain(real_series()),
    }
    values = payloads[name]
    envelope = ContextualSeries(identity=identity, values=values)
    assert contextual_changes_of_character(envelope).values == (
        derive_changes_of_character(values)
    )


def test_identity_cannot_change_a_payload() -> None:
    values = run((2, U), (5, L), (9, U))
    bare = derive_changes_of_character(values)
    for symbol, timeframe in (("BTCUSDT", "4h"), ("ETHUSDT", "1h"), ("X", "1m")):
        envelope = ContextualSeries(
            identity=SeriesIdentity(symbol=symbol, timeframe=timeframe), values=values
        )
        assert contextual_changes_of_character(envelope).values == bare


# ===================== 16. properties =======================================


def _property_runs() -> list[tuple[StructureBreak, ...]]:
    runs = [chain(series(seeded_rows(180, seed))) for seed in range(500, 520)]
    runs.append(outside_bar_breaks())
    runs.append(run((2, U), (5, L), (9, U), (9, L), (14, U)))
    runs.append(())
    return runs


def test_every_change_references_supplied_breaks_by_identity() -> None:
    for breaks in _property_runs():
        supplied = {id(b) for b in breaks}
        for change in derive_changes_of_character(breaks):
            assert id(change.subject) in supplied
            assert id(change.previous) in supplied


def test_every_change_satisfies_all_four_conjuncts() -> None:
    for breaks in _property_runs():
        bars = sorted({b.index for b in breaks})
        by_bar: dict[int, set] = {}
        for b in breaks:
            by_bar.setdefault(b.index, set()).add(b.side)
        for change in derive_changes_of_character(breaks):
            assert isinstance(change.subject, StructureBreak)
            assert change.previous.index < change.index
            assert len(by_bar[change.previous.index]) == 1
            assert change.previous.side is not change.side
            position = bars.index(change.index)
            assert bars[position - 1] == change.previous.index


def test_no_change_is_emitted_at_the_earliest_break_bar() -> None:
    for breaks in _property_runs():
        if not breaks:
            continue
        earliest = min(b.index for b in breaks)
        assert all(c.index != earliest for c in derive_changes_of_character(breaks))


def test_changes_are_a_subsequence_of_the_break_bars() -> None:
    for breaks in _property_runs():
        bars = {b.index for b in breaks}
        assert all(c.index in bars for c in derive_changes_of_character(breaks))


def test_an_exhaustive_small_space_is_consistent() -> None:
    """Every run of up to four (bar, side) breaks over four bars, checked directly."""
    checked = 0
    for size in range(0, 4):
        for bars in itertools.combinations(range(1, 6), size):
            for sides in itertools.product((U, L), repeat=size):
                breaks = run(*zip(bars, sides))
                got = derive_changes_of_character(breaks)
                expected = []
                for earlier, later in itertools.pairwise(bars):
                    if sides[bars.index(later)] is not sides[bars.index(earlier)]:
                        expected.append(later)
                assert [c.index for c in got] == expected
                checked += 1
    assert checked > 100


def test_repeated_execution_produces_identical_results() -> None:
    for breaks in _property_runs():
        first = derive_changes_of_character(breaks)
        assert all(derive_changes_of_character(breaks) == first for _ in range(3))


# ===================== 17. adversarial fixtures =============================


def test_adversarial_a_break_run_with_every_bar_two_sided() -> None:
    breaks = run((2, U), (2, L), (5, U), (5, L), (8, U), (8, L))
    assert derive_changes_of_character(breaks) == ()


def test_adversarial_alternating_two_sided_and_single_sided_bars() -> None:
    breaks = run((2, U), (5, U), (5, L), (8, L), (11, U), (11, L), (14, U))
    got = derive_changes_of_character(breaks)
    # prior of 5 is {U}      -> the lower break at 5 changes character
    # prior of 8 is {U, L}   -> indeterminate, suppressed
    # prior of 11 is {L}     -> the upper break at 11 changes character
    # prior of 14 is {U, L}  -> indeterminate, suppressed
    assert [c.index for c in got] == [5, 11]


def test_adversarial_far_apart_bars() -> None:
    breaks = run((1, U), (1_000_000, L))
    got = derive_changes_of_character(breaks)
    assert [(c.previous.index, c.index) for c in got] == [(1, 1_000_000)]


def test_adversarial_adjacent_bars() -> None:
    breaks = run((5, U), (6, L), (7, U))
    assert [c.index for c in derive_changes_of_character(breaks)] == [6, 7]


def test_adversarial_a_long_alternating_run() -> None:
    # Bars start at 2, not 0: since AH no level is knowable before bar 1, so a
    # run of breaks cannot begin at the origin of the series.
    spec = [(i * 2, U if i % 2 == 0 else L) for i in range(1, 201)]
    got = derive_changes_of_character(run(*spec))
    assert len(got) == 199
    assert [c.index for c in got] == [i * 2 for i in range(2, 201)]


def test_adversarial_a_long_single_sided_run() -> None:
    spec = [(i * 2, U) for i in range(1, 201)]
    assert derive_changes_of_character(run(*spec)) == ()


def test_adversarial_many_duplicates_of_one_run() -> None:
    breaks = list(run((2, U), (5, L), (9, U)))
    expected = derive_changes_of_character(breaks)
    assert derive_changes_of_character(breaks * 50) == expected


def test_adversarial_invalid_ordering_is_not_an_error() -> None:
    """A descending run is legitimate input, not a failure — order is not a contract."""
    breaks = list(run((2, U), (5, L), (9, U)))
    assert derive_changes_of_character(sorted(breaks, key=lambda b: -b.index)) == (
        derive_changes_of_character(breaks)
    )


def test_a_break_at_bar_zero_is_unrepresentable() -> None:
    """Since AH, no level can be knowable at bar 0, so nothing can break there.

    A level becomes knowable at ``origin.index + confirmation_bars`` with a
    window of at least 1 and a non-negative origin, so the earliest breakable bar
    is 1. Before AH the window could be supplied as 0 and a bar-0 break was
    constructible — a fact no detection run could ever produce.
    """
    with pytest.raises(ValueError) as excinfo:
        break_at(0, U, origin_index=0, bars=0)
    assert "at least 1" in str(excinfo.value)

    # And not merely blocked by the helper: the model itself refuses.
    lvl = level(100.0, U, 0)
    bar = candle(0, 99.0, 103.0, 98.0, 102.0)
    crossing = LevelCrossingEvent(
        level=lvl,
        candle=bar,
        index=0,
        kind=CrossingKind.CLOSE_BREACH,
        mechanism=CrossingMechanism.WITHIN_RANGE,
    )
    with pytest.raises(ValueError) as excinfo:
        StructureBreak(crossing=crossing)
    assert str(excinfo.value) == (
        "crossing index (0) precedes eligible_from (2); the level was not yet "
        "knowable"
    )


def test_adversarial_invalid_provenance_cannot_reach_this_layer() -> None:
    """A break without provenance is unconstructible one layer down."""
    unprovenanced = PriceLevel(price=100.0, side=U, origin=None)
    crossing = LevelCrossingEvent(
        level=unprovenanced,
        candle=candle(5, 99, 103, 98, 102),
        index=5,
        kind=CrossingKind.CLOSE_BREACH,
        mechanism=CrossingMechanism.WITHIN_RANGE,
    )
    with pytest.raises(ValueError):
        StructureBreak(crossing=crossing)


def test_adversarial_a_non_close_break_cannot_reach_this_layer() -> None:
    lvl = level(100.0, U, 3)
    touch = LevelCrossingEvent(
        level=lvl,
        candle=candle(7, 99, 100, 98, 99),
        index=7,
        kind=CrossingKind.TOUCH,
        mechanism=CrossingMechanism.WITHIN_RANGE,
    )
    with pytest.raises(ValueError):
        StructureBreak(crossing=touch)


def test_adversarial_mixed_identity_breaks_are_this_layer_s_indifference() -> None:
    """Identity lives on the envelope, never on an element — ADR-0018."""
    btc = break_at(4, U)
    eth_candle = candle(11, 101, 102, 97, 98, symbol="ETHUSDT", timeframe="1h")
    eth_level = level(100.0, L, 9)
    eth = StructureBreak(
        crossing=LevelCrossingEvent(
            level=eth_level,
            candle=eth_candle,
            index=11,
            kind=CrossingKind.CLOSE_BREACH,
            mechanism=CrossingMechanism.WITHIN_RANGE,
        )
    )
    got = derive_changes_of_character([btc, eth])
    assert len(got) == 1  # the payload is analysed; identity is the envelope's job


def test_adversarial_the_real_fixture() -> None:
    breaks = chain(real_series())
    got = derive_changes_of_character(breaks)
    assert len(breaks) == 1
    assert got == ()


# ===================== 18. performance ======================================


def test_the_derivation_is_subquadratic_in_the_break_count() -> None:
    import time

    def elapsed(count: int) -> float:
        breaks = run(*[(i * 2, U if i % 2 == 0 else L) for i in range(1, count + 1)])
        best = float("inf")
        for _ in range(3):
            start = time.perf_counter()
            derive_changes_of_character(breaks)
            best = min(best, time.perf_counter() - start)
        return best

    small = elapsed(500)
    large = elapsed(4000)
    # 8x the input. Quadratic would be ~64x; allow a generous constant-factor
    # margin and still fail a quadratic implementation decisively.
    assert large < small * 24 + 0.05


def test_a_large_run_derives_quickly() -> None:
    import time

    breaks = run(*[(i * 2, U if i % 2 == 0 else L) for i in range(1, 20_001)])
    start = time.perf_counter()
    got = derive_changes_of_character(breaks)
    duration = time.perf_counter() - start
    assert len(got) == 19_999
    assert duration < 2.0


# ===================== 19. exports and architecture guards ==================


def test_the_public_api_is_exactly_five_names() -> None:
    assert set(coc.__all__) == {
        "ChangeOfCharacter",
        "ChangeOfCharacterError",
        "ChangeOfCharacterInputError",
        "derive_changes_of_character",
        "contextual_changes_of_character",
    }
    assert len(coc.__all__) == 5


def test_every_exported_name_resolves() -> None:
    for name in coc.__all__:
        assert hasattr(coc, name), name


def test_no_submodule_collides_with_a_public_name() -> None:
    import pkgutil

    submodules = {m.name for m in pkgutil.iter_modules(coc.__path__)}
    assert submodules == {"changes", "models", "pipeline"}
    assert submodules & set(coc.__all__) == set()


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


def test_every_submodule_declares_its_own_public_surface() -> None:
    """Each module's `__all__` names exactly what it defines for export.

    Without this, a submodule's `__all__` could be emptied or padded and nothing
    would notice, because the package `__init__` imports each name directly.
    """
    assert changes_mod.__all__ == ["derive_changes_of_character"]
    assert models_mod.__all__ == [
        "ChangeOfCharacter",
        "ChangeOfCharacterError",
        "ChangeOfCharacterInputError",
    ]
    assert pipeline_mod.__all__ == ["contextual_changes_of_character"]
    declared = set(changes_mod.__all__) | set(models_mod.__all__) | set(
        pipeline_mod.__all__
    )
    assert declared == set(coc.__all__)
    for module in (changes_mod, models_mod, pipeline_mod):
        for name in module.__all__:
            assert hasattr(module, name), (module.__name__, name)
        public = {
            name
            for name, value in vars(module).items()
            if not name.startswith("_")
            and getattr(value, "__module__", None) == module.__name__
        }
        assert public == set(module.__all__), module.__name__


def test_no_private_helper_is_exported() -> None:
    for private in ("_breaks_by_bar", "_require_envelope", "_SIDE_RANK"):
        assert private not in coc.__all__, private
        assert not hasattr(coc, private), private


def test_no_mutable_public_object_is_exported() -> None:
    for name in coc.__all__:
        assert not isinstance(getattr(coc, name), (list, dict, set)), name


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
        "fmis.structure_break",
        "fmis.series_context",
        "fmis.level_crossing",
        "fmis.change_of_character.changes",
        "fmis.change_of_character.models",
        "fmis.change_of_character.pipeline",
    }


def test_level_side_is_the_only_name_taken_from_level_crossing() -> None:
    """A type name, not logic — and pinned so it cannot quietly become logic."""
    taken: set[str] = set()
    for py in PACKAGE_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module == "fmis.level_crossing":
                taken |= {alias.name for alias in node.names}
    assert taken == {"LevelSide"}


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
        for banned in ("Candle", "CandleSeries", "SeriesIdentity"):
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


def test_no_level_or_crossing_object_is_reached() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            a.asname or a.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in n.names
        }
        for banned in (
            "PriceLevel",
            "LevelOrigin",
            "LevelCrossingEvent",
            "CrossingKind",
            "CrossingMechanism",
            "structural_levels",
            "derive_level_crossings",
            "crossing_kind",
        ):
            assert banned not in names, (py, banned)


def test_does_not_import_structural_trend() -> None:
    trend = "fmis." + "structural_trend"
    assert not any(i.startswith(trend) for i in _internal_imports())
    for py in PACKAGE_DIR.glob("*.py"):
        assert trend not in py.read_text(), py


def test_does_not_import_market_structure() -> None:
    assert not any(
        i.startswith("fmis.market_structure") for i in _internal_imports()
    )


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
        if internal.startswith("fmis.change_of_character"):
            continue
        assert not internal.startswith("fmis.structure_break."), internal
        assert not internal.startswith("fmis.level_crossing."), internal
        assert not internal.startswith("fmis.series_context."), internal


def test_nothing_imports_change_of_character() -> None:
    """Only `fmis.pipeline`, the application layer strictly above this package.

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
    permitted = {root / "pipeline"}
    for py in root.rglob("*.py"):
        if py.parent == PACKAGE_DIR or py.parent in permitted:
            continue
        assert "fmis.change_of_character" not in py.read_text(), py


def test_no_import_cycle_exists() -> None:
    import subprocess

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import fmis.data, fmis.market_structure, fmis.series_context, "
            "fmis.level_crossing, fmis.structure_break; "
            "assert 'fmis.change_of_character' not in sys.modules; print('ok')",
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
                    "now",
                    "utcnow",
                    "today",
                    "monotonic",
                    "perf_counter",
                    "time_ns",
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
        for banned in (
            "isclose",
            "epsilon",
            "atol",
            "rtol",
            "approx",
            "round",
            "Decimal",
            "price",
        ):
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


def test_no_break_logic_is_duplicated() -> None:
    """The break rule, its eligibility arithmetic and its ordering live upstream."""
    for py in PACKAGE_DIR.glob("*.py"):
        used = _referenced_names(py)
        for banned in (
            "derive_structure_breaks",
            "contextual_structure_breaks",
            "_levels_by_side",
            "_reference",
            "_break_key",
            "_require_confirmation_bars",
            "confirmation_bars",
            "eligible_from",
            "bisect_right",
        ):
            assert banned not in used, (py, banned)


def test_no_side_ordering_exists_anywhere_in_the_package() -> None:
    """ADR-0021 §3.7: the key is the index alone, so no side rank can exist."""
    for py in PACKAGE_DIR.glob("*.py"):
        used = _referenced_names(py)
        for banned in ("_SIDE_RANK", "SIDE_RANK", "MappingProxyType", "rank"):
            assert banned not in used, (py, banned)


def test_no_crossing_or_swing_logic_is_duplicated() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        used = _referenced_names(py)
        for banned in (
            "detect_swings",
            "left_bars",
            "right_bars",
            "structural_levels",
            "compare_swings",
            "label_swing",
            "SwingRelation",
            "_level_key",
            "_event_key",
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
            if isinstance(node, ast.Attribute) and node.attr in (
                "symbol",
                "timeframe",
            ):
                raise AssertionError(f"{py} reads an identity field directly")


def test_the_pipeline_delegates_and_never_re_derives() -> None:
    tree = ast.parse((PACKAGE_DIR / "pipeline.py").read_text())
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for required in ("derive_changes_of_character", "ContextualSeries"):
        assert required in called, required
    for node in ast.walk(tree):
        assert not isinstance(node, (ast.BinOp, ast.Compare, ast.For, ast.While)), (
            ast.dump(node)
        )


def test_no_state_machine_type_is_exported_or_defined() -> None:
    """ADR-0021 §3.3: the fold's state is an implementation detail, not a type."""
    for py in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                assert node.name in (
                    "ChangeOfCharacter",
                    "ChangeOfCharacterError",
                    "ChangeOfCharacterInputError",
                ), node.name
        used = {n.lower() for n in _referenced_names(py)}
        for banned in ("enum", "characterstate", "snapshot", "history"):
            assert banned not in used, (py, banned)


def test_no_trading_vocabulary_in_the_package() -> None:
    for py in PACKAGE_DIR.glob("*.py"):
        used = {n.lower() for n in _referenced_names(py)}
        for banned in (
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
            "portfolio",
            "size",
            "reversal",
            "trend",
        ):
            assert banned not in used, (py, banned)


# ===================== 20. nothing upstream changed =========================


def test_existing_swing_behaviour_is_unchanged() -> None:
    assert len(detect_swings(real_series())) == 5


def test_existing_level_crossing_and_break_behaviour_is_unchanged() -> None:
    real = real_series()
    swings = contextual_structural_swings(real, right_bars=RB)
    levels = structural_levels(swings.values)
    crossings = derive_level_crossings(real, list(levels))
    assert len(levels) == 3
    assert len(crossings) == 15
    assert len(derive_structure_breaks(levels, crossings)) == 1


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
    import fmis.structure_break as sb

    assert len(lc.__all__) == 13
    assert len(ms.__all__) == 19
    assert len(sc.__all__) == 7
    assert len(st.__all__) == 5
    assert len(sb.__all__) == 5


def test_the_break_model_still_exposes_exactly_what_this_layer_reads() -> None:
    """The audit conclusion, pinned: no primitive was added or needed."""
    import dataclasses

    assert {f.name for f in dataclasses.fields(StructureBreak)} == {"crossing"}
    # `eligible_from` remains readable — it became a projection of the level's
    # own provenance in Milestone AH rather than a stored field, which is why it
    # is no longer a dataclass field but is still what this layer can read.
    assert isinstance(getattr(StructureBreak, "eligible_from"), property)
    for needed in ("index", "side"):
        assert isinstance(getattr(StructureBreak, needed), property), needed


def test_default_right_bars_still_matches_the_confirmation_delay_used_here() -> None:
    assert DEFAULT_RIGHT_BARS == RB


# ===================== 21. what the next layer consumes =====================


def test_a_change_is_self_describing_without_its_inputs() -> None:
    for change in derive_changes_of_character(chain(series(seeded_rows(200, 81)))):
        described = (
            change.index,
            change.timestamp,
            change.side,
            change.previous.index,
            change.previous.side,
            change.subject.level.price,
            change.subject.origin.index,
            change.subject.label,
        )
        assert len(described) == 8


def test_the_full_chain_composes_end_to_end() -> None:
    candles = series(seeded_rows(250, 83))
    swings = contextual_structural_swings(candles, right_bars=RB)
    levels = contextual_structural_levels(swings)
    crossings = contextual_level_crossings(candles, levels)
    breaks = contextual_structure_breaks(levels, crossings)
    changes = contextual_changes_of_character(breaks)
    assert changes.identity is swings.identity is breaks.identity
    assert isinstance(changes.values, tuple)


def test_trend_remains_a_summary_of_both_and_defines_neither() -> None:
    """Review §15's ordering, pinned from this side too."""
    import fmis.structural_trend as st

    for py in Path(st.__file__).parent.glob("*.py"):
        source = py.read_text()
        assert "fmis.change_of_character" not in source, py
        assert "fmis.structure_break" not in source, py
