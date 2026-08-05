"""Memory & Decision Archive v1 — durable storage for `Workspace`/`DailyRun`.

`ArchiveStore` is the public entry point: it archives a completed `Workspace`
or `DailyRun` to a versioned, integrity-checked JSON record; lists archived
records without reading full payloads; loads and reconstructs one record by
its stable ID with no network access; and verifies integrity, detecting
corruption and unsupported schema versions.

Contracts: [ADR-0027](../../../docs/adr/ADR-0027-memory-and-decision-archive-persistence-schema.md).
Design: [MEMORY_AND_DECISION_ARCHIVE_V1.md](../../../docs/design/MEMORY_AND_DECISION_ARCHIVE_V1.md).

**AO guarantees snapshot reproduction only** — a decoded record equals the
value that was archived, exactly. It does not recompute and it does not
replay history from raw inputs (ADR-0027 §2).
"""

from __future__ import annotations

from fmis.archive.envelope import ARCHIVE_SCHEMA_VERSION, RecordType
from fmis.archive.errors import (
    ArchiveError,
    ArchiveIOError,
    CorruptRecordError,
    DuplicateRecordConflictError,
    IntegrityError,
    InvalidRecordIdError,
    ManifestError,
    RecordNotFoundError,
    RecordValidationError,
    UnsupportedRecordTypeError,
    UnsupportedSchemaVersionError,
)
from fmis.archive.manifest import ManifestEntry
from fmis.archive.render import render_archive_verification, render_manifest, render_record_verification
from fmis.archive.storage import (
    ArchivedRecord,
    ArchiveStore,
    ArchiveVerification,
    RecordVerification,
    default_archive_root,
)

__all__ = [
    "ARCHIVE_SCHEMA_VERSION",
    "RecordType",
    "ArchiveError",
    "ArchiveIOError",
    "CorruptRecordError",
    "DuplicateRecordConflictError",
    "IntegrityError",
    "InvalidRecordIdError",
    "ManifestError",
    "RecordNotFoundError",
    "RecordValidationError",
    "UnsupportedRecordTypeError",
    "UnsupportedSchemaVersionError",
    "ManifestEntry",
    "ArchivedRecord",
    "ArchiveStore",
    "ArchiveVerification",
    "RecordVerification",
    "default_archive_root",
    "render_manifest",
    "render_record_verification",
    "render_archive_verification",
]
