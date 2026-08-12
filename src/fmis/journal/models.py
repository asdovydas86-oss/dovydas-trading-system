"""`JournalEntry` and `TradeJournal` — the owner's own words, and the view over them.

The brief calls this *TradeJournal*. In the data model the record is a
`JournalEntry`, and `TradeJournal` is the **read-time view** over every entry
linked to one subject — which is what the brief's name actually describes. Both
exist here, and neither duplicates the other: one is a source of truth, the other
is a projection with no storage of its own.

**The binding constraint is adoption, not schema.** *"A journal with twelve kinds
and mandatory structured fields is architecturally admirable and will not get
written."* So: three kinds, almost nothing required, everything else nudged.

Two fields carry more weight than their size.

**`recollection` is derived, not set.** It is true exactly when the entry was
written after the decision it concerns had already resolved, and it is a
*property* of two timestamps rather than a field anyone can fill in. That is
deliberate: it is the one flag a human will never set against themselves, and
without it *"I felt uneasy about that one"*, written after a loss, enters the
dataset as predictive signal. Cohort statistics exclude recollections by default.

**Tag provenance has four origins and only three are counted.** `OWNER`,
`AI_PROPOSED_CONFIRMED` and `IMPORTED` are counted and separable;
**`AI_PROPOSED_PENDING` is not counted at all**. Cohort analysis can always
exclude AI-originated tags to check whether a finding survives without them,
which is the only defence against a model training on its own output.

**Links are the architecture.** Six typed, directional kinds. *"A single untyped
'related' edge would collapse six answerable questions into one unanswerable
one."*
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.provenance import Absent, ValueOrigin, VersionedTerm, decode_maybe, encode_maybe
from fmis.records import (
    DomainValidationError,
    PayloadDecodeError,
    RecordAudit,
    TradeDomainError,
    build_domain_record_id,
    content_digest_over,
    require_exact_keys,
    require_mapping,
    require_member,
    require_payload_version,
    require_text,
    require_tuple_of,
    require_utc,
    validate_domain_record_id,
)

__all__ = [
    "JournalError",
    "JOURNAL_ENTRY_SCHEMA_VERSION",
    "SUPPORTED_JOURNAL_ENTRY_VERSIONS",
    "JOURNAL_ENTRY_TYPE_SLUG",
    "JOURNAL_ENTRY_KIND",
    "JournalKind",
    "TagOrigin",
    "COUNTED_TAG_ORIGINS",
    "JournalTag",
    "LinkKind",
    "JournalLink",
    "ReviewStatus",
    "JournalEntry",
    "TradeJournal",
]

JOURNAL_ENTRY_SCHEMA_VERSION = 1
SUPPORTED_JOURNAL_ENTRY_VERSIONS = frozenset({1})
JOURNAL_ENTRY_TYPE_SLUG = "journal_entry"
JOURNAL_ENTRY_KIND = "journal_entry"


class JournalError(TradeDomainError):
    """Base class for every journal failure."""


class JournalKind(Enum):
    """Three kinds, and no more.

    *"Before"* and *"after"* are not kinds: they are derivable from the linked
    decision's own timestamps, and the recollection property already marks the
    hindsight case automatically. Adding them would be three more required
    choices at write time, against an entity whose only real failure mode is not
    being written.
    """

    IDEA = "idea"
    NOTE = "note"
    REVIEW = "review"


class TagOrigin(Enum):
    """Who applied a tag — and therefore whether it may be counted."""

    OWNER = "owner"
    AI_PROPOSED_CONFIRMED = "ai_proposed_confirmed"
    IMPORTED = "imported"
    #: Proposed by a model and not yet confirmed. **Never counted in any cohort.**
    AI_PROPOSED_PENDING = "ai_proposed_pending"


#: The three origins a statistic may include. `AI_PROPOSED_PENDING` is absent, so
#: unconfirmed model output can never train the next model.
COUNTED_TAG_ORIGINS: frozenset[TagOrigin] = frozenset(
    {TagOrigin.OWNER, TagOrigin.AI_PROPOSED_CONFIRMED, TagOrigin.IMPORTED}
)


@dataclass(frozen=True, slots=True)
class JournalTag:
    """One vocabulary term applied to an entry, with who applied it."""

    term: VersionedTerm
    origin: TagOrigin
    applied_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.term, VersionedTerm):
            raise TypeError(
                "term must be a VersionedTerm; an untyped string tag is a word "
                "that can be silently redefined under a statistic"
            )
        require_member(self.origin, TagOrigin, "origin")
        object.__setattr__(
            self, "applied_at", require_utc(self.applied_at, "applied_at")
        )

    @property
    def is_counted(self) -> bool:
        return self.origin in COUNTED_TAG_ORIGINS

    @property
    def value_origin(self) -> ValueOrigin:
        if self.origin is TagOrigin.OWNER:
            return ValueOrigin.ASSERTED
        if self.origin is TagOrigin.IMPORTED:
            return ValueOrigin.ASSERTED
        return ValueOrigin.INTERPRETED

    def to_payload(self) -> dict[str, Any]:
        return {
            "term": self.term.to_payload(),
            "origin": self.origin.value,
            "applied_at": encode_timestamp(self.applied_at),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> JournalTag:
        mapping = require_mapping(raw, "tag")
        require_exact_keys(mapping, {"term", "origin", "applied_at"}, "tag")
        return cls(
            term=VersionedTerm.from_payload(mapping["term"]),
            origin=_member(TagOrigin, mapping["origin"], "tag origin"),
            applied_at=decode_timestamp(mapping["applied_at"]),
        )


class LinkKind(Enum):
    """Six typed, directional edges. Never one untyped `related`."""

    ABOUT = "about"
    CAUSED_BY = "caused_by"
    REVIEWS = "reviews"
    SUPERSEDES = "supersedes"
    LEARNED_FROM = "learned_from"
    CITES = "cites"


@dataclass(frozen=True, slots=True, order=True)
class JournalLink:
    """One typed edge from an entry to something else in the system."""

    kind: LinkKind
    target_kind: str
    target_id: str

    def __post_init__(self) -> None:
        require_member(self.kind, LinkKind, "kind")
        object.__setattr__(
            self, "target_kind", require_text(self.target_kind, "target_kind")
        )
        object.__setattr__(self, "target_id", require_text(self.target_id, "target_id"))

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> JournalLink:
        mapping = require_mapping(raw, "link")
        require_exact_keys(mapping, {"kind", "target_kind", "target_id"}, "link")
        return cls(
            kind=_member(LinkKind, mapping["kind"], "link kind"),
            target_kind=str(mapping["target_kind"]),
            target_id=str(mapping["target_id"]),
        )


class ReviewStatus(Enum):
    """Whether the owner has come back to this entry."""

    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    NEEDS_FOLLOW_UP = "needs_follow_up"


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """One typed, linked, authored note — the only source of the owner's own state."""

    kind: JournalKind
    recorded_at: datetime
    author: str
    audit: RecordAudit
    title: str | Absent = field(default_factory=lambda: Absent("no title"))
    body: str | Absent = field(default_factory=lambda: Absent("no body"))
    period: str | Absent = field(default_factory=lambda: Absent("not a period review"))
    market_snapshot_id: str | Absent = field(
        default_factory=lambda: Absent("no market context was frozen")
    )
    portfolio_snapshot_id: str | Absent = field(
        default_factory=lambda: Absent("no portfolio context was frozen")
    )
    decision_resolved_at: datetime | Absent = field(
        default_factory=lambda: Absent("this entry concerns no resolved decision")
    )
    tags: tuple[JournalTag, ...] = ()
    links: tuple[JournalLink, ...] = ()
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    session_id: str | Absent = field(default_factory=lambda: Absent("no session"))
    supersedes: str | Absent = field(default_factory=lambda: Absent("supersedes nothing"))
    schema_version: int = JOURNAL_ENTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_member(self.kind, JournalKind, "kind")
        object.__setattr__(
            self, "recorded_at", require_utc(self.recorded_at, "recorded_at")
        )
        object.__setattr__(self, "author", require_text(self.author, "author"))
        if not isinstance(self.audit, RecordAudit):
            raise TypeError("audit must be a RecordAudit")
        if self.audit.created_at != self.recorded_at:
            raise DomainValidationError(
                "audit.created_at must equal recorded_at; an entry is created when "
                "it is written"
            )
        for name in ("title", "body", "period", "session_id"):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, require_text(value, name))
        for name in ("market_snapshot_id", "portfolio_snapshot_id", "supersedes"):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                validate_domain_record_id(value)
        if not isinstance(self.decision_resolved_at, Absent):
            object.__setattr__(
                self,
                "decision_resolved_at",
                require_utc(self.decision_resolved_at, "decision_resolved_at"),
            )
        require_tuple_of(self.tags, JournalTag, "tags")
        require_tuple_of(self.links, JournalLink, "links")
        if len(set(self.links)) != len(self.links):
            raise DomainValidationError("a link must not be recorded twice")
        require_member(self.review_status, ReviewStatus, "review_status")
        if self.schema_version not in SUPPORTED_JOURNAL_ENTRY_VERSIONS:
            raise DomainValidationError(
                f"journal entry schema_version {self.schema_version} is not one "
                f"this build writes ({sorted(SUPPORTED_JOURNAL_ENTRY_VERSIONS)})"
            )
        self._validate_kind_rules()

    def _validate_kind_rules(self) -> None:
        """Required: almost nothing. Everything else is nudged, never enforced."""
        has_title = not isinstance(self.title, Absent)
        has_body = not isinstance(self.body, Absent)
        if self.kind is JournalKind.IDEA and not (has_title and has_body):
            raise DomainValidationError(
                "an IDEA carries a title and a body; an idea with neither is an "
                "empty row that will look like a written journal in every count"
            )
        if self.kind is JournalKind.NOTE and not (has_title or has_body):
            raise DomainValidationError("a NOTE carries a title or a body")
        if self.kind is JournalKind.REVIEW:
            if not (has_title and has_body):
                raise DomainValidationError("a REVIEW carries a title and a body")
            if isinstance(self.period, Absent):
                raise DomainValidationError(
                    "a REVIEW names the period it reviews; a review of nothing in "
                    "particular cannot be cohorted"
                )
        if self.kind is not JournalKind.REVIEW and not isinstance(self.period, Absent):
            raise DomainValidationError(
                f"a {self.kind.value} entry does not carry a review period"
            )

    # -- projections ---------------------------------------------------------

    @property
    def recollection(self) -> bool:
        """Whether this was written *after* the decision it concerns resolved.

        **Derived, never set.** There is no constructor argument for it, so the
        owner cannot mark their own hindsight as foresight, and a model cannot set
        it at all.
        """
        if isinstance(self.decision_resolved_at, Absent):
            return False
        return self.recorded_at > self.decision_resolved_at

    @property
    def counted_tags(self) -> tuple[JournalTag, ...]:
        """Tags a statistic may include — unconfirmed model output excluded."""
        return tuple(tag for tag in self.tags if tag.is_counted)

    @property
    def pending_tags(self) -> tuple[JournalTag, ...]:
        return tuple(tag for tag in self.tags if not tag.is_counted)

    def links_of(self, kind: LinkKind) -> tuple[JournalLink, ...]:
        require_member(kind, LinkKind, "kind")
        return tuple(link for link in self.links if link.kind is kind)

    def with_tag(self, tag: JournalTag) -> JournalEntry:
        """Append a tag, producing a **new** entry with an advanced audit block.

        Appending is the only update story an entry has: `tags` and `links` grow,
        and nothing else ever changes. A changed opinion is a new entry with
        `supersedes`.
        """
        if not isinstance(tag, JournalTag):
            raise TypeError("tag must be a JournalTag")
        if any(existing.term == tag.term for existing in self.tags):
            raise DomainValidationError(
                f"{tag.term.qualified_id} is already applied to this entry"
            )
        return _replace(
            self,
            tags=self.tags + (tag,),
            audit=self.audit.appended_at(tag.applied_at),
        )

    def with_link(self, link: JournalLink, *, at: datetime) -> JournalEntry:
        """Append a typed link, producing a new entry with an advanced audit block."""
        if not isinstance(link, JournalLink):
            raise TypeError("link must be a JournalLink")
        if link in self.links:
            raise DomainValidationError("that link is already recorded")
        return _replace(
            self,
            links=self.links + (link,),
            audit=self.audit.appended_at(require_utc(at, "at")),
        )

    # -- identity and serialization -----------------------------------------

    @property
    def digest_basis(self) -> dict[str, Any]:
        """The entry's own content. `tags` and `links` append and are excluded.

        Excluding them keeps the id stable while an entry accumulates tags —
        otherwise confirming a tag in 2027 would re-key a 2026 entry and break
        every link pointing at it.
        """
        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "recorded_at": encode_timestamp(self.recorded_at),
            "author": self.author,
            "title": encode_maybe(self.title, str),
            "body": encode_maybe(self.body, str),
            "period": encode_maybe(self.period, str),
            "market_snapshot_id": encode_maybe(self.market_snapshot_id, str),
            "portfolio_snapshot_id": encode_maybe(self.portfolio_snapshot_id, str),
            "decision_resolved_at": encode_maybe(
                self.decision_resolved_at, encode_timestamp
            ),
            "session_id": encode_maybe(self.session_id, str),
            "supersedes": encode_maybe(self.supersedes, str),
        }

    @property
    def entry_id(self) -> str:
        return build_domain_record_id(
            type_slug=JOURNAL_ENTRY_TYPE_SLUG,
            subject=self.kind.value,
            moment=self.recorded_at,
            digest=content_digest_over(self.digest_basis),
        )

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload.update(
            {
                "entry_id": self.entry_id,
                "tags": [tag.to_payload() for tag in self.tags],
                "links": [link.to_payload() for link in self.links],
                "review_status": self.review_status.value,
                "audit": self.audit.to_payload(),
            }
        )
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> JournalEntry:
        mapping = require_mapping(raw, "journal entry")
        version = require_payload_version(
            mapping,
            supported=SUPPORTED_JOURNAL_ENTRY_VERSIONS,
            entity="journal entry",
        )
        require_exact_keys(
            mapping,
            {
                "schema_version",
                "entry_id",
                "kind",
                "recorded_at",
                "author",
                "title",
                "body",
                "period",
                "market_snapshot_id",
                "portfolio_snapshot_id",
                "decision_resolved_at",
                "session_id",
                "supersedes",
                "tags",
                "links",
                "review_status",
                "audit",
            },
            "journal entry",
        )
        decoded = cls(
            kind=_member(JournalKind, mapping["kind"], "kind"),
            recorded_at=decode_timestamp(mapping["recorded_at"]),
            author=str(mapping["author"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            title=decode_maybe(mapping["title"], str),
            body=decode_maybe(mapping["body"], str),
            period=decode_maybe(mapping["period"], str),
            market_snapshot_id=decode_maybe(mapping["market_snapshot_id"], str),
            portfolio_snapshot_id=decode_maybe(mapping["portfolio_snapshot_id"], str),
            decision_resolved_at=decode_maybe(
                mapping["decision_resolved_at"], decode_timestamp
            ),
            tags=tuple(
                JournalTag.from_payload(item)
                for item in _array(mapping["tags"], "tags")
            ),
            links=tuple(
                JournalLink.from_payload(item)
                for item in _array(mapping["links"], "links")
            ),
            review_status=_member(
                ReviewStatus, mapping["review_status"], "review_status"
            ),
            session_id=decode_maybe(mapping["session_id"], str),
            supersedes=decode_maybe(mapping["supersedes"], str),
            schema_version=version,
        )
        if mapping["entry_id"] != decoded.entry_id:
            raise PayloadDecodeError(
                f"entry_id {mapping['entry_id']!r} does not match the digest of "
                f"the entry it claims to identify ({decoded.entry_id!r})"
            )
        return decoded


def _replace(entry: JournalEntry, **changes: Any) -> JournalEntry:
    values: dict[str, Any] = {
        "kind": entry.kind,
        "recorded_at": entry.recorded_at,
        "author": entry.author,
        "audit": entry.audit,
        "title": entry.title,
        "body": entry.body,
        "period": entry.period,
        "market_snapshot_id": entry.market_snapshot_id,
        "portfolio_snapshot_id": entry.portfolio_snapshot_id,
        "decision_resolved_at": entry.decision_resolved_at,
        "tags": entry.tags,
        "links": entry.links,
        "review_status": entry.review_status,
        "session_id": entry.session_id,
        "supersedes": entry.supersedes,
        "schema_version": entry.schema_version,
    }
    values.update(changes)
    return JournalEntry(**values)


@dataclass(frozen=True, slots=True)
class TradeJournal:
    """Every entry linked to one subject — a **read-time view**, stored nowhere.

    This is the brief's *TradeJournal*, and modelling it as a projection rather
    than a record is what keeps it from becoming a second place an entry can live.
    Delete it and rebuild it from the entries and the answer is identical.

    *"Whether an entry exists at all for a decision is the cheapest discipline
    metric in the system"* — and `is_empty` is that metric.
    """

    subject_kind: str
    subject_id: str
    entries: tuple[JournalEntry, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "subject_kind", require_text(self.subject_kind, "subject_kind")
        )
        object.__setattr__(
            self, "subject_id", require_text(self.subject_id, "subject_id")
        )
        require_tuple_of(self.entries, JournalEntry, "entries")
        for entry in self.entries:
            if not any(
                link.target_id == self.subject_id
                and link.target_kind == self.subject_kind
                for link in entry.links
            ):
                raise DomainValidationError(
                    f"entry {entry.entry_id} carries no link to "
                    f"{self.subject_kind} {self.subject_id}; a journal view holds "
                    "only what actually points at its subject"
                )
        object.__setattr__(
            self,
            "entries",
            tuple(sorted(self.entries, key=lambda item: (item.recorded_at, item.entry_id))),
        )

    @classmethod
    def gather(
        cls, subject_kind: str, subject_id: str, entries: Iterable[JournalEntry]
    ) -> TradeJournal:
        """Build the view by selecting the entries that link to the subject."""
        kind = require_text(subject_kind, "subject_kind")
        identifier = require_text(subject_id, "subject_id")
        selected = tuple(
            entry
            for entry in entries
            if any(
                link.target_id == identifier and link.target_kind == kind
                for link in entry.links
            )
        )
        return cls(subject_kind=kind, subject_id=identifier, entries=selected)

    @property
    def is_empty(self) -> bool:
        """Nothing was written about this subject. The cheapest discipline metric."""
        return not self.entries

    @property
    def excluding_recollections(self) -> tuple[JournalEntry, ...]:
        """What a cohort statistic may read by default."""
        return tuple(entry for entry in self.entries if not entry.recollection)

    @property
    def recollections(self) -> tuple[JournalEntry, ...]:
        return tuple(entry for entry in self.entries if entry.recollection)

    @property
    def counted_tags(self) -> tuple[JournalTag, ...]:
        """Every countable tag across the view, in a stable order."""
        gathered: list[JournalTag] = []
        for entry in self.entries:
            gathered.extend(entry.counted_tags)
        return tuple(
            sorted(gathered, key=lambda tag: (tag.term.qualified_id, tag.applied_at))
        )

    def of_kind(self, kind: JournalKind) -> tuple[JournalEntry, ...]:
        require_member(kind, JournalKind, "kind")
        return tuple(entry for entry in self.entries if entry.kind is kind)


def _array(raw: Any, entity: str) -> list[Any]:
    if not isinstance(raw, list):
        raise PayloadDecodeError(
            f"journal {entity} must be a JSON array, got {type(raw).__name__}"
        )
    return raw


def _member(enum_type: Any, value: Any, entity: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise PayloadDecodeError(
            f"{entity} {value!r} is not a known {enum_type.__name__}"
        ) from error
