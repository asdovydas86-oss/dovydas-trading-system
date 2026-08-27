"""The BZ study layer: firing counts, like-for-like comparison, and the verdict.

**Every test in this file was written to kill a surviving mutant.** The mutation
harness edits one line so a scientific claim becomes false and requires the suite
to notice; each of the following corresponds to a probe that the first run did
*not* kill, which means the behaviour was real but untested. A survivor is a
missing test, not a harmless equivalence, until it is shown to be one.

The probes these close:

    study:a-mechanism-that-never-fired-is-counted-as-firing
    study:the-comparable-column-uses-the-union-not-the-intersection
    study:a-family-is-measured-on-every-sample-at-once
    study:a-failed-criterion-is-reported-as-inconclusive
    study:a-quantile-interpolates-between-two-real-trades
    exits:bys-arming-set-silently-gains-a-bz-mechanic
    exits:trail-falls-back-to-a-price-when-structure-is-absent
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.exits import (
    ExitMechanic,
    exit_policy_by_id,
    simulate_managed_trade,
)
from fmis.swing_lab.metrics import compute_lab_metrics
from fmis.swing_lab.models import LabExitReason
from fmis.swing_lab.persistence import (
    PersistenceTrack,
    ThesisObservation,
    ThesisTimeline,
    observe_path,
)
from fmis.swing_lab.persistence_study import (
    BzVerdict,
    FamilyComparison,
    FamilyMeasurement,
    _quantile,
    assess_bz,
    compare_families,
)
from fmis.swing_lab.trades import FRICTIONLESS_COSTS, simulate_trade
from fmis.swing_setup.models import Direction

_UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=_UTC)
FOUR_HOURS = timedelta(hours=4)

CONTROL = exit_policy_by_id("bz_exit_control")
THESIS = exit_policy_by_id("bz_exit_thesis_failure")
STAGNATION = exit_policy_by_id("bz_exit_stagnation_12")
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


class TestTheQuantileIsNearestRank:
    """`study:a-quantile-interpolates-between-two-real-trades`.

    A quantile that interpolates reports an excursion no position ever reached.
    Every value this returns must be one of its inputs.
    """

    def test_every_quantile_is_an_actual_input(self) -> None:
        values = [Decimal(str(v)) for v in (0, 1, 2, 3, 10)]
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            assert _quantile(values, fraction) in values

    def test_the_median_of_an_odd_sample_is_the_middle_element(self) -> None:
        values = [Decimal("1"), Decimal("5"), Decimal("100")]
        assert _quantile(values, 0.50) == Decimal("5")

    def test_the_extremes_are_the_extremes(self) -> None:
        values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]
        assert _quantile(values, 0.0) == Decimal("1")
        assert _quantile(values, 1.0) == Decimal("4")

    def test_an_empty_sample_states_nothing(self) -> None:
        assert _quantile([], 0.5) is None

    def test_it_never_averages_two_neighbours(self) -> None:
        """The specific interpolation a naive implementation would produce."""
        values = [Decimal("0"), Decimal("100")]
        assert _quantile(values, 0.5) in values
        assert _quantile(values, 0.5) != Decimal("50")


class TestFiringIsCountedCorrectly:
    """`study:a-mechanism-that-never-fired-is-counted-as-firing`.

    A mechanism that never fired did not improve anything, and its expectancy
    would silently be the control's. The count is what makes that visible.
    """

    @staticmethod
    def _run(bars, policy, timeline=None):
        return simulate_managed_trade(
            bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=1, entry_price=bars[1].open,
            entry_at=bars[1].open_time, signal_at=bars[0].open_time,
            reference_price=bars[0].close, stop_price=Decimal("90"),
            target_price=Decimal("200"), planned_risk_reward=3.0,
            window_bars=30, costs=FRICTIONLESS_COSTS, policy=policy,
            timeline=timeline,
        ).trade

    def test_a_stop_out_is_not_a_mechanism_firing(self) -> None:
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "101", "85", "88"),
        )
        trade = self._run(bars, GIVEBACK)
        assert trade.exit_reason is LabExitReason.STOP
        assert trade.exit_reason not in {
            LabExitReason.THESIS_INVALIDATED,
            LabExitReason.STAGNATION,
            LabExitReason.GIVEBACK,
        }

    def test_a_time_stop_is_not_a_mechanism_firing(self) -> None:
        flat = tuple(_bar(i, "100", "101", "99", "100") for i in range(6))
        trade = self._run(flat, GIVEBACK)
        assert trade.exit_reason is LabExitReason.TIME_STOP

    def test_a_target_is_not_a_mechanism_firing(self) -> None:
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "210", "99", "205"),
        )
        assert self._run(bars, GIVEBACK).exit_reason is LabExitReason.TARGET

    def test_each_mechanism_names_itself_when_it_does_fire(self) -> None:
        """Three different findings, three different labels."""
        timeline = ThesisTimeline(
            symbol="BTCUSDT",
            observations={
                0: _observation(0),
                1: _observation(1, setup_structural_trend="sustained_lower",
                                execution_structural_trend="sustained_lower"),
                2: _observation(2),
            },
        )
        drift = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "108", "99", "106"),
            _bar(2, "106", "107", "105", "106"),
        )
        assert self._run(drift, THESIS, timeline).exit_reason is (
            LabExitReason.THESIS_INVALIDATED
        )
        flat = tuple(_bar(i, "100", "101", "99", "100") for i in range(20))
        assert self._run(flat, STAGNATION).exit_reason is LabExitReason.STAGNATION


class TestTheComparableColumnIsAnIntersection:
    """`study:the-comparable-column-uses-the-union-not-the-intersection`.

    The like-for-like column must re-measure over the setups **all** families
    could measure. A union would include setups some family could not measure,
    which is the opposite of like-for-like.
    """

    @staticmethod
    def _trade(setup_id: str, net: str | None) -> object:
        from fmis.swing_lab.models import LabTrade

        return LabTrade(
            variant_id="v", symbol="BTCUSDT", setup_id=setup_id,
            direction=Direction.LONG, signal_at=T0, entry_at=T0,
            entry_price=Decimal("100"), initial_stop=Decimal("90"),
            target=Decimal("200"), planned_reference_price=Decimal("100"),
            exit_at=T0 + FOUR_HOURS,
            exit_price=None if net is None else Decimal("110"),
            exit_reason=(
                LabExitReason.AMBIGUOUS_SAME_BAR if net is None
                else LabExitReason.TARGET
            ),
            bars_held=1,
            gross_r=None if net is None else Decimal(net),
            net_r=None if net is None else Decimal(net),
            mfe_r=Decimal("1"), mae_r=Decimal("0"),
            cost_policy_id="swing-lab-conservative-10bps",
            planned_risk_reward=3.0, segment=None,
            context_regime_structure="trending",
            context_structural_trend="sustained_higher",
            setup_structural_trend="sustained_higher",
        )

    def _measurement(self, policy_id: str, trades) -> FamilyMeasurement:
        frozen = tuple(trades)
        return FamilyMeasurement(
            policy_id=policy_id, hypothesis_id="BZ-H0",
            geometry_policy_id="geom_production", sample="development",
            cost_policy_id="swing-lab-conservative-10bps", trades=frozen,
            metrics=compute_lab_metrics(frozen, label=policy_id),
            fired=0, ambiguous=0, exit_reasons=(),
        )

    def test_a_setup_one_family_could_not_measure_is_excluded(self) -> None:
        control = self._measurement(
            "bz_exit_control",
            [self._trade("a", "1"), self._trade("b", "-1")],
        )
        # The managed family could not measure setup 'b' — it went ambiguous.
        managed = self._measurement(
            "bz_exit_giveback_half",
            [self._trade("a", "1"), self._trade("b", None)],
        )
        comparison = compare_families(
            [control, managed], control_policy_id="bz_exit_control"
        )
        assert comparison.shared_setups == 1
        for item in comparison.measurements:
            assert item.comparable_metrics is not None
            assert item.comparable_metrics.measurable_trades == 1

    def test_the_control_loses_its_advantage_in_the_comparable_column(self) -> None:
        """**The precise flattery the column exists to remove.**

        Both families measure the same twenty-five winners. The control
        additionally keeps a −1R loser that the managed family dropped as
        ambiguous. Raw, the managed family looks better purely because its worst
        trade vanished; like-for-like — over the setups both could measure — the
        two are exactly equal, and the improvement is zero rather than positive.
        """
        shared = [self._trade(f"s{i}", "1") for i in range(25)]
        control = self._measurement(
            "bz_exit_control", [*shared, self._trade("bad", "-1")]
        )
        managed = self._measurement(
            "bz_exit_giveback_half", [*shared, self._trade("bad", None)]
        )
        comparison = compare_families(
            [control, managed], control_policy_id="bz_exit_control"
        )
        assert comparison.shared_setups == 25
        # Raw, the managed family looks better...
        raw_control = control.metrics.expectancy_r.value
        raw_managed = managed.metrics.expectancy_r.value
        assert raw_managed > raw_control
        # ...and like-for-like the advantage is entirely gone.
        assert comparison.improvement("bz_exit_giveback_half") == Decimal("0")

    def test_no_shared_setup_yields_an_empty_comparable_column(self) -> None:
        control = self._measurement("bz_exit_control", [self._trade("a", "1")])
        managed = self._measurement(
            "bz_exit_giveback_half", [self._trade("b", "1")]
        )
        comparison = compare_families(
            [control, managed], control_policy_id="bz_exit_control"
        )
        assert comparison.shared_setups == 0
        assert comparison.improvement("bz_exit_giveback_half") is None

    def test_an_unmeasurable_improvement_is_none_never_zero(self) -> None:
        """'No improvement' and 'unmeasurable' are different findings."""
        control = self._measurement("bz_exit_control", [])
        managed = self._measurement("bz_exit_giveback_half", [])
        comparison = compare_families(
            [control, managed], control_policy_id="bz_exit_control"
        )
        assert comparison.improvement("bz_exit_giveback_half") is None


class TestTheVerdictOrder:
    """`study:a-failed-criterion-is-reported-as-inconclusive`.

    A genuine failure must never be reported as merely inconclusive. REJECTED is
    checked before INCONCLUSIVE, and that order is the claim.
    """

    def _comparison(self, control_r: str, family_r: str) -> FamilyComparison:
        from fmis.swing_lab.models import LabTrade

        def trades(policy_id: str, value: str):
            return tuple(
                LabTrade(
                    variant_id=policy_id, symbol="BTCUSDT", setup_id=f"s{i}",
                    direction=Direction.LONG, signal_at=T0, entry_at=T0,
                    entry_price=Decimal("100"), initial_stop=Decimal("90"),
                    target=Decimal("200"), planned_reference_price=Decimal("100"),
                    exit_at=T0 + FOUR_HOURS, exit_price=Decimal("110"),
                    exit_reason=LabExitReason.TARGET, bars_held=1,
                    gross_r=Decimal(value), net_r=Decimal(value),
                    mfe_r=Decimal("1"), mae_r=Decimal("0"),
                    cost_policy_id="swing-lab-conservative-10bps",
                    planned_risk_reward=3.0, segment=None,
                    context_regime_structure="trending",
                    context_structural_trend="sustained_higher",
                    setup_structural_trend="sustained_higher",
                )
                for i in range(25)
            )

        def measurement(policy_id: str, value: str) -> FamilyMeasurement:
            frozen = trades(policy_id, value)
            return FamilyMeasurement(
                policy_id=policy_id, hypothesis_id="BZ-H1",
                geometry_policy_id="geom_production", sample="development",
                cost_policy_id="swing-lab-conservative-10bps", trades=frozen,
                metrics=compute_lab_metrics(frozen, label=policy_id),
                fired=1, ambiguous=0, exit_reasons=(),
            )

        return compare_families(
            [
                measurement("bz_exit_control", control_r),
                measurement("bz_exit_thesis_failure", family_r),
            ],
            control_policy_id="bz_exit_control",
        )

    def test_a_family_that_does_not_improve_is_rejected_not_inconclusive(self) -> None:
        comparison = self._comparison("1", "1")   # zero improvement
        assessment = assess_bz(
            "bz_exit_thesis_failure",
            geometry_policy_id="geom_production",
            comparisons={"development": comparison},
            causal_proven=True, robust=True, ambiguity_decisive=False,
        )
        assert assessment.verdict is BzVerdict.REJECTED
        assert "improves_development" in assessment.failed

    def test_an_unopened_holdout_is_inconclusive_never_rejected(self) -> None:
        """**Defect BZ-D1.** A sample that was never run is not evidence against.

        The sealed classification rules say a below-floor sample means "the test
        could not be run, which is NOT a pass" — INCONCLUSIVE. Reporting it as
        REJECTED would claim evidence against a hypothesis nobody measured, and
        would make a development-only pass look like a refutation.
        """
        comparison = self._comparison("1", "2")   # +1R improvement, clears the bar
        assessment = assess_bz(
            "bz_exit_thesis_failure",
            geometry_policy_id="geom_production",
            comparisons={"development": comparison},
            causal_proven=True, robust=True, ambiguity_decisive=False,
        )
        # validation and holdout were never measured, so they are unmeasurable.
        assert assessment.verdict is BzVerdict.INCONCLUSIVE

    def test_a_failure_outranks_an_unmeasurable_criterion(self) -> None:
        """Both present: the FAILURE decides. This is the mutant's target."""
        comparison = self._comparison("1", "1")
        assessment = assess_bz(
            "bz_exit_thesis_failure",
            geometry_policy_id="geom_production",
            comparisons={"development": comparison},
            causal_proven=True, robust=True, ambiguity_decisive=False,
        )
        criteria = assessment.mechanism_criteria
        assert any(item.passed is False for item in criteria)
        assert any(item.passed is None for item in criteria)
        assert assessment.verdict is BzVerdict.REJECTED

    def test_an_unproven_causal_claim_rejects(self) -> None:
        comparison = self._comparison("1", "2")
        assessment = assess_bz(
            "bz_exit_thesis_failure",
            geometry_policy_id="geom_production",
            comparisons={"development": comparison},
            causal_proven=False, robust=True, ambiguity_decisive=False,
        )
        assert assessment.verdict is BzVerdict.REJECTED
        assert "causal" in assessment.failed


class TestTheGivebackAddsNoWatchedLevel:
    """`exits:bys-arming-set-silently-gains-a-bz-mechanic`.

    BZ's give-back arms from the running peak at a bar's close. It must NOT
    appear in the level-arming set, or it would put a price in `_State.levels()`
    that nothing ever resolves against — and would multiply ambiguity exactly the
    way Milestone BY's +1R arming level did.
    """

    def test_no_bz_mechanic_arms_a_watched_level(self) -> None:
        for mechanic in (
            ExitMechanic.THESIS_FAILURE,
            ExitMechanic.STAGNATION,
            ExitMechanic.GIVEBACK_FRACTION,
            ExitMechanic.STRUCTURAL_TRAIL,
            ExitMechanic.THESIS_AND_GIVEBACK,
        ):
            assert not mechanic.arms, f"{mechanic.value} arms a watched level"

    def test_every_by_managed_mechanic_still_arms(self) -> None:
        for mechanic in (
            ExitMechanic.PARTIAL_AT_1R,
            ExitMechanic.BREAK_EVEN_AT_1R,
            ExitMechanic.TRAIL_PRIOR_BAR_EXTREME,
        ):
            assert mechanic.arms
        assert not ExitMechanic.FULL_TARGET.arms

    def test_a_giveback_bar_that_would_collide_stays_unambiguous(self) -> None:
        """**The observable consequence.** A third level would make this ambiguous.

        The bar runs through +1R (the give-back arming excursion) and then to the
        target. With a watched arming level this is a two-level collision; without
        one it is a clean target.
        """
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "210", "99", "205"),
        )
        trade = simulate_managed_trade(
            bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=1, entry_price=bars[1].open,
            entry_at=bars[1].open_time, signal_at=bars[0].open_time,
            reference_price=bars[0].close, stop_price=Decimal("90"),
            target_price=Decimal("200"), planned_risk_reward=3.0,
            window_bars=10, costs=FRICTIONLESS_COSTS, policy=GIVEBACK,
        ).trade
        assert trade.exit_reason is LabExitReason.TARGET
        assert trade.is_measurable

    def test_the_decides_on_close_set_is_exactly_bzs(self) -> None:
        assert not ExitMechanic.FULL_TARGET.decides_on_close
        assert not ExitMechanic.PARTIAL_AT_1R.decides_on_close
        assert ExitMechanic.THESIS_FAILURE.decides_on_close
        assert ExitMechanic.GIVEBACK_FRACTION.decides_on_close


class TestTheTrailNeverFallsBackToAPrice:
    """`exits:trail-falls-back-to-a-price-when-structure-is-absent`.

    A structural trail with no confirmed structure must move nothing. Returning
    the bar's close instead would make it a *price* trail wearing a structural
    rule's name — exactly what Milestone BY labelled `exit_trail_prior_bar` as
    NOT being.

    The gap the first mutation run exposed: every existing test supplied an
    observation that EXISTED but held no levels, so the ``observation is None``
    branch — a genuine gap in the timeline — was never walked.
    """

    def _run(self, bars, timeline):
        return simulate_managed_trade(
            bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=1, entry_price=bars[1].open,
            entry_at=bars[1].open_time, signal_at=bars[0].open_time,
            reference_price=bars[0].close, stop_price=Decimal("90"),
            target_price=Decimal("200"), planned_risk_reward=3.0,
            window_bars=30, costs=FRICTIONLESS_COSTS, policy=TRAIL,
            timeline=timeline,
        ).trade

    def test_a_gap_in_the_timeline_moves_no_stop(self) -> None:
        """The observation is ABSENT, not merely empty. The stop must not move."""
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "108", "99", "106"),
            _bar(2, "106", "120", "105", "118"),
            _bar(3, "118", "119", "112", "114"),
            _bar(4, "114", "116", "95", "97"),
        )
        # Only the entry bar has an observation; bars 1-4 are gaps.
        timeline = ThesisTimeline(
            symbol="BTCUSDT", observations={0: _observation(0)}
        )
        trade = self._run(bars, timeline)
        # Had the trail fallen back to each bar's close, the stop would have been
        # dragged up to ~114 and this would have stopped out well above 90.
        assert trade.exit_reason is LabExitReason.TIME_STOP
        assert trade.initial_stop == Decimal("90")

    def test_a_gap_does_not_stop_a_position_out_at_its_own_close(self) -> None:
        """The sharpest form: a falling bar whose close is above the real stop."""
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "108", "99", "106"),
            _bar(2, "106", "107", "104", "105"),
            _bar(3, "105", "106", "103", "104"),
        )
        timeline = ThesisTimeline(
            symbol="BTCUSDT", observations={0: _observation(0)}
        )
        trade = self._run(bars, timeline)
        assert trade.exit_reason is LabExitReason.TIME_STOP
        assert trade.exit_price == Decimal("104")


class TestAFamilyIsMeasuredOnOneSampleOnly:
    """`study:a-family-is-measured-on-every-sample-at-once`.

    A measurement labelled `development` must contain development trades and
    nothing else. Dropping the sample filter would pool every sample into every
    cell — Milestone BY defect BY-D6's failure mode, one layer lower — and every
    per-sample expectancy would silently describe the whole universe.
    """

    def test_only_the_named_samples_candidates_are_measured(self) -> None:
        from datetime import datetime as _dt

        from fmis.swing_lab.geometry_replay import GeometryCapture
        from fmis.swing_lab.geometry_variants import PRODUCTION_GEOMETRY
        from fmis.swing_lab.persistence_study import measure_family
        from fmis.swing_lab.trades import CONSERVATIVE_COSTS

        from tests.swing_lab_helpers import candidate

        early = candidate(
            symbol="BTCUSDT", setup_id="early",
            signal_at=_dt(2024, 1, 1, tzinfo=_UTC), signal_index=1,
        )
        late = candidate(
            symbol="BTCUSDT", setup_id="late",
            signal_at=_dt(2026, 1, 1, tzinfo=_UTC), signal_index=1,
        )
        bars = tuple(
            PriceBar(
                symbol="BTCUSDT", interval="4h",
                open_time=T0 + FOUR_HOURS * i,
                open=Decimal("100"), high=Decimal("104"),
                low=Decimal("97"), close=Decimal("101"),
            )
            for i in range(20)
        )
        capture = GeometryCapture(
            admission_variant_id="v", admission_policy_id="p",
            candidates=(early, late), bars_by_symbol={"BTCUSDT": bars},
        )

        class _Spec:
            def __init__(self, name: str) -> None:
                self.name = name

        def sample_of(symbol: str, signal_at):
            return _Spec("development" if signal_at.year == 2024 else "validation")

        development = measure_family(
            capture, geometry=PRODUCTION_GEOMETRY, policy=CONTROL,
            hypothesis_id="BZ-H0", timelines={}, ladders=None,
            sample_of=sample_of, sample_name="development",
            costs=CONSERVATIVE_COSTS, evaluation_window_bars=10,
        )
        validation = measure_family(
            capture, geometry=PRODUCTION_GEOMETRY, policy=CONTROL,
            hypothesis_id="BZ-H0", timelines={}, ladders=None,
            sample_of=sample_of, sample_name="validation",
            costs=CONSERVATIVE_COSTS, evaluation_window_bars=10,
        )
        assert {t.setup_id for t in development.trades} == {"early"}
        assert {t.setup_id for t in validation.trades} == {"late"}
        assert development.sample == "development"
        assert validation.sample == "validation"

    def test_a_candidate_in_no_sample_is_measured_nowhere(self) -> None:
        from datetime import datetime as _dt

        from fmis.swing_lab.geometry_replay import GeometryCapture
        from fmis.swing_lab.geometry_variants import PRODUCTION_GEOMETRY
        from fmis.swing_lab.persistence_study import measure_family
        from fmis.swing_lab.trades import CONSERVATIVE_COSTS

        from tests.swing_lab_helpers import candidate

        orphan = candidate(symbol="BTCUSDT", setup_id="orphan", signal_index=1)
        bars = tuple(
            PriceBar(
                symbol="BTCUSDT", interval="4h",
                open_time=T0 + FOUR_HOURS * i,
                open=Decimal("100"), high=Decimal("104"),
                low=Decimal("97"), close=Decimal("101"),
            )
            for i in range(20)
        )
        capture = GeometryCapture(
            admission_variant_id="v", admission_policy_id="p",
            candidates=(orphan,), bars_by_symbol={"BTCUSDT": bars},
        )
        measurement = measure_family(
            capture, geometry=PRODUCTION_GEOMETRY, policy=CONTROL,
            hypothesis_id="BZ-H0", timelines={}, ladders=None,
            sample_of=lambda symbol, at: None, sample_name="development",
            costs=CONSERVATIVE_COSTS, evaluation_window_bars=10,
        )
        assert measurement.trades == ()


class TestTheFiredCounterIsTheMechanism:
    """`study:a-mechanism-that-never-fired-is-counted-as-firing`.

    The counter lives in `measure_family`, so it needs a measurement to test —
    asserting an exit reason alone leaves the tally itself uncovered.
    """

    @staticmethod
    def _capture(bars):
        from fmis.swing_lab.geometry_replay import GeometryCapture

        from tests.swing_lab_helpers import candidate

        return GeometryCapture(
            admission_variant_id="v", admission_policy_id="p",
            candidates=(candidate(setup_id="only", signal_index=1),),
            bars_by_symbol={"BTCUSDT": bars},
        )

    @staticmethod
    def _measure(capture, policy):
        from fmis.swing_lab.geometry_variants import PRODUCTION_GEOMETRY
        from fmis.swing_lab.persistence_study import measure_family
        from fmis.swing_lab.trades import CONSERVATIVE_COSTS

        class _Spec:
            name = "development"

        return measure_family(
            capture, geometry=PRODUCTION_GEOMETRY, policy=policy,
            hypothesis_id="BZ-H0", timelines={}, ladders=None,
            sample_of=lambda symbol, at: _Spec(), sample_name="development",
            costs=CONSERVATIVE_COSTS, evaluation_window_bars=40,
        )

    def _flat(self, count: int = 30):
        return tuple(
            PriceBar(
                symbol="BTCUSDT", interval="4h",
                open_time=T0 + FOUR_HOURS * i,
                open=Decimal("100"), high=Decimal("100.5"),
                low=Decimal("99.5"), close=Decimal("100"),
            )
            for i in range(count)
        )

    def test_a_stagnant_position_counts_one_firing(self) -> None:
        capture = self._capture(self._flat())
        measurement = self._measure(capture, STAGNATION)
        assert measurement.trades
        assert measurement.trades[0].exit_reason is LabExitReason.STAGNATION
        assert measurement.fired == 1

    def test_the_control_never_fires(self) -> None:
        """**The mutant's target.** An inverted tally would report 1 here."""
        capture = self._capture(self._flat())
        measurement = self._measure(capture, CONTROL)
        assert measurement.fired == 0

    def test_a_giveback_that_never_armed_never_fires(self) -> None:
        capture = self._capture(self._flat())
        measurement = self._measure(capture, GIVEBACK)
        assert measurement.fired == 0
        assert measurement.trades[0].exit_reason is LabExitReason.TIME_STOP


class TestTheQuantileConvention:
    """`study:a-quantile-interpolates-between-two-real-trades`, tightened.

    The first run's probe survived because both the original and the mutant are
    *nearest-rank* rules that happen to agree on every sample the earlier tests
    used. They disagree at n=8, p75 — so the convention is pinned there, because
    a reported p75 that silently moves by one rank between two milestones is a
    figure two reports would state differently.
    """

    def test_the_p75_convention_is_pinned_at_eight_samples(self) -> None:
        values = [Decimal(str(v)) for v in (1, 2, 3, 4, 5, 6, 7, 8)]
        assert _quantile(values, 0.75) == Decimal("6")

    def test_the_p25_convention_is_pinned_at_eight_samples(self) -> None:
        values = [Decimal(str(v)) for v in (1, 2, 3, 4, 5, 6, 7, 8)]
        assert _quantile(values, 0.25) == Decimal("3")


class TestTheCombinationKeepsItsComponentsThresholds:
    """`exits:the-combination-loosens-one-of-its-components`.

    H5 composes H1 and H3 **unchanged and at their own declared thresholds**.
    Loosening either inside the combination would make it a different rule from
    the one the pre-registration sealed, while still carrying its id.
    """

    def test_the_combination_does_not_arm_below_its_components_threshold(self) -> None:
        combination = exit_policy_by_id("bz_exit_thesis_and_giveback")
        assert combination.giveback_arm_r == GIVEBACK.giveback_arm_r
        assert combination.giveback_fraction == GIVEBACK.giveback_fraction

        timeline = ThesisTimeline(
            symbol="BTCUSDT",
            observations={i: _observation(i) for i in range(6)},
        )
        # Peak is only +0.5R, well under the +1R arm; a loosened arm would fire.
        small = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "105", "99", "104"),
            _bar(2, "104", "105", "99", "100"),
            _bar(3, "100", "101", "99", "100"),
            _bar(4, "100", "101", "99", "100"),
            _bar(5, "100", "101", "99", "100"),
        )
        trade = simulate_managed_trade(
            small, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=1, entry_price=small[1].open,
            entry_at=small[1].open_time, signal_at=small[0].open_time,
            reference_price=small[0].close, stop_price=Decimal("90"),
            target_price=Decimal("200"), planned_risk_reward=3.0,
            window_bars=30, costs=FRICTIONLESS_COSTS, policy=combination,
            timeline=timeline,
        ).trade
        assert trade.exit_reason is LabExitReason.TIME_STOP


class TestObserveAllPaths:
    """The bridge from a capture to the causal path dataset.

    Covered offline because the only other exercise it gets is the real capture,
    and a function whose sole test is an hour-long network run is a function
    nobody can iterate on.
    """

    @staticmethod
    def _capture(*candidates, bars=None):
        from fmis.swing_lab.geometry_replay import GeometryCapture

        rows = bars or tuple(
            PriceBar(
                symbol="BTCUSDT", interval="4h",
                open_time=T0 + FOUR_HOURS * i,
                open=Decimal("100"), high=Decimal("104"),
                low=Decimal("97"), close=Decimal("101"),
            )
            for i in range(20)
        )
        return GeometryCapture(
            admission_variant_id="v", admission_policy_id="p",
            candidates=candidates, bars_by_symbol={"BTCUSDT": rows},
        )

    @staticmethod
    def _observe(capture, sample_of=None, timelines=None):
        from fmis.swing_lab.geometry_variants import PRODUCTION_GEOMETRY
        from fmis.swing_lab.persistence_study import observe_all_paths

        class _Spec:
            name = "development"

        return observe_all_paths(
            capture,
            geometry=PRODUCTION_GEOMETRY,
            timelines=timelines or {},
            sample_of=sample_of or (lambda symbol, at: _Spec()),
            evaluation_window_bars=10,
        )

    def test_one_path_per_opened_position(self) -> None:
        from tests.swing_lab_helpers import candidate

        tracks = self._observe(
            self._capture(
                candidate(setup_id="a", signal_index=1),
                candidate(setup_id="b", signal_index=2),
            )
        )
        assert {t.setup_id for t in tracks} == {"a", "b"}
        assert all(t.sample == "development" for t in tracks)
        assert all(t.checkpoints for t in tracks)

    def test_a_candidate_in_no_sample_yields_no_path(self) -> None:
        from tests.swing_lab_helpers import candidate

        tracks = self._observe(
            self._capture(candidate(setup_id="orphan", signal_index=1)),
            sample_of=lambda symbol, at: None,
        )
        assert tracks == ()

    def test_a_candidate_with_no_entry_bar_yields_no_path(self) -> None:
        """History ran out. A dataset shortfall is not a flat trade."""
        from tests.swing_lab_helpers import candidate

        short = tuple(
            PriceBar(
                symbol="BTCUSDT", interval="4h",
                open_time=T0 + FOUR_HOURS * i,
                open=Decimal("100"), high=Decimal("104"),
                low=Decimal("97"), close=Decimal("101"),
            )
            for i in range(3)
        )
        tracks = self._observe(
            self._capture(candidate(setup_id="late", signal_index=2), bars=short)
        )
        assert tracks == ()

    def test_a_position_opening_beyond_its_stop_yields_no_path(self) -> None:
        """No risk denominator means no path to observe — a stated absence."""
        from tests.swing_lab_helpers import candidate

        gapped = (
            PriceBar(
                symbol="BTCUSDT", interval="4h", open_time=T0,
                open=Decimal("100"), high=Decimal("104"),
                low=Decimal("97"), close=Decimal("101"),
            ),
            # The entry bar opens far below the production stop at ~98.
            PriceBar(
                symbol="BTCUSDT", interval="4h", open_time=T0 + FOUR_HOURS,
                open=Decimal("50"), high=Decimal("52"),
                low=Decimal("48"), close=Decimal("51"),
            ),
        ) + tuple(
            PriceBar(
                symbol="BTCUSDT", interval="4h",
                open_time=T0 + FOUR_HOURS * i,
                open=Decimal("51"), high=Decimal("53"),
                low=Decimal("49"), close=Decimal("52"),
            )
            for i in range(2, 10)
        )
        tracks = self._observe(
            self._capture(candidate(setup_id="gapped", signal_index=0), bars=gapped)
        )
        assert tracks == ()

    def test_the_timeline_reaches_the_checkpoints(self) -> None:
        from tests.swing_lab_helpers import candidate

        timeline = ThesisTimeline(
            symbol="BTCUSDT",
            observations={i: _observation(i) for i in range(20)},
        )
        tracks = self._observe(
            self._capture(candidate(setup_id="a", signal_index=1)),
            timelines={"BTCUSDT": timeline},
        )
        assert tracks
        assert tracks[0].entry_thesis_known
        assert tracks[0].checkpoints[0].thesis.is_known
