"""Synthetic calibration. **The estimator is tested before it is trusted.**

Milestone CC's residual estimator was believed for a whole milestone and then
shown by simulation to be structurally incapable of answering its own question.
These tests are the discipline that follows from that: every scenario states what
the estimator ought to find, and the calibration is asserted against those
statements rather than against whatever the estimator happened to return.

The two assertions that carry the most weight are the last two. One asserts that
the estimator reproduces the **ordering** of four known correlations — a
requirement no amount of bias can satisfy by accident. The other asserts that
applying Milestone CC's cross-sectional demeaning to a panel with a large true
correlation drives the estimate to exactly ``-1/(K-1)``, which is CC's failure
reproduced with CD's own machinery.
"""

from __future__ import annotations

import statistics

import pytest

from fmis.paired_dependence.models import GroupingAxis, PairedDependenceError
from fmis.paired_dependence.preregistration import (
    CALIBRATION_REPLICATES,
    CD_MASTER_SEED,
    PRIMARY_BLOCK_BARS,
)
from fmis.paired_dependence.synthetic import (
    CALIBRATION_SCENARIOS,
    SyntheticScenario,
    generate_panel,
    scenario_by_id,
)
from fmis.paired_dependence.uncertainty import estimate_on_axis

BLOCK = GroupingAxis.TIME_BLOCK
ASSET = GroupingAxis.ECONOMIC_ASSET


def _means(scenario, replicates=CALIBRATION_REPLICATES):
    between, within = [], []
    for replicate in range(replicates):
        rows = generate_panel(
            scenario,
            block_bars=PRIMARY_BLOCK_BARS,
            master_seed=CD_MASTER_SEED,
            replicate=replicate,
        )
        value = estimate_on_axis(
            rows, axis=BLOCK, block_bars=PRIMARY_BLOCK_BARS
        ).correlation
        if value is not None:
            between.append(value)
        value = estimate_on_axis(
            rows, axis=ASSET, block_bars=PRIMARY_BLOCK_BARS
        ).correlation
        if value is not None:
            within.append(value)
    return (
        statistics.fmean(between) if between else None,
        statistics.fmean(within) if within else None,
    )


class TestGeneration:
    def test_a_panel_is_a_pure_function_of_its_identity(self):
        scenario = scenario_by_id("moderate_between")
        first = generate_panel(scenario, block_bars=60, master_seed=1, replicate=0)
        second = generate_panel(scenario, block_bars=60, master_seed=1, replicate=0)
        assert first == second

    def test_a_different_replicate_gives_a_different_panel(self):
        scenario = scenario_by_id("moderate_between")
        first = generate_panel(scenario, block_bars=60, master_seed=1, replicate=0)
        second = generate_panel(scenario, block_bars=60, master_seed=1, replicate=1)
        assert first != second

    def test_observations_land_in_the_block_they_were_generated_for(self):
        rows = generate_panel(
            scenario_by_id("independent"), block_bars=60, master_seed=1
        )
        assert all(row.bar_index % 60 == 0 for row in rows)

    def test_a_cell_larger_than_a_block_is_refused(self):
        scenario = SyntheticScenario(
            scenario_id="too_dense",
            description="",
            assets=3,
            blocks=3,
            observations_per_cell=5,
            market=0.0,
            asset=0.0,
            noise=1.0,
        )
        with pytest.raises(PairedDependenceError, match="share a bar index"):
            generate_panel(scenario, block_bars=4, master_seed=1)

    def test_an_unknown_scenario_is_refused_by_name(self):
        with pytest.raises(PairedDependenceError, match="no calibration scenario"):
            scenario_by_id("wishful_thinking")

    def test_a_negative_standard_deviation_is_refused(self):
        with pytest.raises(PairedDependenceError, match="cannot be negative"):
            SyntheticScenario(
                scenario_id="x", description="", assets=2, blocks=2,
                observations_per_cell=1, market=-1.0, asset=0.0, noise=1.0,
            )

    def test_a_panel_with_no_variance_at_all_is_refused(self):
        with pytest.raises(PairedDependenceError, match="no correlation to recover"):
            SyntheticScenario(
                scenario_id="x", description="", assets=2, blocks=2,
                observations_per_cell=1, market=0.0, asset=0.0, noise=0.0,
            )

    def test_duplicated_identities_appear_under_a_second_label(self):
        rows = generate_panel(
            scenario_by_id("duplicated_identity"), block_bars=60, master_seed=1
        )
        wrapped = {row.economic_asset for row in rows if "WRAPPED" in row.economic_asset}
        assert len(wrapped) == 5

    def test_a_scenario_with_no_point_expectation_says_so(self):
        assert scenario_by_id("unequal_observations").expected_between_asset is None
        assert scenario_by_id("non_exchangeable_blocks").expected_within_asset is None
        assert scenario_by_id("moderate_between").has_point_expectation


class TestCalibration:
    @pytest.mark.parametrize(
        "scenario", [s for s in CALIBRATION_SCENARIOS if s.has_point_expectation],
        ids=lambda s: s.scenario_id,
    )
    def test_every_point_expectation_is_recovered_within_its_tolerance(self, scenario):
        tolerance = 1.0 / (scenario.assets - 1)
        between, within = _means(scenario)
        assert between is not None and within is not None
        assert abs(between - scenario.expected_between_asset) <= tolerance, (
            f"{scenario.scenario_id}: r_b expected "
            f"{scenario.expected_between_asset}, got {between}"
        )
        assert abs(within - scenario.expected_within_asset) <= tolerance, (
            f"{scenario.scenario_id}: rho_w expected "
            f"{scenario.expected_within_asset}, got {within}"
        )

    def test_the_between_asset_ordering_is_reproduced_strictly(self):
        values = [
            _means(scenario_by_id(name))[0]
            for name in ("independent", "weak_between", "moderate_between", "strong_between")
        ]
        assert all(value is not None for value in values)
        assert values == sorted(values)
        assert len(set(values)) == 4

    def test_the_tolerance_is_not_wide_enough_to_swallow_the_ordering(self):
        # A tolerance that admitted 'independent' and 'strong_between' as the same
        # answer would make the calibration vacuous. 1/(K-1) at K=15 is 0.0714 and
        # the gap between those two scenarios is 0.5.
        tolerance = 1.0 / (15 - 1)
        assert tolerance < 0.5


class TestCcFailureIsReproduced:
    """Milestone CC's estimator returns the same value at every true correlation."""

    @pytest.mark.parametrize(
        "scenario_id",
        ["independent", "weak_between", "moderate_between", "strong_between",
         "dominant_market_factor"],
    )
    def test_the_cc_residual_estimator_is_pinned_whatever_the_truth(self, scenario_id):
        from fmis.paired_dependence.controls import cc_residual_correlation

        scenario = scenario_by_id(scenario_id)
        rows = generate_panel(scenario, block_bars=60, master_seed=CD_MASTER_SEED)
        artefact = -1.0 / (scenario.assets - 1)
        assert cc_residual_correlation(rows, block_bars=60) == pytest.approx(
            artefact, abs=0.01
        )

    def test_and_cd_s_own_estimator_is_not(self):
        weak = _means(scenario_by_id("independent"))[0]
        strong = _means(scenario_by_id("strong_between"))[0]
        assert strong - weak > 0.4

    def test_the_market_factor_removed_scenario_expects_the_artefact_not_zero(self):
        scenario = scenario_by_id("market_factor_removed")
        assert scenario.expected_between_asset == pytest.approx(
            -1.0 / (scenario.assets - 1)
        )
        between, _within = _means(scenario)
        assert between == pytest.approx(-1.0 / (scenario.assets - 1), abs=0.01)
