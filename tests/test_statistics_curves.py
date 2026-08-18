"""The equity curve, the drawdown curve, and the breakdowns.

The drawdown walk is the most intricate arithmetic in the milestone, so every
case is a hand-computed sequence: recovery, non-recovery, a decline that begins
before the curve ever rose, and the pair of figures that must describe **one**
episode rather than two.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from fmis.accounts import Book
from fmis.money import AssetCode, Money
from fmis.portfolio_risk import UNCLASSIFIED
from fmis.provenance import Absent
from fmis.snapshotting import TradeDirection
from fmis.statistics import (
    DIMENSION_NAMES,
    DIMENSIONS,
    Breakdown,
    LifecyclePhase,
    SamplePolicy,
    StatSource,
    StatisticsRefusedError,
    as_percentage,
    cut_by,
    breakdown_set,
    drawdown_curve,
    equity_curve,
)
from statistics_helpers import at, money, stat

USDT = AssetCode("USDT")
LOW = SamplePolicy(minimum_sample=1)
NONE = Absent("no starting equity was supplied")


def curve(*steps: tuple[str, int], starting: Money | Absent = NONE):
    """Build a curve from `(net, close-day)` pairs, in the order given."""
    trades = tuple(
        stat(f"t{index}", net=net, closed_day=day, opened_day=0)
        for index, (net, day) in enumerate(steps)
    )
    return equity_curve(trades, quote_asset=USDT, starting_equity=starting)


# --------------------------------------------------------------------------
# Equity
# --------------------------------------------------------------------------


def test_the_curve_steps_once_per_closed_trade_in_close_order() -> None:
    built = curve(("100", 3), ("-40", 1), ("10", 2))
    assert [point.delta.text for point in built.points] == ["-40", "10", "100"]
    assert [point.cumulative.text for point in built.points] == ["-40", "-30", "70"]


def test_an_open_trade_never_enters_the_curve_and_is_counted_separately() -> None:
    """Its contribution needs a mark, is unrealized and reverses. Including it
    would make yesterday's curve change today."""
    trades = (
        stat("a", net="100", closed_day=1),
        stat("b", phase=LifecyclePhase.OPEN, closed_day=None, net=None),
    )
    built = equity_curve(trades, quote_asset=USDT, starting_equity=NONE)
    assert len(built.points) == 1
    assert built.open_trades == 1


def test_a_closed_trade_with_no_stateable_result_is_excluded_and_named() -> None:
    """A zero step would draw a flat segment where the truth is unmeasured."""
    trades = (stat("a", net="100", closed_day=1), stat("b", net=None, closed_day=2))
    built = equity_curve(trades, quote_asset=USDT, starting_equity=NONE)
    assert len(built.points) == 1
    assert any("t" not in reason or "b" in reason for reason in built.excluded)
    assert built.excluded


def test_two_trades_closing_in_one_instant_order_stably() -> None:
    """Otherwise the peak, and therefore the drawdown, differ between runs."""
    trades = (
        stat("zzz", net="10", closed_day=1),
        stat("aaa", net="-10", closed_day=1),
    )
    first = equity_curve(trades, quote_asset=USDT, starting_equity=NONE)
    second = equity_curve(tuple(reversed(trades)), quote_asset=USDT, starting_equity=NONE)
    assert [point.trade_ref for point in first.points] == ["aaa", "zzz"]
    assert [point.trade_ref for point in first.points] == [
        point.trade_ref for point in second.points
    ]


def test_without_a_baseline_the_curve_is_cumulative_profit_and_loss() -> None:
    built = curve(("100", 1))
    assert built.realized == money("100")
    assert isinstance(built.current_equity, Absent)


def test_with_a_baseline_the_curve_becomes_an_equity_curve() -> None:
    built = curve(("100", 1), starting=money("1000"))
    assert built.current_equity == money("1100")
    assert built.points[0].equity == money("1100")


def test_a_baseline_in_another_asset_is_refused() -> None:
    with pytest.raises(StatisticsRefusedError, match="cannot baseline"):
        equity_curve(
            (), quote_asset=USDT, starting_equity=Money(Decimal(1), AssetCode("BTC"))
        )


def test_an_empty_curve_realizes_an_explicit_zero_in_its_asset() -> None:
    """No closed trade genuinely means no realized profit or loss."""
    built = equity_curve((), quote_asset=USDT, starting_equity=NONE)
    assert built.is_empty
    assert built.realized == Money.zero(USDT)
    assert built.peak_equity == Money.zero(USDT)


def test_trades_settling_in_another_asset_are_simply_not_on_this_curve() -> None:
    trades = (stat("a", net="100", closed_day=1), stat("b", symbol="SOL", quote="BTC"))
    built = equity_curve(trades, quote_asset=USDT, starting_equity=NONE)
    assert len(built.points) == 1


def test_a_replay_truncates_rather_than_recomputes() -> None:
    built = curve(("100", 1), ("-40", 2), ("10", 3))
    replayed = built.as_of(at(2))
    assert [point.cumulative.text for point in replayed.points] == ["100", "60"]
    assert any("not part of this replay" in reason for reason in replayed.excluded)


def test_a_replay_that_drops_nothing_adds_no_note() -> None:
    built = curve(("100", 1))
    assert built.as_of(at(9)).excluded == built.excluded


def test_an_out_of_order_curve_is_refused_at_construction() -> None:
    """Constructed directly: the builder sorts, and this is what makes that a
    property rather than a hope."""
    from fmis.statistics import EquityCurve, EquityPoint

    points = (
        EquityPoint(at=at(5), trade_ref="late", delta=money("1"),
                    cumulative=money("1"), equity=NONE),
        EquityPoint(at=at(1), trade_ref="early", delta=money("1"),
                    cumulative=money("2"), equity=NONE),
    )
    with pytest.raises(StatisticsRefusedError, match="oldest first"):
        EquityCurve(quote_asset=USDT, points=points, starting_equity=NONE,
                    excluded=(), open_trades=0)


def test_a_step_and_a_curve_in_two_assets_cannot_be_one_point() -> None:
    from fmis.statistics import EquityPoint

    with pytest.raises(StatisticsRefusedError, match="cannot move a curve"):
        EquityPoint(
            at=at(1), trade_ref="x",
            delta=Money(Decimal(1), AssetCode("BTC")),
            cumulative=money("1"), equity=NONE,
        )


def test_a_percentage_names_which_baseline_it_lacked() -> None:
    absent = as_percentage(money("10"), NONE)
    assert "records the owner's opening capital nowhere" in absent.reason
    assert isinstance(as_percentage(money("10"), money("0")), Absent)
    assert as_percentage(money("10"), money("200")) == Decimal("0.05")


# --------------------------------------------------------------------------
# Drawdown
# --------------------------------------------------------------------------


def test_a_curve_at_its_high_water_mark_has_a_drawdown_of_exactly_zero() -> None:
    """The one place in this package where a zero is a measurement."""
    reading = drawdown_curve(curve(("100", 1), ("50", 2)), LOW)
    assert reading.current == Money.zero(USDT)
    assert not reading.in_drawdown
    assert isinstance(reading.ongoing, Absent)


def test_a_recovered_decline_is_one_period_with_its_depth_and_duration() -> None:
    # +100 (peak) → -60 (trough at 40) → +80 (recovers to 120, above 100)
    reading = drawdown_curve(curve(("100", 1), ("-60", 3), ("80", 6)), LOW)
    assert len(reading.periods) == 1
    period = reading.periods[0]
    assert period.depth == money("60")
    assert not period.is_ongoing
    assert period.duration == timedelta(days=5)
    assert period.trades == 2
    assert reading.recoveries == (period,)


def test_a_decline_that_has_not_recovered_is_ongoing_not_a_finished_episode() -> None:
    """The most flattering error available here: it turns *"I am still down"*
    into a completed episode with a duration."""
    reading = drawdown_curve(curve(("100", 1), ("-60", 3)), LOW)
    assert len(reading.periods) == 1
    assert reading.periods[0].is_ongoing
    assert reading.recoveries == ()
    assert reading.current == money("60")
    assert not isinstance(reading.ongoing, Absent)


def test_a_curve_that_only_ever_fell_records_the_decline_from_the_origin() -> None:
    """`ST-4` extended to time: the peak it fell from is the account's opening
    level, which this system records neither the value nor the instant of."""
    reading = drawdown_curve(curve(("-40", 1), ("-30", 2)), LOW)
    assert len(reading.periods) == 1
    assert reading.periods[0].depth == money("70")
    assert reading.current == money("70")


def test_a_recovery_to_exactly_the_old_high_counts_as_recovered() -> None:
    """Requiring it to exceed the high would leave every flat recovery
    permanently ongoing."""
    reading = drawdown_curve(curve(("100", 1), ("-30", 2), ("30", 3)), LOW)
    assert not reading.periods[0].is_ongoing


def test_two_separate_declines_are_two_periods() -> None:
    reading = drawdown_curve(
        curve(("100", 1), ("-50", 2), ("60", 3), ("-20", 4)), LOW
    )
    assert len(reading.periods) == 2
    assert [period.depth.text for period in reading.periods] == ["50", "20"]
    assert reading.average == money("35")


def test_the_maximum_and_its_percentage_describe_one_episode() -> None:
    """Ranking by percentage separately can select a different period, and a
    page showing one episode's depth beside another's percentage reads as a
    single fact."""
    reading = drawdown_curve(
        curve(("100", 1), ("-50", 2), ("60", 3), ("-20", 4), starting=money("1000")),
        LOW,
    )
    assert reading.maximum == reading.deepest.depth
    assert reading.maximum_percent == reading.deepest.depth_percent


def test_the_percentage_denominator_is_the_equity_at_the_peak() -> None:
    """A 50 decline from 1100 is not the same drawdown as 50 from 1000."""
    reading = drawdown_curve(
        curve(("100", 1), ("-50", 2), starting=money("1000")), LOW
    )
    assert reading.periods[0].depth_percent == Decimal(50) / Decimal(1100)


def test_without_a_baseline_the_shape_survives_and_the_percentage_does_not() -> None:
    with_base = drawdown_curve(curve(("100", 1), ("-50", 2), starting=money("1000")), LOW)
    without = drawdown_curve(curve(("100", 1), ("-50", 2)), LOW)
    assert with_base.maximum == without.maximum == money("50")
    assert isinstance(without.maximum_percent, Absent)
    assert isinstance(without.current_percent, Absent)


def test_the_longest_and_the_deepest_are_separate_questions() -> None:
    # A long shallow decline, then a short deep one.
    reading = drawdown_curve(
        curve(("100", 1), ("-10", 2), ("10", 40), ("-90", 41), ("90", 42)), LOW
    )
    assert reading.longest is not reading.deepest
    assert reading.deepest.depth == money("90")
    assert reading.longest.duration > reading.deepest.duration


def test_an_empty_curve_has_no_periods_and_absent_extremes() -> None:
    reading = drawdown_curve(equity_curve((), quote_asset=USDT, starting_equity=NONE), LOW)
    assert reading.periods == ()
    assert isinstance(reading.maximum, Absent)
    assert isinstance(reading.longest, Absent)
    assert isinstance(reading.deepest, Absent)
    assert reading.current == Money.zero(USDT)


def test_a_drawdown_depth_is_never_signed() -> None:
    from fmis.statistics import DrawdownPeriod

    with pytest.raises(StatisticsRefusedError, match="positive magnitude"):
        DrawdownPeriod(
            peak_at=at(1), trough_at=at(2), recovered_at=Absent("no"),
            peak=money("10"), trough=money("20"), depth=money("-10"),
            depth_percent=Absent("no"), trades=1,
        )


def test_a_period_cannot_recover_before_it_bottoms_or_bottom_before_its_peak() -> None:
    from fmis.statistics import DrawdownPeriod

    with pytest.raises(StatisticsRefusedError, match="recover before"):
        DrawdownPeriod(
            peak_at=at(1), trough_at=at(5), recovered_at=at(3),
            peak=money("10"), trough=money("5"), depth=money("5"),
            depth_percent=Absent("no"), trades=1,
        )
    with pytest.raises(StatisticsRefusedError, match="precede the peak"):
        DrawdownPeriod(
            peak_at=at(5), trough_at=at(1), recovered_at=Absent("no"),
            peak=money("10"), trough=money("5"), depth=money("5"),
            depth_percent=Absent("no"), trades=1,
        )


def test_the_curve_and_the_drawdown_refuse_wrong_types() -> None:
    with pytest.raises(TypeError, match="EquityCurve"):
        drawdown_curve("not a curve", LOW)
    with pytest.raises(TypeError, match="SamplePolicy"):
        drawdown_curve(equity_curve((), quote_asset=USDT, starting_equity=NONE), "no")


# --------------------------------------------------------------------------
# Breakdowns
# --------------------------------------------------------------------------


def test_every_declared_dimension_produces_a_cut() -> None:
    trades = (stat("a"), stat("b", symbol="ETH"))
    cuts = breakdown_set(trades, LOW, quote_asset=USDT)
    assert len(cuts.breakdowns) == len(DIMENSIONS) + 1  # +1 for regime
    assert {entry.dimension for entry in cuts.breakdowns} == set(DIMENSION_NAMES)


def test_the_cells_of_a_dimension_partition_the_corpus() -> None:
    trades = (stat("a", symbol="BTC"), stat("b", symbol="ETH"), stat("c", symbol="BTC"))
    cut = cut_by(trades, "symbol", lambda s: s.market.base_asset.code, LOW,
                       quote_asset=USDT)
    assert sum(cell.size for cell in cut.cells) == len(trades)
    assert {cell.key for cell in cut.cells} == {"BTC", "ETH"}


def test_a_trade_the_dimension_cannot_classify_becomes_an_unclassified_cell() -> None:
    """Dropping it would make the classified minority speak for everything."""
    trades = (stat("a", setup_type="breakout"), stat("b", setup_type=None))
    cuts = breakdown_set(trades, LOW, quote_asset=USDT)
    setup = cuts.by_dimension("setup")
    assert {cell.key for cell in setup.cells} == {"breakout", UNCLASSIFIED}
    assert sum(cell.size for cell in setup.cells) == 2


def test_unclassified_sorts_last_so_a_real_key_is_never_buried_under_it() -> None:
    trades = (stat("a", setup_type=None), stat("b", setup_type="zzz"),
              stat("c", setup_type="aaa"))
    cut = breakdown_set(trades, LOW, quote_asset=USDT).by_dimension("setup")
    assert [cell.key for cell in cut.cells] == ["aaa", "zzz", UNCLASSIFIED]


def test_books_and_sources_follow_their_declared_order_not_the_alphabet() -> None:
    trades = (stat("a", book=Book.PAPER), stat("b", book=Book.INVESTING))
    cut = breakdown_set(trades, LOW, quote_asset=USDT).by_dimension("book")
    assert [cell.key for cell in cut.cells] == ["investing", "paper"]


def test_each_cell_carries_its_own_sample_floor() -> None:
    """What makes a breakdown safe to look at: cells that survive slicing are
    the ones with enough trades behind them, and the rest say so."""
    trades = tuple(stat(f"t{i}", symbol="BTC" if i else "ETH") for i in range(6))
    cut = cut_by(trades, "symbol", lambda s: s.market.base_asset.code,
                       SamplePolicy(minimum_sample=3), quote_asset=USDT)
    small = cut.cell("ETH")
    large = cut.cell("BTC")
    assert isinstance(small.performance.win_rate, Absent)
    assert not isinstance(large.performance.win_rate, Absent)


def test_the_number_of_cells_examined_is_carried_on_the_set() -> None:
    """`TRADER_WORKSPACE` §3.4.12's mechanism — the defence is this number, not
    a paragraph."""
    trades = (stat("a", symbol="BTC"), stat("b", symbol="ETH"))
    cuts = breakdown_set(trades, LOW, quote_asset=USDT)
    assert cuts.cells_examined == sum(entry.size for entry in cuts.breakdowns)
    assert cuts.cells_examined > len(cuts.breakdowns)
    assert "No multiplicity correction" in cuts.note


def test_the_regime_dimension_used_is_named_on_the_result() -> None:
    """A page cannot show *"by regime"* without saying which regime."""
    trades = (stat("a", regime_states={"trend": "up", "volatility": "high"}),)
    cuts = breakdown_set(trades, LOW, quote_asset=USDT, regime_dimension="volatility")
    assert cuts.regime_dimension == "volatility"
    assert [cell.key for cell in cuts.by_dimension("regime").cells] == ["high"]


def test_a_trade_with_no_snapshot_lands_in_the_unclassified_regime_cell() -> None:
    cuts = breakdown_set((stat("a"),), LOW, quote_asset=USDT)
    assert [cell.key for cell in cuts.by_dimension("regime").cells] == [UNCLASSIFIED]


def test_calendar_cells_come_from_the_close_and_not_the_commitment() -> None:
    """Bucketing a running trade by its commitment would put it into a
    completed month's performance."""
    trades = (
        stat("a", committed_day=0, closed_day=40),
        stat("b", phase=LifecyclePhase.OPEN, committed_day=0, closed_day=None, net=None),
    )
    cuts = breakdown_set(trades, LOW, quote_asset=USDT)
    keys = {cell.key for cell in cuts.by_dimension("month").cells}
    assert UNCLASSIFIED in keys
    assert "2026-02" in keys


def test_quarter_and_year_cells_are_derived_from_the_same_instant() -> None:
    cuts = breakdown_set((stat("a", closed_day=100),), LOW, quote_asset=USDT)
    assert [c.key for c in cuts.by_dimension("quarter").cells] == ["2026-Q2"]
    assert [c.key for c in cuts.by_dimension("year").cells] == ["2026"]


def test_an_unknown_dimension_is_an_absence_naming_the_choices() -> None:
    cuts = breakdown_set((stat("a"),), LOW, quote_asset=USDT)
    absent = cuts.by_dimension("mood")
    assert isinstance(absent, Absent)
    assert "symbol" in absent.reason


def test_an_absent_cell_says_no_trade_falls_under_it() -> None:
    cut = cut_by((stat("a"),), "symbol", lambda s: "BTC", LOW, quote_asset=USDT)
    assert isinstance(cut.cell("ETH"), Absent)


def test_a_breakdown_with_a_duplicate_cell_key_is_refused() -> None:
    from fmis.statistics import BreakdownCell
    from fmis.statistics.general import general_statistics
    from fmis.statistics.performance import performance_statistics

    cell = BreakdownCell(
        key="same",
        general=general_statistics((), LOW),
        performance=performance_statistics((), LOW, quote_asset=USDT),
    )
    with pytest.raises(TypeError, match="duplicate cell key"):
        Breakdown(dimension="symbol", cells=(cell, cell), quote_asset=USDT)
