"""The published Milestone CD artifacts, pinned. **What CC does and CD did not.**

Independent review found that no committed test read CD's own artifacts, while
Milestone CC pins its capture in `tests/test_universe_study.py`. That made CD
weaker than CC on the exact axis CD exists to fix: if either published file were
corrupted, swapped or silently regenerated, nothing would fail.

These tests read the real files, verify their digests and seals, and pin the
headline figures report 0040 quotes. They are skipped — not failed — when the
artifacts are absent, so a clone without them still has a green suite; but when
they are present, every number in the report's §1 is checked against them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fmis.paired_dependence.artifact import (
    dependence_rows_of,
    read_dependence_study,
    verify_dependence_study_digest,
)
from fmis.paired_dependence.preregistration import CD_PREREGISTRATION_DIGEST

_ARTIFACTS = Path(__file__).resolve().parents[1] / "reports" / "artifacts"
_STUDY = _ARTIFACTS / "0040_cd_paired_dependence.json.gz"
_CAPTURE = _ARTIFACTS / "0040_cd_source_capture.json.gz"

#: The capture the published study was measured over.
CAPTURE_DIGEST = "07b500c7f26ac8b2a57784646654b620c2e4e4a20a475808f96b44c53b0f475f"


@pytest.fixture(scope="module")
def study():
    if not _STUDY.exists():
        pytest.skip(f"{_STUDY.name} is not present in this checkout")
    return read_dependence_study(_STUDY)


class TestThePublishedStudy:
    def test_its_content_digest_verifies(self, study):
        assert verify_dependence_study_digest(study)

    def test_it_was_measured_under_this_build_s_seal(self, study):
        study.require_seal()
        assert study.preregistration_digest == CD_PREREGISTRATION_DIGEST

    def test_it_names_the_capture_it_was_measured_over(self, study):
        study.require_source(CAPTURE_DIGEST)

    def test_it_carries_every_observation(self, study):
        rows = dependence_rows_of(study)
        assert len(rows) == 2390
        assert len({row.economic_asset for row in rows}) == 36
        assert {row.horizon for row in rows} == {24}

    def test_the_headline_panel_is_the_pre_registered_one(self, study):
        panel = self._headline(study)
        assert panel["family_id"] == "ca_null_matched_timing"
        assert panel["sample"] == "development"

    @staticmethod
    def _headline(study):
        return next(
            item
            for item in study.payload["panels"]
            if item["family_id"] == "ca_null_matched_timing"
            and item["sample"] == "development"
        )

    def test_the_headline_figures_report_0040_quotes(self, study):
        panel = self._headline(study)
        assert panel["between_asset"]["point"] == pytest.approx(0.198438, abs=5e-7)
        assert panel["between_asset"]["lower"] == pytest.approx(-0.049065, abs=5e-7)
        assert panel["between_asset"]["upper"] == pytest.approx(0.418073, abs=5e-7)
        assert panel["within_asset"]["point"] == pytest.approx(-0.035450, abs=5e-7)
        assert panel["within_asset"]["lower"] == pytest.approx(-0.077362, abs=5e-7)
        assert panel["within_asset"]["upper"] == pytest.approx(-0.006421, abs=5e-7)

    def test_the_five_counts_report_0040_quotes(self, study):
        coverage = self._headline(study)["coverage"]
        assert coverage["rows"] == 155
        assert coverage["admissions"] == 155
        assert coverage["economic_assets"] == 15
        assert coverage["provider_symbols"] == 15
        assert coverage["blocks_with_two_or_more_assets"] == 38

    def test_the_post_review_correction_is_carried_in_the_file(self, study):
        contemporaneity = self._headline(study)["contemporaneity"]
        assert contemporaneity["contemporaneity_fraction"] == pytest.approx(
            0.1880, abs=5e-5
        )
        assert contemporaneity["overlap_corrected_correlation"] == pytest.approx(
            0.037310, abs=5e-7
        )
        assert contemporaneity["effective_clusters_at_38_sealed"] == pytest.approx(
            4.56, abs=0.01
        )
        assert contemporaneity["effective_clusters_at_38_corrected"] == pytest.approx(
            15.96, abs=0.01
        )

    def test_the_verdict_is_inconclusive_and_approves_nothing(self, study):
        assessment = study.payload["assessment"]
        assert assessment["verdict"] == "inconclusive"
        assert assessment["is_approved_for_trading"] is False
        assert assessment["earns_forward_test"] is False

    def test_r_b_is_positive_in_every_one_of_the_fifteen_panels(self, study):
        points = [item["between_asset"]["point"] for item in study.payload["panels"]]
        assert len(points) == 15
        assert all(value > 0 for value in points)
        assert min(points) == pytest.approx(0.0951, abs=5e-5)
        assert max(points) == pytest.approx(0.5492, abs=5e-5)

    def test_the_cc_residual_control_is_NOT_negative_everywhere(self, study):
        """The claim an earlier draft of report 0040 made, and had to withdraw."""
        values = [item["cc_residual_correlation"] for item in study.payload["panels"]]
        assert max(values) == pytest.approx(0.0045, abs=5e-5)
        assert not all(value < 0 for value in values)


class TestThePublishedCapture:
    def test_it_verifies_and_holds_both_universes(self):
        if not _CAPTURE.exists():
            pytest.skip(f"{_CAPTURE.name} is not present in this checkout")
        from fmis.swing_lab.persistence_artifact import (
            read_persistence_capture,
            verify_capture_digest,
        )

        capture = read_persistence_capture(_CAPTURE)
        assert verify_capture_digest(capture)
        assert capture.content_digest == CAPTURE_DIGEST
        assert set(capture.universe_names) == {"primary", "holdout"}

    def test_it_reproduces_milestone_CA_s_published_candidate_counts(self):
        if not _CAPTURE.exists():
            pytest.skip(f"{_CAPTURE.name} is not present in this checkout")
        from fmis.swing_lab.persistence_artifact import read_persistence_capture

        capture = read_persistence_capture(_CAPTURE)
        # Report 0037 §4.1 published these from the capture Milestone CA measured.
        assert capture.universe("primary").candidates == 246
        assert capture.universe("holdout").candidates == 234
