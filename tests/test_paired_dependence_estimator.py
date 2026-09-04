"""The estimator's arithmetic, its refusals and its two axes.

The properties asserted here are the ones a reader has to be able to take on
trust for the rest of the milestone to mean anything: the ANOVA reduces to the
textbook balanced case, the weighted form reduces to the unweighted one at unit
weights, an undefined decomposition is `None` rather than zero, and the two
grouping axes really do measure two different things.
"""

from __future__ import annotations

import pytest

from fmis.paired_dependence.estimator import (
    CellReduction,
    block_index,
    effective_clusters_from,
    group_by_asset,
    group_by_block,
    intraclass_icc,
    pairwise_asset_correlations,
    required_clusters_under_dependence,
)
from fmis.paired_dependence.models import (
    GroupingAxis,
    PairedDependenceError,
    Weighting,
)
from paired_dependence_helpers import panel, row

ASSET = GroupingAxis.ECONOMIC_ASSET
BLOCK = GroupingAxis.TIME_BLOCK


class TestIntraclassIcc:
    def test_balanced_k0_is_the_common_group_size(self):
        groups = {"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0], "c": [7.0, 8.0, 9.0]}
        components = intraclass_icc(groups, axis=ASSET)
        assert components.k0 == pytest.approx(3.0)
        assert components.degrees_between == 2
        assert components.degrees_within == 6

    def test_msb_and_msw_are_the_textbook_sums(self):
        groups = {"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0], "c": [7.0, 8.0, 9.0]}
        components = intraclass_icc(groups, axis=ASSET)
        # group means 2, 5, 8; grand 5; SSB = 3*(9+0+9) = 54 on 2 df
        assert components.mean_square_between == pytest.approx(27.0)
        # each group's SSW is 2; total 6 on 6 df
        assert components.mean_square_within == pytest.approx(1.0)

    def test_identical_groups_give_a_correlation_of_zero_between_them(self):
        groups = {"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0, 3.0], "c": [1.0, 2.0, 3.0]}
        components = intraclass_icc(groups, axis=ASSET)
        assert components.correlation == pytest.approx(-0.5)
        # MSB is exactly zero, so the between-variance is negative and the
        # estimate is the artefact -1/(m-1). It is REPORTED, not truncated away.
        assert components.mean_square_between == pytest.approx(0.0)
        assert components.truncated_correlation == 0.0

    def test_constant_groups_that_differ_are_perfectly_correlated(self):
        groups = {"a": [1.0, 1.0], "b": [5.0, 5.0], "c": [9.0, 9.0]}
        components = intraclass_icc(groups, axis=ASSET)
        assert components.correlation == pytest.approx(1.0)

    def test_unit_weights_reduce_to_the_unweighted_formula_exactly(self):
        groups = {"a": [1.0, 2.0], "b": [4.0, 5.0, 6.0], "c": [7.0]}
        plain = intraclass_icc(groups, axis=ASSET)
        weighted = intraclass_icc(
            groups,
            axis=ASSET,
            weighting=Weighting.OBSERVATION_COUNT,
            weights={key: [1.0] * len(value) for key, value in groups.items()},
        )
        assert weighted.correlation == plain.correlation
        assert weighted.k0 == plain.k0
        assert weighted.mean_square_between == plain.mean_square_between

    def test_one_group_is_refused_with_a_reason_not_a_zero(self):
        components = intraclass_icc({"a": [1.0, 2.0, 3.0]}, axis=BLOCK)
        assert components.correlation is None
        assert components.truncated_correlation is None
        assert "two groups" in components.reason

    def test_no_within_group_degrees_of_freedom_is_refused(self):
        components = intraclass_icc({"a": [1.0], "b": [2.0]}, axis=BLOCK)
        assert components.correlation is None
        assert "two" in components.reason and "member" in components.reason

    def test_a_constant_panel_has_no_correlation_rather_than_zero(self):
        components = intraclass_icc({"a": [3.0, 3.0], "b": [3.0, 3.0]}, axis=BLOCK)
        assert components.correlation is None
        assert "total variance" in components.reason

    def test_empty_groups_are_skipped_not_counted(self):
        components = intraclass_icc(
            {"a": [1.0, 2.0], "b": [4.0, 5.0], "c": []}, axis=ASSET
        )
        assert components.groups == 2

    def test_a_non_real_value_is_refused(self):
        with pytest.raises(PairedDependenceError, match="non-real"):
            intraclass_icc({"a": [1.0, "x"], "b": [2.0, 3.0]}, axis=ASSET)

    def test_a_non_finite_value_is_refused(self):
        with pytest.raises(PairedDependenceError, match="non-finite"):
            intraclass_icc({"a": [1.0, float("inf")], "b": [2.0, 3.0]}, axis=ASSET)

    def test_a_bad_axis_is_refused(self):
        with pytest.raises(PairedDependenceError, match="GroupingAxis"):
            intraclass_icc({"a": [1.0, 2.0]}, axis="economic_asset")

    def test_observation_weighting_without_weights_is_refused(self):
        with pytest.raises(PairedDependenceError, match="weight for every group"):
            intraclass_icc(
                {"a": [1.0, 2.0]}, axis=BLOCK, weighting=Weighting.OBSERVATION_COUNT
            )

    def test_a_mismatched_weight_count_is_refused(self):
        with pytest.raises(PairedDependenceError, match="weight"):
            intraclass_icc(
                {"a": [1.0, 2.0]},
                axis=BLOCK,
                weighting=Weighting.OBSERVATION_COUNT,
                weights={"a": [1.0]},
            )

    def test_a_zero_weight_is_refused_as_a_hidden_exclusion(self):
        with pytest.raises(PairedDependenceError, match="non-positive weight"):
            intraclass_icc(
                {"a": [1.0, 2.0], "b": [3.0, 4.0]},
                axis=BLOCK,
                weighting=Weighting.OBSERVATION_COUNT,
                weights={"a": [1.0, 0.0], "b": [1.0, 1.0]},
            )

    def test_the_payload_names_which_quantity_it_holds(self):
        payload = intraclass_icc(
            {"a": [1.0, 2.0], "b": [3.0, 4.0]}, axis=BLOCK
        ).payload()
        assert payload["axis"] == "time_block"
        assert "between-asset" in payload["measures"]
        assert payload["member_unit"] == "one (economic asset, time block) cell mean"


class TestBlockIndex:
    def test_blocks_are_cut_from_bar_zero(self):
        assert block_index(0, block_bars=60) == 0
        assert block_index(59, block_bars=60) == 0
        assert block_index(60, block_bars=60) == 1

    def test_a_negative_bar_is_refused(self):
        with pytest.raises(PairedDependenceError):
            block_index(-1, block_bars=60)

    def test_a_zero_block_length_is_refused(self):
        with pytest.raises(PairedDependenceError):
            block_index(10, block_bars=0)


class TestGrouping:
    def test_the_asset_axis_groups_individual_observations(self):
        rows = [
            row(difference=1.0, symbol="AAAUSDT", bar_index=0),
            row(difference=2.0, symbol="AAAUSDT", bar_index=1),
            row(difference=3.0, symbol="BBBUSDT", bar_index=0),
        ]
        grouped = group_by_asset(rows)
        assert grouped == {"AAA": [1.0, 2.0], "BBB": [3.0]}

    def test_the_block_axis_reduces_a_cell_to_one_member(self):
        rows = [
            row(difference=1.0, symbol="AAAUSDT", bar_index=0),
            row(difference=3.0, symbol="AAAUSDT", bar_index=1),
            row(difference=5.0, symbol="BBBUSDT", bar_index=2),
        ]
        values, weights, assets = group_by_block(rows, block_bars=60)
        assert values == {0: [2.0, 5.0]}
        assert weights == {0: [2.0, 1.0]}
        assert assets == {0: ["AAA", "BBB"]}

    def test_cell_first_keeps_the_earliest_bar_not_the_mean(self):
        rows = [
            row(difference=9.0, symbol="AAAUSDT", bar_index=5),
            row(difference=1.0, symbol="AAAUSDT", bar_index=2),
        ]
        values, _weights, _assets = group_by_block(
            rows, block_bars=60, reduction=CellReduction.CELL_FIRST
        )
        assert values == {0: [1.0]}

    def test_a_block_holding_one_asset_is_kept(self):
        rows = [row(difference=1.0, symbol="AAAUSDT", bar_index=0)]
        values, _weights, _assets = group_by_block(rows, block_bars=60)
        assert values == {0: [1.0]}

    def test_a_bad_reduction_is_refused(self):
        with pytest.raises(PairedDependenceError, match="CellReduction"):
            group_by_block([], block_bars=60, reduction="cell_mean")


class TestPairwise:
    def test_a_pair_that_never_shares_a_block_yields_no_correlation(self):
        rows = [
            row(difference=float(i), symbol="AAAUSDT", bar_index=i * 60)
            for i in range(6)
        ] + [
            row(difference=float(i), symbol="BBBUSDT", bar_index=(i + 20) * 60)
            for i in range(6)
        ]
        correlations, coverage = pairwise_asset_correlations(
            rows, block_bars=60, minimum_shared_blocks=4
        )
        assert correlations == {}
        assert coverage == {
            "possible_pairs": 1,
            "measurable_pairs": 0,
            "pairs_below_floor": 1,
        }

    def test_a_pair_sharing_enough_blocks_is_measured(self):
        rows = []
        for i in range(6):
            rows.append(row(difference=float(i), symbol="AAAUSDT", bar_index=i * 60))
            rows.append(row(difference=float(i), symbol="BBBUSDT", bar_index=i * 60 + 1))
        correlations, coverage = pairwise_asset_correlations(
            rows, block_bars=60, minimum_shared_blocks=4
        )
        assert coverage["measurable_pairs"] == 1
        assert correlations[("AAA", "BBB")] == pytest.approx(1.0)

    def test_a_floor_below_two_is_refused(self):
        with pytest.raises(PairedDependenceError):
            pairwise_asset_correlations([], block_bars=60, minimum_shared_blocks=1)


class TestSaturation:
    def test_zero_correlation_leaves_the_requirement_untouched(self):
        assert required_clusters_under_dependence(467, 0.0) == (467.0, True)

    def test_a_correlation_at_the_threshold_is_unreachable(self):
        assert required_clusters_under_dependence(467, 1.0 / 467) == (None, False)

    def test_a_correlation_above_the_threshold_is_unreachable(self):
        assert required_clusters_under_dependence(467, 0.0023) == (None, False)

    def test_below_the_threshold_the_requirement_inflates(self):
        needed, reachable = required_clusters_under_dependence(467, 0.001)
        assert reachable
        assert needed > 467
        assert needed == pytest.approx(467 * (1 - 0.001) / (1 - 467 * 0.001))

    def test_an_unidentified_correlation_returns_no_requirement_and_stays_reachable(self):
        assert required_clusters_under_dependence(467, None) == (None, True)

    def test_a_negative_correlation_is_clamped_rather_than_credited(self):
        assert required_clusters_under_dependence(467, -0.5) == (467.0, True)

    def test_effective_clusters_saturates_at_one_over_r(self):
        assert effective_clusters_from(10**6, 0.01) == pytest.approx(100.0, rel=1e-3)

    def test_effective_clusters_is_none_without_a_correlation(self):
        assert effective_clusters_from(100, None) is None

    def test_effective_clusters_clamps_a_negative_rather_than_creating_information(self):
        assert effective_clusters_from(100, -0.2) == 100.0


class TestTwoAxesMeasureTwoThings:
    def test_a_block_factor_moves_r_b_and_not_rho_w(self):
        from fmis.paired_dependence.uncertainty import estimate_on_axis

        flat = panel(market=0.0, level=0.0)
        shared = panel(market=1.0, level=0.0)
        assert estimate_on_axis(shared, axis=BLOCK, block_bars=60).correlation > (
            estimate_on_axis(flat, axis=BLOCK, block_bars=60).correlation or -1.0
        )

    def test_an_asset_level_moves_rho_w_and_not_r_b(self):
        from fmis.paired_dependence.uncertainty import estimate_on_axis

        levelled = panel(market=0.0, level=1.0, per_cell=2)
        flat = panel(market=0.0, level=0.0, per_cell=2)
        assert estimate_on_axis(levelled, axis=ASSET, block_bars=60).correlation > (
            estimate_on_axis(flat, axis=ASSET, block_bars=60).correlation or -1.0
        )


class TestMutationSurvivorRegressions:
    """Regressions added after a rule-level mutation probe survived.

    Each test below names the probe it exists to kill. A survivor is a rule no
    test was watching, and the fix for one is a test, never a narrowing of the
    rule.
    """

    def test_a_pair_sharing_FEWER_than_the_floor_of_blocks_is_excluded(self):
        """Kills: `drop the shared-block floor`.

        The existing coverage test used a pair sharing ZERO blocks, which
        `pearson` refuses on its own — so the floor itself was never exercised.
        This pair shares three blocks against a floor of four.
        """
        rows = []
        for i in range(3):
            rows.append(row(difference=float(i), symbol="AAAUSDT", bar_index=i * 60))
            rows.append(row(difference=float(i * 2), symbol="BBBUSDT", bar_index=i * 60 + 1))
        # BBB alone occupies three further blocks, so neither series is constant
        # and only the SHARED count can be what excludes the pair.
        for i in range(3, 6):
            rows.append(row(difference=float(i), symbol="BBBUSDT", bar_index=i * 60))
        correlations, coverage = pairwise_asset_correlations(
            rows, block_bars=60, minimum_shared_blocks=4
        )
        assert coverage["measurable_pairs"] == 0
        assert coverage["pairs_below_floor"] == 1
        assert correlations == {}

    def test_and_the_same_pair_IS_measured_once_the_floor_is_reached(self):
        """The non-vacuity half: the floor excludes, and nothing else does."""
        rows = []
        for i in range(4):
            rows.append(row(difference=float(i), symbol="AAAUSDT", bar_index=i * 60))
            rows.append(row(difference=float(i * 2), symbol="BBBUSDT", bar_index=i * 60 + 1))
        _correlations, coverage = pairwise_asset_correlations(
            rows, block_bars=60, minimum_shared_blocks=4
        )
        assert coverage["measurable_pairs"] == 1
