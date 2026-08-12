"""Append-only files, atomic publication, and what happens when two writers race.

The claim under test is narrow and worth stating exactly: **no code path in this
package can shorten or rewrite a published line file**, and the one path that can
replace one (`RecordIndex.write_all`, the rebuild) is reachable only from
`RecordStore.rebuild_index`, which recomputes it from truth.

Concurrency is deliberately modest. Architecture §24.4 lists concurrency controls
as not built, with the trigger *"more than one writer process exists — today there
is exactly one."* What is built is the lock that stops one writer's own two threads
from interleaving a read-modify-write, and these tests hold it to that and not to
more.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from persistence_helpers import NOW, new_record_store, write_request
from trade_domain_helpers import AT, market_snapshot, quantity, trade

from fmis.persistence import (
    AppendOnlyViolationError,
    StoreIOError,
    StoreLayout,
    append_lines,
    line_count,
    read_lines,
)

# --------------------------------------------------------------------------
# The primitive.
# --------------------------------------------------------------------------


def test_a_missing_file_reads_as_empty(tmp_path: Path) -> None:
    """No event of this kind in this calendar year — emptiness, not an error."""
    assert read_lines(tmp_path / "absent.jsonl") == ()
    assert line_count(tmp_path / "absent.jsonl") == 0


def test_an_empty_file_reads_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_bytes(b"")
    assert read_lines(path) == ()


def test_a_directory_is_not_a_line_file(tmp_path: Path) -> None:
    (tmp_path / "adirectory").mkdir()
    with pytest.raises(StoreIOError, match="not a file"):
        read_lines(tmp_path / "adirectory")


def test_lines_append_and_the_earlier_bytes_never_move(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    append_lines(path, ('{"a":1}',))
    first = path.read_bytes()
    append_lines(path, ('{"b":2}',))
    assert path.read_bytes().startswith(first)
    assert read_lines(path) == ('{"a":1}', '{"b":2}')


def test_appending_nothing_creates_nothing(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    append_lines(path, ())
    assert not path.exists()


def test_a_truncated_tail_is_reported_rather_than_dropped(tmp_path: Path) -> None:
    """The last append did not finish. Completing it is impossible; dropping it
    would be a silent repair of an append-only file."""
    path = tmp_path / "log.jsonl"
    path.write_text('{"a":1}\n{"b":2}', encoding="utf-8")
    with pytest.raises(AppendOnlyViolationError, match="mid-line"):
        read_lines(path)


def test_invalid_utf8_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    path.write_bytes(b"\xff\xfe\n")
    with pytest.raises(AppendOnlyViolationError, match="not valid UTF-8"):
        read_lines(path)


def test_a_line_containing_a_newline_is_refused(tmp_path: Path) -> None:
    with pytest.raises(AppendOnlyViolationError, match="split into two records"):
        append_lines(tmp_path / "log.jsonl", ("one\ntwo",))


def test_lines_must_be_a_tuple_of_str(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="tuple of str"):
        append_lines(tmp_path / "log.jsonl", ["a list"])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="tuple of str"):
        append_lines(tmp_path / "log.jsonl", (1,))  # type: ignore[arg-type]


def test_an_append_computed_against_stale_content_is_refused(tmp_path: Path) -> None:
    """Someone else appended in between; publishing anyway would file against a
    store state that no longer exists."""
    path = tmp_path / "log.jsonl"
    append_lines(path, ('{"a":1}',))
    with pytest.raises(AppendOnlyViolationError, match="computed against"):
        append_lines(path, ('{"b":2}',), expected_existing=0)


def test_an_append_against_current_content_succeeds(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    append_lines(path, ('{"a":1}',), expected_existing=0)
    append_lines(path, ('{"b":2}',), expected_existing=1)
    assert line_count(path) == 2


# --------------------------------------------------------------------------
# The store's use of it.
# --------------------------------------------------------------------------


def test_a_second_write_never_rewrites_the_first_line(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(occurred_at=AT(10)), request=write_request())
    path = tmp_path / "ledger" / "trade" / "2026.jsonl"
    before = path.read_bytes()
    store.publish(trade(occurred_at=AT(11)), request=write_request())
    assert path.read_bytes().startswith(before)


def test_a_record_file_is_published_atomically(tmp_path: Path) -> None:
    """No temporary file survives, and the final path is complete or absent."""
    store = new_record_store(tmp_path)
    subject = market_snapshot()
    receipt = store.publish(subject, request=write_request())
    directory = (tmp_path / receipt.relative_path).parent
    assert [path.name for path in directory.iterdir()] == [
        f"{subject.snapshot_id}.json"
    ]


def test_the_index_only_grows_on_an_ordinary_write(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(occurred_at=AT(10)), request=write_request())
    before = store.layout.index_path.read_bytes()
    store.publish(trade(occurred_at=AT(11)), request=write_request())
    assert store.layout.index_path.read_bytes().startswith(before)


def test_the_journal_only_grows_on_an_ordinary_write(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(occurred_at=AT(10)), request=write_request())
    path = tmp_path / "journal" / "2026.jsonl"
    before = path.read_bytes()
    store.publish(trade(occurred_at=AT(11)), request=write_request())
    assert path.read_bytes().startswith(before)


# --------------------------------------------------------------------------
# Two threads.
# --------------------------------------------------------------------------


def test_concurrent_writes_all_land_and_the_store_still_verifies(
    tmp_path: Path,
) -> None:
    """Eight threads, eight distinct records, one intact index and one intact chain."""
    store = new_record_store(tmp_path)
    subjects = [trade(occurred_at=AT(9 + hour)) for hour in range(8)]
    failures: list[BaseException] = []
    barrier = threading.Barrier(len(subjects))

    def publish(subject) -> None:
        try:
            barrier.wait(timeout=10)
            store.publish(subject, request=write_request())
        except BaseException as error:  # noqa: BLE001 - reported, not swallowed
            failures.append(error)

    threads = [threading.Thread(target=publish, args=(item,)) for item in subjects]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert failures == []
    assert len(store.index.entries()) == len(subjects)
    assert store.journal.verify().ok
    assert store.verify().ok
    assert {entry.record_id for entry in store.index.entries()} == {
        item.event_id for item in subjects
    }


def test_concurrent_writes_of_the_same_record_produce_one_record(
    tmp_path: Path,
) -> None:
    """Content-derived identity plus the writer lock: a race resolves to idempotency."""
    store = new_record_store(tmp_path)
    subject = trade()
    receipts: list[object] = []
    failures: list[BaseException] = []
    barrier = threading.Barrier(4)

    def publish() -> None:
        try:
            barrier.wait(timeout=10)
            receipts.append(store.publish(subject, request=write_request()))
        except BaseException as error:  # noqa: BLE001
            failures.append(error)

    threads = [threading.Thread(target=publish) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert failures == []
    assert len(store.index.entries()) == 1
    assert len(store.journal.events()) == 1
    assert sum(1 for receipt in receipts if receipt.created) == 1  # type: ignore[attr-defined]


def test_the_writer_lock_is_reentrant_across_sequential_uses(tmp_path: Path) -> None:
    layout = StoreLayout(tmp_path)
    with layout.exclusive():
        pass
    with layout.exclusive():
        pass
    assert layout.lock_path.is_file()


def test_the_lock_file_is_not_mistaken_for_a_stored_record(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request())
    assert store.layout.lock_path.is_file()
    assert store.verify().ok
    assert store.layout.lock_path not in store.layout.all_stored_files()


# --------------------------------------------------------------------------
# The layout.
# --------------------------------------------------------------------------


def test_a_layout_requires_a_path() -> None:
    with pytest.raises(TypeError, match="path"):
        StoreLayout(42)  # type: ignore[arg-type]


def test_years_are_read_from_the_directory(tmp_path: Path) -> None:
    from fmis.persistence import RecordKind

    store = new_record_store(tmp_path)
    assert store.layout.journal_years() == ()
    assert store.layout.log_years(RecordKind.TRADE) == ()
    store.publish(trade(), request=write_request())
    assert store.layout.journal_years() == (2026,)
    assert store.layout.log_years(RecordKind.TRADE) == (2026,)


def test_a_non_year_file_in_a_year_directory_is_ignored(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request())
    (tmp_path / "journal" / "notes.txt").write_text("scratch", encoding="utf-8")
    assert store.layout.journal_years() == (2026,)


def test_a_naive_filing_moment_is_refused(tmp_path: Path) -> None:
    layout = StoreLayout(tmp_path)
    with pytest.raises(TypeError, match="timezone-aware"):
        layout.journal_relative_path(NOW.replace(tzinfo=None))
