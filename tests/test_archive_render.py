"""Direct tests for `archive list`/`archive verify`'s plain-text rendering."""

from __future__ import annotations

from datetime import datetime, timezone

from fmis.archive.envelope import ARCHIVE_SCHEMA_VERSION, RecordType
from fmis.archive.identity import build_record_id
from fmis.archive.manifest import ManifestEntry
from fmis.archive.render import (
    render_archive_verification,
    render_manifest,
    render_record_verification,
)
from fmis.archive.storage import ArchiveVerification, RecordVerification

_AS_OF = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
_DIGEST = "sha256:" + "a" * 64


def _workspace_entry(**overrides: object) -> ManifestEntry:
    kwargs = dict(
        record_id=build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of=_AS_OF, digest=_DIGEST),
        record_type=RecordType.WORKSPACE,
        schema_version=ARCHIVE_SCHEMA_VERSION,
        archived_at=_AS_OF,
        analysis_as_of=_AS_OF,
        subject=("BTCUSDT",),
        relative_path="workspace/2026/08/x.json",
        content_digest=_DIGEST,
        context_state="sufficient",
    )
    kwargs.update(overrides)
    return ManifestEntry(**kwargs)


def _daily_entry(**overrides: object) -> ManifestEntry:
    kwargs = dict(
        record_id=build_record_id(type_slug="daily", subject="2sym", analysis_as_of=_AS_OF, digest=_DIGEST),
        record_type=RecordType.DAILY_RUN,
        schema_version=ARCHIVE_SCHEMA_VERSION,
        archived_at=_AS_OF,
        analysis_as_of=_AS_OF,
        subject=("BTCUSDT", "ETHUSDT"),
        relative_path="daily/2026/08/x.json",
        content_digest=_DIGEST,
        requested_count=2,
        completed_count=2,
        failed_count=0,
    )
    kwargs.update(overrides)
    return ManifestEntry(**kwargs)


# ============ render_manifest =================================================


def test_render_manifest_on_empty_entries() -> None:
    assert render_manifest(()) == "No archived records."


def test_render_manifest_shows_a_workspace_entry() -> None:
    text = render_manifest((_workspace_entry(),))
    assert "1 archived record(s):" in text
    assert "BTCUSDT" in text
    assert "context=sufficient" in text


def test_render_manifest_shows_a_workspace_entry_without_context_state() -> None:
    text = render_manifest((_workspace_entry(context_state=None),))
    assert "context=-" in text


def test_render_manifest_shows_a_daily_entry() -> None:
    text = render_manifest((_daily_entry(),))
    assert "completed=2/2 failed=0" in text


def test_render_manifest_shows_multiple_entries() -> None:
    text = render_manifest((_workspace_entry(), _daily_entry()))
    assert "2 archived record(s):" in text


# ============ render_record_verification =======================================


def test_render_record_verification_ok() -> None:
    result = RecordVerification(record_id="workspace-BTCUSDT-20260805T120000Z-aaaaaaaaaaaaaaaa", ok=True)
    assert render_record_verification(result) == f"{result.record_id}: OK"


def test_render_record_verification_failed() -> None:
    result = RecordVerification(
        record_id="workspace-BTCUSDT-20260805T120000Z-aaaaaaaaaaaaaaaa",
        ok=False,
        problems=("RecordNotFoundError: gone",),
    )
    text = render_record_verification(result)
    assert "FAILED" in text
    assert "RecordNotFoundError: gone" in text


# ============ render_archive_verification =======================================


def test_render_archive_verification_ok() -> None:
    assert "Archive OK" in render_archive_verification(ArchiveVerification(ok=True))


def test_render_archive_verification_missing_files() -> None:
    result = ArchiveVerification(ok=False, missing_files=("a", "b"))
    text = render_archive_verification(result)
    assert "missing files (2): a, b" in text


def test_render_archive_verification_orphan_files() -> None:
    result = ArchiveVerification(ok=False, orphan_files=("stray.json",))
    text = render_archive_verification(result)
    assert "orphan files (1): stray.json" in text


def test_render_archive_verification_duplicate_entries() -> None:
    result = ArchiveVerification(ok=False, duplicate_manifest_entries=("x",))
    text = render_archive_verification(result)
    assert "duplicate manifest entries (1): x" in text


def test_render_archive_verification_digest_mismatches() -> None:
    result = ArchiveVerification(ok=False, digest_mismatches=("x", "y"))
    text = render_archive_verification(result)
    assert "digest mismatches (2): x, y" in text


def test_render_archive_verification_combines_every_category() -> None:
    result = ArchiveVerification(
        ok=False,
        missing_files=("a",),
        orphan_files=("b",),
        duplicate_manifest_entries=("c",),
        digest_mismatches=("d",),
        manifest_mismatches=("e",),
    )
    text = render_archive_verification(result)
    for fragment in (
        "missing files", "orphan files", "duplicate manifest entries",
        "digest mismatches", "manifest/record disagreements",
    ):
        assert fragment in text


def test_render_archive_verification_manifest_mismatches_alone() -> None:
    result = ArchiveVerification(ok=False, manifest_mismatches=("x", "y"))
    text = render_archive_verification(result)
    assert "manifest/record disagreements (2): x, y" in text
