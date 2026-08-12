"""The envelope every stored record is wrapped in, and the two byte formats.

An envelope adds exactly four things to a domain payload, and each earns its
place:

* **`kind`** — which decoder reads this. Without it a reader must guess from the
  directory it happened to find the file in, and a misfiled record decodes as the
  wrong type instead of failing.
* **`written_at`** — when FMITS filed it, which is *not* when the thing happened.
  Excluded from the digest, following ADR-0027 §3's precedent for `archived_at`:
  a record re-published after a crash must produce identical bytes, or every
  restart writes a duplicate.
* **`content_digest`** — the record's own digest, carried alongside so integrity
  is checkable without reconstructing the record.
* **`schema_version`** — the *envelope's* version, separate from the payload's.
  One can move without the other, and a single number would make an envelope
  change look like a record change.

**Two byte formats, one digest.** Record files are `canonical_dumps` — the frozen,
indented, sorted encoder the archive already ships. Log files are one compact line
per event, because a year file is appended to and scanned. The digest is computed
over neither: it comes from the domain record's own basis through
`content_digest_over`, so the format a record happens to be stored in can never
change its identity.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fmis.archive.errors import ArchiveError
from fmis.archive.json_safe import (
    canonical_dumps,
    canonical_loads,
    decode_timestamp,
    encode_timestamp,
    reject_duplicate_json_keys,
)
from fmis.records import (
    PayloadDecodeError,
    require_exact_keys,
    require_int,
    require_mapping,
    require_payload_version,
    require_text,
    require_utc,
)

from fmis.persistence.errors import StoreIntegrityError
from fmis.persistence.kinds import RecordKind, kind_of

__all__ = [
    "STORE_SCHEMA_VERSION",
    "SUPPORTED_STORE_VERSIONS",
    "StoredEnvelope",
    "encode_envelope_bytes",
    "decode_envelope_bytes",
    "encode_line",
    "decode_line",
]

#: The envelope's own contract version. Bumping it ships a reader for every prior
#: version, exactly as `fmis.records.schema` requires of a payload.
STORE_SCHEMA_VERSION = 1

SUPPORTED_STORE_VERSIONS = frozenset({1})

_ENVELOPE_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "record_id",
        "payload_schema_version",
        "occurred_at",
        "written_at",
        "content_digest",
        "payload",
    }
)


@dataclass(frozen=True, slots=True)
class StoredEnvelope:
    """One domain payload, plus what the store needs to find and check it."""

    kind: RecordKind
    record_id: str
    payload_schema_version: int
    occurred_at: datetime
    written_at: datetime
    content_digest: str
    payload: Mapping[str, Any]
    schema_version: int = STORE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RecordKind):
            raise TypeError(f"kind must be a RecordKind, got {type(self.kind).__name__}")
        object.__setattr__(self, "record_id", require_text(self.record_id, "record_id"))
        require_int(self.payload_schema_version, "payload_schema_version", minimum=1)
        object.__setattr__(
            self, "occurred_at", require_utc(self.occurred_at, "occurred_at")
        )
        object.__setattr__(
            self, "written_at", require_utc(self.written_at, "written_at")
        )
        digest = require_text(self.content_digest, "content_digest")
        if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
            raise StoreIntegrityError(
                f"content_digest must be a 'sha256:<64 hex>' string, got {digest!r}"
            )
        object.__setattr__(self, "content_digest", digest)
        if not isinstance(self.payload, Mapping):
            raise TypeError(
                f"payload must be a Mapping, got {type(self.payload).__name__}"
            )
        if self.schema_version not in SUPPORTED_STORE_VERSIONS:
            raise StoreIntegrityError(
                f"store envelope schema_version {self.schema_version} is not one "
                f"this build writes ({sorted(SUPPORTED_STORE_VERSIONS)})"
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "record_id": self.record_id,
            "payload_schema_version": self.payload_schema_version,
            "occurred_at": encode_timestamp(self.occurred_at),
            "written_at": encode_timestamp(self.written_at),
            "content_digest": self.content_digest,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> StoredEnvelope:
        mapping = require_mapping(raw, "store envelope")
        version = require_payload_version(
            mapping, supported=SUPPORTED_STORE_VERSIONS, entity="store envelope"
        )
        require_exact_keys(mapping, _ENVELOPE_KEYS, "store envelope")
        payload = mapping["payload"]
        if not isinstance(payload, Mapping):
            raise PayloadDecodeError(
                f"store envelope payload must be a JSON object, got "
                f"{type(payload).__name__}"
            )
        return cls(
            kind=kind_of(mapping["kind"]),
            record_id=str(mapping["record_id"]),
            payload_schema_version=mapping["payload_schema_version"],
            occurred_at=decode_timestamp(mapping["occurred_at"]),
            written_at=decode_timestamp(mapping["written_at"]),
            content_digest=str(mapping["content_digest"]),
            payload=dict(payload),
            schema_version=version,
        )


def encode_envelope_bytes(envelope: StoredEnvelope) -> bytes:
    """A record file's bytes — the archive's frozen canonical encoder, reused."""
    return canonical_dumps(envelope.to_payload())


def decode_envelope_bytes(data: bytes) -> StoredEnvelope:
    """Read a record file, reporting unparseable bytes as a store-integrity failure.

    `canonical_loads` raises `fmis.archive`'s `CorruptRecordError`, which is not a
    `PersistenceError` and would therefore escape every `except` in this package —
    including `verify()`'s, turning a sweep that should *report* a corrupt file
    into one that crashes on it.
    """
    try:
        decoded = canonical_loads(data)
    except ArchiveError as error:
        raise StoreIntegrityError(f"record file is unreadable: {error}") from error
    return StoredEnvelope.from_payload(decoded)


def encode_line(value: Mapping[str, Any]) -> str:
    """One log or index line: compact, sorted, newline-free.

    Sorted keys for the same reason `canonical_dumps` sorts them — a line that
    depends on dict insertion order cannot be compared byte-for-byte against the
    line already on disk, and that comparison is the whole of this store's
    append-only proof.
    """
    try:
        text = json.dumps(
            dict(value),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        # `TypeError` for a value with no JSON form at all (a set, a Decimal that
        # slipped through); `ValueError` for one that has a form JSON forbids
        # (`NaN`). Both mean the same thing to a caller and neither is repaired.
        raise PayloadDecodeError(f"value is not JSON-safe: {error}") from error
    if "\n" in text:  # pragma: no cover - json.dumps escapes newlines
        raise PayloadDecodeError("a log line must not contain a newline")
    return text


def decode_line(line: str, *, line_number: int) -> dict[str, Any]:
    try:
        decoded = json.loads(line, object_pairs_hook=reject_duplicate_json_keys)
    except json.JSONDecodeError as error:
        raise StoreIntegrityError(
            f"line {line_number} is not valid JSON: {error}"
        ) from error
    except Exception as error:  # duplicate key, surfaced by the pairs hook
        raise StoreIntegrityError(f"line {line_number}: {error}") from error
    if not isinstance(decoded, dict):
        raise StoreIntegrityError(
            f"line {line_number} is not a JSON object, got {type(decoded).__name__}"
        )
    return decoded
