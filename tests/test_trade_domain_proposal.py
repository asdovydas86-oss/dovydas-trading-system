"""`OpportunityProposal`, its lifecycle stream, and the fold that is its state.

The brief's *Opportunity* and *Decision*. The tests below are organised around the
four creation rules and the state machine, because those are the places where a
regression would be silent rather than loud.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from trade_domain_helpers import (
    AT,
    MARKET,
    OTHER_MARKET,
    anchor,
    level,
    level_origin,
    lifecycle_event,
    market_snapshot,
    proposal,
    reason_tag,
    version_set,
)

from fmis.accounts import Book
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError, PayloadDecodeError, RecordAudit
from fmis.proposal import (
    AUTHOR_ORIGINS,
    ASSERTED_KINDS,
    KIND_ORIGINS,
    MEASURED_KINDS,
    UNCALIBRATED_PROBABILITY,
    TERMINAL_STATES,
    TRANSITIONS,
    AdmissionOutcome,
    DirectionalAssessment,
    DirectionalCase,
    EvidenceCitation,
    IllegalTransitionError,
    LifecycleKind,
    ModelAttribution,
    OpportunityProposal,
    ProposalAuthor,
    ProposalLifecycleEvent,
    ProposalState,
    ProposalStateView,
    StatedConfidence,
    admit,
    fold_proposal_state,
)
from fmis.snapshotting import LevelSideRef, RiskRewardReading, TradeDirection

MODEL = ModelAttribution(
    model_id="claude-opus-5",
    model_version="2026-08",
    template_id="proposal-review",
    template_version="3",
    context_package_id="ctx-42",
    context_digest="sha256:" + "d" * 64,
)


# --------------------------------------------------------------------------
# Stated confidence is never a probability.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["0.7", "70%", "7", " 0,7 ", "-3"])
def test_a_numeric_looking_confidence_label_is_rejected(label: str) -> None:
    with pytest.raises(DomainValidationError, match="not a probability"):
        StatedConfidence(label)


@pytest.mark.parametrize("label", ["moderate", "high conviction", "B+", "2 of 3 families"])
def test_a_worded_confidence_label_is_accepted(label: str) -> None:
    assert StatedConfidence(label).label == label.strip()


def test_calibrated_probability_is_absent_at_creation_and_cannot_be_set() -> None:
    subject = proposal()
    assert isinstance(subject.calibrated_probability, Absent)
    assert subject.probability == UNCALIBRATED_PROBABILITY
    with pytest.raises(DomainValidationError, match="stays Absent"):
        proposal(calibrated_probability=Decimal("0.7"))
    with pytest.raises(DomainValidationError, match="probability must be"):
        proposal(probability="0.7")


# --------------------------------------------------------------------------
# Creation rule 1 — both directions assessed, never collapsed.
# --------------------------------------------------------------------------


def test_both_directional_cases_are_kept_apart() -> None:
    assessment = proposal().directional_assessment
    assert assessment.case_for(TradeDirection.LONG).direction is TradeDirection.LONG
    assert assessment.case_for(TradeDirection.SHORT).direction is TradeDirection.SHORT
    assert assessment.case_for(TradeDirection.NO_TRADE) is None
    payload = assessment.to_payload()
    assert set(payload) == {"long_case", "short_case"}
    assert not set(payload) & {"net", "score", "winner"}


def test_a_case_argued_for_the_wrong_side_is_rejected() -> None:
    case = DirectionalCase(TradeDirection.SHORT, ("x",), "y")
    with pytest.raises(DomainValidationError, match="both sides are assessed"):
        DirectionalAssessment(long_case=case, short_case=case)


def test_no_trade_is_not_a_side_to_argue() -> None:
    with pytest.raises(DomainValidationError, match="NO_TRADE is the conclusion"):
        DirectionalCase(TradeDirection.NO_TRADE, (), "nothing here")


def test_a_no_trade_proposal_is_valid_and_carries_no_anchor() -> None:
    subject = proposal(
        direction=TradeDirection.NO_TRADE,
        anchor=Absent("no invalidation level to anchor on"),
        invalidation=Absent("no level"),
        stop=Absent("no level"),
        risk_reward=Absent("no stop, no risk denominator"),
        take_profit_structure=(),
    )
    assert subject.direction is TradeDirection.NO_TRADE
    assert OpportunityProposal.from_payload(subject.to_payload()) == subject


def test_a_no_trade_proposal_carrying_an_anchor_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="NO_TRADE proposal carries no anchor"):
        proposal(
            direction=TradeDirection.NO_TRADE,
            invalidation=Absent("no level"),
            stop=Absent("no level"),
            risk_reward=Absent("no stop"),
        )


# --------------------------------------------------------------------------
# Creation rule 2 — a proposal with no case against it is an advertisement.
# --------------------------------------------------------------------------


def test_opposing_evidence_is_required_and_non_empty() -> None:
    with pytest.raises(DomainValidationError, match="advertisement"):
        proposal(opposing_evidence=())


def test_supporting_evidence_is_required_and_non_empty() -> None:
    with pytest.raises(DomainValidationError, match="supporting_evidence is required"):
        proposal(supporting_evidence=())


def test_an_evidence_citation_names_the_layer_that_produced_it() -> None:
    citation = EvidenceCitation("trend", "ema stack aligned", "fmis.decision_support")
    assert EvidenceCitation.from_payload(citation.to_payload()) == citation


# --------------------------------------------------------------------------
# Creation rule 3 — no fabricated price.
# --------------------------------------------------------------------------


def test_a_proposal_with_no_stop_cannot_state_a_risk_reward() -> None:
    with pytest.raises(DomainValidationError, match="no risk denominator"):
        proposal(stop=Absent("no level detected"))


def test_a_directional_proposal_states_the_invalidation_that_can_disprove_it() -> None:
    with pytest.raises(DomainValidationError, match="cannot be proved wrong"):
        proposal(invalidation=Absent("no level"), stop=Absent("no level"), risk_reward=Absent("no stop"))


def test_the_stored_risk_reward_is_a_pair_and_not_a_ratio() -> None:
    payload = proposal().to_payload()["risk_reward"]["value"]
    assert set(payload) == {"risk_distance", "reward_distance"}


# --------------------------------------------------------------------------
# Creation rule 4 — the anchor, and one live proposal per anchor.
# --------------------------------------------------------------------------


def test_a_directional_proposal_requires_an_anchor() -> None:
    with pytest.raises(DomainValidationError, match="carries an anchor"):
        proposal(anchor=Absent("none computed"))


def test_the_anchor_must_be_the_origin_the_proposal_actually_rests_on() -> None:
    with pytest.raises(DomainValidationError, match="MEASURED fact the proposal"):
        proposal(anchor=anchor(origin=level_origin("a-different-swing")))


@pytest.mark.parametrize(
    "override, message",
    [
        ({"direction": TradeDirection.SHORT}, "anchor direction"),
        ({"market": OTHER_MARKET}, "anchor names market"),
        ({"book": Book.DAY}, "anchor names book"),
    ],
)
def test_an_anchor_disagreeing_with_the_proposal_is_rejected(
    override: dict, message: str
) -> None:
    with pytest.raises(DomainValidationError, match=message):
        proposal(anchor=anchor(**override))


def test_a_second_proposal_on_a_live_anchor_becomes_a_reaffirmation() -> None:
    first = proposal()
    candidate = proposal(created_at=AT(11))
    live = ((first, fold_proposal_state(first, ())),)
    admission = admit(
        candidate,
        live,
        occurred_at=AT(11),
        recorded_at=AT(11),
        causing_close_time=AT(11),
    )
    assert admission.outcome is AdmissionOutcome.REAFFIRMED
    assert admission.proposal.proposal_id == first.proposal_id
    assert admission.reaffirmation.kind is LifecycleKind.REAFFIRMED
    assert admission.reaffirmation.proposal_id == first.proposal_id


def test_a_different_anchor_creates_a_new_proposal() -> None:
    first = proposal()
    other_origin = level_origin("swing-low-999")
    candidate = proposal(
        invalidation=level("57000", origin=other_origin),
        stop=level("57000", origin=other_origin),
        anchor=anchor(origin=other_origin),
    )
    admission = admit(
        candidate,
        ((first, fold_proposal_state(first, ())),),
        occurred_at=AT(11),
        recorded_at=AT(11),
        causing_close_time=AT(11),
    )
    assert admission.outcome is AdmissionOutcome.CREATED
    assert admission.proposal is candidate
    assert isinstance(admission.reaffirmation, Absent)


def test_admission_compares_against_live_proposals_only() -> None:
    subject = proposal()
    resolved = fold_proposal_state(
        subject,
        (
            lifecycle_event(subject, LifecycleKind.WITHDRAWN_BY_AUTHOR, 10),
            lifecycle_event(subject, LifecycleKind.RESOLVED, 11),
        ),
    )
    with pytest.raises(DomainValidationError, match="is not live"):
        admit(
            proposal(created_at=AT(11)),
            ((subject, resolved),),
            occurred_at=AT(11),
            recorded_at=AT(11),
            causing_close_time=AT(11),
        )


def test_a_reaffirmation_carries_the_new_snapshot_as_its_reference() -> None:
    first = proposal()
    candidate = proposal(created_at=AT(11))
    admission = admit(
        candidate,
        ((first, fold_proposal_state(first, ())),),
        occurred_at=AT(11),
        recorded_at=AT(11),
        causing_close_time=AT(11),
        note="re-observed on the 4h close",
    )
    assert admission.reaffirmation.reference == candidate.market_snapshot_id
    assert admission.reaffirmation.note == "re-observed on the 4h close"


# --------------------------------------------------------------------------
# Author rules.
# --------------------------------------------------------------------------


def test_each_author_produces_a_differently_trustworthy_record() -> None:
    assert AUTHOR_ORIGINS[ProposalAuthor.DETERMINISTIC_POLICY] is ValueOrigin.POLICY_DERIVED
    assert AUTHOR_ORIGINS[ProposalAuthor.OWNER] is ValueOrigin.ASSERTED
    assert AUTHOR_ORIGINS[ProposalAuthor.MODEL] is ValueOrigin.INTERPRETED
    assert proposal().origin is ValueOrigin.POLICY_DERIVED


def test_a_model_authored_proposal_must_capture_the_conditions_it_ran_under() -> None:
    with pytest.raises(DomainValidationError, match="must name the model"):
        proposal(author=ProposalAuthor.MODEL, policy_id=Absent("not policy-authored"))


def test_a_model_authored_proposal_is_interpreted_and_round_trips() -> None:
    subject = proposal(
        author=ProposalAuthor.MODEL,
        policy_id=Absent("not policy-authored"),
        model=MODEL,
    )
    assert subject.is_model_authored
    assert subject.origin is ValueOrigin.INTERPRETED
    assert OpportunityProposal.from_payload(subject.to_payload()) == subject


def test_a_human_or_policy_decision_cannot_be_attributed_to_a_model() -> None:
    with pytest.raises(DomainValidationError, match="carries no model attribution"):
        proposal(model=MODEL)


def test_a_model_authored_proposal_carries_no_policy_id() -> None:
    with pytest.raises(DomainValidationError, match="does not carry a policy_id"):
        proposal(author=ProposalAuthor.MODEL, model=MODEL)


def test_a_policy_authored_proposal_names_its_policy() -> None:
    with pytest.raises(DomainValidationError, match="must name the policy"):
        proposal(policy_id=Absent("none"))


def test_an_owner_authored_proposal_is_not_a_policy_version() -> None:
    with pytest.raises(DomainValidationError, match="the owner is not a policy version"):
        proposal(author=ProposalAuthor.OWNER)


def test_an_owner_authored_proposal_is_asserted() -> None:
    subject = proposal(author=ProposalAuthor.OWNER, policy_id=Absent("owner-authored"))
    assert subject.origin is ValueOrigin.ASSERTED


def test_a_model_attribution_requires_a_checkable_context_digest() -> None:
    with pytest.raises(DomainValidationError, match="checkable"):
        ModelAttribution("m", "1", "t", "1", "ctx", "not-a-digest")


# --------------------------------------------------------------------------
# Identity, immutability and serialization.
# --------------------------------------------------------------------------


def test_a_proposal_is_identified_by_its_content_and_round_trips() -> None:
    subject = proposal()
    assert OpportunityProposal.from_payload(subject.to_payload()) == subject
    assert subject.proposal_id == proposal().proposal_id


def test_changing_any_asserted_field_changes_the_proposal_id() -> None:
    assert proposal().proposal_id != proposal(
        entry_conditions=("a different condition",)
    ).proposal_id


def test_a_tampered_proposal_id_is_rejected_on_decode() -> None:
    payload = proposal().to_payload()
    payload["proposal_id"] = "proposal-x-20260812T090000Z-0123456789abcdef"
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        OpportunityProposal.from_payload(payload)


def test_a_payload_carrying_a_probability_value_was_not_written_by_this_domain() -> None:
    payload = proposal().to_payload()
    payload["calibrated_probability"] = {"value": "0.7"}
    with pytest.raises(PayloadDecodeError, match="must be an absence"):
        OpportunityProposal.from_payload(payload)


def test_a_proposal_is_frozen_at_the_moment_it_was_authored() -> None:
    with pytest.raises(DomainValidationError, match="must equal created_at"):
        proposal(audit=RecordAudit.frozen_at(AT(8)))


def test_a_proposal_that_expires_before_it_exists_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="expires before it exists"):
        proposal(valid_until=AT(8))


def test_expiry_is_a_comparison_and_not_a_stored_flag() -> None:
    subject = proposal()
    assert not subject.is_expired_at(AT(10))
    assert subject.is_expired_at(AT(9, day=16))
    assert "expired" not in subject.to_payload()


def test_a_proposal_can_be_cited_as_a_consumed_source() -> None:
    subject = proposal()
    source = subject.as_consumed_source()
    assert source.record_id == subject.proposal_id
    assert source.kind == "opportunity_proposal"


def test_a_proposal_may_supersede_a_prior_one_by_id() -> None:
    first = proposal()
    second = proposal(created_at=AT(10), supersedes=first.proposal_id)
    assert second.supersedes == first.proposal_id
    assert OpportunityProposal.from_payload(second.to_payload()) == second


# --------------------------------------------------------------------------
# The lifecycle stream — the brief's Decision.
# --------------------------------------------------------------------------


def test_the_origin_of_a_lifecycle_kind_is_fixed_and_not_a_callers_choice() -> None:
    assert KIND_ORIGINS[LifecycleKind.OWNER_DECIDED] is ValueOrigin.ASSERTED
    assert KIND_ORIGINS[LifecycleKind.ENTRY_TRIGGERED] is ValueOrigin.MEASURED
    assert KIND_ORIGINS[LifecycleKind.UNTRADEABLE_ASSESSED] is ValueOrigin.ABSENT
    assert set(KIND_ORIGINS) == set(LifecycleKind)
    assert MEASURED_KINDS.isdisjoint(ASSERTED_KINDS)


def test_owner_decided_requires_a_reason_tag_from_a_closed_vocabulary() -> None:
    subject = proposal()
    with pytest.raises(DomainValidationError, match="requires a reason_tag"):
        lifecycle_event(
            subject,
            LifecycleKind.OWNER_DECIDED,
            10,
            causing_close_time=Absent("asserted"),
        )
    event = lifecycle_event(
        subject,
        LifecycleKind.OWNER_DECIDED,
        10,
        causing_close_time=Absent("asserted"),
        reason_tag=reason_tag("thesis_no_longer_valid"),
    )
    assert event.origin is ValueOrigin.ASSERTED


def test_a_measured_event_carries_the_candle_close_that_caused_it() -> None:
    subject = proposal()
    with pytest.raises(DomainValidationError, match="ordered by that time"):
        lifecycle_event(
            subject,
            LifecycleKind.ENTRY_TRIGGERED,
            10,
            causing_close_time=Absent("not recorded"),
        )


def test_an_asserted_event_must_not_claim_a_causing_candle() -> None:
    subject = proposal()
    with pytest.raises(DomainValidationError, match="not caused by a candle"):
        lifecycle_event(
            subject,
            LifecycleKind.WITHDRAWN_BY_AUTHOR,
            10,
            causing_close_time=AT(10, day=13),
        )


def test_untradeable_assessed_cannot_be_produced_and_says_why() -> None:
    with pytest.raises(DomainValidationError, match="spread and depth"):
        lifecycle_event(proposal(), LifecycleKind.UNTRADEABLE_ASSESSED, 10)


def test_an_event_recorded_before_it_happened_is_rejected() -> None:
    subject = proposal()
    with pytest.raises(DomainValidationError, match="cannot learn of something"):
        lifecycle_event(
            subject, LifecycleKind.ENTRY_TRIGGERED, 11, recorded_at=AT(10, day=13)
        )


def test_a_lifecycle_event_round_trips_and_verifies_its_own_id() -> None:
    event = lifecycle_event(proposal(), LifecycleKind.ENTRY_TRIGGERED, 11)
    assert ProposalLifecycleEvent.from_payload(event.to_payload()) == event
    payload = event.to_payload()
    payload["event_id"] = "lifecycle_event-x-20260813T110000Z-0123456789abcdef"
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        ProposalLifecycleEvent.from_payload(payload)


def test_an_unknown_lifecycle_kind_is_a_clean_rejection() -> None:
    payload = lifecycle_event(proposal(), LifecycleKind.EXECUTED, 11).to_payload()
    payload["kind"] = "vibed"
    with pytest.raises(PayloadDecodeError, match="not known to this build"):
        ProposalLifecycleEvent.from_payload(payload)


def test_recorded_at_is_outside_the_event_digest_so_a_restart_is_idempotent() -> None:
    subject = proposal()
    early = lifecycle_event(subject, LifecycleKind.ENTRY_TRIGGERED, 11)
    late = lifecycle_event(
        subject, LifecycleKind.ENTRY_TRIGGERED, 11, recorded_at=AT(20, day=13)
    )
    assert early.event_id == late.event_id


# --------------------------------------------------------------------------
# The fold — the state machine.
# --------------------------------------------------------------------------


def _accept(subject: OpportunityProposal, hour: int = 10) -> ProposalLifecycleEvent:
    return lifecycle_event(
        subject,
        LifecycleKind.OWNER_DECIDED,
        hour,
        causing_close_time=Absent("asserted"),
        reason_tag=reason_tag("accepted", "acceptance_reason"),
    )


def test_a_proposal_with_no_events_is_live() -> None:
    view = fold_proposal_state(proposal(), ())
    assert view.state is ProposalState.LIVE
    assert view.is_live
    assert not view.is_terminal
    assert view.applied == ()


def test_the_happy_path_reaches_executed_then_resolved() -> None:
    subject = proposal()
    events = (
        _accept(subject),
        lifecycle_event(subject, LifecycleKind.ENTRY_TRIGGERED, 11),
        lifecycle_event(subject, LifecycleKind.EXECUTED, 12),
        lifecycle_event(subject, LifecycleKind.RESOLVED, 13),
    )
    view = fold_proposal_state(subject, events)
    assert view.state is ProposalState.RESOLVED
    assert view.is_terminal
    assert len(view.applied) == 4


def test_a_reaffirmation_keeps_a_live_proposal_live() -> None:
    subject = proposal()
    view = fold_proposal_state(
        subject, (lifecycle_event(subject, LifecycleKind.REAFFIRMED, 10),)
    )
    assert view.state is ProposalState.LIVE


def test_expiry_undecided_and_untriggered_reach_the_same_state_from_different_places() -> None:
    subject = proposal()
    undecided = fold_proposal_state(
        subject, (lifecycle_event(subject, LifecycleKind.EXPIRED_UNDECIDED, 11),)
    )
    untriggered = fold_proposal_state(
        subject,
        (_accept(subject), lifecycle_event(subject, LifecycleKind.EXPIRED_UNTRIGGERED, 11)),
    )
    assert undecided.state is ProposalState.LAPSED
    assert untriggered.state is ProposalState.LAPSED
    assert LifecycleKind.EXPIRED_UNDECIDED is not LifecycleKind.EXPIRED_UNTRIGGERED


def test_a_fill_after_invalidation_is_entered_anyway_and_not_executed() -> None:
    subject = proposal()
    view = fold_proposal_state(
        subject,
        (
            _accept(subject),
            lifecycle_event(subject, LifecycleKind.INVALIDATION_REACHED, 11),
            lifecycle_event(subject, LifecycleKind.EXECUTED_WHILE_INVALID, 12),
        ),
    )
    assert view.state is ProposalState.ENTERED_ANYWAY


@pytest.mark.parametrize(
    "kind",
    [
        LifecycleKind.EXECUTED,
        LifecycleKind.ENTRY_TRIGGERED,
        LifecycleKind.EXPIRED_UNTRIGGERED,
        LifecycleKind.RESOLVED,
    ],
)
def test_an_event_that_cannot_follow_the_current_state_is_refused(
    kind: LifecycleKind,
) -> None:
    subject = proposal()
    with pytest.raises(IllegalTransitionError, match="cannot follow state live"):
        fold_proposal_state(subject, (lifecycle_event(subject, kind, 11),))


def test_nothing_follows_the_terminal_state() -> None:
    assert TRANSITIONS[ProposalState.RESOLVED] == {}
    assert TERMINAL_STATES == {ProposalState.RESOLVED}
    subject = proposal()
    with pytest.raises(IllegalTransitionError, match="terminal"):
        fold_proposal_state(
            subject,
            (
                lifecycle_event(subject, LifecycleKind.WITHDRAWN_BY_AUTHOR, 10),
                lifecycle_event(subject, LifecycleKind.RESOLVED, 11),
                lifecycle_event(subject, LifecycleKind.REAFFIRMED, 12),
            ),
        )


def test_the_stream_is_ordered_by_causing_close_and_not_by_scan_time() -> None:
    subject = proposal()
    trigger = lifecycle_event(
        subject, LifecycleKind.ENTRY_TRIGGERED, 11, recorded_at=AT(20, day=13)
    )
    decision = _accept(subject, hour=10)
    view = fold_proposal_state(subject, (trigger, decision))
    assert view.state is ProposalState.TRIGGERED


def test_two_events_on_one_candle_are_reported_as_ambiguous_and_never_ordered() -> None:
    subject = proposal()
    view = fold_proposal_state(
        subject,
        (
            _accept(subject),
            lifecycle_event(subject, LifecycleKind.ENTRY_TRIGGERED, 11, same_bar=True),
            lifecycle_event(
                subject, LifecycleKind.INVALIDATION_REACHED, 11, same_bar=True
            ),
        ),
    )
    assert view.is_ambiguous
    assert view.state is ProposalState.DECIDED
    assert len(view.ambiguous_events) == 2


def test_two_events_on_one_candle_that_are_not_marked_are_refused() -> None:
    subject = proposal()
    with pytest.raises(DomainValidationError, match="not marked same_bar"):
        fold_proposal_state(
            subject,
            (
                _accept(subject),
                lifecycle_event(subject, LifecycleKind.ENTRY_TRIGGERED, 11),
                lifecycle_event(subject, LifecycleKind.INVALIDATION_REACHED, 11),
            ),
        )


def test_a_same_bar_group_reaching_one_state_is_applied_rather_than_refused() -> None:
    subject = proposal()
    view = fold_proposal_state(
        subject,
        (
            _accept(subject),
            lifecycle_event(subject, LifecycleKind.REAFFIRMED, 11, same_bar=True),
            lifecycle_event(subject, LifecycleKind.REAFFIRMED, 11, same_bar=True, note="second read"),
        ),
    )
    assert not view.is_ambiguous
    assert view.state is ProposalState.DECIDED


def test_a_same_bar_marker_without_a_causing_candle_is_rejected() -> None:
    subject = proposal()
    with pytest.raises(DomainValidationError, match="cannot share a bar"):
        lifecycle_event(
            subject,
            LifecycleKind.WITHDRAWN_BY_AUTHOR,
            10,
            causing_close_time=Absent("asserted"),
            same_bar=True,
        )


def test_a_superseded_event_is_excluded_from_the_fold() -> None:
    subject = proposal()
    wrong = lifecycle_event(subject, LifecycleKind.INVALIDATION_REACHED, 11)
    correction = lifecycle_event(
        subject, LifecycleKind.REAFFIRMED, 12, supersedes=wrong.event_id
    )
    view = fold_proposal_state(subject, (wrong, correction))
    assert view.state is ProposalState.LIVE
    assert wrong.event_id not in view.applied


def test_an_event_belonging_to_another_proposal_is_refused() -> None:
    subject = proposal()
    other_origin = level_origin("swing-low-999")
    other = proposal(
        invalidation=level("57000", origin=other_origin),
        stop=level("57000", origin=other_origin),
        anchor=anchor(origin=other_origin),
    )
    with pytest.raises(DomainValidationError, match="belongs to proposal"):
        fold_proposal_state(
            subject, (lifecycle_event(other, LifecycleKind.REAFFIRMED, 10),)
        )


def test_the_fold_is_pure_and_repeatable() -> None:
    subject = proposal()
    events = (_accept(subject), lifecycle_event(subject, LifecycleKind.ENTRY_TRIGGERED, 11))
    assert fold_proposal_state(subject, events) == fold_proposal_state(subject, events)


def test_a_state_view_reports_its_ambiguity_consistently() -> None:
    with pytest.raises(DomainValidationError, match="at least the two events"):
        ProposalStateView(ProposalState.LIVE, (), is_ambiguous=True, ambiguous_events=("a",))
    with pytest.raises(DomainValidationError, match="not ambiguous"):
        ProposalStateView(ProposalState.LIVE, (), ambiguous_events=("a", "b"))


def test_a_state_view_serializes_for_a_surface() -> None:
    view = fold_proposal_state(proposal(), ())
    assert view.to_payload() == {
        "state": "live",
        "applied": [],
        "is_ambiguous": False,
        "ambiguous_events": [],
    }


def test_the_fold_rejects_something_that_is_not_a_proposal() -> None:
    with pytest.raises(TypeError, match="OpportunityProposal"):
        fold_proposal_state("a proposal", ())  # type: ignore[arg-type]
