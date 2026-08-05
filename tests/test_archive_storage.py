"""`ArchiveStore`: atomicity, duplicates, verification, and the manifest.

Every test uses `tmp_path` — no test may ever write into the owner's real
archive (design doc §5, ADR-0027 §5).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fmis.archive.envelope import (
    ARCHIVE_SCHEMA_VERSION,
    ArchiveEnvelope,
    RecordType,
    compute_content_digest,
    encode_envelope,
)
from fmis.archive.errors import (
    ArchiveIOError,
    CorruptRecordError,
    DuplicateRecordConflictError,
    IntegrityError,
    InvalidRecordIdError,
    ManifestError,
    RecordNotFoundError,
    UnsupportedSchemaVersionError,
)
from fmis.archive.identity import build_record_id
from fmis.archive.manifest import ManifestEntry, MANIFEST_FILENAME, append_manifest_entry, read_manifest
from fmis.archive.storage import ArchiveStore, _relative_path, default_archive_root
from fmis.daily.models import DailyRun
from fmis.workspace.models import Workspace
from tests.archive_helpers import fixture_daily_run, fixture_workspace


@pytest.fixture
def store(tmp_path: Path) -> ArchiveStore:
    return ArchiveStore(tmp_path / "archive")


# ============ 1. archiving a Workspace / DailyRun ============================


def test_archiving_a_workspace_creates_a_readable_record(store: ArchiveStore) -> None:
    workspace = fixture_workspace()
    record = store.archive_workspace(workspace)
    assert record.created is True
    loaded = store.load(record.record_id)
    assert loaded == workspace
    assert isinstance(loaded, Workspace)


def test_archiving_a_daily_run_creates_a_readable_record(store: ArchiveStore) -> None:
    run = fixture_daily_run()
    record = store.archive_daily_run(run)
    assert record.created is True
    loaded = store.load(record.record_id)
    assert loaded == run
    assert isinstance(loaded, DailyRun)


def test_the_record_file_actually_exists_at_the_relative_path(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    assert (store.root / record.relative_path).is_file()


def test_the_layout_year_and_month_are_taken_in_utc_not_the_original_offset(
    store: ArchiveStore,
) -> None:
    """20:30 on 2026-01-31 in UTC-5 is 2026-02-01 01:30 UTC — a different
    calendar month. The layout must key off the UTC instant (ADR-0027 §5),
    not the offset the caller happened to supply."""
    from datetime import timedelta

    minus5 = timezone(timedelta(hours=-5))
    late_january_local = datetime(2026, 1, 31, 20, 30, tzinfo=minus5)
    workspace = fixture_workspace()
    shifted = Workspace(
        symbol=workspace.symbol,
        objective=workspace.objective,
        as_of=late_january_local,
        source=workspace.source,
        sections=workspace.sections,
        metadata=workspace.metadata,
    )
    record = store.archive_workspace(shifted)
    assert record.relative_path.startswith("workspace/2026/02/")


def test_archiving_publishes_a_manifest_entry(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    entries = store.list()
    assert len(entries) == 1
    assert entries[0].record_id == record.record_id
    assert entries[0].relative_path == record.relative_path
    assert entries[0].content_digest == record.content_digest


def test_archiving_creates_the_root_and_nested_directories(tmp_path: Path) -> None:
    root = tmp_path / "does" / "not" / "exist" / "yet"
    store = ArchiveStore(root)
    store.archive_workspace(fixture_workspace())
    assert root.is_dir()
    assert (root / "workspace").is_dir()


def test_default_archive_root_is_outside_the_repository() -> None:
    assert default_archive_root() == Path.home() / ".fmits" / "archive"


# ============ 2. atomicity ====================================================


def test_a_successful_write_leaves_no_temp_file_behind(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    record_dir = (store.root / record.relative_path).parent
    leftovers = [p for p in record_dir.iterdir() if p.name.startswith(".") and p.suffix == ".tmp"]
    assert leftovers == []


def test_an_interrupted_publish_leaves_no_partial_final_file(
    store: ArchiveStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    real_replace = os.replace

    def failing_replace(src, dst):  # noqa: ANN001
        raise OSError("simulated crash between write and publish")

    monkeypatch.setattr("fmis.archive.atomic.os.replace", failing_replace)
    with pytest.raises(ArchiveIOError):
        store.archive_workspace(fixture_workspace())
    monkeypatch.setattr("fmis.archive.atomic.os.replace", real_replace)

    # No partial final file, and the temp file was cleaned up.
    workspace_dir = store.root / "workspace"
    assert not workspace_dir.exists() or not any(
        p.suffix == ".json" for p in workspace_dir.rglob("*.json")
    )


def test_a_write_failure_raises_archive_io_error_not_a_bare_oserror(
    store: ArchiveStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_mkstemp(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise OSError("disk full")

    monkeypatch.setattr("fmis.archive.atomic.tempfile.mkstemp", failing_mkstemp)
    with pytest.raises(ArchiveIOError):
        store.archive_workspace(fixture_workspace())


# ============ 3. duplicates and conflicts =====================================


def test_archiving_the_same_workspace_twice_is_idempotent(store: ArchiveStore) -> None:
    workspace = fixture_workspace()
    first = store.archive_workspace(workspace)
    second = store.archive_workspace(workspace)
    assert first.record_id == second.record_id
    assert first.content_digest == second.content_digest
    assert second.created is False
    assert len(store.list()) == 1


def test_an_identical_duplicate_does_not_rewrite_the_file(
    store: ArchiveStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = fixture_workspace()
    store.archive_workspace(workspace)

    calls = []
    import fmis.archive.storage as storage_module

    real_atomic_write = storage_module.atomic_write

    def counting_atomic_write(path, data):  # noqa: ANN001
        calls.append(path)
        return real_atomic_write(path, data)

    monkeypatch.setattr(storage_module, "atomic_write", counting_atomic_write)
    store.archive_workspace(workspace)
    assert calls == []  # no record file rewritten; no manifest rewrite either


def test_a_true_conflicting_duplicate_raises_without_overwriting(
    store: ArchiveStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates the astronomically unlikely digest-prefix collision (ADR-0027 §4/§6)
    by hand-placing a *different* envelope at the exact path/record_id a real
    archive call will independently compute — without needing a real SHA-256
    collision."""
    workspace = fixture_workspace()
    payload_a = __import__("fmis.archive.codec", fromlist=["encode_workspace"]).encode_workspace(workspace)
    digest_a = compute_content_digest(
        record_type=RecordType.WORKSPACE,
        schema_version=ARCHIVE_SCHEMA_VERSION,
        analysis_as_of=workspace.as_of,
        subject=(workspace.symbol,),
        payload=payload_a,
    )
    record_id = build_record_id(
        type_slug="workspace", subject=workspace.symbol, analysis_as_of=workspace.as_of, digest=digest_a
    )
    relative = _relative_path(RecordType.WORKSPACE, record_id, workspace.as_of)
    final_path = store.root / relative
    final_path.parent.mkdir(parents=True, exist_ok=True)

    fabricated_digest = "sha256:" + "0" * 64
    fabricated = ArchiveEnvelope(
        record_type=RecordType.WORKSPACE,
        schema_version=ARCHIVE_SCHEMA_VERSION,
        record_id=record_id,
        archived_at=datetime.now(timezone.utc),
        analysis_as_of=workspace.as_of,
        subject=(workspace.symbol,),
        payload={**payload_a, "source": "different-content"},
        content_digest=fabricated_digest,
    )
    final_path.write_bytes(encode_envelope(fabricated))

    with pytest.raises(DuplicateRecordConflictError):
        store.archive_workspace(workspace)

    # The fabricated file is untouched — never silently overwritten.
    assert final_path.read_bytes() == encode_envelope(fabricated)


# ============ 4. loading =======================================================


def test_loading_a_missing_record_raises_not_found(store: ArchiveStore) -> None:
    record_id = build_record_id(
        type_slug="workspace",
        subject="BTCUSDT",
        analysis_as_of=datetime.now(timezone.utc),
        digest="sha256:" + "a" * 64,
    )
    with pytest.raises(RecordNotFoundError):
        store.load(record_id)


@pytest.mark.parametrize(
    "bad_id",
    ["../../etc/passwd", "not-a-record-id", "workspace-BTC/USDT-20260101T000000Z-aaaaaaaaaaaaaaaa"],
)
def test_loading_an_invalid_record_id_is_rejected_before_touching_the_filesystem(
    store: ArchiveStore, bad_id: str
) -> None:
    with pytest.raises(InvalidRecordIdError):
        store.load(bad_id)


def test_loading_corrupt_json_raises_corrupt_record_error(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    path = store.root / record.relative_path
    path.write_bytes(b"{not json")
    with pytest.raises(CorruptRecordError):
        store.load(record.record_id)


def test_loading_a_digest_mismatch_raises_integrity_error(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    path = store.root / record.relative_path
    original = path.read_bytes()
    tampered = original.replace(b'"BTCUSDT"', b'"XTCUSDT"', 1)
    assert tampered != original
    path.write_bytes(tampered)
    with pytest.raises(IntegrityError):
        store.load(record.record_id)


def test_loading_an_unsupported_schema_version_is_rejected(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    path = store.root / record.relative_path
    envelope = json.loads(path.read_text())
    envelope["schema_version"] = 999
    path.write_text(json.dumps(envelope, sort_keys=True, indent=2))
    with pytest.raises(UnsupportedSchemaVersionError):
        store.load(record.record_id)


def test_show_performs_no_network_call(store: ArchiveStore, monkeypatch: pytest.MonkeyPatch) -> None:
    record = store.archive_workspace(fixture_workspace())

    def boom(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("archive.load must never touch the network")

    monkeypatch.setattr("fmis.providers.binance.fetch_klines", boom, raising=False)
    monkeypatch.setattr("urllib.request.urlopen", boom, raising=False)
    loaded = store.load(record.record_id)
    assert loaded is not None


# ============ 5. listing =======================================================


def test_list_returns_every_archived_record(store: ArchiveStore) -> None:
    store.archive_workspace(fixture_workspace(symbol="BTCUSDT"))
    store.archive_workspace(fixture_workspace(symbol="ETHUSDT", seeds=(2, 6, 10)))
    entries = store.list()
    assert len(entries) == 2
    assert {e.subject for e in entries} == {("BTCUSDT",), ("ETHUSDT",)}


def test_list_never_reads_a_record_payload(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    path = store.root / record.relative_path
    path.write_bytes(b"this is not valid JSON at all, but list() must not care")
    entries = store.list()  # must not raise, must not touch the corrupted payload
    assert len(entries) == 1
    assert entries[0].record_id == record.record_id


def test_list_on_an_empty_archive_returns_nothing(store: ArchiveStore) -> None:
    assert store.list() == ()


# ============ 6. verification: single record ==================================


def test_verify_record_ok_for_a_healthy_record(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    result = store.verify_record(record.record_id)
    assert result.ok is True
    assert result.problems == ()


def test_verify_record_reports_a_missing_record(store: ArchiveStore) -> None:
    record_id = build_record_id(
        type_slug="workspace",
        subject="BTCUSDT",
        analysis_as_of=datetime.now(timezone.utc),
        digest="sha256:" + "a" * 64,
    )
    result = store.verify_record(record_id)
    assert result.ok is False
    assert "RecordNotFoundError" in result.problems[0]


def test_verify_record_reports_a_digest_mismatch(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    path = store.root / record.relative_path
    path.write_bytes(path.read_bytes().replace(b'"BTCUSDT"', b'"XTCUSDT"', 1))
    result = store.verify_record(record.record_id)
    assert result.ok is False
    assert "IntegrityError" in result.problems[0]


def test_verify_record_never_raises_for_a_known_problem_category(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    path = store.root / record.relative_path
    path.write_bytes(b"{garbage")
    result = store.verify_record(record.record_id)  # must not raise
    assert result.ok is False


# ============ 7. verification: the whole archive ===============================


def test_verify_archive_ok_when_everything_matches(store: ArchiveStore) -> None:
    store.archive_workspace(fixture_workspace())
    store.archive_daily_run(fixture_daily_run())
    result = store.verify_archive()
    assert result.ok is True
    assert result.missing_files == ()
    assert result.orphan_files == ()
    assert result.duplicate_manifest_entries == ()
    assert result.digest_mismatches == ()


def test_verify_archive_detects_a_missing_file(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    (store.root / record.relative_path).unlink()
    result = store.verify_archive()
    assert result.ok is False
    assert record.record_id in result.missing_files


def test_verify_archive_detects_an_orphan_file(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    orphan_path = (store.root / record.relative_path).with_name("orphan-not-in-manifest.json")
    orphan_path.write_bytes((store.root / record.relative_path).read_bytes())
    result = store.verify_archive()
    assert result.ok is False
    assert any("orphan-not-in-manifest" in p for p in result.orphan_files)


def test_verify_archive_detects_a_digest_mismatch(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    path = store.root / record.relative_path
    path.write_bytes(path.read_bytes().replace(b'"BTCUSDT"', b'"XTCUSDT"', 1))
    result = store.verify_archive()
    assert result.ok is False
    assert record.record_id in result.digest_mismatches


def test_verify_archive_detects_a_duplicate_manifest_entry(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    entries = read_manifest(store.root)
    # Bypass append_manifest_entry's own duplicate rejection to simulate a
    # manifest that was corrupted by something other than this package.
    lines = (store.root / MANIFEST_FILENAME).read_text().splitlines()
    (store.root / MANIFEST_FILENAME).write_text("\n".join([*lines, lines[0]]) + "\n")
    result = store.verify_archive()
    assert result.ok is False
    assert record.record_id in result.duplicate_manifest_entries


def test_verify_archive_rejects_a_manifest_entry_that_escapes_the_root(store: ArchiveStore) -> None:
    store.archive_workspace(fixture_workspace())
    lines = (store.root / MANIFEST_FILENAME).read_text().splitlines()
    entry = json.loads(lines[0])
    entry["relative_path"] = "../../../etc/passwd"
    entry["record_id"] = entry["record_id"]
    (store.root / MANIFEST_FILENAME).write_text(json.dumps(entry, sort_keys=True) + "\n")
    result = store.verify_archive()
    assert result.ok is False
    assert result.missing_files  # treated as missing, never read


def test_verify_archive_never_reads_a_real_file_outside_the_root(store: ArchiveStore) -> None:
    """A stronger version of the test above: a *real, readable* file sits at
    the escaping path. If the defense-in-depth check in `_resolve_within_root`
    were ever disabled, this file would be opened and would fail to decode as
    a valid envelope — landing in `digest_mismatches`, a different outcome
    from the correct one (`missing_files`), which is exactly what this test
    distinguishes."""
    record = store.archive_workspace(fixture_workspace())
    outside_file = store.root.parent / "outside.json"
    outside_file.write_bytes(b"not a valid archive envelope")

    lines = (store.root / MANIFEST_FILENAME).read_text().splitlines()
    entry = json.loads(lines[0])
    entry["relative_path"] = "../outside.json"
    (store.root / MANIFEST_FILENAME).write_text(json.dumps(entry, sort_keys=True) + "\n")

    result = store.verify_archive()
    assert result.ok is False
    assert record.record_id in result.missing_files
    assert record.record_id not in result.digest_mismatches


def test_verify_archive_on_an_empty_archive_is_ok(store: ArchiveStore) -> None:
    result = store.verify_archive()
    assert result.ok is True


def test_verify_archive_surfaces_a_malformed_manifest(store: ArchiveStore) -> None:
    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / MANIFEST_FILENAME).write_text("{not valid json\n")
    result = store.verify_archive()
    assert result.ok is False


# ============ 8. manifest ======================================================


def test_append_manifest_entry_rejects_a_duplicate_record_id(tmp_path: Path) -> None:
    entry = ManifestEntry(
        record_id=build_record_id(
            type_slug="workspace", subject="BTCUSDT",
            analysis_as_of=datetime.now(timezone.utc), digest="sha256:" + "a" * 64,
        ),
        record_type=RecordType.WORKSPACE,
        schema_version=ARCHIVE_SCHEMA_VERSION,
        archived_at=datetime.now(timezone.utc),
        analysis_as_of=datetime.now(timezone.utc),
        subject=("BTCUSDT",),
        relative_path="workspace/2026/01/x.json",
        content_digest="sha256:" + "a" * 64,
    )
    append_manifest_entry(tmp_path, entry)
    with pytest.raises(ManifestError):
        append_manifest_entry(tmp_path, entry)


def test_read_manifest_on_a_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_manifest(tmp_path / "nowhere") == ()


def test_read_manifest_rejects_a_malformed_line(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / MANIFEST_FILENAME).write_text('{"record_id": "missing-other-fields"}\n')
    with pytest.raises(ManifestError):
        read_manifest(tmp_path)


def test_read_manifest_skips_blank_lines(tmp_path: Path) -> None:
    entry = ManifestEntry(
        record_id=build_record_id(
            type_slug="workspace", subject="BTCUSDT",
            analysis_as_of=datetime.now(timezone.utc), digest="sha256:" + "a" * 64,
        ),
        record_type=RecordType.WORKSPACE,
        schema_version=ARCHIVE_SCHEMA_VERSION,
        archived_at=datetime.now(timezone.utc),
        analysis_as_of=datetime.now(timezone.utc),
        subject=("BTCUSDT",),
        relative_path="workspace/2026/01/x.json",
        content_digest="sha256:" + "a" * 64,
    )
    append_manifest_entry(tmp_path, entry)
    existing = (tmp_path / MANIFEST_FILENAME).read_text()
    (tmp_path / MANIFEST_FILENAME).write_text(existing + "\n\n")
    assert len(read_manifest(tmp_path)) == 1


# ============ 9. remaining edges ==============================================


def test_a_corrupt_existing_file_at_the_target_path_is_a_conflict_not_a_duplicate(
    store: ArchiveStore,
) -> None:
    """`_existing_digest` returns `None` for a file it cannot decode, which
    must never be treated as "identical" — only a matching digest is."""
    workspace = fixture_workspace()
    from fmis.archive.codec import encode_workspace

    payload = encode_workspace(workspace)
    digest = compute_content_digest(
        record_type=RecordType.WORKSPACE,
        schema_version=ARCHIVE_SCHEMA_VERSION,
        analysis_as_of=workspace.as_of,
        subject=(workspace.symbol,),
        payload=payload,
    )
    record_id = build_record_id(
        type_slug="workspace", subject=workspace.symbol, analysis_as_of=workspace.as_of, digest=digest
    )
    final_path = store.root / _relative_path(RecordType.WORKSPACE, record_id, workspace.as_of)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(b"not a valid envelope at all")

    with pytest.raises(DuplicateRecordConflictError):
        store.archive_workspace(workspace)


def test_an_identical_duplicate_backfills_a_missing_manifest_entry(store: ArchiveStore) -> None:
    workspace = fixture_workspace()
    record = store.archive_workspace(workspace)
    (store.root / MANIFEST_FILENAME).unlink()
    assert store.list() == ()

    second = store.archive_workspace(workspace)
    assert second.record_id == record.record_id
    assert second.created is False
    entries = store.list()
    assert len(entries) == 1
    assert entries[0].record_id == record.record_id


def test_path_for_continues_past_a_non_matching_manifest_entry(store: ArchiveStore) -> None:
    first = store.archive_workspace(fixture_workspace(symbol="BTCUSDT"))
    second = store.archive_workspace(fixture_workspace(symbol="ETHUSDT", seeds=(2, 6, 10)))
    assert len(store.list()) == 2
    # Looking up the *second* manifest entry forces the lookup loop past a
    # non-matching first entry.
    loaded = store.load(second.record_id)
    assert loaded.symbol == "ETHUSDT"
    assert store.load(first.record_id).symbol == "BTCUSDT"


def test_load_reports_not_found_when_the_manifest_entry_survives_but_the_file_is_gone(
    store: ArchiveStore,
) -> None:
    record = store.archive_workspace(fixture_workspace())
    (store.root / record.relative_path).unlink()
    with pytest.raises(RecordNotFoundError):
        store.load(record.record_id)


def test_load_detects_a_record_id_mismatch_between_manifest_and_file_content(
    store: ArchiveStore,
) -> None:
    record = store.archive_workspace(fixture_workspace())
    manifest_path = store.root / MANIFEST_FILENAME
    entries = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    other_id = build_record_id(
        type_slug="workspace",
        subject="OTHERSY",
        analysis_as_of=datetime.now(timezone.utc),
        digest="sha256:" + "b" * 64,
    )
    entries[0]["record_id"] = other_id
    manifest_path.write_text("\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n")

    with pytest.raises(IntegrityError):
        store.load(other_id)


def test_load_detects_a_record_id_forged_to_match_a_correct_digest(store: ArchiveStore) -> None:
    """Review finding P1-2: the file's own `content_digest` and `payload`
    are left completely untouched — only `record_id` (in both the file and
    the manifest) is swapped for a *different but validly-shaped* id. A
    digest-only check cannot see this, because the digest never changes;
    only recomputing `record_id` from the (still-correct) content and
    comparing catches it."""
    workspace = fixture_workspace()
    record = store.archive_workspace(workspace)
    record_path = store.root / record.relative_path
    envelope = json.loads(record_path.read_text())

    forged_id = build_record_id(
        type_slug="workspace",
        subject="FORGEDXX",
        analysis_as_of=workspace.as_of,
        digest=record.content_digest,
    )
    assert forged_id != record.record_id  # the attack is only interesting if it differs
    envelope["record_id"] = forged_id
    record_path.write_text(json.dumps(envelope, sort_keys=True, indent=2) + "\n")

    manifest_path = store.root / MANIFEST_FILENAME
    manifest_entries = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    manifest_entries[0]["record_id"] = forged_id
    manifest_path.write_text("\n".join(json.dumps(e, sort_keys=True) for e in manifest_entries) + "\n")

    with pytest.raises(IntegrityError, match="does not match the id its own content implies"):
        store.load(forged_id)

    result = store.verify_record(forged_id)
    assert result.ok is False
    assert "does not match the id its own content implies" in result.problems[0]


def test_load_detects_a_corrupted_self_declared_record_id_even_when_content_is_genuine(
    store: ArchiveStore,
) -> None:
    """Isolates the *other* half of the record-id check from the test above.
    Here `content_digest`/`payload`/`subject`/`analysis_as_of` are all
    genuine and still correspond to the *original* record id, and the
    manifest still (correctly) points at it — only the file's own
    self-declared `record_id` field is corrupted to a different, validly-
    shaped value. Recomputing an id from content alone cannot catch this,
    because the recomputed id still equals the correct, looked-up id; only
    comparing the file's own claimed `record_id` against what it was looked
    up by does."""
    workspace = fixture_workspace()
    record = store.archive_workspace(workspace)
    record_path = store.root / record.relative_path
    envelope = json.loads(record_path.read_text())

    corrupted_self_id = build_record_id(
        type_slug="workspace",
        subject="CORRUPTD",
        analysis_as_of=workspace.as_of,
        digest=record.content_digest,
    )
    assert corrupted_self_id != record.record_id
    envelope["record_id"] = corrupted_self_id  # only the file's self-claim changes
    record_path.write_text(json.dumps(envelope, sort_keys=True, indent=2) + "\n")
    # The manifest is untouched — it still correctly names `record.record_id`.

    with pytest.raises(IntegrityError, match="contains a different record_id"):
        store.load(record.record_id)


def test_verify_archive_detects_a_manifest_field_drifted_from_the_record(store: ArchiveStore) -> None:
    """Review finding P1-3: `content_digest` matching proves the *record
    file* is intact; it says nothing about whether the manifest's own
    separately-stored summary of it (here, `context_state`) still agrees —
    `archive list` trusts that field without ever opening the record."""
    record = store.archive_workspace(fixture_workspace())
    manifest_path = store.root / MANIFEST_FILENAME
    entries = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    assert entries[0]["context_state"] == "sufficient"
    entries[0]["context_state"] = "insufficient"
    manifest_path.write_text("\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n")

    result = store.verify_archive()
    assert result.ok is False
    assert record.record_id in result.manifest_mismatches
    assert record.record_id not in result.digest_mismatches  # the record file itself is untouched


def test_verify_archive_detects_a_drifted_manifest_subject(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    manifest_path = store.root / MANIFEST_FILENAME
    entries = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    entries[0]["subject"] = ["SOMEOTHERSYM"]
    manifest_path.write_text("\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n")

    result = store.verify_archive()
    assert result.ok is False
    assert record.record_id in result.manifest_mismatches


def test_verify_archive_detects_a_drifted_daily_run_manifest_summary(store: ArchiveStore) -> None:
    record = store.archive_daily_run(fixture_daily_run(symbols=("BTCUSDT", "ETHUSDT")))
    manifest_path = store.root / MANIFEST_FILENAME
    entries = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    entries[0]["failed_count"] = 99
    manifest_path.write_text("\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n")

    result = store.verify_archive()
    assert result.ok is False
    assert record.record_id in result.manifest_mismatches


def test_resolve_within_root_rejects_an_absolute_relative_path(store: ArchiveStore) -> None:
    with pytest.raises(InvalidRecordIdError, match="must be relative"):
        store._resolve_within_root("/etc/passwd")


def test_verify_archive_treats_undecodable_content_as_a_digest_mismatch(store: ArchiveStore) -> None:
    record = store.archive_workspace(fixture_workspace())
    (store.root / record.relative_path).write_bytes(b"{not json at all")
    result = store.verify_archive()
    assert result.ok is False
    assert record.record_id in result.digest_mismatches


def test_atomic_write_directory_creation_failure_raises_archive_io_error(
    store: ArchiveStore,
) -> None:
    # Block the directory a record needs by placing a plain file where a
    # directory must be created — a filesystem-level failure, no monkeypatch.
    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / "workspace").write_text("I am a file, not a directory")
    with pytest.raises(ArchiveIOError):
        store.archive_workspace(fixture_workspace())
