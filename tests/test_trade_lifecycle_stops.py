"""Milestone BO — stop management as appended events, and the law it obeys.

`AP` §9.3 in executable form. Three things are asserted that a design document
can only assert in prose:

**`TradePlan.initial_invalidation` is never touched.** The fold produces an
effective stop; the commitment's own field is byte-identical before and after.

**A rule this system applies may only tighten.** A `POLICY_DERIVED` amendment
that widened is refused *at read time* as well as at write time, so a store
containing one is rejected rather than quietly measured.

**The chain is validated, not trusted.** An amendment whose `previous_stop` does
not match what the last one left is a refusal, because an effective stop folded
across a gap is a value no record supports.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fmis.provenance import Absent, ValueOrigin, VersionedTerm
from fmis.records import DomainValidationError, PayloadDecodeError, RecordAudit
from fmis.snapshotting import TradeDirection
from fmis.trade_lifecycle import (
    AMENDABLE_ORIGINS,
    BREAK_EVEN_TERM,
    STOP_AMENDMENT_REASON_VOCABULARY,
    STOP_POLICY_VOCABULARY,
    SUGGESTED_AMENDMENT_REASONS,
    TRAILING_TERM,
    StopAmendment,
    StopAmendmentError,
    StopHistory,
    StopMove,
    fold_stop_history,
)
from paper_helpers import activation, at, plan, short_plan


OWNER_TERM = VersionedTerm(
    vocabulary_id=STOP_AMENDMENT_REASON_VOCABULARY,
    term_id="structure_changed",
    taxonomy_version=1,
)


def amendment(subject, previous: str, new: str, *, hours: int = 1, **overrides):
    fields = {
        "activation_id": subject.activation_id,
        "previous_stop": Decimal(previous),
        "new_stop": Decimal(new),
        "reason": OWNER_TERM,
        "origin": ValueOrigin.ASSERTED,
        "author": "owner",
        "occurred_at": at(hours),
        "recorded_at": at(hours),
        "audit": RecordAudit.frozen_at(at(hours)),
    }
    fields.update(overrides)
    if overrides.get("origin") is ValueOrigin.POLICY_DERIVED:
        fields.setdefault("policy_id", "fmits-paper-fill")
        fields.setdefault("policy_version", 1)
        fields.setdefault("causing_close_time", fields["occurred_at"])
        fields.setdefault("reason", BREAK_EVEN_TERM)
    return StopAmendment(**fields)


# --------------------------------------------------------------------------
# The record
# --------------------------------------------------------------------------


def test_an_amendment_round_trips_through_its_payload_exactly() -> None:
    original = amendment(activation(), "95", "100")
    assert StopAmendment.from_payload(original.to_payload()) == original


def test_a_move_that_changes_nothing_is_not_a_move() -> None:
    with pytest.raises(StopAmendmentError, match="already"):
        amendment(activation(), "95", "95")


def test_an_untagged_move_cannot_be_counted_and_is_refused() -> None:
    with pytest.raises(TypeError, match="VersionedTerm"):
        amendment(activation(), "95", "100", reason="structure changed")


def test_only_two_origins_may_move_a_stop() -> None:
    """A measurement does not move a stop, and **no model may**."""
    assert AMENDABLE_ORIGINS == {ValueOrigin.ASSERTED, ValueOrigin.POLICY_DERIVED}
    for origin in (ValueOrigin.MEASURED, ValueOrigin.INTERPRETED, ValueOrigin.ABSENT):
        with pytest.raises(StopAmendmentError, match="never"):
            amendment(activation(), "95", "100", origin=origin)


def test_a_policy_move_names_the_policy_and_the_candle_that_produced_it() -> None:
    with pytest.raises(StopAmendmentError, match="names the policy"):
        StopAmendment(
            activation_id=activation().activation_id,
            previous_stop=Decimal("95"),
            new_stop=Decimal("100"),
            reason=BREAK_EVEN_TERM,
            origin=ValueOrigin.POLICY_DERIVED,
            author="engine",
            occurred_at=at(1),
            recorded_at=at(1),
            audit=RecordAudit.frozen_at(at(1)),
        )
    with pytest.raises(StopAmendmentError, match="closed candle"):
        amendment(
            activation(),
            "95",
            "100",
            origin=ValueOrigin.POLICY_DERIVED,
            causing_close_time=Absent("none"),
        )


def test_an_owner_move_names_no_policy_because_it_has_none() -> None:
    with pytest.raises(StopAmendmentError, match="names no policy"):
        amendment(activation(), "95", "100", policy_id="x", policy_version=1)


def test_the_policy_pair_is_stated_together_or_not_at_all() -> None:
    with pytest.raises(StopAmendmentError, match="together or not at all"):
        amendment(activation(), "95", "100", policy_id="x")


def test_tightening_is_decided_by_the_side_and_never_stored_on_the_record() -> None:
    """A second copy of the direction here would be the field that eventually
    disagrees with the activation's."""
    assert "direction" not in StopAmendment.__dataclass_fields__
    move = amendment(activation(), "95", "100")
    assert move.tightens(TradeDirection.LONG)
    assert move.widens(TradeDirection.SHORT)


def test_the_author_is_excluded_from_the_digest_but_kept_on_the_record() -> None:
    subject = activation()
    one = amendment(subject, "95", "100", author="owner")
    two = amendment(subject, "95", "100", author="someone else")
    assert one.amendment_id == two.amendment_id
    assert StopAmendment.from_payload(two.to_payload()).author == "someone else"


def test_a_payload_whose_id_does_not_match_its_content_is_refused() -> None:
    payload = amendment(activation(), "95", "100").to_payload()
    payload["amendment_id"] = "stop_amendment-x-20260801T000000Z-" + "0" * 16
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        StopAmendment.from_payload(payload)


def test_an_unknown_origin_read_from_disk_is_a_clean_rejection() -> None:
    payload = amendment(activation(), "95", "100").to_payload()
    payload["origin"] = "vibes"
    with pytest.raises(PayloadDecodeError, match="not known to this build"):
        StopAmendment.from_payload(payload)


def test_the_suggested_reasons_are_the_design_records_six_and_are_not_enforced() -> None:
    """`AP` §9.3 calls the vocabulary closed; §20.2 says membership is the
    owner's, and this repository's shipped precedent follows §20.2."""
    assert set(SUGGESTED_AMENDMENT_REASONS) == {
        "structure_changed",
        "volatility_expanded",
        "de_risking",
        "emotional",
        "error_correction",
        "thesis_invalidated",
    }
    invented = amendment(
        activation(),
        "95",
        "100",
        reason=VersionedTerm(
            vocabulary_id=STOP_AMENDMENT_REASON_VOCABULARY,
            term_id="a_term_the_owner_invented",
            taxonomy_version=1,
        ),
    )
    assert invented.reason.term_id == "a_term_the_owner_invented"


def test_the_two_policy_terms_belong_to_this_code_paths_own_vocabulary() -> None:
    for term in (BREAK_EVEN_TERM, TRAILING_TERM):
        assert term.vocabulary_id == STOP_POLICY_VOCABULARY


# --------------------------------------------------------------------------
# The fold
# --------------------------------------------------------------------------


def _history(subject, *amendments, direction=TradeDirection.LONG, initial="95", **kw):
    return fold_stop_history(
        initial_stop=Decimal(initial),
        direction=direction,
        amendments=amendments,
        **kw,
    )


def test_a_history_with_no_move_is_the_commitment_itself() -> None:
    history = _history(activation())
    assert history.initial == history.effective == Decimal("95")
    assert not history.has_moved
    assert history.honours_initial


def test_the_plans_own_field_is_untouched_by_any_amendment() -> None:
    committed = plan()
    before = committed.to_payload()
    subject = activation(committed)
    history = _history(subject, amendment(subject, "95", "100"))
    assert history.effective == Decimal("100")
    assert committed.initial_invalidation == Decimal("95")
    assert committed.to_payload() == before


def test_a_tightened_stop_still_honours_the_commitment() -> None:
    """Not *'unchanged'*: counting a tightening as a departure would make the
    metric read as indiscipline every time the owner did the right thing."""
    subject = activation()
    history = _history(subject, amendment(subject, "95", "100"))
    assert history.tightening_count == 1
    assert history.widening_count == 0
    assert history.honours_initial


def test_a_widened_stop_is_counted_and_the_history_says_so() -> None:
    subject = activation()
    history = _history(subject, amendment(subject, "95", "90"))
    assert history.widening_count == 1
    assert not history.honours_initial
    assert history.owner_move_count == 1


def test_widening_is_mirrored_for_the_other_side() -> None:
    subject = activation(short_plan(), entry_price=Decimal("100"))
    tighter = _history(
        subject,
        amendment(subject, "105", "100"),
        direction=TradeDirection.SHORT,
        initial="105",
    )
    assert tighter.widening_count == 0
    looser = _history(
        subject,
        amendment(subject, "105", "110"),
        direction=TradeDirection.SHORT,
        initial="105",
    )
    assert looser.widening_count == 1


def test_a_rule_this_system_applies_may_only_tighten() -> None:
    subject = activation()
    with pytest.raises(StopAmendmentError, match="may only tighten"):
        _history(
            subject,
            amendment(subject, "95", "90", origin=ValueOrigin.POLICY_DERIVED),
        )


def test_a_chain_that_does_not_join_is_refused() -> None:
    subject = activation()
    with pytest.raises(StopAmendmentError, match="does not join"):
        _history(subject, amendment(subject, "97", "100"))


def test_the_chain_folds_in_order_and_the_effective_stop_is_what_the_last_left() -> None:
    subject = activation()
    history = _history(
        subject,
        amendment(subject, "100", "105", hours=2),
        amendment(subject, "95", "100", hours=1),
    )
    assert history.effective == Decimal("105")
    assert [move.arithmetic for move in history.moves] == ["95 → 100", "100 → 105"]


def test_a_bounded_fold_uses_the_stop_that_was_in_force_then() -> None:
    """A monitoring reading taken while replaying history must not use the stop
    in force now."""
    subject = activation()
    args = (amendment(subject, "95", "100", hours=1), amendment(subject, "100", "105", hours=3))
    assert _history(subject, *args, at=at(2)).effective == Decimal("100")
    assert _history(subject, *args, at=at(4)).effective == Decimal("105")


def test_a_superseded_amendment_is_dropped_before_the_fold_sees_it() -> None:
    subject = activation()
    wrong = amendment(subject, "95", "90", hours=1)
    correction = amendment(
        subject, "95", "100", hours=2, supersedes=wrong.amendment_id
    )
    history = _history(subject, wrong, correction)
    assert history.effective == Decimal("100")
    assert len(history.moves) == 1


def test_a_history_needs_a_side_to_tell_tightening_from_widening() -> None:
    with pytest.raises(DomainValidationError, match="has none"):
        _history(activation(), direction=TradeDirection.NO_TRADE)


def test_a_history_refuses_an_effective_stop_no_move_supports() -> None:
    with pytest.raises(DomainValidationError, match="no move"):
        StopHistory(initial=Decimal("95"), effective=Decimal("100"))
    move = StopMove(
        amendment_id=amendment(activation(), "95", "100").amendment_id,
        at=at(1),
        previous_stop=Decimal("95"),
        new_stop=Decimal("100"),
        reason=OWNER_TERM,
        origin=ValueOrigin.ASSERTED,
        tightened=True,
    )
    with pytest.raises(DomainValidationError, match="what the last move left"):
        StopHistory(initial=Decimal("95"), effective=Decimal("105"), moves=(move,))


def test_a_history_serializes_for_export_and_cannot_be_read_back() -> None:
    subject = activation()
    history = _history(subject, amendment(subject, "95", "100"))
    payload = history.to_payload()
    assert payload["effective"] == "100"
    assert payload["moves"][0]["tightened"] is True
    assert not hasattr(StopHistory, "from_payload")


def test_the_fold_rejects_something_that_is_not_an_amendment() -> None:
    with pytest.raises(TypeError, match="StopAmendment"):
        _history(activation(), "a move")
