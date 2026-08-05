"""Direct validation tests for `ManifestEntry.__post_init__` and `read_manifest`."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from fmis.archive.envelope import ARCHIVE_SCHEMA_VERSION, RecordType
from fmis.archive.errors import ManifestError
from fmis.archive.identity import build_record_id
from fmis.archive.manifest import MANIFEST_FILENAME, ManifestEntry, read_manifest

_AS_OF = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
_DIGEST = "sha256:" + "a" * 64
_RECORD_ID = build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of=_AS_OF, digest=_DIGEST)


def _valid_kwargs(**overrides: object) -> dict:
    kwargs = dict(
        record_id=_RECORD_ID,
        record_type=RecordType.WORKSPACE,
        schema_version=ARCHIVE_SCHEMA_VERSION,
        archived_at=_AS_OF,
        analysis_as_of=_AS_OF,
        subject=("BTCUSDT",),
        relative_path="workspace/2026/08/x.json",
        content_digest=_DIGEST,
    )
    kwargs.update(overrides)
    return kwargs


def test_a_valid_entry_constructs() -> None:
    ManifestEntry(**_valid_kwargs())  # does not raise


def test_rejects_a_non_record_type() -> None:
    with pytest.raises(TypeError):
        ManifestEntry(**_valid_kwargs(record_type="workspace"))


def test_rejects_a_non_int_schema_version() -> None:
    with pytest.raises(TypeError):
        ManifestEntry(**_valid_kwargs(schema_version="1"))


def test_rejects_a_naive_archived_at() -> None:
    with pytest.raises(TypeError):
        ManifestEntry(**_valid_kwargs(archived_at=datetime(2026, 1, 1)))


def test_rejects_a_naive_analysis_as_of() -> None:
    with pytest.raises(TypeError):
        ManifestEntry(**_valid_kwargs(analysis_as_of=datetime(2026, 1, 1)))


def test_rejects_a_subject_with_a_non_str_entry() -> None:
    with pytest.raises(TypeError):
        ManifestEntry(**_valid_kwargs(subject=(1,)))


def test_rejects_an_empty_relative_path() -> None:
    with pytest.raises(TypeError):
        ManifestEntry(**_valid_kwargs(relative_path=""))


def test_rejects_a_content_digest_without_the_prefix() -> None:
    with pytest.raises(TypeError):
        ManifestEntry(**_valid_kwargs(content_digest="a" * 64))


def test_read_manifest_wraps_an_os_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / MANIFEST_FILENAME).write_text("")

    real_read_text = Path.read_text

    def failing_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == MANIFEST_FILENAME:
            raise OSError("permission denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", failing_read_text)
    with pytest.raises(ManifestError):
        read_manifest(tmp_path)


def test_read_manifest_rejects_a_duplicate_json_key_in_a_line(tmp_path: Path) -> None:
    """Review finding P3: `manifest.jsonl` lines get the same duplicate-key
    rejection record files already had, via the shared
    `reject_duplicate_json_keys` hook."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / MANIFEST_FILENAME).write_text('{"record_id": "x", "record_id": "y"}\n')
    with pytest.raises(ManifestError, match="duplicate JSON key"):
        read_manifest(tmp_path)
