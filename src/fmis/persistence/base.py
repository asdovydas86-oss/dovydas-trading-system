"""The shape every repository has, and the two verbs that are almost never legal.

Eleven repositories, one base. What they share is not code reuse for its own sake:
it is the guarantee that `load`, `history`, `at` and `search` mean the *same thing*
on every kind, so a caller who has learned one repository has learned all of them.

**`update` never succeeds, anywhere.** Not on a captured artifact, not on a source
of truth, not on anything. It exists as a method because callers will look for it,
and a method that raises with the legal path named is worth more than an
`AttributeError` that leaves them to guess. This store has exactly two ways a
record's meaning changes:

* append a **new record that supersedes** the old one — `replace`, on the three
  kinds that have that mechanism; or
* append the **next observation** — which is not a change to anything.

**`replace` also raises by default.** A subclass that can supersede overrides it,
so a kind acquires an update path only by someone writing one, never by inheriting
one. That is the opposite of the usual default and it is the point: the failure this
guards against is a captured artifact quietly gaining an edit path three milestones
after it was declared frozen.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fmis.records import require_member, require_text

from fmis.persistence.criteria import SearchCriteria
from fmis.persistence.errors import (
    FrozenRecordError,
    PersistenceError,
    UnknownRecordKindError,
)
from fmis.persistence.index import IndexEntry
from fmis.persistence.kinds import (
    DurabilityClass,
    OwnerScope,
    RecordKind,
    SPECS,
    spec_for_record,
)
from fmis.persistence.lineage import Lineage, VersionEngine
from fmis.persistence.store import RecordStore, WriteReceipt, WriteRequest

__all__ = ["Repository"]


class Repository:
    """One typed face over the store, restricted to the kinds it owns."""

    #: Every kind this repository may read or write. The first is its primary.
    kinds: tuple[RecordKind, ...] = ()

    def __init__(self, store: RecordStore) -> None:
        if not isinstance(store, RecordStore):
            raise TypeError("store must be a RecordStore")
        if not self.kinds:
            raise PersistenceError(
                f"{type(self).__name__} declares no kinds; a repository that owns "
                "nothing would silently accept every record in the store"
            )
        self._store = store
        self._versions = VersionEngine(store)

    @property
    def store(self) -> RecordStore:
        return self._store

    @property
    def versions(self) -> VersionEngine:
        return self._versions

    @property
    def primary_kind(self) -> RecordKind:
        return self.kinds[0]

    # -- writing -------------------------------------------------------------

    def create(self, record: Any, *, request: WriteRequest) -> WriteReceipt:
        """Store one record of a kind this repository owns.

        Idempotent by content: publishing the identical record twice returns a
        receipt with `created=False` and appends no second journal event.
        """
        self._require_owned(record)
        return self._store.publish(record, request=request)

    def update(self, record_id: str, *_: Any, **__: Any) -> WriteReceipt:
        """Always refuses, naming the legal path for this kind."""
        raise FrozenRecordError(self._no_edit_path(require_text(record_id, "record_id")))

    def replace(self, record_id: str, *_: Any, **__: Any) -> WriteReceipt:
        """Refuses unless a subclass has a supersession mechanism to offer."""
        raise FrozenRecordError(self._no_edit_path(require_text(record_id, "record_id")))

    def _no_edit_path(self, record_id: str) -> str:
        spec = SPECS[self.primary_kind]
        if spec.durability is DurabilityClass.CAPTURED_ARTIFACT:
            return (
                f"{spec.kind.value} {record_id!r} is a captured artifact: it was "
                "frozen with its inputs at a named moment and has no edit path. A "
                "later reading of the same subject is a new record, not a change to "
                "this one"
            )
        return (
            f"{spec.kind.value} {record_id!r} is append-only and is never edited in "
            "place. If it is wrong, append a record that supersedes it — the "
            "original stays readable, which is the difference between what happened "
            "and what the owner believed happened"
        )

    # -- reading -------------------------------------------------------------

    def load(self, record_id: str) -> Any:
        """The exact version named, byte-verified. Never redirected to a later one."""
        return self._store.load(self._require_owned_id(record_id))

    def load_latest(self, record_id: str) -> Any:
        """What this record says now, after every supersession in its chain."""
        return self._versions.head(self._require_owned_id(record_id))

    def history(self, record_id: str) -> tuple[Any, ...]:
        """Every version of this record, oldest first."""
        return self._versions.history(self._require_owned_id(record_id))

    def lineage(self, record_id: str) -> Lineage:
        return self._versions.lineage(self._require_owned_id(record_id))

    def at(self, record_id: str, moment: datetime) -> Any | None:
        """What this record said when the store knew only what it knew at `moment`."""
        return self._versions.at(self._require_owned_id(record_id), moment)

    def exists(self, record_id: str) -> bool:
        entry = self._store.index.get(require_text(record_id, "record_id"))
        return entry is not None and entry.kind in self.kinds

    def count(self, kind: RecordKind | None = None) -> int:
        return len(self.entries(kind=kind))

    def entries(
        self,
        *,
        kind: RecordKind | None = None,
        criteria: SearchCriteria | None = None,
    ) -> tuple[IndexEntry, ...]:
        """Index rows only — no payload is decoded here.

        Ordered by the instant each record describes, then by id. Deterministic on
        purpose: a listing whose order depends on the order things were written is a
        listing that changes when history is backfilled.
        """
        if kind is not None:
            require_member(kind, RecordKind, "kind")
            if kind not in self.kinds:
                raise UnknownRecordKindError(
                    f"{type(self).__name__} does not own {kind.value}; it owns "
                    f"{sorted(owned.value for owned in self.kinds)}"
                )
            wanted = (kind,)
        else:
            wanted = self.kinds
        rows = [
            entry for entry in self._store.index.entries() if entry.kind in wanted
        ]
        if criteria is not None:
            if not isinstance(criteria, SearchCriteria):
                raise TypeError("criteria must be a SearchCriteria")
            rows = [entry for entry in rows if criteria.matches(entry)]
            if criteria.filters_supersession:
                superseded = set(self._store.successors())
                rows = [
                    entry
                    for entry in rows
                    if (entry.record_id in superseded) is criteria.superseded
                ]
        rows.sort(key=lambda entry: (entry.occurred_at, entry.record_id))
        if criteria is not None and criteria.limit is not None:
            rows = rows[: criteria.limit]
        return tuple(rows)

    def search(self, criteria: SearchCriteria | None = None) -> tuple[Any, ...]:
        """Every matching record, decoded, in the same deterministic order."""
        return tuple(
            self._store.load(entry.record_id)
            for entry in self.entries(criteria=criteria)
        )

    def all(self) -> tuple[Any, ...]:
        return self.search()

    def load_by_owner(
        self,
        *,
        book: str | None = None,
        market: str | None = None,
        account: str | None = None,
        criteria: SearchCriteria | None = None,
    ) -> tuple[Any, ...]:
        """Every record belonging to one book, market or account.

        See `OwnerScope` on why those three are what "by owner" means in a
        single-owner system. Supplying none of them returns everything this
        repository owns, which is the honest reading of "no restriction".
        """
        base = criteria or SearchCriteria()
        return self.search(
            base.narrowed(book=book, market=market, account=account)
        )

    def owner_scopes(self) -> tuple[OwnerScope, ...]:
        """The distinct scopes this repository holds records for, deduplicated."""
        seen: dict[tuple[str | None, str | None, str | None], OwnerScope] = {}
        for entry in self.entries():
            scope = entry.owner_scope
            seen.setdefault((scope.book, scope.market, scope.account), scope)
        return tuple(seen.values())

    # -- internals -----------------------------------------------------------

    def _require_owned(self, record: Any) -> None:
        spec = spec_for_record(record)
        if spec.kind not in self.kinds:
            raise UnknownRecordKindError(
                f"{type(self).__name__} does not own {spec.kind.value}; it owns "
                f"{sorted(kind.value for kind in self.kinds)}"
            )

    def _require_owned_id(self, record_id: str) -> str:
        wanted = require_text(record_id, "record_id")
        entry = self._store.index.get(wanted)
        if entry is not None and entry.kind not in self.kinds:
            raise UnknownRecordKindError(
                f"record {wanted!r} is a {entry.kind.value}, which "
                f"{type(self).__name__} does not own"
            )
        return wanted
