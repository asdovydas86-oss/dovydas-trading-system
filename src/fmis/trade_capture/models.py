"""Value types for trade capture — what was committed to, and what filled it.

A **swing trade** is not one record in this domain and modelling it as one would
undo three milestones of separation. It is a `TradePlan` (what the owner
committed to), one or more `Trade` fills (what happened to money), and whatever
the owner wrote about it (`JournalEntry`). `TradeView` is the read-time
assembly of the three, built on every call and stored nowhere — which is what
keeps it from becoming a fourth place any of those facts lives.

**`CaptureStatus` is derived from the fills and is never stored.** `PLANNED`
means a commitment with nothing filled against it; `OPEN` and `CLOSED` come from
the position fold, under the owner's dust policy. A stored status would be a
second answer to *"am I in this trade"*, and the first `Correction` would make
the two disagree.

**Every absence carries its reason.** `Absent(reason)` rather than `None`
throughout, for the reason `AP` §14.3 gives concretely: a missing figure stored
as zero *"makes the total look plausible and survives for years"*. A trade with
no target has no risk/reward — not a risk/reward of zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from fmis.accounts import Book, MarketId
from fmis.journal import TradeJournal
from fmis.ledger import TradeSide
from fmis.money import Money, Quantity
from fmis.plan import TradePlan
from fmis.positions import Position
from fmis.provenance import Absent
from fmis.records import (
    require_int,
    require_member,
    require_text,
    require_tuple_of,
    require_utc,
)
from fmis.snapshotting import RiskRewardReading, TradeDirection

__all__ = [
    "TradeCaptureError",
    "CaptureRefusedError",
    "TradeNotFoundError",
    "CaptureStatus",
    "CaptureWarning",
    "WrittenRecord",
    "FillLine",
    "TradeView",
    "TradeRow",
    "TradeFilters",
    "TradeListing",
    "CaptureOutcome",
]


class TradeCaptureError(Exception):
    """Base class for every trade-capture failure.

    Follows the package-error convention `TodayError`, `WorkspaceError` and
    `PersistenceError` established elsewhere, so the CLI can catch this layer's
    failures as a group and map them to one exit code.
    """


class CaptureRefusedError(TradeCaptureError):
    """The owner asked for something the records cannot represent.

    Its own class because every instance of it is **actionable by the owner** and
    none of them is a defect: a stop on the wrong side of the entry, a close
    larger than the open exposure, a plan that does not exist. The message names
    the two values that disagree, because a refusal the owner cannot act on is
    the same as a crash.
    """


class TradeNotFoundError(TradeCaptureError):
    """No plan with that id is in this store.

    Separate from `CaptureRefusedError` so the CLI can say *"not found"* rather
    than *"refused"* — a distinction the owner needs when they have mistyped an
    id rather than mis-stated a trade.
    """


class CaptureStatus(Enum):
    """Where a recorded trade stands. **Derived from the fills, stored never.**

    Three members, and `PLANNED` is not decoration: a commitment with nothing
    filled against it is a real and useful state — it is the plan the owner made
    and did not take — and collapsing it into `CLOSED` would make *"how often do
    I plan and not act"* unanswerable.
    """

    PLANNED = "planned"
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True, order=True)
class CaptureWarning:
    """One qualification on a value this view reports.

    A code and a statement, and nothing else. There is no severity: this layer
    produces no ranking, and a severity field would be the first place one
    appeared.
    """

    code: str
    statement: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", require_text(self.code, "code"))
        object.__setattr__(self, "statement", require_text(self.statement, "statement"))


@dataclass(frozen=True, slots=True)
class WrittenRecord:
    """One record a capture command put in the store — or found already there.

    **`created` is reported rather than hidden.** Re-running `fmits trade record`
    after a crash resolves to `created=False` on every record, because the store
    is idempotent by content. A surface that printed "recorded" either way would
    teach the owner that a second run creates a second trade, which is exactly
    the belief the content-derived `event_id` exists to make false.
    """

    kind: str
    record_id: str
    created: bool
    relative_path: str

    def __post_init__(self) -> None:
        for name in ("kind", "record_id", "relative_path"):
            object.__setattr__(self, name, require_text(getattr(self, name), name))
        if not isinstance(self.created, bool):
            raise TypeError("created must be a bool")


@dataclass(frozen=True, slots=True)
class FillLine:
    """One resolved fill against a plan, flattened for reading.

    Built from a `ResolvedTrade` and never from a raw `Trade`: reading the ledger
    without applying supersession is how a surface eventually reports a value the
    owner already corrected. `was_corrected` carries that fact forward so the
    page can say so.
    """

    event_id: str
    occurred_at: datetime
    side: TradeSide
    quantity: Quantity
    price: Decimal
    fee: Money
    account: str
    was_corrected: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", require_text(self.event_id, "event_id"))
        object.__setattr__(
            self, "occurred_at", require_utc(self.occurred_at, "occurred_at")
        )
        require_member(self.side, TradeSide, "side")
        if not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be a Quantity")
        if not isinstance(self.price, Decimal):
            raise TypeError("price must be a Decimal")
        if not isinstance(self.fee, Money):
            raise TypeError("fee must be a Money")
        object.__setattr__(self, "account", require_text(self.account, "account"))
        if not isinstance(self.was_corrected, bool):
            raise TypeError("was_corrected must be a bool")

    @property
    def consideration(self) -> Money:
        """`quantity × price` — a product, shown rather than stored."""
        return self.quantity.value_at(self.price, self.fee.asset)


@dataclass(frozen=True, slots=True)
class TradeView:
    """One recorded swing trade, assembled from the three records that hold it.

    A **projection**. Deleting it and rebuilding it from the plan, the ledger and
    the journal produces an equal value, which is the same durability
    classification `Position` carries and for the same reason.
    """

    plan: TradePlan
    status: CaptureStatus
    fills: tuple[FillLine, ...]
    position: Position | Absent
    entry_price: Decimal | Absent
    capital_at_risk: Money | Absent
    planned_risk_reward: RiskRewardReading | Absent
    journal: TradeJournal
    accounts: tuple[str, ...]
    warnings: tuple[CaptureWarning, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.plan, TradePlan):
            raise TypeError("plan must be a TradePlan")
        require_member(self.status, CaptureStatus, "status")
        require_tuple_of(self.fills, FillLine, "fills")
        if not isinstance(self.position, (Position, Absent)):
            raise TypeError("position must be a Position or Absent")
        if not isinstance(self.entry_price, (Decimal, Absent)):
            raise TypeError("entry_price must be a Decimal or Absent")
        if not isinstance(self.capital_at_risk, (Money, Absent)):
            raise TypeError("capital_at_risk must be a Money or Absent")
        if not isinstance(self.planned_risk_reward, (RiskRewardReading, Absent)):
            raise TypeError("planned_risk_reward must be a RiskRewardReading or Absent")
        if not isinstance(self.journal, TradeJournal):
            raise TypeError("journal must be a TradeJournal")
        require_tuple_of(self.accounts, str, "accounts")
        require_tuple_of(self.warnings, CaptureWarning, "warnings")
        if (self.status is CaptureStatus.PLANNED) != (not self.fills):
            raise ValueError(
                "PLANNED means nothing has filled against this commitment; a "
                "status and a fill list that disagree would put the same fact in "
                "two places"
            )

    @property
    def plan_id(self) -> str:
        return self.plan.plan_id

    @property
    def realized_pnl_net(self) -> Money | Absent:
        """The fold's own figure, forwarded. **Not a taxable gain**, ever."""
        if isinstance(self.position, Absent):
            return Absent("nothing has filled against this commitment")
        return self.position.realized_pnl_net

    @property
    def open_quantity(self) -> Quantity | Absent:
        if isinstance(self.position, Absent):
            return Absent("nothing has filled against this commitment")
        return self.position.net_quantity


@dataclass(frozen=True, slots=True)
class TradeRow:
    """One line of `fmits trade list`. Every figure on it is already computed."""

    plan_id: str
    committed_at: datetime
    market: MarketId
    book: Book
    direction: TradeDirection
    status: CaptureStatus
    stop: Decimal
    first_target: Decimal | Absent
    accounts: tuple[str, ...]
    capital_at_risk: Money | Absent
    realized_pnl_net: Money | Absent

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", require_text(self.plan_id, "plan_id"))
        object.__setattr__(
            self, "committed_at", require_utc(self.committed_at, "committed_at")
        )
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        require_member(self.book, Book, "book")
        require_member(self.direction, TradeDirection, "direction")
        require_member(self.status, CaptureStatus, "status")
        if not isinstance(self.stop, Decimal):
            raise TypeError("stop must be a Decimal")
        if not isinstance(self.first_target, (Decimal, Absent)):
            raise TypeError("first_target must be a Decimal or Absent")
        require_tuple_of(self.accounts, str, "accounts")
        for name in ("capital_at_risk", "realized_pnl_net"):
            if not isinstance(getattr(self, name), (Money, Absent)):
                raise TypeError(f"{name} must be a Money or Absent")


@dataclass(frozen=True, slots=True)
class TradeFilters:
    """What `fmits trade list` was asked to include.

    Carried onto the listing and printed with it. A filtered page that does not
    say what it filtered on is a page a reader will mistake for the whole set —
    the same reason `SearchCriteria` exists one layer down, applied to a surface.
    """

    status: CaptureStatus | None = None
    symbol: str | None = None
    account: str | None = None
    direction: TradeDirection | None = None
    since: datetime | None = None
    until: datetime | None = None

    def __post_init__(self) -> None:
        if self.status is not None:
            require_member(self.status, CaptureStatus, "status")
        if self.direction is not None:
            require_member(self.direction, TradeDirection, "direction")
        for name in ("symbol", "account"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_text(value, name))
        for name in ("since", "until"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_utc(value, name))
        if self.since is not None and self.until is not None and self.until < self.since:
            raise ValueError(
                f"until {self.until.isoformat()} precedes since "
                f"{self.since.isoformat()}"
            )

    @property
    def stated(self) -> tuple[tuple[str, str], ...]:
        """The filters actually applied, as `(axis, value)` pairs, in a fixed order."""
        pairs: list[tuple[str, str]] = []
        for label, value in (
            ("status", self.status),
            ("symbol", self.symbol),
            ("account", self.account),
            ("direction", self.direction),
        ):
            if value is not None:
                pairs.append((label, getattr(value, "value", value)))
        for label, moment in (("since", self.since), ("until", self.until)):
            if moment is not None:
                pairs.append((label, moment.isoformat()))
        return tuple(pairs)


@dataclass(frozen=True, slots=True)
class TradeListing:
    """Every matching row, plus what was filtered and how much was excluded.

    `total` is the count **before** filtering, so a listing can never read as the
    whole store when it is not. A page that shows three rows and does not say
    forty exist is the cheapest way to make an owner believe they are flat.
    """

    rows: tuple[TradeRow, ...]
    filters: TradeFilters
    total: int

    def __post_init__(self) -> None:
        require_tuple_of(self.rows, TradeRow, "rows")
        if not isinstance(self.filters, TradeFilters):
            raise TypeError("filters must be a TradeFilters")
        require_int(self.total, "total", minimum=0)
        if len(self.rows) > self.total:
            raise ValueError(
                f"{len(self.rows)} rows shown out of a stated total of {self.total}"
            )

    @property
    def excluded(self) -> int:
        return self.total - len(self.rows)


@dataclass(frozen=True, slots=True)
class CaptureOutcome:
    """What a write command wrote, and the trade as it stands afterwards."""

    action: str
    written: tuple[WrittenRecord, ...]
    view: TradeView

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", require_text(self.action, "action"))
        require_tuple_of(self.written, WrittenRecord, "written", minimum_length=1)
        if not isinstance(self.view, TradeView):
            raise TypeError("view must be a TradeView")

    @property
    def plan_id(self) -> str:
        return self.view.plan_id

    @property
    def was_already_stored(self) -> bool:
        """Whether every record this command wrote was already there, byte for byte."""
        return not any(record.created for record in self.written)
