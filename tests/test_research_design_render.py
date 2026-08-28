"""The report. **It prints what it is given and decides nothing.**

The renderer is held here rather than through the CLI because the CLI can only
show one assessment — Milestone CA's — and the shapes that matter most are the
ones CA does not produce: a prospective assessment, a caveat-free READY design,
and a powered target. Each is rendered once so no branch of the report is written
but never read.
"""

from __future__ import annotations

import pytest

from fmis.research_design.models import (
    AssessmentMode,
    DesignVerdict,
    ResolutionCriterion,
)
from fmis.research_design.render import render_design_assessment, wrap_text
from fmis.research_design.resolution import (
    DesignPoint,
    post_hoc_resolution,
    prospective_design,
    required_half_width,
)
from fmis.research_design.verdict import assess_research_design
from tests.research_design_helpers import (
    UNIT,
    a_dependence,
    a_frame,
    a_question,
    a_target,
    an_effect,
    an_estimator,
)


def _render(**overrides) -> str:
    frame = overrides.pop("frame", None) or a_frame()
    target = overrides.pop("target", None) or a_target()
    dependence = overrides.pop("dependence", None) or a_dependence()
    resolution = overrides.pop("resolution", None) or post_hoc_resolution(
        frame=frame,
        observed_half_width=overrides.pop("width", 0.5578),
        effect=an_effect(),
        target=target,
        estimator=an_estimator(),
    )
    return render_design_assessment(
        assess_research_design(
            assessment_id="r-1",
            question=a_question(),
            effect=an_effect(),
            uncertainty_unit=UNIT,
            dependence=dependence,
            estimator=an_estimator(),
            target=target,
            frames=(frame,),
            primary_sample=frame.name,
            resolution=resolution,
            sensitivity_correlations=overrides.pop(
                "correlations", (0.0, 0.05, 0.10, 0.20, 0.50)
            ),
            **overrides,
        )
    )


class TestTheReportShape:
    def test_every_line_fits_the_declared_width(self) -> None:
        for line in _render().splitlines():
            assert len(line) <= 78, line

    def test_it_is_deterministic(self) -> None:
        assert _render() == _render()

    def test_the_mode_banner_comes_before_anything_that_could_soften_it(self) -> None:
        report = _render()
        assert report.index("POST-HOC RESOLUTION DIAGNOSTIC") < report.index("VERDICT")

    def test_a_post_hoc_report_names_the_misuse_it_must_not_be_put_to(self) -> None:
        assert "must never be quoted as one" in _render()

    def test_a_post_hoc_report_states_the_smallest_effect_it_could_have_seen(self) -> None:
        assert "smallest resolvable" in _render()


class TestTheProspectiveShape:
    def test_a_prospective_report_is_labelled_prospective(self) -> None:
        frame = a_frame()
        report = _render(
            frame=frame,
            resolution=prospective_design(
                frame=frame,
                assumed_observation_sd=3.5,
                assumed_intracluster_correlation=0.0,
                dispersion_source="a prior milestone's published summary",
                effect=an_effect(),
                target=a_target(),
                estimator=an_estimator(),
            ),
        )
        assert "PROSPECTIVE DESIGN ASSESSMENT" in report
        assert "POST-HOC RESOLUTION DIAGNOSTIC" not in report

    def test_a_prospective_report_says_predicted_rather_than_observed(self) -> None:
        frame = a_frame()
        report = _render(
            frame=frame,
            resolution=prospective_design(
                frame=frame,
                assumed_observation_sd=3.5,
                assumed_intracluster_correlation=0.0,
                dispersion_source="a pilot",
                effect=an_effect(),
                target=a_target(),
                estimator=an_estimator(),
            ),
        )
        assert "predicted half-width" in report
        assert "observed half-width" not in report

    def test_a_prospective_report_states_no_smallest_resolvable_effect(self) -> None:
        """It has not measured one, so it does not print one."""
        frame = a_frame()
        report = _render(
            frame=frame,
            resolution=prospective_design(
                frame=frame,
                assumed_observation_sd=3.5,
                assumed_intracluster_correlation=0.0,
                dispersion_source="a pilot",
                effect=an_effect(),
                target=a_target(),
                estimator=an_estimator(),
            ),
        )
        assert "smallest resolvable" not in report


class TestTheVerdictLines:
    def test_a_ready_design_prints_no_caveats_and_says_so(self) -> None:
        report = _render(
            width=0.01,
            dependence=a_dependence(
                correlation=0.05, source="a measured pilot", overlapping_horizon=0
            ),
            correlations=(0.0, 0.05),
        )
        assert "READY" in report
        assert "none stated" in report

    def test_an_underpowered_design_says_what_no_edge_would_have_meant(self) -> None:
        report = _render()
        assert "UNDERPOWERED" in report
        assert "NOT 'no effect'" in report

    def test_a_powered_target_prints_its_power(self) -> None:
        target = a_target(
            criterion=ResolutionCriterion.POWERED_DETECTION, power=0.80
        )
        frame = a_frame()
        report = _render(
            frame=frame,
            target=target,
            resolution=post_hoc_resolution(
                frame=frame, observed_half_width=0.5578, effect=an_effect(),
                target=target, estimator=an_estimator(),
            ),
        )
        assert "powered_detection" in report
        assert "power                 0.8" in report

    def test_an_interval_target_prints_no_power_line(self) -> None:
        assert "  power " not in _render()

    def test_every_verdict_has_a_rendered_sentence(self) -> None:
        """A verdict with no line would print a blank where the answer belongs."""
        from fmis.research_design.render import _VERDICT_LINE

        assert set(_VERDICT_LINE) == set(DesignVerdict)

    def test_every_mode_has_a_rendered_banner(self) -> None:
        from fmis.research_design.render import _MODE_BANNER

        assert set(_MODE_BANNER) == set(AssessmentMode)


class TestTheGrowthTable:
    def test_it_prints_every_path_and_marks_the_unreachable_ones(self) -> None:
        report = _render()
        assert "more_clusters_same_density" in report
        assert "more_observations_same_clusters" in report
        assert "independent_observations" in report
        assert "UNREACHABLE" in report

    def test_it_prints_a_half_width_floor_where_one_exists(self) -> None:
        assert "half-width floor" in _render()


class TestWrapping:
    def test_a_word_longer_than_the_width_is_emitted_rather_than_dropped(self) -> None:
        long_word = "x" * 200
        lines = wrap_text(long_word)
        assert "".join(line.strip() for line in lines) == long_word

    def test_wrapping_preserves_every_word(self) -> None:
        text = " ".join(f"word{index}" for index in range(60))
        assert " ".join(" ".join(lines.split()) for lines in wrap_text(text)) == text

    def test_an_empty_string_wraps_to_nothing(self) -> None:
        assert wrap_text("") == ()

    def test_the_indent_is_applied_to_every_line(self) -> None:
        lines = wrap_text(" ".join(["word"] * 50), indent="    ")
        assert all(line.startswith("    ") for line in lines)


class TestTheRendererComputesNothing:
    def test_it_reports_the_half_width_it_was_handed(self) -> None:
        assert "0.5578" in _render()

    def test_it_reports_the_effect_magnitude_exactly_as_declared(self) -> None:
        """`Decimal("0.10")` renders as declared, not as a float's shortest repr."""
        assert "0.10 atr" in _render()

    def test_a_design_point_payload_is_json_safe(self) -> None:
        import json

        point = DesignPoint(
            clusters=15, observations=155, observations_per_cluster=10.3,
            half_width=0.5578, resolves=False, extrapolated=False,
            subsample_spread=0.01,
        )
        json.dumps(point.payload())
        assert point.is_measured

    def test_a_non_target_cannot_produce_a_required_half_width(self) -> None:
        with pytest.raises(TypeError, match="must be a DesignTarget"):
            required_half_width(an_effect(), "95%")  # type: ignore[arg-type]
