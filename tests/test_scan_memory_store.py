"""Persistence: the codec, the store, and every way both are asked to fail.

**The claim these tests defend.** Scan memory survives the process. Not the
object, not the cache — the process. A store is built, a scan is recorded, the
store object is thrown away, a *new* one is built over the same directory, and
the baseline is still there. If history only worked while a Python object stayed
alive, Slice 3 would not have shipped anything.

**And the failures are first-class.** Corrupt bytes, a truncated file, a future
schema and a read-only directory each have a named outcome, and in none of them
does the current market analysis become untrue.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from fmis.scan_memory import (
    DEFAULT_RETAINED_SCANS,
    DEFAULT_SCAN_MEMORY_ROOT,
    ComparisonStatus,
    ScanHistoryFormatError,
    ScanHistoryIOError,
    ScanHistoryStore,
    ScanMemoryError,
    compare_and_record,
    decode_scan,
    encode_scan,
)

from tests.scan_memory_helpers import AT, LATER, record, state, store_at


# ---------------------------------------------------------------------------
# The codec
# ---------------------------------------------------------------------------


def test_a_record_survives_a_round_trip_by_value() -> None:
    original = record(state("AAAUSDT"), state("BBBUSDT", state="candidate", direction="sideA"))
    assert decode_scan(encode_scan(original)) == original


def test_encoding_is_canonical_so_the_same_record_is_the_same_bytes() -> None:
    original = record(state())
    assert encode_scan(original) == encode_scan(original)


def test_every_stored_field_survives_the_round_trip() -> None:
    """Field by field, so a field added to the model and forgotten in the codec
    fails here rather than silently defaulting on the next restart."""
    original = record(
        state(
            "AAAUSDT",
            state="candidate",
            direction="sideA",
            developing_state="direction_stated",
            developing_lean="sideA",
            blocker_kind="awaiting_confirmation",
            blocker_observed="no confirming close",
            structural_trends=(("context", "trending"), ("setup", None)),
            independence_established=True,
            evidence_available=False,
            supporting=3,
            conflicting=2,
            missing=1,
            unavailable=4,
        )
    )
    restored = decode_scan(encode_scan(original))
    for name in type(original.symbols[0]).__slots__:
        assert getattr(restored.symbols[0], name) == getattr(original.symbols[0], name), name
    assert restored.identity == original.identity
    assert restored.recorded_at == original.recorded_at


def test_bytes_that_are_not_json_are_refused() -> None:
    with pytest.raises(ScanHistoryFormatError, match="not readable JSON"):
        decode_scan(b"{not json at all")


def test_a_truncated_record_is_refused() -> None:
    data = encode_scan(record(state()))
    with pytest.raises(ScanHistoryFormatError):
        decode_scan(data[: len(data) // 2])


def test_a_future_schema_is_refused_rather_than_reinterpreted() -> None:
    """§25. *"Do not silently reinterpret old persisted fields under new
    semantics"* — and the same in the other direction."""
    payload = json.loads(encode_scan(record(state())))
    payload["schema_version"] = 99
    with pytest.raises(ScanHistoryFormatError, match="schema 99"):
        decode_scan(json.dumps(payload).encode("utf-8"))


def test_a_missing_field_is_refused() -> None:
    payload = json.loads(encode_scan(record(state())))
    del payload["symbols"][0]["blocker_kind"]
    with pytest.raises(ScanHistoryFormatError, match="blocker_kind"):
        decode_scan(json.dumps(payload).encode("utf-8"))


def test_a_field_of_the_wrong_type_is_refused() -> None:
    payload = json.loads(encode_scan(record(state())))
    payload["symbols"][0]["supporting"] = "many"
    with pytest.raises(ScanHistoryFormatError, match="supporting"):
        decode_scan(json.dumps(payload).encode("utf-8"))


def test_a_naive_instant_in_stored_bytes_is_refused() -> None:
    payload = json.loads(encode_scan(record(state())))
    payload["recorded_at"] = "2026-08-24T12:00:00"
    with pytest.raises(ScanHistoryFormatError, match="no timezone"):
        decode_scan(json.dumps(payload).encode("utf-8"))


def test_bytes_describing_a_record_the_domain_refuses_are_a_format_failure() -> None:
    payload = json.loads(encode_scan(record(state("AAAUSDT"))))
    payload["unreadable"] = ["AAAUSDT"]
    with pytest.raises(ScanHistoryFormatError, match="invalid record"):
        decode_scan(json.dumps(payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


def test_the_default_root_is_outside_the_repository(tmp_path) -> None:
    """§26. Runtime history is never committed, and needs no ignore rule because
    it is not inside the checkout at all."""
    import fmis

    checkout = __import__("pathlib").Path(fmis.__file__).resolve().parents[2]
    assert checkout not in DEFAULT_SCAN_MEMORY_ROOT.resolve().parents
    assert DEFAULT_SCAN_MEMORY_ROOT.name == "scan_memory"


def test_the_store_never_falls_back_to_the_owners_history() -> None:
    with pytest.raises(TypeError):
        ScanHistoryStore()  # type: ignore[call-arg]


def test_a_store_that_keeps_one_record_is_refused(tmp_path) -> None:
    with pytest.raises(ScanMemoryError, match="at least 2"):
        store_at(tmp_path, retain=1)


def test_an_empty_store_has_no_baseline(tmp_path) -> None:
    assert store_at(tmp_path).latest_complete() is None


def test_a_recorded_scan_is_read_back(tmp_path) -> None:
    store = store_at(tmp_path)
    original = record(state())
    store.append(original)
    assert store.latest_complete() == original


def test_history_survives_the_store_object_being_thrown_away(tmp_path) -> None:
    """**§27, the acceptance requirement.** Two store objects, one directory."""
    root = tmp_path / "scan_memory"
    first = record(state("AAAUSDT"), reference_time=AT)
    ScanHistoryStore(root).append(first)
    del first
    reopened = ScanHistoryStore(root)
    baseline = reopened.latest_complete()
    assert baseline is not None and baseline.identity.reference_time == AT


def test_a_second_scan_compares_against_the_first_across_two_store_objects(tmp_path) -> None:
    """The whole restart-continuity claim, end to end and offline."""
    root = tmp_path / "scan_memory"
    compare_and_record(record(state("AAAUSDT"), reference_time=AT), store=ScanHistoryStore(root))
    comparison = compare_and_record(
        record(state("AAAUSDT", state="candidate", direction="sideA"), reference_time=LATER),
        store=ScanHistoryStore(root),
    )
    assert comparison.status is ComparisonStatus.COMPARED
    assert comparison.previous_scan_at == AT
    assert comparison.changed_count == 1


def test_the_newest_complete_scan_is_the_baseline(tmp_path) -> None:
    store = store_at(tmp_path)
    for index, moment in enumerate((AT, LATER)):
        store.append(record(state(), reference_time=moment, recorded_at=moment))
    baseline = store.latest_complete()
    assert baseline is not None and baseline.identity.reference_time == LATER


def test_an_incomplete_scan_never_becomes_the_baseline(tmp_path) -> None:
    """**§20.** A provider outage is recorded honestly and skipped as a baseline."""
    store = store_at(tmp_path)
    store.append(record(state("AAAUSDT"), state("BBBUSDT"), reference_time=AT, recorded_at=AT))
    store.append(
        record(
            state("AAAUSDT"),
            universe=("AAAUSDT", "BBBUSDT"),
            reference_time=LATER,
            recorded_at=LATER,
        )
    )
    baseline = store.latest_complete()
    assert baseline is not None
    assert baseline.identity.reference_time == AT
    assert len(store.records()) == 2, "the partial scan is still recorded, honestly"


def test_recording_the_same_completed_scan_twice_creates_one_record(tmp_path) -> None:
    """**§23.** The path is a pure function of the scan's identity."""
    store = store_at(tmp_path)
    original = record(state())
    store.append(original)
    store.append(original)
    assert len(store.records()) == 1


def test_a_scan_is_never_compared_with_a_stored_copy_of_itself(tmp_path) -> None:
    """No `A → A` history from a re-recorded observation."""
    store = store_at(tmp_path)
    original = record(state())
    assert compare_and_record(original, store=store).status is ComparisonStatus.NO_PREVIOUS_SCAN
    again = compare_and_record(original, store=store)
    assert again.status is ComparisonStatus.NO_PREVIOUS_SCAN
    assert again.changes == ()


# ---------------------------------------------------------------------------
# Atomicity, retention and failure
# ---------------------------------------------------------------------------


def test_an_interrupted_write_leaves_no_readable_record(tmp_path) -> None:
    """**§21.** A partial file is never a `*.json`, so no reader can see one."""
    store = store_at(tmp_path)
    store.append(record(state()))
    directory = store.scans_directory
    (directory / ".ghost.json.tmp").write_bytes(b'{"schema_version": 1, "trunc')
    assert len(store.records()) == 1
    assert store.latest_complete() is not None


def test_a_dot_prefixed_file_is_never_read(tmp_path) -> None:
    store = store_at(tmp_path)
    store.scans_directory.mkdir(parents=True)
    (store.scans_directory / ".half.json").write_bytes(b"{")
    assert store.records() == ()


def test_retention_keeps_the_newest_and_prunes_the_rest(tmp_path) -> None:
    """§24. Deterministic, and bounded — never a historical warehouse."""
    store = store_at(tmp_path, retain=3)
    moments = [AT.replace(hour=hour) for hour in range(1, 8)]
    for moment in moments:
        store.append(record(state(), reference_time=moment, recorded_at=moment))
    kept = [stored.record.identity.reference_time for stored in store.records()]
    assert kept == sorted(moments, reverse=True)[:3]


def test_the_default_retention_is_bounded_and_small() -> None:
    assert 2 <= DEFAULT_RETAINED_SCANS <= 32


def test_a_corrupt_newest_record_makes_history_unavailable_not_wrong(tmp_path) -> None:
    """**§25.** Skipping to an older record would silently redefine *the
    previous scan* as *some earlier scan*, over a gap nobody was told about."""
    store = store_at(tmp_path)
    store.append(record(state(), reference_time=AT, recorded_at=AT))
    newest = store.append(record(state(), reference_time=LATER, recorded_at=LATER))
    newest.path.write_bytes(b"corrupted by something outside this process")
    with pytest.raises(ScanHistoryFormatError):
        store.latest_complete()


def test_a_corrupt_history_never_breaks_the_current_scan(tmp_path) -> None:
    """The whole point of §25: the market analysis is untouched."""
    store = store_at(tmp_path)
    stored = store.append(record(state(), reference_time=AT, recorded_at=AT))
    stored.path.write_bytes(b"not a record")
    comparison = compare_and_record(
        record(state(), reference_time=LATER, recorded_at=LATER), store=store
    )
    assert comparison.status is ComparisonStatus.HISTORY_UNAVAILABLE
    assert comparison.changes == () and comparison.unchanged == ()
    assert "could not be read" in comparison.reason
    assert comparison.recorded, "the current scan is still remembered"


def test_a_history_write_failure_is_stated_and_never_hidden(tmp_path) -> None:
    """§20's last clause. The analysis is true; only the remembering failed."""

    class Refusing(ScanHistoryStore):
        def append(self, record_):  # noqa: ANN001
            raise ScanHistoryIOError("the disk is full")

    comparison = compare_and_record(record(state()), store=Refusing(tmp_path / "h"))
    assert not comparison.recorded
    assert "was not recorded" in comparison.recording_note
    assert comparison.status is ComparisonStatus.NO_PREVIOUS_SCAN
    assert "Baseline scan recorded" not in comparison.reason


def test_a_recorded_incomplete_scan_says_it_is_not_a_baseline(tmp_path) -> None:
    comparison = compare_and_record(
        record(state("AAAUSDT"), universe=("AAAUSDT", "BBBUSDT")), store=store_at(tmp_path)
    )
    assert comparison.recorded
    assert "not used as a baseline" in comparison.recording_note


def test_appending_something_that_is_not_a_record_is_refused(tmp_path) -> None:
    with pytest.raises(ScanMemoryError, match="must be a ScanRecord"):
        store_at(tmp_path).append({"symbol": "AAAUSDT"})  # type: ignore[arg-type]


def test_nothing_but_market_analysis_state_reaches_the_bytes() -> None:
    """§49. No key, token, header or credential can be in a record, because no
    field of the model could hold one — asserted over the encoded payload."""
    payload = json.loads(encode_scan(record(state())))
    text = json.dumps(payload).lower()
    for secret in ("api", "key", "token", "secret", "auth", "password", "wallet"):
        assert secret not in text, secret


def test_two_stores_over_one_directory_see_one_history(tmp_path) -> None:
    """§22. Names are unique per scan identity, so two writers cannot collide on
    one file and neither can produce a half record."""
    root = tmp_path / "scan_memory"
    one, two = ScanHistoryStore(root), ScanHistoryStore(root)
    one.append(record(state(), reference_time=AT, recorded_at=AT))
    two.append(record(state(), reference_time=LATER, recorded_at=LATER))
    assert len(one.records()) == len(two.records()) == 2


def test_a_record_is_not_mutated_by_being_stored(tmp_path) -> None:
    original = record(state())
    before = repr(original)
    store_at(tmp_path).append(original)
    assert repr(original) == before
    assert original == replace(original)
