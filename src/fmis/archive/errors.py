"""The typed error hierarchy for `fmis.archive`.

Every failure category ADR-0027 §7 names gets its own subclass. Raising the
base `ArchiveError` directly is reserved for genuinely uncategorized failures;
every code path below has a specific error to raise instead, so a caller can
tell a missing record from a corrupt one from a permission failure without
parsing a message.
"""

from __future__ import annotations

__all__ = [
    "ArchiveError",
    "RecordNotFoundError",
    "InvalidRecordIdError",
    "CorruptRecordError",
    "IntegrityError",
    "UnsupportedRecordTypeError",
    "UnsupportedSchemaVersionError",
    "RecordValidationError",
    "DuplicateRecordConflictError",
    "ManifestError",
    "ArchiveIOError",
]


class ArchiveError(Exception):
    """Base class for every archive failure.

    Follows the package-error convention `WorkspaceError`, `DailyRunError` and
    `DecisionContextError` established elsewhere, so a caller can catch this
    layer's failures as a group.
    """


class RecordNotFoundError(ArchiveError):
    """No record exists at the path a valid record ID resolves to."""


class InvalidRecordIdError(ArchiveError):
    """A record ID is malformed, or would resolve outside the archive root."""


class CorruptRecordError(ArchiveError):
    """A record file could not be parsed as the canonical envelope shape.

    Covers malformed JSON, truncated content, and duplicate JSON object keys —
    every case where the *bytes on disk* are not a valid envelope, as opposed
    to a valid envelope whose content does not check out (`IntegrityError`) or
    whose payload does not build a valid domain model (`RecordValidationError`).
    """


class IntegrityError(ArchiveError):
    """A record's `content_digest` does not match its recomputed digest."""


class UnsupportedRecordTypeError(ArchiveError):
    """A record's `record_type` is not one this version of the code knows."""


class UnsupportedSchemaVersionError(ArchiveError):
    """A record's schema version (envelope or payload) is not supported.

    No migration path exists in v1 (ADR-0027 §8): a version outside the
    supported set is rejected cleanly rather than guessed at.
    """


class RecordValidationError(ArchiveError):
    """A record's payload parsed but the reconstructed domain model rejected it.

    Distinct from `CorruptRecordError`: the JSON was well-formed and every
    field had the right shape, but `Workspace`/`DailyRun` (or a nested model)
    raised its own `__post_init__` validation — for example a metadata value
    that is not JSON-safe, caught at encode time before either error can occur
    on decode of a record this package itself wrote.
    """


class DuplicateRecordConflictError(ArchiveError):
    """A record ID collision between two archive calls with different content.

    Record IDs are content-derived (ADR-0027 §4), so this can only occur from
    a digest-prefix collision — astronomically unlikely, never silently
    resolved by overwriting or renaming either record.
    """


class ManifestError(ArchiveError):
    """The manifest is inconsistent with the record files, or could not be
    updated.

    Covers a stale entry (file missing), an orphan record (file present, no
    entry), a duplicate entry, and a write failure while publishing a new
    entry — never auto-repaired (ADR-0027 §6).
    """


class ArchiveIOError(ArchiveError):
    """A filesystem operation failed for a reason outside this package's
    control — permissions, a full disk, or a race on the archive root."""
