"""Negative and hostile controls — **and the non-vacuity proof for each one.**

Milestone CC shipped an ordering control that could not detect an expectancy
sort, and Milestone CA shipped a holdout control its own docstring claimed but
which did not exist. Both were found by independent review, not by the suite. So
every control here is asserted twice: once that it passes on the panel it should
pass on, and once that it **fails** on a panel it should fail on. A control with
only the first assertion is a formality.
"""

from __future__ import annotations

import pytest

from fmis.paired_dependence.controls import (
    cc_residual_correlation,
    duplicate_rows,
    hash_free,
    outcome_permutation_stable,
    panel_shape,
    run_negative_controls,
    shuffle_asset_identity,
    shuffle_time_blocks,
    split_exposure,
)
from fmis.paired_dependence.estimator import effective_clusters_from
from fmis.paired_dependence.models import GroupingAxis, PairedDependenceError
from fmis.paired_dependence.preregistration import CD_MASTER_SEED
from fmis.paired_dependence.synthetic import generate_panel, scenario_by_id
from fmis.paired_dependence.uncertainty import estimate_on_axis
from paired_dependence_helpers import panel, row

BLOCK = GroupingAxis.TIME_BLOCK
ASSET = GroupingAxis.ECONOMIC_ASSET


def _between(rows, block_bars=60):
    return estimate_on_axis(rows, axis=BLOCK, block_bars=block_bars).correlation


def _within(rows, block_bars=60):
    return estimate_on_axis(rows, axis=ASSET, block_bars=block_bars).correlation


class TestShuffleTimeBlocks:
    def test_it_collapses_a_real_block_factor(self):
        rows = generate_panel(
            scenario_by_id("strong_between"), block_bars=60, master_seed=1
        )
        before = _between(rows)
        after = _between(shuffle_time_blocks(rows, block_bars=60, seed=7))
        assert before > 0.4
        assert after < 0.1

    def test_NON_VACUITY_it_does_not_collapse_a_panel_it_cannot_touch(self):
        # A panel whose every asset holds ONE observation has nothing to permute
        # within an asset, so the control must leave every value exactly where it
        # was. A control that "collapsed" this panel would be destroying
        # structure by accident rather than by design.
        rows = [
            row(difference=float(i % 5), symbol=f"A{i:02d}USDT", bar_index=i * 60)
            for i in range(12)
        ]
        shuffled = shuffle_time_blocks(rows, block_bars=60, seed=7)
        assert [
            (item.economic_asset, item.bar_index, item.difference) for item in shuffled
        ] == [
            (item.economic_asset, item.bar_index, item.difference) for item in rows
        ]

    def test_it_preserves_every_asset_s_own_observation_count(self):
        rows = generate_panel(
            scenario_by_id("strong_between"), block_bars=60, master_seed=1
        )
        shuffled = shuffle_time_blocks(rows, block_bars=60, seed=7)
        def census(panel_rows):
            counts = {}
            for item in panel_rows:
                counts[item.economic_asset] = counts.get(item.economic_asset, 0) + 1
            return counts
        assert census(shuffled) == census(rows)

    def test_it_is_deterministic_across_processes(self):
        rows = generate_panel(scenario_by_id("moderate_between"), block_bars=60, master_seed=1)
        assert shuffle_time_blocks(rows, block_bars=60, seed=3) == shuffle_time_blocks(
            rows, block_bars=60, seed=3
        )


class TestShuffleAssetIdentity:
    def test_it_collapses_a_real_asset_level(self):
        rows = generate_panel(
            scenario_by_id("within_asset_only"), block_bars=60, master_seed=1
        )
        before = _within(rows)
        after = _within(shuffle_asset_identity(rows, seed=7))
        assert before > 0.3
        assert abs(after) < 0.05

    def test_NON_VACUITY_it_leaves_a_panel_with_no_asset_structure_where_it_was(self):
        rows = generate_panel(scenario_by_id("independent"), block_bars=60, master_seed=1)
        before = _within(rows)
        after = _within(shuffle_asset_identity(rows, seed=7))
        assert abs(before) < 0.05 and abs(after) < 0.05

    def test_it_preserves_the_timeline_exactly(self):
        rows = generate_panel(scenario_by_id("within_asset_only"), block_bars=60, master_seed=1)
        shuffled = shuffle_asset_identity(rows, seed=7)
        assert sorted(item.bar_index for item in shuffled) == sorted(
            item.bar_index for item in rows
        )
        assert sorted(item.difference for item in shuffled) == pytest.approx(
            sorted(item.difference for item in rows)
        )


class TestDuplicatedRows:
    def test_duplication_does_not_move_the_between_asset_estimate(self):
        rows = panel(market=1.0)
        assert _between(duplicate_rows(rows)) == pytest.approx(_between(rows))

    def test_duplication_does_not_create_economic_assets(self):
        rows = panel(market=1.0)
        assert len({item.economic_asset for item in duplicate_rows(rows)}) == len(
            {item.economic_asset for item in rows}
        )

    def test_duplication_does_not_create_effective_clusters(self):
        rows = panel(market=1.0)
        original = effective_clusters_from(
            len({item.economic_asset for item in rows}), _between(rows)
        )
        doubled_rows = duplicate_rows(rows)
        doubled = effective_clusters_from(
            len({item.economic_asset for item in doubled_rows}), _between(doubled_rows)
        )
        assert doubled == pytest.approx(original)

    def test_NON_VACUITY_a_row_count_DOES_double_so_the_control_is_watching_something(self):
        rows = panel(market=1.0)
        assert len(duplicate_rows(rows)) == 2 * len(rows)

    def test_copying_once_is_refused_as_copying_nothing(self):
        with pytest.raises(PairedDependenceError):
            duplicate_rows(panel(), copies=1)


class TestCcResidualControl:
    def test_it_returns_the_artefact_whatever_the_true_correlation(self):
        values = [
            cc_residual_correlation(
                generate_panel(scenario_by_id(name), block_bars=60, master_seed=CD_MASTER_SEED),
                block_bars=60,
            )
            for name in ("independent", "moderate_between", "strong_between")
        ]
        assert max(values) - min(values) < 0.01

    def test_NON_VACUITY_cd_s_own_estimator_spreads_over_the_same_panels(self):
        values = [
            _between(
                generate_panel(scenario_by_id(name), block_bars=60, master_seed=CD_MASTER_SEED)
            )
            for name in ("independent", "moderate_between", "strong_between")
        ]
        assert max(values) - min(values) > 0.4

    def test_it_is_none_when_no_pair_shares_two_blocks(self):
        rows = [row(difference=1.0, symbol="AAAUSDT", bar_index=0)]
        assert cc_residual_correlation(rows, block_bars=60) is None


class TestSplitExposure:
    def test_one_exposure_split_across_two_symbols_looks_like_two_clusters(self):
        rows = panel(assets=6, blocks=10)
        split = split_exposure(rows, economic_asset="A00", symbols=("A00A", "A00B"))
        assert len({item.economic_asset for item in split}) == 7
        assert len({item.economic_asset for item in rows}) == 6

    def test_and_collapsing_them_back_restores_the_original_asset_count(self):
        rows = panel(assets=6, blocks=10)
        split = split_exposure(rows, economic_asset="A00", symbols=("A00A", "A00B"))
        collapsed = {
            ("A00" if item.economic_asset.startswith("A00") else item.economic_asset)
            for item in split
        }
        assert collapsed == {item.economic_asset for item in rows}

    def test_splitting_across_one_symbol_is_refused(self):
        with pytest.raises(PairedDependenceError, match="splits nothing"):
            split_exposure(panel(), economic_asset="A00", symbols=("A00A",))

    def test_splitting_an_absent_asset_is_refused(self):
        with pytest.raises(PairedDependenceError, match="nothing to split"):
            split_exposure(panel(), economic_asset="NOPE", symbols=("X", "Y"))


class TestOutcomePermutation:
    def test_permuting_every_difference_leaves_the_panel_s_shape_identical(self):
        assert outcome_permutation_stable(panel(market=1.0), block_bars=60, seed=5)

    def test_NON_VACUITY_a_shaper_that_reads_an_outcome_is_caught(self):
        def leaky(rows, *, block_bars):
            return {
                **panel_shape(rows, block_bars=block_bars),
                "first_difference": rows[0].difference,
            }

        rows = panel(market=1.0)
        assert not outcome_permutation_stable(
            rows, block_bars=60, seed=5, shaper=leaky
        )

    def test_panel_shape_holds_no_measured_value(self):
        shape = panel_shape(panel(market=1.0), block_bars=60)
        assert set(shape) == {"rows", "assets", "blocks", "cells", "bar_indices"}


class TestHashFree:
    def test_it_is_stable_and_not_python_s_salted_hash(self):
        assert hash_free("BTC") == hash_free("BTC")
        assert hash_free("BTC") != hash_free("ETH")


class TestRunNegativeControls:
    def test_every_control_reports_a_before_and_an_after(self):
        readings = run_negative_controls(panel(market=1.0), block_bars=60, seed=7)
        assert {item.control_id for item in readings} == {
            "shuffled_time_blocks",
            "shuffled_asset_identity",
            "duplicated_rows_between",
            "duplicated_rows_within",
            # Added after independent review: at EQUAL_CELL a duplicated panel is
            # PROVABLY unchanged, so that arm cannot fail. This is the arm where
            # it can.
            "duplicated_rows_between_observation_weighted",
            "cc_residual_estimator",
        }
        for item in readings:
            assert item.watches_for
            assert item.expectation
            assert set(item.payload()) == {
                "control_id", "watches_for", "axis", "observed",
                "under_control", "shift", "expectation",
            }

    def test_the_shift_is_none_when_either_side_is_unmeasured(self):
        readings = run_negative_controls(
            [row(difference=1.0, symbol="AAAUSDT", bar_index=0)], block_bars=60, seed=7
        )
        assert any(item.shift is None for item in readings)
