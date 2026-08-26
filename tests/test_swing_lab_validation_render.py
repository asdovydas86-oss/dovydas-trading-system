"""The terminal report. **Renders what was measured, computes nothing.**

The report's *order* is its argument — verdict, seal, samples, results, plateau,
costs, walk-forward, decomposition, limitations — because a reader who stops
after one screen must not come away with a different impression from one who
reads to the end. That order is asserted here as an ordering of offsets rather
than as a set of substrings, since a report that printed the tables first and
the verdict last would pass a set check and fail the reader.

The other property under test is that nothing can be quoted without its basis:
the deciding cost scenario, the seal, whether the holdout was opened and whether
the no-lookahead suite was proven all appear, and a failing plateau neighbour is
printed rather than summarised away.
"""

from __future__ import annotations

import pytest

from fmis.swing_lab.preregistration import DECIDING_COST_POLICY_ID, PRE_REGISTRATION
from fmis.swing_lab.validation_render import (
    render_costs,
    render_decompositions,
    render_mechanics,
    render_plateau,
    render_results,
    render_samples,
    render_seal,
    render_validation_study,
    render_verdict_first,
    render_walk_forward,
)

from tests.test_swing_lab_validation_study import _study


@pytest.fixture(scope="module")
def study():
    return _study()


@pytest.fixture(scope="module")
def report(study) -> str:
    return render_validation_study(study)


# ------------------------------------------------------------------ order ---


def test_the_verdict_comes_before_any_table_that_could_argue_with_it(report) -> None:
    """A table of expectancies first would invite a reader to find the best row."""
    verdict = report.index("VALIDATION VERDICT")
    for later in ("PRE-REGISTRATION", "SAMPLES", "RESULTS", "COST SENSITIVITY",
                  "WALK-FORWARD", "DECOMPOSITION", "LIMITATIONS"):
        assert verdict < report.index(later), later


def test_the_sections_appear_in_the_documented_order(report) -> None:
    offsets = [
        report.index(name)
        for name in (
            "VALIDATION VERDICT", "PRE-REGISTRATION", "SAMPLES", "RESULTS",
            "CRITERIA, BY POLICY", "PARAMETER PLATEAU", "COST SENSITIVITY",
            "WALK-FORWARD", "DECOMPOSITION", "LIMITATIONS",
        )
    ]
    assert offsets == sorted(offsets)


def test_the_results_are_in_pre_registration_order_and_never_sorted_by_result(
    study, report
) -> None:
    offsets = [report.index(item.policy_id) for item in study.policies]
    assert offsets == sorted(offsets)
    assert [item.policy_id for item in study.policies] == [
        item.policy_id for item in PRE_REGISTRATION.hypotheses
    ]


# ------------------------------------------------------------------ basis ---


def test_no_number_can_be_quoted_without_its_basis(report) -> None:
    assert DECIDING_COST_POLICY_ID in report
    assert "No candidate may be selected on any other" in report
    assert "deciding cost scenario" in report


def test_the_seal_is_printed_and_a_mismatch_is_stated(study) -> None:
    text = render_seal(study)
    assert study.manifest.preregistration_digest in text
    assert "DOES NOT MATCH" in text


def test_the_lookahead_suite_status_is_stated_either_way(study) -> None:
    """Both branches, because only one of them can be checked on any one study."""
    from dataclasses import replace

    assert "passed for this capture" in render_seal(study)
    unproven = replace(
        study, manifest=replace(study.manifest, no_lookahead_proven=False)
    )
    assert "NOT PROVEN" in render_seal(unproven)


def test_every_sample_prints_its_contamination(study) -> None:
    text = render_samples(study)
    for spec in study.manifest.samples:
        assert spec["name"].upper() in text
        assert spec["contamination"][:40] in text


# ---------------------------------------------------------------- refusals ---


def test_a_refused_figure_prints_an_absence_and_its_sample_size(study) -> None:
    """`— (n=3)` and `0.0000 (n=3)` are different claims and must look different."""
    text = render_results(study)
    assert "— (n=" in text


def test_every_blocking_criterion_is_named(study, report) -> None:
    for item in study.policies:
        for criterion in item.assessment.blocking:
            assert criterion.name in report


def test_a_failing_plateau_neighbour_is_printed_not_summarised(study) -> None:
    with_plateau = [item for item in study.policies if item.plateau is not None]
    assert with_plateau
    for item in with_plateau:
        text = render_plateau(item.plateau, item.policy_id)
        for point in item.plateau.readings:
            assert f"{point.threshold:g}" in text
        # The primary point sits on BOTH axes of the cross, so it is marked once
        # per axis it centres — one point measured twice, never two points.
        marked = [p for p in item.plateau.readings if p.is_primary]
        assert marked
        assert len({p.policy_id for p in marked}) == 1
        assert text.count("*") == len(marked)


def test_a_policy_without_a_neighbourhood_says_so(study) -> None:
    text = render_plateau(None, "some_policy")
    assert "no pre-declared neighbourhood" in text


def test_the_walk_forward_prints_empty_windows(study) -> None:
    text = render_walk_forward(study.walk_forward, study.walk_forward_policy_id)
    assert "no re-optimisation" in text
    for window in study.walk_forward:
        assert window.label in text


def test_the_decomposition_states_whether_cohorts_agree(study) -> None:
    text = render_decompositions(study.decompositions)
    for cut in study.decompositions:
        assert cut.name in text
    assert any(
        phrase in text
        for phrase in ("agrees on sign", "DISAGREE on sign", "too few reportable")
    )


def test_the_cost_table_marks_the_deciding_scenario(study) -> None:
    text = render_costs(study)
    assert f"{DECIDING_COST_POLICY_ID} *" in text


def test_the_limitations_print_in_full(study, report) -> None:
    for item in study.manifest.limitations[:6]:
        assert item[:50] in report


def test_the_report_ends_with_both_digests(study, report) -> None:
    assert study.manifest.result_digest in report
    assert study.manifest.preregistration_digest in report


# --------------------------------------------------------------- mechanics ---


def test_the_mechanics_section_says_so_when_nothing_was_measured(report) -> None:
    """An empty table here would read as 'management does not help'."""
    assert "NOT MEASURED for this run" in report


def test_the_mechanics_section_renders_when_a_study_is_supplied() -> None:
    from decimal import Decimal

    from fmis.swing_lab.entry import PRE_DECLARED_ENTRY_POLICIES
    from fmis.swing_lab.exits import PRE_DECLARED_EXIT_POLICIES
    from fmis.swing_lab.metrics import compute_lab_metrics
    from fmis.swing_lab.validation_mechanics import (
        AmbiguityReading,
        EntryMeasurement,
        ExitMeasurement,
        MechanicsStudy,
    )
    from tests.test_swing_lab_metrics import many

    metrics = compute_lab_metrics(many(25, "0.3"), label="probe")
    study = MechanicsStudy(
        geometry_policy_id="probe",
        sample="development",
        entries=(
            EntryMeasurement(
                policy=PRE_DECLARED_ENTRY_POLICIES[0], trades=(), filled=25,
                missed=5, miss_reasons=(("continuation_not_confirmed", 5),),
                metrics=metrics, median_bars_waited=1.0, gapped_fills=0,
            ),
        ),
        exits=(
            ExitMeasurement(
                policy=PRE_DECLARED_EXIT_POLICIES[0], used_ladder=True, trades=(),
                metrics=metrics, armed=10, ambiguous=2, resolved_by_descent=4,
                mean_mfe_captured=Decimal("0.4"),
            ),
        ),
        ambiguity=AmbiguityReading(
            without_ladder=19, with_ladder=2, resolved=17, still_ambiguous=2,
            unresolved_spans=(("BTCUSDT", "2024-01-01T00:00:00+00:00"),),
        ),
    )
    text = render_mechanics(study)
    assert "89.5%" in text                       # 17 of 19, from the engine
    assert "never guessed" in text
    assert "continuation_not_confirmed" in text
    assert "NO ladder" in text


def test_the_ambiguity_section_reports_a_zero_resolution_without_dividing(study) -> None:
    from fmis.swing_lab.validation_mechanics import AmbiguityReading, MechanicsStudy

    empty = MechanicsStudy(
        geometry_policy_id="probe", sample="development", entries=(), exits=(),
        ambiguity=AmbiguityReading(
            without_ladder=0, with_ladder=0, resolved=0, still_ambiguous=0,
            unresolved_spans=(),
        ),
    )
    text = render_mechanics(empty)
    assert "resolved" in text
    assert "%" not in text.split("§7")[0].split("resolved")[-1][:20]
