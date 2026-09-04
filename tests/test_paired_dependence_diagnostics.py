"""Post-review diagnostics, pinned against the published artifact.

Every number an independent reviewer established and I reproduced is asserted
here against `reports/artifacts/0040_cd_paired_dependence.json.gz`, so report
0040's corrected claims cannot drift away from the file they describe.

**These are diagnostics, not the sealed measurement.** Nothing here feeds a
verdict. The sealed path is untouched and is pinned separately in
`tests/test_paired_dependence_artifact_pinned.py`.
"""

from __future__ import annotations

import gzip
import itertools
import json
import statistics
from pathlib import Path

import pytest

from fmis.paired_dependence.estimator import (
    contemporaneity_fraction,
    intraclass_icc,
)
from fmis.paired_dependence.models import GroupingAxis
from fmis.paired_dependence.synthetic import SyntheticRow
from fmis.paired_dependence.uncertainty import estimate_on_axis
from fmis.universe.dependence import pearson

_STUDY = (
    Path(__file__).resolve().parents[1]
    / "reports" / "artifacts" / "0040_cd_paired_dependence.json.gz"
)
BLOCK = GroupingAxis.TIME_BLOCK
ASSET = GroupingAxis.ECONOMIC_ASSET


@pytest.fixture(scope="module")
def payload():
    if not _STUDY.exists():
        pytest.skip(f"{_STUDY.name} is not present in this checkout")
    return json.loads(gzip.decompress(_STUDY.read_bytes()).decode("utf-8"))


@pytest.fixture(scope="module")
def rows(payload):
    return payload["observations"]


@pytest.fixture(scope="module")
def headline(rows):
    return [
        r for r in rows
        if r["family_id"] == "ca_null_matched_timing" and r["sample"] == "development"
    ]


def _panel(records, field="difference"):
    return [
        SyntheticRow(
            economic_asset=r["economic_asset"],
            bar_index=r["bar_index"],
            difference=r[field],
        )
        for r in records
    ]


def _rb(records, field="difference", block_bars=60):
    return estimate_on_axis(
        _panel(records, field), axis=BLOCK, block_bars=block_bars
    ).correlation


class TestB_TheControlVarianceCollapse:
    """Reviewer B, F1(c). The mechanism CD actually measured."""

    def test_the_control_leg_carries_a_fraction_of_the_admission_s_variance(
        self, headline
    ):
        admission = statistics.stdev(r["admission_forward"] for r in headline)
        control = statistics.stdev(r["control_forward"] for r in headline)
        assert control / admission == pytest.approx(0.168, abs=0.005)

    def test_the_paired_difference_is_almost_the_raw_admission_outcome(self, headline):
        correlation = pearson(
            [r["difference"] for r in headline],
            [r["admission_forward"] for r in headline],
        )
        assert correlation == pytest.approx(0.9868, abs=5e-4)

    def test_every_row_averages_two_hundred_control_draws(self, rows):
        assert {r["control_draws"] for r in rows} == {200}

    def test_the_opposite_direction_family_is_an_exact_rescaling(self, rows):
        family = [
            r for r in rows
            if r["family_id"] == "ca_null_opposite_direction"
            and r["sample"] == "development"
        ]
        assert family
        assert max(
            abs(r["control_forward"] + r["admission_forward"]) for r in family
        ) < 1e-12
        assert max(
            abs(r["difference"] - 2 * r["admission_forward"]) for r in family
        ) < 1e-12

    def test_and_therefore_its_r_b_IS_the_raw_admission_r_b(self, rows):
        """The ICC is scale-invariant, so `D = 2 x admission` cannot differ."""
        for sample in ("development", "validation", "holdout"):
            family = [
                r for r in rows
                if r["family_id"] == "ca_null_opposite_direction"
                and r["sample"] == sample
            ]
            assert _rb(family, "difference") == pytest.approx(
                _rb(family, "admission_forward"), abs=1e-9
            )

    def test_the_pairing_barely_moves_r_b_on_any_family(self, payload, rows):
        """The general form of the finding, across all fifteen panels."""
        for panel in payload["panels"]:
            records = [
                r for r in rows
                if r["family_id"] == panel["family_id"]
                and r["sample"] == panel["sample"]
            ]
            paired = _rb(records, "difference")
            raw = _rb(records, "admission_forward")
            assert abs(paired - raw) < 0.15, (panel["family_id"], panel["sample"])


class TestB_SameBarControlsExistAndDefeatTheFirstMechanism:
    """Reviewer B, F1(a) and F1(b)."""

    def test_two_families_draw_a_same_bar_control(self, rows):
        by_family = {}
        for r in rows:
            by_family.setdefault(r["family_id"], set()).add(r["radius_tier"])
        same_bar = [f for f, tiers in by_family.items() if tiers == {None}]
        assert sorted(same_bar) == [
            "ca_null_opposite_direction",
            "ca_null_random_direction_same_bar",
        ]

    def test_they_are_960_of_the_2390_rows(self, rows):
        assert len(rows) == 2390
        assert sum(1 for r in rows if r["radius_tier"] is None) == 960

    def test_the_matched_families_sit_overwhelmingly_at_the_tightest_tier(self, rows):
        tiers = [r["radius_tier"] for r in rows if r["radius_tier"] is not None]
        assert len(tiers) == 1430
        assert sum(1 for t in tiers if t == 0) == 1387

    def test_the_matching_radius_is_a_ceiling_in_the_source(self):
        import inspect

        from fmis.swing_lab import admission_matching

        source = inspect.getsource(admission_matching.eligible_pool)
        assert "distance < separation or distance > radius" in source

    def test_same_bar_families_are_NOT_less_dependent(self, payload):
        """Why 'use a same-instant control' cannot be the fix."""
        same_bar = [
            p["between_asset"]["point"]
            for p in payload["panels"]
            if p["family_id"] in (
                "ca_null_opposite_direction", "ca_null_random_direction_same_bar"
            )
            and p["sample"] == "development"
        ]
        assert len(same_bar) == 2
        assert min(same_bar) > 0.18


class TestB_ValidationIsNotASmallSampleEffect:
    """Reviewer B, F3. Reproduced on development sub-windows."""

    def test_no_development_sub_window_at_validation_s_size_reaches_its_value(
        self, headline
    ):
        ordered = sorted(headline, key=lambda r: r["bar_index"])
        low, high = ordered[0]["bar_index"], ordered[-1]["bar_index"]
        span = int((high - low) * 14 / 24)      # validation is 14 of development's 24 months
        values, start = [], low
        while start + span <= high:
            window = [r for r in ordered if start <= r["bar_index"] <= start + span]
            if 76 <= len(window) <= 96:         # validation's own n is 91
                estimate = _rb(window)
                if estimate is not None:
                    values.append(estimate)
            start += 60
        assert len(values) >= 25
        assert max(values) < 0.478, (
            "a development sub-window matched to validation's size reached "
            "validation's r_b, which would make the small-sample explanation live"
        )
        assert statistics.median(values) == pytest.approx(0.138, abs=0.02)


class TestB_ThePanelIsSurvivorOnly:
    """Reviewer B, F4. One bar-zero timestamp per universe."""

    def test_every_symbol_shares_one_bar_zero_per_universe(self, rows):
        from datetime import datetime, timedelta

        for universe in ("primary", "holdout"):
            zeros = {
                (
                    datetime.fromisoformat(r["as_of"])
                    - timedelta(hours=4 * r["bar_index"])
                ).isoformat()
                for r in rows
                if r["universe"] == universe
            }
            assert len(zeros) == 1, (universe, sorted(zeros))

    def test_which_means_no_instrument_listed_or_delisted_mid_window(self, rows):
        """Stated as what it is: a structural property, not a corrected bias."""
        assert len({r["symbol"] for r in rows if r["universe"] == "primary"}) == 15
        assert len({r["symbol"] for r in rows if r["universe"] == "holdout"}) == 21


class TestB_OverlapRetentionBiasesRhoWDownward:
    """Reviewer B, F6. The direction that flatters Milestone CB."""

    @staticmethod
    def _rho_w(records):
        return estimate_on_axis(_panel(records), axis=ASSET, block_bars=60).correlation

    def test_dropping_the_overlaps_raises_rho_w(self, headline):
        by_asset = {}
        for r in headline:
            by_asset.setdefault(r["economic_asset"], []).append(r["bar_index"])

        def overlapping(row):
            return any(
                abs(row["bar_index"] - other) < 60
                for other in by_asset[row["economic_asset"]]
                if other != row["bar_index"]
            )

        kept = self._rho_w(headline)
        dropped = self._rho_w([r for r in headline if not overlapping(r)])
        assert kept == pytest.approx(-0.0355, abs=5e-4)
        assert dropped == pytest.approx(-0.0135, abs=5e-3)
        assert dropped > kept, "retention must bias rho_w DOWNWARD"
        assert abs(dropped - kept) == pytest.approx(0.022, abs=5e-3)


class TestA_TheOverlapCorrectedDesignEffect:
    """Reviewer A, S1. Both the sealed and the corrected quantity."""

    def test_the_contemporaneity_fraction_on_the_headline_panel(self, headline):
        assert contemporaneity_fraction(_panel(headline), block_bars=60) == (
            pytest.approx(0.1880, abs=5e-5)
        )

    def test_the_artifact_carries_BOTH_the_sealed_and_the_corrected_figure(
        self, payload
    ):
        for panel in payload["panels"]:
            block = panel["contemporaneity"]
            assert block["sealed_correlation"] is not None
            assert block["overlap_corrected_correlation"] is not None
            assert block["effective_clusters_at_38_sealed"] is not None
            assert block["effective_clusters_at_38_corrected"] is not None
            # The correction always shrinks the correlation, hence RAISES K_eff.
            assert (
                block["effective_clusters_at_38_corrected"]
                > block["effective_clusters_at_38_sealed"]
            )

    def test_the_qualitative_verdict_survives_the_correction(self, payload):
        """Every corrected value still exceeds 1/K*, so nothing flips."""
        threshold = 1.0 / 467
        corrected = [
            p["contemporaneity"]["overlap_corrected_correlation"]
            for p in payload["panels"]
        ]
        assert len(corrected) == 15
        assert all(value > threshold for value in corrected)
        assert min(corrected) == pytest.approx(0.0174, abs=5e-4)
        assert max(corrected) == pytest.approx(0.1009, abs=5e-4)

    def test_the_corrected_effective_clusters_are_still_far_below_467(self, payload):
        at_106 = [
            p["contemporaneity"]["effective_clusters_at_106_corrected"]
            for p in payload["panels"]
        ]
        assert max(at_106) < 40.0
        assert 467 / max(at_106) > 12.0


class TestA_TheSealedStraddleRuleChangedNoVerdict:
    """Reviewer A, S7. Disclosed, pinned, and shown to be inert here."""

    def test_no_measured_panel_falls_in_the_band_where_the_rule_misreads(
        self, payload
    ):
        threshold = 1.0 / 467
        for panel in payload["panels"]:
            lower = panel["between_asset"]["lower"]
            # The rule misreads only when 0 < lower < 1/K*. No panel is there.
            assert not (0.0 < lower < threshold), (
                panel["family_id"], panel["sample"], lower
            )

    def test_so_the_sealed_wording_defect_changed_nothing(self, payload):
        assert payload["assessment"]["verdict"] == "inconclusive"
        assert payload["requirement"]["outcome"] == "inconclusive"


class TestC_TheCcResidualControlIsNotNegativeEverywhere:
    """Reviewer C, H3. The claim an earlier draft made and had to withdraw."""

    def test_one_panel_returns_a_positive_value(self, payload):
        values = [p["cc_residual_correlation"] for p in payload["panels"]]
        assert max(values) == pytest.approx(0.0045, abs=5e-5)
        assert sum(1 for v in values if v >= 0) == 1

    def test_but_it_is_still_uninformative_about_the_truth(self, payload):
        """What the control is actually worth, stated correctly."""
        residual = [p["cc_residual_correlation"] for p in payload["panels"]]
        measured = [p["between_asset"]["point"] for p in payload["panels"]]
        assert max(residual) - min(residual) < 0.34
        assert min(measured) > max(residual)
