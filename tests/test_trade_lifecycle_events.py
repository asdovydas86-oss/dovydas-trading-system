"""Milestone BO — the lifecycle stream and the fold that is the only state.

Three properties are what these tests exist for.

**Illegal transitions raise.** The milestone brief asks for it in those words,
and the table is the whole of the answer: an event absent from the current
state's row is an error, never a silent no-op.

**Nothing is stored.** Every state on every page is `fold_trade_lifecycle`'s
return value, and the same events in a different order give the same answer.

**Two events one candle cannot order are a refusal.** The engine never emits
such a pair, and the fold refuses one anyway — because a store can be written to
by a future build, and an arbitrary order presented as a real one is exactly the
corruption AP-D4a names.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from fmis.provenance import Absent, ValueOrigin, VersionedTerm
from fmis.records import DomainValidationError, PayloadDecodeError, RecordAudit
from fmis.trade_lifecycle import (
    CAUSAL_RANK,
    LIFECYCLE_KIND_ORIGINS,
    LIFECYCLE_TRANSITIONS,
    LIVE_LIFECYCLE_STATES,
    MEASURED_LIFECYCLE_KINDS,
    TERMINAL_LIFECYCLE_STATES,
    IllegalLifecycleTransitionError,
    TradeLifecycleEvent,
    TradeLifecycleKind,
    TradeLifecycleState,
    TradeLifecycleView,
    fold_trade_lifecycle,
)
from paper_helpers import activation, at, event


def _fold(subject, *events):
    return fold_trade_lifecycle(subject.activation_id, events)


# --------------------------------------------------------------------------
# The table
# --------------------------------------------------------------------------


def test_every_state_has_a_row_and_only_one_is_terminal() -> None:
    assert set(LIFECYCLE_TRANSITIONS) == set(TradeLifecycleState)
    assert TERMINAL_LIFECYCLE_STATES == {TradeLifecycleState.RESOLVED}
    assert LIFECYCLE_TRANSITIONS[TradeLifecycleState.RESOLVED] == {}


def test_every_kind_has_an_origin_and_a_causal_rank() -> None:
    assert set(LIFECYCLE_KIND_ORIGINS) == set(TradeLifecycleKind)
    assert set(CAUSAL_RANK) == set(TradeLifecycleKind)
    assert len(set(CAUSAL_RANK.values())) == len(TradeLifecycleKind)


def test_a_stop_amendment_has_no_single_origin_because_it_is_genuinely_two() -> None:
    """The owner moving their own stop is `ASSERTED`; a rule the owner enabled
    is `POLICY_DERIVED`. The record the event references carries which."""
    assert (
        LIFECYCLE_KIND_ORIGINS[TradeLifecycleKind.STOP_AMENDED] is ValueOrigin.ABSENT
    )


def test_a_halt_is_not_a_live_state() -> None:
    """A halted trade is waiting for the owner, not for the next candle."""
    assert TradeLifecycleState.AMBIGUOUS not in LIVE_LIFECYCLE_STATES
    assert TradeLifecycleState.PENDING in LIVE_LIFECYCLE_STATES


def test_every_reachable_state_can_still_reach_a_resolution() -> None:
    """No state is a dead end that could never be scored."""
    for state, row in LIFECYCLE_TRANSITIONS.items():
        if state is TradeLifecycleState.RESOLVED:
            continue
        assert row, state


# --------------------------------------------------------------------------
# The fold
# --------------------------------------------------------------------------


def test_a_stream_with_no_events_folds_to_pending() -> None:
    view = _fold(activation())
    assert view.state is TradeLifecycleState.PENDING
    assert view.applied == ()
    assert isinstance(view.last_event_at, Absent)
    assert view.is_live


def test_the_happy_path_folds_through_every_state_it_passes() -> None:
    subject = activation()
    view = _fold(
        subject,
        event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1),
        event(subject, TradeLifecycleKind.ENTRY_FILLED, hours=1, bar_sequence=1),
        event(subject, TradeLifecycleKind.PARTIAL_EXIT_FILLED, hours=2),
        event(subject, TradeLifecycleKind.EXIT_FILLED, hours=3),
        event(subject, TradeLifecycleKind.OUTCOME_RECORDED, hours=4),
    )
    assert view.state is TradeLifecycleState.RESOLVED
    assert view.is_terminal
    assert len(view.applied) == 5
    assert view.last_event_at == at(4)


def test_the_fold_does_not_depend_on_the_order_events_are_handed_to_it() -> None:
    subject = activation()
    events = [
        event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1),
        event(subject, TradeLifecycleKind.ENTRY_FILLED, hours=1, bar_sequence=1),
        event(subject, TradeLifecycleKind.EXIT_FILLED, hours=3),
    ]
    assert _fold(subject, *events) == _fold(subject, *reversed(events))


def test_an_illegal_transition_raises_and_names_what_was_legal() -> None:
    subject = activation()
    with pytest.raises(IllegalLifecycleTransitionError, match="cannot follow state"):
        _fold(subject, event(subject, TradeLifecycleKind.ENTRY_FILLED, hours=1))


def test_nothing_follows_a_resolution() -> None:
    subject = activation()
    with pytest.raises(IllegalLifecycleTransitionError, match="terminal"):
        _fold(
            subject,
            event(subject, TradeLifecycleKind.EXPIRED, hours=1),
            event(subject, TradeLifecycleKind.OUTCOME_RECORDED, hours=2),
            event(subject, TradeLifecycleKind.OUTCOME_RECORDED, hours=3),
        )


def test_an_event_belonging_to_another_activation_is_refused() -> None:
    subject = activation()
    other = activation(activated_at=at(5))
    with pytest.raises(DomainValidationError, match="belongs to activation"):
        _fold(subject, event(other, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1))


def test_a_superseded_event_is_dropped_before_the_fold_sees_it() -> None:
    subject = activation()
    wrong = event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1)
    correction = event(
        subject,
        TradeLifecycleKind.ENTRY_TRIGGERED,
        hours=2,
        supersedes=wrong.event_id,
    )
    view = _fold(subject, wrong, correction)
    assert view.applied == (correction.event_id,)
    assert view.last_event_at == at(2)


def test_two_events_the_fold_cannot_order_are_a_refusal() -> None:
    """Equal `(when, bar_sequence, causal rank)` means nothing decides which
    came first, and applying either order would invent a sequence."""
    subject = activation()
    first = event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1)
    second = event(
        subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1, note="a second one"
    )
    with pytest.raises(DomainValidationError, match="share an ordering key"):
        _fold(subject, first, second)


def test_two_rungs_on_one_bar_are_ordered_by_the_sequence_geometry_gave_them() -> None:
    subject = activation()
    view = _fold(
        subject,
        event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1),
        event(subject, TradeLifecycleKind.ENTRY_FILLED, hours=1, bar_sequence=1),
        event(subject, TradeLifecycleKind.PARTIAL_EXIT_FILLED, hours=2),
        event(
            subject,
            TradeLifecycleKind.EXIT_FILLED,
            hours=2,
            bar_sequence=1,
            causing_close_time=at(2),
        ),
    )
    assert view.state is TradeLifecycleState.CLOSED


def test_a_halt_is_reachable_from_every_state_that_can_hold_exposure() -> None:
    subject = activation()
    view = _fold(
        subject,
        event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1),
        event(subject, TradeLifecycleKind.ENTRY_FILLED, hours=1, bar_sequence=1),
        event(subject, TradeLifecycleKind.AMBIGUOUS_BAR, hours=2),
    )
    assert view.state is TradeLifecycleState.AMBIGUOUS
    assert view.is_halted
    assert not view.is_live
    assert not view.is_terminal


def test_a_halt_is_resolved_by_the_exit_the_owner_records() -> None:
    subject = activation()
    view = _fold(
        subject,
        event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1),
        event(subject, TradeLifecycleKind.ENTRY_FILLED, hours=1, bar_sequence=1),
        event(subject, TradeLifecycleKind.AMBIGUOUS_BAR, hours=2),
        event(subject, TradeLifecycleKind.EXIT_FILLED, hours=3),
    )
    assert view.state is TradeLifecycleState.CLOSED


def test_exposure_is_derived_from_the_state_and_never_stored_beside_it() -> None:
    subject = activation()
    opened = _fold(
        subject,
        event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1),
        event(subject, TradeLifecycleKind.ENTRY_FILLED, hours=1, bar_sequence=1),
    )
    assert opened.has_exposure
    assert not _fold(subject).has_exposure


def test_the_fold_rejects_something_that_is_not_an_event() -> None:
    with pytest.raises(TypeError, match="TradeLifecycleEvent"):
        fold_trade_lifecycle(activation().activation_id, ("an event",))


# --------------------------------------------------------------------------
# The event record
# --------------------------------------------------------------------------


def test_an_event_round_trips_through_its_payload_exactly() -> None:
    subject = activation()
    original = event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1)
    assert TradeLifecycleEvent.from_payload(original.to_payload()) == original


def test_an_event_carries_no_price_and_no_quantity() -> None:
    """A fill's numbers live on the `Trade` the ledger holds; this names it."""
    fields = set(TradeLifecycleEvent.__dataclass_fields__)
    assert "price" not in fields
    assert "quantity" not in fields
    assert "reference" in fields


def test_a_measured_kind_must_carry_the_candle_that_caused_it() -> None:
    subject = activation()
    with pytest.raises(DomainValidationError, match="closed candle"):
        event(
            subject,
            TradeLifecycleKind.ENTRY_TRIGGERED,
            hours=1,
            causing_close_time=Absent("none"),
        )


def test_an_exit_is_not_a_measured_kind_because_a_manual_close_is_one_too() -> None:
    """The same kind records a simulated exit and the owner's own close;
    requiring a causing candle would make the second unrepresentable."""
    assert TradeLifecycleKind.EXIT_FILLED not in MEASURED_LIFECYCLE_KINDS
    subject = activation()
    manual = event(
        subject,
        TradeLifecycleKind.EXIT_FILLED,
        hours=3,
        causing_close_time=Absent("the owner closed this by hand"),
    )
    assert manual.ordering_key == at(3)


def test_a_cancellation_requires_a_reason_from_the_owners_vocabulary() -> None:
    subject = activation()
    with pytest.raises(DomainValidationError, match="reason tag"):
        event(
            subject,
            TradeLifecycleKind.CANCELLED,
            hours=1,
            reason=Absent("none given"),
        )


def test_a_halt_must_say_what_could_not_be_ordered() -> None:
    subject = activation()
    with pytest.raises(DomainValidationError, match="must say what"):
        event(
            subject,
            TradeLifecycleKind.AMBIGUOUS_BAR,
            hours=1,
            note=Absent("no note"),
        )


def test_a_supersession_event_names_what_took_over() -> None:
    subject = activation()
    with pytest.raises(DomainValidationError, match="names the activation"):
        event(
            subject,
            TradeLifecycleKind.SUPERSEDED,
            hours=1,
            reference=Absent("no reference"),
        )


def test_a_bar_sequence_needs_a_bar_to_be_a_position_inside() -> None:
    subject = activation()
    with pytest.raises(DomainValidationError, match="position inside one"):
        event(
            subject,
            TradeLifecycleKind.EXIT_FILLED,
            hours=1,
            causing_close_time=Absent("manual"),
            bar_sequence=2,
        )


def test_an_event_cannot_be_learned_of_before_it_happened() -> None:
    subject = activation()
    with pytest.raises(DomainValidationError, match="before it happened"):
        event(
            subject,
            TradeLifecycleKind.ENTRY_TRIGGERED,
            hours=2,
            recorded_at=at(1),
        )


def test_the_ordering_key_is_the_candle_and_not_when_the_run_happened() -> None:
    """A simulation that runs late records a later `recorded_at` and the same
    ordering key, which is the whole point."""
    subject = activation()
    early = event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1)
    late = event(
        subject,
        TradeLifecycleKind.ENTRY_TRIGGERED,
        hours=1,
        recorded_at=at(500),
    )
    assert early.ordering_key == late.ordering_key
    assert early.event_id == late.event_id


def test_an_unknown_kind_read_from_disk_is_a_clean_rejection() -> None:
    subject = activation()
    payload = event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1).to_payload()
    payload["kind"] = "liquidated"
    with pytest.raises(PayloadDecodeError, match="clean rejection"):
        TradeLifecycleEvent.from_payload(payload)


def test_a_payload_whose_id_does_not_match_its_content_is_refused() -> None:
    subject = activation()
    payload = event(subject, TradeLifecycleKind.ENTRY_TRIGGERED, hours=1).to_payload()
    payload["event_id"] = "lifecycle_step-x-20260801T000000Z-" + "0" * 16
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        TradeLifecycleEvent.from_payload(payload)


def test_the_audit_block_of_an_event_is_frozen() -> None:
    subject = activation()
    with pytest.raises(DomainValidationError, match="frozen at creation"):
        event(
            subject,
            TradeLifecycleKind.ENTRY_TRIGGERED,
            hours=1,
            audit=RecordAudit(created_at=at(1), updated_at=at(2)),
        )


def test_a_reason_must_be_a_versioned_term() -> None:
    subject = activation()
    with pytest.raises(TypeError, match="VersionedTerm"):
        event(subject, TradeLifecycleKind.CANCELLED, hours=1, reason="because")


# --------------------------------------------------------------------------
# The view
# --------------------------------------------------------------------------


def test_a_view_that_applied_events_knows_when_the_last_one_was() -> None:
    with pytest.raises(DomainValidationError, match="when the last one was"):
        TradeLifecycleView(state=TradeLifecycleState.OPEN, applied=("x",))
    with pytest.raises(DomainValidationError, match="no last event"):
        TradeLifecycleView(
            state=TradeLifecycleState.OPEN, applied=(), last_event_at=at(1)
        )


def test_a_view_serializes_for_export_and_cannot_be_read_back() -> None:
    view = TradeLifecycleView(state=TradeLifecycleState.PENDING)
    assert view.to_payload()["state"] == "pending"
    assert not hasattr(TradeLifecycleView, "from_payload")


def test_a_versioned_reason_tag_is_carried_through_the_payload() -> None:
    subject = activation()
    original = event(
        subject,
        TradeLifecycleKind.CANCELLED,
        hours=1,
        reason=VersionedTerm(
            vocabulary_id="stop_amendment_reason",
            term_id="de_risking",
            taxonomy_version=1,
        ),
    )
    decoded = TradeLifecycleEvent.from_payload(original.to_payload())
    assert decoded.reason.term_id == "de_risking"
