"""Audit and provenance metadata every trading-domain record carries.

Two small records, and both are load-bearing.

**`RecordAudit`** answers *when did this come into being, and when did it last
change*. For the sixteen captured artifacts in this domain those two instants are
**required to be equal** — a captured artifact is frozen at a named moment and a
change is a new record, so an `updated_at` that could differ from `created_at`
would be a field that can never be right. `require_unmodified` makes that a
construction-time rejection rather than a comment.

**`ConsumedSource`** is Law 8: *"a captured artifact records the identifiers and
digests of every source-of-truth record and every other captured artifact it
read."* One tuple per artifact buys three things nothing else can supply — a
correction becomes *derivable* staleness rather than a silent disagreement
(AP-D9), a deleted middle event becomes a detected dangling reference, and the
tax requirement *"a report names the `event_id`s and digests it consumed"* is one
field now and unanswerable later.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.records.errors import DomainValidationError, PayloadDecodeError
from fmis.records.identity import validate_domain_record_id
from fmis.records.validation import require_text, require_utc

__all__ = [
    "RecordAudit",
    "ConsumedSource",
    "normalize_consumed_sources",
    "require_unmodified",
    "encode_consumed_sources",
    "decode_consumed_sources",
]


@dataclass(frozen=True, slots=True, order=False)
class RecordAudit:
    """When a record came into being, and when it last changed.

    `updated_at` never means "someone edited a field" — nothing in this domain
    has an edit path. It means "the latest append against this record known at
    construction": a config-event fold, an appended tag, an appended lifecycle
    event. For a frozen artifact it equals `created_at` and `is_unmodified` is
    true forever.
    """

    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        created = require_utc(self.created_at, "created_at")
        updated = require_utc(self.updated_at, "updated_at")
        if updated < created:
            raise DomainValidationError(
                f"updated_at {updated.isoformat()} precedes created_at "
                f"{created.isoformat()}; a record cannot change before it exists"
            )
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)

    @classmethod
    def frozen_at(cls, moment: datetime) -> RecordAudit:
        """The audit block of a captured artifact: created and never changed."""
        return cls(created_at=moment, updated_at=moment)

    @property
    def is_unmodified(self) -> bool:
        """Whether anything has been appended since creation."""
        return self.created_at == self.updated_at

    def appended_at(self, moment: datetime) -> RecordAudit:
        """A new audit block recording an append at `moment`.

        Returns a *new* value — `RecordAudit` is frozen, so a caller cannot
        advance a record's audit block without producing the new record that
        justifies it.
        """
        return RecordAudit(created_at=self.created_at, updated_at=moment)

    def to_payload(self) -> dict[str, Any]:
        return {
            "created_at": encode_timestamp(self.created_at),
            "updated_at": encode_timestamp(self.updated_at),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> RecordAudit:
        if not isinstance(raw, Mapping):
            raise PayloadDecodeError(
                f"audit must be a JSON object, got {type(raw).__name__}"
            )
        missing = {"created_at", "updated_at"} - set(raw)
        if missing:
            raise PayloadDecodeError(f"audit is missing {sorted(missing)}")
        extra = set(raw) - {"created_at", "updated_at"}
        if extra:
            raise PayloadDecodeError(f"audit has unknown field(s) {sorted(extra)}")
        return cls(
            created_at=decode_timestamp(raw["created_at"]),
            updated_at=decode_timestamp(raw["updated_at"]),
        )


def require_unmodified(audit: RecordAudit, entity: str) -> RecordAudit:
    """Reject an audit block claiming a frozen artifact changed.

    Used by every captured artifact. The alternative — accepting the value and
    documenting that it should not differ — is how a "frozen" record acquires an
    edit path three milestones later without anyone deciding it should.
    """
    if not isinstance(audit, RecordAudit):
        raise TypeError(f"audit must be a RecordAudit, got {type(audit).__name__}")
    if not audit.is_unmodified:
        raise DomainValidationError(
            f"{entity} is a captured artifact and is frozen at creation; "
            f"updated_at {audit.updated_at.isoformat()} must equal created_at "
            f"{audit.created_at.isoformat()}. A change is a new record"
        )
    return audit


@dataclass(frozen=True, slots=True, order=True)
class ConsumedSource:
    """One record a captured artifact read, named by id **and** digest.

    The digest is what makes this more than a foreign key: an id alone tells a
    later reader *which* record was read, and the digest tells them whether the
    record still says what it said. That difference is the whole of AP-D9's
    answer — staleness is derived and rendered, and the artifact is never
    rewritten.
    """

    record_id: str
    content_digest: str
    kind: str

    def __post_init__(self) -> None:
        digest = require_text(self.content_digest, "content_digest")
        if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
            raise DomainValidationError(
                f"content_digest must be a 'sha256:<64 hex>' string, got {digest!r}"
            )
        object.__setattr__(self, "record_id", validate_domain_record_id(self.record_id))
        object.__setattr__(self, "content_digest", digest)
        object.__setattr__(self, "kind", require_text(self.kind, "kind"))

    def to_payload(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "content_digest": self.content_digest,
            "kind": self.kind,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> ConsumedSource:
        if not isinstance(raw, Mapping):
            raise PayloadDecodeError(
                f"consumed source must be a JSON object, got {type(raw).__name__}"
            )
        expected = {"record_id", "content_digest", "kind"}
        if set(raw) != expected:
            raise PayloadDecodeError(
                f"consumed source keys {sorted(raw)} != {sorted(expected)}"
            )
        return cls(
            record_id=str(raw["record_id"]),
            content_digest=str(raw["content_digest"]),
            kind=str(raw["kind"]),
        )


def normalize_consumed_sources(
    sources: Iterable[ConsumedSource],
) -> tuple[ConsumedSource, ...]:
    """Sort, deduplicate, and reject one id claiming two digests.

    Sorting makes the tuple a pure function of the *set* that was read, so two
    artifacts that consumed the same inputs in a different order are byte-equal
    and therefore share an identity. The conflict rejection is the important
    half: one `record_id` with two digests means a caller assembled the list from
    two views of the store, and silently keeping either would make the staleness
    check answer a question about a record nobody read.
    """
    seen: dict[str, ConsumedSource] = {}
    for source in sources:
        if not isinstance(source, ConsumedSource):
            raise TypeError(
                f"consumed source must be a ConsumedSource, got "
                f"{type(source).__name__}"
            )
        existing = seen.get(source.record_id)
        if existing is not None and existing != source:
            raise DomainValidationError(
                f"consumed source {source.record_id} was supplied twice with "
                f"different content ({existing.content_digest} vs "
                f"{source.content_digest}); one of the two readings is stale"
            )
        seen[source.record_id] = source
    return tuple(sorted(seen.values()))


def encode_consumed_sources(sources: tuple[ConsumedSource, ...]) -> list[Any]:
    return [source.to_payload() for source in sources]


def decode_consumed_sources(raw: Any) -> tuple[ConsumedSource, ...]:
    if not isinstance(raw, list):
        raise PayloadDecodeError(
            f"consumed_sources must be a JSON array, got {type(raw).__name__}"
        )
    return normalize_consumed_sources(ConsumedSource.from_payload(item) for item in raw)
