"""`RecordStore` — the one thing that writes, and the only way to read what it wrote.

Every repository in this package is a typed face over this class. There is no
second write path, which is what makes the write journal complete rather than
mostly complete: a record that reached disk without a journal event would have to
have been written by code that does not exist.

**The publish sequence, and what a crash between any two steps leaves behind.**

1. **Payload.** A record file is published atomically (`os.replace`); a log line is
   appended with `O_APPEND`. Crash here: nothing, or a complete record nobody
   indexed. `verify()` reports it as an orphan and republishing is idempotent,
   because the bytes are a pure function of the content.
2. **Journal.** One event, linked to the previous one. Crash here: the record and
   its audit trail exist, the index does not. `verify()` reports it and
   `rebuild_index()` repairs it — the index is the only rebuildable thing in the
   store, and this is why.
3. **Index.** The lookup row. Crash after: nothing was lost.

The order is deliberate. The journal is written *before* the index because the
journal is truth and the index is a projection of it; the reverse order would
produce an indexed record with no audit trail, which nothing can repair.

**Identical content is an idempotent success, never a second record.** Re-entering
a fill after a crash, re-running a scan that produces the same snapshot, or
importing the same statement twice all resolve to `created=False` and no new
journal event — because nothing changed, and an audit trail that records
non-events dilutes the ones that matter.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fmis.archive.atomic import atomic_write
from fmis.archive.errors import ArchiveError
from fmis.provenance import Absent, VersionedTerm
from fmis.records import (
    ConsumedSource,
    TradeDomainError,
    require_member,
    require_text,
    require_utc,
)
from fmis.versioning import VersionSet

from fmis.persistence.appendonly import append_lines, read_lines
from fmis.persistence.envelope import (
    StoredEnvelope,
    decode_envelope_bytes,
    decode_line,
    encode_envelope_bytes,
    encode_line,
)
from fmis.persistence.errors import (
    FrozenRecordError,
    LineageError,
    PersistenceError,
    RecordConflictError,
    RecordMissingError,
    StoreIntegrityError,
    StoreIOError,
)
from fmis.persistence.index import IndexEntry, RecordIndex
from fmis.persistence.journal_engine import (
    JournalEngine,
    JournalEvent,
    WriteOperation,
    WriteSource,
)
from fmis.persistence.kinds import (
    DurabilityClass,
    RecordKind,
    RecordSpec,
    SPECS,
    StorageShape,
    spec_for_record,
)
from fmis.persistence.layout import StoreLayout

__all__ = [
    "WriteRequest",
    "WriteReceipt",
    "RecordCheck",
    "StoreVerification",
    "RecordStore",
]


@dataclass(frozen=True, slots=True)
class WriteRequest:
    """Why this write is happening, and everything the journal event needs.

    Required on every write, with no default anywhere that matters. A default
    author is an unattributable record; a default reason is an uncountable one; a
    default `written_at` is a clock inside the store. The one thing a caller may
    omit is `provenance`, because a record that read nothing genuinely read
    nothing.
    """

    written_at: datetime
    source: WriteSource
    author: str
    reason: VersionedTerm
    version_set: VersionSet
    operation: WriteOperation = WriteOperation.CREATE
    provenance: tuple[ConsumedSource, ...] = ()
    note: str | Absent = field(default_factory=lambda: Absent("no note"))

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "written_at", require_utc(self.written_at, "written_at")
        )
        require_member(self.source, WriteSource, "source")
        object.__setattr__(self, "author", require_text(self.author, "author"))
        if not isinstance(self.reason, VersionedTerm):
            raise TypeError("reason must be a VersionedTerm")
        if not isinstance(self.version_set, VersionSet):
            raise TypeError("version_set must be a VersionSet")
        require_member(self.operation, WriteOperation, "operation")
        if not isinstance(self.provenance, tuple):
            raise TypeError("provenance must be a tuple of ConsumedSource")
        for source in self.provenance:
            if not isinstance(source, ConsumedSource):
                raise TypeError("provenance must be a tuple of ConsumedSource")
        if not isinstance(self.note, Absent):
            object.__setattr__(self, "note", require_text(self.note, "note"))

    def superseding(self) -> WriteRequest:
        """The same request, recorded as a supersession."""
        return WriteRequest(
            written_at=self.written_at,
            source=self.source,
            author=self.author,
            reason=self.reason,
            version_set=self.version_set,
            operation=WriteOperation.SUPERSEDE,
            provenance=self.provenance,
            note=self.note,
        )

    def appending(self) -> WriteRequest:
        """The same request, recorded as an append to an existing stream."""
        return WriteRequest(
            written_at=self.written_at,
            source=self.source,
            author=self.author,
            reason=self.reason,
            version_set=self.version_set,
            operation=WriteOperation.APPEND,
            provenance=self.provenance,
            note=self.note,
        )


@dataclass(frozen=True, slots=True)
class WriteReceipt:
    """What a successful publish returns.

    `created` is false when the identical record was already stored. A caller that
    treats that as a failure is wrong, and a caller that cannot tell the difference
    would count every crash-recovery re-entry as a new fill.
    """

    record_id: str
    kind: RecordKind
    content_digest: str
    relative_path: str
    created: bool
    journal_event: JournalEvent | None = None


@dataclass(frozen=True, slots=True)
class RecordCheck:
    """The result of verifying one stored record."""

    record_id: str
    ok: bool
    problems: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StoreVerification:
    """Everything a full sweep found, by category. Reported, never repaired."""

    ok: bool
    indexed_count: int = 0
    journal_event_count: int = 0
    #: The write journal's own chain problems, verbatim.
    journal_problems: tuple[str, ...] = ()
    #: Indexed records whose payload is not where the index says it is.
    missing_payloads: tuple[str, ...] = ()
    #: Indexed records whose stored bytes no longer produce what they claim.
    integrity_failures: tuple[str, ...] = ()
    #: Stored payloads no index row points at — a crash between step 1 and step 3.
    orphan_payloads: tuple[str, ...] = ()
    #: Records with a journal event and no index row — a crash between 2 and 3.
    unindexed_writes: tuple[str, ...] = ()
    #: Index rows with no journal event — the one direction nothing can repair.
    unjournalled_records: tuple[str, ...] = ()
    #: Two records claiming to supersede the same one.
    lineage_branches: tuple[str, ...] = ()
    #: A record superseding an id this store does not hold.
    dangling_supersessions: tuple[str, ...] = ()


class RecordStore:
    """One durable store rooted at `root`.

    `root` is always explicit — this class never falls back to a default, so a test
    or a CLI invocation cannot reach the owner's real store by omission. That is
    `fmis.archive.storage`'s rule, kept for the same reason.
    """

    def __init__(self, root: Path | str) -> None:
        self._layout = StoreLayout(Path(root))
        self._index = RecordIndex(self._layout)
        self._journal = JournalEngine(self._layout)

    @property
    def root(self) -> Path:
        return self._layout.root

    @property
    def layout(self) -> StoreLayout:
        return self._layout

    @property
    def index(self) -> RecordIndex:
        return self._index

    @property
    def journal(self) -> JournalEngine:
        return self._journal

    # ------------------------------------------------------------------ #
    # Writing
    # ------------------------------------------------------------------ #

    def publish(self, record: Any, *, request: WriteRequest) -> WriteReceipt:
        """Store one record and journal the fact. The only write path there is."""
        if not isinstance(request, WriteRequest):
            raise TypeError("request must be a WriteRequest")
        spec = spec_for_record(record)
        if spec.durability is DurabilityClass.REBUILDABLE_PROJECTION:
            # Unreachable while no spec declares that class, and kept because the
            # day one does, it must be refused here rather than silently filed.
            raise PersistenceError(  # pragma: no cover
                f"{spec.kind.value} is a rebuildable projection and is never stored"
            )
        record_id = spec.identity(record)
        spec.validate_id(record_id)
        supersedes = spec.supersedes(record)
        operation = self._operation_for(request.operation, supersedes)
        digest = spec.digest(record)
        payload = spec.encode(record)
        occurred_at = require_utc(spec.moment(record), "record moment")
        if request.written_at < occurred_at and not spec.moment_may_be_future:
            raise PersistenceError(
                f"this record is filed at {request.written_at.isoformat()}, before "
                f"the instant it claims to describe ({occurred_at.isoformat()}); "
                "FMITS cannot store a record of something that has not happened"
            )
        envelope = StoredEnvelope(
            kind=spec.kind,
            record_id=record_id,
            payload_schema_version=int(payload["schema_version"]),
            occurred_at=occurred_at,
            written_at=request.written_at,
            content_digest=digest,
            payload=payload,
        )
        relative_path = self._layout.relative_path_for(
            kind=spec.kind,
            shape=spec.shape,
            record_id=record_id,
            moment=occurred_at,
        )

        with self._layout.exclusive():
            self._require_supersedable(spec, supersedes)
            existing = self._index.get(record_id)
            if existing is not None:
                return self._resolve_duplicate(
                    spec=spec, existing=existing, envelope=envelope
                )
            stored = self._write_payload(spec, envelope, relative_path)
            # If the payload was already there, its own `written_at` is the truth:
            # the record was filed then, and this call only discovered it. Taking
            # the request's instant instead would move a filing date every time a
            # lost index was repaired by a retry.
            filed_at = stored.written_at
            prior = self._existing_journal_event(record_id) if stored is not envelope else None
            event = prior or self._journal.append(
                occurred_at=request.written_at,
                source=request.source,
                author=request.author,
                reason=request.reason,
                version_set=request.version_set,
                operation=operation,
                record_kind=spec.kind,
                record_id=record_id,
                content_digest=digest,
                provenance=request.provenance,
                supersedes=supersedes,
                note=request.note,
            )
            scope = spec.owner_scope(record)
            self._index.append(
                IndexEntry(
                    record_id=record_id,
                    kind=spec.kind,
                    durability=spec.durability,
                    shape=spec.shape,
                    relative_path=relative_path,
                    content_digest=digest,
                    payload_schema_version=envelope.payload_schema_version,
                    occurred_at=occurred_at,
                    written_at=filed_at,
                    lineage_key=spec.lineage_key(record),
                    book=scope.book,
                    market=scope.market,
                    account=scope.account,
                    supersedes=supersedes,
                    journal_sequence=event.sequence,
                    journal_event_id=event.event_id,
                )
            )
        return WriteReceipt(
            record_id=record_id,
            kind=spec.kind,
            content_digest=digest,
            relative_path=relative_path,
            created=prior is None,
            journal_event=event,
        )

    def _existing_journal_event(self, record_id: str) -> JournalEvent | None:
        """The event that already recorded this record's arrival, if there is one.

        Consulted only when the payload turned out to be on disk already — the
        crash-between-steps case. Appending a second event for a record the journal
        already accounts for would put a write in the audit trail that never
        happened; the index row is what was missing, and the index row is what this
        call restores.
        """
        for event in self._journal.events():
            if event.record_id == record_id:
                return event
        return None

    def _require_supersedable(self, spec: RecordSpec, supersedes: str | None) -> None:
        """A chain never crosses kinds, and only a store can check that.

        `supersedes` holds a domain record id, and the id pattern cannot tell a
        journal entry's from a trade's — both are well-formed. Without this check a
        journal entry could name a trade, and the trade would then resolve to a
        *note* as its current version: `load_latest` on a fill would return the
        owner's prose about it.

        The target being **absent** is not refused here. A correction imported
        before the fill it corrects is ordinary backfill; the gap is reported by
        `verify()` and refused at read time by `fmis.ledger.LedgerResolver`, which
        is where a dangling reference actually matters.
        """
        if supersedes is None:
            return
        target = self._index.get(supersedes)
        if target is None:
            return
        if target.kind not in spec.supersedes_kinds:
            raise LineageError(
                f"a {spec.kind.value} may not supersede a {target.kind.value}. A "
                f"chain stays within one kind, and {spec.kind.value} supersedes "
                f"{sorted(kind.value for kind in spec.supersedes_kinds) or ['nothing']}"
            )

    @staticmethod
    def _operation_for(
        requested: WriteOperation, supersedes: str | None
    ) -> WriteOperation:
        """The record decides whether this is a supersession; the caller does not.

        A record naming something it replaces **is** a supersession, whatever the
        caller called it. Reading that off the record rather than trusting the
        request closes the failure where a correction filed as a plain create is
        invisible to every later reader of the chain — a mistake nobody would
        notice until a report showed a value the owner had already corrected.

        The reverse is a refusal rather than a downgrade: a caller who says
        `SUPERSEDE` about a record that names nothing has misunderstood something,
        and quietly filing it as a create would hide that.
        """
        if supersedes is not None:
            return WriteOperation.SUPERSEDE
        if requested is WriteOperation.SUPERSEDE:
            raise PersistenceError(
                "this write is marked as a supersession, but the record names "
                "nothing it supersedes. The link lives on the record — a "
                "correction's `supersedes`, an entry's `supersedes` — so that it "
                "survives outside this store's index"
            )
        return requested

    def _resolve_duplicate(
        self, *, spec: RecordSpec, existing: IndexEntry, envelope: StoredEnvelope
    ) -> WriteReceipt:
        """Decide what a second write of an already-stored id means.

        Three outcomes, and the middle one is the reason this reads the stored
        payload instead of trusting the digest. `DecisionWindow` derives its id and
        its digest from its *reference* fields, so a pruned window — rows dropped,
        everything else identical — is a different payload under the same digest.
        Comparing digests alone would file that as an idempotent success and
        silently keep whichever version happened to be written first.
        """
        stored = self._read_stored_payload(existing)
        if stored == dict(envelope.payload):
            return WriteReceipt(
                record_id=existing.record_id,
                kind=existing.kind,
                content_digest=existing.content_digest,
                relative_path=existing.relative_path,
                created=False,
                journal_event=None,
            )
        if existing.content_digest == envelope.content_digest:
            raise FrozenRecordError(
                f"{spec.kind.value} {existing.record_id!r} is already stored with "
                "the same identity and different content. For a decision window "
                "this is a prune — dropping the captured rows — and this store "
                "refuses it: its first rule is that nothing already published is "
                "rewritten, and no measured trigger for reclaiming that space "
                "exists yet. The captured window stays captured"
            )
        raise RecordConflictError(
            f"{spec.kind.value} {existing.record_id!r} is already stored with a "
            f"different content_digest ({existing.content_digest} != "
            f"{envelope.content_digest}) — a digest-prefix collision"
        )

    def _write_payload(
        self, spec: RecordSpec, envelope: StoredEnvelope, relative_path: str
    ) -> StoredEnvelope:
        """Publish the payload, or leave an identical one alone. Returns what is
        on disk afterwards — which is the *stored* envelope when one was already
        there, not the one that was offered.

        **Sameness is judged on content, never on bytes.** An envelope carries
        `written_at`, so two filings of the identical record produce different
        bytes; comparing bytes would report a conflict on every crash-recovery
        retry. ADR-0027 §3 already draws this line for `archived_at`, and this is
        the same line: what a record *is* excludes when it was filed.
        """
        path = self._layout.resolve_within_root(relative_path)
        if spec.shape is StorageShape.RECORD_FILE:
            if path.is_file():
                # Present but unindexed: a crash between step 1 and step 3, or a
                # file restored by hand. This store never writes over it. A file
                # that will not decode is certainly not this record, and is treated
                # as different content rather than as an excuse to overwrite it.
                try:
                    stored = self._decode_record_file(path)
                except StoreIOError:
                    # Not a conflict: the file could not be *read*. Reporting that
                    # as "different content" would send a caller looking for a
                    # record collision that does not exist.
                    raise
                except (PersistenceError, TradeDomainError):
                    stored = None
                if stored is not None and _is_same_record(stored, envelope):
                    return stored
                raise RecordConflictError(
                    f"{path} already holds different content for record "
                    f"{envelope.record_id!r}; it is not indexed, so this store did "
                    "not write it and will not overwrite it"
                )
            try:
                atomic_write(path, encode_envelope_bytes(envelope))
            except ArchiveError as error:
                raise StoreIOError(f"could not publish {path}: {error}") from error
            return envelope
        existing_lines = read_lines(path)
        for number, candidate in enumerate(existing_lines, start=1):
            decoded = decode_line(candidate, line_number=number)
            if decoded.get("record_id") != envelope.record_id:
                continue
            stored = StoredEnvelope.from_payload(decoded)
            if _is_same_record(stored, envelope):
                return stored
            raise RecordConflictError(
                f"{path} line {number} already holds event "
                f"{envelope.record_id!r} with different content; it is not "
                "indexed, so this store did not write it and will not replace it"
            )
        append_lines(
            path,
            (encode_line(envelope.to_payload()),),
            expected_existing=len(existing_lines),
        )
        return envelope

    def _decode_record_file(self, path: Path) -> StoredEnvelope:
        try:
            data = path.read_bytes()
        except OSError as error:
            raise StoreIOError(f"could not read {path}: {error}") from error
        return decode_envelope_bytes(data)

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #

    def load(self, record_id: str) -> Any:
        """Reconstruct one record, exactly as it was stored.

        Four independent checks, because each one catches something the others do
        not: the index row must point where the layout says it should (a re-pointed
        row), the envelope must name the id that was asked for (a misfiled record),
        the decoded record must re-derive the same id (a payload edited in a way
        that still parses), and it must re-derive the same digest (an edit to a
        field the id does not cover).
        """
        entry = self._index.find(record_id)
        return self._load_entry(entry)

    def load_envelope(self, record_id: str) -> StoredEnvelope:
        entry = self._index.find(record_id)
        return self._read_envelope(entry)

    def exists(self, record_id: str) -> bool:
        return self._index.contains(record_id)

    def entries(self, kind: RecordKind | None = None) -> tuple[IndexEntry, ...]:
        """Every index row, metadata only — no payload is read here."""
        rows = self._index.entries()
        if kind is None:
            return rows
        require_member(kind, RecordKind, "kind")
        return tuple(entry for entry in rows if entry.kind is kind)

    def records(self, kind: RecordKind) -> tuple[Any, ...]:
        """Every stored record of one kind, ordered by the instant it describes."""
        rows = sorted(
            self.entries(kind), key=lambda entry: (entry.occurred_at, entry.record_id)
        )
        return tuple(self._load_entry(entry) for entry in rows)

    def _load_entry(self, entry: IndexEntry) -> Any:
        spec = SPECS[entry.kind]
        envelope = self._read_envelope(entry)
        try:
            decoded = spec.decode(dict(envelope.payload))
        except PersistenceError:
            raise
        except TradeDomainError as error:
            # A payload the domain refuses to decode — an unknown field, an
            # unsupported version, a self-declared id that no longer matches its
            # own content. From the store's side every one of those is the same
            # fact: these bytes are not what they say they are.
            raise StoreIntegrityError(
                f"record {entry.record_id!r} does not decode: "
                f"{type(error).__name__}: {error}"
            ) from error
        derived_id = spec.identity(decoded)
        if derived_id != entry.record_id:
            raise StoreIntegrityError(
                f"record {entry.record_id!r} decodes to a record whose own id is "
                f"{derived_id!r}; the payload has been altered since it was written"
            )
        derived_digest = spec.digest(decoded)
        if derived_digest != entry.content_digest:
            raise StoreIntegrityError(
                f"record {entry.record_id!r} decodes to content digesting to "
                f"{derived_digest}, not the indexed {entry.content_digest}"
            )
        return decoded

    def _read_envelope(self, entry: IndexEntry) -> StoredEnvelope:
        expected_path = self._layout.relative_path_for(
            kind=entry.kind,
            shape=entry.shape,
            record_id=entry.record_id,
            moment=entry.occurred_at,
        )
        if entry.relative_path != expected_path:
            raise StoreIntegrityError(
                f"index row for {entry.record_id!r} points at "
                f"{entry.relative_path!r}, but its own kind and instant place it at "
                f"{expected_path!r}; the row has been re-pointed"
            )
        envelope = self._read_envelope_at(entry)
        if envelope.record_id != entry.record_id:
            raise StoreIntegrityError(
                f"the payload indexed as {entry.record_id!r} names itself "
                f"{envelope.record_id!r}"
            )
        if envelope.content_digest != entry.content_digest:
            raise StoreIntegrityError(
                f"record {entry.record_id!r} carries digest "
                f"{envelope.content_digest}, the index says {entry.content_digest}"
            )
        return envelope

    def _read_envelope_at(self, entry: IndexEntry) -> StoredEnvelope:
        path = self._layout.resolve_within_root(entry.relative_path)
        if entry.shape is StorageShape.RECORD_FILE:
            if not path.is_file():
                raise RecordMissingError(
                    f"the payload for {entry.record_id!r} is not at {path}"
                )
            try:
                data = path.read_bytes()
            except OSError as error:
                raise StoreIOError(f"could not read {path}: {error}") from error
            return decode_envelope_bytes(data)
        for number, line in enumerate(read_lines(path), start=1):
            decoded = decode_line(line, line_number=number)
            if decoded.get("record_id") == entry.record_id:
                return StoredEnvelope.from_payload(decoded)
        raise RecordMissingError(
            f"no line in {path} holds event {entry.record_id!r}"
        )

    def _read_stored_payload(self, entry: IndexEntry) -> Mapping[str, Any]:
        return dict(self._read_envelope_at(entry).payload)

    def log_envelopes(self, kind: RecordKind) -> tuple[StoredEnvelope, ...]:
        """Every envelope in one kind's year files, in file order.

        Reads the *files*, not the index — which is what makes it usable to rebuild
        the index and to detect a log line the index never learned about.
        """
        require_member(kind, RecordKind, "kind")
        if SPECS[kind].shape is not StorageShape.EVENT_LOG:
            raise PersistenceError(f"{kind.value} is not stored as an event log")
        found: list[StoredEnvelope] = []
        for year in self._layout.log_years(kind):
            path = self._layout.resolve_within_root(f"ledger/{kind.value}/{year}.jsonl")
            for number, line in enumerate(read_lines(path), start=1):
                found.append(
                    StoredEnvelope.from_payload(decode_line(line, line_number=number))
                )
        return tuple(found)

    def record_envelopes(self, kind: RecordKind) -> tuple[StoredEnvelope, ...]:
        """Every envelope in one kind's record files, in path order."""
        require_member(kind, RecordKind, "kind")
        if SPECS[kind].shape is not StorageShape.RECORD_FILE:
            raise PersistenceError(f"{kind.value} is not stored as record files")
        found: list[StoredEnvelope] = []
        for path in self._layout.record_files(kind):
            try:
                data = path.read_bytes()
            except OSError as error:  # pragma: no cover - unreadable file
                raise StoreIOError(f"could not read {path}: {error}") from error
            found.append(decode_envelope_bytes(data))
        return tuple(found)

    def stored_envelopes(self) -> tuple[StoredEnvelope, ...]:
        """Every envelope on disk, of every kind, read from the files themselves."""
        found: list[StoredEnvelope] = []
        for kind, spec in SPECS.items():
            if spec.shape is StorageShape.RECORD_FILE:
                found.extend(self.record_envelopes(kind))
            else:
                found.extend(self.log_envelopes(kind))
        return tuple(found)

    # ------------------------------------------------------------------ #
    # Verification and repair
    # ------------------------------------------------------------------ #

    def verify_record(self, record_id: str) -> RecordCheck:
        """Every defined problem as a result, never a raise."""
        try:
            self.load(record_id)
        except PersistenceError as error:
            return RecordCheck(
                record_id=record_id,
                ok=False,
                problems=(f"{type(error).__name__}: {error}",),
            )
        return RecordCheck(record_id=record_id, ok=True)

    def verify(self) -> StoreVerification:
        """Sweep the whole store: journal chain, payloads, index, orphans, lineage."""
        journal_result = self._journal.verify()
        try:
            rows = self._index.entries()
        except PersistenceError as error:
            return StoreVerification(
                ok=False,
                journal_event_count=journal_result.event_count,
                journal_problems=journal_result.problems,
                integrity_failures=(f"index unreadable: {error}",),
            )

        missing: list[str] = []
        failures: list[str] = []
        for entry in rows:
            check = self.verify_record(entry.record_id)
            if check.ok:
                continue
            if any("RecordMissingError" in problem for problem in check.problems):
                missing.append(entry.record_id)
            else:
                failures.extend(f"{entry.record_id}: {p}" for p in check.problems)

        indexed_ids = {entry.record_id for entry in rows}
        try:
            stored_ids = {
                envelope.record_id for envelope in self.stored_envelopes()
            }
        except PersistenceError as error:
            stored_ids = set()
            failures.append(f"stored payloads unreadable: {error}")
        orphans = sorted(stored_ids - indexed_ids)

        journalled: set[str] = set()
        if journal_result.ok:
            journalled = {event.record_id for event in self._journal.events()}
        unindexed = sorted(journalled - indexed_ids)
        unjournalled = sorted(indexed_ids - journalled) if journal_result.ok else []

        branches, dangling = self._lineage_problems(rows)

        ok = not (
            journal_result.problems
            or missing
            or failures
            or orphans
            or unindexed
            or unjournalled
            or branches
            or dangling
        )
        return StoreVerification(
            ok=ok,
            indexed_count=len(rows),
            journal_event_count=journal_result.event_count,
            journal_problems=journal_result.problems,
            missing_payloads=tuple(missing),
            integrity_failures=tuple(failures),
            orphan_payloads=tuple(orphans),
            unindexed_writes=tuple(unindexed),
            unjournalled_records=tuple(unjournalled),
            lineage_branches=tuple(branches),
            dangling_supersessions=tuple(dangling),
        )

    def _lineage_problems(
        self, rows: tuple[IndexEntry, ...]
    ) -> tuple[list[str], list[str]]:
        known = {entry.record_id for entry in rows}
        successors: dict[str, str] = {}
        branches: list[str] = []
        dangling: list[str] = []
        for entry in sorted(rows, key=lambda row: row.journal_sequence):
            target = entry.supersedes
            if target is None:
                continue
            if target not in known:
                dangling.append(f"{entry.record_id} supersedes unknown {target}")
                continue
            if target in successors:
                branches.append(
                    f"{target} is superseded by both {successors[target]} and "
                    f"{entry.record_id}"
                )
                continue
            successors[target] = entry.record_id
        return branches, dangling

    def rebuild_index(self) -> tuple[IndexEntry, ...]:
        """Reconstruct `index.jsonl` from the payloads and the write journal.

        The test that keeps the index honest, available as an operation: rebuild it
        and every answer the store gives is identical. It exists because the index
        is the only rebuildable thing here — the payloads and the journal are truth,
        and a rebuild that needed either of them to be repaired would be a repair,
        not a rebuild.

        A payload with no journal event is **not** indexed: there is no honest
        `journal_sequence` to give it, and inventing one would forge the audit
        trail to make a lookup table complete.
        """
        with self._layout.exclusive():
            events = self._journal.events()
            by_record: dict[str, JournalEvent] = {}
            for event in events:
                by_record.setdefault(event.record_id, event)
            rebuilt: list[IndexEntry] = []
            for envelope in self.stored_envelopes():
                event = by_record.get(envelope.record_id)
                if event is None:
                    continue
                spec = SPECS[envelope.kind]
                decoded = spec.decode(dict(envelope.payload))
                scope = spec.owner_scope(decoded)
                rebuilt.append(
                    IndexEntry(
                        record_id=envelope.record_id,
                        kind=envelope.kind,
                        durability=spec.durability,
                        shape=spec.shape,
                        relative_path=self._layout.relative_path_for(
                            kind=envelope.kind,
                            shape=spec.shape,
                            record_id=envelope.record_id,
                            moment=envelope.occurred_at,
                        ),
                        content_digest=spec.digest(decoded),
                        payload_schema_version=envelope.payload_schema_version,
                        occurred_at=envelope.occurred_at,
                        written_at=envelope.written_at,
                        lineage_key=spec.lineage_key(decoded),
                        book=scope.book,
                        market=scope.market,
                        account=scope.account,
                        supersedes=spec.supersedes(decoded),
                        journal_sequence=event.sequence,
                        journal_event_id=event.event_id,
                    )
                )
            rebuilt.sort(key=lambda entry: entry.journal_sequence)
            self._index.write_all(rebuilt)
        return tuple(rebuilt)

    # ------------------------------------------------------------------ #
    # Lineage — the version engine's raw material
    # ------------------------------------------------------------------ #

    def successors(self) -> dict[str, str]:
        """`{superseded id: the id that supersedes it}`, with branches refused."""
        successors: dict[str, str] = {}
        for entry in sorted(
            self._index.entries(), key=lambda row: row.journal_sequence
        ):
            target = entry.supersedes
            if target is None:
                continue
            if target in successors:
                raise LineageError(
                    f"record {target!r} is superseded by two records "
                    f"({successors[target]!r} and {entry.record_id!r}). A chain "
                    "extends; it never branches, because a branch gives 'what does "
                    "this say now' two answers"
                )
            successors[target] = entry.record_id
        return successors

    def written_at_of(self, record_id: str) -> datetime:
        return self._index.find(record_id).written_at


def _is_same_record(stored: StoredEnvelope, offered: StoredEnvelope) -> bool:
    """Whether two envelopes hold the same record, ignoring when each was filed."""
    return (
        stored.kind is offered.kind
        and stored.record_id == offered.record_id
        and stored.content_digest == offered.content_digest
        and dict(stored.payload) == dict(offered.payload)
    )
