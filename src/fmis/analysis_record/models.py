"""`AnalysisRecord` — the domain's citation of an archived analysis page.

The archived page itself is `AO`'s, built and shipping today: `fmis.archive`
writes it once, atomically, under ADR-0027, and never rewrites it. This type does
not duplicate that record and does not re-encode it. It is the **citation** — the
id, the digest, the subject and the instant — which is exactly what §9.7's
relationship row describes: *"Cited by `MarketSnapshot`, `OpportunityProposal`,
`JournalEntry`, `DecisionEpisode` — by id, in one direction only."*

**The one product change the data model asks for**, and it is why this type
exists: an archived analysis must be reachable *from* a proposal and a trade, and
vice versa. Today the only bridge is the owner copying a `record_id` into notes
outside the system. `as_consumed_source()` supplies the edge at no extra cost —
Law 8's tuple already carries id and digest, so a proposal that cites an analysis
is also a proposal whose staleness against a re-archived analysis is derivable.

**Nothing here modifies `fmis.archive`.** The record-id validator is imported
rather than reimplemented, so this type accepts exactly the record types the
archive actually writes, and widens automatically if that enum is opened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fmis.archive.identity import parse_record_id, validate_record_id
from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.records import (
    ConsumedSource,
    DomainValidationError,
    RecordAudit,
    TradeDomainError,
    require_exact_keys,
    require_int,
    require_mapping,
    require_payload_version,
    require_text,
    require_tuple_of,
    require_unmodified,
    require_utc,
)

__all__ = [
    "AnalysisRecordError",
    "AnalysisRecord",
    "ANALYSIS_RECORD_SCHEMA_VERSION",
    "SUPPORTED_ANALYSIS_RECORD_VERSIONS",
    "ANALYSIS_RECORD_KIND",
]

ANALYSIS_RECORD_SCHEMA_VERSION = 1
SUPPORTED_ANALYSIS_RECORD_VERSIONS = frozenset({1})

#: What this citation is called inside a `ConsumedSource`. A short, stable string
#: rather than a class name, so renaming the class never changes stored bytes.
ANALYSIS_RECORD_KIND = "analysis_record"


class AnalysisRecordError(TradeDomainError):
    """Base class for every analysis-record citation failure."""


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    """One archived analysis page, cited by id and digest.

    Immutable in every field, because the thing it points at is. `archived_at` is
    a filing timestamp and is deliberately excluded from the archive's own content
    digest (ADR-0027 §3) — a re-archive of unchanged data a day later must produce
    the identical digest, which is what makes citing one an idempotent act.
    """

    record_id: str
    record_type: str
    payload_schema_version: int
    analysis_as_of: datetime
    subject: tuple[str, ...]
    content_digest: str
    archived_at: datetime
    audit: RecordAudit
    schema_version: int = ANALYSIS_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_record_id(self.record_id)
        object.__setattr__(
            self, "record_type", require_text(self.record_type, "record_type")
        )
        require_int(self.payload_schema_version, "payload_schema_version", minimum=1)
        object.__setattr__(
            self, "analysis_as_of", require_utc(self.analysis_as_of, "analysis_as_of")
        )
        subject = require_tuple_of(self.subject, str, "subject", minimum_length=1)
        object.__setattr__(
            self,
            "subject",
            tuple(require_text(part, "subject entry") for part in subject),
        )
        digest = require_text(self.content_digest, "content_digest")
        if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
            raise DomainValidationError(
                f"content_digest must be a 'sha256:<64 hex>' string, got {digest!r}"
            )
        object.__setattr__(self, "content_digest", digest)
        object.__setattr__(
            self, "archived_at", require_utc(self.archived_at, "archived_at")
        )
        require_unmodified(self.audit, "AnalysisRecord")
        if self.schema_version not in SUPPORTED_ANALYSIS_RECORD_VERSIONS:
            raise DomainValidationError(
                f"analysis record schema_version {self.schema_version} is not one "
                f"this build writes ({sorted(SUPPORTED_ANALYSIS_RECORD_VERSIONS)})"
            )
        stated_type = parse_record_id(self.record_id).group("type_slug")
        if not self.record_type.startswith(stated_type):
            raise DomainValidationError(
                f"record_type {self.record_type!r} disagrees with the record id's "
                f"own type slug {stated_type!r}; a citation that names the wrong "
                "kind of page cannot be resolved"
            )

    @property
    def subject_label(self) -> str:
        """`BTCUSDT · swing` — the citation form a surface renders."""
        return " · ".join(self.subject)

    def as_consumed_source(self) -> ConsumedSource:
        """This citation as a Law 8 entry on a captured artifact that read it."""
        return ConsumedSource(
            record_id=self.record_id,
            content_digest=self.content_digest,
            kind=ANALYSIS_RECORD_KIND,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "record_type": self.record_type,
            "payload_schema_version": self.payload_schema_version,
            "analysis_as_of": encode_timestamp(self.analysis_as_of),
            "subject": list(self.subject),
            "content_digest": self.content_digest,
            "archived_at": encode_timestamp(self.archived_at),
            "audit": self.audit.to_payload(),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> AnalysisRecord:
        mapping = require_mapping(raw, "analysis record")
        version = require_payload_version(
            mapping,
            supported=SUPPORTED_ANALYSIS_RECORD_VERSIONS,
            entity="analysis record",
        )
        require_exact_keys(
            mapping,
            {
                "schema_version",
                "record_id",
                "record_type",
                "payload_schema_version",
                "analysis_as_of",
                "subject",
                "content_digest",
                "archived_at",
                "audit",
            },
            "analysis record",
        )
        subject_raw = mapping["subject"]
        if not isinstance(subject_raw, list):
            raise AnalysisRecordError("analysis record subject must be a JSON array")
        return cls(
            record_id=str(mapping["record_id"]),
            record_type=str(mapping["record_type"]),
            payload_schema_version=mapping["payload_schema_version"],
            analysis_as_of=decode_timestamp(mapping["analysis_as_of"]),
            subject=tuple(str(part) for part in subject_raw),
            content_digest=str(mapping["content_digest"]),
            archived_at=decode_timestamp(mapping["archived_at"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            schema_version=version,
        )
