"""The metadata-only manifest: `manifest.jsonl`.

ADR-0027 §10. One JSON object per line, each carrying exactly what `archive
list` needs to display a record without opening it. Written via the same
temp-file-then-`os.replace` sequence every record file uses (§6): the whole
file is read, the new line appended in memory, and the result published
atomically — so `manifest.jsonl` is never observed half-written, at the cost
of an O(entry count) rewrite per archive call, accepted because ADR-0027
Rejected Alternatives judges that cost proportionate to this owner's expected
record volume (hundreds, not millions).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fmis.archive.atomic import atomic_write
from fmis.archive.envelope import RecordType
from fmis.archive.errors import CorruptRecordError, ManifestError
from fmis.archive.identity import validate_record_id
from fmis.archive.json_safe import decode_timestamp, encode_timestamp, reject_duplicate_json_keys

__all__ = ["ManifestEntry", "MANIFEST_FILENAME", "read_manifest", "append_manifest_entry"]

MANIFEST_FILENAME = "manifest.jsonl"


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    record_id: str
    record_type: RecordType
    schema_version: int
    archived_at: datetime
    analysis_as_of: datetime
    subject: tuple[str, ...]
    relative_path: str
    content_digest: str
    context_state: str | None = None
    requested_count: int | None = None
    completed_count: int | None = None
    failed_count: int | None = None

    def __post_init__(self) -> None:
        validate_record_id(self.record_id)
        if not isinstance(self.record_type, RecordType):
            raise TypeError("record_type must be a RecordType")
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool):
            raise TypeError("schema_version must be an int")
        for name in ("archived_at", "analysis_as_of"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise TypeError(f"{name} must be a timezone-aware datetime")
        if not isinstance(self.subject, tuple) or not all(isinstance(s, str) for s in self.subject):
            raise TypeError("subject must be a tuple of str")
        if not isinstance(self.relative_path, str) or not self.relative_path:
            raise TypeError("relative_path must be a non-empty str")
        if not isinstance(self.content_digest, str) or not self.content_digest.startswith("sha256:"):
            raise TypeError("content_digest must be a 'sha256:<hex>' str")


def _encode_entry(entry: ManifestEntry) -> dict[str, Any]:
    return {
        "record_id": entry.record_id,
        "record_type": entry.record_type.value,
        "schema_version": entry.schema_version,
        "archived_at": encode_timestamp(entry.archived_at),
        "analysis_as_of": encode_timestamp(entry.analysis_as_of),
        "subject": list(entry.subject),
        "relative_path": entry.relative_path,
        "content_digest": entry.content_digest,
        "context_state": entry.context_state,
        "requested_count": entry.requested_count,
        "completed_count": entry.completed_count,
        "failed_count": entry.failed_count,
    }


def _decode_entry(raw: dict[str, Any], *, line_number: int) -> ManifestEntry:
    try:
        return ManifestEntry(
            record_id=raw["record_id"],
            record_type=RecordType(raw["record_type"]),
            schema_version=raw["schema_version"],
            archived_at=decode_timestamp(raw["archived_at"]),
            analysis_as_of=decode_timestamp(raw["analysis_as_of"]),
            subject=tuple(raw["subject"]),
            relative_path=raw["relative_path"],
            content_digest=raw["content_digest"],
            context_state=raw.get("context_state"),
            requested_count=raw.get("requested_count"),
            completed_count=raw.get("completed_count"),
            failed_count=raw.get("failed_count"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ManifestError(f"manifest line {line_number} is malformed: {error}") from error


def read_manifest(root: Path) -> tuple[ManifestEntry, ...]:
    """Read every manifest entry, metadata-only — never a record's payload."""
    path = root / MANIFEST_FILENAME
    if not path.is_file():
        return ()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ManifestError(f"could not read manifest {path}: {error}") from error
    entries: list[ManifestEntry] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line, object_pairs_hook=reject_duplicate_json_keys)
        except json.JSONDecodeError as error:
            raise ManifestError(f"manifest line {line_number} is not valid JSON: {error}") from error
        except CorruptRecordError as error:
            raise ManifestError(f"manifest line {line_number}: {error}") from error
        entries.append(_decode_entry(raw, line_number=line_number))
    return tuple(entries)


def append_manifest_entry(root: Path, entry: ManifestEntry) -> None:
    """Publish one new manifest entry, atomically rewriting the whole file.

    Raises `ManifestError` (never a silent partial write) if the existing
    manifest cannot be read, or if `entry.record_id` already has an entry —
    a duplicate manifest entry is rejected here rather than produced.
    """
    existing = read_manifest(root)
    if any(existing_entry.record_id == entry.record_id for existing_entry in existing):
        raise ManifestError(f"manifest already has an entry for {entry.record_id!r}")
    lines = [json.dumps(_encode_entry(e), sort_keys=True) for e in (*existing, entry)]
    body = ("\n".join(lines) + "\n").encode("utf-8") if lines else b""
    atomic_write(root / MANIFEST_FILENAME, body)
