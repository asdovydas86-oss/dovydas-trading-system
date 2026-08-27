"""Hostile review of Milestone BZ. **Each probe tries to make BZ say something false.**

Every test here is an attack, not a feature check. The question each one asks is
"can I get this milestone to state a number it is not entitled to state" — a rate
from an empty cohort, an expectancy from one trade, a resolved ordering from an
ambiguous bar, a promotion from a policy nobody sealed, a thesis reading from a
data gap.

The rule the suite enforces throughout is the repository's own: **a programmer
error propagates, a data absence becomes a stated absence, and neither is ever
turned into a market fact.**
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.exits import exit_policy_by_id, simulate_managed_trade
from fmis.swing_lab.metrics import SAMPLE_FLOOR, compute_lab_metrics
from fmis.swing_lab.models import LabExitReason, SwingLabError
from fmis.swing_lab.persistence import (
    PostEntryCheckpoint,
    ThesisObservation,
    ThesisState,
    ThesisTimeline,
    observe_path,
    thesis_state,
)
from fmis.swing_lab.persistence_preregistration import (
    BZ_PRE_REGISTRATION,
    BZ_PREREGISTRATION_DIGEST,
    bz_preregistration_digest,
    is_bz_pre_registered,
)
from fmis.swing_lab.trades import CONSERVATIVE_COSTS, FRICTIONLESS_COSTS, simulate_trade
from fmis.swing_lab.persistence_study import (
    BzVerdict,
    assess_bz,
    compare_families,
    decompose_giveback,
    measure_family,
    summarise_paths,
)
from fmis.swing_setup.models import Direction

_UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=_UTC)
FOUR_HOURS = timedelta(hours=4)

CONTROL = exit_policy_by_id("bz_exit_control")
THESIS = exit_policy_by_id("bz_exit_thesis_failure")
GIVEBACK = exit_policy_by_id("bz_exit_giveback_half")
TRAIL = exit_policy_by_id("bz_exit_structural_trail")


def _bar(index: int, o: str, h: str, low: str, c: str) -> PriceBar:
    return PriceBar(
        symbol="BTCUSDT", interval="4h", open_time=T0 + FOUR_HOURS * index,
        open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(c),
    )


def _observation(index: int, **overrides) -> ThesisObservation:
    base = dict(
        symbol="BTCUSDT", as_of=T0 + FOUR_HOURS * index, bar_index=index,
        context_structural_trend="sustained_higher",
        setup_structural_trend="sustained_higher",
        execution_structural_trend="sustained_higher",
        context_regime_structure="trending",
        evidence_state=None, evidence_dominant_alignment=None,
        decision_context_state="sufficient", setup_state="confirmed",
        setup_direction="long", execution_close=100.0,
        upper_levels=(), lower_levels=(),
    )
    base.update(overrides)
    return ThesisObservation(**base)


def _track(bars, *, direction=Direction.LONG, stop=Decimal("90"), window=30,
           timeline=None, checkpoints=(1, 2, 3)):
    return observe_path(
        bars, symbol="BTCUSDT", setup_id="s", direction=direction,
        sample="development", signal_at=bars[0].open_time, signal_index=0,
        entry_price=bars[1].open, initial_stop=stop, target=Decimal("200"),
        evaluation_window_bars=window, timeline=timeline, checkpoints=checkpoints,
    )


class TestEmptyAndThinCohorts:
    """A milestone must refuse to state what it cannot support."""

    def test_zero_paths_states_no_rate(self) -> None:
        summary = summarise_paths((), label="empty")
        assert summary.paths == 0
        assert summary.full_r_giveback_rate is None
        assert summary.rate_reached("1.0") is None
        assert summary.peak_r_median is None
        assert summary.median_bars_to_peak is None

    def test_zero_trades_states_no_expectancy(self) -> None:
        metrics = compute_lab_metrics((), label="empty")
        assert metrics.measurable_trades == 0
        assert metrics.expectancy_r.value is None
        assert metrics.expectancy_r.reason is not None

    def test_one_trade_is_below_the_floor_and_refused(self) -> None:
        """A single trade is not an expectancy however good it looks."""
        winner = _track(
            (
                _bar(0, "100", "101", "99", "100"),
                _bar(1, "100", "150", "99", "148"),
            ),
            window=2,
            checkpoints=(1,),
        )
        assert winner.peak_r == Decimal("5")
        summary = summarise_paths((winner,), label="one")
        # A count of 1 is reportable; a per-cohort RATE is not, and the
        # decomposition refuses it.
        decomposition = decompose_giveback((winner,), (), label="one")
        for _count, rate in decomposition.by_direction.values():
            assert rate is None, "a cohort below the floor stated a rate"

    def test_a_cohort_exactly_at_the_floor_is_stated(self) -> None:
        """The boundary is inclusive, and it is asserted rather than assumed."""
        tracks = tuple(
            _track(
                (
                    _bar(0, "100", "101", "99", "100"),
                    _bar(1, "100", "150", "99", "148"),
                ),
                window=2, checkpoints=(1,),
            )
            for _ in range(SAMPLE_FLOOR)
        )
        decomposition = decompose_giveback(tracks, (), label="floor")
        rates = [rate for _count, rate in decomposition.by_direction.values()]
        assert all(rate is not None for rate in rates)

    def test_one_below_the_floor_is_refused(self) -> None:
        tracks = tuple(
            _track(
                (
                    _bar(0, "100", "101", "99", "100"),
                    _bar(1, "100", "150", "99", "148"),
                ),
                window=2, checkpoints=(1,),
            )
            for _ in range(SAMPLE_FLOOR - 1)
        )
        decomposition = decompose_giveback(tracks, (), label="under")
        rates = [rate for _count, rate in decomposition.by_direction.values()]
        assert all(rate is None for rate in rates)


class TestDegenerateGeometry:
    def test_a_zero_risk_geometry_is_refused_not_measured(self) -> None:
        with pytest.raises(SwingLabError, match="no risk denominator"):
            _track(
                (_bar(0, "100", "101", "99", "100"), _bar(1, "100", "101", "99", "100")),
                stop=Decimal("100"),
            )

    def test_an_entry_gapping_through_its_stop_is_a_loss_never_skipped(self) -> None:
        """Skipping would delete exactly the worst fills."""
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "85", "95", "80", "90"),
        )
        result = simulate_managed_trade(
            bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=1, entry_price=bars[1].open,
            entry_at=bars[1].open_time, signal_at=bars[0].open_time,
            reference_price=bars[0].close, stop_price=Decimal("90"),
            target_price=Decimal("200"), planned_risk_reward=3.0, window_bars=10,
            costs=FRICTIONLESS_COSTS,
            policy=CONTROL,
        )
        assert result.trade.exit_reason is LabExitReason.ENTRY_GAPPED_THROUGH_STOP
        assert result.trade.net_r == Decimal("-1")

    def test_a_huge_decimal_does_not_lose_precision(self) -> None:
        """Prices are exact decimals; a 10-digit instrument must still divide."""
        big = (
            PriceBar(symbol="X", interval="4h", open_time=T0,
                     open=Decimal("1234567890.12345678"),
                     high=Decimal("1234567890.12345679"),
                     low=Decimal("1234567890.12345677"),
                     close=Decimal("1234567890.12345678")),
            PriceBar(symbol="X", interval="4h", open_time=T0 + FOUR_HOURS,
                     open=Decimal("1234567890.12345678"),
                     high=Decimal("1234567891.12345678"),
                     low=Decimal("1234567890.12345678"),
                     close=Decimal("1234567891.00000000")),
        )
        track = observe_path(
            big, symbol="X", setup_id="s", direction=Direction.LONG,
            sample="development", signal_at=T0, signal_index=0,
            entry_price=big[1].open, initial_stop=Decimal("1234567889.12345678"),
            target=Decimal("1234567899"), evaluation_window_bars=2,
            checkpoints=(1,),
        )
        assert track.risk == Decimal("1")
        assert track.checkpoint(1).mfe_r == Decimal("1")

    def test_a_tiny_risk_is_overwhelmed_by_costs_and_says_so(self) -> None:
        """Cost in R is fee x (entry+exit)/risk. A near-zero risk must explode it."""
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "100.5", "99.99", "100.2"),
            _bar(2, "100.2", "100.3", "99.98", "100"),
        )
        trade = simulate_trade(
            bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, signal_index=0, signal_at=T0,
            reference_price=Decimal("100"), stop_price=Decimal("99.99"),
            target_price=Decimal("200"), planned_risk_reward=3.0,
            window_bars=3, costs=CONSERVATIVE_COSTS,
        )
        assert trade.net_r is not None
        assert trade.gross_r is not None
        # The cost drag is enormous relative to a 0.01 risk, and it is reported
        # rather than clipped.
        assert trade.gross_r - trade.net_r > Decimal("10")


class TestAmbiguityIsNeverGuessed:
    def test_a_bar_reaching_both_levels_stays_ambiguous(self) -> None:
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "205", "85", "150"),
        )
        result = simulate_managed_trade(
            bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=1, entry_price=bars[1].open,
            entry_at=bars[1].open_time, signal_at=bars[0].open_time,
            reference_price=bars[0].close, stop_price=Decimal("90"),
            target_price=Decimal("200"), planned_risk_reward=3.0,
            window_bars=10, costs=FRICTIONLESS_COSTS, policy=CONTROL,
        )
        assert result.trade.exit_reason is LabExitReason.AMBIGUOUS_SAME_BAR
        assert result.trade.net_r is None
        assert not result.trade.is_measurable

    def test_an_ambiguous_trade_is_excluded_from_expectancy_and_counted(self) -> None:
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "205", "85", "150"),
        )
        result = simulate_managed_trade(
            bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=1, entry_price=bars[1].open,
            entry_at=bars[1].open_time, signal_at=bars[0].open_time,
            reference_price=bars[0].close, stop_price=Decimal("90"),
            target_price=Decimal("200"), planned_risk_reward=3.0,
            window_bars=10, costs=FRICTIONLESS_COSTS, policy=CONTROL,
        )
        metrics = compute_lab_metrics((result.trade,), label="amb")
        assert metrics.ambiguous_trades == 1
        assert metrics.measurable_trades == 0
        assert metrics.expectancy_r.value is None

    def test_a_close_decided_mechanic_adds_no_watched_level(self) -> None:
        """BZ's mechanics decide on a close, so they cannot multiply ambiguity.

        The same collision bar is ambiguous for the control and for a BZ family,
        and the counts are equal — which is the claim the pre-registration's
        ambiguity policy makes and this asserts rather than assumes.
        """
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "205", "85", "150"),
        )

        def run(policy, timeline=None):
            return simulate_managed_trade(
                bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
                direction=Direction.LONG, entry_index=1, entry_price=bars[1].open,
                entry_at=bars[1].open_time, signal_at=bars[0].open_time,
                reference_price=bars[0].close, stop_price=Decimal("90"),
                target_price=Decimal("200"), planned_risk_reward=3.0,
                window_bars=10, costs=FRICTIONLESS_COSTS, policy=policy,
                timeline=timeline,
            ).trade.exit_reason

        timeline = ThesisTimeline(
            symbol="BTCUSDT",
            observations={0: _observation(0), 1: _observation(1)},
        )
        assert run(CONTROL) is LabExitReason.AMBIGUOUS_SAME_BAR
        assert run(GIVEBACK) is LabExitReason.AMBIGUOUS_SAME_BAR
        assert run(THESIS, timeline) is LabExitReason.AMBIGUOUS_SAME_BAR
        assert run(TRAIL, timeline) is LabExitReason.AMBIGUOUS_SAME_BAR


class TestAbsenceIsStatedNeverInvented:
    def test_a_missing_instant_is_unavailable_not_intact(self) -> None:
        assert thesis_state(_observation(0), None, Direction.LONG) is (
            ThesisState.UNAVAILABLE
        )
        assert not ThesisState.UNAVAILABLE.is_adverse

    def test_unavailable_evidence_after_entry_does_not_close_a_position(self) -> None:
        """A data gap must never read as a thesis failure."""
        bars = tuple(_bar(i, "100", "101", "99", "100") for i in range(6))
        timeline = ThesisTimeline(
            symbol="BTCUSDT", observations={0: _observation(0)}
        )
        result = simulate_managed_trade(
            bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=1, entry_price=bars[1].open,
            entry_at=bars[1].open_time, signal_at=bars[0].open_time,
            reference_price=bars[0].close, stop_price=Decimal("90"),
            target_price=Decimal("200"), planned_risk_reward=3.0,
            window_bars=10,
            costs=FRICTIONLESS_COSTS,
            policy=THESIS, timeline=timeline,
        )
        assert result.trade.exit_reason is LabExitReason.TIME_STOP

    def test_a_missing_execution_close_yields_no_levels_not_a_guess(self) -> None:
        """A warming-up view has no ordering reference, so both sides are EMPTY."""
        observation = _observation(0, execution_close=None)
        assert observation.upper_levels == ()
        assert observation.lower_levels == ()

    def test_a_structural_trail_with_no_levels_moves_nothing(self) -> None:
        bars = tuple(_bar(i, "100", "101", "99", "100") for i in range(6))
        timeline = ThesisTimeline(
            symbol="BTCUSDT",
            observations={i: _observation(i) for i in range(6)},
        )
        result = simulate_managed_trade(
            bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=1, entry_price=bars[1].open,
            entry_at=bars[1].open_time, signal_at=bars[0].open_time,
            reference_price=bars[0].close, stop_price=Decimal("90"),
            target_price=Decimal("200"), planned_risk_reward=3.0,
            window_bars=10,
            costs=FRICTIONLESS_COSTS,
            policy=TRAIL, timeline=timeline,
        )
        assert result.trade.initial_stop == Decimal("90")
        assert result.trade.exit_reason is LabExitReason.TIME_STOP


class TestIdentityAndOrdering:
    def test_a_duplicate_observation_is_refused(self) -> None:
        from fmis.swing_lab.persistence_replay import TimelineCollector

        collector = TimelineCollector()
        # A hand-built duplicate cannot go through __call__ without an instant,
        # so the invariant is asserted at the timeline instead.
        with pytest.raises(SwingLabError, match="own bar_index"):
            ThesisTimeline(symbol="BTCUSDT", observations={5: _observation(0)})
        assert collector.observed == 0

    def test_a_timeline_cannot_hold_another_symbols_structure(self) -> None:
        with pytest.raises(SwingLabError, match="holds a ETHUSDT"):
            ThesisTimeline(
                symbol="BTCUSDT",
                observations={0: _observation(0, symbol="ETHUSDT")},
            )

    def test_a_comparison_refuses_to_mix_samples(self) -> None:
        """Milestone BY defect BY-D6: pooling changes what is measured."""
        from fmis.swing_lab.metrics import compute_lab_metrics as metrics_of
        from fmis.swing_lab.persistence_study import FamilyMeasurement

        def measurement(sample: str) -> FamilyMeasurement:
            return FamilyMeasurement(
                policy_id="bz_exit_control", hypothesis_id="BZ-H0",
                geometry_policy_id="geom_production", sample=sample,
                cost_policy_id="swing-lab-conservative-10bps", trades=(),
                metrics=metrics_of((), label=sample), fired=0, ambiguous=0,
                exit_reasons=(),
            )

        with pytest.raises(SwingLabError, match="one sample, one geometry"):
            compare_families(
                [measurement("development"), measurement("holdout")],
                control_policy_id="bz_exit_control",
            )

    def test_an_empty_comparison_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="at least one measurement"):
            compare_families([], control_policy_id="bz_exit_control")

    def test_path_observation_is_deterministic(self) -> None:
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "108", "99", "106"),
            _bar(2, "106", "120", "105", "118"),
        )
        assert _track(bars).payload() == _track(bars).payload()

    def test_the_summary_payload_is_json_safe(self) -> None:
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "108", "99", "106"),
        )
        summary = summarise_paths((_track(bars, window=2, checkpoints=(1,)),), label="j")
        json.dumps(summary.payload())


class TestPromotionCannotBeBypassed:
    def test_a_policy_nobody_sealed_can_never_be_promoted(self) -> None:
        """**The gate.** The first criterion is membership, not a caller's flag."""
        assessment = assess_bz(
            "bz_exit_invented_after_the_results",
            geometry_policy_id="geom_production",
            comparisons={},
            causal_proven=True,
            robust=True,
            ambiguity_decisive=False,
        )
        assert assessment.verdict is BzVerdict.NOT_MEASURED
        assert not assessment.verdict.earns_forward_test

    def test_no_verdict_approves_trading(self) -> None:
        for verdict in BzVerdict:
            assert not verdict.is_approved_for_trading
        assert BzVerdict.MECHANISM_EVIDENCE.earns_forward_test is False
        assert BzVerdict.CANDIDATE.earns_forward_test is True

    def test_a_neighbourhood_point_is_not_pre_registered(self) -> None:
        assert not is_bz_pre_registered("bz_exit_stagnation_8")
        assert not is_bz_pre_registered("bz_exit_giveback_0_67")
        assert is_bz_pre_registered("bz_exit_stagnation_12")

    def test_a_tampered_seal_fails_every_assessment(self) -> None:
        """A result read under a different pre-registration is refused."""
        from dataclasses import replace

        tampered = replace(
            BZ_PRE_REGISTRATION,
            hypotheses=BZ_PRE_REGISTRATION.hypotheses[:-1],
        )
        assessment = assess_bz(
            "bz_exit_thesis_failure",
            geometry_policy_id="geom_production",
            comparisons={},
            causal_proven=True,
            robust=True,
            ambiguity_decisive=False,
            preregistration=tampered,
        )
        assert not assessment.digest_matches
        pre_registered = next(
            item for item in assessment.mechanism_criteria
            if item.name == "pre_registered"
        )
        assert pre_registered.passed is False

    def test_the_live_seal_still_matches_its_pin(self) -> None:
        assert bz_preregistration_digest() == BZ_PREREGISTRATION_DIGEST

    def test_a_digest_is_stable_across_hash_seeds(self) -> None:
        """`PYTHONHASHSEED` must not reach any digest this milestone pins."""
        import subprocess
        import sys

        seen = set()
        for seed in ("0", "1", "12345"):
            result = subprocess.run(
                [
                    sys.executable, "-c",
                    "from fmis.swing_lab.persistence_preregistration import "
                    "bz_preregistration_digest as d; print(d())",
                ],
                capture_output=True, text=True,
                env={"PYTHONHASHSEED": seed, "PATH": __import__("os").environ["PATH"]},
            )
            assert result.returncode == 0, result.stderr
            seen.add(result.stdout.strip())
        assert seen == {BZ_PREREGISTRATION_DIGEST}


class TestConcentrationAndDominance:
    def test_one_symbol_dominating_is_measured_not_hidden(self) -> None:
        from fmis.swing_lab.robustness import concentration_of
        def trade(symbol: str, high: str):
            bars = (
                PriceBar(symbol=symbol, interval="4h", open_time=T0,
                         open=Decimal("100"), high=Decimal("101"),
                         low=Decimal("99"), close=Decimal("100")),
                PriceBar(symbol=symbol, interval="4h", open_time=T0 + FOUR_HOURS,
                         open=Decimal("100"), high=Decimal(high),
                         low=Decimal("99"), close=Decimal(high)),
            )
            return simulate_trade(
                bars, variant_id="v", symbol=symbol, setup_id=f"s-{symbol}",
                direction=Direction.LONG, signal_index=0, signal_at=T0,
                reference_price=Decimal("100"), stop_price=Decimal("90"),
                target_price=Decimal("500"), planned_risk_reward=3.0,
                window_bars=2, costs=FRICTIONLESS_COSTS,
            )

        trades = [trade("BIGUSDT", "400"), trade("SMLUSDT", "101")]
        share = concentration_of(trades, lambda t: t.symbol)
        assert share is not None and share > Decimal("0.9")

    def test_a_single_period_is_visible_in_the_walk_forward(self) -> None:
        """Empty windows are emitted, so a policy that stopped trading shows."""
        from fmis.swing_lab.validation_study import walk_forward

        windows = walk_forward(
            (), start=T0, end=T0 + timedelta(days=365), label="none"
        )
        assert windows
        assert all(item.metrics.measurable_trades == 0 for item in windows)


class TestCheckpointInvariants:
    def test_a_negative_giveback_cannot_be_constructed(self) -> None:
        with pytest.raises(SwingLabError, match="cannot be below the close"):
            PostEntryCheckpoint(
                bar=1, at=T0, close_r=Decimal("2"), mfe_r=Decimal("2"),
                mae_r=Decimal("0"), peak_r=Decimal("1"),
                giveback_r=Decimal("-1"), thesis=ThesisState.INTACT,
            )

    def test_bar_zero_is_refused(self) -> None:
        """Bar 1 is the entry bar; there is no bar 0 of an open position."""
        with pytest.raises(SwingLabError, match="bar 1 is the entry bar"):
            PostEntryCheckpoint(
                bar=0, at=T0, close_r=Decimal("0"), mfe_r=Decimal("0"),
                mae_r=Decimal("0"), peak_r=Decimal("0"),
                giveback_r=Decimal("0"), thesis=ThesisState.INTACT,
            )

    def test_a_future_timestamp_is_simply_a_later_bar(self) -> None:
        """No clock is read, so a 'future' bar is not special and must not be."""
        far = (
            PriceBar(symbol="BTCUSDT", interval="4h",
                     open_time=datetime(2099, 1, 1, tzinfo=_UTC),
                     open=Decimal("100"), high=Decimal("101"),
                     low=Decimal("99"), close=Decimal("100")),
            PriceBar(symbol="BTCUSDT", interval="4h",
                     open_time=datetime(2099, 1, 1, 4, tzinfo=_UTC),
                     open=Decimal("100"), high=Decimal("110"),
                     low=Decimal("99"), close=Decimal("108")),
        )
        track = observe_path(
            far, symbol="BTCUSDT", setup_id="s", direction=Direction.LONG,
            sample="development", signal_at=far[0].open_time, signal_index=0,
            entry_price=far[1].open, initial_stop=Decimal("90"),
            target=Decimal("200"), evaluation_window_bars=2, checkpoints=(1,),
        )
        assert track.checkpoint(1).mfe_r == Decimal("1")
