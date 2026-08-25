"""Metrics: the arithmetic, and the refusals that stop a small sample looking solid."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.swing_lab.metrics import (
    SAMPLE_FLOOR,
    LabMeasure,
    classify,
    lab_breakdown_by,
    compute_lab_metrics,
)
from fmis.swing_lab.models import LabExitReason, LabTrade, LabVerdict, SwingLabError
from fmis.swing_lab.robustness import concentration_of, measure_robustness
from fmis.swing_setup.models import Direction

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def trade(
    net_r: str | None,
    *,
    index: int = 0,
    symbol: str = "BTCUSDT",
    direction: Direction = Direction.LONG,
    reason: LabExitReason = LabExitReason.TARGET,
    segment: str | None = "q1",
    bars: int = 5,
) -> LabTrade:
    value = None if net_r is None else Decimal(net_r)
    return LabTrade(
        variant_id="v",
        symbol=symbol,
        setup_id=f"s{index}",
        direction=direction,
        signal_at=T0 + timedelta(days=index),
        entry_at=T0 + timedelta(days=index),
        entry_price=Decimal("100"),
        initial_stop=Decimal("90"),
        target=Decimal("120"),
        planned_reference_price=Decimal("100"),
        exit_at=T0 + timedelta(days=index, hours=1),
        exit_price=Decimal("110"),
        exit_reason=reason,
        bars_held=bars,
        gross_r=value,
        net_r=value,
        mfe_r=None if value is None else Decimal("1"),
        mae_r=None if value is None else Decimal("-0.5"),
        cost_policy_id="test",
        planned_risk_reward=2.0,
        segment=segment,
        context_regime_structure="trending",
        context_structural_trend="sustained_higher",
        setup_structural_trend="sustained_higher",
    )


def many(count: int, net_r: str, **kwargs) -> list[LabTrade]:
    return [trade(net_r, index=i, **kwargs) for i in range(count)]


class TestTheSampleFloor:
    def test_a_thin_cohort_reports_absence_not_a_number(self) -> None:
        metrics = compute_lab_metrics(many(3, "2"), label="thin")
        assert metrics.expectancy_r.value is None
        assert metrics.expectancy_r.n == 3
        assert "below the" in metrics.expectancy_r.reason
        assert metrics.win_rate.value is None

    def test_the_floor_is_inclusive(self) -> None:
        assert compute_lab_metrics(many(SAMPLE_FLOOR, "1"), label="x").expectancy_r.is_present
        assert not compute_lab_metrics(
            many(SAMPLE_FLOOR - 1, "1"), label="x"
        ).expectancy_r.is_present

    def test_an_empty_sample_is_not_a_crash(self) -> None:
        metrics = compute_lab_metrics((), label="empty")
        assert metrics.trades == 0
        assert metrics.expectancy_r.value is None
        assert metrics.total_r == Decimal("0")
        assert metrics.equity_curve == ()
        assert metrics.max_drawdown.max_drawdown_r == Decimal("0")

    def test_counts_are_reported_even_below_the_floor(self) -> None:
        """A thin cohort still shows how thin it is."""
        metrics = compute_lab_metrics(many(3, "2"), label="thin")
        assert metrics.trades == 3
        assert metrics.wins == 3

    def test_a_measure_cannot_hide_its_sample(self) -> None:
        with pytest.raises(SwingLabError, match="non-negative int"):
            LabMeasure(value=Decimal("1"), n=-1)

    def test_a_measure_states_a_value_or_a_reason_never_both(self) -> None:
        with pytest.raises(SwingLabError, match="never both"):
            LabMeasure(value=Decimal("1"), n=30, reason="because")

    def test_an_absent_measure_must_say_why(self) -> None:
        with pytest.raises(SwingLabError, match="must carry a reason"):
            LabMeasure(value=None, n=30)


class TestArithmetic:
    def test_expectancy_is_the_mean_net_r(self) -> None:
        trades = many(10, "2") + many(10, "-1")
        for index, item in enumerate(trades):
            object.__setattr__(item, "setup_id", f"s{index}")
        metrics = compute_lab_metrics(trades, label="x")
        assert metrics.expectancy_r.value == Decimal("0.5")
        assert metrics.expectancy_r.n == 20

    def test_profit_factor_is_gross_profit_over_gross_loss(self) -> None:
        metrics = compute_lab_metrics(many(10, "2") + many(10, "-1"), label="x")
        assert metrics.profit_factor.value == Decimal("2")

    def test_profit_factor_is_absent_rather_than_infinite_without_losses(self) -> None:
        metrics = compute_lab_metrics(many(25, "2"), label="x")
        assert metrics.profit_factor.value is None
        assert "no denominator" in metrics.profit_factor.reason

    def test_win_rate_counts_by_sign_not_by_exit_reason(self) -> None:
        """A target that netted below zero after costs is a loss."""
        metrics = compute_lab_metrics(
            many(20, "-0.01", reason=LabExitReason.TARGET), label="x"
        )
        assert metrics.losses == 20
        assert metrics.win_rate.value == 0

    def test_a_scratch_is_neither_a_win_nor_a_loss(self) -> None:
        metrics = compute_lab_metrics(many(20, "0"), label="x")
        assert metrics.wins == 0 and metrics.losses == 0
        assert metrics.scratches == 20

    def test_median_is_the_middle_not_the_mean(self) -> None:
        trades = many(19, "1") + many(1, "100")
        metrics = compute_lab_metrics(trades, label="x")
        assert metrics.median_r.value == Decimal("1")
        assert metrics.expectancy_r.value > Decimal("1")

    def test_largest_win_and_loss_are_reported(self) -> None:
        metrics = compute_lab_metrics(many(10, "3") + many(10, "-2"), label="x")
        assert metrics.largest_win_r == Decimal("3")
        assert metrics.largest_loss_r == Decimal("-2")


class TestUnmeasurableTradesAreExcludedAndCounted:
    def test_ambiguous_trades_never_enter_expectancy(self) -> None:
        trades = many(20, "1") + [
            trade(None, index=99, reason=LabExitReason.AMBIGUOUS_SAME_BAR)
        ]
        metrics = compute_lab_metrics(trades, label="x")
        assert metrics.trades == 21
        assert metrics.measurable_trades == 20
        assert metrics.ambiguous_trades == 1
        assert metrics.expectancy_r.value == Decimal("1")

    def test_unentered_trades_are_counted_separately(self) -> None:
        trades = many(20, "1") + [trade(None, index=99, reason=LabExitReason.NO_ENTRY_BAR)]
        metrics = compute_lab_metrics(trades, label="x")
        assert metrics.unentered_trades == 1
        assert metrics.measurable_trades == 20

    def test_every_exit_reason_appears_in_the_tally(self) -> None:
        trades = many(5, "1") + many(5, "-1", reason=LabExitReason.STOP)
        reasons = dict(compute_lab_metrics(trades, label="x").exit_reasons)
        assert reasons == {"target": 5, "stop": 5}


class TestDrawdown:
    def test_drawdown_measures_from_the_running_peak_including_the_peak_itself(
        self,
    ) -> None:
        trades = [
            trade("1", index=0),
            trade("1", index=1),
            trade("-3", index=2),
            trade("1", index=3),
        ]
        metrics = compute_lab_metrics(trades, label="x")
        # Peak is +2 after two wins; trough is -1 after the -3. Decline = 3.
        assert metrics.max_drawdown.max_drawdown_r == Decimal("3")
        assert metrics.max_drawdown.peak_index == 1
        assert metrics.max_drawdown.trough_index == 2

    def test_a_monotonically_rising_curve_has_no_drawdown(self) -> None:
        metrics = compute_lab_metrics(many(20, "1"), label="x")
        assert metrics.max_drawdown.max_drawdown_r == Decimal("0")

    def test_recovery_is_reported(self) -> None:
        recovered = compute_lab_metrics(
            [trade("1", index=0), trade("-1", index=1), trade("2", index=2)], label="x"
        )
        assert recovered.max_drawdown.recovered
        never = compute_lab_metrics(
            [trade("1", index=0), trade("-1", index=1)], label="x"
        )
        assert not never.max_drawdown.recovered

    def test_drawdown_duration_spans_peak_to_trough(self) -> None:
        metrics = compute_lab_metrics(
            [trade("1", index=0), trade("-1", index=5)], label="x"
        )
        assert metrics.max_drawdown.duration == timedelta(days=5)

    def test_the_equity_curve_is_cumulative(self) -> None:
        metrics = compute_lab_metrics(
            [trade("1", index=0), trade("2", index=1)], label="x"
        )
        assert [point.cumulative_r for point in metrics.equity_curve] == [
            Decimal("1"),
            Decimal("3"),
        ]

    def test_the_curve_is_ordered_by_exit_not_by_argument_order(self) -> None:
        forward = compute_lab_metrics(
            [trade("1", index=0), trade("-2", index=1)], label="x"
        )
        reversed_input = compute_lab_metrics(
            [trade("-2", index=1), trade("1", index=0)], label="x"
        )
        assert [p.cumulative_r for p in forward.equity_curve] == [
            p.cumulative_r for p in reversed_input.equity_curve
        ]


class TestBreakdowns:
    def test_cohorts_add_back_to_the_whole(self) -> None:
        trades = many(10, "1", symbol="BTCUSDT") + many(10, "1", symbol="ETHUSDT")
        cohorts = lab_breakdown_by(trades, lambda t: t.symbol)
        assert sum(cohort.trades for cohort in cohorts) == len(trades)

    def test_an_unkeyed_trade_is_labelled_not_dropped(self) -> None:
        cohorts = lab_breakdown_by(many(3, "1", segment=None), lambda t: t.segment)
        assert [cohort.label for cohort in cohorts] == ["unattributed"]
        assert cohorts[0].trades == 3

    def test_cohorts_are_sorted_by_label(self) -> None:
        trades = many(2, "1", symbol="ZZZ") + many(2, "1", symbol="AAA")
        assert [c.label for c in lab_breakdown_by(trades, lambda t: t.symbol)] == [
            "AAA",
            "ZZZ",
        ]


class TestRobustness:
    def test_the_chronological_split_uses_the_window_midpoint(self) -> None:
        trades = [trade("1", index=i) for i in range(10)]
        reading = measure_robustness(
            trades,
            variant_id="v",
            measurement_start=T0,
            measurement_end=T0 + timedelta(days=10),
        )
        labels = {c.label for c in reading.split("chronological").cohorts}
        assert labels == {"train_first_half", "validation_second_half"}
        counts = {c.label: c.trades for c in reading.split("chronological").cohorts}
        assert counts["train_first_half"] == 5

    def test_concentration_uses_absolute_r_so_a_big_loss_concentrates_too(self) -> None:
        trades = [trade("-10", index=0, symbol="A"), trade("1", index=1, symbol="B")]
        assert concentration_of(trades, lambda t: t.symbol) == Decimal("10") / Decimal("11")

    def test_concentration_is_absent_when_nothing_is_measurable(self) -> None:
        assert concentration_of([trade(None, index=0)], lambda t: t.symbol) is None

    def test_agreement_needs_at_least_two_reportable_cohorts(self) -> None:
        trades = many(30, "1", symbol="A")
        reading = measure_robustness(
            trades,
            variant_id="v",
            measurement_start=T0,
            measurement_end=T0 + timedelta(days=60),
        )
        # Only one symbol clears the floor, so there is nothing to agree with.
        assert reading.split("symbol").all_cohorts_agree_on_sign is None

    def test_an_inverted_window_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="must be after"):
            measure_robustness(
                [], variant_id="v", measurement_start=T0, measurement_end=T0
            )

    def test_an_unknown_split_names_the_available_ones(self) -> None:
        reading = measure_robustness(
            [], variant_id="v", measurement_start=T0, measurement_end=T0 + timedelta(days=1)
        )
        with pytest.raises(SwingLabError, match="chronological"):
            reading.split("nonexistent")


class TestVerdictClassification:
    """The verdict must be derived, deterministic and reconstructable.

    Added by the BW release gate: the `/lab` surface is required to distinguish
    REJECTED from INCONCLUSIVE, and a classification a reader cannot recompute
    from the artifact is an assertion rather than a finding.
    """

    def test_a_positive_expectancy_is_a_forward_test_candidate_only(self) -> None:
        metrics = compute_lab_metrics(many(25, "1"), label="x")
        assert classify(metrics) is LabVerdict.CANDIDATE_FOR_FORWARD_TEST

    def test_a_negative_expectancy_is_rejected(self) -> None:
        metrics = compute_lab_metrics(many(25, "-1"), label="x")
        assert classify(metrics) is LabVerdict.REJECTED

    def test_a_zero_expectancy_is_rejected_not_a_candidate(self) -> None:
        """Break-even is not an edge, and must not be promoted as one."""
        metrics = compute_lab_metrics(many(25, "0"), label="x")
        assert classify(metrics) is LabVerdict.REJECTED

    def test_a_thin_sample_is_inconclusive_not_rejected(self) -> None:
        """Too few trades establishes nothing — in either direction."""
        assert classify(compute_lab_metrics(many(3, "-5"), label="x")) is (
            LabVerdict.INCONCLUSIVE
        )
        assert classify(compute_lab_metrics(many(3, "5"), label="x")) is (
            LabVerdict.INCONCLUSIVE
        )

    def test_an_unmeasured_variant_is_inconclusive(self) -> None:
        assert classify(compute_lab_metrics((), label="x")) is LabVerdict.INCONCLUSIVE

    def test_no_verdict_approves_trading(self) -> None:
        for verdict in LabVerdict:
            assert verdict.is_approved_for_trading is False
            assert verdict.statement

    def test_the_strongest_verdict_says_it_is_not_approval(self) -> None:
        statement = LabVerdict.CANDIDATE_FOR_FORWARD_TEST.statement
        assert "NOT approval" in statement

    def test_the_verdict_ignores_profit_factor_and_win_rate(self) -> None:
        """One criterion decides, so a flattering secondary figure cannot promote.

        A cohort with a 96 % win rate and a negative expectancy — many tiny wins
        and one large loss — must still be REJECTED.
        """
        trades = many(24, "0.1") + [trade("-5", index=99)]
        metrics = compute_lab_metrics(trades, label="x")
        assert metrics.win_rate.value > Decimal("0.9")
        assert metrics.expectancy_r.value < 0
        assert classify(metrics) is LabVerdict.REJECTED

    def test_the_verdict_is_reconstructable_from_the_metrics_alone(self) -> None:
        metrics = compute_lab_metrics(many(25, "-1"), label="x")
        assert classify(metrics) is classify(metrics)

    def test_a_non_metrics_argument_is_refused(self) -> None:
        with pytest.raises(TypeError, match="VariantMetrics"):
            classify("rejected")
