"""Type guards, decode failures and I/O failures — the paths nothing happy reaches.

Every check in this package that says *"this is not the type I need"* or *"these
bytes are not what they claim"* is exercised here. They are worth testing for the
same reason they are worth writing: each one is the difference between a failure
that names itself and a failure that surfaces three layers away as something else.

The I/O failures are produced by real filesystem conditions where one exists — an
unreadable file, a directory where a file should be — and by substituting the
module's own `os` binding where none does. Neither is a mock of the code under
test; both are a mock of the disk.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pytest
from persistence_helpers import (
    NOW,
    analysis_record,
    journal_entry,
    new_record_store,
    new_store,
    portfolio_snapshot,
    write_request,
)
from trade_domain_helpers import (
    AT,
    correction,
    decision_window,
    market_snapshot,
    proposal,
    quantity,
    reason_tag,
    trade,
    version_set,
)

from fmis.archive.errors import ArchiveIOError
from fmis.archive.json_safe import canonical_dumps, canonical_loads
from fmis.persistence import (
    DEFAULT_STORE_ROOT,
    SPECS,
    AppendOnlyViolationError,
    DurabilityClass,
    IndexEntry,
    JournalEvent,
    LineageError,
    OwnerScope,
    PersistenceError,
    RecordIndex,
    RecordKind,
    RecordMissingError,
    SearchCriteria,
    StorageShape,
    StoreIntegrityError,
    StoreIOError,
    StoreLayout,
    StorePathError,
    StoredEnvelope,
    UnknownRecordKindError,
    VersionEngine,
    WriteOperation,
    WriteSource,
    append_lines,
    default_store_root,
    read_lines,
    spec_for_kind,
)
from fmis.persistence import appendonly as appendonly_module
from fmis.persistence import store as store_module
from fmis.persistence.envelope import decode_line, encode_line
from fmis.provenance import Absent
from fmis.records import PayloadDecodeError

SKIP_AS_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="a permission test is meaningless as root",
)


class _FailingOs:
    """The real `os`, with one call substituted. A mock of the disk, not of the code."""

    def __init__(self, failing: str) -> None:
        self._failing = failing

    def __getattr__(self, name: str):
        if name == self._failing:
            def explode(*_: object, **__: object):
                raise OSError("the disk said no")

            return explode
        return getattr(os, name)


# --------------------------------------------------------------------------
# kinds.py
# --------------------------------------------------------------------------


def test_a_spec_is_reachable_by_kind() -> None:
    assert spec_for_kind(RecordKind.TRADE).type_slug == "trade"
    with pytest.raises(UnknownRecordKindError, match="must be a RecordKind"):
        spec_for_kind("trade")  # type: ignore[arg-type]


def test_an_owner_scope_component_is_a_non_empty_string_or_none() -> None:
    assert OwnerScope().book is None
    for field in ("book", "market", "account"):
        with pytest.raises(TypeError, match=field):
            OwnerScope(**{field: ""})
        with pytest.raises(TypeError, match=field):
            OwnerScope(**{field: 7})


def test_a_subclass_of_a_record_type_is_not_that_record_type() -> None:
    """Its extra fields would be dropped by the parent's encoder, and the
    round-trip claim would be false."""
    from fmis.ledger import Trade
    from fmis.persistence import spec_for_record

    class Embellished(Trade):  # type: ignore[misc]
        pass

    with pytest.raises(UnknownRecordKindError, match="not a persisted record type"):
        spec_for_record.__wrapped__ if False else spec_for_record(
            Embellished.__new__(Embellished)
        )


# --------------------------------------------------------------------------
# layout.py
# --------------------------------------------------------------------------


def test_the_default_root_lives_outside_the_checkout() -> None:
    assert default_store_root() == DEFAULT_STORE_ROOT
    assert DEFAULT_STORE_ROOT.name == "store"
    assert ".fmits" in DEFAULT_STORE_ROOT.parts


def test_a_symlink_out_of_the_root_is_refused(tmp_path: Path) -> None:
    """A path with no `..` in it that still escapes — the case the containment
    check exists for, since the pattern check cannot see it."""
    root = tmp_path / "store"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escape").symlink_to(outside)
    with pytest.raises(StorePathError, match="escapes"):
        StoreLayout(root).resolve_within_root("escape/secret.json")


def test_an_unreadable_year_directory_is_reported(tmp_path: Path, monkeypatch) -> None:
    layout = StoreLayout(tmp_path)
    (tmp_path / "journal").mkdir()
    monkeypatch.setattr(
        "fmis.persistence.layout.os.listdir",
        lambda *_: (_ for _ in ()).throw(OSError("no")),
    )
    with pytest.raises(StoreIOError, match="could not list"):
        layout.journal_years()


def test_an_unwritable_root_is_reported(tmp_path: Path) -> None:
    blocked = tmp_path / "afile"
    blocked.write_text("not a directory", encoding="utf-8")
    layout = StoreLayout(blocked / "store")
    with pytest.raises(StoreIOError, match="could not create the store root"):
        with layout.exclusive():
            pass


@SKIP_AS_ROOT
def test_an_unopenable_lock_is_reported(tmp_path: Path) -> None:
    layout = StoreLayout(tmp_path)
    tmp_path.chmod(0o500)
    try:
        with pytest.raises(StoreIOError, match="writer lock"):
            with layout.exclusive():
                pass
    finally:
        tmp_path.chmod(0o700)


# --------------------------------------------------------------------------
# appendonly.py
# --------------------------------------------------------------------------


@SKIP_AS_ROOT
def test_an_unreadable_line_file_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    path.write_text('{"a":1}\n', encoding="utf-8")
    path.chmod(0o000)
    try:
        with pytest.raises(StoreIOError, match="could not read"):
            read_lines(path)
    finally:
        path.chmod(0o600)


def test_a_directory_where_a_parent_should_be_is_reported(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file", encoding="utf-8")
    with pytest.raises(StoreIOError, match="could not create directory"):
        append_lines(blocker / "nested" / "log.jsonl", ('{"a":1}',))


def test_a_path_that_cannot_be_opened_is_reported(tmp_path: Path) -> None:
    directory = tmp_path / "adirectory"
    directory.mkdir()
    with pytest.raises(StoreIOError, match="could not open"):
        append_lines(directory, ('{"a":1}',))


def test_a_failed_write_is_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(appendonly_module, "os", _FailingOs("write"))
    with pytest.raises(StoreIOError, match="could not append"):
        append_lines(tmp_path / "log.jsonl", ('{"a":1}',))


def test_a_failed_fsync_is_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(appendonly_module, "os", _FailingOs("fsync"))
    with pytest.raises(StoreIOError, match="could not append"):
        append_lines(tmp_path / "log.jsonl", ('{"a":1}',))


# --------------------------------------------------------------------------
# envelope.py
# --------------------------------------------------------------------------


def _valid_envelope() -> StoredEnvelope:
    subject = trade()
    return StoredEnvelope(
        kind=RecordKind.TRADE,
        record_id=subject.event_id,
        payload_schema_version=1,
        occurred_at=subject.occurred_at,
        written_at=NOW,
        content_digest=subject.content_digest,
        payload=subject.to_payload(),
    )


def test_an_envelope_refuses_a_non_kind() -> None:
    with pytest.raises(TypeError, match="RecordKind"):
        StoredEnvelope(
            kind="trade",  # type: ignore[arg-type]
            record_id="x",
            payload_schema_version=1,
            occurred_at=NOW,
            written_at=NOW,
            content_digest="sha256:" + "a" * 64,
            payload={},
        )


def test_an_envelope_refuses_a_malformed_digest() -> None:
    with pytest.raises(StoreIntegrityError, match="sha256"):
        StoredEnvelope(
            kind=RecordKind.TRADE,
            record_id="x",
            payload_schema_version=1,
            occurred_at=NOW,
            written_at=NOW,
            content_digest="md5:whatever",
            payload={},
        )


def test_an_envelope_refuses_a_non_mapping_payload() -> None:
    with pytest.raises(TypeError, match="payload must be a Mapping"):
        StoredEnvelope(
            kind=RecordKind.TRADE,
            record_id="x",
            payload_schema_version=1,
            occurred_at=NOW,
            written_at=NOW,
            content_digest="sha256:" + "a" * 64,
            payload=["not a mapping"],  # type: ignore[arg-type]
        )


def test_an_envelope_refuses_an_unwritable_version() -> None:
    with pytest.raises(StoreIntegrityError, match="not one this build writes"):
        StoredEnvelope(
            kind=RecordKind.TRADE,
            record_id="x",
            payload_schema_version=1,
            occurred_at=NOW,
            written_at=NOW,
            content_digest="sha256:" + "a" * 64,
            payload={},
            schema_version=99,
        )


def test_an_envelope_refuses_a_non_object_payload_on_decode() -> None:
    payload = _valid_envelope().to_payload()
    payload["payload"] = ["not an object"]
    with pytest.raises(PayloadDecodeError, match="must be a JSON object"):
        StoredEnvelope.from_payload(payload)


def test_a_line_must_be_json_safe() -> None:
    with pytest.raises(PayloadDecodeError, match="not JSON-safe"):
        encode_line({"amount": {1, 2}})


def test_a_malformed_line_is_reported_with_its_number() -> None:
    with pytest.raises(StoreIntegrityError, match="line 7 is not valid JSON"):
        decode_line("{not json", line_number=7)


def test_a_line_with_a_duplicate_key_is_reported() -> None:
    with pytest.raises(StoreIntegrityError, match="line 3"):
        decode_line('{"a":1,"a":2}', line_number=3)


def test_a_line_that_is_not_an_object_is_reported() -> None:
    with pytest.raises(StoreIntegrityError, match="not a JSON object"):
        decode_line("[1,2,3]", line_number=1)


# --------------------------------------------------------------------------
# index.py
# --------------------------------------------------------------------------


def _index_entry(**overrides: object) -> IndexEntry:
    values: dict = {
        "record_id": "trade-x-20260812T100000Z-0123456789abcdef",
        "kind": RecordKind.TRADE,
        "durability": DurabilityClass.SOURCE_OF_TRUTH,
        "shape": StorageShape.EVENT_LOG,
        "relative_path": "ledger/trade/2026.jsonl",
        "content_digest": "sha256:" + "a" * 64,
        "payload_schema_version": 1,
        "occurred_at": AT(10),
        "written_at": NOW,
        "lineage_key": "binance:BTCUSDT:spot",
        "book": "swing",
        "market": "binance:BTCUSDT:spot",
        "account": "binance_spot",
        "supersedes": None,
        "journal_sequence": 0,
        "journal_event_id": "journal_event-create-20260820T120000Z-0123456789abcdef",
    }
    values.update(overrides)
    return IndexEntry(**values)  # type: ignore[arg-type]


def test_an_index_entry_refuses_a_non_enum() -> None:
    for field, wrong in (
        ("kind", "trade"),
        ("durability", "source_of_truth"),
        ("shape", "event_log"),
    ):
        with pytest.raises(TypeError, match=field):
            _index_entry(**{field: wrong})


def test_an_index_entry_refuses_a_malformed_digest() -> None:
    with pytest.raises(StoreIntegrityError, match="sha256"):
        _index_entry(content_digest="nope")


def test_an_index_entry_refuses_an_unwritable_version() -> None:
    with pytest.raises(StoreIntegrityError, match="not one this build writes"):
        _index_entry(schema_version=99)


def test_an_index_entry_round_trips_and_reports_its_scope() -> None:
    entry = _index_entry()
    assert IndexEntry.from_payload(entry.to_payload()) == entry
    assert entry.owner_scope == OwnerScope(
        book="swing", market="binance:BTCUSDT:spot", account="binance_spot"
    )
    assert not entry.is_frozen
    assert _index_entry(durability=DurabilityClass.CAPTURED_ARTIFACT).is_frozen


def test_an_index_entry_refuses_an_unknown_enum_member() -> None:
    payload = _index_entry().to_payload()
    payload["durability"] = "immortal"
    with pytest.raises(StoreIntegrityError, match="not a known DurabilityClass"):
        IndexEntry.from_payload(payload)


def test_the_index_requires_a_layout_and_reports_it(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="StoreLayout"):
        RecordIndex(tmp_path)  # type: ignore[arg-type]
    layout = StoreLayout(tmp_path)
    assert RecordIndex(layout).layout is layout


def test_the_index_refuses_a_non_entry(tmp_path: Path) -> None:
    index = RecordIndex(StoreLayout(tmp_path))
    with pytest.raises(TypeError, match="must be an IndexEntry"):
        index.append("a row")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="every entry must be an IndexEntry"):
        index.write_all(("a row",))  # type: ignore[arg-type]


def test_an_unindexed_lookup_is_missing_and_get_says_so(tmp_path: Path) -> None:
    index = RecordIndex(StoreLayout(tmp_path))
    assert index.get("trade-x-20260812T100000Z-0123456789abcdef") is None
    assert not index.contains("trade-x-20260812T100000Z-0123456789abcdef")
    with pytest.raises(RecordMissingError):
        index.find("trade-x-20260812T100000Z-0123456789abcdef")


# --------------------------------------------------------------------------
# journal_engine.py
# --------------------------------------------------------------------------


def _event(**overrides: object) -> JournalEvent:
    values: dict = {
        "sequence": 0,
        "occurred_at": NOW,
        "source": WriteSource.OWNER,
        "author": "owner",
        "reason": reason_tag(),
        "version_set": version_set(),
        "operation": WriteOperation.CREATE,
        "record_kind": RecordKind.TRADE,
        "record_id": "trade-x-20260812T100000Z-0123456789abcdef",
        "content_digest": "sha256:" + "a" * 64,
        "previous_event_id": Absent("first"),
    }
    values.update(overrides)
    return JournalEvent(**values)  # type: ignore[arg-type]


def test_an_event_refuses_an_untagged_reason() -> None:
    with pytest.raises(TypeError, match="cannot be counted"):
        _event(reason="because")


def test_an_event_refuses_a_non_version_set() -> None:
    with pytest.raises(TypeError, match="VersionSet"):
        _event(version_set="v1")


def test_an_event_refuses_a_malformed_digest() -> None:
    with pytest.raises(StoreIntegrityError, match="sha256"):
        _event(content_digest="nope")


def test_an_event_refuses_an_unwritable_version() -> None:
    with pytest.raises(StoreIntegrityError, match="not one this build writes"):
        _event(schema_version=99)


def test_an_event_carries_a_note_and_a_chain_digest() -> None:
    event = _event(note="typed by hand from the exchange page")
    assert event.note == "typed by hand from the exchange page"
    assert event.content_chain_digest.startswith("sha256:")
    assert JournalEvent.from_payload(event.to_payload()) == event


def test_an_event_refuses_an_unknown_enum_member() -> None:
    payload = _event().to_payload()
    payload["source"] = "telepathy"
    with pytest.raises(StoreIntegrityError, match="not a known WriteSource"):
        JournalEvent.from_payload(payload)


def test_removing_the_first_event_is_detected(tmp_path: Path) -> None:
    """The remaining head now names a predecessor that is not there."""
    store = new_record_store(tmp_path)
    for hour in (10, 11):
        store.publish(trade(occurred_at=AT(hour)), request=write_request())
    path = tmp_path / "journal" / "2026.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[1] + "\n", encoding="utf-8")
    problems = store.journal.verify().problems
    assert any("is first but names a predecessor" in problem for problem in problems)


def test_a_repeated_first_event_is_detected(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request())
    path = tmp_path / "journal" / "2026.jsonl"
    line = path.read_text(encoding="utf-8")
    path.write_text(line + line, encoding="utf-8")
    problems = store.journal.verify().problems
    assert any("names no predecessor but is not first" in p for p in problems)


def test_filing_time_moving_backwards_inside_the_file_is_detected(
    tmp_path: Path,
) -> None:
    """`append` cannot produce this. A hand-edited file can, and it is caught."""
    layout = StoreLayout(tmp_path)
    first = _event(occurred_at=NOW + timedelta(hours=1))
    second = _event(
        sequence=1,
        occurred_at=NOW,
        previous_event_id=first.event_id,
        record_id="trade-y-20260812T100000Z-0123456789abcdef",
    )
    append_lines(
        layout.journal_path(NOW),
        (encode_line(first.to_payload()), encode_line(second.to_payload())),
    )
    store = new_record_store(tmp_path)
    problems = store.journal.verify().problems
    assert any("never moves backwards" in problem for problem in problems)


def test_the_engine_reports_its_layout(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    assert store.journal.layout is store.layout


# --------------------------------------------------------------------------
# store.py
# --------------------------------------------------------------------------


def test_a_write_request_carries_a_note(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request(note="entered from the phone"))
    assert store.journal.events()[0].note == "entered from the phone"


def test_republishing_over_a_lost_index_restores_the_row_and_nothing_else(
    tmp_path: Path,
) -> None:
    """A crash between indexing and everything else. Retrying restores the row.

    The record and its journal event are already there, so this is not a new write:
    `created` is false, no second event is appended, and the filing date stays the
    one the record was actually filed on rather than moving to the retry.
    """
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    store.publish(subject, request=write_request())
    store.layout.index_path.unlink()
    receipt = store.publish(
        subject, request=write_request(written_at=NOW + timedelta(hours=1))
    )
    assert not receipt.created
    assert len(store.journal.events()) == 1
    assert store.written_at_of(subject.snapshot_id) == NOW
    assert store.load(subject.snapshot_id) == subject
    assert store.verify().ok


def test_republishing_an_unindexed_log_line_appends_no_second_line(
    tmp_path: Path,
) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    receipt = store.publish(subject, request=write_request())
    store.layout.index_path.unlink()
    again = store.publish(
        subject, request=write_request(written_at=NOW + timedelta(hours=1))
    )
    assert not again.created
    path = tmp_path / receipt.relative_path
    assert len(path.read_text(encoding="utf-8").strip().split("\n")) == 1
    assert store.verify().ok


def test_an_orphan_payload_with_no_journal_event_is_journalled_on_retry(
    tmp_path: Path,
) -> None:
    """The other half of the crash story: the payload landed, nothing else did.

    Here there *is* no audit trail yet, so the retry writes one — and takes the
    filing date from the payload already on disk, because that is when the record
    was actually filed.
    """
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    store.publish(subject, request=write_request())
    store.layout.index_path.unlink()
    for year in store.layout.journal_years():
        (tmp_path / "journal" / f"{year}.jsonl").unlink()
    receipt = store.publish(
        subject, request=write_request(written_at=NOW + timedelta(hours=1))
    )
    assert receipt.created
    assert len(store.journal.events()) == 1
    assert store.written_at_of(subject.snapshot_id) == NOW
    assert store.verify().ok


def test_a_failed_atomic_publish_is_reported(tmp_path: Path, monkeypatch) -> None:
    store = new_record_store(tmp_path)

    def explode(*_: object, **__: object) -> None:
        raise ArchiveIOError("the disk said no")

    monkeypatch.setattr(store_module, "atomic_write", explode)
    with pytest.raises(StoreIOError, match="could not publish"):
        store.publish(market_snapshot(), request=write_request())


def test_a_payload_naming_a_different_record_is_detected(tmp_path: Path) -> None:
    """The envelope says one id, the index says another — a misfiled record."""
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    receipt = store.publish(subject, request=write_request())
    path = tmp_path / receipt.relative_path
    payload = canonical_loads(path.read_bytes())
    payload["record_id"] = "market_snapshot-x-20260812T090000Z-0123456789abcdef"
    path.write_bytes(canonical_dumps(payload))
    with pytest.raises(StoreIntegrityError, match="names itself"):
        store.load(subject.snapshot_id)


def test_a_decoded_record_disagreeing_with_its_own_id_is_detected(
    tmp_path: Path,
) -> None:
    """An analysis citation carries the archive's id inside its payload, so the two
    can be made to disagree — which is exactly what the second check is for."""
    store = new_record_store(tmp_path)
    citation = analysis_record()
    receipt = store.publish(citation, request=write_request())
    path = tmp_path / receipt.relative_path
    payload = canonical_loads(path.read_bytes())
    payload["payload"]["record_id"] = "workspace-ETHUSDT-20260812T090000Z-abcdef0123456789"
    path.write_bytes(canonical_dumps(payload))
    with pytest.raises(StoreIntegrityError, match="whose own id is"):
        store.load(citation.record_id)


def test_a_decoded_record_disagreeing_with_its_own_digest_is_detected(
    tmp_path: Path,
) -> None:
    store = new_record_store(tmp_path)
    citation = analysis_record()
    receipt = store.publish(citation, request=write_request())
    path = tmp_path / receipt.relative_path
    payload = canonical_loads(path.read_bytes())
    payload["payload"]["content_digest"] = "sha256:" + "e" * 64
    path.write_bytes(canonical_dumps(payload))
    with pytest.raises(StoreIntegrityError, match="decodes to content digesting to"):
        store.load(citation.record_id)


def test_an_envelope_digest_disagreeing_with_the_index_is_detected(
    tmp_path: Path,
) -> None:
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    receipt = store.publish(subject, request=write_request())
    path = tmp_path / receipt.relative_path
    payload = canonical_loads(path.read_bytes())
    payload["content_digest"] = "sha256:" + "e" * 64
    path.write_bytes(canonical_dumps(payload))
    with pytest.raises(StoreIntegrityError, match="the index says"):
        store.load(subject.snapshot_id)


@SKIP_AS_ROOT
def test_an_unreadable_record_file_is_reported(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    receipt = store.publish(subject, request=write_request())
    path = tmp_path / receipt.relative_path
    path.chmod(0o000)
    try:
        with pytest.raises(StoreIOError, match="could not read"):
            store.load(subject.snapshot_id)
    finally:
        path.chmod(0o600)


@SKIP_AS_ROOT
def test_an_unreadable_record_file_blocks_a_republish_as_io_not_conflict(
    tmp_path: Path,
) -> None:
    """"We could not read it" is not "it holds something else"."""
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    receipt = store.publish(subject, request=write_request())
    store.layout.index_path.unlink()
    path = tmp_path / receipt.relative_path
    path.chmod(0o000)
    try:
        with pytest.raises(StoreIOError, match="could not read"):
            store.publish(
                subject, request=write_request(written_at=NOW + timedelta(hours=1))
            )
    finally:
        path.chmod(0o600)


def test_an_indexed_event_missing_from_its_year_file_is_reported(
    tmp_path: Path,
) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    receipt = store.publish(subject, request=write_request())
    (tmp_path / receipt.relative_path).write_text("", encoding="utf-8")
    with pytest.raises(RecordMissingError, match="no line in"):
        store.load(subject.event_id)


def test_verification_survives_an_unreadable_index(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request())
    store.layout.index_path.write_text("{not json\n", encoding="utf-8")
    result = store.verify()
    assert not result.ok
    assert any("index unreadable" in problem for problem in result.integrity_failures)


def test_verification_survives_an_unreadable_payload_sweep(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    receipt = store.publish(market_snapshot(), request=write_request())
    (tmp_path / receipt.relative_path).write_text("{not json", encoding="utf-8")
    result = store.verify()
    assert not result.ok
    assert result.integrity_failures


def test_the_filing_instant_of_a_record_is_readable(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    assert store.written_at_of(subject.event_id) == NOW


def test_a_store_level_error_during_decode_is_not_relabelled(
    tmp_path: Path, monkeypatch
) -> None:
    """A `PersistenceError` raised while decoding stays itself, rather than being
    reported as a payload that does not decode."""
    from dataclasses import replace

    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())

    def explode(_: object) -> object:
        raise PersistenceError("a store-level failure")

    patched = dict(SPECS)
    patched[RecordKind.TRADE] = replace(patched[RecordKind.TRADE], decode=explode)
    monkeypatch.setattr(store_module, "SPECS", patched)
    with pytest.raises(PersistenceError, match="a store-level failure"):
        store.load(subject.event_id)


# --------------------------------------------------------------------------
# lineage.py
# --------------------------------------------------------------------------


def test_the_engine_reports_its_store(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    assert VersionEngine(store).store is store


def test_the_engine_loads_an_exact_version(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    assert VersionEngine(store).load(subject.event_id) == subject


def test_a_backwards_loop_in_the_chain_is_refused(tmp_path: Path, monkeypatch) -> None:
    """Unreachable while ids are digests, and refused rather than walked forever."""
    store = new_record_store(tmp_path)
    first = trade(occurred_at=AT(10))
    second = trade(occurred_at=AT(11))
    store.publish(first, request=write_request())
    store.publish(second, request=write_request())
    monkeypatch.setattr(
        type(store),
        "successors",
        lambda _: {first.event_id: second.event_id, second.event_id: first.event_id},
    )
    with pytest.raises(LineageError, match="loops back"):
        VersionEngine(store).lineage(first.event_id)


def test_a_forward_loop_in_the_chain_is_refused(tmp_path: Path, monkeypatch) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    monkeypatch.setattr(
        type(store), "successors", lambda _: {subject.event_id: subject.event_id}
    )
    with pytest.raises(LineageError, match="loops back"):
        VersionEngine(store).lineage(subject.event_id)


def test_a_chain_naming_a_record_the_store_lacks_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    missing = "correction-x-20260812T110000Z-0123456789abcdef"
    monkeypatch.setattr(
        type(store), "successors", lambda _: {subject.event_id: missing}
    )
    with pytest.raises(LineageError, match="does not hold"):
        VersionEngine(store).lineage(subject.event_id)


# --------------------------------------------------------------------------
# criteria.py and base.py
# --------------------------------------------------------------------------


def test_criteria_reject_a_non_bool_supersession_filter() -> None:
    with pytest.raises(TypeError, match="bool or None"):
        SearchCriteria(superseded="maybe")  # type: ignore[arg-type]


def test_criteria_reject_kinds_that_are_not_a_tuple() -> None:
    with pytest.raises(TypeError, match="tuple of RecordKind"):
        SearchCriteria(kinds=[RecordKind.TRADE])  # type: ignore[arg-type]


def test_criteria_filter_on_the_upper_end_of_the_occurrence_axis(
    tmp_path: Path,
) -> None:
    store = new_store(tmp_path)
    store.trades.create(trade(occurred_at=AT(11)), request=write_request())
    assert store.trades.search(SearchCriteria(until=AT(10))) == ()
    assert len(store.trades.search(SearchCriteria(until=AT(12)))) == 1


def test_a_terminal_proposal_is_left_out_of_the_live_set(tmp_path: Path) -> None:
    """The loop has to skip something for `live_proposals` to mean anything."""
    from fmis.proposal import LifecycleKind
    from trade_domain_helpers import lifecycle_event

    store = new_store(tmp_path)
    live = proposal()
    store.opportunities.create(live, request=write_request())
    done = proposal(created_at=AT(10))
    store.opportunities.create(done, request=write_request())
    store.opportunities.append_event(
        lifecycle_event(done, LifecycleKind.INVALIDATION_REACHED, 11),
        request=write_request(),
    )
    found = store.opportunities.live_proposals()
    assert [item[0] for item in found] == [live]


def test_a_trade_repository_refuses_an_id_belonging_to_another_kind(
    tmp_path: Path,
) -> None:
    store = new_store(tmp_path)
    subject = market_snapshot()
    store.snapshots.create(subject, request=write_request())
    with pytest.raises(PersistenceError, match="not a trade"):
        store.trades.load_latest(subject.snapshot_id)


def test_a_forward_only_loop_in_the_chain_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    """A chain whose walk backwards terminates and whose walk forwards does not."""
    store = new_record_store(tmp_path)
    first = trade(occurred_at=AT(10))
    second = trade(occurred_at=AT(11))
    store.publish(first, request=write_request())
    store.publish(second, request=write_request())
    monkeypatch.setattr(
        type(store),
        "successors",
        lambda _: {first.event_id: second.event_id, second.event_id: second.event_id},
    )
    with pytest.raises(LineageError, match="loops back"):
        VersionEngine(store).lineage(first.event_id)


def test_a_series_lookup_after_every_member_returns_the_last(tmp_path: Path) -> None:
    """The loop exhausts rather than breaking — the ordinary "latest so far" case."""
    store = new_record_store(tmp_path)
    for filed, hour in enumerate((9, 10)):
        store.publish(
            portfolio_snapshot(as_of=AT(hour)),
            request=write_request(written_at=NOW + timedelta(hours=filed)),
        )
    chosen = VersionEngine(store).series_at(
        RecordKind.PORTFOLIO_SNAPSHOT, "main", AT(23)
    )
    assert chosen is not None and chosen.occurred_at == AT(10)


def test_a_journal_event_lookup_scans_past_other_records(tmp_path: Path) -> None:
    """The orphan-retry path finds the right event among several."""
    store = new_record_store(tmp_path)
    store.publish(trade(occurred_at=AT(10)), request=write_request())
    subject = market_snapshot()
    store.publish(subject, request=write_request())
    store.layout.index_path.unlink()
    receipt = store.publish(
        subject, request=write_request(written_at=NOW + timedelta(hours=1))
    )
    assert not receipt.created
    assert receipt.journal_event.record_id == subject.snapshot_id


def test_verification_reports_no_journalled_set_when_the_chain_is_broken(
    tmp_path: Path,
) -> None:
    """A store cannot be told what is unjournalled when the journal itself is not
    readable — reporting a guess there would be worse than reporting nothing."""
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request())
    path = tmp_path / "journal" / "2026.jsonl"
    path.write_text(
        path.read_text(encoding="utf-8").replace('"author":"owner"', '"author":"nobody"'),
        encoding="utf-8",
    )
    result = store.verify()
    assert not result.ok
    assert result.journal_problems
    assert result.unjournalled_records == ()


def test_criteria_filter_on_the_known_at_axis_in_both_directions(
    tmp_path: Path,
) -> None:
    store = new_store(tmp_path)
    store.trades.create(trade(), request=write_request())
    assert store.trades.search(SearchCriteria(known_since=NOW + timedelta(days=1))) == ()
    assert store.trades.search(SearchCriteria(known_until=NOW - timedelta(days=1))) == ()


def test_a_repository_requires_a_store() -> None:
    from fmis.persistence import TradeRepository

    with pytest.raises(TypeError, match="RecordStore"):
        TradeRepository("/tmp")  # type: ignore[arg-type]


def test_a_repository_exposes_its_version_engine_and_lineage(tmp_path: Path) -> None:
    store = new_store(tmp_path)
    subject = trade()
    store.trades.create(subject, request=write_request())
    assert isinstance(store.trades.versions, VersionEngine)
    assert store.trades.lineage(subject.event_id).length == 1
    assert store.trades.at(subject.event_id, NOW) == subject
    assert store.trades.primary_kind is RecordKind.TRADE


def test_a_position_repository_reports_its_policy(tmp_path: Path) -> None:
    from trade_domain_helpers import dust_policy

    store = new_store(tmp_path)
    assert store.positions.dust == dust_policy()
    assert store.positions.calculation_version


# --------------------------------------------------------------------------
# The repositories' remaining type guards.
# --------------------------------------------------------------------------


def test_a_correction_must_be_a_correction(tmp_path: Path) -> None:
    store = new_store(tmp_path)
    subject = trade()
    store.trades.create(subject, request=write_request())
    with pytest.raises(TypeError, match="must be a Correction"):
        store.trades.replace(
            subject.event_id, correction="fix it", request=write_request()
        )


def test_a_superseding_entry_must_be_an_entry(tmp_path: Path) -> None:
    store = new_store(tmp_path)
    first = journal_entry()
    store.journals.create(first, request=write_request())
    with pytest.raises(TypeError, match="must be a JournalEntry"):
        store.journals.replace(first.entry_id, "a new note", request=write_request())


def test_a_superseding_event_must_be_an_event(tmp_path: Path) -> None:
    store = new_store(tmp_path)
    subject = proposal()
    store.opportunities.create(subject, request=write_request())
    from fmis.proposal import LifecycleKind
    from trade_domain_helpers import lifecycle_event

    event = lifecycle_event(subject, LifecycleKind.REAFFIRMED, 11)
    store.opportunities.append_event(event, request=write_request())
    with pytest.raises(TypeError, match="ProposalLifecycleEvent"):
        store.opportunities.replace(
            event.event_id, "a better event", request=write_request()
        )


def test_snapshots_can_be_read_for_one_market_and_kind(tmp_path: Path) -> None:
    store = new_store(tmp_path)
    from trade_domain_helpers import MARKET

    window = decision_window()
    store.snapshots.create(window, request=write_request())
    assert store.snapshots.for_market(
        MARKET.value, kind=RecordKind.DECISION_WINDOW
    ) == (window,)


def test_portfolio_snapshots_can_be_read_without_narrowing(tmp_path: Path) -> None:
    store = new_store(tmp_path)
    subject = portfolio_snapshot()
    store.portfolios.create(subject, request=write_request())
    assert store.portfolios.snapshots() == (subject,)
