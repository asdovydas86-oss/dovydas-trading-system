"""The verdict rules, in their sealed order — and what each one refuses.

The ordering assertion is the important one. Calibration is read first and
short-circuits everything after it, so a study whose estimator failed its
synthetic check can never report `MEASURED` however clean its real numbers look.
That is Milestone CC's lesson made executable, and a test that only checked the
happy path would not notice if the order were reversed.
"""

from __future__ import annotations

import pytest

from fmis.paired_dependence.integration import assess_requirement
from fmis.paired_dependence.models import (
    DependenceVerdict,
    GroupingAxis,
    PairedDependenceError,
)
from fmis.paired_dependence.uncertainty import bootstrap_interval
from fmis.paired_dependence.verdict import (
    CalibrationOutcome,
    CalibrationReading,
    FloorReading,
    assess_cd,
    calibrate,
    check_floors,
)
from paired_dependence_helpers import panel

BLOCK = GroupingAxis.TIME_BLOCK
ASSET = GroupingAxis.ECONOMIC_ASSET


def _interval(axis=BLOCK, rows=None):
    return bootstrap_interval(
        rows if rows is not None else panel(market=1.0),
        axis=axis,
        resample_axis=axis,
        block_bars=60,
        draws=100,
        confidence=0.95,
        master_seed=1,
        identity=["test"],
    )


def _calibration(passed=True, ordering=True):
    return CalibrationOutcome(
        readings=(
            CalibrationReading(
                scenario_id="independent", axis=BLOCK, expected=0.0,
                mean_estimate=0.0 if passed else 0.9, tolerance=0.07,
                replicates=25, within_tolerance=passed,
            ),
        ),
        ordering_reproduced=ordering,
        ordering_detail=(("independent", 0.0),),
        passed=passed and ordering,
        reasoning="synthetic",
    )


def _floors(met=True):
    return (FloorReading(name="economic_assets", required=3, observed=12 if met else 1, met=met),)


class TestCalibrate:
    def test_the_real_calibration_passes_at_the_sealed_settings(self):
        from fmis.paired_dependence.preregistration import (
            CALIBRATION_REPLICATES,
            CD_MASTER_SEED,
            PRIMARY_BLOCK_BARS,
        )

        outcome = calibrate(
            replicates=CALIBRATION_REPLICATES,
            block_bars=PRIMARY_BLOCK_BARS,
            master_seed=CD_MASTER_SEED,
        )
        assert outcome.passed, outcome.reasoning
        assert outcome.ordering_reproduced
        assert outcome.failures == ()

    def test_scenarios_with_no_point_expectation_cannot_fail_it(self):
        from fmis.paired_dependence.preregistration import CD_MASTER_SEED

        outcome = calibrate(replicates=3, block_bars=60, master_seed=CD_MASTER_SEED)
        undecidable = [
            item
            for item in outcome.readings
            if item.scenario_id in ("unequal_observations", "non_exchangeable_blocks")
        ]
        assert undecidable
        assert all(item.within_tolerance is None for item in undecidable)

    def test_the_readings_carry_their_deviation(self):
        from fmis.paired_dependence.preregistration import CD_MASTER_SEED

        outcome = calibrate(replicates=3, block_bars=60, master_seed=CD_MASTER_SEED)
        for item in outcome.readings:
            payload = item.payload()
            if payload["expected"] is not None and payload["mean_estimate"] is not None:
                assert payload["deviation"] == pytest.approx(
                    abs(payload["mean_estimate"] - payload["expected"])
                )


class TestCheckFloors:
    def test_every_pre_registered_floor_is_reported(self):
        rows = panel(market=1.0)
        from fmis.paired_dependence.observations import dependence_coverage_of

        readings = check_floors(
            dependence_coverage_of(rows, block_bars=60),
            _interval(BLOCK, rows),
            _interval(ASSET, rows),
            min_groups=10, min_members=30, min_economic_assets=3,
            min_informative_blocks=10,
        )
        assert {item.name for item in readings} == {
            "economic_assets", "informative_blocks", "between_asset_groups",
            "between_asset_members", "within_asset_groups", "within_asset_members",
        }

    def test_a_thin_panel_fails_its_floors(self):
        from fmis.paired_dependence.observations import dependence_coverage_of

        rows = panel(assets=2, blocks=3)
        readings = check_floors(
            dependence_coverage_of(rows, block_bars=60),
            _interval(BLOCK, rows),
            _interval(ASSET, rows),
            min_groups=10, min_members=30, min_economic_assets=3,
            min_informative_blocks=10,
        )
        assert any(not item.met for item in readings)


class TestVerdictOrdering:
    def _assess(self, *, calibration, floors, between, within, requirement):
        return assess_cd(
            calibration=calibration, floors=floors, between=between,
            within=within, requirement=requirement,
        )

    def test_a_failed_calibration_short_circuits_everything(self):
        # A panel and a requirement that would otherwise be MEASURED.
        requirement = assess_requirement(
            point=0.0, lower=0.0, upper=0.0, within_asset_correlation=0.0
        )
        assessment = self._assess(
            calibration=_calibration(passed=False),
            floors=_floors(met=True),
            between=_interval(BLOCK),
            within=_interval(ASSET),
            requirement=requirement,
        )
        assert assessment.verdict is DependenceVerdict.INVALID_ESTIMATOR
        assert "may be read" in assessment.reasoning

    def test_a_scrambled_ordering_also_invalidates_the_estimator(self):
        requirement = assess_requirement(
            point=0.0, lower=0.0, upper=0.0, within_asset_correlation=0.0
        )
        assessment = self._assess(
            calibration=_calibration(passed=True, ordering=False),
            floors=_floors(met=True),
            between=_interval(BLOCK),
            within=_interval(ASSET),
            requirement=requirement,
        )
        assert assessment.verdict is DependenceVerdict.INVALID_ESTIMATOR

    def test_an_unmet_floor_is_inconclusive_and_names_the_floor(self):
        requirement = assess_requirement(
            point=0.0, lower=0.0, upper=0.0, within_asset_correlation=0.0
        )
        assessment = self._assess(
            calibration=_calibration(),
            floors=_floors(met=False),
            between=_interval(BLOCK),
            within=_interval(ASSET),
            requirement=requirement,
        )
        assert assessment.verdict is DependenceVerdict.INCONCLUSIVE
        assert "economic_assets" in assessment.reasoning
        assert assessment.unmet_floors == ("economic_assets",)

    def test_a_straddling_interval_is_inconclusive(self):
        requirement = assess_requirement(
            point=0.02, lower=-0.05, upper=0.20, within_asset_correlation=0.0
        )
        assessment = self._assess(
            calibration=_calibration(),
            floors=_floors(),
            between=_interval(BLOCK),
            within=_interval(ASSET),
            requirement=requirement,
        )
        assert assessment.verdict is DependenceVerdict.INCONCLUSIVE
        assert "unreachable at any universe size" in assessment.reasoning

    def test_a_wide_but_finite_range_is_weakly_identified(self):
        requirement = assess_requirement(
            point=0.0010, lower=0.0000, upper=0.0020, within_asset_correlation=0.0
        )
        assert requirement.order_of_magnitude_span > 10.0
        assessment = self._assess(
            calibration=_calibration(),
            floors=_floors(),
            between=_interval(BLOCK),
            within=_interval(ASSET),
            requirement=requirement,
        )
        assert assessment.verdict is DependenceVerdict.WEAKLY_IDENTIFIED

    def test_one_unreachable_bound_is_weakly_identified(self):
        # The lower bound is strictly positive, so the interval does NOT straddle
        # zero-to-saturation and the straddle rule does not fire; the upper bound
        # is above the threshold, so no finite span exists.
        requirement = assess_requirement(
            point=0.0010, lower=0.0005, upper=0.0030, within_asset_correlation=0.0
        )
        assert requirement.order_of_magnitude_span is None
        assessment = self._assess(
            calibration=_calibration(),
            floors=_floors(),
            between=_interval(BLOCK),
            within=_interval(ASSET),
            requirement=requirement,
        )
        assert assessment.verdict is DependenceVerdict.WEAKLY_IDENTIFIED

    def test_a_tight_range_is_measured(self):
        requirement = assess_requirement(
            point=0.00005, lower=0.00000, upper=0.00010, within_asset_correlation=0.0
        )
        assert requirement.order_of_magnitude_span <= 10.0
        assessment = self._assess(
            calibration=_calibration(),
            floors=_floors(),
            between=_interval(BLOCK),
            within=_interval(ASSET),
            requirement=requirement,
        )
        assert assessment.verdict is DependenceVerdict.MEASURED

    def test_a_refused_interval_is_inconclusive(self):
        from paired_dependence_helpers import row

        thin = _interval(BLOCK, rows=[row(difference=1.0, symbol="AAAUSDT", bar_index=0)])
        requirement = assess_requirement(
            point=None, lower=None, upper=None, within_asset_correlation=None
        )
        assessment = self._assess(
            calibration=_calibration(),
            floors=_floors(),
            between=thin,
            within=_interval(ASSET),
            requirement=requirement,
        )
        assert assessment.verdict is DependenceVerdict.INCONCLUSIVE


class TestRefusals:
    def test_a_foreign_calibration_is_refused(self):
        with pytest.raises(PairedDependenceError):
            assess_cd(
                calibration=object(), floors=(), between=_interval(BLOCK),
                within=_interval(ASSET),
                requirement=assess_requirement(
                    point=0.0, lower=0.0, upper=0.0, within_asset_correlation=None
                ),
            )

    def test_a_foreign_interval_is_refused(self):
        with pytest.raises(PairedDependenceError):
            assess_cd(
                calibration=_calibration(), floors=(), between=object(),
                within=_interval(ASSET),
                requirement=assess_requirement(
                    point=0.0, lower=0.0, upper=0.0, within_asset_correlation=None
                ),
            )

    def test_a_foreign_requirement_is_refused(self):
        with pytest.raises(PairedDependenceError):
            assess_cd(
                calibration=_calibration(), floors=(), between=_interval(BLOCK),
                within=_interval(ASSET), requirement=object(),
            )


class TestNoVerdictApprovesAnything:
    def test_every_dependence_verdict_refuses_to_promote(self):
        for member in DependenceVerdict:
            assert member.is_approved_for_trading is False
            assert member.earns_forward_test is False
            assert member.says_nothing_about_the_hypothesis is True

    def test_only_the_two_strongest_are_usable_by_a_design(self):
        usable = {m for m in DependenceVerdict if m.is_usable_by_a_design}
        assert usable == {
            DependenceVerdict.MEASURED, DependenceVerdict.WEAKLY_IDENTIFIED
        }

    def test_the_assessment_payload_states_the_three_refusals(self):
        requirement = assess_requirement(
            point=0.0, lower=0.0, upper=0.0, within_asset_correlation=0.0
        )
        payload = assess_cd(
            calibration=_calibration(), floors=_floors(), between=_interval(BLOCK),
            within=_interval(ASSET), requirement=requirement,
        ).payload()
        assert payload["is_approved_for_trading"] is False
        assert payload["earns_forward_test"] is False
        assert payload["says_nothing_about_the_hypothesis"] is True


class TestMutationSurvivorRegressions:
    """Regressions added after a rule-level mutation probe survived.

    Both probes below attack the calibration gate, which is the single rule that
    stands between Milestone CC's failure and CD repeating it. A pinned estimator
    — one returning the same value at every true correlation, which is exactly
    what CC's residual estimator did — must FAIL calibration, and these assert it
    from the outside rather than trusting the comparison to be written correctly.
    """

    @staticmethod
    def _pinned(value):
        """An estimator that returns ``value`` whatever it is handed."""
        import fmis.paired_dependence.verdict as module
        from fmis.paired_dependence.estimator import VarianceComponents

        def constant(rows, *, axis, block_bars, reduction=None, weighting=None):
            return VarianceComponents(
                axis=axis, groups=10, members=30, groups_with_multiple=10,
                degrees_between=9, degrees_within=20, mean_square_between=1.0,
                mean_square_within=1.0, k0=3.0, between_variance=0.0,
                within_variance=1.0, correlation=value, reason=None,
            )

        return module, constant

    def test_an_estimator_pinned_at_one_value_fails_the_ORDERING(self, monkeypatch):
        """Kills: `ordering allows ties`.

        Four scenarios with four different true correlations must produce four
        different means. An estimator returning one value for all of them — CC's
        exact failure mode — passes a `<=` ordering check and must not.
        """
        module, constant = self._pinned(0.25)
        monkeypatch.setattr(module, "estimate_on_axis", constant, raising=False)
        import fmis.paired_dependence.uncertainty as uncertainty

        monkeypatch.setattr(uncertainty, "estimate_on_axis", constant)
        outcome = calibrate(replicates=3, block_bars=60, master_seed=1)
        assert outcome.ordering_reproduced is False
        assert outcome.passed is False
        assert "ordering" in outcome.reasoning

    def test_an_estimator_that_misses_every_expectation_fails_the_TOLERANCE(
        self, monkeypatch
    ):
        """Kills: `calibration tolerance always passes`.

        A constant 0.9 is outside the 1/(K-1) tolerance of almost every
        scenario's stated expectation, so the tolerance comparison must record
        failures. If it cannot, the tolerance is decorative.
        """
        module, constant = self._pinned(0.9)
        monkeypatch.setattr(module, "estimate_on_axis", constant, raising=False)
        import fmis.paired_dependence.uncertainty as uncertainty

        monkeypatch.setattr(uncertainty, "estimate_on_axis", constant)
        outcome = calibrate(replicates=3, block_bars=60, master_seed=1)
        assert outcome.failures
        assert outcome.passed is False

    def test_NON_VACUITY_the_real_estimator_passes_both_gates(self):
        """What makes the two injections above tests rather than tautologies."""
        outcome = calibrate(replicates=3, block_bars=60, master_seed=1)
        assert outcome.ordering_reproduced is True
        assert outcome.failures == ()
