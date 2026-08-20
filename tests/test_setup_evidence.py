"""Milestone BR — Setup Evidence: the deterministic explanation layer.

The claims this suite exists to pin, each independently:

* the projection **changes nothing** — every field it carries through is
  identical, by value and by reference where the source held a reference;
* `decision_ready` is a total function of `sufficiency` **alone**, proven by
  varying every other field and asserting the answer never moves;
* the four groups partition the items: no item is in two groups, and every
  item's status agrees with the group it sits in;
* correlated readings are never counted as independent corroboration;
* confluence is derived on every call and stored nowhere;
* no score, weight, confidence or probability field exists anywhere;
* equal assessments produce byte-identical reports;
* a `WAIT` page says honestly that nothing supports a directional view.

Expected values are derived by hand from the mapping rules, never by calling
the projection under test and asserting it equals itself.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone

import pytest

from fmis.decision_context import ContextState
from fmis.decision_support import Alignment, OverallState
from fmis.evidence import EvidenceFamily
from fmis.setup_evidence import (
    ConfluenceSummary,
    EvidenceItem,
    SetupEvidenceStatus,
    SetupEvidenceError,
    SetupEvidenceReport,
    SetupIdentityRef,
    decision_ready_for,
    project_setup_evidence,
    render_setup_evidence,
)
from fmis.setup_evidence.correlation import (
    KEY_CALIBRATION,
    KEY_CONFIRMATION,
    KEY_CONTEXT_TREND,
    KEY_EVIDENCE_ALIGNMENT,
    KEY_GEOMETRY,
    KEY_REGIME_GATE,
    KEY_SETUP_TREND,
    FACTOR_FAMILIES,
    independent_pairs_exist,
)
from fmis.setup_evidence.render import PAGE_WIDTH
from fmis.structural_trend import StructuralTrendType
from fmis.swing_setup import SetupState, evaluate_setup

from test_swing_setup_policy import base_inputs, mirror

_AS_OF = datetime(2026, 1, 2, tzinfo=timezone.utc)


# ============ fixtures =======================================================


def confirmed():
    """A CONFIRMED assessment: both trends sustained, evidence agreeing."""
    return evaluate_setup(base_inputs())


def candidate():
    """A CANDIDATE: the confirming break is stale, so confirmation is awaited."""
    return evaluate_setup(base_inputs(execution_closed_count=200))


def wait_no_direction():
    """A WAIT with nothing readable at all — the honest-empty case."""
    return evaluate_setup(
        base_inputs(
            context_structural_trend=StructuralTrendType.INDETERMINATE,
            setup_structural_trend=StructuralTrendType.INDETERMINATE,
            evidence_state=OverallState.INSUFFICIENT_DATA,
            evidence_dominant_alignment=None,
        )
    )


def wait_conflicting():
    """A WAIT where families were read and disagreed with themselves."""
    return evaluate_setup(
        base_inputs(
            context_structural_trend=StructuralTrendType.NEUTRAL,
            setup_structural_trend=StructuralTrendType.NEUTRAL,
            evidence_state=OverallState.WAIT,
        )
    )


def wait_one_lean():
    """A WAIT where exactly one family leaned — evidence exists, quorum did not."""
    return evaluate_setup(
        base_inputs(
            setup_structural_trend=StructuralTrendType.INDETERMINATE,
            evidence_state=OverallState.INSUFFICIENT_DATA,
            evidence_dominant_alignment=None,
        )
    )


ALL_FIXTURES = (
    confirmed,
    candidate,
    wait_no_direction,
    wait_conflicting,
    wait_one_lean,
)


# ============ 1. the projection alters nothing ==============================


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_the_projection_does_not_mutate_the_assessment(build) -> None:
    """The assessment is read, never written. Compared field by field."""
    assessment = build()
    before = {f.name: getattr(assessment, f.name) for f in dataclasses.fields(assessment)}
    project_setup_evidence(assessment)
    after = {f.name: getattr(assessment, f.name) for f in dataclasses.fields(assessment)}
    assert before == after


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_carried_fields_are_identical_not_merely_equal(build) -> None:
    """Thesis, invalidation and regime context are carried by reference.

    Equality would pass if the projection had rebuilt them from parsed text.
    Identity proves it did not touch them at all.
    """
    assessment = build()
    report = project_setup_evidence(assessment)
    assert report.thesis is assessment.thesis
    assert report.invalidation is assessment.invalidation
    assert report.regime_context is assessment.regime_context
    assert report.symbol == assessment.symbol
    assert report.as_of == assessment.as_of


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_sufficiency_is_carried_not_reinterpreted(build) -> None:
    assessment = build()
    report = project_setup_evidence(assessment)
    assert report.sufficiency is assessment.sufficiency


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_no_limitation_is_lost_though_a_restatement_may_be_relocated(build) -> None:
    """Nothing is dropped. A restatement is *moved*, and must still be there.

    A limitation that merely repeats a factor already projected as its own item
    is not carried a second time (see `_factor_restatement_lines`). That is a
    relocation, never a loss: this asserts every such line still corresponds to
    a real item in the report, and that every other limitation survives verbatim.
    """
    from fmis.setup_evidence.project import _factor_restatement_lines

    assessment = build()
    report = project_setup_evidence(assessment)
    projected = {item.statement for item in report.unavailable}
    restatements = _factor_restatement_lines(assessment)

    factor_keys = {item.key for item in report.all_items}
    for line in assessment.limitations:
        if line in restatements:
            # It was relocated, so the factor it restates must be present.
            family = line.split(" ", 1)[0]
            assert f"factor:{family}" in factor_keys, line
        else:
            assert line in projected, line


# ============ 2. decision_ready is sufficiency, and only sufficiency ========


def test_decision_ready_covers_every_context_state() -> None:
    """A fourth ContextState member must fail here rather than default to ready."""
    for state in ContextState:
        assert isinstance(decision_ready_for(state), bool)


def test_decision_ready_matches_context_state_semantics_exactly() -> None:
    """LIMITED is ready: nothing blocking is missing. INSUFFICIENT is not."""
    assert decision_ready_for(ContextState.SUFFICIENT) is True
    assert decision_ready_for(ContextState.LIMITED) is True
    assert decision_ready_for(ContextState.INSUFFICIENT) is False


def test_decision_ready_rejects_a_non_context_state() -> None:
    with pytest.raises(TypeError):
        decision_ready_for("sufficient")


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_report_decision_ready_equals_the_pure_function(build) -> None:
    assessment = build()
    report = project_setup_evidence(assessment)
    assert report.decision_ready is decision_ready_for(assessment.sufficiency)


def test_decision_ready_does_not_move_when_anything_else_changes() -> None:
    """The load-bearing test: only `sufficiency` can change the answer.

    Every other dimension the assessment carries — state, direction, evidence
    agreement, geometry, limitations — is varied while sufficiency is held, and
    the answer is asserted constant. If a future edit made `decision_ready`
    consult the evidence groups, this fails.
    """
    for state in ContextState:
        answers = set()
        for build in ALL_FIXTURES:
            assessment = build()
            varied = dataclasses.replace(assessment, sufficiency=state)
            answers.add(project_setup_evidence(varied).decision_ready)
        assert len(answers) == 1, (state, answers)
        assert answers.pop() is decision_ready_for(state)


def test_decision_ready_is_not_a_direction_and_not_an_instruction() -> None:
    """`decision_ready` on a WAIT with sufficient context is still True.

    Readiness is about information, never about whether to act. A WAIT result
    built on complete data is fully "decision ready" — the decision it is ready
    for is *not to trade*.
    """
    report = project_setup_evidence(wait_no_direction())
    assert report.state_text == "WAIT"
    assert report.direction_text is None
    assert report.sufficiency is ContextState.SUFFICIENT
    assert report.decision_ready is True


# ============ 3. the four groups partition the items ========================


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_no_item_appears_in_two_groups(build) -> None:
    report = project_setup_evidence(build())
    keys = [item.key for item in report.all_items]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_every_item_status_agrees_with_its_group(build) -> None:
    report = project_setup_evidence(build())
    for group, status in (
        (report.supporting, SetupEvidenceStatus.SUPPORTING),
        (report.conflicting, SetupEvidenceStatus.CONFLICTING),
        (report.missing, SetupEvidenceStatus.MISSING),
        (report.unavailable, SetupEvidenceStatus.UNAVAILABLE),
    ):
        for item in group:
            assert item.status is status


def test_a_report_holding_one_item_in_two_groups_is_unrepresentable() -> None:
    """The invariant is enforced by the type, not only by the builder."""
    item = EvidenceItem(
        key="k",
        families=(),
        status=SetupEvidenceStatus.SUPPORTING,
        statement="s",
        observed="o",
        source="src",
    )
    with pytest.raises(SetupEvidenceError, match="appears twice"):
        SetupEvidenceReport(
            symbol="BTCUSDT",
            as_of=_AS_OF,
            state_text="WAIT",
            direction_text=None,
            thesis=(),
            supporting=(item, item),
            conflicting=(),
            missing=(),
            unavailable=(),
            invalidation=(),
            regime_context=(),
            family_summary=(),
            confluence=_empty_confluence(),
            sufficiency=ContextState.SUFFICIENT,
            decision_ready=True,
            decision_ready_reason="r",
            warnings=(),
            open_questions=(),
        )


def test_a_report_whose_group_disagrees_with_a_status_is_unrepresentable() -> None:
    item = EvidenceItem(
        key="k",
        families=(),
        status=SetupEvidenceStatus.MISSING,
        statement="s",
        observed="o",
        source="src",
    )
    with pytest.raises(SetupEvidenceError, match="group and status must agree"):
        SetupEvidenceReport(
            symbol="BTCUSDT",
            as_of=_AS_OF,
            state_text="WAIT",
            direction_text=None,
            thesis=(),
            supporting=(item,),
            conflicting=(),
            missing=(),
            unavailable=(),
            invalidation=(),
            regime_context=(),
            family_summary=(),
            confluence=_empty_confluence(),
            sufficiency=ContextState.SUFFICIENT,
            decision_ready=True,
            decision_ready_reason="r",
            warnings=(),
            open_questions=(),
        )


def _empty_confluence() -> ConfluenceSummary:
    return ConfluenceSummary(
        agreeing_families=(),
        conflicting_families=(),
        agreeing_item_count=0,
        independent_agreeing_families=0,
        independence_established=False,
        derived_from=(),
        caveats=(),
    )


# ============ 4. status mapping is deterministic and hand-checkable =========


def test_agreeing_factors_are_supporting_on_a_directional_assessment() -> None:
    assessment = confirmed()
    report = project_setup_evidence(assessment)
    supporting = {item.key for item in report.supporting}
    assert KEY_CONTEXT_TREND in supporting
    assert KEY_SETUP_TREND in supporting
    assert KEY_EVIDENCE_ALIGNMENT in supporting


def test_a_family_that_disagrees_with_itself_is_conflicting_not_unavailable() -> None:
    """CONFLICTING and UNAVAILABLE are different facts and stay apart."""
    report = project_setup_evidence(wait_conflicting())
    conflicting = {item.key for item in report.conflicting}
    assert KEY_CONTEXT_TREND in conflicting
    assert KEY_SETUP_TREND in conflicting
    unavailable = {item.key for item in report.unavailable}
    assert KEY_CONTEXT_TREND not in unavailable


def test_an_unreadable_family_is_unavailable_not_missing() -> None:
    report = project_setup_evidence(wait_no_direction())
    unavailable = {item.key for item in report.unavailable}
    assert {KEY_CONTEXT_TREND, KEY_SETUP_TREND, KEY_EVIDENCE_ALIGNMENT} <= unavailable
    assert not report.missing


def test_an_awaited_confirmation_is_missing_and_a_occurred_one_is_supporting() -> None:
    awaiting = project_setup_evidence(candidate())
    assert awaiting.state_text == "CANDIDATE"
    assert KEY_CONFIRMATION in {item.key for item in awaiting.missing}

    occurred = project_setup_evidence(confirmed())
    assert occurred.state_text == "CONFIRMED"
    assert KEY_CONFIRMATION in {item.key for item in occurred.supporting}


def test_the_absent_calibration_is_always_reported_never_omitted() -> None:
    for build in ALL_FIXTURES:
        report = project_setup_evidence(build())
        assert KEY_CALIBRATION in {item.key for item in report.unavailable}


def test_a_wait_assessment_projects_no_geometry() -> None:
    """A WAIT carries no protective level, so no geometry item is invented."""
    report = project_setup_evidence(wait_no_direction())
    assert KEY_GEOMETRY not in {item.key for item in report.all_items}


def test_the_mapping_is_a_mirror_across_both_sides() -> None:
    """The projection is symmetric: mirroring the inputs mirrors nothing but values."""
    left = project_setup_evidence(evaluate_setup(base_inputs()))
    right = project_setup_evidence(evaluate_setup(mirror(base_inputs())))
    assert left.state_text == right.state_text
    assert [i.key for i in left.supporting] == [i.key for i in right.supporting]
    assert left.confluence.agreeing_families == right.confluence.agreeing_families
    assert left.decision_ready is right.decision_ready
    assert left.direction_text != right.direction_text


# ============ 5. deduplication by stable key ================================


def test_repeated_limitations_are_collapsed_to_one_item() -> None:
    """The same inherited line arriving twice is one gap, not two."""
    assessment = evaluate_setup(base_inputs(inherited_limitations=("X-1: dup", "X-1: dup")))
    report = project_setup_evidence(assessment)
    matching = [i for i in report.unavailable if i.statement == "X-1: dup"]
    assert len(matching) == 1


def test_the_trigger_is_not_projected_as_a_second_item() -> None:
    """`Trigger.statement` *is* `confirmation[0]`; projecting both would double it."""
    assessment = confirmed()
    assert assessment.trigger is not None
    assert assessment.trigger.statement == assessment.confirmation[0]

    report = project_setup_evidence(assessment)
    statements = [item.statement for item in report.all_items]
    assert statements.count(assessment.confirmation[0]) == 1
    assert "trigger" not in {item.key for item in report.all_items}


def test_the_trigger_detail_is_preserved_in_the_confirmation_inputs() -> None:
    """Deduplicating must not lose the parts that were genuinely additional."""
    assessment = confirmed()
    report = project_setup_evidence(assessment)
    item = next(i for i in report.all_items if i.key == KEY_CONFIRMATION)
    assert item.inputs["trigger_kind"] == assessment.trigger.kind.value
    assert item.inputs["trigger_level"] == assessment.trigger.level.price
    assert item.inputs["trigger_bar_index"] == assessment.trigger.bar_index


def test_the_protective_level_is_projected_once_not_three_times() -> None:
    """The level appears as `stop`, inside `invalidation`, and inside `risk_reward`."""
    assessment = confirmed()
    assert assessment.stop is not None
    assert assessment.risk_reward is not None
    assert assessment.risk_reward.stop == assessment.stop.price
    assert str(assessment.stop.price) in assessment.invalidation[0]

    report = project_setup_evidence(assessment)
    geometry = [i for i in report.all_items if i.key == KEY_GEOMETRY]
    assert len(geometry) == 1


def test_a_limitation_restating_a_factor_is_not_reported_a_second_time() -> None:
    """One fact, two sections, found on the live BTCUSDT page.

    The policy appends a limitation for every family that cast no vote, which
    restates a factor this projection has already emitted as its own item.
    Reporting both put all three factors on the page twice.
    """
    assessment = wait_conflicting()
    report = project_setup_evidence(assessment)

    conflicting_keys = {item.key for item in report.conflicting}
    assert KEY_CONTEXT_TREND in conflicting_keys

    for item in report.unavailable:
        assert "cast no vote" not in item.statement, item.statement


def test_the_restatement_reconstruction_still_matches_what_the_policy_emits() -> None:
    """The coupling that makes the deduplication work, asserted directly.

    `_factor_restatement_lines` rebuilds the policy's own wording rather than
    parsing it. If that wording ever changes, this fails loudly here instead of
    the duplicates quietly reappearing on the page.
    """
    from fmis.setup_evidence.project import _factor_restatement_lines

    assessment = wait_conflicting()
    rebuilt = _factor_restatement_lines(assessment)
    restated = [line for line in assessment.limitations if "cast no vote" in line]
    assert restated, "the fixture must actually produce restatement lines"
    for line in restated:
        assert line in rebuilt, line


def test_an_unrelated_limitation_is_never_dropped_by_the_restatement_filter() -> None:
    """The filter removes restatements only — a real gap must always survive."""
    assessment = evaluate_setup(
        base_inputs(
            context_structural_trend=StructuralTrendType.NEUTRAL,
            setup_structural_trend=StructuralTrendType.NEUTRAL,
            evidence_state=OverallState.WAIT,
            inherited_limitations=("X-7: a genuine inherited gap",),
        )
    )
    report = project_setup_evidence(assessment)
    statements = {item.statement for item in report.unavailable}
    assert "X-7: a genuine inherited gap" in statements


def test_two_different_items_sharing_a_key_are_refused_not_merged() -> None:
    from fmis.setup_evidence.project import _deduplicate

    one = EvidenceItem(
        key="k", families=(), status=SetupEvidenceStatus.SUPPORTING,
        statement="a", observed="o", source="s",
    )
    other = EvidenceItem(
        key="k", families=(), status=SetupEvidenceStatus.SUPPORTING,
        statement="b", observed="o", source="s",
    )
    assert _deduplicate([one, one]) == (one,)
    with pytest.raises(SetupEvidenceError, match="share the key"):
        _deduplicate([one, other])


# ============ 6. correlated readings are not independent votes ==============


def test_confluence_counts_families_not_items() -> None:
    """Three agreeing items over two families is two, never three."""
    report = project_setup_evidence(confirmed())
    assert report.confluence.agreeing_item_count == 3
    assert report.confluence.independent_agreeing_families == 2
    assert set(report.confluence.agreeing_families) == {
        EvidenceFamily.TREND,
        EvidenceFamily.MOMENTUM,
    }


def test_independence_is_not_established_for_the_live_factor_set() -> None:
    """The finding this milestone exists to surface.

    All three directional factors draw on TREND, so no two of them are
    family-disjoint, and the two structural-trend readings share a method while
    the setup-role pair shares a series. The report must say so rather than
    presenting three agreeing items as three-fold corroboration.
    """
    report = project_setup_evidence(confirmed())
    assert report.confluence.independence_established is False
    assert report.confluence.caveats


def test_the_regime_precondition_never_counts_as_a_family_vote() -> None:
    """A gate that the trend factor already satisfied is not a second opinion."""
    report = project_setup_evidence(confirmed())
    gate = next(i for i in report.all_items if i.key == KEY_REGIME_GATE)
    assert gate.families == ()
    assert KEY_CONTEXT_TREND in gate.correlated_with
    assert gate.key not in report.confluence.derived_from


def test_geometry_and_calibration_carry_no_family_and_cannot_inflate_confluence() -> None:
    """A favourable ratio is not corroboration of a direction."""
    report = project_setup_evidence(confirmed())
    for key in (KEY_GEOMETRY, KEY_CALIBRATION, KEY_CONFIRMATION):
        item = next(i for i in report.all_items if i.key == key)
        assert item.families == ()
        assert key not in report.confluence.derived_from


def test_independent_pairs_requires_disjoint_families_and_no_named_correlation() -> None:
    def item(key: str, families: tuple[EvidenceFamily, ...]) -> EvidenceItem:
        return EvidenceItem(
            key=key, families=families, status=SetupEvidenceStatus.SUPPORTING,
            statement="s", observed="o", source="src",
        )

    # Disjoint families, no declared correlation -> independent.
    assert independent_pairs_exist(
        (item("a", (EvidenceFamily.TREND,)), item("b", (EvidenceFamily.VOLUME,)))
    )
    # Shared family -> not independent.
    assert not independent_pairs_exist(
        (item("a", (EvidenceFamily.TREND,)), item("b", (EvidenceFamily.TREND,)))
    )
    # An item with no family can never establish independence — in **either**
    # position. Both orderings are asserted because the guard is written once
    # per loop: a mutation probe that removed only the outer check survived a
    # test that placed the unfamilied item second, since the inner check caught
    # it. With the unfamilied item first, an empty family set trivially fails to
    # intersect anything and would otherwise read as "disjoint, therefore
    # independent" — which is the exact inference this rule exists to refuse.
    assert not independent_pairs_exist(
        (item("a", (EvidenceFamily.TREND,)), item("b", ()))
    )
    assert not independent_pairs_exist(
        (item("a", ()), item("b", (EvidenceFamily.TREND,)))
    )
    assert not independent_pairs_exist((item("a", ()), item("b", ())))
    # Disjoint families but a declared correlation -> still not independent.
    assert not independent_pairs_exist(
        (
            item(KEY_CONTEXT_TREND, (EvidenceFamily.TREND,)),
            item(KEY_REGIME_GATE, (EvidenceFamily.VOLUME,)),
        )
    )


def test_a_wait_with_disagreeing_leans_reports_no_agreeing_set() -> None:
    """Summing leans that point different ways would be the core error."""
    assessment = evaluate_setup(
        base_inputs(
            context_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
            setup_structural_trend=StructuralTrendType.SUSTAINED_LOWER,
            evidence_state=OverallState.INSUFFICIENT_DATA,
            evidence_dominant_alignment=None,
        )
    )
    assert assessment.state is SetupState.WAIT
    report = project_setup_evidence(assessment)
    assert report.confluence.agreeing_families == ()
    assert report.confluence.agreeing_item_count == 0
    assert any("do not share one lean" in c for c in report.confluence.caveats)


def test_every_live_factor_family_is_mapped_to_the_shared_vocabulary() -> None:
    """An unmapped factor must warn, so this asserts none is unmapped today."""
    assessment = confirmed()
    for factor in assessment.directional_factors:
        assert factor.family in FACTOR_FAMILIES
    report = project_setup_evidence(assessment)
    assert not any("no entry in the ADR-0011" in w for w in report.warnings)


# ============ 7. confluence is derived, never stored ========================


def test_confluence_is_recomputed_on_every_call() -> None:
    """Two projections of one assessment produce equal but distinct summaries."""
    assessment = confirmed()
    first = project_setup_evidence(assessment).confluence
    second = project_setup_evidence(assessment).confluence
    assert first == second
    assert first is not second


def test_confluence_is_not_a_field_on_the_assessment() -> None:
    """Nothing upstream stores it; it exists only as this projection's output."""
    names = {f.name for f in dataclasses.fields(confirmed())}
    assert "confluence" not in names
    assert not any("confluence" in name for name in names)


def test_confluence_cannot_claim_a_family_it_does_not_list() -> None:
    """The count is bounded by `agreeing_families`, never by the item count.

    An earlier form of this guard compared against `agreeing_item_count`, which
    was wrong: `setup_evidence_alignment` maps to two families, so one agreeing
    item legitimately contributes two. What must stay impossible is claiming
    more families than are actually named.
    """
    with pytest.raises(SetupEvidenceError, match="cannot exceed"):
        ConfluenceSummary(
            agreeing_families=(EvidenceFamily.TREND,),
            conflicting_families=(),
            agreeing_item_count=3,
            independent_agreeing_families=2,
            independence_established=False,
            derived_from=(),
            caveats=(),
        )


def test_confluence_cannot_report_families_with_no_agreeing_items() -> None:
    """A family is present only because some item carried it."""
    with pytest.raises(SetupEvidenceError, match="no agreeing items"):
        ConfluenceSummary(
            agreeing_families=(EvidenceFamily.TREND,),
            conflicting_families=(),
            agreeing_item_count=0,
            independent_agreeing_families=1,
            independence_established=False,
            derived_from=(),
            caveats=(),
        )


def test_one_agreeing_item_may_carry_two_families() -> None:
    """The exact shape that crashed `fmits evidence SOLUSDT` on live data.

    One supporting item, two mapped families. `FACTOR_FAMILIES` defines that
    mapping deliberately, so the report must build — and must still count the
    two families rather than the one item.
    """
    summary = ConfluenceSummary(
        agreeing_families=(EvidenceFamily.TREND, EvidenceFamily.MOMENTUM),
        conflicting_families=(),
        agreeing_item_count=1,
        independent_agreeing_families=2,
        independence_established=False,
        derived_from=(KEY_EVIDENCE_ALIGNMENT,),
        caveats=("one item, two families",),
    )
    assert summary.agreeing_item_count == 1
    assert summary.independent_agreeing_families == 2


def test_confluence_builds_when_the_alignment_is_the_only_agreeing_item() -> None:
    """The same shape end-to-end, through the real producer.

    Built from the live mapping rather than a hand-written family tuple, so a
    future change to `FACTOR_FAMILIES` cannot leave this passing vacuously.
    """
    from fmis.setup_evidence.project import _confluence

    families = FACTOR_FAMILIES["setup_evidence_alignment"]
    assert len(families) == 2, "this regression needs a genuinely multi-family item"

    alignment = EvidenceItem(
        key=KEY_EVIDENCE_ALIGNMENT,
        families=families,
        status=SetupEvidenceStatus.SUPPORTING,
        statement="alignment leans long",
        observed="upward",
        source="fmis.decision_support",
        inputs={"lean": "long"},
    )
    summary = _confluence((alignment,), (), frozenset({KEY_EVIDENCE_ALIGNMENT}))

    assert summary.agreeing_item_count == 1
    assert summary.independent_agreeing_families == 2
    assert set(summary.agreeing_families) == set(families)
    # One item cannot corroborate itself, so independence stays unestablished
    # and the upstream double-count caveat still prints.
    assert summary.independence_established is False
    assert any("counted twice" in caveat for caveat in summary.caveats)


# ============ 8. no score, weight, confidence or probability ================


_FORBIDDEN_FIELD_TOKENS = (
    "score", "weight", "confidence", "probability", "rank", "strength",
    "quality", "rating", "grade",
)


def test_no_report_type_has_a_scoring_field() -> None:
    for kind in (
        SetupEvidenceReport, EvidenceItem, ConfluenceSummary, SetupIdentityRef,
    ):
        for field in dataclasses.fields(kind):
            for token in _FORBIDDEN_FIELD_TOKENS:
                assert token not in field.name.lower(), (kind.__name__, field.name)


def test_no_strength_enum_exists_in_the_package() -> None:
    """The four-level strength enum was specified and deliberately dropped."""
    import fmis.setup_evidence as se

    assert not hasattr(se, "EvidenceStrength")
    assert not hasattr(se, "Strength")
    for member in SetupEvidenceStatus:
        assert member.name not in {"STRONG", "MEDIUM", "WEAK", "NEUTRAL"}


def test_the_rendered_page_carries_no_numeric_quality_claim() -> None:
    for build in ALL_FIXTURES:
        page = render_setup_evidence(project_setup_evidence(build())).lower()
        for token in ("score:", "confidence:", "rating:", "grade:", "strength:"):
            assert token not in page


def _flat(page: str) -> str:
    """The page's prose with layout removed.

    Assertions about *content* must not depend on where the wrapper happened to
    break a line — a phrase that spans a wrap is still on the page.
    """
    return " ".join(page.split()).lower()


def test_the_page_never_recommends_an_action() -> None:
    for build in ALL_FIXTURES:
        page = _flat(render_setup_evidence(project_setup_evidence(build())))
        for token in ("we recommend", "you should", "is a good trade"):
            assert token not in page
        # The disclaimer states the opposite, and must be present on every page.
        assert "not a recommendation to trade" in page


# ============ 9. determinism ================================================


def _serialisable(report: SetupEvidenceReport) -> str:
    return json.dumps(
        {
            "symbol": report.symbol,
            "state": report.state_text,
            "direction": report.direction_text,
            "ready": report.decision_ready,
            "items": [
                [i.key, i.status.value, [f.value for f in i.families], i.statement,
                 i.source, list(i.correlated_with)]
                for i in report.all_items
            ],
            "confluence": [
                [f.value for f in report.confluence.agreeing_families],
                [f.value for f in report.confluence.conflicting_families],
                report.confluence.agreeing_item_count,
                report.confluence.independent_agreeing_families,
                report.confluence.independence_established,
                list(report.confluence.derived_from),
                list(report.confluence.caveats),
            ],
            "warnings": list(report.warnings),
            "open_questions": list(report.open_questions),
        },
        sort_keys=True,
    )


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_equal_assessments_produce_byte_identical_reports(build) -> None:
    first = _serialisable(project_setup_evidence(build()))
    second = _serialisable(project_setup_evidence(build()))
    assert first == second


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_equal_assessments_produce_byte_identical_pages(build) -> None:
    first = render_setup_evidence(project_setup_evidence(build()))
    second = render_setup_evidence(project_setup_evidence(build()))
    assert first == second


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_family_and_item_ordering_is_canonical(build) -> None:
    """Ordering is by declaration position, so two runs never disagree."""
    report = project_setup_evidence(build())
    order = list(EvidenceFamily)
    positions = [order.index(s.family) for s in report.family_summary]
    assert positions == sorted(positions)
    assert list(report.confluence.derived_from) == sorted(report.confluence.derived_from)
    for item in report.all_items:
        assert list(item.correlated_with) == sorted(item.correlated_with)


# ============ 10. no lookahead, and identity is not re-derived ==============


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_the_report_never_carries_a_timestamp_after_the_assessment(build) -> None:
    """No-lookahead is inherited: nothing here reads a clock or a later bar."""
    assessment = build()
    report = project_setup_evidence(assessment)
    assert report.as_of == assessment.as_of
    for item in report.all_items:
        assert item.as_of is None or item.as_of <= assessment.as_of


def test_the_projection_reads_no_clock() -> None:
    """A projection that read `now` would not be replayable. Proven by source."""
    import ast
    import pathlib

    import fmis.setup_evidence as se

    root = pathlib.Path(se.__file__).parent
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"now", "utcnow", "today", "time"}, path.name


def test_setup_identity_is_carried_and_never_derived_here() -> None:
    """The identity is the caller's; this package holds no rule for building one."""
    ref = SetupIdentityRef(setup_id="setup:abcdef")
    report = project_setup_evidence(confirmed(), setup_identity=ref)
    assert report.setup_identity is ref

    without = project_setup_evidence(confirmed())
    assert without.setup_identity is None


def test_setup_identity_does_not_change_any_other_part_of_the_report() -> None:
    """Attaching a name to a setup cannot change what the evidence says."""
    ref = SetupIdentityRef(setup_id="setup:abcdef")
    with_id = project_setup_evidence(confirmed(), setup_identity=ref)
    without = project_setup_evidence(confirmed())
    assert _serialisable(with_id) == _serialisable(without)


def test_a_bad_identity_type_is_refused() -> None:
    with pytest.raises(TypeError):
        project_setup_evidence(confirmed(), setup_identity="setup:abcdef")


# ============ 11. WAIT renders honestly =====================================


def test_a_wait_with_no_directional_evidence_says_so_plainly() -> None:
    report = project_setup_evidence(wait_no_direction())
    page = render_setup_evidence(report)
    assert report.supporting == ()
    assert "none — nothing currently supports a directional view" in page
    assert "WAIT" in page


def test_a_wait_page_is_complete_and_hides_no_section() -> None:
    """Sections are never dropped to make an empty result look shorter."""
    page = render_setup_evidence(project_setup_evidence(wait_no_direction()))
    for heading in (
        "WHY THIS SETUP EXISTS",
        "SUPPORTING EVIDENCE",
        "CONFLICTING EVIDENCE",
        "MISSING CONFIRMATION",
        "UNAVAILABLE / LIMITATIONS",
        "FAMILY CONFLUENCE",
        "DECISION READINESS",
    ):
        assert heading in page


def test_a_wait_that_did_have_one_lean_shows_it_rather_than_pretending_emptiness() -> None:
    """"Nothing supports it" and "one family leaned but quorum failed" differ."""
    report = project_setup_evidence(wait_one_lean())
    assert report.supporting
    page = _flat(render_setup_evidence(report))
    assert "no directional candidate was formed" in page


def test_the_standing_invalidation_is_not_presented_as_a_present_conflict() -> None:
    report = project_setup_evidence(confirmed())
    page = render_setup_evidence(report)
    assert report.conflicting == ()
    assert "none currently conflicts" in page
    assert "not a present conflict" in page
    assert report.invalidation == report.invalidation


# ============ 12. the page respects its own width ===========================


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_no_line_exceeds_the_page_width(build) -> None:
    """A wrapped line reads as a different value; the width is a contract."""
    page = render_setup_evidence(project_setup_evidence(build()))
    for line in page.splitlines():
        assert len(line) <= PAGE_WIDTH, (len(line), line)


@pytest.mark.parametrize("build", ALL_FIXTURES)
def test_the_page_has_no_trailing_whitespace(build) -> None:
    page = render_setup_evidence(project_setup_evidence(build()))
    for line in page.splitlines():
        assert line == line.rstrip(), repr(line)


def test_a_very_long_statement_still_respects_the_width() -> None:
    """Wrapping is real, not an accident of the fixtures' sentence lengths."""
    assessment = evaluate_setup(
        base_inputs(inherited_limitations=("X-9: " + "verylongtoken" * 40,))
    )
    page = render_setup_evidence(project_setup_evidence(assessment))
    for line in page.splitlines():
        assert len(line) <= PAGE_WIDTH, (len(line), line)


def test_a_long_symbol_cannot_push_the_header_rule_over_the_margin() -> None:
    """Nothing bounds `SetupAssessment.symbol`, so the renderer must."""
    assessment = dataclasses.replace(confirmed(), symbol="X" * 120)
    page = render_setup_evidence(project_setup_evidence(assessment))
    for line in page.splitlines():
        assert len(line) <= PAGE_WIDTH, (len(line), line)


def test_confluence_with_nothing_to_compare_is_not_reported_as_a_failure() -> None:
    """"Not established" about an empty set would be a finding about nothing."""
    report = project_setup_evidence(wait_no_direction())
    assert report.confluence.agreeing_item_count == 0
    page = _flat(render_setup_evidence(report))
    assert "not assessed — no agreeing evidence to compare" in page
    assert "not established" not in page


def test_open_questions_are_the_awaited_items_not_the_unreadable_ones() -> None:
    """An unavailable input is not a question waiting for an answer."""
    report = project_setup_evidence(candidate())
    assert report.missing
    assert report.unavailable
    assert len(report.open_questions) == len(report.missing)
    for item in report.unavailable:
        assert not any(question.startswith(item.key) for question in report.open_questions)


# ============ 13. the branches the live fixtures do not reach ==============


def test_geometry_reports_a_missing_objective_level_rather_than_estimating_one() -> None:
    assessment = evaluate_setup(base_inputs(setup_levels=()))
    assert assessment.stop is not None
    assert assessment.risk_reward is None
    report = project_setup_evidence(assessment)
    item = next(i for i in report.missing if i.key == KEY_GEOMETRY)
    assert item.observed == "protective level only"
    assert item.inputs["protective_level"] == assessment.stop.price


def test_geometry_reports_no_protective_level_rather_than_inventing_one() -> None:
    assessment = evaluate_setup(base_inputs(execution_levels=(), setup_levels=()))
    assert assessment.stop is None
    report = project_setup_evidence(assessment)
    item = next(i for i in report.missing if i.key == KEY_GEOMETRY)
    assert item.observed == "no protective level"
    assert item.inputs == {}


def test_a_factor_opposing_the_direction_is_grouped_as_conflicting() -> None:
    """Unreachable under policy v1, and represented rather than assumed away.

    A candidate requires zero opposing votes, so the live policy cannot emit
    this. Building it by hand proves the projection would group it correctly if
    a future policy ever did, instead of silently filing it as supporting.
    """
    from fmis.swing_setup import DirectionalFactor, Lean

    assessment = confirmed()
    opposing = Lean.SHORT if assessment.direction.value == "long" else Lean.LONG
    flipped = dataclasses.replace(
        assessment,
        directional_factors=(
            dataclasses.replace(assessment.directional_factors[0], lean=opposing),
            *assessment.directional_factors[1:],
        ),
    )
    report = project_setup_evidence(flipped)
    item = next(i for i in report.conflicting if i.key == KEY_CONTEXT_TREND)
    assert item.status is SetupEvidenceStatus.CONFLICTING
    assert "against the assessment" in item.statement


def test_an_unmapped_factor_family_warns_and_claims_no_family() -> None:
    """A future fourth factor must be visibly unclassified, never guessed."""
    from fmis.swing_setup import DirectionalFactor, Lean

    assessment = confirmed()
    extended = dataclasses.replace(
        assessment,
        directional_factors=(
            *assessment.directional_factors,
            DirectionalFactor(
                family="order_flow_imbalance",
                lean=Lean.LONG if assessment.direction.value == "long" else Lean.SHORT,
                observed="whatever a future engine reports",
                source="fmis.some_future_engine",
            ),
        ),
    )
    report = project_setup_evidence(extended)
    item = next(i for i in report.all_items if i.key == "factor:order_flow_imbalance")
    assert item.families == ()
    assert any("no entry in the ADR-0011" in w for w in report.warnings)
    assert item.key not in report.confluence.derived_from


def test_a_research_override_is_warned_about_never_explained_as_production() -> None:
    assessment = evaluate_setup(base_inputs(), research_confirmation_max_age=0)
    report = project_setup_evidence(assessment)
    assert any("research override" in w.lower() for w in report.warnings)


def test_a_limited_decision_context_is_warned_about_and_still_ready() -> None:
    assessment = dataclasses.replace(confirmed(), sufficiency=ContextState.LIMITED)
    report = project_setup_evidence(assessment)
    assert report.decision_ready is True
    assert any("LIMITED" in w for w in report.warnings)


def test_the_standing_note_disappears_when_the_factors_become_independent() -> None:
    """The note is derived, so a genuinely independent factor set removes it."""
    import fmis.setup_evidence.correlation as correlation

    original = correlation.FACTOR_FAMILIES
    try:
        correlation.FACTOR_FAMILIES = {
            "a": (EvidenceFamily.TREND,),
            "b": (EvidenceFamily.VOLUME,),
        }
        assert correlation.standing_family_note() is None
        correlation.FACTOR_FAMILIES = {"a": (EvidenceFamily.TREND,)}
        assert correlation.standing_family_note() is None
    finally:
        correlation.FACTOR_FAMILIES = original
    assert correlation.standing_family_note() is not None


def test_the_identity_block_renders_an_occurrence_when_one_is_supplied() -> None:
    ref = SetupIdentityRef(setup_id="setup:abcdef", occurrence_id="occ:123")
    page = render_setup_evidence(
        project_setup_evidence(confirmed(), setup_identity=ref)
    )
    assert "setup:abcdef" in page
    assert "occ:123" in page


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"key": ""}, "key must be a non-empty str"),
        ({"families": [EvidenceFamily.TREND]}, "families must be a tuple"),
        ({"families": (EvidenceFamily.TREND, EvidenceFamily.TREND)}, "must not repeat"),
        ({"families": ("trend",)}, "must be an EvidenceFamily"),
        ({"status": "supporting"}, "must be a SetupEvidenceStatus"),
        ({"scope": "  "}, "scope must be a non-empty str"),
        ({"as_of": "2026-01-02"}, "as_of must be a datetime"),
        ({"correlated_with": ["x"]}, "correlated_with must be a tuple"),
        ({"independence_note": " "}, "independence_note must be"),
    ],
)
def test_an_evidence_item_refuses_a_malformed_field(kwargs, match) -> None:
    base = dict(
        key="k", families=(), status=SetupEvidenceStatus.SUPPORTING,
        statement="s", observed="o", source="src",
    )
    base.update(kwargs)
    with pytest.raises((SetupEvidenceError, TypeError), match=match):
        EvidenceItem(**base)


def test_an_item_cannot_be_correlated_with_itself() -> None:
    with pytest.raises(SetupEvidenceError, match="cannot be correlated with itself"):
        EvidenceItem(
            key="k", families=(), status=SetupEvidenceStatus.SUPPORTING,
            statement="s", observed="o", source="src", correlated_with=("k",),
        )


def test_a_report_cannot_reference_a_correlation_target_it_does_not_hold() -> None:
    """A dangling correlation key would print a caveat pointing at nothing."""
    item = EvidenceItem(
        key="k", families=(), status=SetupEvidenceStatus.SUPPORTING,
        statement="s", observed="o", source="src", correlated_with=("absent",),
    )
    with pytest.raises(SetupEvidenceError, match="not an item in this report"):
        SetupEvidenceReport(
            symbol="BTCUSDT", as_of=_AS_OF, state_text="WAIT", direction_text=None,
            thesis=(), supporting=(item,), conflicting=(), missing=(), unavailable=(),
            invalidation=(), regime_context=(), family_summary=(),
            confluence=_empty_confluence(), sufficiency=ContextState.SUFFICIENT,
            decision_ready=True, decision_ready_reason="r", warnings=(),
            open_questions=(),
        )


def test_a_family_summary_refuses_a_negative_count() -> None:
    from fmis.setup_evidence import FamilySummary

    with pytest.raises(SetupEvidenceError, match="cannot be negative"):
        FamilySummary(
            family=EvidenceFamily.TREND, supporting=-1, conflicting=0,
            missing=0, unavailable=0,
        )


def test_a_setup_identity_ref_refuses_a_blank_id() -> None:
    with pytest.raises(SetupEvidenceError, match="setup_id must be a non-empty str"):
        SetupIdentityRef(setup_id="  ")


def test_established_independence_renders_its_own_verdict() -> None:
    """The positive branch, which live data never reaches today.

    Every real assessment reports independence as NOT established, so without a
    hand-built report this branch would be unexercised — and a future factor set
    that genuinely was independent would render an untested line.
    """
    items = tuple(
        EvidenceItem(
            key=key, families=(family,), status=SetupEvidenceStatus.SUPPORTING,
            statement="s", observed="o", source="src", inputs={"lean": "same"},
        )
        for key, family in (
            ("independent:a", EvidenceFamily.TREND),
            ("independent:b", EvidenceFamily.VOLUME),
        )
    )
    from fmis.setup_evidence.project import _confluence

    confluence = _confluence(items, (), frozenset(i.key for i in items))
    assert confluence.independence_established is True
    report = SetupEvidenceReport(
        symbol="BTCUSDT", as_of=_AS_OF, state_text="CONFIRMED", direction_text="X",
        thesis=("t",), supporting=items, conflicting=(), missing=(), unavailable=(),
        invalidation=(), regime_context=(), family_summary=(), confluence=confluence,
        sufficiency=ContextState.SUFFICIENT, decision_ready=True,
        decision_ready_reason="r", warnings=(), open_questions=(),
    )
    page = _flat(render_setup_evidence(report))
    assert "established — at least two agreeing items share no family" in page


def test_an_assessment_with_no_regime_context_projects_no_regime_item() -> None:
    assessment = dataclasses.replace(confirmed(), regime_context=())
    report = project_setup_evidence(assessment)
    assert KEY_REGIME_GATE not in {item.key for item in report.all_items}


def test_an_empty_thesis_renders_a_stated_absence_not_a_blank() -> None:
    assessment = dataclasses.replace(confirmed(), thesis=())
    page = _flat(render_setup_evidence(project_setup_evidence(assessment)))
    assert "no thesis stated" in page


def test_render_rejects_a_non_report() -> None:
    with pytest.raises(TypeError):
        render_setup_evidence(confirmed())


def test_project_rejects_a_non_assessment() -> None:
    with pytest.raises(TypeError):
        project_setup_evidence("BTCUSDT")


# ============ 12. `fmits evidence` isolates one symbol's projection failure ==


def _evidence_results():
    """Three assessed symbols, in the order the isolation regression needs.

    Each assessment carries its own symbol, because the page header is rendered
    from the assessment rather than from the requested symbol — three fixtures
    sharing one symbol would make "the later page rendered" unfalsifiable.
    """
    from fmis.swing_setup.compose import SetupRunResult

    return tuple(
        SetupRunResult(
            requested_symbol=symbol,
            assessment=dataclasses.replace(confirmed(), symbol=symbol),
        )
        for symbol in ("BTCUSDT", "SOLUSDT", "ETHUSDT")
    )


def _fail_projection_for(target, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the projection raise for exactly one assessment, by identity.

    ``target`` must be the very object the CLI will be handed — the fixtures
    build equal-but-distinct assessments, so identity is what selects one symbol
    and leaves its neighbours on the real code path.

    Driven through the CLI's own seam rather than a market shape, so the test
    pins the *exception boundary* and cannot quietly stop exercising it when the
    shape that originally triggered it stops occurring.
    """
    from fmis.pipeline import cli as cli_module

    real = cli_module.project_setup_evidence

    def projection(assessment, **kwargs):
        if assessment is target:
            raise SetupEvidenceError("independent_agreeing_families cannot exceed")
        return real(assessment, **kwargs)

    monkeypatch.setattr(cli_module, "project_setup_evidence", projection)


def test_a_projection_failure_does_not_suppress_the_symbols_behind_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """BTCUSDT valid, SOLUSDT fails to project, ETHUSDT must still render.

    The defect this pins lost every page queued behind the failing symbol.
    """
    from fmis.pipeline import cli as cli_module

    ordered = _evidence_results()
    monkeypatch.setattr(cli_module, "run_setup_for_symbols", lambda *a, **kw: ordered)
    _fail_projection_for(ordered[1].assessment, monkeypatch)

    exit_code = cli_module.main(["evidence", "BTCUSDT", "SOLUSDT", "ETHUSDT"])
    captured = capsys.readouterr()

    assert "SETUP EVIDENCE — BTCUSDT" in captured.out
    assert "SETUP EVIDENCE — ETHUSDT" in captured.out, (
        "the symbol behind the failure was suppressed"
    )
    assert "SETUP EVIDENCE — SOLUSDT" not in captured.out
    assert "SOLUSDT" in captured.err
    assert "evidence could not be projected" in captured.err
    # Two symbols still produced a true report, so the run is not a failure.
    assert exit_code == 0


def test_a_projection_failure_reports_that_symbol_on_stderr_not_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refusal must never look like a page, and never be half a page."""
    from fmis.pipeline import cli as cli_module

    ordered = _evidence_results()
    monkeypatch.setattr(cli_module, "run_setup_for_symbols", lambda *a, **kw: ordered)
    _fail_projection_for(ordered[1].assessment, monkeypatch)

    cli_module.main(["evidence", "BTCUSDT", "SOLUSDT", "ETHUSDT"])
    captured = capsys.readouterr()

    assert captured.out.count("SETUP EVIDENCE") == 2
    assert "could not be projected" not in captured.out


def test_every_symbol_failing_to_project_is_a_non_zero_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Isolation must not turn a total failure into a clean exit."""
    from fmis.pipeline import cli as cli_module

    ordered = _evidence_results()
    monkeypatch.setattr(cli_module, "run_setup_for_symbols", lambda *a, **kw: ordered)

    def always_fails(assessment, **kwargs):
        raise SetupEvidenceError("nothing could be projected")

    monkeypatch.setattr(cli_module, "project_setup_evidence", always_fails)

    exit_code = cli_module.main(["evidence", "BTCUSDT", "SOLUSDT", "ETHUSDT"])
    assert exit_code == 1
    assert "SETUP EVIDENCE" not in capsys.readouterr().out


def test_a_programmer_error_is_not_swallowed_by_the_isolation_guard(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only `SetupEvidenceError` is caught. A bug must still reach the operator."""
    from fmis.pipeline import cli as cli_module

    ordered = _evidence_results()
    monkeypatch.setattr(cli_module, "run_setup_for_symbols", lambda *a, **kw: ordered)

    def boom(assessment, **kwargs):
        raise AttributeError("a bug in the projection, not a refusal")

    monkeypatch.setattr(cli_module, "project_setup_evidence", boom)

    with pytest.raises(AttributeError, match="a bug in the projection"):
        cli_module.main(["evidence", "BTCUSDT", "SOLUSDT", "ETHUSDT"])


def test_a_render_failure_is_isolated_the_same_way(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guard covers the render too, so no partial page precedes the error."""
    from fmis.pipeline import cli as cli_module

    ordered = _evidence_results()
    monkeypatch.setattr(cli_module, "run_setup_for_symbols", lambda *a, **kw: ordered)
    real = cli_module.render_setup_evidence
    seen: list[str] = []

    def render(report):
        seen.append(report.symbol)
        if len(seen) == 2:
            raise SetupEvidenceError("cannot render this report")
        return real(report)

    monkeypatch.setattr(cli_module, "render_setup_evidence", render)

    exit_code = cli_module.main(["evidence", "BTCUSDT", "SOLUSDT", "ETHUSDT"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.count("SETUP EVIDENCE") == 2
    assert "could not be projected" in captured.err


def test_an_analysis_failure_is_isolated_alongside_a_projection_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other failure mode on this loop: no assessment was produced at all.

    Restructuring the guard moved this branch, so it is pinned here rather than
    left to the surfaces that happen to exercise `fmits setup`.
    """
    from fmis.pipeline import cli as cli_module
    from fmis.swing_setup.compose import SetupRunResult

    ordered = (
        SetupRunResult(requested_symbol="BADUSDT", failure="provider rejected the symbol"),
        SetupRunResult(
            requested_symbol="ETHUSDT",
            assessment=dataclasses.replace(confirmed(), symbol="ETHUSDT"),
        ),
    )
    monkeypatch.setattr(cli_module, "run_setup_for_symbols", lambda *a, **kw: ordered)

    exit_code = cli_module.main(["evidence", "BADUSDT", "ETHUSDT"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "SETUP EVIDENCE — ETHUSDT" in captured.out
    assert "provider rejected the symbol" in captured.err
    assert "could not be projected" not in captured.err


def test_every_symbol_failing_analysis_is_a_non_zero_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from fmis.pipeline import cli as cli_module
    from fmis.swing_setup.compose import SetupRunResult

    ordered = (
        SetupRunResult(requested_symbol="AUSDT", failure="down"),
        SetupRunResult(requested_symbol="BUSDT", failure="down"),
    )
    monkeypatch.setattr(cli_module, "run_setup_for_symbols", lambda *a, **kw: ordered)

    assert cli_module.main(["evidence", "AUSDT", "BUSDT"]) == 1
    assert "SETUP EVIDENCE" not in capsys.readouterr().out
