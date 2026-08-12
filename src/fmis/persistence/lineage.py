"""The version engine: what a record says now, what it said then, and every step between.

**There is no `UPDATE` in this store, so "version" means something exact here.** A
version is a whole record. Correcting a trade appends a `Correction` carrying the
replacement in full; superseding a journal entry appends a new entry naming the old
one. Every past version stays byte-identical and loadable forever, and the *chain*
is the only thing that moves.

Three questions, three methods, and they are genuinely different:

* `history(id)` — every version, oldest first. What did the owner first believe,
  and what do we now know.
* `head(id)` — what it says now.
* `at(id, moment)` — what it said at a past instant, decided by **`written_at`**,
  not by `occurred_at`. That distinction is the whole of "immutable historical
  reconstruction": a correction filed today for a fill in March does not change
  what a report run in April was entitled to say. Reconstructing April's answer
  means asking what the store *knew* in April.

**A chain extends; it never branches.** Two records superseding one is a rejected
state rather than a merge, because a branch gives *"what actually happened"* two
answers and any store that picks one is quietly deciding which of the owner's
corrections counted. That is `fmis.ledger.LedgerResolver`'s rule, applied to every
kind rather than to trades alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fmis.records import require_member, require_text, require_utc

from fmis.persistence.errors import LineageError, RecordMissingError
from fmis.persistence.index import IndexEntry
from fmis.persistence.kinds import RecordKind
from fmis.persistence.store import RecordStore

__all__ = ["Lineage", "VersionEngine"]


@dataclass(frozen=True, slots=True)
class Lineage:
    """One record's whole version history, as ids and the instants they were filed.

    Ids and instants rather than records: a lineage is answered from the index
    alone, so asking *"was this ever corrected"* about ten thousand trades does not
    decode ten thousand payloads.
    """

    origin_id: str
    version_ids: tuple[str, ...]
    written_ats: tuple[datetime, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin_id", require_text(self.origin_id, "origin_id"))
        if not isinstance(self.version_ids, tuple) or not self.version_ids:
            raise LineageError("a lineage holds at least the record it started from")
        if len(self.written_ats) != len(self.version_ids):
            raise LineageError(
                "every version in a lineage carries the instant it was filed"
            )
        if self.version_ids[0] != self.origin_id:
            raise LineageError("a lineage starts at its own origin")

    @property
    def head_id(self) -> str:
        """The live version — the one nothing supersedes."""
        return self.version_ids[-1]

    @property
    def length(self) -> int:
        return len(self.version_ids)

    @property
    def was_superseded(self) -> bool:
        return self.length > 1

    def id_at(self, moment: datetime) -> str | None:
        """The id that was live at `moment`, or `None` if nothing was known yet.

        `None` rather than the origin, because *"the store held no such record"* and
        *"the store held the first version"* are different answers, and a caller
        that cannot tell them apart will report a position the owner did not have.
        """
        when = require_utc(moment, "moment")
        live: str | None = None
        for record_id, written_at in zip(self.version_ids, self.written_ats):
            if written_at <= when:
                live = record_id
            else:
                break
        return live


class VersionEngine:
    """Version-aware loading over any store. Reads only; it never writes."""

    def __init__(self, store: RecordStore) -> None:
        if not isinstance(store, RecordStore):
            raise TypeError("store must be a RecordStore")
        self._store = store

    @property
    def store(self) -> RecordStore:
        return self._store

    # -- lineage -------------------------------------------------------------

    def lineage(self, record_id: str) -> Lineage:
        """The whole chain any member of it belongs to.

        Accepts *any* id in the chain, not only the original: a caller holding a
        correction's id is asking about the same history as one holding the trade's,
        and making them find the origin first would be making them reimplement this.
        """
        wanted = require_text(record_id, "record_id")
        rows = {entry.record_id: entry for entry in self._store.index.entries()}
        if wanted not in rows:
            raise RecordMissingError(f"no record {wanted!r} is indexed in this store")
        successors = self._store.successors()
        predecessors: dict[str, str] = {}
        for superseded, successor in successors.items():
            predecessors[successor] = superseded

        origin = wanted
        seen = {origin}
        while origin in predecessors:
            origin = predecessors[origin]
            if origin in seen:
                raise LineageError(
                    f"the chain containing {wanted!r} loops back to {origin!r}"
                )
            seen.add(origin)

        chain = [origin]
        walked = {origin}
        current = origin
        while current in successors:
            current = successors[current]
            if current in walked:
                raise LineageError(
                    f"the chain starting at {origin!r} loops back to {current!r}"
                )
            walked.add(current)
            chain.append(current)
        missing = [step for step in chain if step not in rows]
        if missing:
            raise LineageError(
                f"the chain containing {wanted!r} names record(s) this store does "
                f"not hold: {missing}"
            )
        return Lineage(
            origin_id=origin,
            version_ids=tuple(chain),
            written_ats=tuple(rows[step].written_at for step in chain),
        )

    # -- version-aware loading -----------------------------------------------

    def load(self, record_id: str) -> Any:
        """The exact version named. Never resolved, never redirected."""
        return self._store.load(record_id)

    def head(self, record_id: str) -> Any:
        """What this record says now, after every supersession."""
        return self._store.load(self.lineage(record_id).head_id)

    def history(self, record_id: str) -> tuple[Any, ...]:
        """Every version, oldest first."""
        return tuple(
            self._store.load(step) for step in self.lineage(record_id).version_ids
        )

    def at(self, record_id: str, moment: datetime) -> Any | None:
        """What this record said at a past instant, or `None` if it was unknown then."""
        live = self.lineage(record_id).id_at(moment)
        return None if live is None else self._store.load(live)

    def is_live(self, record_id: str) -> bool:
        """Whether nothing supersedes this record."""
        return record_id not in self._store.successors()

    # -- series --------------------------------------------------------------

    def series(self, kind: RecordKind, lineage_key: str) -> tuple[IndexEntry, ...]:
        """Every record of one kind sharing a lineage key, oldest first.

        Not the same thing as a chain, and the difference matters. Three portfolio
        snapshots of one portfolio are three *observations*, none of which supersedes
        another; three versions of one risk budget are three *generations* of one
        policy, and only the latest is in force. Both are answered here and neither
        is called a version of the other.
        """
        # `kind` is required explicitly rather than defaulted: `entries(None)`
        # means *every* kind, and a series silently spanning kinds would group two
        # unrelated records that happen to share a lineage key.
        require_member(kind, RecordKind, "kind")
        wanted = require_text(lineage_key, "lineage_key")
        rows = [
            entry
            for entry in self._store.entries(kind)
            if entry.lineage_key == wanted
        ]
        rows.sort(key=lambda entry: (entry.occurred_at, entry.record_id))
        return tuple(rows)

    def series_at(
        self, kind: RecordKind, lineage_key: str, moment: datetime
    ) -> IndexEntry | None:
        """The latest record of a series whose own instant does not follow `moment`."""
        when = require_utc(moment, "moment")
        live: IndexEntry | None = None
        for entry in self.series(kind, lineage_key):
            if entry.occurred_at <= when:
                live = entry
            else:
                break
        return live
