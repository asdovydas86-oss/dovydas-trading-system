"""The bootstrap: which axis it resamples, and what it refuses.

The property that makes a cluster bootstrap a cluster bootstrap — a group drawn
twice becomes **two** groups — is asserted directly, because merging the copies
back would produce an interval too narrow by exactly the resampling it was
supposed to do, and nothing about the output would look wrong.
"""

from __future__ import annotations

import pytest

from dataclasses import replace

from fmis.paired_dependence.models import GroupingAxis, PairedDependenceError
from fmis.paired_dependence.synthetic import generate_panel, scenario_by_id
from fmis.paired_dependence.uncertainty import bootstrap_interval, estimate_on_axis
from paired_dependence_helpers import panel, row

BLOCK = GroupingAxis.TIME_BLOCK
ASSET = GroupingAxis.ECONOMIC_ASSET


def _interval(rows, *, axis=BLOCK, resample_axis=BLOCK, draws=200, seed=11):
    return bootstrap_interval(
        rows,
        axis=axis,
        resample_axis=resample_axis,
        block_bars=60,
        draws=draws,
        confidence=0.95,
        master_seed=seed,
        identity=["test"],
    )


class TestInterval:
    def test_the_point_is_the_unresampled_estimate(self):
        rows = panel(market=1.0)
        assert _interval(rows).point == estimate_on_axis(
            rows, axis=BLOCK, block_bars=60
        ).correlation

    def test_the_bounds_bracket_the_point_for_a_well_behaved_panel(self):
        interval = _interval(
            generate_panel(scenario_by_id("strong_between"), block_bars=60, master_seed=1)
        )
        assert interval.lower is not None and interval.upper is not None
        assert interval.lower <= interval.point <= interval.upper

    def test_the_same_seed_gives_the_same_interval(self):
        rows = generate_panel(scenario_by_id("moderate_between"), block_bars=60, master_seed=1)
        assert _interval(rows).payload() == _interval(rows).payload()

    def test_a_different_identity_gives_a_different_interval(self):
        rows = generate_panel(scenario_by_id("moderate_between"), block_bars=60, master_seed=1)
        first = bootstrap_interval(
            rows, axis=BLOCK, resample_axis=BLOCK, block_bars=60, draws=200,
            confidence=0.95, master_seed=11, identity=["a"],
        )
        second = bootstrap_interval(
            rows, axis=BLOCK, resample_axis=BLOCK, block_bars=60, draws=200,
            confidence=0.95, master_seed=11, identity=["b"],
        )
        assert first.lower != second.lower or first.upper != second.upper

    def test_a_wider_confidence_gives_a_wider_interval(self):
        rows = generate_panel(scenario_by_id("moderate_between"), block_bars=60, master_seed=1)
        narrow = bootstrap_interval(
            rows, axis=BLOCK, resample_axis=BLOCK, block_bars=60, draws=400,
            confidence=0.50, master_seed=11, identity=["x"],
        )
        wide = bootstrap_interval(
            rows, axis=BLOCK, resample_axis=BLOCK, block_bars=60, draws=400,
            confidence=0.99, master_seed=11, identity=["x"],
        )
        assert wide.half_width > narrow.half_width

    def test_half_width_and_excludes_zero_are_none_without_bounds(self):
        interval = _interval([row(difference=1.0, symbol="AAAUSDT", bar_index=0)])
        assert interval.half_width is None
        assert interval.excludes_zero is None

    def test_excludes_zero_reads_the_bounds_and_not_the_point(self):
        interval = _interval(
            generate_panel(scenario_by_id("strong_between"), block_bars=60, master_seed=1)
        )
        assert interval.excludes_zero == (
            interval.lower > 0.0 or interval.upper < 0.0
        )


class TestResampling:
    def test_a_group_drawn_twice_becomes_two_groups(self):
        # Two blocks, each holding two assets with identical values inside a
        # block. Resampling blocks must be able to draw one block twice, and if
        # the two copies merged the members-per-group would double.
        rows = panel(assets=4, blocks=12, market=1.0)
        interval = _interval(rows, draws=100)
        assert interval.draws_used > 0
        # The panel has 12 blocks; every resample also has 12 groups, never fewer
        # merged ones, so the component member count is stable.
        assert interval.components.groups == 12

    def test_resampling_assets_is_a_declared_sensitivity_not_an_error(self):
        rows = generate_panel(scenario_by_id("moderate_between"), block_bars=60, master_seed=1)
        interval = _interval(rows, axis=BLOCK, resample_axis=ASSET)
        assert interval.resample_axis is ASSET
        assert interval.lower is not None

    def test_the_within_asset_interval_resamples_assets(self):
        rows = generate_panel(scenario_by_id("within_asset_only"), block_bars=60, master_seed=1)
        interval = _interval(rows, axis=ASSET, resample_axis=ASSET)
        assert interval.point > 0.3
        assert interval.lower is not None


class TestRefusals:
    def test_an_undefined_point_refuses_the_interval_with_its_reason(self):
        interval = _interval([row(difference=1.0, symbol="AAAUSDT", bar_index=0)])
        assert interval.lower is None
        assert "point estimate is undefined" in interval.reason

    def test_one_resampling_bucket_is_refused(self):
        rows = [
            row(difference=float(i), symbol=f"A{i}USDT", bar_index=i)
            for i in range(6)
        ]
        interval = _interval(rows, axis=BLOCK, resample_axis=BLOCK)
        assert interval.lower is None
        assert "at least two" in interval.reason

    def test_a_zero_draw_count_is_refused(self):
        with pytest.raises(PairedDependenceError):
            _interval(panel(market=1.0), draws=0)

    def test_a_confidence_outside_the_open_unit_interval_is_refused(self):
        with pytest.raises(PairedDependenceError):
            bootstrap_interval(
                panel(market=1.0), axis=BLOCK, resample_axis=BLOCK, block_bars=60,
                draws=10, confidence=1.0, master_seed=1, identity=["x"],
            )

    def test_a_bad_resample_axis_is_refused(self):
        with pytest.raises(PairedDependenceError, match="resample_axis"):
            bootstrap_interval(
                panel(market=1.0), axis=BLOCK, resample_axis="blocks", block_bars=60,
                draws=10, confidence=0.95, master_seed=1, identity=["x"],
            )

    def test_undefined_draws_are_counted_and_excluded(self):
        interval = _interval(panel(assets=2, blocks=12, market=1.0), draws=200)
        assert interval.draws_used + interval.draws_undefined == 200


class TestEstimateOnAxis:
    def test_observation_weighting_is_ignored_on_the_asset_axis(self):
        from fmis.paired_dependence.models import Weighting

        rows = panel(assets=6, blocks=8, per_cell=2, level=1.0)
        equal = estimate_on_axis(rows, axis=ASSET, block_bars=60)
        weighted = estimate_on_axis(
            rows, axis=ASSET, block_bars=60, weighting=Weighting.OBSERVATION_COUNT
        )
        assert equal.correlation == weighted.correlation

    def test_a_bad_axis_is_refused(self):
        with pytest.raises(PairedDependenceError, match="GroupingAxis"):
            estimate_on_axis(panel(), axis="asset", block_bars=60)


class TestMutationSurvivorRegressions:
    """Regressions added after a rule-level mutation probe survived.

    Each names the probe it exists to kill.
    """

    def test_a_fifty_percent_confidence_still_has_a_positive_width(self):
        """Kills: `one-sided tail`.

        With ``tail = (1 - level) / 2`` a 50 % interval runs from the 25th to the
        75th percentile and has positive width. With a one-sided ``tail = 1 -
        level`` both bounds land on the median and the width collapses to zero —
        which no comparison between two confidence levels can detect, because the
        ordering survives.
        """
        rows = generate_panel(
            scenario_by_id("moderate_between"), block_bars=60, master_seed=1
        )
        interval = bootstrap_interval(
            rows, axis=BLOCK, resample_axis=BLOCK, block_bars=60, draws=400,
            confidence=0.50, master_seed=11, identity=["half"],
        )
        assert interval.half_width is not None
        assert interval.half_width > 0.0
        assert interval.lower < interval.upper

    def test_a_cluster_drawn_twice_becomes_two_groups_and_not_one(self):
        """Kills: `merge a twice-drawn cluster`.

        Two assets, one observation each per block. Resampling assets draws the
        SAME asset twice in about half the draws. Relabelled, those two copies
        are two members of every block and the estimate is defined. Merged back
        into one, every block holds a single member, the within-group degrees of
        freedom vanish and the draw is undefined — so a merge shows up as a
        collapse in the usable-draw count, and nowhere else.
        """
        rows = []
        for block in range(12):
            rows.append(row(difference=float(block), symbol="AAAUSDT", bar_index=block * 60))
            rows.append(
                row(difference=float(block) + 0.5, symbol="BBBUSDT", bar_index=block * 60 + 1)
            )
        interval = bootstrap_interval(
            rows, axis=BLOCK, resample_axis=ASSET, block_bars=60, draws=300,
            confidence=0.95, master_seed=5, identity=["merge"],
        )
        assert interval.draws_undefined == 0
        assert interval.draws_used == 300

    def test_a_single_resampling_bucket_is_refused_where_the_point_IS_defined(self):
        """Kills: `bootstrap a single bucket`.

        The earlier test reached the same message through the *point estimate*
        being undefined, so the bucket check itself was never exercised. Here the
        point estimate is defined on the asset axis and only the resampling axis
        is degenerate.
        """
        rows = [
            row(difference=float(i), symbol=f"A{i}USDT", bar_index=i)
            for i in range(8)
        ] + [
            row(difference=float(i) + 0.5, symbol=f"A{i}USDT", bar_index=i + 10)
            for i in range(8)
        ]
        interval = bootstrap_interval(
            rows, axis=ASSET, resample_axis=BLOCK, block_bars=60, draws=50,
            confidence=0.95, master_seed=3, identity=["one-bucket"],
        )
        assert interval.point is not None, "the point estimate must be defined"
        assert interval.lower is None
        assert "resampling time_block needs at least two" in interval.reason

    def test_an_interval_read_off_a_minority_of_draws_is_refused(self, monkeypatch):
        """Kills: `accept an interval read off a minority of draws`.

        **This is fault injection, and it says so.** The branch is deliberately
        hard to reach from data: on the block axis a group drawn twice becomes
        two groups, so a resample almost always has as many groups as the panel
        and the estimate is almost always defined. The highest undefined rate a
        single "unlucky bucket" construction can produce is ``1/e``, about 37 % —
        below the majority this rule watches for. Contriving a panel to cross 50 %
        would be fitting a fixture to a branch; injecting the fault states plainly
        what is being tested.

        The first call is left defined, because that one is the POINT estimate and
        a refusal there is a different branch with a different message.
        """
        import fmis.paired_dependence.uncertainty as module

        real = module.estimate_on_axis
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            components = real(*args, **kwargs)
            if calls["n"] == 1 or calls["n"] % 5 == 0:
                return components
            return replace(components, correlation=None, reason="injected")

        monkeypatch.setattr(module, "estimate_on_axis", flaky)
        rows = generate_panel(
            scenario_by_id("moderate_between"), block_bars=60, master_seed=1
        )
        interval = bootstrap_interval(
            rows, axis=BLOCK, resample_axis=BLOCK, block_bars=60, draws=100,
            confidence=0.95, master_seed=9, identity=["minority"],
        )
        assert interval.point is not None, "the point estimate must survive"
        assert interval.lower is None
        assert "produced a defined" in interval.reason
        assert interval.draws_used * 2 < interval.draws_requested

    def test_NON_VACUITY_the_same_panel_without_the_fault_yields_an_interval(self):
        """What makes the injection above a test rather than a tautology."""
        rows = generate_panel(
            scenario_by_id("moderate_between"), block_bars=60, master_seed=1
        )
        interval = bootstrap_interval(
            rows, axis=BLOCK, resample_axis=BLOCK, block_bars=60, draws=100,
            confidence=0.95, master_seed=9, identity=["minority"],
        )
        assert interval.lower is not None
        assert interval.draws_used == 100
