"""The three repositories over money: trades, the whole ledger, and positions.

They are three because they answer three different questions and one class
answering all three would be the place the answers drift apart.

* **`TradeRepository`** writes and reads `Trade` records. It is the *write* face.
* **`LedgerRepository`** reads the whole event stream — trades and corrections
  together — through `fmis.ledger.LedgerResolver`, and is the only way to learn
  what a trade currently says. Its `resolved()` is the read face.
* **`PositionRepository`** stores nothing at all.

**Reading a trade without applying supersession is possible and is a mistake.**
`TradeRepository.load` returns exactly what was written, which is what a caller
asking for a specific historical version wants and what a caller asking "what do I
hold" must not use. `load_latest` resolves the chain, and `LedgerRepository`
resolves the whole stream at once. The domain marks the distinction with a token
`ResolvedTrade` that a caller cannot construct; this layer keeps that intact by
never unwrapping one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fmis.accounts import Book
from fmis.ledger import (
    Correction,
    LedgerResolver,
    ResolvedTrade,
    Trade,
    TradeStatus,
)
from fmis.money import DustPolicy
from fmis.positions import POSITION_CALCULATION_VERSION, Position, fold_positions
from fmis.records import require_member, require_text, require_utc

from fmis.persistence.base import Repository
from fmis.persistence.criteria import SearchCriteria
from fmis.persistence.errors import (
    FrozenRecordError,
    PersistenceError,
    ProjectionError,
    RecordMissingError,
)
from fmis.persistence.kinds import RecordKind
from fmis.persistence.store import RecordStore, WriteReceipt, WriteRequest

__all__ = ["TradeRepository", "LedgerRepository", "PositionRepository"]


class TradeRepository(Repository):
    """`Trade` records: recorded, corrected by supersession, never edited."""

    kinds = (RecordKind.TRADE,)

    def create(self, record: Any, *, request: WriteRequest) -> WriteReceipt:
        """Record a fill.

        A `DRAFT` trade is refused: a draft was never asserted, is not in the
        ledger, and storing one would put a value into an append-only economic
        record that the owner had not yet stated. `Trade.recorded()` promotes it
        through the status machine first.
        """
        if isinstance(record, Trade) and record.status is not TradeStatus.RECORDED:
            raise PersistenceError(
                f"this trade is {record.status.value} and is not in the ledger. "
                "Promote it with `Trade.recorded()` first — an append-only economic "
                "record holds what was asserted, and a draft was not"
            )
        return super().create(record, request=request)

    def replace(
        self,
        record_id: str,
        replacement: Trade | None = None,
        *,
        correction: Correction | None = None,
        request: WriteRequest | None = None,
        **_: Any,
    ) -> WriteReceipt:
        """Correct a recorded trade by appending a `Correction` that supersedes it.

        The original stays readable forever. That is the difference between *what
        happened* and *what the owner believed happened*, and it is why this is a
        `replace` rather than an `update`: nothing about the stored trade changes.

        The caller supplies the whole `Correction` — its reason tag, its author and
        its own audit block are the owner's assertions and this layer invents none
        of them. `replacement` is accepted as a convenience only to check that the
        correction the caller built actually carries it.
        """
        if correction is None or request is None:
            raise PersistenceError(
                "correcting a trade needs the Correction to append and a "
                "WriteRequest saying who is correcting it and why"
            )
        if not isinstance(correction, Correction):
            raise TypeError("correction must be a Correction")
        target = require_text(record_id, "record_id")
        if correction.supersedes != target:
            raise PersistenceError(
                f"this correction supersedes {correction.supersedes!r}, not the "
                f"trade {target!r} it was asked to replace"
            )
        if replacement is not None and correction.replacement != replacement:
            raise PersistenceError(
                "the correction's replacement is not the trade that was supplied"
            )
        if not self._store.exists(target):
            raise RecordMissingError(
                f"trade {target!r} is not in this store; a correction naming an "
                "event that does not resolve is a detected gap, not something to "
                "resolve by guessing"
            )
        return self._store.publish(correction, request=request.superseding())

    def load_latest(self, record_id: str) -> Trade:
        """What this trade says now, after every correction in its chain.

        A chain ends on a `Correction`, whose `replacement` *is* the current trade —
        so this returns a `Trade` for every id in the chain, never a `Correction`.
        """
        head = self._versions.head(self._require_owned_id(record_id))
        return head.replacement if isinstance(head, Correction) else head

    def _require_owned_id(self, record_id: str) -> str:
        """A trade's chain runs through corrections, which this repository reads."""
        wanted = require_text(record_id, "record_id")
        entry = self._store.index.get(wanted)
        if entry is not None and entry.kind not in (
            RecordKind.TRADE,
            RecordKind.CORRECTION,
        ):
            raise PersistenceError(
                f"record {wanted!r} is a {entry.kind.value}, not a trade"
            )
        return wanted

    def for_market(
        self, market: str, *, book: Book | None = None
    ) -> tuple[Trade, ...]:
        """Every stored trade in one market, optionally in one book."""
        return self.load_by_owner(
            market=require_text(market, "market"),
            book=None if book is None else require_member(book, Book, "book").value,
        )


class LedgerRepository(Repository):
    """The whole economic stream, read only through supersession.

    Owns both kinds because a resolver over trades without their corrections
    reports values the owner has already corrected — which is the exact failure the
    domain's `ResolvedTrade` token exists to make hard.
    """

    kinds = (RecordKind.TRADE, RecordKind.CORRECTION)

    def trades(self, criteria: SearchCriteria | None = None) -> tuple[Trade, ...]:
        return tuple(
            self._store.load(entry.record_id)
            for entry in self.entries(kind=RecordKind.TRADE, criteria=criteria)
        )

    def corrections(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[Correction, ...]:
        return tuple(
            self._store.load(entry.record_id)
            for entry in self.entries(kind=RecordKind.CORRECTION, criteria=criteria)
        )

    def resolver(self, criteria: SearchCriteria | None = None) -> LedgerResolver:
        """The domain's resolver over everything this store holds.

        Built fresh each call and cached nowhere. A cached resolver is a second
        answer to *what happened* that goes stale the moment a correction is filed,
        and the fold is milliseconds at this owner's volumes.
        """
        return LedgerResolver(
            trades=self.trades(criteria), corrections=self.corrections(criteria)
        )

    def resolved(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[ResolvedTrade, ...]:
        """Every live trade, ordered by when it happened. The only way to read one."""
        return self.resolver(criteria).resolved()

    def resolved_as_known_at(self, moment: datetime) -> tuple[ResolvedTrade, ...]:
        """The ledger as it stood when the store knew only what it knew at `moment`.

        The reconstruction that makes a past report reproducible. A correction filed
        today does not change what April's report was entitled to say, and this is
        how April's report is re-derived: filter on `written_at`, not `occurred_at`.
        """
        when = require_utc(moment, "moment")
        return self.resolver(SearchCriteria(known_until=when)).resolved()

    def status_of(self, event_id: str) -> TradeStatus:
        """`RECORDED` if this id is the live head, `SUPERSEDED` if it was corrected."""
        return self.resolver().status_of(require_text(event_id, "event_id"))

    def stale_inputs(self) -> dict[str, str]:
        """`{superseded id: the digest it now resolves to}`.

        What a captured artifact's `consumed_sources` is compared against to render
        staleness. The artifact is never rewritten and never recomputed — a surface
        shows that one of its inputs has since been corrected.
        """
        return self.resolver().superseded_digests()

    def replace(self, record_id: str, *_: Any, **__: Any) -> WriteReceipt:
        raise FrozenRecordError(
            "a correction is appended through TradeRepository.replace, which checks "
            "that the event being superseded is actually in this store. Publishing "
            "one here would skip that check"
        )


class PositionRepository(Repository):
    """Positions — folded on demand, stored never.

    **This repository has no records.** Architecture §24.3 classes a position as a
    rebuildable projection: *"delete every rebuildable projection, recompute, and
    assert identical results."* Making that a class that refuses to write, rather
    than a note in a document, is the difference between a rule and a hope.

    Everything here is a fold over `LedgerRepository.resolved()`. `create`, `update`
    and `replace` all raise, and the message says where the write belongs.
    """

    kinds = (RecordKind.TRADE, RecordKind.CORRECTION)

    def __init__(self, store: RecordStore, *, dust: DustPolicy) -> None:
        super().__init__(store)
        if not isinstance(dust, DustPolicy):
            raise TypeError(
                "a position fold needs a DustPolicy: what counts as flat is the "
                "owner's threshold, and this layer invents none"
            )
        self._dust = dust
        self._ledger = LedgerRepository(store)

    @property
    def dust(self) -> DustPolicy:
        return self._dust

    @property
    def calculation_version(self) -> str:
        return POSITION_CALCULATION_VERSION

    # -- the refusals --------------------------------------------------------

    def create(self, record: Any, *, request: WriteRequest) -> WriteReceipt:
        raise ProjectionError(
            "a position is a fold over the ledger and is never stored. Storing one "
            "would create a second answer to 'what do I hold', and the two drift "
            "the first time the fold's policy version moves. Write the trade"
        )

    def update(self, record_id: str, *_: Any, **__: Any) -> WriteReceipt:
        raise ProjectionError(
            "a position has no stored representation to update. Correct the trade "
            "and refold"
        )

    def replace(self, record_id: str, *_: Any, **__: Any) -> WriteReceipt:
        raise ProjectionError(
            "a position has no stored representation to replace. Correct the trade "
            "and refold"
        )

    def load(self, record_id: str) -> Any:
        raise ProjectionError(
            "positions have no ids in this store — a derived key can move when a "
            "dust policy changes, so nothing frozen may reference one. Fold and "
            "select instead"
        )

    # -- the folds -----------------------------------------------------------

    def rebuild(self, criteria: SearchCriteria | None = None) -> tuple[Position, ...]:
        """Fold the resolved ledger into positions. The whole of this repository."""
        return fold_positions(self._ledger.resolved(criteria), dust=self._dust)

    def as_known_at(self, moment: datetime) -> tuple[Position, ...]:
        """The positions the store would have reported at a past instant."""
        return fold_positions(
            self._ledger.resolved_as_known_at(moment), dust=self._dust
        )

    def open_positions(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[Position, ...]:
        return tuple(position for position in self.rebuild(criteria) if position.is_open)

    def load_by_owner(
        self,
        *,
        book: str | None = None,
        market: str | None = None,
        account: str | None = None,
        criteria: SearchCriteria | None = None,
    ) -> tuple[Position, ...]:
        """Positions in one book or market — filtered on the *trades* that fold into them.

        `account` narrows which trades are folded, not which positions come out: a
        position is keyed by `(market, book)` and holds no account of its own,
        because a book never shares capacity across accounts and pretending
        otherwise would let one position claim two.
        """
        base = criteria or SearchCriteria()
        return self.rebuild(
            base.narrowed(book=book, market=market, account=account)
        )

    def total_fees_in(self, asset: Any, criteria: SearchCriteria | None = None) -> Any:
        from fmis.positions import total_fees

        return total_fees(self.rebuild(criteria), asset)

    def is_reproducible(self, criteria: SearchCriteria | None = None) -> bool:
        """Fold twice and compare — the §24.3 classification test, as a method.

        A projection that does not reproduce is a captured artifact wearing the
        wrong label, and the day that becomes true this returns `False` instead of
        the store quietly holding two different answers.
        """
        return self.rebuild(criteria) == self.rebuild(criteria)
