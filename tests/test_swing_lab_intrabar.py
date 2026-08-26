"""Ordering two events inside one bar, and refusing to when the data cannot.

The property that matters is not "the ladder resolves things" — it is **the
ladder never resolves something the candles do not actually say**. So most of
what follows drives the module toward a wrong answer and requires `AMBIGUOUS`:
a missing 15m span, a partial cover, two levels past the open, a ladder built
upside down, and a finer series that disagrees with its parent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.snapshotting import TradeDirection
from fmis.swing_lab.intrabar import (
    AmbiguityLedger,
    BarLadder,
    TouchKind,
    TouchLevel,
    bars_within,
    first_touch,
)
from fmis.swing_lab.models import SwingLabError

_UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=_UTC)
LONG = TradeDirection.LONG
SHORT = TradeDirection.SHORT

STOP = TouchLevel(name="stop", price=Decimal("90"), favourable=False)
TARGET = TouchLevel(name="target", price=Decimal("110"), favourable=True)


def _bar(
    interval: str, offset: timedelta, o: str, h: str, low: str, c: str,
    *, symbol: str = "BTCUSDT",
) -> PriceBar:
    return PriceBar(
        symbol=symbol, interval=interval, open_time=T0 + offset,
        open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(c),
    )


def _hours(count: float) -> timedelta:
    return timedelta(hours=count)


# --------------------------------------------------------------- ordering ---


def test_one_level_in_one_bar_resolves_without_any_ladder() -> None:
    """The common case must not consult a ladder at all."""
    bar = _bar("4h", _hours(0), "100", "112", "99", "111")
    touch = first_touch([bar], side=LONG, levels=(STOP, TARGET))
    assert touch.kind is TouchKind.RESOLVED
    assert touch.level is TARGET
    assert touch.fill_price == Decimal("110")
    assert touch.descents == 0


def test_a_bar_reaching_neither_level_reports_none_and_the_walk_continues() -> None:
    quiet = _bar("4h", _hours(0), "100", "105", "95", "101")
    hit = _bar("4h", _hours(4), "101", "111", "100", "110")
    touch = first_touch([quiet, hit], side=LONG, levels=(STOP, TARGET))
    assert touch.bar is hit


def test_a_walk_over_bars_reaching_nothing_reports_none() -> None:
    quiet = _bar("4h", _hours(0), "100", "105", "95", "101")
    touch = first_touch([quiet], side=LONG, levels=(STOP, TARGET))
    assert touch.kind is TouchKind.NONE
    assert touch.level is None


def test_both_levels_in_one_bar_is_ambiguous_without_a_ladder() -> None:
    """BX's refusal, reproduced. This is the state the module exists to improve on."""
    bar = _bar("4h", _hours(0), "100", "112", "88", "100")
    touch = first_touch([bar], side=LONG, levels=(STOP, TARGET))
    assert touch.kind is TouchKind.AMBIGUOUS
    assert touch.level is None


def test_a_1h_ladder_resolves_a_4h_ambiguity() -> None:
    """The milestone's §8 claim, in one test: real candles, real ordering."""
    coarse = _bar("4h", _hours(0), "100", "112", "88", "100")
    fine = (
        _bar("1h", _hours(0), "100", "104", "99", "103"),
        _bar("1h", _hours(1), "103", "112", "102", "111"),   # target first
        _bar("1h", _hours(2), "111", "111", "88", "90"),     # stop afterwards
        _bar("1h", _hours(3), "90", "100", "89", "100"),
    )
    ladder = BarLadder("BTCUSDT", (("4h", (coarse,)), ("1h", fine)))
    touch = first_touch([coarse], side=LONG, levels=(STOP, TARGET), ladder=ladder)
    assert touch.kind is TouchKind.RESOLVED
    assert touch.level is TARGET
    assert touch.interval == "1h"
    assert touch.descents == 1


def test_the_ladder_can_reverse_the_naive_reading() -> None:
    """Same coarse bar, opposite 1H path, opposite answer. The evidence decides."""
    coarse = _bar("4h", _hours(0), "100", "112", "88", "100")
    fine = (
        _bar("1h", _hours(0), "100", "101", "88", "89"),     # stop first
        _bar("1h", _hours(1), "89", "95", "88", "94"),
        _bar("1h", _hours(2), "94", "112", "93", "111"),
        _bar("1h", _hours(3), "111", "111", "99", "100"),
    )
    ladder = BarLadder("BTCUSDT", (("4h", (coarse,)), ("1h", fine)))
    touch = first_touch([coarse], side=LONG, levels=(STOP, TARGET), ladder=ladder)
    assert touch.level is STOP


def test_a_1h_bar_holding_both_descends_to_15m() -> None:
    coarse = _bar("4h", _hours(0), "100", "112", "88", "100")
    fine = tuple(
        _bar("1h", _hours(index), "100", "112", "88", "100") if index == 0
        else _bar("1h", _hours(index), "100", "101", "99", "100")
        for index in range(4)
    )
    finest = tuple(
        _bar("15m", timedelta(minutes=15 * index), *values)
        for index, values in enumerate(
            [
                ("100", "104", "99", "103"),
                ("103", "112", "102", "111"),   # target
                ("111", "111", "88", "90"),     # stop
                ("90", "100", "89", "100"),
            ]
        )
    )
    ladder = BarLadder(
        "BTCUSDT", (("4h", (coarse,)), ("1h", fine), ("15m", finest))
    )
    touch = first_touch([coarse], side=LONG, levels=(STOP, TARGET), ladder=ladder)
    assert touch.level is TARGET
    assert touch.interval == "15m"
    assert touch.descents == 2


def test_a_short_trade_reads_its_levels_the_other_way_round() -> None:
    """A side-swap is the mutation that hides best; it is tested directly."""
    stop = TouchLevel(name="stop", price=Decimal("110"), favourable=False)
    target = TouchLevel(name="target", price=Decimal("90"), favourable=True)
    bar = _bar("4h", _hours(0), "100", "101", "88", "89")
    touch = first_touch([bar], side=SHORT, levels=(stop, target))
    assert touch.level is target
    assert touch.fill_price == Decimal("90")


# --------------------------------------------------------------- refusals ---


def test_two_levels_past_the_open_stay_ambiguous_even_with_a_ladder() -> None:
    """A bar open past both levels cannot be ordered at ANY resolution.

    Descending would find the same fact one rung down, so the refusal is
    immediate rather than after a pointless fetch — and it is a refusal, not a
    guess at which of the two the open was "more" past.
    """
    coarse = _bar("4h", _hours(0), "95", "112", "88", "100")
    # Two protective levels, both already behind the bar's opening price: a
    # trailing stop at 99 and a wider one at 96. The open is past both at the
    # same instant, so nothing orders them.
    stop = TouchLevel(name="stop", price=Decimal("99"), favourable=False)
    target = TouchLevel(name="wider_stop", price=Decimal("96"), favourable=False)
    fine = tuple(_bar("1h", _hours(i), "95", "112", "88", "100") for i in range(4))
    ladder = BarLadder("BTCUSDT", (("4h", (coarse,)), ("1h", fine)))
    touch = first_touch([coarse], side=LONG, levels=(stop, target), ladder=ladder)
    assert touch.kind is TouchKind.AMBIGUOUS


def test_exactly_one_level_past_the_open_resolves_without_descending() -> None:
    """The one piece of intrabar ordering four prices genuinely contain."""
    bar = _bar("4h", _hours(0), "88", "112", "87", "100")
    touch = first_touch([bar], side=LONG, levels=(STOP, TARGET))
    assert touch.kind is TouchKind.RESOLVED
    assert touch.level is STOP
    assert touch.gapped is True
    assert touch.fill_price == Decimal("88")   # the open, not the level
    assert touch.descents == 0


def test_a_partial_15m_cover_refuses_to_descend() -> None:
    """Three of four finer bars could place the first touch in the missing one."""
    coarse = _bar("4h", _hours(0), "100", "112", "88", "100")
    fine = (
        _bar("1h", _hours(0), "100", "104", "99", "103"),
        _bar("1h", _hours(1), "103", "112", "102", "111"),
        _bar("1h", _hours(2), "111", "111", "88", "90"),
    )   # only three hours of a four-hour span
    ladder = BarLadder("BTCUSDT", (("4h", (coarse,)), ("1h", fine)))
    touch = first_touch([coarse], side=LONG, levels=(STOP, TARGET), ladder=ladder)
    assert touch.kind is TouchKind.AMBIGUOUS


def test_a_missing_span_refuses_to_descend() -> None:
    coarse = _bar("4h", _hours(8), "100", "112", "88", "100")
    elsewhere = tuple(_bar("1h", _hours(i), "100", "101", "99", "100") for i in range(4))
    ladder = BarLadder("BTCUSDT", (("4h", (coarse,)), ("1h", elsewhere)))
    assert first_touch(
        [coarse], side=LONG, levels=(STOP, TARGET), ladder=ladder
    ).kind is TouchKind.AMBIGUOUS


def test_the_bottom_of_the_ladder_refuses_rather_than_guessing() -> None:
    coarse = _bar("4h", _hours(0), "100", "112", "88", "100")
    fine = tuple(_bar("1h", _hours(i), "100", "112", "88", "100") for i in range(4))
    ladder = BarLadder("BTCUSDT", (("4h", (coarse,)), ("1h", fine)))
    assert first_touch(
        [coarse], side=LONG, levels=(STOP, TARGET), ladder=ladder
    ).kind is TouchKind.AMBIGUOUS


def test_a_finer_series_disagreeing_with_its_parent_is_refused() -> None:
    """A provider fault must fail loudly, never be smoothed into a resolution."""
    coarse = _bar("4h", _hours(0), "100", "112", "88", "100")
    fine = tuple(_bar("1h", _hours(i), "100", "101", "99", "100") for i in range(4))
    ladder = BarLadder("BTCUSDT", (("4h", (coarse,)), ("1h", fine)))
    with pytest.raises(SwingLabError, match="the two series disagree"):
        first_touch([coarse], side=LONG, levels=(STOP, TARGET), ladder=ladder)


# ----------------------------------------------------------------- ladder ---


def test_a_ladder_must_be_ordered_coarsest_first() -> None:
    """Reversed, a 'descent' would reach a LONGER bar and manufacture ambiguity."""
    with pytest.raises(SwingLabError, match="coarsest-first"):
        BarLadder("BTCUSDT", (("1h", ()), ("4h", ())))


def test_a_ladder_refuses_two_rungs_of_the_same_interval() -> None:
    with pytest.raises(SwingLabError, match="coarsest-first"):
        BarLadder("BTCUSDT", (("4h", ()), ("4h", ())))


def test_a_ladder_refuses_a_bar_from_another_symbol() -> None:
    stray = _bar("1h", _hours(0), "1", "2", "1", "2", symbol="ETHUSDT")
    with pytest.raises(SwingLabError, match="holds a ETHUSDT bar"):
        BarLadder("BTCUSDT", (("4h", ()), ("1h", (stray,))))


def test_a_ladder_needs_at_least_one_rung() -> None:
    with pytest.raises(SwingLabError, match="at least one rung"):
        BarLadder("BTCUSDT", ())


def test_the_bottom_rung_has_nothing_finer() -> None:
    ladder = BarLadder("BTCUSDT", (("4h", ()), ("1h", ())))
    assert ladder.finer_than("1h") is None
    assert ladder.finer_than("4h")[0] == "1h"


def test_asking_for_an_absent_rung_names_the_ones_present() -> None:
    ladder = BarLadder("BTCUSDT", (("4h", ()), ("1h", ())))
    with pytest.raises(SwingLabError, match="holds no '15m' rung"):
        ladder.finer_than("15m")


# ------------------------------------------------------------ bars_within ---


def test_bars_within_is_half_open() -> None:
    bars = tuple(_bar("1h", _hours(index), "100", "101", "99", "100") for index in range(6))
    window = bars_within(bars, T0 + _hours(1), T0 + _hours(3))
    assert [bar.open_time for bar in window] == [T0 + _hours(1), T0 + _hours(2)]


def test_bars_within_returns_nothing_for_an_empty_span() -> None:
    bars = tuple(_bar("1h", _hours(index), "100", "101", "99", "100") for index in range(3))
    assert bars_within(bars, T0 + _hours(9), T0 + _hours(9)) == ()


def test_bars_within_refuses_an_inverted_span() -> None:
    with pytest.raises(SwingLabError, match="must not precede"):
        bars_within((), T0 + _hours(3), T0)


def test_an_unordered_rung_is_refused_at_ladder_construction() -> None:
    """A binary search over unsorted rows returns a wrong slice, silently.

    The check lives on `BarLadder` rather than inside `bars_within`: it is the
    ladder that owns the series, the cost is paid once instead of once per
    search, and re-validating on every call made the documented bisect
    decorative — an O(n) scan in front of an O(log n) search, run thousands of
    times over ~26k rows.
    """
    out_of_order = (
        _bar("1h", _hours(3), "100", "101", "99", "100"),
        _bar("1h", _hours(1), "100", "101", "99", "100"),
    )
    with pytest.raises(SwingLabError, match="not ordered by open_time"):
        BarLadder("BTCUSDT", (("4h", ()), ("1h", out_of_order)))


def test_bars_within_is_a_real_bisect_and_not_a_scan() -> None:
    """Guards the fix: no per-call key list, no per-call ordering scan."""
    import inspect

    from fmis.swing_lab import intrabar

    body = inspect.getsource(intrabar.bars_within)
    assert "bisect_left" in body and "bisect_right" in body
    assert "for bar in bars" not in body      # no materialised key list
    assert "zip(times" not in body            # no pairwise ordering scan


# ------------------------------------------------------------- validation ---


def test_levels_must_be_distinctly_named() -> None:
    twin = TouchLevel(name="stop", price=Decimal("95"), favourable=False)
    with pytest.raises(SwingLabError, match="must be distinct"):
        first_touch([], side=LONG, levels=(STOP, twin))


def test_at_least_one_level_must_be_watched() -> None:
    with pytest.raises(SwingLabError, match="at least one level"):
        first_touch([], side=LONG, levels=())


def test_a_touch_level_refuses_a_non_positive_price() -> None:
    with pytest.raises(SwingLabError, match="must be positive"):
        TouchLevel(name="stop", price=Decimal("0"), favourable=False)


def test_a_touch_level_refuses_a_float_price() -> None:
    """Float prices are how a comparison starts failing on the 17th decimal."""
    with pytest.raises(TypeError, match="must be a Decimal"):
        TouchLevel(name="stop", price=90.0, favourable=False)


# --------------------------------------------------------------- bookkeeping ---


def test_the_ledger_counts_only_events_that_needed_the_ladder() -> None:
    ledger = AmbiguityLedger()
    ledger.record(
        first_touch(
            [_bar("4h", _hours(0), "100", "112", "99", "111")],
            side=LONG, levels=(STOP, TARGET),
        )
    )
    assert ledger.encountered == 0

    coarse = _bar("4h", _hours(0), "100", "112", "88", "100")
    fine = (
        _bar("1h", _hours(0), "100", "104", "99", "103"),
        _bar("1h", _hours(1), "103", "112", "102", "111"),
        _bar("1h", _hours(2), "111", "111", "88", "90"),
        _bar("1h", _hours(3), "90", "100", "89", "100"),
    )
    ledger.record(
        first_touch(
            [coarse], side=LONG, levels=(STOP, TARGET),
            ladder=BarLadder("BTCUSDT", (("4h", (coarse,)), ("1h", fine))),
        )
    )
    assert ledger.encountered == 1
    assert ledger.resolved == 1
    assert ledger.by_interval == {"1h": 1}

    ledger.record(first_touch([coarse], side=LONG, levels=(STOP, TARGET)))
    assert ledger.unresolved == 1
    assert ledger.payload() == {
        "encountered": 2, "resolved": 1, "unresolved": 1,
        "resolved_by_interval": {"1h": 1},
    }
