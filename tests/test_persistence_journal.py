"""The write journal: completeness, the hash chain, ordering, and tamper detection.

The one property everything else rests on is that **every write appends exactly one
event and no write path can skip it**. The rest is what makes that claim checkable
after the fact: the chain links each event to its predecessor, so a removed,
altered or reordered event fails verification with the first broken link named.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from persistence_helpers import NOW, journal_entry, new_record_store, write_request
from trade_domain_helpers import (
    AT,
    correction,
    market_snapshot,
    quantity,
    reason_tag,
    trade,
    version_set,
)

from fmis.persistence import (
    AppendOnlyViolationError,
    JournalEngine,
    JournalEvent,
    PersistenceError,
    RecordKind,
    StoreIntegrityError,
    StoreLayout,
    WriteOperation,
    WriteSource,
)
from fmis.provenance import Absent
from fmis.records import ConsumedSource

# --------------------------------------------------------------------------
# Completeness: one event per write, and no write without one.
# --------------------------------------------------------------------------


def test_every_write_appends_exactly_one_event(tmp_path: Path, sample_records) -> None:
    store = new_record_store(tmp_path)
    for record in sample_records:
        store.publish(record, request=write_request())
    events = store.journal.events()
    assert len(events) == len(sample_records)
    assert [event.sequence for event in events] == list(range(len(sample_records)))


def test_an_idempotent_write_appends_no_event(tmp_path: Path) -> None:
    """Nothing changed, so nothing is recorded. An audit trail of non-events
    dilutes the events that matter."""
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    store.publish(subject, request=write_request())
    assert len(store.journal.events()) == 1


def test_a_refused_write_appends_no_event(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    with pytest.raises(PersistenceError):
        store.publish(trade(occurred_at=AT(10)), request=write_request(written_at=AT(9)))
    assert store.journal.events() == ()


def test_every_journalled_record_is_indexed_and_the_reverse(
    tmp_path: Path, sample_records
) -> None:
    store = new_record_store(tmp_path)
    for record in sample_records:
        store.publish(record, request=write_request())
    journalled = {event.record_id for event in store.journal.events()}
    indexed = {entry.record_id for entry in store.index.entries()}
    assert journalled == indexed


def test_the_index_row_names_the_event_that_created_it(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    receipt = store.publish(subject, request=write_request())
    entry = store.index.find(subject.event_id)
    assert entry.journal_event_id == receipt.journal_event.event_id
    assert entry.journal_sequence == receipt.journal_event.sequence


# --------------------------------------------------------------------------
# The six required fields.
# --------------------------------------------------------------------------


def test_an_event_carries_timestamp_source_author_reason_version_and_provenance(
    tmp_path: Path,
) -> None:
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    provenance = (
        ConsumedSource(
            record_id="market_snapshot-x-20260812T090000Z-0123456789abcdef",
            content_digest="sha256:" + "c" * 64,
            kind="market_snapshot",
        ),
    )
    store.publish(
        subject,
        request=write_request(
            source=WriteSource.POLICY_ENGINE,
            author="scan",
            reason=reason_tag("scheduled_scan", "write_reason"),
            provenance=provenance,
        ),
    )
    event = store.journal.events()[0]
    assert event.occurred_at == NOW
    assert event.source is WriteSource.POLICY_ENGINE
    assert event.author == "scan"
    assert event.reason.qualified_id == "write_reason:scheduled_scan"
    assert event.version_set == version_set()
    assert event.provenance == provenance


def test_an_event_round_trips_to_an_equal_value(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request())
    event = store.journal.events()[0]
    assert JournalEvent.from_payload(event.to_payload()) == event


def test_an_untagged_write_is_refused() -> None:
    """*"An untagged correction cannot be counted"* — the same rule, one layer up."""
    with pytest.raises(TypeError, match="VersionedTerm"):
        write_request(reason="because")


# --------------------------------------------------------------------------
# The operation is read off the record, not taken from the caller.
# --------------------------------------------------------------------------


def test_a_correction_is_journalled_as_a_supersession_however_it_was_requested(
    tmp_path: Path,
) -> None:
    store = new_record_store(tmp_path)
    original = trade()
    store.publish(original, request=write_request())
    fix = correction(original, trade(quantity=quantity("0.6")))
    store.publish(fix, request=write_request(operation=WriteOperation.CREATE))
    event = store.journal.events()[1]
    assert event.operation is WriteOperation.SUPERSEDE
    assert event.supersedes == original.event_id


def test_claiming_a_supersession_a_record_does_not_make_is_refused(
    tmp_path: Path,
) -> None:
    store = new_record_store(tmp_path)
    with pytest.raises(PersistenceError, match="names nothing it supersedes"):
        store.publish(
            trade(), request=write_request(operation=WriteOperation.SUPERSEDE)
        )


def test_an_event_may_not_claim_a_supersession_without_naming_one() -> None:
    with pytest.raises(PersistenceError, match="must name the record it supersedes"):
        JournalEvent(
            sequence=0,
            occurred_at=NOW,
            source=WriteSource.OWNER,
            author="owner",
            reason=reason_tag(),
            version_set=version_set(),
            operation=WriteOperation.SUPERSEDE,
            record_kind=RecordKind.TRADE,
            record_id="trade-x-20260812T100000Z-0123456789abcdef",
            content_digest="sha256:" + "a" * 64,
            previous_event_id=Absent("first"),
        )


def test_an_event_may_not_name_a_supersession_without_claiming_one() -> None:
    with pytest.raises(PersistenceError, match="invisible to every later reader"):
        JournalEvent(
            sequence=0,
            occurred_at=NOW,
            source=WriteSource.OWNER,
            author="owner",
            reason=reason_tag(),
            version_set=version_set(),
            operation=WriteOperation.CREATE,
            record_kind=RecordKind.TRADE,
            record_id="trade-x-20260812T100000Z-0123456789abcdef",
            content_digest="sha256:" + "a" * 64,
            previous_event_id=Absent("first"),
            supersedes="trade-y-20260812T100000Z-0123456789abcdef",
        )


# --------------------------------------------------------------------------
# The chain.
# --------------------------------------------------------------------------


def test_each_event_links_to_the_one_before_it(tmp_path: Path, sample_records) -> None:
    store = new_record_store(tmp_path)
    for record in sample_records:
        store.publish(record, request=write_request())
    events = store.journal.events()
    assert isinstance(events[0].previous_event_id, Absent)
    for earlier, later in zip(events, events[1:]):
        assert later.previous_event_id == earlier.event_id


def test_a_first_event_may_not_name_a_predecessor() -> None:
    with pytest.raises(StoreIntegrityError, match="no predecessor to name"):
        JournalEvent(
            sequence=0,
            occurred_at=NOW,
            source=WriteSource.OWNER,
            author="owner",
            reason=reason_tag(),
            version_set=version_set(),
            operation=WriteOperation.CREATE,
            record_kind=RecordKind.TRADE,
            record_id="trade-x-20260812T100000Z-0123456789abcdef",
            content_digest="sha256:" + "a" * 64,
            previous_event_id="journal_event-create-20260812T100000Z-0123456789abcdef",
        )


def test_a_later_event_may_not_omit_its_predecessor() -> None:
    with pytest.raises(StoreIntegrityError, match="broken chain"):
        JournalEvent(
            sequence=1,
            occurred_at=NOW,
            source=WriteSource.OWNER,
            author="owner",
            reason=reason_tag(),
            version_set=version_set(),
            operation=WriteOperation.CREATE,
            record_kind=RecordKind.TRADE,
            record_id="trade-x-20260812T100000Z-0123456789abcdef",
            content_digest="sha256:" + "a" * 64,
            previous_event_id=Absent("none"),
        )


def test_removing_an_event_from_the_middle_breaks_the_chain(tmp_path: Path) -> None:
    """The property the chain exists for: a deletion is detected, not merely unlikely."""
    store = new_record_store(tmp_path)
    for hour in (10, 11, 12):
        store.publish(trade(occurred_at=AT(hour)), request=write_request())
    path = tmp_path / "journal" / "2026.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
    result = store.journal.verify()
    assert not result.ok
    assert any("sequence" in problem for problem in result.problems)
    with pytest.raises(StoreIntegrityError, match="does not verify"):
        store.journal.events()


def test_reordering_two_events_breaks_the_chain(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    for hour in (10, 11, 12):
        store.publish(trade(occurred_at=AT(hour)), request=write_request())
    path = tmp_path / "journal" / "2026.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(
        "\n".join([lines[0], lines[2], lines[1]]) + "\n", encoding="utf-8"
    )
    assert not store.journal.verify().ok


def test_altering_a_field_inside_an_event_is_detected(tmp_path: Path) -> None:
    """The event id is a digest of every field, so any edit fails to re-derive it."""
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request())
    path = tmp_path / "journal" / "2026.jsonl"
    text = path.read_text(encoding="utf-8").replace('"author":"owner"', '"author":"nobody"')
    path.write_text(text, encoding="utf-8")
    result = store.journal.verify()
    assert not result.ok
    assert any("does not match the digest" in problem for problem in result.problems)


def test_an_event_id_is_a_pure_function_of_its_content(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request())
    event = store.journal.events()[0]
    assert event.event_id == JournalEvent.from_payload(event.to_payload()).event_id


# --------------------------------------------------------------------------
# Ordering: filing time never moves backwards.
# --------------------------------------------------------------------------


def test_a_write_filed_before_the_head_is_refused(tmp_path: Path) -> None:
    """A record may be backfilled; the act of filing it happens now."""
    store = new_record_store(tmp_path)
    store.publish(trade(occurred_at=AT(10)), request=write_request(written_at=NOW))
    with pytest.raises(AppendOnlyViolationError, match="before the journal head"):
        store.publish(
            trade(occurred_at=AT(9)),
            request=write_request(written_at=NOW - timedelta(days=1)),
        )


def test_a_backfilled_record_is_filed_now_and_that_is_visible(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    old = trade(occurred_at=AT(10, day=1))
    store.publish(old, request=write_request())
    entry = store.index.find(old.event_id)
    assert entry.occurred_at == AT(10, day=1)
    assert entry.written_at == NOW


def test_two_writes_at_the_same_instant_are_both_accepted(tmp_path: Path) -> None:
    """Equal is not backwards. Two records filed in one second is ordinary."""
    store = new_record_store(tmp_path)
    store.publish(trade(occurred_at=AT(10)), request=write_request())
    store.publish(trade(occurred_at=AT(11)), request=write_request())
    assert len(store.journal.events()) == 2


def test_events_span_calendar_years_in_order(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(occurred_at=AT(10)), request=write_request())
    store.publish(
        market_snapshot(built_at=AT(9).replace(year=2027)),
        request=write_request(written_at=NOW.replace(year=2027)),
    )
    assert store.layout.journal_years() == (2026, 2027)
    events = store.journal.events()
    assert [event.sequence for event in events] == [0, 1]
    assert store.journal.verify().ok


# --------------------------------------------------------------------------
# Reading.
# --------------------------------------------------------------------------


def test_the_head_is_the_most_recent_event(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    assert store.journal.head() is None
    for hour in (10, 11):
        store.publish(trade(occurred_at=AT(hour)), request=write_request())
    assert store.journal.head() == store.journal.events()[-1]


def test_a_records_own_audit_trail_is_readable(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    store.publish(market_snapshot(), request=write_request())
    events = store.journal.events_for(subject.event_id)
    assert len(events) == 1
    assert events[0].record_id == subject.event_id


def test_events_can_be_read_over_a_closed_interval(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(occurred_at=AT(10)), request=write_request(written_at=NOW))
    later = NOW + timedelta(days=1)
    store.publish(journal_entry(), request=write_request(written_at=later))
    assert len(store.journal.events_between(since=later)) == 1
    assert len(store.journal.events_between(until=NOW)) == 1
    assert len(store.journal.events_between(since=NOW, until=later)) == 2


def test_an_inverted_interval_is_refused(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    with pytest.raises(PersistenceError, match="precedes since"):
        store.journal.events_between(since=NOW, until=NOW - timedelta(days=1))


def test_an_empty_journal_verifies(tmp_path: Path) -> None:
    engine = JournalEngine(StoreLayout(tmp_path))
    result = engine.verify()
    assert result.ok
    assert result.event_count == 0
    assert result.head_sequence is None


def test_the_engine_requires_a_layout() -> None:
    with pytest.raises(TypeError, match="StoreLayout"):
        JournalEngine("/tmp")  # type: ignore[arg-type]


def test_a_truncated_journal_file_is_reported_rather_than_repaired(
    tmp_path: Path,
) -> None:
    """The last append did not finish. Dropping the partial line would be a repair."""
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request())
    path = tmp_path / "journal" / "2026.jsonl"
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")
    result = store.journal.verify()
    assert not result.ok
    assert any("mid-line" in problem for problem in result.problems)
