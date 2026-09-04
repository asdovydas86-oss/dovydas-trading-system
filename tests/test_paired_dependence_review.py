"""Regressions for every finding an independent hostile review confirmed.

Each test names the finding it exists to prevent recurring. Three reviewers
attacked Milestone CD — statistics, bias/causality, engineering — and the two
most consequential findings were an **outright bug** in the weighted estimator
and an **estimand error sealed into the pre-registration**. Both are pinned here.

The distinction this file keeps: a finding in CD's own *code* is FIXED and
regressed; a finding in CD's *seal* is DISCLOSED and its current behaviour is
pinned, because changing a sealed rule after seeing results is what a
pre-registration exists to prevent. Both kinds are tested — one for the corrected
behaviour, the other so the disclosed behaviour cannot drift silently.
"""

from __future__ import annotations

import statistics
from pathlib import Path

import pytest

from fmis.paired_dependence.estimator import (
    contemporaneity_fraction,
    intraclass_icc,
    leave_one_out,
    overlap_corrected_correlation,
)
from fmis.paired_dependence.integration import assess_requirement
from fmis.paired_dependence.models import (
    GroupingAxis,
    PairedDependenceError,
    RequirementOutcome,
    Weighting,
)
from fmis.paired_dependence.preregistration import CD_POST_REVIEW_LIMITATIONS
from paired_dependence_helpers import panel, row

BLOCK = GroupingAxis.TIME_BLOCK
ASSET = GroupingAxis.ECONOMIC_ASSET

GROUPS = {
    "b1": [1.0, 2.0, 3.0],
    "b2": [4.0, 5.5, 6.0],
    "b3": [7.0, 8.0, 9.5],
    "b4": [2.0, 3.5, 1.0],
}


class TestA_S3_TheWeightedIccIsScaleInvariant:
    """FIXED. Multiplying every weight by a constant must change nothing.

    Before the fix the estimate was driven toward zero by a pure change of units
    — rho 0.860 at weight 1.0, 0.381 at weight 10.0 — because a weighted sum of
    squares was divided by unweighted degrees of freedom and E[MSB]'s own
    s2_e coefficient was omitted. The only weighted test used weights of exactly
    1.0, which is the single case that cannot detect it.
    """

    def _weighted(self, factor: float) -> float:
        return intraclass_icc(
            GROUPS,
            axis=BLOCK,
            weighting=Weighting.OBSERVATION_COUNT,
            weights={key: [factor] * len(value) for key, value in GROUPS.items()},
        ).correlation

    @pytest.mark.parametrize("factor", [0.5, 1.0, 2.0, 5.0, 10.0, 1000.0])
    def test_a_common_weight_factor_does_not_move_the_estimate(self, factor):
        assert self._weighted(factor) == pytest.approx(self._weighted(1.0), abs=1e-12)

    def test_and_it_equals_the_unweighted_estimate(self):
        assert self._weighted(1.0) == pytest.approx(
            intraclass_icc(GROUPS, axis=BLOCK).correlation, abs=1e-12
        )

    def test_unit_weights_still_reduce_EXACTLY_on_an_unbalanced_panel(self):
        groups = {"a": [1.0, 2.0], "b": [4.0, 5.0, 6.0], "c": [7.0]}
        plain = intraclass_icc(groups, axis=BLOCK)
        weighted = intraclass_icc(
            groups,
            axis=BLOCK,
            weighting=Weighting.OBSERVATION_COUNT,
            weights={key: [1.0] * len(value) for key, value in groups.items()},
        )
        assert weighted.correlation == plain.correlation

    def test_NON_VACUITY_unequal_weights_do_change_the_estimate(self):
        """A scale-invariant estimator that ignored weights entirely would also
        pass every test above. This asserts the weights are still read."""
        skewed = intraclass_icc(
            GROUPS,
            axis=BLOCK,
            weighting=Weighting.OBSERVATION_COUNT,
            weights={"b1": [1.0, 1.0, 9.0], "b2": [9.0, 1.0, 1.0],
                     "b3": [1.0, 9.0, 1.0], "b4": [1.0, 1.0, 9.0]},
        ).correlation
        assert skewed != pytest.approx(self._weighted(1.0), abs=1e-9)


class TestA_S1_TheEffectiveClusterCorrelationIsNotRb:
    """DISCLOSED as CD-8, with the correction computable beside the sealed value.

    `r_b` is the correlation between two individual contemporaneous observations.
    `K/(1+(K-1)r)` expects the mean pairwise correlation of cluster-level series.
    They coincide only if every admission of one asset is contemporaneous with
    every admission of another.
    """

    def test_the_contemporaneity_fraction_is_below_one_on_a_scattered_panel(self):
        rows = []
        for asset in range(10):
            for block in range(20):
                if (asset + block) % 4 == 0:      # scattered, not aligned
                    rows.append(
                        row(difference=float(block), symbol=f"A{asset}USDT",
                            bar_index=block * 60)
                    )
        fraction = contemporaneity_fraction(rows, block_bars=60)
        assert 0.0 < fraction < 1.0

    def test_a_fully_aligned_panel_has_a_fraction_of_one(self):
        """Non-vacuity: q is 1 exactly when the sealed formula would be right."""
        rows = [
            row(difference=float(block), symbol=f"A{asset}USDT", bar_index=block * 60)
            for asset in range(6)
            for block in range(12)
        ]
        assert contemporaneity_fraction(rows, block_bars=60) == pytest.approx(1.0)

    def test_the_correction_shrinks_the_correlation_on_a_scattered_panel(self):
        rows = panel(assets=8, blocks=30, market=1.0)
        thinned = [r for r in rows if (int(r.bar_index) // 60 + hash(r.symbol) % 7) % 3 == 0]
        corrected = overlap_corrected_correlation(
            thinned, correlation=0.20, block_bars=60
        )
        assert corrected is not None
        assert 0.0 < corrected < 0.20

    def test_it_is_none_rather_than_zero_when_undefined(self):
        assert contemporaneity_fraction([], block_bars=60) is None
        assert contemporaneity_fraction(
            [row(difference=1.0, symbol="AAAUSDT", bar_index=0)], block_bars=60
        ) is None
        assert overlap_corrected_correlation([], correlation=0.2, block_bars=60) is None
        assert overlap_corrected_correlation(
            panel(), correlation=None, block_bars=60
        ) is None

    def test_the_finding_is_recorded_OUTSIDE_the_seal(self):
        text = " ".join(CD_POST_REVIEW_LIMITATIONS)
        assert "CD-8" in text
        assert "OVERSTATED" in text
        from fmis.paired_dependence.preregistration import CD_PRE_REGISTRATION

        # And the seal itself is untouched by the correction.
        assert "q * r_b" not in " ".join(CD_PRE_REGISTRATION.secondary_estimators)


class TestA_S4_TheHeadlineStabilityIsMeasuredNotAsserted:
    """DISCLOSED as CD-16. Share-of-magnitude cannot detect a fragile variance ratio."""

    def test_leave_one_out_reports_a_spread_over_every_drop(self):
        rows = panel(assets=10, blocks=20, market=1.0, level=0.4)
        reading = leave_one_out(rows, axis=BLOCK, block_bars=60, by="asset")
        assert reading["dropped"] == 10
        assert len(reading["readings"]) == 10
        assert reading["minimum"] <= reading["maximum"]
        assert reading["spread"] == pytest.approx(
            reading["maximum"] - reading["minimum"]
        )

    def test_it_can_drop_blocks_too(self):
        rows = panel(assets=6, blocks=15, market=1.0)
        reading = leave_one_out(rows, axis=BLOCK, block_bars=60, by="block")
        assert reading["dropped"] == 15

    def test_NON_VACUITY_a_panel_whose_dependence_rests_on_one_asset_shows_a_spread(self):
        """A flat leave-one-out sweep would make the diagnostic decorative.

        Five assets track a block factor exactly; one does not. Dropping the odd
        asset out raises the block-shared share sharply, so the sweep must show a
        wide spread — and if it did not, the diagnostic could never detect the
        fragility it exists to detect.
        """
        rows = []
        for asset in range(5):
            for block in range(15):
                rows.append(
                    row(difference=float((block % 4) - 1.5),
                        symbol=f"A{asset}USDT", bar_index=block * 60)
                )
        for block in range(15):
            rows.append(
                row(difference=9.0 * ((block * 7) % 5 - 2),
                    symbol="ODDUSDT", bar_index=block * 60)
            )
        reading = leave_one_out(rows, axis=BLOCK, block_bars=60, by="asset")
        assert reading["spread"] > 0.05, reading

    def test_an_unknown_drop_axis_is_refused(self):
        with pytest.raises(PairedDependenceError, match="not 'symbol'"):
            leave_one_out(panel(), axis=BLOCK, block_bars=60, by="symbol")


class TestA_S7_TheSealedStraddleRuleIsPinnedAndDisclosed:
    """DISCLOSED as CD-9, NOT fixed.

    The sealed rule fires on "at or below zero to at or above 1/K*". The
    condition that actually means "both a finite and an infinite requirement are
    supported" is `lower < 1/K* <= upper`; zero has no role in it. Changing a
    verdict rule after seeing results is what a pre-registration prevents, so the
    sealed behaviour is pinned here and disclosed in the report.
    """

    def test_an_interval_inside_the_decisive_band_is_reported_UNREACHABLE(self):
        assessment = assess_requirement(
            point=0.05, lower=0.0005, upper=0.30, within_asset_correlation=0.0
        )
        assert assessment.outcome is RequirementOutcome.UNREACHABLE
        # ... even though a finite requirement IS supported at the lower bound.
        assert assessment.lower.reachable
        assert assessment.lower.required_clusters is not None

    def test_the_sealed_rule_still_catches_an_interval_that_reaches_zero(self):
        assessment = assess_requirement(
            point=0.198, lower=-0.049, upper=0.418, within_asset_correlation=0.0
        )
        assert assessment.outcome is RequirementOutcome.INCONCLUSIVE

    def test_the_discrepancy_is_recorded_outside_the_seal(self):
        text = " ".join(CD_POST_REVIEW_LIMITATIONS)
        assert "CD-9" in text and "DISCLOSED rather than corrected" in text


class TestB_F1_TheMechanismClaimIsCorrected:
    """DISCLOSED as CD-10. The first draft's mechanism was wrong three ways."""

    def test_the_matching_radius_is_a_CEILING_not_a_floor(self):
        """The inequality the first draft inverted."""
        import inspect

        from fmis.swing_lab import admission_matching

        source = inspect.getsource(admission_matching.eligible_pool)
        assert "distance < separation or distance > radius" in source

    def test_two_sealed_families_use_a_SAME_BAR_control(self):
        from fmis.swing_lab.admission_preregistration import (
            CA_NULL_FAMILIES,
            CaControlSource,
        )

        same_bar = [
            item.family_id
            for item in CA_NULL_FAMILIES
            if item.control_source is CaControlSource.SAME_BAR
        ]
        assert len(same_bar) == 2
        assert "ca_null_opposite_direction" in same_bar

    def test_the_finding_is_recorded_outside_the_seal(self):
        text = " ".join(CD_POST_REVIEW_LIMITATIONS)
        assert "CD-10" in text and "CEILING" in text


class TestEveryConfirmedFindingIsRecorded:
    def test_each_post_review_limitation_is_numbered_in_sequence(self):
        assert len(CD_POST_REVIEW_LIMITATIONS) >= 12
        for index, item in enumerate(CD_POST_REVIEW_LIMITATIONS, start=8):
            assert item.startswith(f"CD-{index} —"), item

    def test_they_are_carried_SEPARATELY_from_the_sealed_limitations(self):
        from fmis.paired_dependence.preregistration import (
            CD_LIMITATIONS,
            CD_PRE_REGISTRATION,
        )

        assert set(CD_POST_REVIEW_LIMITATIONS) & set(CD_LIMITATIONS) == set()
        assert CD_PRE_REGISTRATION.limitations == CD_LIMITATIONS

    def test_the_seal_is_unchanged_by_any_of_them(self):
        from fmis.paired_dependence.preregistration import (
            CD_PREREGISTRATION_DIGEST,
            cd_preregistration_digest,
        )

        assert cd_preregistration_digest() == CD_PREREGISTRATION_DIGEST
        assert CD_PREREGISTRATION_DIGEST == (
            "28f8ebed0aa66dd77d16b08b8a8eecda86c922e5ded9db6da24881674c37c25d"
        )


class TestC_M2_TheObserverHookIsInertByConstruction:
    """FIXED. The hook now hands out read-only copies.

    `PairedRecord` is frozen but its horizon maps were plain dicts behind a
    `Mapping` annotation, so an observer could write into one and silently move
    Milestone CA's published effect. Independent review demonstrated it:
    `record.control_forward[24] = 99.0` changed `difference(24)` from +1.0 to
    −97.5. Inertness was a property of CD's own well-behaved observer, not of the
    hook.
    """

    def test_the_observer_cannot_write_through_a_horizon_map(self):
        from fmis.swing_lab.admission_study import _read_only_record
        from paired_dependence_helpers import record

        original = record(difference=1.0)
        handed = _read_only_record(original)
        with pytest.raises(TypeError):
            handed.control_forward[24] = 99.0
        with pytest.raises(TypeError):
            handed.admission_forward[24] = 99.0

    def test_NON_VACUITY_the_raw_record_WOULD_have_allowed_it(self):
        from paired_dependence_helpers import record

        original = record(difference=1.0)
        before = original.difference(24)
        original.control_forward[24] = 99.0        # a plain dict, writable
        assert original.difference(24) != before   # ... and it moves the effect

    def test_the_copy_carries_identical_values(self):
        from fmis.swing_lab.admission_study import _read_only_record
        from paired_dependence_helpers import record

        original = record(difference=0.375, control=1.25)
        handed = _read_only_record(original)
        assert handed.difference(24) == original.difference(24)
        assert dict(handed.admission_forward) == dict(original.admission_forward)
        assert dict(handed.control_forward) == dict(original.control_forward)
        assert handed.symbol == original.symbol
        assert handed.bar_index == original.bar_index


class TestC_M5_RhoWIsNotPresentedAsIfItVaried:
    """FIXED in the renderer. rho_w reads no grid dimension at all."""

    def test_rho_w_is_identical_across_every_block_length(self):
        from fmis.paired_dependence.uncertainty import estimate_on_axis

        rows = panel(assets=8, blocks=20, per_cell=2, market=1.0, level=0.5)
        values = {
            estimate_on_axis(rows, axis=ASSET, block_bars=b).correlation
            for b in (24, 60, 120, 180)
        }
        assert len(values) == 1

    def test_the_renderer_prints_it_once_and_says_why(self):
        from fmis.paired_dependence import render

        source = Path(render.__file__).read_text(encoding="utf-8")
        assert "rho_w is NOT a column here" in source
        assert "would read as robustness when nothing was varied" in source


class TestC_L1_ReproductionDoesNotDependOnRowOrder:
    """FIXED. `study_from_rows` sorts by observation id before measuring."""

    def test_the_entry_point_canonicalises_order(self):
        import inspect

        from fmis.paired_dependence.study import study_from_rows

        source = inspect.getsource(study_from_rows)
        assert "sorted(rows, key=lambda item: item.observation_id)" in source


class TestC_H1_TheDuplicationControlReadsTheWeighting:
    """Kills: `duplication control ignores the weighting`.

    After the weighted-ICC fix the two weightings agree on any panel whose cells
    are all the same size, because the estimator is now scale-invariant — so a
    control that silently dropped the weighting would pass on every uniform
    fixture. It must be pinned on a panel with **unequal** cell sizes, which is
    the only shape where the two arms differ.
    """

    @staticmethod
    def _unequal():
        """Assets contribute different numbers of observations per block."""
        rows = []
        for asset in range(8):
            for block in range(14):
                for slot in range(1 + (asset % 4)):      # 1..4 per cell
                    rows.append(
                        row(
                            difference=float((block % 5) - 2) + 0.3 * slot
                            + 0.7 * ((asset * 3) % 5 - 2),
                            symbol=f"A{asset}USDT",
                            bar_index=block * 60 + slot,
                        )
                    )
        return rows

    def test_the_two_weightings_differ_on_a_panel_with_unequal_cells(self):
        from fmis.paired_dependence.uncertainty import estimate_on_axis

        rows = self._unequal()
        equal = estimate_on_axis(
            rows, axis=BLOCK, block_bars=60, weighting=Weighting.EQUAL_CELL
        ).correlation
        weighted = estimate_on_axis(
            rows, axis=BLOCK, block_bars=60, weighting=Weighting.OBSERVATION_COUNT
        ).correlation
        assert equal != pytest.approx(weighted, abs=1e-6), (equal, weighted)

    def test_the_observation_weighted_control_reports_the_WEIGHTED_estimate(self):
        from fmis.paired_dependence.controls import run_negative_controls
        from fmis.paired_dependence.uncertainty import estimate_on_axis

        rows = self._unequal()
        reading = next(
            item
            for item in run_negative_controls(rows, block_bars=60, seed=3)
            if item.control_id == "duplicated_rows_between_observation_weighted"
        )
        weighted = estimate_on_axis(
            rows, axis=BLOCK, block_bars=60, weighting=Weighting.OBSERVATION_COUNT
        ).correlation
        assert reading.observed == pytest.approx(weighted, abs=1e-12)

    def test_and_duplication_still_leaves_that_arm_unmoved(self):
        """The control's own claim, on the arm where it can actually fail."""
        from fmis.paired_dependence.controls import run_negative_controls

        reading = next(
            item
            for item in run_negative_controls(self._unequal(), block_bars=60, seed=3)
            if item.control_id == "duplicated_rows_between_observation_weighted"
        )
        assert reading.observed == pytest.approx(reading.under_control, abs=1e-9)


class TestA_S3_NonVacuity_TheOldImplementationWouldFail:
    """**Proof that the scale-invariance regression is not vacuous.**

    A test asserting `f(x) == f(2x)` says nothing unless some plausible
    implementation violates it. The implementation that shipped in Milestone CD's
    first run did. It is reconstructed here — divide the weighted sums of squares
    by the *unweighted* degrees of freedom and omit the `s2_e` coefficient in
    `E[MSB]`, exactly as the original did — and asserted to FAIL the very property
    the fixed estimator now satisfies.

    This is the difference between "the test passes" and "the test can fail".
    """

    GROUPS = {
        "b1": [1.0, 2.0, 3.0],
        "b2": [4.0, 5.5, 6.0],
        "b3": [7.0, 8.0, 9.5],
        "b4": [2.0, 3.5, 1.0],
    }

    @classmethod
    def _original_broken(cls, factor: float) -> float:
        """Milestone CD's first weighted ICC, reconstructed verbatim in effect."""
        cleaned = [
            (key, tuple(values), tuple(factor for _ in values))
            for key, values in sorted(cls.GROUPS.items())
        ]
        group_count = len(cleaned)
        member_count = sum(len(values) for _k, values, _w in cleaned)
        total_weight = sum(sum(w) for _k, _v, w in cleaned)
        grand = sum(
            value * weight
            for _k, values, w in cleaned
            for value, weight in zip(values, w)
        ) / total_weight
        ssb = ssw = sum_squared_weights = 0.0
        for _key, values, w in cleaned:
            group_weight = sum(w)
            sum_squared_weights += group_weight * group_weight
            group_mean = sum(v * gw for v, gw in zip(values, w)) / group_weight
            ssb += group_weight * (group_mean - grand) ** 2
            for value, gw in zip(values, w):
                ssw += gw * (value - group_mean) ** 2
        degrees_between = group_count - 1
        degrees_within = member_count - group_count
        msb = ssb / degrees_between                 # weighted SSB ...
        msw = ssw / degrees_within                  # ... over UNWEIGHTED df: the bug
        k0 = (total_weight - sum_squared_weights / total_weight) / degrees_between
        between = (msb - msw) / k0                  # ... and no E[MSB] coefficient
        return between / (between + msw)

    def _fixed(self, factor: float) -> float:
        return intraclass_icc(
            self.GROUPS,
            axis=BLOCK,
            weighting=Weighting.OBSERVATION_COUNT,
            weights={key: [factor] * len(v) for key, v in self.GROUPS.items()},
        ).correlation

    def test_the_reconstruction_reproduces_the_reported_defect(self):
        """The four values independent review measured, to three decimals."""
        assert self._original_broken(1.0) == pytest.approx(0.860, abs=5e-4)
        assert self._original_broken(2.0) == pytest.approx(0.755, abs=5e-4)
        assert self._original_broken(5.0) == pytest.approx(0.551, abs=5e-4)
        assert self._original_broken(10.0) == pytest.approx(0.381, abs=5e-4)

    def test_the_OLD_implementation_FAILS_the_scale_invariance_property(self):
        """If it did not, the regression above would be certifying nothing."""
        assert self._original_broken(10.0) != pytest.approx(
            self._original_broken(1.0), abs=1e-6
        )

    def test_the_NEW_implementation_passes_it(self):
        assert self._fixed(10.0) == pytest.approx(self._fixed(1.0), abs=1e-12)

    def test_both_agree_at_unit_weights_which_is_why_the_old_test_was_blind(self):
        """The old suite's only weighted test used weights of exactly 1.0."""
        assert self._original_broken(1.0) == pytest.approx(self._fixed(1.0), abs=1e-12)

    def test_and_both_agree_with_the_UNWEIGHTED_sealed_formula_there(self):
        """Category A, not B: the repair makes the code execute the SEALED
        estimator faithfully. The seal specifies the unweighted ANOVA method of
        moments; a weighted sensitivity over the same estimator must reduce to it
        exactly at unit weights, and must not move when units change. It does
        both now, and the sealed unweighted path never changed."""
        sealed = intraclass_icc(self.GROUPS, axis=BLOCK).correlation
        assert self._fixed(1.0) == pytest.approx(sealed, abs=1e-12)
        assert self._original_broken(1.0) == pytest.approx(sealed, abs=1e-12)
