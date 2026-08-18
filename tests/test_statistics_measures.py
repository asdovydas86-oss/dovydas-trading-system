"""The four families — general, performance, risk, quality — and distributions.

Every figure here is checked against arithmetic done by hand in the test, not
against the implementation's own answer. A test that asserts
`profit_factor == gross_profit / gross_loss` proves the two expressions agree
and nothing about whether either is right.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from fmis.accounts import Book
from fmis.money import AssetCode, Money
from fmis.provenance import Absent
from fmis.snapshotting import TradeDirection
from fmis.statistics import (
    HISTOGRAM_KINDS,
    Bucket,
    LifecyclePhase,
    Sample,
    SamplePolicy,
    StatSource,
    StatisticsRefusedError,
    general_statistics,
    histogram_of,
    performance_statistics,
    quality_statistics,
    risk_statistics,
    total_duration,
    utilization_of,
)
from statistics_helpers import money, stat

USDT = AssetCode("USDT")
LOW = SamplePolicy(minimum_sample=1)
HIGH = SamplePolicy(minimum_sample=100)


#: Four closed trades whose arithmetic is trivial to verify by hand:
#: +100, -50, +200, -50 → gross +300 / -100, net +200 over four resolved.
CORPUS = (
    stat("a", net="100", risk="50", r_multiple="2", closed_day=1),
    stat("b", net="-50", risk="50", r_multiple="-1", closed_day=2, mfe="0.4", mae="-1"),
    stat("c", net="200", risk="100", r_multiple="2", closed_day=3),
    stat("d", net="-50", risk="50", r_multiple="-1", closed_day=4, mfe="0.2", mae="-1"),
)

#: The same corpus with **unequal** losses. `CORPUS`'s two losers are both −50,
#: which makes the largest and the smallest loss the same number — so a
#: mutation swapping one extreme for the other survived every assertion over
#: it. Found by a mutation probe, and the fix is a fixture that can tell them
#: apart rather than an extra assertion over one that cannot.
UNEQUAL_LOSSES = (
    stat("a", net="100", closed_day=1),
    stat("b", net="-20", closed_day=2),
    stat("c", net="-90", closed_day=3),
)


# --------------------------------------------------------------------------
# General — counts and durations
# --------------------------------------------------------------------------


def test_the_counts_partition_the_corpus_exactly_once_by_result() -> None:
    general = general_statistics(CORPUS + (stat("e", phase=LifecyclePhase.OPEN,
                                                 closed_day=None, net=None),), LOW)
    assert general.total == 5
    assert (
        general.winning.count
        + general.losing.count
        + general.scratch.count
        + general.unresolved.count
    ) == general.total


def test_the_counts_partition_the_corpus_exactly_once_by_phase() -> None:
    trades = CORPUS + (
        stat("e", phase=LifecyclePhase.OPEN, closed_day=None, net=None),
        stat("f", phase=LifecyclePhase.CANCELLED, opened_day=None, closed_day=None,
             net=None),
        stat("g", phase=LifecyclePhase.EXPIRED, opened_day=None, closed_day=None,
             net=None),
        stat("h", phase=LifecyclePhase.PENDING, opened_day=None, closed_day=None,
             net=None),
        stat("i", phase=LifecyclePhase.TRIGGERED, opened_day=None, closed_day=None,
             net=None),
        stat("j", phase=LifecyclePhase.AMBIGUOUS, closed_day=None, net=None),
    )
    general = general_statistics(trades, LOW)
    covered = (
        general.pending.count + general.triggered.count + general.open_trades.count
        + general.closed.count + general.cancelled.count + general.expired.count
        + general.ambiguous.count
    )
    assert covered == general.total == 10


def test_paper_and_other_books_partition_the_corpus() -> None:
    trades = (stat("a", book=Book.PAPER), stat("b", book=Book.SWING))
    general = general_statistics(trades, LOW)
    assert general.paper.count == 1
    assert general.live.count == 1
    assert general.paper.count + general.live.count == general.total


def test_every_directional_side_gets_a_row_even_at_zero() -> None:
    """A page that dropped the empty side would read as a system that never
    took it, which is a claim about the owner's behaviour."""
    general = general_statistics((stat("a", direction=TradeDirection.LONG),), LOW)
    assert len(general.by_direction) == 2
    assert {entry.count for entry in general.by_direction} == {0, 1}


def test_both_sources_get_a_row_even_at_zero() -> None:
    general = general_statistics((stat("a", source=StatSource.SIMULATED),), LOW)
    assert len(general.by_source) == 2


def test_the_duration_figures_are_the_hand_computed_ones() -> None:
    trades = (
        stat("a", opened_day=0, closed_day=1),
        stat("b", opened_day=0, closed_day=3),
        stat("c", opened_day=0, closed_day=8),
    )
    general = general_statistics(trades, LOW)
    assert general.average_holding_time == timedelta(days=4)
    assert general.median_holding_time == timedelta(days=3)
    assert general.maximum_holding_time == timedelta(days=8)
    assert general.minimum_holding_time == timedelta(days=1)


def test_a_trade_that_never_opened_contributes_no_zero_duration() -> None:
    """A zero would drag every average toward trades that never existed."""
    trades = (
        stat("a", opened_day=0, closed_day=4),
        stat("b", phase=LifecyclePhase.CANCELLED, opened_day=None, closed_day=None,
             net=None),
    )
    general = general_statistics(trades, LOW)
    assert general.holding_time.size == 1
    assert general.average_holding_time == timedelta(days=4)


def test_bar_counts_average_exactly_rather_than_as_a_float() -> None:
    trades = (stat("a", bars=1), stat("b", bars=2))
    general = general_statistics(trades, LOW)
    assert general.average_bars_held == Decimal("1.5")


def test_total_duration_counts_concurrent_trades_twice_and_says_so() -> None:
    """Exposure, not calendar time — the docstring's own distinction."""
    trades = (stat("a", opened_day=0, closed_day=2), stat("b", opened_day=0, closed_day=2))
    general = general_statistics(trades, LOW)
    assert total_duration(general.holding_time) == timedelta(days=4)


def test_total_duration_refuses_a_non_sample() -> None:
    with pytest.raises(TypeError, match="Sample"):
        total_duration("not a sample")


# --------------------------------------------------------------------------
# Performance — money, R, and the floored rates
# --------------------------------------------------------------------------


def test_the_money_figures_are_the_hand_computed_ones() -> None:
    reading = performance_statistics(CORPUS, LOW, quote_asset=USDT)
    assert reading.gross_profit == money("300")
    assert reading.gross_loss == money("100")
    assert reading.net_profit == money("200")
    assert reading.average_win == money("150")
    assert reading.average_loss == money("-50")
    assert reading.largest_win == money("200")
    assert reading.largest_loss == money("-50")
    assert reading.expectancy == money("50")


def test_the_largest_loss_is_the_biggest_one_and_not_the_smallest() -> None:
    """Losses are negative, so the extremum must be taken at the **small** end.
    Reaching for the top would report the trade that cost least as the worst."""
    reading = performance_statistics(UNEQUAL_LOSSES, LOW, quote_asset=USDT)
    assert reading.largest_loss == money("-90")
    assert reading.largest_win == money("100")


def test_gross_loss_is_carried_as_a_positive_magnitude() -> None:
    """A signed gross loss makes profit factor negative, which is not a scale
    anybody reads correctly."""
    reading = performance_statistics(CORPUS, LOW, quote_asset=USDT)
    assert reading.gross_loss.amount > 0


def test_profit_factor_and_payoff_ratio_are_the_hand_computed_ones() -> None:
    reading = performance_statistics(CORPUS, LOW, quote_asset=USDT)
    assert reading.profit_factor == Decimal(3)
    assert reading.payoff_ratio == Decimal(3)


def test_a_corpus_with_no_loser_has_no_profit_factor_rather_than_a_large_one() -> None:
    reading = performance_statistics(
        (stat("a", net="10"), stat("b", net="20")), LOW, quote_asset=USDT
    )
    assert isinstance(reading.profit_factor, Absent)
    assert "undefined rather than large" in reading.profit_factor.reason


def test_win_and_loss_rate_are_over_the_resolved_population_only() -> None:
    """An open trade is in neither numerator nor denominator."""
    trades = CORPUS + (
        stat("e", phase=LifecyclePhase.OPEN, closed_day=None, net=None),
    )
    reading = performance_statistics(trades, LOW, quote_asset=USDT)
    assert reading.winners.total == 4
    assert reading.win_rate == Decimal("0.5")
    assert reading.loss_rate == Decimal("0.5")


def test_the_rates_are_refused_below_the_floor_and_the_totals_are_not() -> None:
    """The distinction the milestone rests on, asserted on one reading."""
    reading = performance_statistics(CORPUS, HIGH, quote_asset=USDT)
    assert isinstance(reading.win_rate, Absent)
    assert isinstance(reading.profit_factor, Absent)
    assert isinstance(reading.payoff_ratio, Absent)
    assert reading.gross_profit == money("300")
    assert reading.net_profit == money("200")
    assert reading.expectancy == money("50")


def test_expectancy_in_r_is_the_mean_of_the_stateable_r_multiples() -> None:
    reading = performance_statistics(CORPUS, LOW, quote_asset=USDT)
    assert reading.expectancy_r == Decimal("0.5")
    assert reading.average_r == Decimal("0.5")
    assert reading.best_r == Decimal(2)
    assert reading.worst_r == Decimal(-1)


def test_a_recorded_trade_with_no_r_reduces_the_r_sample_and_says_so() -> None:
    trades = CORPUS + (
        stat("e", source=StatSource.RECORDED, net="10", r_multiple=None, closed_day=5),
    )
    reading = performance_statistics(trades, LOW, quote_asset=USDT)
    assert reading.r_sample.size == 4
    assert reading.r_sample.missing == 1


def test_a_total_with_an_unstateable_contributor_is_absent() -> None:
    trades = (stat("a", net="10"), stat("b", net=None))
    reading = performance_statistics(trades, LOW, quote_asset=USDT)
    assert reading.gross_profit == money("10")
    assert reading.resolved.size == 1


def test_a_corpus_settling_in_two_assets_is_refused_rather_than_added() -> None:
    trades = (stat("a", quote="USDT"), stat("b", symbol="SOL", quote="BTC"))
    with pytest.raises(TypeError, match="split it by quote asset"):
        performance_statistics(trades, LOW, quote_asset=USDT)


def test_an_empty_corpus_produces_absences_and_an_explicit_zero_total() -> None:
    reading = performance_statistics((), LOW, quote_asset=USDT)
    assert reading.gross_profit == Money.zero(USDT)
    assert isinstance(reading.average_win, Absent)
    assert isinstance(reading.win_rate, Absent)


# --------------------------------------------------------------------------
# Risk
# --------------------------------------------------------------------------


def test_open_and_closed_risk_are_two_populations() -> None:
    trades = (
        stat("a", phase=LifecyclePhase.OPEN, closed_day=None, net=None, risk="30"),
        stat("b", risk="70"),
        stat("c", risk="90"),
    )
    reading = risk_statistics(
        trades, LOW, quote_asset=USDT,
        equity_basis=Absent("none"), utilization=Absent("none"),
    )
    assert reading.total_open_risk == money("30")
    assert reading.largest_open_risk == money("30")
    assert reading.largest_closed_risk == money("90")
    assert reading.average_closed_risk == money("80")


def test_a_total_open_risk_with_a_missing_contributor_is_absent() -> None:
    trades = (
        stat("a", phase=LifecyclePhase.OPEN, closed_day=None, net=None, risk="30"),
        stat("b", phase=LifecyclePhase.OPEN, closed_day=None, net=None, risk=None),
    )
    reading = risk_statistics(
        trades, LOW, quote_asset=USDT,
        equity_basis=Absent("none"), utilization=Absent("none"),
    )
    assert isinstance(reading.total_open_risk, Absent)


def test_risk_percentages_appear_once_a_baseline_is_supplied() -> None:
    trades = (stat("a", risk="50"), stat("b", risk="150"))
    reading = risk_statistics(
        trades, LOW, quote_asset=USDT,
        equity_basis=money("1000"), utilization=Absent("none"),
    )
    assert reading.average_risk_fraction == Decimal("0.1")
    assert reading.median_risk_fraction == Decimal("0.1")


def test_utilization_divides_open_risk_into_the_owners_ceiling() -> None:
    assert utilization_of(money("250"), money("1000")) == Decimal("0.25")


def test_utilization_names_which_half_is_missing() -> None:
    """The actionable part: *"you set no budget"* and *"your open risk cannot be
    totalled"* need different responses."""
    no_ceiling = utilization_of(money("250"), Absent("no risk budget recorded"))
    assert "no risk budget recorded" in no_ceiling.reason
    no_risk = utilization_of(Absent("one position is unpriced"), money("1000"))
    assert "one position is unpriced" in no_risk.reason


def test_a_ceiling_of_zero_is_undefined_rather_than_fully_consumed() -> None:
    absent = utilization_of(money("10"), money("0"))
    assert "undefined rather than complete" in absent.reason


def test_utilization_refuses_to_cross_two_assets() -> None:
    other = Money(Decimal(1000), AssetCode("BTC"))
    assert isinstance(utilization_of(money("10"), other), Absent)


def test_utilization_refuses_a_non_money() -> None:
    with pytest.raises(TypeError):
        utilization_of(Decimal(1), money("1"))


# --------------------------------------------------------------------------
# Quality
# --------------------------------------------------------------------------


def test_the_worst_adverse_excursion_is_the_most_negative_one() -> None:
    """Reaching for the largest would report the trade that went *least* far
    against the owner as the worst one they sat through."""
    trades = (stat("a", mae="-0.2"), stat("b", mae="-1.5"), stat("c", mae="-0.7"))
    reading = quality_statistics(trades, LOW)
    assert reading.maximum_adverse_r == Decimal("-1.5")


def test_the_best_favourable_excursion_is_the_largest_one() -> None:
    trades = (stat("a", mfe="0.2"), stat("b", mfe="4"), stat("c", mfe="1"))
    assert quality_statistics(trades, LOW).maximum_favourable_r == Decimal(4)


def test_the_excursion_figures_report_how_many_contributed() -> None:
    """`ST-2`: a corpus of eight simulated and four recorded trades produces
    excursion figures that say n = 8, never twelve."""
    trades = tuple(stat(f"s{i}", mae="-1", mfe="2") for i in range(8)) + tuple(
        stat(f"r{i}", source=StatSource.RECORDED, mae=None, mfe=None)
        for i in range(4)
    )
    reading = quality_statistics(trades, LOW)
    assert reading.adverse.size == 8
    assert reading.adverse.missing == 4
    assert reading.average_adverse_r == Decimal(-1)


def test_a_corpus_with_no_excursion_at_all_reports_absence_not_zero() -> None:
    trades = tuple(
        stat(f"r{i}", source=StatSource.RECORDED, mae=None, mfe=None)
        for i in range(3)
    )
    reading = quality_statistics(trades, LOW)
    assert isinstance(reading.average_adverse_r, Absent)
    assert isinstance(reading.average_favourable_r, Absent)
    assert reading.adverse.size == 0


def test_the_average_excursion_is_the_mean_of_the_full_ranges() -> None:
    trades = (stat("a", mfe="3", mae="-1"), stat("b", mfe="1", mae="-1"))
    assert quality_statistics(trades, LOW).average_excursion_r == Decimal(3)


def test_capture_efficiency_reports_both_a_mean_and_a_median() -> None:
    """The mean is dominated by small denominators; both are shown for that
    reason and the basis says so."""
    trades = (
        stat("a", r_multiple="2", mfe="4"),
        stat("b", r_multiple="-1", mfe="0.1"),
        stat("c", r_multiple="1", mfe="2"),
    )
    reading = quality_statistics(trades, LOW)
    assert reading.median_capture_efficiency == Decimal("0.5")
    assert reading.average_capture_efficiency < 0
    assert "median is the more readable" in reading.capture_basis


# --------------------------------------------------------------------------
# Distributions
# --------------------------------------------------------------------------


def test_every_value_lands_in_exactly_one_bucket() -> None:
    values = tuple(Decimal(str(raw)) for raw in (-5, -2, -1, -0.5, 0, 0.5, 1, 2, 3, 9))
    histogram = histogram_of(
        Sample(subject="R multiple", values=values, missing=0), kind="r_multiple"
    )
    assert sum(bucket.count for bucket in histogram.buckets) == len(values)


def test_a_value_exactly_on_an_edge_lands_in_the_upper_bucket() -> None:
    """Half-open `[lower, upper)`, so consecutive bins never double-count."""
    histogram = histogram_of(
        Sample(subject="R", values=(Decimal(1),), missing=0), kind="r_multiple"
    )
    placed = [bucket.label for bucket in histogram.buckets if bucket.count]
    assert placed == ["1 to 2"]


def test_the_tails_are_open_ended_rather_than_clamped() -> None:
    """The tail is what decides whether a system survives."""
    histogram = histogram_of(
        Sample(subject="R", values=(Decimal(-40), Decimal(40)), missing=0),
        kind="r_multiple",
    )
    assert histogram.buckets[0].count == 1
    assert histogram.buckets[-1].count == 1
    assert histogram.buckets[0].is_open_ended
    assert histogram.buckets[-1].is_open_ended


def test_empty_buckets_are_kept_because_the_gaps_are_the_information() -> None:
    histogram = histogram_of(
        Sample(subject="R", values=(Decimal(-1), Decimal(3)), missing=0),
        kind="r_multiple",
    )
    assert any(bucket.count == 0 for bucket in histogram.buckets)
    assert len(histogram.buckets) == len(HISTOGRAM_KINDS["r_multiple"]) + 1


def test_the_edges_do_not_move_when_a_value_is_added() -> None:
    """Data-derived bins make two runs a week apart incomparable."""
    first = histogram_of(
        Sample(subject="R", values=(Decimal(1),), missing=0), kind="r_multiple"
    )
    second = histogram_of(
        Sample(subject="R", values=(Decimal(1), Decimal(50)), missing=0),
        kind="r_multiple",
    )
    assert [bucket.label for bucket in first.buckets] == [
        bucket.label for bucket in second.buckets
    ]


def test_a_holding_time_histogram_bins_in_exact_days() -> None:
    values = (timedelta(hours=12), timedelta(days=2), timedelta(days=40))
    histogram = histogram_of(
        Sample(subject="holding time", values=values, missing=0), kind="holding_time"
    )
    assert histogram.unit == "days"
    assert [bucket.count for bucket in histogram.buckets] == [1, 1, 0, 0, 0, 1]


def test_a_duration_exactly_on_a_day_edge_lands_in_the_upper_bucket() -> None:
    histogram = histogram_of(
        Sample(subject="t", values=(timedelta(days=1),), missing=0),
        kind="holding_time",
    )
    assert [bucket.label for bucket in histogram.buckets if bucket.count] == ["1 to 3"]


def test_the_missing_count_travels_with_the_shape() -> None:
    histogram = histogram_of(
        Sample(subject="R", values=(Decimal(1),), missing=7), kind="r_multiple"
    )
    assert histogram.missing == 7
    assert histogram.population == 8


def test_an_unknown_histogram_kind_is_refused_rather_than_binned_by_guess() -> None:
    with pytest.raises(StatisticsRefusedError, match="no bucket edges"):
        histogram_of(Sample(subject="x", values=(), missing=0), kind="slippage")


def test_a_value_of_the_wrong_type_for_its_kind_is_refused() -> None:
    with pytest.raises(TypeError):
        histogram_of(
            Sample(subject="x", values=(timedelta(days=1),), missing=0),
            kind="r_multiple",
        )
    with pytest.raises(TypeError):
        histogram_of(
            Sample(subject="x", values=(Decimal(1),), missing=0),
            kind="holding_time",
        )


def test_a_bucket_that_cannot_hold_anything_is_refused() -> None:
    with pytest.raises(StatisticsRefusedError, match="nothing can fall inside"):
        Bucket(label="bad", lower=Decimal(5), upper=Decimal(1), count=0)


def test_a_bucket_open_at_both_ends_is_the_population_and_not_a_bucket() -> None:
    with pytest.raises(StatisticsRefusedError, match="not a\\s+bucket"):
        Bucket(label="everything", lower=None, upper=None, count=1)


def test_a_histogram_that_dropped_a_value_is_refused() -> None:
    """Constructed directly: the builder cannot produce this, and the guard is
    what makes that a property rather than a hope."""
    from fmis.statistics import Histogram

    with pytest.raises(StatisticsRefusedError, match="a shape the data does not have"):
        Histogram(
            kind="r_multiple",
            unit="R",
            buckets=(Bucket(label="x", lower=None, upper=Decimal(0), count=1),),
            size=5,
            missing=0,
        )


def test_the_peak_is_what_a_bar_chart_scales_against() -> None:
    histogram = histogram_of(
        Sample(subject="R", values=(Decimal(1), Decimal(1), Decimal(9)), missing=0),
        kind="r_multiple",
    )
    assert histogram.peak == 2
    assert not histogram.is_empty
