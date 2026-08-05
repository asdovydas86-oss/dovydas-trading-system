"""The archive envelope: the one JSON shape every record file holds.

ADR-0027 §3. Seven keys, no others. `schema_version` here is the envelope's
own version, owned by `fmis.archive` — distinct from `payload["schema_version"]`,
which is `WORKSPACE_SCHEMA_VERSION`/`DAILY_SCHEMA_VERSION`, owned by
`fmis.workspace`/`fmis.daily` and carried through unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from fmis.archive.errors import CorruptRecordError, UnsupportedRecordTypeError, UnsupportedSchemaVersionError
from fmis.archive.identity import content_digest as _sha256_digest
from fmis.archive.identity import validate_record_id
from fmis.archive.json_safe import canonical_dumps, decode_timestamp, encode_timestamp

__all__ = [
    "ARCHIVE_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "RecordType",
    "ArchiveEnvelope",
    "encode_envelope",
    "decode_envelope",
    "compute_content_digest",
    "envelope_content_digest",
]

#: Bumped when the envelope's own shape changes in a way a reader must notice.
ARCHIVE_SCHEMA_VERSION = 1

#: The envelope schema versions this build can read. No migration path exists
#: yet (ADR-0027 §8): anything outside this set is rejected cleanly.
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})

_ENVELOPE_KEYS = {
    "record_type", "schema_version", "record_id", "archived_at",
    "analysis_as_of", "subject", "payload", "content_digest",
}


class RecordType(str, Enum):
    WORKSPACE = "workspace"
    DAILY_RUN = "daily_run"


@dataclass(frozen=True, slots=True)
class ArchiveEnvelope:
    record_type: RecordType
    schema_version: int
    record_id: str
    archived_at: datetime
    analysis_as_of: datetime
    subject: tuple[str, ...]
    payload: dict[str, Any]
    content_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.record_type, RecordType):
            raise TypeError(f"record_type must be a RecordType, got {type(self.record_type).__name__}")
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool):
            raise TypeError("schema_version must be an int")
        validate_record_id(self.record_id)
        for name in ("archived_at", "analysis_as_of"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise TypeError(f"{name} must be a timezone-aware datetime")
        if not isinstance(self.subject, tuple) or not self.subject or not all(
            isinstance(s, str) and s for s in self.subject
        ):
            raise TypeError("subject must be a non-empty tuple of non-empty str")
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dict")
        if not isinstance(self.content_digest, str) or not self.content_digest.startswith("sha256:"):
            raise TypeError("content_digest must be a 'sha256:<hex>' str")


def _digest_basis(
    *,
    record_type: RecordType,
    schema_version: int,
    analysis_as_of: datetime,
    subject: tuple[str, ...],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Exactly the fields `content_digest` covers.

    `record_id` and `archived_at` are excluded on purpose (ADR-0027 §3):
    `record_id` is *derived from* this digest, so including it would be
    circular, and `archived_at` is a filing timestamp that must not affect
    whether two archive calls of the same analysis are recognised as
    duplicates — a re-archive of unchanged data a day later must produce the
    identical digest.
    """
    return {
        "record_type": record_type.value,
        "schema_version": schema_version,
        "analysis_as_of": encode_timestamp(analysis_as_of),
        "subject": list(subject),
        "payload": payload,
    }


def compute_content_digest(
    *,
    record_type: RecordType,
    schema_version: int,
    analysis_as_of: datetime,
    subject: tuple[str, ...],
    payload: dict[str, Any],
) -> str:
    """The `content_digest` a record with this content must carry.

    Called twice for the same record — once to derive `record_id` before the
    envelope exists, once more inside `envelope_content_digest` to verify a
    loaded record — and must return the identical value both times.
    """
    basis = _digest_basis(
        record_type=record_type,
        schema_version=schema_version,
        analysis_as_of=analysis_as_of,
        subject=subject,
        payload=payload,
    )
    return _sha256_digest(canonical_dumps(basis))


def envelope_content_digest(envelope: ArchiveEnvelope) -> str:
    """Recompute the digest a loaded envelope's content should carry."""
    return compute_content_digest(
        record_type=envelope.record_type,
        schema_version=envelope.schema_version,
        analysis_as_of=envelope.analysis_as_of,
        subject=envelope.subject,
        payload=envelope.payload,
    )


def encode_envelope(envelope: ArchiveEnvelope) -> bytes:
    """The exact bytes written to disk for this envelope."""
    body: dict[str, Any] = {
        "record_type": envelope.record_type.value,
        "schema_version": envelope.schema_version,
        "record_id": envelope.record_id,
        "archived_at": encode_timestamp(envelope.archived_at),
        "analysis_as_of": encode_timestamp(envelope.analysis_as_of),
        "subject": list(envelope.subject),
        "payload": envelope.payload,
        "content_digest": envelope.content_digest,
    }
    return canonical_dumps(body)


def decode_envelope(raw: Any) -> ArchiveEnvelope:
    if not isinstance(raw, dict):
        raise CorruptRecordError(f"envelope must be a JSON object, got {type(raw).__name__}")
    missing = _ENVELOPE_KEYS - set(raw)
    if missing:
        raise CorruptRecordError(f"envelope is missing required field(s): {sorted(missing)}")
    extra = set(raw) - _ENVELOPE_KEYS
    if extra:
        raise CorruptRecordError(f"envelope has unknown field(s): {sorted(extra)}")

    record_type_raw = raw["record_type"]
    if not isinstance(record_type_raw, str):
        raise CorruptRecordError("envelope.record_type must be a str")
    try:
        record_type = RecordType(record_type_raw)
    except ValueError as error:
        raise UnsupportedRecordTypeError(
            f"envelope.record_type {record_type_raw!r} is not a known record type"
        ) from error

    schema_version = raw["schema_version"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise CorruptRecordError("envelope.schema_version must be an int")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedSchemaVersionError(
            f"envelope schema_version {schema_version} is not supported; "
            f"this build supports {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )

    record_id = raw["record_id"]
    if not isinstance(record_id, str):
        raise CorruptRecordError("envelope.record_id must be a str")
    validate_record_id(record_id)

    subject_raw = raw["subject"]
    if not isinstance(subject_raw, list) or not subject_raw:
        raise CorruptRecordError("envelope.subject must be a non-empty JSON array")
    subject = tuple(subject_raw)
    if not all(isinstance(s, str) and s for s in subject):
        raise CorruptRecordError("envelope.subject entries must be non-empty str")

    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise CorruptRecordError("envelope.payload must be a JSON object")

    content_digest = raw["content_digest"]
    if not isinstance(content_digest, str):
        raise CorruptRecordError("envelope.content_digest must be a str")

    return ArchiveEnvelope(
        record_type=record_type,
        schema_version=schema_version,
        record_id=record_id,
        archived_at=decode_timestamp(raw["archived_at"]),
        analysis_as_of=decode_timestamp(raw["analysis_as_of"]),
        subject=subject,
        payload=payload,
        content_digest=content_digest,
    )
