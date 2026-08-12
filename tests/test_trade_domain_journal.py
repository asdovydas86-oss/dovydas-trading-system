"""`JournalEntry` and `TradeJournal` — the brief's *TradeJournal*.

Two properties carry most of the value and are tested hardest: **recollection is
derived rather than set**, and **unconfirmed model output is never counted**.
"""

from __future__ import annotations

import pytest
from trade_domain_helpers import AT, market_snapshot, reason_tag

from fmis.journal import (
    COUNTED_TAG_ORIGINS,
    JournalEntry,
    JournalKind,
    JournalLink,
    JournalTag,
    LinkKind,
    ReviewStatus,
    TagOrigin,
    TradeJournal,
)
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError, PayloadDecodeError, RecordAudit

ABOUT_MARKET = JournalLink(LinkKind.ABOUT, "market", "binance:BTCUSDT:spot")


def entry(**overrides: object) -> JournalEntry:
    recorded = overrides.pop("recorded_at", AT(9))
    values: dict = {
        "kind": JournalKind.IDEA,
        "recorded_at": recorded,
        "author": "owner",
        "audit": RecordAudit.frozen_at(recorded),
        "title": "BTC continuation retest",
        "body": "waiting for a close above 62000 on the execution role",
        "links": (ABOUT_MARKET,),
    }
    values.update(overrides)
    return JournalEntry(**values)


# --------------------------------------------------------------------------
# Kind rules: required almost nothing, nudged everything else.
# --------------------------------------------------------------------------


def test_an_idea_carries_a_title_and_a_body() -> None:
    with pytest.raises(DomainValidationError, match="IDEA carries a title and a body"):
        entry(body=Absent("nothing written"))


def test_a_note_carries_a_title_or_a_body() -> None:
    assert entry(kind=JournalKind.NOTE, body=Absent("no body")).title
    assert entry(kind=JournalKind.NOTE, title=Absent("no title")).body
    with pytest.raises(DomainValidationError, match="NOTE carries a title or a body"):
        entry(kind=JournalKind.NOTE, title=Absent("no title"), body=Absent("no body"))


def test_a_review_names_the_period_it_reviews() -> None:
    with pytest.raises(DomainValidationError, match="names the period"):
        entry(kind=JournalKind.REVIEW)
    reviewed = entry(kind=JournalKind.REVIEW, period="2026-W33")
    assert reviewed.period == "2026-W33"


def test_a_non_review_does_not_carry_a_period() -> None:
    with pytest.raises(DomainValidationError, match="does not carry a review period"):
        entry(period="2026-W33")


def test_a_review_still_needs_a_title_and_a_body() -> None:
    with pytest.raises(DomainValidationError, match="REVIEW carries a title and a body"):
        entry(kind=JournalKind.REVIEW, period="2026-W33", body=Absent("nothing"))


# --------------------------------------------------------------------------
# Recollection — derived, and impossible to set.
# --------------------------------------------------------------------------


def test_recollection_is_false_when_nothing_had_resolved() -> None:
    assert not entry().recollection


def test_recollection_is_true_when_the_entry_followed_the_outcome() -> None:
    assert entry(recorded_at=AT(12), decision_resolved_at=AT(10)).recollection


def test_foresight_written_before_the_outcome_is_not_a_recollection() -> None:
    assert not entry(recorded_at=AT(9), decision_resolved_at=AT(12)).recollection


def test_recollection_cannot_be_supplied_by_a_caller() -> None:
    with pytest.raises(TypeError):
        entry(recollection=False)  # type: ignore[call-arg]


def test_recollection_is_not_a_stored_field() -> None:
    assert "recollection" not in entry().to_payload()


# --------------------------------------------------------------------------
# Tags: four origins, three counted.
# --------------------------------------------------------------------------


def test_only_three_of_the_four_tag_origins_are_counted() -> None:
    assert COUNTED_TAG_ORIGINS == {
        TagOrigin.OWNER,
        TagOrigin.AI_PROPOSED_CONFIRMED,
        TagOrigin.IMPORTED,
    }
    assert TagOrigin.AI_PROPOSED_PENDING not in COUNTED_TAG_ORIGINS


def test_an_unconfirmed_model_tag_is_kept_and_never_counted() -> None:
    pending = JournalTag(
        reason_tag("hesitation", "emotion"), TagOrigin.AI_PROPOSED_PENDING, AT(10)
    )
    tagged = entry().with_tag(pending)
    assert tagged.pending_tags == (pending,)
    assert tagged.counted_tags == ()
    assert not pending.is_counted


def test_a_confirmed_model_tag_is_counted_and_stays_separable() -> None:
    confirmed = JournalTag(
        reason_tag("hesitation", "emotion"), TagOrigin.AI_PROPOSED_CONFIRMED, AT(10)
    )
    tagged = entry().with_tag(confirmed)
    assert tagged.counted_tags == (confirmed,)
    assert confirmed.value_origin is ValueOrigin.INTERPRETED


def test_an_owner_tag_is_asserted() -> None:
    owned = JournalTag(reason_tag("moved_stop", "mistake"), TagOrigin.OWNER, AT(10))
    assert owned.value_origin is ValueOrigin.ASSERTED
    assert JournalTag(
        reason_tag("moved_stop", "mistake"), TagOrigin.IMPORTED, AT(10)
    ).value_origin is ValueOrigin.ASSERTED


def test_a_tag_must_be_a_vocabulary_term_and_not_a_bare_string() -> None:
    with pytest.raises(TypeError, match="silently redefined"):
        JournalTag("hesitation", TagOrigin.OWNER, AT(10))  # type: ignore[arg-type]


def test_the_same_term_cannot_be_applied_twice() -> None:
    tag = JournalTag(reason_tag("moved_stop", "mistake"), TagOrigin.OWNER, AT(10))
    with pytest.raises(DomainValidationError, match="already applied"):
        entry().with_tag(tag).with_tag(tag)


def test_appending_a_tag_advances_updated_at_and_never_the_entry_id() -> None:
    original = entry()
    tagged = original.with_tag(
        JournalTag(reason_tag("moved_stop", "mistake"), TagOrigin.OWNER, AT(11))
    )
    assert tagged.entry_id == original.entry_id
    assert tagged.audit.created_at == original.audit.created_at
    assert tagged.audit.updated_at == AT(11)
    assert not tagged.audit.is_unmodified


def test_a_tag_round_trips() -> None:
    tag = JournalTag(reason_tag("moved_stop", "mistake"), TagOrigin.OWNER, AT(10))
    assert JournalTag.from_payload(tag.to_payload()) == tag


def test_with_tag_type_checks_its_input() -> None:
    with pytest.raises(TypeError):
        entry().with_tag("moved_stop")  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Links are the architecture.
# --------------------------------------------------------------------------


def test_six_typed_link_kinds_exist_and_none_is_an_untyped_related() -> None:
    assert {kind.value for kind in LinkKind} == {
        "about",
        "caused_by",
        "reviews",
        "supersedes",
        "learned_from",
        "cites",
    }
    assert "related" not in {kind.value for kind in LinkKind}


def test_links_are_selectable_by_kind() -> None:
    subject = entry()
    assert subject.links_of(LinkKind.ABOUT) == (ABOUT_MARKET,)
    assert subject.links_of(LinkKind.CITES) == ()


def test_a_link_may_be_appended_and_never_duplicated() -> None:
    cited = JournalLink(LinkKind.CITES, "analysis_record", "workspace-BTCUSDT-1")
    linked = entry().with_link(cited, at=AT(11))
    assert len(linked.links) == 2
    assert linked.audit.updated_at == AT(11)
    with pytest.raises(DomainValidationError, match="already recorded"):
        linked.with_link(cited, at=AT(12))


def test_a_repeated_link_at_construction_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="must not be recorded twice"):
        entry(links=(ABOUT_MARKET, ABOUT_MARKET))


def test_with_link_type_checks_its_input() -> None:
    with pytest.raises(TypeError):
        entry().with_link("about the market", at=AT(11))  # type: ignore[arg-type]


def test_a_link_round_trips() -> None:
    assert JournalLink.from_payload(ABOUT_MARKET.to_payload()) == ABOUT_MARKET


# --------------------------------------------------------------------------
# Frozen context is a reference, never a copy.
# --------------------------------------------------------------------------


def test_the_frozen_context_is_a_snapshot_id_and_not_a_restated_regime() -> None:
    snapshot = market_snapshot()
    subject = entry(market_snapshot_id=snapshot.snapshot_id)
    payload = subject.to_payload()
    assert payload["market_snapshot_id"] == {"value": snapshot.snapshot_id}
    assert "regime" not in payload
    assert "conflicts" not in payload


def test_a_context_reference_must_be_a_real_record_id() -> None:
    with pytest.raises(DomainValidationError, match="expected shape"):
        entry(market_snapshot_id="the one from tuesday")


# --------------------------------------------------------------------------
# Identity and serialization.
# --------------------------------------------------------------------------


def test_an_entry_round_trips_and_verifies_its_own_id() -> None:
    subject = entry().with_tag(
        JournalTag(reason_tag("moved_stop", "mistake"), TagOrigin.OWNER, AT(11))
    )
    assert JournalEntry.from_payload(subject.to_payload()) == subject
    payload = subject.to_payload()
    payload["entry_id"] = "journal_entry-idea-20260812T090000Z-0123456789abcdef"
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        JournalEntry.from_payload(payload)


def test_an_entry_is_created_when_it_is_written() -> None:
    with pytest.raises(DomainValidationError, match="must equal recorded_at"):
        entry(audit=RecordAudit.frozen_at(AT(8)))


def test_a_changed_opinion_is_a_new_entry_that_supersedes_the_old_one() -> None:
    first = entry()
    second = entry(recorded_at=AT(12), supersedes=first.entry_id)
    assert second.supersedes == first.entry_id
    assert second.entry_id != first.entry_id


def test_review_status_defaults_to_unreviewed_and_is_a_closed_set() -> None:
    assert entry().review_status is ReviewStatus.UNREVIEWED
    assert {status.value for status in ReviewStatus} == {
        "unreviewed",
        "reviewed",
        "needs_follow_up",
    }


def test_an_unknown_journal_kind_on_decode_is_a_clean_rejection() -> None:
    payload = entry().to_payload()
    payload["kind"] = "manifesto"
    with pytest.raises(PayloadDecodeError, match="JournalKind"):
        JournalEntry.from_payload(payload)


# --------------------------------------------------------------------------
# TradeJournal — the read-time view.
# --------------------------------------------------------------------------


def test_the_view_gathers_only_entries_that_point_at_the_subject() -> None:
    linked = entry()
    unlinked = entry(
        recorded_at=AT(11),
        links=(JournalLink(LinkKind.ABOUT, "market", "binance:ETHUSDT:spot"),),
    )
    view = TradeJournal.gather("market", "binance:BTCUSDT:spot", (linked, unlinked))
    assert view.entries == (linked,)
    assert not view.is_empty


def test_an_empty_view_is_the_cheapest_discipline_metric() -> None:
    view = TradeJournal.gather("market", "binance:SOLUSDT:spot", (entry(),))
    assert view.is_empty
    assert view.entries == ()


def test_the_view_refuses_an_entry_that_does_not_point_at_its_subject() -> None:
    with pytest.raises(DomainValidationError, match="carries no link to"):
        TradeJournal("market", "binance:SOLUSDT:spot", (entry(),))


def test_the_view_orders_its_entries_by_when_they_were_written() -> None:
    late = entry(recorded_at=AT(12))
    early = entry(recorded_at=AT(9))
    view = TradeJournal.gather("market", "binance:BTCUSDT:spot", (late, early))
    assert [item.recorded_at for item in view.entries] == [AT(9), AT(12)]


def test_the_view_separates_recollections_from_what_a_cohort_may_read() -> None:
    foresight = entry(recorded_at=AT(9), decision_resolved_at=AT(12))
    hindsight = entry(recorded_at=AT(13), decision_resolved_at=AT(12))
    view = TradeJournal.gather(
        "market", "binance:BTCUSDT:spot", (foresight, hindsight)
    )
    assert view.recollections == (hindsight,)
    assert view.excluding_recollections == (foresight,)


def test_the_view_gathers_only_countable_tags() -> None:
    owned = JournalTag(reason_tag("moved_stop", "mistake"), TagOrigin.OWNER, AT(10))
    pending = JournalTag(
        reason_tag("hesitation", "emotion"), TagOrigin.AI_PROPOSED_PENDING, AT(10)
    )
    subject = entry().with_tag(owned).with_tag(pending)
    view = TradeJournal.gather("market", "binance:BTCUSDT:spot", (subject,))
    assert view.counted_tags == (owned,)


def test_the_view_selects_by_kind() -> None:
    idea = entry()
    note = entry(recorded_at=AT(11), kind=JournalKind.NOTE)
    view = TradeJournal.gather("market", "binance:BTCUSDT:spot", (idea, note))
    assert view.of_kind(JournalKind.NOTE) == (note,)
    assert view.of_kind(JournalKind.REVIEW) == ()
