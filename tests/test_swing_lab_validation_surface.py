"""The `/validation` page. **A read model and an HTML page, computing nothing.**

Two guarantees the tests below exist to hold:

* **the page can state nothing the engine refused.** Every figure arrives
  already reduced; where `fmis.swing_lab.metrics` declined to state a rate the
  page shows an absence with a reason, and there is no code path that could
  compute one.
* **the page cannot flatter a result.** The seal, the deciding cost scenario,
  whether the holdout was opened and whether the no-lookahead suite was proven
  are all rendered — so a number cannot be read without the basis it rests on.

Plus the hostile checks every read-only surface in this repository carries:
script injection, an unverified digest, and nothing loaded at all.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from fmis.operator_dashboard.compose import DASHBOARD_LIMITATIONS
from fmis.operator_dashboard.models import ValidationView
from fmis.operator_dashboard.render import render_page
from fmis.operator_dashboard.sections import validation_view
from fmis.swing_lab.preregistration import PRE_REGISTRATION
from fmis.swing_lab.validation_artifact import (
    ValidationArtifact,
    encode_validation_study,
    read_validation_artifact,
    verify_preregistration_seal,
    verify_result_digest,
    write_validation_study,
)

from tests.test_swing_lab_validation_study import _study

_T0 = datetime(2026, 8, 25, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def artifact(tmp_path_factory) -> ValidationArtifact:
    path = tmp_path_factory.mktemp("surface") / "by.json"
    write_validation_study(_study(), path)
    return read_validation_artifact(path)


@pytest.fixture(scope="module")
def view(artifact) -> ValidationView:
    return validation_view(
        artifact,
        digest_verified=verify_result_digest(artifact),
        seal_matches=verify_preregistration_seal(artifact),
    )


def _snapshot(subject: ValidationView | None):
    """A minimal snapshot carrying only what the validation page reads."""
    from fmis.operator_dashboard.compose import _section
    from fmis.operator_dashboard.models import (
        DashboardSection,
        DashboardSectionStatus,
        OperatorDashboardSnapshot,
        OverviewCounts,
    )

    def absent(name: str) -> DashboardSection:
        return DashboardSection(
            name=name,
            status=DashboardSectionStatus.UNAVAILABLE,
            unavailable_reason="not built for this test",
        )

    section = (
        None
        if subject is None
        else _section(
            "validation", subject, as_of=None,
            source=f"saved validation artifact · {subject.experiment_id}",
            empty=not subject.policies,
        )
    )
    return OperatorDashboardSnapshot(
        refreshed_at=_T0,
        reference_time=_T0,
        counts=OverviewCounts(),
        pulse=absent("pulse"),
        macro=absent("macro"),
        swing=absent("swing"),
        portfolio=absent("portfolio"),
        paper=absent("paper"),
        performance=absent("performance"),
        health=absent("health"),
        validation=section,
        warnings=(),
        limitations=DASHBOARD_LIMITATIONS,
    )


# ------------------------------------------------------------ the read model ---


def test_the_view_carries_every_sealed_hypothesis_in_declaration_order(view) -> None:
    """Never sorted by result — a table sorted by expectancy has chosen a winner."""
    assert [item.policy_id for item in view.policies] == [
        item.policy_id for item in PRE_REGISTRATION.hypotheses
    ]


def test_the_view_carries_each_sample_with_its_contamination(view) -> None:
    """The caveat cannot be separated from the row it qualifies."""
    assert len(view.samples) == 3
    for row in view.samples:
        assert row.contamination.strip()
        assert row.symbols


def test_the_view_marks_exactly_one_deciding_cost_scenario_per_cell_group(view) -> None:
    for policy in view.policies:
        deciding = {item.sample for item in policy.cells if item.is_deciding}
        assert deciding == {"development", "validation", "holdout"}
        assert all(
            item.cost_policy_id == view.deciding_cost_policy_id
            for item in policy.cells
            if item.is_deciding
        )


def test_the_view_states_no_rate_the_engine_refused(view) -> None:
    """Where metrics declined a figure, the view carries the absence and its reason."""
    absent = [
        item
        for policy in view.policies
        for item in policy.cells
        if item.expectancy is None
    ]
    assert absent
    assert all(item.expectancy_reason for item in absent)


def test_the_view_carries_the_non_structural_flag(view) -> None:
    controls = [item for item in view.policies if not item.is_structural]
    assert len(controls) == 1
    assert controls[0].role == "non_structural_control"


def test_the_view_carries_the_plateau_including_failing_neighbours(view) -> None:
    with_plateau = [item for item in view.policies if item.plateau is not None]
    assert with_plateau
    for item in with_plateau:
        assert len(item.plateau.points) >= 3
        centres = [point for point in item.plateau.points if point.is_primary]
        assert centres
        assert len({point.expectancy for point in centres}) == 1


def test_the_view_never_approves_trading(view) -> None:
    assert view.is_approved_for_trading is False


def test_the_view_reports_a_mismatched_seal_as_mismatched(view) -> None:
    """A fixture study's rules are not the repository's, and the view says so."""
    assert view.seal_matches is False


# ------------------------------------------------------------------ the page ---


def test_the_page_renders_with_a_study_loaded(view) -> None:
    html = render_page(_snapshot(view), "/validation")
    assert "Validation verdict" in html
    assert "Pre-registration" in html
    assert view.deciding_cost_policy_id in html


def test_the_page_says_so_plainly_with_nothing_loaded() -> None:
    """An empty table here would read as 'nothing works' rather than 'nothing was measured'."""
    html = render_page(_snapshot(None), "/validation")
    assert "No validation study is loaded" in html


def test_the_page_states_no_candidate_when_there_is_none(view) -> None:
    html = render_page(_snapshot(view), "/validation")
    assert "NO FORWARD-TEST CANDIDATE" in html


def test_the_page_names_every_blocking_criterion(view) -> None:
    html = render_page(_snapshot(view), "/validation")
    for policy in view.policies:
        for name in policy.blocking_criteria:
            assert name in html


def test_the_page_prints_every_samples_contamination(view) -> None:
    """A caveat in a footnote is a caveat a reader will quote a number without."""
    html = render_page(_snapshot(view), "/validation")
    for row in view.samples:
        assert row.contamination[:40] in html


def test_the_page_marks_the_deciding_cost_scenario(view) -> None:
    html = render_page(_snapshot(view), "/validation")
    assert "deciding" in html
    assert "no candidate may be selected on the frictionless column" in html


def test_the_page_reports_a_mismatched_seal_loudly(view) -> None:
    html = render_page(_snapshot(view), "/validation")
    assert "DOES NOT MATCH" in html


def test_the_page_reports_an_unopened_holdout(artifact) -> None:
    subject = validation_view(artifact, digest_verified=True, seal_matches=True)
    html = render_page(_snapshot(subject), "/validation")
    assert "opened" in html


def test_the_page_reports_an_unverified_digest_as_unverified(artifact) -> None:
    subject = validation_view(artifact, digest_verified=False, seal_matches=False)
    assert "NOT VERIFIED" in render_page(_snapshot(subject), "/validation")


def test_the_page_reports_an_unproven_lookahead_suite(view) -> None:
    html = render_page(_snapshot(view), "/validation")
    assert "No-lookahead suite" in html


def test_the_page_escapes_a_hostile_experiment_id(artifact) -> None:
    payload = json.loads(json.dumps(artifact.payload))
    payload["manifest"]["experiment_id"] = "<script>alert(1)</script>"
    subject = validation_view(
        ValidationArtifact(payload), digest_verified=False, seal_matches=False
    )
    html = render_page(_snapshot(subject), "/validation")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_the_page_escapes_a_hostile_symbol(artifact) -> None:
    payload = json.loads(json.dumps(artifact.payload))
    payload["manifest"]["samples"][0]["symbols"][0] = "<img src=x onerror=1>"
    subject = validation_view(
        ValidationArtifact(payload), digest_verified=False, seal_matches=False
    )
    html = render_page(_snapshot(subject), "/validation")
    assert "<img src=x" not in html


def test_the_validation_route_is_in_the_navigation(view) -> None:
    assert "/validation" in render_page(_snapshot(view), "/")


def test_the_walk_forward_table_shows_empty_windows(view) -> None:
    """A curve that dropped its empty windows would read as continuous coverage."""
    html = render_page(_snapshot(view), "/validation")
    assert "Walk-forward" in html
    assert view.walk_forward
    for window in view.walk_forward:
        assert window.label in html


def test_every_decomposition_reaches_the_page(view) -> None:
    html = render_page(_snapshot(view), "/validation")
    for cut in view.decompositions:
        assert cut.name in html


def test_the_limitations_reach_the_page_in_full(view) -> None:
    html = render_page(_snapshot(view), "/validation")
    assert view.limitations
    for item in view.limitations[:4]:
        assert item[:40].replace("&", "&amp;") in html


# ------------------------------------------------- the REAL server chain ---
#
# `refresh()` accepted `geometry` and `validation` and forwarded neither, so
# `fmits dashboard --validation-artifact v.json` decoded the artifact, handed it
# to the refresher, and the page still said nothing was loaded. The tests above
# build a snapshot by hand and so could not see that; these drive the production
# chain end to end — SnapshotHolder -> refresh -> build_snapshot -> render_page —
# which is the only path the shipped command actually uses.


def _refresher():
    from functools import partial

    from fmis.operator_dashboard.compose import refresh
    from tests.test_operator_dashboard_compose import _runners

    return partial(refresh, **_runners())


def test_a_validation_artifact_reaches_the_page_through_the_real_chain(view) -> None:
    from fmis.operator_dashboard.server import SnapshotHolder

    holder = SnapshotHolder(refresher=_refresher(), symbols=(), validation=view)
    snapshot = holder.current()
    assert snapshot.validation is not None
    assert snapshot.validation.data is view
    html = render_page(snapshot, "/validation")
    assert "No validation study is loaded" not in html
    assert "NO FORWARD-TEST CANDIDATE" in html


def test_a_geometry_artifact_reaches_the_page_through_the_real_chain() -> None:
    """The same defect existed for `--geometry-artifact` since Milestone BX."""
    from fmis.operator_dashboard.models import GeometryView
    from fmis.operator_dashboard.server import SnapshotHolder

    subject = GeometryView(experiment_id="wiring-probe", policies=())
    snapshot = SnapshotHolder(
        refresher=_refresher(), symbols=(), geometry=subject
    ).current()
    assert snapshot.geometry is not None
    assert snapshot.geometry.data is subject


def test_the_real_chain_still_says_so_when_no_artifact_is_supplied() -> None:
    """The negative control: the wiring must not fabricate a section."""
    from fmis.operator_dashboard.server import SnapshotHolder

    snapshot = SnapshotHolder(refresher=_refresher(), symbols=()).current()
    assert snapshot.validation is None
    assert "No validation study is loaded" in render_page(snapshot, "/validation")
