"""`Position` — the fold of one market's events in one book between two flats.

The unit of exposure, the unit of risk, and the round trip. **Nothing here is
stored**: a position is a pure fold over the resolved ledger, and deleting every
position and recomputing must produce the identical result. That is not a nice
property; it *is* the CI test the durability classification rests on.

Four rules the fold implements rather than documents.

**A direction flip is a split.** A fill carrying exposure through zero closes one
position and opens another at the same instant. Merging them would put two
decisions under one round trip and make duration, R-multiple and every
duration-keyed learning metric read the wrong thing.

**`average_entry` is a pair, never a quotient.** `AverageCost` holds
`(total_cost, total_quantity)` and computes the per-unit value at read time,
because `average × quantity ≠ cost` under any decimal context and a stored
average would be the one number nobody could reconcile against the two it came
from.

**Gross and net P&L are always both present.** A figure that silently includes or
excludes fees is a figure two readers will interpret two ways, and fee drag is
the one cost a swing trader on perpetuals pays without noticing.

**A captured artifact never references a position by its derived key.** `Position`
carries `event_ids` — the set of ledger events that composed it — so a later dust
or fold-policy version bump that redraws a position boundary leaves every frozen
artifact still resolvable. That single rule converts AP-D8's Critical identity
hazard into a resolvable one at the cost of a tuple of ids.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fmis.accounts import Book, MarketId
from fmis.money import AssetCode, Money, Quantity
from fmis.provenance import Absent, ValueOrigin
from fmis.records import (
    DomainStateError,
    DomainValidationError,
    TradeDomainError,
    require_int,
    require_member,
    require_text,
    require_tuple_of,
    require_utc,
)

__all__ = [
    "PositionsError",
    "IllegalPositionTransitionError",
    "PositionState",
    "POSITION_STATE_TRANSITIONS",
    "PositionDirection",
    "ReconciliationState",
    "PositionKey",
    "AverageCost",
    "Position",
    "advance_position_state",
    "total_fees",
]


class PositionsError(TradeDomainError):
    """Base class for every position-fold failure."""


class IllegalPositionTransitionError(DomainStateError, PositionsError):
    """A position state change the fold does not permit."""


class PositionState(Enum):
    """`OPEN` while exposure is non-zero, `CLOSED` once it is within dust.

    Two members, not five. The brief's *Entered*, *Scaled* and *Reduced* are not
    states: they are events that change the fold's numbers while it stays open,
    and modelling a partial exit as a lifecycle state would put one fact in two
    places. *Flipped* is not a state either — it is the moment one position ends
    and another begins, which is why `closed_by_flip` is a property of the
    *closed* position rather than a state of its own.
    """

    OPEN = "open"
    CLOSED = "closed"


#: A position opens, accumulates, and closes. It never reopens: the next
#: non-zero exposure in the same `(market, book)` pair is the *next* position,
#: with the next flat-crossing ordinal.
POSITION_STATE_TRANSITIONS: dict[PositionState, frozenset[PositionState]] = {
    PositionState.OPEN: frozenset({PositionState.OPEN, PositionState.CLOSED}),
    PositionState.CLOSED: frozenset(),
}


def advance_position_state(
    current: PositionState, target: PositionState
) -> PositionState:
    """Move a position's state, refusing every transition the fold forbids."""
    require_member(current, PositionState, "current")
    require_member(target, PositionState, "target")
    allowed = POSITION_STATE_TRANSITIONS[current]
    if target not in allowed:
        raise IllegalPositionTransitionError(
            f"a {current.value} position cannot become {target.value}. A closed "
            "position never reopens; the next exposure is the next position, "
            "with the next flat-crossing ordinal"
        )
    return target


class PositionDirection(Enum):
    """Which way the exposure points."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class ReconciliationState(Enum):
    """Whether the fold has been checked against the venue.

    Three values, **no transition machine and no automatic repair**.
    `UNRECONCILED` is the only state this build produces, and the gap is rendered
    rather than hidden — the same discipline the workspace applies to an
    unavailable section.
    """

    UNRECONCILED = "unreconciled"
    RECONCILED = "reconciled"
    DISPUTED = "disputed"


@dataclass(frozen=True, slots=True, order=True)
class PositionKey:
    """`(market, book, flat_crossing_ordinal)` — a **derived key**, never stored.

    A display convenience. Nothing frozen may reference a position by this key,
    because a dust-policy bump can move where one position ends and the next
    begins, and a captured artifact pointing here would silently start meaning
    something else.
    """

    market_id: str
    book: str
    flat_crossing_ordinal: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "market_id", require_text(self.market_id, "market_id"))
        object.__setattr__(self, "book", require_text(self.book, "book"))
        require_int(self.flat_crossing_ordinal, "flat_crossing_ordinal", minimum=0)

    def __str__(self) -> str:
        return f"{self.market_id}|{self.book}|#{self.flat_crossing_ordinal}"


@dataclass(frozen=True, slots=True)
class AverageCost:
    """`(total_cost, total_quantity)` — and the division is done at read time."""

    total_cost: Money
    total_quantity: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.total_cost, Money):
            raise TypeError("total_cost must be a Money")
        if not isinstance(self.total_quantity, Quantity):
            raise TypeError("total_quantity must be a Quantity")
        if self.total_quantity.amount < 0:
            raise DomainValidationError(
                f"total_quantity cannot be negative, got {self.total_quantity}; "
                "direction lives on the position, not inside its cost basis"
            )

    @property
    def per_unit(self) -> Decimal | Absent:
        """The quotient — computed here, stored nowhere.

        `Absent` rather than a division by zero when nothing has been acquired:
        an average cost over no units is not zero, it is undefined, and a zero
        would flow into a P&L figure that looked plausible.
        """
        if self.total_quantity.amount == 0:
            return Absent("no quantity has been acquired, so there is no average")
        return self.total_cost.amount / self.total_quantity.amount

    @property
    def arithmetic(self) -> str:
        """The division shown, not merely its result."""
        return f"{self.total_cost.text} ÷ {self.total_quantity.text}"

    def to_payload(self) -> dict[str, Any]:
        return {
            "total_cost": self.total_cost.to_payload(),
            "total_quantity": self.total_quantity.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class Position:
    """One round trip, folded. A rebuildable projection: delete it and recompute."""

    key: PositionKey
    market: MarketId
    book: Book
    state: PositionState
    direction: PositionDirection
    net_quantity: Quantity
    average_entry: AverageCost
    average_exit: AverageCost | Absent
    realized_pnl_gross: Money
    realized_pnl_net: Money
    fees: tuple[Money, ...]
    opened_at: datetime
    closed_at: datetime | Absent
    max_exposure: Quantity
    trade_count: int
    add_count: int
    reduce_count: int
    event_ids: tuple[str, ...]
    calculation_version: str
    dust_policy_id: str
    dust_policy_version: int
    closed_by_flip: bool = False
    reconciliation: ReconciliationState = ReconciliationState.UNRECONCILED

    def __post_init__(self) -> None:
        if not isinstance(self.key, PositionKey):
            raise TypeError("key must be a PositionKey")
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        require_member(self.book, Book, "book")
        require_member(self.state, PositionState, "state")
        require_member(self.direction, PositionDirection, "direction")
        require_member(self.reconciliation, ReconciliationState, "reconciliation")
        for name in ("net_quantity", "max_exposure"):
            if not isinstance(getattr(self, name), Quantity):
                raise TypeError(f"{name} must be a Quantity")
        if not isinstance(self.average_entry, AverageCost):
            raise TypeError("average_entry must be an AverageCost")
        if not isinstance(self.average_exit, (AverageCost, Absent)):
            raise TypeError("average_exit must be an AverageCost or Absent")
        for name in ("realized_pnl_gross", "realized_pnl_net"):
            if not isinstance(getattr(self, name), Money):
                raise TypeError(f"{name} must be a Money")
        require_tuple_of(self.fees, Money, "fees")
        fee_assets = [fee.asset.code for fee in self.fees]
        if len(set(fee_assets)) != len(fee_assets):
            raise DomainValidationError(
                "fees are totalled per asset; one asset must not appear twice"
            )
        object.__setattr__(self, "opened_at", require_utc(self.opened_at, "opened_at"))
        if not isinstance(self.closed_at, Absent):
            object.__setattr__(
                self, "closed_at", require_utc(self.closed_at, "closed_at")
            )
            if self.closed_at < self.opened_at:
                raise DomainValidationError("closed_at precedes opened_at")
        for name in ("trade_count", "add_count", "reduce_count"):
            require_int(getattr(self, name), name, minimum=0)
        require_tuple_of(self.event_ids, str, "event_ids", minimum_length=1)
        object.__setattr__(
            self, "calculation_version", require_text(self.calculation_version, "calculation_version")
        )
        object.__setattr__(
            self, "dust_policy_id", require_text(self.dust_policy_id, "dust_policy_id")
        )
        require_int(self.dust_policy_version, "dust_policy_version", minimum=1)
        if not isinstance(self.closed_by_flip, bool):
            raise TypeError("closed_by_flip must be a bool")
        if self.state is PositionState.CLOSED and isinstance(self.closed_at, Absent):
            raise DomainValidationError("a closed position states when it closed")
        if self.state is PositionState.OPEN and not isinstance(self.closed_at, Absent):
            raise DomainValidationError("an open position has no closed_at")
        if self.state is PositionState.CLOSED and (
            self.direction is not PositionDirection.FLAT
        ):
            raise DomainValidationError(
                "a closed position is flat; a direction on it would claim exposure "
                "that no longer exists"
            )
        if self.closed_by_flip and self.state is not PositionState.CLOSED:
            raise DomainValidationError(
                "closed_by_flip marks how a position ended; an open one has not"
            )

    # -- projections ---------------------------------------------------------

    @property
    def origin(self) -> ValueOrigin:
        """`MEASURED` over `ASSERTED` inputs."""
        return ValueOrigin.MEASURED

    @property
    def is_open(self) -> bool:
        return self.state is PositionState.OPEN

    @property
    def duration(self) -> Any:
        """How long the round trip lasted, or `Absent` while it is open."""
        if isinstance(self.closed_at, Absent):
            return Absent("the position is still open")
        return self.closed_at - self.opened_at

    def unrealized_pnl(self, mark: Decimal | Absent, quote: AssetCode) -> Money | Absent:
        """Requires a mark, and says so when there is none.

        `Absent(reason)` rather than zero, because a zero unrealized P&L on an
        unmarked position makes a portfolio total look plausible and survives for
        years.
        """
        if isinstance(mark, Absent):
            return Absent(f"no mark is available for {self.market.value}")
        if not isinstance(mark, Decimal):
            raise TypeError("mark must be a Decimal or Absent")
        if self.state is PositionState.CLOSED:
            return Absent("a closed position has no unrealized profit or loss")
        entry_per_unit = self.average_entry.per_unit
        if isinstance(entry_per_unit, Absent):
            return entry_per_unit
        return Money((mark - entry_per_unit) * self.net_quantity.amount, quote)

    def fees_in(self, asset: AssetCode) -> Money:
        for fee in self.fees:
            if fee.asset == asset:
                return fee
        return Money.zero(asset)

    def to_payload(self) -> dict[str, Any]:
        """A rebuildable projection still serializes — for export, never for storage.

        Nothing reads this back: the position is recomputed from the ledger, and a
        `from_payload` here would be an invitation to persist a fold and let it
        drift from the events that produce it.
        """
        return {
            "key": str(self.key),
            "market": self.market.to_payload(),
            "book": self.book.value,
            "state": self.state.value,
            "direction": self.direction.value,
            "net_quantity": self.net_quantity.to_payload(),
            "average_entry": self.average_entry.to_payload(),
            "average_exit": (
                {"absent": self.average_exit.to_payload()}
                if isinstance(self.average_exit, Absent)
                else {"value": self.average_exit.to_payload()}
            ),
            "realized_pnl_gross": self.realized_pnl_gross.to_payload(),
            "realized_pnl_net": self.realized_pnl_net.to_payload(),
            "fees": [fee.to_payload() for fee in self.fees],
            "opened_at": self.opened_at.isoformat(),
            "closed_at": (
                None if isinstance(self.closed_at, Absent) else self.closed_at.isoformat()
            ),
            "max_exposure": self.max_exposure.to_payload(),
            "trade_count": self.trade_count,
            "add_count": self.add_count,
            "reduce_count": self.reduce_count,
            "event_ids": list(self.event_ids),
            "calculation_version": self.calculation_version,
            "dust_policy_id": self.dust_policy_id,
            "dust_policy_version": self.dust_policy_version,
            "closed_by_flip": self.closed_by_flip,
            "reconciliation": self.reconciliation.value,
        }


def total_fees(positions: Iterable[Position], asset: AssetCode) -> Money:
    """Fee drag across positions, in one named asset."""
    total = Money.zero(asset)
    for position in positions:
        total = total + position.fees_in(asset)
    return total



