"""What the portfolio is made of, and what it is made of *by*.

Three shapes and one rule. The shapes are `ExposureLine` (one unit of exposure),
`ExposureBreakdown` (the same lines grouped on one axis), and `PortfolioState`
(every line, every breakdown, and the money figures over them). The rule is that
**a figure that cannot be computed is `Absent(reason)` and never a zero**, which
`fmis.portfolio` states at its sharpest: *"a zero makes the total look plausible
and survives for years."*

**`ExposureLine` is deliberately not a `Position`.** A position is the fold of one
market's events in one book, and it holds no account — a book never shares
capacity across accounts, so the fold has no account to name. A portfolio must
report exposure *per account* and *per venue*, so the unit here carries both, and
a line is produced by folding **one account's fills at a time**. That is the
operation `PositionRepository.load_by_owner` already sanctions (*"account narrows
which trades are folded"*), and the consequence is stated rather than hidden: the
book-wide fold over the same market can differ from the sum of its per-account
folds, and `PortfolioState.accounts_share_a_market` names every market where the
two readings are not the same question.

**A line is also what a *proposed* trade reduces to.** One shape for held and
proposed exposure means the arithmetic that produces a portfolio's gross, net and
open risk runs exactly once, and a before/after comparison cannot accidentally
compare two differently-computed numbers. `ExposureSource` keeps the two
distinguishable on the page.

**There is no composite portfolio score here, and there never will be.** `AP`
§15.2: *"a single number would collapse all three strata into one value whose
meaning no one could recover."* Every aggregate in this module is a named money
figure or an explicit pair, and every share is a numerator and a denominator with
the division done at read time.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fmis.accounts import AccountId, Book, MarketId, MarketMode, VenueId
from fmis.money import AssetCode, Money, Quantity, canonical_decimal_text
from fmis.portfolio import MarkQuote
from fmis.positions import PositionDirection
from fmis.provenance import Absent, ValueOrigin
from fmis.records import (
    IDENTIFIER_PATTERN,
    DomainValidationError,
    require_int,
    require_member,
    require_pattern,
    require_text,
    require_tuple_of,
    require_utc,
)
from fmis.snapshotting import TradeDirection

from fmis.portfolio_risk.geometry import (
    RISK_BASIS,
    RiskGeometryError,
    capital_at_risk_of,
)

__all__ = [
    "ExposureSource",
    "ExposureDimension",
    "ExposureLine",
    "PendingCommitment",
    "ExposureEntry",
    "ExposureBreakdown",
    "PortfolioState",
    "direction_of",
    "sum_or_absent",
    "UNCLASSIFIED",
]

#: The key a line whose base asset the owner's classification does not name is
#: filed under. A word rather than an omission: a group breakdown that silently
#: dropped unclassified exposure would read as a fully classified portfolio.
UNCLASSIFIED = "unclassified"


class ExposureSource(Enum):
    """Whether a line is exposure the owner has, or exposure being considered.

    Two members, and mixing them is the failure the enum prevents: a `PROPOSED`
    line inside a *before* state would report a position the owner does not hold,
    which is the one error a portfolio page must never make.
    """

    HELD = "held"
    PROPOSED = "proposed"


class ExposureDimension(Enum):
    """The axes exposure is grouped on. A closed set, because each one is a
    different question and an open string would let two spellings of one axis
    produce two answers.

    Three axes describe *what* is held, and the difference between them is the
    difference between three real questions:

    * `INSTRUMENT` is the full `MarketId` — venue, pair and mode. Counterparty
      risk follows this one.
    * `SYMBOL` is the traded pair, so *"I am long BTCUSDT on two venues"* is one
      concentration rather than two unrelated ones.
    * `ASSET` is the **base asset alone**, and it is the one that answers *"how
      much of this portfolio is a bet on BTC"*. `BTCUSDT` and `BTCUSDC` are two
      symbols and one bet; a portfolio that reported them as unrelated would be
      presenting concentration as diversification, which is the single most
      expensive mistake this package can make.
    """

    ACCOUNT = "account"
    VENUE = "venue"
    BOOK = "book"
    INSTRUMENT = "instrument"
    SYMBOL = "symbol"
    ASSET = "asset"
    DIRECTION = "direction"
    GROUP = "group"


def direction_of(direction: TradeDirection) -> PositionDirection:
    """A plan's or a proposal's side, as the position vocabulary's own member.

    Two enums exist for a reason `fmis.snapshotting` states: `TradeDirection`
    carries `NO_TRADE`, which is a decision not to act and has no exposure. This
    maps the two directional members and refuses the third rather than defaulting
    it to anything.
    """
    require_member(direction, TradeDirection, "direction")
    if direction is TradeDirection.LONG:
        return PositionDirection.LONG
    if direction is TradeDirection.SHORT:
        return PositionDirection.SHORT
    raise DomainValidationError(
        "NO_TRADE is a decision not to act and carries no exposure; it has no "
        "position direction, and mapping it to FLAT would make a declined idea "
        "indistinguishable from a closed position"
    )


@dataclass(frozen=True, slots=True)
class ExposureLine:
    """One unit of exposure: whose, where, which way, how much, and at what risk.

    Every field that could be unknown is `Absent(reason)` rather than optional.
    `entry` is unknown for a holding with no acquisition cost recorded, `stop` for
    one no commitment names a level for, and `mark` for one nothing has valued —
    and each absence propagates into a *named* absent figure rather than a
    silently smaller total.
    """

    account: AccountId
    market: MarketId
    book: Book
    direction: PositionDirection
    quantity: Quantity
    source: ExposureSource
    entry: Decimal | Absent = field(
        default_factory=lambda: Absent("no acquisition price is recorded")
    )
    stop: Decimal | Absent = field(
        default_factory=lambda: Absent("no commitment records a stop for this exposure")
    )
    mark: MarkQuote | Absent = field(
        default_factory=lambda: Absent("no mark was supplied for this market")
    )
    origin_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.account, AccountId):
            raise TypeError("account must be an AccountId")
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        require_member(self.book, Book, "book")
        require_member(self.direction, PositionDirection, "direction")
        if self.direction is PositionDirection.FLAT:
            raise DomainValidationError(
                "a flat line is not exposure; a closed position leaves the "
                "portfolio rather than sitting in it at zero"
            )
        if not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be a Quantity")
        if self.quantity.amount <= 0:
            raise DomainValidationError(
                f"quantity must be a positive magnitude, got {self.quantity}; the "
                "direction is already carried by `direction`"
            )
        if self.quantity.asset != self.market.base_asset:
            raise DomainValidationError(
                f"quantity is denominated in {self.quantity.asset} but the market "
                f"trades {self.market.base_asset} as its base asset"
            )
        require_member(self.source, ExposureSource, "source")
        for name in ("entry", "stop"):
            value = getattr(self, name)
            if isinstance(value, Absent):
                continue
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal or Absent")
            if value <= 0:
                raise DomainValidationError(f"{name} must be positive, got {value}")
            object.__setattr__(self, name, Decimal(canonical_decimal_text(value)))
        if not isinstance(self.mark, (MarkQuote, Absent)):
            raise TypeError("mark must be a MarkQuote or Absent")
        require_tuple_of(self.origin_ids, str, "origin_ids")

    # -- identity on each axis ----------------------------------------------

    @property
    def origin(self) -> ValueOrigin:
        """`MEASURED` for a held line, `ASSERTED` for a proposed one.

        A proposal's entry, stop and size are stated by the owner and can simply
        be wrong; a held line's are folded from the ledger. A surface that
        rendered both the same way would be a lie of omission.
        """
        return (
            ValueOrigin.MEASURED
            if self.source is ExposureSource.HELD
            else ValueOrigin.ASSERTED
        )

    @property
    def venue(self) -> VenueId:
        return self.market.venue

    @property
    def mode(self) -> MarketMode:
        return self.market.mode

    def key_on(self, dimension: ExposureDimension) -> str:
        """The bucket this line falls in on one axis.

        `GROUP` is deliberately absent: a line belongs to as many groups as the
        owner's classification names, so it has no single key and
        `ExposureBreakdown.by_group` takes the map rather than asking a line.
        """
        require_member(dimension, ExposureDimension, "dimension")
        if dimension is ExposureDimension.ACCOUNT:
            return self.account.value
        if dimension is ExposureDimension.VENUE:
            return self.venue.value
        if dimension is ExposureDimension.BOOK:
            return self.book.value
        if dimension is ExposureDimension.INSTRUMENT:
            return self.market.value
        if dimension is ExposureDimension.SYMBOL:
            return self.market.pair_symbol
        if dimension is ExposureDimension.ASSET:
            return self.market.base_asset.code
        if dimension is ExposureDimension.DIRECTION:
            return self.direction.value
        raise DomainValidationError(
            "a line has no single group key: an asset may belong to several of "
            "the owner's classifications at once, so group exposure is computed "
            "from the classification map rather than read off a line"
        )

    @property
    def scope(self) -> tuple[str, str, str]:
        """`(account, market, book)` — the triple one open position lives in.

        The match key for duplicate and scale-in detection. Book is part of it
        because books never share capacity: the same market held in `SWING` and
        in `INVESTING` is two positions and not one bigger one.
        """
        return (self.account.value, self.market.value, self.book.value)

    # -- money, or the reason there is none ---------------------------------

    def notional(self, base: AssetCode) -> Money | Absent:
        """`|quantity| × mark`, unsigned, or why it cannot be stated."""
        if isinstance(self.mark, Absent):
            return Absent(
                f"no mark for {self.market.value}: {self.mark.reason}"
            )
        if self.mark.quote_asset != base:
            return Absent(
                f"{self.market.value} is marked in {self.mark.quote_asset} and no "
                f"rate to {base} was supplied"
            )
        return self.quantity.value_at(self.mark.price, base)

    def signed_notional(self, base: AssetCode) -> Money | Absent:
        """Notional with the direction's sign — negative while short.

        A separate method rather than a flag on one, because gross and net answer
        two different questions and a caller that could get either from one call
        by passing a boolean will eventually pass the wrong one.
        """
        value = self.notional(base)
        if isinstance(value, Absent):
            return value
        return value if self.direction is PositionDirection.LONG else -value

    def cost_basis(self, base: AssetCode) -> Money | Absent:
        """`|quantity| × entry` — what the exposure was opened at."""
        if isinstance(self.entry, Absent):
            return Absent(
                f"no entry price for {self.market.value}: {self.entry.reason}"
            )
        if self.market.quote_asset != base:
            return Absent(
                f"{self.market.value} is quoted in {self.market.quote_asset} and "
                f"no rate to {base} was supplied"
            )
        return self.quantity.value_at(self.entry, base)

    def capital_at_risk(self, base: AssetCode) -> Money | Absent:
        """`risk distance × quantity`, or the reason there is no risk distance.

        `Absent` rather than a raise, because one unmeasurable position must not
        stop a portfolio from reporting the rest — and rather than a zero,
        because a position with no recorded stop is the *most* dangerous kind and
        a zero would file it as the safest.
        """
        if isinstance(self.entry, Absent):
            return Absent(
                f"no entry price for {self.market.value}: {self.entry.reason}"
            )
        if isinstance(self.stop, Absent):
            return Absent(
                f"no stop for {self.market.value}: {self.stop.reason}"
            )
        if self.market.quote_asset != base:
            return Absent(
                f"{self.market.value} is quoted in {self.market.quote_asset} and "
                f"no rate to {base} was supplied"
            )
        try:
            return capital_at_risk_of(
                self.direction,
                entry=self.entry,
                stop=self.stop,
                quantity=self.quantity,
                quote_asset=base,
            )
        except RiskGeometryError as error:
            return Absent(str(error))

    @property
    def risk_basis(self) -> str:
        return RISK_BASIS

    def with_quantity(self, quantity: Quantity) -> ExposureLine:
        """The same exposure, resized. Used to model a reduction, never stored."""
        return ExposureLine(
            account=self.account,
            market=self.market,
            book=self.book,
            direction=self.direction,
            quantity=quantity,
            source=self.source,
            entry=self.entry,
            stop=self.stop,
            mark=self.mark,
            origin_ids=self.origin_ids,
        )

    def to_payload(self) -> dict[str, Any]:
        """For export and rendering. **Nothing reads this back.**

        There is no `from_payload`, following `Position`'s own precedent: a line
        is folded from the ledger, and a decoder here would be an invitation to
        persist a projection and let it drift from the events behind it.
        """
        return {
            "account": self.account.value,
            "market": self.market.to_payload(),
            "book": self.book.value,
            "direction": self.direction.value,
            "quantity": self.quantity.to_payload(),
            "source": self.source.value,
            "entry": (
                {"absent": self.entry.to_payload()}
                if isinstance(self.entry, Absent)
                else {"value": canonical_decimal_text(self.entry)}
            ),
            "stop": (
                {"absent": self.stop.to_payload()}
                if isinstance(self.stop, Absent)
                else {"value": canonical_decimal_text(self.stop)}
            ),
            "mark": (
                {"absent": self.mark.to_payload()}
                if isinstance(self.mark, Absent)
                else {"value": self.mark.to_payload()}
            ),
            "origin_ids": list(self.origin_ids),
        }


@dataclass(frozen=True, slots=True)
class PendingCommitment:
    """A commitment with nothing filled against it, and what it cannot tell us.

    Carried on the state rather than dropped, because *"I have four plans open
    and no positions"* is a real portfolio fact. What it deliberately does not
    carry is a capital figure: `TradePlan` states a stop and targets and **no
    intended size**, so the capital a pending commitment would consume is not
    derivable from anything stored. `PortfolioState.reserved_capital` says so in
    those words rather than reserving zero.
    """

    plan_id: str
    market: MarketId
    book: Book
    direction: TradeDirection
    stop: Decimal
    committed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", require_text(self.plan_id, "plan_id"))
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        require_member(self.book, Book, "book")
        require_member(self.direction, TradeDirection, "direction")
        if not isinstance(self.stop, Decimal):
            raise TypeError("stop must be a Decimal")
        object.__setattr__(self, "stop", Decimal(canonical_decimal_text(self.stop)))
        object.__setattr__(
            self, "committed_at", require_utc(self.committed_at, "committed_at")
        )


@dataclass(frozen=True, slots=True)
class ExposureEntry:
    """One bucket on one axis, as figures and a count — never as a percentage.

    The share is computed by `ExposureBreakdown`, which holds the denominator.
    Keeping the two apart is `AllocationEntry`'s own rule applied here: a stored
    percentage is a number nobody can reconcile against the pair it came from.
    """

    key: str
    gross: Money | Absent
    net: Money | Absent
    open_risk: Money | Absent
    line_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", require_text(self.key, "key"))
        for name in ("gross", "net", "open_risk"):
            value = getattr(self, name)
            if not isinstance(value, (Money, Absent)):
                raise TypeError(f"{name} must be a Money or Absent")
        require_int(self.line_count, "line_count", minimum=1)

    def to_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "gross": _amount_payload(self.gross),
            "net": _amount_payload(self.net),
            "open_risk": _amount_payload(self.open_risk),
            "line_count": self.line_count,
        }


@dataclass(frozen=True, slots=True)
class ExposureBreakdown:
    """The same lines, grouped on one axis, with the totals the shares divide by.

    **The denominator is a field.** A concentration is `this bucket ÷ the whole`,
    and holding the whole beside the parts is what lets a reader check the
    division instead of trusting it — and what makes a numerator/denominator
    transposition a visible wrong answer rather than a plausible one.
    """

    dimension: ExposureDimension
    entries: tuple[ExposureEntry, ...]
    total_gross: Money | Absent
    total_open_risk: Money | Absent
    #: Assets the classification map files in more than one group. Only ever
    #: non-empty on a `GROUP` breakdown, where the buckets deliberately overlap
    #: and therefore sum to **more** than the portfolio's gross exposure.
    overlapping_keys: tuple[str, ...] = ()
    classification_version: str | Absent = field(
        default_factory=lambda: Absent("this axis needs no classification")
    )

    def __post_init__(self) -> None:
        require_member(self.dimension, ExposureDimension, "dimension")
        require_tuple_of(self.entries, ExposureEntry, "entries")
        keys = [entry.key for entry in self.entries]
        if len(set(keys)) != len(keys):
            raise DomainValidationError(
                "a key appears twice in one breakdown; one bucket, one figure, or "
                "a share has two answers"
            )
        for name in ("total_gross", "total_open_risk"):
            value = getattr(self, name)
            if not isinstance(value, (Money, Absent)):
                raise TypeError(f"{name} must be a Money or Absent")
        require_tuple_of(self.overlapping_keys, str, "overlapping_keys")
        if self.overlapping_keys and self.dimension is not ExposureDimension.GROUP:
            raise DomainValidationError(
                f"only a group breakdown overlaps; {self.dimension.value} buckets "
                "are disjoint and a line falls in exactly one"
            )
        if not isinstance(self.classification_version, (str, Absent)):
            raise TypeError("classification_version must be a str or Absent")
        if isinstance(self.classification_version, str):
            object.__setattr__(
                self,
                "classification_version",
                require_text(self.classification_version, "classification_version"),
            )
        if (
            self.dimension is ExposureDimension.GROUP
            and isinstance(self.classification_version, Absent)
        ):
            raise DomainValidationError(
                "a group breakdown states the classification version it was "
                "computed under; two versions produce visibly different "
                "allocations rather than silently contradictory ones"
            )

    @property
    def origin(self) -> ValueOrigin:
        """`MEASURED` on every axis but `GROUP`, which reads an owner's mapping."""
        return (
            ValueOrigin.POLICY_DERIVED
            if self.dimension is ExposureDimension.GROUP
            else ValueOrigin.MEASURED
        )

    def entry(self, key: str) -> ExposureEntry | Absent:
        wanted = require_text(key, "key")
        for candidate in self.entries:
            if candidate.key == wanted:
                return candidate
        return Absent(
            f"nothing in this portfolio falls under {self.dimension.value} "
            f"{wanted!r}"
        )

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(entry.key for entry in self.entries)

    def gross_share(self, key: str) -> Decimal | Absent:
        """`bucket gross ÷ total gross` — divided here, stored nowhere."""
        return _share(self.entry(key), "gross", self.total_gross)

    def risk_share(self, key: str) -> Decimal | Absent:
        """`bucket open risk ÷ total open risk` — divided here, stored nowhere."""
        return _share(self.entry(key), "open_risk", self.total_open_risk)

    def to_payload(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "entries": [entry.to_payload() for entry in self.entries],
            "total_gross": _amount_payload(self.total_gross),
            "total_open_risk": _amount_payload(self.total_open_risk),
            "overlapping_keys": list(self.overlapping_keys),
            "classification_version": (
                {"absent": self.classification_version.to_payload()}
                if isinstance(self.classification_version, Absent)
                else {"value": self.classification_version}
            ),
        }


@dataclass(frozen=True, slots=True)
class PortfolioState:
    """The whole portfolio at one instant — folded on demand, stored never.

    A **rebuildable projection** in the architecture's §24.3 sense: delete it,
    recompute it from the resolved ledger and the same supplied marks, and the
    result is equal. `PortfolioRepository` holds the *frozen* observations
    (`PortfolioSnapshot`); this is the live reading, and the two are different
    objects on purpose — a snapshot must never be recomputed from live data, and
    this must never be stored.

    **Every money figure is `Money | Absent`.** Equity, cash and marks are all
    supplied by the caller, because this package reaches no venue and ingests no
    price. Nothing here substitutes a plausible value for a missing one.
    """

    portfolio_id: str
    base_currency: AssetCode
    as_of: datetime
    books_covered: tuple[Book, ...]
    lines: tuple[ExposureLine, ...]
    pending: tuple[PendingCommitment, ...]
    breakdowns: tuple[ExposureBreakdown, ...]
    equity: Money | Absent
    cash: Money | Absent
    gross_exposure: Money | Absent
    net_exposure: Money | Absent
    long_exposure: Money | Absent
    short_exposure: Money | Absent
    open_risk: Money | Absent
    deployed_capital: Money | Absent
    reserved_capital: Money | Absent
    #: When the equity and cash figures were **true**, which is not when this
    #: state was built. `MarkQuote.as_of` exists for the identical reason one
    #: layer down: *"a mark read at 22:00 and frozen into a 22:15 snapshot is
    #: fifteen minutes stale, and a reader is entitled to see that rather than
    #: infer it."* Every percent-of-equity limit is measured against this
    #: number, so a six-week-old equity silently reinterpreting the 2 % rule is
    #: exactly the failure the field prevents.
    equity_as_of: datetime | Absent = field(
        default_factory=lambda: Absent("no valuation instant was stated")
    )
    #: Markets whose fills sit in more than one account. Named because a
    #: per-account fold and a book-wide fold answer different questions there,
    #: and a reader comparing this page to `fmits trade show` is entitled to know
    #: which markets the two can legitimately disagree about.
    accounts_share_a_market: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "portfolio_id",
            require_pattern(self.portfolio_id, IDENTIFIER_PATTERN, "portfolio_id"),
        )
        if not isinstance(self.base_currency, AssetCode):
            object.__setattr__(self, "base_currency", AssetCode(self.base_currency))
        object.__setattr__(self, "as_of", require_utc(self.as_of, "as_of"))
        require_tuple_of(self.books_covered, Book, "books_covered", minimum_length=1)
        if len(set(self.books_covered)) != len(self.books_covered):
            raise DomainValidationError("books_covered must not repeat a book")
        require_tuple_of(self.lines, ExposureLine, "lines")
        for line in self.lines:
            if line.book not in self.books_covered:
                raise DomainValidationError(
                    f"a line in book {line.book.value} sits in a state covering "
                    f"{sorted(book.value for book in self.books_covered)}; an "
                    "aggregate states which books it covers and holds nothing else"
                )
        require_tuple_of(self.pending, PendingCommitment, "pending")
        require_tuple_of(self.breakdowns, ExposureBreakdown, "breakdowns")
        dimensions = [breakdown.dimension for breakdown in self.breakdowns]
        if len(set(dimensions)) != len(dimensions):
            raise DomainValidationError("an axis must not be broken down twice")
        if not isinstance(self.equity_as_of, (datetime, Absent)):
            raise TypeError("equity_as_of must be a datetime or Absent")
        if isinstance(self.equity_as_of, datetime):
            object.__setattr__(
                self, "equity_as_of", require_utc(self.equity_as_of, "equity_as_of")
            )
            if self.equity_as_of > self.as_of:
                raise DomainValidationError(
                    f"the equity figure is dated {self.equity_as_of.isoformat()}, "
                    f"after the reading at {self.as_of.isoformat()}; a valuation "
                    "from the future is not a valuation"
                )
        for name in (
            "equity",
            "cash",
            "gross_exposure",
            "net_exposure",
            "long_exposure",
            "short_exposure",
            "open_risk",
            "deployed_capital",
            "reserved_capital",
        ):
            value = getattr(self, name)
            if not isinstance(value, (Money, Absent)):
                raise TypeError(f"{name} must be a Money or Absent")
            if isinstance(value, Money) and value.asset != self.base_currency:
                raise DomainValidationError(
                    f"{name} is stated in {value.asset} but this portfolio's base "
                    f"currency is {self.base_currency}"
                )
        require_tuple_of(
            self.accounts_share_a_market, str, "accounts_share_a_market"
        )

    # -- projections ---------------------------------------------------------

    @property
    def origin(self) -> ValueOrigin:
        """`MEASURED` over the resolved ledger and the marks it was handed."""
        return ValueOrigin.MEASURED

    @property
    def is_empty(self) -> bool:
        """No open exposure. **Not** the same as knowing the owner holds nothing."""
        return not self.lines

    @property
    def open_position_count(self) -> int:
        return len(self.lines)

    @property
    def pending_count(self) -> int:
        return len(self.pending)

    @property
    def held_lines(self) -> tuple[ExposureLine, ...]:
        return tuple(
            line for line in self.lines if line.source is ExposureSource.HELD
        )

    @property
    def proposed_lines(self) -> tuple[ExposureLine, ...]:
        return tuple(
            line for line in self.lines if line.source is ExposureSource.PROPOSED
        )

    @property
    def equity_staleness(self) -> Any:
        """How old the equity figure is at this reading, or why that is unknown.

        A `timedelta`, computed here and stored nowhere. Zero is a legitimate
        answer and means the valuation is the reading's own instant.
        """
        if isinstance(self.equity_as_of, Absent):
            return Absent(
                f"the equity figure states no instant: {self.equity_as_of.reason}"
            )
        return self.as_of - self.equity_as_of

    @property
    def available_capital(self) -> Money | Absent:
        """`cash − reserved`. A subtraction, computed here and stored nowhere."""
        if isinstance(self.cash, Absent):
            return Absent(f"cash is not known: {self.cash.reason}")
        if isinstance(self.reserved_capital, Absent):
            return Absent(
                f"reserved capital is not known: {self.reserved_capital.reason}"
            )
        return self.cash - self.reserved_capital

    @property
    def leverage(self) -> Decimal | Absent:
        """`gross ÷ equity` — the pair divided at read time, never a stored ratio."""
        if isinstance(self.gross_exposure, Absent):
            return Absent(
                f"gross exposure is not known: {self.gross_exposure.reason}"
            )
        if isinstance(self.equity, Absent):
            return Absent(f"equity is not known: {self.equity.reason}")
        if self.equity.amount <= 0:
            return Absent(
                f"equity is {self.equity}, so leverage is undefined rather than "
                "large"
            )
        return self.gross_exposure.amount / self.equity.amount

    def breakdown(self, dimension: ExposureDimension) -> ExposureBreakdown | Absent:
        require_member(dimension, ExposureDimension, "dimension")
        for candidate in self.breakdowns:
            if candidate.dimension is dimension:
                return candidate
        return Absent(
            f"this state was not broken down by {dimension.value}"
        )

    def lines_in_scope(self, scope: tuple[str, str, str]) -> tuple[ExposureLine, ...]:
        """Every line in one `(account, market, book)` triple."""
        return tuple(line for line in self.lines if line.scope == scope)

    def lines_for_symbol(self, symbol: str) -> tuple[ExposureLine, ...]:
        wanted = require_text(symbol, "symbol").upper()
        return tuple(
            line
            for line in self.lines
            if line.market.pair_symbol.upper() == wanted
        )

    def lines_for_asset(self, asset: AssetCode | str) -> tuple[ExposureLine, ...]:
        """Every line whose **base asset** is this one, whatever it is quoted in.

        `BTCUSDT` and `BTCUSDC` are two symbols and one bet, and this is the
        method that says so.
        """
        wanted = asset if isinstance(asset, AssetCode) else AssetCode(asset)
        return tuple(
            line for line in self.lines if line.market.base_asset == wanted
        )

    @property
    def unmarked(self) -> tuple[ExposureLine, ...]:
        return tuple(line for line in self.lines if isinstance(line.mark, Absent))

    @property
    def unstopped(self) -> tuple[ExposureLine, ...]:
        """Open exposure no commitment records a stop for.

        The single most useful list on this object, and the reason `open_risk`
        is `Absent` rather than a smaller number when it is non-empty.
        """
        return tuple(line for line in self.lines if isinstance(line.stop, Absent))

    @property
    def risk_basis(self) -> str:
        return RISK_BASIS

    def to_payload(self) -> dict[str, Any]:
        """For export and rendering. There is no decoder, by design."""
        return {
            "portfolio_id": self.portfolio_id,
            "base_currency": self.base_currency.code,
            "as_of": self.as_of.isoformat(),
            "books_covered": [book.value for book in self.books_covered],
            "lines": [line.to_payload() for line in self.lines],
            "pending": [
                {
                    "plan_id": item.plan_id,
                    "market": item.market.to_payload(),
                    "book": item.book.value,
                    "direction": item.direction.value,
                    "stop": canonical_decimal_text(item.stop),
                    "committed_at": item.committed_at.isoformat(),
                }
                for item in self.pending
            ],
            "breakdowns": [
                breakdown.to_payload() for breakdown in self.breakdowns
            ],
            "equity": _amount_payload(self.equity),
            "equity_as_of": (
                {"absent": self.equity_as_of.to_payload()}
                if isinstance(self.equity_as_of, Absent)
                else {"value": self.equity_as_of.isoformat()}
            ),
            "cash": _amount_payload(self.cash),
            "gross_exposure": _amount_payload(self.gross_exposure),
            "net_exposure": _amount_payload(self.net_exposure),
            "long_exposure": _amount_payload(self.long_exposure),
            "short_exposure": _amount_payload(self.short_exposure),
            "open_risk": _amount_payload(self.open_risk),
            "deployed_capital": _amount_payload(self.deployed_capital),
            "reserved_capital": _amount_payload(self.reserved_capital),
            "available_capital": _amount_payload(self.available_capital),
            "accounts_share_a_market": list(self.accounts_share_a_market),
            "risk_basis": self.risk_basis,
        }


def _amount_payload(value: Money | Absent) -> dict[str, Any]:
    if isinstance(value, Absent):
        return {"absent": value.to_payload()}
    return {"value": value.to_payload()}


def _share(
    entry: ExposureEntry | Absent, attribute: str, total: Money | Absent
) -> Decimal | Absent:
    """`part ÷ whole`, with every way it can fail to exist named separately."""
    if isinstance(entry, Absent):
        return entry
    part = getattr(entry, attribute)
    if isinstance(part, Absent):
        return Absent(f"the {attribute} of {entry.key!r} is not known: {part.reason}")
    if isinstance(total, Absent):
        return Absent(f"the portfolio's total {attribute} is not known: {total.reason}")
    if total.amount == 0:
        return Absent(
            f"the portfolio's total {attribute} is zero, so a share of it is "
            "undefined rather than zero"
        )
    return part.amount / total.amount


def sum_or_absent(
    values: Iterable[Money | Absent], *, asset: AssetCode, subject: str
) -> Money | Absent:
    """Add money figures, refusing a total that silently omits a missing one.

    `PortfolioSnapshot.total_value`'s rule, generalized: *"a partial total is the
    most dangerous number a portfolio page can show, because it looks
    complete."* Every unknown contributor is named in the reason, so a reader
    learns which position broke the figure rather than only that it is missing.
    """
    total = Money.zero(asset)
    reasons: list[str] = []
    for value in values:
        if isinstance(value, Absent):
            reasons.append(value.reason)
            continue
        total = total + value
    if reasons:
        return Absent(f"{subject} cannot be totalled: " + "; ".join(sorted(set(reasons))))
    return total
