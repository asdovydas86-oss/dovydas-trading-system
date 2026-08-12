"""`index.jsonl` — the metadata index, and the one thing in this store that is not truth.

Every other file here is a source of truth or a captured artifact. The index is
neither: it is a **rebuildable projection** over the record files, the ledger year
files and the write journal, and `RecordStore.rebuild_index()` reconstructs it
byte-for-byte from them. That is deliberate and load-bearing. An index that cannot
be thrown away is a second place a record's metadata lives, and the two eventually
disagree — which is the specific failure `fmis.archive`'s own
`manifest_mismatches` check exists to detect after the fact. Here it is
detectable *and* repairable, because nothing depends on the index that cannot be
recomputed.

What it buys: `search`, `load_by_owner`, `history` and every listing answer
without opening a single payload. A store that had to decode 50,000 records to
answer *"which trades in the swing book touched BTCUSDT last March"* would decode
50,000 records every time.

**Nullable columns really are null here.** The domain uses `Absent(reason)` and
never `None`, because a missing *value* has a reason worth keeping. An index
column is not a value: `market: null` means this kind of record has no market, the
reason lives on the record itself, and inventing a reason string per column would
put prose in a lookup table.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.records import (
    require_exact_keys,
    require_int,
    require_mapping,
    require_payload_version,
    require_text,
    require_utc,
)

from fmis.persistence.appendonly import append_lines, line_count, read_lines
from fmis.persistence.envelope import decode_line, encode_line
from fmis.persistence.errors import RecordMissingError, StoreIntegrityError
from fmis.persistence.kinds import (
    DurabilityClass,
    OwnerScope,
    RecordKind,
    StorageShape,
    kind_of,
)
from fmis.persistence.layout import StoreLayout

__all__ = [
    "INDEX_SCHEMA_VERSION",
    "SUPPORTED_INDEX_VERSIONS",
    "IndexEntry",
    "RecordIndex",
]

INDEX_SCHEMA_VERSION = 1
SUPPORTED_INDEX_VERSIONS = frozenset({1})

_INDEX_KEYS = frozenset(
    {
        "schema_version",
        "record_id",
        "kind",
        "durability",
        "shape",
        "relative_path",
        "content_digest",
        "payload_schema_version",
        "occurred_at",
        "written_at",
        "lineage_key",
        "book",
        "market",
        "account",
        "supersedes",
        "journal_sequence",
        "journal_event_id",
    }
)


@dataclass(frozen=True, slots=True)
class IndexEntry:
    """One row: everything a listing, a filter or a lineage walk needs."""

    record_id: str
    kind: RecordKind
    durability: DurabilityClass
    shape: StorageShape
    relative_path: str
    content_digest: str
    payload_schema_version: int
    occurred_at: datetime
    written_at: datetime
    lineage_key: str
    book: str | None
    market: str | None
    account: str | None
    supersedes: str | None
    journal_sequence: int
    journal_event_id: str
    schema_version: int = INDEX_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", require_text(self.record_id, "record_id"))
        for name, enum_type in (
            ("kind", RecordKind),
            ("durability", DurabilityClass),
            ("shape", StorageShape),
        ):
            if not isinstance(getattr(self, name), enum_type):
                raise TypeError(f"{name} must be a {enum_type.__name__}")
        object.__setattr__(
            self, "relative_path", require_text(self.relative_path, "relative_path")
        )
        digest = require_text(self.content_digest, "content_digest")
        if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
            raise StoreIntegrityError(
                f"content_digest must be a 'sha256:<64 hex>' string, got {digest!r}"
            )
        object.__setattr__(self, "content_digest", digest)
        require_int(self.payload_schema_version, "payload_schema_version", minimum=1)
        object.__setattr__(
            self, "occurred_at", require_utc(self.occurred_at, "occurred_at")
        )
        object.__setattr__(
            self, "written_at", require_utc(self.written_at, "written_at")
        )
        object.__setattr__(
            self, "lineage_key", require_text(self.lineage_key, "lineage_key")
        )
        for name in ("book", "market", "account", "supersedes"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_text(value, name))
        require_int(self.journal_sequence, "journal_sequence", minimum=0)
        object.__setattr__(
            self,
            "journal_event_id",
            require_text(self.journal_event_id, "journal_event_id"),
        )
        if self.schema_version not in SUPPORTED_INDEX_VERSIONS:
            raise StoreIntegrityError(
                f"index schema_version {self.schema_version} is not one this build "
                f"writes ({sorted(SUPPORTED_INDEX_VERSIONS)})"
            )

    @property
    def owner_scope(self) -> OwnerScope:
        return OwnerScope(book=self.book, market=self.market, account=self.account)

    @property
    def is_frozen(self) -> bool:
        return self.durability is DurabilityClass.CAPTURED_ARTIFACT

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "kind": self.kind.value,
            "durability": self.durability.value,
            "shape": self.shape.value,
            "relative_path": self.relative_path,
            "content_digest": self.content_digest,
            "payload_schema_version": self.payload_schema_version,
            "occurred_at": encode_timestamp(self.occurred_at),
            "written_at": encode_timestamp(self.written_at),
            "lineage_key": self.lineage_key,
            "book": self.book,
            "market": self.market,
            "account": self.account,
            "supersedes": self.supersedes,
            "journal_sequence": self.journal_sequence,
            "journal_event_id": self.journal_event_id,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> IndexEntry:
        mapping = require_mapping(raw, "index entry")
        version = require_payload_version(
            mapping, supported=SUPPORTED_INDEX_VERSIONS, entity="index entry"
        )
        require_exact_keys(mapping, _INDEX_KEYS, "index entry")
        return cls(
            record_id=str(mapping["record_id"]),
            kind=kind_of(mapping["kind"]),
            durability=_member(DurabilityClass, mapping["durability"], "durability"),
            shape=_member(StorageShape, mapping["shape"], "shape"),
            relative_path=str(mapping["relative_path"]),
            content_digest=str(mapping["content_digest"]),
            payload_schema_version=mapping["payload_schema_version"],
            occurred_at=decode_timestamp(mapping["occurred_at"]),
            written_at=decode_timestamp(mapping["written_at"]),
            lineage_key=str(mapping["lineage_key"]),
            book=_optional(mapping["book"]),
            market=_optional(mapping["market"]),
            account=_optional(mapping["account"]),
            supersedes=_optional(mapping["supersedes"]),
            journal_sequence=mapping["journal_sequence"],
            journal_event_id=str(mapping["journal_event_id"]),
            schema_version=version,
        )


class RecordIndex:
    """`index.jsonl`, read and appended to as a whole."""

    def __init__(self, layout: StoreLayout) -> None:
        if not isinstance(layout, StoreLayout):
            raise TypeError("layout must be a StoreLayout")
        self._layout = layout

    @property
    def layout(self) -> StoreLayout:
        return self._layout

    def entries(self) -> tuple[IndexEntry, ...]:
        """Every row, in write order, rejecting a repeated record id.

        A duplicate id is rejected on *read* rather than only prevented on write,
        because the index is a plain text file the owner can open and a hand-edit
        that duplicates a line would otherwise make `find` return whichever row
        happened to come first.
        """
        found: list[IndexEntry] = []
        seen: dict[str, int] = {}
        for number, line in enumerate(read_lines(self._layout.index_path), start=1):
            entry = IndexEntry.from_payload(decode_line(line, line_number=number))
            if entry.record_id in seen:
                raise StoreIntegrityError(
                    f"index line {number} repeats record {entry.record_id!r}, first "
                    f"indexed on line {seen[entry.record_id]}"
                )
            seen[entry.record_id] = number
            found.append(entry)
        return tuple(found)

    def find(self, record_id: str) -> IndexEntry:
        wanted = require_text(record_id, "record_id")
        for entry in self.entries():
            if entry.record_id == wanted:
                return entry
        raise RecordMissingError(f"no record {wanted!r} is indexed in this store")

    def get(self, record_id: str) -> IndexEntry | None:
        try:
            return self.find(record_id)
        except RecordMissingError:
            return None

    def contains(self, record_id: str) -> bool:
        return self.get(record_id) is not None

    def append(self, entry: IndexEntry, *, expected_existing: int | None = None) -> None:
        if not isinstance(entry, IndexEntry):
            raise TypeError("entry must be an IndexEntry")
        path = self._layout.index_path
        append_lines(
            path,
            (encode_line(entry.to_payload()),),
            expected_existing=(
                line_count(path) if expected_existing is None else expected_existing
            ),
        )

    def write_all(self, entries: Iterable[IndexEntry]) -> None:
        """Publish a whole index from scratch — the rebuild path, and only that.

        Not an append: this replaces the file. It is the one write in the package
        that can shrink a file, which is why it lives here under a name no ordinary
        write path calls, and why `RecordStore.rebuild_index` is the only caller.
        """
        rows = tuple(entries)
        for entry in rows:
            if not isinstance(entry, IndexEntry):
                raise TypeError("every entry must be an IndexEntry")
        path = self._layout.index_path
        path.unlink(missing_ok=True)
        append_lines(
            path, tuple(encode_line(entry.to_payload()) for entry in rows),
            expected_existing=0,
        )


def _optional(value: Any) -> str | None:
    return None if value is None else str(value)


def _member(enum_type: Any, value: Any, entity: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise StoreIntegrityError(
            f"index {entity} {value!r} is not a known {enum_type.__name__}"
        ) from error
