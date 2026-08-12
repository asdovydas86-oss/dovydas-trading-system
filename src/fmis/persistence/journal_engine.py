"""The write journal: what the store did to itself, hash-chained and append-only.

**This is not `fmis.journal`.** That package holds `JournalEntry` — the owner's own
words, typed and tagged, a source of truth about a person. This one holds
`JournalEvent` — one line per write the store performed, a source of truth about
the store. They share a word and nothing else, and the two names never collide.

Every write to any repository appends exactly one event, carrying the six things
the milestone requires — **timestamp, source, author, reason, version,
provenance** — plus the three the store needs to make them useful: which record,
which kind, and which digest. There is no write path that does not go through
`RecordStore.publish`, and no `publish` that does not append here.

**The chain is what makes "nothing is rewritten" checkable rather than promised.**
Each event's digest covers its predecessor's id. Remove an event, alter a field,
or reorder two lines, and every event after the change fails verification with the
first broken link named. An append-only file that is merely *opened* in append mode
is honest about the writer; a hash chain is honest about the file.

**Filing time is monotonic, and that is enforced.** A record may be backfilled —
a trade that happened in 2024 is filed with `occurred_at` in 2024 — but the
*journal event* recording that filing happens now. An event that claims to precede
the current head is refused, because an audit trail that can be inserted into in
the middle is not one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.provenance import Absent, VersionedTerm, decode_maybe, encode_maybe
from fmis.records import (
    ConsumedSource,
    build_domain_record_id,
    content_digest_over,
    decode_consumed_sources,
    encode_consumed_sources,
    normalize_consumed_sources,
    require_exact_keys,
    require_int,
    require_mapping,
    require_member,
    require_payload_version,
    require_text,
    require_utc,
    validate_domain_record_id,
)
from fmis.versioning import VersionSet

from fmis.persistence.appendonly import append_lines, line_count, read_lines
from fmis.persistence.envelope import decode_line, encode_line
from fmis.persistence.errors import (
    AppendOnlyViolationError,
    PersistenceError,
    StoreIntegrityError,
)
from fmis.persistence.kinds import RecordKind, kind_of
from fmis.persistence.layout import StoreLayout

__all__ = [
    "JOURNAL_EVENT_SCHEMA_VERSION",
    "SUPPORTED_JOURNAL_EVENT_VERSIONS",
    "JOURNAL_EVENT_TYPE_SLUG",
    "WriteSource",
    "WriteOperation",
    "JournalEvent",
    "JournalVerification",
    "JournalEngine",
]

JOURNAL_EVENT_SCHEMA_VERSION = 1
SUPPORTED_JOURNAL_EVENT_VERSIONS = frozenset({1})

#: Distinct from every domain type slug — asserted by a test, because a collision
#: would let a journal event id parse as a record id and vice versa.
JOURNAL_EVENT_TYPE_SLUG = "journal_event"


class WriteSource(Enum):
    """How the write entered FMITS. A closed vocabulary.

    Mirrors `fmis.ledger.LedgerSource` where the two overlap and adds the three
    ways a write can originate inside the system rather than outside it. Recorded
    per *write*, not per record: the same trade typed by hand and later confirmed
    by an exchange sync is one record and two journal events, and the second one
    is how anybody ever learns the sync ran.
    """

    OWNER = "owner"
    STATEMENT_IMPORT = "statement_import"
    EXCHANGE_API = "exchange_api"
    POLICY_ENGINE = "policy_engine"
    MODEL = "model"
    REBUILD = "rebuild"
    MIGRATION = "migration"


class WriteOperation(Enum):
    """What the write meant. Never what it did to the bytes — that is always
    "appended one immutable record".

    `SUPERSEDE` does not rewrite anything. It records that the record being written
    claims to replace an earlier one, which is the only form an update takes in
    this system.
    """

    CREATE = "create"
    SUPERSEDE = "supersede"
    APPEND = "append"


@dataclass(frozen=True, slots=True)
class JournalEvent:
    """One write, fully described and linked to the one before it."""

    sequence: int
    occurred_at: datetime
    source: WriteSource
    author: str
    reason: VersionedTerm
    version_set: VersionSet
    operation: WriteOperation
    record_kind: RecordKind
    record_id: str
    content_digest: str
    previous_event_id: str | Absent
    provenance: tuple[ConsumedSource, ...] = ()
    supersedes: str | Absent = field(
        default_factory=lambda: Absent("this write supersedes nothing")
    )
    note: str | Absent = field(default_factory=lambda: Absent("no note"))
    schema_version: int = JOURNAL_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_int(self.sequence, "sequence", minimum=0)
        object.__setattr__(
            self, "occurred_at", require_utc(self.occurred_at, "occurred_at")
        )
        require_member(self.source, WriteSource, "source")
        object.__setattr__(self, "author", require_text(self.author, "author"))
        if not isinstance(self.reason, VersionedTerm):
            raise TypeError(
                "reason must be a VersionedTerm; an untagged write cannot be "
                "counted, and 'why did this record appear' is the question the "
                "journal exists to answer"
            )
        if not isinstance(self.version_set, VersionSet):
            raise TypeError("version_set must be a VersionSet")
        require_member(self.operation, WriteOperation, "operation")
        require_member(self.record_kind, RecordKind, "record_kind")
        object.__setattr__(self, "record_id", require_text(self.record_id, "record_id"))
        digest = require_text(self.content_digest, "content_digest")
        if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
            raise StoreIntegrityError(
                f"content_digest must be a 'sha256:<64 hex>' string, got {digest!r}"
            )
        object.__setattr__(self, "content_digest", digest)
        if not isinstance(self.previous_event_id, Absent):
            validate_domain_record_id(self.previous_event_id)
        elif self.sequence != 0:
            raise StoreIntegrityError(
                f"event {self.sequence} names no predecessor; only the first event "
                "in a store has none, and a later one without a link is a broken "
                "chain rather than a beginning"
            )
        if self.sequence == 0 and not isinstance(self.previous_event_id, Absent):
            raise StoreIntegrityError(
                "the first event in a store has no predecessor to name"
            )
        object.__setattr__(
            self, "provenance", normalize_consumed_sources(self.provenance)
        )
        if not isinstance(self.supersedes, Absent):
            object.__setattr__(
                self, "supersedes", require_text(self.supersedes, "supersedes")
            )
            if self.operation is not WriteOperation.SUPERSEDE:
                raise PersistenceError(
                    f"this write names a record it supersedes but its operation is "
                    f"{self.operation.value}; a supersession that is not recorded as "
                    "one is invisible to every later reader of the chain"
                )
        elif self.operation is WriteOperation.SUPERSEDE:
            raise PersistenceError(
                "a SUPERSEDE write must name the record it supersedes"
            )
        if not isinstance(self.note, Absent):
            object.__setattr__(self, "note", require_text(self.note, "note"))
        if self.schema_version not in SUPPORTED_JOURNAL_EVENT_VERSIONS:
            raise StoreIntegrityError(
                f"journal event schema_version {self.schema_version} is not one "
                f"this build writes ({sorted(SUPPORTED_JOURNAL_EVENT_VERSIONS)})"
            )

    # -- identity ------------------------------------------------------------

    @property
    def digest_basis(self) -> dict[str, Any]:
        """Every field, including the link. Nothing here is filing metadata.

        A record's digest excludes when it was filed; a *journal event* is the
        filing, so its timestamp is content. `previous_event_id` is in the basis
        because that is what makes this a chain rather than a list.
        """
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "occurred_at": encode_timestamp(self.occurred_at),
            "source": self.source.value,
            "author": self.author,
            "reason": self.reason.to_payload(),
            "version_set": self.version_set.to_payload(),
            "operation": self.operation.value,
            "record_kind": self.record_kind.value,
            "record_id": self.record_id,
            "content_digest": self.content_digest,
            "previous_event_id": encode_maybe(self.previous_event_id, str),
            "provenance": encode_consumed_sources(self.provenance),
            "supersedes": encode_maybe(self.supersedes, str),
            "note": encode_maybe(self.note, str),
        }

    @property
    def event_id(self) -> str:
        return build_domain_record_id(
            type_slug=JOURNAL_EVENT_TYPE_SLUG,
            subject=self.operation.value,
            moment=self.occurred_at,
            digest=content_digest_over(self.digest_basis),
        )

    @property
    def content_chain_digest(self) -> str:
        return content_digest_over(self.digest_basis)

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload["event_id"] = self.event_id
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> JournalEvent:
        mapping = require_mapping(raw, "journal event")
        version = require_payload_version(
            mapping, supported=SUPPORTED_JOURNAL_EVENT_VERSIONS, entity="journal event"
        )
        require_exact_keys(mapping, _EVENT_KEYS, "journal event")
        decoded = cls(
            sequence=mapping["sequence"],
            occurred_at=decode_timestamp(mapping["occurred_at"]),
            source=_member(WriteSource, mapping["source"], "source"),
            author=str(mapping["author"]),
            reason=VersionedTerm.from_payload(mapping["reason"]),
            version_set=VersionSet.from_payload(mapping["version_set"]),
            operation=_member(WriteOperation, mapping["operation"], "operation"),
            record_kind=kind_of(mapping["record_kind"]),
            record_id=str(mapping["record_id"]),
            content_digest=str(mapping["content_digest"]),
            previous_event_id=decode_maybe(mapping["previous_event_id"], str),
            provenance=decode_consumed_sources(mapping["provenance"]),
            supersedes=decode_maybe(mapping["supersedes"], str),
            note=decode_maybe(mapping["note"], str),
            schema_version=version,
        )
        if mapping["event_id"] != decoded.event_id:
            raise StoreIntegrityError(
                f"journal event_id {mapping['event_id']!r} does not match the "
                f"digest of the event it claims to identify ({decoded.event_id!r}); "
                "a field has been altered since it was written"
            )
        return decoded


_EVENT_KEYS = frozenset(
    {
        "schema_version",
        "event_id",
        "sequence",
        "occurred_at",
        "source",
        "author",
        "reason",
        "version_set",
        "operation",
        "record_kind",
        "record_id",
        "content_digest",
        "previous_event_id",
        "provenance",
        "supersedes",
        "note",
    }
)


@dataclass(frozen=True, slots=True)
class JournalVerification:
    """What a full chain walk found. Problems are reported, never repaired."""

    ok: bool
    event_count: int = 0
    #: Every defect, in the order the walk met them, each naming the sequence
    #: number it was found at so a human can go straight to the line.
    problems: tuple[str, ...] = ()

    @property
    def head_sequence(self) -> int | None:
        return self.event_count - 1 if self.event_count else None


class JournalEngine:
    """The append-only, hash-chained record of every write this store performed."""

    def __init__(self, layout: StoreLayout) -> None:
        if not isinstance(layout, StoreLayout):
            raise TypeError("layout must be a StoreLayout")
        self._layout = layout

    @property
    def layout(self) -> StoreLayout:
        return self._layout

    # -- reading -------------------------------------------------------------

    def events(self) -> tuple[JournalEvent, ...]:
        """Every event, in sequence order, with the chain verified as it is read.

        Verification happens here rather than in a separate opt-in method because
        an unverified read of an audit trail is worth very little: a caller who
        forgets to verify gets exactly the reassurance a tampered chain is designed
        to give them.
        """
        found = self._read_all()
        self._require_intact(found)
        return found

    def head(self) -> JournalEvent | None:
        """The most recent event, read without walking the whole chain.

        The head lives in the latest year file's last line, because filing time is
        monotonic and `append` enforces it.
        """
        years = self._layout.journal_years()
        if not years:
            return None
        latest = years[-1]
        lines = read_lines(self._layout.resolve_within_root(f"journal/{latest}.jsonl"))
        if not lines:  # pragma: no cover - append never creates an empty year file
            return None
        return JournalEvent.from_payload(
            decode_line(lines[-1], line_number=len(lines))
        )

    def events_for(self, record_id: str) -> tuple[JournalEvent, ...]:
        """Every write that touched one record — the record's own audit trail."""
        wanted = require_text(record_id, "record_id")
        return tuple(event for event in self.events() if event.record_id == wanted)

    def events_between(
        self, *, since: datetime | None = None, until: datetime | None = None
    ) -> tuple[JournalEvent, ...]:
        """Every write filed in a closed interval — the "as known at" axis."""
        lower = None if since is None else require_utc(since, "since")
        upper = None if until is None else require_utc(until, "until")
        if lower is not None and upper is not None and upper < lower:
            raise PersistenceError(
                f"until {upper.isoformat()} precedes since {lower.isoformat()}"
            )
        return tuple(
            event
            for event in self.events()
            if (lower is None or event.occurred_at >= lower)
            and (upper is None or event.occurred_at <= upper)
        )

    def verify(self) -> JournalVerification:
        """Walk the whole chain, reporting every defect as a result rather than a raise."""
        try:
            found = self._read_all()
        except PersistenceError as error:
            return JournalVerification(ok=False, problems=(str(error),))
        problems = self._chain_problems(found)
        return JournalVerification(
            ok=not problems, event_count=len(found), problems=tuple(problems)
        )

    # -- writing -------------------------------------------------------------

    def append(
        self,
        *,
        occurred_at: datetime,
        source: WriteSource,
        author: str,
        reason: VersionedTerm,
        version_set: VersionSet,
        operation: WriteOperation,
        record_kind: RecordKind,
        record_id: str,
        content_digest: str,
        provenance: Iterable[ConsumedSource] = (),
        supersedes: str | Absent | None = None,
        note: str | Absent | None = None,
    ) -> JournalEvent:
        """Link one new event onto the head and publish it.

        The caller supplies `occurred_at`; nothing in this package reads a clock.
        That is the same rule the domain follows and for the same reason — a store
        that stamps itself cannot be replayed, and a test that has to freeze a
        clock is a test that will eventually be flaky instead of wrong.
        """
        moment = require_utc(occurred_at, "occurred_at")
        current = self.head()
        if current is None:
            sequence = 0
            previous: str | Absent = Absent("this is the first write to this store")
        else:
            if moment < current.occurred_at:
                raise AppendOnlyViolationError(
                    f"this write is filed at {moment.isoformat()}, before the "
                    f"journal head at {current.occurred_at.isoformat()}. A record "
                    "may be backfilled; the act of filing it happens now, and an "
                    "audit trail that can be inserted into in the middle is not one"
                )
            sequence = current.sequence + 1
            previous = current.event_id
        event = JournalEvent(
            sequence=sequence,
            occurred_at=moment,
            source=source,
            author=author,
            reason=reason,
            version_set=version_set,
            operation=operation,
            record_kind=record_kind,
            record_id=record_id,
            content_digest=content_digest,
            previous_event_id=previous,
            provenance=tuple(provenance),
            supersedes=(
                Absent("this write supersedes nothing") if supersedes is None
                else supersedes
            ),
            note=Absent("no note") if note is None else note,
        )
        path = self._layout.journal_path(moment)
        append_lines(
            path,
            (encode_line(event.to_payload()),),
            expected_existing=line_count(path),
        )
        return event

    # -- internals -----------------------------------------------------------

    def _read_all(self) -> tuple[JournalEvent, ...]:
        found: list[JournalEvent] = []
        for year in self._layout.journal_years():
            path = self._layout.resolve_within_root(f"journal/{year}.jsonl")
            for number, line in enumerate(read_lines(path), start=1):
                found.append(
                    JournalEvent.from_payload(decode_line(line, line_number=number))
                )
        return tuple(found)

    def _chain_problems(self, found: tuple[JournalEvent, ...]) -> list[str]:
        problems: list[str] = []
        previous: JournalEvent | None = None
        for position, event in enumerate(found):
            if event.sequence != position:
                problems.append(
                    f"event at position {position} claims sequence {event.sequence}; "
                    "an event has been removed, reordered or inserted"
                )
            if previous is None:
                if not isinstance(event.previous_event_id, Absent):
                    problems.append(
                        f"event {event.sequence} is first but names a predecessor"
                    )
            else:
                if isinstance(event.previous_event_id, Absent):
                    problems.append(
                        f"event {event.sequence} names no predecessor but is not first"
                    )
                elif event.previous_event_id != previous.event_id:
                    problems.append(
                        f"event {event.sequence} links to "
                        f"{event.previous_event_id!r}, but the event before it is "
                        f"{previous.event_id!r}; the chain is broken here"
                    )
                if event.occurred_at < previous.occurred_at:
                    problems.append(
                        f"event {event.sequence} is filed before event "
                        f"{previous.sequence}; filing time never moves backwards"
                    )
            previous = event
        return problems

    def _require_intact(self, found: tuple[JournalEvent, ...]) -> None:
        problems = self._chain_problems(found)
        if problems:
            raise StoreIntegrityError(
                "the write journal does not verify: " + "; ".join(problems)
            )


def _member(enum_type: Any, value: Any, entity: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise StoreIntegrityError(
            f"{entity} {value!r} is not a known {enum_type.__name__}; an unknown "
            "member is a clean rejection, never a default"
        ) from error
