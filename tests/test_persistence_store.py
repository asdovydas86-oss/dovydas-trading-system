"""`RecordStore` — round-trip, identity, idempotency, integrity, verification.

The properties tested hardest are the ones a later reader would otherwise have to
take on trust: **what is restored equals what was written**, **the same content
written twice is one record**, and **a byte altered on disk is detected rather
than decoded**.
"""

from __future__ import annotations

from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from persistence_helpers import NOW, new_record_store, new_store, write_request
from trade_domain_helpers import (
    AT,
    BTC,
    MARKET,
    USDT,
    correction,
    decision_window,
    market_snapshot,
    proposal,
    quantity,
    trade,
)

from fmis.archive.json_safe import canonical_dumps, canonical_loads
from fmis.journal import JournalEntry, JournalKind, JournalLink, LinkKind
from fmis.persistence import (
    DurabilityClass,
    FrozenRecordError,
    IndexEntry,
    PersistenceError,
    RecordConflictError,
    RecordKind,
    RecordMissingError,
    SPECS,
    StorageShape,
    StoreIntegrityError,
    StorePathError,
    StoredEnvelope,
    UnknownRecordKindError,
    WriteOperation,
    WriteRequest,
    WriteSource,
    spec_for_record,
)
from fmis.records import RecordAudit
from fmis.snapshotting import WindowMode

# --------------------------------------------------------------------------
# Round-trip: what is restored equals what was written.
# --------------------------------------------------------------------------


def test_a_trade_round_trips_to_an_equal_value(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    receipt = store.publish(subject, request=write_request())
    assert receipt.created
    assert store.load(subject.event_id) == subject


def test_every_persisted_kind_round_trips(tmp_path: Path, sample_records) -> None:
    """One sweep. A kind that gains a field and forgets its decoder fails here."""
    store = new_record_store(tmp_path)
    for record in sample_records:
        spec = spec_for_record(record)
        store.publish(record, request=write_request())
        restored = store.load(spec.identity(record))
        assert restored == record, spec.kind.value
        assert spec.digest(restored) == spec.digest(record), spec.kind.value


def test_a_restored_record_re_encodes_to_the_identical_bytes(
    tmp_path: Path, sample_records
) -> None:
    """Equality is not enough: the bytes must be stable too, or a digest moves."""
    store = new_record_store(tmp_path)
    for record in sample_records:
        spec = spec_for_record(record)
        store.publish(record, request=write_request())
        restored = store.load(spec.identity(record))
        assert canonical_dumps(spec.encode(restored)) == canonical_dumps(
            spec.encode(record)
        )


def test_every_record_kind_has_a_spec_and_every_spec_is_reachable() -> None:
    from fmis.persistence import RecordKind as Kind

    assert set(SPECS) == set(Kind)
    assert len({spec.type_slug for spec in SPECS.values()}) == len(SPECS)


# --------------------------------------------------------------------------
# Identity: content-derived, stable, and never re-derived differently.
# --------------------------------------------------------------------------


def test_writing_identical_content_twice_is_one_record(tmp_path: Path) -> None:
    """The crash-recovery case: a fill re-entered is not a second position move."""
    store = new_record_store(tmp_path)
    subject = trade()
    first = store.publish(subject, request=write_request())
    second = store.publish(subject, request=write_request())
    assert first.created is True
    assert second.created is False
    assert second.journal_event is None
    assert len(store.entries()) == 1
    assert len(store.journal.events()) == 1


def test_an_idempotent_write_is_unaffected_by_who_wrote_it(tmp_path: Path) -> None:
    """The same fill typed by hand and later synced is one event, not two."""
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    second = store.publish(
        subject,
        request=write_request(source=WriteSource.EXCHANGE_API, author="binance-sync"),
    )
    assert second.created is False
    assert len(store.entries()) == 1


def test_two_records_differing_only_in_content_get_different_ids(
    tmp_path: Path,
) -> None:
    store = new_record_store(tmp_path)
    first = trade()
    second = trade(quantity=quantity("0.75"))
    store.publish(first, request=write_request())
    store.publish(second, request=write_request())
    assert first.event_id != second.event_id
    assert len(store.entries()) == 2


def _reindexed(entry: IndexEntry, **overrides: object) -> IndexEntry:
    """The same index row with one column changed — for forging a corrupt store."""
    values = {
        name: getattr(entry, name)
        for name in IndexEntry.__dataclass_fields__
        if name != "schema_version"
    }
    values.update(overrides)
    return IndexEntry(**values)  # type: ignore[arg-type]


def test_an_id_stored_with_other_content_and_another_digest_is_a_conflict(
    tmp_path: Path,
) -> None:
    """The digest-prefix collision branch — handled, not assumed unreachable.

    A genuine 64-bit prefix collision cannot be constructed to order, so the shape
    of one is: an id already stored, whose recorded digest and whose stored bytes
    both differ from what is being written. A pruned window supplies the differing
    bytes; the forged index digest supplies the differing digest.
    """
    store = new_record_store(tmp_path)
    captured = decision_window()
    store.publish(captured, request=write_request())
    entry = store.index.find(captured.window_id)
    store.index.write_all(
        (_reindexed(entry, content_digest="sha256:" + "0" * 64),)
    )
    with pytest.raises(RecordConflictError, match="digest-prefix collision"):
        store.publish(captured.prune(NOW), request=write_request())


def test_an_unindexed_record_file_holding_other_content_is_never_overwritten(
    tmp_path: Path,
) -> None:
    """A file this store did not write is left exactly where it is."""
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    receipt = store.publish(subject, request=write_request())
    path = tmp_path / receipt.relative_path
    store.layout.index_path.unlink()
    path.write_bytes(b'{"schema_version": 1}\n')
    with pytest.raises(RecordConflictError, match="will not overwrite"):
        store.publish(subject, request=write_request())
    assert path.read_bytes() == b'{"schema_version": 1}\n'


def test_an_unindexed_log_line_for_the_same_event_is_never_replaced(
    tmp_path: Path,
) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    receipt = store.publish(subject, request=write_request())
    path = tmp_path / receipt.relative_path
    store.layout.index_path.unlink()
    text = path.read_text(encoding="utf-8").replace('"asserted_by":"owner"', '"asserted_by":"someone"')
    path.write_text(text, encoding="utf-8")
    with pytest.raises(RecordConflictError, match="will not replace"):
        store.publish(subject, request=write_request())


def test_a_forged_index_digest_is_caught_by_verification(tmp_path: Path) -> None:
    """The index is a projection; a hand-edited row is detected, never trusted."""
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    entry = store.index.find(subject.event_id)
    store.index.write_all(
        (_reindexed(entry, content_digest="sha256:" + "0" * 64),)
    )
    result = store.verify()
    assert not result.ok
    assert result.integrity_failures
    assert store.rebuild_index()[0].content_digest == entry.content_digest


def test_a_pruned_decision_window_is_refused_rather_than_published(
    tmp_path: Path,
) -> None:
    """One identity, two contents — the one case a digest comparison would miss.

    A window's id and digest cover its *reference* fields, so pruning the captured
    rows produces different bytes under the same digest. The store refuses it: its
    first rule is that nothing already published is rewritten, and no measured
    trigger for reclaiming that space exists yet.
    """
    store = new_record_store(tmp_path)
    captured = decision_window()
    store.publish(captured, request=write_request())
    pruned = captured.prune(NOW)
    assert pruned.window_id == captured.window_id
    assert pruned.mode is WindowMode.REFERENCE
    with pytest.raises(FrozenRecordError, match="prune"):
        store.publish(pruned, request=write_request())
    assert store.load(captured.window_id) == captured


# --------------------------------------------------------------------------
# Rejections at the write boundary.
# --------------------------------------------------------------------------


def test_a_record_may_not_be_filed_before_the_instant_it_describes(
    tmp_path: Path,
) -> None:
    store = new_record_store(tmp_path)
    subject = trade(occurred_at=AT(10))
    with pytest.raises(PersistenceError, match="has not happened"):
        store.publish(subject, request=write_request(written_at=AT(9)))


def test_a_risk_budget_may_take_effect_in_the_future(tmp_path: Path, budget) -> None:
    """The one exception, and it is the owner scheduling their own limit change."""
    store = new_record_store(tmp_path)
    future = budget(effective_from=NOW + timedelta(days=7))
    assert store.publish(future, request=write_request()).created


def test_a_type_the_store_has_no_spec_for_is_refused(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    with pytest.raises(UnknownRecordKindError, match="not a persisted record type"):
        store.publish(object(), request=write_request())


def test_a_write_request_is_required_and_typed(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    with pytest.raises(TypeError, match="WriteRequest"):
        store.publish(trade(), request="now please")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("author", "", "author"),
        ("reason", "typo", "VersionedTerm"),
        ("version_set", "v1", "VersionSet"),
        ("written_at", NOW.replace(tzinfo=None), "written_at"),
    ],
)
def test_a_write_request_refuses_an_unusable_field(field, value, message) -> None:
    with pytest.raises((TypeError, PersistenceError, Exception), match=message):
        write_request(**{field: value})


def test_a_write_request_refuses_a_non_tuple_provenance() -> None:
    with pytest.raises(TypeError, match="ConsumedSource"):
        write_request(provenance=["not a tuple"])


def test_a_write_request_refuses_a_non_source_in_provenance() -> None:
    with pytest.raises(TypeError, match="ConsumedSource"):
        write_request(provenance=("not a source",))


# --------------------------------------------------------------------------
# Integrity: a byte altered on disk is detected, never decoded.
# --------------------------------------------------------------------------


def test_a_tampered_record_file_is_detected(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    receipt = store.publish(subject, request=write_request())
    path = tmp_path / receipt.relative_path
    payload = canonical_loads(path.read_bytes())
    payload["payload"]["limitations"] = ["a limitation nobody wrote"]
    path.write_bytes(canonical_dumps(payload))
    with pytest.raises(StoreIntegrityError):
        store.load(subject.snapshot_id)


def test_a_tampered_log_line_is_detected(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    receipt = store.publish(subject, request=write_request())
    path = tmp_path / receipt.relative_path
    text = path.read_text(encoding="utf-8").replace('"price":"60000"', '"price":"70000"')
    path.write_text(text, encoding="utf-8")
    with pytest.raises((StoreIntegrityError, PersistenceError)):
        store.load(subject.event_id)


def test_a_re_pointed_index_row_is_refused(tmp_path: Path) -> None:
    """A row whose path does not follow from its own kind and instant."""
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    store.publish(subject, request=write_request())
    entry = store.index.find(subject.snapshot_id)
    store.index.write_all(
        (
            _reindexed(
                entry, relative_path="records/market_snapshot/1999/01/elsewhere.json"
            ),
        )
    )
    with pytest.raises(StoreIntegrityError, match="re-pointed"):
        store.load(subject.snapshot_id)


def test_a_missing_payload_is_reported_as_missing(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    receipt = store.publish(subject, request=write_request())
    (tmp_path / receipt.relative_path).unlink()
    with pytest.raises(RecordMissingError):
        store.load(subject.snapshot_id)


def test_an_unindexed_record_is_not_loadable(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    with pytest.raises(RecordMissingError):
        store.load("trade-x-20260812T100000Z-0123456789abcdef")


def test_a_duplicated_index_line_is_refused_on_read(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request())
    line = store.layout.index_path.read_text(encoding="utf-8")
    store.layout.index_path.write_text(line + line, encoding="utf-8")
    with pytest.raises(StoreIntegrityError, match="repeats record"):
        store.index.entries()


def test_a_path_escaping_the_root_is_refused(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    for candidate in ("/etc/passwd", "../outside.json", "records/../../outside.json"):
        with pytest.raises(StorePathError):
            store.layout.resolve_within_root(candidate)


def test_an_empty_relative_path_is_refused(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    with pytest.raises(StorePathError, match="non-empty"):
        store.layout.resolve_within_root("")


# --------------------------------------------------------------------------
# The envelope.
# --------------------------------------------------------------------------


def test_the_envelope_round_trips_and_rejects_an_unknown_field(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    envelope = store.load_envelope(subject.event_id)
    assert StoredEnvelope.from_payload(envelope.to_payload()) == envelope
    payload = envelope.to_payload()
    payload["surprise"] = 1
    with pytest.raises(Exception, match="unknown field"):
        StoredEnvelope.from_payload(payload)


def test_the_envelope_rejects_an_unsupported_version(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    payload = store.load_envelope(subject.event_id).to_payload()
    payload["schema_version"] = 99
    with pytest.raises(Exception, match="not supported"):
        StoredEnvelope.from_payload(payload)


def test_the_envelope_rejects_a_kind_this_build_does_not_know(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    payload = store.load_envelope(subject.event_id).to_payload()
    payload["kind"] = "quantum_position"
    with pytest.raises(UnknownRecordKindError, match="newer one"):
        StoredEnvelope.from_payload(payload)


def test_written_at_does_not_change_a_record_digest(tmp_path: Path) -> None:
    """The whole of the idempotency claim: filing time is not content."""
    first = new_record_store(tmp_path / "a")
    second = new_record_store(tmp_path / "b")
    subject = trade()
    left = first.publish(subject, request=write_request())
    right = second.publish(subject, request=write_request(written_at=NOW + timedelta(days=5)))
    assert left.content_digest == right.content_digest
    assert left.record_id == right.record_id


# --------------------------------------------------------------------------
# Verification and rebuild.
# --------------------------------------------------------------------------


def test_a_clean_store_verifies(tmp_path: Path, sample_records) -> None:
    store = new_record_store(tmp_path)
    for record in sample_records:
        store.publish(record, request=write_request())
    result = store.verify()
    assert result.ok, result
    assert result.indexed_count == len(sample_records)
    assert result.journal_event_count == len(sample_records)


def test_verification_reports_an_orphan_payload(tmp_path: Path) -> None:
    """A crash between writing the payload and indexing it — detected, not hidden."""
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    store.publish(subject, request=write_request())
    store.layout.index_path.unlink()
    result = store.verify()
    assert not result.ok
    assert subject.snapshot_id in result.orphan_payloads
    assert subject.snapshot_id in result.unindexed_writes


def test_verification_reports_a_missing_payload(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    receipt = store.publish(subject, request=write_request())
    (tmp_path / receipt.relative_path).unlink()
    result = store.verify()
    assert not result.ok
    assert result.missing_payloads == (subject.snapshot_id,)


def test_verification_reports_an_integrity_failure(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    receipt = store.publish(subject, request=write_request())
    path = tmp_path / receipt.relative_path
    payload = canonical_loads(path.read_bytes())
    payload["payload"]["limitations"] = ["altered"]
    path.write_bytes(canonical_dumps(payload))
    result = store.verify()
    assert not result.ok
    assert result.integrity_failures


def test_verify_record_reports_rather_than_raises(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    check = store.verify_record("trade-x-20260812T100000Z-0123456789abcdef")
    assert not check.ok
    assert check.problems and "RecordMissingError" in check.problems[0]


def test_a_healthy_record_verifies(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    assert store.verify_record(subject.event_id).ok


def test_the_index_rebuilds_to_the_identical_rows(tmp_path: Path, sample_records) -> None:
    """The index is the only rebuildable thing in the store, and this proves it."""
    store = new_record_store(tmp_path)
    for record in sample_records:
        store.publish(record, request=write_request())
    before = store.index.entries()
    store.layout.index_path.unlink()
    assert store.index.entries() == ()
    rebuilt = store.rebuild_index()
    assert rebuilt == before
    assert store.index.entries() == before
    assert store.verify().ok


def test_a_rebuild_will_not_index_a_record_with_no_journal_event(
    tmp_path: Path,
) -> None:
    """Inventing a sequence number would forge the audit trail to complete a table."""
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    store.publish(subject, request=write_request())
    for year in store.layout.journal_years():
        (tmp_path / "journal" / f"{year}.jsonl").unlink()
    store.layout.index_path.unlink()
    assert store.rebuild_index() == ()


def test_a_rebuilt_index_survives_a_corrected_trade(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    original = trade()
    store.publish(original, request=write_request())
    replacement = trade(quantity=quantity("0.6"))
    fix = correction(original, replacement)
    store.publish(
        fix, request=write_request(operation=WriteOperation.SUPERSEDE)
    )
    before = store.index.entries()
    store.layout.index_path.unlink()
    assert store.rebuild_index() == before
    assert store.successors() == {original.event_id: fix.event_id}


# --------------------------------------------------------------------------
# Listing and shapes.
# --------------------------------------------------------------------------


def test_entries_filter_by_kind_and_read_no_payload(tmp_path: Path, sample_records) -> None:
    store = new_record_store(tmp_path)
    for record in sample_records:
        store.publish(record, request=write_request())
    for kind in RecordKind:
        rows = store.entries(kind)
        assert all(entry.kind is kind for entry in rows)
    assert len(store.entries()) == len(sample_records)


def test_records_of_one_kind_come_back_in_a_deterministic_order(
    tmp_path: Path,
) -> None:
    store = new_record_store(tmp_path)
    later = trade(occurred_at=AT(11))
    earlier = trade(occurred_at=AT(10))
    store.publish(later, request=write_request())
    store.publish(earlier, request=write_request())
    assert [item.occurred_at for item in store.records(RecordKind.TRADE)] == [
        AT(10),
        AT(11),
    ]


def test_the_two_file_shapes_land_where_the_layout_says(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    receipt = store.publish(subject, request=write_request())
    assert receipt.relative_path.startswith("ledger/trade/")
    assert receipt.relative_path.endswith(".jsonl")
    snapshot = market_snapshot()
    snap_receipt = store.publish(snapshot, request=write_request())
    assert snap_receipt.relative_path.startswith("records/market_snapshot/")
    assert snap_receipt.relative_path.endswith(".json")


def test_asking_for_the_wrong_shape_is_refused(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    with pytest.raises(PersistenceError, match="not stored as an event log"):
        store.log_envelopes(RecordKind.MARKET_SNAPSHOT)
    with pytest.raises(PersistenceError, match="not stored as record files"):
        store.record_envelopes(RecordKind.TRADE)


def test_a_ledger_year_file_holds_one_line_per_event(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    for hour in (10, 11, 12):
        store.publish(trade(occurred_at=AT(hour)), request=write_request())
    path = tmp_path / "ledger" / "trade" / "2026.jsonl"
    assert len(path.read_text(encoding="utf-8").strip().split("\n")) == 3
    assert len(store.log_envelopes(RecordKind.TRADE)) == 3


def test_events_in_two_calendar_years_land_in_two_files(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(occurred_at=AT(10)), request=write_request())
    store.publish(
        trade(occurred_at=AT(10).replace(year=2027)),
        request=write_request(written_at=NOW.replace(year=2027, month=9)),
    )
    assert store.layout.log_years(RecordKind.TRADE) == (2026, 2027)
    assert len(store.log_envelopes(RecordKind.TRADE)) == 2


# --------------------------------------------------------------------------
# The durability classification.
# --------------------------------------------------------------------------


def test_no_persisted_kind_is_classed_as_a_projection() -> None:
    """A projection with a spec would be a projection with a file."""
    for spec in SPECS.values():
        assert spec.durability is not DurabilityClass.REBUILDABLE_PROJECTION
        assert spec.durability is not DurabilityClass.DISPOSABLE_AGGREGATE


def test_only_sources_of_truth_are_stored_as_event_logs() -> None:
    """A captured artifact belongs in a record file — it is reached by id, once."""
    for spec in SPECS.values():
        if spec.shape is StorageShape.EVENT_LOG:
            assert spec.durability is DurabilityClass.SOURCE_OF_TRUTH, spec.kind
